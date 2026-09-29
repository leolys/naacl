#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
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

from adversarial_pipeline.llm_client import complete_text, make_client


DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark/health_tasks/benchmark_health_tasks.jsonl"
DEFAULT_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark/health_tasks/review_annotations.json"
DEFAULT_APPROVED_TASKS = REPO_ROOT / "web_agent_benchmark/health_shell/approved_health_shell_tasks.jsonl"
DEFAULT_DESIGNS = REPO_ROOT / "web_agent_benchmark/health_shell/gpt_page_designs.jsonl"
DEFAULT_FAILURES = REPO_ROOT / "web_agent_benchmark/health_shell/gpt_page_design_failures.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "web_agent_benchmark/health_shell/shell_build_summary.md"

LEAK_RE = re.compile(
    r"\b(ground truth|true value|actual value|correct|neutral|misleading|success|misleading_failure|dual axis|inverted axis)\b",
    re.I,
)

DESIGN_SYSTEM_PROMPT = """You design agent-visible benchmark task pages for the Health / Public Health / Clinical Care domain.
Return strict JSON only. Do not include Markdown fences.

Hard constraints:
- Rewrite only the agent-visible task-page wording.
- Preserve the same hidden scoring semantics and the same downstream decision structure.
- Make the task feel like a real health operations workflow, not a chart QA quiz.
- Do not explicitly instruct the agent to read labels, compare title truthfulness, or identify the misleading trick.
- Frame the task as a dashboard-based operational routing decision.
- Use natural, professional English for a workflow UI.
- Action labels must be parallel downstream actions.
- Never mention: ground truth, correct, misleading, neutral, success, failure, true value, actual value, dual axis, inverted axis.
"""

