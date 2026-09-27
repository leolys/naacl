import copy
import unittest

from engine import RuleStore, assert_public, normalized_candidates, validate_verification, parse_json


def fixture():
    rules = [{"id": "x", "text": "Position relates to ticks on this axis", "component": "axis", "conditions": "same axis"}]
    chains = [{"rule_id": "x", "observations": [{"ref": "chart_1", "location": "axis", "content": "ticks visible"}],
               "option_label": "Route A", "claim": "meets task"}]
    candidates = normalized_candidates({"rules": rules, "chains": chains}, ["Route A", "Route B"])
    verdict = {"checks": [{"chain_id": "c1", "O": "supported", "B": "supported", "implication": "supported",
                "evidence": [{"ref": "chart_1", "location": "axis", "content": "tick mapping"}], "reason": "axis supports relation"}],
                "recommendation": "Route A", "unresolved_reason": ""}
    return candidates, verdict


class EngineTests(unittest.TestCase):
    def test_complete_json_with_only_trailing_closers(self):
        log = []
        self.assertEqual(parse_json('{"rules": [], "chains": []}]}', True, log), {"rules": [], "chains": []})
        self.assertEqual(log[0]["ignored_suffix"], "]}")
        with self.assertRaises(ValueError):
            parse_json('{"a": 1}]}')
        for bad in ('{"a": 1} {"a": 2}', '{"a": 1} explanation', '{"a":', '[1]]', '{"a": 1}[', '{"a": 1}null', '{"a": 1}]}'):
            with self.assertRaises(ValueError):
                parse_json(bad, True)

    def test_candidate_bound_precedes_dedup_and_does_not_backfill(self):
        c, _ = fixture()
        base = copy.deepcopy(c["chains"][0])
        alternate = {**base, "option_label": "Route B"}
        generated = {"rules": c["rules"], "chains": [base, base, base, alternate]}
        with self.assertRaises(ValueError):
            normalized_candidates(generated, ["Route A", "Route B"])
        bounded = normalized_candidates(generated, ["Route A", "Route B"], cap_by_order=True)
        self.assertEqual(len(bounded["chains"]), 1)
        self.assertEqual(bounded["chains"][0]["option_label"], "Route A")

    def test_private_nested_key_blocked(self):
        with self.assertRaises(ValueError):
            assert_public({"history": [{"gold": "A"}]})

    def test_rule_state_not_action(self):
        c, v = fixture()
        state = RuleStore()
        state.update(c, v)
        self.assertNotIn("option_label", state.records[0])
        self.assertEqual(state.read("chart_1", "task_metric")[0]["match"], "applicable")
        self.assertEqual(state.read("chart_2", "task_metric")[0]["match"], "not_applicable")
        self.assertEqual(state.read(None, "task_metric")[0]["match"], "undetermined")

    def test_refutation_not_automatic_opposite(self):
        c, v = fixture()
        v["checks"][0]["B"] = "refuted"
        result = validate_verification(c, v, ["Route A", "Route B"])
        self.assertIsNone(result["recommendation"])

    def test_unknown_does_not_support_action(self):
        c, v = fixture()
        v["checks"][0]["O"] = "undetermined"
        self.assertIsNone(validate_verification(c, v, ["Route A"]).get("recommendation"))

    def test_revoke_and_reactivate_retain_history(self):
        c, v = fixture()
        store = RuleStore()
        store.update(c, v)
        v["checks"][0]["B"] = "refuted"
        store.update(c, v)
        self.assertTrue(store.invalid_dependencies({"used_rule_ids": ["m1"]}))
        self.assertEqual(store.records[0]["version"], 2)
        self.assertEqual(len(store.records[0]["changes"]), 2)
        v["checks"][0]["B"] = "supported"
        store.update(c, v)
        self.assertEqual(store.records[0]["status"], "active")
        self.assertEqual(len(store.records[0]["changes"]), 3)

    def test_duplicate_not_extra_vote(self):
        c, _ = fixture()
        g = {"rules": c["rules"], "chains": [c["chains"][0], copy.deepcopy(c["chains"][0])]}
        self.assertEqual(len(normalized_candidates(g, ["Route A"])["chains"]), 1)

    def test_all_chains_checked(self):
        c, v = fixture()
        v["checks"] = []
        with self.assertRaises(ValueError):
            validate_verification(c, v, ["Route A"])

    def test_conflicting_fully_supported_choices_abstain(self):
        c, v = fixture()
        chain = copy.deepcopy(c["chains"][0])
        chain.update(chain_id="c2", option_label="Route B")
        c["chains"].append(chain)
        check = copy.deepcopy(v["checks"][0])
        check["chain_id"] = "c2"
        v["checks"].append(check)
        self.assertIsNone(validate_verification(c, v, ["Route A", "Route B"])["recommendation"])

    def test_same_rule_cannot_be_both_supported_and_refuted(self):
        c, v = fixture()
        chain = copy.deepcopy(c["chains"][0])
        chain.update(chain_id="c2", claim="different comparison")
        c["chains"].append(chain)
        check = copy.deepcopy(v["checks"][0])
        check.update(chain_id="c2", B="refuted")
        v["checks"].append(check)
        self.assertIsNone(validate_verification(c, v, ["Route A", "Route B"])["recommendation"])
        store = RuleStore()
        store.update(c, v)
        self.assertEqual(store.records[0]["status"], "disputed")

    def test_actual_page_evidence_is_valid_but_unseen_page_is_not(self):
        c, v = fixture()
        v["checks"][0]["evidence"].append({"ref": "page_00", "location": "task", "content": "public routing requirement"})
        self.assertEqual(validate_verification(c, v, ["Route A"], ["chart_1", "page_00"])["recommendation"], "Route A")
        with self.assertRaises(ValueError):
            validate_verification(c, v, ["Route A"], ["chart_1", "page_01"])
        v["checks"][0]["evidence"] = [v["checks"][0]["evidence"][1]]
        with self.assertRaises(ValueError):
            validate_verification(c, v, ["Route A"], ["chart_1", "page_00"])


if __name__ == "__main__":
    unittest.main()
