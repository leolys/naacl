import copy
import json
from pathlib import Path
import tempfile
import unittest

import run_panel as pipeline
from dependencies import records, downstream, read, dump, sha
from registration_records import SCHEMAS, validate, assemble, action_relations
from registration_prompts import REGISTER_PROMPTS, REGISTER, COVERAGE


def candidate(identifier='p1', label='A'):
    return {'id': identifier, 'candidate': {'claim': 'Candidate ' + label, 'option_label': label},
            'visual_cues': ['located visible relation'], 'reading_to_try': 'compare indicated magnitudes',
            'assumptions': ['marks represent task metric']}


def chain(identifier='c1', label='A'):
    return {'id': identifier, 'O': [{'location': 'visible region', 'content': 'literal mark'}],
            'B': {'rule': 'compare magnitude', 'conditions': []},
            'C': {'claim': 'Candidate ' + label, 'option_label': label}}


class FakeAPI:
    def __init__(self, registrations=None):
        self.calls = []
        self.registrations = iter(registrations or [])

    def call(self, folder, system, context, image, schema, stage):
        folder.mkdir()
        self.calls.append((stage, copy.deepcopy(context), sha(image), system))
        if stage == 'register':
            return json.dumps(next(self.registrations, {'candidates': [candidate()]}))
        if stage == 'expand':
            assert read(folder.parent / 'result.json')['registration']['candidates']
            return json.dumps({'proposal_id': context['proposal']['id'], 'outcome': 'expanded',
                               'chains': [chain('new')], 'reason': 'mock only'})
        return json.dumps({'checks': [{'chain_id': c['id'], 'O_status': 'uncertain',
                                      'B_status': 'uncertain', 'inference': 'valid',
                                      'reason': 'mock only', 'visible_evidence': []} for c in context['chains']],
                           'summary': 'mock only'})


def input_fixture(root):
    inputs = root / 'inputs'
    for case in ('one', 'two'):
        dump(inputs / case / 'context.json', {'goal': 'public goal', 'options': ['A', 'B'],
                                             'public_task': {'value': 'public readonly business value'}})
        dump(inputs / case / 'initial.json', {'chains': [chain()]})
        (inputs / case / 'chart.png').write_bytes(b'unchanged-image')
    return inputs


