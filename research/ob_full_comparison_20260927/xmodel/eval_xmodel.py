"""OFFLINE ONLY scorer for xmodel runs. state()/pair() logic is verbatim from
the archived evaluate.py so numbers are directly comparable across rounds.
Adds: McNemar exact test, bootstrap CI, cross-model matrix, cost from ledger.
"""
import argparse
import json
import math
import random
from collections import Counter, defaultdict
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent
VERSIONS = ['plain', 'v3', 'v4', 'v5', 'v6', 'v7']
DOMAIN_N = {'business47': 47, 'environment35': 35, 'health19': 19, 'public39': 39}
BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 20260928


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


def mcnemar_exact(b, c):
    """Two-sided exact McNemar on discordant pairs b=wrong_to_target, c=target_to_wrong."""
    if b == c:
        return 1.0
    n = b + c
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1))
    return min(1.0, tail * 2 * (0.5 ** n) * 2)  # 2*P(X<=k) with X~Bin(n,0.5)


def bootstrap_ci(inds_left, inds_right, keys_order, b=BOOTSTRAP_B, seed=BOOTSTRAP_SEED):
    rng = random.Random(seed)
    n = len(keys_order)
    deltas = []
    for _ in range(b):
        sample = [keys_order[rng.randrange(n)] for _ in range(n)]
        deltas.append(sum(inds_right[k] for k in sample) / n - sum(inds_left[k] for k in sample) / n)
    deltas.sort()
    return {'point': sum(inds_right.values()) / n - sum(inds_left.values()) / n,
            'ci95': [deltas[int(0.025 * (b - 1))], deltas[int(0.975 * (b - 1))]],
            'b': b, 'seed': seed}


def load_results(root, versions):
    results = {v: {} for v in versions}
    for version in versions:
        for key in read(PANEL / 'manifest.json')['units']:
            path = root / 'runs' / version / key / 'result.json'
            results[version][key] = read(path) if path.exists() else {
                'unit': key, 'version': version, 'status': 'not_completed'}
    return results


def cost_of(root, versions):
    ledger = read(root / 'ledger.json')
    out = {}
    for version in versions + ['service_controls']:
        selected = [e for e in ledger['events'] if (e['stage'] == 'control' if version == 'service_controls'
                    else e['stage'] != 'control' and e['version'] == version)]
        usage = Counter()
        for event in selected:
            if known_usage(event.get('usage')):
                usage.update({k: event['usage'].get(k, 0) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')})
        out[version] = {'attempts': len(selected), 'known_usage': dict(usage),
                        'unknown_usage_attempts': sum(not known_usage(e.get('usage')) for e in selected),
                        'known_request_seconds_sum': round(sum(e.get('elapsed', 0) for e in selected), 1),
                        'http_status': dict(Counter(str(e.get('http_status')) for e in selected))}
    return out


def evaluate_model(results, versions, units, labels):
    keys_all = list(units)
    panels = {'full140': keys_all,
              'previous_dev24': [k for k, u in units.items() if u['panel'] == 'dev'],
              'remaining116': [k for k, u in units.items() if u['panel'] != 'dev']}
    comparisons = {}
    for version in versions:
        data = {'version': version, 'panels': {}}
        for panel, keys in panels.items():
            counts = dict(Counter(state(results[version][key], labels[key]) for key in keys))
            entry = {'n': len(keys), 'counts': counts,
                     'agreement_rate': counts.get('target', 0) / len(keys)}
            if version != 'plain':
                p = pair(results['plain'], results[version], keys, units, labels)
                p['mcnemar'] = mcnemar_exact(p['broad_transitions'].get('wrong_to_target', 0),
                                             p['broad_transitions'].get('target_to_wrong', 0))
                p['bootstrap'] = bootstrap_ci(
                    {k: int(state(results['plain'][k], labels[k]) == 'target') for k in keys},
                    {k: int(state(results[version][k], labels[k]) == 'target') for k in keys}, keys)
                p.pop('rows')
                entry['vs_plain'] = p
            data['panels'][panel] = entry
        comparisons[version] = data
    return comparisons, panels


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, nargs='+', help='one or more xmodel result roots')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    units = read(PANEL / 'manifest.json')['units']
    labels = read(PANEL / 'offline/labels.json')['tasks']
    report = {'scope': 'single-image original-label agreement, known dataset, no browser submissions',
              'protocol': 'xmodel_20260928', 'models': {}, 'labels_sha256': sha(PANEL / 'offline/labels.json')}
    for root_path in args.out:
        root = Path(root_path)
        identity = read(root / 'runtime_identity_xmodel.json')
        versions = identity['versions']
        results = load_results(root, versions)
        all_terminal = all(r['status'] in ('completed', 'interface_failed')
                           for v in versions for r in results[v].values())
        model_key = identity['model']
        comparisons, panels = evaluate_model(results, versions, units, labels)
        counts = {v: comparisons[v]['panels']['full140']['counts'] for v in versions}
        report['models'][model_key] = {
            'root': str(root), 'identity': identity, 'all_terminal': all_terminal,
            'counts': counts, 'comparisons': comparisons, 'cost': cost_of(root, versions),
            'domain_counts': {v: {d: dict(Counter(state(results[v][k], labels[k]) for k in units
                            if units[k]['domain'] == d)) for d in DOMAIN_N} for v in versions}}
    new(Path(args.output) / 'SUMMARY_XMODEL.json', report)
    headline = {}
    for model_key, m in report['models'].items():
        headline[model_key] = {v: c.get('target', 0) for v, c in m['counts'].items()}
    print(json.dumps(headline, ensure_ascii=False, indent=1))
