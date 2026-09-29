#!/usr/bin/env python3
"""Merge Gemini 3 Pro targeted agent-error repair runs.

The merge is conservative: only base rows whose original outcome is
`agent_error` are eligible for replacement. All other base rows are kept
unchanged, so the original full-run baseline remains auditable.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ["official", "clean"]
SCENARIOS = ["public39", "business47", "environment35", "health19"]


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


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario")), str(row.get("slug"))


def is_transient_model_failure(row: dict[str, Any]) -> bool:
    if row.get("outcome") == "success":
        return False
    haystack = " ".join(
        [
            str(row.get("exception", "")),
            str(row.get("error_attribution", "")),
            json.dumps(row.get("trace", []), ensure_ascii=False),
        ]
    ).lower()
    markers = [
        "transient http",
        "http 429",
        "http 502",
        "http 503",
        "http 504",
        "connection error",
        "timed out",
        "empty response",
        "empty final content",
        "empty content",
        "llm_action_generation_error",
    ]
    return any(marker in haystack for marker in markers)


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
        f"# Gemini 3 Pro Agent-Error Repaired {benchmark} Summary",
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


def write_pair_summary(all_rows: list[dict[str, Any]], output_root: Path) -> None:
    by_key: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    for row in all_rows:
        key = (str(row.get("model_key")), str(row.get("scenario")), str(row.get("slug")), str(row.get("task_id")))
        by_key.setdefault(key, {})[str(row.get("benchmark"))] = row

    paired_rows: list[dict[str, Any]] = []
    for (model_key, scenario, slug, task_id), pair in sorted(by_key.items()):
        official = pair.get("official")
        clean = pair.get("clean")
        paired_rows.append(
            {
                "model_key": model_key,
                "scenario": scenario,
                "slug": slug,
                "task_id": task_id,
                "official_outcome": official.get("outcome") if official else None,
                "clean_outcome": clean.get("outcome") if clean else None,
                "official_selected_action_label": official.get("selected_action_label") if official else None,
                "clean_selected_action_label": clean.get("selected_action_label") if clean else None,
                "pair_category": pair_category(official, clean),
            }
        )
    write_jsonl(output_root / "paired_results.jsonl", paired_rows)

    lines = [
        "# Gemini 3 Pro Agent-Error Repaired Pair Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Paired rows: `{len(paired_rows)}`",
        "",
    ]
    for model_key in sorted({row["model_key"] for row in paired_rows}):
        subset = [row for row in paired_rows if row["model_key"] == model_key]
        total = len(subset)
        official_success = sum(1 for row in subset if row.get("official_outcome") == "success")
        clean_success = sum(1 for row in subset if row.get("clean_outcome") == "success")
        counts = Counter(row["pair_category"] for row in subset)
        lines.extend(
            [
                f"## {model_key}",
                "",
                f"- Official success rate: `{official_success}/{total} ({(official_success / total if total else 0):.2%})`",
                f"- Clean success rate: `{clean_success}/{total} ({(clean_success / total if total else 0):.2%})`",
                f"- Clean minus official success rate: `{((clean_success - official_success) / total if total else 0):.2%}`",
                f"- Pair categories: `{dict(counts)}`",
                "",
                "| Category | Count |",
                "|---|---:|",
            ]
        )
        for category, count in sorted(counts.items()):
            lines.append(f"| {category} | {count} |")
        lines.append("")
    (output_root / "pair_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_benchmark(
    *,
    base_model_slug: str,
    repair_model_slug: str,
    output_model_slug: str,
    benchmark: str,
    base_root: Path,
    repair_root: Path,
    output_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    base_dir = base_root / base_model_slug / benchmark
    repair_dir = repair_root / repair_model_slug / benchmark
    out_dir = output_root / output_model_slug / benchmark

    base_rows = read_jsonl(base_dir / "runs.jsonl")
    repair_rows = read_jsonl(repair_dir / "runs.jsonl")
    if len(base_rows) != 140:
        raise RuntimeError(f"{base_dir / 'runs.jsonl'} expected 140 rows, found {len(base_rows)}")

    base_by_key = {row_key(row): dict(row) for row in base_rows}
    if len(base_by_key) != len(base_rows):
        raise RuntimeError(f"{base_dir / 'runs.jsonl'} has duplicate scenario/slug rows")

    repair_by_key = {row_key(row): dict(row) for row in repair_rows}
    merged_by_key = dict(base_by_key)
    manifest: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for key, repair_row in sorted(repair_by_key.items()):
        base_row = base_by_key.get(key)
        if not base_row:
            skipped.append({"benchmark": benchmark, "scenario": key[0], "slug": key[1], "reason": "not_in_base"})
            continue
        if base_row.get("outcome") != "agent_error":
            skipped.append(
                {
                    "benchmark": benchmark,
                    "scenario": key[0],
                    "slug": key[1],
                    "reason": "base_outcome_not_agent_error",
                    "base_outcome": base_row.get("outcome"),
                    "repair_outcome": repair_row.get("outcome"),
                }
            )
            continue
        merged_row = dict(repair_row)
        merged_row["model_key"] = base_row.get("model_key", repair_row.get("model_key"))
        merged_row["model_metadata"] = base_row.get("model_metadata", repair_row.get("model_metadata"))
        merged_row["repair_source"] = "agent_error_repair"
        merged_row["base_outcome_before_repair"] = base_row.get("outcome")
        merged_row["base_error_attribution_before_repair"] = base_row.get("error_attribution")
        merged_row["repair_model_key"] = repair_row.get("model_key")
        merged_row["repair_model_metadata"] = repair_row.get("model_metadata")
        merged_by_key[key] = merged_row
        manifest.append(
            {
                "base_model_slug": base_model_slug,
                "repair_model_slug": repair_model_slug,
                "output_model_slug": output_model_slug,
                "benchmark": benchmark,
                "scenario": key[0],
                "slug": key[1],
                "task_id": repair_row.get("task_id"),
                "base_outcome": base_row.get("outcome"),
                "repair_outcome": repair_row.get("outcome"),
                "base_error_attribution": base_row.get("error_attribution"),
                "repair_error_attribution": repair_row.get("error_attribution"),
                "base_record_dir": base_row.get("record_dir"),
                "repair_record_dir": repair_row.get("record_dir"),
            }
        )

    merged_rows = list(merged_by_key.values())
    merged_rows.sort(key=lambda row: (SCENARIOS.index(str(row.get("scenario"))), str(row.get("slug"))))
    if len(merged_rows) != 140:
        raise RuntimeError(f"{output_model_slug}/{benchmark} merged row count is {len(merged_rows)}, expected 140")

    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "runs.jsonl", merged_rows)
    failures = [row for row in merged_rows if row.get("outcome") != "success"]
    write_jsonl(out_dir / "failures.jsonl", failures)
    write_jsonl(out_dir / "transient_failures.jsonl", [row for row in failures if is_transient_model_failure(row)])
    write_summary(out_dir / "summary.md", merged_rows, model_slug=output_model_slug, benchmark=benchmark)
    (out_dir / "run_config.json").write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "record_type": "gemini3pro_agent_error_repaired",
                "base_dir": display_path(base_dir),
                "repair_dir": display_path(repair_dir),
                "base_model_slug": base_model_slug,
                "repair_model_slug": repair_model_slug,
                "output_model_slug": output_model_slug,
                "replacement_policy": "replace only base rows whose outcome is agent_error",
                "base_outcome_counts": dict(Counter(row.get("outcome") for row in base_rows)),
                "repair_outcome_counts": dict(Counter(row.get("outcome") for row in repair_rows)),
                "merged_outcome_counts": dict(Counter(row.get("outcome") for row in merged_rows)),
                "replaced_count": len(manifest),
                "skipped_repair_rows": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(
        f"# Gemini 3 Pro {benchmark} Agent-Error Repaired Record\n\n"
        "This directory merges the original full Gemini 3 Pro run with targeted reruns "
        "for rows whose original outcome was `agent_error`.\n\n"
        f"- Base directory: `{display_path(base_dir)}`\n"
        f"- Repair directory: `{display_path(repair_dir)}`\n"
        f"- Base model slug: `{base_model_slug}`\n"
        f"- Repair model slug: `{repair_model_slug}`\n"
        f"- Output model slug: `{output_model_slug}`\n"
        f"- Replaced rows: `{len(manifest)}`\n"
        f"- Output rows: `{len(merged_rows)}`\n",
        encoding="utf-8",
    )

    stats = {
        "benchmark": benchmark,
        "base_rows": len(base_rows),
        "repair_rows": len(repair_rows),
        "replaced_count": len(manifest),
        "skipped_count": len(skipped),
        "base_outcome_counts": dict(Counter(row.get("outcome") for row in base_rows)),
        "repair_outcome_counts": dict(Counter(row.get("outcome") for row in repair_rows)),
        "merged_outcome_counts": dict(Counter(row.get("outcome") for row in merged_rows)),
    }
    return merged_rows, manifest, stats


def write_repair_summary(output_root: Path, stats_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Gemini 3 Pro Agent-Error Repair Merge Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        "",
        "| Benchmark | Base Outcomes | Repair Outcomes | Merged Outcomes | Replaced |",
        "|---|---|---|---|---:|",
    ]
    for row in stats_rows:
        lines.append(
            f"| {row['benchmark']} | `{row['base_outcome_counts']}` | "
            f"`{row['repair_outcome_counts']}` | `{row['merged_outcome_counts']}` | "
            f"{row['replaced_count']} |"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "repair_merge_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--repair-root", type=Path, required=True)
    parser.add_argument("--model-slug", help="Backward-compatible alias for using the same base/repair/output slug.")
    parser.add_argument("--base-model-slug")
    parser.add_argument("--repair-model-slug")
    parser.add_argument("--output-model-slug")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    base_model_slug = args.base_model_slug or args.model_slug
    repair_model_slug = args.repair_model_slug or args.model_slug
    output_model_slug = args.output_model_slug or base_model_slug
    if not base_model_slug or not repair_model_slug or not output_model_slug:
        raise RuntimeError(
            "Provide either --model-slug, or all required split slugs via "
            "--base-model-slug and --repair-model-slug."
        )

    base_root = args.base_root.resolve()
    repair_root = args.repair_root.resolve()
    output_root = args.output_root.resolve()
    all_rows: list[dict[str, Any]] = []
    replacement_manifest: list[dict[str, Any]] = []
    stats_rows: list[dict[str, Any]] = []

    for benchmark in BENCHMARKS:
        rows, manifest, stats = merge_benchmark(
            base_model_slug=base_model_slug,
            repair_model_slug=repair_model_slug,
            output_model_slug=output_model_slug,
            benchmark=benchmark,
            base_root=base_root,
            repair_root=repair_root,
            output_root=output_root,
        )
        all_rows.extend(rows)
        replacement_manifest.extend(manifest)
        stats_rows.append(stats)

    write_jsonl(output_root / "replacement_manifest.jsonl", replacement_manifest)
    write_pair_summary(all_rows, output_root)
    write_repair_summary(output_root, stats_rows)
    print(f"Wrote Gemini 3 Pro agent-error repaired records to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