DESIGN_USER_PROMPT = """Rewrite the agent-visible task-page wording for this health benchmark task.

Task ID: {task_id}
Case ID: {case_id}
Task readiness: {task_readiness}
Misleader family: {misleader_type}
Plot type: {plot_type}
Source dataset: {source_dataset}

Current agent-visible page:
- Page title: {page_title}
- Workflow instruction: {workflow_instruction}
- Chart reference: {chart_reference}
- Primary action field label: {primary_action_field_label}
- Completion action label: {completion_action_label}

Current visible context fields:
{context_fields_json}

Current action semantics that MUST stay aligned with hidden scoring:
{action_semantics_json}

Hidden task intent summary (for preserving semantics only; do not expose this language directly):
{hidden_summary}

Image-only reviewer context, if any:
{image_only_summary}

CSV sample, if any:
{csv_summary}

Return exactly this JSON schema:
{{
  "page_title": "string",
  "workflow_instruction": "string",
  "chart_reference": "string",
  "primary_action_field_label": "string",
  "completion_action_label": "string",
  "companion_fields": [
    {{"field_label": "string", "value": "string"}}
  ],
  "action_labels": {{
    "expected": "string",
    "misleading": "string",
    "neutral": "string"
  }}
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


def load_annotations(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    payload.setdefault("annotations", {})
    return payload


def resolve_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return str(path)


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


def sanitize_agent_text(text: Any) -> str:
    cleaned = LEAK_RE.sub("", str(text or ""))
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def csv_preview(task: dict[str, Any], limit: int = 6) -> list[dict[str, str]]:
    chart_asset = task.get("chart_asset", {})
    if not chart_asset.get("has_csv"):
        return []
    csv_path = resolve_path(chart_asset.get("csv_path"))
    if not csv_path or not Path(csv_path).exists():
        return []
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            rows.append({str(k): str(v) for k, v in row.items() if k is not None})
        return rows


def companion_fields(task: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for field in task.get("companion_actions", []):
        label = str(field.get("field_label") or "").strip()
        value = str(field.get("correct_value") or "").strip()
        field_id = str(field.get("field_id") or "").strip()
        if label and value:
            out.append({"field_id": field_id, "field_label": label, "value": value})
    return out


def action_slot_map(task: dict[str, Any]) -> dict[str, dict[str, str]]:
    expected_id = str(task.get("expected_action_id") or "")
    misleading_ids = [str(x) for x in task.get("misleading_action_ids", [])]
    neutral_action: dict[str, str] | None = None
    expected_action: dict[str, str] | None = None
    misleading_action: dict[str, str] | None = None
    for action in task.get("action_space", []):
        action_id = str(action.get("action_id") or "")
        label = str(action.get("label") or "")
        payload = {"action_id": action_id, "label": label}
        if action_id == expected_id:
            expected_action = payload
        elif action_id in misleading_ids and misleading_action is None:
            misleading_action = payload
        elif neutral_action is None:
            neutral_action = payload
    if not expected_action or not misleading_action or not neutral_action:
        raise RuntimeError(f"Could not derive expected/misleading/neutral action slots for {task['task_id']}")
    return {"expected": expected_action, "misleading": misleading_action, "neutral": neutral_action}


def task_signature(task: dict[str, Any]) -> str:
    slot_map = action_slot_map(task)
    payload = {
        "task_id": task.get("task_id"),
        "page_title": task.get("page_title"),
        "workflow_instruction": task.get("workflow_instruction"),
        "chart_reference": task.get("chart_reference"),
        "primary_action_field_label": task.get("primary_action", {}).get("field_label"),
        "completion_action_label": task.get("completion_action", {}).get("label"),
        "companion_fields": companion_fields(task),
        "action_labels": {slot: slot_map[slot]["label"] for slot in ["expected", "misleading", "neutral"]},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def hidden_summary(task: dict[str, Any]) -> str:
    ground_truth = task.get("ground_truth", {})
    intermediate = task.get("intermediate_decision", {})
    lines = [
        f"Ground-truth entity: {ground_truth.get('ground_truth_entity')}",
        f"Ground-truth computation: {ground_truth.get('ground_truth_computation')}",
        f"Reasoning operation: {task.get('reasoning_operation')}",
        f"Intermediate decision prompt: {intermediate.get('prompt')}",
        f"Intended misleading choice: {task.get('misleading_context', {}).get('misleading_target')}",
        f"Visual trap summary: {task.get('misleading_context', {}).get('expected_visual_trap')}",
    ]
    return "\n".join(f"- {sanitize_agent_text(line)}" for line in lines if line)


def image_only_summary(task: dict[str, Any]) -> str:
    ctx = task.get("image_only_review_context") or {}
    if not ctx:
        return "None."
    keys = [
        "metric_definition",
        "draft_design_rationale",
        "reviewer_note",
        "ocr_text",
    ]
    lines = []
    for key in keys:
        value = ctx.get(key)
        if value:
            lines.append(f"- {key}: {str(value).strip()}")
    return "\n".join(lines) if lines else "None."


def build_prompt_payload(task: dict[str, Any]) -> str:
    slot_map = action_slot_map(task)
    action_payload = {
        "expected": {
            "action_id": slot_map["expected"]["action_id"],
            "current_label": slot_map["expected"]["label"],
            "semantic_role": "This is the hidden success action and must remain the operationally correct route.",
        },
        "misleading": {
            "action_id": slot_map["misleading"]["action_id"],
            "current_label": slot_map["misleading"]["label"],
            "semantic_role": "This is the hidden misleading route and must stay plausible but wrong.",
        },
        "neutral": {
            "action_id": slot_map["neutral"]["action_id"],
            "current_label": slot_map["neutral"]["label"],
            "semantic_role": "This is the hidden irrelevant route and must stay plausible but non-priority.",
        },
    }
    csv_rows = csv_preview(task)
    return DESIGN_USER_PROMPT.format(
        task_id=task.get("task_id"),
        case_id=task.get("case_id"),
        task_readiness=task.get("task_readiness"),
        misleader_type=task.get("misleader_type"),
        plot_type=task.get("plot_type"),
        source_dataset=task.get("source_dataset"),
        page_title=task.get("page_title"),
        workflow_instruction=task.get("workflow_instruction"),
        chart_reference=task.get("chart_reference"),
        primary_action_field_label=task.get("primary_action", {}).get("field_label"),
        completion_action_label=task.get("completion_action", {}).get("label"),
        context_fields_json=json.dumps(companion_fields(task), ensure_ascii=False, indent=2),
        action_semantics_json=json.dumps(action_payload, ensure_ascii=False, indent=2),
        hidden_summary=hidden_summary(task),
        image_only_summary=image_only_summary(task),
        csv_summary=json.dumps(csv_rows, ensure_ascii=False, indent=2) if csv_rows else "No CSV preview available.",
    )


def normalize_design(payload: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    slot_map = action_slot_map(task)
    original_fields = companion_fields(task)

    page_title = sanitize_agent_text(payload.get("page_title") or task.get("page_title") or "Health Task")
    workflow_instruction = sanitize_agent_text(payload.get("workflow_instruction") or task.get("workflow_instruction") or "")
    chart_reference = sanitize_agent_text(payload.get("chart_reference") or task.get("chart_reference") or "")
    primary_action_field_label = sanitize_agent_text(payload.get("primary_action_field_label") or task.get("primary_action", {}).get("field_label") or "Health route")
    completion_action_label = sanitize_agent_text(payload.get("completion_action_label") or task.get("completion_action", {}).get("label") or "Submit health routing decision")

    companion_payload = payload.get("companion_fields")
    normalized_fields: list[dict[str, str]] = []
    if isinstance(companion_payload, list):
        for item in companion_payload:
            if not isinstance(item, dict):
                continue
            label = sanitize_agent_text(item.get("field_label"))
            value = sanitize_agent_text(item.get("value"))
            if label and value:
                normalized_fields.append({"field_label": label, "value": value})
    if not normalized_fields:
        normalized_fields = [{"field_label": field["field_label"], "value": field["value"]} for field in original_fields]

    raw_action_labels = payload.get("action_labels") or {}
    expected_label = sanitize_agent_text(raw_action_labels.get("expected") or slot_map["expected"]["label"])
    misleading_label = sanitize_agent_text(raw_action_labels.get("misleading") or slot_map["misleading"]["label"])
    neutral_label = sanitize_agent_text(raw_action_labels.get("neutral") or slot_map["neutral"]["label"])

    if not page_title:
        page_title = str(task.get("page_title") or "Health Task")
    if not workflow_instruction:
        workflow_instruction = str(task.get("workflow_instruction") or "")
    if not chart_reference:
        chart_reference = str(task.get("chart_reference") or "")

    return {
        "page_title": page_title,
        "workflow_instruction": workflow_instruction,
        "chart_reference": chart_reference,
        "primary_action_field_label": primary_action_field_label,
        "completion_action_label": completion_action_label,
        "companion_fields": normalized_fields[:6],
        "action_labels": {
            "expected": expected_label,
            "misleading": misleading_label,
            "neutral": neutral_label,
        },
    }


def validate_design(design: dict[str, Any]) -> list[str]:
    issues = []
    for key in ["page_title", "workflow_instruction", "chart_reference", "primary_action_field_label", "completion_action_label"]:
        if LEAK_RE.search(str(design.get(key, ""))):
            issues.append(f"leak_in_{key}")
        if not str(design.get(key, "")).strip():
            issues.append(f"blank_{key}")
    for field in design.get("companion_fields", []):
        if LEAK_RE.search(str(field.get("field_label", ""))) or LEAK_RE.search(str(field.get("value", ""))):
            issues.append("leak_in_companion_fields")
    for slot, label in (design.get("action_labels") or {}).items():
        if LEAK_RE.search(str(label)):
            issues.append(f"leak_in_action_{slot}")
        if not str(label).strip():
            issues.append(f"blank_action_{slot}")
    return issues


def apply_design(task: dict[str, Any], design: dict[str, Any]) -> dict[str, Any]:
    task = json.loads(json.dumps(task, ensure_ascii=False))
    slot_map = action_slot_map(task)
    task["page_title"] = design["page_title"]
    task["workflow_instruction"] = design["workflow_instruction"]
    task["chart_reference"] = design["chart_reference"]
    task.setdefault("primary_action", {})
    task["primary_action"]["field_label"] = design["primary_action_field_label"]
    task["primary_action"]["correct_action_label"] = design["action_labels"]["expected"]
    task.setdefault("completion_action", {})
    task["completion_action"]["label"] = design["completion_action_label"]
    task["companion_actions"] = [
        {
            "field_id": re.sub(r"[^a-z0-9]+", "_", field["field_label"].lower()).strip("_") or f"field_{idx+1}",
            "field_label": field["field_label"],
            "correct_value": field["value"],
            "input_type": "readonly",
            "required": False,
        }
        for idx, field in enumerate(design["companion_fields"])
    ]
    label_map = {
        slot_map["expected"]["action_id"]: design["action_labels"]["expected"],
        slot_map["misleading"]["action_id"]: design["action_labels"]["misleading"],
        slot_map["neutral"]["action_id"]: design["action_labels"]["neutral"],
    }
    for action in task.get("action_space", []):
        action_id = str(action.get("action_id") or "")
        if action_id in label_map:
            action["label"] = label_map[action_id]
    task["shell_page_design"] = {
        "generated_at": utc_now(),
        "page_title": design["page_title"],
    }
    return task


def approved_tasks(tasks_path: Path, annotations_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    annotations = load_annotations(annotations_path).get("annotations", {})
    approved, rejected = [], []
    for task in read_jsonl(tasks_path):
        status = annotations.get(task["task_id"], {}).get("status")
        if status == "approved_for_shell":
            approved.append(task)
        elif status == "reject":
            rejected.append(task)
    return approved, rejected


def generate_design(client: Any, task: dict[str, Any]) -> tuple[dict[str, Any], str]:
    raw = complete_text(
        client,
        DESIGN_SYSTEM_PROMPT,
        build_prompt_payload(task),
        max_output_tokens=1800,
    )
    parsed = parse_json_object(raw)
    return normalize_design(parsed, task), raw


def build_summary(approved: list[dict[str, Any]], rejected: list[dict[str, Any]], design_rows: list[dict[str, Any]], failure_rows: list[dict[str, Any]], out_path: Path) -> None:
    readiness = Counter(task.get("task_readiness") for task in approved)
    misleaders = Counter(task.get("misleader_type") for task in approved)
    lines = [
        "# Health Shell Build Summary",
        "",
        f"- Loaded approved health shell tasks: {len(approved)}",
        f"- Readiness distribution: {dict(readiness)}",
        f"- Misleader distribution: {dict(misleaders)}",
        f"- GPT page design success count: {len(design_rows)}",
        f"- GPT page design failure count: {len(failure_rows)}",
        f"- Excluded rejected tasks: {len(rejected)}",
        "",
        "## Rejected Tasks",
        "",
    ]
    for task in rejected:
        lines.append(f"- `{task['task_id']}` ({task.get('task_readiness')})")
    lines.extend([
        "",
        "## Shell Task Index",
        "",
        "| Slug | Task ID | Readiness | Title |",
        "|---|---|---|---|",
    ])
    for idx, task in enumerate(approved, start=1):
        lines.append(f"| health{idx:03d} | {task['task_id']} | {task.get('task_readiness')} | {task.get('page_title')} |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--approved-out", type=Path, default=DEFAULT_APPROVED_TASKS)
    parser.add_argument("--designs-out", type=Path, default=DEFAULT_DESIGNS)
    parser.add_argument("--failures-out", type=Path, default=DEFAULT_FAILURES)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    approved, rejected = approved_tasks(args.tasks, args.annotations)
    if len(approved) != 19:
        raise RuntimeError(f"Expected 19 approved health tasks, found {len(approved)}")

    cached_rows = read_jsonl(args.designs_out)
    cached_by_task_id = {row.get("task_id"): row for row in cached_rows}
    failure_rows = read_jsonl(args.failures_out)
    failure_by_task_id = {row.get("task_id"): row for row in failure_rows}

    client = make_client()
    final_tasks: list[dict[str, Any]] = []
    design_rows_out: dict[str, dict[str, Any]] = dict(cached_by_task_id)
    failure_rows_out: dict[str, dict[str, Any]] = dict(failure_by_task_id)

    for index, task in enumerate(approved, start=1):
        signature = task_signature(task)
        cached = cached_by_task_id.get(task["task_id"])
        design: dict[str, Any] | None = None
        raw_text = ""
        source_status = "cached"
        try:
            print(f"[{index}/{len(approved)}] building {task['task_id']}", flush=True)
            if cached and cached.get("task_signature") == signature:
                design = normalize_design(cached.get("design", {}), task)
            else:
                design, raw_text = generate_design(client, task)
                issues = validate_design(design)
                if issues:
                    raise RuntimeError(f"invalid_gpt_design: {issues}")
                design_rows_out[task["task_id"]] = {
                    "task_id": task["task_id"],
                    "case_id": task["case_id"],
                    "task_signature": signature,
                    "generated_at": utc_now(),
                    "llm_backend": os.environ.get("LLM_BACKEND", ""),
                    "llm_model": os.environ.get("HEXIN_MODEL") or os.environ.get("OPENAI_MODEL") or "",
                    "design": design,
                    "raw_text": raw_text,
                    "source_status": "gpt_generated",
                }
                failure_rows_out.pop(task["task_id"], None)
                source_status = "gpt_generated"
            rendered = apply_design(task, design)
            rendered["shell_page_design"]["source_status"] = source_status
            final_tasks.append(rendered)
            write_jsonl(args.approved_out, final_tasks)
            write_jsonl(args.designs_out, list(design_rows_out.values()))
            write_jsonl(args.failures_out, list(failure_rows_out.values()))
            print(f"[{index}/{len(approved)}] done {task['task_id']} ({source_status})", flush=True)
        except Exception as exc:
            failure_rows_out[task["task_id"]] = {
                "task_id": task["task_id"],
                "case_id": task["case_id"],
                "task_signature": signature,
                "failed_at": utc_now(),
                "error": str(exc),
            }
            fallback = json.loads(json.dumps(task, ensure_ascii=False))
            fallback["shell_page_design"] = {
                "generated_at": utc_now(),
                "source_status": "fallback_original_task_copy",
                "error": str(exc),
            }
            final_tasks.append(fallback)
            write_jsonl(args.approved_out, final_tasks)
            write_jsonl(args.designs_out, list(design_rows_out.values()))
            write_jsonl(args.failures_out, list(failure_rows_out.values()))
            print(f"[{index}/{len(approved)}] fallback {task['task_id']}: {exc}", flush=True)

    write_jsonl(args.approved_out, final_tasks)
    write_jsonl(args.designs_out, list(design_rows_out.values()))
    write_jsonl(args.failures_out, list(failure_rows_out.values()))
    build_summary(final_tasks, rejected, list(design_rows_out.values()), list(failure_rows_out.values()), args.summary_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
