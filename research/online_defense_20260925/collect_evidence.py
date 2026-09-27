"""Offline evidence collection. Never invokes a model, browser, or changes raw runs."""
import base64
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from deps import HERE, PROJECT, module, wire, public_inputs


def optional(path, default=None):
    return wire.read(path, default)


def collect_run(name, ledger):
    root=HERE/name
    if not (root/'summary.json').exists():
        return None
    scores=wire.read(root/'offline_scores.json')
    rows=[]
    for score in scores:
        unit=root/score['unit']
        result=wire.read(unit/'result.json')
        events=[x for x in ledger['events'] if Path(x['folder']).is_relative_to(unit)]
        contexts=[]
        route=[]
        history=wire.read(unit/'browser/history.json',[])
        for request_path in sorted(unit.glob('step_*/**/request.json')):
            folder=request_path.parent
            request=wire.read(request_path)
            envelope=wire.read(folder/'context.json')
            context=envelope['context']
            public_inputs.assert_public(context)
            user=request['messages'][1]['content']
            assert json.loads(user[0]['text'])==context
            assert context.get('history',[])==history[:len(context.get('history',[]))]
            pictures=[x['image_url']['url'] for x in user if x['type']=='image_url']
            assert len(pictures)==len(envelope['images'])
            for picture, asset in zip(pictures,envelope['images']):
                digest=sha256(base64.b64decode(picture.split(',',1)[1],validate=True)).hexdigest()
                assert digest==asset['sha256']==wire.digest(Path(asset['file']))
                assert Path(asset['file']).is_relative_to(unit/'browser')
            state=context.get('state',{})
            selected=[o['label'] for o in state.get('option_states',[]) if o['selected']]
            assert selected==([state['current_selection']] if state.get('current_selection') else [])
            contexts.append({'path':str(request_path.relative_to(HERE)),
                'phase':envelope['phase'],'stage':folder.name,
                'system_prompt':request['messages'][0]['content'],
                'public_context':context,'images':envelope['images'],
                'text_matches_archived_context':True,'images_match_actual_browser_bytes':True,
                'history_matches_real_executions':True,'selection_flags_consistent':True})
            for attempt_path in sorted(folder.glob('attempt_*.json')):
                item=wire.read(attempt_path)
                route.append({k:item.get(k) for k in ('attempt','phase','requested_model','http_status',
                             'response_model','response_id','finish_reason','elapsed_seconds')})
        defense_folders=sorted(unit.glob('step_*/defense'))
        defense=defense_folders[0] if defense_folders else None
        initial=optional(defense/'initial_set.json',{}) if defense else {}
        combined=optional(defense/'combined.json',{}) if defense else {}
        questions=optional(defense/'questions/parsed.json',{}) if defense else {}
        supplement=optional(defense/'supplement/parsed.json',{}) if defense else {}
        verdict=optional(defense/'verified.json',{}) if defense else {}
        rules=[wire.read(p) for p in sorted(unit.glob('rule_state_v*.json'))]
        row={'unit':score['unit'],'run':name,'score':score,'result':result,
            'cost':{'request_attempts':len(events),
                'estimated_usd':sum(e['charged_estimated_usd'] for e in events),
                'input_tokens':sum(e.get('normalized_usage',{}).get('values',{}).get('input_tokens',0) for e in events),
                'output_tokens':sum(e.get('normalized_usage',{}).get('values',{}).get('output_tokens',0) for e in events),
                'browser_operations':len(history)},
            'initial_set':initial,'questions':questions,'supplement':supplement,
            'combined':combined,'verification':verdict,'rule_states':rules,
            'requests':contexts,'route_records':route,
            'counts':{'initial_chains':len(initial.get('chains',[])),
                'questions':len(questions.get('questions',[])),
                'new_chains_raw':len(supplement.get('new_chains',[])),
                'new_chains_validated':len(combined.get('chains',[]))-len(initial.get('chains',[])) if combined else None,
                'refinements_raw':len(supplement.get('refinements',[])),
                'verified_targets':len(verdict.get('checks',[])),
                'rule_state_versions':len(rules),
                'blocked_actions':sum(bool(r.get('blocked')) for r in result['action_records'])}}
        row['classification']=classify(row)
        rows.append(row)
    frozen=wire.read(root/'runtime.json')['sources']
    unchanged=all(Path(p).is_file() and wire.digest(p)==digest for p,digest in frozen.items())
    aggregate={}
    for system in ('ordinary','online_completion'):
        items=[r for r in rows if r['score']['system']==system]
        aggregate[system]={'runs':len(items),'statuses':dict(Counter(r['score']['status'] for r in items)),
            'true_submissions':sum(r['score']['server_receipt_count'] for r in items),
            'original_success':sum((r['score']['original_evaluation'] or {}).get('outcome')=='success' for r in items),
            'hooks':sum(r['score']['hook_count'] for r in items),
            'verification_completed':sum(bool(r['verification']) for r in items),
            'request_attempts':sum(r['cost']['request_attempts'] for r in items),
            'browser_operations':sum(r['cost']['browser_operations'] for r in items)}
    return {'run':name,'rows':rows,'aggregate':aggregate,'frozen_sources_unchanged':unchanged,
        'interface_audit':{'requests_checked':sum(len(r['requests']) for r in rows),
            'full_wire_text_images_history_selection_checks':'pass',
            'hidden_field_allowlist_check':'pass',
            'limits':'No semantic certification. Existing original chart captions remain visible; no arm-blindness claim.',
            'requested_endpoint':'https://api.apiyi.com/v1/chat/completions',
            'identity_limit':'Response model is gateway self-report; upstream identity not independently attested.'}}


