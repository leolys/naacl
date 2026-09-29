import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runner import one_run
from deps import wire

class FakeBudget:
    value={}
    def save(self): pass

class FakeBrowser:
    last=None
    def __init__(self,case,output,budget,executable):
        FakeBrowser.last=self
        self.output=output
        output.mkdir(parents=True)
        self.chart=output/'fixture.txt'
        self.chart.write_text('scripted image placeholder; never sent to a model')
        self.public={'task_alias':'task','user_goal':'Select A','option_labels':['A','B']}
        self.selected=''
        self.history=[]
        self.submitted=False
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def snapshot(self):
        return {'task':self.public,'state':{'page':'form','current_selection':self.selected,'options':['A','B']},'history':self.history},[]
    def execute(self,action):
        if action['kind']=='select':self.selected=action['option']
        if action['kind']=='submit':self.submitted=True
        receipt={'ok':True,'submitted':self.submitted,'observed_selection_after':self.selected}
        self.history.append({'action':copy.deepcopy(action),'receipt':receipt})
        return receipt

class ScriptedAPI:
    def __init__(self):self.contexts=[]
    def call(self,folder,task,phase,prompt,context,images):
        self.contexts.append(copy.deepcopy(context))
        folder.mkdir(parents=True)
        wire.dump(folder/'context.json',context)
        if folder.name=='actor':
            supplied='interpretation_rules' in context
            selected=context['state']['current_selection']
            return {'action':{'kind':'submit'} if selected else {'kind':'select','option':'A'},
                'chart_dependent':True,'brief_basis':'Scripted interface only.',
                'used_rules':[{'rule_id':'r1','version':1,'conditions_match':True,'basis':'Mock matching conditions.'}] if supplied else [],
                'supporting_chain_ids':['base_c1'] if supplied else [],'challenge':None}
        obs={'ref':'chart_1','location':'top','content':'Printed A.'}
        if folder.name=='generation':
            assert not FakeBrowser.last.history, 'the pending primary proposal must not have executed'
            return {'rules':[{'id':'r1','text':'Use this label under task rule.','component':'labels','conditions':'Task asks A.'}],
                'chains':[{'chain_id':'base_c1','rule_id':'r1','observations':[obs],'option_label':'A','claim':'A is supported conditionally.'}]}
        if folder.name=='questions':return {'questions':[],'summary':'Scripted no further questions, not completeness proof.'}
        if folder.name=='verification':
            return {'checks':[{'target_id':'base_c1', **{d:{'status':'supported','evidence':[obs],'reason':'Mock.'} for d in ('O','B','implication')}}], 'summary':'Mock only.'}
        raise AssertionError('unexpected stage '+folder.name)

def test_full_preexecution_lifecycle_with_scripted_model(tmp_path):
    api=ScriptedAPI()
    result=one_run(api,FakeBudget(),{'max_actor_calls':8,'max_reverification':1,'browser_executable':None},
        {'alias':'task','task_id':'mock','arm':'fixture','domain':'fixture'},'online_completion',tmp_path/'unit',FakeBrowser)
    assert result['status']=='submitted'
    assert result['evidence_mode']=='scripted_control'
    assert result['hook_events'][0]['selection_at_hook']==''
    assert not result['action_records'][0]['executed']
    assert [e['action']['kind'] for e in result['history']]==['select','submit']
    assert len(result['rule_reads'])==2
    assert (tmp_path/'unit/rule_state_v1.json').exists()
    assert any('verified_arguments' in c for c in api.contexts)
    assert len(api.contexts)==6 # 3 actor, generation, questions, verification; skip supplement

def test_ordinary_path_never_runs_verification(tmp_path):
    api=ScriptedAPI()
    result=one_run(api,FakeBudget(),{'max_actor_calls':8,'max_reverification':1,'browser_executable':None},
        {'alias':'task','task_id':'mock','arm':'fixture','domain':'fixture'},'ordinary',tmp_path/'unit',FakeBrowser)
    assert result['status']=='submitted'
    assert not result['hook_events'] and not result['rule_reads']
    assert len(api.contexts)==2
