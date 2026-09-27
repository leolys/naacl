from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


SUPPORTED_OPERATIONS = {
    "extreme_value",
    "pairwise_comparison",
    "rank_order",
    "trend_direction",
    "largest_change",
    "rate_of_change",
    "axis_or_scale_interpretation",
    "visual_size_vs_data_value",
    "correlation_direction",
    "relative_difference_judgment",
    "threshold_judgment",
    "largest_recent_change",
    "cumulative_vs_recent_change",
    "annotation_claim_verification",
    "cherry_picking_generalization_check",
}


@dataclass
class ValidationResult:
    valid: bool
    ground_truth_entity: str | None = None
    ground_truth_value: float | str | list[str] | None = None
    validation_error: str | None = None


def get_threshold(spec: dict[str, Any]) -> float | None:
    for key in ["threshold_value", "threshold", "decision_threshold"]:
        if key in spec:
            return parse_float(spec.get(key))
    return None


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


def normalize_rule(rule: str | None) -> str:
    rule = (rule or "max").strip().lower()
    aliases = {
        "highest": "max",
        "largest": "max",
        "top": "max",
        "greater": "max",
        "lowest": "min",
        "smallest": "min",
        "bottom": "min",
        "lower": "min",
        "invert_then_highest": "invert_then_max",
        "reverse_then_max": "invert_then_max",
        "inverted_max": "invert_then_max",
        "invert_then_lowest": "invert_then_min",
        "reverse_then_min": "invert_then_min",
        "inverted_min": "invert_then_min",
    }
    return aliases.get(rule, rule)


def natural_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+(?:\.\d+)?)", str(value))
    key: list[Any] = []
    for part in parts:
        if not part:
            continue
        try:
            key.append(float(part))
        except ValueError:
            key.append(part.lower())
    return key


def require_columns(headers: list[str], columns: list[str]) -> str | None:
    missing = [col for col in columns if col and col not in headers]
    if missing:
        return f"Missing CSV columns: {missing}; available={headers}"
    return None


def numeric_pairs(rows: list[dict[str, str]], entity_column: str, metric_column: str) -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    for row in rows:
        entity = str(row.get(entity_column, "")).strip()
        value = parse_float(row.get(metric_column))
        if entity and value is not None:
            pairs.append((entity, value))
    return pairs


def unique_extreme(pairs: list[tuple[str, float]], rule: str) -> ValidationResult:
    if not pairs:
        return ValidationResult(False, validation_error="No numeric entity/metric pairs.")
    target = min(value for _, value in pairs) if rule == "min" else max(value for _, value in pairs)
    winners = sorted({entity for entity, value in pairs if value == target})
    if len(winners) != 1:
        return ValidationResult(False, validation_error=f"Ground truth is not unique: {winners}")
    return ValidationResult(True, ground_truth_entity=winners[0], ground_truth_value=target)


def validate_extreme(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str,
    metric_column: str,
    decision_rule: str,
) -> ValidationResult:
    err = require_columns(headers, [entity_column, metric_column])
    if err:
        return ValidationResult(False, validation_error=err)
    rule = normalize_rule(decision_rule)
    if rule not in {"max", "min"}:
        return ValidationResult(False, validation_error=f"Unsupported decision_rule for extreme operation: {decision_rule}")
    return unique_extreme(numeric_pairs(rows, entity_column, metric_column), rule)


def validate_pairwise(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str,
    metric_column: str,
    decision_rule: str,
    comparison_entities: list[str],
) -> ValidationResult:
    err = require_columns(headers, [entity_column, metric_column])
    if err:
        return ValidationResult(False, validation_error=err)
    if len(comparison_entities) != 2:
        return ValidationResult(False, validation_error="pairwise_comparison requires exactly two comparison_entities.")
    wanted = {str(entity) for entity in comparison_entities}
    pairs = [(entity, value) for entity, value in numeric_pairs(rows, entity_column, metric_column) if entity in wanted]
    found = {entity for entity, _ in pairs}
    if found != wanted:
        return ValidationResult(False, validation_error=f"Could not find both comparison entities. wanted={wanted}, found={found}")
    return unique_extreme(pairs, "min" if normalize_rule(decision_rule) == "min" else "max")


