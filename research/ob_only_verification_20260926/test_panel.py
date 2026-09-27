import copy
import json
from pathlib import Path
import tempfile
import unittest

import run_panel as pipeline
from bindings import read, dump, SOURCE, transport
from records_ob import project, decision_input, SCHEMAS, validate
from prompts_ob import VERIFY, DECIDE


def context():
    return {'goal': 'Use task evidence', 'public_task': {'text': 'Choose a route'}, 'options': ['A', 'B'],
            'gold': 'HIDDEN', 'previous_verify': 'OLD_VERDICT'}


def chains():
    return {'chains': [{'id': 'old', 'O': [{'location': 'left', 'content': 'visible cue'}],
                         'B': {'rule': 'An unconfirmed visual mapping', 'conditions': ['a condition']},
                         'C': {'claim': 'HIDDEN_C', 'option_label': 'A'}}]}


def checks(ctx):
    assessment = {'evidence': 'visible/public basis', 'status': 'unclear'}
    return {'reviews': [{'id': r['id'],
                         'O': [{'index': i + 1, **assessment} for i in range(len(r['O']))],
                         'B': {'visual_decoding': dict(assessment), 'task_applicability': dict(assessment)}}
                        for r in ctx['records']]}


def fixture(root):
    source = root / 'source'
    for c in ('one', 'two'):
        folder = source / 'registration' / c
        dump(folder / 'context.json', context())
        dump(folder / 'candidate_set.json', chains())
        dump(folder / 'registration.json', {'candidates': []})
        dump(folder / 'initial.json', chains())
        dump(folder / 'result.json', {'verification': 'OLD_REJECT'})
        (folder / 'chart.png').write_bytes(b'identical image')
    return source


class FakeAPI:
    def __init__(self, bad=None):
        self.calls, self.bad = [], bad

    def call(self, folder, system, ctx, image, schema, stage):
        folder.mkdir(parents=True)
        self.calls.append({'system': system, 'context': copy.deepcopy(ctx), 'image': image.read_bytes(), 'schema': schema, 'stage': stage})
        if self.bad == 'transport':
            raise transport.LimitStop('Unknown transport')
        if self.bad == 'interface' and stage == 'ob_verify':
            return '{"inference":"valid"}'
        return json.dumps(checks(ctx) if stage == 'ob_verify' else {'basis': 'fresh decision', 'option_label': 'B'})


