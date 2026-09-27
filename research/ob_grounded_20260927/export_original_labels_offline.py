"""Post-freeze, read-only original-label alignment. Never imported by run.py.

This does not submit actions or invoke the original scorer. It aligns public
option labels to released expected_action_id/role fields only when the option
projection agrees exactly. Unsupported records remain unscored.
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def align(options, public_options):
    if not options or [o['label'] for o in options] != public_options:
        return {'supported': False, 'reason': 'released_option_projection_does_not_match_frozen_public_options'}
    if len(set(public_options)) != len(public_options):
        return {'supported': False, 'reason': 'duplicate_public_labels_ambiguous'}
    def role(o):
        original = o.get('role', o.get('review_role', ''))
        return {'misleading': 'misleading_trap', 'irrelevant': 'neutral_or_irrelevant'}.get(original, original)
    options = [{**o, 'alignment_role': role(o)} for o in options]
    correct = [o for o in options if o['alignment_role'] == 'correct']
    if len(correct) != 1:
        return {'supported': False, 'reason': 'no_unique_original_correct_action'}
    return {'supported': True, 'original_correct_label': correct[0]['label'], 'options': options,
            'meaning': 'Original-label alignment only, not business submission or new human review.'}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    freeze = HERE / 'FREEZE.json'
    if not freeze.exists():
        raise RuntimeError('Only run after candidate is frozen; never use labels to tune it')
    frozen = read(freeze)
    for name, expected_hash in frozen['runtime_hashes'].items():
        if sha(HERE / name) != expected_hash:
            raise ValueError('Frozen runtime identity changed: ' + name)
    manifest = read(HERE / 'manifest.json')
    sys.path.insert(0, str(args.project_root))
    from web_agent_benchmark.public_benchmark import public_benchmark_shell_app as shell
    from web_agent_benchmark.business_shell import business_shell_app as business
    from web_agent_benchmark.environment_energy_shell import environment_shell_app as environment
    from web_agent_benchmark.health_shell import health_shell_app as health
    modules = {'business47': business, 'public39': shell, 'environment35': environment, 'health19': health}
    split = args.project_root / 'web_agent_benchmark/benchmark_v2_open/splits/official140'
    raw = {}
    sources = {}
    for domain in ('business47', 'environment35', 'health19', 'public39'):
        file = split / (domain + '_tasks.jsonl')
        sources[str(file)] = sha(file)
        for line in file.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            task = json.loads(line)
            slug = task.get('official_slug')
            if not slug or slug in raw:
                raise ValueError('Missing/duplicate official slug; do not guess ordering')
            raw[slug] = (task, str(file))
    result = {}
    for key, unit in manifest['units'].items():
        if unit['panel'] != 'full':
            continue
        data = HERE / 'data' / key
        if sha(data / 'input.json') != unit['input_sha256'] or sha(data / unit['image']) != unit['image_sha256']:
            raise ValueError('Frozen public input identity changed: ' + key)
        public = read(data / 'input.json')
        source = raw.get(unit['slug'])
        if source is None:
            result[key] = {'supported': False, 'reason': 'original_slug_not_found'}
            continue
        task, path = source
        record = {'task': task, 'source_group': str(task.get('official_source_group') or 'public39_clean_tasks'),
                  'override': task.get('official_shell_override') or {}, 'source_record': {'task': task}}
        module = modules[unit['domain']]
        options = module.action_options(task if unit['domain'] == 'business47' else record)
        original_chart = args.project_root / task['chart_asset']['figure_path']
        original_chart_hash = sha(original_chart)
        if original_chart_hash != unit['image_sha256']:
            result[key] = {'supported': False, 'reason': 'original_chart_identity_mismatch',
                           'source_path': path, 'original_chart_sha256': original_chart_hash}
            continue
        result[key] = {**align(options, public['options']), 'source_path': path,
                       'source_task_id': task.get('task_id'), 'official_slug': unit['slug'],
                       'source_module': module.__name__, 'original_chart_sha256': original_chart_hash}
    projection_sources = {str(Path(inspect.getsourcefile(fn))): sha(Path(inspect.getsourcefile(fn)))
                          for fn in (shell.action_options, shell.legacy_public.action_options,
                                     business.action_options, environment.action_options, health.action_options)}
    payload = {'freeze_sha256': sha(freeze), 'source_file_hashes': sources,
               'original_action_options_module_hashes': projection_sources,
               'alignment_version': 'domain_native_options_v2',
               'original_labels_unchanged': True, 'human_review_performed': False,
               'business_submissions': 0, 'model_calls': 0, 'tasks': result}
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(payload, out, ensure_ascii=False, indent=2)
    print(json.dumps({'tasks': len(result), 'aligned': sum(x['supported'] for x in result.values()),
                      'unsupported': {k: v['reason'] for k, v in result.items() if not v['supported']},
                      'output_sha256': sha(args.output), 'model_calls': 0}))

if __name__ == '__main__':
    main()
