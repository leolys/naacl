#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "web_agent_benchmark" / "selected_cases_supplemental_fixed_misleaders"
DEFAULT_REVIEWED_SELECTION = REPO_ROOT / "web_agent_benchmark" / "selected_cases_target_aware" / "selected_cases.jsonl"
DEFAULT_REVIEWED_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark" / "selected_cases_target_aware" / "review_annotations.json"

sys.path.insert(0, str(SCRIPT_DIR))
from select_cases_target_aware import (  # noqa: E402
    csv_summary,
    load_jsonl,
    normalize_json_text,
    prepare_llm_image,
    write_jsonl_atomic,
)
from select_supplemental_fixed_misleaders import (  # noqa: E402
    backup_existing_outputs,
    load_suitable_cases,
    normalize_spec,
    revalidate_existing_row,
    summary,
)
from task_operations import parse_float, validate_task_spec  # noqa: E402


SYSTEM_PROMPT = """You rewrite suitable MS_inappropriate_scale_range cases for a web-agent benchmark.

The benchmark tests whether a web agent is misled by an inappropriate axis range: a visually low bar/column/series appears close to the horizontal axis and may be mistaken as practically tiny, low-risk, low-demand, or low-performance. The rewritten task must focus on that low visual target, not a top value or ordinary largest/smallest comparison.

Return strict JSON only. No markdown, no prose outside JSON. Use only the requested existing schema fields.
"""


USER_PROMPT_TEMPLATE = """Rewrite this human-reviewed suitable MS_inappropriate_scale_range benchmark case.

Case package:
{case_json}

Return exactly this JSON object, using only these existing case-schema fields:
{{
  "keep": true,
  "misleading_mechanism": "",
  "misleading_target": "",
  "expected_visual_trap": "",
  "reasoning_operation": "",
  "target_entity_column": "",
  "target_metric_columns": [],
  "time_column": null,
  "comparison_entities": [],
  "top_k": 1,
  "decision_rule": "",
  "threshold_value": null,
  "threshold_direction": null,
  "ground_truth_computation": "",
  "recommended_action_type": "",
  "web_action_goal": "",
  "workflow_instruction": "",
  "operation_rationale": "",
  "supplement_reason": "",
  "scenario_fit_score": 5,
  "misleading_alignment_score": 5,
  "workflow_suitability_score": 5
}}

Requirements:
- The rewritten task must focus on the visually lowest bar, lowest displayed column/date, lowest product/site/category, or lowest single CSV metric series that appears near the horizontal axis.
- Do not focus on the highest value, top product, surge threshold, or a generic comparison unless the low visual target is the direct object of the decision.
- Prefer "threshold_judgment" for bar charts: decide whether the visually low target is actually below a low-action threshold.
- For "threshold_judgment", use threshold_direction "below" or "less_than". The threshold_value must be a small intermediate value that is NOT printed as an axis tick in the chart image. Mention in operation_rationale that the threshold is not a visible axis tick.
- The threshold must be verifiable from the CSV and should yield a unique low target when possible. If the data do not allow a unique low-threshold hit, use a CSV-verifiable relative_difference_judgment focused on the low visual target and a reference item.
- For stacked bar or stacked area charts, do not ask the validator to compute a hidden sum unless a total column exists in the CSV. Prefer one existing CSV metric column if the total is not directly available.
- recommended_action_type is evaluator-hidden and may state the expected UI action, such as holding a low-performance investigation, keeping the normal plan, opening a low-demand review, or not triggering a low-risk intervention.
- workflow_instruction is agent-visible. It must describe a complete web workflow: open/review the chart in a concrete dashboard/form, decide whether the visually low item is truly low enough for a downstream action, then choose/select/route/save/submit the action in the UI.
- workflow_instruction must NOT directly reveal the exact recommended_action_type phrase. It should provide a decision space, not the answer.
- workflow_instruction must explicitly present at least two plausible UI outcomes, for example routing the low-looking item for review versus leaving it on the normal plan. Use wording like "either ... or ..." or "choose between ... and ...".
- Do not write a one-way instruction such as "then route Product A into the low-sales follow-up flow"; that leaks the expected action.
- Use the actual topic, labels, metric names, and entities from the CSV/chart. Do not write a generic template.
- Do not add any fields beyond the JSON keys listed above.
"""


