import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from deps import core, public_inputs
from method import (should_hook, update_state, state_view, action_support, validate_actor, validate_challenge)

PUBLIC = {'option_labels': ['A','B'], 'user_goal': 'Choose by the visible task.'}
OBS = {'ref':'chart_1','location':'axis','content':'Tick text is 10.'}

def fixture(status='supported'):
    initial = core.import_initial({'rules':[{'id':'r1','text':'Position follows the axis.','component':'axis','conditions':'Uses this axis.'}],
        'chains':[{'chain_id':'base_c1','rule_id':'r1','observations':[OBS], 'claim_kind':'supports_action','option_label':'A','claim':'Conditional A.'}]}, PUBLIC)
    verdict = {'checks':[{'target_id':'base_c1', **{d:{'status':status,'evidence':[OBS], 'reason':'Mock only.'} for d in ('O','B','implication')}}], 'summary':'Mock only.'}
    state = update_state(initial, verdict, 'task', 'image')
    proposal = {'action':{'kind':'select','option':'A'},'chart_dependent':True,'brief_basis':'Mock.',
        'used_rules':[{'rule_id':'r1','version':1,'conditions_match':True,'basis':'Same axis.'}],
        'supporting_chain_ids':['base_c1'],'challenge':None}
    return initial, verdict, state, proposal

@pytest.mark.parametrize('option',['A','B'])
def test_neutral_pre_action_hook(option):
    proposal = fixture()[3]
    proposal['action']['option'] = option
    assert should_hook(proposal, True, False)
    assert not should_hook(proposal, True, True)
    assert not should_hook(proposal, False, False)

def test_supported_chain_can_keep_same_choice():
    _,v,s,p = fixture()
    assert action_support(p,s,v,'A') == []
    p['action'] = {'kind':'submit'}
    assert action_support(p,s,v,'A') == []

def test_B_support_alone_never_authorizes_choice():
    initial,v,_,p = fixture()
    v['checks'][0]['O']['status'] = 'refuted'
    state = update_state(initial,v,'task','image')
    assert state['rules'][0]['status'] == 'active'
    assert action_support(p,state,v,'')

def test_explicit_scope_and_current_version_required():
    initial,v,s,p=fixture()
    with pytest.raises(ValueError): state_view(s,'other','image')
    with pytest.raises(ValueError): state_view(s,'task','other')
    second=update_state(initial,v,'task','image',s)
    assert second['version']==2 and second['rules'][0]['history'][-1]['previous_status']=='active'
    assert action_support(p,second,v,'')
    p['used_rules'][0]['version']=2
    assert not action_support(p,second,v,'')
    p['used_rules'][0]['conditions_match']=None
    assert action_support(p,second,v,'')

@pytest.mark.parametrize('status',['refuted','undetermined'])
def test_uncertain_or_revoked_rule_not_active(status):
    _,v,s,p=fixture(status)
    assert action_support(p,s,v,'')

def test_other_choice_requires_actual_support():
    _,v,s,p=fixture()
    p['action']['option']='B'
    assert action_support(p,s,v,'')

def test_complete_set_survives_zero_new_explanations():
    initial,_,_,_=fixture()
    initial['chains'].append(dict(initial['chains'][0],chain_id='base_c2'))
    initial['initial_counts']['chains']=2
    questions={'questions':[],'summary':'No additional gaps found; not exhaustive.'}
    additions={'new_rules':[],'new_chains':[],'refinements':[],'question_responses':[]}
    assert len(core.apply_supplement(additions,initial,questions,PUBLIC)['chains'])==2

def test_no_hidden_public_fields():
    for key in ('expected_action_id','correct_value','condition','gold','evaluation_hidden_from_agent'):
        with pytest.raises(ValueError): public_inputs.assert_public({'context':{key:'sentinel'}})

def test_challenge_requires_actual_public_citation():
    assert not validate_challenge({'reason':'It feels wrong','evidence':[]},PUBLIC)
    assert validate_challenge({'reason':'This tick challenges mapping','evidence':[OBS]},PUBLIC)
    with pytest.raises(ValueError): validate_challenge({'reason':'No','evidence':[{'ref':'gold'}]},PUBLIC)

def test_single_action_schema():
    validate_actor(fixture()[3])
    with pytest.raises(ValueError): validate_actor({'action':[{'kind':'submit'}]})

def test_navigation_and_empty_submit_do_not_trigger_primary_hook():
    p=fixture()[3]
    p['action']={'kind':'open_link','label':'Open Form'}
    assert not should_hook(p,True,False)
    p['action']={'kind':'submit'}
    assert not should_hook(p,True,False)
    assert should_hook(p,True,False,'A')

def test_unsettled_other_candidate_does_not_block_independent_supported_chain():
    initial,v,s,p=fixture()
    extra=copy.deepcopy(initial['chains'][0])
    extra.update(chain_id='supp_c1',rule_id='supp_r1')
    initial['chains'].append(extra)
    initial['rules'].append(dict(initial['rules'][0],id='supp_r1'))
    extra_check=copy.deepcopy(v['checks'][0])
    extra_check['target_id']='supp_c1'
    extra_check['O']['status']='undetermined'
    v['checks'].append(extra_check)
    s=update_state(initial,v,'task','image')
    assert not action_support(p,s,v,'') # other candidate's mere existence is not a veto
    p['used_rules'].append({'rule_id':'supp_r1','version':1,'conditions_match':True,'basis':'Public form condition.'})
    assert not action_support(p,s,v,'') # reference a B rule, without asserting its chain supports this choice
    p['supporting_chain_ids'].append('supp_c1')
    assert action_support(p,s,v,'') # falsely claim unsettled premise as verified support
    p['supporting_chain_ids']=['supp_c1']
    assert action_support(p,s,v,'')
