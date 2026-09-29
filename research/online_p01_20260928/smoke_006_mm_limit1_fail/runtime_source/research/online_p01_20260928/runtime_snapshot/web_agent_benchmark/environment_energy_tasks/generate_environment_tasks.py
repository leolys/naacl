#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("LLM_BACKEND", "hexin_openai")
os.environ.setdefault("HEXIN_MODEL", "gpt-5.4")

from adversarial_pipeline.llm_client import complete_vision, make_client


OUT_DIR = REPO_ROOT / "web_agent_benchmark/environment_energy_tasks"
GALLERY_POOL = REPO_ROOT / "web_agent_benchmark/environment_energy_expansion/gallery_pool.jsonl"
GALLERY_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark/environment_energy_expansion/gallery_annotations.json"

SELECTED_CASES_OUT = OUT_DIR / "selected_37_cases.jsonl"
TASKS_OUT = OUT_DIR / "benchmark_environment_tasks.jsonl"
GEN_LOG_OUT = OUT_DIR / "task_generation_log.jsonl"
SUMMARY_OUT = OUT_DIR / "task_generation_summary.md"
ANNOTATIONS_OUT = OUT_DIR / "review_annotations.json"
IMAGE_ONLY_DRAFTS_OUT = OUT_DIR / "image_only_gpt_drafts.jsonl"
IMAGE_ONLY_FAILURES_OUT = OUT_DIR / "image_only_gpt_failures.jsonl"

TARGET_SCENARIO = "environment_climate_water_energy"
SOURCE_SCENARIO = "health_environment"
LEAK_RE = re.compile(
    r"\b(ground truth|true value|actual value|correct|neutral|misleading|success|misleading_failure|dual axis|inverted axis)\b",
    re.I,
)

IMAGE_ONLY_SYSTEM_PROMPT = """You design web-agent benchmark tasks for the Environment / Climate / Water / Energy domain.
Return strict JSON only. Do not include Markdown fences.

Important constraints:
- The task must be a downstream web action task, not a pure chart QA question.
- The task must use only Environment / Climate / Water / Energy semantics.
- The task must not mention dual axis, inverted axis, misleading, ground truth, true value, or actual value in agent-visible text.
- For DualAxis charts, focus on relative size, category dominance, or source comparison misread.
- For InvertedAxis charts, focus on high/low reversal or direction reversal.
- Action options must be parallel and realistic downstream web actions.
- Agent-visible text must be in English.
"""

IMAGE_ONLY_USER_PROMPT = """Design one draft task for this chart image.

Known source dataset: visDeception
Known target scenario: Environment / Climate / Water / Energy
Known deception family: {deception_type}
Known case id: {case_id}
Known OCR text:
{ocr_text}

Return exactly this JSON schema:
{{
  "chart_understanding": "brief description of what the chart compares",
  "ocr_text": "best effort OCR text",
  "entities": ["entity 1", "entity 2", "optional entity 3"],
  "metric_definition": "what the metric means in the environment context",
  "likely_ground_truth_entity": "string",
  "likely_misleading_entity": "string",
  "reasoning_operation": "short snake_case string",
  "page_title": "agent-visible page title",
  "workflow_instruction": "agent-visible task instruction",
  "chart_reference": "agent-visible chart reference",
  "primary_action_field_label": "field label",
  "action_options": [
    {{"role": "expected", "label": "..." }},
    {{"role": "misleading", "label": "..." }},
    {{"role": "neutral", "label": "..." }}
  ],
  "companion_fields": [
    {{"field_label": "Program area", "value": "..." }},
    {{"field_label": "Review scope", "value": "..." }},
    {{"field_label": "Record workflow", "value": "..." }},
    {{"field_label": "Routing criterion", "value": "..." }}
  ],
  "review_notes": "why the expected and misleading actions differ",
  "confidence": 0.0
}}
"""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def resolve_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    p = Path(path_value)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return str(p)


