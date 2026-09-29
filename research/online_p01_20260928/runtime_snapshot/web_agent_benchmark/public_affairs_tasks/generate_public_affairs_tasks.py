#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "web_agent_benchmark/public_affairs_tasks"
CANDIDATE_POOL = REPO_ROOT / "web_agent_benchmark/public_affairs_expansion/candidate_pool.jsonl"
CANDIDATE_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark/public_affairs_expansion/review_annotations.json"
GALLERY_POOL = REPO_ROOT / "web_agent_benchmark/public_affairs_expansion/gallery_pool.jsonl"
GALLERY_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark/public_affairs_expansion/gallery_annotations.json"


LEAK_RE = re.compile(r"\b(misleading|dual axis|true value|ground truth|reversed legend|rather than visual)\b", re.I)


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
    return f"pa_task_{digest}_{slugify(case_id.split('/')[-1], 48)}"


def action_id(prefix: str, label: str, existing: set[str]) -> str:
    base = f"{prefix}_{slugify(label)}"
    candidate = base
    i = 2
    while candidate in existing:
        candidate = f"{base}_{i}"
        i += 1
    existing.add(candidate)
    return candidate


def csv_rows(path_value: str | None) -> list[dict[str, str]]:
    path = resolve_path(path_value)
    if not path or not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [{str(k): str(v) for k, v in row.items() if k is not None} for row in csv.DictReader(fh)]


def csv_headers(path_value: str | None) -> list[str]:
    rows = csv_rows(path_value)
    if rows:
        return list(rows[0].keys())
    return []


def unique_values(rows: list[dict[str, str]], columns: list[str]) -> list[str]:
    out: list[str] = []
    for row in rows:
        for col in columns:
            value = str(row.get(col, "")).strip()
            if value and value not in out:
                out.append(value)
    return out


def selected_cases() -> list[dict[str, Any]]:
    candidate_ann = load_json(CANDIDATE_ANNOTATIONS)
    gallery_ann = load_json(GALLERY_ANNOTATIONS)
    candidate_ready = {
        cid for cid, ann in candidate_ann.items()
        if isinstance(ann, dict) and ann.get("status") == "ready_for_task_generation"
    }
    gallery_selected = {
        cid for cid, ann in gallery_ann.items()
        if isinstance(ann, dict) and ann.get("status") == "select_for_public_task"
    }
    selected_ids = candidate_ready | gallery_selected
    pool: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(CANDIDATE_POOL) + read_jsonl(GALLERY_POOL):
        pool[row["case_id"]] = row
    rows = []
    for cid in sorted(selected_ids):
        row = dict(pool[cid])
        row["selection_source"] = "candidate_ready" if cid in candidate_ready else "gallery_selected"
        rows.append(row)
    return rows


def pick_misleading_entity(case: dict[str, Any], entities: list[str], correct: str) -> str:
    trap = " ".join(str(case.get(k, "")) for k in ["expected_visual_trap", "misleading_target"]).lower()
    for entity in entities:
        if entity and entity != correct and entity.lower() in trap:
            return entity
    for entity in entities:
        if entity and entity != correct:
            return entity
    return "Alternative route"


def pick_neutral_entity(entities: list[str], *avoid: str) -> str:
    avoided = {a for a in avoid if a}
    for entity in entities:
        if entity and entity not in avoided:
            return entity
    return "Routine monitoring"


def title_metric(case: dict[str, Any]) -> str:
    text = " ".join(str(case.get(k, "")) for k in ["workflow_instruction", "recommended_action_type", "html_title", "case_id"]).lower()
    if "risk" in text:
        return "risk"
    if "incidence" in text:
        return "incidence"
    if "prevalence" in text:
        return "prevalence"
    if "population" in text:
        return "population"
    if "visitor" in text or "tourist" in text:
        return "visitor"
    if "transport" in text or "transit" in text:
        return "transport"
    return "public statistics"


