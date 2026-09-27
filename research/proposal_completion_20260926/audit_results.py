"""Read-only payload/accounting audit. Semantic fidelity is assessed separately."""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
from lean_prompts import PROMPTS
from prepare_inputs import read, sha, dump


def audit(root):
    ledger, config = read(root/'ledger.json'), read(root/'config.json')
    events = [e for e in ledger['events'] if e['kind']=='request']
    assert len(events) == ledger['request_attempts']
    rows, payload_checks = [], []
    for case in config['cases']:
        folder = root/case
        if not (folder/'result.json').exists():
            rows.append({'case':case,'status':'not_run'})
            continue
        result, public = read(folder/'result.json'), read(folder/'context.json')
        proposals = (result.get('proposals') or {}).get('proposals',[])
        initial = read(folder/'initial.json')
        aggregate = result.get('candidate_set')
        new = (aggregate or {}).get('chains',[])[len(initial['chains']):] if aggregate else []
        expanded = [e for e in result['expansions'] if e.get('data',{}).get('outcome')=='expanded']
        for request_path in sorted(folder.glob('*/request.json')):
            stage_folder = request_path.parent
            stage = 'expand' if stage_folder.name.startswith('expand_') else stage_folder.name
            request = read(request_path)
            context = read(stage_folder/'context.json')
            assert request['messages'][0]['content'] == PROMPTS[stage]
            assert json.loads(request['messages'][1]['content'][0]['text']) == context
            encoded = request['messages'][1]['content'][1]['image_url']['url'].split(',',1)[1]
            assert hashlib.sha256(base64.b64decode(encoded)).hexdigest() == sha(folder/'chart.png')
            assert all(context[key] == public[key] for key in public)
            if stage == 'expand':
                index = int(stage_folder.name.rsplit('_',1)[1])
                assert context['proposal'] == proposals[index]
            if stage == 'verify':
                assert context['chains'] == aggregate['chains']
                assert 'proposal' not in context and 'existing_action_labels' not in context
            payload_checks.append({'case':case,'stage':stage_folder.name,'system_context_image_match':True})
        initial_labels = {c['C']['option_label'] for c in initial['chains']}
        rows.append({'case':case,'status':result['status'],'proposal_count':len(proposals),
            'proposal_action_labels':[p['candidate']['option_label'] for p in proposals],
            'expansion_calls':len(result['expansions']),'expanded_calls':len(expanded),
            'unexpanded_calls':sum(e.get('data',{}).get('outcome')=='unexpanded' for e in result['expansions']),
            'expansion_interface_failures':sum(e['status']!='accepted' for e in result['expansions']),
            'complete_new_records_before_aggregation':sum(len(e['data']['chains']) for e in expanded),
            'aggregated_new_chains':len(new) if aggregate else None,
            'new_action_labels':sorted({c['C']['option_label'] for c in new if c['C']['option_label'] is not None}-initial_labels),
            'verification_executed':result.get('verification') is not None,
            'submitted':result['submitted'], 'semantic_quality':'not_determined_by_this_script'})
    snapshots = read(root/'source_hashes.json')
    assert all(sha(root/'runtime_source'/path)==expected for path,expected in snapshots.items())
    return {'rows':rows,'request_attempts':len(events),'stage_counts':dict(Counter(e['stage'] for e in events)),
            'http_status_counts':dict(Counter(str(e.get('http_status')) for e in events)),
            'retry_attempts':sum(e.get('attempt',1)>1 for e in events),
            'usage':{key:sum((e.get('usage') or {}).get(key,0) or 0 for e in events) for key in ('prompt_tokens','completion_tokens','total_tokens')},
            'browser_operations':ledger['browser_operations'],'paid_api_requests':ledger['paid_api_requests'],
            'payload_checks':payload_checks, 'source_snapshot_hashes_verified':len(snapshots)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.run)
    dump(args.output,result)
    print(json.dumps({key:value for key,value in result.items() if key!='payload_checks'},ensure_ascii=False))