class PanelTests(unittest.TestCase):
    def test_projection_removes_C_but_preserves_OB_and_public_context(self):
        source = chains()
        projected = project(context(), source)
        self.assertEqual(set(projected), {'goal', 'public_task', 'options', 'records'})
        self.assertEqual(projected['records'][0], {'id': 'r1', 'O': source['chains'][0]['O'], 'B': source['chains'][0]['B']})
        self.assertNotIn('HIDDEN', json.dumps(projected))
        projected['records'][0]['B']['rule'] = 'mutated'
        self.assertNotEqual(projected['records'][0]['B'], source['chains'][0]['B'])

    def test_C_and_old_verdict_sentinels_do_not_change_online_inputs(self):
        a, b = chains(), chains()
        b['chains'][0]['C'] = {'claim': 'another outcome', 'option_label': 'B'}
        ca, cb = context(), context()
        cb['previous_verify'] = 'opposite old verdict'
        pa, pb = project(ca, a), project(cb, b)
        self.assertEqual(pa, pb)
        self.assertEqual(decision_input(pa, checks(pa)), decision_input(pb, checks(pb)))

    def test_no_semantic_sanitization_of_embedded_actions(self):
        source = chains()
        source['chains'][0]['B']['rule'] = 'Embedded proposal chooses A, with conflicting assumptions'
        self.assertEqual(project(context(), source)['records'][0]['B'], source['chains'][0]['B'])

    def test_schema_has_no_inference_or_whole_chain_verdict(self):
        encoded = json.dumps(SCHEMAS)
        for word in ('inference', 'valid', 'winner', 'accept_chain'):
            self.assertNotIn(word, encoded)
        self.assertNotIn('C', SCHEMAS['ob_verify']['properties'])

    def test_review_covers_every_record_and_observation_once(self):
        ctx = project(context(), chains())
        value = checks(ctx)
        validate('ob_verify', value, ctx)
        value['reviews'][0]['O'].append(dict(value['reviews'][0]['O'][0]))
        with self.assertRaises(ValueError):
            validate('ob_verify', value, ctx)
        with self.assertRaises(ValueError):
            validate('ob_verify', {'reviews': []}, ctx)

    def test_does_not_repair_evidence_status_semantically(self):
        ctx = project(context(), chains())
        value = checks(ctx)
        value['reviews'][0]['B']['visual_decoding'] = {'evidence': 'This reading is unsupported', 'status': 'supported'}
        self.assertEqual(validate('ob_verify', value, ctx), value)

    def test_choice_may_differ_from_source_or_be_null(self):
        ctx = project(context(), chains())
        for option in ('B', None):
            validate('decide', {'basis': 'explicit basis', 'option_label': option}, ctx)
        with self.assertRaises(ValueError):
            validate('decide', {'basis': 'invented', 'option_label': 'X'}, ctx)

    def test_fixed_verify_decide_order_and_same_image(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); api = FakeAPI()
            summary = pipeline.execute({'variants': ['registration'], 'cases': ['one', 'two'], 'scope': 'mock'}, fixture(root), root / 'run', api)
            self.assertEqual(summary['status'], 'finished')
            self.assertEqual([c['stage'] for c in api.calls], ['ob_verify', 'decide', 'ob_verify', 'decide'])
            self.assertTrue(all(c['image'] == b'identical image' for c in api.calls))
            self.assertEqual(api.calls[0]['system'], VERIFY)
            self.assertEqual(api.calls[1]['system'], DECIDE)
            self.assertNotIn('HIDDEN_C', json.dumps([c['context'] for c in api.calls]))
            self.assertNotIn('OLD_REJECT', json.dumps([c['context'] for c in api.calls]))
            self.assertEqual(api.calls[1]['context']['ob_checks'], checks(api.calls[0]['context'])['reviews'])
            self.assertTrue(all(r['decision']['option_label'] == 'B' and not r['submitted'] for r in summary['results']))

    def test_interface_failure_no_retry_or_decision(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); api = FakeAPI('interface')
            summary = pipeline.execute({'variants': ['registration'], 'cases': ['one', 'two'], 'scope': 'mock'}, fixture(root), root / 'run', api)
            self.assertEqual(len(api.calls), 2)
            self.assertTrue(all(r['decision'] is None for r in summary['results']))
            self.assertTrue(all('interface_failed' in r['status'] for r in summary['results']))

    def test_unknown_transport_stops_global_without_replay(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); api = FakeAPI('transport'); source = fixture(root)
            with self.assertRaises(transport.LimitStop):
                pipeline.execute({'variants': ['registration'], 'cases': ['one', 'two'], 'scope': 'mock'}, source, root / 'run', api)
            self.assertEqual(len(api.calls), 1)
            summary = read(root / 'run/summary.json')
            self.assertEqual(summary['status'], 'stopped')
            self.assertEqual(summary['results'][1]['status'], 'prepared')

    def test_hard_cap_counts_all_attempts(self):
        with tempfile.TemporaryDirectory() as t:
            ledger = transport.Ledger(t, {'max_request_attempts': 20, 'max_browser_operations': 0})
            for i in range(20):
                ledger.event('request', {'attempt': 1 + (i % 2)})
            with self.assertRaises(transport.LimitStop):
                ledger.event('request', {})
            self.assertEqual(ledger.data['request_attempts'], 20)

    def test_real_fixed_eight_units_all_records_retained(self):
        config = read(Path(__file__).with_name('config.json'))
        m = pipeline.manifest(config)
        self.assertEqual(len(m['units']), 8)
        self.assertEqual(sum(u['records'] for u in m['units'].values()), 28)
        for key in m['units']:
            ctx, source = read(SOURCE / key / 'context.json'), read(SOURCE / key / 'candidate_set.json')
            projected = project(ctx, source)
            self.assertEqual(len(projected['records']), len(source['chains']))
            for a, b in zip(projected['records'], source['chains']):
                self.assertEqual((a['O'], a['B']), (b['O'], b['B']))

    def test_prompts_generic_and_no_inference_reintroduced(self):
        for prompt in (VERIFY, DECIDE):
            for token in ('Firefox', 'Maine', 'TX', 'KS', '87%', 'b002', 'pub001', 'pub013'):
                self.assertNotIn(token, prompt)
        self.assertLess(len(VERIFY.split()), 180)
        self.assertLess(len(DECIDE.split()), 150)


if __name__ == '__main__':
    unittest.main()
