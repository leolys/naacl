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
    def lower():
        if k == 0:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if (1 - mid) ** n <= alpha / 2:
                hi = mid
            else:
                lo = mid
        return hi

    def upper():
        if k == n:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if mid ** n <= alpha / 2:
                lo = mid
            else:
                hi = mid
        return lo

    return lower(), upper()


def paired_ci(n01, n10, n_total, alpha=0.05):
    """Exact conservative CI for (n01-n10)/n_total via discordant-pair binomial CI."""
    n_disc = n01 + n10
    if n_disc == 0:
        return [0.0, 0.0]
    lo, hi = clopper(n01, n_disc, alpha)
    return [(2 * lo - n_disc) / n_total, (2 * hi - n_disc) / n_total]


def state(result):
    if result['out'].get('status') != 'ok':
        return 'interface_failed'
    value = result['out']['value']
    choice = value.get('option_label')
    if choice is None:
        return 'no_option'
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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(HERE / 'results'))
    args = parser.parse_args()
    out_root = Path(args.out)
    labels = json.loads((OB / 'offline' / 'labels.json').read_text())['tasks']

    seeds = sorted({p.name for p in (out_root / 'runs' / 'plain').glob('seed*')} ) if (out_root / 'runs' / 'plain').exists() else []
    scores = {'seeds': seeds, 'plain': {}, 'v5': {}, 'paired': {}, 'sc3': {}, 'tab': {}, 'clean': {}}

    plain_runs = {v: load_runs(out_root, 'plain', v) for v in seeds}
    v5_runs = {v: load_runs(out_root, 'v5', v) for v in seeds}

    for v in seeds:
        for arm_name, runs in (('plain', plain_runs[v]), ('v5', v5_runs[v])):
            counts = {'target': 0, 'trap': 0, 'other': 0, 'no_option': 0, 'interface_failed': 0, 'missing': 0}
            for key, label in labels.items():
                r = runs.get(key)
                if r is None:
                    counts['missing'] += 1
                    continue
                if r['out'].get('status') != 'ok':
                    counts['interface_failed'] += 1
                    continue
                counts[classify(state(r), label)] += 1
            scores[arm_name][v] = counts
        a = b = 0
        kinds = {}
        for key, label in labels.items():
            rp, rv = plain_runs[v].get(key), v5_runs[v].get(key)
            if rp is None or rv is None or rp['out'].get('status') != 'ok' or rv['out'].get('status') != 'ok':
                kinds[key] = 'incomplete'
                continue
            cp = classify(state(rp), label)
            cv = classify(state(rv), label)
            kind = ('target_maintained' if cp == cv == 'target'
                    else 'wrong_to_target' if cp in ('trap', 'other') and cv == 'target'
                    else 'target_to_wrong' if cp == 'target' and cv in ('trap', 'other')
                    else 'no_option_to_target' if cp == 'no_option' and cv == 'target'
                    else 'target_to_no_option' if cp == 'target' and cv == 'no_option'
                    else 'wrong_to_wrong' if cp in ('trap', 'other') and cv in ('trap', 'other')
                    else 'other_pair')
            kinds[key] = kind
            a += int(cp == 'target' and cv in ('trap', 'other'))
            b += int(cp in ('trap', 'other') and cv == 'target')
        n_disc = a + b
        scores['paired'][v] = {
            'target_to_wrong': a, 'wrong_to_target': b,
            'net': b - a,
            'mcnemar_p': binom_two_sided(min(a, b), n_disc),
            'diff_ci95': paired_ci(b, a, len(labels)),
            'kinds': {k: sum(1 for x in kinds.values() if x == k) for k in set(kinds.values())},
        }

    import statistics
    for arm_name in ('plain', 'v5'):
        targets = [scores[arm_name][v]['target'] for v in seeds if scores[arm_name][v]]
        if len(targets) >= 2:
            scores[arm_name]['mean_target'] = statistics.mean(targets)
            scores[arm_name]['stdev_target'] = statistics.stdev(targets)

    # self-consistency over the three plain seeds
    sc3_counts = {'target': 0, 'trap': 0, 'other': 0, 'no_option': 0, 'tie': 0, 'interface_failed': 0}
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

    for arm_name in ('tab', 'clean'):
        runs = load_runs(out_root, arm_name, arm_name)
        counts = {'target': 0, 'trap': 0, 'other': 0, 'no_option': 0, 'interface_failed': 0, 'missing': 0}
        for key, label in labels.items():
            r = runs.get(key)
            if r is None:
                counts['missing'] += 1
                continue
            if r['out'].get('status') != 'ok':
                counts['interface_failed'] += 1
                continue
            counts[classify(state(r), label)] += 1
        scores[arm_name] = counts

    (out_root / 'scores.json').write_text(json.dumps(scores, indent=2), encoding='utf-8')
    print(json.dumps({k: scores[k] for k in ('plain', 'v5', 'paired', 'sc3', 'tab', 'clean')}, indent=2))


if __name__ == '__main__':
    main()
