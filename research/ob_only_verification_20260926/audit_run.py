"""Offline actual-payload integrity/accounting checks, not semantic validation."""
import argparse
import base64
from collections import Counter
import hashlib
from pathlib import Path

from bindings import read, dump, sha, SOURCE
from run_panel import SOURCE_FILES
from prompts_ob import VERIFY, DECIDE
from records_ob import project, decision_input, SCHEMAS, validate


def audit(root):
    config, summary, ledger = (read(root / n) for n in ('config.json', 'summary.json', 'ledger.json'))
    manifest = read(root / 'input_manifest.json')
    events = [e for e in ledger['events'] if e['kind'] == 'request']
    checks = {'attempts_counted': len(events) == ledger['request_attempts'],
              'bounded': len(events) <= config['max_request_attempts'],
              'no_browser_or_paid': ledger['browser_operations'] == ledger['paid_api_requests'] == 0,
              'only_two_new_stages': set(e['stage'] for e in events) <= {'ob_verify', 'decide'}}
    rows, unit_rows = [], []
    for r in summary['results']:
        key = r['variant'] + '/' + r['case']
        folder = root / key
        for name in SOURCE_FILES:
            checks[key + '/' + name] = sha(folder / ('source_' + name)) == manifest['units'][key]['files'][name]
            checks[key + '/original_unchanged/' + name] = sha(SOURCE / key / name) == manifest['units'][key]['files'][name]
        ctx = read(folder / 'source_context.json')
        source = read(folder / 'source_candidate_set.json')
        projected = project(ctx, source)
        checks[key + '/projection'] = projected == read(folder / 'projected.json')
        checks[key + '/no_C_field'] = all(set(x) == {'id', 'O', 'B'} for x in projected['records'])
        if r['verification'] is not None:
            validate('ob_verify', r['verification'], projected)
        if r['decision'] is not None:
            validate('decide', r['decision'], projected)
        for stage, system in (('ob_verify', VERIFY), ('decide', DECIDE)):
            path = folder / stage / 'request.json'
            if not path.exists():
                continue
            expected = projected if stage == 'ob_verify' else decision_input(projected, r['verification'])
            payload = read(path); messages = payload['messages']
            actual = read(path.parent / 'context.json')
            blob = base64.b64decode(messages[1]['content'][1]['image_url']['url'].split(',', 1)[1])
            flags = {'exact_context': expected == actual == __import__('json').loads(messages[1]['content'][0]['text']),
                     'exact_system': messages[0] == {'role': 'system', 'content': system},
                     'same_image': hashlib.sha256(blob).hexdigest() == sha(folder / 'source_chart.png'),
                     'schema': payload['structured_outputs']['json'] == SCHEMAS[stage],
                     'decoding': all(payload[k] == config[k] for k in ('model', 'temperature', 'top_p', 'top_k', 'seed'))
                       and payload['max_tokens'] == config['max_output_tokens'][stage]
                       and payload['chat_template_kwargs'] == {'enable_thinking': False},
                     'no_extra_messages': len(messages) == 2 and len(messages[1]['content']) == 2}
            name = path.relative_to(root).as_posix()
            checks[name] = all(flags.values())
            rows.append({'request': name, **flags})
        reviews = (r['verification'] or {}).get('reviews', [])
        unit_rows.append({'unit': key, 'source_records': len(projected['records']),
                         'O_items': sum(len(x['O']) for x in projected['records']),
                         'verified_records': len(reviews),
                         'O_statuses': dict(Counter(o['status'] for x in reviews for o in x['O'])),
                         'B_visual_statuses': dict(Counter(x['B']['visual_decoding']['status'] for x in reviews)),
                         'B_task_statuses': dict(Counter(x['B']['task_applicability']['status'] for x in reviews)),
                         'decision': r['decision'], 'status': r['status'], 'submitted': r['submitted']})
    for name, h in read(root / 'source_hashes.json').items():
        checks['snapshot/' + name] = sha(root / 'runtime_source' / name) == h
    usage = {k: sum((e.get('usage') or {}).get(k, 0) for e in events) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    return {'passed': all(checks.values()), 'semantic_validation': False, 'terminal_status': summary['status'],
            'request_attempts': len(events), 'retries': sum(e['attempt'] > 1 for e in events),
            'stages': dict(Counter(e['stage'] for e in events)),
            'http_statuses': dict(Counter(str(e.get('http_status')) for e in events)),
            **usage, 'usage_complete': all(bool(e.get('usage')) for e in events),
            'usage_scope': 'returned response usage only; absent usage is unknown, not zero',
            'browser_operations': ledger['browser_operations'], 'paid_api_requests': ledger['paid_api_requests'],
            'units': unit_rows, 'checks': checks, 'actual_requests': rows}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError('No overwrite')
    result = audit(a.run)
    dump(a.output, result)
    print({k: v for k, v in result.items() if k not in ('checks', 'actual_requests', 'units')})
    print(result['units'])
    if not result['passed']:
        raise SystemExit(1)
