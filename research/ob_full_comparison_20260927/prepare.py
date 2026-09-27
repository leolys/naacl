"""Mechanical copy of frozen inputs/prompts. No result-dependent selection."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'ob_refinement_20260927'
GROUND = HERE.parent / 'ob_grounded_20260927'
VERSIONS = ['plain', 'v3', 'v4', 'v5', 'v6', 'v7']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)


def copy_new(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    assert sha(source) == sha(destination)


def schedule_for(keys):
    assert len(keys) == 140 and len(set(keys)) == 140
    rows = []
    for worker in range(4):
        for position, key in enumerate(keys[worker::4]):
            shift = (position + worker) % len(VERSIONS)
            order = VERSIONS[shift:] + VERSIONS[:shift]
            for within, version in enumerate(order):
                rows.append({'worker': worker, 'case_position': position,
                             'within_case_position': within, 'unit': key, 'version': version})
    assert len(rows) == len({(r['unit'], r['version']) for r in rows}) == 840
    return rows


def main():
    original = read(OLD / 'manifest.json')
    assert len(original['units']) == 140
    for version in VERSIONS:
        source = (GROUND if version == 'v3' else OLD) / ('prompts_' + version + '.py')
        copy_new(source, HERE / source.name)
    copy_new(OLD / 'schema.py', HERE / 'schema_new.py')
    copy_new(GROUND / 'schema.py', HERE / 'schema_v3.py')
    for key, unit in original['units'].items():
        for filename, expected in [('input.json', unit['input_sha256']), (unit['image'], unit['image_sha256'])]:
            source = OLD / 'data' / key / filename
            assert sha(source) == expected
            copy_new(source, HERE / 'data' / key / filename)
        projected = read(HERE / 'data' / key / 'input.json')
        assert set(projected) == {'goal', 'public_task', 'options', 'records'}
        assert projected['records']
    new(HERE / 'manifest.json', {'scope': 'fresh descriptive six-version fixed140 single-image comparison',
        'source_manifest_sha256': sha(OLD / 'manifest.json'),
        'development_ids': original['development_ids'], 'units': original['units']})
    new(HERE / 'schedule.json', {'assignment': 'manifest round robin; rotating six-version order',
                               'rows': schedule_for(list(original['units']))})
    for filename in ('labels.json', 'old_v3_summary.json', 'old_v3_choices.json'):
        copy_new(OLD / 'offline' / filename, HERE / 'offline' / filename)
    # Synthetic service control, not a chart and not an edited benchmark asset.
    from PIL import Image
    controls = HERE / 'controls'
    controls.mkdir(exist_ok=False)
    Image.new('RGB', (128, 128), (235, 235, 235)).save(controls / 'blank.png')
    new(HERE / 'PREPARATION.json', {
        'source_manifest': str(OLD / 'manifest.json'), 'source_manifest_sha256': sha(OLD / 'manifest.json'),
        'source_files': {str(p.relative_to(HERE)): sha(p) for p in HERE.glob('prompts_*.py')},
        'n_tasks': 140, 'n_records': sum(u['record_count'] for u in original['units'].values()),
        'n_configuration_units': 840, 'normal_requests': 2240, 'control_requests': 4,
        'fresh_results': True, 'offline_directory_not_uploaded': True})
    print('Prepared 140 exact inputs, 840 disjoint units; historical scores remain offline.')


if __name__ == '__main__':
    main()
