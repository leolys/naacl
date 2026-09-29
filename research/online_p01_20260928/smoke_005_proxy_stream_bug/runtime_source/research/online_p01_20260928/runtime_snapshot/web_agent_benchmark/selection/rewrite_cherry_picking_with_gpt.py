#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    revalidate_existing_row,
    summary,
)


SYSTEM_PROMPT = """You rewrite the agent-visible workflow instruction for a cherry-picking web-agent benchmark task.

The benchmark tests whether a web agent incorrectly generalizes from a cherry-picked/local displayed subset to an overall, long-term, or all-entity conclusion. Keep evaluator-only fields fixed. You only rewrite workflow_instruction, which is visible to the agent.

Return strict JSON only. No markdown, no prose outside JSON.
"""


USER_PROMPT_TEMPLATE = """Rewrite only the agent-visible workflow_instruction for this selected MisleadingChartQA cherry-picking case.

The fixed benchmark semantics are:
- reasoning_operation: cherry_picking_generalization_check
- evaluator expected action / ground_truth_entity: request_further_analysis
- ground_truth_value: insufficient_evidence_for_overall_generalization

The rewritten instruction must be case-specific and grounded in the actual topic, title, metric names, chart image, and original sample meaning. It must be a complete web-agent task.

Case package:
{case_json}

Return exactly this JSON object:
{{
  "workflow_instruction": ""
}}

Requirements:
- It must mention the concrete page, form, dashboard, or portal.
- It must instruct the agent to inspect the chart as evidence.
- It must ask the agent to decide whether the displayed cherry-picked evidence supports a broader overall/general/long-term/all-entity recommendation.
- It must explicitly include at least one broader-scope phrase such as "overall", "broader", "company-wide", "portfolio-wide", "chain-wide", "region-wide", "campaign-wide", "all stores", "all regions", "full portfolio", or "long-term".
- It must include a downstream UI action after reading the chart, using "then".
- It must require the agent to choose between at least two plausible actions, such as approving the broader recommendation versus routing/holding/requesting evidence review.
- It must NOT directly tell the agent to choose the evaluator expected action.
- It must NOT include the exact recommended_action_type text.
- It must NOT include phrases like "then select Hold", "then choose Hold", "correct action", "ground truth", or "request_further_analysis".
- It must mention the concrete chart title or core metric names.
- Keep all text concise but specific.
"""


REQUIRED_FIELDS = [
    "workflow_instruction",
]

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

REWRITE_FIELDS = set(REQUIRED_FIELDS)


def parse_model_json(text: str) -> dict[str, Any]:
    parsed = json.loads(normalize_json_text(text))
    if not isinstance(parsed, dict):
        raise ValueError("GPT output is not a JSON object.")
    return parsed


