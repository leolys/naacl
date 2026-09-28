"""Portable cross-model runner for the static 140x6 panel.

New protocol version (xmodel). Distinct from the archived 2026-09-27 run:
new endpoints, new output root, self-declared runtime identity, no old seal.
Prompt text, contexts() projection, schemas, decoding parameters, stage flow,
and no-quality-retry discipline are kept byte-identical to the original engine.
"""
import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import requests
import sys

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent
for _p in (str(PANEL),):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import schema_new
import schema_v3
VERSIONS = ['plain', 'v3', 'v4', 'v5', 'v6', 'v7']
CONTROL_SCHEMA = {'type': 'object', 'properties': {'ready': {'type': 'boolean', 'enum': [True]}},
                  'required': ['ready'], 'additionalProperties': False}
MAX_TOTAL_ATTEMPTS = 2600


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


def update_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


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


def load_prompts(version):
    spec = importlib.util.spec_from_file_location('prompts_' + version, PANEL / ('prompts_' + version + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Runner:
    def __init__(self, args):
        self.model = args.model
        self.endpoint = args.endpoint.rstrip('/') + '/chat/completions'
        self.base = self.endpoint.split('/v1/chat/completions')[0]
        self.versions = args.versions
        self.enable_thinking = args.enable_thinking
        self.limit = args.limit
        self.root = Path(args.out)
        self.http_timeout = args.http_timeout
        self.http = requests.Session()
        self.http.trust_env = False
        self.ledger_file = self.root / 'ledger.json'
        self.ledger = read(self.ledger_file) if self.ledger_file.exists() else {
            'model': self.model, 'attempts': 0, 'events': [], 'structured_mode': None}
        self.manifest = read(PANEL / 'manifest.json')['units']
        self.labels_sha = sha(PANEL / 'offline/labels.json')
        self.mode_probed = False
        self.prompts = {v: load_prompts(v) for v in self.versions}

    def guard(self):
        if self.ledger.get('blocked'):
            raise Stop(self.ledger['blocked'])
        if self.ledger['attempts'] >= MAX_TOTAL_ATTEMPTS:
            raise Stop('total_attempt_cap')

    def probe(self):
        """One-time detection of structured-output parameter form on this server."""
        if self.ledger.get('structured_mode'):
            return
        base_schema = {'type': 'object', 'properties': {'ready': {'type': 'boolean', 'enum': [True]}},
                       'required': ['ready'], 'additionalProperties': False}
        for mode, field in (('structured_outputs', 'structured_outputs'), ('response_format', 'response_format')):
            payload = self._payload('probe', 'Return exactly {"ready":true}. Non-chart service check.',
                                    {'purpose': 'structured-output mode probe'}, None, 'control',
                                    64, base_schema if mode == 'structured_outputs' else None,
                                    response_format=None if mode == 'structured_outputs'
                                    else {'type': 'json_schema', 'json_schema': {'name': 'probe', 'schema': base_schema}})
            if mode == 'response_format':
                payload.pop('structured_outputs', None)
            self.ledger['attempts'] += 1
            self.ledger['events'].append({'number': self.ledger['attempts'], 'version': 'probe',
                                          'stage': 'control', 'mode': mode, 'start': stamp(),
                                          'state': 'sent_outcome_pending'})
            response = self.http.post(self.endpoint, json=payload, timeout=self.http_timeout, allow_redirects=False)
            try:
                body = response.json()
            except ValueError:
                body = {'raw_body': response.text}
            self.ledger['events'][-1].update(http_status=response.status_code, state='response_saved',
                usage=body.get('usage') if isinstance(body, dict) else None)
            update_json(self.ledger_file, self.ledger)
            if response.status_code == 200:
                self.ledger['structured_mode'] = mode
                update_json(self.ledger_file, self.ledger)
                return
            print('probe %s -> %d %s' % (mode, response.status_code, str(response.text)[:200]), flush=True)
        self.ledger['structured_mode'] = 'none'
        update_json(self.ledger_file, self.ledger)
        print('structured-output disabled; relying on prompt + strict validation', flush=True)

    def _payload(self, stage, system, context, image_path, version, max_tokens, schema=None, response_format=None):
        content = [{'type': 'text', 'text': json.dumps(context, ensure_ascii=False, indent=2)}]
        if image_path is not None:
            image_bytes = Path(image_path).read_bytes()
            mime = 'image/jpeg' if image_bytes[:2] == b'\xff\xd8' else 'image/png'
            content.append({'type': 'image_url', 'image_url': {'url': 'data:' + mime + ';base64,' +
                base64.b64encode(image_bytes).decode('ascii')}})
        payload = {'model': self.model, 'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'seed': 12345,
                   'max_tokens': max_tokens, 'messages': [{'role': 'system', 'content': system},
                                                          {'role': 'user', 'content': content}]}
        if self.enable_thinking:
            payload['chat_template_kwargs'] = {'enable_thinking': False}
        if schema is not None:
            payload['structured_outputs'] = {'json': schema}
        if response_format is not None:
            payload['response_format'] = response_format
        return payload

    def call(self, folder, system, context, image, stage, version):
        folder = Path(folder)
        schema = output_schema(version, stage, context)
        response_format = None
        mode = self.ledger.get('structured_mode')
        if mode == 'none':
            schema = None
        elif mode == 'response_format':
            response_format = {'type': 'json_schema', 'json_schema': {'name': version + '_' + stage, 'schema': schema}}
            schema = None
        payload = self._payload(stage, system, context, image, version,
                                64 if stage == 'control' else self._stage_tokens(stage),
                                schema, response_format)
        if folder.exists():
            if not (folder / 'request.json').exists() or read(folder / 'request.json') != payload:
                raise Stop('resume_payload_mismatch_or_unknown')
            if (folder / 'accepted.json').exists():
                return validate(version, stage, read(folder / 'accepted.json'), context)
            if (folder / 'failure.json').exists():
                raise ValueError('Previously failed stage retained; no quality retry')
            response_file = folder / 'response_01.json'
            if response_file.exists() and read(response_file).get('http_status') == 200:
                save_new(folder / ('recovery_%d.json' % time.time_ns()),
                         {'at': stamp(), 'response': response_file.name, 'new_request': False})
                return self.accept(folder, read(response_file)['body'], stage, context, version)
            raise Stop('incomplete_unknown_stage_no_automatic_replay')
        self.guard()
        folder.mkdir(parents=True, exist_ok=False)
        save_new(folder / 'request.json', payload)
        save_new(folder / 'context.json', context)
        if image is not None:
            save_new(folder / 'image_identity.json', {'sha256': sha(image), 'bytes': Path(image).stat().st_size})
        self.ledger['attempts'] += 1
        event = {'number': self.ledger['attempts'], 'version': version, 'stage': stage,
                 'folder': str(folder.relative_to(self.root)), 'start': stamp(), 'state': 'sent_outcome_pending'}
        self.ledger['events'].append(event)
        update_json(self.ledger_file, self.ledger)
        start = time.monotonic()
        try:
            response = self.http.post(self.endpoint, json=payload, timeout=self.http_timeout, allow_redirects=False)
        except requests.RequestException as exc:
            event.update(state='unknown_transport', error=type(exc).__name__, elapsed=time.monotonic() - start)
            self.ledger['blocked'] = 'unknown_transport_no_retry'
            update_json(self.ledger_file, self.ledger)
            raise Stop(self.ledger['blocked']) from exc
        try:
            body = response.json()
        except ValueError:
            body = {'raw_body': response.text}
        save_new(folder / 'response_01.json', {'http_status': response.status_code, 'body': body})
        event.update(http_status=response.status_code, state='response_saved', elapsed=time.monotonic() - start,
                     usage=body.get('usage') if isinstance(body, dict) else None,
                     model=body.get('model') if isinstance(body, dict) else None)
        update_json(self.ledger_file, self.ledger)
        if response.status_code != 200:
            self.ledger['blocked'] = 'http_%s' % response.status_code
            update_json(self.ledger_file, self.ledger)
            raise Stop(self.ledger['blocked'])
        return self.accept(folder, body, stage, context, version)

    @staticmethod
    def _stage_tokens(stage):
        return {'read': 1500, 'verify': 3600, 'decide': 700, 'control': 64}[stage]

    def accept(self, folder, body, stage, context, version):
        try:
            if not isinstance(body, dict) or body.get('model') != self.model:
                raise ValueError('unexpected service response/model')
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

    def run(self):
        self.root.mkdir(parents=True, exist_ok=True)
        identity_file = self.root / 'runtime_identity_xmodel.json'
        if not identity_file.exists():
            save_new(identity_file, {'model': self.model, 'endpoint': self.base, 'versions': self.versions,
                                     'enable_thinking_chat_template': self.enable_thinking,
                                     'labels_sha256': self.labels_sha, 'runner': 'xmodel_20260928',
                                     'max_total_attempts': MAX_TOTAL_ATTEMPTS,
                                     'decoding': {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'seed': 12345,
                                                  'max_output_tokens': {'read': 1500, 'verify': 3600, 'decide': 700, 'control': 64}}})
        identity = read(identity_file)
        if identity['model'] != self.model:
            raise Stop('identity model changed')
        summary_file = self.root / 'summary.json'
        summary = read(summary_file) if summary_file.exists() else {
            'model': self.model, 'status': 'prepared', 'started': stamp(), 'units': {},
            'expected_units': 140 * len(self.versions)}
        if getattr(self, 'limit', None):
            summary['limit'] = self.limit
        if summary['status'] == 'finished':
            print('already finished; no requests', flush=True)
            return
        health = self.http.get(self.base + '/health', timeout=15, allow_redirects=False)
        if health.status_code != 200:
            raise Stop('replica not ready')
        summary.update(status='running', pid=os.getpid(), endpoint=self.base)
        update_json(summary_file, summary)
        self.probe()
        control_folder = self.root / 'control'
        try:
            self.call(control_folder, 'Return exactly {"ready":true}. This is a non-chart service check.',
                      {'purpose': 'synthetic image plus structured-output service check'},
                      PANEL / 'controls/blank.png', 'control', 'plain')
        except Exception:
            control_folder_fallback = self.root / 'control_noimage'
            self.call(control_folder_fallback, 'Return exactly {"ready":true}. This is a non-chart service check.',
                      {'purpose': 'text-only structured-output service check'}, None, 'control', 'plain')
        unit_keys = list(self.manifest)
        if getattr(self, 'limit', None):
            unit_keys = unit_keys[:self.limit]
            summary['status'] = 'smoke_finished'
        for version in self.versions:
            for key in unit_keys:
                unit = self.manifest[key]
                data, dest = PANEL / 'data' / key, self.root / 'runs' / version / key
                result_file = dest / 'result.json'
                if result_file.exists():
                    summary['units'][version + '/' + key] = read(result_file)
                    continue
                if sha(data / 'input.json') != unit['input_sha256'] or sha(data / unit['image']) != unit['image_sha256']:
                    raise Stop('fixed data changed: ' + key)
                self.guard()
                projected = read(data / 'input.json')
                contexts(projected)
                result = {'unit': key, 'version': version, 'status': 'running', 'started': stamp()}
                notes = checks = None
                stage = 'decide' if version == 'plain' else 'read'
                try:
                    if version != 'plain':
                        print('READ ' + version + '/' + key, flush=True)
                        notes = self.call(dest / 'read', self.prompts[version].READ, contexts(projected),
                                          data / unit['image'], 'read', version)
                        stage = 'verify'
                        print('VERIFY ' + version + '/' + key, flush=True)
                        checks = self.call(dest / 'verify', self.prompts[version].VERIFY,
                                           contexts(projected, notes), data / unit['image'], 'verify', version)
                    stage = 'decide'
                    print('DECIDE ' + version + '/' + key, flush=True)
                    decision = self.call(dest / 'decide', self.prompts[version].DECIDE,
                                         contexts(projected, notes, checks), data / unit['image'], 'decide', version)
                    result.update(status='completed', choice=decision, ended=stamp())
                except Stop:
                    save_new(dest / ('stop_%d.json' % time.time_ns()),
                             {**result, 'status': 'stopped', 'stage': stage, 'at': stamp()})
                    raise
                except Exception as exc:
                    result.update(status='interface_failed', failed_stage=stage, ended=stamp(),
                                  error={'type': type(exc).__name__, 'message': str(exc)[:400]})
                save_new(result_file, result)
                summary['units'][version + '/' + key] = result
                summary.update(attempts=self.ledger['attempts'], updated=stamp())
                update_json(summary_file, summary)
                print('DONE %s/%s status=%s attempts=%d' % (version, key, result['status'],
                                                            self.ledger['attempts']), flush=True)
        summary['status'] = 'finished'
        summary.update(ended=stamp(), attempts=self.ledger['attempts'])
        update_json(summary_file, summary)
        print('finished units=%d attempts=%d' % (len(summary['units']), self.ledger['attempts']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--endpoint', required=True, help='e.g. http://127.0.0.1:8058/v1')
    parser.add_argument('--versions', default='plain,v3,v4,v5,v6,v7')
    parser.add_argument('--enable-thinking', action='store_true', help='send chat_template_kwargs enable_thinking=false')
    parser.add_argument('--out', required=True)
    parser.add_argument('--http-timeout', type=int, default=300)
    parser.add_argument('--limit', type=int, default=None, help='process only the first N units (smoke)')
    args = parser.parse_args()
    args.versions = [v for v in args.versions.split(',') if v]
    for v in args.versions:
        if v not in VERSIONS:
            raise SystemExit('unknown version: ' + v)
    Runner(args).run()
