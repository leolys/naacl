#!/usr/bin/env python3
"""Build a mechanism-stratified mini-set for prompt-intervention experiments."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
DEFAULT_INPUT_ROOT = DEFAULT_RECORD_ROOT / "final_selected_merged_20260523_kimi_full140_replaced"
DEFAULT_OUTPUT_ROOT = DEFAULT_RECORD_ROOT / "prompt_intervention_miniset_20260525"
SCENARIO_ORDER = ["public39", "business47", "environment35", "health19"]


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


def task_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    scenario = str(row["scenario"])
    scenario_idx = SCENARIO_ORDER.index(scenario) if scenario in SCENARIO_ORDER else 999
    return scenario_idx, str(row["slug"])


def load_task_stats(input_root: Path) -> list[dict[str, Any]]:
    manifest_path = input_root / "merge_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    included = manifest.get("included") or []
    if len(included) != 11:
        raise RuntimeError(f"Expected 11 models, found {len(included)}")

    by_task: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in included:
        model_key = str(entry["model_key"])
        model_slug = str(entry["model_slug"])
        official_rows = read_jsonl(input_root / model_slug / "official" / "runs.jsonl")
        clean_rows = read_jsonl(input_root / model_slug / "clean" / "runs.jsonl")
        if len(official_rows) != 140 or len(clean_rows) != 140:
            raise RuntimeError(f"{model_slug} expected 140/140 rows, found {len(official_rows)}/{len(clean_rows)}")
        clean_by_task = {(row["scenario"], row["slug"]): row for row in clean_rows}
        for official in official_rows:
            key = (official["scenario"], official["slug"])
            clean = clean_by_task[key]
            task = by_task.setdefault(
                key,
                {
                    "scenario": official["scenario"],
                    "slug": official["slug"],
                    "task_id": official.get("task_id"),
                    "case_id": official.get("case_id"),
                    "title": official.get("title"),
                    "template": official.get("template"),
                    "source_dataset": official.get("source_dataset"),
                    "source_group": official.get("source_group"),
                    "source_slug": official.get("source_slug"),
                    "misleader_type": official.get("misleader_type") or "unknown",
                    "reasoning_operation": official.get("reasoning_operation"),
                    "model_count": 0,
                    "clean_success_count": 0,
                    "official_success_count": 0,
                    "misleading_failure_count": 0,
                    "irrelevant_action_failure_count": 0,
                    "agent_timeout_count": 0,
                    "agent_error_count": 0,
                    "model_outcomes": {},
                },
            )
            task["model_count"] += 1
            if clean.get("outcome") == "success":
                task["clean_success_count"] += 1
            official_outcome = str(official.get("outcome"))
            if official_outcome == "success":
                task["official_success_count"] += 1
            elif official_outcome == "misleading_failure":
                task["misleading_failure_count"] += 1
            elif official_outcome == "irrelevant_action_failure":
                task["irrelevant_action_failure_count"] += 1
            elif official_outcome == "agent_timeout":
                task["agent_timeout_count"] += 1
            elif official_outcome == "agent_error":
                task["agent_error_count"] += 1
            task["model_outcomes"][model_key] = {
                "clean": clean.get("outcome"),
                "official": official_outcome,
            }
    if len(by_task) != 140:
        raise RuntimeError(f"Expected 140 unique task pairs, found {len(by_task)}")
    return sorted(by_task.values(), key=task_sort_key)


def select_miniset(tasks: list[dict[str, Any]], *, per_type: int) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        by_type[str(task["misleader_type"])].append(task)

    selected: list[dict[str, Any]] = []
    for misleader_type in sorted(by_type, key=lambda key: (-len(by_type[key]), key)):
        candidates = sorted(
            by_type[misleader_type],
            key=lambda row: (
                -int(row["clean_success_count"]),
                int(row["official_success_count"]),
                -int(row["misleading_failure_count"]),
                task_sort_key(row),
            ),
        )
        for rank, row in enumerate(candidates[: min(per_type, len(candidates))], start=1):
            selected_row = dict(row)
            selected_row["selection_rank_within_type"] = rank
            selected_row["selection_rule"] = (
                "min(per_type,count) by clean_success desc, official_success asc, "
                "misleading_failure desc, scenario/slug asc"
            )
            selected.append(selected_row)
    return sorted(selected, key=lambda row: (str(row["misleader_type"]), task_sort_key(row)))


def task_overrides(selected: list[dict[str, Any]]) -> dict[str, str]:
    by_scenario: dict[str, list[str]] = defaultdict(list)
    for row in selected:
        by_scenario[str(row["scenario"])].append(str(row["slug"]))
    return {
        scenario: ",".join(sorted(slugs))
        for scenario, slugs in sorted(by_scenario.items(), key=lambda item: SCENARIO_ORDER.index(item[0]))
    }


def write_distribution(path: Path, *, tasks: list[dict[str, Any]], selected: list[dict[str, Any]], overrides: dict[str, str]) -> None:
    by_type = Counter(str(row["misleader_type"]) for row in tasks)
    selected_by_type = Counter(str(row["misleader_type"]) for row in selected)
    lines = [
        "# Misleading Visualization Type Distribution and Mini-Set",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Full paired tasks: `{len(tasks)}`",
        f"- Mini-set tasks: `{len(selected)}`",
        f"- Covered misleading types: `{len(selected_by_type)}`",
        "- Selection rule: for each misleading type, select `min(3, count)` tasks by high clean success, low official success, high mechanism-aligned misleading failures, then stable scenario/slug order.",
        "",
        "## Distribution",
        "",
        "| Misleader Type | Full Task Count | Mini-Set Count |",
        "|---|---:|---:|",
    ]
    for misleader_type, count in by_type.most_common():
        lines.append(f"| {misleader_type} | {count} | {selected_by_type.get(misleader_type, 0)} |")
    lines.extend(["", "## Task Overrides", "", "```json", json.dumps(overrides, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## Selected Tasks", "", "| Type | Scenario | Slug | Clean Success | Official Success | Misleading Failure |", "|---|---|---|---:|---:|---:|"])
    for row in selected:
        lines.append(
            f"| {row['misleader_type']} | {row['scenario']} | {row['slug']} | "
            f"{row['clean_success_count']} | {row['official_success_count']} | {row['misleading_failure_count']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--per-type", type=int, default=3)
    args = parser.parse_args()

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    tasks = load_task_stats(input_root)
    selected = select_miniset(tasks, per_type=args.per_type)
    overrides = task_overrides(selected)

    write_jsonl(output_root / "miniset_manifest.jsonl", selected)
    (output_root / "task_overrides.json").write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_distribution(output_root / "misleader_distribution.md", tasks=tasks, selected=selected, overrides=overrides)
    config = {
        "generated_at": utc_now(),
        "input_root": str(input_root),
        "output_root": str(output_root),
        "per_type": args.per_type,
        "full_task_count": len(tasks),
        "miniset_task_count": len(selected),
        "covered_misleader_types": len({row["misleader_type"] for row in selected}),
        "task_overrides": overrides,
    }
    (output_root / "miniset_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote mini-set to {output_root}")
    print(f"Full tasks: {len(tasks)}")
    print(f"Mini-set tasks: {len(selected)}")
    print(f"Covered types: {config['covered_misleader_types']}")
    print("Task overrides:", json.dumps(overrides, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
