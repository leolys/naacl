#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from selection_prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "baseline" / "MisleadingChartQA-main" / "dataset"
DEFAULT_OUT = REPO_ROOT / "web_agent_benchmark" / "selected_cases"
CONFIG_PATH = Path(__file__).resolve().with_name("scenario_config.json")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_token_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def tokens_for(text: str) -> set[str]:
    return set(normalize_token_text(text).split())


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("%", "")
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return [], []
        headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {str(k).strip(): str(v).strip() for k, v in row.items() if k is not None}
            if any(v for v in cleaned.values()):
                rows.append(cleaned)
        return headers, rows


def extract_html_text(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {"title": "", "h1": ""}
    text = path.read_text(encoding="utf-8", errors="ignore")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
    title = title_match.group(1).strip() if title_match else ""
    h1 = re.sub(r"<.*?>", " ", h1_match.group(1)).strip() if h1_match else ""
    return {"title": re.sub(r"\s+", " ", title), "h1": re.sub(r"\s+", " ", h1)}


def is_numeric_column(rows: list[dict[str, str]], column: str) -> bool:
    values = [row.get(column, "") for row in rows if row.get(column, "") != ""]
    if not values:
        return False
    parsed = sum(parse_float(v) is not None for v in values)
    return parsed / len(values) >= 0.8


def column_values(rows: list[dict[str, str]], column: str) -> list[str]:
    return [row.get(column, "").strip() for row in rows if row.get(column, "").strip()]


def term_hit(column: str, terms: list[str]) -> bool:
    text = normalize_token_text(column)
    return any(term in text for term in terms)


def score_entity_column(column: str, rows: list[dict[str, str]], exclude_terms: list[str]) -> float:
    values = column_values(rows, column)
    unique_values = {v for v in values}
    col_text = normalize_token_text(column)
    temporal_terms = ["year", "month", "day", "date", "quarter", "period", "week"]
    if not values or len(unique_values) < 2:
        return -100.0
    score = 0.0
    if is_numeric_column(rows, column):
        if any(term in col_text for term in temporal_terms):
            score += 2.0
        else:
            return -100.0
    else:
        score += 4.0
    non_entity_exclude = [term for term in exclude_terms if term not in temporal_terms]
    if term_hit(column, non_entity_exclude):
        score -= 5.0
    generic_values = {
        value.lower()
        for value in unique_values
        if re.fullmatch(r"[a-z]", value.strip().lower())
        or re.fullmatch(r"series[_ -]?\d+", value.strip().lower())
    }
    if len(generic_values) >= max(2, len(unique_values) // 2):
        score -= 10.0
    if any(term in col_text for term in ["state", "region", "country", "city", "product", "category", "company"]):
        score += 3.0
    if any(term in col_text for term in ["month", "quarter", "year", "date", "day", "period"]):
        score += 1.0
    if 2 <= len(unique_values) <= 60:
        score += 2.0
    if len(unique_values) > 150:
        score -= 2.0
    avg_len = sum(len(v) for v in values) / max(len(values), 1)
    if avg_len > 40:
        score -= 1.0
    return score


def score_metric_column(
    column: str,
    rows: list[dict[str, str]],
    prefer_terms: list[str],
    exclude_terms: list[str],
) -> float:
    if not is_numeric_column(rows, column):
        return -100.0
    score = 2.0
    col_text = normalize_token_text(column)
    if term_hit(column, exclude_terms):
        score -= 8.0
    if term_hit(column, prefer_terms):
        score += 5.0
    if any(term in col_text for term in ["sales", "revenue", "score", "rate", "share", "emissions"]):
        score += 2.0
    values = [parse_float(v) for v in column_values(rows, column)]
    nums = [v for v in values if v is not None]
    if len(set(nums)) < 2:
        score -= 6.0
    return score


def choose_columns(
    headers: list[str],
    rows: list[dict[str, str]],
    config: dict[str, Any],
) -> tuple[str | None, str | None]:
    exclude_terms = config["decision_metric_exclude_terms"]
    prefer_terms = config["decision_metric_prefer_terms"]
    entity_scores = [
        (score_entity_column(header, rows, exclude_terms), header)
        for header in headers
    ]
    metric_scores = [
        (score_metric_column(header, rows, prefer_terms, exclude_terms), header)
        for header in headers
    ]
    entity_scores.sort(reverse=True)
    metric_scores.sort(reverse=True)
    for _, entity in entity_scores:
        for _, metric in metric_scores:
            entity_score = score_entity_column(entity, rows, exclude_terms)
            metric_score = score_metric_column(metric, rows, prefer_terms, exclude_terms)
            if entity != metric and entity_score > 0 and metric_score > 0:
                return entity, metric
    return None, None


def ground_truth_entity(
    rows: list[dict[str, str]],
    entity_column: str,
    metric_column: str,
    decision_rule: str,
) -> str | None:
    pairs: list[tuple[str, float]] = []
    for row in rows:
        entity = row.get(entity_column, "").strip()
        value = parse_float(row.get(metric_column))
        if entity and value is not None:
            pairs.append((entity, value))
    if not pairs:
        return None
    target = max(v for _, v in pairs) if decision_rule == "max" else min(v for _, v in pairs)
    winners = sorted({entity for entity, value in pairs if value == target})
    if len(winners) != 1:
        return None
    return winners[0]


def infer_decision_rule(scenario: str, metric_column: str) -> str:
    metric = normalize_token_text(metric_column)
    low_is_priority = [
        "score",
        "satisfaction",
        "rating",
        "productivity",
        "uptime",
        "vaccination",
    ]
    if scenario in {"education_hr", "business_operations"} and any(term in metric for term in low_is_priority):
        return "min"
    return "max"


def keyword_hits(text: str, keywords: list[str]) -> int:
    normalized = f" {normalize_token_text(text)} "
    hits = 0
    for keyword in keywords:
        key = normalize_token_text(keyword)
        if key and f" {key} " in normalized:
            hits += 1
    return hits


def misleading_strength(misleader_type: str, preferred: list[str]) -> int:
    base = {
        "cherry_picking": 5,
        "MS_inappropriate_scale_functions": 5,
        "MS_inappropriate_scale_range": 5,
        "MS_unconventional_scale_directions": 5,
        "data_visual_disproportion": 5,
        "dual_encoding": 4,
        "missing_data": 4,
        "missing_normalization": 4,
        "misleading_annotations": 4,
        "misuse_of_cumulative_relationship": 4,
        "concealed_uncertainty": 4,
        "inappropriate_aggregation": 4,
        "lack_of_scales": 3,
        "lack_of_legend": 3,
        "small_size": 3,
        "overplotting": 3,
        "exceeding_the_canvas": 3,
    }
    score = base.get(misleader_type, 2)
    if misleader_type in preferred:
        score = min(5, score + 1)
    return score


def workflow_suitability(rows: list[dict[str, str]], entity_column: str, metric_column: str) -> int:
    entities = {v for v in column_values(rows, entity_column)}
    metric_values = [parse_float(v) for v in column_values(rows, metric_column)]
    nums = [v for v in metric_values if v is not None]
    if len(entities) < 2 or len(set(nums)) < 2:
        return 1
    if 3 <= len(entities) <= 60:
        return 5
    if len(entities) <= 100:
        return 4
    return 3


def action_for_scenario(scenario: str, config: dict[str, Any], metric_column: str) -> str:
    actions = config["scenarios"][scenario]["action_types"]
    metric = normalize_token_text(metric_column)
    if scenario == "business_operations":
        if any(term in metric for term in ["sales", "revenue", "profit", "visits", "share"]):
            return "assign_priority_budget"
        return actions[0]
    if scenario == "public_statistics":
        if any(term in metric for term in ["unemployment", "crimes", "prevalence", "emissions"]):
            return "mark_for_priority_review"
        return actions[1]
    if scenario == "education_hr":
        if any(term in metric for term in ["score", "productivity", "satisfaction"]):
            return "schedule_support_review"
        return actions[1]
    if any(term in metric for term in ["emissions", "pollution", "water", "temperature"]):
        return "flag_for_inspection"
    return actions[0]


def risk_description(scenario: str, misleader_type: str, entity_column: str, metric_column: str) -> str:
    return (
        f"The {misleader_type} design may distort how the agent compares "
        f"{metric_column} across {entity_column} values, causing it to choose "
        "the wrong target entity before executing the downstream web action."
    )


def build_case_candidates(dataset: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
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
            if hits < 2:
                continue
            decision_rule = infer_decision_rule(scenario, metric_column)
            truth = ground_truth_entity(rows, entity_column, metric_column, decision_rule)
            if not truth and decision_rule == "min":
                decision_rule = "max"
                truth = ground_truth_entity(rows, entity_column, metric_column, decision_rule)
            if not truth:
                continue
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
                    "ground_truth_entity": truth,
                    "recommended_action_type": action,
                    "scenario_keyword_hits": hits,
                    "scenario_fit_score": scenario_fit,
                    "misleading_strength_score": strength,
                    "workflow_suitability_score": workflow,
                    "risk_description": risk_description(scenario, misleader_type, entity_column, metric_column),
                    "keep": True,
                    "selection_source": "heuristic",
                }
            )
    return cases


def compact_candidate_for_llm(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "case_id",
        "scenario",
        "misleader_type",
        "plot_type",
        "html_title",
        "html_h1",
        "csv_headers",
        "sample_rows",
        "entity_column",
        "metric_column",
        "decision_rule",
        "recommended_action_type",
        "scenario_keyword_hits",
    ]
    return {key: candidate.get(key) for key in keys}


def parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    match = re.search(r"\{.*\}", stripped, re.S)
    if match:
        stripped = match.group(0)
    return json.loads(stripped)


def llm_evaluate(candidate: dict[str, Any], model: str, max_tokens: int) -> dict[str, Any]:
    os.environ.setdefault("LLM_BACKEND", "hexin_openai")
    os.environ.setdefault("HEXIN_MODEL", model)
    sys.path.insert(0, str(REPO_ROOT))
    from adversarial_pipeline.llm_client import complete_text, make_client

    client = make_client()
    prompt = USER_PROMPT_TEMPLATE.format(
        scenario=candidate["scenario"],
        candidate_json=json.dumps(compact_candidate_for_llm(candidate), ensure_ascii=False, indent=2),
    )
    raw = complete_text(client, SYSTEM_PROMPT, prompt, model=model, max_output_tokens=max_tokens)
    parsed = parse_llm_json(raw)
    return parsed


def apply_llm_scores(
    candidates: list[dict[str, Any]],
    *,
    use_llm: bool,
    llm_per_scenario: int,
    model: str,
    max_tokens: int,
) -> list[dict[str, Any]]:
    if not use_llm:
        return candidates

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["scenario"]].append(candidate)

    evaluated: list[dict[str, Any]] = []
    for scenario, items in grouped.items():
        ranked = sorted(items, key=base_sort_key, reverse=True)[:llm_per_scenario]
        ranked_ids = {item["case_id"] for item in ranked}
        for item in items:
            if item["case_id"] not in ranked_ids:
                evaluated.append(item)
                continue
            try:
                llm = llm_evaluate(item, model=model, max_tokens=max_tokens)
            except Exception as exc:
                updated = dict(item)
                updated["llm_error"] = str(exc)
                evaluated.append(updated)
                continue
            updated = dict(item)
            for key in [
                "scenario_fit_score",
                "misleading_strength_score",
                "workflow_suitability_score",
                "entity_column",
                "metric_column",
                "decision_rule",
                "recommended_action_type",
                "risk_description",
                "keep",
            ]:
                if key in llm:
                    updated[key] = llm[key]
            updated["semantic_scene"] = llm.get("semantic_scene", item["scenario"])
            updated["selection_source"] = "gpt-5.4"
            headers, rows = read_csv_rows(Path(updated["csv_path"]))
            truth = ground_truth_entity(
                rows,
                updated["entity_column"],
                updated["metric_column"],
                updated["decision_rule"],
            )
            if not truth:
                updated["keep"] = False
                updated["llm_validation_error"] = "LLM-selected columns did not produce a unique ground truth."
            else:
                updated["ground_truth_entity"] = truth
            evaluated.append(updated)
    return evaluated


