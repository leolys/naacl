#!/usr/bin/env python3
"""Run Gemini 3 Pro thinking-budget probe variants on selected agent-error tasks."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PAIR_RUNNER = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_pair_benchmarks.py"
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "gemini3pro_thinking_budget_probe_20260518"
)
MODEL_RECORD_DIR = "gemini_3_pro_image_preview_temp0_top_p1_seed12345"

OFFICIAL_TASK_OVERRIDES = "public39=pub018,pub032;business47=b008,b017,b032,b035"
CLEAN_TASK_OVERRIDES = "public39=pub016;business47=b002,b020,b024,b047"

BASE_VARIANTS: list[dict[str, str | None]] = [
    {
        "name": "v0_baseline_8096",
        "extra_body": None,
        "thinking_budget_supported": "unknown",
    },
    {
        "name": "v1_reasoning_effort_low",
        "extra_body": '{"reasoning_effort":"low"}',
        "thinking_budget_supported": "unknown",
    },
    {
        "name": "v2_thinking_budget_512",
        "extra_body": '{"thinking":{"type":"enabled","budget_tokens":512}}',
        "thinking_budget_supported": "unknown",
    },
]
OPTIONAL_ZERO_VARIANT = {
    "name": "v3_thinking_budget_0",
    "extra_body": '{"thinking":{"type":"enabled","budget_tokens":0}}',
    "thinking_budget_supported": "unknown",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_command(cmd: list[str], *, env: dict[str, str], dry_run: bool) -> int:
    print("[probe] " + " ".join(cmd))
    if dry_run:
        return 0
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, text=True, check=False)
    return completed.returncode


def build_command(
    *,
    benchmark: str,
    task_overrides: str,
    variant_name: str,
    extra_body: str | None,
    thinking_budget_supported: str,
    output_root: Path,
    args: argparse.Namespace,
) -> list[str]:
    cmd = [
        sys.executable,
        str(PAIR_RUNNER),
        "--benchmark",
        benchmark,
        "--models",
        "gemini3pro_image_preview",
        "--profile",
        "full",
        "--model-max-output-tokens",
        str(args.model_max_output_tokens),
        "--aime-max-retries",
        str(args.aime_max_retries),
        "--aime-request-delay-sec",
        str(args.aime_request_delay_sec),
        "--aime-read-timeout-sec",
        str(args.aime_read_timeout_sec),
        "--max-steps",
        str(args.max_steps),
        "--task-overrides",
        task_overrides,
        "--record-root",
        str(output_root / variant_name),
        "--experiment-variant",
        variant_name,
        "--thinking-budget-supported",
        thinking_budget_supported,
        "--port-offset",
        str(args.port_offset),
    ]
    if extra_body:
        cmd.extend(["--aime-extra-body-json", extra_body])
    return cmd


def exception_class(row: dict[str, Any]) -> str:
    text = str(row.get("exception", ""))
    trace_text = json.dumps(row.get("trace", []), ensure_ascii=False)
    haystack = f"{text}\n{trace_text}".lower()
    if "empty content" in haystack or "content': none" in haystack:
        return "empty_content"
    if "no json object found" in haystack:
        return "no_json_object"
    if "timed out" in haystack or "timeout" in haystack:
        return "timeout"
    if "http error 400" in haystack or "unsupported" in haystack or "unknown field" in haystack:
        return "unsupported_parameter"
    return "other"


def token_values(row: dict[str, Any]) -> list[tuple[int | None, int | None, int | None]]:
    values: list[tuple[int | None, int | None, int | None]] = []
    pattern = re.compile(
        r"'completion_tokens': (?P<completion>\d+).*?"
        r"'reasoning_tokens': (?P<reasoning>\d+).*?"
        r"'text_tokens': (?P<text>\d+)",
        re.S,
    )
    for match in pattern.finditer(str(row.get("exception", ""))):
        values.append(
            (
                int(match.group("completion")),
                int(match.group("reasoning")),
                int(match.group("text")),
            )
        )
    for step in row.get("trace") or []:
        metadata = ((step.get("action") or {}).get("_response_metadata") or {})
        usage = metadata.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        if usage:
            values.append(
                (
                    usage.get("completion_tokens"),
                    details.get("reasoning_tokens"),
                    details.get("text_tokens"),
                )
            )
    return values


def summarize_variant(variant_root: Path) -> dict[str, Any]:
    model_root = variant_root / MODEL_RECORD_DIR
    summary: dict[str, Any] = {"variant": variant_root.name, "benchmarks": {}}
    for benchmark in ["official", "clean"]:
        rows = read_jsonl(model_root / benchmark / "runs.jsonl")
        outcome_counts = Counter(row.get("outcome", "") for row in rows)
        agent_errors = [row for row in rows if row.get("outcome") == "agent_error"]
        error_classes = Counter(exception_class(row) for row in agent_errors)
        all_token_values = [value for row in agent_errors for value in token_values(row)]
        near_budget_no_text = sum(
            1
            for _, reasoning, text in all_token_values
            if reasoning is not None and reasoning >= 8000 and (text or 0) == 0
        )
        summary["benchmarks"][benchmark] = {
            "rows": len(rows),
            "outcomes": dict(outcome_counts),
            "agent_error_classes": dict(error_classes),
            "near_budget_no_text": near_budget_no_text,
        }
    return summary


def write_summary(output_root: Path, summaries: list[dict[str, Any]]) -> None:
    lines = [
        "# Gemini3Pro Thinking Budget Probe Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Output root: `{output_root}`",
        "",
        "| Variant | Benchmark | Rows | Outcomes | Agent Error Classes | Near-Budget No-Text |",
        "|---|---|---:|---|---|---:|",
    ]
    for summary in summaries:
        for benchmark, row in summary["benchmarks"].items():
            lines.append(
                f"| {summary['variant']} | {benchmark} | {row['rows']} | "
                f"`{row['outcomes']}` | `{row['agent_error_classes']}` | "
                f"{row['near_budget_no_text']} |"
            )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "probe_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_root / "probe_summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    variants = list(BASE_VARIANTS)
    if args.include_thinking_budget_zero:
        variants.append(OPTIONAL_ZERO_VARIANT)
    env = os.environ.copy()
    if not args.dry_run and not env.get("AIME_LITELLM_API_KEY"):
        raise RuntimeError("AIME_LITELLM_API_KEY is required to run the probe.")
    summaries: list[dict[str, Any]] = []
    for variant in variants:
        variant_name = str(variant["name"])
        extra_body = variant["extra_body"]
        thinking_budget_supported = str(variant["thinking_budget_supported"])
        official_cmd = build_command(
            benchmark="official",
            task_overrides=OFFICIAL_TASK_OVERRIDES,
            variant_name=variant_name,
            extra_body=extra_body,
            thinking_budget_supported=thinking_budget_supported,
            output_root=args.output_root,
            args=args,
        )
        clean_cmd = build_command(
            benchmark="clean",
            task_overrides=CLEAN_TASK_OVERRIDES,
            variant_name=variant_name,
            extra_body=extra_body,
            thinking_budget_supported=thinking_budget_supported,
            output_root=args.output_root,
            args=args,
        )
        for cmd in [official_cmd, clean_cmd]:
            returncode = run_command(cmd, env=env, dry_run=args.dry_run)
            if returncode != 0:
                return returncode
        if not args.dry_run:
            summaries.append(summarize_variant(args.output_root / variant_name))
    if not args.dry_run:
        write_summary(args.output_root, summaries)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--model-max-output-tokens", type=int, default=8096)
    parser.add_argument("--aime-max-retries", type=int, default=2)
    parser.add_argument("--aime-request-delay-sec", type=float, default=2.0)
    parser.add_argument("--aime-read-timeout-sec", type=float, default=300.0)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--port-offset", type=int, default=0)
    parser.add_argument("--include-thinking-budget-zero", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
