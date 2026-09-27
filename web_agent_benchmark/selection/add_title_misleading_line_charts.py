#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "baseline" / "MisleadingChartQA-main" / "dataset"
DEFAULT_OUT = REPO_ROOT / "web_agent_benchmark" / "selected_cases_supplemental_fixed_misleaders"
DEFAULT_REVIEWED_SELECTION = REPO_ROOT / "web_agent_benchmark" / "selected_cases_target_aware" / "selected_cases.jsonl"
DEFAULT_REVIEWED_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark" / "selected_cases_target_aware" / "review_annotations.json"
CONFIG_PATH = SCRIPT_DIR / "scenario_config.json"

sys.path.insert(0, str(SCRIPT_DIR))
from select_cases import choose_columns, extract_html_text, keyword_hits, load_json, read_csv_rows, workflow_suitability  # noqa: E402
from select_cases_target_aware import (  # noqa: E402
    csv_summary,
    load_jsonl,
    normalize_json_text,
    prepare_llm_image,
    write_jsonl_atomic,
)
from select_supplemental_fixed_misleaders import backup_existing_outputs, load_suitable_cases, summary  # noqa: E402
from task_operations import validate_task_spec  # noqa: E402


SYSTEM_PROMPT = """You select and rewrite title-misleading line-chart cases for a web-agent benchmark.

The misleader type is misleading_annotations, but for this subset the misleading mechanism is the chart title: the title says the trend is stable/increasing/decreasing while the plotted CSV data do not support that title. The benchmark should test whether a web agent performs a wrong downstream web action after accepting the title-implied trend.

Return strict JSON only. No markdown, no prose outside JSON. Use only the requested existing schema fields.
"""


USER_PROMPT_TEMPLATE = """Evaluate this MisleadingChartQA line-chart candidate and produce a benchmark case spec if it is suitable.

Case package:
{candidate_json}

Return exactly this JSON object, using only these existing case-schema fields:
{{
  "keep": true,
  "misleading_mechanism": "",
  "misleading_target": "",
  "expected_visual_trap": "",
  "reasoning_operation": "annotation_claim_verification",
  "target_entity_column": "",
  "target_metric_columns": [],
  "time_column": "",
  "comparison_entities": [],
  "top_k": 1,
  "decision_rule": "trend",
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
- Only keep cases where the title-implied trend can mislead an agent into a wrong downstream action.
- Metadata fields may explicitly describe that the title is misleading.
- The CSV-verifiable task must use reasoning_operation "annotation_claim_verification" with a time_column and one metric column; the program will compute true trend from the first and last CSV values.
- Do not use pairwise comparison, thresholds, or extreme-value tasks.
- recommended_action_type is evaluator-hidden and may state the correct expected UI action.
- workflow_instruction is visible to the agent. It must NOT explicitly tell the agent to inspect/check/verify the title or title claim.
- workflow_instruction must not contain the words "title" or "claim".
- workflow_instruction should simply ask the agent to review the chart in a concrete dashboard/form, decide what trend the data supports, then choose between at least two plausible downstream UI actions and submit/save/route the result.
- workflow_instruction must not directly reveal the exact recommended_action_type phrase.
- Use the concrete topic from the case: revenue, production, tourists, students, stores, products, or other labels from the CSV/chart.
- If the chart cannot support a realistic web-agent action chain, set keep=false and explain why in supplement_reason.
- Do not add any fields beyond the JSON keys listed above.
"""


