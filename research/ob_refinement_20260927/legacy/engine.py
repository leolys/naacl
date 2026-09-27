"""Serial resumable local-model diagnostic with a shared global budget/lock."""
import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import requests

from schema import SCHEMAS, validate

HERE = Path(__file__).resolve().parent

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def dump(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, p)

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def stamp():
    return datetime.now(timezone.utc).isoformat()

class Stop(RuntimeError):
    pass

class GlobalLock:
    def __enter__(self):
        import fcntl
        self.handle = (HERE / 'PROCESS.lock').open('a+')
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self

    def __exit__(self, *args):
        self.handle.close()

class Client:
    def __init__(self, config, root=HERE):
        self.config, self.root = config, Path(root)
        if config['endpoint'] != 'http://127.0.0.1:8058/v1/chat/completions' or config['model'] != 'Qwen3.8-27B':
            raise ValueError('Only existing authorized local service')
        self.http = requests.Session()
        self.http.trust_env = False
        self.ledger_file = self.root / 'ledger.json'
        self.ledger = read(self.ledger_file) if self.ledger_file.exists() else {'events': [], 'attempts': 0}

    def guard(self):
        if self.ledger.get('blocked'):
            raise Stop(self.ledger['blocked'])
        if datetime.now(timezone.utc) >= datetime.fromisoformat(self.config['deadline_utc']):
            raise Stop('deadline_no_new_requests')
        if self.ledger['attempts'] >= self.config['max_attempts']:
            raise Stop('global_attempt_cap')
        if (self.root / 'STOP_AFTER_CURRENT').exists():
            raise Stop('operator_stop_after_current')

    def call(self, folder, system, context, image, stage):
        folder = Path(folder)
        mime = 'image/jpeg' if Path(image).read_bytes()[:2] == b'\xff\xd8' else 'image/png'
        payload = {'model': self.config['model'], 'temperature': self.config['temperature'],
                   'top_p': self.config['top_p'], 'top_k': self.config['top_k'], 'seed': self.config['seed'],
                   'max_tokens': self.config['max_output_tokens'][stage],
                   'chat_template_kwargs': {'enable_thinking': self.config['enable_thinking']},
                   'structured_outputs': {'json': SCHEMAS[stage]},
                   'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': [
                       {'type': 'text', 'text': json.dumps(context, ensure_ascii=False, indent=2)},
                       {'type': 'image_url', 'image_url': {'url': 'data:' + mime + ';base64,' +
                            base64.b64encode(Path(image).read_bytes()).decode('ascii')}}]}]}
        if folder.exists():
            if read(folder / 'request.json') != payload:
                raise Stop('resume_payload_mismatch')
            if (folder / 'accepted.json').exists():
                return validate(stage, read(folder / 'accepted.json'), context)
            if (folder / 'failure.json').exists():
                raise ValueError('Previously failed stage retained; no quality retry')
            # Safe crash recovery: consume an archived 200 response, never send again.
            responses = sorted(folder.glob('response_*.json'))
            if responses:
                last = read(responses[-1])
                if last.get('http_status') == 200:
                    prior = [e for e in self.ledger['events'] if e['folder'] == str(folder.relative_to(self.root))]
                    # Recovery is a sidecar, not a rewrite of an old pending event.
                    dump(folder / 'recovery_metadata.json', {'reused_archived_response': responses[-1].name,
                        'new_request': False, 'ledger_event_numbers': [e['number'] for e in prior],
                        'response_usage': last['body'].get('usage') if isinstance(last['body'], dict) else None,
                        'note': 'Audit response usage separately if original event lacked usage.'})
                    return self.accept(folder, last['body'], stage, context)
            raise Stop('incomplete_unknown_stage_no_automatic_replay')
        self.guard()
        folder.mkdir(parents=True, exist_ok=False)
        dump(folder / 'request.json', payload)
        dump(folder / 'context.json', context)
        dump(folder / 'image_identity.json', {'sha256': sha(image), 'bytes': Path(image).stat().st_size})
        for attempt in range(1, self.config['transient_http_attempts'] + 1):
            self.guard()
            self.ledger['attempts'] += 1
            event = {'number': self.ledger['attempts'], 'folder': str(folder.relative_to(self.root)),
                     'stage': stage, 'attempt': attempt, 'start': stamp(), 'state': 'sent_outcome_pending'}
            self.ledger['events'].append(event)
            dump(self.ledger_file, self.ledger)
            start = time.monotonic()
            try:
                response = self.http.post(self.config['endpoint'], json=payload,
                    timeout=self.config['http_timeout_seconds'], allow_redirects=False)
            except requests.RequestException as exc:
                event.update(state='unknown_transport', error=type(exc).__name__, elapsed=time.monotonic()-start)
                self.ledger['blocked'] = 'unknown_transport_no_retry'
                dump(self.ledger_file, self.ledger)
                raise Stop(self.ledger['blocked']) from exc
            try:
                body = response.json()
            except ValueError:
                body = {'raw_body': response.text}
            # Preserve even non-object JSON before accessing optional metadata.
            dump(folder / ('response_%02d.json' % attempt), {'http_status': response.status_code, 'body': body})
            event.update(http_status=response.status_code, elapsed=time.monotonic()-start,
                         state='response_saved', usage=body.get('usage') if isinstance(body, dict) else None,
                         model=body.get('model') if isinstance(body, dict) else None)
            dump(self.ledger_file, self.ledger)
            if response.status_code in (408, 429, 500, 502, 503, 504) and attempt < self.config['transient_http_attempts']:
                time.sleep(2)
                continue
            if response.status_code != 200:
                self.ledger['blocked'] = 'http_%s' % response.status_code
                dump(self.ledger_file, self.ledger)
                raise Stop(self.ledger['blocked'])
            return self.accept(folder, body, stage, context)

    def accept(self, folder, body, stage, context):
        try:
            if not isinstance(body, dict):
                raise ValueError('Non-object service response')
            if body.get('model') != self.config['model']:
                raise ValueError('Unexpected response model')
            value = json.loads(body['choices'][0]['message']['content'])
            value = validate(stage, value, context)
        except Exception as exc:
            dump(folder / 'failure.json', {'type': type(exc).__name__, 'error': str(exc), 'no_quality_retry': True})
            raise
        dump(folder / 'accepted.json', value)
        return value

