"""Create a checked archive of the new run and offline review, never old files."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def main():
    files = sorted(p for p in HERE.rglob('*') if p.is_file()
                   and '__pycache__' not in p.parts
                   and not any(s.startswith('partial_') for s in p.relative_to(HERE).parts)
                   and p.suffix not in ('.tgz', '.zip', '.pyc') and p.name != 'DELIVERY.json')
    target = HERE / 'OB_ONLY_ARTIFACTS.zip'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity error')
    metadata = {'file': target.name, 'files': len(files), 'bytes': target.stat().st_size,
                'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'crc_verified': True,
                'run_status': json.loads((HERE / 'run_live_001/summary.json').read_text(encoding='utf-8'))['status'],
                'standalone_html': 'review_001/OB_ONLY_REVIEW.html',
                'note': 'The HTML is portable; source/runtime dependencies and raw requests are archived, not a standalone model installation.'}
    (HERE / 'DELIVERY.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
