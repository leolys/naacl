#!/usr/bin/env python3
"""Build a public-affairs expansion candidate pool.

This script does not create task specs. It selects chart candidates that can be
reviewed and rewritten into public-affairs web-agent tasks.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

SOURCE_FILES = [
    REPO_ROOT / "web_agent_benchmark/selected_cases_supplemental_fixed_misleaders/candidate_scores.jsonl",
    REPO_ROOT / "web_agent_benchmark/selected_cases_target_aware/candidate_scores.jsonl",
    REPO_ROOT / "web_agent_benchmark/selected_cases/candidate_scores.jsonl",
]

TASK_SPECS = REPO_ROOT / "web_agent_benchmark/tasks/benchmark_tasks.jsonl"
OUTPUT_DIR = REPO_ROOT / "web_agent_benchmark/public_affairs_expansion"

ALLOWED_MISLEADERS = {
    "MS_unconventional_scale_directions",
    "MS_inappropriate_scale_range",
    "misleading_annotations",
    "cherry_picking",
    "data_visual_disproportion",
}

EXCLUDED_MISLEADERS = {
    "small_size",
    "categorical_encoding_for_continuous_data",
    "dual_encoding",
    "missing_data",
}

TARGET_MIX = {
    "MS_inappropriate_scale_range": 9,
    "misleading_annotations": 8,
    "MS_unconventional_scale_directions": 5,
    "cherry_picking": 5,
    "data_visual_disproportion": 3,
}

PREFERRED_CASE_SUFFIXES = {
    "MS_inappropriate_scale_range": [
        "MS_inappropriate_scale_range_stacked_bar_chart_45",
        "MS_inappropriate_scale_range_stacked_bar_chart_145",
        "MS_inappropriate_scale_range_stacked_bar_chart_146",
        "MS_inappropriate_scale_range_stacked_bar_chart_123",
        "MS_inappropriate_scale_range_stacked_area_chart_65",
        "MS_inappropriate_scale_range_stacked_area_chart_66",
        "MS_inappropriate_scale_range_stacked_area_chart_74",
        "MS_inappropriate_scale_range_stacked_area_chart_75",
        "MS_inappropriate_scale_range_stacked_bar_chart_109",
        "MS_inappropriate_scale_range_stacked_bar_chart_131",
        "MS_inappropriate_scale_range_stacked_bar_chart_111",
    ],
    "misleading_annotations": [
        "misleading_annotations_line_chart_1",
        "misleading_annotations_line_chart_5",
        "misleading_annotations_line_chart_8",
        "misleading_annotations_line_chart_19",
        "misleading_annotations_pie_chart_4",
        "misleading_annotations_pie_chart_6",
        "misleading_annotations_pie_chart_7",
        "misleading_annotations_pie_chart_47",
        "misleading_annotations_pie_chart_48",
        "misleading_annotations_pie_chart_49",
    ],
    "MS_unconventional_scale_directions": [
        "MS_unconventional_scale_directions_choropleth_map_18",
        "MS_unconventional_scale_directions_choropleth_map_61",
        "MS_unconventional_scale_directions_choropleth_map_63",
        "MS_unconventional_scale_directions_choropleth_map_64",
        "MS_unconventional_scale_directions_choropleth_map_66",
        "MS_unconventional_scale_directions_choropleth_map_65",
        "MS_unconventional_scale_directions_choropleth_map_70",
    ],
    "cherry_picking": [
        "cherry_picking_scatter_plot_23",
        "cherry_picking_scatter_plot_96",
        "cherry_picking_scatter_plot_140",
        "cherry_picking_scatter_plot_135",
        "cherry_picking_scatter_plot_120",
        "cherry_picking_scatter_plot_119",
        "cherry_picking_scatter_plot_117",
        "cherry_picking_scatter_plot_114",
        "cherry_picking_scatter_plot_109",
        "cherry_picking_scatter_plot_105",
    ],
    "data_visual_disproportion": [
        "data_visual_disproportion_scatter_plot_16",
        "data_visual_disproportion_scatter_plot_21",
        "data_visual_disproportion_scatter_plot_20",
        "data_visual_disproportion_scatter_plot_28",
        "data_visual_disproportion_scatter_plot_26",
        "data_visual_disproportion_scatter_plot_30",
    ],
}

LEAKAGE_TERMS_TO_REMOVE = [
    "verify underlying data",
    "true value",
    "actual value",
    "misleading",
    "rather than visual",
    "rather than the visual",
    "insufficient evidence",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def compact_path(path: str | None) -> str | None:
    if not path:
        return path
    try:
        p = Path(path)
        if p.is_absolute():
            return str(p.relative_to(REPO_ROOT))
    except ValueError:
        pass
    return path


def source_rank(path: Path) -> int:
    try:
        return SOURCE_FILES.index(path)
    except ValueError:
        return 99


def valid_rank(row: dict[str, Any]) -> int:
    if row.get("validation_passed") is True:
        return 0
    if row.get("validation_passed") is None:
        return 1
    return 2


def best_row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        valid_rank(row),
        source_rank(Path(row["_source_file"])),
        -(row.get("workflow_suitability_score") or 0),
        -(row.get("scenario_fit_score") or 0),
        row.get("case_id", ""),
    )


def candidate_sort_key(row: dict[str, Any], misleader_type: str) -> tuple[Any, ...]:
    suffixes = PREFERRED_CASE_SUFFIXES.get(misleader_type, [])
    case_id = row.get("case_id", "")
    preferred_index = 10_000
    for index, suffix in enumerate(suffixes):
        if case_id.endswith(suffix):
            preferred_index = index
            break
    public_first = 0 if row.get("scenario") == "public_statistics" else 1
    scatter_prefer = 0
    if misleader_type in {"cherry_picking", "data_visual_disproportion"}:
        scatter_prefer = 0 if row.get("plot_type") == "scatter_plot" else 1
    return (
        preferred_index,
        public_first,
        scatter_prefer,
        valid_rank(row),
        -(row.get("workflow_suitability_score") or 0),
        -(row.get("scenario_fit_score") or 0),
        row.get("case_id", ""),
    )


def load_existing_task_case_ids() -> set[str]:
    existing = set()
    for row in read_jsonl(TASK_SPECS):
        case_id = row.get("case_id")
        if case_id:
            existing.add(case_id)
    return existing


def public_template(row: dict[str, Any]) -> str:
    misleader_type = row.get("misleader_type")
    plot_type = row.get("plot_type")
    operation = row.get("reasoning_operation")
    if misleader_type == "cherry_picking":
        return "Public Evidence Review"
    if misleader_type == "data_visual_disproportion":
        return "Public Feedback Priority Routing"
    if plot_type == "choropleth_map":
        return "State / Regional Priority Review"
    if operation == "threshold_judgment" or plot_type in {"stacked_bar_chart", "stacked_area_chart"}:
        return "Municipal Transit / Public Alert Routing"
    if misleader_type == "misleading_annotations":
        return "Tourism / Regional Civic Planning"
    return "Public Affairs Routing"


def proposed_frame(row: dict[str, Any]) -> str:
    misleader_type = row.get("misleader_type")
    if misleader_type == "cherry_picking":
        return (
            "Rewrite as a public program evidence-routing task: inspect the selected-period "
            "scatter evidence, decide whether it supports a broad civic rollout or requires "
            "full-period evidence review, then submit the corresponding public approval route."
        )
    if misleader_type == "data_visual_disproportion":
        return (
            "Rewrite as a public feedback/category priority task: inspect the public response "
            "dashboard, identify the true priority category, and route that category into "
            "outreach or service-planning follow-up."
        )
    if misleader_type == "MS_unconventional_scale_directions":
        return (
            "Use as a state or regional priority-routing task where the map determines which "
            "jurisdiction should enter public follow-up."
        )
    if misleader_type == "MS_inappropriate_scale_range":
        return (
            "Use as a public alert or service-capacity routing task where the chart determines "
            "whether a date, region, or service unit crosses an operational threshold."
        )
    if misleader_type == "misleading_annotations":
        return (
            "Use as a public statistics route assignment task where the annotation can induce "
            "the wrong trend, average, or category decision."
        )
    return "Rewrite into a public affairs workflow before task generation."


def rewrite_note(row: dict[str, Any]) -> str:
    if row.get("misleader_type") == "cherry_picking":
        return (
            "Original workflow is mostly business-oriented. Rewrite entity names, page title, "
            "and actions into civic evidence review; do not expose insufficient-evidence wording."
        )
    if row.get("misleader_type") == "data_visual_disproportion":
        return (
            "Original workflow is mostly business-oriented. Rewrite commercial entities into "
            "public service categories or civic feedback categories before task generation."
        )
    if row.get("misleader_type") == "MS_unconventional_scale_directions":
        return (
            "Neutralize any reversed-legend explanation in the visible page; action should be "
            "jurisdiction routing, not legend verification."
        )
    if row.get("misleader_type") == "MS_inappropriate_scale_range":
        return (
            "If a cutoff is required, present it as a policy rule and include parallel action "
            "branches; verify evaluator-controlled threshold/ground truth before generation."
        )
    if row.get("misleader_type") == "misleading_annotations":
        return (
            "Remove annotation-correction hints from visible workflow; make the action a public "
            "route or follow-up choice driven by the chart."
        )
    return "Needs public-affairs rewrite review."


def action_chain_hint(row: dict[str, Any]) -> str:
    misleader_type = row.get("misleader_type")
    if misleader_type == "cherry_picking":
        return (
            "chart evidence -> evidence sufficiency judgment -> request full-period evidence "
            "review / approve limited pilot follow-up / reject broad rollout"
        )
    if misleader_type == "data_visual_disproportion":
        return (
            "public feedback dashboard -> true highest or target category judgment -> route "
            "category to priority review / outreach planning / routine monitoring"
        )
    if row.get("plot_type") == "choropleth_map":
        return (
            "map interpretation -> highest-risk or highest-need jurisdiction judgment -> open "
            "jurisdiction profile for priority follow-up"
        )
    if row.get("reasoning_operation") == "threshold_judgment":
        return (
            "dashboard interpretation -> threshold/policy status judgment -> submit alert, "
            "normal monitoring, or alternate response route"
        )
    return (
        "chart interpretation -> public status judgment -> choose a parallel public-affairs "
        "routing action"
    )


def make_output_record(row: dict[str, Any], rank: int) -> dict[str, Any]:
    transfer_required = row.get("misleader_type") in {"cherry_picking", "data_visual_disproportion"}
    return {
        "candidate_id": f"public_affairs_candidate_{rank:03d}",
        "case_id": row.get("case_id"),
        "source_file": str(Path(row["_source_file"]).relative_to(REPO_ROOT)),
        "source_scenario": row.get("scenario"),
        "target_scenario": "public_affairs",
        "public_affairs_transfer_required": transfer_required,
        "misleader_type": row.get("misleader_type"),
        "plot_type": row.get("plot_type"),
        "reasoning_operation": row.get("reasoning_operation"),
        "figure_path": compact_path(row.get("figure_path")),
        "csv_path": compact_path(row.get("csv_path")),
        "html_path": compact_path(row.get("html_path")),
        "html_title": row.get("html_title") or row.get("html_h1"),
        "csv_headers": row.get("csv_headers"),
        "sample_rows": row.get("sample_rows"),
        "ground_truth_entity": row.get("ground_truth_entity"),
        "ground_truth_value": row.get("ground_truth_value"),
        "ground_truth_computation": row.get("ground_truth_computation"),
        "misleading_target": row.get("misleading_target"),
        "expected_visual_trap": row.get("expected_visual_trap"),
        "source_workflow_instruction": row.get("workflow_instruction"),
        "source_recommended_action_type": row.get("recommended_action_type"),
        "recommended_public_template": public_template(row),
        "proposed_public_task_frame": proposed_frame(row),
        "proposed_action_chain_hint": action_chain_hint(row),
        "rewrite_note": rewrite_note(row),
        "leakage_terms_to_remove": LEAKAGE_TERMS_TO_REMOVE,
        "candidate_priority": "primary_review",
        "review_status": "unreviewed",
        "review_required_before_task_generation": True,
        "validation_passed": row.get("validation_passed"),
        "workflow_suitability_score": row.get("workflow_suitability_score"),
        "scenario_fit_score": row.get("scenario_fit_score"),
    }


def markdown_table(rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    widths = [len(str(cell)) for cell in header]
    for row in rows[1:]:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    lines = []
    lines.append("| " + " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(header)) + " |")
    lines.append("| " + " | ".join("-" * widths[i] for i in range(len(widths))) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) + " |")
    return "\n".join(lines)


def build_summary(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], skipped_current: int) -> str:
    by_misleader = Counter(row["misleader_type"] for row in selected)
    by_template = Counter(row["recommended_public_template"] for row in selected)
    by_transfer = Counter("transfer_required" if row["public_affairs_transfer_required"] else "native_public" for row in selected)

    lines = [
        "# Public Affairs Expansion Candidate Pool",
        "",
        "## Summary",
        "",
        f"- Selected candidates: {len(selected)}",
        f"- Existing task case IDs skipped: {skipped_current}",
        f"- Policy-excluded candidate records written: {len(excluded)}",
        f"- Native public candidates: {by_transfer.get('native_public', 0)}",
        f"- Public-affairs transfer candidates: {by_transfer.get('transfer_required', 0)}",
        "",
        "## Revised Candidate Families",
        "",
        "Allowed:",
        "",
    ]
    for name in sorted(ALLOWED_MISLEADERS):
        lines.append(f"- `{name}`")
    lines.extend(["", "Excluded:", ""])
    for name in sorted(EXCLUDED_MISLEADERS):
        lines.append(f"- `{name}`")

    lines.extend(["", "## Selected Mix", ""])
    rows = [["Misleader family", "Selected", "Target"]]
    for name, target in TARGET_MIX.items():
        rows.append([name, by_misleader.get(name, 0), target])
    lines.append(markdown_table(rows))

    lines.extend(["", "## Template Distribution", ""])
    rows = [["Template", "Count"]]
    for template, count in sorted(by_template.items()):
        rows.append([template, count])
    lines.append(markdown_table(rows))

    lines.extend(["", "## Review Requirements", ""])
    lines.extend(
        [
            "- Every candidate remains `unreviewed`; none should enter task generation before manual review.",
            "- `cherry_picking` and `data_visual_disproportion` are public-affairs transfer candidates and require workflow/action rewriting.",
            "- Visible workflows must not contain `verify underlying data`, `true value`, `actual value`, `misleading`, or `rather than visual` phrasing.",
            "- Cherry-picking tasks should be framed as public evidence routing or approval workflow, not as an explicit insufficient-evidence quiz.",
        ]
    )

    lines.extend(["", "## Candidate List", ""])
    rows = [["ID", "Case ID", "Family", "Source scenario", "Template", "Transfer"]]
    for row in selected:
        rows.append(
            [
                row["candidate_id"],
                row["case_id"],
                row["misleader_type"],
                row["source_scenario"],
                row["recommended_public_template"],
                "yes" if row["public_affairs_transfer_required"] else "no",
            ]
        )
    lines.append(markdown_table(rows))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    existing_case_ids = load_existing_task_case_ids()

    all_rows: list[dict[str, Any]] = []
    for source_file in SOURCE_FILES:
        for row in read_jsonl(source_file):
            row = dict(row)
            row["_source_file"] = str(source_file)
            all_rows.append(row)

    skipped_current = 0
    excluded_by_policy: list[dict[str, Any]] = []
    candidates_by_case: dict[str, dict[str, Any]] = {}

    for row in all_rows:
        case_id = row.get("case_id")
        if not case_id:
            continue
        misleader_type = row.get("misleader_type")
        if case_id in existing_case_ids:
            skipped_current += 1
            continue
        if misleader_type in EXCLUDED_MISLEADERS:
            if row.get("validation_passed") is not False and row.get("keep") is not False:
                excluded_by_policy.append(
                    {
                        "case_id": case_id,
                        "misleader_type": misleader_type,
                        "plot_type": row.get("plot_type"),
                        "scenario": row.get("scenario"),
                        "source_file": str(Path(row["_source_file"]).relative_to(REPO_ROOT)),
                        "exclusion_reason": "misleader_family_excluded_by_public_affairs_policy",
                    }
                )
            continue
        if misleader_type not in ALLOWED_MISLEADERS:
            continue
        if row.get("validation_passed") is False or row.get("keep") is False:
            continue
        if not row.get("figure_path") or not row.get("csv_path"):
            continue

        current = candidates_by_case.get(case_id)
        if current is None or best_row_key(row) < best_row_key(current):
            candidates_by_case[case_id] = row

    deduped_candidates = list(candidates_by_case.values())
    selected_source_rows: list[dict[str, Any]] = []
    selected_case_ids: set[str] = set()
    for misleader_type, target_count in TARGET_MIX.items():
        family_rows = [row for row in deduped_candidates if row.get("misleader_type") == misleader_type]
        family_rows.sort(key=lambda row, mt=misleader_type: candidate_sort_key(row, mt))
        picked = family_rows[:target_count]
        if len(picked) < target_count:
            raise SystemExit(
                f"Not enough candidates for {misleader_type}: needed {target_count}, found {len(picked)}"
            )
        for row in picked:
            if row["case_id"] not in selected_case_ids:
                selected_source_rows.append(row)
                selected_case_ids.add(row["case_id"])

    selected = [make_output_record(row, index + 1) for index, row in enumerate(selected_source_rows)]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "candidate_pool.jsonl", selected)
    write_jsonl(args.output_dir / "excluded_by_policy.jsonl", excluded_by_policy)

    review_annotations = {
        row["case_id"]: {
            "candidate_id": row["candidate_id"],
            "status": "unreviewed",
            "issues": [],
            "notes": "",
            "recommended_action": "manual_review_before_task_generation",
        }
        for row in selected
    }
    (args.output_dir / "review_annotations.json").write_text(
        json.dumps(review_annotations, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "candidate_pool_summary.md").write_text(
        build_summary(selected, excluded_by_policy, skipped_current),
        encoding="utf-8",
    )

    by_family = Counter(row["misleader_type"] for row in selected)
    print(f"Wrote {len(selected)} public-affairs expansion candidates to {args.output_dir}")
    print("Selected mix:", dict(by_family))
    print(f"Policy-excluded records: {len(excluded_by_policy)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