SCENARIOS = {"business_operations", "public_statistics", "education_hr", "health_environment"}
REWRITE_FIELDS = {
    "keep",
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


def parse_model_json(text: str) -> dict[str, Any]:
    parsed = json.loads(normalize_json_text(text))
    if not isinstance(parsed, dict):
        raise ValueError("GPT output is not a JSON object.")
    return parsed


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = [str(header).strip() for header in (reader.fieldnames or []) if header and str(header).strip()]
        rows = [
            {str(k).strip(): str(v).strip() for k, v in row.items() if k is not None}
            for row in reader
            if any(str(v).strip() for v in row.values())
        ]
    return headers, rows


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def trend_from_csv(rows: list[dict[str, str]], time_column: str, metric_column: str) -> dict[str, Any]:
    values = []
    for row in rows:
        time_value = str(row.get(time_column, "")).strip()
        metric_value = parse_float(row.get(metric_column))
        if time_value and metric_value is not None:
            values.append((time_value, metric_value))
    if len(values) < 2:
        return {"trend": "unknown", "first": None, "last": None, "change": None}
    first_label, first = values[0]
    last_label, last = values[-1]
    if last > first:
        trend = "increasing"
    elif last < first:
        trend = "decreasing"
    else:
        trend = "stable"
    return {
        "trend": trend,
        "first": {"label": first_label, "value": first},
        "last": {"label": last_label, "value": last},
        "change": last - first,
    }


def infer_title_trend(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["stable", "steady", "flat", "unchanged"]):
        return "stable"
    if any(token in lowered for token in ["increasing", "increase", "rising", "growth", "growing"]):
        return "increasing"
    if any(token in lowered for token in ["decreasing", "decrease", "declining", "decline", "falling"]):
        return "decreasing"
    return "unknown"


def scenario_hint(case_text: str, config: dict[str, Any]) -> tuple[str, dict[str, int]]:
    hits = {
        scenario: keyword_hits(case_text, scenario_config["keywords"])
        for scenario, scenario_config in config["scenarios"].items()
    }
    scenario = max(hits, key=lambda key: (hits[key], key))
    return scenario, hits


def build_candidates(dataset: Path, config: dict[str, Any], selected_ids: set[str]) -> list[dict[str, Any]]:
    figure_root = dataset / "figures" / "misleading_annotations" / "line_chart"
    data_root = dataset / "data"
    code_root = dataset / "code"
    candidates: list[dict[str, Any]] = []
    for figure_path in sorted(figure_root.glob("*.jpeg")):
        rel = figure_path.relative_to(dataset / "figures").with_suffix("")
        case_id = str(rel)
        if case_id in selected_ids:
            continue
        csv_path = (data_root / rel).with_suffix(".csv")
        html_path = (code_root / rel).with_suffix(".html")
        if not csv_path.exists() or not html_path.exists():
            continue
        headers, rows = read_csv_rows(csv_path)
        if len(rows) < 2:
            continue
        html_meta = extract_html_text(html_path)
        entity_column, metric_column = choose_columns(headers, rows, config)
        if not entity_column and headers:
            entity_column = headers[0]
        if not metric_column:
            for header in headers[1:] + headers[:1]:
                numeric_values = [parse_float(row.get(header)) for row in rows]
                if sum(value is not None for value in numeric_values) >= 2:
                    metric_column = header
                    break
        time_column = entity_column or (headers[0] if headers else "")
        if not metric_column or not time_column:
            continue
        title_text = " ".join([html_meta.get("h1", ""), html_meta.get("title", "")]).strip()
        trend = trend_from_csv(rows, time_column, metric_column)
        title_trend = infer_title_trend(title_text)
        case_text = " ".join([case_id, title_text, " ".join(headers), " ".join(" ".join(row.values()) for row in rows[:5])])
        scenario, hits = scenario_hint(case_text, config)
        candidates.append(
            {
                "case_id": case_id,
                "scenario": scenario,
                "scenario_keyword_hits_by_scene": hits,
                "misleader_type": "misleading_annotations",
                "plot_type": "line_chart",
                "figure_path": str(figure_path),
                "csv_path": str(csv_path),
                "html_path": str(html_path),
                "html_title": html_meta.get("title", ""),
                "html_h1": html_meta.get("h1", ""),
                "csv_headers": headers,
                "sample_rows": rows[:5],
                "entity_column": time_column,
                "metric_column": metric_column,
                "target_entity_column": time_column,
                "target_metric_columns": [metric_column],
                "time_column": time_column,
                "title_implied_trend": title_trend,
                "csv_true_trend": trend,
                "target_aware": True,
                "review_source": "supplemental_fixed_misleaders",
                "selection_source": "gpt-5.4-vision-title-misleading-line-chart",
                "scenario_fit_score": 3,
                "misleading_strength_score": 5 if title_trend != "unknown" and title_trend != trend.get("trend") else 2,
                "workflow_suitability_score": workflow_suitability(rows, time_column, metric_column),
            }
        )
    return candidates


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": candidate["case_id"],
        "scenario_hint": candidate["scenario"],
        "allowed_scenarios": sorted(SCENARIOS),
        "misleader_type": candidate["misleader_type"],
        "plot_type": candidate["plot_type"],
        "html_title": candidate.get("html_title", ""),
        "html_h1": candidate.get("html_h1", ""),
        "title_implied_trend": candidate.get("title_implied_trend"),
        "csv_true_trend_hint": candidate.get("csv_true_trend"),
        "csv_path": candidate["csv_path"],
        "figure_path": candidate["figure_path"],
        "csv_summary": csv_summary(Path(candidate["csv_path"])),
        "recommended_columns": {
            "time_column": candidate.get("time_column"),
            "metric_column": candidate.get("metric_column"),
        },
    }


