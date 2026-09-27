"""Offline lexical caveats and candidate inventory, never model input or truth labels."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PATTERN = re.compile(r'mislabeled|mislead|decept|distort|truncat|reverse|invert', re.I)


def strings(value, path='$'):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, path + '.' + key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from strings(item, path + '[%d]' % i)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    records, o_counts, b_form, domains, families = Counter(), Counter(), Counter(), Counter(), Counter()
    rows = {}
    for key, unit in manifest['units'].items():
        if unit['panel'] != 'full':
            continue
        path = HERE / 'data' / key / 'input.json'
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != unit['input_sha256']:
            raise ValueError('Frozen input changed: ' + key)
        value = json.loads(path.read_text(encoding='utf-8'))
        matches = [{'path': p, 'text': s, 'lexemes': sorted(set(m.group().lower() for m in PATTERN.finditer(s)))}
                   for p, s in strings(value['public_task']) if PATTERN.search(s)]
        records[len(value['records'])] += 1
        for record in value['records']:
            o_counts[len(record['O'])] += 1
            b_form[type(record['B']).__name__] += 1
        domains[unit['domain']] += 1
        families[unit['family']] += 1
        rows[key] = {'input_sha256': digest, 'old_candidate_count': len(value['records']),
                     'O_count': sum(len(r['O']) for r in value['records']),
                     'public_lexical_hits': matches}
    output = {'created': datetime.now(timezone.utc).isoformat(), 'planned_tasks': len(rows),
              'old_candidate_count_distribution': dict(records), 'O_per_candidate_distribution': dict(o_counts),
              'B_storage_forms': dict(b_form), 'domains': dict(domains), 'families': dict(families),
              'public_keyword_pattern': PATTERN.pattern,
              'tasks_with_public_lexical_hits': [k for k, v in rows.items() if v['public_lexical_hits']],
              'units': rows,
              'interpretation': 'Mechanical lexical audit, not leakage certification or semantic classification. Existing public task fields remain unchanged. Candidate O/B text is intentionally outside this public-task scan; B may contain previous action conclusions.'}
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in output.items() if k != 'units'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