def classify(row):
    result=row['result']
    if result['status']=='submitted':return '真实提交；按原评分单独报告'
    if result.get('error'):
        return '接口/响应失败；不能当作已执行核验的语义失败'
    if result['status']=='unresolved_public_evidence':
        return '模型核验后返回证据未确定；没有实际选择或提交'
    if row['counts']['blocked_actions']:
        return 'actor 引用了未充分核实的依赖，动作校验拒绝执行后耗尽调用限额'
    return '普通动作调用限额耗尽；无真实提交'


def main():
    ledger=wire.read(HERE/'live_budget.json')
    runs=[value for value in (collect_run('live_v1',ledger),collect_run('live_v2_schema_debug',ledger)) if value]
    bundle={'generated_by':'offline collector; no model or browser calls','runs':runs,
        'budget':{k:v for k,v in ledger.items() if k not in ('events','browser_events')},
        'assets':optional(HERE/'asset_recovery/provenance.json'),
        'all_condition_get_audit':{k:v for k,v in wire.read(HERE/'asset_check_v2/asset_audit.json').items() if k!='cases'},
        'all_condition_post_controls':{k:v for k,v in wire.read(HERE/'batch_post_controls/summary.json').items() if k!='units'}}
    wire.dump(HERE/'EVIDENCE.json',bundle)
    overview={'fixed_panel':runs[0]['aggregate'],'engineering_debug':[r['aggregate'] for r in runs[1:]],
              'budget':bundle['budget'],'requests_wire_audited':sum(r['interface_audit']['requests_checked'] for r in runs),
              'all_recorded_sources_unchanged':all(r['frozen_sources_unchanged'] for r in runs)}
    wire.dump(HERE/'RESULT_SUMMARY.json',overview)
    helper=PROJECT/'aris_repo/tools/evidence_check.py'
    if helper.is_file():
        checker=module('online_evidence_precheck',helper)
        wire.dump(HERE/'evidence_precheck.json',checker.check_batch(wire.read(HERE/'claims_to_check.json'),root=PROJECT))
    else:
        wire.dump(HERE/'evidence_precheck.json',{'status':'helper_unavailable','semantic_review_still_required':True})
    print(json.dumps(overview,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