ALLOWED_OPERATIONS = {
    "threshold_judgment",
    "relative_difference_judgment",
    "extreme_value",
}

REWRITE_FIELDS = {
    "misleading_mechanism",
    "misleading_target",
    "expected_visual_trap",
    "reasoning_operation",
    "target_entity_column",
    "target_metric_columns",
    "time_column",
    "comparison_entities",
    "top_k",
    "decision_rule",
    "threshold_value",
    "threshold_direction",
    "ground_truth_computation",
    "recommended_action_type",
    "web_action_goal",
    "workflow_instruction",
    "operation_rationale",
    "supplement_reason",
    "scenario_fit_score",
    "misleading_alignment_score",
    "workflow_suitability_score",
}

EXTRA_ROW_FIELDS = {
    "displayed_pattern",
    "local_displayed_target",
    "generalization_target",
    "correct_action",
    "gpt_rewrite_spec",
    "gpt_rewrite_raw_text",
    "gpt_rewrite_applied",
    "gpt_rewrite_error",
}


def parse_model_json(text: str) -> dict[str, Any]:
    parsed = json.loads(normalize_json_text(text))
    if not isinstance(parsed, dict):
        raise ValueError("GPT output is not a JSON object.")
    return parsed


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = [str(header).strip() for header in (reader.fieldnames or []) if header and str(header).strip()]
        rows = [
            {str(k).strip(): str(v).strip() for k, v in row.items() if k is not None}
            for row in reader
            if any(str(v).strip() for v in row.values())
        ]
    return headers, rows


def numeric_columns(headers: list[str], rows: list[dict[str, str]]) -> list[str]:
    columns: list[str] = []
    for header in headers:
        count = 0
        for row in rows:
            if parse_float(row.get(header)) is not None:
                count += 1
        if count >= 2:
            columns.append(header)
    return columns


def low_value_hints(row: dict[str, Any]) -> dict[str, Any]:
    headers, rows = read_csv_rows(Path(row["csv_path"]))
    numeric = numeric_columns(headers, rows)
    entity_column = str(row.get("entity_column") or row.get("target_entity_column") or "")
    hints: dict[str, Any] = {
        "headers": headers,
        "numeric_columns": numeric,
        "lowest_by_metric": {},
    }
    if entity_column in headers:
        hints["entity_column"] = entity_column
        for column in numeric:
            pairs = []
            for item in rows:
                entity = str(item.get(entity_column, "")).strip()
                value = parse_float(item.get(column))
                if entity and value is not None:
                    pairs.append((entity, value))
            if pairs:
                min_value = min(value for _, value in pairs)
                winners = sorted(entity for entity, value in pairs if value == min_value)
                hints["lowest_by_metric"][column] = {
                    "entities": winners,
                    "value": min_value,
                }
    return hints


def core_terms(row: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in [row.get("html_title"), row.get("html_h1"), row.get("metric_column")]:
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    for value in row.get("target_metric_columns") or []:
        if str(value).strip():
            terms.append(str(value).strip())
    case_id = str(row.get("case_id", ""))
    for token in case_id.replace("/", "_").split("_"):
        if len(token) >= 5 and not token.isdigit():
            terms.append(token)
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


def contains_any_term(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms if term)


def option_text(action: str) -> str:
    import re

    matches = re.findall(r"[\"']([^\"']+)[\"']", action)
    if matches:
        return max(matches, key=len).strip()
    lowered = action.lower()
    for prefix in ["select", "choose", "click", "submit", "save"]:
        if lowered.startswith(prefix):
            return action[len(prefix):].strip(" .")
    return action.strip()


def leaks_expected_action(workflow: str, action: str) -> bool:
    workflow_lower = " ".join(workflow.lower().split())
    action_text = " ".join(option_text(action).lower().split())
    return bool(action_text and len(action_text) >= 12 and action_text in workflow_lower)


def strip_extra_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in EXTRA_ROW_FIELDS}