def validate_rank_order(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str,
    metric_column: str,
    decision_rule: str,
    top_k: int = 1,
) -> ValidationResult:
    result = validate_extreme(rows, headers, entity_column, metric_column, decision_rule)
    if top_k <= 1 or not result.valid:
        return result
    pairs = numeric_pairs(rows, entity_column, metric_column)
    reverse = normalize_rule(decision_rule) != "min"
    ranked = sorted(pairs, key=lambda item: item[1], reverse=reverse)
    if len(ranked) < top_k:
        return ValidationResult(False, validation_error=f"Could not compute rank {top_k}.")
    kth_value = ranked[top_k - 1][1]
    kth_entities = sorted({entity for entity, value in pairs if value == kth_value})
    if len(kth_entities) != 1:
        return ValidationResult(False, validation_error=f"Rank {top_k} ground truth is not unique: {kth_entities}")
    entities = []
    seen = set()
    for entity, _ in ranked:
        if entity not in seen:
            entities.append(entity)
            seen.add(entity)
        if len(entities) == top_k:
            break
    if len(entities) < top_k:
        return ValidationResult(False, validation_error=f"Could not compute top_{top_k}.")
    return ValidationResult(True, ground_truth_entity=entities[top_k - 1], ground_truth_value=entities)


def grouped_by_entity_time(
    rows: list[dict[str, str]],
    entity_column: str | None,
    time_column: str,
    metric_column: str,
) -> dict[str, list[tuple[str, float]]]:
    groups: dict[str, list[tuple[str, float]]] = defaultdict(list)
    use_entity_column = entity_column if entity_column and entity_column != time_column else None
    for row in rows:
        entity = str(row.get(use_entity_column, "")).strip() if use_entity_column else "__series__"
        time_value = str(row.get(time_column, "")).strip()
        metric_value = parse_float(row.get(metric_column))
        if entity and time_value and metric_value is not None:
            groups[entity].append((time_value, metric_value))
    for entity in list(groups):
        groups[entity].sort(key=lambda item: natural_key(item[0]))
    return groups


def validate_trend_direction(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str | None,
    time_column: str,
    metric_column: str,
) -> ValidationResult:
    cols = [time_column, metric_column] + ([entity_column] if entity_column else [])
    err = require_columns(headers, [col for col in cols if col])
    if err:
        return ValidationResult(False, validation_error=err)
    groups = grouped_by_entity_time(rows, entity_column, time_column, metric_column)
    if len(groups) != 1:
        return ValidationResult(False, validation_error="trend_direction currently requires a single series or a preselected entity.")
    points = next(iter(groups.values()))
    if len(points) < 2:
        return ValidationResult(False, validation_error="Need at least two time points.")
    first, last = points[0][1], points[-1][1]
    if last > first:
        direction = "increasing"
    elif last < first:
        direction = "decreasing"
    else:
        direction = "stable"
    return ValidationResult(True, ground_truth_entity=direction, ground_truth_value=last - first)


def validate_change(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str | None,
    time_column: str,
    metric_column: str,
    operation: str,
    decision_rule: str,
) -> ValidationResult:
    cols = [time_column, metric_column] + ([entity_column] if entity_column else [])
    err = require_columns(headers, [col for col in cols if col])
    if err:
        return ValidationResult(False, validation_error=err)
    groups = grouped_by_entity_time(rows, entity_column, time_column, metric_column)
    candidates: list[tuple[str, float]] = []
    for entity, points in groups.items():
        if len(points) < 2:
            continue
        first_label, first = points[0]
        last_label, last = points[-1]
        if operation == "rate_of_change":
            if first == 0:
                continue
            change = (last - first) / abs(first)
        else:
            change = last - first
        label = entity if entity != "__series__" else f"{first_label}->{last_label}"
        candidates.append((label, change))
    if not candidates:
        return ValidationResult(False, validation_error="No comparable change candidates.")
    rule = normalize_rule(decision_rule)
    if rule not in {"max", "min"}:
        rule = "max"
    return unique_extreme(candidates, rule)


