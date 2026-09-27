"""Parallel by disjoint worker, serial per endpoint. Immutable raw artifacts."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import requests
import schema_new
import schema_v3

HERE = Path(__file__).resolve().parent
VERSIONS = ['plain', 'v3', 'v4', 'v5', 'v6', 'v7']
PORTS = [8059, 8060, 8061, 8058]
CONTROL_SCHEMA = {'type': 'object', 'properties': {'ready': {'type': 'boolean', 'enum': [True]}},
                  'required': ['ready'], 'additionalProperties': False}


class Stop(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def owned_update(path, value):
    """Only worker-local summary/ledger, under its whole-process lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


class WorkerLock:
    def __init__(self, root):
        self.root = Path(root)

    def __enter__(self):
        import fcntl
        self.root.mkdir(parents=True, exist_ok=True)
        self.handle = (self.root / 'PROCESS.lock').open('a+')
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self

    def __exit__(self, *args):
        self.handle.close()


def unique_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError('duplicate JSON object key')
        value[key] = child
    return value


def contexts(projected, notes=None, checks=None):
    if set(projected) != {'goal', 'public_task', 'options', 'records'}:
        raise Stop('unexpected input projection')
    value = copy.deepcopy({k: projected[k] for k in ('goal', 'public_task', 'options')})
    if notes is not None:
        value['records'] = copy.deepcopy(projected['records'])
        value['independent_visual_notes'] = copy.deepcopy(notes)
    if checks is not None:
        if notes is None:
            raise Stop('checks without actual notes')
        value['ob_checks'] = copy.deepcopy(checks['reviews'])
    return value


def output_schema(version, stage, context):
    if stage == 'control':
        return copy.deepcopy(CONTROL_SCHEMA)
    return copy.deepcopy(schema_v3.SCHEMAS[stage]) if version == 'v3' else schema_new.output_schema(stage, context)


def validate(version, stage, value, context):
    if stage == 'control':
        if not isinstance(value, dict) or set(value) != {'ready'} or value['ready'] is not True:
            raise ValueError('non-chart control mismatch')
        return value
    return (schema_v3 if version == 'v3' else schema_new).validate(stage, value, context)


def check_config(config):
    if config['versions'] != VERSIONS or [x['port'] for x in config['workers']] != PORTS:
        raise Stop('fixed versions or endpoints changed')
    if config['paid_api_allowed'] or config['concurrency_per_worker'] != 1:
        raise Stop('resource bounds changed')
    if not 1 <= config['max_attempts_per_worker'] <= 650 or config['max_total_attempts'] != 2600:
        raise Stop('attempt bounds changed')
    expected = {'model': 'Qwen3.8-27B', 'temperature': .7, 'top_p': .8, 'top_k': 20,
                'seed': 12345, 'enable_thinking': False, 'transient_http_attempts': 2,
                'deadline_utc': '2026-09-27T15:00:00+00:00'}
    if any(config[k] != v for k, v in expected.items()):
        raise Stop('fixed decoding/deadline changed')


def verify_seal(root=HERE):
    seal = read(root / 'RUNTIME_SEAL.json')
    for name, expected in seal['files'].items():
        if sha(root / name) != expected:
            raise Stop('source/input changed: ' + name)
    return sha(root / 'RUNTIME_SEAL.json')


