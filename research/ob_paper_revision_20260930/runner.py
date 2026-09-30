"""Standalone baseline/seed runner for the paper-revision experiments.

Reuses the frozen ob_full_comparison protocol: same prompts, schemas, sampling
parameters, candidate pool (records inside each task input.json), and scoring
against offline/labels.json. New output directory; no modification of the
sealed ob_full_comparison_20260927 artifacts.
"""
import argparse
import base64
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OB = HERE.parent / 'ob_full_comparison_20260927'
sys.path.insert(0, str(OB))

import schema_new

CLEAN_ASSETS = HERE.parent.parent / 'web_agent_benchmark' / 'clean_benchmark_v1' / 'assets'


def load_prompts(version):
    spec = importlib.util.spec_from_file_location('prompts_' + version, OB / ('prompts_' + version + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_manifest():
    manifest = json.loads((OB / 'manifest.json').read_text())['units']
    units = {}
    for key, unit in manifest.items():
        units[key] = {
            'input': json.loads((OB / 'data' / key / 'input.json').read_text()),
            'image': OB / 'data' / key / unit['image'],
            'clean_image': CLEAN_ASSETS / key.split('_', 1)[1] / 'clean.png',
        }
    return units


def label_set(labels):
    return {x['label']: x for x in labels['options']}


class Endpoint:
    def __init__(self, url, model, sampling, lock):
        self.url, self.model, self.sampling = url, model, sampling
        self.http = requests.Session()
        self.http.trust_env = False
        self.lock = lock

    def call(self, system, context, image_path, schema, max_tokens, seed, with_image=True):
        message_user = [{'type': 'text', 'text': json.dumps(context, ensure_ascii=False, indent=2)}]
        if with_image:
            image_bytes = Path(image_path).read_bytes()
            mime = 'image/jpeg' if image_bytes[:2] == b'\xff\xd8' else 'image/png'
            message_user.append({'type': 'image_url', 'image_url': {
                'url': 'data:' + mime + ';base64,' + base64.b64encode(image_bytes).decode('ascii')}})
        payload = {'model': self.model, 'temperature': self.sampling['temperature'],
                   'top_p': self.sampling['top_p'], 'top_k': self.sampling['top_k'], 'seed': seed,
                   'max_tokens': max_tokens,
                   'chat_template_kwargs': {'enable_thinking': self.sampling['enable_thinking']},
                   'structured_outputs': {'json': schema},
                   'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': message_user}]}
        last = None
        for attempt in range(2):
            start = time.monotonic()
            try:
                response = self.http.post(self.url, json=payload, timeout=600, allow_redirects=False)
            except requests.RequestException as exc:
                last = {'type': type(exc).__name__, 'message': str(exc)}
                time.sleep(2)
                continue
            if response.status_code == 200:
                body = response.json()
                choice = body['choices'][0]
                if choice.get('finish_reason') != 'stop':
                    last = {'type': 'finish_reason', 'message': choice.get('finish_reason')}
                    time.sleep(1)
                    continue
                value = json.loads(choice['message']['content'])
                return {'status': 'ok', 'value': value,
                        'usage': body.get('usage', {}), 'elapsed': time.monotonic() - start}
            last = {'type': 'http_' + str(response.status_code), 'message': response.text[:300]}
            time.sleep(3)
        return {'status': 'failed', 'error': last, 'elapsed': time.monotonic() - start}


def contexts(unit, notes=None, checks=None):
    projected = unit['input']
    value = {k: projected[k] for k in ('goal', 'public_task', 'options')}
    if notes is not None:
        value['records'] = projected['records']
        value['independent_visual_notes'] = notes
    if checks is not None:
        value['ob_checks'] = checks['reviews']
    return value


def run_plain(api, unit, seed, image, prompts):
    schema = schema_new.output_schema('decide', contexts(unit))
    out = api.call(prompts.DECIDE, contexts(unit), image, schema,
                   api.sampling['max_output_tokens']['decide'], seed)
    return {'stage': 'decide', 'out': out}


def run_v5(api, unit, seed, image, prompts):
    notes = api.call(prompts.READ, contexts(unit), image, schema_new.output_schema('read', contexts(unit)),
                     api.sampling['max_output_tokens']['read'], seed)
    if notes['status'] != 'ok':
        return {'stage': 'read', 'out': notes}
    checks = api.call(prompts.VERIFY, contexts(unit, notes['value']), image,
                      schema_new.output_schema('verify', contexts(unit, notes['value'])),
                      api.sampling['max_output_tokens']['verify'], seed)
    if checks['status'] != 'ok':
        return {'stage': 'verify', 'out': checks}
    decision = api.call(prompts.DECIDE, contexts(unit, notes['value'], checks['value']), image,
                        schema_new.output_schema('decide', contexts(unit, notes['value'], checks['value'])),
                        api.sampling['max_output_tokens']['decide'], seed)
    return {'stage': 'decide', 'out': decision}


