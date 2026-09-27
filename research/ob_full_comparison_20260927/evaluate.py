"""OFFLINE ONLY: full-denominator original-label agreement, not semantic certification."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = ['plain', 'v3', 'v4', 'v5', 'v6', 'v7']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)


def known_usage(usage):
    return isinstance(usage, dict) and all(isinstance(usage.get(k), int) and not isinstance(usage[k], bool)
        and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))


def state(result, label):
    if result.get('status') != 'completed':
        return 'interface_failed' if result.get('status') == 'interface_failed' else 'not_completed'
    choice = result['choice']['option_label']
    if choice is None:
        return 'no_option'
    if choice == label['original_correct_label']:
        return 'target'
    options = {x['label']: x for x in label['options']}
    if choice not in options:
        raise ValueError('Nonpublic completed choice')
    return 'trap' if options[choice]['alignment_role'] == 'misleading_trap' else 'other'


def pair(left, right, keys, units, labels):
    counts = Counter()
    detailed = Counter()
    families = defaultdict(lambda: {'n': 0, 'net_target': 0})
    rows = {}
    common = nonnull = common_delta = nonnull_delta = 0
    for key in keys:
        a, b = state(left[key], labels[key]), state(right[key], labels[key])
        delta = int(b == 'target') - int(a == 'target')
        if a == b == 'target':
            kind = 'target_maintained'
        elif a in ('trap', 'other') and b == 'target':
            kind = 'wrong_to_target'
        elif a == 'target' and b in ('trap', 'other'):
            kind = 'target_to_wrong'
        elif a in ('no_option', 'interface_failed', 'not_completed') and b == 'target':
            kind = 'null_or_failure_to_target'
        elif a == 'target' and b in ('no_option', 'interface_failed', 'not_completed'):
            kind = 'target_to_null_or_failure'
        else:
            kind = 'other_transition'
        counts[kind] += 1
        detailed[a + ' -> ' + b] += 1
        family = families[units[key]['family']]
        family['n'] += 1
        family['net_target'] += delta
        rows[key] = {'from': a, 'to': b, 'net_target': delta, 'transition': kind,
            'from_choice': left[key].get('choice', {}).get('option_label'),
            'to_choice': right[key].get('choice', {}).get('option_label')}
        if left[key]['status'] == right[key]['status'] == 'completed':
            common += 1
            common_delta += delta
            if a != 'no_option' and b != 'no_option':
                nonnull += 1
                nonnull_delta += delta
    return {'n': len(keys), 'net_target': sum(x['net_target'] for x in rows.values()),
        'broad_transitions': dict(counts), 'exact_transitions': dict(detailed), 'rows': rows,
        'families': dict(families), 'common_parsed_including_null': {'n': common, 'net_target': common_delta},
        'both_nonnull_auxiliary': {'n': nonnull, 'net_target': nonnull_delta}}


def evaluate(capture, output):
    output.mkdir(parents=True, exist_ok=False)
    units = read(HERE / 'manifest.json')['units']
    labels = read(HERE / 'offline/labels.json')['tasks']
    history = read(HERE / 'offline/old_v3_summary.json')['units']
    schedule = read(HERE / 'schedule.json')['rows']
    prior_label_digest = read(HERE.parent / 'ob_refinement_20260927/analysis/v7_dev.json')['source_hashes']['offline/labels.json']
    labels_unchanged = sha(HERE / 'offline/labels.json') == prior_label_digest
    if not labels_unchanged:
        raise ValueError('Original label file changed relative to archived prior evaluation')
    results = {version: {} for version in VERSIONS}
    files = {name: sha(HERE / name) for name in ('manifest.json', 'schedule.json', 'offline/labels.json',
             'offline/old_v3_summary.json', 'RUNTIME_SEAL.json', 'config.json')}
    files['capture/CAPTURE_MANIFEST.json'] = sha(capture / 'CAPTURE_MANIFEST.json')
    costs, events_all = {}, []
    for worker in range(4):
        summary_file = capture / 'workers' / str(worker) / 'summary.json'
        ledger_file = capture / 'workers' / str(worker) / 'ledger.json'
        summary = read(summary_file) if summary_file.exists() else {'status': 'not_started', 'units': {}}
        ledger = read(ledger_file) if ledger_file.exists() else {'events': [], 'attempts': 0}
        if ledger['attempts'] != len(ledger['events']) or ledger['attempts'] > 650:
            raise ValueError('ledger count/budget mismatch')
        for event in ledger['events']:
            folder = capture / event['folder']
            if sha(folder / 'request.json') != event['request_sha256']:
                raise ValueError('ledger request digest mismatch')
            response_file = folder / ('response_%02d.json' % event['attempt'])
            if response_file.exists():
                archived = read(response_file)
                if event.get('http_status') != archived['http_status']:
                    raise ValueError('ledger response status mismatch; use a settled snapshot')
                if isinstance(archived['body'], dict) and archived['body'].get('usage') != event.get('usage'):
                    raise ValueError('ledger response usage mismatch')
        events_all += ledger['events']
        files[str(summary_file)] = sha(summary_file) if summary_file.exists() else None
        files[str(ledger_file)] = sha(ledger_file) if ledger_file.exists() else None
        costs[str(worker)] = {'attempts': ledger['attempts'], 'status': summary['status'],
                             'runtime_preserved': summary.get('runtime_preserved')}
    for row in schedule:
        key, version = row['unit'], row['version']
        path = capture / 'runs' / version / key / 'result.json'
        result = read(path) if path.exists() else {'unit': key, 'version': version, 'worker': row['worker'], 'status': 'not_completed'}
        if (result['unit'], result['version'], result['worker']) != (key, version, row['worker']):
            raise ValueError('result crossed worker/version/task')
        if key in results[version]:
            raise ValueError('duplicate result')
        results[version][key] = result
        files[str(path)] = sha(path) if path.exists() else None
    event_ids = [(e['worker'], e['number']) for e in events_all]
    if len(set(event_ids)) != len(events_all):
        raise ValueError('duplicate accounting event')
    cost_by_version = {}
    for version in VERSIONS + ['service_controls']:
        selected = [e for e in events_all if (e['stage'] == 'control' if version == 'service_controls'
                                             else e['stage'] != 'control' and e['version'] == version)]
        usage = Counter()
        for event in selected:
            if known_usage(event.get('usage')):
                usage.update({k: event['usage'].get(k, 0) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')})
        cost_by_version[version] = {'attempts': len(selected), 'retry_attempts': sum(e['attempt'] > 1 for e in selected),
            'known_usage': dict(usage), 'unknown_usage_attempts': sum(not known_usage(e.get('usage')) for e in selected),
            'stages': dict(Counter(e['stage'] for e in selected)), 'http_status': dict(Counter(str(e.get('http_status')) for e in selected)),
            'known_request_seconds_sum': sum(e.get('elapsed', 0) for e in selected),
            'unknown_elapsed_attempts': sum('elapsed' not in e or e.get('elapsed_unknown_after_crash', False) for e in selected)}
    panels = {'full140': list(units), 'previous_dev24': [k for k, u in units.items() if u['panel'] == 'dev'],
              'remaining116': [k for k, u in units.items() if u['panel'] != 'dev']}
    comparisons = {}
    for version in VERSIONS:
        data = {'version': version, 'panels': {}, 'cost': cost_by_version[version], 'units': results[version]}
        for panel, keys in panels.items():
            data['panels'][panel] = {'n': len(keys), 'counts': dict(Counter(state(results[version][key], labels[key]) for key in keys)),
                'vs_plain': pair(results['plain'], results[version], keys, units, labels),
                'vs_fresh_v3': pair(results['v3'], results[version], keys, units, labels),
                'vs_historical_v3': pair(history, results[version], keys, units, labels)}
        comparisons[version] = data
        new(output / (version + '.json'), data)
    report = {'scope': 'single-image original-label agreement, known dataset, no browser submissions',
        'capture': str(capture), 'counts': {v: d['panels']['full140']['counts'] for v, d in comparisons.items()},
        'total_attempts': len(events_all), 'costs': cost_by_version, 'workers': costs,
        'all840_terminal': all(r['status'] in ('completed', 'interface_failed') for v in results.values() for r in v.values()),
        'all_workers_finished': all(x['status'] == 'finished' for x in costs.values()),
        'runtime_preserved_all': all(x['runtime_preserved'] is True for x in costs.values()),
        'fixed_labels_changed': not labels_unchanged, 'fixed_label_prior_digest': prior_label_digest,
        'business_submissions': 0, 'paid_api_calls': 0,
        'caveats': ['v3 schema differs from v4-v7', 'fixed historical O/B generation cost excluded',
                    'original-label agreement is not O/B semantic correctness', 'env008 retains evidence_conflict'],
        'source_hashes': files}
    new(output / 'SUMMARY.json', report)
    print(json.dumps({k: report[k] for k in ('counts', 'total_attempts', 'all840_terminal', 'all_workers_finished')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.capture, args.output)
