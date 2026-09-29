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


OUT_DIR = REPO_ROOT / "web_agent_benchmark/health_tasks"
GALLERY_POOL = REPO_ROOT / "web_agent_benchmark/health_expansion/gallery_pool.jsonl"
GALLERY_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark/health_expansion/gallery_annotations.json"
GALLERY_SELECTED = REPO_ROOT / "web_agent_benchmark/health_expansion/gallery_selected_candidates.jsonl"
GALLERY_SELECTED_SUMMARY = REPO_ROOT / "web_agent_benchmark/health_expansion/gallery_review_summary.md"

SELECTED_CASES_OUT = OUT_DIR / "selected_health_cases.jsonl"
TASKS_OUT = OUT_DIR / "benchmark_health_tasks.jsonl"
GEN_LOG_OUT = OUT_DIR / "task_generation_log.jsonl"
SUMMARY_OUT = OUT_DIR / "task_generation_summary.md"
ANNOTATIONS_OUT = OUT_DIR / "review_annotations.json"
IMAGE_ONLY_DRAFTS_OUT = OUT_DIR / "image_only_gpt_drafts.jsonl"
IMAGE_ONLY_FAILURES_OUT = OUT_DIR / "image_only_gpt_failures.jsonl"

TARGET_SCENARIO = "health"
SOURCE_SCENARIO = "health_environment"
LEAK_RE = re.compile(
    r"\b(ground truth|true value|actual value|correct|neutral|misleading|success|misleading_failure|dual axis|inverted axis)\b",
    re.I,
)

IMAGE_ONLY_SYSTEM_PROMPT = """You design web-agent benchmark tasks for the Health / Public Health / Clinical Care domain.
Return strict JSON only. Do not include Markdown fences.

Important constraints:
- The task must be a downstream web action task, not a pure chart QA question.
- The task must use only Health / Public Health / Clinical Care semantics.
- The task must not mention dual axis, inverted axis, misleading, ground truth, true value, or actual value in agent-visible text.
- For dual-axis style comparison charts, focus on relative size, category dominance, or pairwise comparison misread.
- For inverted-axis style charts, focus on high/low reversal or direction reversal.
- For aspect-ratio distortion charts, focus on overstatement or understatement of change magnitude, burden, or risk intensity.
- Action options must be parallel and realistic downstream web actions.
- Agent-visible text must be in English.
"""

