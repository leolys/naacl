"""OFFLINE ONLY: fixed labels and paired accounting, never imported by runner."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


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
        raise ValueError('Completed choice outside original public options')
    return 'trap' if options[choice]['alignment_role'] == 'misleading_trap' else 'other'


def paired(left, right, ids, units, labels):
    rows = {}
    families = defaultdict(lambda: {'n': 0, 'net_target': 0})
    transitions, broad = Counter(), Counter()
    common, nonnull = [], []
    for key in ids:
        a, b = state(left[key], labels[key]), state(right[key], labels[key])
        delta = int(b == 'target') - int(a == 'target')
        family = families[units[key]['family']]
        family['n'] += 1
        family['net_target'] += delta
        transitions[a + ' -> ' + b] += 1
        if a == b == 'target':
            kind = 'target_maintained'
        elif a in ('trap', 'other') and b == 'target':
            kind = 'wrong_to_target'
        elif a == 'target' and b in ('trap', 'other'):
            kind = 'target_to_wrong'
        elif a not in ('target', 'trap', 'other') and b == 'target':
            kind = 'null_or_failure_to_target'
        elif a == 'target' and b not in ('target', 'trap', 'other'):
            kind = 'target_to_null_or_failure'
        else:
            kind = 'other_transition'
        broad[kind] += 1
        row = {'from': a, 'to': b, 'net_target': delta, 'transition': kind,
               'family': units[key]['family'],
               'from_choice': left[key].get('choice', {}).get('option_label'),
               'to_choice': right[key].get('choice', {}).get('option_label')}
        rows[key] = row
        if left[key]['status'] == right[key]['status'] == 'completed':
            common.append(row)
            if a != 'no_option' and b != 'no_option':
                nonnull.append(row)
    return {'n': len(ids), 'net_target': sum(x['net_target'] for x in rows.values()),
            'positive_net_families': sum(x['net_target'] > 0 for x in families.values()),
            'common_parsed_including_null': {'n': len(common), 'net_target': sum(x['net_target'] for x in common)},
            'both_nonnull_auxiliary': {'n': len(nonnull), 'net_target': sum(x['net_target'] for x in nonnull)},
            'exact_transitions': dict(transitions), 'broad_transitions': dict(broad),
            'families': dict(families), 'rows': rows}


def load_current(version, panel, units):
    panels = ('dev', 'application') if panel == 'full' else (panel,)
    merged, sources = {}, {}
    for current in panels:
        path = HERE / 'runs' / (version + '_' + current) / 'summary.json'
        summary = read(path)
        if summary['status'] != 'finished' or summary['version'] != version or summary['panel'] != current:
            raise ValueError('Not a finished matching panel: ' + str(path))
        expected = {key for key, value in units.items() if value['panel'] == current}
        if set(summary['units']) != expected:
            raise ValueError('Missing or extra units: ' + str(path))
        if not summary.get('runtime_preserved'):
            raise ValueError('Runtime identity not preserved')
        if set(merged).intersection(summary['units']):
            raise ValueError('Duplicate unit')
        merged.update(summary['units'])
        sources[str(path.relative_to(HERE))] = digest(path)
    return merged, sources


def evaluate(version, panel):
    manifest = read(HERE / 'manifest.json')
    units = manifest['units']
    ids = [key for key, value in units.items() if panel == 'full' or value['panel'] == panel]
    labels = read(HERE / 'offline/labels.json')['tasks']
    old = read(HERE / 'offline/old_v3_summary.json')['units']
    plain, plain_sources = load_current('plain', panel, units)
    current, current_sources = load_current(version, panel, units)
    comparisons = {name: paired(source, current, ids, units, labels)
                   for name, source in [('plain', plain), ('historical_v3', old)]}
    counts = {name: dict(Counter(state(source[key], labels[key]) for key in ids))
              for name, source in [('plain', plain), ('historical_v3', old), (version, current)]}
    conditions = {name: {'net_at_least_2': values['net_target'] >= 2,
                         'at_least_2_positive_families': values['positive_net_families'] >= 2,
                         'common_parsed_net_at_least_1': values['common_parsed_including_null']['net_target'] >= 1}
                  for name, values in comparisons.items()} if panel == 'dev' else None
    numeric_gate = all(all(x.values()) for x in conditions.values()) if conditions else None
    application_conditions = None
    application_gate = None
    if panel == 'full':
        app_ids = [key for key in ids if units[key]['panel'] == 'application']
        application_conditions = {}
        for name, source in [('plain', plain), ('historical_v3', old)]:
            app = paired(source, current, app_ids, units, labels)
            application_conditions[name] = {
                'full_net_at_least_7': comparisons[name]['net_target'] >= 7,
                'application_net_positive': app['net_target'] > 0,
                'full_common_parsed_net_nonnegative': comparisons[name]['common_parsed_including_null']['net_target'] >= 0,
                'application_net_target': app['net_target'],
                'application_common_parsed_including_null': app['common_parsed_including_null'],
            }
        application_gate = all(all(value[key] for key in (
            'full_net_at_least_7', 'application_net_positive', 'full_common_parsed_net_nonnegative'))
            for value in application_conditions.values())
    return {'version': version, 'panel': panel, 'n': len(ids), 'counts': counts,
            'comparisons': comparisons, 'dev_conditions': conditions, 'dev_numeric_gate': numeric_gate,
            'application_conditions': application_conditions, 'application_numeric_gate': application_gate,
            'qualitative_gate': 'separate required audit; numeric agreement is not semantic certification',
            'source_hashes': {**plain_sources, **current_sources,
                'manifest.json': digest(HERE / 'manifest.json'),
                'offline/labels.json': digest(HERE / 'offline/labels.json'),
                'offline/old_v3_summary.json': digest(HERE / 'offline/old_v3_summary.json')},
            'business_submissions': 0, 'labels_changed': False,
            'scope': 'static original-label agreement; development/application not independent unseen tasks'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', choices=['v4', 'v5', 'v6', 'v7'], required=True)
    parser.add_argument('--panel', choices=['dev', 'application', 'full'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.version, args.panel)
    save_new(args.output, result)
    print(json.dumps({k: result[k] for k in ('version', 'panel', 'n', 'counts', 'dev_numeric_gate')}, ensure_ascii=False))
