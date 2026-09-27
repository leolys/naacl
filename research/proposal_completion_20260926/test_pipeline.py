import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import records
import run as pipeline
from prepare_inputs import project_public, read, dump
from lean_prompts import PROMPTS


def proposal(identifier='p1', label='A'):
    return {'id':identifier, 'candidate':{'claim':'Candidate '+label,'option_label':label},
            'visual_cues':['visible marked region'], 'reading_to_try':'compare the indicated magnitudes',
            'assumptions':['The displayed marks encode the task metric.']}


def chain(identifier='c1', label='A'):
    return {'id':identifier,'O':[{'location':'visible region','content':'literal mark'}],
            'B':{'rule':'compare task metric','conditions':[]},'C':{'claim':'Candidate '+label,'option_label':label}}


class FakeAPI:
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []

    def call(self, folder, system, context, image, schema, stage):
        folder.mkdir()
        self.calls.append((stage,copy.deepcopy(context),pipeline.sha(image)))
        if stage == 'expand':
            # The model has not been called yet; the proposed record must already be durable.
            assert read(folder.parent/'result.json')['proposals']['proposals']
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response)


class PipelineTests(unittest.TestCase):
    def test_full_static_business_values_survive(self):
        root = Path(__file__).resolve().parent.parent/'conclusion_search_20260926/transfer_inputs'
        for case in ('b002','pub013'):
            source = read(root/case/'public_context.json')
            result = project_public(source)
            self.assertEqual(result['public_task'], source['state']['task'])
            self.assertNotIn('history', result)
            self.assertNotIn('pending_proposal', result)
        fields = result['public_task']['companion_fields']
        self.assertIn('Highest risk state in the dashboard', [f.get('value') for f in fields])

    def test_gui_visible_task_exact(self):
        source = {'goal':'g','options':['A','B'],'state':{'text':'Rule: choose by metric 7.','elements':{'selected_text':'A'},'url':'local'},'history':['A']}
        before = copy.deepcopy(source)
        self.assertEqual(project_public(source), {'goal':'g','options':['A','B'],'public_task':{'page_text':source['state']['text']}})
        self.assertEqual(source,before)

    def test_zero_proposals_valid(self):
        records.validate('propose',{'proposals':[],'notes':'nothing further apparent'},{'options':['A']})

    def test_same_label_different_proposals_preserved(self):
        proposals = {'proposals':[proposal('p1'),proposal('p2')],'notes':'two possible bases'}
        expansions = [{'status':'accepted','data':{'proposal_id':p['id'],'outcome':'expanded','chains':[chain('h1')],'reason':'articulated'}} for p in proposals['proposals']]
        result = records.assemble({'chains':[chain()]},proposals,expansions)
        self.assertEqual(len(result['chains']),3)
        self.assertEqual(len(result['proposal_links']),2)

    def test_unexpanded_not_deleted(self):
        p = proposal()
        data = {'proposal_id':'p1','outcome':'unexpanded','chains':[],'reason':'literal comparison unavailable'}
        records.validate('expand',data,{'options':['A'],'proposal':p})
        result = records.assemble({'chains':[chain()]},{'proposals':[p]},[{'status':'accepted','data':data}])
        self.assertEqual(result['proposal_links'][0]['proposal'],p)
        self.assertEqual(result['proposal_links'][0]['chain_ids'],[])

    def test_retargeted_complete_chain_kept_and_flagged(self):
        p = proposal()
        data = {'proposal_id':'p1','outcome':'expanded','chains':[chain('h1','B')],'reason':'candidate'}
        records.validate('expand',data,{'options':['A','B'],'proposal':p})
        result = records.assemble({'chains':[chain()]},{'proposals':[p]},[{'status':'accepted','data':data}])
        self.assertFalse(result['proposal_links'][0]['same_action_label'])
        self.assertEqual(result['chains'][-1]['C']['option_label'],'B')

    def test_invalid_expansion_reference(self):
        data = {'proposal_id':'wrong','outcome':'expanded','chains':[chain()],'reason':'x'}
        with self.assertRaises(ValueError):
            records.validate('expand',data,{'options':['A'],'proposal':proposal()})

    def test_verify_all_ids_required(self):
        with self.assertRaises(ValueError):
            records.validate('verify',{'checks':[],'summary':'x'},{'options':['A'],'chains':[chain()]})

    def test_preserved_before_expand_and_no_action(self):
        p = proposal()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inputs=root/'inputs'; output=root/'out'; output.mkdir()
            context={'goal':'g','public_task':{'rule':'original public rule'},'options':['A','B']}
            dump(inputs/'case/context.json',context)
            dump(inputs/'case/initial.json',{'chains':[chain()],'notes':'old'})
            (inputs/'case/chart.png').write_bytes(b'same image')
            api=FakeAPI([{'proposals':[p],'notes':'possible'},
                         {'proposal_id':'p1','outcome':'unexpanded','chains':[],'reason':'missing literal relation'},
                         {'checks':[{'chain_id':'c1','O_status':'uncertain','B_status':'uncertain','inference':'valid','reason':'mock only','visible_evidence':[]}],'summary':'mock only'}])
            result=pipeline.run_case('case',inputs,output,api)
            self.assertEqual([c[0] for c in api.calls],['propose','expand','verify'])
            self.assertEqual(len({c[2] for c in api.calls}),1)
            self.assertNotIn('existing_action_labels',api.calls[1][1])
            self.assertNotIn('proposal',api.calls[2][1])
            self.assertFalse(result['submitted'])
            self.assertEqual(result['candidate_set']['proposal_links'][0]['outcome'],'unexpanded')

    def test_input_manifests_and_payload_guard(self):
        here=Path(__file__).resolve().parent
        pipeline.check_inputs(here.parent.parent,here/'inputs',read(here/'inputs/manifest.json'),read(here/'config.json')['cases'])
        bad=read(here/'inputs/manifest.json')
        bad['cases']['b002']['files']['chart.png']='bad'
        with self.assertRaises(ValueError):
            pipeline.check_inputs(here.parent.parent,here/'inputs',bad,read(here/'config.json')['cases'])

    def test_budget_hard_stop(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=pipeline.base.Ledger(td,{'max_request_attempts':24,'max_browser_operations':0})
            ledger.data['request_attempts']=24
            with self.assertRaises(pipeline.base.LimitStop):
                ledger.event('request',{'mock':True})
            self.assertEqual(ledger.data['request_attempts'],24)

    def test_no_legacy_prompt_append(self):
        self.assertEqual(set(PROMPTS),{'propose','expand','verify'})
        for prompt in PROMPTS.values():
            self.assertLess(len(prompt.split()),220)
            for term in ('Maine','Texas','Firefox','Illinois','87%','High / 100'):
                self.assertNotIn(term,prompt)


if __name__ == '__main__':
    unittest.main()
