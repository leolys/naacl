"""Project only audited public content; preserve static task values without recursion."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def project_public(context):
    state = context['state']
    if 'task' in state:
        task = copy.deepcopy(state['task'])  # Includes all readonly business values.
    else:
        task = {'page_text': state['text']}  # Exact visible text, not current select flags/tokens.
    return {'goal': context['goal'], 'public_task': task, 'options': copy.deepcopy(context['options'])}


def prepare(project, output):
    root = project/'research/conclusion_search_20260926'
    if output.exists():
        raise FileExistsError('Do not overwrite prepared inputs')
    output.mkdir(parents=True)
    manifest = {'cases': {}, 'scope': 'public task + same complete chart; old chains are offline/shared verification inputs'}
    for case, arm in [('pub001_misleading', 'official140'), ('pub001_normal', 'clean140'), ('b002', None), ('pub013', None)]:
        if arm:
            src = root/'run_isolated_001'/arm
            checkpoint = src/'source_checkpoint.json'
            record = read(checkpoint)
            context = {'goal': 'Complete the current Public Affairs benchmark task in the browser and submit the form.',
                       'state': record['state'], 'options': [o['text'] for s in record['state']['elements']['selects']
                           if s['name']=='primary_action' for o in s['options'] if o['value'] and not o['disabled']]}
            image, initial = src/'public_chart_observation/chart.png', src/'shared_initial.json'
            source_files = [checkpoint, image, initial, src/'reuse_provenance.json']
            if sha(initial) != read(src/'reuse_provenance.json')['initial_sha256']:
                raise ValueError('Initial source drift')
            if sha(image) != sha(root/'run_chart_001'/arm/'public_chart_observation/chart.png'):
                raise ValueError('Image source drift')
        else:
            src = root/'run_transfer_001'/case
            source_context = src/'public_context.json'
            context = read(source_context)
            image, initial = src/'chart.png', src/'shared_initial/accepted.json'
            prepared = root/'transfer_inputs'/case
            old_manifest = read(prepared/'manifest.json')
            if sha(prepared/'public_context.json') != old_manifest['context_sha256'] or read(prepared/'public_context.json') != context:
                raise ValueError('Static public context changed')
            if sha(image) != old_manifest['png_sha256']:
                raise ValueError('Static image changed')
            source_files = [source_context, image, initial, prepared/'manifest.json', prepared/'public_context.json']
        folder = output/case
        public = project_public(context)
        dump(folder/'context.json', public)
        shutil.copyfile(image, folder/'chart.png')
        shutil.copyfile(initial, folder/'initial.json')
        manifest['cases'][case] = {'files': {name: sha(folder/name) for name in ('context.json','chart.png','initial.json')},
             'source_files': {p.relative_to(project).as_posix(): sha(p) for p in source_files},
             'public_projection': 'goal + exact state.task' if not arm else 'goal + exact state.text + public option labels',
             'no_new_prefix': True, 'image_crop_or_resize': False}
    dump(output/'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.project, args.output), ensure_ascii=False, indent=2))