def call_gpt(
    candidate: dict[str, Any],
    *,
    model: str,
    max_output_tokens: int,
    image_cache_dir: Path,
    vision_max_side: int,
    vision_quality: int,
    llm_retries: int,
    llm_retry_sleep: float,
    feedback: str = "",
) -> tuple[dict[str, Any], str, str]:
    os.environ.setdefault("LLM_BACKEND", "hexin_openai")
    os.environ.setdefault("HEXIN_MODEL", model)
    sys.path.insert(0, str(REPO_ROOT))
    from adversarial_pipeline.llm_client import complete_vision, make_client

    client = make_client()
    image_path = prepare_llm_image(
        Path(candidate["figure_path"]),
        image_cache_dir,
        max_side=vision_max_side,
        quality=vision_quality,
    )
    prompt = USER_PROMPT_TEMPLATE.format(
        candidate_json=json.dumps(compact_candidate(candidate), ensure_ascii=False, indent=2),
    )
    if feedback:
        prompt += "\n\nPrevious output failed these checks. Fix them and return JSON only:\n" + feedback
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
            return parse_model_json(raw), raw, str(image_path)
        except Exception as exc:
            last_error = exc
            if attempt < llm_retries:
                time.sleep(llm_retry_sleep * (attempt + 1))
    raise RuntimeError(f"GPT-5.4 title-line call failed after {llm_retries + 1} attempts: {last_error}")


