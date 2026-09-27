"""Offline projection/prompt tests. No model, API, browser, or SSH is invoked."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


strategies = load(ROOT / "search_strategies.py", "conclusion_search_strategies_test")
historical = load(ROOT.parent / "alternative_conclusion_20260926" / "prompts.py",
                  "historical_conclusion_prompt_test")


def candidate(cid="c1", option="Route A", claim="Choose A because PRIVATE_C_REASON."):
    return {"id": cid, "O": [{"location": "PRIVATE_O_LOCATION", "content": "PRIVATE_O_CONTENT"}],
            "B": {"rule": "PRIVATE_B_RULE", "conditions": ["PRIVATE_B_CONDITION"]},
            "C": {"claim": claim, "option_label": option},
            "notes": "PRIVATE_CHAIN_NOTES"}


def context():
    return {
        "goal": "Choose the appropriate public route.",
        "state": {"public_text": "Route A and Route B are available.",
                  "current_selection": "Route A"},
        "history": [{"action": "open_form", "receipt": {"executed": True}}],
        "options": ["Route A", "Route B"],
        "pending_proposal": {"action": "submit"},
        "initial_chains": [candidate()],
        "notes": "PRIVATE_INITIAL_NOTES",
        "verifier": {"verdict": "PRIVATE_OLD_VERDICT"},
        "evaluator": {"answer": "PRIVATE_EVALUATOR"},
    }


class ProjectionTests(unittest.TestCase):
    def test_v1_uses_historical_prompt_verbatim(self):
        result = strategies.make_strategy_request("V1", historical.QUESTIONS_NEW, context())
        self.assertEqual(result["system"], historical.QUESTIONS_NEW)
        self.assertIs(result["system"], historical.QUESTIONS_NEW)

    def test_v1_v2_identical_action_only_permissions(self):
        v1 = strategies.make_strategy_request("V1", historical.QUESTIONS_NEW, context())
        v2 = strategies.make_strategy_request("V2", historical.QUESTIONS_NEW, context())
        self.assertEqual(v1["context"], v2["context"])
        self.assertNotEqual(v1["system"], v2["system"])
        self.assertEqual(set(v1["context"]), set(strategies.PUBLIC_FIELDS) | {"existing_conclusions"})
        self.assertEqual(v1["context"]["existing_conclusions"], [{"option_label": "Route A"}])

    def test_no_original_ob_claim_ids_counts_or_notes_transmitted(self):
        for variant in ("V1", "V2"):
            with self.subTest(variant=variant):
                projected = strategies.make_strategy_request(variant, historical.QUESTIONS_NEW, context())["context"]
                serialized = json.dumps(projected)
                self.assertNotIn("PRIVATE_", serialized)
                self.assertNotIn("initial_chains", projected)
                self.assertEqual(set(projected["existing_conclusions"][0]), {"option_label"})

    def test_public_fields_preserved_and_deepcopied(self):
        source = context()
        before = copy.deepcopy(source)
        projected = strategies.build_action_conclusion_context(source)
        for field in strategies.PUBLIC_FIELDS:
            self.assertEqual(projected[field], source[field])
        self.assertEqual(source, before)
        projected["state"]["current_selection"] = "mutated"
        projected["history"][0]["receipt"]["executed"] = False
        projected["options"].append("not in source")
        projected["pending_proposal"]["action"] = "mutated"
        self.assertEqual(source, before)

    def test_dedup_exact_option_even_when_claims_differ(self):
        source = context()
        source["initial_chains"] = [
            candidate("c1", "Route A", "Choose A by one basis."),
            candidate("c2", "Route A", "Choose A under a different proposition."),
            candidate("c3", "Route B", "Choose B."),
            candidate("c4", "Route A", "Choose A by one basis."),
        ]
        projected = strategies.build_action_conclusion_context(source)
        self.assertEqual(projected["existing_conclusions"],
                         [{"option_label": "Route A"}, {"option_label": "Route B"}])
        self.assertNotIn("count", json.dumps(projected["existing_conclusions"]))

    def test_different_public_labels_not_semantically_merged(self):
        source = context()
        source["options"] += ["route a"]
        source["initial_chains"] += [candidate("c2", "route a")]
        self.assertEqual(strategies.build_action_conclusion_context(source)["existing_conclusions"],
                         [{"option_label": "Route A"}, {"option_label": "route a"}])

    def test_empty_initial_set_allowed(self):
        source = context()
        source["initial_chains"] = []
        self.assertEqual(strategies.build_action_conclusion_context(source)["existing_conclusions"], [])

    def test_null_option_aborts_instead_of_rewriting(self):
        source = context()
        source["initial_chains"].append(candidate("c2", None, "The first group exceeds the second."))
        before = copy.deepcopy(source)
        with self.assertRaisesRegex(strategies.ProjectionUnsupported, "null-option"):
            strategies.build_action_conclusion_context(source)
        self.assertEqual(source, before)

    def test_unknown_or_malformed_option_aborts(self):
        for option in ("Route Z", "route a", 3, []):
            source = context()
            source["initial_chains"] = [candidate(option=option)]
            with self.subTest(option=option):
                with self.assertRaises(strategies.ProjectionUnsupported):
                    strategies.build_action_conclusion_context(source)

    def test_missing_public_field_or_candidate_structure_aborts(self):
        source = context()
        source.pop("history")
        with self.assertRaises(strategies.ProjectionUnsupported):
            strategies.build_action_conclusion_context(source)
        for records in (None, {"chains": []}, [{"id": "c1"}], [None]):
            source = context()
            source["initial_chains"] = records
            with self.subTest(records=records):
                with self.assertRaises(strategies.ProjectionUnsupported):
                    strategies.build_action_conclusion_context(source)

    def test_no_v3_execution_path(self):
        with self.assertRaisesRegex(ValueError, "proposal"):
            strategies.make_strategy_request("V3", historical.QUESTIONS_NEW, context())
        self.assertIn("not an implemented", strategies.V3_DESIGN_PROPOSAL)

    def test_v2_generic_no_named_task_or_answer(self):
        prompt = strategies.V2_OPTIONS_QUESTIONS.lower()
        for word in ("pub001", "pub013", "b001", "b002", "maine", "texas", "illinois"):
            self.assertNotIn(word, prompt)
        self.assertIn("each public option in turn", prompt)
        self.assertIn("questions=[]", prompt)
        self.assertIn("at most two", prompt)
        self.assertIn("do not require one question per option", prompt)
        self.assertIn("not verification", prompt)

    def test_original_prompt_argument_required(self):
        with self.assertRaises(ValueError):
            strategies.make_strategy_request("V1", "", context())


if __name__ == "__main__":
    unittest.main()
