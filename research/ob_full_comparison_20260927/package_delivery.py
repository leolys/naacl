"""Package stable evidence in sibling-preserving layout; no secrets/caches/old partials."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED
from evaluate import HERE, read, sha, new

SECRET = re.compile(rb'(?<![A-Za-z0-9_])(?:Bearer\s+[A-Za-z0-9_\-]{18,}|sk-[A-Za-z0-9_\-]{18,})')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    final = HERE / 'captures/final_001'
    analysis = HERE / 'analysis/final_001'
    view = HERE / 'review_final_002'
    qa = HERE / 'qa_final_002'
    checked = read(qa / 'QA.json')
    assert checked['passed'] and checked['tested_html_sha256'] == sha(view / 'OB_FULL_COMPARISON_REVIEW.html')
    integrity = read(analysis / 'INTEGRITY.json')
    summary = read(analysis / 'SUMMARY.json')
    assert integrity['complete_evidence_panel']
    assert integrity['capture_sha256'] == sha(final / 'CAPTURE_MANIFEST.json') == summary['source_hashes']['capture/CAPTURE_MANIFEST.json']
    assert summary['all840_terminal'] and summary['all_workers_finished'] and summary['runtime_preserved_all']
    for name in ('REPORT.md', 'NEXT_ACTION.md', 'EXECUTION_COMMANDS.md', 'FINAL_ADVERSARIAL_REVIEW.md'):
        assert (HERE / name).is_file(), name
    files = set()
    for pattern in ('*.py', '*.md', '*.json'):
        files.update(HERE.glob(pattern))
    for folder in (HERE / 'data', HERE / 'controls', HERE / 'offline', HERE / 'checks', final, analysis, view, qa):
        files.update(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                     and 'cache' not in p.parts and p.suffix not in ('.tmp', '.lock'))
    # Exact historical references used by the offline label-digest/source-equality tests.
    old = HERE.parent / 'ob_refinement_20260927'
    grounded = HERE.parent / 'ob_grounded_20260927'
    files.add(old / 'analysis/v7_dev.json')
    files.add(old / 'schema.py')
    files.update(old / ('prompts_' + v + '.py') for v in ('plain', 'v4', 'v5', 'v6', 'v7'))
    files.update([grounded / 'schema.py', grounded / 'prompts_v3.py'])
    identities = {}
    for path in sorted(files):
        assert path.is_file(), path
        data = path.read_bytes()
        if path.suffix in ('.py', '.md', '.json', '.html', '.log', '.txt', '.xml') and SECRET.search(data):
            raise ValueError('Potential secret: ' + str(path))
        key = path.relative_to(HERE.parent).as_posix()
        identities[key] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    manifest = {'created': datetime.now(timezone.utc).isoformat(), 'files': identities,
        'viewer': HERE.name + '/review_final_002/OB_FULL_COMPARISON_REVIEW.html',
        'layout': 'Keep the sibling directories for offline evaluate/test reproduction.',
        'scope': '140 fixed public inputs/images; six fresh versions, every request/response/ledger; offline labels/history; source; analysis; review; no weights/cache/credentials. Historical sibling files are exact references, not changed experiments.'}
    with ZipFile(args.output, 'x', ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(HERE.parent).as_posix())
        archive.writestr('DELIVERY_FILE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(args.output) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert archive.testzip() is None
        for name, identity in identities.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == identity['sha256'], name
    result = {'path': str(args.output.resolve()), 'files': len(identities), 'bytes': args.output.stat().st_size,
              'sha256': sha(args.output), 'all_crc_and_hashes_verified': True}
    new(args.output.with_suffix('.manifest.json'), result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
