from __future__ import annotations

import unittest

from ..trace_metrics import RecoveryTracker, classify_branch, summarize_trace


BASE = "http://127.0.0.1:8137"


class RecoveryMetricTests(unittest.TestCase):
    def test_branch_classifier(self) -> None:
        self.assertEqual(classify_branch(BASE + "/travel/state/IL", "misleading"), "trap")
        self.assertEqual(
            classify_branch(BASE + "/travel/confirm/KS/johnson", "misleading"),
            "correct",
        )
        self.assertEqual(
            classify_branch(BASE + "/travel-clean/state/IL", "misleading"),
            "neutral",
        )

    def test_back_then_correct_branch_is_recovery_without_reentry(self) -> None:
        tracker = RecoveryTracker("misleading")
        first = tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        self.assertTrue(first["trap_entry"])
        tracker.observe(
            BASE + "/travel/state/IL",
            BASE + "/travel/dashboard",
            "PRESS_BACK",
        )
        recovery = tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/KS", "PRESS_ENTER"
        )
        self.assertTrue(recovery["recovery"])
        self.assertFalse(recovery["reentry"])
        self.assertEqual(
            tracker.summary(),
            {
                "trap_entered": True,
                "trap_screenshot_observed_by_model": False,
                "back_after_trap": True,
                "back_reversed_observed_trap": False,
                "trap_exited": True,
                "trap_reentered": False,
                "url_branch_recovery": True,
                "correct_after_back_reversal": False,
            },
        )

    def test_trap_after_exit_is_reentry(self) -> None:
        tracker = RecoveryTracker("misleading")
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        tracker.observe(
            BASE + "/travel/state/IL", BASE + "/travel/dashboard", "PRESS_BACK"
        )
        reentry = tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        self.assertTrue(reentry["reentry"])
        self.assertTrue(tracker.summary()["trap_reentered"])

    def test_trap_screenshot_observation_is_distinct_from_url_entry(self) -> None:
        tracker = RecoveryTracker("misleading")
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        self.assertFalse(tracker.summary()["trap_screenshot_observed_by_model"])
        observed = tracker.observe_screenshot(BASE + "/travel/state/IL")
        self.assertTrue(observed["trap_screenshot"])
        self.assertTrue(tracker.summary()["trap_screenshot_observed_by_model"])

    def test_observed_trap_back_then_correct_is_strict_ordered_reversal(self) -> None:
        tracker = RecoveryTracker("misleading")
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        tracker.observe_screenshot(BASE + "/travel/state/IL")
        back = tracker.observe(
            BASE + "/travel/state/IL", BASE + "/travel/dashboard", "PRESS_BACK"
        )
        correct = tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/KS", "PRESS_ENTER"
        )
        self.assertTrue(back["back_reversed_observed_trap"])
        self.assertTrue(correct["correct_after_back_reversal"])

    def test_unrelated_later_back_cannot_masquerade_as_ordered_reversal(self) -> None:
        tracker = RecoveryTracker("misleading")
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        tracker.observe_screenshot(BASE + "/travel/state/IL")
        tracker.observe(
            BASE + "/travel/state/IL", BASE + "/travel/dashboard", "CLICK"
        )
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/dashboard", "PRESS_BACK"
        )
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/KS", "PRESS_ENTER"
        )
        summary = tracker.summary()
        self.assertTrue(summary["back_after_trap"])
        self.assertTrue(summary["url_branch_recovery"])
        self.assertFalse(summary["back_reversed_observed_trap"])
        self.assertFalse(summary["correct_after_back_reversal"])

    def test_reentry_invalidates_strict_correct_after_back_reversal(self) -> None:
        tracker = RecoveryTracker("misleading")
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        tracker.observe_screenshot(BASE + "/travel/state/IL")
        tracker.observe(
            BASE + "/travel/state/IL", BASE + "/travel/dashboard", "PRESS_BACK"
        )
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/IL", "PRESS_ENTER"
        )
        tracker.observe(
            BASE + "/travel/state/IL", BASE + "/travel/dashboard", "PRESS_BACK"
        )
        tracker.observe(
            BASE + "/travel/dashboard", BASE + "/travel/state/KS", "PRESS_ENTER"
        )
        summary = tracker.summary()
        self.assertTrue(summary["trap_reentered"])
        self.assertFalse(summary["correct_after_back_reversal"])

    def test_jsonl_style_summary(self) -> None:
        rows = [
            {
                "record_type": "step",
                "observed_before_action": {"trap_screenshot": False},
                "events": {
                    "trap_entry": True,
                    "back_after_trap": False,
                    "trap_exit": False,
                    "reentry": False,
                    "recovery": False,
                    "back_reversed_observed_trap": False,
                    "correct_after_back_reversal": False,
                },
            },
            {
                "record_type": "step",
                "observed_before_action": {"trap_screenshot": True},
                "events": {
                    "trap_entry": False,
                    "back_after_trap": True,
                    "trap_exit": True,
                    "reentry": False,
                    "recovery": True,
                    "back_reversed_observed_trap": True,
                    "correct_after_back_reversal": True,
                },
            },
        ]
        self.assertEqual(
            summarize_trace(rows),
            {
                "trap_entered": True,
                "trap_screenshot_observed_by_model": True,
                "back_after_trap": True,
                "back_reversed_observed_trap": True,
                "trap_exited": True,
                "trap_reentered": False,
                "url_branch_recovery": True,
                "correct_after_back_reversal": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
