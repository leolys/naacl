"""Frozen two-implementation panel. Register all units before downstream calls."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from dependencies import HERE, PREVIOUS, DEPENDENCIES, transport, downstream, read, dump, sha, check_dependencies
from registration_prompts import REGISTER_PROMPTS
from registration_records import SCHEMAS, validate, assemble, action_relations


def check_inputs(project, cases):
    inputs = PREVIOUS / 'inputs'
    manifest = read(inputs / 'manifest.json')
    if list(manifest['cases']) != cases:
        raise ValueError('Fixed input panel changed')
    for case in cases:
        entry = manifest['cases'][case]
        for name, expected in entry['files'].items():
            if sha(inputs / case / name) != expected:
                raise ValueError('Input identity changed: ' + case + '/' + name)
        for path, expected in entry['source_files'].items():
            if sha(project / path) != expected:
                raise ValueError('Original source changed: ' + path)
    return inputs, manifest


def call(api, folder, stage, variant, context, image):
    system = REGISTER_PROMPTS[variant] if stage == 'register' else downstream.PROMPTS[stage]
    raw = api.call(folder, system, context, image, SCHEMAS[stage], stage)
    dump(folder / 'raw.json', {'content': raw})
    parsed = json.loads(raw)
    validate(stage, parsed, context)
    dump(folder / 'accepted.json', parsed)
    return parsed


def register_unit(variant, case, inputs, output, api):
    source = inputs / case
    context, initial = read(source / 'context.json'), read(source / 'initial.json')
    folder = output / variant / case
    folder.mkdir(parents=True)
    for name in ('context.json', 'initial.json', 'chart.png'):
        shutil.copyfile(source / name, folder / name)
    result = {'variant': variant, 'case': case, 'status': 'registering',
              'registration': None, 'action_relations': [], 'expansions': [],
              'candidate_set': None, 'verification': None, 'submitted': False,
              'actor_status': 'not_run_candidate_diagnostic', 'new_natural_prefix': False}
    try:
        context['existing_action_labels'] = list(dict.fromkeys(c['C']['option_label'] for c in initial['chains']))
        result['registration'] = call(api, folder / 'register', 'register', variant, context, folder / 'chart.png')
        result['action_relations'] = action_relations(initial, result['registration'])
        result['status'] = 'registered_pending_downstream'
    except transport.LimitStop:
        result['status'] = 'stopped_global_budget_or_transport'
        raise
    except Exception as exc:
        result.update(status='registration_interface_failed_no_retry',
                      error={'type': type(exc).__name__, 'message': str(exc)})
    finally:
        # Save registered candidates before any expansion can run, including failures.
        dump(folder / 'result.json', result)
    return result


def finish_unit(result, output, api):
    variant, case = result['variant'], result['case']
    folder = output / variant / case
    context, initial = read(folder / 'context.json'), read(folder / 'initial.json')
    image = folder / 'chart.png'
    try:
        for index, candidate in enumerate(result['registration']['candidates']):
            try:
                data = call(api, folder / ('expand_%02d' % index), 'expand', variant,
                            {**copy.deepcopy(context), 'proposal': copy.deepcopy(candidate)}, image)
                result['expansions'].append({'status': 'accepted', 'data': data})
            except transport.LimitStop:
                raise
            except Exception as exc:
                result['expansions'].append({'status': 'interface_failed_no_retry',
                                            'error': {'type': type(exc).__name__, 'message': str(exc)}})
            dump(folder / 'result.json', result)
        result['candidate_set'] = assemble(initial, result['registration'], result['expansions'])
        dump(folder / 'candidate_set.json', result['candidate_set'])
        if result['candidate_set']['chains']:
            result['verification'] = call(api, folder / 'verify', 'verify', variant,
                                          {**copy.deepcopy(context), 'chains': result['candidate_set']['chains']}, image)
        result['status'] = 'completed_candidate_diagnostic'
    except transport.LimitStop:
        result['status'] = 'stopped_global_budget_or_transport'
        raise
    except Exception as exc:
        result.update(status='downstream_interface_failed_no_retry',
                      error={'type': type(exc).__name__, 'message': str(exc)})
    finally:
        dump(folder / 'result.json', result)
    return result


def collect(output, variants, cases):
    return [read(output / v / c / 'result.json') for v in variants for c in cases
            if (output / v / c / 'result.json').exists()]


def execute_panel(config, inputs, output, api):
    summary = {'status': 'running', 'results': [], 'scope': config['scope'],
               'ordinary_reread_arm': False, 'new_natural_prefixes': 0,
               'browser_operations': 0, 'paid_api_requests': 0}
    try:
        for variant in config['variants']:
            for case in config['cases']:
                print('REGISTER ' + variant + '/' + case, flush=True)
                result = register_unit(variant, case, inputs, output, api)
                print(json.dumps({'variant': variant, 'case': case, 'status': result['status'],
                                  'candidates': len((result['registration'] or {}).get('candidates', []))}), flush=True)
                summary['results'] = collect(output, config['variants'], config['cases'])
                dump(output / 'summary.json', summary)
        for result in summary['results']:
            if result['status'] == 'registered_pending_downstream':
                print('EXPAND_VERIFY ' + result['variant'] + '/' + result['case'], flush=True)
                finish_unit(result, output, api)
                dump(output / 'summary.json', summary)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        summary['results'] = collect(output, config['variants'], config['cases'])
        summary['unstarted_units'] = [v + '/' + c for v in config['variants'] for c in config['cases']
                                     if not (output / v / c / 'result.json').exists()]
        dump(output / 'summary.json', summary)
    return summary


def preflight(api, output):
    health = api.http.get('http://127.0.0.1:8058/health', timeout=10, allow_redirects=False)
    models = api.http.get('http://127.0.0.1:8058/v1/models', timeout=10, allow_redirects=False).json()
    probes = {}
    commands = {'gpu': ['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu', '--format=csv,noheader'],
                'processes': ['ps', '-p', '316818,319282,282313', '-o', 'pid,lstart,args']}
    for label, command in commands.items():
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
        probes[label] = {'returncode': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr}
    dump(output / 'service_preflight.json', {'time_utc': datetime.now(timezone.utc).isoformat(),
                                            'health_http': health.status_code, 'models': models, 'probes': probes})
    if health.status_code != 200 or api.config['model'] not in [m['id'] for m in models['data']]:
        raise ValueError('Existing authorized model service unavailable; no fallback')
    if 'GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7' not in probes['gpu']['stdout']:
        raise ValueError('Expected user-authorized GPU not found; no new resource assignment')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = read(HERE / 'config.json')
    if (config['variants'] != ['registration', 'coverage'] or config['max_request_attempts'] != 40 or
            config['max_browser_operations'] != 0 or config['concurrency'] != 1 or config['paid_api_allowed']):
        raise ValueError('Fixed bounds or variants changed')
    check_dependencies(args.project)
    inputs, manifest = check_inputs(args.project, config['cases'])
    if args.output.exists():
        raise FileExistsError('Refusing overwrite or quality rerun')
    with (HERE / 'LIVE_LOCK.json').open('x', encoding='utf-8') as stream:
        json.dump({'output': str(args.output), 'fresh_request_cap': 40}, stream)
    args.output.mkdir()
    ledger = transport.Ledger(args.output, config)
    ledger.save()
    api = transport.LocalAPI(config, ledger)
    sources = [HERE / name for name in ('run_panel.py', 'dependencies.py', 'registration_records.py',
                                       'registration_prompts.py', 'config.json', 'PROTOCOL.md')] + DEPENDENCIES
    snapshot = {}
    for source in sources:
        relative = source.relative_to(args.project)
        target = args.output / 'runtime_source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        snapshot[relative.as_posix()] = sha(source)
    dump(args.output / 'source_hashes.json', snapshot)
    dump(args.output / 'input_manifest.json', manifest)
    dump(args.output / 'config.json', config)
    preflight(api, args.output)
    try:
        execute_panel(config, inputs, args.output, api)
    finally:
        summary = read(args.output / 'summary.json')
        summary.update(request_attempts=ledger.data['request_attempts'],
                       source_preserved={p: sha(args.project / p) == h for p, h in snapshot.items()})
        dump(args.output / 'summary.json', summary)
        print(json.dumps({k: v for k, v in summary.items() if k != 'results'}), flush=True)


if __name__ == '__main__':
    main()
