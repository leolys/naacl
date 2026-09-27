"""One explicit interface-v2 launch; serial, owned-child cleanup, no retries."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import time
import urllib.request

from .run_action_codec import continuation_source, NAME, ATTEMPT
from .retry_startup import check_identity
from .launch import gpu_state
from .settings import RUN_ROOT, CONFIGS, CONDA, REPO, PORT, EVAL_PYTHON, common_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorized-action-codec', action='store_true', required=True)
    parser.add_argument('--allow-shared-gpu', action='store_true', required=True)
    parser.parse_args()
    lock = (RUN_ROOT / 'wave.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    source = continuation_source()
    identity = check_identity(NAME, source)
    root, log_path = RUN_ROOT / ATTEMPT, RUN_ROOT / (ATTEMPT + '_service.log')
    if root.exists() or log_path.exists():
        raise RuntimeError('Authorized one-time interface continuation already attempted')
    preflight = gpu_state()
    config = CONFIGS[NAME]
    index = json.loads((Path(config['weights']) / 'model.safetensors.index.json').read_text())
    required = (index['metadata']['total_size'] + 1048575) // 1048576 + 10240
    if preflight['total_mib'] - preflight['used_mib'] < required:
        raise RuntimeError('Insufficient free GPU7 memory; no launch')
    env = common_env()
    command = [str(CONDA / 'envs' / config['env'] / 'bin/python'), '-u', '-m',
        'research.multi_model_simple_check.server', '--model', NAME, '--allowed-root', str(RUN_ROOT), '--port', str(PORT)]
    record = dict(model=NAME, attempt=ATTEMPT, source=str(source), explicit_user_authorization=True,
        shared_gpu_authorized=True, gpu_preflight=preflight, required_free_mib=required,
        identity_check=identity, started_at=time.time(), service_command=command)
    status_path = RUN_ROOT / (ATTEMPT + '_status.json')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with log_path.open('x') as log:
        process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
        record.update(owned_service_pid=process.pid, status='loading')
        status_path.write_text(json.dumps(record, indent=2))
        try:
            deadline = time.monotonic() + 900
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    with opener.open(f'http://127.0.0.1:{PORT}/health', timeout=2) as response:
                        health = json.load(response)
                    if health.get('model_name') == NAME:
                        break
                except Exception:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('Service not ready; no implicit retry')
            command = [str(EVAL_PYTHON), '-u', '-m', 'research.multi_model_simple_check.run_action_codec',
                '--authorized-action-codec']
            record.update(status='running_panel', panel_command=command)
            status_path.write_text(json.dumps(record, indent=2))
            with (RUN_ROOT / (ATTEMPT + '_panel.log')).open('x') as panel_log:
                result = subprocess.run(command, cwd=REPO, env=env, stdout=panel_log, stderr=subprocess.STDOUT)
            record.update(status='panel_process_finished', panel_exit_code=result.returncode)
            if (root / 'final_status.json').exists():
                record['panel_final_status'] = json.loads((root / 'final_status.json').read_text())
        except Exception as exc:
            record.update(status='interface_continuation_stopped', error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            record.update(service_exit_code=process.returncode, ended_at=time.time())
            status_path.write_text(json.dumps(record, indent=2))
            print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
