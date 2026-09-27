"""Prepare native-Codex translation work; never calls a model or network."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import panel_core as core
import run_panel as runner


def sid(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:20]


def records():
    for entry in core.read(HERE.parent / 'catalog.json')['tasks']:
        folder = HERE / 'run' / 'tasks' / entry['task_slug']
        record = core.read(folder / 'record.json') or runner.initial_record(entry, HERE.parent)
        # View-only archive recovery: retain truncated/nonparsed model text, never
        # reinterpret it as a valid verification or mutate the canonical record.
        for phase in ('proposal', 'generation', 'verification'):
            if record['status'][phase] != 'failed':
                continue
            stage_folder = record.get('stages', {}).get(phase, {}).get('folder')
            if not stage_folder:
                continue
            responses = sorted((folder / stage_folder).glob('response_*.json'))
            if not responses:
                continue
            path = responses[-1]
            body = core.read(path)
            choices = body.get('choices', []) if isinstance(body, dict) else []
            if not choices or not isinstance(choices[0], dict):
                continue
            text = choices[0].get('message', {}).get('content')
            if isinstance(text, str) and text.strip():
                record.setdefault('display_failure_outputs', {})[phase] = text
                record.setdefault('display_failure_provenance', {})[phase] = {
                    'response_file': str(path), 'sha256': core.digest(path),
                    'finish_reason': choices[0].get('finish_reason'),
                    'scope': 'raw failed-stage output for viewing only; not repaired or accepted'}
        yield record


def items(record):
    values = core.translation_items(record)
    # Rejected output remains readable too; use the same text traversal rules.
    for phase in ('proposal', 'generation', 'verification'):
        name = phase + '_invalid_raw'
        if name in record:
            for row in core.translation_items({phase if phase != 'generation' else 'generated': record[name]}):
                row['key'] = name + row['key'][row['key'].index('.'):]
                values.append(row)
    for phase, text in record.get('display_failure_outputs', {}).items():
        values.append({'key': 'display_failure_outputs.' + phase, 'text': text})
    return values


def prepare(max_chars=14000):
    inbox = HERE / 'translations' / 'inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    assigned = {}
    for path in sorted(inbox.glob('chunk_*.json')):
        for row in core.read(path)['items']:
            assigned[row['id']] = row['text']
    pending = {}
    for record in records():
        for row in items(record):
            identity = sid(row['text'])
            if identity in assigned:
                if assigned[identity] != row['text']:
                    raise ValueError('translation identity collision')
                continue
            pending.setdefault(identity, {'id': identity, 'text': row['text'], 'examples': []})
            if len(pending[identity]['examples']) < 2:
                pending[identity]['examples'].append(record['task_slug'] + ':' + row['key'])
    chunks, current, size = [], [], 0
    for row in pending.values():
        if current and size + len(row['text']) > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(row)
        size += len(row['text'])
    if current:
        chunks.append(current)
    offset = len(list(inbox.glob('chunk_*.json')))
    written = []
    for index, chunk in enumerate(chunks, offset + 1):
        path = inbox / ('chunk_%03d.json' % index)
        if path.exists():
            raise FileExistsError(path)
        core.dump(path, {'instruction': 'Translate faithfully into simplified Chinese. Preserve numbers, entities, quotes, negatives, uncertainty, and errors. No analysis or invented corrections. Return items keyed by id; no API calls.', 'items': chunk})
        written.append({'file': path.name, 'items': len(chunk), 'characters': sum(len(x['text']) for x in chunk)})
    print(json.dumps({'new': written, 'new_strings': len(pending)}, ensure_ascii=False))
    return written


def load_translations():
    result, warnings, provenance = {}, [], {}
    inbox = HERE / 'translations' / 'inbox'
    for path in sorted((HERE / 'translations' / 'outbox').glob('chunk_*.json')):
        source = core.read(inbox / path.name)
        value = core.read(path)
        expected = {row['id']: row['text'] for row in source['items']}
        if value.get('producer') != 'codex-native' or set(value.get('items', {})) != set(expected):
            raise ValueError('translation keys/producer mismatch: ' + path.name)
        checks = core.validate_translation([{'key': k, 'text': v} for k, v in expected.items()], value)
        warnings.extend({'file': path.name, **row} for row in checks)
        for identity, text in value['items'].items():
            if identity in result and result[identity] != text:
                raise ValueError('conflicting native translation')
            result[identity] = text
            provenance[identity] = path.relative_to(HERE).as_posix()
    return result, warnings, provenance


def status():
    translated, warnings, _ = load_translations()
    total, complete, missing = 0, 0, set()
    for record in records():
        expected = {sid(row['text']) for row in items(record)}
        total += len(expected)
        complete += expected <= set(translated)
        missing.update(expected - set(translated))
    value = {'native_unique_translations': len(translated), 'tasks_current_text_complete': complete,
             'missing_unique_strings': len(missing), 'numeric_warnings': warnings}
    print(json.dumps(value, ensure_ascii=False))
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'status'])
    args = parser.parse_args()
    prepare() if args.command == 'prepare' else status()
