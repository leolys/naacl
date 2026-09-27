"""Read-only run snapshot to a new archive; omit model caches and labels."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def main():
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = HERE / ('CAPTURE_' + suffix + '.zip')
    roots = ['runs', 'workers', 'dispatch', 'resources', 'checks', 'cleanup']
    paths = [p for name in roots for p in (HERE / name).rglob('*') if p.is_file() and 'cache' not in p.parts
             and '__pycache__' not in p.parts and p.suffix not in ('.tmp', '.lock')]
    paths += [HERE / name for name in ('RUNTIME_SEAL.json', 'config.json', 'manifest.json', 'schedule.json', 'PROTOCOL.md')]
    hashes = {}
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            data = path.read_bytes()
            name = path.relative_to(HERE).as_posix()
            archive.writestr(name, data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        archive.writestr('CAPTURE_MANIFEST.json', json.dumps({'created': suffix, 'files': hashes,
            'live_snapshot_may_span_multiple_instants': True, 'no_model_calls': True}, indent=2))
    print(json.dumps({'path': str(output), 'files': len(hashes), 'bytes': output.stat().st_size,
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