def normalize_spec(spec: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    out = {key: spec.get(key) for key in REWRITE_FIELDS if key in spec}
    out["scenario"] = candidate["scenario"]
    out["misleader_type"] = "misleading_annotations"
    out["plot_type"] = "line_chart"
    out["keep"] = bool(spec.get("keep", True))
    out["reasoning_operation"] = "annotation_claim_verification"
    out["target_entity_column"] = out.get("target_entity_column") or candidate["time_column"]
    out["time_column"] = out.get("time_column") or candidate["time_column"]
    metrics = out.get("target_metric_columns") or [candidate["metric_column"]]
    if isinstance(metrics, str):
        metrics = [metrics]
    out["target_metric_columns"] = [str(metric) for metric in metrics if str(metric)]
    if not out["target_metric_columns"]:
        out["target_metric_columns"] = [candidate["metric_column"]]
    out["comparison_entities"] = []
    out["top_k"] = int(out.get("top_k") or 1)
    out["decision_rule"] = out.get("decision_rule") or "trend"
    out["threshold_value"] = None
    out["threshold_direction"] = None
    for score_key in ["scenario_fit_score", "misleading_alignment_score", "workflow_suitability_score"]:
        try:
            out[score_key] = int(out.get(score_key, candidate.get(score_key, 4)))
        except Exception:
            out[score_key] = 4
        out[score_key] = max(1, min(5, out[score_key]))
    return out


def option_text(action: str) -> str:
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


def validate_spec(spec: dict[str, Any], candidate: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []
    if not spec.get("keep"):
        errors.append("keep=false")
    if spec.get("reasoning_operation") != "annotation_claim_verification":
        errors.append("reasoning_operation must be annotation_claim_verification.")
    if spec.get("comparison_entities"):
        errors.append("comparison_entities must be empty so validation uses trend verification.")
    workflow = str(spec.get("workflow_instruction", ""))
    workflow_lower = workflow.lower()
    if "title" in workflow_lower or "claim" in workflow_lower:
        errors.append("workflow_instruction must not mention title or claim.")
    if "then" not in workflow_lower:
        errors.append("workflow_instruction must include downstream action using then.")
    if not any(term in workflow_lower for term in ["select", "choose", "submit", "save", "route", "open", "set", "click"]):
        errors.append("workflow_instruction must include a UI execution verb.")
    has_choice = (
        (" either " in f" {workflow_lower} " and " or " in f" {workflow_lower} ")
        or "choose between" in workflow_lower
        or "select between" in workflow_lower
        or "decide between" in workflow_lower
    )
    if not has_choice:
        errors.append("workflow_instruction must present at least two plausible UI outcomes.")
    if leaks_expected_action(workflow, str(spec.get("recommended_action_type", ""))):
        errors.append("workflow_instruction directly reveals recommended_action_type.")
    if not str(spec.get("misleading_mechanism", "")).strip():
        errors.append("missing misleading_mechanism.")
    if "title" not in str(spec.get("misleading_mechanism", "")).lower():
        errors.append("misleading_mechanism should explicitly describe title-driven misleading intent.")
    headers, rows = read_csv(Path(candidate["csv_path"]))
    validation = validate_task_spec(rows=rows, headers=headers, spec=spec)
    validation_payload = {
        "valid": validation.valid,
        "ground_truth_entity": validation.ground_truth_entity,
        "ground_truth_value": validation.ground_truth_value,
        "validation_error": validation.validation_error,
    }
    if not validation.valid:
        errors.append(f"CSV validation failed: {validation.validation_error}")
    return not errors, errors, validation_payload


def build_output(candidate: dict[str, Any], spec: dict[str, Any], raw: str, image_path: str, validation: dict[str, Any], elapsed: float) -> dict[str, Any]:
    metrics = spec.get("target_metric_columns") or []
    output = {
        **candidate,
        "keep": bool(spec.get("keep")),
        "scenario": spec.get("scenario") or candidate["scenario"],
        "misleading_mechanism": spec.get("misleading_mechanism", ""),
        "misleading_target": spec.get("misleading_target", ""),
        "expected_visual_trap": spec.get("expected_visual_trap", ""),
        "reasoning_operation": "annotation_claim_verification",
        "target_entity_column": spec.get("target_entity_column", ""),
        "target_metric_columns": metrics,
        "entity_column": spec.get("target_entity_column", ""),
        "metric_column": metrics[0] if metrics else "",
        "time_column": spec.get("time_column"),
        "comparison_entities": [],
        "top_k": spec.get("top_k", 1),
        "decision_rule": spec.get("decision_rule", "trend"),
        "threshold_value": None,
        "threshold_direction": None,
        "ground_truth_computation": spec.get("ground_truth_computation", ""),
        "web_action_goal": spec.get("web_action_goal", ""),
        "recommended_action_type": spec.get("recommended_action_type") or spec.get("web_action_goal", ""),
        "workflow_instruction": spec.get("workflow_instruction", ""),
        "operation_rationale": spec.get("operation_rationale", ""),
        "supplement_reason": spec.get("supplement_reason", ""),
        "review_source": "supplemental_fixed_misleaders",
        "scenario_fit_score": spec.get("scenario_fit_score", 1),
        "misleading_alignment_score": spec.get("misleading_alignment_score", 1),
        "workflow_suitability_score": spec.get("workflow_suitability_score", 1),
        "selection_source": "gpt-5.4-vision-title-misleading-line-chart",
        "risk_description": spec.get("misleading_mechanism", ""),
        "target_aware": True,
        "llm_model": candidate.get("llm_model", "gpt-5.4"),
        "llm_called": True,
        "llm_raw_text": raw,
        "llm_image_path": image_path,
        "llm_spec": spec,
        "validation_passed": bool(validation.get("valid")),
        "validation_error": validation.get("validation_error"),
        "ground_truth_entity": validation.get("ground_truth_entity"),
        "ground_truth_value": validation.get("ground_truth_value"),
        "elapsed_sec": round(elapsed, 3),
    }
    for transient in ["title_implied_trend", "csv_true_trend"]:
        output.pop(transient, None)
    return output


def evaluate_one(
    candidate: dict[str, Any],
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
    started = time.time()
    feedback = ""
    attempts: list[dict[str, Any]] = []
    last_raw = ""
    last_spec: dict[str, Any] | None = None
    last_image_path = ""
    last_validation = {"valid": False, "validation_error": "not evaluated"}
    last_errors: list[str] = []
    for _ in range(max(1, validation_retries + 1)):
        try:
            raw_spec, raw, image_path = call_gpt(
                candidate,
                model=model,
                max_output_tokens=max_output_tokens,
                image_cache_dir=image_cache_dir,
                vision_max_side=vision_max_side,
                vision_quality=vision_quality,
                llm_retries=llm_retries,
                llm_retry_sleep=llm_retry_sleep,
                feedback=feedback,
            )
            spec = normalize_spec(raw_spec, candidate)
            ok, errors, validation = validate_spec(spec, candidate)
            attempts.append({"raw_text": raw, "spec": spec, "errors": errors, "validation": validation})
            last_raw, last_spec, last_image_path, last_validation, last_errors = raw, spec, image_path, validation, errors
            if ok:
                output = build_output(candidate, spec, raw, image_path, validation, time.time() - started)
                output["llm_model"] = model
                return output
            feedback = "; ".join(errors)
        except Exception as exc:
            last_errors = [str(exc)]
            attempts.append({"raw_text": "", "spec": None, "errors": last_errors, "validation": None})
            feedback = str(exc)
    fallback_spec = last_spec or normalize_spec({"keep": False, "supplement_reason": "; ".join(last_errors)}, candidate)
    output = build_output(candidate, fallback_spec, last_raw, last_image_path, last_validation, time.time() - started)
    output["keep"] = False
    output["validation_passed"] = False
    output["validation_error"] = "; ".join(last_errors) or output.get("validation_error")
    output["llm_model"] = model
    output["llm_attempts"] = attempts
    return output


def select_top(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    valid = [
        row for row in rows
        if row.get("keep")
        and row.get("validation_passed")
        and row.get("reasoning_operation") == "annotation_claim_verification"
    ]
    valid.sort(
        key=lambda row: (
            int(row.get("misleading_alignment_score", 1)) * 4
            + int(row.get("workflow_suitability_score", 1)) * 3
            + int(row.get("scenario_fit_score", 1)) * 2,
            row.get("scenario", ""),
            row.get("case_id", ""),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    scenario_counts: Counter[str] = Counter()
    seen_titles: Counter[str] = Counter()
    remaining = valid[:]
    while remaining and len(selected) < count:
        remaining.sort(
            key=lambda row: (
                int(row.get("misleading_alignment_score", 1)) * 4
                + int(row.get("workflow_suitability_score", 1)) * 3
                + int(row.get("scenario_fit_score", 1)) * 2
                - scenario_counts[row.get("scenario", "")] * 0.75
                - seen_titles[str(row.get("html_h1", ""))] * 0.4,
                row.get("case_id", ""),
            ),
            reverse=True,
        )
        chosen = remaining.pop(0)
        selected.append(chosen)
        scenario_counts[chosen.get("scenario", "")] += 1
        seen_titles[str(chosen.get("html_h1", ""))] += 1
    return selected


def merge_candidate_rows(existing: list[dict[str, Any]], evaluated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row.get("case_id"): row for row in existing if row.get("case_id")}
    for row in evaluated:
        by_id[row["case_id"]] = row
    ordered_existing_ids = [row.get("case_id") for row in existing if row.get("case_id")]
    emitted: set[str] = set()
    merged: list[dict[str, Any]] = []
    for case_id in ordered_existing_ids:
        if case_id in by_id and case_id not in emitted:
            merged.append(by_id[case_id])
            emitted.add(case_id)
    for row in evaluated:
        if row["case_id"] not in emitted:
            merged.append(row)
            emitted.add(row["case_id"])
    return merged


def regression_errors(original_selected: list[dict[str, Any]], new_selected: list[dict[str, Any]], added: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if len(new_selected) != len(original_selected) + 10:
        errors.append(f"selected row count should be {len(original_selected) + 10}, got {len(new_selected)}")
    original_ids = {row["case_id"] for row in original_selected}
    added_ids = [row["case_id"] for row in added]
    if len(set(added_ids)) != len(added_ids):
        errors.append("duplicate added case_id.")
    if original_ids & set(added_ids):
        errors.append(f"added rows duplicate existing selected ids: {sorted(original_ids & set(added_ids))}")
    selected_ids = [row["case_id"] for row in new_selected]
    if len(set(selected_ids)) != len(selected_ids):
        errors.append("selected_cases contains duplicate case_id.")
    for row in added:
        case_id = row["case_id"]
        if row.get("misleader_type") != "misleading_annotations" or row.get("plot_type") != "line_chart":
            errors.append(f"{case_id}: added row is not misleading_annotations/line_chart.")
        if not row.get("validation_passed"):
            errors.append(f"{case_id}: validation_passed is false: {row.get('validation_error')}")
        workflow = str(row.get("workflow_instruction", "")).lower()
        if "title" in workflow or "claim" in workflow:
            errors.append(f"{case_id}: workflow mentions title/claim.")
        if leaks_expected_action(str(row.get("workflow_instruction", "")), str(row.get("recommended_action_type", ""))):
            errors.append(f"{case_id}: workflow leaks recommended_action_type.")
        headers, rows = read_csv(Path(row["csv_path"]))
        validation = validate_task_spec(rows=rows, headers=headers, spec=row)
        if not validation.valid:
            errors.append(f"{case_id}: ground truth not computable: {validation.validation_error}")
        elif str(row.get("ground_truth_entity")) != str(validation.ground_truth_entity):
            errors.append(f"{case_id}: ground_truth mismatch metadata={row.get('ground_truth_entity')} csv={validation.ground_truth_entity}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append 10 title-misleading line chart cases using GPT-5.4 vision.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reviewed-selection", type=Path, default=DEFAULT_REVIEWED_SELECTION)
    parser.add_argument("--reviewed-annotations", type=Path, default=DEFAULT_REVIEWED_ANNOTATIONS)
    parser.add_argument("--target-count", type=int, default=10)
    parser.add_argument("--model", type=str, default="gpt-5.4")
    parser.add_argument("--max-output-tokens", type=int, default=2600)
    parser.add_argument("--vision-max-side", type=int, default=1200)
    parser.add_argument("--vision-quality", type=int, default=82)
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--llm-retry-sleep", type=float, default=2.0)
    parser.add_argument("--validation-retries", type=int, default=1)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-calls", type=int, default=0, help="Optional debugging cap; 0 evaluates all non-selected line charts.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_path = args.out / "selected_cases.jsonl"
    candidate_path = args.out / "candidate_scores.jsonl"
    if not selected_path.exists() or not candidate_path.exists():
        raise SystemExit(f"Missing selected/candidate files under {args.out}")
    selected_rows = load_jsonl(selected_path)
    candidate_rows = load_jsonl(candidate_path)
    if len(selected_rows) != 100:
        raise SystemExit(f"Expected current selected_cases to have 100 rows before append, got {len(selected_rows)}")

    selected_ids = {row["case_id"] for row in selected_rows}
    config = load_json(CONFIG_PATH)
    candidates = build_candidates(args.dataset, config, selected_ids)
    if args.max_calls:
        candidates = candidates[:args.max_calls]
    if len(candidates) < args.target_count:
        raise SystemExit(f"Not enough non-selected line_chart candidates: {len(candidates)}")

    backup_path = backup_existing_outputs(args.out)
    image_cache_dir = args.out / ".image_cache"
    evaluated: list[dict[str, Any]] = []
    processed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                evaluate_one,
                candidate,
                model=args.model,
                max_output_tokens=args.max_output_tokens,
                image_cache_dir=image_cache_dir,
                vision_max_side=args.vision_max_side,
                vision_quality=args.vision_quality,
                llm_retries=args.llm_retries,
                llm_retry_sleep=args.llm_retry_sleep,
                validation_retries=args.validation_retries,
            ): candidate
            for candidate in candidates
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {**candidate, "llm_called": True, "llm_model": args.model, "keep": False, "validation_passed": False, "validation_error": str(exc)}
            evaluated.append(row)
            processed += 1
            print(
                json.dumps(
                    {
                        "processed": processed,
                        "case_id": candidate["case_id"],
                        "keep": row.get("keep"),
                        "valid": row.get("validation_passed"),
                        "gt": row.get("ground_truth_entity"),
                        "error": row.get("validation_error"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    added = select_top(evaluated, args.target_count)
    if len(added) < args.target_count:
        raise SystemExit(f"Only {len(added)} valid title-misleading line charts passed; need {args.target_count}.")
    new_selected = selected_rows + added
    errors = regression_errors(selected_rows, new_selected, added)
    if errors:
        raise SystemExit("Regression check failed before writing:\n" + "\n".join(errors))

    merged_candidates = merge_candidate_rows(candidate_rows, evaluated)
    write_jsonl_atomic(selected_path, new_selected)
    write_jsonl_atomic(candidate_path, merged_candidates)

    log_path = args.out / "line_chart_title_rewrite_log.jsonl"
    log_rows = [
        {
            "case_id": row["case_id"],
            "keep": row.get("keep"),
            "validation_passed": row.get("validation_passed"),
            "validation_error": row.get("validation_error"),
            "ground_truth_entity": row.get("ground_truth_entity"),
            "llm_raw_text": row.get("llm_raw_text", ""),
            "llm_spec": row.get("llm_spec"),
        }
        for row in evaluated
    ]
    write_jsonl_atomic(log_path, log_rows)

    suitable_cases = load_suitable_cases(args.reviewed_selection, args.reviewed_annotations)
    notes = [
        f"Previous supplemental output was backed up to {backup_path}.",
        f"Title-misleading line-chart candidates evaluated with GPT-5.4: {len(evaluated)}.",
        f"Title-misleading line-chart rows appended: {len(added)}.",
        f"Title-misleading line-chart GPT log: {log_path}.",
    ]
    (args.out / "selection_summary.md.tmp").write_text(
        summary(new_selected, merged_candidates, suitable_cases, notes),
        encoding="utf-8",
    )
    (args.out / "selection_summary.md.tmp").replace(args.out / "selection_summary.md")

    print(
        json.dumps(
            {
                "selected_rows": len(new_selected),
                "candidate_rows": len(merged_candidates),
                "evaluated": len(evaluated),
                "added": [row["case_id"] for row in added],
                "log": str(log_path),
                "backup": backup_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
