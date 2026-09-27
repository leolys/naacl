"""Offline protocol tests; fake network clients only, never real inference."""
import copy
import json
from pathlib import Path

import pytest

import panel_core as core
import run_panel as runner


def config():
    return core.read(core.HERE / "config.json")


def public():
    return {"task_alias": "neutral", "user_goal": "Choose from this chart.",
            "option_labels": ["A", "B"], "primary_field_label": "Choice"}


def record():
    return {"task_slug": "test", "public_task": public(), "chart_file": "not-read-here.png",
            "status": {p: "not_run" for p in core.PHASES}, "stages": {}, "proposal": None,
            "generated": None, "normalized": None, "verification": None, "rule_state": [],
            "translations": {"items": {}}, "error": None}


def test_shared_prompts_unchanged_and_no_private_context():
    rec = record()
    rec["offline_metadata"] = {"gold": "private"}
    rec["proposal"] = {"action": {"kind": "select", "option": "A"}}
    prompt, context, images = runner.phase_input("generation", rec)
    assert prompt == core.GENERATOR
    assert "private" not in json.dumps(context)
    assert context["history"] == [] and context["state"]["current_selection"] == ""
    assert images == [("chart_1", "not-read-here.png")]


def test_translation_is_text_only_and_exact_keys():
    rec = record()
    rec["generated"] = {"rules": [{"id": "r1", "text": "An estimate is 1.3."}], "chains": []}
    rec["offline_metadata"] = {"gold": "SECRET"}
    prompt, context, images = runner.phase_input("translation", rec)
    assert images == [] and "SECRET" not in json.dumps(context)
    assert "not a chart analyst" in prompt
    translated = {"items": {row["key"]: "译文 " + row["text"] for row in context["items"]}}
    assert core.validate_translation(context["items"], translated) == []
    with pytest.raises(ValueError):
        core.validate_translation(context["items"], {"items": {}})
    warnings = core.validate_translation([{"key": "one", "text": "1.3"}], {"items": {"one": "一个不同数字"}})
    assert warnings[0]["type"] == "numeric_literal_missing"


def test_service_quota_stops_on_first_attempt(tmp_path):
    class Reply:
        status_code = 400
        def json(self):
            return {"error": {"type": "budget_exceeded", "message": "quota", "user_email": "private@example.invalid"}}
    class FakeSession:
        def __init__(self):
            self.proxies, self.calls = {}, 0
        def post(self, *args, **kwargs):
            self.calls += 1
            return Reply()
    settings = config()
    budget = core.PersistentBudget(tmp_path / "budget.json", settings)
    session = FakeSession()
    api = core.PanelAPI(settings, budget, session)
    with pytest.raises(core.ServiceStop, match="server_quota_exceeded"):
        api.call(tmp_path / "call", "fixed", "proposal", core.PROPOSAL_PROMPT, {"task": public()}, [])
    assert session.calls == 1 and budget.value["request_attempts"] == 1
    wire = core.read(tmp_path / "call" / "request.json")
    assert "Authorization" not in json.dumps(wire) and "private@example" not in json.dumps(wire)
    assert core.service_category(429, {"error": {"type": "insufficient_quota"}}) == "server_quota_exceeded"


