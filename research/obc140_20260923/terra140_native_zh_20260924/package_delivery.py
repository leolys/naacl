"""Package local deliverables; no upload, no source mutation, no credentials."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent


def require_current_checks(folder):
    def read(name):
        return json.loads((folder / name).read_text(encoding='utf-8'))
    state = read('run/run_state.json')
    if state.get('status') not in ('completed', 'finished_with_terminal_failures'):
        raise RuntimeError('Cannot package an unfinished or blocked run as a complete delivery')
    checks, browser = read('delivery_checks.json'), read('browser_check.json')
    if checks.get('engineering_status') != 'PASS' or browser.get('status') != 'PASS':
        raise RuntimeError('Current delivery and browser checks must pass before packaging')
    for filename, key in (('OBC140_TERRA_ZH_REVIEW.html','html_sha256'),
                          ('review_data_zh.json','review_data_sha256')):
        digest = hashlib.sha256((folder / filename).read_bytes()).hexdigest()
        if checks.get(key) != digest or browser.get(key) != digest:
            raise RuntimeError('Artifact changed or was not checked: ' + filename)
    records = checks.get('record_sha256', {})
    if len(records) != 140:
        raise RuntimeError('Expected checks for exactly 140 canonical records')
    for relative, expected in records.items():
        if not re.fullmatch(r'run/tasks/[A-Za-z0-9_-]+/record\.json', relative):
            raise RuntimeError('Unexpected canonical record path in delivery checks')
        if hashlib.sha256((folder / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Canonical record changed after checks: ' + relative)
    return checks


def credential_pattern_found(data):
    pattern = rb'(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{15,}'
    if re.search(pattern, data):
        return True
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return bool(re.search(pattern, data.decode('utf-16', errors='replace').encode('utf-8')))
    return False


def package():
    archive = HERE.parent / 'OBC140_TERRA_NATIVE_ZH_20260924.zip'
    if archive.exists():
        raise FileExistsError('Delivery archive exists; version explicitly, never overwrite')
    if not (HERE / 'OBC140_TERRA_ZH_REVIEW.html').is_file():
        raise FileNotFoundError('final standalone viewer not generated')
    require_current_checks(HERE)
    files = []
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or '.pytest_cache' in path.parts:
            continue
        if path.name.startswith(('PREVIEW_', 'preview_', 'review_data_preview')):
            continue
        if path.suffix == '.tmp' or path.name == 'run.lock':
            raise RuntimeError('Do not package active or interrupted run files')
        files.append((path, 'materials/' + path.relative_to(HERE).as_posix()))
    catalog = json.loads((HERE.parent / 'catalog.json').read_text(encoding='utf-8'))
    for entry in catalog['tasks']:
        for key in ('public_file','chart_file','offline_file'):
            path = HERE.parent / entry[key]
            files.append((path, 'original_inputs/' + entry[key]))
    files.append((HERE.parent / 'catalog.json', 'original_inputs/catalog.json'))
    trace = HERE.parents[2] / '.aris/traces/experiment-bridge/2026-09-24_terra140_utf8'
    for path in sorted(trace.glob('*')):
        if path.is_file():
            files.append((path, 'review_traces/' + path.name))
    for path, _ in files:
        if credential_pattern_found(path.read_bytes()):
            raise RuntimeError('Possible API credential in delivery candidate: ' + str(path))
    manifest = [{'file': target, 'bytes': path.stat().st_size,
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path, target in files]
    document = {'created_at': datetime.now(timezone.utc).isoformat(), 'files': manifest,
                'credential_scan': {'files_scanned': len(files), 'scope': 'All file bytes plus BOM-marked UTF-16 text; sk- credential pattern only',
                    'pattern_matches': 0, 'universal_secret_detection_claimed': False},
                'notes': ['Single HTML works offline on another computer.',
                          'Archive contains original inputs and raw public requests/responses; credentials are not intentionally included.',
                          'All included files passed a limited credential-pattern scan; this is not a guarantee covering every possible secret type.',
                          'Historical absolute paths remain provenance, not rewritten portability claims.',
                          'No GPU, browser business actions, or new API calls during packaging.']}
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path, target in files:
            bundle.write(path, target)
        bundle.writestr('PACKAGE_MANIFEST.json', json.dumps(document, ensure_ascii=False, indent=2))
    (HERE / 'PACKAGE_MANIFEST.json').write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    table = ['# Research Output Manifest', '', '| Timestamp | Skill | File | Stage | Description |',
             '|-----------|-------|------|-------|-------------|']
    table.extend('| 2026-09-24 | experiment-bridge / render-html | %s | implementation | %s bytes; SHA256 %s |'
                 % (row['file'], row['bytes'], row['sha256']) for row in manifest)
    (HERE / 'MANIFEST.md').write_text('\n'.join(table) + '\n', encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'files': len(files)}, ensure_ascii=False))


if __name__ == '__main__':
    package()
