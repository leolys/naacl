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
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark" / "tasks" / "benchmark_tasks.jsonl"
DEFAULT_OUT = REPO_ROOT / "web_agent_benchmark" / "business_shell" / "business_task_visual_grounding_review.jsonl"
DEFAULT_MD = REPO_ROOT / "web_agent_benchmark" / "business_shell" / "business_task_visual_grounding_review.md"
DEFAULT_LOG = REPO_ROOT / "web_agent_benchmark" / "business_shell" / "business_task_visual_grounding_review_log.jsonl"

REQUIRED_FIELDS = {
    "visual_grounding_verdict",
    "visual_to_action_score",
    "misleading_alignment_score",
    "workflow_realism_score",
    "field_relevance_score",
    "leakage_risk",
    "main_issue",
    "recommended_fix",
    "is_chart_interpretation_required_for_success",
    "does_misread_lead_to_wrong_action",
    "does_workflow_degenerate_to_chart_qa",
}

SYSTEM_PROMPT = """You are reviewing web-agent benchmark tasks for VisualWebArena-style visual grounding.

Judge whether the chart interpretation is required for task success and whether a plausible visual misread would directly cause the agent to take the wrong downstream web action.

Return only strict JSON. Do not rewrite the task. Do not reveal hidden labels. Do not add extra keys."""


