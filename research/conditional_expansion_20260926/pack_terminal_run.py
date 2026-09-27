"""Archive a terminal finished OR stopped run without relabelling its outcome."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    status = json.loads((a.source / 'summary.json').read_text(encoding='utf-8'))['status']
    if status not in ('finished', 'stopped'):
        raise ValueError('Source is not terminal')
    paths = sorted(x for x in a.source.rglob('*') if x.is_file())
    before = {x.relative_to(a.source).as_posix(): sha(x) for x in paths}
    with tarfile.open(a.output, 'x:gz') as archive:
        for path in paths:
            archive.add(path, arcname=a.source.name + '/' + path.relative_to(a.source).as_posix(), recursive=False)
    after = {x.relative_to(a.source).as_posix(): sha(x) for x in paths}
    if before != after:
        raise ValueError('Source changed while archiving; archive invalid')
    print(json.dumps({'status': status, 'files': len(paths), 'source_unchanged': True,
                      'archive_sha256': sha(a.output), 'bytes': a.output.stat().st_size}))


if __name__ == '__main__':
    main()
