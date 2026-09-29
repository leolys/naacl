#!/usr/bin/env python3
"""Build paired task sets for the GUI-Reflection benchmark run.

The chart-only set is derived by comparing paired records.  It is not selected
from a handwritten slug deny-list.  Chart assets and split-specific metadata
are intentionally outside the comparison because those fields must differ
between the misleading and clean arms.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_ROOT = REPO_ROOT / "web_agent_benchmark" / "benchmark_v2_open"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "task_sets"

# These fields cover the task text/workflow shown by the shells, the available
# actions, and the labels used to score the final decision.  Equality here is
# the operational definition of a chart-only pair for this experiment.
PAIR_COMPARISON_FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "task_and_workflow": (
        "workflow_instruction",
        "page_title",
        "chart_reference",
        "shell_page_design",
        "recommended_environment_template",
        "image_only_review_context",
    ),
    "action_space": (
        "primary_action",
        "action_space",
        "companion_actions",
        "completion_action",
    ),
    "ground_truth_and_scoring": (
        "ground_truth",
        "intermediate_decision",
        "expected_action_id",
        "misleading_action_ids",
        "fallback_scoring",
    ),
}
PAIR_COMPARISON_FIELDS = tuple(
    field
    for fields in PAIR_COMPARISON_FIELD_GROUPS.values()
    for field in fields
)
READINESS_EXCLUSIONS = frozenset({"image_only_draft"})
REVIEW_ISSUE_EXCLUSIONS = frozenset({"gt_uncertain"})
REVIEW_ANNOTATION_RELATIVE_PATHS = {
    "public_statistics": Path(
        "web_agent_benchmark/public_affairs_tasks/review_annotations.json"
    ),
    "environment_climate_water_energy": Path(
        "web_agent_benchmark/environment_energy_tasks/review_annotations.json"
    ),
    "health": Path("web_agent_benchmark/health_tasks/review_annotations.json"),
}


@dataclass(frozen=True)
class LocatedTask:
    """One task record together with its source location."""

    row: dict[str, Any]
    path: Path
    line_number: int


@dataclass(frozen=True)
class BuiltTaskSets:
    """The four experiment populations plus their machine-readable summary."""

    full140: tuple[dict[str, Any], ...]
    chart_only114: tuple[dict[str, Any], ...]
    readiness95: tuple[dict[str, Any], ...]
    strict_review94: tuple[dict[str, Any], ...]
    smoke17: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


def _read_jsonl(path: Path) -> list[LocatedTask]:
    located: list[LocatedTask] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if line.strip():
            located.append(
                LocatedTask(json.loads(line), path.resolve(), line_number)
            )
    return located


def _load_split(dataset_root: Path, split: str) -> dict[str, LocatedTask]:
    split_dir = dataset_root / "splits" / split
    if not split_dir.is_dir():
        raise FileNotFoundError(f"Missing split directory: {split_dir}")

    by_pair: dict[str, LocatedTask] = {}
    for path in sorted(split_dir.glob("*_tasks.jsonl")):
        for located in _read_jsonl(path):
            pair_group_id = located.row.get("pair_group_id")
            if not pair_group_id:
                raise ValueError(
                    f"Missing pair_group_id in {path}:{located.line_number}"
                )
            if pair_group_id in by_pair:
                previous = by_pair[pair_group_id]
                raise ValueError(
                    "Duplicate pair_group_id "
                    f"{pair_group_id!r} in {previous.path} and {path}"
                )
            by_pair[pair_group_id] = located
    return by_pair


def paired_field_differences(
    official: dict[str, Any], clean: dict[str, Any]
) -> tuple[str, ...]:
    """Return non-chart task/action/ground-truth fields that differ."""

    return tuple(
        field
        for field in PAIR_COMPARISON_FIELDS
        if official.get(field) != clean.get(field)
    )


def _portable_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _chart_path(row: dict[str, Any]) -> str | None:
    chart_asset = row.get("chart_asset") or {}
    value = chart_asset.get("figure_path")
    return str(value) if value else None


def _paired_readiness(
    official: dict[str, Any], clean: dict[str, Any]
) -> tuple[str | None, str | None]:
    return official.get("task_readiness"), clean.get("task_readiness")


def _load_review_annotations(
    repo_root: Path,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Load source-task review annotations, keyed by scenario and task id."""

    annotations_by_scenario: dict[str, dict[str, dict[str, Any]]] = {}
    for scenario, relative_path in REVIEW_ANNOTATION_RELATIVE_PATHS.items():
        annotation_path = repo_root / relative_path
        payload = json.loads(annotation_path.read_text(encoding="utf-8"))
        annotations = payload.get("annotations")
        if not isinstance(annotations, dict):
            raise ValueError(
                f"Expected an annotations object in {annotation_path}"
            )
        annotations_by_scenario[scenario] = annotations
    return annotations_by_scenario


