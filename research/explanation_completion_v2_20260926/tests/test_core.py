import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("completion_v2_core", ROOT / "core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

PUBLIC = {"user_goal": "Select the route with the greater requested quantity.",
          "option_labels": ["Route A", "Route B"],
          "policy_tables": [{"rows": [["Criterion", "Greater requested quantity"]]}]}
OBS = {"ref": "chart_1", "location": "route marks", "content": "Route A has the taller visible mark."}
TASK = {"ref": "public_task", "path": "/user_goal", "content": PUBLIC["user_goal"]}
RULE = {"id": "r1", "text": "If mark height measures the requested quantity, select the taller mark.",
        "component": "axis", "conditions": "Mark height measures the requested quantity."}


def initial(shared=False):
    rules = [copy.deepcopy(RULE)]
    if not shared:
        rules.append(dict(RULE, id="r2", text="If the printed values are the requested quantities, select their leader."))
    return {"rules": rules, "chains": [
        {"observations": [copy.deepcopy(OBS)], "rule_id": "r1", "option_label": "Route A",
         "claim": "Route A has the greater requested quantity, so select Route A."},
        {"observations": [{"ref": "chart_1", "location": "printed values",
                           "content": "Route B has the greater printed value."}],
         "rule_id": "r1" if shared else "r2", "option_label": "Route B",
         "claim": "Route B has the greater requested quantity, so select Route B."},
    ]}


def questions():
    return {"questions": [{"id": "q1", "target_chain_ids": ["base_c1", "base_c2"],
                            "focus": "rule_conditions", "question": "Which mapping condition is supported?"}],
            "summary": "One bounded condition question; no completeness claim."}


def empty_supplement():
    return {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": [
        {"question_id": "q1", "outcome": "already_covered", "record_ids": [],
         "covered_chain_ids": ["base_c1", "base_c2"], "reason": "Both readings already occur in the set."}]}


def support(status):
    return {"status": status, "evidence": [] if status == "undetermined" else [copy.deepcopy(OBS)],
            "reason": "Synthetic check for interface testing only."}


def verification(combined, b_status="undetermined", o_status="supported"):
    return {"schema_version": "explanation_verification_v2", "chain_checks": [
        {"target_id": chain["chain_id"], "O": support(o_status), "B_applicability": support(b_status),
         "conditional_inference": {"status": "valid",
                                   "premise_ids": ["chain:" + chain["chain_id"], "rule:" + chain["rule_id"]],
                                   "missing_premises": [], "reason": "Given these premises, this route claim follows."}}
        for chain in combined["chains"]],
        "refinement_checks": [{"target_id": record["id"], "support": support("supported")}
                              for record in combined["refinements"]],
        "summary": "Independent mock checks; neither route is selected by this interface."}


