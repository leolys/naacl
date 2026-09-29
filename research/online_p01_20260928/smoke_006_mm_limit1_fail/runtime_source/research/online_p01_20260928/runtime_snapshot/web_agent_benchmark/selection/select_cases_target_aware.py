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
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from target_aware_prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from task_operations import SUPPORTED_OPERATIONS, validate_task_spec


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "baseline" / "MisleadingChartQA-main" / "dataset"
DEFAULT_OUT = REPO_ROOT / "web_agent_benchmark" / "selected_cases_target_aware"
CONFIG_PATH = SCRIPT_DIR / "scenario_config.json"

sys.path.insert(0, str(SCRIPT_DIR))
from select_cases import (  # noqa: E402
    action_for_scenario,
    base_sort_key,
    choose_columns,
    extract_html_text,
    infer_decision_rule,
    keyword_hits,
    load_json,
    misleading_strength,
    read_csv_rows,
    risk_description,
    workflow_suitability,
)


def normalize_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    match = re.search(r"\{.*\}", stripped, re.S)
    return match.group(0) if match else stripped


def parse_model_json(text: str) -> dict[str, Any]:
    return json.loads(normalize_json_text(text))


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score_for_pool(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return base_sort_key(candidate)


def candidate_key(candidate: dict[str, Any]) -> str:
    return f"{candidate['scenario']}::{candidate['case_id']}"


def build_target_aware_candidates(dataset: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    data_root = dataset / "data"
    figure_root = dataset / "figures"
    code_root = dataset / "code"

    for csv_path in sorted(data_root.rglob("*.csv")):
        rel = csv_path.relative_to(data_root)
        if len(rel.parts) < 3:
            continue
        misleader_type, plot_type = rel.parts[0], rel.parts[1]
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
        if not entity_column or not metric_column:
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
        for scenario, scenario_config in config["scenarios"].items():
            hits = keyword_hits(case_text, scenario_config["keywords"])
            min_hits = 1 if scenario == "health_environment" else 2
            if hits < min_hits:
                continue
            decision_rule = infer_decision_rule(scenario, metric_column)
            scenario_fit = min(5, max(1, 1 + hits // 2))
            strength = misleading_strength(misleader_type, config["preferred_misleaders"])
            workflow = workflow_suitability(rows, entity_column, metric_column)
            action = action_for_scenario(scenario, config, metric_column)
            case_id = str(rel.with_suffix(""))
            cases.append(
                {
                    "case_id": case_id,
                    "scenario": scenario,
                    "misleader_type": misleader_type,
                    "plot_type": plot_type,
                    "figure_path": str(figure_path),
                    "csv_path": str(csv_path),
                    "html_path": str(html_path) if html_path.exists() else "",
                    "html_title": html_meta["title"],
                    "html_h1": html_meta["h1"],
                    "csv_headers": headers,
                    "sample_rows": sample_rows,
                    "entity_column": entity_column,
                    "metric_column": metric_column,
                    "decision_rule": decision_rule,
                    "ground_truth_entity": "",
                    "recommended_action_type": action,
                    "scenario_keyword_hits": hits,
                    "scenario_fit_score": scenario_fit,
                    "misleading_strength_score": strength,
                    "workflow_suitability_score": workflow,
                    "risk_description": risk_description(scenario, misleader_type, entity_column, metric_column),
                    "keep": True,
                    "selection_source": "target-aware-heuristic-recall",
                }
            )
    return cases


def csv_summary(csv_path: Path, max_rows: int = 50) -> dict[str, Any]:
    headers, rows = read_csv_rows(csv_path)
    sample_rows = rows[:max_rows]
    stats: dict[str, Any] = {}
    for header in headers:
        values = [row.get(header, "") for row in rows if row.get(header, "") != ""]
        numeric: list[float] = []
        for value in values:
            try:
                numeric.append(float(str(value).replace(",", "").replace("%", "")))
            except ValueError:
                pass
        if numeric and len(numeric) >= max(1, int(0.7 * len(values))):
            stats[header] = {
                "type": "numeric",
                "min": min(numeric),
                "max": max(numeric),
                "unique": len(set(numeric)),
            }
        else:
            stats[header] = {
                "type": "categorical",
                "unique": len(set(values)),
                "examples": list(dict.fromkeys(values[:8])),
            }
    return {
        "headers": headers,
        "row_count": len(rows),
        "sample_rows": sample_rows,
        "column_stats": stats,
        "is_full_csv_included": len(rows) <= max_rows,
    }


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    html_path = Path(candidate["html_path"]) if candidate.get("html_path") else None
    html_meta = extract_html_text(html_path if html_path and html_path.exists() else None)
    summary = csv_summary(Path(candidate["csv_path"]))
    return {
        "case_id": candidate["case_id"],
        "scenario": candidate["scenario"],
        "misleader_type": candidate["misleader_type"],
        "plot_type": candidate["plot_type"],
        "html_title": candidate.get("html_title") or html_meta["title"],
        "html_h1": candidate.get("html_h1") or html_meta["h1"],
        "csv_path": candidate["csv_path"],
        "figure_path": candidate["figure_path"],
        "csv_summary": summary,
        "heuristic_entity_column": candidate.get("entity_column"),
        "heuristic_metric_column": candidate.get("metric_column"),
        "heuristic_decision_rule": candidate.get("decision_rule"),
    }


def prepare_llm_image(
    image_path: Path,
    cache_dir: Path,
    *,
    max_side: int,
    quality: int,
) -> Path:
    """Create a smaller JPEG for vision calls while keeping original image paths in outputs."""
    try:
        from PIL import Image
    except ImportError:
        return image_path

    cache_dir.mkdir(parents=True, exist_ok=True)
    stat = image_path.stat()
    digest_src = f"{image_path.resolve()}::{stat.st_mtime_ns}::{stat.st_size}::{max_side}::{quality}"
    digest = hashlib.sha1(digest_src.encode("utf-8")).hexdigest()[:16]
    cached = cache_dir / f"{image_path.stem}-{digest}.jpg"
    if cached.exists() and cached.stat().st_size > 0:
        return cached

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side))
        img.save(cached, format="JPEG", quality=quality, optimize=True)
    return cached


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
        scenario=candidate["scenario"],
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
    normalized.setdefault("keep", False)
    normalized.setdefault("target_metric_columns", [])
    if isinstance(normalized.get("target_metric_columns"), str):
        normalized["target_metric_columns"] = [normalized["target_metric_columns"]]
    normalized.setdefault("comparison_entities", [])
    normalized.setdefault("time_column", None)
    normalized.setdefault("top_k", 1)
    normalized.setdefault("decision_rule", "max")
    normalize_axis_or_scale_rule(normalized)
    for score_key in ["scenario_fit_score", "misleading_alignment_score", "workflow_suitability_score"]:
        try:
            normalized[score_key] = int(normalized.get(score_key, 1))
        except Exception:
            normalized[score_key] = 1
        normalized[score_key] = max(1, min(5, normalized[score_key]))
    return normalized


def metric_mentioned(text: str, metric_columns: list[str]) -> bool:
    lowered = text.lower()
    for metric in metric_columns:
        metric_text = str(metric).strip().lower()
        if not metric_text:
            continue
        if metric_text in lowered or metric_text.replace("_", " ") in lowered:
            return True
    return False


def normalize_axis_or_scale_rule(spec: dict[str, Any]) -> None:
    if spec.get("reasoning_operation") != "axis_or_scale_interpretation":
        return
    original_rule = str(spec.get("decision_rule", "")).strip().lower()
    if original_rule not in {"invert_then_max", "invert_then_min"}:
        return
    metrics = spec.get("target_metric_columns") or []
    if isinstance(metrics, str):
        metrics = [metrics]
    text = str(spec.get("ground_truth_computation", "")).lower()
    if not metric_mentioned(text, [str(metric) for metric in metrics]):
        return
    max_hit = any(term in text for term in ["maximum", "highest", "largest", "max value", "max "])
    min_hit = any(term in text for term in ["minimum", "lowest", "smallest", "min value", "min "])
    if max_hit and not min_hit:
        spec["decision_rule"] = "max"
        spec["decision_rule_normalized_from"] = original_rule
    elif min_hit and not max_hit:
        spec["decision_rule"] = "min"
        spec["decision_rule_normalized_from"] = original_rule


def apply_spec_fields(output: dict[str, Any], spec: dict[str, Any], candidate: dict[str, Any]) -> None:
    output.update(
        {
            "keep": bool(spec.get("keep")),
            "scenario": spec.get("scenario") or candidate["scenario"],
            "misleading_mechanism": spec.get("misleading_mechanism", ""),
            "misleading_target": spec.get("misleading_target", ""),
            "expected_visual_trap": spec.get("expected_visual_trap", ""),
            "reasoning_operation": spec.get("reasoning_operation", ""),
            "target_entity_column": spec.get("target_entity_column", ""),
            "target_metric_columns": spec.get("target_metric_columns", []),
            "time_column": spec.get("time_column"),
            "comparison_entities": spec.get("comparison_entities", []),
            "top_k": spec.get("top_k", 1),
            "decision_rule": spec.get("decision_rule", "max"),
            "decision_rule_normalized_from": spec.get("decision_rule_normalized_from", ""),
            "ground_truth_computation": spec.get("ground_truth_computation", ""),
            "web_action_goal": spec.get("web_action_goal", ""),
            "workflow_instruction": spec.get("workflow_instruction", ""),
            "scenario_fit_score": spec.get("scenario_fit_score", 1),
            "misleading_alignment_score": spec.get("misleading_alignment_score", 1),
            "workflow_suitability_score": spec.get("workflow_suitability_score", 1),
            "selection_source": "gpt-5.4-vision-target-aware",
        }
    )


def validate_output_row(output: dict[str, Any], candidate: dict[str, Any]) -> None:
    output["validation_passed"] = False
    output["validation_error"] = None
    if output["scenario"] != candidate["scenario"]:
        output["validation_error"] = f"LLM scenario mismatch: {output['scenario']} != {candidate['scenario']}"
    elif not output["keep"]:
        output["validation_error"] = "LLM marked keep=false."
    elif output["reasoning_operation"] not in SUPPORTED_OPERATIONS:
        output["validation_error"] = f"Unsupported operation for selection: {output['reasoning_operation']}"
    elif "then" not in output.get("workflow_instruction", "").lower():
        output["validation_error"] = "workflow_instruction does not clearly include a downstream web action."
    else:
        headers, rows = read_csv_rows(Path(candidate["csv_path"]))
        validation = validate_task_spec(rows=rows, headers=headers, spec=output)
        if validation.valid:
            output["validation_passed"] = True
            output["ground_truth_entity"] = validation.ground_truth_entity
            output["ground_truth_value"] = validation.ground_truth_value
            output["entity_column"] = output["target_entity_column"]
            output["metric_column"] = output["target_metric_columns"][0] if output["target_metric_columns"] else ""
            output["recommended_action_type"] = output["web_action_goal"]
        else:
            output["validation_error"] = validation.validation_error


def revalidate_existing_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row.get("llm_called") or not row.get("case_id") or not row.get("scenario"):
        return row
    output = dict(row)
    spec_source = output.get("llm_spec") if isinstance(output.get("llm_spec"), dict) else output
    spec = normalize_spec(spec_source, output)
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


def select_diverse_valid(rows: list[dict[str, Any]], per_scenario: int) -> tuple[list[dict[str, Any]], list[str]]:
    selected: list[dict[str, Any]] = []
    notes: list[str] = []
    used: set[str] = set()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("validation_passed") and row.get("keep") and row.get("llm_called"):
            grouped[row["scenario"]].append(row)

    for scenario in sorted(grouped):
        pool = [row for row in grouped[scenario] if row["case_id"] not in used]
        chosen_for_scenario: list[dict[str, Any]] = []
        mis_counts: Counter[str] = Counter()
        plot_counts: Counter[str] = Counter()
        op_counts: Counter[str] = Counter()
        while pool and len(chosen_for_scenario) < per_scenario:
            def key(row: dict[str, Any]) -> tuple[float, int, int, int]:
                total = (
                    int(row.get("misleading_alignment_score", 1)) * 3
                    + int(row.get("scenario_fit_score", 1)) * 2
                    + int(row.get("workflow_suitability_score", 1)) * 2
                )
                penalty = (
                    mis_counts[row["misleader_type"]] * 1.2
                    + plot_counts[row["plot_type"]] * 0.7
                    + op_counts[row["reasoning_operation"]] * 1.0
                )
                return (
                    total - penalty,
                    int(row.get("misleading_alignment_score", 1)),
                    int(row.get("scenario_fit_score", 1)),
                    int(row.get("workflow_suitability_score", 1)),
                )

            pool.sort(key=key, reverse=True)
            chosen = pool.pop(0)
            chosen_for_scenario.append(chosen)
            used.add(chosen["case_id"])
            mis_counts[chosen["misleader_type"]] += 1
            plot_counts[chosen["plot_type"]] += 1
            op_counts[chosen["reasoning_operation"]] += 1
            pool = [row for row in pool if row["case_id"] not in used]

        if len(chosen_for_scenario) < per_scenario:
            notes.append(f"{scenario}: selected {len(chosen_for_scenario)} of {per_scenario}; not enough validated target-aware candidates.")
        selected.extend(chosen_for_scenario)
    return selected, notes


def summary(selected: list[dict[str, Any]], all_rows: list[dict[str, Any]], notes: list[str]) -> str:
    lines = [
        "# Target-Aware Misleading Visualization Selection Summary",
        "",
        f"- Total selected: {len(selected)}",
        f"- Total GPT-scored candidates: {len(all_rows)}",
        f"- Validation passed: {sum(1 for row in all_rows if row.get('validation_passed'))}",
        f"- GPT errors: {sum(1 for row in all_rows if row.get('llm_error'))}",
        "",
    ]
    failure_counts = Counter(row.get("validation_error") or "valid" for row in all_rows if not row.get("validation_passed"))
    if failure_counts:
        lines.append("## Validation Failures")
        lines.append("")
        for reason, count in failure_counts.most_common(12):
            lines.append(f"- {count}: {reason}")
        lines.append("")

    for scenario in sorted({row["scenario"] for row in selected}):
        items = [row for row in selected if row["scenario"] == scenario]
        lines += [
            f"## {scenario}",
            "",
            f"- Selected: {len(items)}",
            f"- Misleader distribution: {dict(Counter(row['misleader_type'] for row in items))}",
            f"- Plot distribution: {dict(Counter(row['plot_type'] for row in items))}",
            f"- Operation distribution: {dict(Counter(row['reasoning_operation'] for row in items))}",
            "",
            "| # | case_id | misleader | operation | target | ground truth | scores |",
            "|---|---|---|---|---|---|---|",
        ]
        for idx, row in enumerate(items, 1):
            target = str(row.get("misleading_target", "")).replace("|", "/")
            scores = f"{row.get('scenario_fit_score')}/{row.get('misleading_alignment_score')}/{row.get('workflow_suitability_score')}"
            lines.append(
                f"| {idx} | `{row['case_id']}` | `{row['misleader_type']}` | `{row['reasoning_operation']}` | {target} | `{row.get('ground_truth_entity')}` | {scores} |"
            )
        lines += ["", "High-alignment examples:", ""]
        for row in sorted(items, key=lambda r: int(r.get("misleading_alignment_score", 1)), reverse=True)[:5]:
            lines.append(f"- `{row['case_id']}`: {row.get('expected_visual_trap', '')}")
        lines.append("")

    if notes:
        lines += ["## Selection Notes", ""]
        lines.extend(f"- {note}" for note in notes)
        lines.append("")
    return "\n".join(lines)


def candidate_pool_by_scenario(candidates: list[dict[str, Any]], pool_size: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["scenario"]].append(candidate)
    picked: list[dict[str, Any]] = []
    for scenario, rows in sorted(grouped.items()):
        rows = sorted(rows, key=score_for_pool, reverse=True)
        picked.extend(rows[:pool_size])
    return picked


def sorted_candidates_by_scenario(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["scenario"]].append(candidate)
    return {scenario: sorted(rows, key=score_for_pool, reverse=True) for scenario, rows in grouped.items()}


def flatten_pool(
    grouped: dict[str, list[dict[str, Any]]],
    pool_size: int,
    *,
    scenarios: list[str] | None = None,
) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    allowed = set(scenarios) if scenarios is not None else None
    for scenario, rows in sorted(grouped.items()):
        if allowed is not None and scenario not in allowed:
            continue
        picked.extend(rows[:pool_size])
    return picked


def scenario_needs_more(
    selected: list[dict[str, Any]],
    scenario: str,
    per_scenario: int,
    min_misleader_types: int,
) -> bool:
    items = [row for row in selected if row["scenario"] == scenario]
    if len(items) < per_scenario:
        return True
    return len({row["misleader_type"] for row in items}) < min_misleader_types


def selection_complete(
    selected: list[dict[str, Any]],
    scenarios: list[str],
    per_scenario: int,
    min_misleader_types: int,
) -> bool:
    counts = Counter(row["scenario"] for row in selected)
    if not all(counts.get(scenario, 0) >= per_scenario for scenario in scenarios):
        return False
    return all(
        len({row["misleader_type"] for row in selected if row["scenario"] == scenario}) >= min_misleader_types
        for scenario in scenarios
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Target-aware GPT-5.4 selection for MisleadingChartQA web-agent benchmark.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--per-scenario", type=int, default=25)
    parser.add_argument("--min-misleader-types", type=int, default=3)
    parser.add_argument("--candidate-pool", type=int, default=120)
    parser.add_argument("--expand-pools", type=str, default="180,240")
    parser.add_argument("--model", type=str, default="gpt-5.4")
    parser.add_argument("--max-output-tokens", type=int, default=1800)
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
    config = load_json(CONFIG_PATH)
    candidate_scores_path = args.out / "candidate_scores.jsonl"
    image_cache_dir = args.out / ".image_cache"

    all_candidates = build_target_aware_candidates(args.dataset, config)
    grouped_candidates = sorted_candidates_by_scenario(all_candidates)
    scenarios = sorted(grouped_candidates)
    expand_pools = [int(value.strip()) for value in args.expand_pools.split(",") if value.strip()]
    pool_steps = [args.candidate_pool] + [pool for pool in expand_pools if pool > args.candidate_pool]
    existing_rows = load_jsonl(candidate_scores_path) if args.resume else []
    if existing_rows:
        existing_rows = [revalidate_existing_row(row) for row in existing_rows]
        write_jsonl_atomic(candidate_scores_path, existing_rows)
    existing_by_key = {candidate_key(row): row for row in existing_rows if "case_id" in row and "scenario" in row}

    processed_count = 0
    active_pool_size = args.candidate_pool
    selected: list[dict[str, Any]] = []
    notes: list[str] = []
    stop_for_cap = False
    candidates: list[dict[str, Any]] = []
    for pool_size in pool_steps:
        active_pool_size = pool_size
        selected, notes = select_diverse_valid(list(existing_by_key.values()), per_scenario=args.per_scenario)
        pool_scenarios = [
            scenario
            for scenario in scenarios
            if scenario_needs_more(selected, scenario, args.per_scenario, args.min_misleader_types)
        ]
        if not pool_scenarios:
            break
        candidates = flatten_pool(grouped_candidates, pool_size, scenarios=pool_scenarios)
        pending_candidates = [candidate for candidate in candidates if candidate_key(candidate) not in existing_by_key]
        if args.max_llm_calls:
            remaining = args.max_llm_calls - processed_count
            if remaining <= 0:
                stop_for_cap = True
                break
            pending_candidates = pending_candidates[:remaining]

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
                for candidate in pending_candidates
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
                processed_count += 1
                print(
                    json.dumps(
                        {
                            "processed": processed_count,
                            "pool_size": pool_size,
                            "scenario": candidate["scenario"],
                            "case_id": candidate["case_id"],
                            "valid": row.get("validation_passed"),
                            "error": row.get("validation_error") or row.get("llm_error"),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        if args.max_llm_calls and processed_count >= args.max_llm_calls:
            stop_for_cap = True
        all_rows = list(existing_by_key.values())
        selected, notes = select_diverse_valid(all_rows, per_scenario=args.per_scenario)
        if stop_for_cap or selection_complete(selected, scenarios, args.per_scenario, args.min_misleader_types):
            break

    all_rows = list(existing_by_key.values())
    selected, notes = select_diverse_valid(all_rows, per_scenario=args.per_scenario)
    write_jsonl_atomic(args.out / "selected_cases.jsonl", selected)
    summary_text = summary(selected, all_rows, notes)
    summary_tmp = args.out / "selection_summary.md.tmp"
    summary_tmp.write_text(summary_text, encoding="utf-8")
    summary_tmp.replace(args.out / "selection_summary.md")
    print(
        json.dumps(
            {
                "candidate_pool": len(candidates),
                "active_pool_size": active_pool_size,
                "available_candidates": len(all_candidates),
                "gpt_scored": len(all_rows),
                "processed_this_run": processed_count,
                "selected": len(selected),
                "out": str(args.out),
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
