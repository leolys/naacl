"""Create a credential-screened transport archive from an allowlisted inventory.

No source mutation, no credentials in audit output, no original compressed
archives (they would bypass recursive scope and secret checks).
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
from inventory import excluded, TEXT_SUFFIXES
from sanitize import clean, assert_clean


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe relative path')
    return p


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    inv = json.loads(a.inventory.read_text(encoding='utf-8'))
    root = Path(inv['root']).resolve()
    records = []
    omissions = []
    counts = Counter()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(a.output, 'x', ZIP_DEFLATED, compresslevel=5) as archive:
        for index, row in enumerate(inv['files']):
            rel = safe_relative(row['path'])
            if excluded(rel.parts):
                omissions.append({'path': str(rel), 'reason': 'final_scope_filter'})
                continue
            path = root.joinpath(*rel.parts)
            if path.is_symlink() or root not in path.resolve().parents:
                raise ValueError('Source escaped root: ' + str(rel))
            raw = path.read_bytes()
            if len(raw) != row['bytes']:
                raise ValueError('Source changed size after inventory: ' + str(rel))
            data, changes = clean(raw) if path.suffix.lower() in TEXT_SUFFIXES else (raw, [])
            if path.suffix.lower() in TEXT_SUFFIXES:
                assert_clean(data)
            archive.writestr(str(rel), data)
            records.append({'path': str(rel), 'source_sha256': digest(raw),
                            'export_sha256': digest(data), 'source_bytes': len(raw),
                            'export_bytes': len(data), 'redactions': changes})
            for item in changes:
                counts[item['kind']] += item['count']
            if index and index % 5000 == 0:
                print(json.dumps({'progress_files': index, 'side': inv['side']}), flush=True)
        manifest = {'kind': 'sanitized_export_copy', 'side': inv['side'],
                    'source_inventory_sha256': digest(a.inventory.read_bytes()),
                    'files': records, 'omitted': omissions,
                    'credential_pattern_counts': dict(counts),
                    'source_unchanged': True, 'original_hashes_are_provenance_not_export_hashes': True}
        archive.writestr('EXPORT_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(a.output) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        for row in records:
            if digest(archive.read(row['path'])) != row['export_sha256']:
                raise ValueError('ZIP SHA failure: ' + row['path'])
    with a.output.open('rb') as inp:
        h = hashlib.sha256()
        for chunk in iter(lambda: inp.read(1024 * 1024), b''):
            h.update(chunk)
    result = {'archive': a.output.name, 'file_count': len(records),
              'bytes': a.output.stat().st_size, 'sha256': h.hexdigest(),
              'crc_and_all_file_sha_verified': True, 'redaction_counts': dict(counts)}
    with a.output.with_suffix('.receipt.json').open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
