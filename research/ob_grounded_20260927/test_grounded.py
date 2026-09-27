import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import run
from prepare import full_project
from schema import validate

BASE = {'goal': 'Choose highest usage.', 'public_task': {'user_goal': 'Choose highest usage.'},
        'options': ['A', 'B'], 'records': [{'id': 'r1', 'O': ['one mark'], 'B': 'a conditional reading'}]}
NOTE = {'appearance_facts': [{'location': 'plot', 'fact': 'one mark'}], 'printed_facts': [], 'public_definitions': [], 'uncertain': []}

class Tests(unittest.TestCase):
    def test_read_blind(self):
        p = {**copy.deepcopy(BASE), 'C': 'secret conclusion', 'gold': 'hidden'}
        c = run.contexts(p)
        self.assertEqual(set(c), {'goal', 'public_task', 'options'})
        self.assertNotIn('records', c)
        self.assertNotIn('secret', json.dumps(c))

    def test_preserve_conditions(self):
        p = {'user_goal': 'g', 'option_labels': ['a'], 'gold': 'do not send'}
        n = {'rules': [{'id': 'b', 'text': 'if condition', 'conditions': 'assumption X', 'component': 'hidden type'}],
             'chains': [{'rule_id': 'b', 'observations': [{'content': 'raw'}], 'claim': 'C', 'option_label': 'a'}]}
        got = full_project(p, n)
        self.assertEqual(got['records'][0]['B'], {'text': 'if condition', 'conditions': 'assumption X'})
        self.assertEqual(got['records'][0]['O'], [{'content': 'raw'}])
        self.assertNotIn('gold', json.dumps(got))
        self.assertNotIn('component', json.dumps(got))
        self.assertNotIn('claim', json.dumps(got))

    def test_context_preserves_records(self):
        got = run.contexts(BASE, NOTE)
        self.assertEqual(got['records'], BASE['records'])
        got['records'][0]['O'].append('change')
        self.assertEqual(BASE['records'][0]['O'], ['one mark'])

    def test_status_and_coverage(self):
        a = {'evidence': 'visible mark', 'status': 'supported'}
        v = {'reviews': [{'id': 'r1', 'O': [{'index': 1, **a}], 'B': {'reading_checked': 'a conditional reading', **a}}]}
        validate('verify', v, BASE)
        for mutate in ('id', 'index', 'inference'):
            bad = copy.deepcopy(v)
            if mutate == 'id': bad['reviews'][0]['id'] = 'r2'
            if mutate == 'index': bad['reviews'][0]['O'][0]['index'] = 2
            if mutate == 'inference': bad['reviews'][0]['inference'] = a
            with self.assertRaises(ValueError): validate('verify', bad, BASE)

    def test_duplicate_O_rejected(self):
        a = {'evidence': 'visible mark', 'status': 'supported'}
        v = {'reviews': [{'id': 'r1', 'O': [{'index': 1, **a}, {'index': 1, **a}], 'B': {'reading_checked': 'a conditional reading', **a}}]}
        with self.assertRaises(ValueError): validate('verify', v, BASE)

    def test_read_channels_and_bounds(self):
        validate('read', NOTE, BASE)
        bad = copy.deepcopy(NOTE)
        bad['appearance_facts'] *= 9
        with self.assertRaises(ValueError): validate('read', bad, BASE)
        bad = copy.deepcopy(NOTE)
        bad['visible_facts'] = bad.pop('appearance_facts')
        with self.assertRaises(ValueError): validate('read', bad, BASE)

    def test_options_no_forced_decision(self):
        validate('decide', {'basis': 'unclear', 'option_label': None}, BASE)
        validate('decide', {'basis': 'available', 'option_label': 'A'}, BASE)
        with self.assertRaises(ValueError): validate('decide', {'basis': 'bad', 'option_label': 'gold'}, BASE)

    def test_supply_bounds(self):
        v = {'records': [{'id': 'r1', 'O': ['o'], 'B': 'b'}]}
        validate('supply', v, BASE)
        with self.assertRaises(ValueError): validate('supply', {'records': []}, BASE)

    def fixture(self, root):
        c = run.read(Path(__file__).parent / 'config.json')
        c['deadline_utc'] = '2099-01-01T00:00:00+00:00'
        return run.Client(c, root)

    def test_budget_before_call(self):
        with tempfile.TemporaryDirectory() as t:
            api = self.fixture(t)
            api.ledger['attempts'] = api.config['max_attempts']
            with self.assertRaises(run.Stop): api.guard()

    def test_deadline(self):
        with tempfile.TemporaryDirectory() as t:
            api = self.fixture(t)
            api.config['deadline_utc'] = '2000-01-01T00:00:00+00:00'
            with self.assertRaises(run.Stop): api.guard()

    def test_no_external_endpoint(self):
        c = run.read(Path(__file__).parent / 'config.json')
        c['endpoint'] = 'https://unapproved.invalid'
        with self.assertRaises(ValueError): run.Client(c)

    def test_resume_archived_no_call(self):
        with tempfile.TemporaryDirectory() as t:
            api = self.fixture(t)
            image = Path(t) / 'chart.png'
            image.write_bytes(b'\x89PNG mock')
            api.http = Mock()
            response = Mock(status_code=200)
            response.json.return_value = {'model': 'Qwen3.8-27B', 'choices': [{'message': {'content': json.dumps(NOTE)}}],
                                         'usage': {'total_tokens': 9}}
            api.http.post.return_value = response
            result = api.call(Path(t) / 'read', 'system', run.contexts(BASE), image, 'read')
            self.assertEqual(result, NOTE)
            self.assertEqual(api.ledger['attempts'], 1)
            self.assertEqual(api.call(Path(t) / 'read', 'system', run.contexts(BASE), image, 'read'), NOTE)
            self.assertEqual(api.http.post.call_count, 1)
            with self.assertRaises(run.Stop): api.call(Path(t) / 'read', 'CHANGED', run.contexts(BASE), image, 'read')

    def test_unknown_transport_stops(self):
        with tempfile.TemporaryDirectory() as t:
            api = self.fixture(t)
            image = Path(t) / 'chart.png'
            image.write_bytes(b'\x89PNG mock')
            api.http = Mock()
            api.http.post.side_effect = run.requests.Timeout('mock')
            with self.assertRaises(run.Stop): api.call(Path(t) / 'read', 'sys', run.contexts(BASE), image, 'read')
            self.assertEqual(api.ledger['attempts'], 1)
            self.assertEqual(api.http.post.call_count, 1)
            with self.assertRaises(run.Stop): api.guard()

    def test_nonobject_response_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            api = self.fixture(t)
            image = Path(t) / 'chart.png'
            image.write_bytes(b'\x89PNG mock')
            api.http = Mock()
            response = Mock(status_code=200)
            response.json.return_value = ['invalid', 'but preserve original']
            api.http.post.return_value = response
            with self.assertRaises(ValueError): api.call(Path(t) / 'read', 'sys', run.contexts(BASE), image, 'read')
            self.assertEqual(run.read(Path(t) / 'read/response_01.json')['body'], ['invalid', 'but preserve original'])
            self.assertTrue((Path(t) / 'read/failure.json').exists())
            self.assertEqual(api.ledger['attempts'], 1)

    def test_crash_recovery_usage_sidecar(self):
        with tempfile.TemporaryDirectory() as t:
            api = self.fixture(t)
            image = Path(t) / 'chart.png'
            image.write_bytes(b'\x89PNG mock')
            api.http = Mock()
            response = Mock(status_code=200)
            response.json.return_value = {'model': 'Qwen3.8-27B', 'choices': [{'message': {'content': json.dumps(NOTE)}}], 'usage': {'total_tokens': 9}}
            api.http.post.return_value = response
            api.call(Path(t) / 'read', 'sys', run.contexts(BASE), image, 'read')
            (Path(t) / 'read/accepted.json').unlink()
            api.ledger['events'][0].pop('usage')
            api.ledger['events'][0]['state'] = 'sent_outcome_pending'
            before = copy.deepcopy(api.ledger)
            self.assertEqual(api.call(Path(t) / 'read', 'sys', run.contexts(BASE), image, 'read'), NOTE)
            self.assertEqual(api.ledger, before)
            self.assertEqual(api.http.post.call_count, 1)
            self.assertEqual(run.read(Path(t) / 'read/recovery_metadata.json')['response_usage'], {'total_tokens': 9})

    def test_manifest_all_and_family_separation(self):
        m = run.read(Path(__file__).parent / 'manifest.json')
        full = [u for u in m['units'].values() if u['panel'] == 'full']
        self.assertEqual(len(full), 140)
        self.assertEqual(len([u for u in full if not u['records']]), 4)
        c = [u for u in full if u['confirm']]
        self.assertEqual(len(c), 12)
        self.assertEqual(len({u['family'] for u in c}), 12)
        self.assertFalse({u['family'] for u in c} & set(m['dev_families']))
        for k, u in m['units'].items():
            d = Path(__file__).parent / 'data' / k
            self.assertEqual(run.sha(d / 'input.json'), u['input_sha256'])
            self.assertEqual(run.sha(d / u['image']), u['image_sha256'])

if __name__ == '__main__':
    unittest.main()