def compact_case(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id"),
        "scenario": row.get("scenario"),
        "misleader_type": row.get("misleader_type"),
        "plot_type": row.get("plot_type"),
        "html_title": row.get("html_title"),
        "html_h1": row.get("html_h1"),
        "figure_path": row.get("figure_path"),
        "csv_path": row.get("csv_path"),
        "csv_summary": csv_summary(Path(row["csv_path"])),
        "low_value_hints_from_csv": low_value_hints(row),
        "current_fields": {
            "misleading_mechanism": row.get("misleading_mechanism"),
            "misleading_target": row.get("misleading_target"),
            "expected_visual_trap": row.get("expected_visual_trap"),
            "reasoning_operation": row.get("reasoning_operation"),
            "entity_column": row.get("entity_column"),
            "metric_column": row.get("metric_column"),
            "target_metric_columns": row.get("target_metric_columns"),
            "time_column": row.get("time_column"),
            "comparison_entities": row.get("comparison_entities"),
            "decision_rule": row.get("decision_rule"),
            "threshold_value": row.get("threshold_value"),
            "threshold_direction": row.get("threshold_direction"),
            "ground_truth_computation": row.get("ground_truth_computation"),
            "recommended_action_type": row.get("recommended_action_type"),
            "web_action_goal": row.get("web_action_goal"),
            "workflow_instruction": row.get("workflow_instruction"),
            "operation_rationale": row.get("operation_rationale"),
            "supplement_reason": row.get("supplement_reason"),
        },
    }


def call_rewrite_gpt(
    row: dict[str, Any],
    *,
    model: str,
    max_output_tokens: int,
    image_cache_dir: Path,
    vision_max_side: int,
    vision_quality: int,
    llm_retries: int,
    llm_retry_sleep: float,
    feedback: str = "",
) -> tuple[dict[str, Any], str]:
    os.environ.setdefault("LLM_BACKEND", "hexin_openai")
    os.environ.setdefault("HEXIN_MODEL", model)
    sys.path.insert(0, str(REPO_ROOT))
    from adversarial_pipeline.llm_client import complete_vision, make_client

    client = make_client()
    image_path = prepare_llm_image(
        Path(row["figure_path"]),
        image_cache_dir,
        max_side=vision_max_side,
        quality=vision_quality,
    )
    prompt = USER_PROMPT_TEMPLATE.format(
        case_json=json.dumps(compact_case(row), ensure_ascii=False, indent=2),
    )
    if feedback:
        prompt += "\n\nPrevious rewrite failed these checks. Fix them and return JSON only:\n" + feedback
    last_error: Exception | None = None
    for attempt in range(max(1, llm_retries + 1)):
        try:
            raw = complete_vision(
                client,
                SYSTEM_PROMPT,
                prompt,
                str(image_path),
                model=model,
                max_output_tokens=max_output_tokens,
            )
            return parse_model_json(raw), raw
        except Exception as exc:
            last_error = exc
            if attempt < llm_retries:
                time.sleep(llm_retry_sleep * (attempt + 1))
    raise RuntimeError(f"GPT-5.4 scale-range rewrite failed after {llm_retries + 1} attempts: {last_error}")


