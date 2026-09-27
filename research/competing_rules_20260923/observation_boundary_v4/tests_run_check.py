"""Bounded offline tests: no API requests and no browser launches."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location("observation_check", Path(__file__).with_name("run_check.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def config():
    return {"model": "fixed", "temperature": 0, "max_tokens": 2200, "timeout_seconds": 120,
            "max_attempts_per_call": 3, "competitors": 2, "max_request_attempts": 60, "max_browser_operations": 30,
            "task_ids": [case["task_slug"] for case in runner.CASES], "profiles": list(runner.PROFILES), "condition": "official140"}


def test_fixed_case_and_alternating_profile_order():
    assert [case["task_slug"] for case in runner.CASES] == ["pub013", "health004", "b046", "pub031", "b001"]
    assert [runner.profile_order(i) for i in range(5)] == [runner.PROFILES, runner.PROFILES[::-1], runner.PROFILES, runner.PROFILES[::-1], runner.PROFILES]
    first, second = (runner.profile_config(config(), profile) for profile in runner.PROFILES)
    assert {k: v for k, v in first.items() if k != "defense_prompt_profile"} == {k: v for k, v in second.items() if k != "defense_prompt_profile"}


def test_hard_caps_and_legacy_dispatch(monkeypatch):
    monkeypatch.setattr(runner.engine, "defense_prompts", lambda cfg: (runner.engine.GENERATOR, runner.engine.VERIFIER)
                        if cfg["defense_prompt_profile"] == "legacy" else ("new generator", "new verifier"), raising=False)
    runner.validate_config(config())
    with pytest.raises(ValueError):
        runner.validate_config(dict(config(), max_request_attempts=61))
    with pytest.raises(ValueError):
        runner.validate_config(dict(config(), max_browser_operations=31))
    with pytest.raises(ValueError):
        runner.validate_config(dict(config(), temperature=0.5))
    with pytest.raises(ValueError):
        runner.validate_config(dict(config(), condition="clean140"))
    with pytest.raises(ValueError):
        runner.validate_config(dict(config(), task_ids=list(reversed(config()["task_ids"]))))


def test_wire_archive_must_match_actual_text_and_images():
    context = {"context": {"task": {"task_alias": "case01"}}, "images": [{"ref": "chart_1", "file": "chart.png"}]}
    request = {"messages": [{"role": "system", "content": "old"}, {"role": "user", "content": [
        {"type": "text", "text": json.dumps(context["context"])}, {"type": "text", "text": "Observation chart_1"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b"image").decode()}}]}]}
    assert set(runner.wire_bindings(request, context)) == {"chart_1"}
    changed = copy.deepcopy(context)
    changed["context"]["task"]["task_alias"] = "another"
    with pytest.raises(ValueError):
        runner.wire_bindings(request, changed)


def test_module_generation_failure_is_not_counted_as_executed_verifier(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise ValueError("generated candidate count invalid")
    monkeypatch.setattr(runner.engine, "verify", reject)
    shared = {"public_input": {"task": {}, "state": {}, "history": [], "proposal": {"action": {"kind": "select", "option": "A"}}}, "images": []}
    result = runner.run_module({"task_slug": "fixed", "task_alias": "case01", "source": "saved"}, "legacy", shared,
                               None, SimpleNamespace(attempts=0), config(), tmp_path / "module")
    assert not result["verifier_executed"]
    assert result["status"] == "generation_call_or_parse_failure"
    assert not result["submitted"] and not result["business_action_executed"]


def test_new_case_nonselection_is_unsupported_without_executing_action(tmp_path, monkeypatch):
    class NoActionBrowser:
        public_task = {"task_alias": "diag04"}
        chart_path = tmp_path / "chart.png"
        history = [{"source": "deterministic_setup"}]
        receipt = None

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def snapshot(self, tag):
            return {"state": {"options": ["A", "B"], "current_selection": ""}, "screenshot": str(tmp_path / "page.png")}

        def execute(self, *args, **kwargs):
            raise AssertionError("A proposal must never be executed in module preparation")

    class OneProposal:
        count = 0

        def call(self, *args, **kwargs):
            self.count += 1
            return {"action": {"kind": "observe"}}

    monkeypatch.setattr(runner, "BrowserTask", NoActionBrowser)
    api = OneProposal()
    with pytest.raises(ValueError, match="did not propose a valid selection"):
        runner.fresh_case({"task_slug": "fixed"}, tmp_path / "data", tmp_path / "out" / "shared_input", api, None, config())
    assert api.count == 1


def test_completed_module_does_not_execute_recommendation(tmp_path, monkeypatch):
    def completed(*args, **kwargs):
        return {"recommendation": "B", "checks": []}
    monkeypatch.setattr(runner.engine, "verify", completed)
    shared = {"public_input": {"task": {}, "state": {}, "history": [], "proposal": {"action": {"kind": "select", "option": "A"}}}, "images": []}
    result = runner.run_module({"task_slug": "fixed", "task_alias": "case01", "source": "saved"}, "observation_boundary_v4", shared,
                               None, SimpleNamespace(attempts=0), config(), tmp_path / "module")
    assert result["status"] == "completed" and result["recommendation"] == "B"
    assert not result["submitted"] and not result["business_action_executed"]


def test_offline_recommendation_agreement_is_not_submission_success(tmp_path):
    (tmp_path / "offline").mkdir()
    (tmp_path / "offline" / "raw.json").write_text(json.dumps({"action_space": [
        {"action_id": "gold-private", "label": "B"}, {"action_id": "wrong", "label": "A"}], "expected_action_id": "gold-private"}), encoding="utf-8")
    rows = runner.offline_scores([{"task_slug": "fixed", "recommendation": "B", "source_first_proposal": {"action": {"kind": "select", "option": "A"}}}],
                                 [{"task_slug": "fixed", "source": "saved"}], {"fixed": tmp_path})
    evaluated = rows[0]["offline_evaluation"]
    assert evaluated["original_label_agreement_of_recommendation"] is True
    assert evaluated["actual_submission"] is False
    assert evaluated["end_to_end_success"] == "not_applicable_module_diagnostic"


def test_source_preparation_strips_hidden_fields_and_preserves_chart(tmp_path):
    source = tmp_path / "raw"
    split = source / "splits" / "official140"
    split.mkdir(parents=True)
    asset = source / "assets" / "official140" / "family" / "fixed"
    asset.mkdir(parents=True)
    (asset / "figure.png").write_bytes(b"original-image-bytes")
    raw = {"task_slug": "fixed", "chart_asset": {"figure_path": "original/figure.png"},
           "workflow_instruction": "Choose the matching visible route.", "action_space": [{"label": "A", "action_id": "correct_A"}],
           "expected_action_id": "correct_A", "ground_truth": {"private": "secret"},
           "primary_action": {"field_label": "Route"}, "companion_actions": []}
    (split / "family_tasks.jsonl").write_text(json.dumps(raw) + "\n", encoding="utf-8")
    case = {"task_slug": "fixed", "family": "family", "task_alias": "diag04"}
    result = runner.prepare_new_case(case, source, tmp_path / "data")
    public = (result / "public.json").read_text(encoding="utf-8")
    assert "expected_action_id" not in public and "correct_A" not in public and "secret" not in public
    assert (result / "chart.png").read_bytes() == b"original-image-bytes"
