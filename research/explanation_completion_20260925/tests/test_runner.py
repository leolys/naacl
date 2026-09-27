"""Offline-only orchestration and budget checks; no simulated result is research evidence."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("completion_runner_test", HERE / "runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Offline test attempted network")
    monkeypatch.setattr(runner.wire.requests.sessions.Session, "request", deny)

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    for name in ("config.json", "manifest.json"):
        runner.wire.dump(tmp_path / name, runner.wire.read(HERE / name))
    monkeypatch.setattr(runner, "HERE", tmp_path)
    monkeypatch.setattr(runner, "freeze_sources", lambda output: runner.wire.dump(
        output / "runtime.json", {"source_sha256": {}, "offline_test_fixture": True}))
    return tmp_path

def test_complete_initial_sets_and_original_text_are_preserved():
    for task, count in (("b001", 1), ("b002", 2), ("env001", 2), ("health001", 2), ("pub013", 1)):
        inputs = runner.load_case(task)
        raw, base = inputs["initial_generated_raw"], inputs["base_arguments"]
        assert len(base["chains"]) == count
        assert base["rules"] == raw["rules"]
        for original, imported in zip(raw["chains"], base["chains"]):
            assert all(imported[key] == value for key, value in original.items())
        context = runner.build_context("questions", inputs, {})
        assert len(context["initial_arguments"]["chains"]) == count
        assert "source_sha256" not in context and "base_proposal" not in context
        runner.public_inputs.assert_public(context)

def test_prepare_never_constructs_client(isolated):
    def deny_client(*args):
        raise AssertionError("prepare constructed a client")
    summary = runner.run(isolated / "prepared", api_factory=deny_client)
    assert summary["request_attempts"] == 0
    assert summary["status"] == "prepared_not_sent"
    assert all(summary["source_preservation"].values())
    with pytest.raises(ValueError):
        runner.run(isolated / "prepared", api_factory=deny_client)

def test_verifier_projection_omits_questioner_assessments():
    inputs = runner.load_case("b002")
    combined = copy.deepcopy(inputs["base_arguments"])
    combined["question_responses"] = [{"outcome": "already_covered", "reason": "DO NOT SEND"}]
    context = runner.build_context("verification", inputs, {"combined": combined})
    assert "DO NOT SEND" not in json.dumps(context)
    assert len(context["arguments"]["chains"]) == 2

def test_frozen_config_rejects_budget_model_and_sample_drift():
    config, manifest = runner.wire.read(HERE / "config.json"), runner.wire.read(HERE / "manifest.json")
    runner.validate_config(config, manifest)
    for key, value in (("max_request_attempts", 13), ("max_estimated_usd", 3), ("model", "other"),
                       ("max_refinements", 3), ("quality_retries", True)):
        changed = {**config, key: value}
        with pytest.raises(ValueError):
            runner.validate_config(changed, manifest)
    with pytest.raises(ValueError):
        runner.validate_config(config, {**manifest, "cases": manifest["cases"][::-1]})

def test_attempt_and_estimated_budget_boundaries(tmp_path):
    config = runner.wire.read(HERE / "config.json")
    budget = runner.EstimatedBudget(tmp_path / "attempts.json", config)
    for i in range(12):
        budget.current_folder = tmp_path / ("request_%02d" % i)
        budget.charge({"task_slug": "mock", "phase": "generation", "round": "test", "attempt": 1})
        # Synthetic zero-usage accounting, not a provider response.
        budget.value["events"][-1].update(accounting_status="usage_reconciled", charged_estimated_usd=0)
        budget.save()
    with pytest.raises(runner.wire.ServiceStop, match="request_budget"):
        budget.charge({"task_slug": "mock", "phase": "generation", "round": "test", "attempt": 1})
    money_budget = runner.EstimatedBudget(tmp_path / "money.json", config)
    for i in range(8):
        money_budget.current_folder = tmp_path / ("unknown_%02d" % i)
        money_budget.charge({"task_slug": "mock", "phase": "generation", "round": "test", "attempt": 1})
    assert money_budget.value["estimated_ledger_usd"] == 2
    with pytest.raises(runner.wire.ServiceStop, match="estimated_usd"):
        money_budget.charge({"task_slug": "mock", "phase": "generation", "round": "test", "attempt": 1})

def test_mock_pipeline_separate_from_live_evidence(isolated, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "offline-placeholder-not-a-credential")
    class MockAPI:
        def __init__(self, config, budget):
            self.budget = budget
        def call(self, folder, task_id, phase, prompt, context, images):
            self.budget.current_folder = folder
            self.budget.charge({"task_slug": task_id, "phase": phase, "round": "synthetic", "attempt": 1})
            event = self.budget.value["events"][-1]
            event.update(accounting_status="usage_reconciled", charged_estimated_usd=0, offline_fixture=True)
            self.budget.save()
            if "arguments" in context:
                return {"checks": [{"target_id": c["chain_id"], **{k: {
                    "status": "undetermined", "evidence": [], "reason": "Synthetic interface fixture only."}
                    for k in ("O", "B", "implication")}} for c in context["arguments"]["chains"]],
                    "summary": "MOCK: no semantic or coverage claim."}
            if "counterquestions" in context:
                return {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": []}
            return {"questions": [], "summary": "MOCK: no semantic or coverage claim."}
    result = runner.run(isolated / "mock_only", live=True, api_factory=MockAPI)
    assert result["status"] == "mock_completed", result
    assert result["mode"] == "mock" and result["evidence_mode"] == "offline_fixture"
    assert result["request_attempts"] == 6  # Empty question sets need no supplement call.
    assert result["browser_operations"] == 0
    assert all(case["status"] == "mock_completed" for case in result["cases"])
    for task in runner.FIXED_IDS:
        case = runner.wire.read(isolated / "mock_only/cases" / task / "result.json")
        assert case["evidence_mode"] == "offline_fixture"
        state = runner.wire.read(isolated / "mock_only/cases" / task / "rule_state.json")
        assert state is not None
        assert runner.wire.read(isolated / "mock_only/cases" / task / "state_reload_check.json")["identical"]
