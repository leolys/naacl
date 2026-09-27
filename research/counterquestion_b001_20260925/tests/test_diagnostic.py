"""Synthetic, network-disabled regressions for the bounded counterquestion flow."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("b001_counterquestion_diagnostic", HERE / "run_diagnostic.py")
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("These tests must never send a network request")
    monkeypatch.setattr(diagnostic.core.requests.sessions.Session, "request", forbidden)


@pytest.fixture
def public():
    return {"task_alias": "task_test", "page_title": "Public task", "user_goal": "Choose a route.",
            "chart_reference": "Use this chart.", "primary_field_label": "Route",
            "option_labels": ["Route A", "Route B"], "companion_fields": [],
            "completion_label": "Submit Form", "policy_tables": [], "page_instructions": []}


@pytest.fixture
def base():
    return {"rules": [{"id": "seed_rule_7", "text": "Z binding applies if the printed key governs marks.",
                       "component": "z binding", "conditions": "This chart only."}],
            "chains": [{"chain_id": "seed_chain_7", "rule_id": "seed_rule_7",
                        "observations": [{"ref": "chart_1", "location": "left mark", "content": "The mark is blue."}],
                        "option_label": "Route A", "claim": "Z conditional claim for the original route."}]}


@pytest.fixture
def questions(base):
    return {"questions": [{"id": "q" + str(i + 1), "kind": kind,
                           "target_chain_ids": [base["chains"][0]["chain_id"]],
                           "target_rule_ids": [base["rules"][0]["id"]],
                           "question": "Which visible fact tests this condition?",
                           "brief_assessment": "The interpretation remains conditional.",
                           "chart_evidence": [], "candidate_bridge": None,
                           "discriminating_check": "Check the printed legend.", "uncertainty": "Not yet verified."}
                          for i, kind in enumerate(diagnostic.KINDS)],
            "questioning_summary": "Inspect the stated bridge without assuming it is wrong."}


def empty_competitors(questions):
    return {"new_rules": [], "new_chains": [],
            "question_responses": [{"question_id": q["id"], "resolution": "no_supported_alternative",
                                    "candidate_ids": [], "reason": "No alternative localized for this question."}
                                   for q in questions["questions"]]}


def one_competitor(questions):
    value = empty_competitors(questions)
    value["new_rules"] = [{"id": "new_r1", "text": "A different binding applies if the mark uses another key.",
                           "component": "a binding", "conditions": "Conditional same-chart alternative."}]
    value["new_chains"] = [{"candidate_id": "n1", "question_ids": ["q1", "q3"], "rule_id": "new_r1",
                            "observations": [{"ref": "chart_1", "location": "right mark", "content": "The mark is red."}],
                            "option_label": "Route B", "claim": "A conditional alternative route.",
                            "difference_from_base": "A different mark-to-key binding."}]
    for row in value["question_responses"]:
        if row["question_id"] in {"q1", "q3"}:
            row.update(resolution="candidate_generated", candidate_ids=["n1"])
    return value


def test_exact_question_kinds_and_supplied_ids(questions, base):
    original = copy.deepcopy(questions)
    assert diagnostic.validate_questions(questions, base) == original
    assert [q["kind"] for q in questions["questions"]] == diagnostic.KINDS
    assert all(q["target_chain_ids"] == ["seed_chain_7"] for q in questions["questions"])


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_kind", "wrong_id", "unknown_chain", "unknown_rule"])
def test_reject_incomplete_or_incorrect_question_targets(questions, base, mutation):
    if mutation == "missing":
        questions["questions"].pop()
    elif mutation == "extra":
        questions["questions"].append(copy.deepcopy(questions["questions"][0]))
    elif mutation == "wrong_kind":
        questions["questions"][1]["kind"] = "evidence_sufficiency"
    elif mutation == "wrong_id":
        questions["questions"][0]["id"] = "q9"
    elif mutation == "unknown_chain":
        questions["questions"][0]["target_chain_ids"] = ["c1"]
    else:
        questions["questions"][0]["target_rule_ids"] = ["r1"]
    with pytest.raises(ValueError):
        diagnostic.validate_questions(questions, base)


def test_unknown_question_evidence_ref_rejected(questions, base):
    questions["questions"][0]["chart_evidence"] = [{"ref": "another_arm", "location": "plot", "content": "A mark."}]
    with pytest.raises(ValueError, match="chart reference"):
        diagnostic.validate_questions(questions, base)


def test_zero_alternatives_allowed_with_per_question_reasons(questions, base, public):
    result = diagnostic.merge_candidates(empty_competitors(questions), base, questions, public)
    assert len(result["normalized"]["chains"]) == 1
    assert result["combined_raw"] == base
    assert result["candidate_provenance"][0]["source"] == "inherited"


@pytest.mark.parametrize("mutation", ["missing_response", "duplicate_response", "empty_reason", "wrong_resolution", "invented_candidate"])
def test_zero_alternatives_require_complete_honest_responses(questions, base, public, mutation):
    value = empty_competitors(questions)
    if mutation == "missing_response":
        value["question_responses"].pop()
    elif mutation == "duplicate_response":
        value["question_responses"][2] = copy.deepcopy(value["question_responses"][0])
    elif mutation == "empty_reason":
        value["question_responses"][0]["reason"] = " "
    elif mutation == "wrong_resolution":
        value["question_responses"][0]["resolution"] = "candidate_generated"
    else:
        value["question_responses"][0]["candidate_ids"] = ["n1"]
    with pytest.raises(ValueError):
        diagnostic.merge_candidates(value, base, questions, public)


@pytest.mark.parametrize("mutation", ["unknown_question", "no_question", "missing_backlink", "spurious_backlink",
                                      "unknown_ref", "unknown_option", "colliding_rule", "extra_candidates"])
def test_reject_invalid_candidate_dependencies_and_scope(questions, base, public, mutation):
    value = one_competitor(questions)
    if mutation == "unknown_question":
        value["new_chains"][0]["question_ids"] = ["q99"]
    elif mutation == "no_question":
        value["new_chains"][0]["question_ids"] = []
    elif mutation == "missing_backlink":
        value["question_responses"][0]["candidate_ids"] = []
    elif mutation == "spurious_backlink":
        value["question_responses"][1].update(candidate_ids=["n1"], resolution="candidate_generated")
    elif mutation == "unknown_ref":
        value["new_chains"][0]["observations"][0]["ref"] = "chart_2"
    elif mutation == "unknown_option":
        value["new_chains"][0]["option_label"] = "Route C"
    elif mutation == "colliding_rule":
        value["new_rules"][0]["id"] = base["rules"][0]["id"]
    else:
        value["new_chains"] *= 3
    with pytest.raises(ValueError):
        diagnostic.merge_candidates(value, base, questions, public)


def test_inherited_content_and_trace_survive_normalized_id_reordering(questions, base, public):
    before = copy.deepcopy(base)
    result = diagnostic.merge_candidates(one_competitor(questions), base, questions, public)
    assert base == before
    assert result["combined_raw"]["chains"][0] == before["chains"][0]
    inherited = next(p for p in result["candidate_provenance"] if p["source"] == "inherited")
    assert inherited["source_id"] == "seed_chain_7"
    assert inherited["normalized_chain_id"] == "c2"
    current = next(c for c in result["normalized"]["chains"] if c["chain_id"] == inherited["normalized_chain_id"])
    for key in ("observations", "claim", "option_label"):
        assert current[key] == before["chains"][0][key]
    rule = next(r for r in result["normalized"]["rules"] if r["id"] == current["rule_id"])
    assert {k: v for k, v in rule.items() if k != "id"} == {k: v for k, v in before["rules"][0].items() if k != "id"}
    fresh = next(p for p in result["candidate_provenance"] if p["source"] == "new")
    assert fresh["question_ids"] == ["q1", "q3"]


def test_same_action_competitor_is_allowed(questions, base, public):
    value = one_competitor(questions)
    value["new_chains"][0]["option_label"] = "Route A"
    result = diagnostic.merge_candidates(value, base, questions, public)
    assert len(result["normalized"]["chains"]) == 2
    assert {c["option_label"] for c in result["normalized"]["chains"]} == {"Route A"}


def test_seed_whitelists_inheritance_without_old_verdict_or_gold(monkeypatch, tmp_path, base, public):
    old = {"public_task": public, "proposal": {"action": {"kind": "select", "option": "Route A"}},
           "normalized": base, "verification": {"marker": "OLD_VERDICT_SENTINEL"},
           "rule_state": [{"marker": "OLD_RULE_STATE_SENTINEL"}], "gold": "HIDDEN_SENTINEL"}
    monkeypatch.setattr(diagnostic.core, "read", lambda p: old if Path(p).name == "record.json" else public)
    saved = {}
    monkeypatch.setattr(diagnostic.core, "dump", lambda p, value: saved.update({Path(p).name: copy.deepcopy(value)}))
    monkeypatch.setattr(diagnostic.core, "digest", lambda p: "synthetic-source-digest")
    monkeypatch.setattr(diagnostic.shutil, "copyfile", lambda *args: None)
    monkeypatch.setattr(diagnostic, "source_files", lambda: [])
    inputs = diagnostic.seed(tmp_path / "synthetic_seed")
    assert set(inputs) == {"task", "base_proposal", "base_arguments"}
    assert inputs["base_arguments"] == base
    wire = json.dumps(inputs)
    assert all(marker not in wire for marker in ("OLD_VERDICT_SENTINEL", "OLD_RULE_STATE_SENTINEL", "HIDDEN_SENTINEL"))
    assert saved["seed_input.json"] == inputs


@pytest.mark.parametrize("invalid_phase", [None, "counterquestions", "competitors"])
def test_mock_flow_passes_real_question_output_and_blinds_verifier(monkeypatch, tmp_path, base, public, questions, invalid_phase):
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    inputs = {"task": public, "base_arguments": base, "base_proposal": {"action": {"kind": "select", "option": "Route A"}}}
    monkeypatch.setattr(diagnostic, "seed", lambda output: copy.deepcopy(inputs))
    monkeypatch.setattr(diagnostic.core, "read", lambda p: copy.deepcopy(config) if Path(p).name == "config.json" else {"seed_sha256": {}})
    monkeypatch.setattr(diagnostic.core, "dump", lambda *args: None)
    monkeypatch.setenv("MODEL_API_KEY", "offline-mock-not-a-credential")
    captured = []

    class FakeBudget:
        def __init__(self, *args):
            self.value = {"request_attempts": 0, "estimated_ledger_usd": 0}

        def reconcile(self):
            pass

    class FakeAPI:
        def __init__(self, config, budget):
            self.budget = budget

        def call(self, folder, task_id, phase, prompt, context, images):
            stage = Path(folder).parent.name
            self.budget.value["request_attempts"] += 1
            captured.append((stage, copy.deepcopy(context)))
            if stage == invalid_phase:
                return {"questions": []} if stage == "counterquestions" else {"new_chains": []}
            if stage == "counterquestions":
                return copy.deepcopy(questions)
            if stage == "competitors":
                return one_competitor(questions)
            return {"checks": [{"chain_id": c["chain_id"], "O": "supported", "B": "supported",
                                "implication": "supported", "evidence": copy.deepcopy(c["observations"]),
                                "reason": "Synthetic fixture, not a semantic finding."}
                               for c in context["arguments"]["chains"]],
                    "recommendation": None, "unresolved_reason": "Synthetic fixture."}

    monkeypatch.setattr(diagnostic, "EstimatedBudget", FakeBudget)
    monkeypatch.setattr(diagnostic, "BudgetedPanelAPI", FakeAPI)
    result = diagnostic.run(tmp_path / "mock_only", live=True)
    if invalid_phase:
        assert result["status"] == "stopped_with_invalid_stage"
        assert captured[-1][0] == invalid_phase
        assert len(captured) == (1 if invalid_phase == "counterquestions" else 2)
    else:
        assert result["status"] == "completed"
        assert [stage for stage, _ in captured] == ["counterquestions", "competitors", "verification"]
        assert captured[1][1]["counterquestions"] == questions
        assert captured[1][1]["base_arguments"] == base
        verifier = captured[2][1]
        assert set(verifier) == {"task", "state", "history", "interpretation_rules", "arguments", "public_task_text_paths"}
        assert len(verifier["arguments"]["chains"]) == 2
        assert "user_goal" in verifier["public_task_text_paths"]
        assert all("question_ids" not in c and "candidate_id" not in c for c in verifier["arguments"]["chains"])
    for _, context in captured:
        assert context["history"] == [] and context["interpretation_rules"] == []
        diagnostic.public_inputs.assert_public(context)
        assert not {"gold", "verification", "rule_state", "verification_invalid_raw"} & set(context)
    assert result["browser_operations"] == result["gpu_operations"] == result["translation_api_calls"] == 0


@pytest.mark.parametrize("key,value", [("model", "another-model"), ("endpoint", "https://example.invalid"),
                                       ("max_request_attempts", 10), ("max_estimated_usd", 2),
                                       ("concurrency", 2), ("quality_retries", True)])
def test_changed_bounded_config_rejected_before_seed(monkeypatch, tmp_path, key, value):
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    config[key] = value
    monkeypatch.setattr(diagnostic.core, "read", lambda p: config)
    def unexpected_seed(output):
        pytest.fail("Invalid budget/resource configuration must stop before seed or API construction")
    monkeypatch.setattr(diagnostic, "seed", unexpected_seed)
    with pytest.raises(ValueError, match="configuration changed"):
        diagnostic.run(tmp_path / "must_not_exist", live=False)


def test_public_field_index_contains_only_text_leaf_paths(public):
    public["companion_fields"] = [{"label": "Scope", "required": True, "value": "Current period"}]
    paths = diagnostic.text_paths(public)
    assert "option_labels.0" in paths and "companion_fields.0.value" in paths
    assert "companion_fields.0.required" not in paths
    assert all(value not in paths for value in ("Route A", "Route B", "Current period"))


@pytest.mark.parametrize("field", ["text", "component", "conditions"])
@pytest.mark.parametrize("missing", [False, True])
def test_new_rule_requires_nonempty_interpretation_component_and_scope(questions, base, public, field, missing):
    value = one_competitor(questions)
    if missing:
        value["new_rules"][0].pop(field)
    else:
        value["new_rules"][0][field] = "  "
    with pytest.raises(ValueError, match="interpretation, component and scope"):
        diagnostic.merge_candidates(value, base, questions, public)


@pytest.mark.parametrize("missing", [False, True])
def test_new_chain_requires_nonempty_derived_claim(questions, base, public, missing):
    value = one_competitor(questions)
    if missing:
        value["new_chains"][0].pop("claim")
    else:
        value["new_chains"][0]["claim"] = "\t "
    with pytest.raises(ValueError, match="derived claim"):
        diagnostic.merge_candidates(value, base, questions, public)


def test_exact_base_restatement_rejected_despite_new_ids_and_difference_text(questions, base, public):
    value = one_competitor(questions)
    value["new_rules"][0] = {**copy.deepcopy(base["rules"][0]), "id": "new_r1"}
    value["new_rules"][0]["text"] = "  " + value["new_rules"][0]["text"].upper() + "  "
    chain = value["new_chains"][0]
    for field in ("observations", "option_label", "claim"):
        chain[field] = copy.deepcopy(base["chains"][0][field])
    chain["difference_from_base"] = "This claims to differ, but the actual normalized content is unchanged."
    with pytest.raises(ValueError, match="exact normalized restatement"):
        diagnostic.merge_candidates(value, base, questions, public)


def test_two_new_chains_cannot_be_normalized_duplicates(questions, base, public):
    value = one_competitor(questions)
    second = copy.deepcopy(value["new_chains"][0])
    second.update(candidate_id="n2", rule_id="new_r2")
    value["new_chains"].append(second)
    rule = {**copy.deepcopy(value["new_rules"][0]), "id": "new_r2"}
    rule["text"] = rule["text"].upper()
    value["new_rules"].append(rule)
    for response in value["question_responses"]:
        if response["question_id"] in second["question_ids"]:
            response["candidate_ids"].append("n2")
    with pytest.raises(ValueError, match="exact normalized restatement"):
        diagnostic.merge_candidates(value, base, questions, public)