def pearson(values_a: list[float], values_b: list[float]) -> float | None:
    if len(values_a) != len(values_b) or len(values_a) < 3:
        return None
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    num = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b))
    den_a = math.sqrt(sum((a - mean_a) ** 2 for a in values_a))
    den_b = math.sqrt(sum((b - mean_b) ** 2 for b in values_b))
    if den_a == 0 or den_b == 0:
        return None
    return num / (den_a * den_b)


def validate_correlation_direction(
    rows: list[dict[str, str]],
    headers: list[str],
    metric_columns: list[str],
    threshold: float | None,
) -> ValidationResult:
    if len(metric_columns) < 2:
        return ValidationResult(False, validation_error="correlation_direction requires two target_metric_columns.")
    col_a, col_b = metric_columns[0], metric_columns[1]
    err = require_columns(headers, [col_a, col_b])
    if err:
        return ValidationResult(False, validation_error=err)
    pairs = []
    for row in rows:
        a = parse_float(row.get(col_a))
        b = parse_float(row.get(col_b))
        if a is not None and b is not None:
            pairs.append((a, b))
    corr = pearson([a for a, _ in pairs], [b for _, b in pairs])
    if corr is None:
        return ValidationResult(False, validation_error="Could not compute stable correlation.")
    cutoff = 0.2 if threshold is None else abs(threshold)
    if corr > cutoff:
        label = "positive_correlation"
    elif corr < -cutoff:
        label = "negative_correlation"
    else:
        label = "no_clear_correlation"
    return ValidationResult(True, ground_truth_entity=label, ground_truth_value=round(corr, 4))


def numeric_columns(rows: list[dict[str, str]], headers: list[str], min_values: int = 2) -> list[str]:
    columns: list[str] = []
    for header in headers:
        values = [parse_float(row.get(header)) for row in rows]
        if sum(value is not None for value in values) >= min_values:
            columns.append(header)
    return columns


def infer_time_column(rows: list[dict[str, str]], headers: list[str], metric_columns: list[str]) -> str | None:
    metric_set = set(metric_columns)
    for header in headers:
        if header not in metric_set and header.lower() in {"time", "date", "year", "month", "quarter", "period"}:
            return header
    for header in headers:
        if header not in metric_set:
            values = [str(row.get(header, "")).strip() for row in rows if str(row.get(header, "")).strip()]
            if len(values) >= 2 and len(set(values)) >= 2:
                return header
    return None


