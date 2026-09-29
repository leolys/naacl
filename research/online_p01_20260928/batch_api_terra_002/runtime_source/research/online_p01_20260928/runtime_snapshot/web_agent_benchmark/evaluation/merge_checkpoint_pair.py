#!/usr/bin/env python3
"""Merge official and clean checkpoint outputs into pair records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCENARIOS = ["public39", "business47", "environment35", "health19"]
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
    scenario = str(row.get("scenario"))
    return SCENARIOS.index(scenario), str(row.get("slug"))


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
        success_count = scenario_counts.get("success", 0)
        by_scenario[scenario] = {
            "task_count": len(subset),
            "success_count": success_count,
            "success_rate": success_count / len(subset),
            "outcome_counts": dict(scenario_counts),
        }
    success_count = counts.get("success", 0)
    return {
        "task_count": len(rows),
        "success_count": success_count,
        "success_rate": success_count / len(rows) if rows else 0.0,
        "outcome_counts": dict(counts),
        "by_scenario": by_scenario,
    }


def write_summary(path: Path, rows: list[dict[str, Any]], *, model_slug: str, benchmark: str) -> None:
    summary = summarize_rows(rows)
    lines = [
        f"# {model_slug} {benchmark} Checkpoint Summary",
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


def copy_benchmark(
    *,
    source_root: Path,
    output_root: Path,
    model_slug: str,
    benchmark: str,
    expected_rows: int,
    supplement_root: Path | None = None,
) -> list[dict[str, Any]]:
    source_dir = source_root / model_slug / benchmark
    output_dir = output_root / model_slug / benchmark
    scenario_paths = sorted((source_dir / "_scenario_outputs").glob("*/runs.jsonl"))
    rows = []
    if scenario_paths:
        for path in scenario_paths:
            scenario = path.parent.name
            for row in read_jsonl(path):
                row.setdefault("scenario", scenario)
                rows.append(row)
    else:
        rows = read_jsonl(source_dir / "runs.jsonl")
    if supplement_root is not None:
        supplement_dir = supplement_root / model_slug / benchmark
        supplement_rows = []
        supplement_paths = sorted((supplement_dir / "_scenario_outputs").glob("*/runs.jsonl"))
        if supplement_paths:
            for path in supplement_paths:
                scenario = path.parent.name
                for row in read_jsonl(path):
                    row.setdefault("scenario", scenario)
                    supplement_rows.append(row)
        else:
            supplement_rows = read_jsonl(supplement_dir / "runs.jsonl")
        if not supplement_rows:
            raise RuntimeError(f"No supplemental rows found in {supplement_dir / 'runs.jsonl'}")
        rows.extend(supplement_rows)
    keyed_rows = {row_key(row): row for row in rows}
    if len(keyed_rows) != len(rows):
        raise RuntimeError(f"Duplicate scenario/slug keys while merging {benchmark} rows")
    rows = list(keyed_rows.values())
    if len(rows) != expected_rows:
        raise RuntimeError(f"{source_dir / 'runs.jsonl'} expected {expected_rows} rows, found {len(rows)}")
    rows.sort(key=sort_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "runs.jsonl", rows)
    failures = [row for row in rows if row.get("outcome") != "success"]
    write_jsonl(output_dir / "failures.jsonl", failures)
    write_jsonl(output_dir / "transient_failures.jsonl", [row for row in failures if is_transient_model_failure(row)])
    write_jsonl(output_dir / "agent_error_targets.jsonl", [row for row in rows if row.get("outcome") == "agent_error"])
    write_summary(output_dir / "summary.md", rows, model_slug=model_slug, benchmark=benchmark)
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "record_type": "checkpoint_pair_final",
                "model_slug": model_slug,
                "benchmark": benchmark,
                "source_dir": str(source_dir),
                "supplement_dir": (
                    str(supplement_root / model_slug / benchmark) if supplement_root else None
                ),
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


def write_pair_outputs(
    *,
    output_root: Path,
    official_rows: list[dict[str, Any]],
    clean_rows: list[dict[str, Any]],
    model_key: str,
) -> None:
    official_by_key = {row_key(row): row for row in official_rows}
    clean_by_key = {row_key(row): row for row in clean_rows}
    all_keys = sorted(set(official_by_key) | set(clean_by_key), key=lambda key: (SCENARIOS.index(key[0]), key[1]))
    paired_rows: list[dict[str, Any]] = []
    for scenario, slug in all_keys:
        official = official_by_key.get((scenario, slug))
        clean = clean_by_key.get((scenario, slug))
        paired_rows.append(
            {
                "model_key": model_key,
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
        f"# {model_key} Checkpoint Pair Summary",
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
    parser.add_argument(
        "--clean-supplement-root",
        type=Path,
        help="Optional root containing additional non-overlapping clean rows.",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--model-slug", required=True)
    parser.add_argument("--expected-rows", type=int, default=140)
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    official_rows = copy_benchmark(
        source_root=args.official_root.resolve(),
        output_root=output_root,
        model_slug=args.model_slug,
        benchmark="official",
        expected_rows=args.expected_rows,
    )
    clean_rows = copy_benchmark(
        source_root=args.clean_root.resolve(),
        output_root=output_root,
        model_slug=args.model_slug,
        benchmark="clean",
        expected_rows=args.expected_rows,
        supplement_root=(
            args.clean_supplement_root.resolve() if args.clean_supplement_root else None
        ),
    )
    write_pair_outputs(
        output_root=output_root,
        official_rows=official_rows,
        clean_rows=clean_rows,
        model_key=args.model_key,
    )
    print(f"Wrote checkpoint pair records to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
