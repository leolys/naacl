import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("alt_conclusion_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schemas = load("schemas")
prompts = load("prompts")


def chain(cid="c1", label="Route A", claim="Choose Route A under this reading."):
    return {"id": cid, "O": [{"location": "upper chart", "content": "A mark is blue."}],
            "B": {"rule": "If blue represents the requested category, choose its item.",
                  "conditions": ["The displayed mapping applies."]},
            "C": {"claim": claim, "option_label": label}}


def question(qid="q1"):
    return {"id": qid, "question": "Could the other visible mark support another task action?"}


def check(cid="c1"):
    return {"chain_id": cid, "O_status": "supported", "B_status": "uncertain",
            "inference": "valid", "reason": "O is visible; B is unestablished; C follows conditionally.",
            "visible_evidence": ["upper chart: blue mark"]}


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.context = {"options": ["Route A", "Route B"], "initial_chains": [chain()],
                        "questions": [question()], "chains": [chain()]}

    def reject(self, stage, data, context=None):
        with self.assertRaises(schemas.ValidationError):
            schemas.validate(stage, data, self.context if context is None else context)

    def test_initial_nonmutating(self):
        data = {"chains": [chain()], "notes": "One conditional reading."}
        saved = copy.deepcopy(data)
        self.assertIs(schemas.validate("initial", data, self.context), data)
        self.assertEqual(data, saved)

    def test_zero_initial_allowed(self):
        schemas.validate("initial", {"chains": [], "notes": "No complete candidate formed."}, self.context)

    def test_initial_limit(self):
        self.reject("initial", {"chains": [chain("c" + str(i)) for i in range(4)], "notes": "x"})

    def test_initial_duplicate(self):
        self.reject("initial", {"chains": [chain(), chain()], "notes": "x"})

    def test_option_exact(self):
        self.reject("initial", {"chains": [chain(label="route a")], "notes": "x"})

    def test_null_conclusion_allowed(self):
        schemas.validate("initial", {"chains": [chain(label=None, claim="A is not largest.")],
                                     "notes": "Concrete negative candidate."}, self.context)

    def test_no_semantic_keyword_filter(self):
        schemas.validate("initial", {"chains": [chain(claim="A is unknown or blue.")],
                                     "notes": "A semantic defect is not a syntax defect."}, self.context)

    def test_no_hidden_answer_fields(self):
        data = {"chains": [chain()], "notes": "x", "gold": "Route A"}
        self.reject("initial", data)

    def test_observation_required(self):
        item = chain()
        item["O"] = []
        self.reject("initial", {"chains": [item], "notes": "x"})

    def test_blank_text_rejected(self):
        self.reject("initial", {"chains": [chain(claim=" ")], "notes": "x"})

    def test_options_contract(self):
        self.reject("initial", {"chains": [], "notes": "x"}, {"options": [{"label": "Route A"}]})

    def test_old_and_new_question_shape_equal(self):
        self.assertEqual(schemas.SCHEMAS["questions_old"], schemas.SCHEMAS["questions_new"])
        for stage in ("questions_old", "questions_new"):
            schemas.validate(stage, {"questions": [], "summary": "Already covered."}, self.context)
            schemas.validate(stage, {"questions": [question()], "summary": "One search."}, self.context)

    def test_question_limit_and_unique(self):
        self.reject("questions_new", {"questions": [question(), question()], "summary": "x"})
        self.reject("questions_new", {"questions": [question(str(i)) for i in range(3)], "summary": "x"})

    def supplement(self, added=None, outcome="new_chain", refs=None):
        return {"new_chains": [chain("n1")] if added is None else added,
                "question_responses": [{"question_id": "q1", "outcome": outcome,
                                        "new_chain_ids": ["n1"] if refs is None else refs, "reason": "x"}]}

    def test_same_conclusion_allowed_new_basis(self):
        data = self.supplement()
        data["new_chains"][0]["B"]["rule"] = "A distinct mapping could lead to the same action."
        schemas.validate("supplement", data, self.context)

    def test_no_addition_allowed(self):
        for outcome in ("already_covered", "no_grounded_candidate"):
            schemas.validate("supplement", self.supplement([], outcome, []), self.context)

    def test_zero_questions_no_additions(self):
        context = dict(self.context, questions=[])
        schemas.validate("supplement", {"new_chains": [], "question_responses": []}, context)
        self.reject("supplement", {"new_chains": [chain("n1")], "question_responses": []}, context)

    def test_collision_rejected(self):
        self.reject("supplement", self.supplement([chain("c1")], refs=["c1"]))

    def test_unknown_question_rejected(self):
        data = self.supplement()
        data["question_responses"][0]["question_id"] = "q9"
        self.reject("supplement", data)

    def test_missing_response_rejected(self):
        self.reject("supplement", {"new_chains": [], "question_responses": []})

    def test_unknown_chain_reference_rejected(self):
        self.reject("supplement", self.supplement(refs=["n9"]))

    def test_unlinked_chain_rejected(self):
        self.reject("supplement", self.supplement([chain("n1"), chain("n2")]))

    def test_outcome_reference_mismatch(self):
        self.reject("supplement", self.supplement(outcome="already_covered"))
        self.reject("supplement", self.supplement([], refs=[]))

    def test_duplicate_response_and_reference(self):
        data = self.supplement()
        data["question_responses"].append(copy.deepcopy(data["question_responses"][0]))
        self.reject("supplement", data)
        self.reject("supplement", self.supplement(refs=["n1", "n1"]))

    def test_many_questions_can_share_added_chain(self):
        context = dict(self.context, questions=[question(), question("q2")])
        data = self.supplement()
        data["question_responses"].append(dict(data["question_responses"][0], question_id="q2"))
        schemas.validate("supplement", data, context)

    def test_verify_exact_coverage(self):
        data = {"checks": [check()], "summary": "No winner selected."}
        schemas.validate("verify", data, self.context)
        self.reject("verify", {"checks": [], "summary": "x"})
        self.reject("verify", {"checks": [check("n1")], "summary": "x"})
        self.reject("verify", {"checks": [check(), check()], "summary": "x"})

    def test_verify_empty_candidates(self):
        schemas.validate("verify", {"checks": [], "summary": "No candidates."},
                         dict(self.context, chains=[]))

    def test_independent_judgments_not_linked_by_code(self):
        item = check()
        item.update(O_status="refuted", B_status="uncertain", inference="valid")
        schemas.validate("verify", {"checks": [item], "summary": "Conditional inference only."}, self.context)

    def test_verify_cannot_return_new_claim(self):
        item = check()
        item["claim"] = "Rewritten C"
        self.reject("verify", {"checks": [item], "summary": "x"})

    def test_unknown_stage(self):
        self.reject("winner", {})


class PromptTests(unittest.TestCase):
    def test_stages_match(self):
        self.assertEqual(set(prompts.PROMPTS), set(schemas.SCHEMAS))

    def test_no_task_specific_entities(self):
        combined = "\n".join(prompts.PROMPTS.values()).lower()
        for forbidden in ("pub001", "pub013", "b001", "b002", "illinois", "apple", "firefox"):
            self.assertNotIn(forbidden, combined)

    def test_new_search_not_old_interrogation(self):
        self.assertIn("Starting from a plausible DIFFERENT concrete task", prompts.QUESTIONS_NEW)
        self.assertIn("NOT to", prompts.QUESTIONS_NEW)
        self.assertIn("questions=[]", prompts.QUESTIONS_NEW)
        self.assertIn("omitted observations, rule conditions", prompts.QUESTIONS_OLD)

    def test_same_common_boundary(self):
        for prompt in prompts.PROMPTS.values():
            self.assertTrue(prompt.endswith(prompts.COMMON))
        self.assertIn("not merely assume the desired C", " ".join(prompts.COMMON.split()))
        self.assertIn("does not itself invalidate", " ".join(prompts.VERIFY.split()))


if __name__ == "__main__":
    unittest.main()