def validate_cherry_picking_generalization(
    rows: list[dict[str, str]],
    headers: list[str],
    spec: dict[str, Any],
    metric_columns: list[str],
    time_column: str | None,
) -> ValidationResult:
    if spec.get("misleader_type") != "cherry_picking":
        return ValidationResult(
            False,
            validation_error="cherry_picking_generalization_check is only valid for misleader_type=cherry_picking.",
        )
    plot_type = str(spec.get("plot_type", "")).strip()
    inferred_numeric = numeric_columns(rows, headers)
    metric_columns = [column for column in metric_columns if column in headers]

    if plot_type == "scatter_plot":
        usable = metric_columns[:2] if len(metric_columns) >= 2 else inferred_numeric[:2]
        if len(usable) < 2:
            return ValidationResult(False, validation_error="cherry_picking scatter plot requires at least two numeric CSV columns.")
        pairs = []
        for row in rows:
            a = parse_float(row.get(usable[0]))
            b = parse_float(row.get(usable[1]))
            if a is not None and b is not None:
                pairs.append((a, b))
        if len(pairs) < 3:
            return ValidationResult(False, validation_error="cherry_picking scatter plot requires at least three numeric point pairs.")
        return ValidationResult(
            True,
            ground_truth_entity="request_further_analysis",
            ground_truth_value="insufficient_evidence_for_overall_generalization",
        )

    metric_column = metric_columns[0] if metric_columns else (inferred_numeric[0] if inferred_numeric else "")
    inferred_time = time_column if time_column in headers else infer_time_column(rows, headers, [metric_column])
    if not metric_column or not inferred_time:
        return ValidationResult(False, validation_error="cherry_picking line/generalization check requires time and metric columns.")
    err = require_columns(headers, [inferred_time, metric_column])
    if err:
        return ValidationResult(False, validation_error=err)
    points = []
    for row in rows:
        time_value = str(row.get(inferred_time, "")).strip()
        metric_value = parse_float(row.get(metric_column))
        if time_value and metric_value is not None:
            points.append((time_value, metric_value))
    if len(points) < 3:
        return ValidationResult(False, validation_error="cherry_picking generalization check requires at least three time/metric points.")
    return ValidationResult(
        True,
        ground_truth_entity="request_further_analysis",
        ground_truth_value="insufficient_evidence_for_overall_generalization",
    )


def validate_relative_difference(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str,
    metric_column: str,
    comparison_entities: list[str],
    threshold: float | None,
) -> ValidationResult:
    err = require_columns(headers, [entity_column, metric_column])
    if err:
        return ValidationResult(False, validation_error=err)
    if len(comparison_entities) != 2:
        return ValidationResult(False, validation_error="relative_difference_judgment requires exactly two comparison_entities.")
    if threshold is None:
        return ValidationResult(False, validation_error="relative_difference_judgment requires threshold_value.")
    wanted = [str(entity) for entity in comparison_entities]
    values: dict[str, float] = {}
    for entity, value in numeric_pairs(rows, entity_column, metric_column):
        if entity in wanted and entity not in values:
            values[entity] = value
    if set(values) != set(wanted):
        return ValidationResult(False, validation_error=f"Could not find both comparison entities. wanted={wanted}, found={sorted(values)}")
    a, b = values[wanted[0]], values[wanted[1]]
    denom = max(abs(a), abs(b), 1e-9)
    relative = abs(a - b) / denom
    label = "meaningful_difference" if relative >= threshold else "minor_difference"
    return ValidationResult(True, ground_truth_entity=label, ground_truth_value=round(relative, 4))


def validate_threshold_judgment(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str | None,
    metric_column: str,
    threshold: float | None,
    direction: str,
    comparison_entities: list[str] | None = None,
) -> ValidationResult:
    if threshold is None:
        return ValidationResult(False, validation_error="threshold_judgment requires threshold_value.")
    cols = [metric_column] + ([entity_column] if entity_column else [])
    err = require_columns(headers, [col for col in cols if col])
    if err:
        return ValidationResult(False, validation_error=err)
    direction = (direction or "gte").lower()
    if direction in {"above", "over", "gt", "greater_than", ">"}:
        predicate = lambda value: value > threshold
    elif direction in {"below", "under", "lt", "less_than", "<"}:
        predicate = lambda value: value < threshold
    elif direction in {"lte", "at_or_below", "<="}:
        predicate = lambda value: value <= threshold
    else:
        predicate = lambda value: value >= threshold
    if entity_column:
        pairs = numeric_pairs(rows, entity_column, metric_column)
        focus_entities = [str(entity) for entity in (comparison_entities or []) if str(entity)]
        if len(focus_entities) == 1:
            focus_entity = focus_entities[0]
            matches = [(entity, value) for entity, value in pairs if entity == focus_entity]
            if not matches:
                return ValidationResult(False, validation_error=f"Could not find focus entity for threshold_judgment: {focus_entity}")
            value = matches[0][1]
            if predicate(value):
                return ValidationResult(True, ground_truth_entity=focus_entity, ground_truth_value=value)
            return ValidationResult(True, ground_truth_entity=f"{focus_entity}_does_not_cross_threshold", ground_truth_value=value)
        hits = sorted({entity for entity, value in pairs if predicate(value)})
        if len(hits) == 1:
            value = next(value for entity, value in pairs if entity == hits[0] and predicate(value))
            return ValidationResult(True, ground_truth_entity=hits[0], ground_truth_value=value)
        if not hits:
            return ValidationResult(True, ground_truth_entity="no_entity_crosses_threshold", ground_truth_value=threshold)
        return ValidationResult(False, validation_error=f"Threshold result is not unique: {hits}")
    values = [parse_float(row.get(metric_column)) for row in rows]
    nums = [value for value in values if value is not None]
    if not nums:
        return ValidationResult(False, validation_error="No numeric values for threshold_judgment.")
    hit = any(predicate(value) for value in nums)
    return ValidationResult(True, ground_truth_entity="threshold_met" if hit else "threshold_not_met", ground_truth_value=threshold)


