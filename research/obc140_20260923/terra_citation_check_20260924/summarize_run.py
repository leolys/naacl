"""Offline accounting and input comparability for the fixed Terra check."""
from collections import Counter
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "apiyi_selection_20260924"))
import analyze_usage as accounting
import run_validation as validation
from panel_core import read, dump, PHASES, validate_stage


def summarize():
    model = "gpt-5.6-terra"
    rates = read(HERE.parent / "apiyi_selection_20260924" / "provider_rates.json")
    rate = next(rate for rate in rates["rates"] if rate["modelID"] == model)
    rows, cases, comparisons = [], {}, []
    for task in validation.TASKS:
        folder = validation.OUT / "tasks" / task
        record = read(folder / "record.json")
        case_rows = []
        for phase in PHASES:
            for path in sorted((folder / phase).glob("round_*/attempt_*.json")):
                case_rows.append(accounting.attempt_record(path, HERE, model, task, phase, rate))
            old_path = validation.OLD / model / "tasks" / task / phase / "round_001" / "request.json"
            new_path = folder / phase / "round_001" / "request.json"
            if old_path.exists() and new_path.exists():
                old, new = read(old_path), read(new_path)
                old_blocks, new_blocks = old["messages"][1]["content"], new["messages"][1]["content"]
                comparisons.append({"task": task, "phase": phase,
                    "same_system_prompt": old["messages"][0] == new["messages"][0],
                    "same_model_and_decode": all(old.get(k) == new.get(k)
                        for k in ("model", "temperature", "max_tokens", "reasoning_effort")),
                    "same_image_blocks": [x for x in old_blocks if x["type"] == "image_url"] ==
                                         [x for x in new_blocks if x["type"] == "image_url"],
                    "entire_request_equal": old == new,
                    "note": "Later stages may differ because each run generates its own content; translation also sees typed citation additions."})
        rows.extend(case_rows)
        cases[task] = {"status": record["status"], "costs": accounting.summarize_attempts(case_rows),
                       "chains": len((record.get("generated") or {}).get("chains", [])),
                       "citation_moves": len(record.get("citation_adapter", {}).get("moves", [])),
                       "translation_warnings": record.get("translation_warnings", [])}
        raw_path = folder / "verification" / "round_001" / "parsed.json"
        if raw_path.is_file():
            try:
                validate_stage("verification", read(raw_path), record, validation.configuration())
                cases[task]["old_schema_counterfactual"] = {"status": "accepted_by_schema"}
            except (ValueError, TypeError, KeyError) as error:
                cases[task]["old_schema_counterfactual"] = {"status": "rejected_by_schema", "reason": str(error)}
    budget = read(validation.OUT / "budget.json", {"request_attempts": 0, "events": []})
    event_ids = Counter((x["task_slug"], x["phase"], x["round"], x["attempt"]) for x in budget["events"])
    row_ids = Counter((x["task"], x["phase"], x["round"], x["attempt"]) for x in rows)
    reconciled = event_ids == row_ids and len(rows) == budget["request_attempts"] <= 8
    if not reconciled:
        raise ValueError("budget and archived attempts do not reconcile")
    result = {"model": model, "rate_source": rates["registry_source"],
              "actual_charge_usd": None, "batch140_authorized": False,
              "cost_note": "Unconfirmed public-rate scenarios, not invoice or established upper/lower bounds.",
              "totals": accounting.summarize_attempts(rows), "cases": cases, "attempts": rows,
              "budget_reconciled": reconciled, "input_comparisons": comparisons}
    complete = all(all(case["status"][phase] == "completed" for phase in PHASES)
                   and case["costs"]["all_recorded_attempts_estimated"] for case in cases.values())
    result["arithmetic_140_projection"] = {
        "eligible": complete and len(rows) == 8,
        "scope": "Two known development cases only; no uncertainty bound, unseen quality or actual billing guarantee.",
        "scenarios_usd": {scenario: round(sum(case["costs"]["all_recorded_attempts_scenario_totals_usd"][scenario]
            for case in cases.values()) * 70, 6) for scenario in accounting.SCENARIOS} if complete and len(rows) == 8 else {}}
    if complete and len(rows) == 8:
        tokens = result["totals"]["known_usage_totals"]
        cold_base = (tokens["input_tokens"] * rate["input_usd_per_m"]
                     + tokens["output_tokens"] * rate["output_usd_per_m"]) / 1_000_000
        cold_write = cold_base + (tokens["cache_write_tokens"] + tokens["cached_tokens"]) * (
            0.25 * rate["input_usd_per_m"] / 1_000_000)
        result["cache_sensitivity"] = {
            "why": "These known tasks received cache reads; unseen tasks may not obtain the same hits.",
            "assumptions": "Counterfactual: all returned cached tokens charged at normal input; scenario2 also treats them as new writes at unconfirmed 1.25x. Not a bound or invoice.",
            "two_cases_usd": {accounting.SCENARIOS[0]: round(cold_base, 6),
                              accounting.SCENARIOS[1]: round(cold_write, 6)},
            "arithmetic_140_usd": {accounting.SCENARIOS[0]: round(cold_base * 70, 6),
                                   accounting.SCENARIOS[1]: round(cold_write * 70, 6)}}
    dump(HERE / "cost_and_comparability.json", result)
    print({"requests": len(rows), "totals": result["totals"], "budget_reconciled": reconciled})


if __name__ == "__main__":
    summarize()
