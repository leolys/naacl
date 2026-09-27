"""Read-only cross-file audit of finalized runs; no model, gold, or semantic scoring."""
import argparse
import ast
import base64
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = ('v1_dev', 'v2_dev', 'v3_dev', 'v3_confirm', 'v3_full')


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(root, ledger, run_names=RUNS):
    manifest, frozen = read(root / 'manifest.json'), read(root / 'FREEZE.json')
    issues, response_paths, stages, usage, results = [], set(), Counter(), Counter(), {}
    response_records = {}
    checked_requests = checked_acceptances = 0

    def require(condition, message):
        if not condition:
            issues.append(message)

    for name, identity in frozen['runtime_hashes'].items():
        require(sha(root / name) == identity, 'canonical_runtime:' + name)
    for key, unit in manifest['units'].items():
        data = root / 'data' / key
        require(sha(data / 'input.json') == unit['input_sha256'], 'input:' + key)
        require(sha(data / unit['image']) == unit['image_sha256'], 'image:' + key)

    for run_name in run_names:
        folder = root / 'runs' / run_name
        summary, identities = read(folder / 'summary.json'), read(folder / 'source_hashes.json')
        require(summary['status'] == 'finished', 'not_finished:' + run_name)
        require(summary.get('runtime_preserved') is True, 'runtime_not_preserved:' + run_name)
        for name, identity in identities.items():
            require(sha(folder / 'runtime_source' / name) == identity, 'source_snapshot:' + run_name + '/' + name)
        if run_name in ('v3_confirm', 'v3_full'):
            require(identities == frozen['runtime_hashes'], 'nonfrozen:' + run_name)
        expected = {k for k, u in manifest['units'].items() if
                    (summary['panel'] == 'dev' and u['panel'] == 'dev') or
                    (summary['panel'] == 'confirm' and u['panel'] == 'full' and u['confirm']) or
                    (summary['panel'] == 'full' and u['panel'] == 'full')}
        require(set(summary['units']) == expected, 'panel_coverage:' + run_name)
        source = folder / 'runtime_source'
        config = read(source / 'config.json')
        schema_spec = importlib.util.spec_from_file_location('archived_schema_' + run_name, source / 'schema.py')
        schema_module = importlib.util.module_from_spec(schema_spec)
        schema_spec.loader.exec_module(schema_module)
        require(config['endpoint'] == 'http://127.0.0.1:8058/v1/chat/completions', 'endpoint:' + run_name)
        assignments = ast.parse((source / ('prompts_' + summary['version'] + '.py')).read_text(encoding='utf-8')).body
        prompts = {n.targets[0].id.lower(): ast.literal_eval(n.value) for n in assignments
                   if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
        for key, result in summary['units'].items():
            unit = manifest['units'][key]
            dest = folder / key
            require(read(dest / 'result.json') == result, 'result_summary:' + run_name + '/' + key)
            if result.get('reused_from'):
                prior = root / result['reused_from']
                require(result == {**read(prior / 'result.json'), 'reused_from': result['reused_from'], 'new_calls': 0}, 'reuse:' + key)
                require(not list(dest.glob('*/request.json')), 'reused_but_called:' + key)
                continue
            original = read(root / 'data' / key / 'input.json')
            projected = read(dest / 'projected.json') if (dest / 'projected.json').exists() else original
            expected_projected = json.loads(json.dumps(original))
            if not original['records'] and (dest / 'supply/accepted.json').exists():
                expected_projected['records'] = read(dest / 'supply/accepted.json')['records']
            require(projected == expected_projected, 'candidate_mutation:' + run_name + '/' + key)
            if result['status'] == 'completed':
                require(result['choice'] == read(dest / 'decide/accepted.json'), 'choice_mutation:' + run_name + '/' + key)
            for request_path in dest.glob('*/request.json'):
                checked_requests += 1
                stage = request_path.parent.name
                request = read(request_path)
                require(request['messages'][0]['content'] == prompts[stage], 'system:' + str(request_path))
                for name in ('model', 'temperature', 'top_p', 'top_k', 'seed'):
                    require(request[name] == config[name], 'decoding:' + name + ':' + str(request_path))
                require(request['max_tokens'] == config['max_output_tokens'][stage], 'output_budget:' + str(request_path))
                require(request['chat_template_kwargs']['enable_thinking'] == config['enable_thinking'], 'thinking:' + str(request_path))
                require(request['structured_outputs']['json'] == schema_module.SCHEMAS[stage], 'schema:' + str(request_path))
                payload = request['messages'][1]['content']
                require(len(payload) == 2, 'unexpected_content:' + str(request_path))
                image = base64.b64decode(payload[1]['image_url']['url'].split(',', 1)[1])
                require(hashlib.sha256(image).hexdigest() == unit['image_sha256'], 'payload_image:' + str(request_path))
                require(read(request_path.parent / 'image_identity.json') == {'sha256': unit['image_sha256'], 'bytes': len(image)}, 'image_sidecar:' + str(request_path))
                context = json.loads(payload[0]['text'])
                expected_context = {k: projected[k] for k in ('goal', 'public_task', 'options')}
                if stage in ('verify', 'decide'):
                    expected_context = {**projected, 'independent_visual_notes': read(dest / 'read/accepted.json')}
                if stage == 'decide':
                    expected_context['ob_checks'] = read(dest / 'verify/accepted.json')['reviews']
                require(context == expected_context, 'context_projection:' + str(request_path))
                require(read(request_path.parent / 'context.json') == context, 'context_sidecar:' + str(request_path))
                bodies = []
                for response_path in sorted(request_path.parent.glob('response_*.json')):
                    rel = response_path.relative_to(root).as_posix()
                    require(rel not in response_paths, 'duplicate_response:' + rel)
                    response_paths.add(rel)
                    stages[stage] += 1
                    response_records[rel] = read(response_path)
                    body = response_records[rel].get('body')
                    bodies.append(body)
                    if isinstance(body, dict):
                        require(body.get('model') == config['model'], 'response_model:' + rel)
                        usage.update({k: v for k, v in (body.get('usage') or {}).items() if isinstance(v, int)})
                accepted = request_path.parent / 'accepted.json'
                if accepted.exists():
                    checked_acceptances += 1
                    require(bool(bodies) and read(accepted) == json.loads(bodies[-1]['choices'][0]['message']['content']), 'accepted_mutation:' + str(accepted))
                elif result['status'] == 'interface_failed':
                    require((request_path.parent / 'failure.json').exists(), 'missing_failure:' + str(request_path))
        results[run_name] = {'states': dict(Counter(r['status'] for r in summary['units'].values())),
                             'planned': len(expected), 'reused': sum(bool(r.get('reused_from')) for r in summary['units'].values())}

    ledger_usage, numbered, event_paths = Counter(), set(), set()
    for event in ledger['events']:
        numbered.add(event['number'])
        require(event['state'] == 'response_saved', 'unresolved_attempt:' + str(event['number']))
        rel = event['folder'].replace('\\', '/') + '/response_%02d.json' % event['attempt']
        require(rel in response_paths, 'ledger_response_missing:' + rel)
        require(rel not in event_paths, 'duplicate_ledger_response:' + rel)
        event_paths.add(rel)
        if rel in response_records:
            response = response_records[rel]
            body = response.get('body')
            require(event.get('http_status') == response.get('http_status'), 'event_http:' + str(event['number']))
            require(event.get('usage') == (body.get('usage') if isinstance(body, dict) else None), 'event_usage:' + str(event['number']))
            require(event.get('model') == (body.get('model') if isinstance(body, dict) else None), 'event_model:' + str(event['number']))
            require(event['stage'] == Path(event['folder']).name, 'event_stage:' + str(event['number']))
        if event.get('usage'):
            ledger_usage.update({k: v for k, v in event['usage'].items() if isinstance(v, int)})
    require(numbered == set(range(1, ledger['attempts'] + 1)), 'noncontiguous_ledger')
    require(event_paths == response_paths, 'ledger_response_set_mismatch')
    require(len(ledger['events']) == ledger['attempts'] == len(response_paths), 'ledger_response_count')
    require(ledger_usage == usage, 'usage_not_reconciled')
    return {'artifact_audit_passed': not issues, 'issues': issues, 'checked_unique_requests': checked_requests,
            'checked_raw_acceptances': checked_acceptances, 'archived_responses': len(response_paths),
            'attempts': ledger['attempts'], 'usage': dict(usage), 'responses_by_stage': dict(stages), 'runs': results,
            'business_submissions': 0, 'scope': 'File identities, exact request/accepted content, complete panel coverage, unchanged reuse, and ledger reconciliation. Not semantic O/B truth, human approval, or demonstrated causal benefit.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runs', nargs='+', choices=RUNS, default=RUNS)
    args = parser.parse_args()
    ledger = read(args.ledger)
    result = audit(HERE, ledger.get('ledger', ledger), args.runs)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
