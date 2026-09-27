"""Offline repeated-input audit; no inference or semantic equivalence claim."""
import argparse
from collections import Counter
from pathlib import Path
from evaluate import HERE, digest, read, save_new


def compare():
    manifest = read(HERE / 'manifest.json')
    ids = [key for key, value in manifest['units'].items() if value['panel'] == 'dev']
    roots = [HERE / 'runs' / (version + '_dev') for version in ('v4', 'v7')]
    for root in roots:
        summary = read(root / 'summary.json')
        if summary['status'] != 'finished' or set(summary['units']) != set(ids):
            raise ValueError('Both complete fixed development panels are required')
    rows, counts, sources = {}, {stage: Counter() for stage in ('read', 'verify')}, {}
    for root in roots:
        sources[str((root / 'summary.json').relative_to(HERE))] = digest(root / 'summary.json')
    for key in ids:
        row = {}
        for stage in ('read', 'verify'):
            request_paths = [root / key / stage / 'request.json' for root in roots]
            accepted_paths = [root / key / stage / 'accepted.json' for root in roots]
            available = all(path.exists() for path in request_paths + accepted_paths)
            evidence = {str(path.relative_to(HERE)): digest(path)
                        for path in request_paths + accepted_paths if path.exists()}
            value = {'both_actual_requests_and_accepted_available': available,
                     'evidence_files': evidence}
            counts[stage]['units'] += 1
            if available:
                requests = [read(path) for path in request_paths]
                accepted = [read(path) for path in accepted_paths]
                same_request = requests[0] == requests[1]
                same_accepted = accepted[0] == accepted[1]
                same_prompt = requests[0]['messages'][0]['content'] == requests[1]['messages'][0]['content']
                value.update(request_json_identical=same_request, system_prompt_identical=same_prompt,
                             accepted_json_identical=same_accepted)
                counts[stage]['both_available'] += 1
                counts[stage]['same_request_json'] += int(same_request)
                counts[stage]['same_system_prompt'] += int(same_prompt)
                counts[stage]['same_accepted_json'] += int(same_accepted)
                counts[stage]['same_request_different_accepted_json'] += int(same_request and not same_accepted)
            else:
                counts[stage]['unavailable'] += 1
            row[stage] = value
        rows[key] = row
    return {'versions': ['v4', 'v7'], 'panel': 'fixed_dev24', 'source_files': sources,
            'counts': {key: dict(value) for key, value in counts.items()}, 'units': rows,
            'extra_model_calls': 0,
            'interpretation': 'Exact JSON equality only. Different wording is not automatically a semantic or correctness change. Same prompts do not establish same intermediate outputs; this is not a separate randomized ablation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare()
    save_new(args.output, result)
    print(result['counts'])
