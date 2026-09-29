#!/usr/bin/env python3
"""Targeted Gemini 3 Pro reruns for original agent-error benchmark rows.

This wrapper only selects rows whose original outcome is ``agent_error`` from
the Gemini 3 Pro full140 records, then delegates execution to
``run_pair_benchmarks.py`` with isolated ports and an isolated record root.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
DEFAULT_BASE_ROOT = RECORD_ROOT / "gemini_litellm_full140_20260517"
SOURCE_MODEL_SLUG = "gemini_3_pro_image_preview_temp0_top_p1_seed12345"
MODEL_KEY_TO_SLUG = {
    "gemini3pro_image_preview": "gemini_3_pro_image_preview_temp0_top_p1_seed12345",
    "gemini31pro_preview": "gemini_3_1_pro_preview_temp0_top_p1_seed12345",
}
PAIR_RUNNER = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_pair_benchmarks.py"
QWEN36_RECORD_ROOT = RECORD_ROOT / "qwen_plus_litellm_full140_20260518"

SCENARIOS: dict[str, dict[str, Any]] = {
    "public39": {
        "order": 0,
        "task_count": 39,
        "ports": {"official": 18226, "clean": 18326},
    },
    "business47": {
        "order": 1,
        "task_count": 47,
        "ports": {"official": 18216, "clean": 18316},
    },
    "environment35": {
        "order": 2,
        "task_count": 35,
        "ports": {"official": 18233, "clean": 18333},
    },
    "health19": {
        "order": 3,
        "task_count": 19,
        "ports": {"official": 18237, "clean": 18337},
    },
}
SCENARIO_ORDER = ["public39", "business47", "environment35", "health19"]
BENCHMARKS = ["official", "clean"]


def utcish_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"Missing JSONL file: {path}")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_benchmarks(raw: str) -> list[str]:
    if raw.strip().lower() == "both":
        return list(BENCHMARKS)
    items = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in items if item not in BENCHMARKS]
    if unknown:
        raise RuntimeError(f"Unknown benchmark(s): {', '.join(unknown)}")
    if not items:
        raise RuntimeError("At least one benchmark must be selected.")
    return items


def task_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    scenario = str(row.get("scenario", ""))
    return (int(SCENARIOS.get(scenario, {}).get("order", 999)), str(row.get("slug", "")))


def select_agent_error_rows(
    *,
    base_root: Path,
    source_model_slug: str,
    benchmark: str,
    limit_per_scenario: int | None,
) -> list[dict[str, Any]]:
    runs_path = base_root / source_model_slug / benchmark / "runs.jsonl"
    rows = sorted(read_jsonl(runs_path), key=task_sort_key)
    selected = [row for row in rows if row.get("outcome") == "agent_error"]
    if limit_per_scenario is None:
        return selected
    limited: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for row in selected:
        scenario = str(row.get("scenario", ""))
        if seen[scenario] >= limit_per_scenario:
            continue
        limited.append(row)
        seen[scenario] += 1
    return limited


def task_overrides_for(rows: list[dict[str, Any]]) -> str:
    by_scenario: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        scenario = str(row.get("scenario", ""))
        slug = str(row.get("slug", ""))
        if scenario not in SCENARIOS:
            raise RuntimeError(f"Unknown scenario in base row: {scenario}")
        if not slug:
            raise RuntimeError(f"Missing slug in selected row: {row}")
        by_scenario[scenario].append(slug)
    chunks = []
    for scenario in SCENARIO_ORDER:
        slugs = by_scenario.get(scenario)
        if slugs:
            chunks.append(f"{scenario}={','.join(slugs)}")
    return ";".join(chunks)


def scenario_list_for(rows: list[dict[str, Any]]) -> str:
    scenarios = []
    present = {str(row.get("scenario", "")) for row in rows}
    for scenario in SCENARIO_ORDER:
        if scenario in present:
            scenarios.append(scenario)
    return ",".join(scenarios)


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def selected_ports(benchmark: str, rows: list[dict[str, Any]], port_offset: int) -> dict[str, int]:
    scenarios = {str(row.get("scenario", "")) for row in rows}
    return {
        scenario: int(SCENARIOS[scenario]["ports"][benchmark]) + port_offset
        for scenario in SCENARIO_ORDER
        if scenario in scenarios
    }


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def path_is_or_contains(parent: Path, child: Path) -> bool:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    return child_resolved == parent_resolved or child_resolved.is_relative_to(parent_resolved)


def guard_output_root(output_root: Path, base_root: Path, *, overwrite: bool) -> None:
    protected = [base_root, QWEN36_RECORD_ROOT]
    for protected_root in protected:
        if path_is_or_contains(protected_root, output_root):
            raise RuntimeError(
                f"Refusing to write output under protected root {display_path(protected_root)}: "
                f"{display_path(output_root)}"
            )
    if output_root.exists() and not overwrite:
        raise RuntimeError(
            f"Output root already exists: {display_path(output_root)}. "
            "Use --overwrite only if you intentionally want run_pair_benchmarks.py "
            "to refresh files inside that isolated retry root."
        )


def guard_ports(benchmark: str, rows: list[dict[str, Any]], port_offset: int) -> None:
    busy = []
    for scenario, port in selected_ports(benchmark, rows, port_offset).items():
        if is_port_open(port):
            busy.append(f"{scenario}:{port}")
    if busy:
        raise RuntimeError(
            f"Refusing to run because retry ports are already in use for {benchmark}: "
            f"{', '.join(busy)}"
        )


def build_command(args: argparse.Namespace, *, benchmark: str, rows: list[dict[str, Any]]) -> list[str]:
    overrides = task_overrides_for(rows)
    scenarios = scenario_list_for(rows)
    if not overrides or not scenarios:
        raise RuntimeError(f"No selected agent-error rows for {benchmark}.")
    command = [
        sys.executable,
        str(PAIR_RUNNER),
        "--benchmark",
        benchmark,
        "--models",
        args.run_model_key,
        "--profile",
        "full",
        "--temperature",
        str(args.temperature),
        "--top-p",
        str(args.top_p),
        "--seed",
        str(args.seed),
        "--max-steps",
        str(args.max_steps),
        "--model-max-output-tokens",
        str(args.model_max_output_tokens),
        "--aime-max-retries",
        str(args.aime_max_retries),
        "--aime-request-delay-sec",
        str(args.aime_request_delay_sec),
        "--aime-read-timeout-sec",
        str(args.aime_read_timeout_sec),
        "--scenarios",
        scenarios,
        "--task-overrides",
        overrides,
        "--port-offset",
        str(args.port_offset),
        "--record-root",
        str(args.output_root),
    ]
    if args.aime_base_url is not None:
        command.extend(["--aime-base-url", args.aime_base_url])
    if args.aime_model is not None:
        command.extend(["--aime-model", args.aime_model])
    if args.aime_host_header is not None:
        command.extend(["--aime-host-header", args.aime_host_header])
    if args.aime_verify_ssl is not None:
        command.extend(["--aime-verify-ssl", args.aime_verify_ssl])
    if args.aime_extra_body_json:
        command.extend(["--aime-extra-body-json", args.aime_extra_body_json])
    if args.experiment_variant:
        command.extend(["--experiment-variant", args.experiment_variant])
    if args.thinking_budget_supported:
        command.extend(["--thinking-budget-supported", args.thinking_budget_supported])
    return command


def retry_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_MODEL": args.aime_model or "gemini-3-pro-image-preview",
            "AIME_LITELLM_BASE_URL": args.aime_base_url or "https://127.0.0.1:18443/litellm/v1",
            "AIME_LITELLM_HOST_HEADER": args.aime_host_header or "",
            "AIME_LITELLM_VERIFY_SSL": args.aime_verify_ssl or "false",
        }
    )
    if not args.preserve_proxies:
        env.update(
            {
                "HTTP_PROXY": "",
                "HTTPS_PROXY": "",
                "ALL_PROXY": "",
                "NO_PROXY": "*",
            }
        )
    return env


def summarize_selection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_scenario = Counter(str(row.get("scenario", "")) for row in rows)
    return {
        "total": len(rows),
        "by_scenario": {scenario: by_scenario.get(scenario, 0) for scenario in SCENARIO_ORDER if by_scenario.get(scenario, 0)},
        "slugs": {
            scenario: [str(row.get("slug", "")) for row in rows if row.get("scenario") == scenario]
            for scenario in SCENARIO_ORDER
            if by_scenario.get(scenario, 0)
        },
    }


def output_runs_path(output_root: Path, repair_model_slug: str, benchmark: str) -> Path:
    return output_root / repair_model_slug / benchmark / "runs.jsonl"


def run_benchmark(args: argparse.Namespace, benchmark: str, rows: list[dict[str, Any]]) -> int:
    command = build_command(args, benchmark=benchmark, rows=rows)
    print(f"[gemini3pro-retry] {benchmark}: selected {len(rows)} agent-error rows")
    print(f"[gemini3pro-retry] {benchmark}: ports {selected_ports(benchmark, rows, args.port_offset)}")
    print("[gemini3pro-retry] command:")
    print("  " + " ".join(command))
    if args.dry_run:
        return 0

    env = retry_env(args)
    if not env.get("AIME_LITELLM_API_KEY"):
        raise RuntimeError(
            "AIME_LITELLM_API_KEY is not set. Export it in the shell before running "
            "without --dry-run; the script will not store the key."
        )
    completed = subprocess.run(command, cwd=str(REPO_ROOT), env=env, check=False, text=True)
    if completed.returncode != 0:
        return completed.returncode

    produced_rows = read_jsonl(output_runs_path(args.output_root, args.repair_model_slug, benchmark))
    if len(produced_rows) != len(rows):
        raise RuntimeError(
            f"{benchmark} retry produced {len(produced_rows)} rows, expected {len(rows)}: "
            f"{display_path(output_runs_path(args.output_root, args.repair_model_slug, benchmark))}"
        )
    return 0


def run(args: argparse.Namespace) -> int:
    args.base_root = args.base_root.resolve()
    args.output_root = args.output_root.resolve()
    args.repair_model_slug = args.repair_model_slug or MODEL_KEY_TO_SLUG.get(args.run_model_key)
    if not args.repair_model_slug:
        raise RuntimeError(
            f"Missing repair model slug for --run-model-key {args.run_model_key}; "
            "pass --repair-model-slug."
        )
    benchmarks = parse_benchmarks(args.benchmarks)
    guard_output_root(args.output_root, args.base_root, overwrite=args.overwrite)

    selections: dict[str, list[dict[str, Any]]] = {}
    for benchmark in benchmarks:
        rows = select_agent_error_rows(
            base_root=args.base_root,
            source_model_slug=args.source_model_slug,
            benchmark=benchmark,
            limit_per_scenario=args.limit_per_scenario,
        )
        selections[benchmark] = rows
        if rows:
            guard_ports(benchmark, rows, args.port_offset)

    manifest = {
        "script": display_path(Path(__file__)),
        "base_root": display_path(args.base_root),
        "output_root": display_path(args.output_root),
        "source_model_slug": args.source_model_slug,
        "run_model_key": args.run_model_key,
        "repair_model_slug": args.repair_model_slug,
        "port_offset": args.port_offset,
        "dry_run": args.dry_run,
        "retry_config": {
            "aime_max_retries": args.aime_max_retries,
            "aime_request_delay_sec": args.aime_request_delay_sec,
            "aime_read_timeout_sec": args.aime_read_timeout_sec,
            "aime_extra_body_json": args.aime_extra_body_json,
            "experiment_variant": args.experiment_variant,
            "thinking_budget_supported": args.thinking_budget_supported,
            "model_max_output_tokens": args.model_max_output_tokens,
            "max_steps": args.max_steps,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "seed": args.seed,
            "aime_base_url": args.aime_base_url,
            "aime_model": args.aime_model,
            "aime_host_header": args.aime_host_header,
            "aime_verify_ssl": args.aime_verify_ssl,
            "preserve_proxies": args.preserve_proxies,
        },
        "selections": {
            benchmark: summarize_selection(rows) for benchmark, rows in selections.items()
        },
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    if not args.dry_run:
        args.output_root.mkdir(parents=True, exist_ok=True)
        write_json(args.output_root / "retry_selection_manifest.json", manifest)

    for benchmark in benchmarks:
        rows = selections[benchmark]
        if not rows:
            print(f"[gemini3pro-retry] {benchmark}: no agent-error rows; skipping")
            continue
        code = run_benchmark(args, benchmark, rows)
        if code != 0:
            return code

    if not args.dry_run:
        print(f"[gemini3pro-retry] wrote retry records under {display_path(args.output_root)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, default=DEFAULT_BASE_ROOT)
    parser.add_argument("--source-model-slug", default=SOURCE_MODEL_SLUG)
    parser.add_argument("--run-model-key", default="gemini3pro_image_preview")
    parser.add_argument("--repair-model-slug")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=RECORD_ROOT / f"gemini3pro_agent_error_retry_{utcish_stamp()}",
    )
    parser.add_argument("--benchmarks", default="official,clean", help="Comma list: official,clean or both.")
    parser.add_argument("--port-offset", type=int, default=4000)
    parser.add_argument("--aime-max-retries", type=int, default=3)
    parser.add_argument("--aime-request-delay-sec", type=float, default=1.0)
    parser.add_argument("--aime-read-timeout-sec", type=float, default=180.0)
    parser.add_argument("--aime-extra-body-json")
    parser.add_argument("--aime-base-url")
    parser.add_argument("--aime-model")
    parser.add_argument("--aime-host-header")
    parser.add_argument("--aime-verify-ssl", choices=["true", "false"])
    parser.add_argument(
        "--preserve-proxies",
        action="store_true",
        help="Keep HTTP(S)_PROXY from the parent environment for non-local AIME endpoints.",
    )
    parser.add_argument("--experiment-variant")
    parser.add_argument("--thinking-budget-supported", choices=["true", "false", "unknown"])
    parser.add_argument("--model-max-output-tokens", type=int, default=2048)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", dest="top_p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--limit-per-scenario", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.limit_per_scenario is not None and args.limit_per_scenario <= 0:
        raise RuntimeError("--limit-per-scenario must be positive when provided.")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
