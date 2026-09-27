"""Resolve immutable per-unit evidence from partial snapshots to final run files."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root, snapshots):
    root = root.resolve()
    rows, issues = {}, []
    for snapshot in snapshots:
        metadata = json.loads(snapshot.read_text(encoding='utf-8'))
        matched, skipped, missing, changed = [], [], [], []
        if metadata['files_changed_during_snapshot']:
            issues.append('unstable_snapshot:' + snapshot.name)
        for relative, identity in metadata['files'].items():
            path = PurePosixPath(relative.replace('\\', '/'))
            if len(path.parts) < 3 or path.parts[:2] != ('runs', metadata['run']) or '..' in path.parts:
                issues.append('unexpected_path:' + snapshot.name + ':' + relative)
                continue
            if len(path.parts) == 3 and path.name == 'summary.json':
                # The running summary is expected to change. Its old hash remains in metadata.
                skipped.append(relative)
                continue
            target = (root / Path(*path.parts)).resolve()
            if root not in target.parents:
                issues.append('outside_workspace:' + snapshot.name + ':' + relative)
                continue
            if not target.is_file():
                missing.append(relative)
            elif digest(target) != identity:
                changed.append(relative)
            else:
                matched.append(relative)
        if missing or changed:
            issues.append('unresolved_evidence:' + snapshot.name)
        rows[snapshot.name] = {
            'metadata_sha256': digest(snapshot), 'original_archive_sha256': metadata['archive_sha256'],
            'snapshot_at': metadata['snapshot_at'], 'run': metadata['run'],
            'matched_canonical_paths': matched, 'missing': missing, 'changed': changed,
            'mutable_summaries_not_treated_as_immutable': skipped,
        }
    return {'snapshot_evidence_resolution_passed': not issues, 'issues': issues, 'snapshots': rows,
            'scope': 'Byte identity of per-unit evidence and runtime source against prior collector hashes. Not semantic truth, original partial archive reconstruction, or final-run completion. Running summaries and cumulative ledgers must not be substituted with final ones or added across snapshots.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshots', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    snapshots = args.snapshots or sorted(HERE.glob('ob_grounded_*partial*.json'))
    if not snapshots:
        raise ValueError('No snapshot metadata')
    result = audit(HERE, snapshots)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
    print(json.dumps({'passed': result['snapshot_evidence_resolution_passed'], 'issues': result['issues'],
                      'snapshots': len(snapshots), 'matched_file_references': sum(len(r['matched_canonical_paths']) for r in result['snapshots'].values())}))


if __name__ == '__main__':
    main()
