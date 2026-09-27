import json

import pytest

import analyze_usage as accounting


SOL_RATE = {"modelID": "gpt-5.6-sol", "input_usd_per_m": 4,
            "output_usd_per_m": 20, "cache_read_usd_per_m": 0.4}


def sample_usage():
    return {
        "prompt_tokens": 11553, "input_tokens": 11553,
        "completion_tokens": 110, "output_tokens": 110, "total_tokens": 11663,
        "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 11550},
        "completion_tokens_details": {"reasoning_tokens": 0},
        "billing_usage": {"openai_usage": {
            "prompt_tokens": 0, "completion_tokens": 0,
            "input_tokens": 11553, "output_tokens": 110, "total_tokens": 11663,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 11550},
            "output_tokens_details": {"reasoning_tokens": 28},
        }},
    }


def test_duplicate_aliases_and_reasoning_are_not_double_counted():
    normalized = accounting.normalize_usage(sample_usage())
    assert normalized["values"]["input_tokens"] == 11553
    assert normalized["values"]["output_tokens"] == 110
    assert normalized["values"]["cache_write_tokens"] == 11550
    assert normalized["values"]["reasoning_tokens"] == 28
    assert {c["metric"] for c in normalized["conflicts"]} == {
        "input_tokens", "output_tokens", "reasoning_tokens"}
    costs = accounting.estimate_cost(normalized, SOL_RATE)
    assert costs[accounting.SCENARIOS[0]] == pytest.approx(0.048412)
    assert costs[accounting.SCENARIOS[1]] == pytest.approx(0.059962)
    assert costs["actual_charge_usd"] is None


def test_top_zero_nested_nonzero_is_preserved_as_conflict():
    usage = sample_usage()
    usage["prompt_tokens"] = usage["input_tokens"] = 0
    normalized = accounting.normalize_usage(usage)
    assert normalized["values"]["input_tokens"] == 11553
    conflict = next(c for c in normalized["conflicts"] if c["metric"] == "input_tokens")
    assert conflict["resolution"] == "unique_nonzero_over_zero_alias"
    assert any(o["field"] == "usage.prompt_tokens" and o["value"] == 0 for o in conflict["observed"])


def test_distinct_nonzero_conflict_withholds_price():
    usage = sample_usage()
    usage["prompt_tokens"] = 11554
    normalized = accounting.normalize_usage(usage)
    assert normalized["values"]["input_tokens"] is None
    assert accounting.estimate_cost(normalized, SOL_RATE)[accounting.SCENARIOS[0]] is None


def test_missing_usage_is_unknown_not_free():
    normalized = accounting.normalize_usage({})
    assert not normalized["core_usage_present"]
    assert accounting.estimate_cost(normalized, SOL_RATE)[accounting.SCENARIOS[0]] is None


def test_missing_details_have_explicit_scenario_assumptions():
    normalized = accounting.normalize_usage({"prompt_tokens": 100, "completion_tokens": 20})
    assert len(normalized["assumptions"]) == 2
    cost = accounting.estimate_cost(normalized, SOL_RATE)
    assert cost[accounting.SCENARIOS[0]] == pytest.approx(0.0008)
    assert cost[accounting.SCENARIOS[1]] == cost[accounting.SCENARIOS[0]]


def test_cache_read_subtracts_from_full_price_and_write_adds_only_premium():
    normalized = accounting.normalize_usage({"input_tokens": 1000, "output_tokens": 100,
        "input_tokens_details": {"cached_tokens": 300, "cache_write_tokens": 600}})
    cost = accounting.estimate_cost(normalized, SOL_RATE)
    assert cost[accounting.SCENARIOS[0]] == pytest.approx(0.00492)
    assert cost[accounting.SCENARIOS[1]] == pytest.approx(0.00552)


@pytest.mark.parametrize("usage", [
    {"input_tokens": 100, "output_tokens": 10, "total_tokens": 999},
    {"input_tokens": -1, "output_tokens": 10},
    {"input_tokens": True, "output_tokens": 10},
    {"input_tokens": 272001, "output_tokens": 10},
    {"input_tokens": 100, "output_tokens": 10,
     "input_tokens_details": {"cached_tokens": 70, "cache_write_tokens": 80}},
])
def test_invalid_or_out_of_scope_usage_withholds_prices(usage):
    assert accounting.estimate_cost(accounting.normalize_usage(usage), SOL_RATE)[accounting.SCENARIOS[0]] is None


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_panel(root, completed=True):
    rates = [dict(SOL_RATE, modelID=model) for model in accounting.MODELS]
    put(root / "provider_rates.json", {"rates": rates, "registry_generated_at": "test-fixture"})
    model = accounting.MODELS[0]
    events = []
    for task in accounting.TASKS:
        statuses = {phase: "completed" for phase in accounting.PHASES}
        for phase in accounting.PHASES:
            if not completed and task == "pub013" and phase == "translation":
                statuses[phase] = "not_started"
                continue
            put(root / "runs" / model / "tasks" / task / phase / "round_001" / "attempt_01.json", {
                "attempt": 1, "phase": phase, "requested_model": model, "response_model": model,
                "http_status": 200, "finish_reason": "stop", "elapsed_seconds": 1.5,
                "usage": sample_usage(),
            })
            events.append({"task_slug": task, "phase": phase, "round": "round_001", "attempt": 1})
        put(root / "runs" / model / "tasks" / task / "record.json", {"status": statuses})
    put(root / "runs" / model / "budget.json", {"request_attempts": len(events), "events": events})
    return model