def validate_largest_recent_change(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str | None,
    time_column: str,
    metric_column: str,
    decision_rule: str,
) -> ValidationResult:
    cols = [time_column, metric_column] + ([entity_column] if entity_column else [])
    err = require_columns(headers, [col for col in cols if col])
    if err:
        return ValidationResult(False, validation_error=err)
    groups = grouped_by_entity_time(rows, entity_column, time_column, metric_column)
    candidates: list[tuple[str, float]] = []
    for entity, points in groups.items():
        if len(points) < 2:
            continue
        prev_label, prev = points[-2]
        last_label, last = points[-1]
        label = entity if entity != "__series__" else f"{prev_label}->{last_label}"
        candidates.append((label, last - prev))
    if not candidates:
        return ValidationResult(False, validation_error="No comparable recent change candidates.")
    rule = normalize_rule(decision_rule)
    if rule not in {"max", "min"}:
        rule = "max"
    return unique_extreme(candidates, rule)


def validate_cumulative_vs_recent_change(
    rows: list[dict[str, str]],
    headers: list[str],
    entity_column: str | None,
    time_column: str,
    metric_column: str,
) -> ValidationResult:
    err = require_columns(headers, [time_column, metric_column] + ([entity_column] if entity_column else []))
    if err:
        return ValidationResult(False, validation_error=err)
    groups = grouped_by_entity_time(rows, entity_column, time_column, metric_column)
    if len(groups) != 1:
        return ValidationResult(False, validation_error="cumulative_vs_recent_change requires a single series or preselected entity.")
    points = next(iter(groups.values()))
    if len(points) < 2:
        return ValidationResult(False, validation_error="Need at least two time points for recent change.")
    recent = points[-1][1] - points[-2][1]
    if recent > 0:
        label = "recent_increase"
    elif recent < 0:
        label = "recent_decrease"
    else:
        label = "recent_stable"
    return ValidationResult(True, ground_truth_entity=label, ground_truth_value=recent)


def validate_annotation_claim(
    rows: list[dict[str, str]],
    headers: list[str],
    spec: dict[str, Any],
    entity_column: str | None,
    metric_column: str,
    time_column: str | None,
    comparison_entities: list[str],
    decision_rule: str,
) -> ValidationResult:
    if comparison_entities:
        return validate_pairwise(rows, headers, str(entity_column), metric_column, decision_rule, comparison_entities)
    if time_column:
        return validate_trend_direction(rows, headers, str(entity_column) if entity_column else None, time_column, metric_column)
    return validate_extreme(rows, headers, str(entity_column), metric_column, decision_rule)


