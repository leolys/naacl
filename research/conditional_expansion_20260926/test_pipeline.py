import copy
import json
from pathlib import Path
import tempfile
import unittest

import run_panel as pipeline
from bindings import records, downstream, read, dump, sha
from flat_prompt import EXPAND
from flat_records import SCHEMA, EMPTY, validate, adapt, recover, action_relation


def candidate(label='A'):
    return {'id': 'p1', 'candidate': {'claim': 'Claim ' + label, 'option_label': label},
            'visual_cues': ['located mark'], 'reading_to_try': 'stated reading', 'assumptions': ['unverified condition']}


def chain():
    return {'id': 'old', 'O': [{'location': 'mark', 'content': 'literal'}],
            'B': {'rule': 'original reading', 'conditions': []}, 'C': {'claim': 'A', 'option_label': 'A'}}


def source_fixture(root):
    source = root / 'source'
    for v in ('registration', 'coverage'):
        for c in ('one', 'two'):
            unit = source / v / c
            dump(unit / 'context.json', {'goal': 'public goal', 'options': ['A', 'B'], 'public_task': {'value': 'full public value'}})
            dump(unit / 'initial.json', {'chains': [chain()]})
            dump(unit / 'register/accepted.json', {'candidates': [candidate()]})
            dump(unit / 'result.json', {'old_response_not_allowed_online': 'old refusal'})
            (unit / 'chart.png').write_bytes(b'same image')
    return source


class FakeAPI:
    def __init__(self, responses=None):
        self.responses = iter(responses or [])
        self.calls = []

    def call(self, folder, system, context, image, schema, stage):
        folder.mkdir()
        self.calls.append((stage, copy.deepcopy(context), sha(image), system))
        if stage == 'expand':
            assert read(folder.parent / 'result.json')['registration']['candidates']
            data = next(self.responses, {'O': ['located mark'], 'B': 'If stated unverified condition holds, use this reading.', 'C': 'A'})
            if isinstance(data, Exception):
                raise data
            return json.dumps(data)
        return json.dumps({'checks': [{'chain_id': c['id'], 'O_status': 'uncertain', 'B_status': 'uncertain',
                                       'inference': 'invalid', 'reason': 'mock only', 'visible_evidence': []} for c in context['chains']],
                           'summary': 'mock only'})


class Tests(unittest.TestCase):
    def test_only_three_generated_fields(self):
        self.assertEqual(set(SCHEMA['properties']), {'O', 'B', 'C'})
        with self.assertRaises(ValueError):
            validate({'O': ['x'], 'B': 'if x', 'C': 'A', 'applicable': True})

    def test_empty_allowed_but_partial_empty_rejected(self):
        self.assertEqual(validate(EMPTY), EMPTY)
        with self.assertRaises(ValueError):
            validate({'O': [], 'B': 'uncertain', 'C': 'A'})

    def test_conditional_false_or_inconsistent_not_filtered(self):
        data = {'O': ['A below B'], 'B': 'If higher is required, use the higher.', 'C': 'A'}
        self.assertEqual(validate(data), data)
        self.assertIsNotNone(adapt(data, 'n', ['A', 'B']))

    def test_adapter_reversible_and_no_rule_inserted(self):
        data = {'O': ['at region x: literal mark', 'at region y: other mark'],
                'B': 'If candidate policy is assumed, use its reading; this policy is unverified.', 'C': 'B'}
        mapped = adapt(data, 'conditional_00', ['A', 'B'])
        self.assertEqual(recover(mapped), data)
        self.assertEqual(mapped['B']['conditions'], [])
        self.assertEqual(mapped['C']['option_label'], 'B')

    def test_changed_action_not_repaired(self):
        data = {'O': ['mark'], 'B': 'If rule, then action.', 'C': 'B'}
        self.assertFalse(action_relation(candidate('A'), data)['exact_match'])
        self.assertEqual(adapt(data, 'n', ['A', 'B'])['C']['option_label'], 'B')
        data['C'] = 'a longer proposed action'
        mapped = adapt(data, 'n', ['A', 'B'])
        self.assertIsNone(mapped['C']['option_label'])
        self.assertEqual(mapped['C']['claim'], data['C'])

    def test_all_expansions_before_verify_and_no_source_results_online(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = source_fixture(root); output = root / 'out'; output.mkdir()
            config = {'variants': ['registration', 'coverage'], 'cases': ['one', 'two'], 'scope': 'mock'}
            api = FakeAPI()
            summary = pipeline.execute(config, source, output, api)
            self.assertEqual([c[0] for c in api.calls], ['expand'] * 4 + ['verify'] * 4)
            self.assertEqual(len({c[2] for c in api.calls}), 1)
            for stage, context, _, system in api.calls:
                self.assertEqual(set(context), {'goal', 'options', 'public_task', 'candidate' if stage == 'expand' else 'chains'})
                self.assertEqual(context['public_task'], {'value': 'full public value'})
                self.assertEqual(system, EXPAND if stage == 'expand' else downstream.VERIFY)
            self.assertTrue(all(len(r['candidate_set']['chains']) == 2 and not r['submitted'] for r in summary['results']))

    def test_empty_record_still_retained_and_verifier_gets_old_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = source_fixture(root); output = root / 'out'; output.mkdir()
            api = FakeAPI([EMPTY])
            result = pipeline.expand_unit('registration', 'one', source, output, api)
            pipeline.verify_unit(result, output, api)
            self.assertTrue(result['expansions'][0]['empty_record'])
            self.assertEqual(result['expansions'][0]['data'], EMPTY)
            self.assertEqual(result['candidate_set']['chains'], [chain()])

    def test_structure_failure_archived_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = source_fixture(root); output = root / 'out'; output.mkdir()
            api = FakeAPI([{'O': [], 'B': '', 'C': '', 'reason': 'no'}])
            result = pipeline.expand_unit('registration', 'one', source, output, api)
            self.assertEqual(result['expansions'][0]['status'], 'interface_failed_no_retry')
            self.assertEqual(len(api.calls), 1)
            self.assertTrue((output / 'registration/one/expand_00/raw.json').exists())

    def test_zero_upstream_candidates_no_expansion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = source_fixture(root); output = root / 'out'; output.mkdir()
            dump(source / 'registration/one/register/accepted.json', {'candidates': []})
            api = FakeAPI()
            result = pipeline.expand_unit('registration', 'one', source, output, api)
            self.assertEqual(api.calls, [])
            self.assertEqual(result['expansions'], [])

    def test_global_budget_includes_attempts(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = pipeline.transport.Ledger(td, {'max_request_attempts': 28, 'max_browser_operations': 0})
            ledger.data['request_attempts'] = 28
            with self.assertRaises(pipeline.transport.LimitStop):
                ledger.event('request', {'test': True})

    def test_fixed_source_manifest(self):
        manifest = pipeline.input_manifest(read(pipeline.HERE / 'config.json'))
        self.assertEqual(manifest['candidate_count'], 14)
        self.assertEqual(len(manifest['units']), 8)
        self.assertEqual(manifest['units']['coverage/pub013']['candidate_count'], 0)

    def test_prompt_short_and_generic(self):
        self.assertLess(len(EXPAND.split()), 160)
        for term in ('Maine', 'Texas', 'Firefox', 'Illinois', '87%', 'pub001', 'b002'):
            self.assertNotIn(term, EXPAND)


if __name__ == '__main__':
    unittest.main()
