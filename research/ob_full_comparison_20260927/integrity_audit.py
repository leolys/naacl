"""OFFLINE ONLY: independently match every request/result/accounting event to its owner."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from engine import contexts, output_schema, validate, PORTS
from evaluate import HERE, VERSIONS, read, sha, new


def prompts(version):
    spec = importlib.util.spec_from_file_location('audit_' + version, HERE / ('prompts_' + version + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(capture, output):
    archive_manifest = read(capture / 'CAPTURE_MANIFEST.json')
    for filename, expected in archive_manifest['files'].items():
        if sha(capture / filename) != expected:
            raise ValueError('capture bytes differ: ' + filename)
    if sha(capture / 'RUNTIME_SEAL.json') != sha(HERE / 'RUNTIME_SEAL.json'):
        raise ValueError('captured runtime seal differs')
    manifest = read(HERE / 'manifest.json')['units']
    config = read(HERE / 'config.json')
    rows = read(HERE / 'schedule.json')['rows']
    assignment = {(x['version'], x['unit']): x['worker'] for x in rows}
    modules = {v: prompts(v) for v in VERSIONS}
    events, stage_events = [], {}
    response_paths = set()
    issues = []
    for worker in range(4):
        path = capture / 'workers' / str(worker) / 'ledger.json'
        if not path.exists():
            issues.append('missing ledger ' + str(worker))
            continue
        ledger = read(path)
        assert ledger['attempts'] == len(ledger['events']) <= 650
        assert [e['number'] for e in ledger['events']] == list(range(1, ledger['attempts']+1))
        for event in ledger['events']:
            assert event['worker'] == worker
            folder = capture / event['folder']
            parts = Path(event['folder']).parts
            if event['stage'] == 'control':
                assert parts == ('workers', str(worker), 'control') and event['version'] == 'plain'
            else:
                assert len(parts) == 4 and parts[0] == 'runs'
                assert (parts[1], parts[3]) == (event['version'], event['stage'])
                assert assignment[(parts[1], parts[2])] == worker
            request = folder / 'request.json'
            assert sha(request) == event['request_sha256']
            owner = read(folder / 'owner.json')
            assert owner == {'worker': worker, 'version': event['version'], 'stage': event['stage'],
                             'endpoint': 'http://127.0.0.1:%d/v1/chat/completions' % PORTS[worker]}
            response = folder / ('response_%02d.json' % event['attempt'])
            response_name = response.relative_to(capture).as_posix()
            if response_name in response_paths:
                raise ValueError('same response counted more than once')
            response_paths.add(response_name)
            if response.exists():
                raw = read(response)
                assert raw['http_status'] == event.get('http_status')
                if isinstance(raw['body'], dict):
                    assert raw['body'].get('usage') == event.get('usage')
            else:
                issues.append('no archived response: ' + event['folder'])
            stage_events.setdefault(event['folder'], []).append(event)
        events += ledger['events']
    actual_response_paths = {p.relative_to(capture).as_posix() for base in ('runs', 'workers')
                             for p in (capture / base).rglob('response_*.json')}
    if actual_response_paths - response_paths:
        raise ValueError('orphan response not represented by the ledger')
    actual_request_folders = {p.parent.relative_to(capture).as_posix() for base in ('runs', 'workers')
                             for p in (capture / base).rglob('request.json')}
    if actual_request_folders != set(stage_events):
        raise ValueError('request/ledger stage set mismatch')
    checked_requests = checked_results = 0
    for (version, key), worker in assignment.items():
        root = capture / 'runs' / version / key
        result_file = root / 'result.json'
        if not result_file.exists():
            issues.append('missing result ' + version + '/' + key)
            continue
        result = read(result_file)
        assert (result['version'], result['unit'], result['worker']) == (version, key, worker)
        checked_results += 1
        projected = read(HERE / 'data' / key / 'input.json')
        notes = checks = None
        expected_stages = ['decide'] if version == 'plain' else ['read', 'verify', 'decide']
        for stage in expected_stages:
            folder = root / stage
            request_path = folder / 'request.json'
            if not request_path.exists():
                if result['status'] == 'completed':
                    raise ValueError('completed result lacks required stage')
                break
            request = read(request_path)
            assert request['messages'][0] == {'role': 'system', 'content': getattr(modules[version], stage.upper())}
            actual = json.loads(request['messages'][1]['content'][0]['text'])
            expected = contexts(projected, notes, checks)
            assert actual == expected == read(folder / 'context.json')
            assert request['structured_outputs']['json'] == output_schema(version, stage, expected)
            for parameter in ('model', 'temperature', 'top_p', 'top_k', 'seed'):
                assert request[parameter] == config[parameter]
            assert request['max_tokens'] == config['max_output_tokens'][stage]
            assert request['chat_template_kwargs'] == {'enable_thinking': config['enable_thinking']}
            data_uri = request['messages'][1]['content'][1]['image_url']['url']
            image = base64.b64decode(data_uri.split(',', 1)[1], validate=True)
            assert hashlib.sha256(image).hexdigest() == manifest[key]['image_sha256']
            assert str(folder.relative_to(capture)).replace('\\', '/') in stage_events
            accepted_path = folder / 'accepted.json'
            checked_requests += 1
            if not accepted_path.exists():
                assert result['status'] != 'completed'
                break
            accepted = read(accepted_path)
            responses = [read(p) for p in sorted(folder.glob('response_*.json'))]
            successful = [r for r in responses if r['http_status'] == 200]
            assert len(successful) == 1
            assert successful[0]['body']['model'] == config['model']
            assert json.loads(successful[0]['body']['choices'][0]['message']['content']) == accepted
            validate(version, stage, accepted, expected)
            if stage == 'read':
                notes = accepted
            elif stage == 'verify':
                checks = accepted
            else:
                assert accepted == result['choice']
    if len({(e['worker'], e['number']) for e in events}) != len(events):
        raise ValueError('duplicate worker ledger event')
    new(output, {'capture_sha256': sha(capture / 'CAPTURE_MANIFEST.json'),
        'captured_files_sha256_checked': len(archive_manifest['files']), 'result_ownership_checked': checked_results,
        'exact_stage_requests_checked': checked_requests, 'accounting_attempts_checked': len(events),
        'duplicate_configurations': 0, 'cross_version_or_worker_mismatches': 0,
        'public_context_or_image_mismatches': 0, 'remaining_missing_evidence': issues,
        'complete_evidence_panel': checked_results == 840 and not issues,
        'partial_stage_semantics_checked_only_for_terminal_results': checked_results != 840,
        'response_unique_and_no_orphans': True,
        'semantic_correctness_not_certified': True})
    print(json.dumps({'checked_results': checked_results, 'checked_stage_requests': checked_requests, 'issues': len(issues)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.capture, args.output)
