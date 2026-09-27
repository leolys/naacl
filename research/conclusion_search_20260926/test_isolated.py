import copy
import json
from pathlib import Path
import tempfile
import unittest
import run_isolated as isolated


class IsolationTests(unittest.TestCase):
    def test_remove_action_not_task(self):
        context = {'goal': 'Choose by the public rule', 'options': ['A', 'B'], 'hypothesis_option': 'B',
                   'search_question': 'Could this follow?', 'history': [{'selected': 'A'}],
                   'pending_proposal': {'action': 'submit'}, 'initial_chains': ['secret'],
                   'state': {'url': 'http://127.0.0.1:123/form', 'text': 'Value 7; choose A if at least 5.',
                             'selected_text': 'A', 'elements': {'options': [{'text': 'A', 'selected': True, 'value': 'option_0'}]}}}
        before = copy.deepcopy(context)
        actual = isolated.discovery_context(context)
        self.assertEqual(context, before)
        self.assertEqual(actual['state']['text'], before['state']['text'])
        self.assertEqual(actual['state']['elements']['options'], [{'text': 'A'}])
        self.assertEqual(set(actual), {'goal', 'options', 'hypothesis_option', 'search_question', 'state'})

    def test_real_prepare_archive_chain(self):
        from prepare_transfer import save_json
        with tempfile.TemporaryDirectory() as folder:
            prepared, archived = Path(folder)/'prepared', Path(folder)/'archived'
            prepared.mkdir(); archived.mkdir()
            value = {'goal': 'same', 'options': ['A', 'B']}
            save_json(prepared/'public_context.json', value)
            isolated.base.dump(archived/'public_context.json', value)
            for root in (prepared, archived):
                (root/'chart.png').write_bytes(b'unchanged-image-fixture')
            manifest = {'context_sha256': isolated.base.digest(prepared/'public_context.json'), 'png_sha256': isolated.base.digest(prepared/'chart.png')}
            save_json(prepared/'manifest.json', manifest)
            report = isolated.validate_derived_context(prepared, archived)
            self.assertTrue(report['parsed_json_equal'])
            self.assertNotEqual(report['prepared_context_sha256'], report['archived_context_sha256'])
            isolated.base.dump(archived/'public_context.json', {'goal': 'changed'})
            with self.assertRaises(ValueError):
                isolated.validate_derived_context(prepared, archived)

    def test_actual_static_assets(self):
        for case in ('b002', 'pub013'):
            result = isolated.validate_derived_context(isolated.HERE/'transfer_inputs'/case, isolated.HERE/'run_transfer_001'/case)
            self.assertTrue(result['parsed_json_equal'])


if __name__ == '__main__':
    unittest.main()