def load_business_tasks(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            task = json.loads(line)
            if task.get("scenario") == "business_operations":
                rows.append(task)
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def csv_preview(path: str | Path, limit: int = 8) -> dict[str, Any]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {"path": str(csv_path), "exists": False, "headers": [], "rows": []}
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            rows.append(row)
        return {
            "path": str(csv_path),
            "exists": True,
            "headers": reader.fieldnames or [],
            "rows": rows,
        }


def compact_task_for_review(task: dict[str, Any], safe_task: str) -> dict[str, Any]:
    return {
        "safe_task": safe_task,
        "task_id": task.get("task_id"),
        "case_id": task.get("case_id"),
        "scenario": task.get("scenario"),
        "misleader_type": task.get("misleader_type"),
        "plot_type": task.get("plot_type"),
        "reasoning_operation": task.get("reasoning_operation"),
        "html_title": task.get("chart_asset", {}).get("html_title", ""),
        "workflow_instruction": task.get("workflow_instruction"),
        "misleading_context": task.get("misleading_context"),
        "intermediate_decision": task.get("intermediate_decision"),
        "primary_action": task.get("primary_action"),
        "action_space": task.get("action_space"),
        "ground_truth": task.get("ground_truth"),
        "companion_actions": task.get("companion_actions"),
        "completion_action": task.get("completion_action"),
        "csv_preview": csv_preview(task.get("chart_asset", {}).get("csv_path", "")),
    }


def build_prompt(task: dict[str, Any], safe_task: str) -> str:
    review_payload = compact_task_for_review(task, safe_task)
    return (
        "Review this web-agent task. The attached image is the chart the agent will see.\n\n"
        "Use these labels exactly:\n"
        "- visual_grounding_verdict: strong_fit | needs_minor_rewrite | needs_workflow_redesign\n"
        "- leakage_risk: none | minor | serious\n\n"
        "Scoring guidance:\n"
        "- strong_fit: chart interpretation is necessary; the misleading visual trap maps to a wrong web action; the action is a realistic downstream workflow; no serious answer leakage.\n"
        "- needs_minor_rewrite: the visual-to-action chain exists, but wording, page fields, or form context need tightening.\n"
        "- needs_workflow_redesign: the task is mostly chart QA, chart correction, or the misread would not materially change the downstream action.\n\n"
        "Return strict JSON with exactly these keys:\n"
        "{\n"
        '  "visual_grounding_verdict": "...",\n'
        '  "visual_to_action_score": 1,\n'
        '  "misleading_alignment_score": 1,\n'
        '  "workflow_realism_score": 1,\n'
        '  "field_relevance_score": 1,\n'
        '  "leakage_risk": "...",\n'
        '  "main_issue": "...",\n'
        '  "recommended_fix": "...",\n'
        '  "is_chart_interpretation_required_for_success": true,\n'
        '  "does_misread_lead_to_wrong_action": true,\n'
        '  "does_workflow_degenerate_to_chart_qa": false\n'
        "}\n\n"
        f"Task JSON:\n{json.dumps(review_payload, ensure_ascii=False, indent=2)}"
    )


def normalize_review(spec: dict[str, Any]) -> dict[str, Any]:
    verdict = str(spec.get("visual_grounding_verdict", "")).strip()
    if verdict not in {"strong_fit", "needs_minor_rewrite", "needs_workflow_redesign"}:
        verdict = "needs_minor_rewrite"
    leakage = str(spec.get("leakage_risk", "")).strip()
    if leakage not in {"none", "minor", "serious"}:
        leakage = "minor"
    normalized = {
        "visual_grounding_verdict": verdict,
        "leakage_risk": leakage,
        "main_issue": str(spec.get("main_issue", "")).strip(),
        "recommended_fix": str(spec.get("recommended_fix", "")).strip(),
        "is_chart_interpretation_required_for_success": bool(
            spec.get("is_chart_interpretation_required_for_success")
        ),
        "does_misread_lead_to_wrong_action": bool(spec.get("does_misread_lead_to_wrong_action")),
        "does_workflow_degenerate_to_chart_qa": bool(spec.get("does_workflow_degenerate_to_chart_qa")),
    }
    for key in [
        "visual_to_action_score",
        "misleading_alignment_score",
        "workflow_realism_score",
        "field_relevance_score",
    ]:
        try:
            value = int(spec.get(key, 1))
        except Exception:
            value = 1
        normalized[key] = max(1, min(5, value))
    return normalized


def render_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    verdict_counts = Counter(row["visual_grounding_verdict"] for row in rows)
    leakage_counts = Counter(row["leakage_risk"] for row in rows)
    lines = [
        "# Business Task Visual Grounding Review",
        "",
        f"- Reviewed tasks: {len(rows)}",
        f"- Verdict distribution: {dict(verdict_counts)}",
        f"- Leakage risk distribution: {dict(leakage_counts)}",
        "",
        "## Priority Fixes",
        "",
        "| Safe Task | Verdict | Leakage | Main Issue | Recommended Fix |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        if row["visual_grounding_verdict"] != "strong_fit" or row["leakage_risk"] != "none":
            lines.append(
                f"| {row['safe_task']} | `{row['visual_grounding_verdict']}` | `{row['leakage_risk']}` | "
                f"{row['main_issue']} | {row['recommended_fix']} |"
            )

    for verdict in ["strong_fit", "needs_minor_rewrite", "needs_workflow_redesign"]:
        lines.extend(
            [
                "",
                f"## {verdict}",
                "",
                "| Safe Task | Case ID | Misleader | Operation | Scores | Issue |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in rows:
            if row["visual_grounding_verdict"] != verdict:
                continue
            scores = (
                f"VTA={row['visual_to_action_score']}, "
                f"MA={row['misleading_alignment_score']}, "
                f"WR={row['workflow_realism_score']}, "
                f"FR={row['field_relevance_score']}"
            )
            lines.append(
                f"| {row['safe_task']} | `{row['case_id']}` | `{row['misleader_type']}` | "
                f"`{row['reasoning_operation']}` | {scores} | {row['main_issue']} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    if args.force:
        for path in [args.output, args.markdown, args.log]:
            if path.exists():
                path.unlink()

    existing: dict[str, dict[str, Any]] = {}
    if args.output.exists() and not args.force:
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("main_issue", "")).startswith("LLM review failed:"):
                continue
            existing[row["task_id"]] = row

    os.environ.setdefault("LLM_BACKEND", "hexin_openai")
    os.environ.setdefault("HEXIN_MODEL", args.model)

    from adversarial_pipeline.llm_client import complete_vision, make_client

    client = make_client()

    tasks = load_business_tasks(args.tasks)
    reviewed: list[dict[str, Any]] = []
    for idx, task in enumerate(tasks, start=1):
        safe_task = f"b{idx:03d}"
        if task["task_id"] in existing:
            reviewed.append(existing[task["task_id"]])
            continue
        image_path = Path(task["chart_asset"]["figure_path"])
        started = time.time()
        try:
            raw = complete_vision(
                client,
                SYSTEM_PROMPT,
                build_prompt(task, safe_task),
                image_path,
                model=args.model,
                max_output_tokens=args.max_output_tokens,
            )
            parsed = extract_json(raw)
            normalized = normalize_review(parsed)
            row = {
                "safe_task": safe_task,
                "task_id": task["task_id"],
                "case_id": task["case_id"],
                "scenario": task.get("scenario"),
                "misleader_type": task.get("misleader_type"),
                "plot_type": task.get("plot_type"),
                "reasoning_operation": task.get("reasoning_operation"),
                "llm_model": args.model,
                "llm_called": True,
                **normalized,
                "elapsed_sec": round(time.time() - started, 3),
            }
            append_jsonl(args.output, row)
            append_jsonl(
                args.log,
                {
                    "safe_task": safe_task,
                    "task_id": task["task_id"],
                    "case_id": task["case_id"],
                    "raw_text": raw,
                    "parsed": parsed,
                    "normalized": normalized,
                    "elapsed_sec": row["elapsed_sec"],
                },
            )
            reviewed.append(row)
            print(f"[{safe_task}] {row['visual_grounding_verdict']} leakage={row['leakage_risk']}")
        except Exception as exc:
            row = {
                "safe_task": safe_task,
                "task_id": task["task_id"],
                "case_id": task["case_id"],
                "scenario": task.get("scenario"),
                "misleader_type": task.get("misleader_type"),
                "plot_type": task.get("plot_type"),
                "reasoning_operation": task.get("reasoning_operation"),
                "llm_model": args.model,
                "llm_called": True,
                "visual_grounding_verdict": "needs_minor_rewrite",
                "visual_to_action_score": 1,
                "misleading_alignment_score": 1,
                "workflow_realism_score": 1,
                "field_relevance_score": 1,
                "leakage_risk": "minor",
                "main_issue": f"LLM review failed: {exc}",
                "recommended_fix": "Re-run GPT review for this task.",
                "is_chart_interpretation_required_for_success": False,
                "does_misread_lead_to_wrong_action": False,
                "does_workflow_degenerate_to_chart_qa": False,
                "elapsed_sec": round(time.time() - started, 3),
            }
            append_jsonl(args.output, row)
            append_jsonl(args.log, {"safe_task": safe_task, "task_id": task["task_id"], "error": str(exc)})
            reviewed.append(row)
            print(f"[{safe_task}] ERROR {exc}")

    ordered = sorted(reviewed, key=lambda row: row["safe_task"])
    args.output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in ordered) + "\n",
        encoding="utf-8",
    )
    render_markdown(ordered, args.markdown)
    missing = REQUIRED_FIELDS - set(ordered[0].keys()) if ordered else REQUIRED_FIELDS
    if missing:
        raise RuntimeError(f"Review rows missing fields: {sorted(missing)}")
    if len(ordered) != len(tasks):
        raise RuntimeError(f"Expected {len(tasks)} review rows, got {len(ordered)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--max-output-tokens", type=int, default=1400)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
