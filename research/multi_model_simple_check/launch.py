"""One bounded sequential wave. Own subprocesses only; no recovery restarts."""
import argparse
import fcntl
import json
import os
import subprocess
import time
import urllib.request

from .settings import CONFIGS, NAMES, GPU, PORT, CONDA, REPO, RUN_ROOT, EVAL_PYTHON, common_env


def gpu_state():
    value = subprocess.check_output(['nvidia-smi','-i',GPU,
        '--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu','--format=csv,noheader,nounits'], text=True).strip()
    columns = [s.strip() for s in value.split(',')]
    return dict(index=columns[0], uuid=columns[1], used_mib=int(columns[2]),
                total_mib=int(columns[3]), utilization=int(columns[4]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--allow-shared-gpu', action='store_true')
    args = parser.parse_args()
    assert (RUN_ROOT / 'FROZEN_PLAN.json').is_file(), 'Prepare manifest first'
    env = common_env()
    lock = (RUN_ROOT / 'wave.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    session = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results = []
    for name in NAMES:
        config = CONFIGS[name]
        prefix = RUN_ROOT / (name + '_service')
        record = dict(model=name, gpu_preflight=gpu_state(), started_at=time.time(),
                      shared_gpu_authorized=args.allow_shared_gpu)
        if record['gpu_preflight']['used_mib'] >= 500 and not args.allow_shared_gpu:
            record['status'] = 'blocked_gpu_not_idle'
            results.append(record)
            (RUN_ROOT / 'wave_status.json').write_text(json.dumps(results, indent=2))
            print(json.dumps(record), flush=True)
            break
        index = json.loads((__import__('pathlib').Path(config['weights']) / 'model.safetensors.index.json').read_text())
        required = (index['metadata']['total_size'] + 1048575) // 1048576 + 10240
        record['required_free_mib_weights_plus_10gib'] = required
        if record['gpu_preflight']['total_mib'] - record['gpu_preflight']['used_mib'] < required:
            record['status'] = 'blocked_insufficient_free_vram'
            results.append(record)
            (RUN_ROOT / 'wave_status.json').write_text(json.dumps(results, indent=2))
            print(json.dumps(record), flush=True)
            continue
        if (RUN_ROOT / name).exists() or prefix.with_suffix('.log').exists():
            raise RuntimeError('Refuse to overwrite/restart a previous model attempt')
        python = str(CONDA / 'envs' / config['env'] / 'bin/python')
        command = [python, '-u', '-m', 'research.multi_model_simple_check.server',
                   '--model', name, '--allowed-root', str(RUN_ROOT), '--port', str(PORT)]
        record['service_command'] = command
        with prefix.with_suffix('.log').open('x') as log:
            process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
            record['owned_service_pid'] = process.pid
            prefix.with_suffix('.pid').write_text(str(process.pid))
            print('LOADING ' + name + ' own_pid=' + str(process.pid), flush=True)
            try:
                deadline = time.monotonic() + 900
                while process.poll() is None and time.monotonic() < deadline:
                    try:
                        with session.open(f'http://127.0.0.1:{PORT}/health', timeout=2) as response:
                            health = json.load(response)
                        if health.get('model_name') == name:
                            break
                    except Exception:
                        pass
                    time.sleep(2)
                else:
                    raise RuntimeError('Service exited or did not become ready in 900 seconds')
                record['status'] = 'running_panel'
                results.append(record)
                (RUN_ROOT / 'wave_status.json').write_text(json.dumps(results, indent=2))
                command = [str(EVAL_PYTHON), '-u', '-m', 'research.multi_model_simple_check.run', '--model', name]
                record['panel_command'] = command
                with (RUN_ROOT / (name + '_panel.log')).open('x') as panel_log:
                    status = subprocess.run(command, cwd=REPO, env=env, stdout=panel_log, stderr=subprocess.STDOUT)
                record.update(status='panel_process_finished', panel_exit_code=status.returncode)
            except Exception as exc:
                record.update(status='service_or_launch_failure', error_type=type(exc).__name__, error=str(exc))
                if record not in results:
                    results.append(record)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                record.update(service_exit_code=process.returncode, ended_at=time.time())
                (RUN_ROOT / 'wave_status.json').write_text(json.dumps(results, indent=2))
                print('FINISHED ' + json.dumps(record), flush=True)
                time.sleep(3)
    print('BOUNDED_WAVE_STOPPED', flush=True)


if __name__ == '__main__':
    main()
