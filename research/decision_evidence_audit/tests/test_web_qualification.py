from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.decision_evidence_audit.core import BudgetExceeded, public_task_projection
from research.decision_evidence_audit.web_qualification import (
    CANDIDATES, CONDITIONS, QualificationLedger, option_exercise, prepare, read, run)
from research.decision_evidence_audit.tests.test_core import task_fixture


class WebQualificationTests(unittest.TestCase):
    def test_option_plan_is_public_only_and_exercises_every_label(self):
        raw = task_fixture()
        public = public_task_projection(raw, task_alias="q01")
        swapped = copy.deepcopy(raw)
        swapped["expected_action_id"] = "another_hidden_answer"
        swapped["ground_truth"] = {"different":True}
        swapped["action_space"].reverse()
        public2 = public_task_projection(swapped, task_alias="q01")
        self.assertEqual(public, public2)
        for index in range(7):
            plan = option_exercise(public,index)
            self.assertEqual(plan, option_exercise(public2,index))
            self.assertEqual(sorted(plan),sorted(public["option_labels"]))

    def test_budget_counts_failed_attempts_and_caps_per_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = QualificationLedger(max_model_calls=0,max_browser_transitions=112)
            ledger.bind_snapshot(Path(tmp)/"budget.json")
            ledger.unit_id = "example"
            for _ in range(8):
                ledger.charge_transition(phase="attempt",action={"action":"click_link","text":"missing"})
            with self.assertRaises(BudgetExceeded):
                ledger.charge_transition(phase="attempt",action={"action":"click_link"})
            with self.assertRaises(BudgetExceeded):
                ledger.charge_model(phase="forbidden",request_id="x")
            saved = read(Path(tmp)/"budget.json")
            self.assertEqual(saved["browser_transitions"],8)
            self.assertTrue(all(e["unit_id"]=="example" for e in saved["events"]))
            self.assertEqual(saved["model_calls"],0)

    def test_preparation_preserves_all_fourteen_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"new_run"
            prepare(root)
            self.assertEqual(len(list((root/"units").glob("*/result.json"))),14)
            self.assertEqual(read(root/"budget.json")["browser_transitions"],0)
            self.assertTrue(all(not p["nonchart_field_differences"] for p in read(root/"pair_field_checks.json")))
            for index,slug in enumerate(CANDIDATES):
                a,b = [root/"units"/f"{slug}_{c}" for c in CONDITIONS]
                self.assertEqual(read(a/"public_task.json"),read(b/"public_task.json"))
                self.assertEqual(read(a/"execution_plan.json"),read(b/"execution_plan.json"))
                for directory in (a,b):
                    source = read(directory/"evaluator/source.json")
                    task = read(directory/"evaluator/task_spec.json")
                    self.assertEqual(source["hidden_companions"], [c["field_id"] for c in task.get("companion_actions",[]) if c.get("input_type")=="hidden"])
            with self.assertRaises(FileExistsError):
                prepare(root)

    def test_browser_start_failure_retains_all_units_without_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"new_run"
            prepare(root)
            with patch("research.decision_evidence_audit.web_qualification.require_playwright",side_effect=RuntimeError("browser unavailable")):
                self.assertFalse(run(root))
            result = read(root/"execution_summary.json")
            self.assertEqual(result["submitted"],0)
            self.assertEqual(result["model_calls"],0)
            self.assertEqual(result["browser_transitions"],0)
            self.assertEqual(len(result["rows"]),14)
            self.assertTrue(all(r["reason"]=="browser unavailable" for r in result["rows"]))
            with self.assertRaises(FileExistsError):
                run(root)


if __name__ == "__main__":
    unittest.main()
