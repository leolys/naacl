#!/usr/bin/env python3
"""Merge Sonnet 4.6 official and clean checkpoint outputs into pair records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_SLUG = "claude_sonnet_4_6_aime_responses_temp0_top_p1_seed12345"
SCENARIOS = ["public39", "business47", "environment35", "health19"]
BENCHMARKS = ["official", "clean"]
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


def sort_key(row: dict[str, Any]) -> tuple[int, str]:
    return SCENARIOS.index(str(row.get("scenario"))), str(row.get("slug"))


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


def write_summary(path: Path, rows: list[dict[str, Any]], *, benchmark: str) -> None:
    summary = summarize_rows(rows)
    lines = [
        f"# Sonnet 4.6 {benchmark} Checkpoint Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Model slug: `{MODEL_SLUG}`",
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


def pair_category(official: dict[str, Any] | None, clean: dict[str, Any] | None) -> str:
    official_success = bool(official and official.get("outcome") == "success")
    clean_success = bool(clean and clean.get("outcome") == "success")
    if official_success and clean_success:
        return "official_success_clean_success"
    if (not official_success) and clean_success:
        return "official_misleading_clean_success"
    if official_success and not clean_success:
        return "clean_regression"
    return "both_failed"


def copy_benchmark(*, source_root: Path, output_root: Path, benchmark: str) -> list[dict[str, Any]]:
    source_dir = source_root / MODEL_SLUG / benchmark
    output_dir = output_root / MODEL_SLUG / benchmark
    rows = read_jsonl(source_dir / "runs.jsonl")
    if len(rows) != 140:
        raise RuntimeError(f"{source_dir / 'runs.jsonl'} expected 140 rows, found {len(rows)}")
    rows.sort(key=sort_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "runs.jsonl", rows)
    failures = [row for row in rows if row.get("outcome") != "success"]
    write_jsonl(output_dir / "failures.jsonl", failures)
    write_jsonl(output_dir / "transient_failures.jsonl", [row for row in failures if is_transient_model_failure(row)])
    write_jsonl(output_dir / "agent_error_targets.jsonl", [row for row in rows if row.get("outcome") == "agent_error"])
    write_summary(output_dir / "summary.md", rows, benchmark=benchmark)
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "record_type": "sonnet46_checkpoint_pair_final",
                "source_dir": str(source_dir),
                "output_dir": str(output_dir),
                "outcome_counts": dict(Counter(row.get("outcome") for row in rows)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def write_pair_outputs(output_root: Path, official_rows: list[dict[str, Any]], clean_rows: list[dict[str, Any]]) -> None:
    official_by_key = {row_key(row): row for row in official_rows}
    clean_by_key = {row_key(row): row for row in clean_rows}
    all_keys = sorted(set(official_by_key) | set(clean_by_key), key=lambda key: (SCENARIOS.index(key[0]), key[1]))
    paired_rows: list[dict[str, Any]] = []
    for scenario, slug in all_keys:
        official = official_by_key.get((scenario, slug))
        clean = clean_by_key.get((scenario, slug))
        paired_rows.append(
            {
                "model_key": "claude_sonnet_4_6_aime_responses",
                "scenario": scenario,
                "slug": slug,
                "task_id": (official or clean or {}).get("task_id"),
                "official_outcome": official.get("outcome") if official else None,
                "clean_outcome": clean.get("outcome") if clean else None,
                "official_selected_action_label": official.get("selected_action_label") if official else None,
                "clean_selected_action_label": clean.get("selected_action_label") if clean else None,
                "pair_category": pair_category(official, clean),
            }
        )
    write_jsonl(output_root / "paired_results.jsonl", paired_rows)
    counts = Counter(row["pair_category"] for row in paired_rows)
    official_success = sum(1 for row in paired_rows if row.get("official_outcome") == "success")
    clean_success = sum(1 for row in paired_rows if row.get("clean_outcome") == "success")
    total = len(paired_rows)
    lines = [
        "# Sonnet 4.6 Checkpoint Pair Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Paired rows: `{total}`",
        f"- Official success rate: `{official_success}/{total} ({(official_success / total if total else 0):.2%})`",
        f"- Clean success rate: `{clean_success}/{total} ({(clean_success / total if total else 0):.2%})`",
        f"- Clean minus official success rate: `{((clean_success - official_success) / total if total else 0):.2%}`",
        f"- Pair categories: `{dict(counts)}`",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category, count in sorted(counts.items()):
        lines.append(f"| {category} | {count} |")
    (output_root / "pair_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--clean-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    official_rows = copy_benchmark(source_root=args.official_root.resolve(), output_root=output_root, benchmark="official")
    clean_rows = copy_benchmark(source_root=args.clean_root.resolve(), output_root=output_root, benchmark="clean")
    write_pair_outputs(output_root, official_rows, clean_rows)
    print(f"Wrote Sonnet 4.6 checkpoint pair records to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
