"""Package new diagnostic only; exclude caches and duplicate transport archives."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def main():
    files = sorted(p for p in HERE.rglob('*') if p.is_file()
                   and '__pycache__' not in p.parts
                   and 'expanded_snapshot_001' not in p.parts
                   and p.suffix not in ('.tgz', '.zip', '.pyc')
                   and p.name != 'DELIVERY.json')
    target = HERE / 'CONDITIONAL_EXPANSION_ARTIFACTS.zip'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity check failed')
    metadata = {'file': target.name, 'files': len(files), 'bytes': target.stat().st_size,
                'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'crc_verified': True, 'run_status': 'stopped',
                'html_standalone': 'review_001/CONDITIONAL_EXPANSION_REVIEW.html',
                'notes': 'Only HTML is project-independent. Runtime source/dependencies and requests are archived; no claim of standalone server setup.'}
    (HERE / 'DELIVERY.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
