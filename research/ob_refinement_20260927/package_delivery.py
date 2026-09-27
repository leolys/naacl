"""Package this new round only; excludes archives/partials duplicate evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED
from evaluate import HERE, digest, read, save_new

SECRET = re.compile(rb'(?<![A-Za-z0-9_])(?:Bearer\s+[A-Za-z0-9_\-]{18,}|sk-[A-Za-z0-9_\-]{18,})')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--view', type=Path, required=True)
    parser.add_argument('--qa', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    view, qa = args.view.resolve(), args.qa.resolve()
    if HERE not in view.parents or HERE not in qa.parents:
        raise ValueError('Explicit review/QA folders must be inside this new round')
    checked = read(qa / 'QA.json')
    html_path = view / 'OB_REFINEMENT_REVIEW.html'
    if not checked['passed'] or checked['tested_html_sha256'] != digest(html_path):
        raise ValueError('Exact final viewer has not passed display QA')
    required = ('REPORT.md', 'NEXT_ACTION.md', 'PLAN.md', 'PROGRESS.md', 'EXECUTION.md',
                'VERSION_HISTORY.md', 'config.json', 'manifest.json', 'FINAL_COSTS.json',
                'FINAL_INTEGRITY.json')
    for name in required:
        if not (HERE / name).is_file():
            raise ValueError('Missing final artifact: ' + name)
    files = set()
    for pattern in ('*.py', '*.md', 'offline_tests_*.xml', 'tests_*.xml', 'FREEZE.json'):
        files.update(HERE.glob(pattern))
    # Terminal snapshots are represented by their extracted evidence in runs/.
    # Partial metadata references duplicate, deliberately unbundled directories.
    files.update(p for p in HERE.glob('ob_refinement_*.json')
                 if re.fullmatch(r'ob_refinement_(?:plain|v[4-7])_(?:dev|application)_001\.json', p.name))
    files.update(HERE / name for name in required)
    for folder in ('data', 'runs', 'legacy', 'offline', 'analysis', 'audit'):
        files.update(p for p in (HERE / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for folder in (view, qa):
        files.update(p for p in folder.rglob('*') if p.is_file())
    identities = {}
    for path in sorted(files):
        if path.suffix in ('.py', '.md', '.json', '.html', '.txt', '.xml') and SECRET.search(path.read_bytes()):
            raise ValueError('Potential secret in package: ' + str(path.relative_to(HERE)))
        identities[path.relative_to(HERE).as_posix()] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    manifest = {'created': datetime.now(timezone.utc).isoformat(), 'files': identities,
                'viewer': html_path.relative_to(HERE).as_posix(),
                'scope': 'Original public images/inputs, real requests/responses, old-result offline comparator, all new development versions, frozen application if executed, source, tests, and Chinese review. No weights or credentials.'}
    with ZipFile(args.output, 'x', ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(HERE).as_posix())
        archive.writestr('DELIVERY_FILE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    import hashlib
    with ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise ValueError('CRC failure')
        for name, info in identities.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != info['sha256']:
                raise ValueError('Packaged identity mismatch')
    result = {'path': str(args.output.resolve()), 'files': len(identities), 'bytes': args.output.stat().st_size,
              'sha256': digest(args.output), 'all_crc_and_hashes_verified': True}
    save_new(args.output.with_suffix('.manifest.json'), result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
