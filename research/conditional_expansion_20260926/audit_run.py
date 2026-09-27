"""Offline actual-input/accounting audit; semantic faithfulness is not scored."""
import argparse
import base64
from collections import Counter
import hashlib
from pathlib import Path
import json

from bindings import read, dump, sha, records, downstream
from flat_prompt import EXPAND
from flat_records import SCHEMA, EMPTY, adapt, recover, action_relation
from run_panel import FILES


def audit(root):
    config, manifest = read(root / 'config.json'), read(root / 'input_manifest.json')
    ledger, summary = read(root / 'ledger.json'), read(root / 'summary.json')
    events = [e for e in ledger['events'] if e['kind'] == 'request']
    checks = {'attempt_count': len(events) == ledger['request_attempts'],
              'bounded': len(events) <= config['max_request_attempts'],
              'no_browser_or_paid': ledger['browser_operations'] == ledger['paid_api_requests'] == 0,
              'only_expand_verify': set(e['stage'] for e in events) <= {'expand', 'verify'}}
    first_verify = next((i for i, e in enumerate(events) if e['stage'] == 'verify'), len(events))
    checks['all_expansions_before_verification'] = all(e['stage'] == 'expand' for e in events[:first_verify]) and all(e['stage'] == 'verify' for e in events[first_verify:])
    rows, flow = [], []
    for result in summary['results']:
        key = result['variant'] + '/' + result['case']
        unit = root / key
        context, initial = read(unit / 'context.json'), read(unit / 'initial.json')
        registered = read(unit / 'registration.json')
        expected_chains = list(initial['chains'])
        checks[key + '/registration_preserved'] = registered == result['registration']
        for source_name, target_name in FILES.items():
            checks[key + '/' + target_name] = sha(unit / target_name) == manifest['units'][key]['files'][source_name]
        for entry in result['expansions']:
            if entry['status'] == 'accepted':
                data = entry['data']
                mapped = adapt(data, 'conditional_%02d' % entry['index'], context['options'])
                checks[key + '/adapt_%d' % entry['index']] = mapped == entry['adapted_chain'] and (mapped is None or recover(mapped) == data)
                checks[key + '/relation_%d' % entry['index']] = entry['action_relation'] == action_relation(registered['candidates'][entry['index']], data)
                if mapped is not None:
                    expected_chains.append(mapped)
        checks[key + '/all_records_retained'] = expected_chains == result['candidate_set']['chains']
        for request in sorted(unit.glob('*/request.json')):
            stage = 'expand' if request.parent.name.startswith('expand_') else 'verify'
            payload = read(request)
            expected = dict(context)
            if stage == 'expand':
                expected['candidate'] = registered['candidates'][int(request.parent.name.split('_')[1])]
                expected_system, schema = EXPAND, SCHEMA
            else:
                expected['chains'] = result['candidate_set']['chains']
                expected_system, schema = downstream.VERIFY, records.SCHEMAS['verify']
            messages = payload['messages']
            image_bytes = base64.b64decode(messages[1]['content'][1]['image_url']['url'].split(',', 1)[1])
            flags = {'system': messages[0] == {'role': 'system', 'content': expected_system},
                     'context': json.loads(messages[1]['content'][0]['text']) == expected == read(request.parent / 'context.json'),
                     'schema': payload['structured_outputs']['json'] == schema,
                     'image': hashlib.sha256(image_bytes).hexdigest() == sha(unit / 'chart.png'),
                     'decoding': all(payload[k] == config[k] for k in ('model', 'temperature', 'top_p', 'top_k', 'seed')) and payload['max_tokens'] == config['max_output_tokens'][stage] and payload['chat_template_kwargs'] == {'enable_thinking': False},
                     'exact_message_shape': len(messages) == 2 and len(messages[1]['content']) == 2}
            request_key = request.relative_to(root).as_posix()
            checks[request_key] = all(flags.values())
            rows.append({'request': request_key, **flags})
        checks[key + '/no_submit'] = result['submitted'] is False
        flow.append({'unit': key, 'source_candidates': len(registered['candidates']),
                     'nonempty_records': sum(e['empty_record'] is False for e in result['expansions']),
                     'empty_records': sum(e['empty_record'] is True for e in result['expansions']),
                     'exact_actions': sum((e['action_relation'] or {}).get('exact_match', False) for e in result['expansions']),
                     'verification_chain_instances': len((result['verification'] or {}).get('checks', [])), 'status': result['status']})
    for name, h in read(root / 'source_hashes.json').items():
        checks['snapshot/' + name] = sha(root / 'runtime_source' / name) == h
    usage = {k: sum((e.get('usage') or {}).get(k, 0) for e in events) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    return {'passed': all(checks.values()), 'semantic_fidelity_not_scored': True,
            'terminal_status': summary['status'],
            'usage_records': sum(bool(e.get('usage')) for e in events),
            'usage_complete': all(bool(e.get('usage')) for e in events),
            'usage_scope': 'Only usage returned by completed responses; missing/timeout usage is unknown, not zero.',
            'request_attempts': len(events), 'stages': dict(Counter(e['stage'] for e in events)),
            'http_statuses': dict(Counter(str(e.get('http_status')) for e in events)),
            'retries': sum(e['attempt'] > 1 for e in events), **usage,
            'browser_operations': ledger['browser_operations'], 'paid_api_requests': ledger['paid_api_requests'],
            'flow': flow, 'checks': checks, 'actual_requests': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('No audit overwrite')
    result = audit(args.run)
    dump(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'actual_requests', 'flow')}))
    print(json.dumps(result['flow']))
    if not result['passed']:
        raise SystemExit(1)
