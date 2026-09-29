#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_SELECTION = Path(__file__).resolve().parents[1] / "selected_cases" / "selected_cases.jsonl"


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


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
        headers = [h.strip() for h in (reader.fieldnames or []) if h and h.strip()]
        rows = [
            {str(k).strip(): str(v).strip() for k, v in row.items() if k is not None}
            for row in reader
            if any(str(v).strip() for v in row.values())
        ]
    return headers, rows


def compute_truth(
    rows: list[dict[str, str]],
    entity_column: str,
    metric_column: str,
    decision_rule: str,
) -> str | None:
    pairs: list[tuple[str, float]] = []
    for row in rows:
        entity = row.get(entity_column, "").strip()
        value = parse_float(row.get(metric_column))
        if entity and value is not None:
            pairs.append((entity, value))
    if not pairs:
        return None
    target = max(v for _, v in pairs) if decision_rule == "max" else min(v for _, v in pairs)
    winners = sorted({entity for entity, value in pairs if value == target})
    return winners[0] if len(winners) == 1 else None


def validate(rows: list[dict[str, Any]], per_scenario: int) -> list[str]:
    errors: list[str] = []
    if len(rows) != per_scenario * 4:
        errors.append(f"Expected {per_scenario * 4} rows, found {len(rows)}.")

    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        case_id = row.get("case_id")
        scenario = row.get("scenario")
        by_scenario[str(scenario)].append(row)
        if case_id in seen:
            errors.append(f"Duplicate case_id across selected rows: {case_id}")
        seen.add(str(case_id))

        figure_path = Path(str(row.get("figure_path", "")))
        csv_path = Path(str(row.get("csv_path", "")))
        if not figure_path.exists():
            errors.append(f"{case_id}: missing figure_path {figure_path}")
        if not csv_path.exists():
            errors.append(f"{case_id}: missing csv_path {csv_path}")
            continue

        entity_column = str(row.get("entity_column", ""))
        metric_column = str(row.get("metric_column", ""))
        decision_rule = str(row.get("decision_rule", ""))
        if not entity_column or not metric_column:
            errors.append(f"{case_id}: empty entity_column or metric_column")
            continue
        if decision_rule not in {"max", "min"}:
            errors.append(f"{case_id}: invalid decision_rule {decision_rule}")
            continue

        headers, csv_rows = read_csv_rows(csv_path)
        if entity_column not in headers:
            errors.append(f"{case_id}: entity_column {entity_column} not in CSV headers {headers}")
        if metric_column not in headers:
            errors.append(f"{case_id}: metric_column {metric_column} not in CSV headers {headers}")
        truth = compute_truth(csv_rows, entity_column, metric_column, decision_rule)
        if not truth:
            errors.append(f"{case_id}: ground truth is not unique or not computable")
        elif str(row.get("ground_truth_entity")) != truth:
            errors.append(
                f"{case_id}: ground_truth_entity mismatch; metadata={row.get('ground_truth_entity')} csv={truth}"
            )

    expected_scenarios = {
        "business_operations",
        "public_statistics",
        "education_hr",
        "health_environment",
    }
    if set(by_scenario) != expected_scenarios:
        errors.append(f"Scenario set mismatch: expected {sorted(expected_scenarios)}, found {sorted(by_scenario)}")

    for scenario in expected_scenarios:
        items = by_scenario.get(scenario, [])
        if len(items) != per_scenario:
            errors.append(f"{scenario}: expected {per_scenario}, found {len(items)}.")
        misleaders = Counter(str(item.get("misleader_type")) for item in items)
        if len(misleaders) < 3:
            errors.append(f"{scenario}: expected at least 3 misleader types, found {dict(misleaders)}.")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate selected MisleadingChartQA web-agent benchmark cases.")
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