def public_context(projected):
    return copy.deepcopy({k: projected[k] for k in ('goal', 'public_task', 'options')})

def contexts(projected, reading=None, checks=None):
    if reading is None:
        return public_context(projected)
    result = {**copy.deepcopy(projected), 'independent_visual_notes': copy.deepcopy(reading)}
    if checks is not None:
        result['ob_checks'] = copy.deepcopy(checks['reviews'])
    return result

def preflight(api, output):
    health = api.http.get('http://127.0.0.1:8058/health', timeout=10, allow_redirects=False)
    models = api.http.get('http://127.0.0.1:8058/v1/models', timeout=10, allow_redirects=False).json()
    probe = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu', '--format=csv,noheader'],
                           capture_output=True, text=True, timeout=20)
    process = subprocess.run(['ps', '-p', '316818,319282,282313', '-o', 'pid,lstart,args'], capture_output=True, text=True, timeout=20)
    dump(output / ('preflight_%d.json' % time.time_ns()), {'time': stamp(), 'health': health.status_code,
         'models': models, 'gpu': probe.stdout, 'processes': process.stdout})
    if health.status_code != 200 or api.config['model'] not in [m['id'] for m in models['data']]:
        raise Stop('existing_service_unavailable')
    if 'GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7' not in probe.stdout:
        raise Stop('GPU_identity_changed')

def source_hashes(version):
    return {n: sha(HERE / n) for n in ('run.py', 'schema.py', 'config.json', 'manifest.json', 'prompts_' + version + '.py')}

