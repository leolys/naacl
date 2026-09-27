"""Offline archive/result integrity checks; does not infer semantic correctness."""
import argparse
import json
from pathlib import Path
from evaluate import HERE, digest, read, save_new


def verify_snapshot(metadata):
    meta = read(metadata)
    archive = Path(metadata).with_suffix('.tgz')
    if digest(archive) != meta['archive_sha256'] or meta['files_changed_during_snapshot']:
        raise ValueError('Unstable or mismatched archive')
    for name, expected in meta['files'].items():
        path = (HERE / name).resolve()
        if HERE.resolve() not in path.parents or digest(path) != expected:
            raise ValueError('Extracted content mismatch: ' + name)
    return {'snapshot': Path(metadata).name, 'run': meta['run'],
            'archive_sha256': meta['archive_sha256'], 'verified_files': len(meta['files']),
            'semantic_validity': 'not assessed'}


def validate_requests(run):
    manifest = read(HERE / 'manifest.json')['units']
    summary = read(HERE / 'runs' / run / 'summary.json')
    allowed = {'goal', 'public_task', 'options', 'records', 'independent_visual_notes', 'ob_checks'}
    checked = 0
    accepted_checked = 0
    # Request files are transport archives; validate every actual request context,
    # not just the intermediate projected.json file.
    for request_file in (HERE / 'runs' / run).glob('full_*/*/request.json'):
        value = read(request_file)
        payload = value.get('payload', value)
        messages = payload['messages']
        user = messages[1]['content']
        context = read_user(user)
        if not set(context).issubset(allowed):
            raise ValueError('Unexpected online field: ' + str(request_file))
        key = request_file.parent.parent.name
        original = read(HERE / 'data' / key / 'input.json')
        stage = request_file.parent.name
        unit_path = request_file.parent.parent
        expected = {field: original[field] for field in ('goal', 'public_task', 'options')}
        if stage == 'verify' or (stage == 'decide' and not run.startswith('plain_')):
            expected.update(records=original['records'],
                            independent_visual_notes=read(unit_path / 'read/accepted.json'))
        if stage == 'decide' and not run.startswith('plain_'):
            expected['ob_checks'] = read(unit_path / 'verify/accepted.json')['reviews']
        if context != expected or read(request_file.parent / 'context.json') != context:
            raise ValueError('Actual stage context differs from original or preceding accepted output')
        for field in ('goal', 'public_task', 'options'):
            if context[field] != original[field]:
                raise ValueError('Public projection changed')
        if 'records' in context and context['records'] != original['records']:
            raise ValueError('Original O/B changed')
        if len([x for x in user if x['type'] == 'image_url']) != 1:
            raise ValueError('Expected one unchanged image')
        import base64, hashlib
        image_url = next(x['image_url']['url'] for x in user if x['type'] == 'image_url')
        image_hash = hashlib.sha256(base64.b64decode(image_url.split(',', 1)[1])).hexdigest()
        if image_hash != manifest[key]['image_sha256']:
            raise ValueError('Image differs from fixed original')
        accepted_path = request_file.parent / 'accepted.json'
        if accepted_path.exists():
            response_path = sorted(request_file.parent.glob('response_*.json'))[-1]
            response = read(response_path)
            choice = response['body']['choices'][0]
            if (response['http_status'] != 200 or choice['finish_reason'] != 'stop'
                    or response['body']['model'] != 'Qwen3.8-27B'
                    or json.loads(choice['message']['content']) != read(accepted_path)):
                raise ValueError('Accepted output does not match actual successful response')
            if stage == 'decide':
                result = read(unit_path / 'result.json')
                if (result['choice'] != read(accepted_path)
                        or result != summary['units'][key]):
                    raise ValueError('Final selection differs from accepted response or summary')
            accepted_checked += 1
        checked += 1
    if checked == 0:
        raise ValueError('No archived requests found; do not silently PASS')
    return {'run': run, 'actual_request_files_checked': checked,
            'accepted_responses_and_stage_links_checked': accepted_checked,
            'public_projection_and_image_identity': True, 'status': summary['status'],
            'semantic_validity': 'not assessed'}


def read_user(content):
    import json
    texts = [x['text'] for x in content if x['type'] == 'text']
    if len(texts) != 1:
        raise ValueError('Expected single JSON public context')
    return json.loads(texts[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify_snapshot(args.snapshot)
    result['request_check'] = validate_requests(result['run'])
    save_new(args.output, result)
    print(result)
