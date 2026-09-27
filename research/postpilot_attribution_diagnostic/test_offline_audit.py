import tempfile
import unittest
from pathlib import Path

from PIL import Image

from .offline_audit import pixels_equal, supplied_history_count, transition


class OfflineAuditTests(unittest.TestCase):
    def test_all_transition_classes(self):
        cases = [("A", "A", "correct_to_correct"), ("A", "B", "correct_to_wrong"),
                 ("B", "A", "wrong_to_correct"), ("B", "B", "wrong_to_same_wrong"),
                 ("B", "C", "wrong_to_different_wrong"), ("A", None, "no_output_or_no_submission")]
        for before, after, expected in cases:
            with self.subTest(before=before, after=after):
                self.assertEqual(transition(before, after, "A"), expected)

    def test_no_output_is_not_invented_as_keep(self):
        self.assertEqual(transition("B", None, "A"), "no_output_or_no_submission")

    def test_history_uses_actual_h_base_request_field(self):
        self.assertEqual(supplied_history_count({"recent_executed_actions_and_public_receipts": [{"executed": True}] * 4}), 4)
        self.assertEqual(supplied_history_count({}), 0)

    def test_decoded_pixels_not_path_or_file_size(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b, c = [Path(directory) / f"{x}.png" for x in "abc"]
            Image.new("RGB", (20, 20), "white").save(a, compress_level=0)
            Image.new("RGB", (20, 20), "white").save(b, compress_level=9)
            Image.new("RGB", (20, 20), "black").save(c)
            self.assertTrue(pixels_equal(a, b))
            self.assertFalse(pixels_equal(a, c))


if __name__ == "__main__":
    unittest.main()
