#!/usr/bin/env python3
"""Merge partial Claude Opus 4.6 clean run with checkpoint repair rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
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


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario")), str(row.get("slug"))


def task_slug(row: dict[str, Any]) -> str:
    value = row.get("clean_slug") or row.get("slug") or row.get("official_slug")
    if not value:
        raise RuntimeError(f"Could not determine slug from task row: {row}")
    return str(value)


def load_expected_tasks(clean_root: Path) -> list[tuple[str, str]]:
    tasks: list[tuple[str, str]] = []
    for scenario in SCENARIOS:
        for row in read_jsonl(clean_root / TASK_FILES[scenario]):
            tasks.append((scenario, task_slug(row)))
    return tasks


def read_base_rows(base_clean_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    top_level = read_jsonl(base_clean_dir / "runs.jsonl")
    source_rows = top_level
    if not source_rows:
        for scenario in SCENARIOS:
            for row in read_jsonl(base_clean_dir / "_scenario_outputs" / scenario / "runs.jsonl"):
                row.setdefault("scenario", scenario)
                row.setdefault("scenario_slug", scenario)
                source_rows.append(row)
    for row in source_rows:
        rows[row_key(row)] = dict(row)
    return rows


def read_repair_rows(repair_clean_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in read_jsonl(repair_clean_dir / "runs.jsonl"):
        rows[row_key(row)] = dict(row)
    if not rows:
        for scenario in SCENARIOS:
            for row in read_jsonl(repair_clean_dir / "_scenario_outputs" / scenario / "runs.jsonl"):
                row.setdefault("scenario", scenario)
                row.setdefault("scenario_slug", scenario)
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
        "# Claude Opus 4.6 Clean Repair-Merged Summary",
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-clean-dir", type=Path, required=True)
    parser.add_argument("--repair-clean-dir", type=Path, required=True)
    parser.add_argument("--output-clean-dir", type=Path, required=True)
    parser.add_argument("--clean-root", type=Path, default=REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1")
    parser.add_argument("--model-slug", default="claude_opus_4_6_aime_responses_temp0_top_p1_seed12345")
    args = parser.parse_args()

    expected = load_expected_tasks(args.clean_root)
    base = read_base_rows(args.base_clean_dir)
    repair = read_repair_rows(args.repair_clean_dir)
    merged: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []

    for key in expected:
        base_row = base.get(key)
        repair_row = repair.get(key)
        chosen = None
        source = None
        if base_row is not None and base_row.get("outcome") != "agent_error":
            chosen = dict(base_row)
            source = "base"
        elif repair_row is not None:
            chosen = dict(repair_row)
            source = "repair"
            if base_row is not None:
                chosen["base_outcome_before_repair"] = base_row.get("outcome")
                chosen["base_error_attribution_before_repair"] = base_row.get("error_attribution")
        elif base_row is not None:
            chosen = dict(base_row)
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
                "base_outcome": base_row.get("outcome") if base_row else None,
                "repair_outcome": repair_row.get("outcome") if repair_row else None,
                "merged_outcome": chosen.get("outcome"),
            }
        )

    merged.sort(key=lambda row: (SCENARIOS.index(str(row.get("scenario"))), str(row.get("slug"))))
    failures = [row for row in merged if row.get("outcome") != "success"]
    args.output_clean_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_clean_dir / "runs.jsonl", merged)
    write_jsonl(args.output_clean_dir / "failures.jsonl", failures)
    write_jsonl(args.output_clean_dir / "transient_failures.jsonl", [row for row in failures if is_transient_model_failure(row)])
    write_jsonl(args.output_clean_dir / "repair_merge_manifest.jsonl", manifest)
    write_jsonl(args.output_clean_dir / "missing_after_merge.jsonl", missing)
    write_summary(args.output_clean_dir / "summary.md", merged, model_slug=args.model_slug)
    (args.output_clean_dir / "run_config.json").write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "record_type": "claude_opus46_clean_repair_merged",
                "base_clean_dir": str(args.base_clean_dir),
                "repair_clean_dir": str(args.repair_clean_dir),
                "output_clean_dir": str(args.output_clean_dir),
                "expected_rows": len(expected),
                "merged_rows": len(merged),
                "missing_rows": len(missing),
                "source_counts": dict(Counter(item["source"] for item in manifest)),
                "outcome_counts": dict(Counter(row.get("outcome") for row in merged)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"merged_rows={len(merged)} expected={len(expected)} missing={len(missing)} output={args.output_clean_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