def run(panel, version):
    config = read(HERE / 'config.json')
    if config['max_attempts'] > 560 or config['concurrency'] != 1 or config['paid_api_allowed']:
        raise Stop('authorization_bounds_changed')
    if version not in ('v1', 'v2', 'v3'):
        raise Stop('maximum_three_dev_versions')
    if panel != 'dev':
        frozen = read(HERE / 'FREEZE.json')
        if frozen['version'] != version or frozen['prompt_sha256'] != sha(HERE / ('prompts_' + version + '.py')):
            raise Stop('not_frozen_version')
        if frozen['runtime_hashes'] != source_hashes(version):
            raise Stop('frozen_runtime_changed')
    spec = importlib.util.spec_from_file_location('selected_prompts', HERE / ('prompts_' + version + '.py'))
    prompts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prompts)
    manifest = read(HERE / 'manifest.json')
    units = {k: u for k, u in manifest['units'].items() if
             (panel == 'dev' and u['panel'] == 'dev') or
             (panel == 'confirm' and u['panel'] == 'full' and u['confirm']) or
             (panel == 'full' and u['panel'] == 'full')}
    output = HERE / 'runs' / (version + '_' + panel)
    hashes = source_hashes(version)
    if output.exists():
        if read(output / 'source_hashes.json') != hashes:
            raise Stop('runtime_source_changed_during_run')
    else:
        output.mkdir(parents=True)
        dump(output / 'source_hashes.json', hashes)
        for n in hashes:
            (output / 'runtime_source').mkdir(exist_ok=True)
            shutil.copyfile(HERE / n, output / 'runtime_source' / n)
    api = Client(config)
    summary = {'panel': panel, 'version': version, 'status': 'running', 'units': {},
               'business_submissions': 0, 'paid_api_calls': 0, 'started': stamp()}
    if (output / 'summary.json').exists():
        summary = read(output / 'summary.json')
        summary['status'] = 'running'
    dump(output / 'summary.json', summary)
    preflight(api, output)
    dump(HERE / 'ACTIVE.json', {'pid': os.getpid(), 'run': str(output.relative_to(HERE)), 'started': stamp()})
    try:
        for key, unit in units.items():
            api.guard()
            data = HERE / 'data' / key
            if sha(data / 'input.json') != unit['input_sha256'] or sha(data / unit['image']) != unit['image_sha256']:
                raise Stop('frozen_input_changed')
            dest = output / key
            result = read(dest / 'result.json') if (dest / 'result.json').exists() else {'unit': key, 'status': 'prepared'}
            if result['status'] in ('completed', 'interface_failed'):
                summary['units'][key] = result
                continue
            if panel == 'full':
                reuse = HERE / 'runs' / (version + '_confirm') / key
                if (reuse / 'result.json').exists():
                    prior = read(reuse / 'result.json')
                    if prior['status'] in ('completed', 'interface_failed'):
                        if read(reuse.parent / 'source_hashes.json') != hashes:
                            raise Stop('confirmation_runtime_not_identical')
                        result = {**prior, 'reused_from': str(reuse.relative_to(HERE)), 'new_calls': 0}
                        dump(dest / 'result.json', result)
                        summary['units'][key] = result
                        dump(output / 'summary.json', summary)
                        continue
            projected = read(data / 'input.json')
            image = data / unit['image']
            stage = 'supply' if not projected['records'] else 'read'
            try:
                if not projected['records']:
                    print('SUPPLY ' + key, flush=True)
                    supplied = api.call(dest / 'supply', prompts.SUPPLY, public_context(projected), image, 'supply')
                    projected['records'] = supplied['records']
                    result['new_candidate_source'] = 'Qwen_missing_old_input_one_call'
                dump(dest / 'projected.json', projected)
                stage = 'read'
                print(version + '/' + panel + ' READ ' + key, flush=True)
                reading = api.call(dest / stage, prompts.READ, contexts(projected), image, stage)
                stage = 'verify'
                print('VERIFY ' + key, flush=True)
                checks = api.call(dest / stage, prompts.VERIFY, contexts(projected, reading), image, stage)
                stage = 'decide'
                print('DECIDE ' + key, flush=True)
                choice = api.call(dest / stage, prompts.DECIDE, contexts(projected, reading, checks), image, stage)
                result.update(status='completed', choice=choice, record_count=len(projected['records']))
                print(json.dumps({'unit': key, 'choice': choice['option_label'], 'attempts': api.ledger['attempts']}), flush=True)
            except Stop:
                result.update(status='stopped', stopped_stage=stage)
                raise
            except Exception as exc:
                result.update(status='interface_failed', failed_stage=stage, error={'type': type(exc).__name__, 'message': str(exc)})
            finally:
                dump(dest / 'result.json', result)
                summary['units'][key] = result
                summary['global_attempts'] = api.ledger['attempts']
                dump(output / 'summary.json', summary)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        summary.update(ended=stamp(), global_attempts=api.ledger['attempts'],
                       runtime_preserved=source_hashes(version) == hashes,
                       completed=sum(x['status'] == 'completed' for x in summary['units'].values()))
        dump(output / 'summary.json', summary)
        dump(HERE / 'ACTIVE.json', {'pid': os.getpid(), 'run': str(output.relative_to(HERE)), 'state': 'ended', 'ended': stamp()})
        print(json.dumps({k: v for k, v in summary.items() if k != 'units'}), flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--panel', choices=['dev', 'confirm', 'full'], required=True)
    p.add_argument('--version', choices=['v1', 'v2', 'v3'], required=True)
    args = p.parse_args()
    with GlobalLock():
        run(args.panel, args.version)
