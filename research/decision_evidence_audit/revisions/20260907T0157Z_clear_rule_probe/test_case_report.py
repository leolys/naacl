"""Offline report regression; no model or browser use."""

import unittest

from research.decision_evidence_audit.case_report import transition_class


class CaseReportTests(unittest.TestCase):
    def test_correct_action_text_without_submission_is_not_recovery(self):
        self.assertEqual(
            transition_class("misleading_failure", "success", submitted=False),
            "未完成真实提交",
        )

    def test_distinguishes_recovery_preservation_and_harm(self):
        for before, after, expected in (
            ("misleading_failure", "success", "原本错误后提交正确"),
            ("success", "success", "原本正确并保持"),
            ("success", "misleading_failure", "原本正确却改错"),
            ("misleading_failure", "irrelevant_action_failure", "原本错误且未纠正"),
        ):
            with self.subTest(before=before, after=after):
                self.assertEqual(transition_class(before, after, submitted=True), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
