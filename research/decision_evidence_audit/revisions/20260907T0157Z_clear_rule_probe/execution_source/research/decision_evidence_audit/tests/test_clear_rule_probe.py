"""Clear-rule development routing without changing the original stage-two scope."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research.decision_evidence_audit.core import public_task_projection
from research.decision_evidence_audit.runner import (
    build_parser,
    find_task,
    pair_invariant_differences,
    run_smoke,
    selected_task_slugs,
    task_spec_path,
)
from research.decision_evidence_audit.validate_run import validate_run


class ClearRuleProbeTests(unittest.TestCase):
    def test_default_scope_is_unchanged_and_probe_is_explicit(self):
        args = build_parser().parse_args([])
        self.assertEqual(selected_task_slugs(args), ("env001", "env025"))
        args.tasks = "pub010,env008,b035"
        with self.assertRaises(ValueError):
            selected_task_slugs(args)
        args.profile = "clear-rule-probe"
        self.assertEqual(selected_task_slugs(args), ("pub010", "env008", "b035"))
        for invalid in ("env001", "env008,env008", "pub010,env008,b035,pub020", ""):
            args.tasks = invalid
            with self.assertRaises(ValueError):
                selected_task_slugs(args)

    def test_released_pairs_and_hidden_mutations_do_not_change_public_inputs(self):
        for slug, family in (
            ("pub010", "public39_tasks.jsonl"),
            ("env008", "environment35_tasks.jsonl"),
            ("b035", "business47_tasks.jsonl"),
        ):
            with self.subTest(slug=slug):
                official_path = task_spec_path("official140", slug)
                self.assertEqual(official_path.name, family)
                official = find_task(official_path, slug)
                clean = find_task(task_spec_path("clean140", slug), slug)
                self.assertEqual(pair_invariant_differences(official, clean), [])
                public = public_task_projection(official, task_alias="dev01")
                self.assertEqual(public, public_task_projection(clean, task_alias="dev01"))
                mutated = copy.deepcopy(official)
                mutated["ground_truth"] = {"injected": "wrong answer"}
                mutated["expected_action_id"] = "not_an_option"
                mutated["misleading_action_ids"] = []
                mutated["misleader_type"] = "injected secret"
                mutated["primary_action"]["correct_action_id"] = "not_an_option"
                mutated["action_space"].reverse()
                for action in mutated["action_space"]:
                    action["action_id"] = "injected"
                    action["role"] = "injected"
                    action["scoring_outcome"] = "injected"
                self.assertEqual(public, public_task_projection(mutated, task_alias="dev01"))

    def test_resolver_rejects_unknown_family_and_condition(self):
        for condition, slug in (("other", "env008"), ("clean140", "pub010/../../x")):
            with self.assertRaises(ValueError):
                task_spec_path(condition, slug)

    def test_all_24_units_are_retained_if_no_browser_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = build_parser().parse_args([
                "--profile", "clear-rule-probe", "--tasks", "pub010,env008,b035",
                "--output-root", tmp, "--run-id", "injected_no_browser",
            ])
            with patch(
                "research.decision_evidence_audit.runner.require_playwright",
                side_effect=RuntimeError("injected browser startup failure"),
            ):
                run_root = run_smoke(args)
            manifest = json.loads((run_root / "run_manifest.json").read_text())
            validation = validate_run(run_root)
            self.assertEqual(manifest["configured_units"], 24)
            self.assertEqual(manifest["completed_units"], 24)
            self.assertEqual(manifest["checkpoint_count"], 0)
            self.assertEqual(manifest["budget"]["model_calls"], 0)
            self.assertEqual(manifest["budget"]["browser_transitions"], 0)
            self.assertFalse(manifest["case_level_inspection_allowed"])
            self.assertFalse(manifest["research_interpretation_allowed"])
            self.assertTrue(validation["valid"], validation["errors"])
            self.assertEqual(validation["counts"]["prefixes"], 6)


if __name__ == "__main__":
    unittest.main()
