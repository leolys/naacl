"""Package finalized diagnostic evidence without altering any run or source file."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
REQUIRED_JSON = ('config.json', 'manifest.json', 'FREEZE.json', 'FINAL_ACCOUNTING.json',
                 'FINAL_ARTIFACT_AUDIT.json', 'FULL_LABEL_AGREEMENT.json', 'FINAL_COSTS.json',
                 'ORIGINAL_LABEL_ALIGNMENT_v2.json', 'PUBLIC_INPUT_AUDIT.json',
                 'ZH_EXACT_CACHE.json', 'SUPPLIED_CANDIDATES_ZH.json', 'NEW_EVIDENCE_ZH_v2.json', 'NOTES_v3_full.json',
                 'NOTES_v3_confirm.json', 'NOTES_v3_dev.json', 'NOTES_v2_dev.json', 'NOTES_v1_dev.json',
                 'ob_grounded_v3_confirm_final.json', 'ob_grounded_v3_full_final.json',
                 'SNAPSHOT_LINK_AUDIT.json')
REQUIRED_DOCS = ('README.md', 'REPORT.md', 'NEXT_ACTION.md', 'FINAL_COMPLETION_AUDIT.md')
# A credential prefix is a token boundary, not the suffix of a word such as
# "task-condition-to-action". Keep conservative matching for actual headers/keys.
SECRET = re.compile(rb'(?<![A-Za-z0-9_])(?:Bearer\s+[A-Za-z0-9_\-]{18,}|sk-[A-Za-z0-9_\-]{18,})')


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--view', type=Path, required=True)
    parser.add_argument('--qa', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if json.loads((HERE / 'runs/v3_full/summary.json').read_text(encoding='utf-8'))['status'] != 'finished':
        raise ValueError('Full run is not finalized')
    files = set()
    for pattern in ('*.py', '*.md', '*.xml'):
        files.update(HERE.glob(pattern))
    # Keep snapshot hashes/ledgers as provenance, without duplicating all image requests.
    files.update(HERE.glob('ob_grounded_*partial*.json'))
    files.update(HERE.glob('ob_grounded_*_final.json'))
    for name in REQUIRED_JSON + REQUIRED_DOCS:
        path = HERE / name
        if not path.is_file():
            raise FileNotFoundError(name)
        files.add(path)
    for name, flag in (('FINAL_ARTIFACT_AUDIT.json', 'artifact_audit_passed'),
                       ('SNAPSHOT_LINK_AUDIT.json', 'snapshot_evidence_resolution_passed')):
        if json.loads((HERE / name).read_text(encoding='utf-8')).get(flag) is not True:
            raise ValueError('Unresolved artifact audit: ' + name)
    for directory in ('data', 'offline_source', 'runs', 'service_snapshot'):
        files.update(p for p in (HERE / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for directory in (args.view.resolve(), args.qa.resolve()):
        if not directory.is_dir() or HERE not in directory.parents:
            raise ValueError('Viewer and QA must be explicit existing directories inside the diagnostic workspace')
        files.update(p for p in directory.rglob('*') if p.is_file())
    qa = json.loads((args.qa / 'QA.json').read_text(encoding='utf-8'))
    if qa.get('passed') is not True:
        raise ValueError('Viewer QA has unresolved display issues')
    if qa.get('tested_html_sha256') != sha_bytes((args.view / 'OB_GROUNDED_REVIEW.html').read_bytes()):
        raise ValueError('QA does not identify these exact viewer bytes')
    identities = {}
    for path in sorted(files):
        raw = path.read_bytes()
        if path.suffix in ('.py', '.md', '.json', '.html', '.txt', '.xml') and SECRET.search(raw):
            raise ValueError('Potential credential; inspect before packaging: ' + str(path.relative_to(HERE)))
        identities[path.relative_to(HERE).as_posix()] = {'sha256': sha_bytes(raw), 'bytes': len(raw)}
    manifest = {'created': datetime.now(timezone.utc).isoformat(), 'files': identities,
                'view': args.view.resolve().relative_to(HERE).as_posix() + '/OB_GROUNDED_REVIEW.html',
                'scope': 'Original images and public inputs, candidate provenance, frozen source, all five runs, reports and final offline viewer. No model weights, credentials or prior repository required for viewing.'}
    with ZipFile(args.output, 'x', compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(HERE).as_posix())
        archive.writestr('DELIVERY_FILE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        for name, identity in identities.items():
            if sha_bytes(archive.read(name)) != identity['sha256']:
                raise ValueError('Packaged identity changed: ' + name)
    result = {'archive': str(args.output), 'files': len(identities), 'bytes': args.output.stat().st_size,
              'sha256': sha_bytes(args.output.read_bytes()), 'crc_and_all_file_hashes_verified': True}
    with args.output.with_suffix('.manifest.json').open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