def test_bounded_transport_retry_retains_all_attempts(tmp_path, monkeypatch):
    class Reply:
        def __init__(self, code):
            self.status_code = code
        def json(self):
            if self.status_code == 503:
                return {"error": {"message": "temporarily unavailable"}}
            return {"model": "reported", "usage": {"total_tokens": 4}, "choices": [
                {"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
    class FakeSession:
        proxies = {}
        calls = 0
        def post(self, *args, **kwargs):
            self.calls += 1
            return Reply(503 if self.calls == 1 else 200)
    monkeypatch.setattr(core.time, "sleep", lambda *args: None)
    budget = core.PersistentBudget(tmp_path / "budget.json", config())
    api = core.PanelAPI(config(), budget, FakeSession())
    assert api.call(tmp_path / "round", "test", "proposal", "test", {}, []) == {"ok": True}
    assert len(list((tmp_path / "round").glob("attempt_*.json"))) == 2
    assert budget.value["request_attempts"] == 2


def test_completed_phase_is_never_recalled(tmp_path):
    class NoCalls:
        def call(self, *args, **kwargs):
            raise AssertionError("completed stage must not be resampled")
    rec = record()
    rec["status"]["proposal"] = "completed"
    runner.execute_phase(rec, "proposal", tmp_path, NoCalls(), config())


def test_ambiguous_read_timeout_is_not_resent(tmp_path):
    class TimeoutSession:
        proxies = {}
        calls = 0
        def post(self, *args, **kwargs):
            self.calls += 1
            raise core.requests.ReadTimeout("request already sent; no response")
    session = TimeoutSession()
    budget = core.PersistentBudget(tmp_path / "budget.json", config())
    api = core.PanelAPI(config(), budget, session)
    rec = record()
    rec["chart_file"] = str(core.HERE / core.read(core.HERE / "catalog.json")["tasks"][0]["chart_file"])
    runner.execute_phase(rec, "proposal", tmp_path / "case", api, config())
    assert session.calls == 1 and budget.value["request_attempts"] == 1
    assert rec["status"]["proposal"] == "failed"
    assert rec["error"] == "request_outcome_unknown_no_auto_retry"
    runner.execute_phase(rec, "proposal", tmp_path / "case", api, config(), retry_service=True)
    assert session.calls == 1


def test_uncertain_interruption_is_not_automatically_resent(tmp_path):
    class NoCalls:
        def call(self, *args, **kwargs):
            raise AssertionError("unknown execution must not be retried")
    rec = record()
    rec["status"]["proposal"] = "running"
    rec["stages"]["proposal"] = {"folder": "proposal/round_001"}
    runner.execute_phase(rec, "proposal", tmp_path, NoCalls(), config())
    assert rec["status"]["proposal"] == "failed"
    assert rec["error"] == "interrupted_execution_outcome_unknown"


def test_generated_wrong_structure_not_counted_as_completed(tmp_path):
    class FakeAPI:
        def call(self, folder, *args):
            Path(folder).mkdir(parents=True)
            return {"rules": [], "chains": []}
    rec = record()
    rec["proposal"] = {"action": {"kind": "select", "option": "A"}}
    runner.execute_phase(rec, "generation", tmp_path, FakeAPI(), config())
    assert rec["status"]["generation"] == "invalid"
    assert rec["generated"] is None and rec["generation_invalid_raw"] == {"rules": [], "chains": []}


def test_real140_queue_global_quota_no_followon_dispatch(tmp_path):
    class QuotaAPI:
        calls = 0
        def __init__(self, settings, budget):
            self.budget = budget
        def call(self, folder, task_id, phase, *args):
            self.__class__.calls += 1
            Path(folder).mkdir(parents=True)
            self.budget.charge({"task_slug": task_id, "phase": phase, "attempt": 1})
            raise core.ServiceStop("server_quota_exceeded")
    output = tmp_path / "mock_run"
    summary = runner.run(output, core.HERE, config(), api_factory=QuotaAPI)
    assert QuotaAPI.calls == 1 and summary["request_attempts"] == 1
    assert summary["total_tasks"] == 140 and summary["generated"] == 0
    assert summary["phase_status_counts"]["proposal"] == {"blocked": 1, "not_run": 139}
    with pytest.raises(core.ServiceStop):
        runner.run(output, core.HERE, config(), resume=True, api_factory=QuotaAPI)
    assert QuotaAPI.calls == 1


def test_proposal_does_not_forge_submit_or_execute():
    rec = record()
    with pytest.raises(ValueError):
        core.validate_stage("proposal", {"action": {"kind": "submit"}}, rec, config())
    out = core.validate_stage("proposal", {"action": "select", "option": "A"}, rec, config())
    assert out["proposal"]["action"] == {"kind": "select", "option": "A"}