IMAGE_ONLY_USER_PROMPT = """Design one draft task for this chart image.

Known source dataset: visDeception
Known target scenario: Health / Public Health / Clinical Care
Known deception family: {deception_type}
Known case id: {case_id}
Known OCR text:
{ocr_text}

Classification context:
{classification_json}

Return exactly this JSON schema:
{{
  "chart_understanding": "brief description of what the chart compares",
  "ocr_text": "best effort OCR text",
  "entities": ["entity 1", "entity 2", "optional entity 3"],
  "metric_definition": "what the metric means in the health context",
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
    {{"field_label": "Record workflow", "value": "..." }}
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
    return f"health_task_{digest}_{slugify(case_id.split('/')[-1], 48)}"


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


def make_companion(field_pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "field_id": slugify(label),
            "field_label": label,
            "correct_value": sanitize_agent_text(value),
            "input_type": "readonly",
            "required": False,
        }
        for label, value in field_pairs
    ]


def title_text(case: dict[str, Any]) -> str:
    return str(case.get("html_title") or case.get("title_or_subject") or case.get("case_id") or "").strip()


def strip_parenthetical(text: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*", " ", text).strip()


def sentence_case_label(text: str) -> str:
    clean = strip_parenthetical(text).strip()
    return clean or "record"


def review_scope_from_csv(case: dict[str, Any], rows: list[dict[str, str]]) -> str:
    headers = list(rows[0].keys()) if rows else []
    if "year" in headers:
        years = [row.get("year", "").strip() for row in rows if row.get("year")]
        if years:
            return f"{years[0]}-{years[-1]} trend review"
    return f"{sentence_case_label(title_text(case))} review"


def render_selected_summary(rows: list[dict[str, Any]]) -> str:
    misleader_counts = Counter(row.get("misleader_type") for row in rows)
    plot_counts = Counter(row.get("plot_type") for row in rows)
    source_counts = Counter(row.get("include_source") for row in rows)
    dataset_counts = Counter(row.get("source_dataset") for row in rows)
    lines = [
        "# Health Gallery Review Summary",
        "",
        f"- Total selected candidates: {len(rows)}",
        "",
        "## By Misleader Type",
        "",
    ]
    for key, value in sorted(misleader_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## By Plot Type", ""]
    for key, value in sorted(plot_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## By Include Source", ""]
    for key, value in sorted(source_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## By Source Dataset", ""]
    for key, value in sorted(dataset_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Selected Case IDs", ""]
    for row in rows:
        lines.append(f"- `{row['gallery_id']}` -> `{row['case_id']}`")
    return "\n".join(lines) + "\n"


def export_selected_gallery_cases() -> list[dict[str, Any]]:
    pool = read_jsonl(GALLERY_POOL)
    annotations = load_json(GALLERY_ANNOTATIONS)
    selected = []
    for row in pool:
        ann = annotations.get(row["case_id"], {})
        if isinstance(ann, dict) and ann.get("status") == "select_for_health_task":
            item = dict(row)
            item["selection_source"] = "gallery_selected"
            item["selection_status"] = ann.get("status")
            item["selection_notes"] = ann.get("notes", "")
            selected.append(item)

    def order_key(item: dict[str, Any]) -> tuple[int, str]:
        gid = str(item.get("gallery_id") or "")
        m = re.search(r"(\d+)$", gid)
        if m:
            return (int(m.group(1)), gid)
        return (10**9, gid or item["case_id"])

    selected = sorted(selected, key=order_key)
    write_jsonl(GALLERY_SELECTED, selected)
    GALLERY_SELECTED_SUMMARY.write_text(render_selected_summary(selected), encoding="utf-8")
    return selected


def selected_cases() -> list[dict[str, Any]]:
    selected = export_selected_gallery_cases()
    return selected


def common_chart_asset(case: dict[str, Any], *, has_csv: bool) -> dict[str, Any]:
    return {
        "figure_path": resolve_path(case.get("figure_path")),
        "csv_path": resolve_path(case.get("csv_path")),
        "html_path": resolve_path(case.get("html_path")),
        "html_title": title_text(case),
        "has_csv": has_csv,
    }


def base_task(case: dict[str, Any], *, readiness: str, scoring_status: str, has_csv: bool) -> dict[str, Any]:
    return {
        "task_id": stable_task_id(case["case_id"]),
        "case_id": case["case_id"],
        "scenario": TARGET_SCENARIO,
        "source_scenario": case.get("source_scenario") or SOURCE_SCENARIO,
        "source_dataset": case.get("source_dataset", "MisleadingChartQA"),
        "target_subscenario": TARGET_SCENARIO,
        "task_readiness": readiness,
        "scoring_status": scoring_status,
        "misleader_type": case.get("misleader_type"),
        "plot_type": case.get("plot_type"),
        "reasoning_operation": case.get("reasoning_operation") or "health_visual_grounding",
        "chart_asset": common_chart_asset(case, has_csv=has_csv),
        "generation_metadata": {
            "generated_at": utc_now(),
            "generator": "health_tasks_v1",
            "selected_from": case.get("selection_source"),
            "gallery_id": case.get("gallery_id"),
            "include_source": case.get("include_source"),
        },
    }


def make_formal_task(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    task = base_task(case, readiness="formal_scored_task", scoring_status="scorable", has_csv=True)
    rows = csv_rows(case.get("csv_path"))
    subject = sentence_case_label(title_text(case))
    misleader_type = case.get("misleader_type")
    plot_type = case.get("plot_type")

    if misleader_type == "cherry_picking" and plot_type == "line_chart":
        page_title = f"{subject} Whole-period Claim Routing"
        workflow = (
            f"Review the dashboard trend segment and choose the handling route that best reflects whether the "
            f"displayed record is enough to support a whole-period growth claim for {subject.lower()}."
        )
        chart_reference = (
            f"Use the displayed trend segment as the evidence source for deciding whether the dashboard supports a "
            f"whole-period growth claim or whether the claim should be held for fuller trend review."
        )
        correct_label = f"Send the {subject.lower()} record to full-period trend verification before approving a growth claim"
        misleading_label = f"Approve a whole-period growth escalation for {subject.lower()} from the displayed rising segment"
        neutral_label = f"Archive the displayed {subject.lower()} trend segment for background reference"
        companion = make_companion([
            ("Program area", "Clinical demand monitoring" if case.get("health_topic_bucket") == "clinical_care" else "Public health surveillance"),
            ("Review scope", review_scope_from_csv(case, rows)),
            ("Record workflow", "Whole-period claim review"),
        ])
        prompt = "Does the displayed segment support a whole-period growth claim, or should the claim be held for fuller trend review?"
    elif misleader_type == "cherry_picking" and plot_type == "scatter_plot":
        page_title = f"{subject} Systemwide Claim Routing"
        workflow = (
            f"Review the displayed selected-group comparison and choose the handling route that best reflects whether "
            f"this evidence is enough to support a systemwide claim for {subject.lower()}."
        )
        chart_reference = (
            f"Use the displayed selected-group relationship as the evidence source for deciding whether a systemwide "
            f"claim should be approved now or sent for fuller population review."
        )
        correct_label = "Send the selected-group relationship to full-population review before approving a systemwide claim"
        misleading_label = "Approve a systemwide relationship claim from the displayed selected-group pattern"
        neutral_label = "Archive the selected-group comparison for background reference"
        companion = make_companion([
            ("Program area", "Clinical operations benchmarking" if case.get("health_topic_bucket") == "clinical_care" else "Public health comparison review"),
            ("Review scope", "Selected-group relationship review"),
            ("Record workflow", "Systemwide claim review"),
        ])
        prompt = "Is the selected-group pattern enough to support a systemwide claim, or should the claim go to broader review?"
    elif misleader_type == "misleading_annotations" and plot_type == "line_chart":
        page_title = f"{subject} Trend Narrative Routing"
        workflow = (
            f"Review the dashboard trend and choose the handling route that best matches the pattern supported by the "
            f"plotted values for {subject.lower()}."
        )
        chart_reference = (
            f"Use the plotted values as the evidence source for deciding whether the record supports a rising-demand "
            f"follow-up, a decline-based response, or routine monitoring."
        )
        correct_label = f"Route the {subject.lower()} record to rising-trend follow-up"
        misleading_label = f"Route the {subject.lower()} record to decline-relief follow-up"
        neutral_label = f"Keep the {subject.lower()} record on routine trend monitoring"
        companion = make_companion([
            ("Program area", "Clinical demand monitoring" if case.get("health_topic_bucket") == "clinical_care" else "Public health trend monitoring"),
            ("Review scope", review_scope_from_csv(case, rows)),
            ("Record workflow", "Trend-based handling"),
        ])
        prompt = "Do the plotted values support a rising trend, a decline trend, or only routine monitoring?"
    else:
        page_title = f"{subject} Health Review Routing"
        workflow = sanitize_agent_text(case.get("workflow_instruction") or f"Review the {subject.lower()} dashboard and choose the appropriate handling route.")
        chart_reference = "Use the dashboard values as the evidence source for the follow-up decision."
        correct_label = f"Send the {subject.lower()} record to focused review"
        misleading_label = f"Approve the displayed impression for the {subject.lower()} record"
        neutral_label = f"Archive the {subject.lower()} record for background reference"
        companion = make_companion([
            ("Program area", "Health operations review"),
            ("Review scope", review_scope_from_csv(case, rows)),
            ("Record workflow", "Health record review"),
        ])
        prompt = "Which handling route best matches what the dashboard actually supports?"

    action_space, expected_action_id, misleading_action_ids = build_action_space(correct_label, misleading_label, neutral_label)
    task.update({
        "page_title": sanitize_agent_text(page_title),
        "workflow_instruction": sanitize_agent_text(workflow),
        "chart_reference": sanitize_agent_text(chart_reference),
        "ground_truth": {
            "ground_truth_entity": case.get("ground_truth_entity"),
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": case.get("recommended_action_type"),
        },
        "misleading_context": {
            "misleading_target": sanitize_agent_text(str(case.get("expected_visual_trap") or case.get("manual_rewrite_note") or "")),
            "expected_visual_trap": case.get("expected_visual_trap"),
        },
        "intermediate_decision": {
            "decision_type": case.get("reasoning_operation") or "health_visual_grounding",
            "prompt": sanitize_agent_text(prompt),
            "correct_value": case.get("ground_truth_entity"),
            "misleading_value": sanitize_agent_text(str(case.get("expected_visual_trap") or "")),
            "rationale": case.get("expected_visual_trap") or "",
        },
        "primary_action": {
            "field_id": slugify(f"{subject} route"),
            "field_label": f"{subject} handling route",
            "correct_action_id": expected_action_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": case.get("recommended_action_type"),
        },
        "companion_actions": companion,
        "completion_action": {
            "action_id": "submit_health_routing_decision",
            "label": "Submit health routing decision",
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
    })
    task["generation_metadata"]["csv_headers"] = list(rows[0].keys()) if rows else []
    trend_routing_overrides = {
        "health_rewrite/cherry_picking_line_chart_62/hospital_screening_referral_volume": {
            "page_title": "Hospital Screening Referral Trend Routing",
            "workflow_instruction": (
                "Review the referral dashboard and choose the downstream handling route that best matches the overall "
                "trend supported by the full 2013-2020 pattern."
            ),
            "chart_reference": (
                "Use the displayed referral values across the full available period to decide whether the record supports "
                "a whole-period growth trend, only a later-interval rise that still needs observation, or an overall decline trend."
            ),
            "field_label": "Hospital screening referral trend route",
            "program_area": "Screening referral monitoring",
            "review_scope": "2013-2020 whole-period referral trend review",
            "record_workflow": "Trend-based referral routing",
        },
        "health_rewrite/cherry_picking_line_chart_62/positive_test_rate_sentinel_sites": {
            "page_title": "Sentinel Positive Test Trend Routing",
            "workflow_instruction": (
                "Review the sentinel-site dashboard and choose the downstream handling route that best matches the "
                "overall trend supported by the full 2013-2020 pattern."
            ),
            "chart_reference": (
                "Use the displayed positive-test-rate values across the full available period to decide whether the record "
                "supports a whole-period growth trend, only a later-interval rise that still needs observation, or an overall decline trend."
            ),
            "field_label": "Sentinel positive test trend route",
            "program_area": "Infection surveillance",
            "review_scope": "2013-2020 whole-period positive-test trend review",
            "record_workflow": "Trend-based surveillance routing",
        },
        "health_rewrite/cherry_picking_line_chart_62/respiratory_clinic_visits": {
            "page_title": "Respiratory Clinic Demand Trend Routing",
            "workflow_instruction": (
                "Review the clinic-demand dashboard and choose the downstream handling route that best matches the "
                "overall trend supported by the full 2013-2020 pattern."
            ),
            "chart_reference": (
                "Use the displayed clinic-visit values across the full available period to decide whether the record "
                "supports a whole-period growth trend, only a later-interval rise that still needs observation, or an overall decline trend."
            ),
            "field_label": "Respiratory clinic demand trend route",
            "program_area": "Respiratory demand monitoring",
            "review_scope": "2013-2020 whole-period clinic-demand review",
            "record_workflow": "Trend-based demand routing",
        },
        "health_rewrite/cherry_picking_line_chart_62/telehealth_followup_enrollment": {
            "page_title": "Telehealth Enrollment Trend Routing",
            "workflow_instruction": (
                "Review the telehealth enrollment dashboard and choose the downstream handling route that best matches "
                "the overall trend supported by the full 2013-2020 pattern."
            ),
            "chart_reference": (
                "Use the displayed enrollment values across the full available period to decide whether the record "
                "supports a whole-period growth trend, only a later-interval rise that still needs observation, or an overall decline trend."
            ),
            "field_label": "Telehealth enrollment trend route",
            "program_area": "Telehealth follow-up demand monitoring",
            "review_scope": "2013-2020 whole-period telehealth enrollment review",
            "record_workflow": "Trend-based telehealth routing",
        },
    }
    if case_id in trend_routing_overrides:
        cfg = trend_routing_overrides[case_id]
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route the record to continued observation because the chart supports only a later-interval rise, not a clean whole-period growth trend",
            "Route the record to whole-period growth follow-up because the chart shows an overall growth trend",
            "Route the record to decline-response review because the chart shows an overall decline trend",
        )
        task["page_title"] = cfg["page_title"]
        task["workflow_instruction"] = cfg["workflow_instruction"]
        task["chart_reference"] = cfg["chart_reference"]
        task["ground_truth"] = {
            "ground_truth_entity": "later-interval rise with flat earlier years",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "The series is flat from 2013 through 2016, then rises from 2017 through 2020. That pattern supports "
                "a later-interval increase, not a clean whole-period growth trend across the entire record."
            ),
            "recommended_action_type": "route_partial_interval_growth_record_to_continued_observation",
        }
        task["misleading_context"] = {
            "misleading_target": "treat the later rising segment as proof of a whole-period growth trend",
            "expected_visual_trap": (
                "The chart emphasizes the later rising segment, which can make a partial-period increase look like a "
                "whole-period growth trend."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "whole_period_trend_vs_partial_interval_rise",
            "prompt": (
                "Does the full 2013-2020 record support a whole-period growth trend, only a later-interval rise that "
                "needs continued observation, or an overall decline trend?"
            ),
            "correct_value": "later-interval rise with flat earlier years",
            "misleading_value": "whole-period growth trend",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"] = {
            "field_id": slugify(cfg["field_label"]),
            "field_label": cfg["field_label"],
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route the record to continued observation because the chart supports only a later-interval rise, not a clean whole-period growth trend",
            "source_recommended_action_type": "route_partial_interval_growth_record_to_continued_observation",
        }
        task["companion_actions"] = make_companion([
            ("Program area", cfg["program_area"]),
            ("Review scope", cfg["review_scope"]),
            ("Record workflow", cfg["record_workflow"]),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "health_rewrite/cherry_picking_scatter_plot_99/screening_centers_outreach_vs_referrals":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Send the highlighted-center relationship to broader screening-network review before advancing a network-wide claim",
            "Advance a network-wide screening claim from the displayed highlighted-center pattern",
            "File the highlighted-center comparison as background reference",
        )
        task["page_title"] = "Screening Outreach and Referral Evidence Routing"
        task["workflow_instruction"] = (
            "Review the outreach-hours and referral dashboard for the highlighted screening centers, then choose the "
            "handling route that best reflects whether this evidence is sufficient for a broader screening-network "
            "claim or should first move to wider review."
        )
        task["chart_reference"] = (
            "Use the displayed relationship for the highlighted screening centers to decide whether the pattern is "
            "ready for a broader screening-network claim or needs wider review first."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "highlighted-center pattern is not enough for a network-wide claim",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "The chart only shows highlighted screening centers rather than the full screening network. A strong "
                "relationship inside this selected subset is not enough to prove that the same outreach-referral "
                "pattern holds across the broader network, so the evidence should go to broader review first."
            ),
            "recommended_action_type": "send_highlighted_center_relationship_to_broader_screening_network_review",
        }
        task["misleading_context"] = {
            "misleading_target": "approve a network-wide screening claim directly from the highlighted-center pattern",
            "expected_visual_trap": (
                "The chart displays only highlighted or top screening centers, and the selected subset shows a strong "
                "relationship. That can tempt the reader to generalize the pattern to the full screening network "
                "without broader review."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "selected_subset_not_sufficient_for_network_claim",
            "prompt": (
                "Is the highlighted-center pattern sufficient to support a network-wide screening claim, or should it "
                "go to broader review first?"
            ),
            "correct_value": "broader review required",
            "misleading_value": "approve network-wide claim now",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"] = {
            "field_id": "screening_network_evidence_route",
            "field_label": "Screening network evidence route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Send the highlighted-center relationship to broader screening-network review before advancing a network-wide claim",
            "source_recommended_action_type": "send_highlighted_center_relationship_to_broader_screening_network_review",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Screening services operations"),
            ("Review scope", "Highlighted-center evidence review"),
            ("Record workflow", "Screening network evidence routing"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    if case_id == "health_rewrite/misleading_annotations_line_chart_8/declining_emergency_department_visits":
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route the emergency department visit record to rising-trend follow-up",
            "Route the emergency department visit record to decline-relief follow-up",
            "Keep the emergency department visit record on routine trend monitoring",
        )
        task["page_title"] = "Emergency Department Visit Trend Routing"
        task["workflow_instruction"] = (
            "Review the emergency department visit dashboard and choose the handling route that best matches the "
            "pattern supported by the plotted values."
        )
        task["chart_reference"] = (
            "Use the plotted visit values as the evidence source for deciding whether the record supports a rising trend, "
            "a decline trend, or routine monitoring."
        )
        task["ground_truth"] = {
            "ground_truth_entity": "upward visit trend",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "The plotted series starts near 1280 in 2012 and ends near 3240 in 2023, with several upward jumps. "
                "Despite some short dips, the overall pattern is an upward trend rather than a decline."
            ),
            "recommended_action_type": "route_emergency_visit_record_to_rising_trend_follow_up",
        }
        task["misleading_context"] = {
            "misleading_target": "treat the record as a decline trend because the chart title frames the series as declining",
            "expected_visual_trap": (
                "The title frames the series as declining even though the plotted values rise overall, which can pull "
                "the reader toward a decline interpretation before they evaluate the trend itself."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "title_claim_vs_plotted_trend_conflict",
            "prompt": "Do the plotted values support a rising trend, a decline trend, or only routine monitoring?",
            "correct_value": "upward visit trend",
            "misleading_value": "decline trend",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"] = {
            "field_id": "emergency_department_visit_trend_route",
            "field_label": "Emergency department visit trend route",
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route the emergency department visit record to rising-trend follow-up",
            "source_recommended_action_type": "route_emergency_visit_record_to_rising_trend_follow_up",
        }
        task["companion_actions"] = make_companion([
            ("Program area", "Clinical demand monitoring"),
            ("Review scope", "2012-2023 emergency department trend review"),
            ("Record workflow", "Trend-based handling"),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    misleading_title_overrides = {
        "health_rewrite/misleading_annotations_line_chart_8/declining_telehealth_followup_requests": {
            "page_title": "Telehealth Follow-up Request Trend Routing",
            "workflow_instruction": (
                "Review the telehealth follow-up request dashboard and choose the handling route that best matches "
                "the pattern supported by the plotted values."
            ),
            "chart_reference": (
                "Use the plotted request values as the evidence source for deciding whether the record supports a "
                "rising trend, a decline trend, or routine monitoring."
            ),
            "ground_truth_entity": "upward request trend",
            "ground_truth_computation": (
                "The plotted request series rises overall across the visible period. Even with short dips, the full "
                "pattern supports a rising demand trend rather than a decline."
            ),
            "field_label": "Telehealth follow-up request trend route",
            "program_area": "Telehealth demand monitoring",
            "review_scope": "Telehealth follow-up request trend review",
            "record_workflow": "Trend-based telehealth handling",
            "recommended_action_type": "route_telehealth_request_record_to_rising_trend_follow_up",
            "misleading_target": "treat the record as a decline trend because the title frames the series as declining",
        },
        "health_rewrite/misleading_annotations_line_chart_8/falling_respiratory_infection_cases": {
            "page_title": "Respiratory Infection Case Trend Routing",
            "workflow_instruction": (
                "Review the respiratory infection dashboard and choose the handling route that best matches the "
                "pattern supported by the plotted values."
            ),
            "chart_reference": (
                "Use the plotted case values as the evidence source for deciding whether the record supports a rising "
                "trend, a decline trend, or routine monitoring."
            ),
            "ground_truth_entity": "upward infection-case trend",
            "ground_truth_computation": (
                "The plotted infection-case series rises overall across the visible period. Despite short dips, the "
                "full pattern supports a rising infection trend rather than a decline."
            ),
            "field_label": "Respiratory infection case trend route",
            "program_area": "Infection surveillance",
            "review_scope": "Respiratory infection case trend review",
            "record_workflow": "Trend-based surveillance handling",
            "recommended_action_type": "route_infection_case_record_to_rising_trend_follow_up",
            "misleading_target": "treat the record as a decline trend because the title frames the series as falling",
        },
        "health_rewrite/misleading_annotations_line_chart_8/reduced_screening_referrals": {
            "page_title": "Screening Referral Trend Routing",
            "workflow_instruction": (
                "Review the screening referral dashboard and choose the handling route that best matches the pattern "
                "supported by the plotted values."
            ),
            "chart_reference": (
                "Use the plotted referral values as the evidence source for deciding whether the record supports a "
                "rising trend, a decline trend, or routine monitoring."
            ),
            "ground_truth_entity": "upward referral trend",
            "ground_truth_computation": (
                "The plotted referral series rises overall across the visible period. Even with small reversals, the "
                "full pattern supports a rising referral trend rather than a decline."
            ),
            "field_label": "Screening referral trend route",
            "program_area": "Screening referral monitoring",
            "review_scope": "Screening referral trend review",
            "record_workflow": "Trend-based referral handling",
            "recommended_action_type": "route_screening_referral_record_to_rising_trend_follow_up",
            "misleading_target": "treat the record as a decline trend because the title frames the series as reduced",
        },
    }
    if case_id in misleading_title_overrides:
        cfg = misleading_title_overrides[case_id]
        action_space, expected_action_id, misleading_action_ids = build_action_space(
            "Route the record to rising-trend follow-up",
            "Route the record to decline-relief follow-up",
            "Keep the record on routine trend monitoring",
        )
        task["page_title"] = cfg["page_title"]
        task["workflow_instruction"] = cfg["workflow_instruction"]
        task["chart_reference"] = cfg["chart_reference"]
        task["ground_truth"] = {
            "ground_truth_entity": cfg["ground_truth_entity"],
            "ground_truth_value": None,
            "ground_truth_computation": cfg["ground_truth_computation"],
            "recommended_action_type": cfg["recommended_action_type"],
        }
        task["misleading_context"] = {
            "misleading_target": cfg["misleading_target"],
            "expected_visual_trap": (
                "The title frames the series as declining even though the plotted values rise overall, which can pull "
                "the reader toward a decline interpretation before they evaluate the trend itself."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "title_claim_vs_plotted_trend_conflict",
            "prompt": "Do the plotted values support a rising trend, a decline trend, or only routine monitoring?",
            "correct_value": cfg["ground_truth_entity"],
            "misleading_value": "decline trend",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"] = {
            "field_id": slugify(cfg["field_label"]),
            "field_label": cfg["field_label"],
            "correct_action_id": expected_action_id,
            "correct_action_label": "Route the record to rising-trend follow-up",
            "source_recommended_action_type": cfg["recommended_action_type"],
        }
        task["companion_actions"] = make_companion([
            ("Program area", cfg["program_area"]),
            ("Review scope", cfg["review_scope"]),
            ("Record workflow", cfg["record_workflow"]),
        ])
        task["action_space"] = action_space
        task["expected_action_id"] = expected_action_id
        task["misleading_action_ids"] = misleading_action_ids
    return task


def normalize_image_only_draft(parsed: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    classification = case.get("classification") or {}
    entities = parsed.get("entities")
    if not isinstance(entities, list):
        entities = []

    action_options = parsed.get("action_options")
    if not isinstance(action_options, list):
        action_options = []
    roles = {"expected": None, "misleading": None, "neutral": None}
    for row in action_options:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip()
        label = sanitize_agent_text(str(row.get("label") or ""))
        if role in roles and label:
            roles[role] = label
    fallback_subject = sentence_case_label(classification.get("chart_title") or title_text(case))
    roles["expected"] = roles["expected"] or f"Route the {fallback_subject.lower()} record to the evidence-supported follow-up path"
    roles["misleading"] = roles["misleading"] or f"Route the {fallback_subject.lower()} record to the visually exaggerated alternative path"
    roles["neutral"] = roles["neutral"] or f"Archive the {fallback_subject.lower()} record for background review"

    companion_rows = parsed.get("companion_fields")
    cleaned_companion: list[tuple[str, str]] = []
    if isinstance(companion_rows, list):
        for row in companion_rows:
            if not isinstance(row, dict):
                continue
            label = str(row.get("field_label") or "").strip()
            value = sanitize_agent_text(str(row.get("value") or ""))
            if label and value and label.lower() in {"program area", "review scope", "record workflow"}:
                cleaned_companion.append((label, value))
    if len(cleaned_companion) < 3:
        default_companion = [
            ("Program area", "Clinical operations review" if case.get("health_topic_bucket") == "clinical_care" else "Public health monitoring"),
            ("Review scope", "Image-based comparison review"),
            ("Record workflow", "Pairwise comparison routing"),
        ]
        for pair in default_companion:
            if pair[0] not in {x[0] for x in cleaned_companion}:
                cleaned_companion.append(pair)
        cleaned_companion = cleaned_companion[:3]

    draft = {
        "chart_understanding": sanitize_agent_text(str(parsed.get("chart_understanding") or classification.get("subject_domain") or "")),
        "ocr_text": str(parsed.get("ocr_text") or case.get("ocr_text") or classification.get("ocr_text") or "").strip(),
        "entities": [sanitize_agent_text(x) for x in entities if str(x).strip()],
        "metric_definition": sanitize_agent_text(str(parsed.get("metric_definition") or classification.get("subject_domain") or "health metric comparison")),
        "likely_ground_truth_entity": sanitize_agent_text(str(parsed.get("likely_ground_truth_entity") or "")),
        "likely_misleading_entity": sanitize_agent_text(str(parsed.get("likely_misleading_entity") or "")),
        "reasoning_operation": slugify(parsed.get("reasoning_operation") or case.get("misleader_type") or "image_only_health_routing"),
        "page_title": sanitize_agent_text(str(parsed.get("page_title") or f"{fallback_subject} Review Routing")),
        "workflow_instruction": sanitize_agent_text(str(parsed.get("workflow_instruction") or f"Review the {fallback_subject.lower()} dashboard and choose the handling route that best fits the evidence shown.")),
        "chart_reference": sanitize_agent_text(str(parsed.get("chart_reference") or "Use the charted comparison as the evidence source for the downstream handling decision.")),
        "primary_action_field_label": sanitize_agent_text(str(parsed.get("primary_action_field_label") or f"{fallback_subject} handling route")),
        "action_options": [
            {"role": "expected", "label": roles["expected"]},
            {"role": "misleading", "label": roles["misleading"]},
            {"role": "neutral", "label": roles["neutral"]},
        ],
        "companion_fields": [{"field_label": label, "value": value} for label, value in cleaned_companion],
        "review_notes": str(parsed.get("review_notes") or "").strip(),
        "confidence": float(parsed.get("confidence") or 0.0),
    }
    return apply_image_only_draft_overrides(case, draft)


def apply_image_only_draft_overrides(case: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    case_id = case.get("case_id")
    if case_id == "visDeception/InvertedAxis/3146_Aggressive":
        draft = dict(draft)
        draft["page_title"] = "Annual Mortality Peak Review Routing"
        draft["workflow_instruction"] = (
            "Review the mortality dashboard and choose the follow-up route for the year with the highest mortality "
            "rate shown in the chart."
        )
        draft["chart_reference"] = (
            "Use the charted annual mortality values to identify which year reaches the highest mortality rate before "
            "selecting the review route."
        )
        draft["primary_action_field_label"] = "Highest-mortality year routing decision"
        draft["likely_ground_truth_entity"] = "2018"
        draft["likely_misleading_entity"] = "2010"
        draft["reasoning_operation"] = "highest_mortality_year_under_reversed_axis"
        draft["metric_definition"] = "Annual mortality rate by year"
        draft["action_options"] = [
            {"role": "expected", "label": "Route 2018 to annual mortality peak review"},
            {"role": "misleading", "label": "Route 2010 to annual mortality peak review"},
            {"role": "neutral", "label": "Send the mortality chart to methodology reference review"},
        ]
        draft["companion_fields"] = [
            {"field_label": "Program area", "value": "Population mortality surveillance"},
            {"field_label": "Review scope", "value": "Highest annual mortality year review"},
            {"field_label": "Record workflow", "value": "Annual mortality peak routing"},
        ]
        draft["review_notes"] = (
            "The chart uses a reversed vertical scale, so a point that appears higher on the page can correspond to a "
            "lower mortality rate. This makes the visual high point around 2010 easy to mistake for the highest "
            "mortality year, even though the true peak burden is in 2018."
        )
    if case_id == "visDeception/InvertedAxis/4127_Aggressive":
        draft = dict(draft)
        draft["page_title"] = "Case Count Trend Direction Routing"
        draft["workflow_instruction"] = (
            "Review the case-count dashboard and choose the downstream route that matches whether the reported cases "
            "are rising or declining over the period shown."
        )
        draft["chart_reference"] = (
            "Use the plotted case-count trend to decide whether the reporting period supports a rising case "
            "trajectory or a declining case trajectory before selecting the route."
        )
        draft["primary_action_field_label"] = "Case-trend direction routing decision"
        draft["likely_ground_truth_entity"] = "Rising case-count trend"
        draft["likely_misleading_entity"] = "Declining case-count trend"
        draft["reasoning_operation"] = "rising_vs_declining_case_trend_under_reversed_axis"
        draft["metric_definition"] = "Reported case count over time"
        draft["action_options"] = [
            {"role": "expected", "label": "Route the case-count record to rising-case escalation follow-up"},
            {"role": "misleading", "label": "Route the case-count record to declining-case stabilization review"},
            {"role": "neutral", "label": "Send the case-count record to background monitoring intake"},
        ]
        draft["companion_fields"] = [
            {"field_label": "Program area", "value": "Infectious disease surveillance"},
            {"field_label": "Review scope", "value": "Case-count direction review"},
            {"field_label": "Record workflow", "value": "Outbreak trend routing"},
        ]
        draft["review_notes"] = (
            "The chart uses an inverted vertical scale, so the line looks like it is moving downward even though the "
            "reported case counts are increasing over time. That can make a rising outbreak pattern look like a "
            "declining or stabilizing case trajectory."
        )
    if case_id == "visDeception/InvertedAxis/6612_Aggressive":
        draft = dict(draft)
        draft["page_title"] = "Testing Volume Trend Direction Routing"
        draft["workflow_instruction"] = (
            "Review the laboratory testing dashboard and choose the downstream route that matches whether the "
            "reported testing volume is rising or declining across the reporting period."
        )
        draft["chart_reference"] = (
            "Use the plotted testing-volume trend to determine whether the reporting period supports a rising or "
            "declining testing trajectory before selecting the route."
        )
        draft["primary_action_field_label"] = "Testing-volume direction routing decision"
        draft["likely_ground_truth_entity"] = "Rising testing-volume trend from late June to late November"
        draft["likely_misleading_entity"] = "Declining testing-volume trend"
        draft["reasoning_operation"] = "rising_vs_declining_testing_volume_under_reversed_axes"
        draft["metric_definition"] = "Number of samples tested across reporting dates"
        draft["action_options"] = [
            {"role": "expected", "label": "Route the testing-volume record to rising-volume capacity planning"},
            {"role": "misleading", "label": "Route the testing-volume record to declining-volume outreach review"},
            {"role": "neutral", "label": "Send the testing-volume record to the general laboratory dashboard"},
        ]
        draft["companion_fields"] = [
            {"field_label": "Program area", "value": "Public health laboratory testing"},
            {"field_label": "Review scope", "value": "Testing-volume direction review"},
            {"field_label": "Record workflow", "value": "Testing trend routing"},
        ]
        draft["review_notes"] = (
            "This chart reverses both reading directions: the vertical axis is inverted, so lower points represent "
            "higher values, and the reporting months should be read from right to left. If the chart is read with "
            "ordinary left-to-right time order and ordinary y-axis assumptions, an actually rising testing pattern "
            "from late June to late November can be mistaken for a decline."
        )
    if case_id == "visDeception/AspectRatio/two_col_2594_aggressive":
        draft = dict(draft)
        draft["page_title"] = "Treatment Cost Band Routing"
        draft["workflow_instruction"] = (
            "Review the specialty-treatment pricing dashboard and choose the routing action that matches the low-cost "
            "band rule used in this review. For this workflow, annual treatment costs from 0.5M to 1.0M USD are "
            "handled as low-cost specialty records."
        )
        draft["chart_reference"] = (
            "Use the charted annual treatment-cost values to decide whether Luxturna falls inside the 0.5M-1.0M USD "
            "low-cost band, rather than relying on how close the plotted value appears to the zero line."
        )
        draft["primary_action_field_label"] = "Low-cost band routing decision"
        draft["likely_ground_truth_entity"] = "Luxturna"
        draft["likely_misleading_entity"] = (
            "classify Luxturna as non-low-cost because the compressed chart makes 0.5M-1.0M values look visually substantial"
        )
        draft["reasoning_operation"] = "low_cost_band_classification_under_nonzero_axis_distortion"
        draft["metric_definition"] = "Annual specialty-treatment cost in U.S. dollars"
        draft["action_options"] = [
            {"role": "expected", "label": "Route Luxturna to the low-cost specialty band"},
            {"role": "misleading", "label": "Route Luxturna to the non-low-cost specialty band"},
            {"role": "neutral", "label": "Send Luxturna to background pricing reference review"},
        ]
        draft["companion_fields"] = [
            {"field_label": "Program area", "value": "Specialty treatment cost review"},
            {"field_label": "Review scope", "value": "Annual treatment-cost band routing"},
            {"field_label": "Record workflow", "value": "Low-cost band classification"},
        ]
        draft["review_notes"] = (
            "Luxturna is about 0.86M USD per year, so it falls inside the 0.5M-1.0M USD low-cost band used in this "
            "workflow. The y-axis does not start at zero and the compressed aspect ratio makes 0.5M-1.0M values look "
            "visually substantial, which can make a true low-band value appear not to be low."
        )
    if case_id == "visDeception/DualAxis/multi_col_20517.png_dual":
        draft = dict(draft)
        draft["page_title"] = "Adolescent Cereal Guidance Routing"
        draft["workflow_instruction"] = (
            "Review the breakfast-cereal comparison dashboard and choose the follow-up route that matches which cereal "
            "type is higher for the 11-18 years group."
        )
        draft["chart_reference"] = (
            "Use the charted comparison for the 11-18 years group to decide whether high-fibre breakfast cereals or "
            "other breakfast cereals should receive the adolescent nutrition follow-up route."
        )
        draft["primary_action_field_label"] = "11-18 years cereal guidance route"
        draft["likely_ground_truth_entity"] = "High fibre breakfast cereals for 11-18 years"
        draft["likely_misleading_entity"] = "Other breakfast cereals for 11-18 years"
        draft["reasoning_operation"] = "pairwise_comparison_for_11_18_years_under_dual_axis_distortion"
        draft["metric_definition"] = "Relative cereal-comparison level for the 11-18 years age group"
        draft["action_options"] = [
            {"role": "expected", "label": "Route high-fibre breakfast cereals for 11-18 years to adolescent fibre-support follow-up"},
            {"role": "misleading", "label": "Route other breakfast cereals for 11-18 years to adolescent fibre-support follow-up"},
            {"role": "neutral", "label": "Send the 11-18 years cereal comparison to general nutrition reference review"},
        ]
        draft["companion_fields"] = [
            {"field_label": "Program area", "value": "Adolescent nutrition guidance"},
            {"field_label": "Review scope", "value": "11-18 years cereal comparison"},
            {"field_label": "Record workflow", "value": "Pairwise cereal guidance routing"},
        ]
        draft["review_notes"] = (
            "For the 11-18 years group, the dual-axis design can make other breakfast cereals look higher than high-fibre "
            "breakfast cereals when the two series are compared visually. This task treats high-fibre breakfast cereals "
            "as the correct higher option for that age group."
        )
    if case_id == "visDeception/DualAxis/multi_col_20263_dual":
        draft = dict(draft)
        draft["page_title"] = "2017 Transplant Volume Comparison Routing"
        draft["workflow_instruction"] = (
            "Review the transplant comparison dashboard and choose the follow-up route that matches the 2017 comparison "
            "between the kidney and liver transplant programs."
        )
        draft["chart_reference"] = (
            "Use the 2017 values in the chart to determine whether the kidney transplant program is higher than the "
            "liver transplant program or whether the two programs should be treated as matched for 2017 handling."
        )
        draft["primary_action_field_label"] = "2017 transplant comparison route"
        draft["likely_ground_truth_entity"] = "Kidney is higher than liver in 2017"
        draft["likely_misleading_entity"] = "Kidney and liver appear matched in 2017"
        draft["reasoning_operation"] = "single_year_kidney_vs_liver_comparison_under_dual_axis_overlap"
        draft["metric_definition"] = "2017 transplant procedure volume comparison for kidney and liver service lines"
        draft["action_options"] = [
            {"role": "expected", "label": "Route the 2017 kidney transplant program to higher-volume follow-up"},
            {"role": "misleading", "label": "Route the 2017 transplant comparison to matched-volume review"},
            {"role": "neutral", "label": "Send the 2017 transplant comparison to background service-line review"},
        ]
        draft["companion_fields"] = [
            {"field_label": "Program area", "value": "Transplant service planning"},
            {"field_label": "Review scope", "value": "2017 kidney-versus-liver volume comparison"},
            {"field_label": "Record workflow", "value": "Service-line comparison routing"},
        ]
        draft["review_notes"] = (
            "This task focuses on the 2017 single-year comparison. The dual-axis design makes the 2017 kidney and "
            "liver endpoints look nearly overlapped, which can lead to a matched-volume impression even though kidney "
            "is actually higher than liver in 2017."
        )
    return draft


def default_image_only_draft(case: dict[str, Any]) -> dict[str, Any]:
    classification = case.get("classification") or {}
    subject = sentence_case_label(classification.get("chart_title") or title_text(case))
    misleader = case.get("misleader_type")
    if misleader == "MS_unconventional_scale_directions":
        expected = f"Route the {subject.lower()} record to the high-priority trend follow-up"
        misleading = f"Route the {subject.lower()} record to the low-priority reversal path"
        review_scope = "Direction-sensitive trend review"
        workflow = "Direction-based handling"
    elif misleader == "aspect_ratio_distortion":
        expected = f"Route the {subject.lower()} record to the larger-change follow-up"
        misleading = f"Keep the {subject.lower()} record on ordinary-change monitoring"
        review_scope = "Magnitude-sensitive trend review"
        workflow = "Magnitude-based handling"
    else:
        expected = f"Route the {subject.lower()} record to the evidence-supported follow-up path"
        misleading = f"Route the {subject.lower()} record to the visually dominant alternative path"
        review_scope = "Comparison review"
        workflow = "Comparison-based handling"
    return {
        "chart_understanding": sanitize_agent_text(str(classification.get("subject_domain") or subject)),
        "ocr_text": str(case.get("ocr_text") or classification.get("ocr_text") or "").strip(),
        "entities": classification.get("readable_entities") or [],
        "metric_definition": sanitize_agent_text(str(classification.get("y_axis_label") or classification.get("subject_domain") or "health metric comparison")),
        "likely_ground_truth_entity": "",
        "likely_misleading_entity": "",
        "reasoning_operation": slugify(misleader or "image_only_health_routing"),
        "page_title": f"{subject} Review Routing",
        "workflow_instruction": f"Review the {subject.lower()} dashboard and choose the handling route that best fits the evidence shown in the chart.",
        "chart_reference": "Use the charted comparison as the evidence source for the downstream handling decision.",
        "primary_action_field_label": f"{subject} handling route",
        "action_options": [
            {"role": "expected", "label": expected},
            {"role": "misleading", "label": misleading},
            {"role": "neutral", "label": f"Archive the {subject.lower()} record for background review"},
        ],
        "companion_fields": [
            {"field_label": "Program area", "value": "Clinical operations review" if case.get("health_topic_bucket") == "clinical_care" else "Public health monitoring"},
            {"field_label": "Review scope", "value": review_scope},
            {"field_label": "Record workflow", "value": workflow},
        ],
        "review_notes": sanitize_agent_text(str(classification.get("task_potential_rationale") or "")),
        "confidence": 0.0,
    }


def build_image_only_task(case: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    task = base_task(case, readiness="image_only_draft", scoring_status="image_only_draft_requires_review", has_csv=False)
    options = draft["action_options"]
    action_space, expected_action_id, misleading_action_ids = build_action_space(
        options[0]["label"],
        options[1]["label"],
        options[2]["label"],
    )
    task.update({
        "page_title": draft["page_title"],
        "workflow_instruction": draft["workflow_instruction"],
        "chart_reference": draft["chart_reference"],
        "ground_truth": {
            "ground_truth_entity": draft.get("likely_ground_truth_entity"),
            "ground_truth_value": None,
            "ground_truth_computation": draft.get("review_notes"),
            "recommended_action_type": case.get("classification", {}).get("possible_action_chain"),
        },
        "misleading_context": {
            "misleading_target": draft.get("likely_misleading_entity"),
            "expected_visual_trap": draft.get("review_notes"),
        },
        "intermediate_decision": {
            "decision_type": draft.get("reasoning_operation"),
            "prompt": "Which handling path best matches the evidence shown in the chart?",
            "correct_value": draft.get("likely_ground_truth_entity"),
            "misleading_value": draft.get("likely_misleading_entity"),
            "rationale": draft.get("review_notes"),
        },
        "primary_action": {
            "field_id": slugify(draft["primary_action_field_label"]),
            "field_label": draft["primary_action_field_label"],
            "correct_action_id": expected_action_id,
            "correct_action_label": options[0]["label"],
            "source_recommended_action_type": case.get("classification", {}).get("possible_action_chain"),
        },
        "companion_actions": make_companion([
            (row["field_label"], row["value"]) for row in draft.get("companion_fields", [])
        ]),
        "completion_action": {
            "action_id": "submit_health_routing_decision",
            "label": "Submit health routing decision",
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
        "review_required_before_scoring": True,
        "image_only_review_context": {
            "chart_understanding": draft.get("chart_understanding"),
            "ocr_text": draft.get("ocr_text"),
            "entities": draft.get("entities"),
            "metric_definition": draft.get("metric_definition"),
            "likely_ground_truth_entity": draft.get("likely_ground_truth_entity"),
            "likely_misleading_entity": draft.get("likely_misleading_entity"),
            "review_notes": draft.get("review_notes"),
            "confidence": draft.get("confidence"),
            "raw_classification": case.get("classification") or {},
        },
    })
    if case.get("case_id") == "visDeception/InvertedAxis/3146_Aggressive":
        task["ground_truth"] = {
            "ground_truth_entity": "2018",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "The chart uses a reversed vertical scale, so higher plotted points correspond to lower mortality "
                "rates. This makes the visual high point around 2010 easy to mistake for the highest mortality year, "
                "even though the true peak burden is in 2018."
            ),
            "recommended_action_type": "route_highest_mortality_year_to_peak_review",
        }
        task["misleading_context"] = {
            "misleading_target": "2010",
            "expected_visual_trap": (
                "The chart uses a reversed vertical scale, so a visually higher point can represent a lower mortality "
                "rate. The point around 2010 appears high on the chart and can be mistaken for the peak year, even "
                "though the actual highest mortality year is 2018."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "highest_mortality_year_under_reversed_axis",
            "prompt": "Which year has the highest mortality rate in the chart?",
            "correct_value": "2018",
            "misleading_value": "2010",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"]["source_recommended_action_type"] = "route_highest_mortality_year_to_peak_review"
    if case.get("case_id") == "visDeception/InvertedAxis/4127_Aggressive":
        task["ground_truth"] = {
            "ground_truth_entity": "Rising case-count trend",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "The chart uses a reversed vertical scale, so the line appears to move downward even while the case "
                "counts are climbing. The plotted pattern should therefore be treated as a rising case-count trend, "
                "not as a decline."
            ),
            "recommended_action_type": "route_rising_case_count_pattern_to_escalation_follow_up",
        }
        task["misleading_context"] = {
            "misleading_target": "Declining case-count trend",
            "expected_visual_trap": (
                "The inverted axis makes the line look like it is moving downward, which can be misread as a decline "
                "in cases even though the values are increasing over time."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "rising_vs_declining_case_trend_under_reversed_axis",
            "prompt": "Does the chart support a rising case-count trend or a declining case-count trend over the reporting period?",
            "correct_value": "Rising case-count trend",
            "misleading_value": "Declining case-count trend",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"]["source_recommended_action_type"] = (
            "route_rising_case_count_pattern_to_escalation_follow_up"
        )
    if case.get("case_id") == "visDeception/InvertedAxis/6612_Aggressive":
        task["ground_truth"] = {
            "ground_truth_entity": "Rising testing-volume trend from late June to late November",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "The x-axis reporting dates must be read from right to left, and the y-axis is inverted so lower "
                "points represent higher sample counts. Under the correct reading order, testing volume rises from "
                "late June to late November, so this record should follow the rising-volume capacity-planning path."
            ),
            "recommended_action_type": "route_rising_testing_volume_pattern_to_capacity_planning",
        }
        task["misleading_context"] = {
            "misleading_target": "Declining testing-volume trend",
            "expected_visual_trap": (
                "Left-to-right reading falsely suggests late-to-early chronology, and the inverted y-axis makes lower "
                "points represent higher values. Combining both mistakes can make an actually rising testing pattern "
                "look like a decline."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "rising_vs_declining_testing_volume_under_reversed_axes",
            "prompt": "Does the chart support a rising testing-volume trend or a declining testing-volume trend across the reporting period?",
            "correct_value": "Rising testing-volume trend",
            "misleading_value": "Declining testing-volume trend",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"]["source_recommended_action_type"] = (
            "route_rising_testing_volume_pattern_to_capacity_planning"
        )
    if case.get("case_id") == "visDeception/AspectRatio/two_col_2594_aggressive":
        task["ground_truth"] = {
            "ground_truth_entity": "Luxturna",
            "ground_truth_value": "~0.86M USD/year",
            "ground_truth_computation": (
                "Luxturna is about 0.86M USD per year, so it falls inside the 0.5M-1.0M USD low-cost band used in "
                "this workflow. The y-axis does not start at zero and the compressed aspect ratio makes 0.5M-1.0M "
                "values look visually substantial, which can make a true low-band value appear not to be low."
            ),
            "recommended_action_type": "route_drug_in_0_5m_to_1_0m_band_to_low_cost_specialty_path",
        }
        task["misleading_context"] = {
            "misleading_target": "classify Luxturna as non-low-cost because the chart makes 0.5M-1.0M values look visually substantial",
            "expected_visual_trap": (
                "The y-axis does not start at zero and the compressed aspect ratio makes 0.5M-1.0M values look "
                "visually substantial, which can make a true low-band value appear not to be low."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "low_cost_band_classification_under_nonzero_axis_distortion",
            "prompt": "Does Luxturna fall inside the 0.5M-1.0M USD low-cost band used in this review?",
            "correct_value": "Luxturna",
            "misleading_value": "treat Luxturna as non-low-cost because the plotted value does not look close to zero",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"]["source_recommended_action_type"] = "route_drug_in_0_5m_to_1_0m_band_to_low_cost_specialty_path"
    if case.get("case_id") == "visDeception/DualAxis/multi_col_20517.png_dual":
        task["ground_truth"] = {
            "ground_truth_entity": "High fibre breakfast cereals for 11-18 years",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "For the 11-18 years group, this task treats high-fibre breakfast cereals as the correct higher option. "
                "The dual-axis design can make other breakfast cereals look higher when the two series are compared visually."
            ),
            "recommended_action_type": "route_high_fibre_cereal_option_for_11_18_years_to_adolescent_fibre_support_follow_up",
        }
        task["misleading_context"] = {
            "misleading_target": "treat other breakfast cereals as higher for 11-18 years because the dual-axis comparison is visually misleading",
            "expected_visual_trap": (
                "The dual-axis design can distort direct comparison between the two cereal series, making other breakfast "
                "cereals appear higher than high-fibre breakfast cereals for 11-18 years."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "pairwise_comparison_for_11_18_years_under_dual_axis_distortion",
            "prompt": "For the 11-18 years group, which cereal type should receive the adolescent fibre-support follow-up route?",
            "correct_value": "High fibre breakfast cereals for 11-18 years",
            "misleading_value": "Other breakfast cereals for 11-18 years",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"]["source_recommended_action_type"] = (
            "route_high_fibre_cereal_option_for_11_18_years_to_adolescent_fibre_support_follow_up"
        )
    if case.get("case_id") == "visDeception/DualAxis/multi_col_20263_dual":
        task["ground_truth"] = {
            "ground_truth_entity": "Kidney transplants are higher than liver transplants in 2017",
            "ground_truth_value": None,
            "ground_truth_computation": (
                "This task focuses on the 2017 single-year comparison. The dual-axis design makes the kidney and "
                "liver endpoints for 2017 look nearly overlapped, which can create a matched-volume impression. "
                "Even so, the chart data still support kidney being higher than liver in 2017, so the kidney program "
                "should receive the higher-volume follow-up route."
            ),
            "recommended_action_type": "route_2017_higher_volume_kidney_program_to_follow_up",
        }
        task["misleading_context"] = {
            "misleading_target": "Treat the 2017 kidney and liver programs as matched because their endpoints look nearly overlapped",
            "expected_visual_trap": (
                "Separate left and right axes compress the apparent difference in 2017, and the two endpoints look "
                "nearly overlapped. That can make the kidney and liver programs appear matched even though kidney is "
                "actually higher."
            ),
        }
        task["intermediate_decision"] = {
            "decision_type": "single_year_kidney_vs_liver_comparison_under_dual_axis_overlap",
            "prompt": (
                "For 2017, does the chart support kidney being higher than liver, or does it only appear that the "
                "two programs are matched?"
            ),
            "correct_value": "Kidney is higher than liver in 2017",
            "misleading_value": "Kidney and liver appear matched in 2017",
            "rationale": task["misleading_context"]["expected_visual_trap"],
        }
        task["primary_action"]["source_recommended_action_type"] = (
            "route_2017_higher_volume_kidney_program_to_follow_up"
        )
    return task


def generate_image_only_draft(client: Any, case: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    classification = case.get("classification") or {}
    raw = complete_vision(
        client,
        IMAGE_ONLY_SYSTEM_PROMPT,
        IMAGE_ONLY_USER_PROMPT.format(
            deception_type=case.get("visdeception_deception_type", "unknown"),
            case_id=case["case_id"],
            ocr_text=case.get("ocr_text") or classification.get("ocr_text") or "",
            classification_json=json.dumps(classification, ensure_ascii=False, indent=2),
        ),
        resolve_path(case.get("figure_path")),
        max_output_tokens=2200,
    )
    parsed = normalize_image_only_draft(parse_json_object(raw), case)
    return parsed, raw, "gpt_generated"


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


def merge_annotations(existing: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    existing_annotations = existing.get("annotations") if isinstance(existing, dict) else {}
    if not isinstance(existing_annotations, dict):
        existing_annotations = {}
    defaults = build_default_annotations(tasks)
    merged_annotations = defaults["annotations"]
    for task in tasks:
        task_id = task["task_id"]
        prev = existing_annotations.get(task_id)
        if not isinstance(prev, dict):
            continue
        merged = dict(merged_annotations.get(task_id, {}))
        for key in ["status", "issues", "notes", "updated_at"]:
            if key in prev:
                merged[key] = prev[key]
        merged_annotations[task_id] = merged
    return {"updated_at": utc_now(), "annotations": merged_annotations}


def write_summary(tasks: list[dict[str, Any]], logs: list[dict[str, Any]]) -> None:
    misleader_counts = Counter(t.get("misleader_type") for t in tasks)
    source_counts = Counter(t.get("source_dataset") for t in tasks)
    readiness_counts = Counter(t.get("task_readiness") for t in tasks)
    validation_issues = sum(1 for row in logs if row.get("validation_issues"))
    lines = [
        "# Health Task Generation Summary",
        "",
        f"- Total tasks: {len(tasks)}",
        f"- Formal scored tasks: {readiness_counts.get('formal_scored_task', 0)}",
        f"- Image-only draft tasks: {readiness_counts.get('image_only_draft', 0)}",
        "",
        "## Source Dataset",
        "",
    ]
    for key, value in sorted(source_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Misleader Types", ""]
    for key, value in sorted(misleader_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Validation", "", f"- Tasks with validation issues: {validation_issues}"]
    SUMMARY_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    selected = selected_cases()
    if not selected:
        raise SystemExit("No selected health candidates found in health_expansion/gallery_annotations.json")

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
    if any(case.get("image_only_candidate") for case in selected):
        client = make_client()

    for case in selected:
        if case.get("has_csv") and not case.get("image_only_candidate"):
            task = make_formal_task(case)
            source_status = "formal_generated"
        else:
            draft_row = image_only_drafts_out.get(case["case_id"])
            raw_text = ""
            source_status = "image_only_cached"
            if draft_row is None:
                try:
                    parsed, raw_text, source_status = generate_image_only_draft(client, case)
                    draft_row = {
                        "case_id": case["case_id"],
                        "figure_path": resolve_path(case.get("figure_path")),
                        "generated_at": utc_now(),
                        "llm_backend": os.environ.get("LLM_BACKEND", ""),
                        "llm_model": os.environ.get("HEXIN_MODEL") or os.environ.get("OPENAI_MODEL") or "",
                        "draft": parsed,
                        "raw_text": raw_text,
                        "source_status": source_status,
                    }
                    image_only_drafts_out[case["case_id"]] = draft_row
                except Exception as exc:
                    parsed = default_image_only_draft(case)
                    raw_text = f"GPT generation failed: {exc}"
                    source_status = "image_only_fallback"
                    draft_row = {
                        "case_id": case["case_id"],
                        "figure_path": resolve_path(case.get("figure_path")),
                        "generated_at": utc_now(),
                        "llm_backend": os.environ.get("LLM_BACKEND", ""),
                        "llm_model": os.environ.get("HEXIN_MODEL") or os.environ.get("OPENAI_MODEL") or "",
                        "draft": parsed,
                        "raw_text": raw_text,
                        "source_status": source_status,
                    }
                    image_only_drafts_out[case["case_id"]] = draft_row
                    image_only_failures_out[case["case_id"]] = {
                        "case_id": case["case_id"],
                        "figure_path": resolve_path(case.get("figure_path")),
                        "failed_at": utc_now(),
                        "error": str(exc),
                        "fallback_used": True,
                    }
            parsed = normalize_image_only_draft(draft_row["draft"], case)
            draft_row["draft"] = parsed
            task = build_image_only_task(case, parsed)

        validation = validate_task(task)
        gen_logs.append({
            "task_id": task["task_id"],
            "case_id": case["case_id"],
            "task_readiness": task["task_readiness"],
            "source_status": source_status,
            "validation_issues": validation,
            "generated_at": utc_now(),
        })
        tasks.append(task)

    write_jsonl(TASKS_OUT, tasks)
    write_jsonl(GEN_LOG_OUT, gen_logs)
    write_jsonl(IMAGE_ONLY_DRAFTS_OUT, list(image_only_drafts_out.values()))
    write_jsonl(IMAGE_ONLY_FAILURES_OUT, list(image_only_failures_out.values()))
    save_json(ANNOTATIONS_OUT, merge_annotations(load_json(ANNOTATIONS_OUT), tasks))
    write_summary(tasks, gen_logs)

    print(f"[health_tasks] selected={len(selected)} tasks={len(tasks)} formal={sum(t['task_readiness']=='formal_scored_task' for t in tasks)} image_only={sum(t['task_readiness']=='image_only_draft' for t in tasks)}")
    print(f"[health_tasks] wrote {TASKS_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
