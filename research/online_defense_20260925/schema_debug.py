"""One separately recorded interface debugging run, not a replacement for v1.

Fix selection reason: a string/Boolean prompt-schema mismatch, not task outcome.
Shares the CURRENT 160-attempt/$10/600-operation ledger. Never run concurrently.
"""
import os
from deps import HERE, wire, Budget, BudgetedPanelAPI
import runner
import prompts_v2
from batch_main import freeze_extra, imported_project_sources


def main():
    if not (HERE / 'live_v1/summary.json').exists():
        raise ValueError('finish_frozen_fixed_panel_before_debugging')
    output = HERE / 'live_v2_schema_debug'
    config, cases = runner.config_and_cases()
    case = next(c for c in cases if c['task_id']=='b002' and c['arm']=='official140')
    config = dict(config, protocol='online_explanation_completion_v2_schema_debug',
                  interface_version='typed_scalars_v2', task_ids=['b002'],
                  arms=['official140'], systems=['online_completion'])
    if not os.environ.get('MODEL_API_KEY'):
        raise ValueError('missing_authorized_process_credential')
    if output.exists():
        raise ValueError('one_debug_pass_only_no_automatic_replay')
    runner.prompts = prompts_v2
    output.mkdir()
    runner.freeze(output, config, [case])
    freeze_extra(output, imported_project_sources())
    wire.dump(output/'purpose.json', {'classification':'interface_debug_not_new_paired_result',
        'selected_for':'b002 v1 public_task Boolean content emitted as string under ambiguous prompt',
        'fixed_case_count':1, 'changed':'public evidence scalar type wording only',
        'unchanged':'actor, verifier logic, charts, gold, execution, limits, strict validator',
        'budget_ledger':'../live_budget.json', 'replaces_v1':False})
    budget=Budget(HERE/'live_budget.json',config)
    api=BudgetedPanelAPI(config,budget)
    unit=output/'b002_official140_online_completion'
    print('START interface-debug',flush=True)
    result=runner.one_run(api,budget,config,case,'online_completion',unit)
    scores=runner.offline_score(output,[(unit,result)])
    wire.dump(output/'summary.json',{'units':1,'scores':scores,'budget':budget.value,
        'classification':'interface_debug_only_not_replacement_or_independent_efficacy_sample'})
    print('END interface-debug',result['status'],'attempts',budget.value['request_attempts'],flush=True)


if __name__=='__main__':main()
