"""Launch this serial diagnostic client only, never a model service."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', choices=['plain', 'v4', 'v5', 'v6', 'v7'], required=True)
    parser.add_argument('--panel', choices=['dev', 'application'], required=True)
    args = parser.parse_args()
    import fcntl
    with (HERE / 'PROCESS.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Release this precheck before the worker acquires its lifetime lock. Two
    # simultaneous launchers are still serialized by the worker's LOCK_NB.
    folder = HERE / 'launches' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    folder.mkdir(parents=True, exist_ok=False)
    argv = [sys.executable, '-u', str(HERE / 'run.py'), '--version', args.version, '--panel', args.panel]
    with (folder / 'stdout.log').open('xb') as log:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            cwd=HERE, start_new_session=True, close_fds=True,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    result = {'pid': child.pid, 'command': argv, 'created': datetime.now(timezone.utc).isoformat(),
              'log': str(folder / 'stdout.log'), 'only_diagnostic_client': True,
              'pid_is_not_health_confirmation': True}
    (folder / 'launch.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
