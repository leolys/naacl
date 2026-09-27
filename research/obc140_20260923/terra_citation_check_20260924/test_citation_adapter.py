"""Offline citation boundary tests; archive reads only, no API or credential use.

Located source text is provenance, not semantic verification of a model's claim.
The four archived cases are development fixtures, not new inference results.
"""
import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import citation_adapter as adapter
import run_validation as validation

core = adapter.core
ARCHIVE = HERE.parent / "apiyi_selection_20260924" / "runs"
CASES = [(model, task) for model in ("gpt-5.6-sol", "gpt-5.6-terra")
         for task in ("b001", "pub013")]
CHART_ONLY_CASES = [case for case in CASES if case != ("gpt-5.6-terra", "b001")]
GENERATION_CONFIG = {"competitors": 2, "cap_candidates_by_generation_order": True}


def archive_paths(model, task):
    folder = ARCHIVE / model / "tasks" / task
    return folder / "record.json", folder / "verification" / "round_001" / "parsed.json"


def archived(model="gpt-5.6-terra", task="b001"):
    return tuple(json.loads(path.read_text(encoding="utf-8"))
                 for path in archive_paths(model, task))


def validate(raw, record):
    return adapter.validate_stage("verification", raw, record, {})


def task_citation(raw):
    return next(item for item in raw["checks"][0]["evidence"]
                if item["ref"] != "chart_1")


def chart_only(raw):
    result = copy.deepcopy(raw)
    for check in result["checks"]:
        check["evidence"] = [item for item in check["evidence"]
                             if item["ref"] == "chart_1"]
        check.pop("task_evidence", None)
    return result


