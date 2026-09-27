import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from research.decision_evidence_audit import natural_prefix as np
from research.decision_evidence_audit.core import BudgetExceeded, public_task_projection
from research.decision_evidence_audit.models import RecordedModel
from research.decision_evidence_audit.tests.test_core import task_fixture


class NaturalPrefixTests(unittest.TestCase):
    def test_prepare_four_public_only_pairs_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            np.prepare(root)
            summary = np.read(root / "execution_summary.json")
            self.assertEqual(len(summary["rows"]), 4)
            self.assertEqual(summary["real_model_status"], "not_run")
            self.assertEqual(summary["total_charged_model_events"], 0)
            self.assertEqual(np.read(root / "run_manifest.json")["strategy"], "B0")
            for task in np.TASKS:
                a, b = [np.unit_directory(root, task, condition) for condition in ("official140", "clean140")]
                self.assertEqual(np.read(a / "public_task.json"), np.read(b / "public_task.json"))
                for directory in (a, b):
                    relative = str(directory.relative_to(root))
                    self.assertNotIn(task, relative)
                    self.assertNotIn("official140", relative)
                    self.assertNotIn("clean140", relative)
            with self.assertRaises(FileExistsError):
                np.prepare(root)

    def test_hidden_labels_do_not_change_prefix_input_or_mock_choice(self):
        from research.decision_evidence_audit.runner import prefix_prompt
        raw = task_fixture()
        changed = copy.deepcopy(raw)
        changed["ground_truth"] = {"different": True}
        changed["expected_action_id"] = "route_a"
        changed["action_space"].reverse()
        p1 = public_task_projection(raw, task_alias="n01")
        p2 = public_task_projection(changed, task_alias="n01")
        self.assertEqual(p1, p2)
        state = {"url_path": "/task/n01/form", "selects": []}
        self.assertEqual(prefix_prompt(p1["user_goal"], state), prefix_prompt(p2["user_goal"], state))

    def test_budget_persists_scope_and_charges_failed_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = np.RunLedger(max_model_calls=40, max_browser_transitions=160)
            ledger.bind_snapshot(root / "budget.json")
            ledger.scope, ledger.unit_id = "live", "test"
            backend = MagicMock()
            backend.complete.side_effect = RuntimeError("injected transport failure")
            model = RecordedModel(backend, ledger=ledger)
            with self.assertRaises(RuntimeError):
                model.call(phase="prefix", system_prompt="test", user_prompt="test",
                    image_path=root / "not_needed.png", image_artifact="test.png", public_context={},
                    request_dir=root / "requests", response_dir=root / "responses")
            self.assertEqual(ledger.model_calls, 1)
            self.assertFalse(np.read(root / "responses/request_0001.json")["ok"])
            for _ in range(39):
                ledger.charge_model(phase="test", request_id="budget-test")
            with self.assertRaises(BudgetExceeded):
                ledger.charge_model(phase="test", request_id="over-budget")
            for _ in range(160):
                ledger.charge_transition(phase="attempt", action={"action": "click_link"})
            with self.assertRaises(BudgetExceeded):
                ledger.charge_transition(phase="attempt", action={"action": "click_link"})
            saved = np.read(root / "budget.json")
            self.assertEqual((saved["model_calls"], saved["browser_transitions"]), (40, 160))
            self.assertTrue(all(e["scope"] == "live" and e["unit_id"] == "test" for e in saved["events"]))

    def test_unavailable_service_retains_four_not_run_without_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            np.prepare(root)
            with patch.object(np, "LocalQwenServiceBackend", side_effect=ConnectionError("offline")), patch.object(np, "require_playwright") as browser:
                self.assertFalse(np.live(root, "http://127.0.0.1:8045"))
            browser.assert_not_called()
            result = np.read(root / "execution_summary.json")
            self.assertEqual(len(result["rows"]), 4)
            self.assertTrue(all(r["status"] == "not_run" for r in result["rows"]))
            self.assertEqual(result["total_charged_model_events"], 0)
            self.assertEqual(result["browser_transitions"], 0)
            self.assertFalse((root / "live_attempt.json").exists())
            self.assertTrue((root / "service_checks/check_001.json").is_file())

    def test_online_episode_only_replays_b0_and_keeps_proposal(self):
        checkpoint = SimpleNamespace(current_selection="Route A", pending_proposal={"action": "click_button", "text": "Submit Form"})
        shell = MagicMock()
        shell.__enter__.return_value.base_url = "http://127.0.0.1:1"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(np, "managed_shell", return_value=shell), patch.object(np, "generate_checkpoint", return_value=(checkpoint, {"errors": []})) as prefix, patch.object(np, "replay_and_run_unit", return_value=({"status": "submitted"}, {})) as replay:
                result = np.online_episode(browser=object(), public={"task_alias": "n01", "user_goal": "Use the chart"}, chart=root / "chart.png", root=root, directory=root / "unit", model=object(), ledger=object())
            self.assertEqual(prefix.call_args.kwargs["max_model_calls"], 8)
            self.assertEqual(replay.call_args.kwargs["strategy"], "B0")
            self.assertIs(replay.call_args.kwargs["checkpoint"], checkpoint)
            self.assertEqual(result["pending_proposal"], checkpoint.pending_proposal)
            self.assertEqual(result["checkpoint_selection"], "Route A")

    def test_browser_start_failure_retains_denominator_and_refuses_rerun(self):
        backend = SimpleNamespace(health={"model_path": np.MODEL_PATH, "max_pixels": 1003520}, metadata={"test_only": True})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            np.prepare(root)
            with patch.object(np, "LocalQwenServiceBackend", return_value=backend), patch.object(np, "require_playwright", side_effect=RuntimeError("injected browser failure")):
                self.assertFalse(np.live(root, "http://127.0.0.1:8045"))
                with self.assertRaises(FileExistsError):
                    np.live(root, "http://127.0.0.1:8045")
            summary = np.read(root / "execution_summary.json")
            self.assertEqual(len(summary["rows"]), 4)
            self.assertTrue(all(r["status"] == "not_run" for r in summary["rows"]))
            self.assertEqual(summary["real_model_calls"], 0)
            self.assertEqual(np.read(root / "live_attempt.json")["status"], "infrastructure_failed")


if __name__ == "__main__":
    unittest.main()
