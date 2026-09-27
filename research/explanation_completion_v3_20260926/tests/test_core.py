import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("completion_v3_test_core", ROOT / "core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
prompt_spec = importlib.util.spec_from_file_location("completion_v3_test_prompts", ROOT / "prompts.py")
prompts = importlib.util.module_from_spec(prompt_spec)
prompt_spec.loader.exec_module(prompts)

PUBLIC = {"user_goal": "Select the route with the greater requested quantity.",
          "option_labels": ["Route A", "Route B"],
          "policy_tables": [{"rows": [["Criterion", "Greater requested quantity"]]}]}
OBS = {"ref": "chart_1", "location": "route marks",
       "content": "The top of the mark beside Route A is above the top beside Route B."}
TASK = {"ref": "public_task", "path": "/user_goal", "content": PUBLIC["user_goal"]}
RULE = {"id": "r1", "text": "If height encodes the requested quantity, choose the taller mark.",
        "component": "axis", "conditions": "Assume height encodes the requested quantity."}
GAP = {"id": "gap1", "question": "Which printed unit denotes the requested quantity?",
       "reason": "The visible unit cannot be bound to the requested quantity in a complete candidate."}


def initial(shared=False, count=2):
    rules = [copy.deepcopy(RULE)]
    if not shared and count > 1:
        rules.append(dict(RULE, id="r2", text="If printed numbers encode quantity, choose their leader."))
    chains = [{"observations": [copy.deepcopy(OBS)], "task_evidence": [copy.deepcopy(TASK)],
               "rule_id": "r1", "option_label": "Route A", "claim": "Select Route A for the greater quantity."}]
    if count > 1:
        chains.append({"observations": [{"ref": "chart_1", "location": "value labels",
                                        "content": "The text beside Route A reads 2; beside Route B it reads 5."}],
                       "task_evidence": [copy.deepcopy(TASK)], "rule_id": "r1" if shared else "r2",
                       "option_label": "Route B", "claim": "Select Route B for the greater quantity."})
    return {"rules": rules, "chains": chains, "unresolved_questions": []}


def questions():
    return {"questions": [{"id": "q1", "target_chain_ids": ["base_c1"],
                            "focus": "rule_conditions", "question": "Does another stated mapping yield a candidate?"}],
            "summary": "A bounded condition question, with no completeness assertion."}


def supplement():
    return {"new_rules": [dict(RULE, id="supp_r1", text="A separately stated mapping also gives Route A.")],
            "new_chains": [{"chain_id": "supp_c1", "rule_id": "supp_r1", "observations": [copy.deepcopy(OBS)],
                            "task_evidence": [], "option_label": "Route A", "claim": "Select Route A under this mapping.",
                            "question_ids": ["q1"], "relationship": "compatible"}],
            "refinements": [], "question_responses": [{"question_id": "q1", "outcome": "new_explanation",
                                                        "record_ids": ["supp_c1"], "covered_chain_ids": [],
                                                        "reason": "A distinct basis agrees with the first candidate."}]}


def empty_supplement(outcome="already_covered"):
    return {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": [
        {"question_id": "q1", "outcome": outcome, "record_ids": [],
         "covered_chain_ids": ["base_c1"] if outcome == "already_covered" else [],
         "reason": "The reading is already represented." if outcome == "already_covered" else "The unit binding is unresolved."}]}


def refinement():
    return {"id": "refine_1", "target_chain_id": "base_c1", "question_ids": ["q1"],
            "added_observations": [], "added_task_evidence": [],
            "condition_note": "The mapping applies only to the labelled panel.",
            "reason": "Clarifies the intended scope without rewriting the original."}


def support(status):
    return {"status": status, "evidence": [] if status == "undetermined" else [copy.deepcopy(OBS)],
            "reason": "Synthetic interface judgment, not an empirical result."}


