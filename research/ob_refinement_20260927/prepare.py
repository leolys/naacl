"""Mechanical projection of already frozen public inputs; no network or inference."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'ob_grounded_20260927'
DEV = ('b001 b002 b003 b011 b012 b017 b035 b041 env001 env032 env035 '
       'health002 health005 health006 pub001 pub005 pub006 pub008 pub009 pub021 '
       'pub030 pub032 pub035 pub038').split()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def main():
    if (HERE / 'manifest.json').exists() or (HERE / 'data').exists():
        raise RuntimeError('Prepared input already exists; never overwrite')
    manifest = read(OLD / 'manifest.json')
    summary = read(OLD / 'runs/v3_full/summary.json')
    labels = read(OLD / 'ORIGINAL_LABEL_ALIGNMENT_v2.json')
    choices = read(OLD / 'FULL_LABEL_AGREEMENT.json')
    result = {'scope': '140 original single-image inputs, fixed old O/B candidates; dev24/application116',
              'development_ids': DEV, 'units': {}, 'original_manifest_sha256': sha(OLD / 'manifest.json'),
              'original_summary_sha256': sha(OLD / 'runs/v3_full/summary.json')}
    for key, unit in manifest['units'].items():
        if unit['panel'] != 'full':
            continue
        original = OLD / 'data' / key
        projected = read(original / 'input.json')
        candidate_path = original / 'input.json'
        if not projected['records']:
            previous = summary['units'][key]
            root = OLD / previous['reused_from'] if previous.get('reused_from') else OLD / 'runs/v3_full' / key
            candidate_path = root / 'projected.json'
            generated = read(candidate_path)
            assert all(generated[k] == projected[k] for k in ('goal', 'public_task', 'options'))
            projected['records'] = generated['records']
        assert set(projected) == {'goal', 'public_task', 'options', 'records'} and projected['records']
        target = HERE / 'data' / key
        write(target / 'input.json', projected)
        shutil.copyfile(original / unit['image'], target / unit['image'])
        result['units'][key] = {'slug': unit['slug'], 'panel': 'dev' if unit['slug'] in DEV else 'application',
            'family': unit['family'], 'domain': unit['domain'], 'image': unit['image'],
            'image_sha256': sha(target / unit['image']), 'input_sha256': sha(target / 'input.json'),
            'old_input_sha256': sha(original / 'input.json'),
            'candidate_source_path': str(candidate_path.relative_to(OLD)), 'candidate_source_sha256': sha(candidate_path),
            'candidate_source': unit['candidate_source'], 'record_count': len(projected['records'])}
    assert len(result['units']) == 140 and sum(u['panel'] == 'dev' for u in result['units'].values()) == 24
    write(HERE / 'manifest.json', result)
    write(HERE / 'offline/labels.json', labels)
    write(HERE / 'offline/old_v3_choices.json', choices)
    write(HERE / 'offline/old_v3_summary.json', summary)
    (HERE / 'legacy').mkdir(exist_ok=False)
    for old, new in [('run.py', 'engine.py'), ('schema.py', 'schema.py')]:
        shutil.copyfile(OLD / old, HERE / 'legacy' / new)
    shutil.copyfile(OLD / 'collect.py', HERE / 'collect.py')
    write(HERE / 'legacy/IDENTITY.json', {'source_root': str(OLD),
        'files': {name: sha(HERE / 'legacy' / name) for name in ('engine.py', 'schema.py')},
        'meaning': 'Reuse archived transport/budget/response preservation logic; new runner does not invoke legacy.run.'})
    print(json.dumps({'units': 140, 'dev': 24, 'application': 116, 'manifest_sha256': sha(HERE / 'manifest.json')}))


if __name__ == '__main__':
    main()