class Client:
    def __init__(self, config, worker, root=HERE):
        check_config(config)
        if worker not in range(4):
            raise Stop('unregistered worker')
        self.config, self.worker, self.root = config, worker, Path(root)
        self.work = self.root / 'workers' / str(worker)
        self.endpoint = 'http://127.0.0.1:%d/v1/chat/completions' % PORTS[worker]
        self.http = requests.Session()
        self.http.trust_env = False
        self.ledger_file = self.work / 'ledger.json'
        self.ledger = read(self.ledger_file) if self.ledger_file.exists() else {
            'worker': worker, 'endpoint': self.endpoint, 'attempts': 0, 'events': []}
        if self.ledger['worker'] != worker or self.ledger['endpoint'] != self.endpoint:
            raise Stop('ledger ownership differs')
        self.reconcile_archived_responses()

    def reconcile_archived_responses(self):
        """Settle crash-window events from immutable responses; never replay a request."""
        for event in self.ledger['events']:
            if event['state'] != 'sent_outcome_pending':
                continue
            folder = self.root / event['folder']
            response_file = folder / ('response_%02d.json' % event['attempt'])
            if not response_file.exists():
                self.ledger['blocked'] = 'pending_without_archived_response_no_replay'
                owned_update(self.ledger_file, self.ledger)
                continue
            archived = read(response_file)
            body = archived['body']
            recovery = {'at': stamp(), 'number': event['number'], 'original_event': copy.deepcopy(event),
                        'response_sha256': sha(response_file), 'new_request': False}
            save_new(self.work / ('recovery_%d.json' % time.time_ns()), recovery)
            event.update(state='response_recovered', http_status=archived['http_status'],
                usage=body.get('usage') if isinstance(body, dict) else None,
                model=body.get('model') if isinstance(body, dict) else None,
                recovered_at=recovery['at'], elapsed_unknown_after_crash=True)
            owned_update(self.ledger_file, self.ledger)

    def guard(self):
        if self.ledger.get('blocked'):
            raise Stop(self.ledger['blocked'])
        if datetime.now(timezone.utc) >= datetime.fromisoformat(self.config['deadline_utc']):
            raise Stop('deadline_no_new_requests')
        if self.ledger['attempts'] >= self.config['max_attempts_per_worker']:
            raise Stop('worker_attempt_cap')
        if (self.root / 'STOP_AFTER_CURRENT').exists() or (self.work / 'STOP_AFTER_CURRENT').exists():
            raise Stop('operator_stop_after_current')

    def call(self, folder, system, context, image, stage, version):
        folder = Path(folder)
        image_bytes = Path(image).read_bytes()
        mime = 'image/jpeg' if image_bytes[:2] == b'\xff\xd8' else 'image/png'
        payload = {'model': self.config['model'], 'temperature': self.config['temperature'],
            'top_p': self.config['top_p'], 'top_k': self.config['top_k'], 'seed': self.config['seed'],
            'max_tokens': self.config['max_output_tokens'][stage],
            'chat_template_kwargs': {'enable_thinking': self.config['enable_thinking']},
            'structured_outputs': {'json': output_schema(version, stage, context)},
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': [
                {'type': 'text', 'text': json.dumps(context, ensure_ascii=False, indent=2)},
                {'type': 'image_url', 'image_url': {'url': 'data:' + mime + ';base64,' +
                    base64.b64encode(image_bytes).decode('ascii')}}]}]}
        if folder.exists():
            if not (folder / 'request.json').exists() or read(folder / 'request.json') != payload:
                raise Stop('resume_payload_mismatch_or_unknown')
            owner = read(folder / 'owner.json')
            if owner != {'worker': self.worker, 'version': version, 'stage': stage, 'endpoint': self.endpoint}:
                raise Stop('stage ownership mismatch')
            if (folder / 'accepted.json').exists():
                return validate(version, stage, read(folder / 'accepted.json'), context)
            if (folder / 'failure.json').exists():
                raise ValueError('Previously failed stage retained; no quality retry')
            responses = sorted(folder.glob('response_*.json'))
            if responses and read(responses[-1]).get('http_status') == 200:
                save_new(folder / ('recovery_%d.json' % time.time_ns()), {
                    'at': stamp(), 'response': responses[-1].name, 'new_request': False})
                return self.accept(folder, read(responses[-1])['body'], stage, context, version)
            raise Stop('incomplete_unknown_stage_no_automatic_replay')
        self.guard()
        folder.mkdir(parents=True, exist_ok=False)
        save_new(folder / 'owner.json', {'worker': self.worker, 'version': version, 'stage': stage, 'endpoint': self.endpoint})
        save_new(folder / 'request.json', payload)
        save_new(folder / 'context.json', context)
        save_new(folder / 'image_identity.json', {'sha256': sha(image), 'bytes': len(image_bytes)})
        for attempt in range(1, self.config['transient_http_attempts'] + 1):
            self.guard()
            self.ledger['attempts'] += 1
            event = {'number': self.ledger['attempts'], 'worker': self.worker, 'version': version,
                'folder': str(folder.relative_to(self.root)), 'stage': stage, 'attempt': attempt,
                'start': stamp(), 'state': 'sent_outcome_pending', 'request_sha256': sha(folder / 'request.json')}
            self.ledger['events'].append(event)
            owned_update(self.ledger_file, self.ledger)
            start = time.monotonic()
            try:
                response = self.http.post(self.endpoint, json=payload,
                    timeout=self.config['http_timeout_seconds'], allow_redirects=False)
            except requests.RequestException as exc:
                event.update(state='unknown_transport', error=type(exc).__name__, elapsed=time.monotonic()-start)
                self.ledger['blocked'] = 'unknown_transport_no_retry'
                owned_update(self.ledger_file, self.ledger)
                raise Stop(self.ledger['blocked']) from exc
            try:
                body = response.json()
            except ValueError:
                body = {'raw_body': response.text}
            save_new(folder / ('response_%02d.json' % attempt), {'http_status': response.status_code, 'body': body})
            event.update(http_status=response.status_code, state='response_saved', elapsed=time.monotonic()-start,
                usage=body.get('usage') if isinstance(body, dict) else None,
                model=body.get('model') if isinstance(body, dict) else None)
            owned_update(self.ledger_file, self.ledger)
            if response.status_code in (408, 429, 500, 502, 503, 504) and attempt < self.config['transient_http_attempts']:
                time.sleep(2)
                continue
            if response.status_code != 200:
                self.ledger['blocked'] = 'http_%s' % response.status_code
                owned_update(self.ledger_file, self.ledger)
                raise Stop(self.ledger['blocked'])
            return self.accept(folder, body, stage, context, version)

    def accept(self, folder, body, stage, context, version):
        try:
            if not isinstance(body, dict) or body.get('model') != self.config['model']:
                raise ValueError('unexpected service response/model')
            # Preserve v3's original parser/validation; never silently normalize it.
            if version == 'v3' and stage != 'control':
                value = json.loads(body['choices'][0]['message']['content'])
            else:
                choices = body.get('choices')
                if not isinstance(choices, list) or len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                    raise ValueError('incomplete or nonunique response')
                value = json.loads(choices[0]['message']['content'], object_pairs_hook=unique_object)
            validate(version, stage, value, context)
        except Exception as exc:
            save_new(folder / 'failure.json', {'type': type(exc).__name__, 'error': str(exc), 'no_quality_retry': True})
            raise
        save_new(folder / 'accepted.json', value)
        return value