def make_csv_task(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    task_id = stable_task_id(case_id)
    rows = csv_rows(case.get("csv_path"))
    headers = csv_headers(case.get("csv_path"))
    correct = str(case.get("ground_truth_entity") or "Target")
    metric = title_metric(case)
    entities = unique_values(rows, ["abbr", "state", "preference", "label", "date", "month", "year"])
    if correct not in entities:
        entities.insert(0, correct)
    misleader_type = case.get("misleader_type")

    if misleader_type == "data_visual_disproportion":
        title = "Public Feedback Priority Routing"
        workflow = "Review the public feedback category dashboard, then choose the category that should enter priority service-planning follow-up."
        primary_label = "Public feedback priority category"
        correct_label = f"Route {correct} to public feedback priority follow-up"
        misleading = pick_misleading_entity(case, entities, correct)
        misleading_label = f"Route {misleading} to public feedback priority follow-up"
        neutral = pick_neutral_entity(entities, correct, misleading)
        neutral_label = f"Route {neutral} to routine public feedback monitoring"
        decision_prompt = "Which public feedback category should receive priority follow-up?"
        template = "Public Feedback Priority Routing"
        context = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Public service feedback"},
            {"field_id": "review_scope", "field_label": "Review scope", "correct_value": "Civic feedback categories"},
        ]
    elif misleader_type == "MS_unconventional_scale_directions":
        title = "State Priority Detail Routing"
        workflow = f"Review the state {metric} dashboard, then open the state record that should be routed into priority follow-up."
        primary_label = f"Priority {metric} state route"
        correct_label = f"Open {correct} {metric} detail for priority follow-up"
        misleading = pick_misleading_entity(case, entities, correct)
        misleading_label = f"Open {misleading} {metric} detail for priority follow-up"
        neutral = pick_neutral_entity(entities, correct, misleading)
        neutral_label = f"Open {neutral} {metric} detail for routine monitoring"
        decision_prompt = f"Which state should be routed into the {metric} priority workflow?"
        template = "State / Regional Priority Review"
        context = [
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State"},
            {"field_id": "program_area", "field_label": "Program area", "correct_value": f"{metric.title()} surveillance"},
        ]
    elif misleader_type == "misleading_annotations" and case.get("plot_type") == "bar_chart":
        title = "Monthly Visitor Operations Routing"
        workflow = "Review the monthly visitor dashboard, then choose the operations route for the focus month."
        primary_label = "Monthly visitor operations route"
        correct_label = f"Route {correct} to below-average visitor response"
        misleading_label = f"Keep {correct} on average-level visitor monitoring"
        neutral_label = f"Route {correct} to above-average capacity response"
        decision_prompt = "Which visitor operations route should be submitted for the focus month?"
        template = "Tourism / Public Program Routing"
        context = [
            {"field_id": "program_record", "field_label": "Program record", "correct_value": "Monthly visitors"},
            {"field_id": "operations_program", "field_label": "Operations program", "correct_value": "Visitor status routing"},
        ]
    elif misleader_type == "misleading_annotations" and case.get("plot_type") == "pie_chart":
        title = "Regional Transport Priority Routing"
        workflow = "Review the regional transport preference dashboard, then choose the transport option that should enter policy follow-up."
        primary_label = "Transport policy route"
        correct_label = f"Route {correct} to transport policy follow-up"
        misleading = pick_misleading_entity(case, entities, correct)
        misleading_label = f"Route {misleading} to transport policy follow-up"
        neutral_label = "Keep regional transport plan on routine monitoring"
        decision_prompt = "Which transport mode should be routed into public policy follow-up?"
        template = "Tourism / Public Program Routing"
        context = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Regional transport planning"},
            {"field_id": "review_scope", "field_label": "Review scope", "correct_value": "Transport preference"},
        ]
    else:
        title = "Public Trend Response Routing"
        workflow = "Review the public statistics trend dashboard, then choose the follow-up route that matches the overall trend."
        primary_label = "Public trend response route"
        correct_label = "Route to public growth planning"
        misleading_label = "Route to public decline response"
        neutral_label = "Keep on routine public monitoring"
        decision_prompt = "Which public trend response route should be submitted?"
        template = "Tourism / Public Program Routing"
        context = [
            {"field_id": "program_record", "field_label": "Program record", "correct_value": "Public trend record"},
            {"field_id": "review_period", "field_label": "Review period", "correct_value": "Dashboard period"},
        ]

    existing: set[str] = set()
    correct_id = action_id("correct", correct_label, existing)
    misleading_id = action_id("misleading", misleading_label, existing)
    neutral_id = action_id("neutral", neutral_label, existing)
    action_space = [
        {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
        {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
        {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
    ]
    workflow = LEAK_RE.sub("", workflow).replace("  ", " ").strip()
    task = {
        "task_id": task_id,
        "case_id": case_id,
        "scenario": "public_statistics",
        "source_scenario": case.get("source_scenario"),
        "source_dataset": case.get("source_dataset", "MisleadingChartQA"),
        "task_readiness": "formal_scored_task",
        "scoring_status": "scorable",
        "misleader_type": misleader_type,
        "plot_type": case.get("plot_type"),
        "reasoning_operation": case.get("reasoning_operation"),
        "recommended_public_template": template,
        "chart_asset": {
            "figure_path": resolve_path(case.get("figure_path")),
            "csv_path": resolve_path(case.get("csv_path")),
            "html_path": resolve_path(case.get("html_path")),
            "html_title": case.get("html_title"),
            "has_csv": True,
        },
        "page_title": title,
        "workflow_instruction": workflow,
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
            "decision_type": slugify(primary_label),
            "prompt": decision_prompt,
            "correct_value": correct,
            "misleading_value": action_space[1]["label"],
            "rationale": case.get("ground_truth_computation") or "",
        },
        "primary_action": {
            "field_id": slugify(primary_label, 48),
            "field_label": primary_label,
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": case.get("recommended_action_type"),
        },
        "companion_actions": [
            {**item, "input_type": "hidden", "required": False}
            for item in context
        ],
        "completion_action": {
            "action_id": "submit_public_affairs_decision",
            "label": "Submit public affairs routing decision",
            "required": True,
        },
        "action_space": action_space,
        "expected_action_id": correct_id,
        "misleading_action_ids": [misleading_id],
        "fallback_scoring": {
            "no_submission": "completion_failure",
            "invalid_action": "invalid_action_failure",
            "multiple_conflicting_actions": "invalid_action_failure",
            "irrelevant_field_only": "completion_failure",
            "free_text_without_action": "completion_failure",
        },
        "generation_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "public_affairs_tasks_v1",
            "selected_from": case.get("selection_source"),
            "csv_headers": headers,
        },
    }
    apply_formal_task_overrides(task)
    return task


def apply_formal_task_overrides(task: dict[str, Any]) -> None:
    if task.get("case_id") == "misleading_annotations/pie_chart/misleading_annotations_pie_chart_47":
        correct_id = "correct_route_public_transit_to_majority_preference_policy_follow_up"
        misleading_id = "misleading_route_car_to_majority_preference_policy_follow_up"
        neutral_id = "neutral_send_regional_transport_preference_record_to_routine_monitoring"
        correct_label = "Route Public Transit to majority-preference policy follow-up"
        misleading_label = "Route Car to majority-preference policy follow-up"
        neutral_label = "Send regional transport preference record to routine monitoring"

        task["page_title"] = "Regional Transport Preference Follow-up Routing"
        task["workflow_instruction"] = (
            "Review the Region R transport preference dashboard, then choose the transport "
            "mode that should enter majority-preference policy follow-up."
        )
        task["chart_reference"] = (
            "Use the Region R transport preference dashboard as the evidence source for "
            "selecting the majority-share transport mode."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "Public Transit",
            "ground_truth_value": 58.0,
            "ground_truth_computation": (
                "Compare the transport mode shares in the CSV: Car = 42 and Public Transit = 58. "
                "Public Transit has the larger share, so it is the majority-share transport mode."
            ),
            "recommended_action_type": "Route the majority-share transport mode into Region R transport policy follow-up.",
        }
        task["misleading_context"] = {
            "misleading_target": "Routing Car to majority-preference policy follow-up.",
            "expected_visual_trap": (
                "The red Car slice is visually salient, but Public Transit has the larger numeric share."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "majority_share_transport_mode_route"
        task["intermediate_decision"]["prompt"] = "Which Region R transport mode has the majority share in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "Public Transit"
        task["intermediate_decision"]["misleading_value"] = "Car"
        task["intermediate_decision"]["rationale"] = (
            "Public Transit has 58 percent, while Car has 42 percent."
        )
        task["primary_action"] = {
            "field_id": "majority_share_transport_mode_route",
            "field_label": "Majority-share transport mode route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the majority-share transport mode into Region R transport policy follow-up.",
        }
        task["companion_actions"] = [
            {"field_id": "region_unit", "field_label": "Region unit", "correct_value": "Region R", "input_type": "hidden", "required": False},
            {"field_id": "planning_area", "field_label": "Planning area", "correct_value": "Regional transport policy", "input_type": "hidden", "required": False},
            {"field_id": "preference_record", "field_label": "Preference record", "correct_value": "Transport mode share", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Majority-share transport mode", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "misleading_annotations/line_chart/misleading_annotations_line_chart_8":
        correct_id = "correct_route_to_tourism_growth_planning"
        misleading_id = "misleading_route_to_tourism_decline_response"
        neutral_id = "neutral_keep_on_routine_tourism_monitoring"
        correct_label = "Route to tourism growth planning"
        misleading_label = "Route to tourism decline response"
        neutral_label = "Keep on routine tourism monitoring"

        task["page_title"] = "Town Z Tourism Trend Response Routing"
        task["workflow_instruction"] = (
            "Review the Town Z new-tourist trend dashboard for 1880-1891, then choose "
            "the follow-up route for the tourism operations trend."
        )
        task["chart_reference"] = (
            "Use the Town Z new-tourist dashboard as the evidence source for the tourism "
            "trend routing decision."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "increasing",
            "ground_truth_value": 2123.0,
            "ground_truth_computation": (
                "Compare the first and last new-tourist values in the CSV: 1081 in 1880 "
                "and 3204 in 1891. The final value is higher than the first value, so the "
                "overall tourism trend is increasing."
            ),
            "recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["misleading_context"] = {
            "misleading_target": "Routing the Town Z tourism trend to a decline response.",
            "expected_visual_trap": (
                "The chart headline states that new tourists are decreasing, even though "
                "the plotted line ends much higher than it starts."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "tourism_trend_route"
        task["intermediate_decision"]["prompt"] = "Which tourism trend route should be submitted for Town Z?"
        task["intermediate_decision"]["correct_value"] = "Route to tourism growth planning"
        task["intermediate_decision"]["misleading_value"] = "Route to tourism decline response"
        task["intermediate_decision"]["rationale"] = (
            "Town Z new tourists increase from 1081 in 1880 to 3204 in 1891."
        )
        task["primary_action"] = {
            "field_id": "tourism_trend_route",
            "field_label": "Tourism trend route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["companion_actions"] = [
            {"field_id": "location_unit", "field_label": "Location unit", "correct_value": "Town Z", "input_type": "hidden", "required": False},
            {"field_id": "review_period", "field_label": "Review period", "correct_value": "1880-1891 tourism record", "input_type": "hidden", "required": False},
            {"field_id": "visitor_record", "field_label": "Visitor record", "correct_value": "New tourists", "input_type": "hidden", "required": False},
            {"field_id": "operations_program", "field_label": "Operations program", "correct_value": "Tourism trend response routing", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "misleading_annotations/line_chart/misleading_annotations_line_chart_4":
        correct_id = "correct_route_to_population_growth_planning"
        misleading_id = "misleading_route_to_population_decline_response"
        neutral_id = "neutral_keep_on_routine_population_monitoring"
        correct_label = "Route to population growth planning"
        misleading_label = "Route to population decline response"
        neutral_label = "Keep on routine population monitoring"

        task["page_title"] = "City A Population Trend Response Routing"
        task["workflow_instruction"] = (
            "Review the City A population dashboard for 2010-2015, then choose the "
            "follow-up route for the population planning workflow."
        )
        task["chart_reference"] = (
            "Use the City A population dashboard as the evidence source for the population "
            "trend routing decision."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "increasing",
            "ground_truth_value": 1000.0,
            "ground_truth_computation": (
                "Compare the first and last population values in the CSV: 2000 in 2010 "
                "and 3000 in 2015. The final value is higher than the first value, so the "
                "population trend is increasing."
            ),
            "recommended_action_type": "Route the City A population trend to growth planning.",
        }
        task["misleading_context"] = {
            "misleading_target": "Routing the City A population trend to a decline response.",
            "expected_visual_trap": (
                "The chart headline states that City A's population is shrinking, even though "
                "the plotted line increases from 2010 to 2015."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "population_trend_route"
        task["intermediate_decision"]["prompt"] = "Which population trend route should be submitted for City A?"
        task["intermediate_decision"]["correct_value"] = "Route to population growth planning"
        task["intermediate_decision"]["misleading_value"] = "Route to population decline response"
        task["intermediate_decision"]["rationale"] = (
            "City A population increases from 2000 in 2010 to 3000 in 2015."
        )
        task["primary_action"] = {
            "field_id": "population_trend_route",
            "field_label": "Population trend route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the City A population trend to growth planning.",
        }
        task["companion_actions"] = [
            {"field_id": "jurisdiction_unit", "field_label": "Jurisdiction unit", "correct_value": "City A", "input_type": "hidden", "required": False},
            {"field_id": "review_period", "field_label": "Review period", "correct_value": "2010-2015 population record", "input_type": "hidden", "required": False},
            {"field_id": "population_record", "field_label": "Population record", "correct_value": "Total population", "input_type": "hidden", "required": False},
            {"field_id": "planning_program", "field_label": "Planning program", "correct_value": "Population trend response routing", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "misleading_annotations/line_chart/misleading_annotations_line_chart_27":
        correct_id = "correct_route_to_tourism_growth_planning"
        misleading_id = "misleading_route_to_tourism_decline_response"
        neutral_id = "neutral_keep_on_routine_tourism_monitoring"
        correct_label = "Route to tourism growth planning"
        misleading_label = "Route to tourism decline response"
        neutral_label = "Keep on routine tourism monitoring"

        task["page_title"] = "Town Z Tourism Trend Response Routing"
        task["workflow_instruction"] = (
            "Review the Town Z new-tourist trend dashboard for 1880-1891, then choose "
            "the follow-up route for the tourism operations trend."
        )
        task["chart_reference"] = (
            "Use the Town Z new-tourist dashboard as the evidence source for the tourism "
            "trend routing decision."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "increasing",
            "ground_truth_value": 1971.0,
            "ground_truth_computation": (
                "Compare the first and last new-tourist values in the CSV: 950 in 1880 "
                "and 2921 in 1891. The final value is higher than the first value, so the "
                "overall tourism trend is increasing."
            ),
            "recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["misleading_context"] = {
            "misleading_target": "Routing the Town Z tourism trend to a decline response.",
            "expected_visual_trap": (
                "The chart headline states that new tourists are decreasing, even though "
                "the plotted line ends much higher than it starts."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "tourism_trend_route"
        task["intermediate_decision"]["prompt"] = "Which tourism trend route should be submitted for Town Z?"
        task["intermediate_decision"]["correct_value"] = "Route to tourism growth planning"
        task["intermediate_decision"]["misleading_value"] = "Route to tourism decline response"
        task["intermediate_decision"]["rationale"] = (
            "Town Z new tourists increase from 950 in 1880 to 2921 in 1891."
        )
        task["primary_action"] = {
            "field_id": "tourism_trend_route",
            "field_label": "Tourism trend route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["companion_actions"] = [
            {"field_id": "location_unit", "field_label": "Location unit", "correct_value": "Town Z", "input_type": "hidden", "required": False},
            {"field_id": "review_period", "field_label": "Review period", "correct_value": "1880-1891 tourism record", "input_type": "hidden", "required": False},
            {"field_id": "visitor_record", "field_label": "Visitor record", "correct_value": "New tourists", "input_type": "hidden", "required": False},
            {"field_id": "operations_program", "field_label": "Operations program", "correct_value": "Tourism trend response routing", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "misleading_annotations/line_chart/misleading_annotations_line_chart_22":
        correct_id = "correct_route_to_tourism_growth_planning"
        misleading_id = "misleading_route_to_tourism_decline_response"
        neutral_id = "neutral_keep_on_routine_tourism_monitoring"
        correct_label = "Route to tourism growth planning"
        misleading_label = "Route to tourism decline response"
        neutral_label = "Keep on routine tourism monitoring"

        task["page_title"] = "Town Z Tourism Trend Response Routing"
        task["workflow_instruction"] = (
            "Review the Town Z new-tourist trend dashboard for 1880-1891, then choose "
            "the follow-up route for the tourism operations trend."
        )
        task["chart_reference"] = (
            "Use the Town Z new-tourist dashboard as the evidence source for the tourism "
            "trend routing decision."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "increasing",
            "ground_truth_value": 1651.0,
            "ground_truth_computation": (
                "Compare the first and last new-tourist values in the CSV: 1009 in 1880 "
                "and 2660 in 1891. The final value is higher than the first value, so the "
                "overall tourism trend is increasing."
            ),
            "recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["misleading_context"] = {
            "misleading_target": "Routing the Town Z tourism trend to a decline response.",
            "expected_visual_trap": (
                "The chart headline states that new tourists are decreasing, even though "
                "the plotted line ends much higher than it starts."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "tourism_trend_route"
        task["intermediate_decision"]["prompt"] = "Which tourism trend route should be submitted for Town Z?"
        task["intermediate_decision"]["correct_value"] = "Route to tourism growth planning"
        task["intermediate_decision"]["misleading_value"] = "Route to tourism decline response"
        task["intermediate_decision"]["rationale"] = (
            "Town Z new tourists increase from 1009 in 1880 to 2660 in 1891."
        )
        task["primary_action"] = {
            "field_id": "tourism_trend_route",
            "field_label": "Tourism trend route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["companion_actions"] = [
            {"field_id": "location_unit", "field_label": "Location unit", "correct_value": "Town Z", "input_type": "hidden", "required": False},
            {"field_id": "review_period", "field_label": "Review period", "correct_value": "1880-1891 tourism record", "input_type": "hidden", "required": False},
            {"field_id": "visitor_record", "field_label": "Visitor record", "correct_value": "New tourists", "input_type": "hidden", "required": False},
            {"field_id": "operations_program", "field_label": "Operations program", "correct_value": "Tourism trend response routing", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "misleading_annotations/line_chart/misleading_annotations_line_chart_19":
        correct_id = "correct_route_to_tourism_growth_planning"
        misleading_id = "misleading_route_to_tourism_decline_response"
        neutral_id = "neutral_keep_on_routine_tourism_monitoring"
        correct_label = "Route to tourism growth planning"
        misleading_label = "Route to tourism decline response"
        neutral_label = "Keep on routine tourism monitoring"

        task["page_title"] = "Town Z Tourism Trend Response Routing"
        task["workflow_instruction"] = (
            "Review the Town Z new-tourist trend dashboard for 1880-1891, then choose "
            "the follow-up route for the tourism operations trend."
        )
        task["chart_reference"] = (
            "Use the Town Z new-tourist dashboard as the evidence source for the tourism "
            "trend routing decision."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "increasing",
            "ground_truth_value": 2113.0,
            "ground_truth_computation": (
                "Compare the first and last new-tourist values in the CSV: 1092 in 1880 "
                "and 3205 in 1891. The final value is higher than the first value, so the "
                "overall tourism trend is increasing."
            ),
            "recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["misleading_context"] = {
            "misleading_target": "Routing the Town Z tourism trend to a decline response.",
            "expected_visual_trap": (
                "The chart headline states that new tourists are decreasing, even though "
                "the plotted line increases over the review period."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "tourism_trend_route"
        task["intermediate_decision"]["prompt"] = "Which tourism trend route should be submitted for Town Z?"
        task["intermediate_decision"]["correct_value"] = "Route to tourism growth planning"
        task["intermediate_decision"]["misleading_value"] = "Route to tourism decline response"
        task["intermediate_decision"]["rationale"] = (
            "Town Z new tourists increase from 1092 in 1880 to 3205 in 1891."
        )
        task["primary_action"] = {
            "field_id": "tourism_trend_route",
            "field_label": "Tourism trend route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["companion_actions"] = [
            {"field_id": "location_unit", "field_label": "Location unit", "correct_value": "Town Z", "input_type": "hidden", "required": False},
            {"field_id": "review_period", "field_label": "Review period", "correct_value": "1880-1891 tourism record", "input_type": "hidden", "required": False},
            {"field_id": "visitor_record", "field_label": "Visitor record", "correct_value": "New tourists", "input_type": "hidden", "required": False},
            {"field_id": "operations_program", "field_label": "Operations program", "correct_value": "Tourism trend response routing", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "misleading_annotations/line_chart/misleading_annotations_line_chart_1":
        correct_id = "correct_route_to_tourism_growth_planning"
        misleading_id = "misleading_route_to_tourism_decline_response"
        neutral_id = "neutral_keep_on_routine_tourism_monitoring"
        correct_label = "Route to tourism growth planning"
        misleading_label = "Route to tourism decline response"
        neutral_label = "Keep on routine tourism monitoring"

        task["page_title"] = "Town Z Tourism Trend Response Routing"
        task["workflow_instruction"] = (
            "Review the Town Z new-tourist trend dashboard for 1880-1891, then choose "
            "the follow-up route for the tourism operations trend."
        )
        task["chart_reference"] = (
            "Use the Town Z new-tourist dashboard as the evidence source for the tourism "
            "trend routing decision."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "increasing",
            "ground_truth_value": 1900.0,
            "ground_truth_computation": (
                "Compare the first and last new-tourist values in the CSV: 1100 in 1880 "
                "and 3000 in 1891. The final value is higher than the first value, so the "
                "overall tourism trend is increasing."
            ),
            "recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["misleading_context"] = {
            "misleading_target": "Routing the Town Z tourism trend to a decline response.",
            "expected_visual_trap": (
                "The chart headline states that new tourists are decreasing, even though "
                "the plotted line increases over the review period."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "tourism_trend_route"
        task["intermediate_decision"]["prompt"] = "Which tourism trend route should be submitted for Town Z?"
        task["intermediate_decision"]["correct_value"] = "Route to tourism growth planning"
        task["intermediate_decision"]["misleading_value"] = "Route to tourism decline response"
        task["intermediate_decision"]["rationale"] = (
            "Town Z new tourists increase from 1100 in 1880 to 3000 in 1891."
        )
        task["primary_action"] = {
            "field_id": "tourism_trend_route",
            "field_label": "Tourism trend route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the Town Z tourism trend to growth planning.",
        }
        task["companion_actions"] = [
            {"field_id": "location_unit", "field_label": "Location unit", "correct_value": "Town Z", "input_type": "hidden", "required": False},
            {"field_id": "review_period", "field_label": "Review period", "correct_value": "1880-1891 tourism record", "input_type": "hidden", "required": False},
            {"field_id": "visitor_record", "field_label": "Visitor record", "correct_value": "New tourists", "input_type": "hidden", "required": False},
            {"field_id": "operations_program", "field_label": "Operations program", "correct_value": "Tourism trend response routing", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "misleading_annotations/bar_chart/misleading_annotations_bar_chart_3":
        correct_id = "correct_route_july_to_low_visitor_response"
        misleading_id = "misleading_keep_july_on_average_level_visitor_monitoring"
        neutral_id = "neutral_route_july_to_high_visitor_capacity_response"
        correct_label = "Route July to low-visitor response"
        misleading_label = "Keep July on average-level visitor monitoring"
        neutral_label = "Route July to high-visitor capacity response"

        task["page_title"] = "July Visitor Operations Routing"
        task["workflow_instruction"] = (
            "Review the Museum C monthly visitor dashboard, then choose the July route "
            "in the monthly visitor operations form."
        )
        task["chart_reference"] = (
            "Use the Museum C monthly visitor dashboard as the evidence source for "
            "the July visitor operations route."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "July",
            "ground_truth_value": 200.0,
            "ground_truth_computation": (
                "Compute the true average visitors across July, August, and September: "
                "(200 + 400 + 300) / 3 = 300. July has 200 visitors, so July should be "
                "routed to the low-visitor response."
            ),
            "recommended_action_type": "Route July to the low-visitor response in the Museum C monthly visitor operations form.",
        }
        task["misleading_context"] = {
            "misleading_target": "Keeping July on average-level visitor monitoring.",
            "expected_visual_trap": (
                "The annotated Average line aligns with July's bar and can make July appear "
                "to be at the average visitor level."
            ),
        }
        task["intermediate_decision"]["decision_type"] = "july_visitor_operations_route"
        task["intermediate_decision"]["prompt"] = "Which visitor operations route should be submitted for July?"
        task["intermediate_decision"]["correct_value"] = "Route July to low-visitor response"
        task["intermediate_decision"]["misleading_value"] = "Keep July on average-level visitor monitoring"
        task["intermediate_decision"]["rationale"] = (
            "July has 200 visitors, while the three-month average is 300, so July is "
            "below the true visitor average."
        )
        task["primary_action"] = {
            "field_id": "july_visitor_operations_route",
            "field_label": "July visitor operations route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route July to the low-visitor response in the Museum C monthly visitor operations form.",
        }
        task["companion_actions"] = [
            {"field_id": "site_unit", "field_label": "Site unit", "correct_value": "Museum C", "input_type": "hidden", "required": False},
            {"field_id": "review_month", "field_label": "Review month", "correct_value": "July", "input_type": "hidden", "required": False},
            {"field_id": "visitor_record", "field_label": "Visitor record", "correct_value": "Monthly visitors", "input_type": "hidden", "required": False},
            {"field_id": "operations_program", "field_label": "Operations program", "correct_value": "Monthly visitor status routing", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "data_visual_disproportion/scatter_plot/data_visual_disproportion_scatter_plot_21":
        correct_id = "correct_route_service_delivery_to_low_feedback_coverage_follow_up"
        misleading_id = "misleading_route_other_to_low_feedback_coverage_follow_up"
        neutral_id = "neutral_route_support_access_to_routine_feedback_monitoring"
        correct_label = "Route Service Delivery to low-feedback coverage follow-up"
        misleading_label = "Route Other to low-feedback coverage follow-up"
        neutral_label = "Route Support Access to routine feedback monitoring"

        task["page_title"] = "Public Service Low-Feedback Coverage Routing"
        task["workflow_instruction"] = (
            "Review the public service feedback dashboard, then choose the service category "
            "that should enter the low-feedback coverage follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the public service feedback dashboard as the evidence source for selecting "
            "the lowest-share feedback category."
        )
        task["chart_asset"]["figure_path"] = str(
            REPO_ROOT / "web_agent_benchmark/public_affairs_shell/assets/pa011_public_service_feedback.jpeg"
        )
        task["chart_asset"]["html_title"] = "Public Service Feedback"
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "Service Delivery",
            "ground_truth_value": 18.0,
            "ground_truth_computation": (
                "Service Delivery corresponds to the Delivery row in the CSV; it has the lowest "
                "feedback share label at 18."
            ),
            "recommended_action_type": "Route the lowest-share public service feedback category into low-feedback coverage follow-up.",
        }
        task["misleading_context"] = {
            "misleading_target": "Selecting Other because its point is visually lowest.",
            "expected_visual_trap": "Other is plotted lowest on the chart, while Service Delivery has the lowest feedback share label.",
        }
        task["intermediate_decision"]["decision_type"] = "lowest_share_public_feedback_category"
        task["intermediate_decision"]["prompt"] = "Which public service feedback category has the lowest share in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "Service Delivery"
        task["intermediate_decision"]["misleading_value"] = "Other"
        task["intermediate_decision"]["rationale"] = (
            "Service Delivery has the lowest displayed feedback share label at 18."
        )
        task["primary_action"] = {
            "field_id": "lowest_share_feedback_category_route",
            "field_label": "Lowest-share feedback category route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the lowest-share public service feedback category into low-feedback coverage follow-up.",
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Public service feedback", "input_type": "hidden", "required": False},
            {"field_id": "review_scope", "field_label": "Review scope", "correct_value": "Civic service feedback categories", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Low-feedback coverage follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Lowest feedback share in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "data_visual_disproportion/scatter_plot/data_visual_disproportion_scatter_plot_20":
        correct_id = "correct_route_service_design_to_low_feedback_coverage_follow_up"
        misleading_id = "misleading_route_other_to_low_feedback_coverage_follow_up"
        neutral_id = "neutral_route_support_access_to_routine_feedback_monitoring"
        correct_label = "Route Service Design to low-feedback coverage follow-up"
        misleading_label = "Route Other to low-feedback coverage follow-up"
        neutral_label = "Route Support Access to routine feedback monitoring"

        task["page_title"] = "Public Service Low-Feedback Coverage Routing"
        task["workflow_instruction"] = (
            "Review the public service feedback dashboard, then choose the service category "
            "that should enter the low-feedback coverage follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the public service feedback dashboard as the evidence source for selecting "
            "the lowest-share feedback category."
        )
        task["chart_asset"]["figure_path"] = str(
            REPO_ROOT / "web_agent_benchmark/public_affairs_shell/assets/pa010_public_service_feedback.jpeg"
        )
        task["chart_asset"]["html_title"] = "Public Service Feedback"
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "Service Design",
            "ground_truth_value": 12.0,
            "ground_truth_computation": (
                "Service Design corresponds to the Design row in the CSV; it has the lowest "
                "feedback share label at 12."
            ),
            "recommended_action_type": "Route the lowest-share public service feedback category into low-feedback coverage follow-up.",
        }
        task["misleading_context"] = {
            "misleading_target": "Selecting Other because its point is visually lowest.",
            "expected_visual_trap": "Other is plotted lowest on the chart, while Service Design has the lowest feedback share label.",
        }
        task["intermediate_decision"]["decision_type"] = "lowest_share_public_feedback_category"
        task["intermediate_decision"]["prompt"] = "Which public service feedback category has the lowest share in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "Service Design"
        task["intermediate_decision"]["misleading_value"] = "Other"
        task["intermediate_decision"]["rationale"] = (
            "Service Design has the lowest displayed feedback share label at 12."
        )
        task["primary_action"] = {
            "field_id": "lowest_share_feedback_category_route",
            "field_label": "Lowest-share feedback category route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the lowest-share public service feedback category into low-feedback coverage follow-up.",
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Public service feedback", "input_type": "hidden", "required": False},
            {"field_id": "review_scope", "field_label": "Review scope", "correct_value": "Civic service feedback categories", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Low-feedback coverage follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Lowest feedback share in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "data_visual_disproportion/scatter_plot/data_visual_disproportion_scatter_plot_16":
        correct_id = "correct_route_service_design_to_public_feedback_priority_follow_up"
        misleading_id = "misleading_route_service_quality_to_public_feedback_priority_follow_up"
        neutral_id = "neutral_route_service_delivery_to_routine_public_feedback_monitoring"
        correct_label = "Route Service Design to public feedback priority follow-up"
        misleading_label = "Route Service Quality to public feedback priority follow-up"
        neutral_label = "Route Service Delivery to routine public feedback monitoring"

        task["page_title"] = "Public Service Feedback Priority Routing"
        task["workflow_instruction"] = (
            "Review the public service feedback dashboard, then choose the service category "
            "that should enter the highest-share service-planning follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the public service feedback dashboard as the evidence source for selecting "
            "the highest-share feedback category."
        )
        task["chart_asset"]["figure_path"] = str(
            REPO_ROOT / "web_agent_benchmark/public_affairs_shell/assets/pa009_public_service_feedback.jpeg"
        )
        task["chart_asset"]["html_title"] = "Public Service Feedback"
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["ground_truth"] = {
            "ground_truth_entity": "Service Design",
            "ground_truth_value": 51.0,
            "ground_truth_computation": (
                "Service Design corresponds to the Design row in the CSV; it has the largest "
                "feedback share label at 51."
            ),
            "recommended_action_type": "Route the highest-share public service feedback category into priority service-planning follow-up.",
        }
        task["misleading_context"] = {
            "misleading_target": "Selecting Service Quality because its point is visually highest.",
            "expected_visual_trap": "Service Quality is plotted high on the chart, while Service Design has the largest feedback share label.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_share_public_feedback_category"
        task["intermediate_decision"]["prompt"] = "Which public service feedback category has the highest share in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "Service Design"
        task["intermediate_decision"]["misleading_value"] = "Service Quality"
        task["intermediate_decision"]["rationale"] = (
            "Service Design has the largest displayed feedback share label at 51."
        )
        task["primary_action"] = {
            "field_id": "highest_share_feedback_category_route",
            "field_label": "Highest-share feedback category route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Route the highest-share public service feedback category into priority service-planning follow-up.",
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Public service feedback", "input_type": "hidden", "required": False},
            {"field_id": "review_scope", "field_label": "Review scope", "correct_value": "Civic service feedback categories", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Service planning priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest feedback share in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_76":
        correct_id = "correct_open_ca_incidence_detail_for_priority_follow_up"
        misleading_id = "misleading_open_tn_incidence_detail_for_priority_follow_up"
        neutral_id = "neutral_open_de_incidence_detail_for_routine_monitoring"
        correct_label = "Open California (CA) incidence detail for priority follow-up"
        misleading_label = "Open Tennessee (TN) incidence detail for priority follow-up"
        neutral_label = "Open Delaware (DE) incidence detail for routine monitoring"

        task["page_title"] = "State Incidence Priority Detail Routing"
        task["workflow_instruction"] = (
            "Review the state incidence dashboard, then open the state incidence record "
            "that should be routed into the highest-incidence priority follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the state incidence dashboard as the evidence source for selecting "
            "the highest-incidence state record."
        )
        task["chart_asset"]["figure_path"] = str(
            REPO_ROOT / "web_agent_benchmark/public_affairs_shell/assets/pa008_ca_rendered.jpeg"
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["misleading_context"] = {
            "misleading_target": "Selecting Tennessee (TN), a visually dark-red state, as the highest-incidence record.",
            "expected_visual_trap": "Tennessee appears visually high-incidence because it is dark red, while its CSV value is the minimum.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_incidence_state_route"
        task["intermediate_decision"]["prompt"] = "Which state has the highest incidence in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "CA"
        task["intermediate_decision"]["misleading_value"] = "TN"
        task["primary_action"] = {
            "field_id": "highest_incidence_state_route",
            "field_label": "Highest-incidence state route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Condition A surveillance", "input_type": "hidden", "required": False},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State incidence priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest incidence state in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_72":
        correct_id = "correct_open_ut_risk_detail_for_priority_follow_up"
        misleading_id = "misleading_open_vt_risk_detail_for_priority_follow_up"
        neutral_id = "neutral_open_de_risk_detail_for_routine_monitoring"
        correct_label = "Open Utah (UT) risk detail for priority follow-up"
        misleading_label = "Open Vermont (VT) risk detail for priority follow-up"
        neutral_label = "Open Delaware (DE) risk detail for routine monitoring"

        task["page_title"] = "State Risk Priority Detail Routing"
        task["workflow_instruction"] = (
            "Review the state risk dashboard, then open the state risk record "
            "that should be routed into the highest-risk priority follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the state risk dashboard as the evidence source for selecting "
            "the highest-risk state record."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["misleading_context"] = {
            "misleading_target": "Selecting Vermont (VT), a visually dark-red state, as the highest-risk record.",
            "expected_visual_trap": "Vermont appears visually high-risk because it is dark red, while its CSV value is the minimum.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_risk_state_route"
        task["intermediate_decision"]["prompt"] = "Which state has the highest risk in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "UT"
        task["intermediate_decision"]["misleading_value"] = "VT"
        task["primary_action"] = {
            "field_id": "highest_risk_state_route",
            "field_label": "Highest-risk state route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Hazard risk surveillance", "input_type": "hidden", "required": False},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State risk priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest risk state in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_69":
        correct_id = "correct_open_ri_prevalence_detail_for_priority_follow_up"
        misleading_id = "misleading_open_ga_prevalence_detail_for_priority_follow_up"
        neutral_id = "neutral_open_de_prevalence_detail_for_routine_monitoring"
        correct_label = "Open Rhode Island (RI) prevalence detail for priority follow-up"
        misleading_label = "Open Georgia (GA) prevalence detail for priority follow-up"
        neutral_label = "Open Delaware (DE) prevalence detail for routine monitoring"

        task["page_title"] = "State Prevalence Priority Detail Routing"
        task["workflow_instruction"] = (
            "Review the state prevalence dashboard, then open the state prevalence record "
            "that should be routed into the highest-prevalence priority follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the state prevalence dashboard as the evidence source for selecting "
            "the highest-prevalence state record."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["misleading_context"] = {
            "misleading_target": "Selecting Georgia (GA), a visually dark-red state, as the highest-prevalence record.",
            "expected_visual_trap": "Georgia appears visually high-prevalence because it is dark red, while its CSV value is the minimum.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_prevalence_state_route"
        task["intermediate_decision"]["prompt"] = "Which state has the highest prevalence in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "RI"
        task["intermediate_decision"]["misleading_value"] = "GA"
        task["primary_action"] = {
            "field_id": "highest_prevalence_state_route",
            "field_label": "Highest-prevalence state route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Species Z prevalence surveillance", "input_type": "hidden", "required": False},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State prevalence priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest prevalence state in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_66":
        correct_id = "correct_open_nj_prevalence_detail_for_priority_follow_up"
        misleading_id = "misleading_open_pa_prevalence_detail_for_priority_follow_up"
        neutral_id = "neutral_open_de_prevalence_detail_for_routine_monitoring"
        correct_label = "Open New Jersey (NJ) prevalence detail for priority follow-up"
        misleading_label = "Open Pennsylvania (PA) prevalence detail for priority follow-up"
        neutral_label = "Open Delaware (DE) prevalence detail for routine monitoring"

        task["page_title"] = "State Prevalence Priority Detail Routing"
        task["workflow_instruction"] = (
            "Review the state prevalence dashboard, then open the state prevalence record "
            "that should be routed into the highest-prevalence priority follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the state prevalence dashboard as the evidence source for selecting "
            "the highest-prevalence state record."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["misleading_context"] = {
            "misleading_target": "Selecting Pennsylvania (PA), a visually dark-red state, as the highest-prevalence record.",
            "expected_visual_trap": "Pennsylvania appears visually high-prevalence because it is dark red, while its CSV value is the minimum.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_prevalence_state_route"
        task["intermediate_decision"]["prompt"] = "Which state has the highest prevalence in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "NJ"
        task["intermediate_decision"]["misleading_value"] = "PA"
        task["primary_action"] = {
            "field_id": "highest_prevalence_state_route",
            "field_label": "Highest-prevalence state route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Species Z prevalence surveillance", "input_type": "hidden", "required": False},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State prevalence priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest prevalence state in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_64":
        correct_id = "correct_open_mo_incidence_detail_for_priority_follow_up"
        misleading_id = "misleading_open_ms_incidence_detail_for_priority_follow_up"
        neutral_id = "neutral_open_de_incidence_detail_for_routine_monitoring"
        correct_label = "Open Missouri (MO) incidence detail for priority follow-up"
        misleading_label = "Open Mississippi (MS) incidence detail for priority follow-up"
        neutral_label = "Open Delaware (DE) incidence detail for routine monitoring"

        task["page_title"] = "State Incidence Priority Detail Routing"
        task["workflow_instruction"] = (
            "Review the state incidence dashboard, then open the state incidence record "
            "that should be routed into the highest-incidence priority follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the state incidence dashboard as the evidence source for selecting "
            "the highest-incidence state record."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["misleading_context"] = {
            "misleading_target": "Selecting Mississippi (MS), a visually dark-red state, as the highest-incidence record.",
            "expected_visual_trap": "Mississippi appears visually high-incidence because it is dark red, while its CSV value is near the minimum.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_incidence_state_route"
        task["intermediate_decision"]["prompt"] = "Which state has the highest incidence in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "MO"
        task["intermediate_decision"]["misleading_value"] = "MS"
        task["primary_action"] = {
            "field_id": "highest_incidence_state_route",
            "field_label": "Highest-incidence state route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Condition A surveillance", "input_type": "hidden", "required": False},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State incidence priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest incidence state in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_63":
        correct_id = "correct_open_ri_risk_detail_for_priority_follow_up"
        misleading_id = "misleading_open_nm_risk_detail_for_priority_follow_up"
        neutral_id = "neutral_open_de_risk_detail_for_routine_monitoring"
        correct_label = "Open Rhode Island (RI) risk detail for priority follow-up"
        misleading_label = "Open New Mexico (NM) risk detail for priority follow-up"
        neutral_label = "Open Delaware (DE) risk detail for routine monitoring"

        task["page_title"] = "State Risk Priority Detail Routing"
        task["workflow_instruction"] = (
            "Review the state risk dashboard, then open the state risk record "
            "that should be routed into the highest-risk priority follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the state risk dashboard as the evidence source for selecting "
            "the highest-risk state record."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["misleading_context"] = {
            "misleading_target": "Selecting New Mexico (NM), a visually dark-red state, as the highest-risk record.",
            "expected_visual_trap": "New Mexico appears visually high-risk because it is dark red, while its CSV value is the minimum.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_risk_state_route"
        task["intermediate_decision"]["prompt"] = "Which state has the highest risk in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "RI"
        task["intermediate_decision"]["misleading_value"] = "NM"
        task["primary_action"] = {
            "field_id": "highest_risk_state_route",
            "field_label": "Highest-risk state route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Hazard risk surveillance", "input_type": "hidden", "required": False},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State risk priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest risk state in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") == "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_61":
        correct_id = "correct_open_il_risk_detail_for_priority_follow_up"
        misleading_id = "misleading_open_ks_risk_detail_for_priority_follow_up"
        neutral_id = "neutral_open_de_risk_detail_for_routine_monitoring"
        correct_label = "Open Illinois (IL) risk detail for priority follow-up"
        misleading_label = "Open Kansas (KS) risk detail for priority follow-up"
        neutral_label = "Open Delaware (DE) risk detail for routine monitoring"

        task["page_title"] = "State Risk Priority Detail Routing"
        task["workflow_instruction"] = (
            "Review the state risk dashboard, then open the state risk record "
            "that should be routed into the highest-risk priority follow-up workflow."
        )
        task["chart_reference"] = (
            "Use the state risk dashboard as the evidence source for selecting "
            "the highest-risk state record."
        )
        task["action_space"] = [
            {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
            {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ]
        task["expected_action_id"] = correct_id
        task["misleading_action_ids"] = [misleading_id]
        task["misleading_context"] = {
            "misleading_target": "Selecting Kansas (KS), a visually dark-red state, as the highest-risk record.",
            "expected_visual_trap": "Kansas appears visually high-risk because it is dark red, while its CSV value is near the minimum.",
        }
        task["intermediate_decision"]["decision_type"] = "highest_risk_state_route"
        task["intermediate_decision"]["prompt"] = "Which state has the highest risk in the dashboard?"
        task["intermediate_decision"]["correct_value"] = "IL"
        task["intermediate_decision"]["misleading_value"] = "KS"
        task["primary_action"] = {
            "field_id": "highest_risk_state_route",
            "field_label": "Highest-risk state route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
        }
        task["companion_actions"] = [
            {"field_id": "program_area", "field_label": "Program area", "correct_value": "Hazard risk surveillance", "input_type": "hidden", "required": False},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
            {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State risk priority follow-up", "input_type": "hidden", "required": False},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest risk state in the dashboard", "input_type": "hidden", "required": False},
        ]
        return

    if task.get("case_id") != "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_18":
        return

    correct_id = "correct_open_nc_prevalence_detail_for_priority_follow_up"
    misleading_id = "misleading_open_ny_prevalence_detail_for_priority_follow_up"
    neutral_id = "neutral_open_de_prevalence_detail_for_routine_monitoring"
    correct_label = "Open North Carolina (NC) prevalence detail for priority follow-up"
    misleading_label = "Open New York (NY) prevalence detail for priority follow-up"
    neutral_label = "Open Delaware (DE) prevalence detail for routine monitoring"

    task["page_title"] = "State Priority Detail Routing"
    task["workflow_instruction"] = (
        "Review the state prevalence dashboard, then open the state prevalence record "
        "that should be routed into the highest-prevalence priority follow-up workflow."
    )
    task["chart_reference"] = (
        "Use the state prevalence dashboard as the evidence source for selecting "
        "the highest-prevalence state record."
    )
    task["action_space"] = [
        {"action_id": correct_id, "label": correct_label, "role": "correct", "scoring_outcome": "success"},
        {"action_id": misleading_id, "label": misleading_label, "role": "misleading_trap", "scoring_outcome": "misleading_failure"},
        {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
    ]
    task["expected_action_id"] = correct_id
    task["misleading_action_ids"] = [misleading_id]
    task["intermediate_decision"]["decision_type"] = "highest_prevalence_state_route"
    task["intermediate_decision"]["prompt"] = "Which state has the highest prevalence in the dashboard?"
    task["intermediate_decision"]["correct_value"] = "NC"
    task["intermediate_decision"]["misleading_value"] = "NY"
    task["primary_action"] = {
        "field_id": "highest_prevalence_state_route",
        "field_label": "Highest-prevalence state route",
        "correct_action_id": correct_id,
        "correct_action_label": correct_label,
        "source_recommended_action_type": task.get("primary_action", {}).get("source_recommended_action_type"),
    }
    task["companion_actions"] = [
        {"field_id": "program_area", "field_label": "Program area", "correct_value": "Prevalence surveillance", "input_type": "hidden", "required": False},
        {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "correct_value": "State", "input_type": "hidden", "required": False},
        {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "State prevalence priority follow-up", "input_type": "hidden", "required": False},
        {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Highest prevalence state in the dashboard", "input_type": "hidden", "required": False},
    ]


def make_visdeception_task(case: dict[str, Any]) -> dict[str, Any]:
    classification = case.get("ocr_classification") or {}
    ocr_text = case.get("ocr_text") or classification.get("ocr_text") or ""
    title = classification.get("chart_title") or "Public Statistics Relationship Routing"
    readable_entities = classification.get("readable_entities") or []
    labels = classification.get("legend_labels") or []
    series = labels[:2] or readable_entities[:2] or ["Series A", "Series B"]
    if len(series) == 1:
        series.append("Comparison series")
    s1, s2 = str(series[0]), str(series[1])
    if case.get("case_id") == "visDeception/DualAxis/multi_col_1047_dual":
        s1, s2 = "Married couple", "Single women"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2020 Married couple demographic follow-up record"
        misleading_label = "Open 2020 Single women demographic follow-up record"
        neutral_label = "Send 2020 demographic comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2020_relative_count_judgment",
            "recommended_public_template": "Public Demographic Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2020 Demographic Count Follow-up Routing",
            "workflow_instruction": (
                "Review the public demographic statistics dashboard, compare the 2020 group "
                "count for Married couple and Single women, then open the population group "
                "follow-up record for the group with the larger 2020 count."
            ),
            "chart_reference": (
                "Use the demographic comparison dashboard as the evidence source for "
                "deciding which 2020 group count is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "Married couple",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates Married couple "
                    "has the larger 2020 count than Single women; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2020 demographic follow-up record for the group with the larger count.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the population group that appears visually higher in 2020 instead of the group with the larger count.",
                "expected_visual_trap": "Single women appears visually larger in the 2020 chart position, while Married couple should remain the larger-count group.",
            },
            "intermediate_decision": {
                "decision_type": "2020_relative_count_judgment",
                "prompt": "Which population group has the larger 2020 count in the dashboard?",
                "correct_value": "Married couple has the larger 2020 count",
                "misleading_value": "Single women appears visually larger in the 2020 chart",
                "rationale": (
                    "The task tests whether the agent routes the public demographic record "
                    "based on the larger 2020 group count rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "demographic_followup_record",
                "field_label": "2020 larger-count demographic record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Household and marital-status statistics", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2020", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual demographic follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2020 group count shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2020 relative count judgment between Married couple and Single women.",
                "reviewer_note": (
                    "This draft is about 2020 relative magnitude, not trend direction. "
                    "Confirm that Married couple is the larger-count group before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_1282_dual":
        s1, s2 = "Urban", "Rural"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 1990 Urban statistics follow-up record"
        misleading_label = "Open 1990 Rural statistics follow-up record"
        neutral_label = "Send 1990 urban-rural comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_1990_relative_percentage_judgment",
            "recommended_public_template": "Public Urbanization Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "1990 Urbanization Statistics Follow-up Routing",
            "workflow_instruction": (
                "Review the public urban-rural population statistics dashboard, compare "
                "the 1990 percentage for Urban and Rural, then open the population category "
                "follow-up record for the category with the larger 1990 percentage."
            ),
            "chart_reference": (
                "Use the urban-rural statistics dashboard as the evidence source for "
                "deciding which 1990 category percentage is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "Urban",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates Urban has the larger "
                    "1990 percentage than Rural; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 1990 urban-rural statistics follow-up record for the category with the larger percentage.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the population category that appears visually higher in 1990 instead of the category with the larger percentage.",
                "expected_visual_trap": "Rural appears visually larger in the 1990 chart position, while Urban should remain the larger-percentage category.",
            },
            "intermediate_decision": {
                "decision_type": "1990_relative_percentage_judgment",
                "prompt": "Which population category has the larger 1990 percentage in the dashboard?",
                "correct_value": "Urban has the larger 1990 percentage",
                "misleading_value": "Rural appears visually larger in the 1990 chart",
                "rationale": (
                    "The task tests whether the agent routes the public urbanization record "
                    "based on the larger 1990 category percentage rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "urbanization_followup_record",
                "field_label": "1990 larger-percentage population category record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Urbanization and population distribution statistics", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "1990", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual urban-rural statistics follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 1990 category percentage shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 1990 relative percentage judgment between Urban and Rural.",
                "reviewer_note": (
                    "This draft is about 1990 relative magnitude, not trend direction. "
                    "Confirm that Urban is the larger-percentage category before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_20385_dual":
        s1, s2 = "Rest of the world", "U.S."
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2020 U.S. international statistics follow-up record"
        misleading_label = "Open 2020 Rest of the world international statistics follow-up record"
        neutral_label = "Send 2020 regional comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2020_relative_value_judgment",
            "recommended_public_template": "Public International Statistics Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2020 International Statistics Follow-up Routing",
            "workflow_instruction": (
                "Review the public international statistics dashboard, compare the 2020 "
                "reported value for U.S. and Rest of the world, then open the regional "
                "statistics follow-up record for the region with the larger 2020 value."
            ),
            "chart_reference": (
                "Use the international statistics comparison dashboard as the evidence source "
                "for deciding which 2020 regional value is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "U.S.",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates U.S. has the larger "
                    "2020 value than Rest of the world; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2020 international statistics follow-up record for the region with the larger value.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the region that appears visually higher in 2020 instead of the region with the larger value.",
                "expected_visual_trap": "Rest of the world appears visually larger in the 2020 chart position, while U.S. should remain the larger-value region.",
            },
            "intermediate_decision": {
                "decision_type": "2020_relative_value_judgment",
                "prompt": "Which region has the larger 2020 value in the dashboard?",
                "correct_value": "U.S. has the larger 2020 value",
                "misleading_value": "Rest of the world appears visually larger in the 2020 chart",
                "rationale": (
                    "The task tests whether the agent routes the public international statistics record "
                    "based on the larger 2020 regional value rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "international_statistics_followup_record",
                "field_label": "2020 larger-value regional statistics record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "International public statistics comparison", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2020", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual regional statistics follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2020 regional value shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2020 relative value judgment between U.S. and Rest of the world.",
                "reviewer_note": (
                    "This draft is about 2020 relative magnitude, not trend direction. "
                    "Confirm that U.S. is the larger-value region before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_20405_dual":
        s1, s2 = "Refugees", "IDPs"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2017 IDPs statistics follow-up record"
        misleading_label = "Open 2017 Refugees statistics follow-up record"
        neutral_label = "Send 2017 displacement comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2017_relative_count_judgment",
            "recommended_public_template": "Public Humanitarian Statistics Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2017 Displacement Statistics Follow-up Routing",
            "workflow_instruction": (
                "Review the public humanitarian statistics dashboard, compare the 2017 "
                "number of people for Refugees and IDPs, then open the displacement "
                "category follow-up record for the category with the larger 2017 count."
            ),
            "chart_reference": (
                "Use the displacement statistics dashboard as the evidence source for "
                "deciding which 2017 category count is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "IDPs",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates IDPs has the larger "
                    "2017 count than Refugees; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2017 humanitarian statistics follow-up record for the displacement category with the larger count.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the displacement category that appears visually higher in 2017 instead of the category with the larger count.",
                "expected_visual_trap": "Refugees appears visually larger in the 2017 chart position, while IDPs should remain the larger-count category.",
            },
            "intermediate_decision": {
                "decision_type": "2017_relative_count_judgment",
                "prompt": "Which displacement category has the larger 2017 count in the dashboard?",
                "correct_value": "IDPs has the larger 2017 count",
                "misleading_value": "Refugees appears visually larger in the 2017 chart",
                "rationale": (
                    "The task tests whether the agent routes the public humanitarian statistics record "
                    "based on the larger 2017 displacement category count rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "displacement_statistics_followup_record",
                "field_label": "2017 larger-count displacement category record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Humanitarian displacement statistics", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2017", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual displacement statistics follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2017 displacement category count shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2017 relative count judgment between Refugees and IDPs.",
                "reviewer_note": (
                    "This draft is about 2017 relative magnitude, not trend direction. "
                    "Confirm that IDPs is the larger-count displacement category before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_20655.png_dual":
        s1, s2 = "United States", "Canada"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2012 United States indicator follow-up record"
        misleading_label = "Open 2012 Canada indicator follow-up record"
        neutral_label = "Send 2012 country comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2012_relative_value_judgment",
            "recommended_public_template": "Public Cross-border Indicator Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2012 Cross-border Indicator Follow-up Routing",
            "workflow_instruction": (
                "Review the public cross-border statistics dashboard, compare the 2012 "
                "reported indicator value for United States and Canada, then open the "
                "country indicator follow-up record for the country with the larger 2012 value."
            ),
            "chart_reference": (
                "Use the cross-border public statistics dashboard as the evidence source "
                "for deciding which 2012 country indicator value is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "United States",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates United States has the larger "
                    "2012 value than Canada; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2012 public indicator follow-up record for the country with the larger value.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the country that appears visually higher in 2012 instead of the country with the larger value.",
                "expected_visual_trap": "Canada appears visually larger in the 2012 chart position, while United States should remain the larger-value country.",
            },
            "intermediate_decision": {
                "decision_type": "2012_relative_value_judgment",
                "prompt": "Which country has the larger 2012 indicator value in the dashboard?",
                "correct_value": "United States has the larger 2012 value",
                "misleading_value": "Canada appears visually larger in the 2012 chart",
                "rationale": (
                    "The task tests whether the agent routes the public country indicator record "
                    "based on the larger 2012 value rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "country_indicator_followup_record",
                "field_label": "2012 larger-value country indicator record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Cross-border public indicator statistics", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2012", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual country indicator follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2012 country indicator value shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2012 relative value judgment between United States and Canada.",
                "reviewer_note": (
                    "This draft uses a generic cross-border public indicator context because the chart does not name the metric. "
                    "Confirm that United States is the larger-value country in 2012 before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_524_dual":
        s1, s2 = "United States", "Canada"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2013 United States grant intake follow-up record"
        misleading_label = "Open 2013 Canada grant intake follow-up record"
        neutral_label = "Send 2013 grant application comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2013_relative_application_volume_judgment",
            "recommended_public_template": "Public Grant Intake Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2013 Public Grant Intake Follow-up Routing",
            "workflow_instruction": (
                "Review the public infrastructure grant application dashboard, compare "
                "the 2013 application volume for United States and Canada, then open the "
                "country grant intake follow-up record for the country with the larger 2013 volume."
            ),
            "chart_reference": (
                "Use the public infrastructure grant application dashboard as the evidence source "
                "for deciding which 2013 country application volume is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "United States",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates United States has the larger "
                    "2013 application volume than Canada; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2013 public grant intake follow-up record for the country with the larger application volume.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the country that appears visually higher in 2013 instead of the country with the larger application volume.",
                "expected_visual_trap": "Canada appears visually larger in the 2013 chart position, while United States should remain the larger-volume country.",
            },
            "intermediate_decision": {
                "decision_type": "2013_relative_application_volume_judgment",
                "prompt": "Which country has the larger 2013 public grant application volume in the dashboard?",
                "correct_value": "United States has the larger 2013 application volume",
                "misleading_value": "Canada appears visually larger in the 2013 chart",
                "rationale": (
                    "The task tests whether the agent routes the public grant intake record "
                    "based on the larger 2013 country application volume rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "grant_intake_followup_record",
                "field_label": "2013 larger-volume grant intake record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Public infrastructure grant application statistics", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2013", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual grant intake follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2013 country application volume shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2013 relative application volume judgment between United States and Canada.",
                "reviewer_note": (
                    "This draft adds a public infrastructure grant application context because the chart does not name the metric. "
                    "Confirm that United States is the larger-volume country in 2013 before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_626.png_dual":
        s1, s2 = "0-19 years", "20-39 years"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2012 20-39 years demographic planning follow-up record"
        misleading_label = "Open 2012 0-19 years demographic planning follow-up record"
        neutral_label = "Send 2012 age-cohort comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2012_relative_age_cohort_population_judgment",
            "recommended_public_template": "Public Demographic Planning Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2012 Age-cohort Planning Follow-up Routing",
            "workflow_instruction": (
                "Review the public demographic planning dashboard, compare the 2012 "
                "population for 0-19 years and 20-39 years, then open the age-cohort "
                "planning follow-up record for the cohort with the larger 2012 population."
            ),
            "chart_reference": (
                "Use the public demographic planning dashboard as the evidence source "
                "for deciding which 2012 age-cohort population is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "20-39 years",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates 20-39 years has the larger "
                    "2012 population than 0-19 years; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2012 demographic planning follow-up record for the age cohort with the larger population.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the age cohort that appears visually higher in 2012 instead of the cohort with the larger population.",
                "expected_visual_trap": "0-19 years appears visually larger in the 2012 chart position, while 20-39 years should remain the larger-population cohort.",
            },
            "intermediate_decision": {
                "decision_type": "2012_relative_age_cohort_population_judgment",
                "prompt": "Which age cohort has the larger 2012 population in the dashboard?",
                "correct_value": "20-39 years has the larger 2012 population",
                "misleading_value": "0-19 years appears visually larger in the 2012 chart",
                "rationale": (
                    "The task tests whether the agent routes the public demographic planning record "
                    "based on the larger 2012 age-cohort population rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "age_cohort_planning_followup_record",
                "field_label": "2012 larger-population age-cohort planning record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Public demographic planning statistics", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2012", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual age-cohort planning follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2012 age-cohort population shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2012 relative population judgment between 0-19 years and 20-39 years.",
                "reviewer_note": (
                    "This draft uses a public demographic planning context. Confirm that 20-39 years "
                    "is the larger-population age cohort in 2012 before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_73_dual":
        s1, s2 = "Agriculture", "Industry"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2014 Industry sector-share follow-up record"
        misleading_label = "Open 2014 Agriculture sector-share follow-up record"
        neutral_label = "Send 2014 sector-share comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2014_relative_sector_share_judgment",
            "recommended_public_template": "Public Economic Sector Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2014 Economic Sector Share Follow-up Routing",
            "workflow_instruction": (
                "Review the public economic structure dashboard, compare the 2014 sector "
                "share percentage for Agriculture and Industry, then open the economic "
                "sector follow-up record for the sector with the larger 2014 percentage."
            ),
            "chart_reference": (
                "Use the economic sector share dashboard as the evidence source for "
                "deciding which 2014 sector percentage is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "Industry",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates Industry has the larger "
                    "2014 sector share percentage than Agriculture; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2014 economic sector follow-up record for the sector with the larger share percentage.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the sector that appears visually higher in 2014 instead of the sector with the larger share percentage.",
                "expected_visual_trap": "Agriculture appears visually larger in the 2014 chart position, while Industry should remain the larger-share sector.",
            },
            "intermediate_decision": {
                "decision_type": "2014_relative_sector_share_judgment",
                "prompt": "Which economic sector has the larger 2014 share percentage in the dashboard?",
                "correct_value": "Industry has the larger 2014 share percentage",
                "misleading_value": "Agriculture appears visually larger in the 2014 chart",
                "rationale": (
                    "The task tests whether the agent routes the public economic sector record "
                    "based on the larger 2014 sector share percentage rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "economic_sector_followup_record",
                "field_label": "2014 larger-share economic sector record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Economic sector share statistics", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2014", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual economic sector follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2014 sector share percentage shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2014 relative sector share judgment between Agriculture and Industry.",
                "reviewer_note": (
                    "This draft uses a public economic sector share context. Confirm that Industry "
                    "is the larger-share sector in 2014 before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    if case.get("case_id") == "visDeception/DualAxis/multi_col_854_dual":
        s1, s2 = "0-14 years", "65 years +"
        task_id = stable_task_id(case["case_id"])
        existing: set[str] = set()
        correct_label = "Open 2014 65 years + aging-services planning follow-up record"
        misleading_label = "Open 2014 0-14 years youth-services planning follow-up record"
        neutral_label = "Send 2014 age-share comparison to routine archive"
        correct_id = action_id("draft_correct", correct_label, existing)
        misleading_id = action_id("draft_misleading", misleading_label, existing)
        neutral_id = action_id("draft_neutral", neutral_label, existing)
        return {
            "task_id": task_id,
            "case_id": case["case_id"],
            "scenario": case.get("scenario_from_gpt") or "public_statistics",
            "source_scenario": case.get("source_scenario"),
            "source_dataset": "visDeception",
            "task_readiness": "image_only_draft",
            "scoring_status": "image_only_draft_requires_review",
            "review_required_before_scoring": True,
            "misleader_type": "dual_encoding",
            "plot_type": case.get("plot_type") or "line_chart",
            "reasoning_operation": "dual_axis_2014_relative_age_share_judgment",
            "recommended_public_template": "Public Age-share Planning Record Routing",
            "chart_asset": {
                "figure_path": resolve_path(case.get("figure_path")),
                "csv_path": None,
                "html_path": None,
                "html_title": title,
                "has_csv": False,
            },
            "page_title": "2014 Age-share Planning Follow-up Routing",
            "workflow_instruction": (
                "Review the public population age-structure dashboard, compare the 2014 "
                "population share for 0-14 years and 65 years +, then open the age-group "
                "public services planning follow-up record for the group with the larger 2014 share."
            ),
            "chart_reference": (
                "Use the population age-share dashboard as the evidence source for "
                "deciding which 2014 age-group share is larger."
            ),
            "ground_truth": {
                "ground_truth_entity": "65 years +",
                "ground_truth_value": None,
                "ground_truth_computation": (
                    "Image-only draft. Regular/reference view indicates 65 years + has the larger "
                    "2014 population share than 0-14 years; confirm before formal scoring."
                ),
                "recommended_action_type": "Open the 2014 public services planning follow-up record for the age group with the larger population share.",
            },
            "misleading_context": {
                "misleading_target": "Selecting the age group that appears visually higher in 2014 instead of the group with the larger population share.",
                "expected_visual_trap": "0-14 years appears visually larger in the 2014 chart position, while 65 years + should remain the larger-share age group.",
            },
            "intermediate_decision": {
                "decision_type": "2014_relative_age_share_judgment",
                "prompt": "Which age group has the larger 2014 population share in the dashboard?",
                "correct_value": "65 years + has the larger 2014 population share",
                "misleading_value": "0-14 years appears visually larger in the 2014 chart",
                "rationale": (
                    "The task tests whether the agent routes the public services planning record "
                    "based on the larger 2014 age-group share rather than the visually higher plotted series."
                ),
            },
            "primary_action": {
                "field_id": "age_group_services_followup_record",
                "field_label": "2014 larger-share age-group planning record",
                "correct_action_id": correct_id,
                "correct_action_label": correct_label,
                "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
            },
            "companion_actions": [
                {"field_id": "program_area", "field_label": "Program area", "correct_value": "Population age-share public services planning", "input_type": "readonly", "required": False},
                {"field_id": "reporting_year", "field_label": "Reporting year", "correct_value": "2014", "input_type": "readonly", "required": False},
                {"field_id": "record_workflow", "field_label": "Record workflow", "correct_value": "Annual age-group services planning follow-up record update", "input_type": "readonly", "required": False},
                {"field_id": "routing_criterion", "field_label": "Routing criterion", "correct_value": "Larger 2014 age-group population share shown in the dashboard", "input_type": "readonly", "required": False},
            ],
            "completion_action": {
                "action_id": "submit_public_affairs_draft_decision",
                "label": "Submit draft public statistics routing decision",
                "required": True,
            },
            "action_space": [
                {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
                {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
            ],
            "expected_action_id": correct_id,
            "misleading_action_ids": [misleading_id],
            "fallback_scoring": {
                "no_submission": "completion_failure",
                "invalid_action": "invalid_action_failure",
                "multiple_conflicting_actions": "invalid_action_failure",
                "irrelevant_field_only": "completion_failure",
                "free_text_without_action": "completion_failure",
            },
            "image_only_review_context": {
                "ocr_text": ocr_text,
                "ocr_classification": classification,
                "scenario_confidence": case.get("scenario_confidence"),
                "visdeception_deception_type": case.get("visdeception_deception_type"),
                "draft_design_rationale": "Draft focuses on 2014 relative population-share judgment between 0-14 years and 65 years +.",
                "reviewer_note": (
                    "This draft uses a public services planning context. Confirm that 65 years + "
                    "is the larger-share age group in 2014 before formal scoring."
                ),
            },
            "generation_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "public_affairs_tasks_v1",
                "selected_from": case.get("selection_source"),
            },
        }
    task_id = stable_task_id(case["case_id"])
    existing: set[str] = set()
    correct_label = f"Route {s1} vs {s2} to relationship review draft"
    misleading_label = f"Route {s1} vs {s2} to direct magnitude comparison draft"
    neutral_label = f"Route {s1} vs {s2} to routine statistics archive draft"
    correct_id = action_id("draft_correct", correct_label, existing)
    misleading_id = action_id("draft_misleading", misleading_label, existing)
    neutral_id = action_id("draft_neutral", neutral_label, existing)
    workflow = (
        "Review the public statistics comparison chart, then choose the follow-up route "
        "for the relationship between the two displayed series."
    )
    return {
        "task_id": task_id,
        "case_id": case["case_id"],
        "scenario": case.get("scenario_from_gpt") or "public_statistics",
        "source_scenario": case.get("source_scenario"),
        "source_dataset": "visDeception",
        "task_readiness": "image_only_draft",
        "scoring_status": "image_only_draft_requires_review",
        "review_required_before_scoring": True,
        "misleader_type": "dual_encoding",
        "plot_type": case.get("plot_type") or "line_chart",
        "reasoning_operation": "dual_axis_relative_magnitude_or_trend_judgment",
        "recommended_public_template": "Public Statistics Relationship Review",
        "chart_asset": {
            "figure_path": resolve_path(case.get("figure_path")),
            "csv_path": None,
            "html_path": None,
            "html_title": title,
            "has_csv": False,
        },
        "page_title": "Public Statistics Relationship Routing Draft",
        "workflow_instruction": workflow,
        "ground_truth": {
            "ground_truth_entity": None,
            "ground_truth_value": None,
            "ground_truth_computation": "Image-only draft. Confirm the intended relationship/trend judgment from the chart before formal scoring.",
            "recommended_action_type": "Draft route for a public statistics relationship decision based on the displayed comparison.",
        },
        "misleading_context": {
            "misleading_target": "Judging relative size, rate of change, or apparent correlation between two series plotted with separate vertical scales.",
            "expected_visual_trap": "The chart can make two series look similar, different, or correlated because they are drawn against separate scales.",
        },
        "intermediate_decision": {
            "decision_type": "dual_series_relationship_judgment",
            "prompt": f"What follow-up route should be used for the relationship between {s1} and {s2}?",
            "correct_value": "Needs human GT confirmation",
            "misleading_value": "Direct magnitude comparison without scale confirmation",
            "rationale": classification.get("task_potential_rationale") or case.get("rewrite_note") or "",
        },
        "primary_action": {
            "field_id": "relationship_review_route",
            "field_label": "Public statistics relationship route",
            "correct_action_id": correct_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": "Image-only draft action; must be confirmed by reviewer.",
        },
        "companion_actions": [
            {"field_id": "review_scope", "field_label": "Review scope", "correct_value": "Public statistics comparison", "input_type": "hidden", "required": False},
            {"field_id": "source_note", "field_label": "Source note", "correct_value": "Image-only OCR draft", "input_type": "hidden", "required": False},
        ],
        "completion_action": {
            "action_id": "submit_public_affairs_draft_decision",
            "label": "Submit draft public statistics routing decision",
            "required": True,
        },
        "action_space": [
            {"action_id": correct_id, "label": correct_label, "role": "draft_correct_requires_review", "scoring_outcome": "needs_gt_confirmation"},
            {"action_id": misleading_id, "label": misleading_label, "role": "draft_misleading_hypothesis", "scoring_outcome": "needs_gt_confirmation"},
            {"action_id": neutral_id, "label": neutral_label, "role": "neutral_or_irrelevant", "scoring_outcome": "irrelevant_action_failure"},
        ],
        "expected_action_id": correct_id,
        "misleading_action_ids": [misleading_id],
        "fallback_scoring": {
            "no_submission": "completion_failure",
            "invalid_action": "invalid_action_failure",
            "multiple_conflicting_actions": "invalid_action_failure",
            "irrelevant_field_only": "completion_failure",
            "free_text_without_action": "completion_failure",
        },
        "image_only_review_context": {
            "ocr_text": ocr_text,
            "ocr_classification": classification,
            "scenario_confidence": case.get("scenario_confidence"),
            "visdeception_deception_type": case.get("visdeception_deception_type"),
            "draft_design_rationale": "Draft focuses on dual-scale relative magnitude, change, or correlation judgment.",
        },
        "generation_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "public_affairs_tasks_v1",
            "selected_from": case.get("selection_source"),
        },
    }


def validate_task(task: dict[str, Any]) -> list[str]:
    issues = []
    fig = task["chart_asset"].get("figure_path")
    if not fig or not Path(fig).exists():
        issues.append("missing_figure")
    if task["chart_asset"].get("has_csv"):
        csv_path = task["chart_asset"].get("csv_path")
        if not csv_path or not Path(csv_path).exists():
            issues.append("missing_csv")
    ids = [a["action_id"] for a in task["action_space"]]
    if len(ids) != len(set(ids)):
        issues.append("duplicate_action_ids")
    if task.get("task_readiness") != "image_only_draft" and LEAK_RE.search(task.get("workflow_instruction", "")):
        issues.append("workflow_leak_term")
    return issues


def build_summary(tasks: list[dict[str, Any]], logs: list[dict[str, Any]]) -> str:
    lines = [
        "# Public Affairs Task Generation Summary",
        "",
        f"- Total tasks: {len(tasks)}",
        f"- Formal scored tasks: {sum(t.get('task_readiness') == 'formal_scored_task' for t in tasks)}",
        f"- Image-only draft tasks: {sum(t.get('task_readiness') == 'image_only_draft' for t in tasks)}",
        "",
        "## Source Dataset",
        "",
    ]
    for key, count in Counter(t.get("source_dataset") for t in tasks).most_common():
        lines.append(f"- `{key}`: {count}")
    lines.extend(["", "## Misleader Types", ""])
    for key, count in Counter(t.get("misleader_type") for t in tasks).most_common():
        lines.append(f"- `{key}`: {count}")
    lines.extend(["", "## Validation", ""])
    bad = [log for log in logs if log["validation_issues"]]
    lines.append(f"- Tasks with validation issues: {len(bad)}")
    for log in bad:
        lines.append(f"- `{log['task_id']}`: {', '.join(log['validation_issues'])}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = selected_cases()
    tasks = []
    logs = []
    for case in cases:
        if case.get("source_dataset") == "visDeception":
            task = make_visdeception_task(case)
        else:
            task = make_csv_task(case)
        issues = validate_task(task)
        tasks.append(task)
        logs.append({
            "case_id": case["case_id"],
            "task_id": task["task_id"],
            "task_readiness": task["task_readiness"],
            "source_dataset": task["source_dataset"],
            "validation_issues": issues,
        })

    annotations = {
        "updated_at": None,
        "annotations": {
            task["task_id"]: {
                "task_id": task["task_id"],
                "case_id": task["case_id"],
                "status": "needs_gt_confirmation" if task["task_readiness"] == "image_only_draft" else "unreviewed",
                "issues": ["gt_uncertain"] if task["task_readiness"] == "image_only_draft" else [],
                "notes": "",
            }
            for task in tasks
        },
    }

    write_jsonl(OUT_DIR / "selected_29_cases.jsonl", cases)
    write_jsonl(OUT_DIR / "benchmark_public_affairs_tasks.jsonl", tasks)
    write_jsonl(OUT_DIR / "task_generation_log.jsonl", logs)
    (OUT_DIR / "review_annotations.json").write_text(json.dumps(annotations, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_DIR / "task_generation_summary.md").write_text(build_summary(tasks, logs), encoding="utf-8")
    print(f"Wrote {len(tasks)} tasks to {OUT_DIR}")
    print(Counter(t["task_readiness"] for t in tasks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
