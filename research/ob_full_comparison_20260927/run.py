"""One worker owns 35 fixed tasks x six versions, serial on one model replica."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time
from engine import (HERE, VERSIONS, Client, Stop, WorkerLock, contexts, read, save_new,
                    owned_update, sha, stamp, verify_seal)


def load_prompts(version):
    spec = importlib.util.spec_from_file_location('prompts_' + version, HERE / ('prompts_' + version + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight(api, config):
    base = api.endpoint.rsplit('/v1/', 1)[0]
    health = api.http.get(base + '/health', timeout=15, allow_redirects=False)
    models = api.http.get(base + '/v1/models', timeout=15, allow_redirects=False)
    model_body = models.json()
    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu',
                                   '--format=csv,noheader,nounits'], text=True, timeout=25)
    row = config['workers'][api.worker]
    if health.status_code != 200 or models.status_code != 200 or config['model'] not in [x['id'] for x in model_body['data']]:
        raise Stop('replica not ready')
    if not any(line.startswith(str(row['gpu']) + ', ' + row['uuid'] + ',') for line in gpu.splitlines()):
        raise Stop('GPU UUID mismatch')
    save_new(api.work / ('preflight_%d.json' % time.time_ns()), {'at': stamp(), 'endpoint': api.endpoint,
        'models': model_body, 'health': health.status_code, 'gpu': gpu, 'python': sys.version})


def run(worker):
    config = read(HERE / 'config.json')
    seal = verify_seal()
    manifest = read(HERE / 'manifest.json')['units']
    rows = [r for r in read(HERE / 'schedule.json')['rows'] if r['worker'] == worker]
    if len(rows) != 210 or len({r['unit'] for r in rows}) != 35:
        raise Stop('schedule coverage differs')
    work = HERE / 'workers' / str(worker)
    identity = {'worker': worker, 'seal_sha256': seal, 'rows': rows}
    if (work / 'identity.json').exists():
        if read(work / 'identity.json') != identity:
            raise Stop('worker identity changed')
    else:
        save_new(work / 'identity.json', identity)
    api = Client(config, worker)
    summary_file = work / 'summary.json'
    summary = read(summary_file) if summary_file.exists() else {
        'worker': worker, 'status': 'prepared', 'started': stamp(), 'units': {}, 'expected_units': 210,
        'business_submissions': 0, 'paid_api_calls': 0}
    if summary['status'] == 'finished':
        print('already finished; no requests', flush=True)
        return
    prompts = {v: load_prompts(v) for v in VERSIONS}
    api.guard()
    preflight(api, config)
    summary.update(status='running', pid=os.getpid(), endpoint=api.endpoint)
    owned_update(summary_file, summary)
    try:
        api.call(work / 'control', 'Return exactly {"ready":true}. This is a non-chart service check.',
                 {'purpose': 'synthetic image plus structured-output service check'},
                 HERE / 'controls/blank.png', 'control', 'plain')
        for row in rows:
            key, version = row['unit'], row['version']
            unit = manifest[key]
            data, dest = HERE / 'data' / key, HERE / 'runs' / version / key
            result_file = dest / 'result.json'
            result_id = version + '/' + key
            if result_file.exists():
                result = read(result_file)
                if result.get('worker') != worker or result.get('version') != version or result.get('unit') != key:
                    raise Stop('result ownership differs')
                if result['status'] not in ('completed', 'interface_failed'):
                    raise Stop('unexpected terminal result')
                summary['units'][result_id] = result
                continue
            if sha(data / 'input.json') != unit['input_sha256'] or sha(data / unit['image']) != unit['image_sha256']:
                raise Stop('fixed data changed')
            api.guard()
            projected = read(data / 'input.json')
            # Byte identity plus field whitelist prevents accidental manifest/label projection.
            contexts(projected)
            result = {'unit': key, 'version': version, 'worker': worker, 'status': 'running', 'started': stamp()}
            notes = checks = None
            stage = 'decide' if version == 'plain' else 'read'
            try:
                if version != 'plain':
                    print('READ ' + result_id, flush=True)
                    notes = api.call(dest / 'read', prompts[version].READ, contexts(projected), data / unit['image'], 'read', version)
                    stage = 'verify'
                    print('VERIFY ' + result_id, flush=True)
                    checks = api.call(dest / 'verify', prompts[version].VERIFY, contexts(projected, notes), data / unit['image'], 'verify', version)
                stage = 'decide'
                print('DECIDE ' + result_id, flush=True)
                decision = api.call(dest / 'decide', prompts[version].DECIDE, contexts(projected, notes, checks), data / unit['image'], 'decide', version)
                result.update(status='completed', choice=decision, ended=stamp())
            except Stop:
                save_new(dest / ('stop_%d.json' % time.time_ns()), {**result, 'status': 'stopped', 'stage': stage, 'at': stamp()})
                raise
            except Exception as exc:
                result.update(status='interface_failed', failed_stage=stage, ended=stamp(),
                              error={'type': type(exc).__name__, 'message': str(exc)})
            save_new(result_file, result)
            summary['units'][result_id] = result
            summary.update(attempts=api.ledger['attempts'], updated=stamp())
            owned_update(summary_file, summary)
            print('DONE ' + result_id + ' status=' + result['status'] + ' attempts=' + str(api.ledger['attempts']), flush=True)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        summary.update(ended=stamp(), attempts=api.ledger['attempts'])
        try:
            summary['runtime_preserved'] = verify_seal() == seal
        except Exception as exc:
            summary['runtime_preserved'] = False
            summary['integrity_error'] = str(exc)
        owned_update(summary_file, summary)
        print(summary['status'] + ' units=' + str(len(summary['units'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, choices=range(4), required=True)
    args = parser.parse_args()
    with WorkerLock(HERE / 'workers' / str(args.worker)):
        run(args.worker)
