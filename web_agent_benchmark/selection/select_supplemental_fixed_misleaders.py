#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from supplemental_fixed_prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from task_operations import SUPPORTED_OPERATIONS, validate_task_spec


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "baseline" / "MisleadingChartQA-main" / "dataset"
DEFAULT_OUT = REPO_ROOT / "web_agent_benchmark" / "selected_cases_supplemental_fixed_misleaders"
CONFIG_PATH = SCRIPT_DIR / "scenario_config.json"
DEFAULT_REVIEWED_SELECTION = REPO_ROOT / "web_agent_benchmark" / "selected_cases_target_aware" / "selected_cases.jsonl"
DEFAULT_REVIEWED_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark" / "selected_cases_target_aware" / "review_annotations.json"

ALLOWED_MISLEADERS = {
    "cherry_picking",
    "MS_inappropriate_scale_range",
    "misuse_of_cumulative_relationship",
    "misleading_annotations",
}

SCENARIOS = {"business_operations", "public_statistics", "education_hr", "health_environment"}

PREFERRED_OPERATIONS = {
    "cherry_picking": {"cherry_picking_generalization_check"},
    "MS_inappropriate_scale_range": {"relative_difference_judgment", "threshold_judgment", "largest_change", "extreme_value"},
    "misuse_of_cumulative_relationship": {"cumulative_vs_recent_change", "trend_direction", "largest_recent_change"},
    "misleading_annotations": {"annotation_claim_verification", "trend_direction", "pairwise_comparison", "threshold_judgment", "extreme_value"},
}

sys.path.insert(0, str(SCRIPT_DIR))
from select_cases import (  # noqa: E402
    choose_columns,
    extract_html_text,
    keyword_hits,
    load_json,
    read_csv_rows,
    workflow_suitability,
)
from select_cases_target_aware import (  # noqa: E402
    append_jsonl,
    csv_summary,
    load_jsonl,
    normalize_json_text,
    prepare_llm_image,
    write_jsonl_atomic,
)


def parse_model_json(text: str) -> dict[str, Any]:
    return json.loads(normalize_json_text(text))


def parse_raw_llm_spec(row: dict[str, Any]) -> dict[str, Any] | None:
    raw_text = row.get("llm_raw_text")
    if not raw_text:
        return None
    try:
        parsed = parse_model_json(str(raw_text))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def candidate_key(row: dict[str, Any]) -> str:
    return str(row["case_id"])


def load_suitable_ids(selection_path: Path, annotations_path: Path) -> set[str]:
    if not selection_path.exists() or not annotations_path.exists():
        return set()
    selection_ids = {row["case_id"] for row in load_jsonl(selection_path)}
    obj = json.loads(annotations_path.read_text(encoding="utf-8"))
    annotations = obj.get("annotations", {})
    return {
        case_id
        for case_id, annotation in annotations.items()
        if case_id in selection_ids and annotation.get("status") == "suitable"
    }


def scenario_hint(case_text: str, config: dict[str, Any]) -> tuple[str, dict[str, int]]:
    hits = {
        scenario: keyword_hits(case_text, scenario_config["keywords"])
        for scenario, scenario_config in config["scenarios"].items()
    }
    scenario = max(hits, key=lambda key: (hits[key], key))
    return scenario, hits


