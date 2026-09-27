"""Snapshot completed results without modifying them; ongoing work excluded."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--terminal', action='store_true')
    args = p.parse_args()
    root = HERE / 'runs' / args.run
    summary = read(root / 'summary.json')
    if args.terminal and summary['status'] not in ('finished', 'stopped'):
        raise ValueError('Not terminal')
    selected = []
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix == '.tmp':
            continue
        rel = path.relative_to(root)
        if args.terminal or rel.parts[0] == 'runtime_source' or len(rel.parts) == 1:
            selected.append(path)
        elif (root / rel.parts[0] / 'result.json').exists():
            state = read(root / rel.parts[0] / 'result.json')['status']
            if state in ('completed', 'interface_failed'):
                selected.append(path)
    # Ledger snapshot metadata is copied, not rewritten in the original ledger.
    meta = {'snapshot_at': datetime.now(timezone.utc).isoformat(), 'run': args.run,
            'terminal': args.terminal, 'status': summary['status'],
            'ledger': read(HERE / 'ledger.json'), 'files': {str(x.relative_to(HERE)): digest(x) for x in selected}}
    with tarfile.open(args.output, 'x:gz') as archive:
        for path in selected:
            archive.add(path, arcname=str(path.relative_to(HERE)))
    changed = [str(x.relative_to(HERE)) for x in selected if digest(x) != meta['files'][str(x.relative_to(HERE))]]
    meta.update(files_changed_during_snapshot=changed, archive_sha256=digest(args.output),
                bytes=args.output.stat().st_size)
    args.output.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in meta.items() if k not in ('ledger', 'files')}))

if __name__ == '__main__':
    main()