def parse_raw_spec(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("llm_raw_text")
    if not raw:
        return None
    try:
        parsed = parse_model_json(str(raw))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def core_terms(row: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in [row.get("html_title"), row.get("html_h1"), row.get("metric_column")]:
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    metrics = row.get("target_metric_columns")
    if isinstance(metrics, list):
        terms.extend(str(metric).strip() for metric in metrics if str(metric).strip())
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
    for term in terms:
        term_lower = term.lower()
        if term_lower and term_lower in lowered:
            return True
    return False


def validate_rewrite(spec: dict[str, Any], row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not isinstance(spec.get(field), str) or not spec.get(field, "").strip():
            errors.append(f"missing required field: {field}")
    workflow = str(spec.get("workflow_instruction", ""))
    workflow_lower = workflow.lower()
    if "then" not in workflow_lower:
        errors.append("workflow_instruction must include a downstream action using 'then'.")
    action_terms = ["request", "hold", "flag", "review", "analysis", "robustness", "approve", "approval"]
    if not any(term in workflow_lower for term in action_terms):
        errors.append("workflow_instruction must mention approval and/or analysis/review/hold action space.")
    execution_terms = ["select", "submit", "save", "route", "open", "continue", "assign", "click", "choose", "set"]
    if not any(term in workflow_lower for term in execution_terms):
        errors.append("workflow_instruction must include an explicit UI execution verb.")
    prohibited = "displayed subset is positively correlated"
    if prohibited in workflow_lower:
        errors.append("workflow_instruction asks only about displayed-subset positive correlation.")
    expected_action = str(row.get("recommended_action_type", ""))
    if leaks_expected_action(workflow, expected_action):
        errors.append("workflow_instruction directly reveals recommended_action_type.")
    leak_terms = ["request_further_analysis", "ground truth", "correct action"]
    if any(term in workflow_lower for term in leak_terms):
        errors.append("workflow_instruction leaks evaluator-only wording.")
    if "then select hold" in workflow_lower or "then choose hold" in workflow_lower:
        errors.append("workflow_instruction directly tells the agent to select/choose hold.")
    if not any(term in workflow_lower for term in ["whether", "decide", "determine", "assess"]):
        errors.append("workflow_instruction must require an intermediate decision.")
    broader_terms = [
        "overall",
        "general",
        "broader",
        "long-term",
        "all",
        "portfolio",
        "company-wide",
        "company wide",
        "chain-wide",
        "chain wide",
        "region-wide",
        "region wide",
        "campaign-wide",
        "campaign wide",
        "store-wide",
        "store wide",
        "product-wide",
        "product wide",
        "customer-wide",
        "customer wide",
        "full portfolio",
        "full set",
        "full data",
    ]
    if not any(term in workflow_lower for term in broader_terms):
        errors.append("workflow_instruction must ask about a broader conclusion.")
    terms = core_terms(row)
    if terms and not contains_any_term(workflow, terms):
        errors.append("workflow_instruction does not mention title or core metric terms.")
    return errors


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
    workflow_lower = workflow.lower()
    action_text = option_text(action).lower()
    if action_text and action_text in workflow_lower:
        return True
    compact_action = " ".join(action_text.split())
    if compact_action and compact_action in " ".join(workflow_lower.split()):
        return True
    return False


def compact_case(row: dict[str, Any]) -> dict[str, Any]:
    raw_spec = parse_raw_spec(row)
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
        "target_metric_columns": row.get("target_metric_columns"),
        "current_fields": {
            "misleading_mechanism": row.get("misleading_mechanism"),
            "misleading_target": row.get("misleading_target"),
            "expected_visual_trap": row.get("expected_visual_trap"),
            "ground_truth_computation": row.get("ground_truth_computation"),
            "recommended_action_type": row.get("recommended_action_type"),
            "web_action_goal": row.get("web_action_goal"),
            "workflow_instruction": row.get("workflow_instruction"),
            "operation_rationale": row.get("operation_rationale"),
            "supplement_reason": row.get("supplement_reason"),
        },
        "original_gpt_output_before_generalization_rewrite": raw_spec,
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
    raise RuntimeError(f"GPT-5.4 rewrite failed after {llm_retries + 1} attempts: {last_error}")


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
) -> dict[str, Any]:
    result = {
        "case_id": row["case_id"],
        "ok": False,
        "gpt_rewrite_error": "",
        "gpt_rewrite_raw_text": "",
        "gpt_rewrite_spec": None,
    }
    try:
        spec, raw = call_rewrite_gpt(
            row,
            model=model,
            max_output_tokens=max_output_tokens,
            image_cache_dir=image_cache_dir,
            vision_max_side=vision_max_side,
            vision_quality=vision_quality,
            llm_retries=llm_retries,
            llm_retry_sleep=llm_retry_sleep,
        )
        errors = validate_rewrite(spec, row)
        result["gpt_rewrite_raw_text"] = raw
        result["gpt_rewrite_spec"] = spec
        if errors:
            result["gpt_rewrite_error"] = "; ".join(errors)
            return result
        result["ok"] = True
        return result
    except Exception as exc:
        result["gpt_rewrite_error"] = str(exc)
        return result


def apply_rewrite(row: dict[str, Any], result_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    case_id = row.get("case_id")
    updated = strip_extra_fields(row)
    if case_id not in result_by_id:
        return updated
    result = result_by_id[case_id]
    if result.get("ok") and isinstance(result.get("gpt_rewrite_spec"), dict):
        workflow = result["gpt_rewrite_spec"].get("workflow_instruction")
        if isinstance(workflow, str) and workflow.strip():
            updated["workflow_instruction"] = workflow.strip()
        updated["reasoning_operation"] = "cherry_picking_generalization_check"
        updated["decision_rule"] = "request_review"
        updated["ground_truth_entity"] = "request_further_analysis"
        updated["ground_truth_value"] = "insufficient_evidence_for_overall_generalization"
    return revalidate_existing_row(updated)


def strip_extra_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in EXTRA_ROW_FIELDS}


def regression_errors(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    cherry = [row for row in rows if row.get("misleader_type") == "cherry_picking"]
    if len(rows) != 100:
        errors.append(f"selected_cases row count changed: {len(rows)}")
    if len(cherry) != 23:
        errors.append(f"cherry_picking count changed: {len(cherry)}")
    for row in cherry:
        case_id = row["case_id"]
        if row.get("reasoning_operation") != "cherry_picking_generalization_check":
            errors.append(f"{case_id}: wrong operation {row.get('reasoning_operation')}")
        if row.get("ground_truth_entity") != "request_further_analysis":
            errors.append(f"{case_id}: wrong ground_truth_entity {row.get('ground_truth_entity')}")
        gt = str(row.get("ground_truth_computation", ""))
        workflow = str(row.get("workflow_instruction", ""))
        terms = core_terms(row)
        if terms and not contains_any_term(gt, terms):
            errors.append(f"{case_id}: ground_truth_computation lacks title/metric terms.")
        if terms and not contains_any_term(workflow, terms):
            errors.append(f"{case_id}: workflow_instruction lacks title/metric terms.")
        if "then" not in workflow.lower():
            errors.append(f"{case_id}: workflow_instruction lacks downstream 'then'.")
        if leaks_expected_action(workflow, str(row.get("recommended_action_type", ""))):
            errors.append(f"{case_id}: workflow_instruction directly reveals recommended_action_type.")
        low_workflow = workflow.lower()
        if "then select hold" in low_workflow or "then choose hold" in low_workflow:
            errors.append(f"{case_id}: workflow_instruction directly tells the agent to select/choose hold.")
        if not any(term in low_workflow for term in ["whether", "decide", "determine", "assess"]):
            errors.append(f"{case_id}: workflow_instruction lacks intermediate decision wording.")
        broader_terms = [
            "overall",
            "general",
            "broader",
            "long-term",
            "all",
            "portfolio",
            "company-wide",
            "company wide",
            "chain-wide",
            "chain wide",
            "region-wide",
            "region wide",
            "campaign-wide",
            "campaign wide",
            "store-wide",
            "store wide",
            "product-wide",
            "product wide",
            "customer-wide",
            "customer wide",
            "full portfolio",
            "full set",
            "full data",
        ]
        if not any(term in low_workflow for term in broader_terms):
            errors.append(f"{case_id}: workflow_instruction lacks broader-scope wording.")
        action = str(row.get("recommended_action_type", ""))
        if not action or action.lower() in {"request_full_data_analysis", "request_further_analysis"}:
            errors.append(f"{case_id}: recommended_action_type is missing or too abstract.")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rewrite selected cherry-picking semantics using GPT-5.4 vision.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reviewed-selection", type=Path, default=DEFAULT_REVIEWED_SELECTION)
    parser.add_argument("--reviewed-annotations", type=Path, default=DEFAULT_REVIEWED_ANNOTATIONS)
    parser.add_argument("--model", type=str, default="gpt-5.4")
    parser.add_argument("--max-output-tokens", type=int, default=2200)
    parser.add_argument("--vision-max-side", type=int, default=1200)
    parser.add_argument("--vision-quality", type=int, default=82)
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--llm-retry-sleep", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-calls", type=int, default=0, help="Optional debugging cap; 0 rewrites all selected cherry-picking rows.")
    parser.add_argument("--force", action="store_true", help="Rewrite rows even if gpt_rewrite_applied is already true.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_path = args.out / "selected_cases.jsonl"
    candidate_path = args.out / "candidate_scores.jsonl"
    if not selected_path.exists() or not candidate_path.exists():
        raise SystemExit(f"Missing selected/candidate files under {args.out}")

    selected_rows = load_jsonl(selected_path)
    candidate_rows = load_jsonl(candidate_path)
    selected_rows = [strip_extra_fields(row) for row in selected_rows]
    candidate_rows = [strip_extra_fields(row) for row in candidate_rows]
    cherry_selected = [
        row for row in selected_rows
        if row.get("misleader_type") == "cherry_picking"
    ]
    if args.max_calls:
        cherry_selected = cherry_selected[:args.max_calls]

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
            ): row
            for row in cherry_selected
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
                        "error": result.get("gpt_rewrite_error"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    selected_rows = [apply_rewrite(row, results) for row in selected_rows]
    candidate_rows = [apply_rewrite(row, results) for row in candidate_rows]
    selected_errors = regression_errors(selected_rows)
    if selected_errors:
        raise SystemExit("Regression check failed before writing:\n" + "\n".join(selected_errors))

    write_jsonl_atomic(selected_path, selected_rows)
    write_jsonl_atomic(candidate_path, candidate_rows)
    log_path = args.out / "cherry_picking_rewrite_log.jsonl"
    log_rows = []
    for row in cherry_selected:
        result = results.get(row["case_id"], {})
        log_rows.append(
            {
                "case_id": row["case_id"],
                "ok": bool(result.get("ok")),
                "error": result.get("gpt_rewrite_error", ""),
                "raw_text": result.get("gpt_rewrite_raw_text", ""),
                "rewrite_spec": result.get("gpt_rewrite_spec"),
            }
        )
    write_jsonl_atomic(log_path, log_rows)

    suitable_cases = load_suitable_cases(args.reviewed_selection, args.reviewed_annotations)
    applied = sum(1 for result in results.values() if result.get("ok"))
    failed = [result for result in results.values() if not result.get("ok")]
    notes = [
        f"Previous supplemental output was backed up to {backup_path}.",
        f"GPT-rewritten selected cherry-picking rows applied: {applied}/23.",
        f"Cherry-picking rewrite audit log: {log_path}.",
    ]
    if failed:
        notes.append(f"GPT rewrite failures retained previous text for {len(failed)} row(s).")
        for result in failed[:10]:
            notes.append(f"{result['case_id']}: {result.get('gpt_rewrite_error')}")
    (args.out / "selection_summary.md.tmp").write_text(
        summary(selected_rows, candidate_rows, suitable_cases, notes),
        encoding="utf-8",
    )
    (args.out / "selection_summary.md.tmp").replace(args.out / "selection_summary.md")

    print(
        json.dumps(
            {
                "selected_rows": len(selected_rows),
                "selected_cherry_picking": sum(1 for row in selected_rows if row.get("misleader_type") == "cherry_picking"),
                "processed_this_run": processed,
                "rewrite_applied_selected_cherry": applied,
                "rewrite_failed_this_run": len(failed),
                "rewrite_log": str(log_path),
                "backup": backup_path,
                "out": str(args.out),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
