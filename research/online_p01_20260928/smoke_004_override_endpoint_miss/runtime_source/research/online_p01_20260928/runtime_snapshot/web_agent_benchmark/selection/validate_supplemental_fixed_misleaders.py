#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SELECTION = Path(__file__).resolve().parents[1] / "selected_cases_supplemental_fixed_misleaders" / "selected_cases.jsonl"
DEFAULT_REVIEWED_SELECTION = Path(__file__).resolve().parents[1] / "selected_cases_target_aware" / "selected_cases.jsonl"
DEFAULT_REVIEWED_ANNOTATIONS = Path(__file__).resolve().parents[1] / "selected_cases_target_aware" / "review_annotations.json"

ALLOWED_MISLEADERS = {
    "cherry_picking",
    "MS_inappropriate_scale_range",
    "misuse_of_cumulative_relationship",
    "misleading_annotations",
}

sys.path.insert(0, str(SCRIPT_DIR))
from task_operations import SUPPORTED_OPERATIONS, validate_task_spec  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = [str(h).strip() for h in (reader.fieldnames or []) if h and str(h).strip()]
        rows = [
            {str(k).strip(): str(v).strip() for k, v in row.items() if k is not None}
            for row in reader
            if any(str(v).strip() for v in row.values())
        ]
    return headers, rows


def load_suitable_ids(selection_path: Path, annotations_path: Path) -> set[str]:
    if not selection_path.exists() or not annotations_path.exists():
        return set()
    selected_ids = {row["case_id"] for row in load_jsonl(selection_path)}
    annotations = json.loads(annotations_path.read_text(encoding="utf-8")).get("annotations", {})
    return {
        case_id
        for case_id, annotation in annotations.items()
        if case_id in selected_ids and annotation.get("status") == "suitable"
    }


def validate(rows: list[dict[str, Any]], suitable_ids: set[str], max_count: int) -> list[str]:
    errors: list[str] = []
    if len(rows) > max_count:
        errors.append(f"Expected at most {max_count} rows, found {len(rows)}.")
    seen: set[str] = set()
    for row in rows:
        case_id = str(row.get("case_id", ""))
        if case_id in seen:
            errors.append(f"Duplicate case_id: {case_id}")
        seen.add(case_id)
        if case_id in suitable_ids:
            errors.append(f"{case_id}: duplicates an existing suitable reviewed case.")
        if row.get("misleader_type") not in ALLOWED_MISLEADERS:
            errors.append(f"{case_id}: unexpected misleader_type {row.get('misleader_type')}")
        if not row.get("llm_called"):
            errors.append(f"{case_id}: missing llm_called=true")
        if not row.get("llm_spec"):
            errors.append(f"{case_id}: missing llm_spec")
        if row.get("reasoning_operation") not in SUPPORTED_OPERATIONS:
            errors.append(f"{case_id}: unsupported reasoning_operation {row.get('reasoning_operation')}")
        if row.get("misleader_type") == "cherry_picking":
            if row.get("reasoning_operation") == "correlation_direction":
                errors.append(f"{case_id}: cherry_picking must not use correlation_direction as the final operation.")
            if row.get("reasoning_operation") != "cherry_picking_generalization_check":
                errors.append(f"{case_id}: cherry_picking must use cherry_picking_generalization_check.")
            if row.get("ground_truth_entity") != "request_further_analysis":
                errors.append(f"{case_id}: cherry_picking ground_truth_entity must be request_further_analysis.")
            workflow = str(row.get("workflow_instruction", "")).lower()
            action_terms = ["request", "hold", "flag", "review", "analysis", "robustness", "evidence", "route", "validation", "full"]
            if not any(term in workflow for term in action_terms):
                errors.append(f"{case_id}: cherry_picking workflow does not request analysis/review/hold action.")
        if "then" not in str(row.get("workflow_instruction", "")).lower():
            errors.append(f"{case_id}: workflow_instruction does not include a downstream action.")
        if row.get("reasoning_operation") == "extreme_value" and not row.get("operation_rationale"):
            errors.append(f"{case_id}: extreme_value missing operation_rationale.")
        figure_path = Path(str(row.get("figure_path", "")))
        csv_path = Path(str(row.get("csv_path", "")))
        if not figure_path.exists():
            errors.append(f"{case_id}: missing figure_path {figure_path}")
        if not csv_path.exists():
            errors.append(f"{case_id}: missing csv_path {csv_path}")
            continue
        headers, csv_rows = read_csv_rows(csv_path)
        result = validate_task_spec(rows=csv_rows, headers=headers, spec=row)
        if not result.valid:
            errors.append(f"{case_id}: ground truth not computable: {result.validation_error}")
        elif str(row.get("ground_truth_entity")) != str(result.ground_truth_entity):
            errors.append(
                f"{case_id}: ground_truth_entity mismatch; metadata={row.get('ground_truth_entity')} csv={result.ground_truth_entity}"
            )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate supplemental fixed-misleader selected cases.")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--reviewed-selection", type=Path, default=DEFAULT_REVIEWED_SELECTION)
    parser.add_argument("--reviewed-annotations", type=Path, default=DEFAULT_REVIEWED_ANNOTATIONS)
    parser.add_argument("--max-count", type=int, default=110)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_jsonl(args.selection)
    suitable_ids = load_suitable_ids(args.reviewed_selection, args.reviewed_annotations)
    errors = validate(rows, suitable_ids, args.max_count)
    report = {
        "selection": str(args.selection),
        "row_count": len(rows),
        "valid": not errors,
        "errors": errors,
        "misleader_distribution": dict(Counter(row.get("misleader_type") for row in rows)),
        "scenario_distribution": dict(Counter(row.get("scenario") for row in rows)),
        "operation_distribution": dict(Counter(row.get("reasoning_operation") for row in rows)),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
