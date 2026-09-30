"""Aggregate runner outputs into the revision-experiment scores.

Outputs scores.json with:
- per-seed full-denominator classification for plain and v5 (target/trap/other/no_option/interface_failed)
- paired McNemar matrices v5-vs-plain within each seed, exact p and exact paired-difference CI
- mean/std over seeds for both arms
- sc3 self-consistency majority vote over the three plain seeds
- tab and clean single-round scoring
"""
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OB = HERE.parent / 'ob_full_comparison_20260927'


def binom_two_sided(k, n):
    if n == 0:
        return 1.0
    k = min(k, n - k)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) * 2 * 0.5 ** n
    return min(1.0, p)


def clopper(k, n, alpha=0.05):
    def pge(kk, nn, p):
        return sum(math.comb(nn, i) * p ** i * (1 - p) ** (nn - i) for i in range(kk, nn + 1))

    def ple(kk, nn, p):
        return sum(math.comb(nn, i) * p ** i * (1 - p) ** (nn - i) for i in range(0, kk + 1))

    a, b = 0.0, 1.0
    if k == 0:
        lo = 0.0
    else:
        for _ in range(80):
            m = (a + b) / 2
            if pge(k, n, m) < alpha / 2:
                a = m
            else:
                b = m
        lo = b
    a, b = 0.0, 1.0
    if k == n:
        hi = 1.0
    else:
        for _ in range(80):
            m = (a + b) / 2
            if ple(k, n, m) < alpha / 2:
                b = m
            else:
                a = m
        hi = a
    return lo, hi


def paired_ci(n01, n10, n_total, alpha=0.05):
    """Exact conservative CI for (n01-n10)/n_total via discordant-pair binomial CI."""
    n_disc = n01 + n10
    if n_disc == 0:
        return [0.0, 0.0]
    lo, hi = clopper(n01, n_disc, alpha)
    return [(2 * lo - 1) * n_disc / n_total, (2 * hi - 1) * n_disc / n_total]


def state(result):
    if result['out'].get('status') != 'ok':
        return 'interface_failed'
    value = result['out']['value']
    choice = value.get('option_label')
    if choice is None or choice == 'no_option':
        return None
    return choice


def classify(choice, label):
    if choice is None:
        return 'no_option'
    if choice == label['original_correct_label']:
        return 'target'
    options = {x['label']: x for x in label['options']}
    if choice not in options:
        return 'nonpublic'
    return 'trap' if options[choice]['alignment_role'] == 'misleading_trap' else 'other'


def load_runs(out_root, arm, variant):
    base = out_root / 'runs' / arm / variant
    if not base.exists():
        return {}
    out = {}
    for result_file in sorted(base.glob('*.result.json')):
        out[result_file.stem.replace('.result', '')] = json.loads(result_file.read_text())
    return out


def pair_stat(runs_a, runs_b, labels):
    a = b = 0
    kinds = {}
    for key, label in labels.items():
        ra, rb = runs_a.get(key), runs_b.get(key)
        if ra is None or rb is None or ra['out'].get('status') != 'ok' or rb['out'].get('status') != 'ok':
            kinds[key] = 'incomplete'
            continue
        ca = classify(state(ra), label)
        cb = classify(state(rb), label)
        kind = ('target_maintained' if ca == cb == 'target'
                else 'wrong_to_target' if ca in ('trap', 'other') and cb == 'target'
                else 'target_to_wrong' if ca == 'target' and cb in ('trap', 'other')
                else 'no_option_to_target' if ca == 'no_option' and cb == 'target'
                else 'target_to_no_option' if ca == 'target' and cb == 'no_option'
                else 'wrong_to_wrong' if ca in ('trap', 'other') and cb in ('trap', 'other')
                else 'other_pair')
        kinds[key] = kind
        a += int(ca == 'target' and cb in ('trap', 'other'))
        b += int(ca in ('trap', 'other') and cb == 'target')
    n_disc = a + b
    return {
        'target_to_wrong': a, 'wrong_to_target': b,
        'net': b - a,
        'mcnemar_p': binom_two_sided(min(a, b), n_disc),
        'diff_ci95': paired_ci(b, a, len(labels)),
        'kinds': {k: sum(1 for x in kinds.values() if x == k) for k in set(kinds.values())},
    }