@pytest.fixture(autouse=True)
def forbid_external_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline citation tests must not contact services or launch processes")

    # API construction is blocked before either constructor can read credentials.
    monkeypatch.setattr(core.PanelAPI, "__init__", forbidden)
    monkeypatch.setattr(core.engine.API, "__init__", forbidden)
    monkeypatch.setattr(core.requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


@pytest.fixture(scope="session", autouse=True)
def archived_files_are_unchanged():
    paths = [path for case in CASES for path in archive_paths(*case)]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    yield
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    assert after == before, "Archived records or verifier responses were changed"


def test_terra_b001_old_rejects_new_separates_public_goal_without_editing_verdict():
    record, raw = archived()
    before_record, before_raw = copy.deepcopy(record), copy.deepcopy(raw)
    with pytest.raises(ValueError, match="actual chart observation"):
        core.validate_stage("verification", raw, record, {})

    output = validate(raw, record)
    check = output["verification"]["checks"][0]
    original = task_citation(raw)
    bound = check["task_evidence"][0]
    assert {key: bound[key] for key in original} == original
    assert bound["source_kind"] == "public_task"
    assert bound["source_field"] == "user_goal"
    assert bound["source_text"] == record["public_task"]["user_goal"]
    assert bound["binding_status"] == "source_bound_content_not_verified"
    assert check["evidence"] == chart_only(raw)["checks"][0]["evidence"]
    assert len(check["evidence"]) == 4
    assert chart_only(output["verification"]) == chart_only(raw)
    assert output["verification_raw"] == raw
    assert output["rule_state"][0]["E"] == check["evidence"]
    assert output["rule_state"][0]["task_evidence"] == [bound]
    assert output["citation_adapter"]["moves"] == [{
        "check_index": 0, "chain_id": "c1", "original_evidence_index": 4,
        "original": original, "bound": bound}]
    assert record == before_record and raw == before_raw


@pytest.mark.parametrize("model,task", CHART_ONLY_CASES)
def test_other_three_archived_results_are_semantically_identical(model, task):
    record, raw = archived(model, task)
    before_record, before_raw = copy.deepcopy(record), copy.deepcopy(raw)
    old = core.validate_stage("verification", raw, record, {})
    new = validate(raw, record)
    assert {key: new[key] for key in old} == old
    assert new["verification"] == record["verification"]
    assert new["rule_state"] == record["rule_state"]
    assert new["citation_adapter"]["moves"] == []
    assert all("task_evidence" not in check for check in new["verification"]["checks"])
    assert all("task_evidence" not in state for state in new["rule_state"])
    assert record == before_record and raw == before_raw


def test_outputs_are_detached_from_original_objects_and_raw_response():
    record, raw = archived()
    before_record, before_raw = copy.deepcopy(record), copy.deepcopy(raw)
    output = validate(raw, record)
    output["verification"]["checks"][0]["task_evidence"][0]["content"] = "mutated result"
    output["verification"]["checks"][0]["evidence"][0]["content"] = "mutated visual"
    output["rule_state"][0]["task_evidence"][0]["source_text"] = "mutated state"
    assert output["verification_raw"] == before_raw
    assert output["citation_adapter"]["moves"][0]["original"] == task_citation(before_raw)
    assert output["citation_adapter"]["moves"][0]["bound"]["content"] == task_citation(before_raw)["content"]
    assert record == before_record and raw == before_raw


@pytest.mark.parametrize("source", ["task_001", "task", "public_task"])
@pytest.mark.parametrize("location", ["user_goal", "task.user_goal", "public_task.user_goal"])
def test_current_alias_and_explicit_public_container_paths(source, location):
    record, raw = archived()
    citation = task_citation(raw)
    citation.update(ref=source, location=location)
    bound = validate(raw, record)["verification"]["checks"][0]["task_evidence"][0]
    assert bound["ref"] == source and bound["location"] == location
    assert bound["source_field"] == "user_goal"
    assert bound["source_text"] == record["public_task"]["user_goal"]


@pytest.mark.parametrize("source", ["unknown", "chart_2", "task_114", "TASK_001", "b001", None])
def test_unknown_or_other_task_source_is_rejected(source):
    record, raw = archived()
    task_citation(raw)["ref"] = source
    before_record, before_raw = copy.deepcopy(record), copy.deepcopy(raw)
    with pytest.raises(ValueError, match="unobserved evidence source"):
        validate(raw, record)
    assert record == before_record and raw == before_raw


@pytest.mark.parametrize("location", [
    "missing", "task_114.user_goal", "task_001.user_goal", "user_goal.missing",
    "task.missing", "public_task.missing", "offline_metadata.gold", "gold",
    "option_labels.3", "option_labels.-1", "option_labels.apple", "option_labels..0",
    "task.task.user_goal", "public_task.task.user_goal", "user_go", "User_Goal",
])
def test_nonexistent_or_ambiguous_field_paths_are_rejected(location):
    record, raw = archived()
    record["offline_metadata"] = {"gold": "OFFLINE_ONLY_SENTINEL"}
    task_citation(raw)["location"] = location
    with pytest.raises(ValueError, match="field unavailable"):
        validate(raw, record)


@pytest.mark.parametrize("location", [None, "", "  ", 0, []])
def test_missing_or_nontext_location_is_rejected(location):
    record, raw = archived()
    task_citation(raw)["location"] = location
    with pytest.raises(ValueError, match="exact public field path"):
        validate(raw, record)


@pytest.mark.parametrize("content", [None, "", " \t\n", 0, [], {}])
def test_empty_or_nontext_model_citation_is_rejected(content):
    record, raw = archived()
    task_citation(raw)["content"] = content
    with pytest.raises(ValueError, match="no model text"):
        validate(raw, record)


@pytest.mark.parametrize("field_value", [None, "", " \t\n", 0, False, [], {}])
def test_public_source_must_be_a_nonempty_text_leaf(field_value):
    record, raw = archived()
    record["public_task"]["user_goal"] = field_value
    with pytest.raises(ValueError, match="nonempty public text field"):
        validate(raw, record)


@pytest.mark.parametrize("location,expected_field", [
    ("option_labels.0", "option_labels.0"),
    ("task.option_labels.1", "option_labels.1"),
    ("public_task.companion_fields.0.label", "companion_fields.0.label"),
])
def test_public_array_paths_bind_exact_text_leaves(location, expected_field):
    record, raw = archived()
    record["public_task"]["companion_fields"] = [{"label": "  Exact companion text.\n"}]
    task_citation(raw)["location"] = location
    bound = validate(raw, record)["verification"]["checks"][0]["task_evidence"][0]
    expected = (record["public_task"]["companion_fields"][0]["label"]
                if "companion_fields" in location
                else record["public_task"]["option_labels"][int(location.rsplit(".", 1)[1])])
    assert bound["source_field"] == expected_field
    assert bound["source_text"] == expected


@pytest.mark.parametrize("location", ["option_labels", "companion_fields.0"])
def test_array_or_object_containers_are_not_text_citations(location):
    record, raw = archived()
    record["public_task"]["companion_fields"] = [{"label": "A field"}]
    task_citation(raw)["location"] = location
    with pytest.raises(ValueError, match="nonempty public text field"):
        validate(raw, record)


def test_task_only_evidence_does_not_substitute_for_visual_evidence():
    record, raw = archived()
    raw["checks"][0]["evidence"] = [copy.deepcopy(task_citation(raw))]
    with pytest.raises(ValueError, match="verification lacks evidence"):
        validate(raw, record)


@pytest.mark.parametrize("value", [[], [{"ref": "task", "source_text": "forged"}], None])
def test_raw_task_evidence_cannot_bypass_binding(value):
    record, raw = archived()
    raw["checks"][0]["task_evidence"] = value
    with pytest.raises(ValueError, match="adapter-owned"):
        validate(raw, record)


@pytest.mark.parametrize("source", ["task_001", "task", "public_task"])
def test_public_task_reference_is_still_forbidden_in_generated_observations(source):
    record, _ = archived()
    generated = copy.deepcopy(record["generated"])
    generated["chains"][0]["observations"][0]["ref"] = source
    with pytest.raises(ValueError, match="chart provenance"):
        adapter.validate_stage("generation", generated, record, GENERATION_CONFIG)


@pytest.mark.parametrize("field", ["O", "B", "implication"])
@pytest.mark.parametrize("status", ["refuted", "undetermined"])
def test_task_binding_cannot_rescue_unsupported_recommendation(field, status):
    record, raw = archived()
    raw["checks"][0][field] = status
    original_recommendation = raw["recommendation"]
    output = validate(raw, record)
    old = core.validate_stage("verification", chart_only(raw), record, {})
    assert output["verification"]["recommendation"] is None
    assert chart_only(output["verification"]) == old["verification"]
    assert output["verification_raw"]["recommendation"] == original_recommendation
    assert raw["recommendation"] == original_recommendation
    assert output["verification"]["checks"][0][field] == status


@pytest.mark.parametrize("conflict", ["different_supported_options", "disputed_shared_rule"])
def test_task_binding_preserves_conflicting_conclusion_guards(conflict):
    record, raw = archived()
    second_chain = copy.deepcopy(record["normalized"]["chains"][0])
    second_chain["chain_id"] = "c2"
    second_chain["option_label"] = record["public_task"]["option_labels"][1]
    record["normalized"]["chains"].append(second_chain)
    second_check = copy.deepcopy(raw["checks"][0])
    second_check["chain_id"] = "c2"
    if conflict == "disputed_shared_rule":
        second_check["B"] = "refuted"
    raw["checks"].append(second_check)
    before_record, before_raw = copy.deepcopy(record), copy.deepcopy(raw)
    output = validate(raw, record)
    old = core.validate_stage("verification", chart_only(raw), record, {})
    assert output["verification"]["recommendation"] is None
    assert output["verification"]["unresolved_reason"] == "Conflicting supported conclusions or shared-rule checks"
    assert chart_only(output["verification"]) == old["verification"]
    assert len(output["rule_state"][0]["task_evidence"]) == 2
    assert all(item["ref"] == "chart_1" for item in output["rule_state"][0]["E"])
    if conflict == "disputed_shared_rule":
        assert output["rule_state"][0]["status"] == "disputed"
    assert record == before_record and raw == before_raw


@pytest.mark.parametrize("defect", ["missing_check", "duplicate_check", "unknown_chain", "invalid_status", "invalid_option"])
def test_remaining_verifier_structure_guards_are_preserved(defect):
    record, raw = archived()
    if defect == "missing_check":
        raw["checks"] = []
    elif defect == "duplicate_check":
        raw["checks"].append(copy.deepcopy(raw["checks"][0]))
    elif defect == "unknown_chain":
        raw["checks"][0]["chain_id"] = "other_chain"
    elif defect == "invalid_status":
        raw["checks"][0]["B"] = "probably_true"
    else:
        raw["recommendation"] = "Not a public option"
    with pytest.raises(ValueError):
        validate(raw, record)


def test_false_paraphrase_keeps_original_source_and_explicit_unverified_status():
    record, raw = archived()
    false_text = "The task explicitly requires the lowest-share brand and forbids using true values."
    task_citation(raw)["content"] = false_text
    output = validate(raw, record)
    bound = output["verification"]["checks"][0]["task_evidence"][0]
    assert bound["content"] == false_text
    assert bound["source_text"] == record["public_task"]["user_goal"]
    assert "highest market share" in bound["source_text"]
    assert bound["source_text"] != bound["content"]
    assert bound["binding_status"] == "source_bound_content_not_verified"
    assert "not independently certified" in output["citation_adapter"]["semantics"]
    assert chart_only(output["verification"]) == chart_only(raw)


def test_model_cannot_forge_adapter_source_binding_metadata():
    record, raw = archived()
    task_citation(raw).update(source_kind="chart", source_field="fake_field",
                              source_text="forged original", binding_status="verified")
    output = validate(raw, record)
    bound = output["verification"]["checks"][0]["task_evidence"][0]
    assert bound["source_kind"] == "public_task"
    assert bound["source_field"] == "user_goal"
    assert bound["source_text"] == record["public_task"]["user_goal"]
    assert bound["binding_status"] == "source_bound_content_not_verified"
    assert output["verification_raw"] == raw
    assert output["citation_adapter"]["moves"][0]["original"] == task_citation(raw)


def test_whitespace_in_source_and_model_text_is_preserved_verbatim():
    record, raw = archived()
    record["public_task"]["user_goal"] = "  A public goal.\n"
    task_citation(raw)["content"] = "\tA model paraphrase.  "
    output = validate(raw, record)
    bound = output["verification"]["checks"][0]["task_evidence"][0]
    assert bound["source_text"] == "  A public goal.\n"
    assert bound["content"] == "\tA model paraphrase.  "


def test_private_metadata_is_not_consulted_or_copied_to_output():
    record, raw = archived()
    record["offline_metadata"] = {"gold": "OFFLINE_ONLY_SENTINEL"}
    output = validate(raw, record)
    assert "OFFLINE_ONLY_SENTINEL" not in json.dumps(output)
    assert record["offline_metadata"] == {"gold": "OFFLINE_ONLY_SENTINEL"}


def test_private_data_inside_public_task_is_rejected():
    record, raw = archived()
    record["public_task"]["gold"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="private key in online data"):
        validate(raw, record)


@pytest.mark.parametrize("phase", ["proposal", "generation", "translation"])
def test_other_stages_delegate_without_behavior_changes(phase):
    record, _ = archived("gpt-5.6-sol", "pub013")
    value = record[{"proposal": "proposal", "generation": "generated", "translation": "translations"}[phase]]
    original_record, original_value = copy.deepcopy(record), copy.deepcopy(value)
    assert adapter.validate_stage(phase, value, record, GENERATION_CONFIG) == core.validate_stage(
        phase, value, record, GENERATION_CONFIG)
    assert record == original_record and value == original_value


@pytest.mark.parametrize("raise_inside", [False, True])
def test_selected_validator_restores_previous_function_on_exit(monkeypatch, raise_inside):
    def previous(*args, **kwargs):
        raise AssertionError("The sentinel validator should not execute")

    monkeypatch.setattr(validation.runner, "validate_stage", previous)
    if raise_inside:
        with pytest.raises(RuntimeError, match="scope sentinel"):
            with validation.selected_validator():
                assert validation.runner.validate_stage is adapter.validate_stage
                raise RuntimeError("scope sentinel")
    else:
        with validation.selected_validator():
            assert validation.runner.validate_stage is adapter.validate_stage
    assert validation.runner.validate_stage is previous


def test_configuration_keeps_two_task_eight_request_no_retry_bound():
    original = core.read(ARCHIVE / "gpt-5.6-terra" / "config_snapshot.json")
    configured = validation.configuration()
    assert validation.TASKS == ("b001", "pub013")
    assert configured["max_request_attempts"] == 8
    assert configured["max_attempts_per_call"] == 1
    assert configured["model"] == original["model"]
    assert configured["endpoint"] == original["endpoint"]
    assert configured["temperature"] == 0
    assert configured["phase_max_tokens"] == {
        "proposal": 700, "generation": 2200, "verification": 2200, "translation": 6500}
    assert configured["phase_max_tokens"] == original["phase_max_tokens"]
    assert core.read(ARCHIVE / "gpt-5.6-terra" / "config_snapshot.json") == original