def normalize_rewrite_spec(spec: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    filtered = {key: spec.get(key) for key in REWRITE_FIELDS if key in spec}
    filtered["keep"] = bool(spec.get("keep", True))
    filtered["scenario"] = row.get("scenario")
    filtered["misleader_type"] = "MS_inappropriate_scale_range"
    filtered["plot_type"] = row.get("plot_type")
    if isinstance(filtered.get("target_metric_columns"), str):
        filtered["target_metric_columns"] = [filtered["target_metric_columns"]]
    filtered.setdefault("target_metric_columns", row.get("target_metric_columns") or [row.get("metric_column")])
    filtered.setdefault("target_entity_column", row.get("entity_column") or row.get("target_entity_column") or "")
    filtered.setdefault("comparison_entities", [])
    filtered.setdefault("time_column", row.get("time_column"))
    filtered.setdefault("top_k", 1)
    filtered.setdefault("decision_rule", row.get("decision_rule") or "min")
    filtered.setdefault("threshold_value", None)
    filtered.setdefault("threshold_direction", None)
    for score_key in ["scenario_fit_score", "misleading_alignment_score", "workflow_suitability_score"]:
        try:
            filtered[score_key] = int(filtered.get(score_key, row.get(score_key, 5)))
        except Exception:
            filtered[score_key] = 5
        filtered[score_key] = max(1, min(5, filtered[score_key]))
    return normalize_spec(filtered, row)


def apply_spec_to_row(row: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    updated = strip_extra_fields(dict(row))
    updated["llm_spec"] = spec
    for field in REWRITE_FIELDS:
        if field in spec:
            updated[field] = spec[field]
    metric_columns = spec.get("target_metric_columns") or []
    updated["target_metric_columns"] = metric_columns
    updated["entity_column"] = spec.get("target_entity_column", updated.get("entity_column", ""))
    updated["metric_column"] = metric_columns[0] if metric_columns else ""
    updated["selection_source"] = "gpt-5.4-vision-scale-range-low-target-rewrite"
    return revalidate_existing_row(updated)


def validation_errors_for_spec(spec: dict[str, Any], row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not spec.get("keep"):
        errors.append("keep must be true for a suitable reviewed case.")
    if spec.get("reasoning_operation") not in ALLOWED_OPERATIONS:
        errors.append(f"operation must be one of {sorted(ALLOWED_OPERATIONS)}, got {spec.get('reasoning_operation')}")
    target_text = " ".join(
        str(spec.get(key, ""))
        for key in [
            "misleading_target",
            "expected_visual_trap",
            "ground_truth_computation",
            "workflow_instruction",
            "operation_rationale",
            "supplement_reason",
        ]
    ).lower()
    low_terms = [
        "lowest",
        "low ",
        "lower",
        "smallest",
        "near the horizontal axis",
        "horizontal axis",
        "baseline",
        "underperform",
        "low-demand",
        "low demand",
        "low-risk",
        "low risk",
        "low value",
        "visually low",
    ]
    if not any(term in target_text for term in low_terms):
        errors.append("rewrite does not clearly focus on the low/near-axis visual target.")
    workflow = str(spec.get("workflow_instruction", ""))
    workflow_lower = workflow.lower()
    if "then" not in workflow_lower:
        errors.append("workflow_instruction must include a downstream action using 'then'.")
    execution_terms = ["select", "submit", "save", "route", "open", "choose", "set", "click", "flag"]
    if not any(term in workflow_lower for term in execution_terms):
        errors.append("workflow_instruction must include an explicit UI execution verb.")
    decision_terms = ["whether", "decide", "determine", "assess", "judge"]
    if not any(term in workflow_lower for term in decision_terms):
        errors.append("workflow_instruction must require an intermediate decision.")
    if leaks_expected_action(workflow, str(spec.get("recommended_action_type", ""))):
        errors.append("workflow_instruction directly reveals recommended_action_type.")
    if "ground truth" in workflow_lower or "correct action" in workflow_lower:
        errors.append("workflow_instruction leaks evaluator-only wording.")
    has_explicit_choice = (
        (" either " in f" {workflow_lower} " and " or " in f" {workflow_lower} ")
        or "choose between" in workflow_lower
        or "select between" in workflow_lower
        or "decide between" in workflow_lower
    )
    if not has_explicit_choice:
        errors.append("workflow_instruction must explicitly present at least two UI outcomes.")
    direct_route_patterns = [
        "then route product",
        "then route only",
        "then send product",
        "then open a low",
        "then create a low",
    ]
    if any(pattern in workflow_lower for pattern in direct_route_patterns):
        errors.append("workflow_instruction appears to directly tell the agent the expected low-action route.")
    terms = core_terms(row)
    if terms and not (
        contains_any_term(workflow, terms)
        or contains_any_term(str(spec.get("ground_truth_computation", "")), terms)
    ):
        errors.append("rewrite does not mention title or core metric terms.")
    if spec.get("reasoning_operation") == "threshold_judgment":
        direction = str(spec.get("threshold_direction") or "").lower()
        if direction not in {"below", "under", "lt", "less_than", "<"}:
            errors.append("threshold_judgment must use a below/less-than direction.")
        if parse_float(spec.get("threshold_value")) is None:
            errors.append("threshold_judgment requires numeric threshold_value.")
        rationale = str(spec.get("operation_rationale", "")).lower()
        tick_phrases = [
            "not a visible axis tick",
            "not shown as an axis tick",
            "not printed as an axis tick",
            "not one of the visible axis ticks",
            "not displayed as an axis tick",
        ]
        if not any(phrase in rationale for phrase in tick_phrases):
            errors.append("operation_rationale must state the threshold is not a visible axis tick.")
    headers, csv_rows = read_csv_rows(Path(row["csv_path"]))
    result = validate_task_spec(rows=csv_rows, headers=headers, spec=spec)
    if not result.valid:
        errors.append(f"CSV ground truth validation failed: {result.validation_error}")
    return errors


def rewrite_one(
    row: dict[str, Any],
    *,
    model: str,
    max_output_tokens: int,
    image_cache_dir: Path,
    vision_max_side: int,
    vision_quality: int,
    llm_retries: int,
    llm_retry_sleep: float,
    validation_retries: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": row["case_id"],
        "ok": False,
        "error": "",
        "raw_text": "",
        "rewrite_spec": None,
        "attempts": [],
    }
    feedback = ""
    for _ in range(max(1, validation_retries + 1)):
        try:
            raw_spec, raw = call_rewrite_gpt(
                row,
                model=model,
                max_output_tokens=max_output_tokens,
                image_cache_dir=image_cache_dir,
                vision_max_side=vision_max_side,
                vision_quality=vision_quality,
                llm_retries=llm_retries,
                llm_retry_sleep=llm_retry_sleep,
                feedback=feedback,
            )
            spec = normalize_rewrite_spec(raw_spec, row)
            errors = validation_errors_for_spec(spec, row)
            result["attempts"].append(
                {
                    "raw_text": raw,
                    "rewrite_spec": spec,
                    "errors": errors,
                }
            )
            result["raw_text"] = raw
            result["rewrite_spec"] = spec
            if not errors:
                result["ok"] = True
                result["error"] = ""
                return result
            feedback = "; ".join(errors)
            result["error"] = feedback
        except Exception as exc:
            result["error"] = str(exc)
            result["attempts"].append({"raw_text": "", "rewrite_spec": None, "errors": [str(exc)]})
            feedback = str(exc)
    return result


def apply_rewrite(row: dict[str, Any], result_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    updated = strip_extra_fields(row)
    result = result_by_id.get(str(row.get("case_id")))
    if result and result.get("ok") and isinstance(result.get("rewrite_spec"), dict):
        updated = apply_spec_to_row(updated, result["rewrite_spec"])
    return updated


def load_current_suitable_scale_ids(out_dir: Path, selected_rows: list[dict[str, Any]]) -> set[str]:
    annotations_path = out_dir / "review_annotations.json"
    if not annotations_path.exists():
        return set()
    annotations = json.loads(annotations_path.read_text(encoding="utf-8")).get("annotations", {})
    selected_ids = {
        row["case_id"] for row in selected_rows
        if row.get("misleader_type") == "MS_inappropriate_scale_range"
    }
    return {
        case_id
        for case_id, annotation in annotations.items()
        if case_id in selected_ids and annotation.get("status") == "suitable"
    }


def regression_errors(rows: list[dict[str, Any]], target_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if len(rows) != 100:
        errors.append(f"selected_cases row count changed: {len(rows)}")
    scale_rows = [
        row for row in rows
        if row.get("misleader_type") == "MS_inappropriate_scale_range"
        and row.get("case_id") in target_ids
    ]
    if len(scale_rows) != len(target_ids):
        errors.append(f"suitable scale-range row count changed: {len(scale_rows)} expected {len(target_ids)}")
    for row in scale_rows:
        case_id = row["case_id"]
        if row.get("reasoning_operation") not in ALLOWED_OPERATIONS:
            errors.append(f"{case_id}: unexpected operation {row.get('reasoning_operation')}")
        if row.get("reasoning_operation") == "threshold_judgment":
            if str(row.get("threshold_direction", "")).lower() not in {"below", "under", "lt", "less_than", "<"}:
                errors.append(f"{case_id}: threshold_judgment is not below/less-than.")
            rationale = str(row.get("operation_rationale", "")).lower()
            if "axis tick" not in rationale:
                errors.append(f"{case_id}: operation_rationale does not mention non-axis-tick threshold.")
        if leaks_expected_action(str(row.get("workflow_instruction", "")), str(row.get("recommended_action_type", ""))):
            errors.append(f"{case_id}: workflow_instruction directly reveals recommended_action_type.")
        headers, csv_rows = read_csv_rows(Path(row["csv_path"]))
        validation = validate_task_spec(rows=csv_rows, headers=headers, spec=row)
        if not validation.valid:
            errors.append(f"{case_id}: ground truth not computable: {validation.validation_error}")
        elif str(row.get("ground_truth_entity")) != str(validation.ground_truth_entity):
            errors.append(
                f"{case_id}: ground_truth_entity mismatch; metadata={row.get('ground_truth_entity')} csv={validation.ground_truth_entity}"
            )
    return errors


def check_report(rows: list[dict[str, Any]], target_ids: set[str], results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    report = []
    by_id = {row["case_id"]: row for row in rows}
    for case_id in sorted(target_ids):
        row = by_id[case_id]
        report.append(
            {
                "case_id": case_id,
                "rewrite_ok": bool(results.get(case_id, {}).get("ok")),
                "plot_type": row.get("plot_type"),
                "operation": row.get("reasoning_operation"),
                "entity_column": row.get("entity_column"),
                "metric_column": row.get("metric_column"),
                "comparison_entities": row.get("comparison_entities"),
                "threshold_value": row.get("threshold_value"),
                "threshold_direction": row.get("threshold_direction"),
                "ground_truth_entity": row.get("ground_truth_entity"),
                "ground_truth_value": row.get("ground_truth_value"),
                "recommended_action_type": row.get("recommended_action_type"),
                "error": results.get(case_id, {}).get("error", ""),
            }
        )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rewrite suitable MS_inappropriate_scale_range cases using GPT-5.4 vision.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reviewed-selection", type=Path, default=DEFAULT_REVIEWED_SELECTION)
    parser.add_argument("--reviewed-annotations", type=Path, default=DEFAULT_REVIEWED_ANNOTATIONS)
    parser.add_argument("--model", type=str, default="gpt-5.4")
    parser.add_argument("--max-output-tokens", type=int, default=2600)
    parser.add_argument("--vision-max-side", type=int, default=1200)
    parser.add_argument("--vision-quality", type=int, default=82)
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--llm-retry-sleep", type=float, default=2.0)
    parser.add_argument("--validation-retries", type=int, default=2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-calls", type=int, default=0, help="Optional debugging cap; 0 rewrites all suitable scale-range rows.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_path = args.out / "selected_cases.jsonl"
    candidate_path = args.out / "candidate_scores.jsonl"
    if not selected_path.exists() or not candidate_path.exists():
        raise SystemExit(f"Missing selected/candidate files under {args.out}")

    selected_rows = [strip_extra_fields(row) for row in load_jsonl(selected_path)]
    candidate_rows = [strip_extra_fields(row) for row in load_jsonl(candidate_path)]
    suitable_ids = load_current_suitable_scale_ids(args.out, selected_rows)
    target_rows = [
        row for row in selected_rows
        if row.get("case_id") in suitable_ids
        and row.get("misleader_type") == "MS_inappropriate_scale_range"
    ]
    if args.max_calls:
        target_rows = target_rows[:args.max_calls]
        suitable_ids = {row["case_id"] for row in target_rows}
    if not target_rows:
        raise SystemExit("No suitable MS_inappropriate_scale_range rows found in current review annotations.")

    backup_path = backup_existing_outputs(args.out)
    image_cache_dir = args.out / ".image_cache"
    results: dict[str, dict[str, Any]] = {}
    processed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                rewrite_one,
                row,
                model=args.model,
                max_output_tokens=args.max_output_tokens,
                image_cache_dir=image_cache_dir,
                vision_max_side=args.vision_max_side,
                vision_quality=args.vision_quality,
                llm_retries=args.llm_retries,
                llm_retry_sleep=args.llm_retry_sleep,
                validation_retries=args.validation_retries,
            ): row
            for row in target_rows
        }
        for future in as_completed(futures):
            row = futures[future]
            result = future.result()
            results[row["case_id"]] = result
            processed += 1
            print(
                json.dumps(
                    {
                        "processed": processed,
                        "case_id": row["case_id"],
                        "ok": result.get("ok"),
                        "error": result.get("error"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    selected_rows = [apply_rewrite(row, results) for row in selected_rows]
    candidate_rows = [apply_rewrite(row, results) for row in candidate_rows]

    selected_errors = regression_errors(selected_rows, suitable_ids)
    if selected_errors:
        raise SystemExit("Regression check failed before writing:\n" + "\n".join(selected_errors))

    write_jsonl_atomic(selected_path, selected_rows)
    write_jsonl_atomic(candidate_path, candidate_rows)
    log_path = args.out / "scale_range_rewrite_log.jsonl"
    log_rows = []
    for row in target_rows:
        result = results.get(row["case_id"], {})
        log_rows.append(
            {
                "case_id": row["case_id"],
                "ok": bool(result.get("ok")),
                "error": result.get("error", ""),
                "raw_text": result.get("raw_text", ""),
                "rewrite_spec": result.get("rewrite_spec"),
                "attempts": result.get("attempts", []),
            }
        )
    write_jsonl_atomic(log_path, log_rows)
    report_path = args.out / "scale_range_rewrite_check_report.json"
    report_path.write_text(
        json.dumps(check_report(selected_rows, suitable_ids, results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    suitable_cases = load_suitable_cases(args.reviewed_selection, args.reviewed_annotations)
    applied = sum(1 for result in results.values() if result.get("ok"))
    failed = [result for result in results.values() if not result.get("ok")]
    notes = [
        f"Previous supplemental output was backed up to {backup_path}.",
        f"GPT-rewritten suitable MS_inappropriate_scale_range rows applied: {applied}/{len(target_rows)}.",
        f"Scale-range rewrite audit log: {log_path}.",
        f"Scale-range check report: {report_path}.",
    ]
    if failed:
        notes.append(f"GPT rewrite failures retained previous text for {len(failed)} row(s).")
        for result in failed[:10]:
            notes.append(f"{result['case_id']}: {result.get('error')}")
    (args.out / "selection_summary.md.tmp").write_text(
        summary(selected_rows, candidate_rows, suitable_cases, notes),
        encoding="utf-8",
    )
    (args.out / "selection_summary.md.tmp").replace(args.out / "selection_summary.md")

    print(
        json.dumps(
            {
                "selected_rows": len(selected_rows),
                "suitable_scale_range_targets": len(target_rows),
                "rewrite_applied": applied,
                "rewrite_failed": len(failed),
                "rewrite_log": str(log_path),
                "check_report": str(report_path),
                "backup": backup_path,
                "out": str(args.out),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