def context():
    return {"task_id": "task_x", "chart_ref": "sha256:test", "components": ["axis"],
            "conditions": {"r1": True, "r2": True}}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.raw = initial()
        self.base = core.import_initial(self.raw, PUBLIC)

    def state(self, checked=None, base=None):
        return core.build_rule_state(self.base if base is None else base, checked,
                                     "task_x", "sha256:test", PUBLIC)

    def test_two_competing_chains_can_both_be_valid_with_unknown_applicability(self):
        checked = verification(self.base)
        state = self.state(checked)
        self.assertEqual([check["conditional_inference"]["status"] for check in checked["chain_checks"]], ["valid", "valid"])
        self.assertEqual([rule["status"] for rule in state["rules"]], ["pending", "pending"])
        self.assertEqual([item["grounding"] for item in state["chain_assessments"]], ["conditional_candidate"] * 2)
        self.assertEqual([item["claim"] for item in state["chain_assessments"]], [item["claim"] for item in self.raw["chains"]])
        self.assertEqual(state["chains"], self.base["chains"])
        self.assertFalse(any(rule["usable"] for rule in core.read_rules(state, context())["rules"]))
        self.assertFalse(state["action_authorized"])

    def test_refuted_B_can_have_valid_conditional_inference_but_cannot_be_used(self):
        checked = verification(self.base, b_status="refuted")
        state = self.state(checked)
        self.assertEqual(state["rules"][0]["status"], "revoked")
        self.assertEqual(state["chain_assessments"][0]["grounding"], "contradicted_premises")
        self.assertEqual(state["chain_assessments"][0]["check"]["conditional_inference"]["status"], "valid")
        self.assertEqual(state["chain_assessments"][0]["claim"], self.raw["chains"][0]["claim"])
        self.assertFalse(core.read_rules(state, context())["rules"][0]["usable"])

    def test_no_observations_leaves_grounding_insufficient_without_rewriting_claim(self):
        self.raw["chains"][0].update(observations=[], task_evidence=[copy.deepcopy(TASK)])
        base = core.import_initial(self.raw, PUBLIC)
        checked = verification(base, b_status="supported")
        checked["chain_checks"][0]["O"] = support("undetermined")
        state = self.state(checked, base)
        self.assertEqual(state["chain_assessments"][0]["grounding"], "conditional_candidate")
        self.assertEqual(state["chain_assessments"][0]["claim"], self.raw["chains"][0]["claim"])
        self.assertEqual(state["rules"][0]["status"], "active")
        self.assertFalse(state["chain_assessments"][0]["action_authorized"])

    def test_observation_failure_does_not_revoke_B(self):
        state = self.state(verification(self.base, b_status="supported", o_status="refuted"))
        self.assertEqual(state["rules"][0]["status"], "active")
        self.assertEqual(state["chain_assessments"][0]["grounding"], "contradicted_premises")

    def test_actual_missing_premise_is_incomplete_and_does_not_assert_not_P(self):
        checked = verification(self.base)
        checked["chain_checks"][0]["conditional_inference"].update(
            status="incomplete", missing_premises=["The mapping from the printed value to the requested quantity is not supplied."],
            reason="This missing premise prevents deriving the route claim; it does not derive its negation.")
        state = self.state(checked)
        assessment = state["chain_assessments"][0]
        self.assertEqual(assessment["grounding"], "incomplete_inference")
        self.assertEqual(assessment["claim"], self.raw["chains"][0]["claim"])
        self.assertEqual(state["chains"][0]["option_label"], "Route A")
        self.assertEqual(state["rules"][0]["status"], "pending")
        self.assertNotIn("negated_claim", assessment)

    def test_invalid_inference_does_not_negate_or_replace_C(self):
        checked = verification(self.base, b_status="supported")
        checked["chain_checks"][0]["conditional_inference"].update(status="invalid", reason="The stated premises do not entail this claim.")
        state = self.state(checked)
        self.assertEqual(state["chain_assessments"][0]["grounding"], "invalid_inference")
        self.assertEqual(state["chain_assessments"][0]["claim"], self.raw["chains"][0]["claim"])

    def test_supported_candidate_is_still_not_action_authorization(self):
        state = self.state(verification(self.base, b_status="supported"))
        self.assertEqual(state["chain_assessments"][0]["grounding"], "supported_candidate")
        self.assertFalse(state["action_authorized"])
        self.assertFalse(core.read_rules(state, context())["action_authorized"])

    def test_proposal_relations_are_neither_required_nor_derived_from_options(self):
        state = self.state(verification(self.base))
        for chain in state["chains"]:
            self.assertNotIn("proposal_relation", chain)
            self.assertNotIn("relationship", chain)
        self.raw["chains"][1]["proposal_relation"] = {
            "target_option": "Route A", "stance": "alternative", "reason": "This is a separate route candidate, not proof of the negation."}
        base = core.import_initial(self.raw, PUBLIC)
        self.assertEqual(base["chains"][1]["proposal_relation"], self.raw["chains"][1]["proposal_relation"])
        self.assertNotIn("proposal_relation", base["chains"][0])

    def test_full_archived_set_ignores_normalized_view_and_preserves_order(self):
        raw = initial(shared=True)
        raw["chains"][0]["chain_id"] = "archived_c9"
        raw["chains"].extend([dict(copy.deepcopy(raw["chains"][1]), chain_id="archived_c11",
                                    claim="A third explanatory chain retained as written.")])
        saved = copy.deepcopy(raw)
        base = core.import_initial({"generated": raw, "normalized": {"chains": raw["chains"][:1]}}, PUBLIC)
        self.assertEqual(base["initial_counts"], {"rules": 1, "chains": 3})
        self.assertEqual([c["chain_id"] for c in base["chains"]], ["archived_c9", "base_c2", "archived_c11"])
        self.assertEqual([c["claim"] for c in base["chains"]], [c["claim"] for c in raw["chains"]])
        self.assertEqual(raw, saved)

    def test_bad_original_chain_is_not_silently_dropped(self):
        self.raw["chains"][1]["rule_id"] = "missing"
        with self.assertRaisesRegex(core.SchemaError, "missing rule"):
            core.import_initial(self.raw, PUBLIC)

    def test_zero_supplements_and_zero_questions_preserve_all_original_chains(self):
        combined = core.apply_supplement(empty_supplement(), self.base, questions(), PUBLIC)
        self.assertEqual(combined["chains"], self.base["chains"])
        self.assertEqual(combined["schema_version"], "explanation_completion_v2")
        self.assertEqual(combined["supplement_counts"], {"rules": 0, "chains": 0, "refinements": 0})
        no_questions = {"questions": [], "summary": "No additional bounded question."}
        empty = {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": []}
        combined = core.apply_supplement(empty, self.base, no_questions, PUBLIC)
        self.assertEqual(combined["chains"], self.base["chains"])

    def test_new_chain_preserves_explicit_metadata_and_v1_relationship_contract(self):
        chain = {"chain_id": "supp_c1", "rule_id": "supp_r1", "observations": [copy.deepcopy(OBS)],
                 "option_label": "Route A", "claim_kind": "supports_action", "claim": "This additional mapping also selects Route A.",
                 "question_ids": ["q1"], "relationship": "compatible"}
        supplement = {"new_rules": [dict(RULE, id="supp_r1", text="An additional explicit mapping condition.")],
                      "new_chains": [chain], "refinements": [], "question_responses": [
                          {"question_id": "q1", "outcome": "new_explanation", "record_ids": ["supp_c1"],
                           "covered_chain_ids": [], "reason": "A distinct bridge supports the same route."}]}
        combined = core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        self.assertEqual(combined["chains"][:2], self.base["chains"])
        self.assertNotIn("proposal_relation", combined["chains"][-1])
        self.assertEqual(combined["chains"][-1]["relationship"], "compatible")
        chain["proposal_relation"] = {"target_option": "Route B", "stance": "alternative",
                                      "reason": "Another route candidate does not establish that Route B is false."}
        combined = core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        self.assertEqual(combined["chains"][-1]["proposal_relation"], chain["proposal_relation"])
        self.assertEqual(self.state(verification(combined), combined)["chains"][-1], combined["chains"][-1])
        del chain["relationship"]
        with self.assertRaisesRegex(core.SchemaError, "invalid relationship"):
            core.apply_supplement(supplement, self.base, questions(), PUBLIC)

    def test_supplement_retains_bidirectional_question_links(self):
        supplement = empty_supplement()
        supplement["question_responses"][0]["covered_chain_ids"] = []
        with self.assertRaisesRegex(core.SchemaError, "already_covered"):
            core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        too_many = questions()
        too_many["questions"] *= 4
        with self.assertRaisesRegex(core.SchemaError, "at most three"):
            core.validate_questions(too_many, self.base, PUBLIC)

    def test_condition_only_refinement_does_not_activate_original_B(self):
        supplement = empty_supplement()
        supplement["refinements"] = [{"id": "refine_1", "target_chain_id": "base_c1", "question_ids": ["q1"],
                                      "added_observations": [], "added_task_evidence": [],
                                      "condition_note": "Use the height rule only if height measures the requested quantity.",
                                      "reason": "Expose the existing condition without claiming it holds."}]
        supplement["question_responses"][0].update(outcome="refined_existing", record_ids=["refine_1"])
        combined = core.apply_supplement(supplement, self.base, questions(), PUBLIC)
        checked = verification(combined)
        checked["refinement_checks"][0]["support"]["evidence"] = [copy.deepcopy(TASK)]
        state = self.state(checked, combined)
        self.assertEqual(state["refinements"][0]["status"], "supported")
        self.assertEqual(state["refinements"][0]["support"]["status"], "supported")
        self.assertFalse(state["refinements"][0]["applied_to_original"])
        self.assertEqual(state["refinements"][0]["target_rule_id"], "r1")
        self.assertEqual(state["rules"][0]["status"], "pending")
        self.assertEqual(state["chains"], self.base["chains"])
        self.assertEqual(combined["rules"], self.base["rules"])
        checked["refinement_checks"] = []
        with self.assertRaisesRegex(core.SchemaError, "every refinement"):
            self.state(checked, combined)

    def test_shared_rule_applicability_disagreement_is_preserved(self):
        base = core.import_initial(initial(shared=True), PUBLIC)
        checked = verification(base, b_status="supported")
        checked["chain_checks"][1]["B_applicability"] = support("refuted")
        state = self.state(checked, base)
        self.assertEqual(state["rules"][0]["status"], "disputed")
        self.assertEqual(len(state["rules"][0]["checks"]), 2)
        self.assertFalse(core.read_rules(state, context())["rules"][0]["usable"])

    def test_verification_requires_each_chain_exactly_once(self):
        for malformed in ("missing", "duplicate", "unknown"):
            checked = verification(self.base)
            if malformed == "missing":
                checked["chain_checks"].pop()
            elif malformed == "duplicate":
                checked["chain_checks"].append(copy.deepcopy(checked["chain_checks"][0]))
            else:
                checked["chain_checks"][0]["target_id"] = "unknown"
            with self.subTest(malformed=malformed), self.assertRaises(core.SchemaError):
                self.state(checked)

    def test_definite_O_and_B_need_evidence_and_public_values_must_be_exact(self):
        for dimension in ("O", "B_applicability"):
            checked = verification(self.base, b_status="supported")
            checked["chain_checks"][0][dimension]["evidence"] = []
            with self.subTest(dimension=dimension), self.assertRaisesRegex(core.SchemaError, "evidence reference"):
                self.state(checked)
            checked["chain_checks"][0][dimension]["evidence"] = [copy.deepcopy(TASK)]
            core.validate_verification(checked, self.base, PUBLIC)
            checked["chain_checks"][0][dimension]["evidence"][0]["content"] = "Fabricated task goal"
            with self.assertRaisesRegex(core.SchemaError, "exact public leaf"):
                self.state(checked)

    def test_conditional_references_cannot_borrow_other_chains_rules_or_public(self):
        for refs in (["chain:base_c2", "rule:r1"], ["chain:base_c1", "rule:r2"],
                     ["chain:base_c1", "rule:r1", "public_task:/user_goal"],
                     ["chain:base_c1"], ["chain:base_c1", "rule:r1", "rule:r1"]):
            checked = verification(self.base)
            checked["chain_checks"][0]["conditional_inference"]["premise_ids"] = refs
            with self.subTest(refs=refs), self.assertRaises(core.SchemaError):
                self.state(checked)

    def test_missing_premise_contract_is_explicit(self):
        for status, missing in (("incomplete", []), ("valid", ["Missing mapping"]), ("invalid", ["Missing mapping"])):
            checked = verification(self.base)
            checked["chain_checks"][0]["conditional_inference"].update(status=status, missing_premises=missing)
            with self.subTest(status=status), self.assertRaises(core.SchemaError):
                self.state(checked)

    def test_legacy_verification_and_mixed_dimensions_are_rejected(self):
        legacy = {"checks": [], "summary": "Legacy verification."}
        with self.assertRaisesRegex(core.SchemaError, "explanation_verification_v2"):
            self.state(legacy)
        checked = verification(self.base)
        checked["chain_checks"][0]["implication"] = support("supported")
        with self.assertRaisesRegex(core.SchemaError, "legacy"):
            self.state(checked)
        checked = verification(self.base)
        checked["checks"] = []
        with self.assertRaisesRegex(core.SchemaError, "legacy"):
            self.state(checked)

    def test_unverified_state_remains_pending_and_save_is_exclusive(self):
        state = self.state()
        self.assertTrue(all(rule["status"] == "pending" for rule in state["rules"]))
        self.assertTrue(all(item["grounding"] == "unverified" for item in state["chain_assessments"]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            core.save_state(path, state)
            self.assertEqual(core.load_state(path), state)
            with self.assertRaises(FileExistsError):
                core.save_state(path, state)

    def test_load_and_read_reject_old_state_without_implicit_migration(self):
        state = self.state()
        state["schema_version"] = "task_rule_state_v1"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old-state.json"
            with path.open("w", encoding="utf-8") as stream:
                json.dump(state, stream)
            with self.assertRaisesRegex(core.SchemaError, "not migrated"):
                core.load_state(path)
        with self.assertRaisesRegex(core.SchemaError, "not migrated"):
            core.read_rules(state, context())

    def test_scope_match_mismatch_missing_and_pending_are_distinct(self):
        state = self.state(verification(self.base, b_status="supported"))
        self.assertTrue(all(rule["usable"] for rule in core.read_rules(state, context())["rules"]))
        for field, value in (("task_id", "task_y"), ("chart_ref", "sha256:other"),
                             ("components", ["legend"]), ("conditions", {"r1": False})):
            wrong = dict(context(), **{field: value})
            view = core.read_rules(state, wrong)
            self.assertEqual(view["rules"][0]["applicability"], "inapplicable")
            self.assertFalse(view["rules"][0]["usable"])
        self.assertEqual(core.read_rules(state, {})["rules"][0]["applicability"], "unknown")
        self.assertFalse(core.read_rules(self.state(verification(self.base)), context())["rules"][0]["usable"])
        with self.assertRaisesRegex(core.SchemaError, "concrete image"):
            core.build_rule_state(self.base, None, "task_x", "chart_1", PUBLIC)


if __name__ == "__main__":
    unittest.main()
