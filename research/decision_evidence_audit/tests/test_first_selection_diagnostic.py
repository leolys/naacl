import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research.decision_evidence_audit import first_selection_diagnostic as fs
from research.decision_evidence_audit.core import BudgetExceeded, BudgetLedger, assert_online_payload
from research.decision_evidence_audit.models import RecordedModel


class FirstSelectionTests(unittest.TestCase):
    def test_uniform_first_selection_and_history_cutoff(self):
        for i in range(1, 5):
            d = fs.OLD / "units" / f"episode_{i:02d}"
            s = fs.first_selection_source(d)
            self.assertEqual(s["source_first_selection_local_call"], 3)
            self.assertEqual(s["source_after_local_call"], 4)
            self.assertEqual(len(s["actions"]), 3)
            self.assertEqual(len(s["history"]), 4)
            self.assertEqual(s["history"][-1]["result_state"], s["state"])
            self.assertEqual(s["actions"][-1]["option_text"], fs.current_selection(s["state"]))
            self.assertFalse(any(a.get("text") == "Submit Form" for a in s["actions"]))

    def test_h0_exact_and_h1_only_appends_observed_history(self):
        d = fs.OLD / "units/episode_01"
        s, p = fs.first_selection_source(d), fs.read(d / "public_task.json")
        original = fs.prefix_prompt(p["user_goal"], s["state"])
        self.assertEqual(fs.actor_prompt(p["user_goal"], s["state"], s["history"], "H0"), original)
        h1 = fs.actor_prompt(p["user_goal"], s["state"], s["history"], "H1")
        self.assertEqual(h1[0], original[0])
        self.assertTrue(h1[1].startswith(original[1] + fs.HISTORY_INTRO))
        self.assertNotIn("correct", fs.json.dumps(s["history"]).lower())
        assert_online_payload({"executed_history": s["history"]})

    def test_v_only_goal_options_and_advice_does_not_change_action(self):
        d = fs.OLD / "units/episode_01"
        s, p = fs.first_selection_source(d), fs.read(d / "public_task.json")
        before = copy.deepcopy(s)
        system, user = fs.verification_prompt(p["user_goal"], p["option_labels"])
        self.assertNotIn("selected_text", user)
        self.assertNotIn("executed_history", user)
        advice = {"raw_response": '{"option_label":"Select \'Decreased\'","reason":"test"}',
                  "parsed_option_label": "Select 'Decreased'", "parse_status": "valid"}
        out = fs.actor_prompt(p["user_goal"], s["state"], s["history"], "H1+V", advice)
        self.assertIn("not authoritative", out[1])
        raw = '{"action":"select_option","select_name":"Q4 Traffic Status","option_text":"Select \'Increased\'"}'
        self.assertEqual(fs._extract_action(raw)["option_text"], "Select 'Increased'")
        self.assertEqual(s, before)

    def test_verification_consumes_one_of_six_and_failed_calls_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            ledger = BudgetLedger(max_model_calls=80, max_browser_transitions=240)
            ledger.bind_snapshot(d / "budget.json")
            local = fs.UnitLedger(ledger)
            backend = Mock()
            backend.complete.side_effect = RuntimeError("mock transport failure")
            model = RecordedModel(backend, ledger=local)
            for i in range(6):
                with self.assertRaises(RuntimeError):
                    model.call(phase="verification" if i == 0 else "actor", system_prompt="test",
                        user_prompt="test", image_path=d / "unused.png", image_artifact="unused.png",
                        public_context={}, request_dir=d / "requests", response_dir=d / "responses")
            with self.assertRaises(BudgetExceeded):
                local.charge_model(phase="actor", request_id="over")
            self.assertEqual(local.calls, 6)
            self.assertEqual(backend.complete.call_count, 6)
            for i in range(18):
                local.charge_transition(phase="retry", action={"action": "click_link"})
            with self.assertRaises(BudgetExceeded):
                local.charge_transition(phase="retry", action={"action": "click_link"})

    def test_submit_predicate_uses_original_visible_controls(self):
        s = fs.first_selection_source(fs.OLD / "units/episode_01")["state"]
        self.assertTrue(fs.is_submit_proposal({"action": "click_button", "text": "Submit Form"}, s))
        self.assertFalse(fs.is_submit_proposal({"action": "select_option", "option_text": "Select 'Decreased'"}, s))

    def test_old_input_groups_and_initial_unselected_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            fs.compare_old_inputs(d)
            report = fs.read(d / "OLD_INPUT_COMPARISON.json")
            for pair in report["pairs"]:
                if pair["group"] != [3, 5]:
                    self.assertTrue(pair["user_equal"])
                    self.assertTrue(pair["image_pixels_equal"])
                    self.assertTrue(pair["service_payload_except_path_equal"])
                else:
                    self.assertFalse(pair["user_equal"])
                    self.assertFalse(pair["image_pixels_equal"])
            self.assertTrue(all(x["consistent"] for x in report["selected_flags"]))


if __name__ == "__main__":
    unittest.main()
