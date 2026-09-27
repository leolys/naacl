"""Explicit one-time zero-dispatch browser startup retry, never prefix resampling."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import time
import urllib.request

from .settings import CONFIGS, NAMES, PORT, CONDA, REPO, RUN_ROOT, EVAL_PYTHON, BROWSER, common_env
from .launch import gpu_state
from .run import startup_retry_source, digest


def check_identity(name, source):
    original = json.loads((source/'MODEL_CONFIG.json').read_text())
    for key,value in CONFIGS[name].items():
        if original.get(key) != value:
            raise RuntimeError('Model configuration changed: ' + key)
    if original['gpu'] != '7' or original['browser_sha256'] != digest(BROWSER):
        raise RuntimeError('GPU/browser identity changed')
    if json.loads((source/'TASK_MANIFEST.json').read_text()) != json.loads((RUN_ROOT/f'TASK_MANIFEST_{name}.json').read_text()):
        raise RuntimeError('Task manifest changed')
    checked = {}
    for folder in ('research/decision_evidence_audit','research/prospective_simple_check_pilot'):
        for previous in (source/'executed_sources'/folder).glob('*.py'):
            current = REPO/folder/previous.name
            if digest(current) != digest(previous):
                raise RuntimeError('Frozen actor/policy/harness source changed: ' + str(current))
            checked[str(current.relative_to(REPO))] = digest(current)
    for file in ('server.py','settings.py','env-spec.json'):
        current = REPO/'research/multi_model_simple_check'/file
        if digest(current) != digest(source/'executed_sources/research/multi_model_simple_check'/file):
            raise RuntimeError('Native model configuration/adapter changed: ' + file)
        checked[str(current.relative_to(REPO))] = digest(current)
    health = json.loads((source/'backend_metadata.json').read_text())['health']
    for file,sha in health['model_files'].items():
        if digest(Path(CONFIGS[name]['weights'])/file) != sha:
            raise RuntimeError('Weight configuration/index/code changed: ' + file)
    return dict(checked_source_hashes=checked, manifest_unchanged=True,
                model_config_and_index_unchanged=True, browser_sha256=original['browser_sha256'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', choices=NAMES, required=True)
    p.add_argument('--allow-shared-gpu', action='store_true', required=True)
    args = p.parse_args()
    name = args.model
    source = startup_retry_source(name)
    identity = check_identity(name, source)
    lock = (RUN_ROOT / 'wave.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    root = RUN_ROOT / (name + '_startup_retry01')
    log_path = RUN_ROOT / (name + '_startup_retry01_service.log')
    if root.exists() or log_path.exists():
        raise RuntimeError('One startup retry already attempted; refuse repeat')
    preflight = gpu_state()
    config = CONFIGS[name]
    index = json.loads((Path(config['weights']) / 'model.safetensors.index.json').read_text())
    required = (index['metadata']['total_size'] + 1048575) // 1048576 + 10240
    if preflight['total_mib'] - preflight['used_mib'] < required:
        raise RuntimeError('Insufficient free VRAM; no model launched')
    env = common_env()
    service_command = [str(CONDA/'envs'/config['env']/'bin/python'), '-u', '-m',
        'research.multi_model_simple_check.server','--model',name,'--allowed-root',str(RUN_ROOT),'--port',str(PORT)]
    record = dict(model=name, attempt='startup_retry01', source=str(source), gpu_preflight=preflight,
        identity_check=identity,
        shared_gpu_authorized=True, required_free_mib=required, started_at=time.time(),
        service_command=service_command, change='browser launch timeout 20s to 120s; no model/task/prompt change')
    status_path = RUN_ROOT / (name + '_startup_retry01_status.json')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with log_path.open('x') as log:
        process = subprocess.Popen(service_command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
        record.update(owned_service_pid=process.pid, status='loading')
        status_path.write_text(json.dumps(record, indent=2))
        try:
            deadline = time.monotonic() + 900
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    with opener.open(f'http://127.0.0.1:{PORT}/health', timeout=2) as response:
                        health = json.load(response)
                    if health.get('model_name') == name:
                        break
                except Exception:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('Service failed readiness; no more attempts')
            command = [str(EVAL_PYTHON),'-u','-m','research.multi_model_simple_check.run','--model',name,'--startup-retry']
            record.update(status='running_panel', panel_command=command)
            status_path.write_text(json.dumps(record, indent=2))
            with (RUN_ROOT / (name + '_startup_retry01_panel.log')).open('x') as panel_log:
                result = subprocess.run(command, cwd=REPO, env=env, stdout=panel_log, stderr=subprocess.STDOUT)
            record.update(status='panel_process_finished', panel_exit_code=result.returncode)
            if (root/'final_status.json').exists():
                record['panel_final_status'] = json.loads((root/'final_status.json').read_text())
        except Exception as exc:
            record.update(status='startup_retry_failed', error_type=type(exc).__name__, error=str(exc))
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