def build_candidates(dataset: Path, config: dict[str, Any], exclude_ids: set[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    data_root = dataset / "data"
    figure_root = dataset / "figures"
    code_root = dataset / "code"

    for misleader_type in sorted(ALLOWED_MISLEADERS):
        for csv_path in sorted((data_root / misleader_type).rglob("*.csv")):
            rel = csv_path.relative_to(data_root)
            if len(rel.parts) < 3:
                continue
            plot_type = rel.parts[1]
            case_id = str(rel.with_suffix(""))
            if case_id in exclude_ids:
                continue
            figure_path = (figure_root / rel).with_suffix(".jpeg")
            if not figure_path.exists():
                continue
            html_path = (code_root / rel).with_suffix(".html")
            html_meta = extract_html_text(html_path if html_path.exists() else None)
            try:
                headers, rows = read_csv_rows(csv_path)
            except Exception:
                continue
            if len(rows) < 2 or not headers:
                continue
            entity_column, metric_column = choose_columns(headers, rows, config)
            if not metric_column:
                continue
            sample_rows = rows[:5]
            case_text = " ".join(
                [
                    misleader_type,
                    plot_type,
                    " ".join(headers),
                    " ".join(" ".join(row.values()) for row in sample_rows),
                    html_meta["title"],
                    html_meta["h1"],
                ]
            )
            hint, hits = scenario_hint(case_text, config)
            candidates.append(
                {
                    "case_id": case_id,
                    "scenario": hint,
                    "scenario_keyword_hits_by_scene": hits,
                    "misleader_type": misleader_type,
                    "plot_type": plot_type,
                    "figure_path": str(figure_path),
                    "csv_path": str(csv_path),
                    "html_path": str(html_path) if html_path.exists() else "",
                    "html_title": html_meta["title"],
                    "html_h1": html_meta["h1"],
                    "csv_headers": headers,
                    "sample_rows": sample_rows,
                    "entity_column": entity_column or "",
                    "metric_column": metric_column,
                    "decision_rule": "max",
                    "scenario_fit_score": max(1, min(5, 1 + max(hits.values()) // 2)),
                    "misleading_strength_score": 5,
                    "workflow_suitability_score": workflow_suitability(rows, entity_column or headers[0], metric_column),
                    "keep": True,
                    "selection_source": "supplemental-fixed-heuristic-recall",
                }
            )
    return candidates


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    summary = csv_summary(Path(candidate["csv_path"]))
    return {
        "case_id": candidate["case_id"],
        "scenario_hint": candidate["scenario"],
        "scenario_keyword_hits_by_scene": candidate.get("scenario_keyword_hits_by_scene", {}),
        "allowed_scenarios": sorted(SCENARIOS),
        "misleader_type": candidate["misleader_type"],
        "plot_type": candidate["plot_type"],
        "html_title": candidate.get("html_title", ""),
        "html_h1": candidate.get("html_h1", ""),
        "csv_path": candidate["csv_path"],
        "figure_path": candidate["figure_path"],
        "csv_summary": summary,
        "heuristic_entity_column": candidate.get("entity_column"),
        "heuristic_metric_column": candidate.get("metric_column"),
    }


def call_gpt54_vision(
    candidate: dict[str, Any],
    model: str,
    max_output_tokens: int,
    *,
    image_cache_dir: Path,
    vision_max_side: int,
    vision_quality: int,
    llm_retries: int,
    llm_retry_sleep: float,
) -> tuple[dict[str, Any], str, Path]:
    os.environ.setdefault("LLM_BACKEND", "hexin_openai")
    os.environ.setdefault("HEXIN_MODEL", model)
    sys.path.insert(0, str(REPO_ROOT))
    from adversarial_pipeline.llm_client import complete_vision, make_client

    client = make_client()
    llm_image_path = prepare_llm_image(
        Path(candidate["figure_path"]),
        image_cache_dir,
        max_side=vision_max_side,
        quality=vision_quality,
    )
    prompt = USER_PROMPT_TEMPLATE.format(
        candidate_json=json.dumps(compact_candidate(candidate), ensure_ascii=False, indent=2),
    )
    last_error: Exception | None = None
    for attempt in range(max(1, llm_retries + 1)):
        try:
            raw = complete_vision(
                client,
                SYSTEM_PROMPT,
                prompt,
                str(llm_image_path),
                model=model,
                max_output_tokens=max_output_tokens,
            )
            return parse_model_json(raw), raw, llm_image_path
        except Exception as exc:
            last_error = exc
            if attempt < llm_retries:
                time.sleep(llm_retry_sleep * (attempt + 1))
    raise RuntimeError(f"GPT-5.4 vision call failed after {llm_retries + 1} attempts: {last_error}")


def normalize_spec(spec: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(spec)
    normalized.setdefault("scenario", candidate["scenario"])
    if normalized.get("scenario") not in SCENARIOS:
        normalized["scenario"] = candidate["scenario"]
    normalized.setdefault("keep", False)
    normalized.setdefault("target_metric_columns", [])
    if isinstance(normalized.get("target_metric_columns"), str):
        normalized["target_metric_columns"] = [normalized["target_metric_columns"]]
    normalized.setdefault("comparison_entities", [])
    normalized.setdefault("time_column", None)
    normalized.setdefault("top_k", 1)
    normalized.setdefault("decision_rule", "max")
    normalized.setdefault("threshold_value", None)
    normalized.setdefault("threshold_direction", None)
    normalized.setdefault("operation_rationale", "")
    normalized.setdefault("supplement_reason", "")
    for score_key in ["scenario_fit_score", "misleading_alignment_score", "workflow_suitability_score"]:
        try:
            normalized[score_key] = int(normalized.get(score_key, 1))
        except Exception:
            normalized[score_key] = 1
        normalized[score_key] = max(1, min(5, normalized[score_key]))
    return normalized


def _numeric_columns_from_sample(candidate: dict[str, Any]) -> list[str]:
    headers = [str(header) for header in candidate.get("csv_headers", []) if header]
    rows = candidate.get("sample_rows", [])
    numeric_columns: list[str] = []
    for header in headers:
        numeric_count = 0
        for row in rows:
            try:
                value = str(row.get(header, "")).strip().replace(",", "").replace("%", "")
                if value:
                    float(value)
                    numeric_count += 1
            except Exception:
                pass
        if numeric_count >= 2:
            numeric_columns.append(header)
    return numeric_columns


def _infer_time_column_from_candidate(candidate: dict[str, Any], metric_columns: list[str]) -> str:
    metric_set = set(metric_columns)
    headers = [str(header) for header in candidate.get("csv_headers", []) if header]
    for header in headers:
        if header not in metric_set and header.lower() in {"time", "date", "year", "month", "quarter", "period"}:
            return header
    for header in headers:
        if header not in metric_set:
            return header
    return ""


def _title_for_candidate(candidate: dict[str, Any]) -> str:
    return (
        str(candidate.get("html_title") or "").strip()
        or str(candidate.get("html_h1") or "").strip()
        or str(candidate.get("case_id") or "").strip()
    )


def _relationship_phrase(metric_columns: list[str], candidate: dict[str, Any]) -> str:
    title = _title_for_candidate(candidate)
    if len(metric_columns) >= 2:
        return f"the relationship between {metric_columns[0]} and {metric_columns[1]}"
    if metric_columns:
        time_column = candidate.get("time_column") or _infer_time_column_from_candidate(candidate, metric_columns)
        if time_column:
            return f"the trend of {metric_columns[0]} over {time_column}"
        return f"the pattern in {metric_columns[0]}"
    return f"the pattern shown in {title}"


def _columns_phrase(columns: list[str]) -> str:
    if not columns:
        return "the plotted metric columns"
    if len(columns) == 1:
        return columns[0]
    return ", ".join(columns[:-1]) + f" and {columns[-1]}"


def _scenario_workflow_context(scenario: str) -> str:
    contexts = {
        "business_operations": "campaign or budget-planning workflow",
        "public_statistics": "public-statistics evidence review workflow",
        "education_hr": "education or HR policy review workflow",
        "health_environment": "health or environmental monitoring workflow",
    }
    return contexts.get(scenario, "evidence review workflow")


def _tempting_action_text(spec: dict[str, Any], relationship: str) -> str:
    for key in ["web_action_goal", "workflow_instruction", "misleading_target"]:
        value = str(spec.get(key) or "").strip()
        if value:
            return value
    return f"approving a recommendation based on {relationship}"


def normalize_cherry_picking_spec(spec: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("misleader_type") != "cherry_picking":
        return spec
    normalized = dict(spec)
    numeric_columns = _numeric_columns_from_sample(candidate)
    existing_metrics = [str(col) for col in normalized.get("target_metric_columns", []) if col]
    if candidate.get("plot_type") == "scatter_plot":
        metric_columns = existing_metrics[:2] if len(existing_metrics) >= 2 else numeric_columns[:2]
    else:
        metric_columns = existing_metrics[:1] if existing_metrics else numeric_columns[:1]
        normalized["time_column"] = normalized.get("time_column") or _infer_time_column_from_candidate(candidate, metric_columns)
    title = _title_for_candidate(candidate)
    relationship = _relationship_phrase(metric_columns, {**candidate, **normalized})
    columns_text = _columns_phrase(metric_columns)
    workflow_context = _scenario_workflow_context(str(normalized.get("scenario") or candidate.get("scenario") or ""))
    tempting_action = _tempting_action_text(spec, relationship)
    original_mechanism = str(spec.get("misleading_mechanism") or "").strip()
    default_fields = {
        "misleading_target": (
            f"whether the selected local subset in '{title}' is sufficient evidence for an overall, "
            f"general, long-term, or all-entity conclusion about {relationship}"
        ),
        "expected_visual_trap": (
            f"The agent may see the local pattern in '{title}', treat it as evidence about {relationship}, "
            "and wrongly generalize the selected subset into an overall rule."
        ),
        "ground_truth_computation": (
            f"For '{title}', the CSV columns {columns_text} describe only the displayed "
            f"cherry-picked subset used to show {relationship}. That subset can support a local chart reading, "
            "but it cannot establish the overall/general relationship required by the downstream decision. "
            "Therefore the CSV-verifiable ground truth is request_further_analysis, not approval of the "
            f"tempting action: {tempting_action}"
        ),
        "web_action_goal": "Submit a full-data analysis request for the overall recommendation.",
        "recommended_action_type": "Submit a full-data analysis request for the overall recommendation.",
        "workflow_instruction": (
            f"In the {workflow_context}, review the chart '{title}' about {relationship}. Decide whether the "
            "selected subset is enough to support an overall conclusion, and then choose the downstream action "
            "'Request full-data analysis' or 'Flag for evidence review' instead of approving the recommendation "
            "from the visible subset."
        ),
        "operation_rationale": (
            f"Cherry-picking misleads by making the local displayed pattern about {relationship} look like an "
            "overall rule; the benchmark should test whether the agent refuses that generalization."
        ),
        "supplement_reason": "Rewritten from local displayed-subset reasoning to cherry-picking generalization check.",
    }

    normalized.update(
        {
            "keep": bool(normalized.get("keep", True)),
            "reasoning_operation": "cherry_picking_generalization_check",
            "target_entity_column": "",
            "target_metric_columns": metric_columns,
            "comparison_entities": [],
            "top_k": 1,
            "decision_rule": "request_review",
            "threshold_value": None,
            "threshold_direction": None,
            "ground_truth_entity": "request_further_analysis",
            "ground_truth_value": "insufficient_evidence_for_overall_generalization",
        }
    )
    for field, value in default_fields.items():
        if not normalized.get(field):
            normalized[field] = value
    if original_mechanism:
        normalized.setdefault(
            "misleading_mechanism",
            f"{original_mechanism} The benchmark target is the unsafe jump from this local evidence to an "
            f"overall conclusion about {relationship}.",
        )
    if not normalized.get("misleading_mechanism"):
        normalized["misleading_mechanism"] = (
            f"The visualization shows a selected subset in '{title}' that can make a local pattern about "
            f"{relationship} look like evidence for an overall relationship."
        )
    normalized.update(
        {
            "reasoning_operation": "cherry_picking_generalization_check",
            "decision_rule": "request_review",
            "ground_truth_entity": "request_further_analysis",
            "ground_truth_value": "insufficient_evidence_for_overall_generalization",
        }
    )
    return normalized


def apply_spec_fields(output: dict[str, Any], spec: dict[str, Any], candidate: dict[str, Any]) -> None:
    metric_columns = spec.get("target_metric_columns", [])
    output.update(
        {
            "keep": bool(spec.get("keep")),
            "scenario": spec.get("scenario") or candidate["scenario"],
            "misleading_mechanism": spec.get("misleading_mechanism", ""),
            "misleading_target": spec.get("misleading_target", ""),
            "expected_visual_trap": spec.get("expected_visual_trap", ""),
            "reasoning_operation": spec.get("reasoning_operation", ""),
            "target_entity_column": spec.get("target_entity_column", ""),
            "target_metric_columns": metric_columns,
            "entity_column": spec.get("target_entity_column", ""),
            "metric_column": metric_columns[0] if metric_columns else "",
            "time_column": spec.get("time_column"),
            "comparison_entities": spec.get("comparison_entities", []),
            "top_k": spec.get("top_k", 1),
            "decision_rule": spec.get("decision_rule", "max"),
            "threshold_value": spec.get("threshold_value"),
            "threshold_direction": spec.get("threshold_direction"),
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
            "selection_source": "gpt-5.4-vision-supplemental-fixed-misleaders",
        }
    )
    output["risk_description"] = output["misleading_mechanism"]


def validate_output_row(output: dict[str, Any], candidate: dict[str, Any]) -> None:
    output["validation_passed"] = False
    output["validation_error"] = None
    if output["misleader_type"] not in ALLOWED_MISLEADERS:
        output["validation_error"] = f"Unsupported supplemental misleader_type: {output['misleader_type']}"
    elif output["scenario"] not in SCENARIOS:
        output["validation_error"] = f"Unsupported scenario: {output['scenario']}"
    elif not output["keep"]:
        output["validation_error"] = "LLM marked keep=false."
    elif output["reasoning_operation"] not in SUPPORTED_OPERATIONS:
        output["validation_error"] = f"Unsupported operation for selection: {output['reasoning_operation']}"
    elif "then" not in output.get("workflow_instruction", "").lower():
        output["validation_error"] = "workflow_instruction does not clearly include a downstream web action."
    elif output["reasoning_operation"] == "extreme_value" and not output.get("operation_rationale"):
        output["validation_error"] = "extreme_value requires operation_rationale in supplemental selection."
    else:
        headers, rows = read_csv_rows(Path(candidate["csv_path"]))
        validation = validate_task_spec(rows=rows, headers=headers, spec=output)
        if validation.valid:
            output["validation_passed"] = True
            output["ground_truth_entity"] = validation.ground_truth_entity
            output["ground_truth_value"] = validation.ground_truth_value
        else:
            output["validation_error"] = validation.validation_error


def revalidate_existing_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row.get("llm_called") or not row.get("case_id"):
        return row
    output = dict(row)
    if output.get("misleader_type") == "cherry_picking" and output.get("reasoning_operation") == "cherry_picking_generalization_check":
        spec_source = output
    else:
        raw_spec = parse_raw_llm_spec(output) if output.get("misleader_type") == "cherry_picking" else None
        spec_source = raw_spec or (output.get("llm_spec") if isinstance(output.get("llm_spec"), dict) else output)
    spec = normalize_spec(spec_source, output)
    spec = normalize_cherry_picking_spec(spec, output)
    output["llm_spec"] = spec
    apply_spec_fields(output, spec, output)
    validate_output_row(output, output)
    return output


def evaluate_candidate(
    candidate: dict[str, Any],
    *,
    model: str,
    max_output_tokens: int,
    image_cache_dir: Path,
    vision_max_side: int,
    vision_quality: int,
    llm_retries: int,
    llm_retry_sleep: float,
) -> dict[str, Any]:
    started = time.time()
    output: dict[str, Any] = {
        **candidate,
        "target_aware": True,
        "llm_model": model,
        "llm_called": True,
        "validation_passed": False,
        "validation_error": None,
    }
    try:
        spec_raw, raw_text, llm_image_path = call_gpt54_vision(
            candidate,
            model,
            max_output_tokens,
            image_cache_dir=image_cache_dir,
            vision_max_side=vision_max_side,
            vision_quality=vision_quality,
            llm_retries=llm_retries,
            llm_retry_sleep=llm_retry_sleep,
        )
        spec = normalize_spec(spec_raw, candidate)
        spec = normalize_cherry_picking_spec(spec, candidate)
        output["llm_raw_text"] = raw_text
        output["llm_image_path"] = str(llm_image_path)
        output["llm_spec"] = spec
    except Exception as exc:
        output["keep"] = False
        output["llm_error"] = str(exc)
        output["elapsed_sec"] = round(time.time() - started, 3)
        return output
    apply_spec_fields(output, spec, candidate)
    validate_output_row(output, candidate)
    output["elapsed_sec"] = round(time.time() - started, 3)
    return output


def pool_candidates(candidates: list[dict[str, Any]], per_misleader: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["misleader_type"]].append(candidate)
    picked: list[dict[str, Any]] = []
    for misleader, rows in sorted(grouped.items()):
        rows.sort(
            key=lambda row: (
                int(row.get("workflow_suitability_score", 1)),
                int(row.get("scenario_fit_score", 1)),
                row.get("plot_type", ""),
                row.get("case_id", ""),
            ),
            reverse=True,
        )
        picked.extend(rows[:per_misleader])
    return picked


def select_supplemental(
    rows: list[dict[str, Any]],
    *,
    target_count: int,
    suitable_scenario_counts: Counter[str],
) -> list[dict[str, Any]]:
    pool = [
        row for row in rows
        if row.get("validation_passed")
        and row.get("keep")
        and row.get("llm_called")
        and row.get("misleader_type") in ALLOWED_MISLEADERS
    ]
    selected: list[dict[str, Any]] = []
    mis_counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    op_counts: Counter[str] = Counter()
    plot_counts: Counter[str] = Counter()
    used: set[str] = set()
    while pool and len(selected) < target_count:
        def key(row: dict[str, Any]) -> tuple[float, int, int, int]:
            score = (
                int(row.get("misleading_alignment_score", 1)) * 4
                + int(row.get("workflow_suitability_score", 1)) * 3
                + int(row.get("scenario_fit_score", 1)) * 2
            )
            if row.get("reasoning_operation") in PREFERRED_OPERATIONS.get(row.get("misleader_type"), set()):
                score += 3
            if row.get("reasoning_operation") == "extreme_value":
                score -= 2
            scenario_total = suitable_scenario_counts[row["scenario"]] + scenario_counts[row["scenario"]]
            penalty = (
                mis_counts[row["misleader_type"]] * 0.9
                + scenario_total * 0.45
                + op_counts[row["reasoning_operation"]] * 0.65
                + plot_counts[row["plot_type"]] * 0.35
            )
            return (
                score - penalty,
                int(row.get("misleading_alignment_score", 1)),
                int(row.get("workflow_suitability_score", 1)),
                int(row.get("scenario_fit_score", 1)),
            )

        pool = [row for row in pool if row["case_id"] not in used]
        pool.sort(key=key, reverse=True)
        chosen = pool.pop(0)
        selected.append(chosen)
        used.add(chosen["case_id"])
        mis_counts[chosen["misleader_type"]] += 1
        scenario_counts[chosen["scenario"]] += 1
        op_counts[chosen["reasoning_operation"]] += 1
        plot_counts[chosen["plot_type"]] += 1
    return selected


def backup_existing_outputs(out_dir: Path) -> str | None:
    if not (out_dir / "selected_cases.jsonl").exists() and not (out_dir / "candidate_scores.jsonl").exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = out_dir.with_name(f"{out_dir.name}_backup_{timestamp}")
    ignore = shutil.ignore_patterns(".image_cache")
    shutil.copytree(out_dir, backup_dir, ignore=ignore)
    return str(backup_dir)


def load_suitable_cases(selection_path: Path, annotations_path: Path) -> list[dict[str, Any]]:
    if not selection_path.exists() or not annotations_path.exists():
        return []
    annotations = json.loads(annotations_path.read_text(encoding="utf-8")).get("annotations", {})
    return [
        row for row in load_jsonl(selection_path)
        if annotations.get(row["case_id"], {}).get("status") == "suitable"
    ]


def summary(
    selected: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    suitable_cases: list[dict[str, Any]],
    notes: list[str],
) -> str:
    combined = suitable_cases + selected
    lines = [
        "# Supplemental Fixed-Misleader Selection Summary",
        "",
        f"- Supplemental selected: {len(selected)}",
        f"- GPT-scored candidates: {len(all_rows)}",
        f"- Validation passed: {sum(1 for row in all_rows if row.get('validation_passed'))}",
        f"- Existing suitable cases: {len(suitable_cases)}",
        f"- Combined usable pool: {len(combined)}",
        "",
        "## Supplemental Distribution",
        "",
        f"- Misleader distribution: {dict(Counter(row['misleader_type'] for row in selected))}",
        f"- Scenario distribution: {dict(Counter(row['scenario'] for row in selected))}",
        f"- Operation distribution: {dict(Counter(row['reasoning_operation'] for row in selected))}",
        f"- Plot distribution: {dict(Counter(row['plot_type'] for row in selected))}",
        f"- Cherry-picking generalization rewrites: {sum(1 for row in selected if row.get('misleader_type') == 'cherry_picking' and row.get('reasoning_operation') == 'cherry_picking_generalization_check')}",
        "",
        "## Combined Distribution",
        "",
        f"- Misleader distribution: {dict(Counter(row['misleader_type'] for row in combined))}",
        f"- Scenario distribution: {dict(Counter(row['scenario'] for row in combined))}",
        f"- Operation distribution: {dict(Counter(row.get('reasoning_operation', '') for row in combined))}",
        "",
    ]
    failure_counts = Counter(row.get("validation_error") or "valid" for row in all_rows if not row.get("validation_passed"))
    if failure_counts:
        lines += ["## Validation Failures", ""]
        for reason, count in failure_counts.most_common(15):
            lines.append(f"- {count}: {reason}")
        lines.append("")

    lines += [
        "## Selected Samples",
        "",
        "| # | case_id | misleader | scenario | operation | ground truth | scores |",
        "|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(selected, 1):
        scores = f"{row.get('scenario_fit_score')}/{row.get('misleading_alignment_score')}/{row.get('workflow_suitability_score')}"
        lines.append(
            f"| {idx} | `{row['case_id']}` | `{row['misleader_type']}` | `{row['scenario']}` | `{row['reasoning_operation']}` | `{row.get('ground_truth_entity')}` | {scores} |"
        )
    if notes:
        lines += ["", "## Notes", ""]
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select supplemental fixed-misleader target-aware cases.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reviewed-selection", type=Path, default=DEFAULT_REVIEWED_SELECTION)
    parser.add_argument("--reviewed-annotations", type=Path, default=DEFAULT_REVIEWED_ANNOTATIONS)
    parser.add_argument("--target-count", type=int, default=100)
    parser.add_argument("--candidate-pool-per-misleader", type=int, default=80)
    parser.add_argument("--model", type=str, default="gpt-5.4")
    parser.add_argument("--max-output-tokens", type=int, default=2000)
    parser.add_argument("--vision-max-side", type=int, default=1200)
    parser.add_argument("--vision-quality", type=int, default=82)
    parser.add_argument("--llm-retries", type=int, default=3)
    parser.add_argument("--llm-retry-sleep", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-llm-calls", type=int, default=0, help="Optional cap for debugging; 0 means no cap.")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    backup_path = backup_existing_outputs(args.out)
    config = load_json(CONFIG_PATH)
    candidate_scores_path = args.out / "candidate_scores.jsonl"
    image_cache_dir = args.out / ".image_cache"
    suitable_cases = load_suitable_cases(args.reviewed_selection, args.reviewed_annotations)
    suitable_ids = {row["case_id"] for row in suitable_cases}
    suitable_scenario_counts = Counter(row["scenario"] for row in suitable_cases)

    all_candidates = build_candidates(args.dataset, config, suitable_ids)
    candidates = pool_candidates(all_candidates, args.candidate_pool_per_misleader)
    existing_rows = load_jsonl(candidate_scores_path) if args.resume else []
    if existing_rows:
        existing_rows = [revalidate_existing_row(row) for row in existing_rows]
        write_jsonl_atomic(candidate_scores_path, existing_rows)
    existing_by_key = {candidate_key(row): row for row in existing_rows if row.get("case_id")}
    pending = [candidate for candidate in candidates if candidate_key(candidate) not in existing_by_key]
    if args.max_llm_calls:
        pending = pending[:args.max_llm_calls]

    processed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                evaluate_candidate,
                candidate,
                model=args.model,
                max_output_tokens=args.max_output_tokens,
                image_cache_dir=image_cache_dir,
                vision_max_side=args.vision_max_side,
                vision_quality=args.vision_quality,
                llm_retries=args.llm_retries,
                llm_retry_sleep=args.llm_retry_sleep,
            ): candidate
            for candidate in pending
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    **candidate,
                    "target_aware": True,
                    "llm_model": args.model,
                    "llm_called": True,
                    "keep": False,
                    "validation_passed": False,
                    "validation_error": None,
                    "llm_error": f"Unhandled worker error: {exc}",
                }
            append_jsonl(candidate_scores_path, row)
            existing_by_key[candidate_key(candidate)] = row
            processed += 1
            print(
                json.dumps(
                    {
                        "processed": processed,
                        "case_id": candidate["case_id"],
                        "misleader_type": candidate["misleader_type"],
                        "valid": row.get("validation_passed"),
                        "operation": row.get("reasoning_operation"),
                        "error": row.get("validation_error") or row.get("llm_error"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    all_rows = list(existing_by_key.values())
    selected = select_supplemental(
        all_rows,
        target_count=args.target_count,
        suitable_scenario_counts=suitable_scenario_counts,
    )
    notes: list[str] = []
    if backup_path:
        notes.append(f"Previous supplemental output was backed up to {backup_path}.")
    if len(selected) < args.target_count:
        notes.append(f"Selected {len(selected)} of requested {args.target_count}; not enough validated supplemental candidates.")
    write_jsonl_atomic(args.out / "selected_cases.jsonl", selected)
    (args.out / "selection_summary.md.tmp").write_text(summary(selected, all_rows, suitable_cases, notes), encoding="utf-8")
    (args.out / "selection_summary.md.tmp").replace(args.out / "selection_summary.md")
    print(
        json.dumps(
            {
                "available_candidates": len(all_candidates),
                "candidate_pool": len(candidates),
                "gpt_scored": len(all_rows),
                "processed_this_run": processed,
                "selected": len(selected),
                "existing_suitable": len(suitable_cases),
                "out": str(args.out),
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