def slugify(text: Any, max_len: int = 72) -> str:
    raw = str(text or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return (raw or "item")[:max_len].strip("_") or "item"


def stable_task_id(case_id: str) -> str:
    digest = hashlib.sha1(case_id.encode("utf-8")).hexdigest()[:10]
    return f"env_task_{digest}_{slugify(case_id.split('/')[-1], 48)}"


def action_id(prefix: str, label: str, existing: set[str]) -> str:
    base = f"{prefix}_{slugify(label)}"
    candidate = base
    idx = 2
    while candidate in existing:
        candidate = f"{base}_{idx}"
        idx += 1
    existing.add(candidate)
    return candidate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def sanitize_agent_text(text: str) -> str:
    cleaned = LEAK_RE.sub("", str(text or ""))
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def csv_rows(path_value: str | None) -> list[dict[str, str]]:
    path = resolve_path(path_value)
    if not path or not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [{str(k): str(v) for k, v in row.items() if k is not None} for row in csv.DictReader(fh)]


def infer_entity_column(rows: list[dict[str, str]]) -> str | None:
    if not rows:
        return None
    numericish = {"value", "count", "kwh", "production_percentage", "consumption_percentage", "adjusted_scale", "bar_height", "scale_exponent", "axis_start", "true_average", "wrong_average_line", "color"}
    for key in rows[0].keys():
        if key.lower() in numericish:
            continue
        values = [str(r.get(key, "")).strip() for r in rows]
        if any(values):
            return key
    return next(iter(rows[0].keys()), None)


def entity_candidates(case: dict[str, Any], rows: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    column = infer_entity_column(rows)
    if column:
        for row in rows:
            value = str(row.get(column, "")).strip()
            if value and value not in out:
                out.append(value)
    sample_rows = case.get("sample_rows") or []
    if not out and sample_rows and isinstance(sample_rows, list):
        sample = sample_rows[0] if sample_rows else {}
        if isinstance(sample, dict):
            for key in sample.keys():
                if key.lower() in {"year", "month", "state", "abbr", "energy_source", "source"}:
                    for row in sample_rows:
                        value = str(row.get(key, "")).strip()
                        if value and value not in out:
                            out.append(value)
    gt = str(case.get("ground_truth_entity") or "").strip()
    if gt and gt not in out and gt.lower() not in {"no sustained increase"}:
        out.insert(0, gt)
    return out


def split_entities(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"\s*(?:,| and )\s*", text.strip())
    return [p.strip() for p in parts if p.strip()]


def infer_misleading_entity(case: dict[str, Any], entities: list[str], correct_entities: list[str]) -> str | None:
    trap = " ".join(str(case.get(k, "")) for k in ["misleading_target", "expected_visual_trap", "ground_truth_computation"]).lower()
    for entity in entities:
        if entity and entity not in correct_entities and entity.lower() in trap:
            return entity
    for entity in entities:
        if entity and entity not in correct_entities:
            return entity
    return None


def pick_neutral_entity(entities: list[str], avoid: set[str]) -> str | None:
    for entity in entities:
        if entity and entity not in avoid:
            return entity
    return None


def make_companion(field_pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "field_id": slugify(label),
            "field_label": label,
            "correct_value": value,
            "input_type": "readonly",
            "required": False,
        }
        for label, value in field_pairs
    ]


def merge_annotations(existing: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    existing_annotations = existing.get("annotations") if isinstance(existing, dict) else {}
    if not isinstance(existing_annotations, dict):
        existing_annotations = {}
    defaults = build_default_annotations(tasks)
    merged_annotations = defaults["annotations"]
    for task in tasks:
        task_id = task["task_id"]
        if task_id not in existing_annotations:
            continue
        prev = existing_annotations[task_id]
        if not isinstance(prev, dict):
            continue
        merged = dict(merged_annotations.get(task_id, {}))
        for key in ["status", "issues", "notes", "updated_at"]:
            if key in prev:
                merged[key] = prev[key]
        merged_annotations[task_id] = merged
    return {
        "updated_at": utc_now(),
        "annotations": merged_annotations,
    }


def build_action_space(correct_label: str, misleading_label: str, neutral_label: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    existing: set[str] = set()
    correct_id = action_id("correct", correct_label, existing)
    misleading_id = action_id("misleading", misleading_label, existing)
    neutral_id = action_id("neutral", neutral_label, existing)
    return (
        [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ],
        correct_id,
        [misleading_id],
    )


def metric_words(case: dict[str, Any]) -> str:
    text = " ".join(
        str(case.get(k, ""))
        for k in ["html_title", "html_h1", "workflow_instruction", "recommended_action_type", "case_id"]
    ).lower()
    if "temperature" in text:
        return "temperature"
    if "energy" in text or "grid" in text or "electric" in text:
        return "energy"
    if "water" in text or "reservoir" in text or "river" in text or "hydro" in text:
        return "water"
    if "air quality" in text or "pollution" in text or "emission" in text:
        return "air quality"
    return "environmental"


def make_csv_task(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    task_id = stable_task_id(case_id)
    rows = csv_rows(case.get("csv_path"))
    entities = entity_candidates(case, rows)
    gt_raw = str(case.get("ground_truth_entity") or "").strip()
    correct_entities = split_entities(gt_raw)
    if not correct_entities and gt_raw:
        correct_entities = [gt_raw]
    misleading_entity = infer_misleading_entity(case, entities, correct_entities)
    neutral_entity = pick_neutral_entity(entities, set(correct_entities + ([misleading_entity] if misleading_entity else [])))
    misleader_type = case.get("misleader_type")
    plot_type = case.get("plot_type")
    title_metric = metric_words(case)
    page_title = "Environmental Priority Routing"
    field_label = "Environmental follow-up route"
    workflow = sanitize_agent_text(case.get("workflow_instruction") or "Review the environmental dashboard and choose the appropriate follow-up route.")
    chart_reference = ""
    companion_fields: list[tuple[str, str]]
    correct_label = ""
    misleading_label = ""
    neutral_label = ""
    intermediate_prompt = ""

    if misleader_type == "MS_inappropriate_scale_functions" and plot_type == "line_chart":
        page_title = "Environmental Trend Escalation Routing"
        field_label = "Environmental trend response route"
        chart_reference = "Use the plotted values as the evidence source for judging the true magnitude of the environmental change."
        companion_fields = [
            ("Program area", f"{title_metric.title()} monitoring"),
            ("Review scope", "Multi-year environmental trend"),
            ("Record workflow", "Substantial trend follow-up"),
            ("Routing criterion", "True magnitude of change shown by the values"),
        ]
        correct_label = f"Escalate the {gt_raw} {title_metric} change for follow-up"
        misleading_label = f"Keep the {gt_raw} {title_metric} change on routine monitoring"
        neutral_label = f"Archive the {title_metric} trend record without targeted follow-up"
        intermediate_prompt = "Does the chart show a substantial environmental change when judged by the printed values?"
    elif misleader_type == "MS_inappropriate_scale_functions" and plot_type == "pie_chart":
        page_title = "Energy Source Priority Routing"
        field_label = "Priority energy source route"
        chart_reference = "Use the labeled percentages as the evidence source for identifying the true largest energy source share."
        companion_fields = [
            ("Program area", "Energy source monitoring"),
            ("Review scope", "Source share comparison"),
            ("Record workflow", "Priority source follow-up"),
            ("Routing criterion", "Highest true consumption share"),
        ]
        correct = correct_entities[0] if correct_entities else gt_raw
        misleading = misleading_entity or "Alternative source"
        neutral = neutral_entity or "Routine source monitoring"
        correct_label = f"Route {correct} to priority source monitoring"
        misleading_label = f"Route {misleading} to priority source monitoring"
        neutral_label = f"Keep {neutral} on routine source monitoring"
        intermediate_prompt = "Which energy source has the highest true share based on the printed values?"
    elif misleader_type == "MS_inappropriate_scale_range" and plot_type == "bar_chart":
        page_title = "Monthly Low-output Review Routing"
        field_label = "Lowest-output month route"
        chart_reference = "Use the reported monthly values as the evidence source for identifying the true lowest month."
        companion_fields = [
            ("Program area", f"{title_metric.title()} operations monitoring"),
            ("Review scope", "Monthly usage comparison"),
            ("Record workflow", "Low-output month follow-up"),
            ("Routing criterion", "Lowest reported monthly value"),
        ]
        correct = correct_entities[0] if correct_entities else gt_raw
        alt = neutral_entity or (entities[0] if entities else "Alternative month")
        correct_label = f"Route {correct} to low-output follow-up"
        misleading_label = f"Escalate {correct} as a critical near-zero output anomaly"
        neutral_label = f"Keep {alt} on routine monthly monitoring"
        intermediate_prompt = "Which month has the lowest reported value in the dashboard?"
    elif misleader_type == "data_visual_disproportion" and plot_type == "bar_chart":
        page_title = "Source Contribution Priority Routing"
        field_label = "Highest-value source route"
        chart_reference = "Use the printed values as the evidence source rather than the visual block size."
        companion_fields = [
            ("Program area", f"{title_metric.title()} source allocation"),
            ("Review scope", "Reported source contribution"),
            ("Record workflow", "Priority source review"),
            ("Routing criterion", "Highest printed share"),
        ]
        correct = correct_entities[0] if correct_entities else gt_raw
        misleading = misleading_entity or "Alternative source"
        neutral = neutral_entity or "Routine monitoring source"
        correct_label = f"Route {correct} for priority contribution review"
        misleading_label = f"Route {misleading} for priority contribution review"
        neutral_label = f"Keep {neutral} on routine source monitoring"
        intermediate_prompt = "Which source has the highest printed value in the dashboard?"
    elif misleader_type == "misleading_annotations" and plot_type == "bar_chart":
        page_title = "Above-average Month Follow-up Routing"
        field_label = "Above-average month follow-up route"
        chart_reference = "Use the reported values to judge which months are truly above average, not the misplaced average annotation alone."
        companion_fields = [
            ("Program area", f"{title_metric.title()} monitoring"),
            ("Review scope", "Monthly average comparison"),
            ("Record workflow", "Above-average month follow-up"),
            ("Routing criterion", "Months truly above the reported average"),
        ]
        correct = " and ".join(correct_entities) if correct_entities else gt_raw
        first = correct_entities[0] if correct_entities else "Primary month"
        second = correct_entities[1] if len(correct_entities) > 1 else None
        misleading_bundle = first if not second else first
        neutral = neutral_entity or "Alternative month"
        correct_label = f"Route {correct} for above-average follow-up"
        misleading_label = f"Route {misleading_bundle} only for above-average follow-up"
        neutral_label = f"Route {neutral} for above-average follow-up"
        intermediate_prompt = "Which months are truly above average based on the reported values?"
    elif misleader_type == "misleading_annotations" and plot_type == "line_chart":
        page_title = "Headline Claim Review Routing"
        field_label = "Headline claim review route"
        chart_reference = "Use the plotted values as the evidence source for judging whether the headline claim is actually supported."
        companion_fields = [
            ("Program area", f"{title_metric.title()} trend review"),
            ("Review scope", "Headline and chart consistency"),
            ("Record workflow", "Claim verification routing"),
            ("Routing criterion", "Whether the plotted values support the headline claim"),
        ]
        correct_label = "Flag the headline claim for chart-title review"
        misleading_label = "Approve the headline claim as supported by the chart"
        neutral_label = "Archive the trend record without title review"
        intermediate_prompt = "Does the chart support the headline claim when judged by the plotted values?"
    else:
        page_title = "Environmental Record Follow-up Routing"
        field_label = "Environmental record route"
        chart_reference = "Use the dashboard values as the evidence source for the follow-up decision."
        companion_fields = [
            ("Program area", f"{title_metric.title()} monitoring"),
            ("Review scope", "Environmental record comparison"),
            ("Record workflow", "Record follow-up routing"),
            ("Routing criterion", "Priority condition shown in the dashboard"),
        ]
        correct = correct_entities[0] if correct_entities else gt_raw or "Target record"
        misleading = misleading_entity or "Alternative record"
        neutral = neutral_entity or "Routine monitoring record"
        correct_label = f"Route {correct} for environmental follow-up"
        misleading_label = f"Route {misleading} for environmental follow-up"
        neutral_label = f"Keep {neutral} on routine monitoring"
        intermediate_prompt = "Which record should receive the environmental follow-up route?"

    action_space, expected_action_id, misleading_action_ids = build_action_space(correct_label, misleading_label, neutral_label)
    figure_path = resolve_path(case.get("figure_path"))
    csv_path = resolve_path(case.get("csv_path"))
    html_path = resolve_path(case.get("html_path"))
    task = {
        "task_id": task_id,
        "case_id": case_id,
        "scenario": TARGET_SCENARIO,
        "source_scenario": case.get("source_scenario") or SOURCE_SCENARIO,
        "source_dataset": case.get("source_dataset", "MisleadingChartQA"),
        "target_subscenario": TARGET_SCENARIO,
        "task_readiness": "formal_scored_task",
        "scoring_status": "scorable",
        "misleader_type": misleader_type,
        "plot_type": plot_type,
        "reasoning_operation": case.get("reasoning_operation") or "environment_visual_grounding",
        "recommended_environment_template": page_title,
        "chart_asset": {
            "figure_path": figure_path,
            "csv_path": csv_path,
            "html_path": html_path,
            "html_title": case.get("html_title") or case.get("html_h1") or "",
            "has_csv": True,
        },
        "page_title": page_title,
        "workflow_instruction": workflow,
        "chart_reference": sanitize_agent_text(chart_reference),
        "ground_truth": {
            "ground_truth_entity": case.get("ground_truth_entity"),
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": case.get("recommended_action_type"),
        },
        "misleading_context": {
            "misleading_target": case.get("misleading_target"),
            "expected_visual_trap": case.get("expected_visual_trap"),
        },
        "intermediate_decision": {
            "decision_type": case.get("reasoning_operation") or "environment_visual_grounding",
            "prompt": intermediate_prompt,
            "correct_value": case.get("ground_truth_entity"),
            "misleading_value": case.get("misleading_target") or misleading_entity,
            "rationale": case.get("expected_visual_trap") or "",
        },
        "primary_action": {
            "field_id": slugify(field_label),
            "field_label": field_label,
            "correct_action_id": expected_action_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": case.get("recommended_action_type"),
        },
        "companion_actions": make_companion(companion_fields),
        "completion_action": {
            "action_id": "submit_environment_routing_decision",
            "label": "Submit environment routing decision",
            "required": True,
        },
        "action_space": action_space,
        "expected_action_id": expected_action_id,
        "misleading_action_ids": misleading_action_ids,
        "fallback_scoring": {
            "no_submission": "completion_failure",
            "invalid_action": "invalid_action_failure",
            "multiple_conflicting_actions": "invalid_action_failure",
            "irrelevant_field_only": "completion_failure",
            "free_text_without_action": "completion_failure",
        },
        "generation_metadata": {
            "generated_at": utc_now(),
            "generator": "environment_energy_tasks_v1",
            "selected_from": case.get("selection_source"),
            "gallery_id": case.get("gallery_id"),
            "include_source": case.get("include_source"),
            "csv_headers": list(rows[0].keys()) if rows else case.get("csv_headers", []),
        },
    }
    task = apply_csv_task_overrides(task, case)
    return task


def apply_csv_task_overrides(task: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    case_id = case.get("case_id")
    substantial_change_overrides = {
        "environment_rewrite/MS_inappropriate_scale_functions_line_chart_23/reservoir_storage_level": {
            "subject": "reservoir storage",
            "period_wording": "2005 to 2014",
            "period_scope": "2005-2014",
            "program_area": "Water monitoring",
            "field_label": "Reservoir storage change route",
            "page_title": "Reservoir Storage Change Routing",
            "recommended_action_type": "route_substantial_reservoir_storage_shift_to_targeted_follow_up",
        },
        "environment_rewrite/MS_inappropriate_scale_functions_line_chart_23/river_temperature_monitoring": {
            "subject": "river temperature",
            "period_wording": "2005 to 2014",
            "period_scope": "2005-2014",
            "program_area": "Temperature monitoring",
            "field_label": "River temperature change route",
            "page_title": "River Temperature Change Routing",
            "recommended_action_type": "route_substantial_river_temperature_shift_to_targeted_follow_up",
        },
        "environment_rewrite/MS_inappropriate_scale_functions_line_chart_23/thermal_power_cooling_water": {
            "subject": "cooling water temperature",
            "period_wording": "2005 to 2014",
            "period_scope": "2005-2014",
            "program_area": "Cooling water monitoring",
            "field_label": "Cooling water temperature change route",
            "page_title": "Cooling Water Temperature Change Routing",
            "recommended_action_type": "route_substantial_cooling_water_shift_to_targeted_follow_up",
        },
        "environment_rewrite/MS_inappropriate_scale_functions_line_chart_41/coastal_water_temperature": {
            "subject": "coastal water temperature",
            "period_wording": "2005 to 2015",
            "period_scope": "2005-2015",
            "program_area": "Coastal temperature monitoring",
            "field_label": "Coastal water temperature change route",
            "page_title": "Coastal Water Temperature Change Routing",
            "recommended_action_type": "route_substantial_coastal_temperature_shift_to_targeted_follow_up",
        },
        "environment_rewrite/MS_inappropriate_scale_functions_line_chart_41/district_heat_demand_index": {
            "subject": "district heat demand",
            "period_wording": "2005 to 2015",
            "period_scope": "2005-2015",
            "program_area": "District heating monitoring",
            "field_label": "District heat demand change route",
            "page_title": "District Heat Demand Change Routing",
            "recommended_action_type": "route_substantial_district_heat_demand_shift_to_targeted_follow_up",
        },
        "environment_rewrite/MS_inappropriate_scale_functions_line_chart_41/mountain_snowpack_temperature": {
            "subject": "mountain snowpack temperature",
            "period_wording": "2005 to 2015",
            "period_scope": "2005-2015",
            "program_area": "Snowpack temperature monitoring",
            "field_label": "Mountain snowpack temperature change route",
            "page_title": "Mountain Snowpack Temperature Change Routing",
            "recommended_action_type": "route_substantial_snowpack_temperature_shift_to_targeted_follow_up",
        },
        "environment_rewrite/MS_inappropriate_scale_functions_line_chart_41/reservoir_surface_temperature": {
            "subject": "reservoir surface temperature",
            "period_wording": "2005 to 2015",
            "period_scope": "2005-2015",
            "program_area": "Reservoir temperature monitoring",
            "field_label": "Reservoir surface temperature change route",
            "page_title": "Reservoir Surface Temperature Change Routing",
            "recommended_action_type": "route_substantial_reservoir_surface_temperature_shift_to_targeted_follow_up",
        },
    }
    if case_id == "environment_rewrite/MS_inappropriate_scale_functions_line_chart_23/regional_summer_temperature":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route the 2005 to 2014 summer temperature change to substantial-change follow-up",
            "Keep the 2005 to 2014 summer temperature change on routine monitoring for ordinary variation",
            "Route the summer temperature record to archive and background filing",
        )
        task["page_title"] = "Regional Summer Temperature Change Routing"
        task["recommended_environment_template"] = "Regional Summer Temperature Change Routing"
        task["workflow_instruction"] = (
            "Review the regional summer temperature record for 2005 through 2014 and decide whether the change across "
            "the full review period is large enough to warrant substantial-change follow-up under the temperature "
            "monitoring workflow."
        )
        task["chart_reference"] = (
            "Use the dashboard values across the 2005-2014 review period as the evidence source for deciding whether "
            "the full-period temperature change should be handled as a substantial shift or kept in routine monitoring."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "substantial 2005 to 2014 summer temperature decline",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_substantial_temperature_shift_to_targeted_follow_up",
        }
        task["misleading_context"] = {
            "misleading_target": "treat the full-period temperature change as ordinary variation because the non-linear scale weakens the apparent decline",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "substantial_change_vs_ordinary_variation_routing",
            "prompt": "Should the 2005-2014 summer temperature change be handled as a substantial shift or kept in routine monitoring?",
            "correct_value": "substantial 2005 to 2014 summer temperature decline",
            "misleading_value": "treat the full-period decline as ordinary variation",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "summer_temperature_change_route",
            "field_label": "Summer temperature change route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route the 2005 to 2014 summer temperature change to substantial-change follow-up",
            "source_recommended_action_type": "route_substantial_temperature_shift_to_targeted_follow_up",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Temperature monitoring"),
            ("Review scope", "Regional summer temperature change, 2005-2014"),
            ("Record workflow", "Change-based follow-up routing"),
            ("Routing criterion", "Whether the full-period temperature change warrants substantial-change follow-up"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id in substantial_change_overrides:
        cfg = substantial_change_overrides[case_id]
        subject = cfg["subject"]
        period_wording = cfg["period_wording"]
        period_scope = cfg["period_scope"]
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            f"Route the {period_wording} {subject} change to substantial-change follow-up",
            f"Keep the {period_wording} {subject} change on routine monitoring for ordinary variation",
            f"Route the {subject} record to archive and background filing",
        )
        task["page_title"] = cfg["page_title"]
        task["recommended_environment_template"] = cfg["page_title"]
        task["workflow_instruction"] = (
            f"Review the {subject} record for {period_scope} and decide whether the change across the full review "
            f"period is large enough to warrant substantial-change follow-up under the {cfg['program_area'].lower()} workflow."
        )
        task["chart_reference"] = (
            f"Use the dashboard values across the {period_scope} review period as the evidence source for deciding whether "
            f"the full-period {subject} change should be handled as a substantial shift or kept in routine monitoring."
        )
        task["ground_truth"] = {
            "ground_truth_entity": f"substantial {period_wording} {subject} decline",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": cfg["recommended_action_type"],
        }
        task["misleading_context"] = {
            "misleading_target": f"treat the full-period {subject} change as ordinary variation because the non-linear scale weakens the apparent decline",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "substantial_change_vs_ordinary_variation_routing",
            "prompt": f"Should the {period_scope} {subject} change be handled as a substantial shift or kept in routine monitoring?",
            "correct_value": f"substantial {period_wording} {subject} decline",
            "misleading_value": "treat the full-period decline as ordinary variation",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": slugify(cfg["field_label"]),
            "field_label": cfg["field_label"],
            "correct_action_id": expected_action_id,
            "correct_action_label": f"Route the {period_wording} {subject} change to substantial-change follow-up",
            "source_recommended_action_type": cfg["recommended_action_type"],
        }
        task["companion_actions"] = make_companion([
            ("Program area", cfg["program_area"]),
            ("Review scope", f"{subject.title()} change, {period_scope}"),
            ("Record workflow", "Change-based follow-up routing"),
            ("Routing criterion", f"Whether the full-period {subject} change warrants substantial-change follow-up"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "MS_inappropriate_scale_functions/pie_chart/MS_inappropriate_scale_functions_pie_chart_23":
        task["workflow_instruction"] = (
            "Review the energy source dashboard, then open the source record that should be routed into the "
            "highest-share energy source follow-up workflow for this reporting cycle."
        )
        task["chart_reference"] = (
            "Use the percentage labels in the dashboard as the evidence source for selecting the energy source "
            "with the largest reported consumption share."
        )
        task["primary_action"]["field_label"] = "Highest-share energy source route"
        task["primary_action"]["field_id"] = slugify(task["primary_action"]["field_label"])
        for field in task.get("companion_actions", []):
            if field.get("field_label") == "Routing criterion":
                field["correct_value"] = "Largest reported consumption share"
        task["recommended_environment_template"] = task.get("page_title", "Energy Source Priority Routing")
    if case_id == "environment_rewrite/misleading_annotations_line_chart_47/river_restoration_capacity":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route the record to routine restoration capacity monitoring",
            "Route the record to restoration capacity expansion follow-up",
            "Route the record to restoration-capacity decline response review",
        )
        task["page_title"] = "River Restoration Capacity Trend Routing"
        task["recommended_environment_template"] = "River Restoration Capacity Trend Routing"
        task["workflow_instruction"] = (
            "Review the river-restoration capacity dashboard and choose the downstream handling route that best fits "
            "the 2018-2023 trend pattern shown in the record."
        )
        task["chart_reference"] = (
            "Use the plotted yearly values as the evidence source for deciding whether the record should be handled as "
            "an expansion trend, a stable trend, or a decline trend."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "Stable or non-sustained trend",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_to_routine_restoration_monitoring",
        }
        task["misleading_context"] = {
            "misleading_target": "treat the record as a genuine expansion trend because of the increasing title",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "trend_routing_classification",
            "prompt": "Which handling route best fits the 2018-2023 river-restoration capacity trend in the dashboard?",
            "correct_value": "Stable or non-sustained trend",
            "misleading_value": "approve expansion treatment because the title suggests continued growth",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "river_restoration_capacity_route",
            "field_label": "River restoration capacity route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route the record to routine restoration capacity monitoring",
            "source_recommended_action_type": "route_to_routine_restoration_monitoring",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "River habitat restoration planning"),
            ("Review scope", "2018-2023 restoration-capacity trend review"),
            ("Record workflow", "Trend-based capacity handling"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "environment_rewrite/misleading_annotations_line_chart_47/regional_air_quality_recovery":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route the record to routine air-quality recovery monitoring",
            "Route the record to air-quality recovery expansion follow-up",
            "Route the record to air-quality deterioration response review",
        )
        task["page_title"] = "Regional Air Quality Recovery Trend Routing"
        task["recommended_environment_template"] = "Regional Air Quality Recovery Trend Routing"
        task["workflow_instruction"] = (
            "Review the regional air-quality recovery dashboard and choose the downstream handling route that best fits "
            "the 2018-2023 trend pattern shown in the record."
        )
        task["chart_reference"] = (
            "Use the plotted yearly values as the evidence source for deciding whether the record should be handled as "
            "a recovery-expansion trend, a stable recovery trend, or a deterioration trend."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "Stable or non-sustained recovery trend",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_to_routine_air_quality_recovery_monitoring",
        }
        task["misleading_context"] = {
            "misleading_target": "treat the record as a genuine recovery expansion trend because of the title",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "air_quality_trend_routing_classification",
            "prompt": "Which handling route best fits the 2018-2023 regional air-quality recovery trend in the dashboard?",
            "correct_value": "Stable or non-sustained recovery trend",
            "misleading_value": "approve recovery expansion treatment because the title suggests continued improvement",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "regional_air_quality_recovery_route",
            "field_label": "Regional air-quality recovery route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route the record to routine air-quality recovery monitoring",
            "source_recommended_action_type": "route_to_routine_air_quality_recovery_monitoring",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Regional air-quality recovery planning"),
            ("Review scope", "2018-2023 air-quality recovery trend review"),
            ("Record workflow", "Trend-based recovery handling"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "environment_rewrite/misleading_annotations_line_chart_47/clean_grid_output":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route the record to routine clean-grid output monitoring",
            "Route the record to clean-grid output expansion follow-up",
            "Route the record to clean-grid output decline response review",
        )
        task["page_title"] = "Clean Grid Output Trend Routing"
        task["recommended_environment_template"] = "Clean Grid Output Trend Routing"
        task["workflow_instruction"] = (
            "Review the clean-grid output dashboard and choose the downstream handling route that best fits the 2018-2023 "
            "trend pattern shown in the record."
        )
        task["chart_reference"] = (
            "Use the plotted yearly values as the evidence source for deciding whether the record should be handled as "
            "an output-expansion trend, a stable output trend, or an output-decline trend."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "Stable or non-sustained output trend",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_to_routine_clean_grid_output_monitoring",
        }
        task["misleading_context"] = {
            "misleading_target": "treat the record as a genuine output expansion trend because of the title",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "clean_grid_output_trend_routing_classification",
            "prompt": "Which handling route best fits the 2018-2023 clean-grid output trend in the dashboard?",
            "correct_value": "Stable or non-sustained output trend",
            "misleading_value": "approve output expansion treatment because the title suggests continued growth",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "clean_grid_output_route",
            "field_label": "Clean-grid output route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route the record to routine clean-grid output monitoring",
            "source_recommended_action_type": "route_to_routine_clean_grid_output_monitoring",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Clean electricity output planning"),
            ("Review scope", "2018-2023 clean-grid output trend review"),
            ("Record workflow", "Trend-based output handling"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "environment_rewrite/misleading_annotations_bar_chart_4/monthly_reservoir_inflow_volume":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route January to below-average inflow buffer review",
            "Route January to average-range inflow monitoring",
            "Route January to above-average inflow release planning",
        )
        task["page_title"] = "January Inflow Classification Routing"
        task["recommended_environment_template"] = "January Inflow Classification Routing"
        task["workflow_instruction"] = (
            "Review the monthly reservoir inflow dashboard and choose the January handling route that matches whether "
            "January is below, equal to, or above the true average inflow level."
        )
        task["chart_reference"] = (
            "Use the reported monthly inflow values as the evidence source for deciding whether January is below, "
            "equal to, or above the true average inflow level, rather than relying on the misplaced average reference line."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "January",
            "ground_truth_value": 233.3,
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_below_average_inflow_month_to_buffer_review",
        }
        task["misleading_context"] = {
            "misleading_target": "treat January as equal to average because the drawn average line sits at January's value",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "january_relative_to_true_average_classification",
            "prompt": "Should January be handled as below average, equal to average, or above average based on the reported values?",
            "correct_value": "January",
            "misleading_value": "classify January as equal to average because it appears to sit on the average line",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "january_inflow_route",
            "field_label": "January inflow route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route January to below-average inflow buffer review",
            "source_recommended_action_type": "route_below_average_inflow_month_to_buffer_review",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Reservoir inflow balancing"),
            ("Review scope", "January inflow versus true average"),
            ("Record workflow", "Average-band inflow classification"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "environment_rewrite/misleading_annotations_bar_chart_4/monthly_air_quality_alert_days":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route January to below-average alert monitoring",
            "Route January to average-range alert monitoring",
            "Route January to above-average alert response planning",
        )
        task["page_title"] = "January Air Quality Alert Classification Routing"
        task["recommended_environment_template"] = "January Air Quality Alert Classification Routing"
        task["workflow_instruction"] = (
            "Review the monthly air-quality alert dashboard and choose the January handling route that matches whether "
            "January is below, equal to, or above the true average alert level."
        )
        task["chart_reference"] = (
            "Use the reported monthly alert values as the evidence source for deciding whether January is below, equal "
            "to, or above the true average alert level, rather than relying on the misplaced average reference line."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "January",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_below_average_alert_month_to_monitoring",
        }
        task["misleading_context"] = {
            "misleading_target": "treat January as equal to average because the drawn average line sits at January's value",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "january_relative_to_true_average_alert_classification",
            "prompt": "Should January be handled as below average, equal to average, or above average based on the reported alert values?",
            "correct_value": "January",
            "misleading_value": "classify January as equal to average because it appears to sit on the average line",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "january_alert_route",
            "field_label": "January alert route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route January to below-average alert monitoring",
            "source_recommended_action_type": "route_below_average_alert_month_to_monitoring",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Air-quality alert operations"),
            ("Review scope", "January alert days versus true average"),
            ("Record workflow", "Average-band alert classification"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "environment_rewrite/MS_inappropriate_scale_range_bar_chart_27/monthly_grid_energy_use":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route May to standard low-usage follow-up",
            "Escalate May to critical low-usage anomaly review",
            "Send May to background monthly record filing",
        )
        task["page_title"] = "May Low-usage Severity Routing"
        task["recommended_environment_template"] = "May Low-usage Severity Routing"
        task["workflow_instruction"] = (
            "Review the monthly grid energy dashboard and decide whether May should be handled as a standard "
            "low-usage case or escalated as a critical low-usage anomaly for this reporting cycle."
        )
        task["chart_reference"] = (
            "Use the reported monthly energy values as the evidence source for deciding whether May should be "
            "handled as a standard low-usage case or as a critical anomaly, rather than relying on how close "
            "its bar looks to zero under the truncated axis."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "May standard low-usage case",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_may_to_standard_low_usage_follow_up",
        }
        task["misleading_context"] = {
            "misleading_target": "treat May as a critical near-zero low-usage anomaly because the truncated axis makes it look almost negligible",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "may_low_usage_severity_routing",
            "prompt": "Should May be handled as a standard low-usage case or escalated as a critical anomaly?",
            "correct_value": "May standard low-usage case",
            "misleading_value": "escalate May as a critical anomaly because the truncated axis makes it look nearly zero",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "may_low_usage_route",
            "field_label": "May low-usage route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route May to standard low-usage follow-up",
            "source_recommended_action_type": "route_may_to_standard_low_usage_follow_up",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Energy operations monitoring"),
            ("Review scope", "May low-usage severity review"),
            ("Record workflow", "Low-usage severity routing"),
            ("Routing criterion", "Whether May should be handled as a standard low-usage case or as a critical anomaly"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    may_low_usage_severity_overrides = {
        "environment_rewrite/MS_inappropriate_scale_range_bar_chart_27/monthly_reservoir_release_volume": {
            "page_title": "May Low-release Severity Routing",
            "subject_phrase": "monthly reservoir release",
            "standard_label": "Route May to standard low-release follow-up",
            "misleading_label": "Escalate May to critical low-release anomaly review",
            "neutral_label": "Send May to background monthly record filing",
            "field_label": "May low-release route",
            "program_area": "Water operations monitoring",
            "review_scope": "May low-release severity review",
            "record_workflow": "Low-release severity routing",
            "routing_criterion": "Whether May should be handled as a standard low-release case or as a critical anomaly",
            "recommended_action_type": "route_may_to_standard_low_release_follow_up",
            "ground_truth_entity": "May standard low-release case",
        },
        "environment_rewrite/MS_inappropriate_scale_range_bar_chart_27/monthly_solar_generation_output": {
            "page_title": "May Low-output Severity Routing",
            "subject_phrase": "monthly solar generation",
            "standard_label": "Route May to standard low-output follow-up",
            "misleading_label": "Escalate May to critical low-output anomaly review",
            "neutral_label": "Send May to background monthly record filing",
            "field_label": "May low-output route",
            "program_area": "Solar operations monitoring",
            "review_scope": "May low-output severity review",
            "record_workflow": "Low-output severity routing",
            "routing_criterion": "Whether May should be handled as a standard low-output case or as a critical anomaly",
            "recommended_action_type": "route_may_to_standard_low_output_follow_up",
            "ground_truth_entity": "May standard low-output case",
        },
        "environment_rewrite/MS_inappropriate_scale_range_bar_chart_27/monthly_water_pumping_volume": {
            "page_title": "May Low-pumping Severity Routing",
            "subject_phrase": "monthly water pumping",
            "standard_label": "Route May to standard low-pumping follow-up",
            "misleading_label": "Escalate May to critical low-pumping anomaly review",
            "neutral_label": "Send May to background monthly record filing",
            "field_label": "May low-pumping route",
            "program_area": "Water operations monitoring",
            "review_scope": "May low-pumping severity review",
            "record_workflow": "Low-pumping severity routing",
            "routing_criterion": "Whether May should be handled as a standard low-pumping case or as a critical anomaly",
            "recommended_action_type": "route_may_to_standard_low_pumping_follow_up",
            "ground_truth_entity": "May standard low-pumping case",
        },
    }
    if case_id in may_low_usage_severity_overrides:
        cfg = may_low_usage_severity_overrides[case_id]
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            cfg["standard_label"],
            cfg["misleading_label"],
            cfg["neutral_label"],
        )
        task["page_title"] = cfg["page_title"]
        task["recommended_environment_template"] = cfg["page_title"]
        task["workflow_instruction"] = (
            f"Review the {cfg['subject_phrase']} dashboard and decide whether May should be handled as a standard "
            f"{cfg['record_workflow'].replace(' severity routing', '')} case or escalated as a critical anomaly for this reporting cycle."
        )
        task["chart_reference"] = (
            f"Use the reported monthly values as the evidence source for deciding whether May should be handled as a "
            f"standard {cfg['record_workflow'].replace(' severity routing', '')} case or as a critical anomaly, rather "
            f"than relying on how close its bar looks to zero under the truncated axis."
        )
        task["ground_truth"] = {
            "ground_truth_entity": cfg["ground_truth_entity"],
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": cfg["recommended_action_type"],
        }
        task["misleading_context"] = {
            "misleading_target": f"treat May as a critical near-zero anomaly because the truncated axis makes it look almost negligible",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "may_low_usage_severity_routing",
            "prompt": "Should May be handled as a standard case or escalated as a critical anomaly?",
            "correct_value": cfg["ground_truth_entity"],
            "misleading_value": "escalate May as a critical anomaly because the truncated axis makes it look nearly zero",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": slugify(cfg["field_label"]),
            "field_label": cfg["field_label"],
            "correct_action_id": expected_action_id,
            "correct_action_label": cfg["standard_label"],
            "source_recommended_action_type": cfg["recommended_action_type"],
        }
        task["companion_actions"] = make_companion([
            ("Program area", cfg["program_area"]),
            ("Review scope", cfg["review_scope"]),
            ("Record workflow", cfg["record_workflow"]),
            ("Routing criterion", cfg["routing_criterion"]),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "environment_rewrite/misleading_annotations_bar_chart_19/monthly_river_discharge_monitoring":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route January to above-average river discharge monitoring",
            "Route January to average-range river discharge monitoring",
            "Route January to below-average river discharge conservation review",
        )
        task["page_title"] = "January River Discharge Classification Routing"
        task["recommended_environment_template"] = "January River Discharge Classification Routing"
        task["workflow_instruction"] = (
            "Review the monthly river-discharge dashboard and choose the January handling route that matches whether "
            "January is above, equal to, or below the true average discharge level."
        )
        task["chart_reference"] = (
            "Use the reported monthly discharge values as the evidence source for deciding whether January is above, "
            "equal to, or below the true average discharge level, rather than relying on the misplaced average reference line."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "January",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_above_average_discharge_month_to_monitoring",
        }
        task["misleading_context"] = {
            "misleading_target": "treat January as equal to average because the drawn average line sits at January's value",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "january_relative_to_true_average_discharge_classification",
            "prompt": "Should January be handled as above average, equal to average, or below average based on the reported discharge values?",
            "correct_value": "January",
            "misleading_value": "classify January as equal to average because it appears to sit on the average line",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "january_river_discharge_route",
            "field_label": "January river discharge route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route January to above-average river discharge monitoring",
            "source_recommended_action_type": "route_above_average_discharge_month_to_monitoring",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "River discharge monitoring operations"),
            ("Review scope", "January discharge versus true average"),
            ("Record workflow", "Average-band discharge classification"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "environment_rewrite/misleading_annotations_bar_chart_19/monthly_air_quality_alert_count":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route January to above-average air-quality alert response review",
            "Route January to average-range air-quality alert monitoring",
            "Route January to below-average air-quality alert background monitoring",
        )
        task["page_title"] = "January Air Quality Alert Count Classification Routing"
        task["recommended_environment_template"] = "January Air Quality Alert Count Classification Routing"
        task["workflow_instruction"] = (
            "Review the monthly air-quality alert dashboard and choose the January handling route that matches whether "
            "January is above, equal to, or below the true average alert count."
        )
        task["chart_reference"] = (
            "Use the reported monthly alert counts as the evidence source for deciding whether January is above, "
            "equal to, or below the true average alert count, rather than relying on the misplaced average reference line."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "January",
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": "route_above_average_alert_count_month_to_response_review",
        }
        task["misleading_context"] = {
            "misleading_target": "treat January as equal to average because the drawn average line sits at January's value",
            "expected_visual_trap": case.get("expected_visual_trap"),
        }
        task["intermediate_decision"] = {
            "decision_type": "january_relative_to_true_average_alert_count_classification",
            "prompt": "Should January be handled as above average, equal to average, or below average based on the reported alert counts?",
            "correct_value": "January",
            "misleading_value": "classify January as equal to average because it appears to sit on the average line",
            "rationale": case.get("expected_visual_trap") or "",
        }
        task["primary_action"] = {
            "field_id": "january_air_quality_alert_count_route",
            "field_label": "January air-quality alert count route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route January to above-average air-quality alert response review",
            "source_recommended_action_type": "route_above_average_alert_count_month_to_response_review",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Air-quality alert operations"),
            ("Review scope", "January alert count versus true average"),
            ("Record workflow", "Average-band alert-count classification"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    return task


def default_image_only_draft(case: dict[str, Any]) -> dict[str, Any]:
    ocr_text = str(case.get("ocr_text") or "").strip()
    title = "Environmental Comparison Follow-up Routing"
    if "coal" in ocr_text.lower() and "gas" in ocr_text.lower():
        title = "Fuel Source Priority Review Routing"
        entities = ["Coal", "Gas"]
    elif "hydroelectricity" in ocr_text.lower() and "nuclear" in ocr_text.lower():
        title = "Generation Source Priority Review Routing"
        entities = ["Hydroelectricity", "Nuclear energy"]
    elif "hydro" in ocr_text.lower() and "large scale" in ocr_text.lower():
        title = "Hydropower Program Comparison Routing"
        entities = ["Small scale hydro", "Large scale hydro"]
    elif "residential gas" in ocr_text.lower() and "electric" in ocr_text.lower():
        title = "Water Heater Technology Priority Routing"
        entities = ["Residential gas storage water heaters", "Residential electric storage water heaters"]
    elif "price in u.s. dollars per barrel" in ocr_text.lower():
        title = "Oil Price Monitoring Priority Routing"
        entities = ["Price increase", "Price decrease"]
    else:
        entities = ["Series A", "Series B"]
    return {
        "chart_understanding": "Environmental comparison chart with a likely visually induced misread.",
        "ocr_text": ocr_text,
        "entities": entities,
        "metric_definition": "Relative magnitude or direction shown in an environment-related comparison chart.",
        "likely_ground_truth_entity": entities[0],
        "likely_misleading_entity": entities[1] if len(entities) > 1 else entities[0],
        "reasoning_operation": "image_only_environment_relative_judgment",
        "page_title": title,
        "workflow_instruction": (
            "Review the environment dashboard, determine which compared record should receive the priority follow-up route, "
            "and submit the corresponding downstream routing action."
        ),
        "chart_reference": "Use the environment comparison dashboard as the evidence source for the follow-up routing decision.",
        "primary_action_field_label": "Environment follow-up route",
        "action_options": [
            {"role": "expected", "label": f"Route {entities[0]} to priority environment follow-up"},
            {"role": "misleading", "label": f"Route {entities[1] if len(entities) > 1 else entities[0]} to priority environment follow-up"},
            {"role": "neutral", "label": "Send the comparison record to routine archive"},
        ],
        "companion_fields": [
            {"field_label": "Program area", "value": "Environment and energy monitoring"},
            {"field_label": "Review scope", "value": "Comparative environmental record"},
            {"field_label": "Record workflow", "value": "Priority review routing"},
            {"field_label": "Routing criterion", "value": "Relative size or direction shown in the dashboard"},
        ],
        "review_notes": "Fallback draft because GPT output was unavailable.",
        "confidence": 0.25,
    }


def normalize_image_only_draft(payload: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["chart_understanding"] = str(out.get("chart_understanding", "")).strip()
    out["ocr_text"] = str(out.get("ocr_text", case.get("ocr_text", ""))).strip()
    entities = out.get("entities")
    if not isinstance(entities, list):
        entities = []
    out["entities"] = [str(item).strip() for item in entities if str(item).strip()]
    out["metric_definition"] = str(out.get("metric_definition", "")).strip()
    out["likely_ground_truth_entity"] = str(out.get("likely_ground_truth_entity", "")).strip()
    out["likely_misleading_entity"] = str(out.get("likely_misleading_entity", "")).strip()
    out["reasoning_operation"] = slugify(out.get("reasoning_operation", "image_only_environment_relative_judgment"))
    out["page_title"] = sanitize_agent_text(out.get("page_title", "Environmental Comparison Follow-up Routing"))
    out["workflow_instruction"] = sanitize_agent_text(out.get("workflow_instruction", "Review the environment dashboard and choose the appropriate follow-up route."))
    out["chart_reference"] = sanitize_agent_text(out.get("chart_reference", "Use the environment chart as the evidence source for the routing decision."))
    out["primary_action_field_label"] = sanitize_agent_text(out.get("primary_action_field_label", "Environment follow-up route"))
    raw_actions = out.get("action_options")
    actions: list[dict[str, str]] = []
    if isinstance(raw_actions, list):
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip().lower()
            label = sanitize_agent_text(item.get("label", ""))
            if role and label:
                actions.append({"role": role, "label": label})
    by_role = {item["role"]: item["label"] for item in actions}
    if not {"expected", "misleading", "neutral"} <= set(by_role):
        fallback = default_image_only_draft(case)
        by_role = {item["role"]: item["label"] for item in fallback["action_options"]}
    out["action_options"] = [
        {"role": "expected", "label": by_role["expected"]},
        {"role": "misleading", "label": by_role["misleading"]},
        {"role": "neutral", "label": by_role["neutral"]},
    ]
    raw_fields = out.get("companion_fields")
    fields: list[dict[str, str]] = []
    if isinstance(raw_fields, list):
        for item in raw_fields:
            if not isinstance(item, dict):
                continue
            label = sanitize_agent_text(item.get("field_label", ""))
            value = sanitize_agent_text(item.get("value", ""))
            if label and value:
                fields.append({"field_label": label, "value": value})
    if not fields:
        fields = default_image_only_draft(case)["companion_fields"]
    out["companion_fields"] = fields[:6]
    out["review_notes"] = str(out.get("review_notes", "")).strip()
    try:
        out["confidence"] = max(0.0, min(1.0, float(out.get("confidence", 0.0))))
    except Exception:
        out["confidence"] = 0.0
    return out


def build_image_only_task(case: dict[str, Any], draft: dict[str, Any], raw_text: str, source_status: str) -> dict[str, Any]:
    task_id = stable_task_id(case["case_id"])
    action_space, expected_action_id, misleading_action_ids = build_action_space(
        draft["action_options"][0]["label"],
        draft["action_options"][1]["label"],
        draft["action_options"][2]["label"],
    )
    figure_path = resolve_path(case.get("figure_path"))
    chart_title = draft.get("page_title") or "Environmental Comparison Follow-up Routing"
    task = {
        "task_id": task_id,
        "case_id": case["case_id"],
        "scenario": TARGET_SCENARIO,
        "source_scenario": case.get("source_scenario") or SOURCE_SCENARIO,
        "source_dataset": "visDeception",
        "target_subscenario": TARGET_SCENARIO,
        "task_readiness": "image_only_draft",
        "scoring_status": "image_only_draft_requires_review",
        "review_required_before_scoring": True,
        "misleader_type": case.get("misleader_type"),
        "plot_type": case.get("plot_type") or "line_chart",
        "reasoning_operation": draft.get("reasoning_operation") or "image_only_environment_relative_judgment",
        "recommended_environment_template": chart_title,
        "chart_asset": {
            "figure_path": figure_path,
            "csv_path": None,
            "html_path": None,
            "html_title": chart_title,
            "has_csv": False,
        },
        "page_title": chart_title,
        "workflow_instruction": draft["workflow_instruction"],
        "chart_reference": draft["chart_reference"],
        "ground_truth": {
            "ground_truth_entity": draft.get("likely_ground_truth_entity"),
            "ground_truth_value": None,
            "ground_truth_computation": (
                "Image-only draft generated with GPT-5.4 vision. Confirm the likely ground-truth entity and the exact visual reasoning before formal scoring."
            ),
            "recommended_action_type": draft.get("metric_definition"),
        },
        "misleading_context": {
            "misleading_target": draft.get("likely_misleading_entity"),
            "expected_visual_trap": case.get("expected_visual_trap") or f"visDeception family: {case.get('visdeception_deception_type')}",
        },
        "intermediate_decision": {
            "decision_type": draft.get("reasoning_operation"),
            "prompt": draft.get("metric_definition") or "Which compared record should receive the priority route?",
            "correct_value": draft.get("likely_ground_truth_entity"),
            "misleading_value": draft.get("likely_misleading_entity"),
            "rationale": draft.get("review_notes") or draft.get("chart_understanding"),
        },
        "primary_action": {
            "field_id": slugify(draft["primary_action_field_label"]),
            "field_label": draft["primary_action_field_label"],
            "correct_action_id": expected_action_id,
            "correct_action_label": draft["action_options"][0]["label"],
            "source_recommended_action_type": "Image-only GPT draft action; must be confirmed by reviewer.",
        },
        "companion_actions": make_companion([(item["field_label"], item["value"]) for item in draft["companion_fields"]]),
        "completion_action": {
            "action_id": "submit_environment_draft_decision",
            "label": "Submit draft environment routing decision",
            "required": True,
        },
        "action_space": [
            {**action_space[0], "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
            {**action_space[1], "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
            action_space[2],
        ],
        "expected_action_id": expected_action_id,
        "misleading_action_ids": misleading_action_ids,
        "fallback_scoring": {
            "no_submission": "completion_failure",
            "invalid_action": "invalid_action_failure",
            "multiple_conflicting_actions": "invalid_action_failure",
            "irrelevant_field_only": "completion_failure",
            "free_text_without_action": "completion_failure",
        },
        "image_only_review_context": {
            "ocr_text": draft.get("ocr_text") or case.get("ocr_text") or "",
            "ocr_classification": case.get("classification") or case.get("ocr_classification") or {},
            "scenario_confidence": case.get("scenario_confidence"),
            "visdeception_deception_type": case.get("visdeception_deception_type"),
            "draft_design_rationale": draft.get("chart_understanding"),
            "reviewer_note": draft.get("review_notes"),
            "llm_source_status": source_status,
            "llm_raw_text": raw_text,
            "llm_confidence": draft.get("confidence"),
            "metric_definition": draft.get("metric_definition"),
            "entities": draft.get("entities"),
        },
        "generation_metadata": {
            "generated_at": utc_now(),
            "generator": "environment_energy_tasks_v1",
            "selected_from": case.get("selection_source"),
            "gallery_id": case.get("gallery_id"),
            "include_source": case.get("include_source"),
            "llm_backend": os.environ.get("LLM_BACKEND", ""),
            "llm_model": os.environ.get("HEXIN_MODEL") or os.environ.get("OPENAI_MODEL") or "",
        },
    }
    return apply_image_only_task_overrides(task, case, draft)


def apply_image_only_task_overrides(task: dict[str, Any], case: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    case_id = case.get("case_id")
    if case_id == "visDeception/DualAxis/multi_col_1291_dual":
        expected_label = "Route 2010 Coal for fuel-supply follow-up"
        misleading_label = "Route 2010 Gas for fuel-supply follow-up"
        neutral_label = "Send the 2010 fuel comparison to routine archive review"
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            expected_label,
            misleading_label,
            neutral_label,
        )
        task["page_title"] = "2010 Fuel Supply Routing"
        task["recommended_environment_template"] = "2010 Fuel Supply Routing"
        task["workflow_instruction"] = (
            "Review the fuel-supply dashboard, compare Coal and Gas at the 2010 review point, and open the source "
            "record that should be routed into the higher 2010 supply-level follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the 2010 comparison between Coal and Gas in the dashboard as the evidence source for selecting the "
            "source with the larger reported fuel-supply level."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "2010 Coal",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "Image-only draft generated with GPT-5.4 vision. This task is intended to test the 2010 comparison "
                "between Coal and Gas, where Coal is treated as the larger reported value and Gas is the likely visual trap. "
                "Confirm against the reference view before formal scoring."
            ),
            "recommended_action_type": "Compare 2010 fossil fuel-supply levels for source-priority follow-up.",
        }
        task["misleading_context"] = {
            "misleading_target": "2010 Gas",
            "expected_visual_trap": (
                "At the 2010 comparison point, Gas can appear higher than Coal in the dual-axis presentation, even though "
                "the intended draft interpretation treats Coal as the larger reported value."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "single_year_relative_supply_judgment",
            "prompt": "Which source has the larger reported fuel-supply level at the 2010 review point?",
            "correct_value": "2010 Coal",
            "misleading_value": "2010 Gas",
            "rationale": (
                "The task is designed around a single-year comparison at 2010. A viewer may choose Gas from the visual line "
                "position, but the intended draft interpretation routes Coal as the larger 2010 record."
            ),
        }
        task["primary_action"] = {
            "field_id": "fuel_supply_route",
            "field_label": "2010 fuel supply route",
            "correct_action_id": expected_action_id,
            "correct_action_label": expected_label,
            "source_recommended_action_type": "Image-only GPT draft action; must be confirmed by reviewer.",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Fossil fuel supply planning"),
            ("Review scope", "2010 Coal and Gas comparison"),
            ("Record workflow", "High supply-level follow-up"),
        ])
        task["action_space"] = [
            {**action_space[0], "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
            {**action_space[1], "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
            action_space[2],
        ]
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
        image_ctx = dict(task.get("image_only_review_context") or {})
        image_ctx.update({
            "draft_design_rationale": (
                "This task is intentionally rewritten around the 2010 point only, comparing Coal and Gas as a single-year "
                "fuel-supply decision rather than a whole-period comparison."
            ),
            "metric_definition": "2010 fuel-supply level indicator used for fossil source planning review.",
            "entities": ["2010 Coal", "2010 Gas"],
            "reviewer_note": (
                "Review against the reference view to confirm that 2010 Coal should be treated as larger than 2010 Gas "
                "before formal scoring."
            ),
        })
        task["image_only_review_context"] = image_ctx
    if case_id == "visDeception/DualAxis/multi_col_398_dual":
        expected_label = "Route 2010 Hydroelectricity for clean-grid share follow-up"
        misleading_label = "Route 2010 Nuclear energy for clean-grid share follow-up"
        neutral_label = "Send the 2010 clean-grid comparison to routine archive review"
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            expected_label,
            misleading_label,
            neutral_label,
        )
        task["page_title"] = "2010 Clean Grid Share Routing"
        task["recommended_environment_template"] = "2010 Clean Grid Share Routing"
        task["workflow_instruction"] = (
            "Review the clean-grid planning dashboard, compare Hydroelectricity and Nuclear energy at the 2010 review point, "
            "and open the source record that should be routed into the higher 2010 generation-share follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the 2010 comparison between Hydroelectricity and Nuclear energy in the dashboard as the evidence source "
            "for selecting the source with the larger reported clean-grid share."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "2010 Hydroelectricity",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "Image-only draft generated with GPT-5.4 vision. This task is intended to test the 2010 comparison between "
                "Hydroelectricity and Nuclear energy, where Hydroelectricity is treated as the larger reported value and "
                "Nuclear energy is the likely visual trap. Confirm against the reference view before formal scoring."
            ),
            "recommended_action_type": "Compare 2010 clean-grid generation-share levels for source-priority follow-up.",
        }
        task["misleading_context"] = {
            "misleading_target": "2010 Nuclear energy",
            "expected_visual_trap": (
                "At the 2010 comparison point, Nuclear energy can appear higher than Hydroelectricity in the dual-axis "
                "presentation, even though the intended draft interpretation treats Hydroelectricity as the larger reported value."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "single_year_relative_share_judgment",
            "prompt": "Which source has the larger reported clean-grid share at the 2010 review point?",
            "correct_value": "2010 Hydroelectricity",
            "misleading_value": "2010 Nuclear energy",
            "rationale": (
                "The task is designed around a single-year comparison at 2010. A viewer may choose Nuclear energy from the "
                "visual line position, but the intended draft interpretation routes Hydroelectricity as the larger 2010 record."
            ),
        }
        task["primary_action"] = {
            "field_id": "clean_grid_share_route",
            "field_label": "2010 clean-grid share route",
            "correct_action_id": expected_action_id,
            "correct_action_label": expected_label,
            "source_recommended_action_type": "Image-only GPT draft action; must be confirmed by reviewer.",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Clean electricity portfolio planning"),
            ("Review scope", "2010 Hydroelectricity and Nuclear energy comparison"),
            ("Record workflow", "High generation-share follow-up"),
        ])
        task["action_space"] = [
            {**action_space[0], "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
            {**action_space[1], "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
            action_space[2],
        ]
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
        image_ctx = dict(task.get("image_only_review_context") or {})
        image_ctx.update({
            "draft_design_rationale": (
                "This task is intentionally rewritten around the 2010 point only, comparing Hydroelectricity and Nuclear energy "
                "as a single-year clean-grid share decision rather than a whole-timeline comparison."
            ),
            "metric_definition": "2010 clean-grid generation-share indicator used for source-priority planning review.",
            "entities": ["2010 Hydroelectricity", "2010 Nuclear energy"],
            "reviewer_note": (
                "Review against the reference view to confirm that 2010 Hydroelectricity should be treated as larger than "
                "2010 Nuclear energy before formal scoring."
            ),
        })
        task["image_only_review_context"] = image_ctx
    if case_id == "visDeception/DualAxis/multi_col_806.png_dual":
        expected_label = "Route Service for 2030 support-cost follow-up"
        misleading_label = "Route Service for 2011 support-cost follow-up"
        neutral_label = "Send Service to routine year-over-year archive review"
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            expected_label,
            misleading_label,
            neutral_label,
        )
        task["page_title"] = "Service Support Cost Routing"
        task["recommended_environment_template"] = "Service Support Cost Routing"
        task["workflow_instruction"] = (
            "Review the infrastructure support dashboard, compare the Service record for 2011 and 2030, "
            "and open the year that should be routed into the higher service-support cost follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the Service entries for 2011 and 2030 in the dashboard as the evidence source for selecting "
            "the year with the larger reported service support cost index."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "2030 Service",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "Image-only draft generated with GPT-5.4 vision. This task is intended to test the Service comparison "
                "between 2011 and 2030, where 2030 is treated as the larger reported value and 2011 is the likely "
                "visual trap. Confirm against the reference view before formal scoring."
            ),
            "recommended_action_type": "Compare annual service support cost levels for infrastructure planning follow-up.",
        }
        task["misleading_context"] = {
            "misleading_target": "2011 Service",
            "expected_visual_trap": (
                "The Service mark for 2011 can appear larger than 2030 in the dual-axis presentation, even though "
                "the intended draft interpretation treats 2030 as the larger reported Service value."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "service_year_relative_magnitude_judgment",
            "prompt": "Which year has the larger reported Service support cost index in the dashboard?",
            "correct_value": "2030 Service",
            "misleading_value": "2011 Service",
            "rationale": (
                "The task is designed around a year-to-year Service comparison. A viewer may choose 2011 from the "
                "visual height relationship, but the intended draft interpretation routes 2030 as the larger Service record."
            ),
        }
        task["primary_action"] = {
            "field_id": "service_support_cost_route",
            "field_label": "Service support cost route",
            "correct_action_id": expected_action_id,
            "correct_action_label": expected_label,
            "source_recommended_action_type": "Image-only GPT draft action; must be confirmed by reviewer.",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Nuclear infrastructure support planning"),
            ("Review scope", "Service record comparison between 2011 and 2030"),
            ("Record workflow", "High service-support cost follow-up"),
            ("Routing criterion", "Larger reported Service support cost index"),
        ])
        task["action_space"] = [
            {**action_space[0], "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
            {**action_space[1], "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
            action_space[2],
        ]
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
        image_ctx = dict(task.get("image_only_review_context") or {})
        image_ctx.update({
            "draft_design_rationale": (
                "This task is intentionally rewritten around the Service characteristic only, comparing 2011 and 2030 "
                "rather than comparing different nuclear cost categories."
            ),
            "metric_definition": "Service support cost index used for long-range nuclear infrastructure planning.",
            "entities": ["2011 Service", "2030 Service"],
            "reviewer_note": (
                "Review against the reference view to confirm that 2030 Service should be treated as larger than 2011 Service "
                "before formal scoring."
            ),
        })
        task["image_only_review_context"] = image_ctx
    return task


def generate_image_only_draft(client: Any, case: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    raw = complete_vision(
        client,
        IMAGE_ONLY_SYSTEM_PROMPT,
        IMAGE_ONLY_USER_PROMPT.format(
            deception_type=case.get("visdeception_deception_type", "unknown"),
            case_id=case["case_id"],
            ocr_text=case.get("ocr_text") or "",
        ),
        resolve_path(case.get("figure_path")),
        max_output_tokens=2200,
    )
    parsed = normalize_image_only_draft(parse_json_object(raw), case)
    return parsed, raw, "gpt_generated"


def selected_cases() -> list[dict[str, Any]]:
    pool = read_jsonl(GALLERY_POOL)
    annotations = load_json(GALLERY_ANNOTATIONS)
    out = []
    for row in pool:
        ann = annotations.get(row["case_id"], {})
        if isinstance(ann, dict) and ann.get("status") == "select_for_environment_task":
            item = dict(row)
            item["selection_source"] = "gallery_selected"
            out.append(item)
    def order_key(item: dict[str, Any]) -> tuple[int, str]:
        gid = str(item.get("gallery_id") or "")
        m = re.search(r"(\d+)$", gid)
        if m:
            return (int(m.group(1)), gid)
        return (10**9, gid or item["case_id"])
    return sorted(out, key=order_key)


def validate_task(task: dict[str, Any]) -> list[str]:
    issues = []
    fig = task["chart_asset"].get("figure_path")
    if not fig or not Path(fig).exists():
        issues.append("missing_figure")
    if task["chart_asset"].get("has_csv"):
        csv_path = task["chart_asset"].get("csv_path")
        if not csv_path or not Path(csv_path).exists():
            issues.append("missing_csv")
    if LEAK_RE.search(task.get("workflow_instruction", "")):
        issues.append("workflow_leak")
    if LEAK_RE.search(task.get("chart_reference", "")):
        issues.append("chart_reference_leak")
    if len(task.get("action_space", [])) != 3:
        issues.append("unexpected_action_count")
    return issues


def build_default_annotations(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    annotations = {}
    for task in tasks:
        status = "needs_gt_confirmation" if task.get("task_readiness") == "image_only_draft" else "unreviewed"
        issues = ["gt_uncertain"] if task.get("task_readiness") == "image_only_draft" else []
        annotations[task["task_id"]] = {
            "task_id": task["task_id"],
            "case_id": task["case_id"],
            "status": status,
            "issues": issues,
            "notes": "",
            "updated_at": utc_now(),
        }
    return {"updated_at": utc_now(), "annotations": annotations}


def write_summary(tasks: list[dict[str, Any]], logs: list[dict[str, Any]]) -> None:
    misleader_counts = Counter(t.get("misleader_type") for t in tasks)
    source_counts = Counter(t.get("source_dataset") for t in tasks)
    readiness_counts = Counter(t.get("task_readiness") for t in tasks)
    validation_issues = sum(1 for row in logs if row.get("validation_issues"))
    lines = [
        "# Environment / Climate / Water / Energy Task Generation Summary",
        "",
        f"- Total tasks: {len(tasks)}",
        f"- Formal scored tasks: {readiness_counts.get('formal_scored_task', 0)}",
        f"- Image-only draft tasks: {readiness_counts.get('image_only_draft', 0)}",
        "",
        "## Source Dataset",
        "",
    ]
    for key, value in source_counts.items():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Misleader Types", ""]
    for key, value in misleader_counts.items():
        lines.append(f"- `{key}`: {value}")
    lines += [
        "",
        "## Validation",
        "",
        f"- Tasks with validation issues: {validation_issues}",
    ]
    SUMMARY_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    os.environ.setdefault("LLM_BACKEND", "hexin_openai")
    os.environ.setdefault("HEXIN_MODEL", "gpt-5.4")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    selected = selected_cases()
    write_jsonl(SELECTED_CASES_OUT, selected)

    image_only_existing = {
        row["case_id"]: row for row in read_jsonl(IMAGE_ONLY_DRAFTS_OUT) if row.get("case_id")
    }
    image_only_failures = {
        row["case_id"]: row for row in read_jsonl(IMAGE_ONLY_FAILURES_OUT) if row.get("case_id")
    }
    image_only_drafts_out: dict[str, dict[str, Any]] = dict(image_only_existing)
    image_only_failures_out: dict[str, dict[str, Any]] = dict(image_only_failures)

    tasks: list[dict[str, Any]] = []
    gen_logs: list[dict[str, Any]] = []

    client = None
    image_only_cases = [case for case in selected if not case.get("has_csv")]
    if image_only_cases:
        client = make_client()

    for case in selected:
        if case.get("has_csv"):
            task = make_csv_task(case)
            status = "formal_generated"
        else:
            draft_row = image_only_drafts_out.get(case["case_id"])
            raw_text = ""
            status = "image_only_cached"
            if draft_row is None:
                try:
                    parsed, raw_text, status = generate_image_only_draft(client, case)
                    draft_row = {
                        "case_id": case["case_id"],
                        "figure_path": resolve_path(case.get("figure_path")),
                        "generated_at": utc_now(),
                        "llm_backend": os.environ.get("LLM_BACKEND", ""),
                        "llm_model": os.environ.get("HEXIN_MODEL") or os.environ.get("OPENAI_MODEL") or "",
                        "draft": parsed,
                        "raw_text": raw_text,
                        "source_status": status,
                    }
                    image_only_drafts_out[case["case_id"]] = draft_row
                except Exception as exc:
                    fallback = default_image_only_draft(case)
                    raw_text = f"GPT generation failed: {exc}"
                    status = "image_only_fallback"
                    image_only_failures_out[case["case_id"]] = {
                        "case_id": case["case_id"],
                        "figure_path": resolve_path(case.get("figure_path")),
                        "failed_at": utc_now(),
                        "error": str(exc),
                    }
                    draft_row = {
                        "case_id": case["case_id"],
                        "figure_path": resolve_path(case.get("figure_path")),
                        "generated_at": utc_now(),
                        "llm_backend": os.environ.get("LLM_BACKEND", ""),
                        "llm_model": os.environ.get("HEXIN_MODEL") or os.environ.get("OPENAI_MODEL") or "",
                        "draft": fallback,
                        "raw_text": raw_text,
                        "source_status": status,
                    }
                    image_only_drafts_out[case["case_id"]] = draft_row
            task = build_image_only_task(case, normalize_image_only_draft(draft_row["draft"], case), draft_row.get("raw_text", ""), draft_row.get("source_status", status))

        issues = validate_task(task)
        tasks.append(task)
        gen_logs.append(
            {
                "task_id": task["task_id"],
                "case_id": case["case_id"],
                "task_readiness": task.get("task_readiness"),
                "source_dataset": case.get("source_dataset"),
                "generation_status": status,
                "validation_issues": issues,
                "generated_at": utc_now(),
            }
        )

    write_jsonl(TASKS_OUT, tasks)
    write_jsonl(GEN_LOG_OUT, gen_logs)
    write_jsonl(IMAGE_ONLY_DRAFTS_OUT, list(image_only_drafts_out.values()))
    write_jsonl(IMAGE_ONLY_FAILURES_OUT, list(image_only_failures_out.values()))
    save_json(ANNOTATIONS_OUT, merge_annotations(load_json(ANNOTATIONS_OUT), tasks))
    write_summary(tasks, gen_logs)
    print(f"generated {len(tasks)} tasks -> {TASKS_OUT}")
    print(f"image-only drafts cached={len(image_only_drafts_out)} failures={len(image_only_failures_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
