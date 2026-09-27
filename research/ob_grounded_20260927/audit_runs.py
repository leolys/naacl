"""Offline descriptive accounting. No correctness labels or model calls."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(root):
    summary = read(root / 'summary.json')
    tokens, stages, finishes, ob = Counter(), Counter(), Counter(), Counter()
    identical_reads = defaultdict(list)
    rows, new_responses, reused = {}, 0, 0
    for key, result in summary['units'].items():
        folder = HERE / result['reused_from'] if result.get('reused_from') else root / key
        reused += bool(result.get('reused_from'))
        checks = read(folder / 'verify/accepted.json') if (folder / 'verify/accepted.json').exists() else {'reviews': []}
        for rec in checks['reviews']:
            for o in rec['O']:
                ob['O_' + o['status']] += 1
            b = rec['B']
            if 'status' in b:
                ob['B_' + b['status']] += 1
            else:
                for axis in ('visual_decoding', 'task_applicability'):
                    ob['B_' + axis + '_' + b[axis]['status']] += 1
        req = folder / 'read/request.json'
        if req.exists():
            accepted = folder / 'read/accepted.json'
            identical_reads[digest(req)].append({'unit': key, 'request_sha256': digest(req),
                'accepted_sha256': digest(accepted) if accepted.exists() else None})
        if not result.get('reused_from'):
            for response in folder.glob('*/response_*.json'):
                new_responses += 1
                stages[response.parent.name] += 1
                body = read(response).get('body')
                if not isinstance(body, dict):
                    finishes['nonobject'] += 1
                    continue
                for name, value in (body.get('usage') or {}).items():
                    if isinstance(value, int):
                        tokens[name] += value
                for choice in body.get('choices', []):
                    finishes[str(choice.get('finish_reason'))] += 1
        rows[key] = {'status': result['status'], 'choice': result.get('choice'),
                     'failed_stage': result.get('failed_stage'), 'reused_from': result.get('reused_from')}
    return {'run': root.name, 'summary_sha256': digest(root / 'summary.json'),
            'status': summary['status'], 'states': dict(Counter(r['status'] for r in rows.values())),
            'interface_failures_by_stage': dict(Counter(r['failed_stage'] for r in rows.values() if r['status'] == 'interface_failed')),
            'new_archived_responses': new_responses, 'new_responses_by_stage': dict(stages),
            'new_usage': dict(tokens), 'finish_reasons': dict(finishes), 'reused_units': reused,
            'model_status_counts_not_accuracy': dict(ob), 'business_submissions': 0,
            'exact_repeated_read_requests': [v for v in identical_reads.values() if len(v) > 1],
            'units': rows,
            'limits': ['Counts describe model outputs, not adjudicated truth.',
                       'Repeated blind reads are planned pipeline repetitions, not independent tasks.',
                       'Archived response counts exclude unknown transport attempts; use global ledger for budget.']}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {name: audit(HERE / 'runs' / name) for name in args.runs}
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps({k: {a: b for a, b in v.items() if a not in ('units', 'exact_repeated_read_requests')}
                      for k, v in result.items()}, ensure_ascii=False))

if __name__ == '__main__':
    main()
