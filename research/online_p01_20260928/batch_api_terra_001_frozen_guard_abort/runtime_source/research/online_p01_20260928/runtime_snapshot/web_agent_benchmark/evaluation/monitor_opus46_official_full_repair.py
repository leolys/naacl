#!/usr/bin/env python3
"""Monitor an Opus 4.6 official full run, repair agent errors, and merge rows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_RUNNER = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_claude_opus46_uuid_checkpoint.py"
OFFICIAL_ROOT = REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1"
SCENARIOS = ["public39", "business47", "environment35", "health19"]
TASK_FILES = {
    "public39": "public39_tasks.jsonl",
    "business47": "business47_tasks.jsonl",
    "environment35": "environment35_tasks.jsonl",
    "health19": "health19_tasks.jsonl",
}
TRANSIENT_MARKERS = [
    "transient http",
    "http 429",
    "http 502",
    "http 503",
    "http 504",
    "connection error",
    "timed out",
    "timeout",
    "empty response",
    "empty final content",
    "llm_action_generation_error",
    "auth_unavailable",
    "aime litellm request failed",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def task_slug(row: dict[str, Any]) -> str:
    value = row.get("official_slug") or row.get("slug")
    if not value:
        raise RuntimeError(f"Could not determine official slug from task row: {row}")
    return str(value)


def task_sort_key(item: tuple[str, str] | dict[str, Any]) -> tuple[int, int]:
    if isinstance(item, tuple):
        scenario, slug = item
    else:
        scenario, slug = str(item["scenario"]), str(item["slug"])
    suffix = "".join(ch for ch in slug if ch.isdigit())
    return SCENARIOS.index(scenario), int(suffix or 0)


def load_expected_tasks() -> list[tuple[str, str]]:
    tasks: list[tuple[str, str]] = []
    for scenario in SCENARIOS:
        for row in read_jsonl(OFFICIAL_ROOT / TASK_FILES[scenario]):
            tasks.append((scenario, task_slug(row)))
    return sorted(tasks, key=task_sort_key)


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario")), str(row.get("slug"))


def read_rows_from_run_dir(run_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    top_level = read_jsonl(run_dir / "runs.jsonl")
    source_rows = top_level
    if not source_rows:
        source_rows = []
        for scenario in SCENARIOS:
            source_rows.extend(read_jsonl(run_dir / "_scenario_outputs" / scenario / "runs.jsonl"))
    for row in source_rows:
        rows[row_key(row)] = dict(row)
    return rows


def is_transient_model_failure(row: dict[str, Any]) -> bool:
    if row.get("outcome") == "success":
        return False
    haystack = " ".join(
        [
            str(row.get("exception", "")),
            str(row.get("error", "")),
            str(row.get("error_attribution", "")),
            json.dumps(row.get("trace", []), ensure_ascii=False),
        ]
    ).lower()
    return any(marker in haystack for marker in TRANSIENT_MARKERS)


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row.get("outcome", "unknown") for row in rows)
    by_scenario: dict[str, dict[str, Any]] = {}
    for scenario in SCENARIOS:
        subset = [row for row in rows if row.get("scenario") == scenario]
        if not subset:
            continue
        scenario_counts = Counter(row.get("outcome", "unknown") for row in subset)
        by_scenario[scenario] = {
            "task_count": len(subset),
            "success_count": scenario_counts.get("success", 0),
            "success_rate": scenario_counts.get("success", 0) / len(subset),
            "outcome_counts": dict(scenario_counts),
        }
    return {
        "task_count": len(rows),
        "success_count": counts.get("success", 0),
        "success_rate": counts.get("success", 0) / len(rows) if rows else 0.0,
        "outcome_counts": dict(counts),
        "by_scenario": by_scenario,
    }


def write_summary(path: Path, rows: list[dict[str, Any]], *, model_slug: str) -> None:
    summary = summarize_rows(rows)
    lines = [
        "# Claude Opus 4.6 Official Repair-Merged Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Model slug: `{model_slug}`",
        f"- Total tasks: `{summary['task_count']}`",
        f"- Success count: `{summary['success_count']}`",
        f"- Success rate: `{summary['success_rate']:.2%}`",
        f"- Outcome distribution: `{summary['outcome_counts']}`",
        "",
        "## By Scenario",
        "",
        "| Scenario | Task Count | Success | Success Rate | Outcomes |",
        "|---|---:|---:|---:|---|",
    ]
    for scenario in SCENARIOS:
        item = summary["by_scenario"].get(scenario)
        if item:
            lines.append(
                f"| {scenario} | {item['task_count']} | {item['success_count']} | "
                f"{item['success_rate']:.2%} | `{item['outcome_counts']}` |"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def extract_targets(expected: list[tuple[str, str]], base_rows: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for scenario, slug in expected:
        row = base_rows.get((scenario, slug))
        if row is None:
            targets.append({"benchmark": "official", "scenario": scenario, "slug": slug, "target_reason": "missing_row"})
        elif row.get("outcome") == "agent_error":
            targets.append(
                {
                    "benchmark": "official",
                    "scenario": scenario,
                    "slug": slug,
                    "target_reason": "agent_error",
                    "base_error_attribution": row.get("error_attribution"),
                }
            )
    return targets


def merge_rows(
    *,
    expected: list[tuple[str, str]],
    base_rows: dict[tuple[str, str], dict[str, Any]],
    repair_rows: dict[tuple[str, str], dict[str, Any]],
    output_dir: Path,
    model_slug: str,
) -> None:
    merged: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for key in expected:
        base = base_rows.get(key)
        repair = repair_rows.get(key)
        chosen: dict[str, Any] | None = None
        source = ""
        if base is not None and base.get("outcome") != "agent_error":
            chosen = dict(base)
            source = "base"
        elif repair is not None:
            chosen = dict(repair)
            source = "repair"
            if base is not None:
                chosen["base_outcome_before_repair"] = base.get("outcome")
                chosen["base_error_attribution_before_repair"] = base.get("error_attribution")
        elif base is not None:
            chosen = dict(base)
            source = "base_unrepaired_agent_error"
        else:
            missing.append({"scenario": key[0], "slug": key[1]})
            continue
        chosen["repair_merge_source"] = source
        merged.append(chosen)
        manifest.append(
            {
                "scenario": key[0],
                "slug": key[1],
                "source": source,
                "base_outcome": base.get("outcome") if base else None,
                "repair_outcome": repair.get("outcome") if repair else None,
                "merged_outcome": chosen.get("outcome"),
            }
        )
    merged.sort(key=lambda row: task_sort_key((str(row.get("scenario")), str(row.get("slug")))))
    failures = [row for row in merged if row.get("outcome") != "success"]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "runs.jsonl", merged)
    write_jsonl(output_dir / "failures.jsonl", failures)
    write_jsonl(output_dir / "transient_failures.jsonl", [row for row in failures if is_transient_model_failure(row)])
    write_jsonl(output_dir / "repair_merge_manifest.jsonl", manifest)
    write_jsonl(output_dir / "missing_after_merge.jsonl", missing)
    write_summary(output_dir / "summary.md", merged, model_slug=model_slug)
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "record_type": "claude_opus46_official_monitor_repair_merged",
                "expected_rows": len(expected),
                "base_rows": len(base_rows),
                "repair_rows": len(repair_rows),
                "merged_rows": len(merged),
                "missing_rows": len(missing),
                "source_counts": dict(Counter(row["source"] for row in manifest)),
                "outcome_counts": dict(Counter(row.get("outcome") for row in merged)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def log(message: str, path: Path) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run_repair(args: argparse.Namespace, targets_path: Path) -> int:
    cmd = [
        sys.executable,
        str(CHECKPOINT_RUNNER),
        "--benchmark",
        "official",
        "--model-key",
        args.model_key,
        "--model-slug",
        args.model_slug,
        "--batch-root",
        str(args.repair_batch_root),
        "--output-root",
        str(args.repair_output_root),
        "--targets-file",
        str(targets_path),
        "--cooldown-sec",
        str(args.repair_cooldown_sec),
        "--retry-passes",
        str(args.repair_retry_passes),
        "--retry-cooldown-sec",
        str(args.repair_retry_cooldown_sec),
        "--task-timeout-sec",
        str(args.repair_task_timeout_sec),
        "--port-offset",
        str(args.repair_port_offset),
        "--max-steps",
        str(args.max_steps),
        "--aime-request-delay-sec",
        str(args.aime_request_delay_sec),
        "--aime-max-retries",
        str(args.aime_max_retries),
        "--aime-read-timeout-sec",
        str(args.aime_read_timeout_sec),
        "--aime-base-url",
        args.aime_base_url,
        "--aime-host-header",
        args.aime_host_header,
        "--aime-api-style",
        args.aime_api_style,
        "--aime-verify-ssl",
        args.aime_verify_ssl,
    ]
    args.repair_log.parent.mkdir(parents=True, exist_ok=True)
    with args.repair_log.open("a", encoding="utf-8") as fh:
        fh.write(f"[{utc_now()}] RUN {' '.join(cmd)}\n")
        process = subprocess.run(cmd, cwd=REPO_ROOT, stdout=fh, stderr=fh, text=True)
    return process.returncode


def remaining_agent_error_targets(
    *,
    expected: list[tuple[str, str]],
    base_rows: dict[tuple[str, str], dict[str, Any]],
    repair_rows: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for scenario, slug in expected:
        key = (scenario, slug)
        base = base_rows.get(key)
        repair = repair_rows.get(key)
        if base is None:
            targets.append({"benchmark": "official", "scenario": scenario, "slug": slug, "target_reason": "missing_row"})
        elif base.get("outcome") == "agent_error" and (repair is None or repair.get("outcome") == "agent_error"):
            targets.append(
                {
                    "benchmark": "official",
                    "scenario": scenario,
                    "slug": slug,
                    "target_reason": "agent_error_after_repair" if repair else "agent_error",
                    "base_error_attribution": base.get("error_attribution"),
                    "latest_repair_error_attribution": repair.get("error_attribution") if repair else None,
                }
            )
    return targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--base-official-dir", type=Path, required=True)
    parser.add_argument("--repair-batch-root", type=Path, required=True)
    parser.add_argument("--repair-output-root", type=Path, required=True)
    parser.add_argument("--merged-official-dir", type=Path, required=True)
    parser.add_argument("--targets-path", type=Path, required=True)
    parser.add_argument("--monitor-log", type=Path, required=True)
    parser.add_argument("--repair-log", type=Path, required=True)
    parser.add_argument("--model-key", default="claude_opus_4_6_aime_responses")
    parser.add_argument("--model-slug", default="claude_opus_4_6_aime_responses_temp0_top_p1_seed12345")
    parser.add_argument("--poll-sec", type=float, default=120.0)
    parser.add_argument("--repair-cooldown-sec", type=float, default=30.0)
    parser.add_argument("--repair-retry-passes", type=int, default=4)
    parser.add_argument("--repair-retry-cooldown-sec", type=float, default=120.0)
    parser.add_argument("--repair-task-timeout-sec", type=int, default=900)
    parser.add_argument("--repair-port-offset", type=int, default=17000)
    parser.add_argument(
        "--max-repair-rounds",
        type=int,
        default=0,
        help="Maximum outer repair rounds after the full run exits. Use 0 for unlimited until no agent_error/missing rows remain.",
    )
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--aime-request-delay-sec", type=float, default=2.0)
    parser.add_argument("--aime-max-retries", type=int, default=3)
    parser.add_argument("--aime-read-timeout-sec", type=float, default=300.0)
    parser.add_argument("--aime-base-url", default="https://127.0.0.1:18444/litellm/v1")
    parser.add_argument("--aime-host-header", default="aimemodeldev.myhexin.com")
    parser.add_argument("--aime-api-style", choices=["chat_completions", "responses"], default="responses")
    parser.add_argument("--aime-verify-ssl", choices=["true", "false"], default="false")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not os.environ.get("AIME_LITELLM_API_KEY"):
        raise RuntimeError("AIME_LITELLM_API_KEY is not set; monitor needs it for post-run repair.")
    expected = load_expected_tasks()
    pid = read_pid(args.pid_file)
    if pid is None:
        raise RuntimeError(f"Could not read full-run pid from {args.pid_file}")

    log(f"monitoring pid={pid} expected_tasks={len(expected)}", args.monitor_log)
    while process_running(pid):
        rows = read_rows_from_run_dir(args.base_official_dir)
        counts = Counter(row.get("outcome", "unknown") for row in rows.values())
        log(f"full still running pid={pid} rows={len(rows)}/{len(expected)} outcomes={dict(counts)}", args.monitor_log)
        time.sleep(args.poll_sec)

    base_rows = read_rows_from_run_dir(args.base_official_dir)
    base_counts = Counter(row.get("outcome", "unknown") for row in base_rows.values())
    log(f"full exited rows={len(base_rows)}/{len(expected)} outcomes={dict(base_counts)}", args.monitor_log)
    repair_dir = args.repair_output_root / args.model_slug / "official"
    repair_rows: dict[tuple[str, str], dict[str, Any]] = {}
    repair_round = 0
    while True:
        repair_rows = read_rows_from_run_dir(repair_dir)
        targets = (
            extract_targets(expected, base_rows)
            if repair_round == 0 and not repair_rows
            else remaining_agent_error_targets(expected=expected, base_rows=base_rows, repair_rows=repair_rows)
        )
        write_jsonl(args.targets_path, targets)
        log(f"repair round={repair_round} remaining_targets={len(targets)} wrote={args.targets_path}", args.monitor_log)
        if not targets:
            break
        if args.max_repair_rounds > 0 and repair_round >= args.max_repair_rounds:
            log(f"max repair rounds reached: {args.max_repair_rounds}", args.monitor_log)
            break
        rc = run_repair(args, args.targets_path)
        log(f"repair round={repair_round} exited rc={rc}", args.monitor_log)
        repair_round += 1

    repair_rows = read_rows_from_run_dir(repair_dir)
    merge_rows(
        expected=expected,
        base_rows=base_rows,
        repair_rows=repair_rows,
        output_dir=args.merged_official_dir,
        model_slug=args.model_slug,
    )
    merged_rows = read_jsonl(args.merged_official_dir / "runs.jsonl")
    merged_counts = Counter(row.get("outcome", "unknown") for row in merged_rows)
    log(f"merged rows={len(merged_rows)}/{len(expected)} outcomes={dict(merged_counts)} output={args.merged_official_dir}", args.monitor_log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
