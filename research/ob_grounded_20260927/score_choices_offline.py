"""Label agreement after freezing, never a task-execution or O/B truth score."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def label_class(label, alignment):
    if not alignment.get('supported'):
        return 'unsupported_mapping'
    if label is None:
        return 'no_option'
    match = next((x for x in alignment['options'] if x['label'] == label), None)
    if match is None:
        return 'not_a_public_option'
    role = match.get('alignment_role', match.get('role'))
    return {'correct': 'matches_original_target', 'misleading_trap': 'original_trap_option',
            'neutral_or_irrelevant': 'other_original_option'}.get(role, 'unknown_original_role')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--alignment', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    labels = read(args.alignment)
    if labels['freeze_sha256'] != sha(HERE / 'FREEZE.json'):
        raise ValueError('Label mapping belongs to another freeze')
    frozen = read(HERE / 'FREEZE.json')
    for file, identity in frozen['runtime_hashes'].items():
        if sha(HERE / file) != identity:
            raise ValueError('Frozen runtime changed: ' + file)
    root = HERE / 'runs' / args.run
    if read(root / 'source_hashes.json') != frozen['runtime_hashes']:
        raise ValueError('Run is not the frozen candidate')
    summary = read(root / 'summary.json')
    if summary['panel'] not in ('confirm', 'full'):
        raise ValueError('Development inputs are a different panel')
    manifest = read(HERE / 'manifest.json')
    counts, old_counts, changes, all_transitions = Counter(), Counter(), Counter(), Counter()
    domains, candidates, families = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    rows = {}
    for key, unit in manifest['units'].items():
        if unit['panel'] != 'full' or (summary['panel'] == 'confirm' and not unit['confirm']):
            continue
        result = summary['units'].get(key, {'status': 'not_run'})
        alignment = labels['tasks'][key]
        choice = (result.get('choice') or {}).get('option_label')
        new = label_class(choice, alignment) if result['status'] == 'completed' else result['status']
        history_path = HERE / 'offline_source' / (unit['slug'] + '.json')
        history = read(history_path) if history_path.exists() else {}
        proposal = history.get('old_proposal') or {}
        old_label = (proposal.get('action') or {}).get('option')
        old = label_class(old_label, alignment) if old_label is not None else 'historical_proposal_unavailable'
        counts[new] += 1
        old_counts[old] += 1
        domains[unit['domain']][new] += 1
        candidates[unit['candidate_source']][new] += 1
        families[unit.get('family', 'unclassified')][new] += 1
        all_transitions[old + ' -> ' + new] += 1
        if old_label is not None and result['status'] == 'completed':
            changes[old + ' -> ' + new] += 1
        rows[key] = {'slug': unit['slug'], 'domain': unit['domain'], 'family': unit.get('family'),
                     'status': result['status'], 'new_option': choice, 'new_class': new,
                     'original_target': alignment.get('original_correct_label'),
                     'historical_Terra_option': old_label, 'historical_class': old,
                     'same_option': choice == old_label if choice is not None and old_label is not None else None,
                     'candidate_source': unit['candidate_source'], 'reused_from': result.get('reused_from'),
                     'old_source_sha256': sha(history_path) if history_path.exists() else None}
        if unit['slug'] == 'env008':
            rows[key]['existing_evidence_conflict_caveat'] = 'Preserve original scoring and prior evidence_conflict caveat; do not infer Wind has no visible support.'
    output = {'created': datetime.now(timezone.utc).isoformat(), 'run': args.run, 'run_state': summary['status'],
              'freeze_sha256': sha(HERE / 'FREEZE.json'), 'alignment_sha256': sha(args.alignment),
              'summary_sha256': sha(root / 'summary.json'), 'planned_units': len(rows),
              'new_label_agreement_counts': dict(counts), 'historical_cross_model_counts': dict(old_counts),
              'cross_model_transition_counts_NOT_causal_gain': dict(changes),
              'all_state_transitions_NOT_causal_gain': dict(all_transitions),
              'by_domain': {k: dict(v) for k, v in domains.items()},
              'by_family': {k: dict(v) for k, v in families.items()},
              'by_candidate_source': {k: dict(v) for k, v in candidates.items()}, 'units': rows,
              'business_submissions': 0, 'ob_semantic_accuracy_estimated': False,
              'scope': 'Static option-label alignment, not original scorer execution, human adjudication, same-model baseline gain, or agent task completion.'}
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in output.items() if k != 'units'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