def counts_for(runs, labels):
    counts = {'target': 0, 'trap': 0, 'other': 0, 'no_option': 0, 'interface_failed': 0, 'nonpublic': 0, 'missing': 0}
    for key, label in labels.items():
        r = runs.get(key)
        if r is None:
            counts['missing'] += 1
            continue
        if r['out'].get('status') != 'ok':
            counts['interface_failed'] += 1
            continue
        counts[classify(state(r), label)] += 1
    return counts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(HERE / 'results'))
    args = parser.parse_args()
    out_root = Path(args.out)
    labels = json.loads((OB / 'offline' / 'labels.json').read_text())['tasks']

    seeds = sorted({p.name for p in (out_root / 'runs' / 'plain').glob('seed*')}) if (out_root / 'runs' / 'plain').exists() else []
    scores = {'seeds': seeds, 'plain': {}, 'v5': {}, 'paired': {}, 'paired_extra': {}, 'sc3': {}, 'tab': {}, 'clean': {}}

    plain_runs = {v: load_runs(out_root, 'plain', v) for v in seeds}
    v5_runs = {v: load_runs(out_root, 'v5', v) for v in seeds}

    for v in seeds:
        scores['plain'][v] = counts_for(plain_runs[v], labels)
        scores['v5'][v] = counts_for(v5_runs[v], labels)
        scores['paired'][v] = pair_stat(plain_runs[v], v5_runs[v], labels)

    import statistics
    for arm_name in ('plain', 'v5'):
        targets = [scores[arm_name][v]['target'] for v in seeds if scores[arm_name][v]]
        if len(targets) >= 2:
            scores[arm_name]['mean_target'] = statistics.mean(targets)
            scores[arm_name]['stdev_target'] = statistics.stdev(targets)

    sc3_counts = {'target': 0, 'trap': 0, 'other': 0, 'no_option': 0, 'tie': 0, 'interface_failed': 0}
    sc3_picks = {}
    for key, label in labels.items():
        picks = []
        ok = True
        for v in seeds:
            r = plain_runs[v].get(key)
            if r is None or r['out'].get('status') != 'ok':
                ok = False
                break
            picks.append(state(r))
        if not ok:
            sc3_counts['interface_failed'] += 1
            continue
        sc3_picks[key] = picks
        votes = [p for p in picks if p is not None]
        if not votes:
            sc3_counts['no_option'] += 1
            continue
        top = max(set(votes), key=votes.count)
        if votes.count(top) * 2 <= len(votes):
            sc3_counts['tie'] += 1
            continue
        sc3_counts[classify(top, label)] += 1
    scores['sc3'] = sc3_counts

    tab_runs = load_runs(out_root, 'tab', 'tab')
    clean_runs = load_runs(out_root, 'clean', 'clean')
    scores['tab'] = counts_for(tab_runs, labels)
    scores['clean'] = counts_for(clean_runs, labels)

    if seeds:
        base = plain_runs[seeds[0]]
        scores['paired_extra']['tab_vs_plain'] = pair_stat(base, tab_runs, labels)
        scores['paired_extra']['clean_vs_plain'] = pair_stat(base, clean_runs, labels)
        sc3_runs = {k: {'out': {'status': 'ok', 'value': {'option_label': (max(set([p for p in v if p is not None]), key=[p for p in v if p is not None].count) if [p for p in v if p is not None] and [p for p in v if p is not None].count(max(set([p for p in v if p is not None]), key=[p for p in v if p is not None].count)) * 2 > len(v) else None)}}} for k, v in sc3_picks.items()}
        scores['paired_extra']['sc3_vs_plain'] = pair_stat(base, sc3_runs, labels)

    (out_root / 'scores.json').write_text(json.dumps(scores, indent=2), encoding='utf-8')
    slim = {k: scores[k] for k in ('plain', 'v5', 'paired', 'paired_extra', 'sc3', 'tab', 'clean')}
    for arm in ('plain', 'v5'):
        for v in seeds:
            if v in slim[arm]:
                slim[arm][v].pop('missing', None)
    print(json.dumps(slim, indent=2))


if __name__ == '__main__':
    main()
