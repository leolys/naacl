"""Reuse proven transport only; make new task-indexed schemas explicit per request."""
import importlib.util
import json
from pathlib import Path
import sys
from schema import output_schema, validate

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy_schema = load('_transport_schema_snapshot', HERE / 'legacy/schema.py')
previous = sys.modules.get('schema')
try:
    sys.modules['schema'] = legacy_schema
    legacy = load('_transport_snapshot', HERE / 'legacy/engine.py')
finally:
    if previous is None:
        sys.modules.pop('schema', None)
    else:
        sys.modules['schema'] = previous
legacy.validate = validate
legacy.HERE = HERE
read, dump, sha, stamp, Stop = legacy.read, legacy.dump, legacy.sha, legacy.stamp, legacy.Stop
GlobalLock, preflight = legacy.GlobalLock, legacy.preflight


def unique_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError('duplicate JSON object key')
        value[key] = child
    return value


class Client(legacy.Client):
    def __init__(self, config, root=HERE):
        super().__init__(config, root)

    def call(self, folder, system, context, image, stage):
        # Whole runner is protected by a single process lock and concurrency=1.
        legacy.SCHEMAS[stage] = output_schema(stage, context)
        return super().call(folder, system, context, image, stage)

    def accept(self, folder, body, stage, context):
        try:
            if not isinstance(body, dict) or body.get('model') != self.config['model']:
                raise ValueError('unexpected service response/model')
            choices = body.get('choices')
            if not isinstance(choices, list) or len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                raise ValueError('incomplete or nonunique response')
            value = json.loads(choices[0]['message']['content'], object_pairs_hook=unique_object)
            validate(stage, value, context)
        except Exception as exc:
            dump(Path(folder) / 'failure.json', {'type': type(exc).__name__, 'error': str(exc), 'no_quality_retry': True})
            raise
        dump(Path(folder) / 'accepted.json', value)
        return value
