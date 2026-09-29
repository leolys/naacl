from __future__ import annotations

import unittest

from ..run_agentic_recovery_baselines import (
    action_from_model,
    assert_prompt_safe,
    earliest_harmful_index,
    extract_json_object,
    normalized_snapshot,
)


class AgenticRecoveryBaselineTests(unittest.TestCase):
    def test_extracts_first_json_object_from_fenced_response(self) -> None:
        self.assertEqual(
            extract_json_object('analysis\n```json\n{"action":"revise"}\n```'),
            {"action": "revise"},
        )

    def test_choice_position_maps_only_to_visible_position(self) -> None:
        self.assertEqual(
            action_from_model(
                {"action": "choose", "choice_position": 2},
                ["choose:0", "choose:1", "finish"],
            ),
            "choose:1",
        )
        with self.assertRaises(ValueError):
            action_from_model(
                {"action": "choose", "choice_position": 3},
                ["choose:0", "choose:1", "finish"],
            )

    def test_choice_proposal_on_review_uses_visible_revise_control(self) -> None:
        output = {"action": "choose", "choice_position": 1}
        self.assertEqual(
            action_from_model(output, ["revise", "confirm", "finish"]),
            "revise",
        )
        self.assertEqual(output["executor_adapter"]["executed"], "revise")

    def test_second_rebinding_attempt_is_not_executed(self) -> None:
        output = {"action": "choose", "choice_position": 1}
        self.assertIsNone(
            action_from_model(output, ["confirm", "finish"]),
        )
        self.assertIsNone(output["executor_adapter"]["executed"])
        self.assertTrue(output["executor_adapter"]["invalid_visible_action"])

    def test_second_revision_attempt_is_not_executed(self) -> None:
        output = {"action": "revise"}
        self.assertIsNone(
            action_from_model(output, ["confirm", "finish"]),
        )
        self.assertEqual(output["executor_adapter"]["proposed"], "revise")
        self.assertIsNone(output["executor_adapter"]["executed"])
        self.assertTrue(output["executor_adapter"]["invalid_visible_action"])

    def test_known_but_invisible_actions_are_not_executed(self) -> None:
        retry_output = {"action": "revise"}
        self.assertIsNone(
            action_from_model(
                retry_output,
                ["choose:0", "choose:1", "choose:2", "finish"],
            )
        )
        self.assertTrue(
            retry_output["executor_adapter"]["invalid_visible_action"]
        )

        decision_output = {"action": "confirm"}
        self.assertIsNone(
            action_from_model(
                decision_output,
                ["choose:0", "choose:1", "choose:2", "finish"],
            )
        )
        self.assertTrue(
            decision_output["executor_adapter"]["invalid_visible_action"]
        )

    def test_prompt_leak_guard_rejects_runner_truth(self) -> None:
        assert_prompt_safe("visible screenshots only")
        with self.assertRaisesRegex(ValueError, "runner-only"):
            assert_prompt_safe("use expected_action_id")

    def test_snapshot_normalization_excludes_render_counters(self) -> None:
        result = normalized_snapshot(
            {
                "visible_state": "review",
                "current_choice_token": "choice_1",
                "current_control_position": 1,
                "selection_count": 1,
                "reversal_count": 0,
                "submitted": False,
                "chart_sha256": "abc",
                "render_count": 99,
                "chart_delivery_count": 7,
            }
        )
        self.assertNotIn("render_count", result)
        self.assertNotIn("chart_delivery_count", result)

    def test_harmful_index_is_posthoc_and_uses_role_mapping(self) -> None:
        case = {
            "model_visible_shared": {
                "action_cards": [
                    {"choice_token": "choice_a"},
                    {"choice_token": "choice_b"},
                ]
            },
            "runner_only": {
                "choice_token_to_action_id": {
                    "choice_a": "opaque_a",
                    "choice_b": "opaque_b",
                },
                "roles_by_action_id": {
                    "opaque_a": "correct",
                    "opaque_b": "misleading",
                },
            },
        }
        self.assertEqual(earliest_harmful_index(case, ["choose:1", "confirm"]), 0)
        self.assertIsNone(earliest_harmful_index(case, ["choose:0", "confirm"]))
        self.assertEqual(earliest_harmful_index(case, ["choose:0", "finish"]), 1)


if __name__ == "__main__":
    unittest.main()
