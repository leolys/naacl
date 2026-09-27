import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("completion_core", ROOT / "core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


PUBLIC = {"user_goal": "Select the leading option.", "option_labels": ["Route A", "Route B"],
          "policy_tables": [{"rows": [["Rule", "Largest visible value"]]}]}
OBS = {"ref": "chart_1", "location": "left axis", "content": "The printed tick reads 10."}
RULE = {"id": "r1", "text": "Read position under the axis mapping.",
        "component": "axis", "conditions": "Axis maps the requested quantity."}


def initial(shared=False):
    rules = [copy.deepcopy(RULE)]
    if not shared:
        rules.append(dict(RULE, id="r2", text="Read printed labels."))
    return {"rules": rules, "chains": [
        {"observations": [copy.deepcopy(OBS)], "rule_id": "r1", "option_label": "Route A", "claim": "By r1 select A."},
        {"observations": [copy.deepcopy(OBS)], "rule_id": "r1" if shared else "r2", "option_label": "Route B", "claim": "The other interpretation selects B."},
    ]}


def questions():
    return {"questions": [{"id": "q1", "target_chain_ids": ["base_c1", "base_c2"],
                            "focus": "coverage", "question": "Is this additional reading already represented?"}],
            "summary": "Checks this axis and label interpretation, not exhaustive coverage."}


def empty_supplement():
    return {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": [
        {"question_id": "q1", "outcome": "already_covered", "record_ids": [],
         "covered_chain_ids": ["base_c1", "base_c2"], "reason": "Both are already explicit."}]}


