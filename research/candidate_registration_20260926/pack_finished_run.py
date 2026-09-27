"""Archive completed files only, excluding mutable directory metadata on Ceph."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    summary = json.loads((args.source / 'summary.json').read_text())
    if summary['status'] != 'finished':
        raise ValueError('Only a completed fixed panel may be archived')
    if args.output.exists():
        raise FileExistsError('No archive overwrite')
    paths = sorted(p for p in args.source.rglob('*') if p.is_file())
    before = {p.relative_to(args.source).as_posix(): file_hash(p) for p in paths}
    with tarfile.open(args.output, 'x:gz') as archive:
        for path in paths:
            archive.add(path, arcname=args.source.name + '/' + path.relative_to(args.source).as_posix(), recursive=False)
    after = {p.relative_to(args.source).as_posix(): file_hash(p) for p in paths}
    if before != after:
        raise ValueError('A source file changed during archiving; do not use this archive')
    print(json.dumps({'files': len(paths), 'source_unchanged': True,
                      'archive_sha256': file_hash(args.output), 'bytes': args.output.stat().st_size}))


if __name__ == '__main__':
    main()