def run_tab(api, unit, seed, image, prompts):
    table_schema = {'type': 'object',
                    'properties': {'rows': {'type': 'array',
                                            'items': {'type': 'array',
                                                      'items': {'type': 'string', 'maxLength': 20},
                                                      'maxItems': 3, 'minItems': 3},
                                            'maxItems': 24},
                                   'note': {'type': 'string', 'maxLength': 220}},
                    'required': ['rows', 'note'], 'additionalProperties': False}
    transcription = api.call(prompts.TRANSCRIBE, contexts(unit), image, table_schema,
                             api.sampling['max_output_tokens']['transcribe'], seed)
    if transcription['status'] != 'ok':
        return {'stage': 'transcribe', 'out': transcription}
    context = contexts(unit)
    context['chart_table'] = json.dumps(transcription['value'], ensure_ascii=False)
    schema = schema_new.output_schema('decide', contexts(unit))
    decision = api.call(prompts.DECIDE_TABLE, context, image, schema,
                        api.sampling['max_output_tokens']['decide'], seed, with_image=False)
    return {'stage': 'decide', 'out': decision, 'table': json.dumps(transcription['value'], ensure_ascii=False)}


ARMS = {
    'plain': ('plain', run_plain, True),
    'v5': ('v5', run_v5, True),
    'tab': ('tab', run_tab, True),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', default='http://127.0.0.1:8058/v1/chat/completions')
    parser.add_argument('--model', default='Qwen3.8-27B')
    parser.add_argument('--out', default=str(HERE / 'results'))
    parser.add_argument('--seeds', default='12345,22345,32345')
    parser.add_argument('--arms', default='plain,v5,tab,clean')
    parser.add_argument('--concurrency', type=int, default=4)
    args = parser.parse_args()

    config = json.loads((OB / 'config.json').read_text())
    sampling = {'temperature': config['temperature'], 'top_p': config['top_p'], 'top_k': config['top_k'],
                'enable_thinking': config['enable_thinking'],
                'max_output_tokens': dict(config['max_output_tokens'], transcribe=2400)}
    seeds = [int(s) for s in args.seeds.split(',')]
    arms = args.arms.split(',')

    prompts = {name: load_prompts(name) for name in ('plain', 'v5')}
    spec = importlib.util.spec_from_file_location('prompts_tab', HERE / 'prompts_tab.py')
    prompts['tab'] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prompts['tab'])

    units = load_manifest()
    labels = json.loads((OB / 'offline' / 'labels.json').read_text())['tasks']

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    api = Endpoint(args.endpoint, args.model, sampling, lock)

    jobs = []
    for arm in arms:
        if arm == 'clean':
            for key, unit in units.items():
                jobs.append({'id': f'clean/clean/{key}', 'unit': unit, 'seed': seeds[0],
                             'runner': run_plain, 'image': unit['clean_image'],
                             'prompts': prompts['plain'], 'arm': 'clean', 'variant': 'clean'})
            continue
        base_arm, base_runner, _ = ARMS[arm]
        if arm == 'tab':
            for key, unit in units.items():
                jobs.append({'id': f'tab/tab/{key}', 'unit': unit, 'seed': seeds[0],
                             'runner': run_tab, 'image': unit['image'],
                             'prompts': prompts['tab'], 'arm': 'tab', 'variant': 'tab'})
            continue
        for seed in seeds:
            for key, unit in units.items():
                jobs.append({'id': f'{arm}/seed{seed}/{key}', 'unit': unit, 'seed': seed,
                             'runner': base_runner, 'image': unit['image'],
                             'prompts': prompts[base_arm], 'arm': arm, 'variant': f'seed{seed}'})

    progress = {'done': 0, 'total': len(jobs), 'started': time.strftime('%Y-%m-%dT%H:%M:%S')}
    progress_lock = threading.Lock()

    def execute(job):
        key = job['id'].rsplit('/', 1)[1]
        dest = out_root / 'runs' / job['id'].rsplit('/', 1)[0]
        dest.mkdir(parents=True, exist_ok=True)
        result_file = dest / (key + '.result.json')
        if result_file.exists():
            with progress_lock:
                progress['done'] += 1
            return
        started = time.monotonic()
        try:
            outcome = job['runner'](api, job['unit'], job['seed'], job['image'], job['prompts'])
        except Exception as exc:
            outcome = {'stage': 'exception', 'out': {'status': 'failed', 'error': {'type': type(exc).__name__, 'message': str(exc)}}}
        record = {'arm': job['arm'], 'variant': job['variant'], 'unit': key, 'seed': job['seed'],
                  'stage': outcome['stage'], 'elapsed_s': time.monotonic() - started,
                  'out': outcome['out']}
        if 'table' in outcome:
            (dest / (key + '.table.txt')).write_text(outcome['table'], encoding='utf-8')
        tmp = result_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(result_file)
        with progress_lock:
            progress['done'] += 1
            if progress['done'] % 25 == 0 or progress['done'] == progress['total']:
                (out_root / 'progress.json').write_text(json.dumps(progress), encoding='utf-8')

    threads = []
    sem = threading.Semaphore(args.concurrency)
    def guarded(job):
        sem.acquire()
        try:
            execute(job)
        finally:
            sem.release()
    for job in jobs:
        unit_key = job['id'].rsplit('/', 1)[1]
        job['unit_key'] = unit_key
        t = threading.Thread(target=guarded, args=(job,))
        threads.append(t)
        t.start()
        if len(threads) >= 600:
            threads[0].join()
            threads = threads[1:]
    for t in threads:
        t.join()
    (out_root / 'progress.json').write_text(json.dumps(progress), encoding='utf-8')
    print('RUNNER_DONE', json.dumps(progress))


if __name__ == '__main__':
    main()
