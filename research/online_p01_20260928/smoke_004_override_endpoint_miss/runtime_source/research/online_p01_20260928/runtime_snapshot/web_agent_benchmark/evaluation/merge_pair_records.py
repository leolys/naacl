#!/usr/bin/env python3
"""Merge full benchmark records with targeted reruns.

This script keeps the original full-run records intact and writes a final merged
record tree where targeted reruns replace matching `(model, benchmark, scenario,
slug)` rows.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
MODEL_SLUGS = ["gpt54_temp0_top_p1_seed12345", "kimik2_6_temp0_top_p1_seed12345"]
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


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario")), str(row.get("slug"))


def load_group(path: Path, *, expected: int | None = None) -> list[dict[str, Any]]:
    rows = read_jsonl(path / "runs.jsonl")
    if expected is not None and len(rows) != expected:
        raise RuntimeError(f"{path / 'runs.jsonl'} expected {expected} rows, found {len(rows)}")
    return rows


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
        "kimi k2.6 request failed",
        "transient http",
        "http 429",
        "http 502",
        "http 503",
        "http 504",
        "connection error",
        "timed out",
        "empty response",
        "empty final content",
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
        f"# Final Merged {model_slug} {benchmark} Summary",
        "",
        f"- Generated at: `{utc_now()}`",
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


def write_pair_summary(all_rows: list[dict[str, Any]], out_root: Path) -> None:
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
    write_jsonl(out_root / "paired_results.jsonl", paired_rows)
    lines = [
        "# Final Merged Official/Clean Pair Summary",
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
    (out_root / "pair_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-root", type=Path, default=DEFAULT_RECORD_ROOT)
    parser.add_argument("--replacement-root", type=Path, required=True)
    parser.add_argument("--patch-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    record_root = args.record_root.resolve()
    replacement_root = args.replacement_root.resolve()
    patch_root = args.patch_root.resolve()
    output_root = args.output_root.resolve()

    replacement_manifest: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for model_slug in MODEL_SLUGS:
        for benchmark in BENCHMARKS:
            base_dir = record_root / model_slug / benchmark
            replacement_dir = replacement_root / model_slug / benchmark
            patch_dir = patch_root / model_slug / benchmark
            out_dir = output_root / model_slug / benchmark

            base_rows = load_group(base_dir, expected=140)
            merged_by_key = {row_key(row): dict(row) for row in base_rows}
            if len(merged_by_key) != 140:
                raise RuntimeError(f"{base_dir} has duplicate scenario/slug keys")

            for row in load_group(replacement_dir, expected=27):
                key = row_key(row)
                if key not in merged_by_key:
                    raise RuntimeError(f"Replacement key missing from base: {model_slug}/{benchmark}/{key}")
                merged_by_key[key] = dict(row)
                replacement_manifest.append(
                    {
                        "model_slug": model_slug,
                        "benchmark": benchmark,
                        "scenario": key[0],
                        "slug": key[1],
                        "source": "modified_samples_rerun_20260516",
                    }
                )

            if patch_dir.exists():
                for row in load_group(patch_dir):
                    key = row_key(row)
                    if key != ("health19", "health012"):
                        raise RuntimeError(f"Unexpected patch row: {model_slug}/{benchmark}/{key}")
                    merged_by_key[key] = dict(row)
                    replacement_manifest.append(
                        {
                            "model_slug": model_slug,
                            "benchmark": benchmark,
                            "scenario": key[0],
                            "slug": key[1],
                            "source": "health012_gpt54_clean_rerun_20260517",
                            "outcome": row.get("outcome"),
                            "trace_len": len(row.get("trace") or []),
                        }
                    )

            merged_rows = list(merged_by_key.values())
            merged_rows.sort(key=lambda row: (SCENARIOS.index(str(row.get("scenario"))), str(row.get("slug"))))
            if len(merged_rows) != 140:
                raise RuntimeError(f"{model_slug}/{benchmark} merged row count is {len(merged_rows)}, expected 140")

            out_dir.mkdir(parents=True, exist_ok=True)
            write_jsonl(out_dir / "runs.jsonl", merged_rows)
            failures = [row for row in merged_rows if row.get("outcome") != "success"]
            write_jsonl(out_dir / "failures.jsonl", failures)
            write_jsonl(out_dir / "transient_failures.jsonl", [row for row in failures if is_transient_model_failure(row)])
            write_summary(out_dir / "summary.md", merged_rows, model_slug=model_slug, benchmark=benchmark)
            (out_dir / "run_config.json").write_text(
                json.dumps(
                    {
                        "generated_at": utc_now(),
                        "record_type": "final_merged",
                        "base_dir": str(base_dir.relative_to(REPO_ROOT)),
                        "replacement_dir": str(replacement_dir.relative_to(REPO_ROOT)),
                        "patch_dir": str(patch_dir.relative_to(REPO_ROOT)) if patch_dir.exists() else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            all_rows.extend(merged_rows)

    write_jsonl(output_root / "replacement_manifest.jsonl", replacement_manifest)
    write_pair_summary(all_rows, output_root)
    print(f"Wrote final merged records to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
