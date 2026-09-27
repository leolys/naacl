"""Offline tests; all inference HTTP is mocked and cannot measure effectiveness."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import tempfile
from unittest.mock import patch
import pytest
import requests

import engine
import run
from schema import output_schema, validate

HERE = Path(__file__).resolve().parent


def example():
    return engine.read(HERE / 'data/full_b002/input.json')


def example_image():
    unit = engine.read(HERE / 'manifest.json')['units']['full_b002']
    return HERE / 'data/full_b002' / unit['image']


def response(value, finish='stop'):
    return {'model': 'Qwen3.8-27B', 'choices': [{'finish_reason': finish,
        'message': {'content': json.dumps(value)}}], 'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8}}


def config():
    value = engine.read(HERE / 'config.json')
    value['deadline_utc'] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return value


class FakeHTTP:
    status_code = 200
    def __init__(self, value):
        self.value = value
    def json(self):
        return self.value


def test_fixed_split_and_images():
    manifest = engine.read(HERE / 'manifest.json')
    assert len(manifest['units']) == 140
    assert sum(v['panel'] == 'dev' for v in manifest['units'].values()) == 24
    for key, unit in manifest['units'].items():
        folder = HERE / 'data' / key
        assert engine.sha(folder / unit['image']) == unit['image_sha256']
        assert engine.sha(folder / 'input.json') == unit['input_sha256']
        assert engine.read(folder / 'input.json')['records']


def test_plain_and_read_share_only_public_context():
    projected = example()
    result = run.contexts(projected)
    assert set(result) == {'goal', 'public_task', 'options'}
    assert 'records' not in result and 'family' not in result
    result['options'].clear()
    assert projected['options']


def test_conditions_and_real_history_preserved():
    projected = example()
    notes = {'appearance_facts': [], 'printed_facts': [], 'public_definitions': [], 'uncertain': []}
    checks = {'reviews': {'r1': {'B': 'test'}}}
    value = run.contexts(projected, notes, checks)
    assert value['records'] == projected['records']
    assert value['independent_visual_notes'] == notes and value['ob_checks'] == checks['reviews']
    assert all(set(r) == {'id', 'O', 'B'} for r in value['records'])
    value['records'][0]['B'] = 'changed'
    assert projected['records'][0]['B'] != 'changed'


def test_fixed_record_and_observation_keys():
    projected = example()
    schema = output_schema('verify', projected)
    properties = schema['properties']['reviews']['properties']
    for record in projected['records']:
        assert set(properties[record['id']]['properties']['O']['properties']) == {str(i) for i in range(1, len(record['O'])+1)}
    assert set(properties) == {r['id'] for r in projected['records']}


def test_valid_verify_and_wrong_case_not_repaired():
    projected = example()
    records = {r['id']: {'O': {str(i): {'evidence': 'visible', 'status': 'supported'} for i in range(1, len(r['O'])+1)},
                          'B': {'reading_checked': 'original condition', 'evidence': 'not established', 'status': 'unclear'}}
               for r in projected['records']}
    value = {'reviews': records}
    assert validate('verify', value, projected) == value
    modified = copy.deepcopy(value)
    key = next(iter(modified['reviews']))
    modified['reviews'][key.upper()] = modified['reviews'].pop(key)
    with pytest.raises(ValueError):
        validate('verify', modified, projected)


def test_decision_null_and_public_options_only():
    projected = example()
    validate('decide', {'basis': 'insufficient', 'option_label': None}, projected)
    validate('decide', {'basis': 'evidence', 'option_label': projected['options'][0]}, projected)
    with pytest.raises(ValueError):
        validate('decide', {'basis': 'guess', 'option_label': 'invented option'}, projected)


def test_no_identifier_specific_prompts():
    for path in HERE.glob('prompts_*.py'):
        assert not re.search(r'\b(?:pub|env|health|b)\d{3}\b', path.read_text(encoding='utf-8'))


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError):
        json.loads('{"a":1,"a":2}', object_pairs_hook=engine.unique_object)


def test_call_payload_response_ledger_and_resume():
    projected = example()
    context = run.public_context(projected)
    chosen = {'basis': 'visible public basis', 'option_label': context['options'][0]}
    with tempfile.TemporaryDirectory() as tmp:
        client = engine.Client(config(), tmp)
        folder = Path(tmp) / 'runs/plain_dev/full_b002/decide'
        image = example_image()
        with patch.object(client.http, 'post', return_value=FakeHTTP(response(chosen))) as request:
            assert client.call(folder, 'plain prompt', context, image, 'decide') == chosen
            payload = request.call_args.kwargs['json']
            assert payload['structured_outputs']['json'] == output_schema('decide', context)
            assert set(json.loads(payload['messages'][1]['content'][0]['text'])) == {'goal', 'public_task', 'options'}
            assert request.call_args.kwargs['allow_redirects'] is False
            assert client.call(folder, 'plain prompt', context, image, 'decide') == chosen
            assert request.call_count == 1 and client.ledger['attempts'] == 1
            assert (folder / 'response_01.json').exists()
        changed = copy.deepcopy(context)
        changed['goal'] += ' changed'
        with pytest.raises(engine.Stop):
            client.call(folder, 'plain prompt', changed, image, 'decide')


def test_no_quality_retry_and_raw_length_saved():
    context = run.public_context(example())
    chosen = {'basis': 'x', 'option_label': None}
    with tempfile.TemporaryDirectory() as tmp:
        client = engine.Client(config(), tmp)
        folder = Path(tmp) / 'runs/x/full_b002/decide'
        with patch.object(client.http, 'post', return_value=FakeHTTP(response(chosen, 'length'))) as request:
            with pytest.raises(ValueError):
                client.call(folder, 'prompt', context, example_image(), 'decide')
            with pytest.raises(ValueError):
                client.call(folder, 'prompt', context, example_image(), 'decide')
            assert request.call_count == 1 and (folder / 'response_01.json').exists()
            assert engine.read(folder / 'failure.json')['no_quality_retry'] is True


def test_unknown_transport_blocks_further_requests():
    with tempfile.TemporaryDirectory() as tmp:
        client = engine.Client(config(), tmp)
        with patch.object(client.http, 'post', side_effect=requests.Timeout) as request:
            with pytest.raises(engine.Stop):
                client.call(Path(tmp) / 'runs/x/full_b002/decide', 'prompt', run.public_context(example()),
                            example_image(), 'decide')
            with pytest.raises(engine.Stop):
                client.guard()
            assert request.call_count == 1 and client.ledger['attempts'] == 1


def test_budget_deadline_endpoint_and_application_gate():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = config()
        cfg['max_attempts'] = 0
        with pytest.raises(engine.Stop):
            engine.Client(cfg, tmp).guard()
        cfg = config()
        cfg['deadline_utc'] = '2000-01-01T00:00:00+00:00'
        with pytest.raises(engine.Stop):
            engine.Client(cfg, tmp).guard()
        cfg = config()
        cfg['endpoint'] = 'https://example.invalid'
        with pytest.raises(ValueError):
            engine.Client(cfg, tmp)
    if not (HERE / 'FREEZE.json').exists():
        with pytest.raises(FileNotFoundError):
            run.run('application', 'plain')
