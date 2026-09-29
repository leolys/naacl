import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from batch_main import plan, authorize, terminal_result, unchanged, validate_mode, AUTH_FIELDS
from deps import HERE, wire, Budget


def test_full_catalog_preparation_has_no_inherited_live_budget():
    config, cases = plan(wire.read(HERE / 'batch_config.template.json'))
    assert len(config['task_ids']) == 140 and len(cases) == 280
    assert len({(x['task_id'], x['arm']) for x in cases}) == 280
    assert config['max_request_attempts'] is None
    with pytest.raises(ValueError, match='mode_specific_protocol'):
        authorize(config, {})


def test_authorization_exact_limits_and_scope():
    config, _ = plan({'interface_version':'strict_v1','protocol':'online_explanation_completion_v1_batch_live'})
    authorization = {k: copy.deepcopy(config[k]) for k in AUTH_FIELDS}
    authorization.update(authorized=True, user_approval_reference='scripted unit fixture; not real authorization')
    authorize(config, authorization)
    for key, value in [('max_estimated_usd',11), ('task_ids',['b003']), ('model','other')]:
        changed=copy.deepcopy(config)
        changed[key]=value
        with pytest.raises(ValueError,match='scope_mismatch'):
            authorize(changed,authorization)


@pytest.mark.parametrize('field,value', [('attempt_reserve_usd',0),('estimated_input_usd_per_m',0),
    ('estimated_output_usd_per_m',0),('phase_max_tokens',{'proposal':999999}),
    ('max_attempts_per_call',99),('proxy','http://unapproved')])
def test_cost_and_transport_parameters_cannot_be_overridden(field,value):
    with pytest.raises(ValueError,match='unsupported_configuration_override'):
        plan({field:value})


def test_preparation_protocol_cannot_be_used_for_live():
    config,_=plan(wire.read(HERE/'batch_config.template.json'))
    validate_mode(config,'prepare')
    with pytest.raises(ValueError,match='mode_specific_protocol'):
        validate_mode(config,'live')


def test_resume_does_not_replay_incomplete_or_failed_unit(tmp_path):
    wire.dump(tmp_path/'result.json', {'status':'started'})
    with pytest.raises(ValueError, match='no_automatic_replay'):
        terminal_result(tmp_path)
    wire.dump(tmp_path/'result.json', {'status':'engineering_or_response_failure'})
    assert terminal_result(tmp_path)['status']=='engineering_or_response_failure'


def test_changed_asset_blocks_resume(tmp_path):
    asset=tmp_path/'asset.txt'
    asset.write_text('fixture')
    wire.dump(tmp_path/'runtime.json', {'sources':{str(asset):wire.digest(asset)}})
    unchanged(tmp_path)
    asset.write_text('changed fixture')
    with pytest.raises(ValueError,match='frozen_source_or_asset_changed'):
        unchanged(tmp_path)


def test_actual_browser_operation_cap_is_durable(tmp_path):
    config,_=plan({'max_browser_operations':1,'interface_version':'strict_v1'})
    budget=Budget(tmp_path/'budget.json',config)
    budget.transition({'kind':'scripted_fixture'})
    with pytest.raises(wire.ServiceStop,match='browser_operation_budget_exhausted'):
        budget.transition({'kind':'must_not_execute'})
    assert wire.read(tmp_path/'budget.json')['browser_operations']==1


def test_requests_reserved_before_attempt_and_retry_included(tmp_path):
    config,_=plan({'max_request_attempts':1,'interface_version':'strict_v1'})
    budget=Budget(tmp_path/'budget.json',config)
    budget.current_folder=tmp_path/'request'
    budget.charge({'phase':'proposal','attempt':1})
    assert wire.read(tmp_path/'budget.json')['request_attempts']==1
    with pytest.raises(wire.ServiceStop,match='local_request_budget_exhausted'):
        budget.charge({'phase':'proposal','attempt':2})
    assert len(budget.value['events'])==1