def _review_issues(
    row: dict[str, Any],
    annotations_by_scenario: dict[str, dict[str, dict[str, Any]]],
) -> list[str]:
    annotation = annotations_by_scenario.get(str(row.get("scenario")), {}).get(
        str(row.get("task_id")), {}
    )
    issues = annotation.get("issues") or []
    if not isinstance(issues, list):
        raise ValueError(
            f"Review issues for task {row.get('task_id')!r} must be a list"
        )
    return sorted({str(issue) for issue in issues})


def _base_entry(
    pair_group_id: str,
    official: LocatedTask,
    clean: LocatedTask,
    repo_root: Path,
    annotations_by_scenario: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    official_row = official.row
    clean_row = clean.row
    identity_fields = ("case_uid", "scenario", "task_slug", "misleader_type")
    identity_mismatches = [
        field
        for field in identity_fields
        if official_row.get(field) != clean_row.get(field)
    ]
    if identity_mismatches:
        raise ValueError(
            f"Pair {pair_group_id!r} differs on identity fields: "
            f"{identity_mismatches}"
        )

    scenario = str(official_row.get("scenario"))
    review_annotation_path = REVIEW_ANNOTATION_RELATIVE_PATHS.get(scenario)
    return {
        "pair_group_id": pair_group_id,
        "scenario": official_row.get("scenario"),
        "slug": official_row.get("task_slug"),
        "type": official_row.get("misleader_type"),
        "official_path": _portable_path(official.path, repo_root),
        "official_line": official.line_number,
        "clean_path": _portable_path(clean.path, repo_root),
        "clean_line": clean.line_number,
        "official_chart_path": _chart_path(official_row),
        "clean_chart_path": _chart_path(clean_row),
        "official_readiness": official_row.get("task_readiness"),
        "clean_readiness": clean_row.get("task_readiness"),
        "review_annotation_path": (
            review_annotation_path.as_posix()
            if review_annotation_path is not None
            else None
        ),
        "official_review_issues": _review_issues(
            official_row, annotations_by_scenario
        ),
        "clean_review_issues": _review_issues(
            clean_row, annotations_by_scenario
        ),
        "paired_non_chart_differences": list(
            paired_field_differences(official_row, clean_row)
        ),
    }


def build_task_sets(
    dataset_root: Path = DEFAULT_DATASET_ROOT,
    repo_root: Path = REPO_ROOT,
) -> BuiltTaskSets:
    """Derive the four paired populations from canonical split records."""

    dataset_root = dataset_root.resolve()
    repo_root = repo_root.resolve()
    official_by_pair = _load_split(dataset_root, "official140")
    clean_by_pair = _load_split(dataset_root, "clean140")
    annotations_by_scenario = _load_review_annotations(repo_root)

    official_ids = set(official_by_pair)
    clean_ids = set(clean_by_pair)
    if official_ids != clean_ids:
        missing_clean = sorted(official_ids - clean_ids)
        missing_official = sorted(clean_ids - official_ids)
        raise ValueError(
            "Paired split identifiers differ: "
            f"missing_clean={missing_clean}, missing_official={missing_official}"
        )

    entries = [
        _base_entry(
            pair_group_id,
            official_by_pair[pair_group_id],
            clean_by_pair[pair_group_id],
            repo_root,
            annotations_by_scenario,
        )
        for pair_group_id in official_ids
    ]
    entries.sort(key=lambda item: (str(item["scenario"]), str(item["slug"])))

    chart_only_pair_ids = {
        entry["pair_group_id"]
        for entry in entries
        if not entry["paired_non_chart_differences"]
    }

    readiness_pair_ids: set[str] = set()
    for entry in entries:
        if entry["pair_group_id"] not in chart_only_pair_ids:
            continue
        readiness_values = {
            entry["official_readiness"],
            entry["clean_readiness"],
        }
        if not readiness_values.intersection(READINESS_EXCLUSIONS):
            readiness_pair_ids.add(entry["pair_group_id"])

    strict_review_pair_ids = {
        entry["pair_group_id"]
        for entry in entries
        if entry["pair_group_id"] in readiness_pair_ids
        and not (
            set(entry["official_review_issues"])
            | set(entry["clean_review_issues"])
        ).intersection(REVIEW_ISSUE_EXCLUSIONS)
    }

    ready_by_stratum: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if entry["pair_group_id"] in readiness_pair_ids:
            ready_by_stratum[(entry["scenario"], entry["type"])].append(entry)

    smoke_pair_ids = {
        min(stratum, key=lambda item: str(item["slug"]))["pair_group_id"]
        for stratum in ready_by_stratum.values()
    }
    smoke_slug_by_stratum = {
        stratum_key: min(stratum, key=lambda item: str(item["slug"]))["slug"]
        for stratum_key, stratum in ready_by_stratum.items()
    }

    for entry in entries:
        pair_group_id = entry["pair_group_id"]
        chart_reasons: list[dict[str, Any]] = []
        readiness_reasons: list[dict[str, Any]] = []
        strict_review_reasons: list[dict[str, Any]] = []
        smoke_reasons: list[dict[str, Any]] = []

        if pair_group_id not in chart_only_pair_ids:
            chart_reasons.append(
                {
                    "code": "paired_non_chart_field_mismatch",
                    "fields": entry["paired_non_chart_differences"],
                }
            )

        if pair_group_id not in readiness_pair_ids:
            if pair_group_id not in chart_only_pair_ids:
                readiness_reasons.append({"code": "not_in_chart_only114"})
            else:
                excluded_statuses = sorted(
                    {
                        status
                        for status in _paired_readiness(
                            official_by_pair[pair_group_id].row,
                            clean_by_pair[pair_group_id].row,
                        )
                        if status in READINESS_EXCLUSIONS
                    }
                )
                readiness_reasons.append(
                    {
                        "code": "excluded_task_readiness",
                        "statuses": excluded_statuses,
                    }
                )

        if pair_group_id not in strict_review_pair_ids:
            if pair_group_id not in readiness_pair_ids:
                strict_review_reasons.append({"code": "not_in_readiness95"})
            else:
                excluded_issues = sorted(
                    (
                        set(entry["official_review_issues"])
                        | set(entry["clean_review_issues"])
                    ).intersection(REVIEW_ISSUE_EXCLUSIONS)
                )
                strict_review_reasons.append(
                    {
                        "code": "excluded_review_issue",
                        "issues": excluded_issues,
                    }
                )

        if pair_group_id not in smoke_pair_ids:
            if pair_group_id not in readiness_pair_ids:
                smoke_reasons.append({"code": "not_in_readiness95"})
            else:
                stratum_key = (entry["scenario"], entry["type"])
                smoke_reasons.append(
                    {
                        "code": "not_minimum_slug_for_scenario_type",
                        "selected_slug": smoke_slug_by_stratum[stratum_key],
                    }
                )

        entry["selected"] = {
            "full140": True,
            "chart_only114": pair_group_id in chart_only_pair_ids,
            "readiness95": pair_group_id in readiness_pair_ids,
            "strict_review94": pair_group_id in strict_review_pair_ids,
            "smoke17": pair_group_id in smoke_pair_ids,
        }
        entry["exclusion_reasons"] = {
            "full140": [],
            "chart_only114": chart_reasons,
            "readiness95": readiness_reasons,
            "strict_review94": strict_review_reasons,
            "smoke17": smoke_reasons,
        }

    full140 = tuple(entries)
    chart_only114 = tuple(
        entry for entry in entries if entry["selected"]["chart_only114"]
    )
    readiness95 = tuple(
        entry for entry in entries if entry["selected"]["readiness95"]
    )
    strict_review94 = tuple(
        entry for entry in entries if entry["selected"]["strict_review94"]
    )
    smoke17 = tuple(entry for entry in entries if entry["selected"]["smoke17"])

    field_difference_counts = {
        field: sum(
            field in entry["paired_non_chart_differences"] for entry in entries
        )
        for field in PAIR_COMPARISON_FIELDS
    }
    field_difference_counts = {
        field: count for field, count in field_difference_counts.items() if count
    }
    readiness_exclusion_counts: dict[str, int] = defaultdict(int)
    for entry in chart_only114:
        for status in {
            entry["official_readiness"], entry["clean_readiness"]
        }.intersection(READINESS_EXCLUSIONS):
            readiness_exclusion_counts[str(status)] += 1

    review_issue_counts: dict[str, int] = defaultdict(int)
    for entry in chart_only114:
        for issue in (
            set(entry["official_review_issues"])
            | set(entry["clean_review_issues"])
        ):
            review_issue_counts[str(issue)] += 1

    strict_additional_exclusion_counts: dict[str, int] = defaultdict(int)
    for entry in readiness95:
        for issue in (
            set(entry["official_review_issues"])
            | set(entry["clean_review_issues"])
        ).intersection(REVIEW_ISSUE_EXCLUSIONS):
            strict_additional_exclusion_counts[str(issue)] += 1

    metadata_conflicts = []
    for entry in chart_only114:
        readiness_values = {
            entry["official_readiness"], entry["clean_readiness"]
        }
        review_issues = set(entry["official_review_issues"]) | set(
            entry["clean_review_issues"]
        )
        if (
            "formal_scored_task" in readiness_values
            and "gt_uncertain" in review_issues
        ):
            metadata_conflicts.append(
                {
                    "slug": entry["slug"],
                    "scenario": entry["scenario"],
                    "task_readiness": sorted(
                        status for status in readiness_values if status is not None
                    ),
                    "review_issues": sorted(review_issues),
                    "description": (
                        "canonical row is formal_scored_task while its source "
                        "review annotation still contains gt_uncertain"
                    ),
                }
            )

    strict_review_strata = {
        (entry["scenario"], entry["type"]) for entry in strict_review94
    }
    readiness_smoke_strata = {
        (entry["scenario"], entry["type"]): entry["slug"]
        for entry in smoke17
    }
    strict_missing_smoke_strata = [
        {
            "scenario": scenario,
            "type": misleader_type,
            "readiness95_smoke_slug": slug,
        }
        for (scenario, misleader_type), slug in sorted(
            readiness_smoke_strata.items()
        )
        if (scenario, misleader_type) not in strict_review_strata
    ]

    summary = {
        "dataset_root": _portable_path(dataset_root, repo_root),
        "pair_comparison_field_groups": {
            key: list(fields)
            for key, fields in PAIR_COMPARISON_FIELD_GROUPS.items()
        },
        "task_readiness_exclusions": sorted(READINESS_EXCLUSIONS),
        "review_issue_exclusions": sorted(REVIEW_ISSUE_EXCLUSIONS),
        "review_annotation_sources": {
            scenario: relative_path.as_posix()
            for scenario, relative_path in sorted(
                REVIEW_ANNOTATION_RELATIVE_PATHS.items()
            )
        },
        "selection_rules": {
            "full140": "all paired official140/clean140 records",
            "chart_only114": (
                "no differences in paired task/workflow/action-space/ground-truth fields"
            ),
            "readiness95": (
                "chart_only114 excluding task_readiness=image_only_draft in either arm"
            ),
            "strict_review94": (
                "readiness95 additionally excluding gt_uncertain in source review "
                "annotations; this removes env032"
            ),
            "smoke17": (
                "lexicographically minimum slug per (scenario, type) stratum in readiness95"
            ),
        },
        "counts": {
            "full140": len(full140),
            "chart_only114": len(chart_only114),
            "readiness95": len(readiness95),
            "strict_review94": len(strict_review94),
            "smoke17": len(smoke17),
        },
        "paired_non_chart_field_difference_counts": field_difference_counts,
        "readiness_exclusion_counts_within_chart_only": dict(
            sorted(readiness_exclusion_counts.items())
        ),
        "review_issue_counts_within_chart_only": dict(
            sorted(review_issue_counts.items())
        ),
        "strict_review_additional_exclusion_counts": dict(
            sorted(strict_additional_exclusion_counts.items())
        ),
        "metadata_conflicts": metadata_conflicts,
        "strict_review_strata_count": len(strict_review_strata),
        "strict_review_missing_readiness_smoke_strata": (
            strict_missing_smoke_strata
        ),
        "smoke_strata": [
            {
                "scenario": scenario,
                "type": misleader_type,
                "selected_slug": smoke_slug_by_stratum[(scenario, misleader_type)],
                "eligible_count": len(ready_by_stratum[(scenario, misleader_type)]),
            }
            for scenario, misleader_type in sorted(ready_by_stratum)
        ],
    }
    return BuiltTaskSets(
        full140=full140,
        chart_only114=chart_only114,
        readiness95=readiness95,
        strict_review94=strict_review94,
        smoke17=smoke17,
        summary=summary,
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    path.write_text(text, encoding="utf-8")


def write_task_sets(result: BuiltTaskSets, output_dir: Path) -> None:
    """Write portable JSONL populations and their JSON manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "full140.jsonl", result.full140)
    _write_jsonl(output_dir / "chart_only114.jsonl", result.chart_only114)
    _write_jsonl(output_dir / "readiness95.jsonl", result.readiness95)
    _write_jsonl(output_dir / "strict_review94.jsonl", result.strict_review94)
    _write_jsonl(output_dir / "smoke17.jsonl", result.smoke17)
    (output_dir / "manifest.json").write_text(
        json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_task_sets(args.dataset_root, REPO_ROOT)
    write_task_sets(result, args.output_dir)
    print(json.dumps(result.summary["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
