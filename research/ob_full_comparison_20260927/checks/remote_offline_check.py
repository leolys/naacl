"""Linux checks without installing pytest or touching an existing environment."""
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import verify_seal, WorkerLock, contexts, read, sha, save_new, stamp
from dispatch import listener_owned_by
from prepare import schedule_for


def main():
    seal = verify_seal(ROOT)
    checks = ['all_sealed_source_and_input_hashes_match']
    manifest = read(ROOT / 'manifest.json')
    assert read(ROOT / 'schedule.json')['rows'] == schedule_for(list(manifest['units']))
    for key in manifest['units']:
        assert set(contexts(read(ROOT / 'data' / key / 'input.json'))) == {'goal', 'public_task', 'options'}
    checks += ['schedule_exact840', 'public_projection140']
    with tempfile.TemporaryDirectory(prefix='full140-lock-', dir=ROOT) as temp:
        lockdir = Path(temp) / 'worker0'
        code = "import sys; sys.path.insert(0,sys.argv[1]); from engine import WorkerLock;\ntry:\n with WorkerLock(sys.argv[2]): pass\nexcept BlockingIOError: sys.exit(23)"
        with WorkerLock(lockdir):
            same = subprocess.run([sys.executable, '-c', code, str(ROOT), str(lockdir)])
            other = subprocess.run([sys.executable, '-c', code, str(ROOT), str(Path(temp) / 'worker1')])
            assert same.returncode == 23 and other.returncode == 0
        released = subprocess.run([sys.executable, '-c', code, str(ROOT), str(lockdir)])
        assert released.returncode == 0
    checks += ['cross_process_same_worker_lock_rejected', 'different_worker_lock_allowed', 'released_lock_reusable']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        import os
        assert listener_owned_by(os.getpid(), port)['pid'] == os.getpid()
        try:
            listener_owned_by(1, port)
        except RuntimeError:
            pass
        else:
            raise AssertionError('wrong listener owner accepted')
    checks += ['real_listener_socket_owner_verified', 'wrong_socket_owner_rejected']
    save_new(ROOT / 'checks/REMOTE_OFFLINE_RESULT.json', {'at': stamp(), 'seal_sha256': seal,
        'checks': checks, 'model_requests': 0, 'package_installs': 0, 'python': sys.version})
    print('PASS:', ', '.join(checks))


if __name__ == '__main__':
    main()
