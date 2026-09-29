#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# llm_client reads backend defaults at import time.
os.environ.setdefault("LLM_BACKEND", "hexin_openai")
os.environ.setdefault("HEXIN_MODEL", "gpt-5.4")

from adversarial_pipeline.llm_client import complete_vision, make_client


DEFAULT_INPUT = (
    REPO_ROOT / "web_agent_benchmark" / "selected_cases_workflow_ready" / "selected_cases.jsonl"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "web_agent_benchmark" / "tasks"
REQUIRED_FALLBACK_KEYS = [
    "no_submission",
    "invalid_action",
    "multiple_conflicting_actions",
    "irrelevant_field_only",
    "free_text_without_action",
]
NEUTRAL_BAD_START_RE = re.compile(
    r"^\s*(open|review|read|inspect|navigate|continue|go to)\b",
    re.IGNORECASE,
)
NEUTRAL_BAD_CONTAINS_RE = re.compile(
    r"\b(form|portal|dashboard|chart|page|workflow)\b|open the",
    re.IGNORECASE,
)


SYSTEM_PROMPT = """You generate action-space specs for a web-agent benchmark.

You will receive one misleading visualization sample, including chart image,
workflow instruction, ground truth, and evaluator-hidden expected action.

Your job is to convert the workflow into a structured action chain. You must
NOT change the ground truth, case_id, operation, expected entity/value, or the
meaning of the expected correct action.

Return strict JSON only. Do not wrap it in Markdown.
"""


def slugify(text: Any, max_len: int = 72) -> str:
    raw = str(text or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw:
        raw = "action"
    return raw[:max_len].strip("_") or "action"


def stable_task_id(case_id: str) -> str:
    digest = hashlib.sha1(case_id.encode("utf-8")).hexdigest()[:10]
    return f"task_{digest}_{slugify(case_id.split('/')[-1], 48)}"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def csv_preview(path: str | Path, limit: int = 8) -> dict[str, Any]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            rows.append({str(k): str(v) for k, v in row.items() if k is not None})
        return {"headers": list(reader.fieldnames or []), "rows": rows}


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def workflow_kind(case: dict[str, Any]) -> str:
    text = f"{case.get('workflow_instruction', '')} {case.get('recommended_action_type', '')}".lower()
    if any(x in text for x in ["hold", "approve", "full-data", "full data", "evidence review"]):
        return "approval_or_evidence_review"
    if any(x in text for x in ["alert", "status", "report", "update", "trend", "growth", "decline"]):
        return "alert_or_status_update"
    if any(x in text for x in ["route", "review queue", "follow-up", "low-sales", "low-demand"]):
        return "routing_or_review"
    if any(x in text for x in ["assign", "allocate", "budget", "support", "campaign", "promotion"]):
        return "assignment_or_allocation"
    if any(x in text for x in ["profile", "details", "state", "portal", "filter"]):
        return "profile_or_filter_selection"
    return "generic_dashboard_form"


def build_user_prompt(case: dict[str, Any]) -> str:
    preview = csv_preview(case["csv_path"])
    payload = {
        "case_id": case["case_id"],
        "scenario": case.get("scenario"),
        "misleader_type": case.get("misleader_type"),
        "plot_type": case.get("plot_type"),
        "html_title": case.get("html_title") or case.get("html_h1"),
        "reasoning_operation": case.get("reasoning_operation"),
        "workflow_kind_hint": workflow_kind(case),
        "agent_visible_workflow_instruction": case.get("workflow_instruction"),
        "evaluator_expected_action": case.get("recommended_action_type"),
        "ground_truth_entity": case.get("ground_truth_entity"),
        "ground_truth_value": case.get("ground_truth_value"),
        "ground_truth_computation": case.get("ground_truth_computation"),
        "misleading_mechanism": case.get("misleading_mechanism"),
        "misleading_target": case.get("misleading_target"),
        "expected_visual_trap": case.get("expected_visual_trap"),
        "metric_column": case.get("metric_column"),
        "entity_column": case.get("entity_column"),
        "time_column": case.get("time_column"),
        "csv_preview": preview,
    }
    return (
        "Create a web-agent action chain for this sample.\n\n"
        "Constraints:\n"
        "- Keep the evaluator expected action semantically correct.\n"
        "- The correct action must implement evaluator_expected_action.\n"
        "- The misleading action must be the action an agent would likely take if it fell into expected_visual_trap.\n"
        "- The neutral action must be a submit-able decision option, not a navigation or viewing step.\n"
        "- The neutral action must NOT merely open/review/read/inspect/navigate to a form, page, portal, dashboard, chart, or workflow.\n"
        "- The neutral action should be plausible but neither correct nor the misleading trap.\n"
        "- Companion actions must follow the workflow, not a generic reason-only template.\n"
        "- Do not reveal that the chart is misleading in agent-facing labels.\n\n"
        "Return strict JSON with this exact shape:\n"
        "{\n"
        '  "intermediate_decision": {"decision_type": "...", "prompt": "...", "correct_value": "...", "misleading_value": "...", "rationale": "..."},\n'
        '  "primary_action": {"field_id": "...", "field_label": "...", "correct_action_label": "...", "rationale": "..."},\n'
        '  "misleading_action": {"action_label": "...", "rationale": "..."},\n'
        '  "neutral_action": {"action_label": "...", "rationale": "..."},\n'
        '  "companion_actions": [{"field_id": "...", "field_label": "...", "correct_value": "...", "input_type": "select|checkbox|text|hidden", "rationale": "..."}],\n'
        '  "completion_action": {"action_label": "Submit/Save/Confirm ...", "rationale": "..."}\n'
        "}\n\n"
        f"Sample JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def expected_action_id(case: dict[str, Any]) -> str:
    source = f"{case.get('recommended_action_type')} {case.get('ground_truth_entity')}"
    digest = hashlib.sha1(f"{case.get('case_id')} {source}".encode("utf-8")).hexdigest()[:8]
    return f"correct_{slugify(source, 64)}_{digest}"


def make_action_id(prefix: str, label: str, existing: set[str]) -> str:
    base = f"{prefix}_{slugify(label, 72)}"
    candidate = base
    idx = 2
    while candidate in existing:
        candidate = f"{base}_{idx}"
        idx += 1
    existing.add(candidate)
    return candidate


def csv_values_for_column(case: dict[str, Any], column: str | None) -> list[str]:
    if not column:
        return []
    path = Path(case.get("csv_path") or "")
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            seen: list[str] = []
            for row in reader:
                value = str(row.get(column, "")).strip()
                if value and value not in seen:
                    seen.append(value)
            return seen
    except Exception:
        return []


def entity_candidates(case: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for column in [
        case.get("entity_column"),
        case.get("target_entity_column"),
        "brand",
        "product",
        "browser",
        "category",
        "department",
        "major",
        "subject",
        "state",
        "month",
        "week",
        "day",
        "date",
    ]:
        for value in csv_values_for_column(case, column):
            if value not in candidates:
                candidates.append(value)
    return candidates


def is_bad_neutral_label(label: str) -> bool:
    return bool(
        NEUTRAL_BAD_START_RE.search(label or "")
        or NEUTRAL_BAD_CONTAINS_RE.search(label or "")
    )


def labels_equivalent(a: str, b: str) -> bool:
    return slugify(a, 120) == slugify(b, 120)


def deterministic_neutral_action_label(
    case: dict[str, Any],
    *,
    correct_label: str,
    misleading_label: str,
) -> tuple[str, str]:
    """Return a submit-able neutral decision label plus a rationale."""
    gt = str(case.get("ground_truth_entity") or "")
    op = str(case.get("reasoning_operation") or "")
    kind = workflow_kind(case)
    entities = [
        e
        for e in entity_candidates(case)
        if e and e != gt and e.lower() not in correct_label.lower() and e.lower() not in misleading_label.lower()
    ]
    if kind in {"assignment_or_allocation", "profile_or_filter_selection", "generic_dashboard_form"} or op in {
        "extreme_value",
        "visual_size_vs_data_value",
        "rank_order",
        "axis_or_scale_interpretation",
        "pairwise_comparison",
    }:
        if entities:
            return (
                f"Select {entities[0]}",
                "Deterministic neutral rewrite: choose another submit-able entity that is neither the correct target nor the visual trap.",
            )
        return (
            "Select routine monitoring target",
            "Deterministic neutral rewrite: submit a plausible non-target entity-selection decision.",
        )
    if op == "cherry_picking_generalization_check" or kind == "approval_or_evidence_review":
        return (
            "Route to general manager review",
            "Deterministic neutral rewrite: submit a general review route that is neither approval nor the required full-data analysis hold.",
        )
    if op == "threshold_judgment" or kind == "routing_or_review":
        return (
            "Route to general monitoring review",
            "Deterministic neutral rewrite: submit a non-target review queue distinct from the correct and misleading threshold actions.",
        )
    if kind == "alert_or_status_update" or op in {"annotation_claim_verification", "largest_recent_change"}:
        return (
            "Mark as routine status review",
            "Deterministic neutral rewrite: submit a routine status option distinct from the trend or alert decision.",
        )
    return (
        "Route to routine monitoring",
        "Deterministic neutral rewrite: submit a plausible routine handling option.",
    )


def default_fallback_scoring() -> dict[str, dict[str, str]]:
    return {
        "no_submission": {
            "outcome": "completion_failure",
            "error_attribution": "no_final_submission",
        },
        "invalid_action": {
            "outcome": "invalid_action_failure",
            "error_attribution": "submitted_action_not_in_action_space",
        },
        "multiple_conflicting_actions": {
            "outcome": "ambiguous_action_failure",
            "error_attribution": "conflicting_primary_actions",
        },
        "irrelevant_field_only": {
            "outcome": "no_decision_submitted",
            "error_attribution": "no_primary_action",
        },
        "free_text_without_action": {
            "outcome": "no_decision_submitted",
            "error_attribution": "unstructured_response_without_required_action",
        },
    }


def fallback_spec(case: dict[str, Any]) -> dict[str, Any]:
    """Deterministic emergency fallback used only if GPT fails."""
    correct_label = str(case.get("recommended_action_type") or "Perform the correct workflow action")
    trap = str(case.get("expected_visual_trap") or "Follow the misleading visual impression")
    gt = str(case.get("ground_truth_entity"))
    if case.get("reasoning_operation") == "cherry_picking_generalization_check":
        misleading_label = "Approve the broader recommendation without requesting additional evidence review"
        neutral_label = "Save the form as a draft without routing the recommendation"
    elif case.get("reasoning_operation") == "threshold_judgment":
        misleading_label = "Choose the opposite threshold handling option implied by the chart appearance"
        neutral_label = "Route the item to a general monitoring queue"
    else:
        misleading_label = f"Choose the visually suggested alternative instead of {gt}"
        neutral_label = "Leave the item in a general review queue"
    return {
        "intermediate_decision": {
            "decision_type": case.get("reasoning_operation"),
            "prompt": str(case.get("misleading_target") or ""),
            "correct_value": gt,
            "misleading_value": trap,
            "rationale": "Fallback generated from fixed sample metadata.",
        },
        "primary_action": {
            "field_id": "primary_decision",
            "field_label": "Primary workflow decision",
            "correct_action_label": correct_label,
            "rationale": "Correct action is fixed from recommended_action_type.",
        },
        "misleading_action": {"action_label": misleading_label, "rationale": trap},
        "neutral_action": {
            "action_label": neutral_label,
            "rationale": "A plausible non-target workflow option.",
        },
        "companion_actions": [
            {
                "field_id": "target_or_basis",
                "field_label": "Target or decision basis",
                "correct_value": gt,
                "input_type": "select",
                "rationale": "Companion value derived from fixed ground truth.",
            }
        ],
        "completion_action": {
            "action_label": "Submit the workflow decision",
            "rationale": "Required final submission action.",
        },
    }


def normalize_gpt_spec(obj: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    spec = dict(obj)
    if not isinstance(spec.get("intermediate_decision"), dict):
        spec["intermediate_decision"] = fallback_spec(case)["intermediate_decision"]
    if not isinstance(spec.get("primary_action"), dict):
        spec["primary_action"] = fallback_spec(case)["primary_action"]
    if not isinstance(spec.get("misleading_action"), dict):
        spec["misleading_action"] = fallback_spec(case)["misleading_action"]
    if not isinstance(spec.get("neutral_action"), dict):
        spec["neutral_action"] = fallback_spec(case)["neutral_action"]
    if not isinstance(spec.get("completion_action"), dict):
        spec["completion_action"] = fallback_spec(case)["completion_action"]
    companions = spec.get("companion_actions")
    if not isinstance(companions, list) or not companions:
        companions = fallback_spec(case)["companion_actions"]
    spec["companion_actions"] = [c for c in companions if isinstance(c, dict)]
    if not spec["companion_actions"]:
        spec["companion_actions"] = fallback_spec(case)["companion_actions"]
    return spec


def build_task(case: dict[str, Any], gpt_spec: dict[str, Any], *, used_fallback: bool) -> dict[str, Any]:
    gpt_spec = normalize_gpt_spec(gpt_spec, case)
    task_id = stable_task_id(case["case_id"])
    expected_id = expected_action_id(case)
    existing = {expected_id}
    misleading_label = str(gpt_spec["misleading_action"].get("action_label") or "Misleading workflow option")
    neutral_label = str(gpt_spec["neutral_action"].get("action_label") or "Neutral workflow option")
    correct_label = str(
        gpt_spec["primary_action"].get("correct_action_label")
        or case.get("recommended_action_type")
        or "Correct workflow action"
    )
    neutral_rewritten = False
    if (
        is_bad_neutral_label(neutral_label)
        or labels_equivalent(neutral_label, correct_label)
        or labels_equivalent(neutral_label, misleading_label)
    ):
        neutral_label, neutral_rationale = deterministic_neutral_action_label(
            case,
            correct_label=correct_label,
            misleading_label=misleading_label,
        )
        gpt_spec["neutral_action"]["action_label"] = neutral_label
        gpt_spec["neutral_action"]["rationale"] = neutral_rationale
        neutral_rewritten = True
    misleading_id = make_action_id("misleading", misleading_label, existing)
    neutral_id = make_action_id("neutral", neutral_label, existing)

    action_space = [
        {
            "action_id": expected_id,
            "label": correct_label,
            "role": "correct",
            "scoring_outcome": "success",
            "error_attribution": "none",
            "rationale": str(gpt_spec["primary_action"].get("rationale") or ""),
        },
        {
            "action_id": misleading_id,
            "label": misleading_label,
            "role": "misleading_trap",
            "scoring_outcome": "misleading_failure",
            "error_attribution": "chart_induced_intermediate_decision_error",
            "rationale": str(gpt_spec["misleading_action"].get("rationale") or ""),
        },
        {
            "action_id": neutral_id,
            "label": neutral_label,
            "role": "neutral_or_irrelevant",
            "scoring_outcome": "irrelevant_action_failure",
            "error_attribution": "wrong_or_irrelevant_web_action",
            "rationale": str(gpt_spec["neutral_action"].get("rationale") or ""),
        },
    ]

    companions = []
    for idx, comp in enumerate(gpt_spec["companion_actions"], 1):
        field_id = slugify(comp.get("field_id") or f"companion_{idx}", 48)
        companions.append(
            {
                "field_id": field_id,
                "field_label": str(comp.get("field_label") or field_id.replace("_", " ").title()),
                "correct_value": str(comp.get("correct_value") or case.get("ground_truth_entity")),
                "input_type": str(comp.get("input_type") or "select"),
                "rationale": str(comp.get("rationale") or ""),
                "required": True,
                "scoring_outcome_if_missing": "companion_failure",
            }
        )

    task = {
        "task_id": task_id,
        "case_id": case["case_id"],
        "scenario": case.get("scenario"),
        "misleader_type": case.get("misleader_type"),
        "plot_type": case.get("plot_type"),
        "reasoning_operation": case.get("reasoning_operation"),
        "chart_asset": {
            "figure_path": case.get("figure_path"),
            "csv_path": case.get("csv_path"),
            "html_path": case.get("html_path"),
            "html_title": case.get("html_title") or case.get("html_h1") or "",
        },
        "workflow_instruction": case.get("workflow_instruction"),
        "ground_truth": {
            "ground_truth_entity": case.get("ground_truth_entity"),
            "ground_truth_value": case.get("ground_truth_value"),
            "ground_truth_computation": case.get("ground_truth_computation"),
            "recommended_action_type": case.get("recommended_action_type"),
        },
        "misleading_context": {
            "misleading_mechanism": case.get("misleading_mechanism"),
            "misleading_target": case.get("misleading_target"),
            "expected_visual_trap": case.get("expected_visual_trap"),
        },
        "intermediate_decision": gpt_spec["intermediate_decision"],
        "primary_action": {
            "field_id": slugify(gpt_spec["primary_action"].get("field_id") or "primary_decision"),
            "field_label": str(gpt_spec["primary_action"].get("field_label") or "Primary workflow decision"),
            "correct_action_id": expected_id,
            "correct_action_label": correct_label,
            "source_recommended_action_type": case.get("recommended_action_type"),
            "rationale": str(gpt_spec["primary_action"].get("rationale") or ""),
        },
        "companion_actions": companions,
        "completion_action": {
            "action_id": "submit_workflow_decision",
            "label": str(gpt_spec["completion_action"].get("action_label") or "Submit the workflow decision"),
            "required": True,
            "rationale": str(gpt_spec["completion_action"].get("rationale") or ""),
        },
        "action_space": action_space,
        "expected_action_id": expected_id,
        "misleading_action_ids": [misleading_id],
        "fallback_scoring": default_fallback_scoring(),
        "generation_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workflow_kind": workflow_kind(case),
            "gpt_fallback_used": used_fallback,
            "neutral_action_rewritten": neutral_rewritten,
        },
    }
    return task


def validate_task(task: dict[str, Any], case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if task.get("case_id") != case.get("case_id"):
        errors.append("case_id_changed")
    if task.get("reasoning_operation") != case.get("reasoning_operation"):
        errors.append("reasoning_operation_changed")
    if task.get("ground_truth", {}).get("ground_truth_entity") != case.get("ground_truth_entity"):
        errors.append("ground_truth_entity_changed")
    if task.get("ground_truth", {}).get("ground_truth_value") != case.get("ground_truth_value"):
        errors.append("ground_truth_value_changed")
    action_space = task.get("action_space") or []
    roles = Counter(a.get("role") for a in action_space)
    if roles.get("correct") != 1:
        errors.append("expected_exactly_one_correct_action")
    if roles.get("misleading_trap", 0) < 1:
        errors.append("missing_misleading_trap_action")
    if roles.get("neutral_or_irrelevant", 0) < 1:
        errors.append("missing_neutral_action")
    ids = [a.get("action_id") for a in action_space]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_action_ids")
    if task.get("expected_action_id") not in ids:
        errors.append("expected_action_id_not_in_action_space")
    labels = {a.get("role"): str(a.get("label") or "") for a in action_space}
    neutral_label = labels.get("neutral_or_irrelevant", "")
    if is_bad_neutral_label(neutral_label):
        errors.append("neutral_action_is_navigation_or_viewing_step")
    if labels_equivalent(neutral_label, labels.get("correct", "")):
        errors.append("neutral_action_equals_correct_action")
    if labels_equivalent(neutral_label, labels.get("misleading_trap", "")):
        errors.append("neutral_action_equals_misleading_action")
    if not task.get("companion_actions"):
        errors.append("missing_companion_actions")
    for key in REQUIRED_FALLBACK_KEYS:
        if key not in task.get("fallback_scoring", {}):
            errors.append(f"missing_fallback_{key}")
    workflow = (task.get("workflow_instruction") or "").lower()
    rec = (case.get("recommended_action_type") or "").lower()
    if rec and rec in workflow:
        errors.append("workflow_contains_full_recommended_action")
    return errors


def score_submission(task: dict[str, Any], submission: dict[str, Any]) -> dict[str, str]:
    if not submission.get("submitted"):
        return task["fallback_scoring"]["no_submission"]
    action_id = submission.get("primary_action_id")
    valid_ids = {a["action_id"] for a in task["action_space"]}
    if action_id not in valid_ids:
        return task["fallback_scoring"]["invalid_action"]
    missing_companion = [
        c["field_id"] for c in task.get("companion_actions", []) if c["field_id"] not in submission.get("companion_values", {})
    ]
    if missing_companion:
        return {
            "outcome": "companion_failure",
            "error_attribution": "missing_required_companion_actions",
        }
    return next(a for a in task["action_space"] if a["action_id"] == action_id)


def load_existing_logs(log_path: Path) -> dict[str, dict[str, Any]]:
    if not log_path.exists():
        return {}
    out = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("case_id") and row.get("validation_passed"):
            out[row["case_id"]] = row
    return out


def append_log(log_path: Path, row: dict[str, Any]) -> None:
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def generate(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "benchmark_tasks.jsonl"
    log_path = output_dir / "task_generation_log.jsonl"
    summary_path = output_dir / "task_generation_summary.md"
    annotations_path = output_dir / "task_action_space_review_annotations.json"
    if args.force and log_path.exists():
        log_path.unlink()

    cases = read_jsonl(input_path)
    if args.limit:
        cases = cases[: args.limit]

    existing_logs = {} if args.force else load_existing_logs(log_path)
    client = make_client()
    tasks: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []

    for idx, case in enumerate(cases, 1):
        case_id = case["case_id"]
        if case_id in existing_logs:
            task = existing_logs[case_id]["task"]
            tasks.append(task)
            logs.append(existing_logs[case_id])
            print(f"[{idx}/{len(cases)}] reused {case_id}", flush=True)
            continue

        raw_text = ""
        parsed: dict[str, Any] = {}
        used_fallback = False
        started = time.time()
        try:
            raw_text = complete_vision(
                client,
                SYSTEM_PROMPT,
                build_user_prompt(case),
                case["figure_path"],
                max_output_tokens=args.max_output_tokens,
            )
            parsed = extract_json_object(raw_text)
        except Exception as exc:
            used_fallback = True
            parsed = fallback_spec(case)
            raw_text = f"GPT_FAILURE: {exc!r}"

        task = build_task(case, parsed, used_fallback=used_fallback)
        errors = validate_task(task, case)
        # If GPT produced invalid text, retry once with deterministic fallback.
        if errors and not used_fallback:
            used_fallback = True
            parsed = fallback_spec(case)
            task = build_task(case, parsed, used_fallback=True)
            errors = validate_task(task, case)

        # Scorer dry run.
        expected_result = score_submission(
            task,
            {
                "submitted": True,
                "primary_action_id": task["expected_action_id"],
                "companion_values": {c["field_id"]: c["correct_value"] for c in task["companion_actions"]},
            },
        )
        misleading_result = score_submission(
            task,
            {
                "submitted": True,
                "primary_action_id": task["misleading_action_ids"][0],
                "companion_values": {c["field_id"]: c["correct_value"] for c in task["companion_actions"]},
            },
        )
        no_submit_result = score_submission(task, {"submitted": False})
        invalid_result = score_submission(
            task,
            {
                "submitted": True,
                "primary_action_id": "not_a_real_action",
                "companion_values": {c["field_id"]: c["correct_value"] for c in task["companion_actions"]},
            },
        )
        if expected_result.get("scoring_outcome") != "success":
            errors.append("expected_action_dry_run_failed")
        if misleading_result.get("scoring_outcome") != "misleading_failure":
            errors.append("misleading_action_dry_run_failed")
        if no_submit_result.get("outcome") != "completion_failure":
            errors.append("no_submission_dry_run_failed")
        if invalid_result.get("outcome") != "invalid_action_failure":
            errors.append("invalid_action_dry_run_failed")

        log = {
            "case_id": case_id,
            "task_id": task["task_id"],
            "elapsed_sec": round(time.time() - started, 3),
            "llm_backend": os.environ.get("LLM_BACKEND"),
            "llm_model": os.environ.get("HEXIN_MODEL"),
            "gpt_raw_text": raw_text,
            "gpt_parsed": parsed,
            "task": task,
            "validation_errors": errors,
            "validation_passed": not errors,
            "used_fallback": used_fallback,
        }
        append_log(log_path, log)
        tasks.append(task)
        logs.append(log)
        print(
            f"[{idx}/{len(cases)}] {'ok' if not errors else 'ERR'} {case_id} "
            f"fallback={used_fallback} errors={len(errors)}",
            flush=True,
        )

    write_jsonl(tasks_path, tasks)
    annotations = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "annotations": {
            task["task_id"]: {
                "task_id": task["task_id"],
                "case_id": task["case_id"],
                "status": "unreviewed",
                "issue_type": "",
                "notes": "",
            }
            for task in tasks
        },
    }
    annotations_path.write_text(json.dumps(annotations, ensure_ascii=False, indent=2), encoding="utf-8")

    role_counts = Counter(a["role"] for t in tasks for a in t["action_space"])
    op_counts = Counter(t["reasoning_operation"] for t in tasks)
    misleader_counts = Counter(t["misleader_type"] for t in tasks)
    failed = [log for log in logs if not log["validation_passed"]]
    fallback_count = sum(1 for log in logs if log.get("used_fallback"))
    neutral_rewrite_count = sum(
        1 for task in tasks if task.get("generation_metadata", {}).get("neutral_action_rewritten")
    )
    summary = [
        "# Task Generation Summary\n",
        f"- Created at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Input: `{input_path}`",
        f"- Output: `{output_dir}`",
        f"- Generated tasks: `{len(tasks)}`",
        f"- Validation failures: `{len(failed)}`",
        f"- GPT fallback used: `{fallback_count}`",
        f"- Neutral actions deterministically rewritten: `{neutral_rewrite_count}`",
        "\n## Action Role Distribution\n",
        "| Role | Count |",
        "|---|---:|",
    ]
    for key, value in role_counts.most_common():
        summary.append(f"| `{key}` | {value} |")
    summary.extend(["\n## Operation Distribution\n", "| Operation | Count |", "|---|---:|"])
    for key, value in op_counts.most_common():
        summary.append(f"| `{key}` | {value} |")
    summary.extend(["\n## Misleader Distribution\n", "| Misleader | Count |", "|---|---:|"])
    for key, value in misleader_counts.most_common():
        summary.append(f"| `{key}` | {value} |")
    if failed:
        summary.append("\n## Validation Failures\n")
        for log in failed:
            summary.append(f"- `{log['case_id']}`: {', '.join(log['validation_errors'])}")
    else:
        summary.append("\n## Validation\n\n- All generated tasks passed structural validation and scorer dry run.")
    summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "tasks": len(tasks),
                "validation_failures": len(failed),
                "fallback_used": fallback_count,
                "neutral_rewrites": neutral_rewrite_count,
                "tasks_path": str(tasks_path),
                "summary_path": str(summary_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not failed and len(tasks) == len(cases) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-output-tokens", type=int, default=2500)
    args = parser.parse_args()
    return generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
