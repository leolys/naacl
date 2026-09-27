"""Offline engineering gate for the fixed six-condition counterquestion pilot."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import shutil
import uuid

import pytest


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("counterquestion_general_runner", HERE / "runner.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline gate must never issue a network request")
    monkeypatch.setattr(runner.core.requests.sessions.Session, "request", forbidden)


@pytest.fixture
def public():
    return {
        "task_alias": "task_test", "page_title": "Public task",
        "user_goal": "Choose a route.", "chart_reference": "Use this chart.",
        "primary_field_label": "Route", "option_labels": ["Route A", "Route B"],
        "companion_fields": [], "completion_label": "Submit Form",
        "policy_tables": [], "page_instructions": [],
    }


@pytest.fixture
def base():
    return {
        "rules": [{"id": "seed_rule", "text": "The printed key governs this mark.",
                   "component": "mark-to-key relation", "conditions": "This visible chart only."}],
        "chains": [{"chain_id": "seed_chain", "rule_id": "seed_rule",
                    "observations": [{"ref": "chart_1", "location": "left mark",
                                      "content": "The mark is blue."}],
                    "claim_kind": "supports_action", "option_label": "Route A",
                    "claim": "Under that key, the visible mark supports Route A."}],
    }


@pytest.fixture
def questions(base):
    rows = []
    for index, kind in enumerate(("evidence_sufficiency", "rule_assumptions", "alternative_explanation"), 1):
        rows.append({
            "id": "q%d" % index, "kind": kind,
            "target_chain_ids": [base["chains"][0]["chain_id"]],
            "target_rule_ids": [base["rules"][0]["id"]],
            "question": "Which visible relation tests this bridge?",
            "current_bridge": "The printed key is assumed to govern the blue mark.",
            "brief_assessment": "The bridge remains conditional.",
            "chart_evidence": [], "candidate_bridge": None,
            "discriminating_check": "Inspect the visible key-to-mark relation.",
            "uncertainty": "Not yet independently checked.",
        })
    return {"visual_inventory": [{"ref": "chart_1", "location": "left mark",
                                    "content": "The mark is blue."}],
            "questions": rows, "questioning_summary": "Check the supplied bridge."}


def empty_competitors(questions):
    return {"new_rules": [], "new_chains": [],
            "question_responses": [
                {"question_id": q["id"], "resolution": "no_supported_alternative",
                 "candidate_ids": [], "reason": "No grounded alternative was found."}
                for q in questions["questions"]]}


def one_competitor(questions, kind="supports_action", option="Route B", alternative="Another visible relation applies."):
    value = empty_competitors(questions)
    value["new_rules"] = [{"id": "new_r1", "text": "A necessary visible condition may be absent.",
                           "component": "support sufficiency", "conditions": "This chart only."}]
    value["new_chains"] = [{
        "candidate_id": "n1", "question_ids": ["q1", "q3"],
        "observations": [{"ref": "chart_1", "location": "right mark", "content": "A red mark is visible."}],
        "rule_id": "new_r1", "claim_kind": kind, "option_label": option,
        "claim": "The visible relation changes what the current support establishes.",
        "difference_from_base": "It tests support sufficiency rather than assuming the key applies.",
        "discriminator": {"base_reading": "The blue mark is enough.",
                          "alternative_reading": alternative,
                          "observable_check": "Inspect the key beside both marks.",
                          "availability": "visible" if alternative is not None else "not_available"},
    }]
    for row in value["question_responses"]:
        if row["question_id"] in {"q1", "q3"}:
            row.update(resolution="candidate_generated", candidate_ids=["n1"])
    return value


def checks_for(normalized, status="supported"):
    return [{"chain_id": chain["chain_id"], "O": status, "B": status, "implication": status,
             "evidence": [{"ref": "chart_1", "location": "visible mark", "content": "A mark is visible."}],
             "reason": "Synthetic structural fixture; not a semantic finding."}
            for chain in normalized["chains"]]


@contextmanager
def direct_output(label):
    path = HERE / (".offline_%s_%s" % (label, uuid.uuid4().hex))
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_question_schema_bounds_unknown_refs_and_private_fields(base, questions):
    assert runner.validate_questions(copy.deepcopy(questions), base) == questions
    mutations = []
    too_many = copy.deepcopy(questions)
    too_many["visual_inventory"] *= 9
    mutations.append(too_many)
    missing_bridge = copy.deepcopy(questions)
    missing_bridge["questions"][0]["current_bridge"] = " "
    mutations.append(missing_bridge)
    unknown_ref = copy.deepcopy(questions)
    unknown_ref["visual_inventory"][0]["ref"] = "another_arm"
    mutations.append(unknown_ref)
    private = copy.deepcopy(questions)
    private["questions"][0]["gold"] = "forbidden"
    mutations.append(private)
    for value in mutations:
        with pytest.raises(ValueError):
            runner.validate_questions(value, base)


def test_zero_competition_and_exact_duplicate_are_not_forced_or_counted(base, questions, public):
    empty = runner.merge_candidates(empty_competitors(questions), base, questions, public)
    assert len(empty["normalized"]["chains"]) == 1
    assert empty["normalization_audit"]["unique_new_count"] == 0

    duplicate = one_competitor(questions, option="Route A")
    duplicate["new_rules"][0] = {**copy.deepcopy(base["rules"][0]), "id": "new_r1"}
    for key in ("observations", "claim_kind", "option_label", "claim"):
        duplicate["new_chains"][0][key] = copy.deepcopy(base["chains"][0][key])
    result = runner.merge_candidates(duplicate, base, questions, public)
    assert len(result["combined_raw"]["chains"]) == 2
    assert len(result["normalized"]["chains"]) == 1
    assert result["normalization_audit"]["exact_duplicate_count"] == 1
    fresh = next(row for row in result["candidate_provenance"] if row["source"] == "new")
    assert fresh["exact_duplicate"] is True and fresh["counted_as_new"] is False


def test_nonaction_null_alternative_is_legal_but_action_requires_reading(base, questions, public):
    challenge = one_competitor(questions, kind="challenges_support", option=None, alternative=None)
    result = runner.merge_candidates(challenge, base, questions, public)
    assert {c["claim_kind"] for c in result["normalized"]["chains"]} == {
        "supports_action", "challenges_support"}
    assert next(c for c in result["normalized"]["chains"]
                if c["claim_kind"] == "challenges_support")["option_label"] is None

    invalid = one_competitor(questions, kind="supports_action", option="Route B", alternative=None)
    with pytest.raises(ValueError, match="alternative reading"):
        runner.merge_candidates(invalid, base, questions, public)


def test_candidate_limits_dependencies_and_public_evidence(base, questions, public):
    value = one_competitor(questions)
    third = copy.deepcopy(value["new_chains"][0])
    value["new_chains"] = [copy.deepcopy(third) for _ in range(3)]
    with pytest.raises(ValueError, match="zero to two"):
        runner.merge_candidates(value, base, questions, public)
    value = one_competitor(questions)
    value["new_chains"][0]["question_ids"] = ["q99"]
    with pytest.raises(ValueError, match="question dependencies"):
        runner.merge_candidates(value, base, questions, public)
    value = one_competitor(questions)
    value["new_chains"][0]["observations"][0]["ref"] = "private_chart"
    with pytest.raises(ValueError, match="chart_1"):
        runner.merge_candidates(value, base, questions, public)


def test_raw_verdict_preserved_and_null_challenge_neither_executes_nor_blanket_vetoes(base, questions, public):
    merged = runner.merge_candidates(
        one_competitor(questions, kind="challenges_support", option=None, alternative=None),
        base, questions, public)
    normalized = merged["normalized"]
    accepted = {"checks": checks_for(normalized), "recommendation": "Route A", "unresolved_reason": ""}
    kept = runner.validate_verification(accepted, normalized, public)
    assert kept["verification_raw"] == accepted
    assert kept["verification_validated"]["recommendation"] == "Route A"
    assert kept["recommendation_guard"]["changed"] is False
    assert all(state["status"] == "active" for state in kept["rule_state"])
    assert "no cross-step validity" in kept["rule_state_limit"]

    unsupported = {"checks": checks_for(normalized), "recommendation": "Route B",
                   "unresolved_reason": "The model proposed an unsupported action."}
    guarded = runner.validate_verification(unsupported, normalized, public)
    assert guarded["verification_raw"]["recommendation"] == "Route B"
    assert guarded["verification_validated"]["recommendation"] is None
    assert guarded["recommendation_guard"]["reasons"] == [
        "no_fully_supported_action_chain_for_recommendation"]
    assert guarded["recommendation_guard"]["model_changed_its_mind"] == "not_inferred_from_guard_coercion"


def test_verifier_accepts_bound_public_text_but_rejects_unknown_path(base, public):
    normalized = copy.deepcopy(base)
    value = {"checks": checks_for(normalized), "recommendation": None, "unresolved_reason": "Unresolved."}
    value["checks"][0]["evidence"].append(
        {"ref": "public_task", "location": "user_goal", "content": "Choose a route."})
    result = runner.validate_verification(value, normalized, public)
    check = result["verification_validated"]["checks"][0]
    assert check["task_evidence"][0]["source_field"] == "user_goal"
    bad = copy.deepcopy(value)
    bad["checks"][0]["evidence"][-1]["location"] = "gold.answer"
    with pytest.raises(ValueError, match="field unavailable"):
        runner.validate_verification(bad, normalized, public)


def test_actual_questions_flow_to_competitor_and_verifier_is_blind(base, questions, public):
    inputs = {"task": public, "base_arguments": base, "base_proposal": {"marker": "origin"}}
    result = {"base_arguments": base, "questions": questions,
              "normalized": copy.deepcopy(base), "candidate_provenance": [{"marker": "critic"}]}
    competitor = runner.build_context("competitors", inputs, result)
    assert competitor["counterquestions"] == questions
    assert competitor["base_arguments"] == base
    verifier = runner.build_context("verification", inputs, result)
    assert set(verifier) == {"task", "state", "history", "interpretation_rules",
                             "arguments", "public_task_text_paths"}
    wire = json.dumps(verifier)
    assert "origin" not in wire and "critic" not in wire and "counterquestions" not in wire


def test_load_case_clean_never_reads_paired_arm_and_original_uses_first_generation_match(tmp_path, public):
    archive = tmp_path / "research/obc140_runtime_aligned_20260924"
    write_json(archive / "prepared/tasks/t1/public.json", public)
    clean_chart = tmp_path / "clean/chart.png"
    clean_chart.parent.mkdir(parents=True)
    clean_chart.write_bytes(b"clean-chart")
    clean = {"case_id": "clean", "task_id": "t1", "seed_mode": "fresh_single_argument",
             "chart": "clean/chart.png"}
    loaded = runner.load_case(clean, project_root=tmp_path)
    assert loaded["base_arguments"] is loaded["base_proposal"] is None
    assert loaded["seed_provenance"]["archived_arm_records_read"] is False
    assert not (archive / "run").exists()

    original_chart = tmp_path / "original/chart.jpeg"
    original_chart.parent.mkdir(parents=True)
    original_chart.write_bytes(b"original-chart")
    proposal_path = archive / "run/tasks/t1/proposal/round_001/validated.json"
    generation_path = archive / "run/tasks/t1/generation/round_001/validated.json"
    write_json(proposal_path, {"proposal": {"action": {"kind": "select", "option": "Route A"},
                                             "brief_basis": "fixture"}})
    rules = [{"id": "r%d" % i, "text": "Rule %d" % i, "component": "component %d" % i,
              "conditions": "scope %d" % i} for i in range(1, 4)]
    chains = [
        {"rule_id": "r1", "observations": [{"ref": "chart_1", "location": "one", "content": "one"}],
         "option_label": "Route B", "claim": "first other"},
        {"rule_id": "r2", "observations": [{"ref": "chart_1", "location": "two", "content": "two"}],
         "option_label": "Route A", "claim": "first target"},
        {"rule_id": "r3", "observations": [{"ref": "chart_1", "location": "three", "content": "three"}],
         "option_label": "Route A", "claim": "second target"},
    ]
    write_json(generation_path, {"generated": {"rules": rules, "chains": chains},
                                 "normalized": {"gold": "must not be selected from"}})
    before = {str(path): runner.core.digest(path) for path in
              (proposal_path, generation_path, original_chart,
               archive / "prepared/tasks/t1/public.json")}
    original = {"case_id": "original", "task_id": "t1",
                "seed_mode": "archived_first_proposal_support", "chart": "original/chart.jpeg"}
    loaded = runner.load_case(original, project_root=tmp_path)
    assert loaded["seed_provenance"]["original_chain_index"] == 1
    assert loaded["seed_original"]["chains"][0]["claim"] == "first target"
    assert len(loaded["base_arguments"]["chains"]) == 1
    assert "gold" not in json.dumps(loaded)
    assert before == {path: runner.core.digest(path) for path in before}


def test_prepare_is_zero_network_and_preserves_sources():
    class ForbiddenFactory:
        def __init__(self, *args, **kwargs):
            raise AssertionError("prepare must not construct an API client")
    with direct_output("prepare") as output:
        summary = runner.run(output, live=False, api_factory=ForbiddenFactory)
        assert summary["status"] == "prepared_not_sent"
        assert summary["request_attempts"] == 0
        assert summary["estimated_ledger_usd"] == 0
        assert all(summary["runtime_source_preservation"].values())
        assert len(summary["cases"]) == 6


def test_fixed_chart_and_accounting_controls_cannot_drift():
    config = runner.core.read(HERE / "config.json")
    manifest = runner.core.read(HERE / "manifest.json")
    changes = [
        ("config", "attempt_reserve_usd", 0),
        ("config", "estimated_input_usd_per_m", 0),
        ("config", "estimated_output_usd_per_m", 0),
        ("config", "phase_max_tokens", {"generation": 1, "verification": 1}),
        ("config", "proxy", "http://127.0.0.1:9999"),
        ("config", "timeout_seconds", 1),
        ("manifest", "chart", "another/condition.png"),
    ]
    for target, key, changed in changes:
        candidate_config, candidate_manifest = copy.deepcopy(config), copy.deepcopy(manifest)
        if target == "config":
            candidate_config[key] = changed
        else:
            candidate_manifest["cases"][0][key] = changed
        with pytest.raises(ValueError):
            runner.validate_config(candidate_config, candidate_manifest)


def test_shared_budget_enforces_attempt_and_reserved_cost_caps(tmp_path):
    config = runner.core.read(HERE / "config.json")
    attempt_budget = runner.EstimatedBudget(tmp_path / "attempt_budget.json", config)
    for index in range(24):
        folder = tmp_path / ("attempt_%02d" % index)
        folder.mkdir()
        attempt_budget.current_folder = folder
        attempt_budget.charge({"task_slug": "synthetic", "phase": "generation",
                               "round": "round_001", "attempt": 1})
        runner.core.dump(folder / "response_01.json", {
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}})
        attempt_budget.reconcile()
    with pytest.raises(runner.core.ServiceStop, match="request_budget"):
        attempt_budget.charge({"task_slug": "synthetic", "phase": "generation",
                               "round": "round_001", "attempt": 1})
    assert attempt_budget.value["request_attempts"] == 24

    cost_budget = runner.EstimatedBudget(tmp_path / "cost_budget.json", config)
    unresolved = tmp_path / "unresolved"
    unresolved.mkdir()
    cost_budget.current_folder = unresolved
    for _ in range(12):
        cost_budget.charge({"task_slug": "synthetic", "phase": "verification",
                            "round": "round_001", "attempt": 1})
    with pytest.raises(runner.core.ServiceStop, match="usd_budget"):
        cost_budget.charge({"task_slug": "synthetic", "phase": "verification",
                            "round": "round_001", "attempt": 1})
    assert cost_budget.value["request_attempts"] == 12
    assert cost_budget.value["estimated_ledger_usd"] == 3.0


class OfflinePanelAPI:
    instances = []
    fail_first_questions = False

    def __init__(self, config, budget):
        self.config, self.budget, self.calls = config, budget, []
        type(self).instances.append(self)

    def call(self, folder, task_id, phase, prompt, context, images):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=False)
        self.budget.current_folder = folder
        self.budget.charge({"task_slug": task_id, "phase": phase, "round": folder.name, "attempt": 1})
        runner.core.dump(folder / "response_01.json", {
            "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}})
        self.budget.reconcile()
        self.budget.current_folder = None
        stage = next(name for name, template in runner.PROMPTS.items() if prompt == template)
        self.calls.append({"task_id": task_id, "stage": stage, "phase": phase,
                           "prompt": prompt, "context": copy.deepcopy(context),
                           "budget_id": id(self.budget)})
        if self.fail_first_questions and len(self.calls) == 1 and stage == "questions":
            return {"visual_inventory": [], "questions": []}
        if stage == "seed":
            option = context["task"]["option_labels"][0]
            return {"rules": [{"id": "s1", "text": "A visible relation may support the option.",
                                "component": "visible relation", "conditions": "This chart only."}],
                    "chains": [{"rule_id": "s1", "observations": [
                        {"ref": "chart_1", "location": "visible area", "content": "A mark is visible."}],
                        "option_label": option, "claim": "The conditional relation supports the option."}]}
        if stage == "questions":
            return _questions_for(context["base_arguments"])
        if stage == "competitors":
            return empty_competitors(context["counterquestions"])
        option = context["arguments"]["chains"][0]["option_label"]
        return {"checks": checks_for(context["arguments"]), "recommendation": option,
                "unresolved_reason": "Synthetic fixture only."}


def _questions_for(base):
    rows = []
    kinds = ("evidence_sufficiency", "rule_assumptions", "alternative_explanation")
    for index, kind in enumerate(kinds, 1):
        rows.append({"id": "q%d" % index, "kind": kind,
                     "target_chain_ids": [base["chains"][0]["chain_id"]],
                     "target_rule_ids": [base["rules"][0]["id"]],
                     "question": "Which visible fact tests the bridge?",
                     "current_bridge": "The supplied conditional relation.",
                     "brief_assessment": "Still conditional.", "chart_evidence": [],
                     "candidate_bridge": None,
                     "discriminating_check": "Inspect the localized relation.", "uncertainty": ""})
    return {"visual_inventory": [], "questions": rows, "questioning_summary": "No conflict is forced."}


def test_full_panel_uses_one_global_budget_19_calls_and_generic_stage_prompts(monkeypatch):
    OfflinePanelAPI.instances = []
    OfflinePanelAPI.fail_first_questions = False
    monkeypatch.setenv("MODEL_API_KEY", "offline-placeholder-not-sent")
    with direct_output("full") as output:
        summary = runner.run(output, live=True, api_factory=OfflinePanelAPI)
        assert summary["status"] == "completed"
        assert summary["request_attempts"] == 19 <= 24
        assert 0 < summary["estimated_ledger_usd"] < 3
        assert len(OfflinePanelAPI.instances) == 1
        calls = OfflinePanelAPI.instances[0].calls
        assert len(calls) == 19 and len({call["budget_id"] for call in calls}) == 1
        assert {call["prompt"] for call in calls if call["stage"] == "questions"} == {
            runner.PROMPTS["questions"]}
        assert len({call["task_id"] for call in calls if call["stage"] == "questions"}) > 1
        for call in calls:
            runner.public_inputs.assert_public(call["context"])
            if call["stage"] == "competitors":
                assert call["context"]["counterquestions"]["questions"]
            if call["stage"] == "verification":
                assert set(call["context"]) == {"task", "state", "history", "interpretation_rules",
                                                  "arguments", "public_task_text_paths"}


def test_invalid_stage_has_no_quality_retry_and_later_cases_continue(monkeypatch):
    OfflinePanelAPI.instances = []
    OfflinePanelAPI.fail_first_questions = True
    monkeypatch.setenv("MODEL_API_KEY", "offline-placeholder-not-sent")
    with direct_output("invalid") as output:
        summary = runner.run(output, live=True, api_factory=OfflinePanelAPI)
        calls = OfflinePanelAPI.instances[0].calls
        first = [call for call in calls if call["task_id"] == "b001_original"]
        assert [(call["stage"], call["task_id"]) for call in first] == [("questions", "b001_original")]
        assert len(calls) == 17
        assert summary["status"] == "completed_with_case_failures"
        assert summary["cases"][0]["status"] == "failed_stage_no_quality_retry"
        assert summary["cases"][1]["status"] == "completed"


def test_unknown_request_outcome_stops_the_whole_panel_without_resend(monkeypatch):
    class UnknownOutcomeAPI(OfflinePanelAPI):
        instances = []

        def call(self, folder, task_id, phase, prompt, context, images):
            folder = Path(folder)
            folder.mkdir(parents=True, exist_ok=False)
            self.budget.current_folder = folder
            self.budget.charge({"task_slug": task_id, "phase": phase,
                                "round": folder.name, "attempt": 1})
            self.calls.append({"task_id": task_id, "stage": "questions"})
            raise runner.core.UnknownRequestOutcome("synthetic_unknown_no_resend")

    monkeypatch.setenv("MODEL_API_KEY", "offline-placeholder-not-sent")
    with direct_output("unknown") as output:
        summary = runner.run(output, live=True, api_factory=UnknownOutcomeAPI)
        assert len(UnknownOutcomeAPI.instances) == 1
        assert len(UnknownOutcomeAPI.instances[0].calls) == 1
        assert summary["status"] == "stopped_global"
        assert summary["request_attempts"] == 1
        assert summary["cases"][0]["status"] == "stopped_global"
        assert all(case["status"] == "not_attempted_global_stop" for case in summary["cases"][1:])