class PanelTests(unittest.TestCase):
    def test_zero_valid_and_notes_not_allowed(self):
        validate('register', {'candidates': []}, {'options': ['A']})
        with self.assertRaises(ValueError):
            validate('register', {'candidates': [], 'notes': 'A'}, {'options': ['A']})

    def test_same_action_candidates_preserved(self):
        registered = {'candidates': [candidate('p1'), candidate('p2')]}
        validate('register', registered, {'options': ['A']})
        expansions = [{'status': 'accepted', 'data': {'proposal_id': p['id'], 'outcome': 'expanded',
                                                     'chains': [chain('new')], 'reason': 'mock'}} for p in registered['candidates']]
        result = assemble({'chains': [chain()]}, registered, expansions)
        self.assertEqual(len(result['chains']), 3)
        self.assertEqual([x['relation'] for x in action_relations({'chains': [chain()]}, registered)], ['same_action'] * 2)
        self.assertTrue(all(x['basis_novelty'] == 'not_determined_by_action_label' for x in action_relations({'chains': [chain()]}, registered)))

    def test_unmapped_and_different_action_marked(self):
        p = candidate('p2'); p['candidate']['option_label'] = None
        rel = action_relations({'chains': [chain()]}, {'candidates': [candidate('p1', 'B'), p]})
        self.assertEqual([x['relation'] for x in rel], ['different_action', 'unmapped'])

    def test_unknown_option_and_duplicate_ids_rejected(self):
        for data in ({'candidates': [candidate('p1', 'bad')]}, {'candidates': [candidate(), candidate()]}):
            with self.assertRaises(ValueError):
                validate('register', data, {'options': ['A']})

    def test_downstream_unchanged(self):
        self.assertEqual(SCHEMAS['expand'], records.SCHEMAS['expand'])
        self.assertEqual(SCHEMAS['verify'], records.SCHEMAS['verify'])
        self.assertIs(pipeline.downstream, downstream)

    def test_unexpanded_and_retarget_preserved(self):
        p = candidate()
        for data in ({'proposal_id': 'p1', 'outcome': 'unexpanded', 'chains': [], 'reason': 'missing relation'},
                     {'proposal_id': 'p1', 'outcome': 'expanded', 'chains': [chain('new', 'B')], 'reason': 'retarget'}):
            validate('expand', data, {'options': ['A', 'B'], 'proposal': p})
            result = assemble({'chains': [chain()]}, {'candidates': [p]}, [{'status': 'accepted', 'data': data}])
            self.assertEqual(result['proposal_links'][0]['proposal'], p)
            if data['chains']:
                self.assertFalse(result['proposal_links'][0]['same_action_label'])
                self.assertEqual(result['chains'][-1]['C']['option_label'], 'B')

    def test_all_registration_before_downstream_public_access_and_same_image(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); inputs = input_fixture(root); output = root / 'out'; output.mkdir()
            config = {'variants': ['registration', 'coverage'], 'cases': ['one', 'two'], 'scope': 'mock'}
            api = FakeAPI()
            result = pipeline.execute_panel(config, inputs, output, api)
            self.assertEqual([c[0] for c in api.calls[:4]], ['register'] * 4)
            self.assertEqual(len(api.calls), 12)
            self.assertEqual(len({c[2] for c in api.calls}), 1)
            for stage, context, _, system in api.calls:
                self.assertEqual(context['public_task']['value'], 'public readonly business value')
                self.assertEqual(set(context), {'goal', 'options', 'public_task', {'register': 'existing_action_labels', 'expand': 'proposal', 'verify': 'chains'}[stage]})
                if stage != 'register':
                    self.assertEqual(system, downstream.PROMPTS[stage])
            self.assertEqual(result['status'], 'finished')
            self.assertTrue(all(not r['submitted'] and len(r['candidate_set']['chains']) == 2 for r in result['results']))

    def test_empty_candidates_do_not_expand(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); inputs = input_fixture(root); output = root / 'out'; output.mkdir()
            api = FakeAPI([{'candidates': []}])
            result = pipeline.register_unit('registration', 'one', inputs, output, api)
            pipeline.finish_unit(result, output, api)
            self.assertEqual([c[0] for c in api.calls], ['register', 'verify'])
            self.assertEqual(result['candidate_set']['chains'], [chain()])

    def test_structural_failure_not_repaired_or_retried(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); inputs = input_fixture(root); output = root / 'out'; output.mkdir()
            api = FakeAPI([{'candidates': [], 'notes': 'Candidate B'}])
            result = pipeline.register_unit('registration', 'one', inputs, output, api)
            self.assertEqual(result['status'], 'registration_interface_failed_no_retry')
            self.assertEqual(len(api.calls), 1)
            self.assertTrue((output / 'registration/one/register/raw.json').exists())

    def test_request_budget_hard_stop(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = pipeline.transport.Ledger(td, {'max_request_attempts': 40, 'max_browser_operations': 0})
            ledger.data['request_attempts'] = 40
            with self.assertRaises(pipeline.transport.LimitStop):
                ledger.event('request', {'test': True})
            self.assertEqual(ledger.data['request_attempts'], 40)

    def test_fixed_actual_input_hashes_and_readonly_values(self):
        cases = read(pipeline.HERE / 'config.json')['cases']
        inputs, _ = pipeline.check_inputs(pipeline.HERE.parent.parent, cases)
        fields = read(inputs / 'pub013/context.json')['public_task']['companion_fields']
        self.assertIn('Highest risk state in the dashboard', [f.get('value') for f in fields])

    def test_two_prompts_only_coverage_suffix(self):
        self.assertEqual(set(REGISTER_PROMPTS), {'registration', 'coverage'})
        self.assertTrue(COVERAGE.startswith(REGISTER + '\n'))
        for system in REGISTER_PROMPTS.values():
            for term in ('Maine', 'Texas', 'Firefox', 'Illinois', '87%', 'pub001', 'b002', 'High / 100'):
                self.assertNotIn(term, system)
            self.assertLess(len(system.split()), 250)


if __name__ == '__main__':
    unittest.main()
