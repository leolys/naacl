"""Offline checks of actual archived model inputs and accounting, not semantics."""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path

from dependencies import read, dump, sha, PREVIOUS, downstream
from registration_prompts import REGISTER_PROMPTS
from registration_records import SCHEMAS, assemble, action_relations


def audit(root):
    config, manifest = read(root / 'config.json'), read(root / 'input_manifest.json')
    ledger, summary = read(root / 'ledger.json'), read(root / 'summary.json')
    checks, rows = {}, []
    request_events = [e for e in ledger['events'] if e['kind'] == 'request']
    by_stage = dict(Counter(e['stage'] for e in request_events))
    checks['ledger_count'] = len(request_events) == ledger['request_attempts']
    checks['bounded'] = len(request_events) <= config['max_request_attempts']
    checks['no_browser_or_paid'] = ledger['browser_operations'] == ledger['paid_api_requests'] == 0
    non_register = [i for i, e in enumerate(request_events) if e['stage'] != 'register']
    if non_register:
        checks['register_before_downstream'] = all(e['stage'] == 'register' for e in request_events[:non_register[0]]) and all(e['stage'] != 'register' for e in request_events[non_register[0]:])
    for result in summary['results']:
        variant, case = result['variant'], result['case']
        unit = root / variant / case
        context, initial = read(unit / 'context.json'), read(unit / 'initial.json')
        for name, expected in manifest['cases'][case]['files'].items():
            checks[variant + '/' + case + '/' + name] = sha(unit / name) == expected
        for request in sorted(unit.glob('*/request.json')):
            stage = 'expand' if request.parent.name.startswith('expand_') else request.parent.name
            payload = read(request)
            expected_context = dict(context)
            if stage == 'register':
                expected_context['existing_action_labels'] = list(dict.fromkeys(c['C']['option_label'] for c in initial['chains']))
            elif stage == 'expand':
                index = int(request.parent.name.split('_')[1])
                expected_context['proposal'] = result['registration']['candidates'][index]
            else:
                expected_context['chains'] = result['candidate_set']['chains']
            expected_system = REGISTER_PROMPTS[variant] if stage == 'register' else downstream.PROMPTS[stage]
            key = request.relative_to(root).as_posix()
            messages = payload['messages']
            image_bytes = base64.b64decode(messages[1]['content'][1]['image_url']['url'].split(',', 1)[1])
            details = {'system': messages[0] == {'role': 'system', 'content': expected_system},
                       'context': json.loads(messages[1]['content'][0]['text']) == expected_context == read(request.parent / 'context.json'),
                       'same_image': hashlib.sha256(image_bytes).hexdigest() == sha(unit / 'chart.png'),
                       'schema': payload['structured_outputs']['json'] == SCHEMAS[stage],
                       'decoding': all(payload[k] == config[k] for k in ('model', 'temperature', 'top_p', 'top_k', 'seed')) and payload['max_tokens'] == config['max_output_tokens'][stage] and payload['chat_template_kwargs'] == {'enable_thinking': False},
                       'no_extra_message': len(messages) == 2 and len(messages[1]['content']) == 2}
            checks[key] = all(details.values())
            rows.append({'request': key, **details})
        if result.get('registration') is not None:
            checks[variant + '/' + case + '/relation'] = result['action_relations'] == action_relations(initial, result['registration'])
        if result.get('candidate_set') is not None:
            checks[variant + '/' + case + '/retention'] = result['candidate_set'] == assemble(initial, result['registration'], result['expansions'])
        checks[variant + '/' + case + '/not_submitted'] = result['submitted'] is False
    for name, expected in read(root / 'source_hashes.json').items():
        checks['snapshot/' + name] = sha(root / 'runtime_source' / name) == expected
    prompt_tokens = sum((e.get('usage') or {}).get('prompt_tokens', 0) for e in request_events)
    completion_tokens = sum((e.get('usage') or {}).get('completion_tokens', 0) for e in request_events)
    return {'passed': all(checks.values()), 'semantic_success_not_tested': True,
            'checks': checks, 'actual_requests': rows, 'request_attempts': len(request_events),
            'stages': by_stage, 'http_statuses': dict(Counter(str(e.get('http_status')) for e in request_events)),
            'retry_attempts': sum(e['attempt'] > 1 for e in request_events),
            'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
            'total_tokens': prompt_tokens + completion_tokens,
            'browser_operations': ledger['browser_operations'], 'paid_api_requests': ledger['paid_api_requests']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Do not overwrite an audit artifact')
    result = audit(args.run)
    dump(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'actual_requests')}))
    if not result['passed']:
        raise SystemExit(1)