def verification(combined, status="supported"):
    targets = [c["chain_id"] for c in combined["chains"]] + [r["id"] for r in combined["refinements"]]
    return {"checks": [{"target_id": target, **{
        dim: {"status": status, "evidence": [copy.deepcopy(OBS)] if status != "undetermined" else [],
              "reason": "Synthetic interface test judgment."} for dim in ("O", "B", "implication")}}
                       for target in targets], "summary": "Mock only, not a visual finding."}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.raw = initial()
        self.base = core.import_initial(self.raw, PUBLIC)

    def test_complete_initial_set_keeps_order_text_and_shared_rules(self):
        original = initial(shared=True)
        saved = copy.deepcopy(original)
        imported = core.import_initial({"generated": original, "normalized": {"chains": []}}, PUBLIC)
        self.assertEqual(len(imported["chains"]), 2)
        self.assertEqual(len(imported["rules"]), 1)
        self.assertEqual(imported["chains"][0]["claim"], original["chains"][0]["claim"])
        self.assertEqual(imported["chains"][1]["rule_id"], "r1")
        self.assertEqual(original, saved)

    def test_existing_chain_ids_remain_stable(self):
        self.raw["chains"][0]["chain_id"] = "archived_c9"
        imported = core.import_initial(self.raw, PUBLIC)
        self.assertEqual(imported["chains"][0]["chain_id"], "archived_c9")

    def test_invalid_initial_chain_is_not_silently_dropped(self):
        self.raw["chains"][1]["rule_id"] = "missing"
        with self.assertRaisesRegex(core.SchemaError, "missing rule"):
            core.import_initial(self.raw, PUBLIC)

    def test_zero_new_chains_and_zero_questions_are_legal(self):
        combined = core.apply_supplement(empty_supplement(), self.base, questions(), PUBLIC)
        self.assertEqual(combined["chains"], self.base["chains"])
        no_questions = {"questions": [], "summary": "No further scoped questions at this pass; not exhaustive."}
        empty = {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": []}
        self.assertEqual(core.apply_supplement(empty, self.base, no_questions, PUBLIC)["supplement_counts"]["chains"], 0)

    def new_chain_supplement(self):
        chain = {"chain_id": "supp_c1", "rule_id": "supp_r1", "observations": [copy.deepcopy(OBS)],
                 "option_label": "Route A", "claim_kind": "supports_action", "claim": "A through a distinct reading.",
                 "question_ids": ["q1"], "relationship": "compatible"}
        return {"new_rules": [dict(RULE, id="supp_r1", text="A different mapping than r1.")],
                "new_chains": [chain], "refinements": [], "question_responses": [
                    {"question_id": "q1", "outcome": "new_explanation", "record_ids": ["supp_c1"],
                     "covered_chain_ids": [], "reason": "Different bridge, same action."}]}

    def test_same_action_different_basis_does_not_require_conflict(self):
        combined = core.apply_supplement(self.new_chain_supplement(), self.base, questions(), PUBLIC)
        self.assertEqual(len(combined["chains"]), 3)
        self.assertEqual(combined["chains"][0]["option_label"], combined["chains"][2]["option_label"])

    def test_health_free_text_rule_reference_does_not_shift(self):
        combined = core.apply_supplement(self.new_chain_supplement(), self.base, questions(), PUBLIC)
        self.assertEqual(combined["rules"][0]["id"], "r1")
        self.assertEqual(combined["rules"][-1]["text"], "A different mapping than r1.")
        self.assertEqual(combined["chains"][0]["claim"], "By r1 select A.")

    def test_public_task_leaf_is_allowed_separately_not_as_observation(self):
        supplement = self.new_chain_supplement()
        task = {"ref": "public_task", "path": "/policy_tables/0/rows/0/1", "content": "Largest visible value"}
        supplement["new_chains"][0]["task_evidence"] = [task]
        core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        supplement["new_chains"][0]["observations"] = [task]
        with self.assertRaisesRegex(core.SchemaError, "observations must cite"):
            core.apply_supplement(supplement, self.base, questions(), PUBLIC)

    def test_public_leaf_quote_and_pointer_are_exact(self):
        supplement = self.new_chain_supplement()
        supplement["new_chains"][0]["task_evidence"] = [
            {"ref": "public_task", "path": "/user_goal", "content": "Invented policy"}]
        with self.assertRaisesRegex(core.SchemaError, "exact public leaf"):
            core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        supplement["new_chains"][0]["task_evidence"][0]["path"] = "/policy_tables"
        with self.assertRaisesRegex(core.SchemaError, "scalar leaf"):
            core.apply_supplement(supplement, self.base, questions(), PUBLIC)

    def test_candidate_support_gap_can_have_no_alternative_action(self):
        supplement = self.new_chain_supplement()
        supplement["new_chains"][0].update(claim_kind="challenges_support", option_label=None, relationship="support_gap")
        core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        supplement["new_chains"][0]["option_label"] = "Route A"
        with self.assertRaisesRegex(core.SchemaError, "non-action support gaps"):
            core.apply_supplement(supplement, self.base, questions(), PUBLIC)

    def refinement(self):
        return {"id": "refine_1", "target_chain_id": "base_c1", "question_ids": ["q1"],
                "added_observations": [], "added_task_evidence": [],
                "condition_note": "Only if these ticks are the applicable scale.", "reason": "Expose a prior condition."}

    def test_refinement_keeps_original_rule_and_chain_unchanged(self):
        supplement = empty_supplement()
        supplement["refinements"] = [self.refinement()]
        supplement["question_responses"][0].update(outcome="refined_existing", record_ids=["refine_1"])
        combined = core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        self.assertEqual(combined["chains"], self.base["chains"])
        self.assertEqual(combined["rules"], self.base["rules"])
        self.assertEqual(combined["refinements"][0]["condition_note"], self.refinement()["condition_note"])
        bad = verification(combined)
        bad["checks"].pop()
        with self.assertRaisesRegex(core.SchemaError, "every chain and refinement"):
            core.validate_verification(bad, combined, PUBLIC)

    def test_bidirectional_links_and_covered_ids_required(self):
        bad = self.new_chain_supplement()
        bad["question_responses"][0]["record_ids"] = []
        with self.assertRaisesRegex(core.SchemaError, "both directions"):
            core.apply_supplement(bad, self.base, questions(), PUBLIC)
        bad = empty_supplement()
        bad["question_responses"][0]["covered_chain_ids"] = []
        with self.assertRaisesRegex(core.SchemaError, "already_covered"):
            core.apply_supplement(bad, self.base, questions(), PUBLIC)

    def test_original_ids_cannot_be_reused_as_new_rules(self):
        bad = self.new_chain_supplement()
        bad["new_rules"][0]["id"] = "r1"
        with self.assertRaisesRegex(core.SchemaError, "supp_rN"):
            core.apply_supplement(bad, self.base, questions(), PUBLIC)

    def test_verification_requires_full_unique_checks_and_grounded_definite_judgments(self):
        good = verification(self.base)
        core.validate_verification(good, self.base, PUBLIC)
        good["checks"][0]["B"]["evidence"] = []
        with self.assertRaisesRegex(core.SchemaError, "evidence reference"):
            core.validate_verification(good, self.base, PUBLIC)
        good["checks"][0]["B"]["status"] = "undetermined"
        core.validate_verification(good, self.base, PUBLIC)

    def test_observation_failure_does_not_revoke_supported_bridge(self):
        checked = verification(self.base)
        checked["checks"][0]["O"]["status"] = "refuted"
        checked["checks"][0]["implication"]["status"] = "refuted"
        state = core.build_rule_state(self.base, checked, "task_x", "sha256:test")
        self.assertEqual(state["rules"][0]["status"], "active")
        self.assertEqual(state["rules"][0]["checks"][0]["O"]["status"], "refuted")
        self.assertEqual(state["rules"][0]["checks"][0]["implication"]["status"], "refuted")

    def test_shared_rule_disagreement_is_disputed(self):
        base = core.import_initial(initial(shared=True), PUBLIC)
        checked = verification(base)
        checked["checks"][1]["B"]["status"] = "undetermined"
        state = core.build_rule_state(base, checked, "task_x", "sha256:test")
        self.assertEqual(state["rules"][0]["status"], "disputed")

    def test_no_verification_stays_pending_and_reload_never_promotes(self):
        state = core.build_rule_state(self.base, None, "task_x", "sha256:test")
        self.assertTrue(all(rule["status"] == "pending" for rule in state["rules"]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            core.save_state(path, state)
            self.assertEqual(core.load_state(path), state)
            with self.assertRaises(FileExistsError):
                core.save_state(path, state)

    def test_scope_separates_match_mismatch_unknown_and_state(self):
        state = core.build_rule_state(self.base, verification(self.base), "task_x", "sha256:test")
        context = {"task_id": "task_x", "chart_ref": "sha256:test", "components": ["axis"],
                   "conditions": {"r1": True, "r2": True}}
        view = core.read_rules(state, context)
        self.assertTrue(all(rule["usable"] for rule in view["rules"]))
        wrong = dict(context, chart_ref="sha256:another_arm")
        self.assertEqual(core.read_rules(state, wrong)["rules"][0]["applicability"], "inapplicable")
        self.assertEqual(core.read_rules(state, {})["rules"][0]["applicability"], "unknown")
        pending = core.build_rule_state(self.base, None, "task_x", "sha256:test")
        self.assertFalse(core.read_rules(pending, context)["rules"][0]["usable"])

    def test_partial_verification_cannot_silently_activate_rules(self):
        bad = verification(self.base)
        bad["checks"].pop()
        with self.assertRaisesRegex(core.SchemaError, "full verification"):
            core.build_rule_state(self.base, bad, "task_x", "sha256:test")

    def test_generic_chart_reference_cannot_be_persistent_scope(self):
        with self.assertRaisesRegex(core.SchemaError, "concrete image"):
            core.build_rule_state(self.base, None, "task_x", "chart_1")

    def test_condition_only_refinement_checks_its_asserted_dimensions(self):
        supplement = empty_supplement()
        supplement["refinements"] = [self.refinement()]
        supplement["question_responses"][0].update(outcome="refined_existing", record_ids=["refine_1"])
        combined = core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        checked = verification(combined)
        checked["checks"][-1]["O"].update(status="undetermined", evidence=[], reason="No new O assertion.")
        core.validate_verification(checked, combined, PUBLIC)
        state = core.build_rule_state(combined, checked, "task_x", "sha256:test")
        self.assertEqual(state["refinements"][0]["status"], "supported")
        self.assertFalse(state["refinements"][0]["applied_to_original"])
        self.assertEqual(state["refinements"][0]["asserted_dimensions"], ["B", "implication"])
        self.assertEqual(state["refinements"][0]["target_rule_id"], "r1")
        self.assertEqual(state["refinements"][0]["target_rule_version"], 1)

    def test_no_repeated_supplement_overwrites_an_earlier_pass(self):
        combined = core.apply_supplement(self.new_chain_supplement(), self.base, questions(), PUBLIC)
        with self.assertRaisesRegex(core.SchemaError, "earlier pass"):
            core.apply_supplement(empty_supplement(), combined, questions(), PUBLIC)


if __name__ == "__main__":
    unittest.main()
