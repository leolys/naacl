import unittest
from inventory import excluded
from sanitize import clean, assert_clean, RULES, candidates
from pack_export import safe_relative


class ExportTests(unittest.TestCase):
    def test_secret_removal_without_value_logging(self):
        examples = [b'sk-' + b'A' * 22, b'github_pat_' + b'b' * 30,
                    b'Authorization: Bearer ' + b'c' * 28,
                    b'https://name:' + b'p' * 24 + b'@github.com/repo',
                    b'{"api_key":"' + b'z' * 36 + b'"}']
        for value in examples:
            after, changes = clean(value)
            self.assertTrue(changes)
            self.assertNotEqual(value, after)
            assert_clean(after)
            self.assertNotIn(value.decode(), str(changes))

    def test_regular_model_evidence_unchanged(self):
        raw = b'{"choice":"ME","temperature":0.7,"tokens":1024,"O":"Pale yellow"}'
        self.assertEqual(clean(raw), (raw, []))

    def test_prefilter_does_not_skip_supported_patterns(self):
        examples = [b'ghp_' + b'Q' * 25, b'hf_' + b'Q' * 25,
                    b'AKIA' + b'X' * 16, b'xoxb-' + b'q' * 25,
                    b'{"PASSWORD":"' + b'x' * 25 + b'"}',
                    b'Bearer\t' + b'Q' * 30,
                    b''.join([b'-----BEGIN ', b'PRIVATE KEY-----', b'abc',
                              b'-----END ', b'PRIVATE KEY-----'])]
        for value in examples:
            for kind, pattern, _ in RULES:
                if pattern.search(value):
                    self.assertIn(kind, candidates(value))

    def test_no_credential_or_optional_scope(self):
        for name in ('apikey.txt', 'password.txt', '.env.example', 'cookies.json',
                     'resource_manager.py', 'core.80', 'model.safetensors',
                     'original.zip', 'real_world40/task.json', 'backups/code.py'):
            self.assertTrue(excluded(tuple(name.split('/'))), name)

    def test_paths_are_bounded(self):
        for name in ('../escape', '/root/x', 'C:/x', 'folder\\x'):
            with self.assertRaises(ValueError):
                safe_relative(name)
        self.assertEqual(str(safe_relative('research/a/file.json')), 'research/a/file.json')


if __name__ == '__main__':
    unittest.main()
