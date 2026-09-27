"""Seal prospective runtime and create a public-only upload archive."""
import json
from pathlib import Path
import zipfile
from engine import HERE, read, sha, save_new, stamp


def main():
    files = sorted([*HERE.glob('*.py'), *[HERE / n for n in
                    ('config.json', 'manifest.json', 'schedule.json', 'PROTOCOL.md', 'PREPARATION.json')],
                    *HERE.glob('data/*/*'), HERE / 'controls/blank.png'])
    excluded = {'evaluate.py', 'build_review.py', 'package_delivery.py', 'qa_viewer.py'}
    files = [p for p in files if p.name not in excluded and p.is_file()]
    manifest = {p.relative_to(HERE).as_posix(): sha(p) for p in files}
    assert not any(name.startswith('offline/') or name.startswith('runs/') for name in manifest)
    save_new(HERE / 'RUNTIME_SEAL.json', {'at': stamp(), 'files': manifest,
        'scope': 'all online inputs, prompts, schemas, runner and helpers before first model request'})
    with zipfile.ZipFile(HERE / 'ONLINE_BUNDLE.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for p in files + [HERE / 'RUNTIME_SEAL.json']:
            archive.write(p, p.relative_to(HERE).as_posix())
    save_new(HERE / 'ONLINE_UPLOAD_MANIFEST.json', {'at': stamp(), 'members': manifest,
        'archive_sha256': sha(HERE / 'ONLINE_BUNDLE.zip'), 'seal_sha256': sha(HERE / 'RUNTIME_SEAL.json'),
        'offline_labels_or_prior_results_included': False})
    print(json.dumps({'files': len(files)+1, 'zip_bytes': (HERE / 'ONLINE_BUNDLE.zip').stat().st_size,
                      'seal_sha256': sha(HERE / 'RUNTIME_SEAL.json')}))


if __name__ == '__main__':
    main()
