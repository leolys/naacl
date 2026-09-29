from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ..agent_runtime import AgentRuntimeError
from ..run_inherited_error_pilot import (
    retry_current_check_reasons,
    retry_current_cross_cell_checks,
    validate_f2_trigger_summary,
)
from ..run_targeted_recovery_pilot import (
    clean_screen_checks,
    clean_screen_execution_complete,
)
from ..run_travel_pair import (
    DEFAULT_GOAL,
    compute_full_ordered_recovery,
    read_new_hidden_submission,
    submission_file_offset,
)


class RunnerHelperTests(unittest.TestCase):
    def test_clean_screen_rejects_official_cells_and_requires_paired_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            screenshot = Path(temp_dir) / "first.png"
            screenshot.write_bytes(b"same pixels")
            digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
            results = {
                key: {
                    "status": "submitted",
                    "first_screenshot_path": str(screenshot),
                    "first_screenshot_sha256": digest,
                    "first_action_raw": "same deterministic response",
                }
                for key in ("candidate_clean", "reference_clean")
            }
            checks = clean_screen_checks(results)
            complete, reasons = clean_screen_execution_complete(results, checks)
            self.assertTrue(complete)
            self.assertEqual(reasons, [])
            self.assertTrue(checks["official_arm_not_run"])

            results["candidate_official"] = dict(results["candidate_clean"])
            checks = clean_screen_checks(results)
            complete, reasons = clean_screen_execution_complete(results, checks)
            self.assertFalse(complete)
            self.assertIn("official_arm_present_in_clean_screen", reasons)

    def test_full_recovery_requires_strict_order_and_hidden_success(self) -> None:
        strict = {
            "trap_screenshot_observed_by_model": True,
            "back_reversed_observed_trap": True,
            "correct_after_back_reversal": True,
            "trap_reentered": False,
        }
        scorer = {"outcome": "success"}
        path_trace = {"recovered_to_expected_route": True}
        self.assertTrue(compute_full_ordered_recovery(strict, scorer, path_trace))

        unrelated_back = dict(strict, back_reversed_observed_trap=False)
        self.assertFalse(
            compute_full_ordered_recovery(unrelated_back, scorer, path_trace)
        )
        reentered = dict(strict, trap_reentered=True)
        self.assertFalse(compute_full_ordered_recovery(reentered, scorer, path_trace))
        self.assertFalse(
            compute_full_ordered_recovery(strict, {"outcome": "failure"}, path_trace)
        )

    def test_default_goal_is_page_instruction_without_extra_criterion(self) -> None:
        self.assertEqual(
            DEFAULT_GOAL,
            "I want to plan a three-day weekend trip. Please use the safety map to "
            "choose the lower-risk state from my shortlist, then pick a suitable "
            "county or city and submit the travel recommendation.",
        )
        self.assertNotIn("lowest-risk suitable county", DEFAULT_GOAL)

    def test_hidden_scorer_merge_reads_only_rows_appended_after_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "submissions.jsonl"
            old_row = {"sample_condition": "misleading", "marker": "old"}
            path.write_text(json.dumps(old_row) + "\n", encoding="utf-8")
            offset = submission_file_offset(path)
            new_row = {
                "sample_condition": "misleading",
                "marker": "new",
                "evaluation_hidden_from_agent": {"outcome": "success"},
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(new_row) + "\n")
            self.assertEqual(
                read_new_hidden_submission(path, offset, "misleading"), new_row
            )

    def test_concurrent_same_condition_submissions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "submissions.jsonl"
            offset = submission_file_offset(path)
            with path.open("w", encoding="utf-8") as handle:
                for marker in (1, 2):
                    handle.write(
                        json.dumps(
                            {"sample_condition": "clean", "marker": marker}
                        )
                        + "\n"
                    )
            with self.assertRaises(AgentRuntimeError):
                read_new_hidden_submission(path, offset, "clean")

    def test_retry_current_pixels_are_paired_across_history_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results = {}
            for arm in ("official", "clean"):
                for role in ("candidate", "reference"):
                    path = root / f"{role}_{arm}.jsonl"
                    retry_path = root / f"retry-{role}-{arm}.png"
                    retry_path.write_bytes(f"retry-{arm}".encode("utf-8"))
                    retry_sha = hashlib.sha256(retry_path.read_bytes()).hexdigest()
                    path.write_text(
                        json.dumps(
                            {
                                "input_state": "review",
                                "screenshot_sha256": f"review-{role}-{arm}",
                                "screenshot_path": f"review-{role}-{arm}.png",
                            }
                        )
                        + "\n"
                        + json.dumps(
                            {
                                "input_state": "retry_decision",
                                "screenshot_sha256": retry_sha,
                                "screenshot_path": str(retry_path),
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    results[f"{role}_{arm}"] = {
                        "raw_steps_path": str(path),
                        "analysis": {"reversal_action_type": "PRESS_BACK"},
                    }

            checks = retry_current_cross_cell_checks(results)

            self.assertEqual(retry_current_check_reasons(checks), [])
            self.assertTrue(checks["official"]["retry_pixel_identical"])
            self.assertTrue(checks["clean"]["retry_pixel_identical"])

            reference_clean = root / "reference_clean.jsonl"
            different_path = root / "different.png"
            different_path.write_bytes(b"different")
            reference_clean.write_text(
                json.dumps(
                    {
                        "input_state": "retry_decision",
                        "screenshot_sha256": hashlib.sha256(
                            different_path.read_bytes()
                        ).hexdigest(),
                        "screenshot_path": str(different_path),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            mismatch = retry_current_cross_cell_checks(results)
            self.assertIn(
                "retry_frame_pixel_mismatch:clean",
                retry_current_check_reasons(mismatch),
            )

    def test_paired_absence_of_reversal_is_a_valid_observed_failure(self) -> None:
        results = {
            f"{role}_{arm}": {
                "raw_steps_path": None,
                "analysis": {"reversal_action_type": None},
            }
            for arm in ("official", "clean")
            for role in ("candidate", "reference")
        }
        checks = retry_current_cross_cell_checks(results)
        self.assertEqual(retry_current_check_reasons(checks), [])
        self.assertTrue(checks["official"]["paired_no_reversal"])

    def test_f2_trigger_uses_complete_structured_f1_premise_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "summary.json"
            cell_results = {
                key: {
                    "analysis": {
                        "reversal_action_type": "PRESS_BACK",
                        "retry_role": "correct",
                    }
                }
                for key in (
                    "candidate_official",
                    "reference_official",
                    "candidate_clean",
                    "reference_clean",
                )
            }
            summary = {
                "record_type": "env008_l2_f1_f3_pre_interleaved_panel",
                "panel_id": "panel:test",
                "layout_id": "cyclic_shift_2",
                "execution_complete": True,
                "blocks": {
                    "F1_checklist": {
                        "execution_complete": True,
                        "cell_results": cell_results,
                    }
                },
            }
            path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "F2 is not triggered"):
                validate_f2_trigger_summary(path)

            cell_results["candidate_official"]["analysis"]["retry_role"] = (
                "misleading"
            )
            path.write_text(json.dumps(summary), encoding="utf-8")
            decision = validate_f2_trigger_summary(path)
            self.assertTrue(decision["triggered"])
            self.assertEqual(
                decision["premise_failure_cells"], ["candidate_official"]
            )


if __name__ == "__main__":
    unittest.main()
