"""Offline accounting for the fixed APIYI two-task, three-model development panel.

Reads evidence only. The CLI writes cost_summary.json beside this script and never
imports the runner, accesses credentials, or sends requests.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.4-mini")
TASKS = ("b001", "pub013")
PHASES = ("proposal", "generation", "verification", "translation")
MAX_ATTEMPTS = 24
METRICS = ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")
SCENARIOS = ("regular_no_write_premium_usd", "returned_write_plus_25pct_usd")
FAILED_PHASE_STATES = {"failed", "invalid", "blocked"}


def read_object(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            return {}, "expected_json_object"
        return value, None
    except (OSError, ValueError) as exc:
        return {}, type(exc).__name__


def at(value, keys):
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def token_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def normalize_usage(usage):
    """Collapse aliases; preserve every disagreement without adding aliases together.

    A unique nonzero value wins over zero placeholders. Different positive values
    are unresolved: the canonical value is None, so no monetary estimate is made.
    """
    layers = [("usage", usage)]
    nested = at(usage, ("billing_usage", "openai_usage"))
    if isinstance(nested, dict):
        layers.append(("usage.billing_usage.openai_usage", nested))
    aliases = {
        "input_tokens": [("input_tokens",), ("prompt_tokens",)],
        "output_tokens": [("output_tokens",), ("completion_tokens",)],
        "total_tokens": [("total_tokens",)],
        "cached_tokens": [("input_tokens_details", "cached_tokens"),
                          ("prompt_tokens_details", "cached_tokens")],
        "cache_write_tokens": [("input_tokens_details", "cache_write_tokens"),
                               ("prompt_tokens_details", "cache_write_tokens")],
        "reasoning_tokens": [("output_tokens_details", "reasoning_tokens"),
                             ("completion_tokens_details", "reasoning_tokens")],
    }
    result = {"values": {}, "observations": {}, "conflicts": [],
              "invalid_fields": [], "assumptions": [], "errors": []}
    for metric, paths in aliases.items():
        observed = []
        for prefix, layer in layers:
            for keys in paths:
                value = at(layer, keys)
                if value is None:
                    continue
                field = prefix + "." + ".".join(keys)
                if not token_int(value):
                    result["invalid_fields"].append({"field": field, "value": value})
                else:
                    observed.append({"field": field, "value": value})
        distinct = {item["value"] for item in observed}
        positive = {value for value in distinct if value > 0}
        chosen = next(iter(positive)) if len(positive) == 1 else (
            0 if distinct == {0} else None)
        result["observations"][metric] = observed
        result["values"][metric] = chosen
        if len(distinct) > 1:
            result["conflicts"].append({
                "metric": metric, "observed": observed, "selected_value": chosen,
                "resolution": "unique_nonzero_over_zero_alias" if chosen is not None
                else "unresolved_distinct_positive_values",
            })
        if len(positive) > 1 and metric != "reasoning_tokens":
            result["errors"].append("unresolved_alias_conflict:" + metric)
    values = result["values"]
    for metric in ("input_tokens", "output_tokens"):
        if values[metric] is None:
            result["errors"].append("missing_or_ambiguous:" + metric)
    for metric in ("cached_tokens", "cache_write_tokens"):
        if not result["observations"][metric] and values[metric] is None:
            values[metric] = 0
            result["assumptions"].append("absent_" + metric + "_treated_as_zero_for_scenario")
    if result["invalid_fields"]:
        result["errors"].append("invalid_token_field")
    if all(values[key] is not None for key in ("input_tokens", "output_tokens")):
        computed_total = values["input_tokens"] + values["output_tokens"]
        if values["total_tokens"] is not None and values["total_tokens"] != computed_total:
            result["errors"].append("reported_total_disagrees_with_input_plus_output")
        if all(values[key] is not None for key in ("cached_tokens", "cache_write_tokens")):
            if values["cached_tokens"] + values["cache_write_tokens"] > values["input_tokens"]:
                result["errors"].append("read_and_write_exceed_input_total")
    result["core_usage_present"] = all(result["observations"][key]
                                       for key in ("input_tokens", "output_tokens"))
    return result


def estimate_cost(normalized, rate):
    result = {key: None for key in SCENARIOS}
    result.update(actual_charge_usd=None, api_yi_write_rate_verified=False,
                  reasons_unavailable=list(normalized["errors"]))
    if not rate:
        result["reasons_unavailable"].append("missing_public_model_rate")
    values = normalized["values"]
    if values["input_tokens"] is not None and values["input_tokens"] > 272000:
        result["reasons_unavailable"].append("outside_common_short_context_scope")
    if result["reasons_unavailable"]:
        return result
    p, o, c, w = (values[key] for key in METRICS)
    if any(value is None for value in (p, o, c, w)):
        result["reasons_unavailable"].append("unresolved_billable_token_count")
        return result
    base = ((p - c) * rate["input_usd_per_m"]
            + c * rate["cache_read_usd_per_m"]
            + o * rate["output_usd_per_m"]) / 1_000_000
    result[SCENARIOS[0]] = round(base, 12)
    result[SCENARIOS[1]] = round(base + w * 0.25 * rate["input_usd_per_m"] / 1_000_000, 12)
    result["assumptions"] = normalized["assumptions"] + [
        "read_and_write_details_are_disjoint_subsets_of_input_total",
        "reasoning_already_in_output_total_not_added_again",
        "scenario_2_only_adds_25pct_for_returned_write_tokens_not_confirmed_gateway_rate",
    ]
    return result


def summarize_attempts(rows):
    estimated = [row for row in rows if row["cost"][SCENARIOS[0]] is not None]
    return {
        "attempt_records_count": len(rows),
        "usage_missing_count": sum(not row["normalized_usage"]["core_usage_present"] for row in rows),
        "cost_unavailable_count": len(rows) - len(estimated),
        "usage_conflict_attempt_count": sum(bool(row["normalized_usage"]["conflicts"]) for row in rows),
        "http_success_count": sum(row["transport_outcome"] == "http_success" for row in rows),
        "failed_attempt_count": sum(row["transport_outcome"] == "failed" for row in rows),
        "unknown_outcome_count": sum(row["transport_outcome"] == "unknown" for row in rows),
        "elapsed_seconds_recorded_sum": round(sum(row["elapsed_seconds"] for row in rows
                                                   if isinstance(row["elapsed_seconds"], (int, float))), 6),
        "known_usage_totals": {
            metric: sum(row["normalized_usage"]["values"][metric] or 0 for row in rows)
            for metric in METRICS
        },
        "all_recorded_attempts_estimated": len(estimated) == len(rows),
        "known_usage_scenario_subtotals_usd": {
            key: round(sum(row["cost"][key] for row in estimated), 12) for key in SCENARIOS
        },
        "all_recorded_attempts_scenario_totals_usd": {
            key: round(sum(row["cost"][key] for row in estimated), 12)
            if len(estimated) == len(rows) else None for key in SCENARIOS
        },
        "actual_charge_usd": None,
    }


def attempt_record(path, root, model, task, phase, rate):
    meta, read_error = read_object(path)
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    normalized = normalize_usage(usage)
    cost = estimate_cost(normalized, rate)
    http_status = meta.get("http_status")
    outcome = "unknown"
    if isinstance(http_status, int) and http_status >= 400:
        outcome = "failed"
    elif isinstance(http_status, int) and 200 <= http_status < 300:
        outcome = "http_success"
    elif meta.get("error_category") and "unknown" not in meta["error_category"]:
        outcome = "failed"
    issues = []
    for field in ("requested_model", "response_model"):
        if meta.get(field) and meta[field] != model:
            issues.append(field + "_differs_from_fixed_model")
    if meta.get("phase") and meta["phase"] != phase:
        issues.append("metadata_phase_differs_from_directory")
    if read_error:
        issues.append("attempt_read_error:" + read_error)
    return {
        "file": path.relative_to(root).as_posix(), "model": model,
        "task": task, "phase": phase, "round": path.parent.name,
        "attempt": meta.get("attempt"), "requested_model": meta.get("requested_model"),
        "response_model": meta.get("response_model"), "http_status": http_status,
        "finish_reason": meta.get("finish_reason"), "elapsed_seconds": meta.get("elapsed_seconds"),
        "error_category": meta.get("error_category"), "exception_type": meta.get("exception_type"),
        "transport_outcome": outcome, "issues": issues,
        "normalized_usage": normalized, "cost": cost,
    }


def extrapolation(tasks, reconciliation, rows):
    reasons = []
    if not all(tasks[task]["pipeline_completed"] for task in TASKS):
        reasons.append("both_development_tasks_must_complete_all_four_phases")
    if not reconciliation["matched"]:
        reasons.append("attempt_records_and_budget_not_reconciled")
    if len(rows) != 8 or any(tasks[t]["by_phase"][p]["attempt_records_count"] != 1
                             for t in TASKS for p in PHASES):
        reasons.append("fixed_one_attempt_per_task_phase_not_satisfied")
    if any(row["cost"][SCENARIOS[0]] is None for row in rows):
        reasons.append("one_or_more_attempt_costs_unavailable")
    if any(row["issues"] for row in rows):
        reasons.append("attempt_metadata_issues_require_review")
    result = {"eligible": not reasons, "reasons_withheld": reasons, "target_task_count": 140,
              "execution_authorized": False, "scenarios": {},
              "limitations": ["Two known development tasks do not represent the distribution of 140 tasks.",
                              "Mean/min/max times 140 are arithmetic sensitivity scenarios, not confidence bounds.",
                              "Unknown retries, actual account charges and discounts are not included.",
                              "No batch budget is confirmed; this calculation never authorizes running 140 tasks."]}
    if not reasons:
        for key in SCENARIOS:
            sample = [tasks[task]["all_recorded_attempts_scenario_totals_usd"][key] for task in TASKS]
            result["scenarios"][key] = {
                "per_task_usd": dict(zip(TASKS, sample)),
                "mean_per_task_usd": round(sum(sample) / 2, 12),
                "mean_times_140_usd": round(sum(sample) / 2 * 140, 12),
                "min_times_140_usd": round(min(sample) * 140, 12),
                "max_times_140_usd": round(max(sample) * 140, 12),
            }
    return result


def build_summary(root=HERE):
    root = Path(root)
    rate_document, rate_error = read_object(root / "provider_rates.json")
    if rate_error:
        raise ValueError("Cannot read provider_rates.json: " + rate_error)
    rates = {row["modelID"]: row for row in rate_document["rates"]}
    models, all_rows, completed, failed = {}, [], [], []
    for model in MODELS:
        model_root = root / "runs" / model
        budget, budget_error = read_object(model_root / "budget.json")
        rows, tasks = [], {}
        for task in TASKS:
            task_root = model_root / "tasks" / task
            record, record_error = read_object(task_root / "record.json")
            task_rows, phase_summaries = [], {}
            for phase in PHASES:
                phase_rows = [attempt_record(path, root, model, task, phase, rates.get(model))
                              for path in sorted((task_root / phase).glob("round_*/attempt_*.json"))]
                status = record.get("status", {}).get(phase, "not_started")
                phase_summaries[phase] = dict(summarize_attempts(phase_rows), pipeline_status=status)
                task_rows.extend(phase_rows)
            complete = all(phase_summaries[p]["pipeline_status"] == "completed"
                           and phase_summaries[p]["http_success_count"] >= 1 for p in PHASES)
            failed_phases = [p for p in PHASES if phase_summaries[p]["pipeline_status"] in FAILED_PHASE_STATES]
            tasks[task] = dict(summarize_attempts(task_rows), by_phase=phase_summaries,
                               pipeline_completed=complete, failed_phases=failed_phases,
                               record_read_error=record_error)
            if complete:
                completed.append({"model": model, "task": task})
            if failed_phases:
                failed.append({"model": model, "task": task, "phases": failed_phases})
            rows.extend(task_rows)
        declared = budget.get("request_attempts")
        expected_events = Counter((r["task"], r["phase"], r["round"], r["attempt"]) for r in rows)
        events = budget.get("events")
        events_valid = isinstance(events, list) and all(isinstance(e, dict) for e in events)
        actual_events = Counter((e.get("task_slug"), e.get("phase"), e.get("round"), e.get("attempt"))
                                for e in events) if events_valid else Counter()
        selected_files = {r["file"] for r in rows}
        outside = [p.relative_to(root).as_posix() for p in model_root.glob("tasks/*/*/round_*/attempt_*.json")
                   if p.relative_to(root).as_posix() not in selected_files]
        matched = (not budget_error and token_int(declared) and declared == len(rows)
                   and declared <= 8 and events_valid and actual_events == expected_events and not outside)
        reconciliation = {
            "budget_request_attempts": declared, "attempt_records_count": len(rows),
            "budget_read_error": budget_error, "budget_event_count": len(events) if events_valid else None,
            "event_identity_counts_match": events_valid and actual_events == expected_events,
            "budget_minus_record_count": declared - len(rows) if token_int(declared) else None,
            "outside_fixed_panel_attempt_files": outside, "model_limit": 8, "matched": matched,
            "note": "Budget reservations with no saved attempt can be in flight or interrupted; never count them as free.",
        }
        models[model] = dict(summarize_attempts(rows), by_task=tasks,
                             by_phase={p: summarize_attempts([r for r in rows if r["phase"] == p]) for p in PHASES},
                             reconciliation=reconciliation, price_source=rates.get(model),
                             completed_task_scenario_costs_usd={
                                 task: tasks[task]["all_recorded_attempts_scenario_totals_usd"]
                                 for task in TASKS if tasks[task]["pipeline_completed"]
                             },
                             attempts=rows, extrapolation_140=extrapolation(tasks, reconciliation, rows))
        all_rows.extend(rows)
    total = summarize_attempts(all_rows)
    declarations = [models[m]["reconciliation"]["budget_request_attempts"] for m in MODELS]
    total.update(budget_request_attempts_known_sum=sum(v for v in declarations if token_int(v)),
                 all_model_budgets_available=all(token_int(v) for v in declarations),
                 all_model_budgets_reconciled=all(models[m]["reconciliation"]["matched"] for m in MODELS),
                 max_attempt_records=MAX_ATTEMPTS,
                 within_fixed_attempt_limit=len(all_rows) <= MAX_ATTEMPTS
                 and all((v or 0) <= 8 for v in declarations if token_int(v)),
                 completed_model_task_combinations=completed, completed_combination_count=len(completed),
                 failed_model_task_combinations=failed, failed_combination_count=len(failed))
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_snapshot_no_requests", "fixed_models": list(MODELS),
        "fixed_tasks": list(TASKS), "fixed_phases": list(PHASES), "currency": "USD",
        "rate_source_file": "provider_rates.json", "rate_registry_date": rate_document.get("registry_generated_at"),
        "scenario_1": "Public regular input/output/cache-read rates, no extra write premium; not actual charges.",
        "scenario_2": "Scenario 1 plus returned cache_write_tokens * input rate * 0.25; unconfirmed APIYI assumption, not a bound.",
        "actual_charge_usd": None, "batch_140_authorized": False,
        "limitations": ["Files are a snapshot, not a transactionally consistent live billing view.",
                        "Missing usage and unresolved nonzero alias conflicts leave monetary coverage incomplete.",
                        "Missing cache detail fields are explicitly treated as zero only for these scenarios.",
                        "Completion states are pipeline evidence, not independent semantic-quality judgments.",
                        "Known-usage subtotals exclude unknown costs; they are not account totals or proven lower bounds."],
        "totals": total, "models": models,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE, help="Pilot directory containing rates and runs")
    args = parser.parse_args()
    summary = build_summary(args.root)
    destination = args.root / "cost_summary.json"
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination.resolve()),
                      "attempt_records": summary["totals"]["attempt_records_count"],
                      "completed_combinations": summary["totals"]["completed_combination_count"],
                      "budgets_reconciled": summary["totals"]["all_model_budgets_reconciled"]}))


if __name__ == "__main__":
    main()
