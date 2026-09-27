"""Offline orchestration regressions; no synthetic b001 verdicts are fabricated."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("completion_v2_test_demo", HERE / "offline_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)
workflow = demo.workflow


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("No network is permitted in offline tests")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.mark.parametrize("task,count", [("b001", 1), ("b002", 2), ("pub013", 1)])
def test_real_initial_set_is_preserved_without_new_verdict(task, count):
    inputs = workflow.load_case(task)
    source = next(p for p in inputs["source_sha256"] if "generation" in p)
    generated = workflow.read(source)["generated"]
    assert len(inputs["base_arguments"]["chains"]) == count
    assert inputs["base_arguments"]["rules"] == generated["rules"]
    for original, imported in zip(generated["chains"], inputs["base_arguments"]["chains"]):
        assert all(imported[key] == value for key, value in original.items())
    assert inputs["v2_model_results"] == "not_run"
    proposal_source = next(p for p in inputs["source_sha256"] if "proposal" in p)
    assert inputs["decision_reference"]["proposed_option"] == workflow.read(proposal_source)["proposal"]["action"]["option"]
    context = workflow.build_context("questions", inputs)
    assert context["state"]["current_selection"] == ""
    assert "brief_basis" not in json.dumps(context)


def test_reference_is_not_inferred_from_first_chain():
    inputs, _ = demo.fixture()
    inputs["decision_reference"]["proposed_option"] = "Route B"
    context = workflow.build_context("questions", inputs)
    assert context["decision_reference"]["proposed_option"] == "Route B"
    assert context["initial_arguments"]["chains"][0]["option_label"] == "Route A"
    del inputs["decision_reference"]
    assert "decision_reference" not in workflow.build_context("questions", inputs)


def test_verifier_omits_proposal_and_questioner_assessments():
    inputs, _ = demo.fixture()
    combined = deepcopy(inputs["base_arguments"])
    combined["question_responses"] = [{"reason": "DO_NOT_SEND"}]
    combined["chains"][0]["proposal_relation"] = {"reason": "DO_NOT_SEND"}
    context = workflow.build_context("verification", inputs, {"combined": combined})
    assert "decision_reference" not in context
    assert "DO_NOT_SEND" not in json.dumps(context)
    assert all("claim_kind" not in c for c in context["arguments"]["chains"])
    assert context["arguments"]["chains"][0]["claim"] == combined["chains"][0]["claim"]


def test_prepare_only_zeros_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "new_output", lambda path: (Path(path).mkdir(), Path(path))[1])
    output = tmp_path / "prepared"
    summary = workflow.prepare(output)
    assert summary["status"] == "prepared_not_sent" and summary["model_requests"] == 0
    assert all(summary["source_preservation"].values())
    for task in workflow.CASE_IDS:
        state = workflow.read(output / task / "unverified_rule_state.json")
        assert not state["verification_performed"]
        assert all(r["status"] == "pending" for r in state["rules"])
    with pytest.raises(FileExistsError):
        workflow.prepare(output)


def test_offline_fixture_replays_all_stages_with_claims_intact(tmp_path):
    inputs, responses = demo.fixture()
    result = workflow.replay_fixture(inputs, responses, tmp_path / "mock")
    assert result["status"] == "mock_completed", result
    assert result["model_requests"] == 0 and result["fixture_stages_consumed"] == 3
    assert result["state_reload_identical"]
    state = workflow.read(tmp_path / "mock/rule_state.json")
    assert state["evidence_mode"] == "offline_fixture"
    assert [c["claim"] for c in state["chains"]] == [c["claim"] for c in inputs["base_arguments"]["chains"]]
    assert all(r["status"] == "pending" for r in state["rules"])


def test_zero_questions_skips_supplement_fixture(tmp_path):
    inputs, responses = demo.fixture()
    responses["questions"] = {"questions": [], "summary": "Synthetic no further question fixture."}
    del responses["supplement"]
    result = workflow.replay_fixture(inputs, responses, tmp_path / "empty")
    assert result["status"] == "mock_completed", result
    assert result["fixture_stages_consumed"] == 2


def test_old_verification_fails_without_losing_raw_fixture(tmp_path):
    inputs, responses = demo.fixture()
    responses["verification"] = {"checks": [], "summary": "Legacy deliberately invalid fixture."}
    result = workflow.replay_fixture(inputs, responses, tmp_path / "failure")
    assert result["status"] == "failed_offline_fixture"
    assert result["failure"]["stage"] == "verification"
    assert workflow.read(tmp_path / "failure/verification/raw_fixture_response.json") == responses["verification"]
    assert not (tmp_path / "failure/rule_state.json").exists()


def test_relation_needs_actual_target_but_is_not_inferred_from_option():
    inputs, _ = demo.fixture()
    base = inputs["base_arguments"]
    workflow.validate_relations(base, inputs["task"], inputs["decision_reference"])
    assert "proposal_relation" not in base["chains"][1]
    base["chains"][1]["proposal_relation"] = {"target_option": "Route A", "stance": "alternative", "reason": "A different candidate; not automatically a refutation."}
    workflow.validate_relations(base, inputs["task"], inputs["decision_reference"])
    with pytest.raises(workflow.core.SchemaError):
        workflow.validate_relations(base, inputs["task"], None)
    base["chains"][1]["proposal_relation"]["target_option"] = "Route B"
    with pytest.raises(workflow.core.SchemaError):
        workflow.validate_relations(base, inputs["task"], inputs["decision_reference"])


def test_prompts_generic_and_no_blanket_binary_or_precedence_rule():
    text = "\n".join(workflow.prompts.PROMPTS.values()) + workflow.prompts.GENERATOR
    for token in ("b001", "b002", "pub013", "Apple", "Illinois", "Firefox"):
        assert token not in text
    assert "not a forced yes/no" in text
    assert "Neither printed labels nor customary geometry" in text
    assert "B_applicability" in workflow.prompts.VERIFY
    assert "conditional_inference" in workflow.prompts.VERIFY
    assert workflow.read(HERE / "config.json")["max_real_request_attempts"] == 0