def test_complete_two_case_model_can_extrapolate_without_other_models(tmp_path):
    model = make_panel(tmp_path)
    summary = accounting.build_summary(tmp_path)
    m = summary["models"][model]
    assert m["reconciliation"]["matched"]
    assert m["attempt_records_count"] == 8
    assert summary["totals"]["completed_combination_count"] == 2
    assert m["extrapolation_140"]["eligible"]
    scenario = m["extrapolation_140"]["scenarios"][accounting.SCENARIOS[0]]
    assert scenario["mean_times_140_usd"] == pytest.approx(0.048412 * 4 * 140)
    assert not m["extrapolation_140"]["execution_authorized"]
    assert m["by_task"]["b001"]["attempt_records_count"] == 4
    assert m["by_phase"]["proposal"]["attempt_records_count"] == 2
    assert not (tmp_path / "cost_summary.json").exists()


def test_one_incomplete_task_withholds_140_projection(tmp_path):
    model = make_panel(tmp_path, completed=False)
    m = accounting.build_summary(tmp_path)["models"][model]
    assert not m["extrapolation_140"]["eligible"]
    assert m["extrapolation_140"]["scenarios"] == {}


def test_budget_reservation_without_attempt_is_not_free(tmp_path):
    model = make_panel(tmp_path, completed=False)
    path = tmp_path / "runs" / model / "budget.json"
    budget, _ = accounting.read_object(path)
    budget["request_attempts"] += 1
    budget["events"].append({"task_slug": "pub013", "phase": "translation", "round": "round_001", "attempt": 1})
    put(path, budget)
    m = accounting.build_summary(tmp_path)["models"][model]
    assert not m["reconciliation"]["matched"]
    assert m["reconciliation"]["budget_minus_record_count"] == 1
    assert not m["extrapolation_140"]["eligible"]


def test_failed_attempt_missing_usage_makes_total_unknown(tmp_path):
    model = make_panel(tmp_path)
    folder = tmp_path / "runs" / model / "tasks" / "pub013"
    path = folder / "translation" / "round_001" / "attempt_01.json"
    put(path, {"attempt": 1, "phase": "translation", "http_status": 429, "error_category": "rate_limit"})
    statuses = {phase: "completed" for phase in accounting.PHASES}
    statuses["translation"] = "failed"
    put(folder / "record.json", {"status": statuses})
    result = accounting.build_summary(tmp_path)
    m = result["models"][model]
    assert m["usage_missing_count"] == 1
    assert m["failed_attempt_count"] == 1
    assert m["all_recorded_attempts_scenario_totals_usd"][accounting.SCENARIOS[0]] is None
    assert m["known_usage_scenario_subtotals_usd"][accounting.SCENARIOS[0]] == pytest.approx(7 * 0.048412)
    assert result["totals"]["failed_combination_count"] == 1
    assert not m["extrapolation_140"]["eligible"]


def test_budget_event_identity_mismatch_is_detected_even_when_counts_match(tmp_path):
    model = make_panel(tmp_path)
    path = tmp_path / "runs" / model / "budget.json"
    budget, _ = accounting.read_object(path)
    budget["events"][0]["task_slug"] = "outside_panel"
    put(path, budget)
    m = accounting.build_summary(tmp_path)["models"][model]
    assert not m["reconciliation"]["event_identity_counts_match"]
    assert not m["extrapolation_140"]["eligible"]


def test_snapshot_reader_does_not_modify_runs(tmp_path):
    make_panel(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    accounting.build_summary(tmp_path)
    after = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert before == after


def test_single_completed_task_cost_is_separate_from_withheld_projection(tmp_path):
    model = make_panel(tmp_path)
    path = tmp_path / "runs" / model / "tasks" / "b001" / "record.json"
    record, _ = accounting.read_object(path)
    record["status"]["verification"] = "invalid"
    put(path, record)
    m = accounting.build_summary(tmp_path)["models"][model]
    assert list(m["completed_task_scenario_costs_usd"]) == ["pub013"]
    assert m["completed_task_scenario_costs_usd"]["pub013"][accounting.SCENARIOS[0]] == pytest.approx(4 * 0.048412)
    assert not m["extrapolation_140"]["eligible"]
    assert m["extrapolation_140"]["scenarios"] == {}
