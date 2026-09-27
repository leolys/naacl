"""Offline function substitutes only: no HTTP, GPU, or browser model experiment."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.decision_evidence_audit.core import BudgetExceeded
from research.decision_evidence_audit.models import ModelReply
from research.decision_evidence_audit.frozen_panel import (
    PANEL, PanelLedger, ProjectedModel, fixture_checkpoint, initialize, open_ledger,
    read, reference_policy, submit_decision, close_page_preserving_result, summarize, run_live,
)


class Substitute:
    metadata = {"kind": "offline_function_substitute", "real_inference": False}

    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return ModelReply(value)


class FrozenPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.payloads = read(PANEL / "panel_online_requests.json")
        self.states = {s["state_id"]: s for s in read(PANEL / "control_panel.json")["states"]}

    def tearDown(self):
        self.temp.cleanup()

    def run_substitute(self, entry, replies, *, initial=None, tag="test"):
        initial = initial or self.states[entry["state_id"]]["initial_selection"]
        backend = Substitute(replies)
        ledger = PanelLedger(max_model_calls=3, max_browser_transitions=0)
        ledger.bind_snapshot(self.root / tag / "budget.json")
        model = ProjectedModel(backend, ledger=ledger, payload=entry["model_payload"],
                               events_path=self.root / tag / "model_events.jsonl")
        cp = fixture_checkpoint(entry["model_payload"], initial)
        result = reference_policy().run_policy("B3", cp, model=model, artifact_root=PANEL,
                                               unit_dir=self.root / tag / "policy")
        return result, backend, ledger

    def test_all_24_first_requests_exact_and_reason_does_not_override_label(self):
        for entry in self.payloads:
            with self.subTest(unit=entry["unit_id"]):
                result, backend, ledger = self.run_substitute(entry, [
                    '{"option_label":"Route A","reason":"The correct choice should be Route B."}'
                ], tag=entry["unit_id"])
                self.assertEqual(result.recommended_option, "Route A")
                self.assertEqual(result.changed, result.original_selection != "Route A")
                logged = backend.requests[0].log_payload()
                actual = {key: logged[key] for key in entry["model_payload"]}
                self.assertEqual(actual, entry["model_payload"])
                self.assertEqual(ledger.model_calls, 1)

    def test_hidden_initial_choice_cannot_leak_on_any_round(self):
        hidden = [u for u in self.payloads if u["mode"] == "independent_hidden_selection"]
        responses = [
            '{"observe":{"screenshot_id":"dashboard","region":[0,0,512,384]}}',
            '{"observe":{"screenshot_id":"current","region":[20,60,490,350]}}',
            '{"option_label":"Route A","reason":"independent result"}',
        ]
        runs = []
        for number, initial in enumerate(("Route A", "Route B")):
            result, backend, ledger = self.run_substitute(hidden[0], responses, initial=initial, tag=f"h{number}")
            self.assertEqual(result.active_observations, 2)
            self.assertEqual(result.changed, initial != "Route A")
            for request in backend.requests:
                self.assertEqual(request.public_context["current_selection"], "")
                self.assertEqual(request.public_context["visible_action_prefix"], [])
            runs.append([{k: v for k, v in r.log_payload().items() if k != "request_id"} for r in backend.requests])
        self.assertEqual(runs[0], runs[1])

    def test_text_fact_and_dynamic_feedback_persist(self):
        entry = next(u for u in self.payloads if u["mode"] == "B3_with_text_color_fact")
        result, backend, ledger = self.run_substitute(entry, [
            '{"action":"click_button","text":"Submit Form"}',
            '{"observe":{"screenshot_id":"missing","region":[0,0,10,10]}}',
            '{"option_label":"Route B"}',
        ])
        self.assertEqual(ledger.model_calls, 3)
        self.assertEqual(result.active_observations, 1)
        self.assertEqual(result.verification_metrics["tool_errors"], 1)
        for req in backend.requests:
            self.assertEqual(req.public_context["diagnostic_color_fact"], "The large dashboard rectangle is magenta.")
        self.assertIn("invalid_output", backend.requests[1].user_prompt)
        self.assertIn("Crop unavailable", backend.requests[2].user_prompt)

    def test_invalid_limit_keeps_real_initial_not_empty_or_reason(self):
        entry = next(u for u in self.payloads if u["mode"] == "independent_hidden_selection")
        result, backend, ledger = self.run_substitute(entry, [
            '{"decision":{"option_label":"Route A"}}',
            '{"option_label":"not a visible label","reason":"Route A"}',
            '{"observe":{"screenshot_id":"current","region":[0,0,100,100]}}',
        ], initial="Route B")
        self.assertEqual(result.recommended_option, "Route B")
        self.assertFalse(result.changed)
        self.assertNotEqual(result.parse_status, "valid")
        self.assertEqual(result.active_observations, 0)
        self.assertEqual(ledger.model_calls, 3)

    def test_interface_drift_prevents_backend_call(self):
        entry = copy.deepcopy(self.payloads[0])
        entry["model_payload"]["system_prompt"] += " changed"
        with self.assertRaisesRegex(ValueError, "first request differs"):
            self.run_substitute(entry, ['{"option_label":"Route A"}'])
        self.assertEqual(read(self.root / "test/budget.json")["model_calls"], 0)

    def test_exception_charged_and_raw_error_persisted(self):
        with self.assertRaisesRegex(RuntimeError, "transport failed"):
            self.run_substitute(self.payloads[0], [RuntimeError("transport failed")])
        ledger = read(self.root / "test/budget.json")
        self.assertEqual(ledger["model_calls"], 1)
        self.assertIn("timestamp", ledger["events"][0])
        response = read(self.root / "test/policy/responses/request_0001.json")
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"], "transport failed")

    def test_budget_survives_reload_and_counts_failed_actions(self):
        run = self.root / "run"
        initialize(run)
        ledger = open_ledger(run)
        ledger.unit_id = "failure_case"
        ledger.charge_transition(phase="test_failure", action={"action": "goto"})
        restored = open_ledger(run)
        self.assertEqual(restored.browser_transitions, 1)
        restored.model_calls = 80
        with self.assertRaises(BudgetExceeded):
            restored.charge_model(phase="extra", request_id="rejected")
        self.assertEqual(len(list((run / "units").glob("*/result.json"))), 24)
        with self.assertRaises(FileExistsError):
            initialize(run)

    def test_same_choice_submits_and_ack_loss_is_not_retried(self):
        # Pure executor/page substitutes; real POST checks run via browser-controls.
        class Page:
            url = "/task/control/confirmation"
            def get_by_role(self, *args, **kwargs):
                return self
            def count(self):
                return 1
            def screenshot(self, **kwargs):
                pass
        class Executor:
            page = Page()
            receipts = []
        post = self.root / "post.jsonl"
        calls = []
        def lost_ack(executor, root, *, phase, action):
            calls.append(action)
            post.write_text(json.dumps({"selected_option_label": "Route B"}) + "\n")
            raise RuntimeError("ack lost after POST")
        with patch("research.decision_evidence_audit.frozen_panel.capture_state", return_value={}), \
             patch("research.decision_evidence_audit.frozen_panel.current_selection", return_value="Route B"), \
             patch("research.decision_evidence_audit.frozen_panel.logged_action", side_effect=lost_ack):
            result = submit_decision(Executor(), "Route B", "Route B", self.root, post)
        self.assertEqual(calls, [{"action": "click_button", "text": "Submit Form"}])
        self.assertEqual(result["receipt_count"], 1)
        self.assertEqual(result["status"], "execution_incomplete")
        self.assertIn("ack lost", result["submit_error"])

    def test_cleanup_error_does_not_erase_committed_result(self):
        class Page:
            def close(self):
                raise RuntimeError("cleanup failed")
        result = {"status": "submitted", "receipt": {"selected_option_label": "Route B"}}
        close_page_preserving_result(Page(), result)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["receipt"]["selected_option_label"], "Route B")
        self.assertIn("cleanup failed", result["page_cleanup_error"])

    def test_summary_retains_unrun_24_in_frozen_execution_order(self):
        run = self.root / "run"
        initialize(run)
        summarize(run)
        result = read(run / "summary.json")
        self.assertEqual(result["not_run_units"], 24)
        self.assertEqual(result["submitted_units"], 0)
        self.assertEqual(result["units_with_model_calls"], 0)
        self.assertTrue(all(r["valid_decision_correct"] is None for r in result["rows"]))
        self.assertEqual([r["state_id"] for r in result["rows"]][::3],
                         read(PANEL / "control_panel.json")["execution_state_order"])

    def test_global_backend_failure_persists_cause_without_model_calls(self):
        run = self.root / "run"
        initialize(run)
        with patch("research.decision_evidence_audit.frozen_panel.LocalQwenServiceBackend",
                   side_effect=RuntimeError("offline injected health failure")):
            self.assertFalse(run_live(run, "http://127.0.0.1:8045"))
        outcome = read(run / "live_attempt.json")
        self.assertEqual(outcome["status"], "infrastructure_failed")
        self.assertIn("finished_at", outcome)
        self.assertEqual(read(run / "budget.json")["model_calls"], 0)
        for path in (run / "units").glob("*/result.json"):
            self.assertEqual(read(path)["not_run_reason"], "offline injected health failure")
        with self.assertRaises(FileExistsError):
            run_live(run, "http://127.0.0.1:8045")

    def test_input_archive_matches_frozen_materials(self):
        run = self.root / "run"
        initialize(run)
        for name in ("control_panel.json", "panel_online_requests.json", "B3_REFERENCE.py",
                     "EXPERIMENT_PLAN.md", "CONTROL_FREEZE.md", "panel_images/image_01.png",
                     "panel_images/image_02.png", "panel_images/image_03.png", "panel_images/image_04.png"):
            self.assertEqual((run / "frozen_inputs" / name).read_bytes(), (PANEL / name).read_bytes())

    def test_source_snapshot_failure_retains_global_status_and_all_units(self):
        run = self.root / "run"
        initialize(run)
        with patch("research.decision_evidence_audit.frozen_panel.snapshot_sources",
                   side_effect=OSError("offline injected snapshot failure")):
            self.assertFalse(run_live(run, "http://127.0.0.1:8045"))
        self.assertEqual(read(run / "live_attempt.json")["error_type"], "OSError")
        self.assertEqual(read(run / "summary.json")["not_run_units"], 24)

    def test_attempt_without_response_is_not_classified_as_not_run(self):
        run = self.root / "run"
        initialize(run)
        path = run / "units/unit_01/result.json"
        result = read(path)
        result.update(status="failed", model_calls=1, error="transport failed")
        path.write_text(json.dumps(result))
        summarize(run)
        first = read(run / "summary.json")["rows"][0]
        self.assertEqual(first["attribution"], "attempted_no_raw_response")
        self.assertIsNone(first["valid_decision_correct"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
