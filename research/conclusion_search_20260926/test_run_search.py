import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('current_search_runner', HERE / 'run_search.py')
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def context():
    return {'goal':'Choose the route and submit','state':{'url':'http://127.0.0.1:123/task/pub001/form','text':'public'},
            'history':[{'action':{'action':'select_option','option_text':'Route A'},'receipt':{'executed':True}}],
            'options':['Route A','Route B','Route C'],'pending_proposal':{'action':'click_button','text':'Submit Form'}}


def initial():
    return {'chains':[{'id':'c1','O':[{'location':'plot','content':'OLD OBSERVATION'}],
                       'B':{'rule':'OLD RULE','conditions':[]},
                       'C':{'claim':'Route A because OLD REASON','option_label':'Route A'}}],'notes':'OLD NOTES'}


class FakeAPI:
    def __init__(self, answer=None):
        self.requests=[]
        self.answer=answer

    def call(self, folder, system, data, image, schema, stage):
        folder.mkdir(parents=True)
        self.requests.append({'system':system,'context':copy.deepcopy(data),'schema':copy.deepcopy(schema),'stage':stage})
        if self.answer is not None:
            return json.dumps(self.answer)
        return json.dumps({'chains':[{'id':'h1','O':[{'location':'plot','content':'visible mark'}],
                           'B':{'rule':'conditional test rule','conditions':[]},
                           'C':{'claim':'Candidate route','option_label':data['hypothesis_option']}}],
                           'notes':'candidate only'})


class SearchTests(unittest.TestCase):
    def test_v1_is_exact_prompt_with_no_old_justification(self):
        prompt,data=run.question_request('action_conclusion_only',context(),initial())
        self.assertEqual(prompt,run.base.PROMPTS['questions_new'])
        self.assertEqual(data['existing_conclusions'],[{'option_label':'Route A'}])
        self.assertNotIn('OLD',json.dumps(data))
        self.assertEqual(data['state'],context()['state'])
        self.assertEqual(data['history'],context()['history'])

    def test_v2_same_projection(self):
        _,first=run.question_request('action_conclusion_only',context(),initial())
        _,second=run.question_request('option_search',context(),initial())
        self.assertEqual(first,second)

    def test_fresh_search_has_no_candidate_records(self):
        _,data=run.question_request('fresh_search',context(),initial())
        self.assertEqual(data,context())
        self.assertNotIn('existing_conclusions',data)
        data['state']['text']='changed'
        self.assertEqual(context()['state']['text'],'public')

    def test_normalization_only_touches_state_url(self):
        data=context()['state']
        data['text']='http://127.0.0.1:123 task body is not normalized'
        before=copy.deepcopy(data)
        result=run.normalized_state(data)
        self.assertEqual(data,before)
        self.assertEqual(result['text'],before['text'])
        self.assertEqual(result['url'],'http://127.0.0.1:EPHEMERAL/task/pub001/form')

    def test_normalization_refuses_nonlocal_or_query(self):
        for url in ['https://example.org/','http://127.0.0.1:123/task?answer=x','http://127.0.0.1:123/task#x']:
            with self.assertRaises(ValueError):
                run.normalized_state({'url':url})

    def test_hypotheses_symmetry_preserves_all_and_renames_only_ids(self):
        api=FakeAPI()
        with tempfile.TemporaryDirectory() as path:
            result=run.hypothesis_candidates(api,Path(path),context(),'not_read_by_mock.png')
        self.assertEqual([r['context']['hypothesis_option'] for r in api.requests],context()['options'])
        self.assertEqual(len({r['system'] for r in api.requests}),1)
        self.assertTrue(all('initial_chains' not in r['context'] for r in api.requests))
        self.assertTrue(all(r['schema']['properties']['chains']['maxItems']==1 for r in api.requests))
        self.assertEqual([c['C']['option_label'] for c in result['new_chains']],context()['options'])
        self.assertEqual(len({c['id'] for c in result['new_chains']}),3)
        self.assertTrue(all(h['response']['chains'][0]['id']=='h1' for h in result['hypotheses']))

    def test_empty_hypotheses_are_legitimate_and_all_options_still_run(self):
        api=FakeAPI({'chains':[],'notes':'no candidate'})
        with tempfile.TemporaryDirectory() as path:
            result=run.hypothesis_candidates(api,Path(path),context(),'unused.png')
        self.assertEqual(len(api.requests),3)
        self.assertEqual(result['new_chains'],[])

    def test_oversized_choice_set_fails_before_any_request(self):
        data=context()
        data['options'].append('Route D')
        api=FakeAPI()
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(ValueError):
                run.hypothesis_candidates(api,Path(path),data,'unused.png')
        self.assertEqual(api.requests,[])

    def test_configuration_is_bounded_and_local(self):
        config=run.read(HERE/'config.json')
        self.assertEqual(config['max_request_attempts'],100)
        self.assertEqual(config['max_browser_operations'],300)
        self.assertEqual(config['endpoint'],'http://127.0.0.1:8058/v1/chat/completions')
        self.assertEqual(config['concurrency'],1)
        self.assertEqual(len(config['strategies']),4)


if __name__=='__main__':
    unittest.main()
