import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from audit import read
from diagnostic import (SelectionObservation, SelectionPolicyModel, actor_prompt,
                        public_history, execute_normal, offline_labels, continue_actor)
from runtime import load_runtime


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/decision_evidence_audit/runs/clear_rule_live_20260907T0222Z"
RT = load_runtime(SOURCE)
REQUEST = read(SOURCE / "online/prefixes/prefix_0001/requests/request_0005.json")


class DiagnosticTests(unittest.TestCase):
    def test_reference_runtime_really_loaded(self):
        self.assertTrue(Path(RT.runner.__file__).is_relative_to(SOURCE / "evaluator/runtime_source_snapshot"))

    def test_h0_is_exact_legacy_request(self):
        c = REQUEST["public_context"]
        s, u, ctx = actor_prompt(RT, c["user_goal"], c["state"], "H0", [{"action": {"action": "finish"}}])
        self.assertEqual((s, u), (REQUEST["system_prompt"], REQUEST["user_prompt"]))
        self.assertEqual(ctx, c)

    def test_h1_only_adds_four_actual_receipts_and_updates(self):
        receipts = [{"action": {"action": "select_option", "option_text": f"Route {i}"},
                     "executed": i != 5, "error": "public failure" if i == 5 else "", "attempt": 1,
                     "phase": "offline label must not pass"} for i in range(6)]
        c = REQUEST["public_context"]
        s, u, ctx = actor_prompt(RT, c["user_goal"], c["state"], "H1", receipts)
        self.assertEqual(s, REQUEST["system_prompt"])
        self.assertTrue(u.startswith(REQUEST["user_prompt"] + "\n\n"))
        self.assertEqual(len(ctx["recent_executed_actions_and_public_receipts"]), 4)
        self.assertEqual(ctx["recent_executed_actions_and_public_receipts"][0]["action"]["option_text"], "Route 2")
        self.assertFalse(ctx["recent_executed_actions_and_public_receipts"][-1]["executed"])
        self.assertNotIn("offline label", u)

    def test_after_selection_has_no_pending_submit(self):
        obs = SelectionObservation("goal", [], "A", {}, "a.png", [], [], [])
        self.assertFalse(hasattr(obs, "pending_proposal"))
        self.assertFalse(hasattr(obs, "checkpoint_version"))

    def test_policy_adapter_is_explicit_about_trigger(self):
        class Capture:
            def call(self, **kwargs):
                self.kwargs = kwargs
                return "captured"
        cap = Capture()
        model = SelectionPolicyModel(cap, [{"action": {"action": "select_option", "option_text": "A"}, "executed": True}])
        context = {"verification_phase": "pre_submit_check"}
        model.call(phase="b3_plan", system_prompt="pre-submit VISUAL VERIFIER. The proposed submission has NOT been executed. Check the pending decision. The executor, not this response, handles submission after verification.",
                   user_prompt=json.dumps(context), public_context=context)
        self.assertIn("NO pending submission proposal", cap.kwargs["system_prompt"])
        self.assertNotIn("pre_submit_check", cap.kwargs["user_prompt"])
        self.assertIn("recent_executed_actions_and_public_receipts", cap.kwargs["user_prompt"])

    def test_independent_a2_not_given_selection_or_history(self):
        class Capture:
            def call(self, **kwargs):
                self.kwargs = kwargs
        cap = Capture()
        SelectionPolicyModel(cap, [{"action": {"option_text": "SECRET_CURRENT"}}]).call(
            phase="b2_decision", system_prompt="checking a pending browser decision", user_prompt="goal", public_context={"user_goal": "goal"})
        self.assertNotIn("SECRET_CURRENT", json.dumps(cap.kwargs))
        self.assertNotIn("pending", cap.kwargs["system_prompt"])

    def test_common_executor_allows_change_back_and_no_auto_submit(self):
        class Executor:
            def __init__(self):
                self.actions = []
            def execute(self, action, **kwargs):
                self.actions.append((action, kwargs))
                return {"action": action, "executed": True}
        executor = Executor()
        for label in ("Route B", "Route A"):
            execute_normal(executor, {"action": "select_option", "option_text": label}, phase="test")
        self.assertEqual([a[0]["action"] for a in executor.actions], ["select_option"] * 2)

    def test_hidden_scores_do_not_change_public_prompt(self):
        raw = RT.runner.find_task(RT.runner.task_spec_path("official140", "pub010"), "pub010")
        changed = copy.deepcopy(raw)
        changed["expected_action_id"] = "different offline gold"
        changed["ground_truth"] = {"anything": "different"}
        self.assertEqual(RT.core.public_task_projection(raw, task_alias="dev01"),
                         RT.core.public_task_projection(changed, task_alias="dev01"))

    def test_actor_selection_at_call_limit_never_auto_submits(self):
        state = copy.deepcopy(REQUEST["public_context"]["state"])
        class Model:
            ledger = RT.core.BudgetLedger()
            def call(self, **kwargs):
                self.ledger.charge_model(phase="unit_mock", request_id="unit")
                return RT.models.ModelReply(json.dumps(dict(action="select_option", select_name="primary_action",
                    option_text="Select growth-planning option")), {"request_id": "unit"})
        class Executor:
            def __init__(self):
                self.receipts = []
            def execute(self, action, **kwargs):
                receipt = dict(action=action, executed=True, error="", attempt=1,
                               before_url_path=state["url_path"], after_url_path=state["url_path"])
                self.receipts.append(receipt)
                state["selects"][0]["selected_text"] = action["option_text"]
                for option in state["selects"][0]["options"]:
                    option["selected"] = option["text"] == action["option_text"]
                return receipt
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def capture(*args):
                return copy.deepcopy(state), directory / "unit.png"
            executor = Executor()
            with patch("diagnostic.snapshot", side_effect=capture):
                result = continue_actor(RT, object(), executor, Model(), REQUEST["public_context"]["user_goal"],
                    "dev01", directory, directory / "receipts.jsonl", "H1", [], 1)
            self.assertEqual(result["status"], "actor_call_limit")
            self.assertFalse(result["checkpoint_reached"])
            self.assertFalse(result["submitted"])
            self.assertFalse((directory / "before_submit_checkpoint.json").exists())
            self.assertEqual([x["action"]["action"] for x in executor.receipts], ["select_option"])


if __name__ == "__main__":
    unittest.main()
