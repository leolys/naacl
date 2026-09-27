"""Verified local extraction into a new snapshot directory; never merge results."""
import argparse
import hashlib
from pathlib import Path
import zipfile
import json

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if not args.name.replace('_', '').isalnum():
        raise ValueError('simple snapshot name required')
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != args.sha256:
        raise ValueError('archive hash mismatch')
    destination = HERE / 'captures' / args.name
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.archive) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for name in archive.namelist():
            (destination / name).resolve().relative_to(destination.resolve())
        for name in archive.namelist():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as out:
                out.write(archive.read(name))
    manifest = json.loads((destination / 'CAPTURE_MANIFEST.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected, name
    print('Extracted verified capture:', destination, 'files:', len(manifest['files']))


if __name__ == '__main__':
    main()
