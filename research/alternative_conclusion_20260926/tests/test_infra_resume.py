import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runner


class InfraChecks(unittest.TestCase):
    def test_action_equivalence(self):
        import jsonschema
        schema = json.loads((ROOT / "browser_action_schema.json").read_text(encoding="utf-8"))
        candidates = [{"action":"click_link","text":"Open Dashboard"},
                      {"action":"click_button","text":"Submit Form"},
                      {"action":"select_option","select_name":"primary_action","option_text":"Route A"},
                      {"action":"finish"}, {"action":"finish","text":"extra"},
                      {"action":"select_option","select_name":"x"}, [],
                      {"action":"click_link","text":12}, {"action":"click_link","text":""},
                      {"action":"submit_form"}]
        for data in candidates:
            with self.subTest(data=data):
                expected = True
                try:
                    jsonschema.validate(data, schema)
                except jsonschema.ValidationError:
                    expected = False
                actual = True
                try:
                    runner.validate_actor_action(data)
                except ValueError:
                    actual = False
                self.assertEqual(expected, actual)

    def test_only_ephemeral_port_normalized(self):
        a = {"content":"page http://127.0.0.1:1234/task/x", "image":"base64_A"}
        b = {"content":"page http://127.0.0.1:5678/task/x", "image":"base64_A"}
        self.assertEqual(runner.canonical_local_ports(a), runner.canonical_local_ports(b))
        b["image"] = "base64_B"
        self.assertNotEqual(runner.canonical_local_ports(a), runner.canonical_local_ports(b))


if __name__ == "__main__":
    unittest.main()
