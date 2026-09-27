"""Launch only this diagnostic, detached from SSH; preserve every launch log."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--panel', choices=['dev', 'confirm', 'full'], required=True)
    p.add_argument('--version', choices=['v1', 'v2', 'v3'], required=True)
    args = p.parse_args()
    import fcntl
    with (HERE / 'PROCESS.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Child run.py takes the same lock once launcher releases it.
        folder = HERE / 'launches' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        folder.mkdir(parents=True, exist_ok=False)
        argv = [sys.executable, '-u', str(HERE / 'run.py'), '--panel', args.panel, '--version', args.version]
        with (folder / 'stdout.log').open('xb') as log:
            child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     cwd=HERE, start_new_session=True, close_fds=True,
                                     env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        result = {'pid': child.pid, 'command': argv, 'log': str(folder / 'stdout.log'),
                  'created': datetime.now(timezone.utc).isoformat(), 'only_diagnostic_process': True}
        (folder / 'launch.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
