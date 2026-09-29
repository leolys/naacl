#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SELECTION = Path(__file__).resolve().parents[1] / "selected_cases_target_aware" / "selected_cases.jsonl"

sys.path.insert(0, str(SCRIPT_DIR))
from task_operations import SUPPORTED_OPERATIONS, validate_task_spec  # noqa: E402


EXPECTED_SCENARIOS = {
    "business_operations",
    "public_statistics",
    "education_hr",
    "health_environment",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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


def validate(rows: list[dict[str, Any]], per_scenario: int) -> list[str]:
    errors: list[str] = []
    if len(rows) != per_scenario * len(EXPECTED_SCENARIOS):
        errors.append(f"Expected {per_scenario * len(EXPECTED_SCENARIOS)} rows, found {len(rows)}.")

    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        case_id = str(row.get("case_id", ""))
        scenario = str(row.get("scenario", ""))
        by_scenario[scenario].append(row)
        if case_id in seen:
            errors.append(f"Duplicate case_id: {case_id}")
        seen.add(case_id)

        if not row.get("llm_called"):
            errors.append(f"{case_id}: missing llm_called=true")
        if not row.get("llm_spec"):
            errors.append(f"{case_id}: missing llm_spec")
        if row.get("reasoning_operation") not in SUPPORTED_OPERATIONS:
            errors.append(f"{case_id}: unsupported reasoning_operation {row.get('reasoning_operation')}")
        if "then" not in str(row.get("workflow_instruction", "")).lower():
            errors.append(f"{case_id}: workflow_instruction does not include a downstream action.")

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
        else:
            if str(row.get("ground_truth_entity")) != str(result.ground_truth_entity):
                errors.append(
                    f"{case_id}: ground_truth_entity mismatch; metadata={row.get('ground_truth_entity')} csv={result.ground_truth_entity}"
                )
            if "ground_truth_value" not in row:
                errors.append(f"{case_id}: missing ground_truth_value")

    if set(by_scenario) != EXPECTED_SCENARIOS:
        errors.append(f"Scenario set mismatch: expected {sorted(EXPECTED_SCENARIOS)}, found {sorted(by_scenario)}")

    for scenario in EXPECTED_SCENARIOS:
        items = by_scenario.get(scenario, [])
        if len(items) != per_scenario:
            errors.append(f"{scenario}: expected {per_scenario}, found {len(items)}.")
        misleaders = Counter(str(item.get("misleader_type")) for item in items)
        if len(misleaders) < 3:
            errors.append(f"{scenario}: expected at least 3 misleader types, found {dict(misleaders)}.")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate target-aware selected cases.")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--per-scenario", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_jsonl(args.selection)
    errors = validate(rows, args.per_scenario)
    report = {
        "selection": str(args.selection),
        "row_count": len(rows),
        "valid": not errors,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
