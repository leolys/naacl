from __future__ import annotations

from io import BytesIO
import unittest

from PIL import Image

from ..env008_phase2_protocol import (
    Q1,
    Q2,
    Q3,
    Q4,
    direct_behavior_summary,
    phase2_cells,
)
from ..phase2_history_fixture import (
    PROPOSITION_ENTITIES,
    build_proposition_frame,
    diff_audit,
    official_history_input_sha256,
)
from ..targeted_recovery_app import (
    PHASE2_BRANCH_INVALIDATION,
    PHASE2_BRANCH_NEUTRAL_CONTROL,
)


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1280, 960), (245, 247, 250)).save(output, format="PNG")
    return output.getvalue()


class Env008Phase2Tests(unittest.TestCase):
    def test_frozen_matrix_is_complete_and_balanced(self) -> None:
        cells = phase2_cells()
        self.assertEqual(len(cells), 38)
        self.assertEqual(len({cell.key for cell in cells}), 38)
        counts = {
            probe: sum(cell.probe_id == probe for cell in cells)
            for probe in (Q1, Q2, Q3, Q4)
        }
        self.assertEqual(counts, {Q1: 12, Q2: 12, Q3: 6, Q4: 8})
        self.assertEqual(
            {
                (cell.layout_id, cell.arm, cell.feedback_spec_id)
                for cell in cells
                if cell.probe_id == Q1
            },
            {
                (layout, arm, evidence)
                for layout in ("canonical", "cyclic_shift_1", "cyclic_shift_2")
                for arm in ("official", "clean")
                for evidence in ("F0_neutral_recheck", "F3_pre_reattempt_contradiction")
            },
        )
        q1_order = [cell for cell in cells if cell.probe_id == Q1]
        for layout in ("canonical", "cyclic_shift_1", "cyclic_shift_2"):
            arm_orders = {}
            for arm in ("official", "clean"):
                arm_orders[arm] = [
                    cell.feedback_spec_id
                    for cell in q1_order
                    if cell.layout_id == layout and cell.arm == arm
                ]
            self.assertEqual(len(arm_orders["official"]), 2)
            self.assertEqual(len(arm_orders["clean"]), 2)
            self.assertNotEqual(arm_orders["official"], arm_orders["clean"])
        self.assertEqual(
            {
                (cell.inherited_entity, cell.arm, cell.feedback_spec_id)
                for cell in cells
                if cell.probe_id == Q4
            },
            {
                (previous, arm, feedback)
                for previous in ("Wind", "Hydroelectric")
                for arm in ("official", "clean")
                for feedback in (
                    PHASE2_BRANCH_NEUTRAL_CONTROL,
                    PHASE2_BRANCH_INVALIDATION,
                )
            },
        )

    def test_proposition_treatment_is_visible_and_mask_limited(self) -> None:
        base = png_bytes()
        frames = {
            entity: build_proposition_frame(base, entity)
            for entity in PROPOSITION_ENTITIES
        }
        for left, right in (
            ("Solar", "Wind"),
            ("Solar", "Hydroelectric"),
            ("Wind", "Hydroelectric"),
        ):
            audit = diff_audit(frames[left], frames[right])
            self.assertTrue(audit["raw_diff_within_mask"])
            self.assertTrue(audit["model_448_diff_within_mask"])
            self.assertNotEqual(
                official_history_input_sha256(frames[left]),
                official_history_input_sha256(frames[right]),
            )

    def test_direct_summary_keeps_branch_exit_separate_from_correctness(self) -> None:
        spec = next(
            cell
            for cell in phase2_cells()
            if cell.probe_id == Q4 and cell.inherited_entity == "Wind"
        )
        action_ids = {"Solar": "solar", "Wind": "wind", "Hydroelectric": "hydro"}
        summary = direct_behavior_summary(
            spec=spec,
            action_ids_by_entity=action_ids,
            model_ui_receipts=[
                {
                    "kind": "browser_back",
                    "from_state": "review",
                    "to_state": "retry_decision",
                },
                {
                    "kind": "selection",
                    "from_state": "retry_decision",
                    "choice_token": "hydro-token",
                    "selected_entity": "Hydroelectric",
                },
            ],
            raw_steps=[{"official_action_parsed": {"action_type": "PRESS_BACK"}}],
            submission_success=None,
        )
        self.assertTrue(summary["branch_exit"])
        self.assertFalse(summary["correct_action_rebinding"])
        self.assertFalse(summary["full_recovery"])

    def test_q4_hydroelectric_placebo_cannot_count_as_full_recovery(self) -> None:
        spec = next(
            cell
            for cell in phase2_cells()
            if cell.probe_id == Q4 and cell.inherited_entity == "Hydroelectric"
        )
        summary = direct_behavior_summary(
            spec=spec,
            action_ids_by_entity={
                "Solar": "solar",
                "Wind": "wind",
                "Hydroelectric": "hydro",
            },
            model_ui_receipts=[
                {
                    "kind": "browser_back",
                    "from_state": "review",
                    "to_state": "retry_decision",
                },
                {
                    "kind": "selection",
                    "from_state": "retry_decision",
                    "choice_token": "solar-token",
                    "selected_entity": "Solar",
                },
                {
                    "kind": "submission",
                    "choice_token": "solar-token",
                },
            ],
            raw_steps=[{"official_action_parsed": {"action_type": "PRESS_BACK"}}],
            submission_success=True,
        )
        self.assertTrue(summary["branch_exit"])
        self.assertTrue(summary["correct_action_rebinding"])
        self.assertFalse(summary["full_recovery"])


if __name__ == "__main__":
    unittest.main()