def verification(combined, b_status="undetermined", o_status="supported"):
    return {"schema_version": core.VERIFICATION_SCHEMA, "chain_checks": [
        {"target_id": chain["chain_id"], "O": support(o_status), "B_applicability": support(b_status),
         "conditional_inference": {"status": "valid",
                                   "premise_ids": ["chain:" + chain["chain_id"], "rule:" + chain["rule_id"]],
                                   "missing_premises": [], "reason": "The stated conditional candidate follows."}}
        for chain in combined["chains"]],
        "refinement_checks": [{"target_id": record["id"], "support": support("supported")}
                              for record in combined["refinements"]],
        "summary": "Separate mock judgments, without selecting a winner."}


def context():
    return {"task_id": "task_x", "chart_ref": "sha256:test", "components": ["axis"],
            "conditions": {"r1": True, "r2": True, "supp_r1": True}}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.raw = initial()
        self.base = core.import_initial(self.raw, PUBLIC)

    def state(self, checked=None, base=None):
        return core.build_rule_state(self.base if base is None else base, checked, "task_x", "sha256:test", PUBLIC)

    def test_initial_set_order_ids_text_and_shared_rule_are_preserved(self):
        raw = initial(shared=True)
        raw["chains"][0]["chain_id"] = "archived_c9"
        before = copy.deepcopy(raw)
        result = core.import_initial({"generated": raw, "normalized": {"chains": []}}, PUBLIC)
        self.assertEqual(raw, before)
        self.assertEqual(result["chains"][0], raw["chains"][0])
        self.assertEqual(result["chains"][1], dict(raw["chains"][1], chain_id="base_c2"))
        self.assertEqual(result["rules"], raw["rules"])
        self.assertTrue(all("claim_kind" not in c for c in result["chains"]))

    def test_all_legacy_claim_kinds_are_rejected_instead_of_mapped(self):
        for kind in ("supports_action", "challenges_support", "underdetermined", None):
            raw = initial()
            raw["chains"][0]["claim_kind"] = kind
            with self.subTest(kind=kind), self.assertRaisesRegex(core.SchemaError, "claim_kind"):
                core.import_initial(raw, PUBLIC)
            value = supplement()
            value["new_chains"][0]["claim_kind"] = kind
            with self.assertRaisesRegex(core.SchemaError, "claim_kind"):
                core.apply_supplement(value, self.base, questions(), PUBLIC)

    def test_old_explicit_generation_schema_is_rejected(self):
        for schema in ("explanation_completion_v1", "explanation_completion_v2", "explanation_generation_v2"):
            with self.subTest(schema=schema), self.assertRaisesRegex(core.SchemaError, "not migrated"):
                core.import_initial(dict(self.raw, schema_version=schema), PUBLIC)
        self.assertEqual(core.import_initial(dict(self.raw, schema_version=core.GENERATION_SCHEMA), PUBLIC), self.base)

    def test_unresolved_questions_is_a_required_new_schema_field(self):
        del self.raw["unresolved_questions"]
        with self.assertRaisesRegex(core.SchemaError, "unresolved_questions"):
            core.import_initial(self.raw, PUBLIC)

    def test_concrete_negative_and_comparison_need_no_option_or_kind(self):
        for claim in ("Route A is not the route with the greater quantity.", "Route B exceeds Route A by 3 units."):
            raw = initial(count=1)
            raw["chains"][0].update(option_label=None, claim=claim)
            imported = core.import_initial(raw, PUBLIC)
            self.assertEqual(imported["chains"][0]["claim"], claim)
            self.assertIsNone(imported["chains"][0]["option_label"])
            self.assertNotIn("claim_kind", imported["chains"][0])

    def test_option_is_explicit_and_must_be_a_public_label_or_null(self):
        for replacement in ({}, {"option_label": "Route C"}, {"option_label": []}):
            raw = initial()
            del raw["chains"][0]["option_label"]
            raw["chains"][0].update(replacement)
            with self.subTest(replacement=replacement), self.assertRaises(core.SchemaError):
                core.import_initial(raw, PUBLIC)

    def test_unconfirmed_B_is_allowed_without_verification_fields(self):
        raw = initial(count=1)
        raw["rules"][0]["conditions"] = "Assume, without prior confirmation, that the vertical mapping is decreasing."
        imported = core.import_initial(raw, PUBLIC)
        self.assertEqual(imported["rules"], raw["rules"])
        self.assertEqual(self.state(base=imported)["chain_assessments"][0]["grounding"], "unverified")

    def test_validator_does_not_classify_or_rewrite_claim_text(self):
        # This is deliberately a protocol violation for the model to assess.
        # A string-based correctness filter here would silently hide its error.
        raw = initial(count=1)
        raw["chains"][0].update(option_label=None, claim="The comparison is underdetermined; Route A wins anyway.")
        base = core.import_initial(raw, PUBLIC)
        checked = verification(base)
        checked["chain_checks"][0]["conditional_inference"].update(status="invalid", reason="C contains an unsupported assertion.")
        state = self.state(checked, base)
        self.assertEqual(state["chains"][0]["claim"], raw["chains"][0]["claim"])
        self.assertEqual(state["chain_assessments"][0]["grounding"], "invalid_inference")

    def test_initial_limit_is_three_without_minimum_quota(self):
        self.assertEqual(len(core.import_initial(initial(count=1), PUBLIC)["chains"]), 1)
        raw = initial(shared=True)
        raw["chains"].extend(copy.deepcopy(raw["chains"]))
        with self.assertRaisesRegex(core.SchemaError, "at most three"):
            core.import_initial(raw, PUBLIC)

    def test_no_unused_rules_missing_rules_or_colliding_ids(self):
        for case in ("unused", "missing", "collision"):
            raw = initial()
            if case == "unused":
                raw["rules"].append(dict(RULE, id="unused"))
            elif case == "missing":
                raw["chains"][0]["rule_id"] = "missing"
            else:
                raw["chains"][0]["chain_id"] = "base_c2"
            with self.subTest(case=case), self.assertRaises(core.SchemaError):
                core.import_initial(raw, PUBLIC)

    def test_empty_initial_set_is_explicit_unresolved_data_not_a_fake_chain(self):
        raw = {"rules": [], "chains": [], "unresolved_questions": [copy.deepcopy(GAP)]}
        before = copy.deepcopy(raw)
        base = core.import_initial(raw, PUBLIC)
        state = self.state(base=base)
        self.assertEqual(raw, before)
        self.assertEqual(base["rules"], [])
        self.assertEqual(base["chains"], [])
        self.assertFalse(state["verification_performed"])
        self.assertEqual(state["chain_assessments"], [])
        self.assertEqual(state["unresolved_questions"], raw["unresolved_questions"])
        self.assertEqual(core.read_rules(state, {})["unresolved_questions"], raw["unresolved_questions"])
        with self.assertRaisesRegex(core.SchemaError, "stop"):
            core.apply_supplement(empty_supplement(), base, questions(), PUBLIC)

    def test_empty_set_needs_nonempty_well_formed_unresolved_records(self):
        for gaps in ([], [{}], [dict(GAP, question="")], [dict(GAP, reason="")],
                     [dict(GAP, id="q1")], [GAP, GAP], [dict(GAP, claim="unknown")]):
            with self.subTest(gaps=gaps), self.assertRaises(core.SchemaError):
                core.import_initial({"rules": [], "chains": [], "unresolved_questions": gaps}, PUBLIC)

    def test_no_question_target_is_fabricated_for_empty_set(self):
        base = core.import_initial({"rules": [], "chains": [], "unresolved_questions": [GAP]}, PUBLIC)
        value = {"questions": [], "summary": "No target candidates exist."}
        self.assertEqual(core.validate_questions(value, base, PUBLIC), value)
        with self.assertRaisesRegex(core.SchemaError, "existing initial"):
            core.validate_questions(questions(), base, PUBLIC)

    def test_unresolved_records_survive_nonempty_generation_supplement_and_state(self):
        raw = initial()
        raw["unresolved_questions"] = [copy.deepcopy(GAP)]
        base = core.import_initial(raw, PUBLIC)
        combined = core.apply_supplement(supplement(), base, questions(), PUBLIC)
        state = self.state(verification(combined), combined)
        self.assertEqual(combined["unresolved_questions"], [GAP])
        self.assertEqual(state["unresolved_questions"], [GAP])
        self.assertNotIn("gap1", [c["chain_id"] for c in state["chain_assessments"]])

    def test_same_conclusion_can_have_compatible_independent_basis(self):
        combined = core.apply_supplement(supplement(), self.base, questions(), PUBLIC)
        self.assertEqual(combined["chains"][-1]["relationship"], "compatible")
        self.assertEqual(combined["chains"][0]["option_label"], combined["chains"][-1]["option_label"])
        self.assertEqual(combined["chains"][:2], self.base["chains"])
        self.assertEqual(combined["rules"][:2], self.base["rules"])

    def test_competing_candidate_also_allowed_without_automatic_relation_inference(self):
        value = supplement()
        value["new_chains"][0].update(relationship="competing", option_label=None,
                                       claim="Route A does not have the greater quantity.")
        result = core.apply_supplement(value, self.base, questions(), PUBLIC)
        self.assertEqual(result["chains"][-1]["claim"], value["new_chains"][0]["claim"])
        self.assertNotIn("proposal_relation", result["chains"][-1])

    def test_support_gap_is_not_an_accepted_new_chain_relationship(self):
        for relationship in ("support_gap", "underdetermined", "alternative", None, []):
            value = supplement()
            value["new_chains"][0]["relationship"] = relationship
            with self.subTest(relationship=relationship), self.assertRaisesRegex(core.SchemaError, "compatible or competing"):
                core.apply_supplement(value, self.base, questions(), PUBLIC)

    def test_zero_additions_and_unresolved_response_are_allowed(self):
        for outcome in ("already_covered", "unresolved"):
            result = core.apply_supplement(empty_supplement(outcome), self.base, questions(), PUBLIC)
            self.assertEqual(result["chains"], self.base["chains"])
            self.assertEqual(result["supplement_counts"], {"rules": 0, "chains": 0, "refinements": 0})
        no_questions = {"questions": [], "summary": "No further question on this pass."}
        empty = {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": []}
        self.assertEqual(core.apply_supplement(empty, self.base, no_questions, PUBLIC)["chains"], self.base["chains"])

    def test_refinement_only_adds_evidence_or_conditions_without_changing_original(self):
        value = empty_supplement()
        value["refinements"] = [refinement()]
        value["question_responses"][0].update(outcome="refined_existing", record_ids=["refine_1"])
        combined = core.apply_supplement(value, self.base, questions(), PUBLIC)
        state = self.state(verification(combined), combined)
        self.assertEqual(combined["chains"], self.base["chains"])
        self.assertEqual(combined["rules"], self.base["rules"])
        self.assertEqual(state["refinements"][0]["status"], "supported")
        self.assertFalse(state["refinements"][0]["applied_to_original"])
        self.assertEqual(state["refinements"][0]["asserted_dimensions"], ["support"])

    def test_each_stage_returns_copies_and_does_not_mutate_inputs(self):
        q, value, public = questions(), supplement(), copy.deepcopy(PUBLIC)
        originals = copy.deepcopy((self.base, q, value, public))
        checked_q = core.validate_questions(q, self.base, public)
        combined = core.apply_supplement(value, self.base, checked_q, public)
        check = verification(combined)
        before_check = copy.deepcopy(check)
        state = self.state(check, combined)
        before_state = copy.deepcopy(state)
        core.read_rules(state, context())
        self.assertEqual((self.base, q, value, public), originals)
        self.assertEqual(check, before_check)
        self.assertEqual(state, before_state)
        combined["chains"][0]["claim"] = "mutated return only"
        self.assertEqual(self.base["chains"][0]["claim"], originals[0]["chains"][0]["claim"])

    def test_limits_three_questions_two_chains_two_refinements(self):
        q = questions()
        q["questions"] *= 4
        with self.assertRaisesRegex(core.SchemaError, "three"):
            core.validate_questions(q, self.base, PUBLIC)
        for field in ("new_chains", "new_rules", "refinements"):
            value = supplement()
            value[field] = [refinement() if field == "refinements" else value[field][0]] * 3
            with self.subTest(field=field), self.assertRaisesRegex(core.SchemaError, "at most 2"):
                core.apply_supplement(value, self.base, questions(), PUBLIC)

    def test_response_links_cover_every_question_and_added_record(self):
        for case in ("missing_record_link", "missing_response", "false_covered", "unresolved_with_record"):
            value = supplement()
            if case == "missing_record_link":
                value["question_responses"][0]["record_ids"] = []
            elif case == "missing_response":
                value["question_responses"] = []
            elif case == "false_covered":
                value["question_responses"][0]["covered_chain_ids"] = ["absent"]
            else:
                value["question_responses"][0]["outcome"] = "unresolved"
            with self.subTest(case=case), self.assertRaises(core.SchemaError):
                core.apply_supplement(value, self.base, questions(), PUBLIC)

    def test_second_supplement_cannot_overwrite_first_pass(self):
        for value in (supplement(), empty_supplement()):
            combined = core.apply_supplement(value, self.base, questions(), PUBLIC)
            with self.assertRaisesRegex(core.SchemaError, "earlier pass"):
                core.apply_supplement(empty_supplement(), combined, questions(), PUBLIC)

    def test_chart_and_task_evidence_channels_and_exact_public_leaf(self):
        raw = initial(count=1)
        raw["chains"][0]["observations"] = [copy.deepcopy(TASK)]
        with self.assertRaisesRegex(core.SchemaError, "observations must cite"):
            core.import_initial(raw, PUBLIC)
        for path, content in (("/user_goal", "fabricated goal"), ("/policy_tables", []), ("/missing", "anything")):
            raw = initial(count=1)
            raw["chains"][0]["task_evidence"] = [{"ref": "public_task", "path": path, "content": content}]
            with self.subTest(path=path), self.assertRaises(core.SchemaError):
                core.import_initial(raw, PUBLIC)

    def test_public_json_pointer_escaping_and_scalar_types_are_preserved(self):
        public = {"a/b": {"~": [True, 1, None]}}
        self.assertEqual(core.public_leaf_paths(public), {"/a~1b/~0/0": True, "/a~1b/~0/1": 1, "/a~1b/~0/2": None})

    def test_hidden_data_and_external_evidence_sources_are_rejected(self):
        for key in ("hidden", "gold", "ground_truth", "evaluation_hidden_from_agent", "source_csv"):
            with self.subTest(key=key), self.assertRaisesRegex(core.SchemaError, "private keys"):
                core.import_initial(self.raw, dict(PUBLIC, **{key: "secret"}))
            raw = initial()
            raw["chains"][0][key] = "secret"
            with self.assertRaisesRegex(core.SchemaError, "private keys"):
                core.import_initial(raw, PUBLIC)
        checked = verification(self.base, b_status="supported")
        checked["chain_checks"][0]["B_applicability"]["evidence"] = [
            {"ref": "hidden_answer", "path": "/correct_value", "content": "Route A"}]
        with self.assertRaisesRegex(core.SchemaError, "unknown evidence"):
            core.validate_verification(checked, self.base, PUBLIC)

    def test_competing_conditionals_can_both_be_valid_with_unknown_applicability(self):
        checked = verification(self.base)
        state = self.state(checked)
        self.assertEqual([r["status"] for r in state["rules"]], ["pending", "pending"])
        self.assertEqual([a["grounding"] for a in state["chain_assessments"]], ["conditional_candidate"] * 2)
        self.assertEqual(state["chains"], self.base["chains"])
        self.assertFalse(any(r["usable"] for r in core.read_rules(state, context())["rules"]))
        self.assertFalse(state["action_authorized"])

    def test_refuted_applicability_does_not_invalidate_conditional_inference(self):
        state = self.state(verification(self.base, b_status="refuted"))
        self.assertEqual(state["rules"][0]["status"], "revoked")
        assessment = state["chain_assessments"][0]
        self.assertEqual(assessment["grounding"], "contradicted_premises")
        self.assertEqual(assessment["check"]["conditional_inference"]["status"], "valid")
        self.assertEqual(assessment["claim"], self.raw["chains"][0]["claim"])

    def test_O_refutation_does_not_revoke_supported_B(self):
        state = self.state(verification(self.base, b_status="supported", o_status="refuted"))
        self.assertEqual(state["rules"][0]["status"], "active")
        self.assertEqual(state["chain_assessments"][0]["grounding"], "contradicted_premises")
        self.assertFalse(state["chain_assessments"][0]["action_authorized"])

    def test_undetermined_O_is_preserved_separately_from_supported_B(self):
        state = self.state(verification(self.base, b_status="supported", o_status="undetermined"))
        self.assertEqual(state["rules"][0]["status"], "active")
        self.assertEqual(state["chain_assessments"][0]["grounding"], "conditional_candidate")
        self.assertEqual(state["chain_assessments"][0]["check"]["O"]["status"], "undetermined")

    def test_incomplete_and_invalid_inference_never_replace_or_negate_C(self):
        for status, missing in (("incomplete", ["A comparison premise was not stated."]), ("invalid", [])):
            checked = verification(self.base)
            checked["chain_checks"][0]["conditional_inference"].update(status=status, missing_premises=missing)
            state = self.state(checked)
            self.assertEqual(state["chains"], self.base["chains"])
            self.assertEqual(state["chain_assessments"][0]["grounding"], status + "_inference")
            self.assertNotIn("negated_claim", state["chain_assessments"][0])

    def test_verifier_requires_exact_full_chain_and_refinement_coverage(self):
        value = empty_supplement()
        value["refinements"] = [refinement()]
        value["question_responses"][0].update(outcome="refined_existing", record_ids=["refine_1"])
        combined = core.apply_supplement(value, self.base, questions(), PUBLIC)
        for field in ("chain_checks", "refinement_checks"):
            checked = verification(combined)
            checked[field].pop()
            with self.subTest(field=field), self.assertRaisesRegex(core.SchemaError, "every"):
                core.validate_verification(checked, combined, PUBLIC)

    def test_definite_premise_judgments_need_actual_evidence(self):
        for dimension in ("O", "B_applicability"):
            checked = verification(self.base, b_status="supported")
            checked["chain_checks"][0][dimension]["evidence"] = []
            with self.subTest(dimension=dimension), self.assertRaisesRegex(core.SchemaError, "evidence reference"):
                self.state(checked)

    def test_conditional_inference_cannot_borrow_rival_premises(self):
        for refs in (["chain:base_c2", "rule:r1"], ["chain:base_c1", "rule:r2"],
                     ["chain:base_c1"], ["chain:base_c1", "rule:r1", "public_task:/user_goal"]):
            checked = verification(self.base)
            checked["chain_checks"][0]["conditional_inference"]["premise_ids"] = refs
            with self.subTest(refs=refs), self.assertRaises(core.SchemaError):
                self.state(checked)

    def test_missing_premise_contract_is_independent_of_applicability(self):
        for status, missing in (("incomplete", []), ("valid", ["Missing mapping"]), ("invalid", ["Missing mapping"])):
            checked = verification(self.base)
            checked["chain_checks"][0]["conditional_inference"].update(status=status, missing_premises=missing)
            with self.subTest(status=status), self.assertRaises(core.SchemaError):
                self.state(checked)

    def test_old_or_mixed_verification_schemas_are_rejected(self):
        for schema in ("explanation_verification_v1", "explanation_verification_v2", None):
            checked = verification(self.base)
            checked["schema_version"] = schema
            with self.subTest(schema=schema), self.assertRaisesRegex(core.SchemaError, "explanation_verification_v3"):
                self.state(checked)
        for field in ("B", "implication"):
            checked = verification(self.base)
            checked["chain_checks"][0][field] = support("supported")
            with self.assertRaisesRegex(core.SchemaError, "legacy"):
                self.state(checked)

    def test_v2_adapter_does_not_modify_legacy_module_globals(self):
        old_import, old_chain = core._v1.import_initial, core._v1._chain
        old_schema = core._v2.COMPLETION_SCHEMA
        state = self.state(verification(self.base))
        self.assertIs(core._v1.import_initial, old_import)
        self.assertIs(core._v1._chain, old_chain)
        self.assertEqual(core._v2.COMPLETION_SCHEMA, old_schema)
        self.assertEqual(state["verification_schema"], core.VERIFICATION_SCHEMA)

    def test_shared_B_disagreement_is_not_majority_voted(self):
        base = core.import_initial(initial(shared=True), PUBLIC)
        checked = verification(base, b_status="supported")
        checked["chain_checks"][1]["B_applicability"] = support("undetermined")
        self.assertEqual(self.state(checked, base)["rules"][0]["status"], "disputed")

    def test_save_is_exclusive_reload_preserves_unverified_candidates(self):
        state = self.state()
        self.assertTrue(all(r["status"] == "pending" for r in state["rules"]))
        self.assertTrue(all(a["grounding"] == "unverified" for a in state["chain_assessments"]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            core.save_state(path, state)
            self.assertEqual(core.load_state(path), state)
            with self.assertRaises(FileExistsError):
                core.save_state(path, state)

    def test_old_stored_state_is_not_implicitly_migrated(self):
        for schema in ("task_rule_state_v1", "task_rule_state_v2"):
            state = self.state()
            state["schema_version"] = schema
            with self.subTest(schema=schema), self.assertRaisesRegex(core.SchemaError, "not migrated"):
                core.read_rules(state, context())
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "old.json"
                with path.open("w", encoding="utf-8") as stream:
                    json.dump(state, stream)
                with self.assertRaisesRegex(core.SchemaError, "not migrated"):
                    core.load_state(path)

    def test_scope_matching_remains_independent_from_rule_status(self):
        state = self.state(verification(self.base, b_status="supported"))
        view = core.read_rules(state, context())
        self.assertTrue(all(r["usable"] for r in view["rules"]))
        self.assertFalse(view["action_authorized"])
        for key, replacement in (("task_id", "other"), ("chart_ref", "sha256:other"),
                                 ("components", ["legend"]), ("conditions", {"r1": False})):
            wrong = dict(context(), **{key: replacement})
            self.assertEqual(core.read_rules(state, wrong)["rules"][0]["applicability"], "inapplicable")
        self.assertEqual(core.read_rules(state, {})["rules"][0]["applicability"], "unknown")
        with self.assertRaisesRegex(core.SchemaError, "concrete image"):
            core.build_rule_state(self.base, None, "task_x", "chart_1", PUBLIC)

    def test_prompt_contract_has_four_stages_and_no_generation_logic_warnings(self):
        self.assertEqual(set(prompts.PROMPTS), {"generation", "questions", "supplement", "verification"})
        for stage in ("generation", "questions", "supplement"):
            prompt = prompts.PROMPTS[stage]
            self.assertNotIn('"claim_kind":', prompt)
            self.assertNotIn("counterexample", prompt)
            self.assertNotIn("does not imply not-C", prompt)
            self.assertNotIn("contradictory premises", prompt.lower())
        self.assertIn("unresolved_questions", prompts.GENERATOR)
        self.assertIn('"relationship":"compatible|competing"', prompts.SUPPLEMENT)
        self.assertIn("counterexample", prompts.VERIFY)
        self.assertIn("B_applicability", prompts.VERIFY)


if __name__ == "__main__":
    unittest.main()