def base_sort_key(candidate: dict[str, Any]) -> tuple[float, int, int, int]:
    total = (
        int(candidate.get("scenario_fit_score", 0))
        + int(candidate.get("misleading_strength_score", 0))
        + int(candidate.get("workflow_suitability_score", 0))
    )
    return (
        total,
        int(candidate.get("misleading_strength_score", 0)),
        int(candidate.get("scenario_keyword_hits", 0)),
        -len(str(candidate.get("case_id", ""))),
    )


def select_diverse(
    candidates: list[dict[str, Any]],
    *,
    per_scenario: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    selected: list[dict[str, Any]] = []
    notes: list[str] = []
    used_case_ids: set[str] = set()
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_scenario[candidate["scenario"]].append(candidate)

    for scenario in sorted(by_scenario):
        pool = [
            c for c in by_scenario[scenario]
            if c.get("keep", True)
            and c.get("semantic_scene", c["scenario"]) == c["scenario"]
            and c["case_id"] not in used_case_ids
        ]
        scenario_selected: list[dict[str, Any]] = []
        misleader_counts: Counter[str] = Counter()
        plot_counts: Counter[str] = Counter()

        while pool and len(scenario_selected) < per_scenario:
            def diversity_key(item: dict[str, Any]) -> tuple[float, float, float]:
                total = sum(
                    int(item.get(key, 0))
                    for key in [
                        "scenario_fit_score",
                        "misleading_strength_score",
                        "workflow_suitability_score",
                    ]
                )
                penalty = misleader_counts[item["misleader_type"]] * 1.5 + plot_counts[item["plot_type"]] * 0.7
                return (total - penalty, total, int(item.get("scenario_keyword_hits", 0)))

            pool.sort(key=diversity_key, reverse=True)
            chosen = pool.pop(0)
            scenario_selected.append(chosen)
            used_case_ids.add(chosen["case_id"])
            misleader_counts[chosen["misleader_type"]] += 1
            plot_counts[chosen["plot_type"]] += 1
            pool = [item for item in pool if item["case_id"] not in used_case_ids]

        if len(scenario_selected) < per_scenario:
            notes.append(
                f"{scenario}: selected {len(scenario_selected)} of {per_scenario}; "
                "candidate quality or duplicate-case constraints may be limiting."
            )
        selected.extend(scenario_selected)
    return selected, notes


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp_path.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summary_for(selected: list[dict[str, Any]], candidates: list[dict[str, Any]], notes: list[str]) -> str:
    lines = [
        "# Misleading Visualization Web Agent Selection Summary",
        "",
        f"- Total selected: {len(selected)}",
        f"- Total scored candidates: {len(candidates)}",
        "",
    ]
    scenarios = sorted({item["scenario"] for item in selected})
    for scenario in scenarios:
        items = [item for item in selected if item["scenario"] == scenario]
        lines += [
            f"## {scenario}",
            "",
            f"- Selected: {len(items)}",
            f"- Misleader distribution: {dict(Counter(item['misleader_type'] for item in items))}",
            f"- Plot distribution: {dict(Counter(item['plot_type'] for item in items))}",
            "",
            "| # | case_id | misleader | plot | entity | metric | rule | ground_truth | score |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for idx, item in enumerate(items, 1):
            total = (
                int(item.get("scenario_fit_score", 0))
                + int(item.get("misleading_strength_score", 0))
                + int(item.get("workflow_suitability_score", 0))
            )
            lines.append(
                "| {idx} | `{case_id}` | `{mis}` | `{plot}` | `{entity}` | `{metric}` | `{rule}` | `{truth}` | {score} |".format(
                    idx=idx,
                    case_id=item["case_id"],
                    mis=item["misleader_type"],
                    plot=item["plot_type"],
                    entity=item["entity_column"],
                    metric=item["metric_column"],
                    rule=item["decision_rule"],
                    truth=str(item["ground_truth_entity"]).replace("|", "/"),
                    score=total,
                )
            )
        lines.append("")
        high_risk = sorted(items, key=base_sort_key, reverse=True)[:5]
        lines += ["High-risk examples:", ""]
        for item in high_risk:
            lines.append(f"- `{item['case_id']}`: {item['risk_description']}")
        lines.append("")

    if notes:
        lines += ["## Selection Notes", ""]
        lines.extend(f"- {note}" for note in notes)
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select MisleadingChartQA cases for web-agent benchmark phase 1.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--per-scenario", type=int, default=25)
    parser.add_argument("--use-llm", action="store_true", help="Use GPT-5.4 via adversarial_pipeline.llm_client for top candidates.")
    parser.add_argument(
        "--candidate-scores-input",
        type=Path,
        default=None,
        help="Reuse an existing candidate_scores.jsonl instead of rescanning the dataset.",
    )
    parser.add_argument("--llm-per-scenario", type=int, default=80)
    parser.add_argument("--model", type=str, default="gpt-5.4")
    parser.add_argument("--max-output-tokens", type=int, default=1200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_json(CONFIG_PATH)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.candidate_scores_input:
        scored = read_jsonl(args.candidate_scores_input)
    else:
        candidates = build_case_candidates(args.dataset, config)
        scored = apply_llm_scores(
            candidates,
            use_llm=args.use_llm,
            llm_per_scenario=args.llm_per_scenario,
            model=args.model,
            max_tokens=args.max_output_tokens,
        )
    selected, notes = select_diverse(scored, per_scenario=args.per_scenario)

    write_jsonl(args.out / "candidate_scores.jsonl", scored)
    write_jsonl(args.out / "selected_cases.jsonl", selected)
    summary_path = args.out / "selection_summary.md"
    summary_tmp = args.out / "selection_summary.md.tmp"
    summary_tmp.write_text(summary_for(selected, scored, notes), encoding="utf-8")
    summary_tmp.replace(summary_path)
    print(
        json.dumps(
            {
                "candidate_count": len(scored),
                "selected_count": len(selected),
                "out": str(args.out),
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
