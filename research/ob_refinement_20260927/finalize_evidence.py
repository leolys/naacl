"""Offline terminal accounting and identity aggregation; no network or inference."""
from collections import Counter
from datetime import datetime, timezone
import re

from costs import summarize
from evaluate import HERE, digest, read, save_new
from integrity import validate_requests, verify_snapshot


def main():
    snapshots = [path for path in HERE.glob('ob_refinement_*.json')
                 if re.fullmatch(r'ob_refinement_(?:plain|v[4-7])_(?:dev|application)_001\.json', path.name)]
    if not snapshots:
        raise ValueError('No terminal evidence')
    snapshots.sort(key=lambda path: read(path)['snapshot_at'])
    checks = []
    for path in snapshots:
        meta = read(path)
        if not meta['terminal'] or meta['status'] != 'finished':
            raise ValueError('Only finished terminal runs may be aggregated')
        check = verify_snapshot(path)
        check['request_check'] = validate_requests(meta['run'])
        source = read(HERE / 'runs' / meta['run'] / 'source_hashes.json')
        if any(digest(HERE / name) != expected for name, expected in source.items()):
            raise ValueError('Current online source differs from recorded runtime: ' + meta['run'])
        check['runtime_source_hashes'] = source
        checks.append(check)
    costs = summarize(snapshots[-1])
    if (not costs['all_ledger_responses_available_locally']
            or costs['unknown_usage_attempts']
            or set(costs['by_run']) != {item['run'] for item in checks}):
        raise ValueError('Incomplete final cost or run evidence')

    # Check against identities captured before this round, not newly invented
    # expected hashes. No modifications to the historical source are made.
    manifest = read(HERE / 'manifest.json')
    old = HERE.parent / 'ob_grounded_20260927'
    if digest(old / 'manifest.json') != manifest['original_manifest_sha256']:
        raise ValueError('Historical manifest changed')
    if digest(old / 'runs/v3_full/summary.json') != manifest['original_summary_sha256']:
        raise ValueError('Historical comparator changed')
    if read(old / 'ORIGINAL_LABEL_ALIGNMENT_v2.json') != read(HERE / 'offline/labels.json'):
        raise ValueError('Original labels changed')
    old_identity = read(HERE / 'legacy/IDENTITY.json')['files']
    for old_name, copied in [('run.py', 'engine.py'), ('schema.py', 'schema.py')]:
        if digest(old / old_name) != old_identity[copied]:
            raise ValueError('Historical implementation changed')
    for key, unit in manifest['units'].items():
        comparisons = [(HERE / 'data' / key / 'input.json', unit['input_sha256']),
                       (HERE / 'data' / key / unit['image'], unit['image_sha256']),
                       (old / 'data' / key / unit['image'], unit['image_sha256']),
                       (old / 'data' / key / 'input.json', unit['old_input_sha256']),
                       (old / unit['candidate_source_path'], unit['candidate_source_sha256'])]
        if any(digest(path) != expected for path, expected in comparisons):
            raise ValueError('Fixed public input, image, or historical candidate changed: ' + key)
    report = {'created': datetime.now(timezone.utc).isoformat(), 'runs': checks,
              'manifest_sha256': digest(HERE / 'manifest.json'),
              'plan_sha256': digest(HERE / 'PLAN.md'),
              'total_actual_requests_checked': sum(item['request_check']['actual_request_files_checked'] for item in checks),
              'total_files_verified': sum(item['verified_files'] for item in checks),
              'public_inputs_and_original_images_checked': len(manifest['units']),
              'historical_inputs_candidates_comparator_and_labels_unchanged': True,
              'runtime_sources_match_current_recorded_versions': True,
              'run_status_counts': dict(Counter(read(HERE / 'runs' / item['run'] / 'summary.json')['status'] for item in checks)),
              'frozen': (HERE / 'FREEZE.json').exists(),
              'application_runs': [item['run'] for item in checks if item['run'].endswith('_application')],
              'meaning': 'File identities, original public projection, actual stage links, and raw response accounting only; not model semantic correctness or research effectiveness.'}
    save_new(HERE / 'FINAL_COSTS.json', costs)
    save_new(HERE / 'FINAL_INTEGRITY.json', report)
    print({'attempts': costs['attempts'], 'tokens': costs['known_usage'],
           'runs': len(checks), 'files': report['total_files_verified'],
           'requests': report['total_actual_requests_checked'],
           'fixed_inputs_checked': report['public_inputs_and_original_images_checked'],
           'application_runs': report['application_runs']})


if __name__ == '__main__':
    main()
