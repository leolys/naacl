"""No model calls; validate isolation and honest real-submit accounting."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from adapter import BrowserTask, PUBLIC_KEYS, make_app, prepare_bundle, public_projection, score_summary


@pytest.fixture
def raw():
    return {
        "task_slug": "hidden_case", "workflow_instruction": "Choose Route A or Route B as appropriate, then submit.",
        "page_title": "Routing", "chart_reference": "Chart", "primary_action": {"field_label": "Route"},
        "action_space": [{"label": "Route B", "action_id": "incorrect_B"}, {"label": "Route A", "action_id": "correct_A"}],
        "expected_action_id": "correct_A", "misleading_action_ids": ["incorrect_B"],
        "completion_action": {"label": "Submit route"},
        "ground_truth": {"secret": "ANSWER_SECRET_839"},
        "companion_actions": [
            {"field_id": "context", "field_label": "Private context", "input_type": "hidden", "correct_value": "HIDDEN_SECRET_125", "required": True},
            {"field_id": "note", "field_label": "Reason", "input_type": "text", "correct_value": "TEXT_GOLD_SECRET_747", "required": True},
            {"field_id": "program", "field_label": "Program", "input_type": "readonly", "correct_value": "Public planning", "required": False},
        ],
    }


def test_projection_excludes_gold_and_hidden_context(raw):
    public = public_projection(raw, "case01")
    assert set(public) == PUBLIC_KEYS
    encoded = json.dumps(public)
    for forbidden in ("expected_action_id", "incorrect_B", "correct_A", "ANSWER_SECRET", "HIDDEN_SECRET", "TEXT_GOLD_SECRET", "correct_value"):
        assert forbidden not in encoded
    assert public["option_labels"] == ["Route A", "Route B"]
    assert public["companion_fields"][0]["field"] == "note"
    assert public["companion_fields"][1]["value"] == "Public planning"


def make_test_app(raw, tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"unchanged image")
    return make_app(public_projection(raw, "case01"), chart, tmp_path / "receipts.jsonl", {"context": "HIDDEN_SECRET_125"})


def test_html_and_chart_are_public_only(raw, tmp_path):
    app = make_test_app(raw, tmp_path)
    with app.test_client() as client:
        text = client.get("/task/case01/form").get_data(as_text=True)
        for forbidden in ("correct_A", "incorrect_B", "HIDDEN_SECRET", "TEXT_GOLD_SECRET", "ANSWER_SECRET", "expected_action_id"):
            assert forbidden not in text
        assert 'required' in text
        assert 'readonly' in text
        assert client.get("/task/case01/chart").data == b"unchanged image"
        assert client.get("/task/case01/offline/raw.json").status_code == 404


def test_server_refuses_missing_required_fields(raw, tmp_path):
    app = make_test_app(raw, tmp_path)
    with app.test_client() as client:
        response = client.post("/task/case01/submit", data={"primary_action": "option_0"})
        assert response.status_code == 400
        assert not app.config["RECEIPTS"]
        response = client.post("/task/case01/submit", data={"primary_action": "option_0", "note": "Visible evidence basis"}, follow_redirects=True)
        assert response.status_code == 200
        assert "Submission received" in response.get_data(as_text=True)
        assert len(app.config["RECEIPTS"]) == 1
        receipt = app.config["RECEIPTS"][0]
        assert receipt["selected_option_label"] == "Route A"
        assert "context" not in receipt["fields"]
        assert "HIDDEN_SECRET" not in json.dumps(receipt)


def test_server_does_not_filter_wrong_choices(raw, tmp_path):
    app = make_test_app(raw, tmp_path)
    with app.test_client() as client:
        response = client.post("/task/case01/submit", data={"primary_action": "option_1", "note": "Some evidence"})
        assert response.status_code == 302
        receipt = app.config["RECEIPTS"][0]
        receipt["confirmation_observed"] = True
        scored = score_summary(raw, receipt)
        assert scored["primary_outcome"] == "misleading_failure"
        assert scored["real_submission"]
        assert scored["official_full_end_to_end_score"] == "not_computed"


def test_no_submission_is_not_success(raw):
    assert score_summary(raw, None)["primary_outcome"] == "completion_failure"
    assert not score_summary(raw, {"selected_option_label": "Route A"})["real_submission"]


def test_actual_dataset_bundle_no_answer_fields(tmp_path):
    source = Path(__file__).resolve().parents[2] / ".aris" / "dataset_inventory_20260918" / "raw"
    if not source.exists():
        pytest.skip("Local original dataset snapshot unavailable")
    manifest = prepare_bundle(source, tmp_path / "data")
    assert len(manifest["tasks"]) == 6
    for entry in manifest["tasks"]:
        case = tmp_path / "data" / entry["directory"]
        public = json.loads((case / "public.json").read_text(encoding="utf-8"))
        assert set(public) == PUBLIC_KEYS
        assert "correct_value" not in json.dumps(public)
        assert hashlib.sha256((case / entry["chart_file"]).read_bytes()).hexdigest() == entry["chart_sha256"]
        original = json.loads((case / "offline" / "raw.json").read_text(encoding="utf-8"))
        assert original["workflow_instruction"] == public["user_goal"]


def test_public_allowlist_rejects_extra_gold(raw, tmp_path):
    public = public_projection(raw, "case01")
    public["expected_action_id"] = "correct_A"
    with pytest.raises(ValueError):
        make_app(public, tmp_path / "chart.png", tmp_path / "receipt.jsonl")


@pytest.mark.skipif(not os.environ.get("DEMO_BROWSER_EXECUTABLE"), reason="Explicit existing browser path is required")
def test_real_browser_selection_fill_validation_and_submission(tmp_path):
    source = Path(__file__).resolve().parents[2] / ".aris" / "dataset_inventory_20260918" / "raw"
    if not source.exists():
        pytest.skip("Local original dataset snapshot unavailable")
    prepare_bundle(source, tmp_path / "data")
    charged = []
    with BrowserTask(tmp_path / "data" / "case05", tmp_path / "browser",
                     os.environ["DEMO_BROWSER_EXECUTABLE"], ledger=charged.append) as task:
        initial = task.snapshot("test_initial")["state"]
        assert initial["current_selection"] == ""
        assert len(initial["options"]) == 3
        assert len(task.history) == 3
        label = task.public_task["option_labels"][0]
        selected = task.execute({"kind": "select", "option": label})
        assert selected["ok"] and not selected["submitted"]
        assert task.receipt is None
        assert task.state()["current_selection"] == label
        blocked = task.execute({"kind": "submit"})
        assert not blocked["ok"] and not blocked["submitted"]
        assert task.receipt is None
        filled = task.execute({"kind": "fill", "field": "followup_reason", "value": "Engineering smoke, not a model result."})
        assert filled["ok"]
        submitted = task.execute({"kind": "submit"})
        assert submitted["ok"] and submitted["submitted"]
        assert task.receipt["server_received"] and task.receipt["confirmation_observed"]
        assert task.receipt["selected_option_label"] == label
        assert all(task.receipt["navigation"].values())
        assert len(charged) == 7
