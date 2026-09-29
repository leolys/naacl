#!/usr/bin/env python3
"""Run benchmark tasks as resumable single-task batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
RUN_PAIR = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_pair_benchmarks.py"
BENCHMARK_DIRS = {
    "official": REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1",
    "clean": REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1",
}
SCENARIOS = ["public39", "business47", "environment35", "health19"]
TASK_FILES = {
    "public39": "public39_tasks.jsonl",
    "business47": "business47_tasks.jsonl",
    "environment35": "environment35_tasks.jsonl",
    "health19": "health19_tasks.jsonl",
}
TASK_COUNTS = {
    "public39": 39,
    "business47": 47,
    "environment35": 35,
    "health19": 19,
}
DEFAULT_MODEL_KEY = "claude_opus_4_6_aime_uuid_slow"
DEFAULT_MODEL_SLUG = "claude_opus_4_6_aime_uuid_slow_temp0_top_p1_seed12345"
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
    "unknown provider",
    "aime litellm request failed",
]


def request_body(api_style: str, model: str) -> bytes:
    if api_style == "responses":
        payload: dict[str, Any] = {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "只回答 OK"}]}],
            "max_output_tokens": 32,
        }
    else:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "只回答 OK"}],
            "max_tokens": 32,
        }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def public_endpoint_url(*, base_url: str, host_header: str, api_style: str) -> tuple[str, str]:
    paths = {
        "responses": "/responses",
        "messages": "/messages",
        "chat_completions": "/chat/completions",
    }
    path = paths[api_style]
    match = re.match(r"^https://127\.0\.0\.1:(\d+)(/.*)$", base_url.rstrip("/"))
    if not match:
        return base_url.rstrip("/") + path, ""
    port, base_path = match.groups()
    return f"https://{host_header}{base_path}{path}", f"{host_header}:443:127.0.0.1:{port}"


def probe_api_style(
    *,
    api_style: str,
    base_url: str,
    host_header: str,
    model: str,
    timeout: int,
) -> tuple[int | None, str]:
    url, connect_to = public_endpoint_url(base_url=base_url, host_header=host_header, api_style=api_style)
    command = [
        "curl",
        "--connect-timeout",
        "10",
        "--max-time",
        str(timeout),
        "-sS",
        "-o",
        "-",
        "-w",
        "\n%{http_code}",
        url,
        "-H",
        "Authorization: Bearer " + os.environ["AIME_LITELLM_API_KEY"],
        "-H",
        "Content-Type: application/json",
        "-d",
        request_body(api_style, model).decode("utf-8"),
    ]
    if connect_to:
        command[1:1] = ["--noproxy", "*", "--connect-to", connect_to]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout + 5)
    except Exception as exc:
        return None, repr(exc)
    output = completed.stdout or completed.stderr or ""
    body, _, code_text = output.rpartition("\n")
    try:
        code = int(code_text.strip())
    except ValueError:
        code = None
    return code, body[:500]


def choose_preflight_api_style(
    *,
    args: argparse.Namespace,
    task: dict[str, str],
    pass_index: int,
    attempt: int,
) -> str | None:
    if not args.preflight_before_task:
        return args.aime_api_style
    if not args.aime_base_url:
        return args.aime_api_style
    if not os.environ.get("AIME_LITELLM_API_KEY"):
        raise RuntimeError("AIME_LITELLM_API_KEY is not set.")
    model = args.aime_preflight_model
    if not model:
        return args.aime_api_style
    log_path = args.output_root / "preflight_log.jsonl"
    for preflight_attempt in range(1, args.preflight_attempts + 1):
        if args.aime_api_style == "messages":
            messages_code, messages_body = probe_api_style(
                api_style="messages",
                base_url=args.aime_base_url,
                host_header=args.aime_host_header,
                model=model,
                timeout=args.preflight_timeout_sec,
            )
            append_jsonl(
                log_path,
                {
                    "timestamp": utc_now(),
                    "benchmark": args.benchmark,
                    "scenario": task["scenario"],
                    "slug": task["slug"],
                    "pass_index": pass_index,
                    "attempt": attempt,
                    "preflight_attempt": preflight_attempt,
                    "selected_api_style": "messages" if messages_code == 200 else None,
                    "messages_code": messages_code,
                    "messages_body_excerpt": messages_body[:240],
                },
            )
            if messages_code == 200:
                return "messages"
            if preflight_attempt < args.preflight_attempts:
                time.sleep(args.preflight_sleep_sec)
                continue
            raise RuntimeError(
                f"/messages did not recover for {args.benchmark}/{task['scenario']}/{task['slug']}."
            )
        responses_code, responses_body = probe_api_style(
            api_style="responses",
            base_url=args.aime_base_url,
            host_header=args.aime_host_header,
            model=model,
            timeout=args.preflight_timeout_sec,
        )
        if responses_code == 200:
            append_jsonl(
                log_path,
                {
                    "timestamp": utc_now(),
                    "benchmark": args.benchmark,
                    "scenario": task["scenario"],
                    "slug": task["slug"],
                    "pass_index": pass_index,
                    "attempt": attempt,
                    "preflight_attempt": preflight_attempt,
                    "selected_api_style": "responses",
                    "responses_code": responses_code,
                },
            )
            return "responses"
        chat_code, chat_body = probe_api_style(
            api_style="chat_completions",
            base_url=args.aime_base_url,
            host_header=args.aime_host_header,
            model=model,
            timeout=args.preflight_timeout_sec,
        )
        selected = "chat_completions" if chat_code == 200 else None
        append_jsonl(
            log_path,
            {
                "timestamp": utc_now(),
                "benchmark": args.benchmark,
                "scenario": task["scenario"],
                "slug": task["slug"],
                "pass_index": pass_index,
                "attempt": attempt,
                "preflight_attempt": preflight_attempt,
                "selected_api_style": selected,
                "responses_code": responses_code,
                "chat_code": chat_code,
                "responses_body_excerpt": responses_body[:240],
                "chat_body_excerpt": chat_body[:240],
            },
        )
        if selected:
            return selected
        if preflight_attempt < args.preflight_attempts:
            time.sleep(args.preflight_sleep_sec)
    raise RuntimeError(
        f"Neither /responses nor /chat/completions recovered for "
        f"{args.benchmark}/{task['scenario']}/{task['slug']}."
    )


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


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario")), str(row.get("slug"))


def task_slug(task: dict[str, Any], benchmark: str) -> str:
    value = task.get(f"{benchmark}_slug") or task.get("official_slug") or task.get("slug")
    if not value:
        raise RuntimeError(f"Could not find task slug in row with keys: {sorted(task)}")
    return str(value)


def load_tasks(benchmark: str, *, limit_per_scenario: int | None = None) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    root = BENCHMARK_DIRS[benchmark]
    for scenario in SCENARIOS:
        rows = read_jsonl(root / TASK_FILES[scenario])
        if limit_per_scenario is not None:
            rows = rows[:limit_per_scenario]
        for row in rows:
            tasks.append({"benchmark": benchmark, "scenario": scenario, "slug": task_slug(row, benchmark)})
    return tasks


def task_sort_key(task: dict[str, str]) -> tuple[int, int]:
    scenario = task["scenario"]
    slug = task["slug"]
    suffix = "".join(ch for ch in slug if ch.isdigit())
    return SCENARIOS.index(scenario), int(suffix or 0)


def load_targets_file(path: Path, benchmark: str) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for row in read_jsonl(path):
        row_benchmark = str(row.get("benchmark", benchmark))
        if row_benchmark != benchmark:
            continue
        scenario = str(row.get("scenario", ""))
        slug = str(row.get("slug", ""))
        if scenario not in SCENARIOS:
            raise RuntimeError(f"Unknown scenario in targets file {path}: {scenario}")
        if not slug:
            raise RuntimeError(f"Missing slug in targets file {path}: {row}")
        tasks.append({"benchmark": benchmark, "scenario": scenario, "slug": slug})
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for task in sorted(tasks, key=task_sort_key):
        key = (task["scenario"], task["slug"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(task)
    return unique


def manifest_key(entry: dict[str, Any]) -> tuple[str, str]:
    return str(entry.get("scenario")), str(entry.get("slug"))


def attempt_rows_from_manifest(manifest: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in manifest:
        by_key[manifest_key(entry)].append(entry)
    return by_key


def latest_manifest_by_key(manifest: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in manifest:
        latest[manifest_key(entry)] = entry
    return latest


def read_batch_row(batch_dir: Path, model_slug: str, benchmark: str) -> dict[str, Any] | None:
    runs_path = batch_dir / model_slug / benchmark / "runs.jsonl"
    rows = read_jsonl(runs_path)
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError(f"Expected one row in {runs_path}, found {len(rows)}")
    return rows[0]


def best_rows_from_manifest(
    manifest: list[dict[str, Any]], *, model_slug: str, benchmark: str
) -> dict[tuple[str, str], dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in manifest:
        batch_dir_raw = entry.get("batch_dir")
        if not batch_dir_raw:
            continue
        row = read_batch_row((REPO_ROOT / batch_dir_raw).resolve(), model_slug, benchmark)
        if row:
            best[manifest_key(entry)] = row
    return best


def is_retry_target(row: dict[str, Any] | None) -> bool:
    return row is None or row.get("outcome") == "agent_error"


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


def write_summary(path: Path, rows: list[dict[str, Any]], *, model_slug: str, benchmark: str) -> None:
    summary = summarize_rows(rows)
    lines = [
        f"# {model_slug} Checkpoint {benchmark} Summary",
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
        row = summary["by_scenario"].get(scenario)
        if row:
            lines.append(
                f"| {scenario} | {row['task_count']} | {row['success_count']} | "
                f"{row['success_rate']:.2%} | `{row['outcome_counts']}` |"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_aggregate_outputs(
    *,
    manifest: list[dict[str, Any]],
    args: argparse.Namespace,
    tasks: list[dict[str, str]],
) -> list[dict[str, Any]]:
    best = best_rows_from_manifest(manifest, model_slug=args.model_slug, benchmark=args.benchmark)
    latest_manifest = latest_manifest_by_key(manifest)
    ordered_rows = [best[(task["scenario"], task["slug"])] for task in sorted(tasks, key=task_sort_key) if (task["scenario"], task["slug"]) in best]
    out_dir = args.output_root / args.model_slug / args.benchmark
    write_jsonl(out_dir / "runs.jsonl", ordered_rows)
    failures = [row for row in ordered_rows if row.get("outcome") != "success"]
    write_jsonl(out_dir / "failures.jsonl", failures)
    write_jsonl(out_dir / "transient_failures.jsonl", [row for row in failures if is_transient_model_failure(row)])
    agent_error_targets: list[dict[str, Any]] = []
    for task in sorted(tasks, key=task_sort_key):
        key = (task["scenario"], task["slug"])
        row = best.get(key)
        latest = latest_manifest.get(key, {})
        if row is None or row.get("outcome") == "agent_error":
            agent_error_targets.append(
                {
                    "benchmark": args.benchmark,
                    "scenario": task["scenario"],
                    "slug": task["slug"],
                    "target_reason": "missing_row" if row is None else "agent_error",
                    "latest_outcome": row.get("outcome") if row else None,
                    "latest_error_attribution": row.get("error_attribution") if row else None,
                    "latest_attempt": latest.get("attempt"),
                    "latest_pass_index": latest.get("pass_index"),
                    "latest_batch_dir": latest.get("batch_dir"),
                    "latest_duration_sec": latest.get("duration_sec"),
                    "latest_timed_out": latest.get("timed_out"),
                }
            )
    write_jsonl(args.output_root / "agent_error_targets.jsonl", agent_error_targets)
    write_summary(out_dir / "summary.md", ordered_rows, model_slug=args.model_slug, benchmark=args.benchmark)
    prompt_text = args.extra_system_prompt or ""
    prompt_path = args.extra_system_prompt_file
    run_config = {
        "generated_at": utc_now(),
        "record_type": "single_task_checkpoint",
        "benchmark": args.benchmark,
        "model_key": args.model_key,
        "model_slug": args.model_slug,
        "batch_root": str(args.batch_root.relative_to(REPO_ROOT)),
        "cooldown_sec": args.cooldown_sec,
        "retry_passes": args.retry_passes,
        "retry_cooldown_sec": args.retry_cooldown_sec,
        "task_timeout_sec": args.task_timeout_sec,
        "port_offset": args.port_offset,
        "limit_per_scenario": args.limit_per_scenario,
        "targets_file": str(args.targets_file.relative_to(REPO_ROOT)) if args.targets_file else None,
        "experiment_variant": args.experiment_variant,
        "record_slug_suffix": args.record_slug_suffix,
        "extra_system_prompt": {
            "file": str(prompt_path.relative_to(REPO_ROOT)) if prompt_path else None,
            "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest() if prompt_text else None,
            "character_count": len(prompt_text),
        },
        "aime_overrides": {
            "base_url": args.aime_base_url,
            "host_header": args.aime_host_header,
            "api_style": args.aime_api_style,
            "verify_ssl": args.aime_verify_ssl,
            "request_delay_sec": args.aime_request_delay_sec,
            "max_retries": args.aime_max_retries,
            "read_timeout_sec": args.aime_read_timeout_sec,
            "proxy_enabled": bool(args.aime_proxy),
            "preflight_before_task": args.preflight_before_task,
            "preflight_model": args.aime_preflight_model,
            "preflight_attempts": args.preflight_attempts,
            "preflight_sleep_sec": args.preflight_sleep_sec,
            "preflight_timeout_sec": args.preflight_timeout_sec,
        },
        "expected_task_count": len(tasks) if args.targets_file or args.limit_per_scenario is not None else sum(TASK_COUNTS.values()),
    }
    (out_dir / "run_config.json").write_text(json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ordered_rows


def run_subprocess(cmd: list[str], *, cwd: Path, timeout: int) -> tuple[int | None, str, str, bool, float]:
    started = time.time()
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
    return process.returncode, stdout or "", stderr or "", timed_out, time.time() - started


def cooldown_hint_seconds(text: str) -> int | None:
    normalized = text.replace("\\", "")
    values = [int(value) for value in re.findall(r'"reset_seconds"\s*:\s*(\d+)', normalized)]
    values.extend(int(value) for value in re.findall(r"reset_seconds[=:]\s*(\d+)", normalized))
    return max(values) if values else None


def run_one_task(
    *,
    task: dict[str, str],
    attempt: int,
    pass_index: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    scenario = task["scenario"]
    slug = task["slug"]
    api_style = choose_preflight_api_style(args=args, task=task, pass_index=pass_index, attempt=attempt)
    batch_dir = args.batch_root / args.benchmark / f"attempt_{attempt:02d}" / scenario / slug
    batch_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(RUN_PAIR),
        "--benchmark",
        args.benchmark,
        "--models",
        args.model_key,
        "--profile",
        "full",
        "--scenarios",
        scenario,
        "--task-overrides",
        f"{scenario}={slug}",
        "--record-root",
        str(batch_dir),
        "--port-offset",
        str(args.port_offset),
    ]
    if args.max_steps is not None:
        cmd.extend(["--max-steps", str(args.max_steps)])
    if args.model_max_output_tokens is not None:
        cmd.extend(["--model-max-output-tokens", str(args.model_max_output_tokens)])
    if args.aime_request_delay_sec is not None:
        cmd.extend(["--aime-request-delay-sec", str(args.aime_request_delay_sec)])
    if args.aime_max_retries is not None:
        cmd.extend(["--aime-max-retries", str(args.aime_max_retries)])
    if args.aime_read_timeout_sec is not None:
        cmd.extend(["--aime-read-timeout-sec", str(args.aime_read_timeout_sec)])
    if args.aime_extra_body_json is not None:
        cmd.extend(["--aime-extra-body-json", args.aime_extra_body_json])
    if args.aime_base_url is not None:
        cmd.extend(["--aime-base-url", args.aime_base_url])
    if args.aime_host_header is not None:
        cmd.extend(["--aime-host-header", args.aime_host_header])
    if api_style is not None:
        cmd.extend(["--aime-api-style", api_style])
    if args.aime_verify_ssl is not None:
        cmd.extend(["--aime-verify-ssl", args.aime_verify_ssl])
    if args.aime_proxy is not None:
        cmd.extend(["--aime-proxy", args.aime_proxy])
    if args.extra_system_prompt:
        cmd.extend(["--extra-system-prompt", args.extra_system_prompt])
    if args.record_slug_suffix:
        cmd.extend(["--record-slug-suffix", args.record_slug_suffix])
    if args.experiment_variant:
        cmd.extend(["--experiment-variant", args.experiment_variant])
    if args.dry_run:
        print(" ".join(cmd))
        return {
            "timestamp": utc_now(),
            "benchmark": args.benchmark,
            "scenario": scenario,
            "slug": slug,
            "attempt": attempt,
            "pass_index": pass_index,
            "batch_dir": str(batch_dir.relative_to(REPO_ROOT)),
            "return_code": None,
            "duration_sec": 0.0,
            "timed_out": False,
            "outcome": "dry_run",
            "row_found": False,
            "aime_api_style": api_style,
        }
    return_code, stdout, stderr, timed_out, duration = run_subprocess(cmd, cwd=REPO_ROOT, timeout=args.task_timeout_sec)
    (batch_dir / "checkpoint_stdout.log").write_text(stdout, encoding="utf-8")
    (batch_dir / "checkpoint_stderr.log").write_text(stderr, encoding="utf-8")
    row = read_batch_row(batch_dir, args.model_slug, args.benchmark)
    transient_model_failure = is_transient_model_failure(row) if row else False
    return {
        "timestamp": utc_now(),
        "benchmark": args.benchmark,
        "scenario": scenario,
        "slug": slug,
        "attempt": attempt,
        "pass_index": pass_index,
        "batch_dir": str(batch_dir.relative_to(REPO_ROOT)),
        "return_code": return_code,
        "duration_sec": round(duration, 3),
        "timed_out": timed_out,
        "row_found": row is not None,
        "outcome": row.get("outcome") if row else None,
        "error_attribution": row.get("error_attribution") if row else None,
        "aime_api_style": api_style,
        "transient_model_failure": transient_model_failure,
        "cooldown_hint_sec": cooldown_hint_seconds(stderr),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=["official", "clean"], default="official")
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY)
    parser.add_argument("--model-slug", default=DEFAULT_MODEL_SLUG)
    parser.add_argument("--batch-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--cooldown-sec", type=float, default=60.0)
    parser.add_argument("--retry-passes", type=int, default=2)
    parser.add_argument("--retry-cooldown-sec", type=float, default=180.0)
    parser.add_argument("--task-timeout-sec", type=int, default=1200)
    parser.add_argument("--port-offset", type=int, default=9900)
    parser.add_argument("--limit-per-scenario", type=int)
    parser.add_argument("--targets-file", type=Path)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--model-max-output-tokens", type=int)
    parser.add_argument("--aime-request-delay-sec", type=float)
    parser.add_argument("--aime-max-retries", type=int)
    parser.add_argument("--aime-read-timeout-sec", type=float)
    parser.add_argument("--aime-extra-body-json")
    parser.add_argument("--aime-base-url")
    parser.add_argument("--aime-host-header")
    parser.add_argument("--aime-api-style", choices=["chat_completions", "responses", "messages"])
    parser.add_argument("--aime-verify-ssl", choices=["true", "false"])
    parser.add_argument("--aime-proxy")
    parser.add_argument("--extra-system-prompt-file", type=Path)
    parser.add_argument("--record-slug-suffix", default="")
    parser.add_argument("--experiment-variant")
    parser.add_argument("--preflight-before-task", action="store_true")
    parser.add_argument("--aime-preflight-model")
    parser.add_argument("--preflight-attempts", type=int, default=60)
    parser.add_argument("--preflight-sleep-sec", type=float, default=60.0)
    parser.add_argument("--preflight-timeout-sec", type=int, default=60)
    parser.add_argument("--transient-agent-error-cooldown-sec", type=float)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_root is None:
        args.batch_root = RECORD_ROOT / f"claude_opus_4_6_aime_uuid_slow_{args.benchmark}_batches_20260520"
    if args.output_root is None:
        args.output_root = RECORD_ROOT / f"claude_opus_4_6_aime_uuid_slow_{args.benchmark}_checkpoint_20260520"
    args.batch_root = args.batch_root.resolve()
    args.output_root = args.output_root.resolve()
    args.extra_system_prompt = ""
    if args.extra_system_prompt_file is not None:
        args.extra_system_prompt_file = args.extra_system_prompt_file.resolve()
        args.extra_system_prompt = args.extra_system_prompt_file.read_text(encoding="utf-8").strip()
        if not args.extra_system_prompt:
            raise RuntimeError(f"Extra system prompt file is empty: {args.extra_system_prompt_file}")
    if not args.dry_run and not os.environ.get("AIME_LITELLM_API_KEY"):
        raise RuntimeError("AIME_LITELLM_API_KEY is not set.")
    if args.targets_file is not None:
        args.targets_file = args.targets_file.resolve()
        tasks = load_targets_file(args.targets_file, args.benchmark)
    else:
        tasks = load_tasks(args.benchmark, limit_per_scenario=args.limit_per_scenario)
    manifest_path = args.output_root / "checkpoint_manifest.jsonl"
    manifest = read_jsonl(manifest_path)
    attempts_by_key = attempt_rows_from_manifest(manifest)

    total_passes = 1 if args.dry_run else 1 + max(0, args.retry_passes)
    for pass_index in range(total_passes):
        best = best_rows_from_manifest(manifest, model_slug=args.model_slug, benchmark=args.benchmark)
        if pass_index == 0:
            to_run = [task for task in tasks if is_retry_target(best.get((task["scenario"], task["slug"])))]
        else:
            to_run = [task for task in tasks if is_retry_target(best.get((task["scenario"], task["slug"])))]
        if not to_run:
            print(f"[checkpoint] pass {pass_index}: nothing to run")
            continue
        cooldown = args.cooldown_sec if pass_index == 0 else args.retry_cooldown_sec
        print(f"[checkpoint] pass {pass_index}: {len(to_run)} task(s), cooldown={cooldown}s")
        for index, task in enumerate(sorted(to_run, key=task_sort_key), start=1):
            key = (task["scenario"], task["slug"])
            latest = best.get(key)
            if latest is not None and latest.get("outcome") != "agent_error":
                continue
            attempt = len(attempts_by_key.get(key, [])) + 1
            print(f"[checkpoint] {index}/{len(to_run)} {args.benchmark}/{task['scenario']}/{task['slug']} attempt={attempt}")
            entry = run_one_task(task=task, attempt=attempt, pass_index=pass_index, args=args)
            manifest.append(entry)
            attempts_by_key[key].append(entry)
            if not args.dry_run:
                append_jsonl(manifest_path, entry)
                rows = write_aggregate_outputs(manifest=manifest, args=args, tasks=tasks)
                print(f"[checkpoint] outcome={entry.get('outcome')} aggregated_rows={len(rows)}")
            if not args.dry_run and index < len(to_run):
                sleep_for = cooldown
                if entry.get("outcome") == "agent_error" and entry.get("transient_model_failure"):
                    sleep_for = max(sleep_for, args.retry_cooldown_sec)
                    hint = entry.get("cooldown_hint_sec")
                    if isinstance(hint, int):
                        sleep_for = max(sleep_for, hint + 10)
                    elif args.transient_agent_error_cooldown_sec is not None:
                        sleep_for = max(sleep_for, args.transient_agent_error_cooldown_sec)
                    print(f"[checkpoint] transient agent_error cooldown={sleep_for}s")
                if sleep_for > 0:
                    time.sleep(sleep_for)

    if not args.dry_run:
        rows = write_aggregate_outputs(manifest=manifest, args=args, tasks=tasks)
        expected = len(tasks) if args.targets_file or args.limit_per_scenario is not None else sum(TASK_COUNTS.values())
        print(f"[checkpoint] wrote {len(rows)}/{expected} aggregated row(s) to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