def validate_task_spec(
    *,
    rows: list[dict[str, str]],
    headers: list[str],
    spec: dict[str, Any],
) -> ValidationResult:
    operation = str(spec.get("reasoning_operation", "")).strip()
    if operation not in SUPPORTED_OPERATIONS:
        return ValidationResult(False, validation_error=f"Unsupported reasoning_operation: {operation}")

    entity_column = spec.get("target_entity_column") or spec.get("entity_column")
    metric_columns = spec.get("target_metric_columns") or spec.get("metric_columns") or spec.get("metric_column")
    if isinstance(metric_columns, str):
        metric_columns = [metric_columns]
    metric_columns = [str(col) for col in (metric_columns or []) if col]
    metric_column = metric_columns[0] if metric_columns else ""
    time_column = spec.get("time_column") or None
    decision_rule = normalize_rule(spec.get("decision_rule"))
    comparison_entities = spec.get("comparison_entities") or []
    threshold = get_threshold(spec)
    threshold_direction = str(spec.get("threshold_direction") or spec.get("threshold_operator") or "gte")

    if operation in {"extreme_value", "axis_or_scale_interpretation", "visual_size_vs_data_value"}:
        return validate_extreme(rows, headers, str(entity_column), metric_column, decision_rule)
    if operation == "pairwise_comparison":
        return validate_pairwise(rows, headers, str(entity_column), metric_column, decision_rule, list(comparison_entities))
    if operation == "rank_order":
        top_k = int(spec.get("top_k") or 1)
        return validate_rank_order(rows, headers, str(entity_column), metric_column, decision_rule, top_k=top_k)
    if operation == "trend_direction":
        if not time_column:
            return ValidationResult(False, validation_error="trend_direction requires time_column.")
        return validate_trend_direction(rows, headers, str(entity_column) if entity_column else None, str(time_column), metric_column)
    if operation in {"largest_change", "rate_of_change"}:
        if not time_column:
            return ValidationResult(False, validation_error=f"{operation} requires time_column.")
        return validate_change(
            rows,
            headers,
            str(entity_column) if entity_column else None,
            str(time_column),
            metric_column,
            operation,
            decision_rule,
        )
    if operation == "correlation_direction":
        return validate_correlation_direction(rows, headers, metric_columns, threshold)
    if operation == "cherry_picking_generalization_check":
        return validate_cherry_picking_generalization(rows, headers, spec, metric_columns, str(time_column) if time_column else None)
    if operation == "relative_difference_judgment":
        return validate_relative_difference(rows, headers, str(entity_column), metric_column, list(comparison_entities), threshold)
    if operation == "threshold_judgment":
        threshold_comparison_entities = list(comparison_entities)
        if len(threshold_comparison_entities) == 1:
            focus_entity = str(threshold_comparison_entities[0])
            expected_entity = str(spec.get("ground_truth_entity") or "")
            if expected_entity not in {focus_entity, f"{focus_entity}_does_not_cross_threshold"}:
                threshold_comparison_entities = []
        return validate_threshold_judgment(
            rows,
            headers,
            str(entity_column) if entity_column else None,
            metric_column,
            threshold,
            threshold_direction,
            threshold_comparison_entities,
        )
    if operation == "largest_recent_change":
        if not time_column:
            return ValidationResult(False, validation_error="largest_recent_change requires time_column.")
        return validate_largest_recent_change(
            rows,
            headers,
            str(entity_column) if entity_column else None,
            str(time_column),
            metric_column,
            decision_rule,
        )
    if operation == "cumulative_vs_recent_change":
        if not time_column:
            return ValidationResult(False, validation_error="cumulative_vs_recent_change requires time_column.")
        return validate_cumulative_vs_recent_change(rows, headers, str(entity_column) if entity_column else None, str(time_column), metric_column)
    if operation == "annotation_claim_verification":
        return validate_annotation_claim(
            rows,
            headers,
            spec,
            str(entity_column) if entity_column else None,
            metric_column,
            str(time_column) if time_column else None,
            list(comparison_entities),
            decision_rule,
        )
    return ValidationResult(False, validation_error=f"Unhandled operation: {operation}")
