"""Expand all frozen candidates once, then verify all units without feedback."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from bindings import HERE, PROJECT, PREVIOUS, SOURCE_RUN, DEPENDENCIES, read, dump, sha, check_dependencies, transport, records, downstream
from flat_prompt import EXPAND
from flat_records import SCHEMA, EMPTY, validate, adapt, action_relation

FILES = {'context.json': 'context.json', 'initial.json': 'initial.json', 'chart.png': 'chart.png',
         'register/accepted.json': 'registration.json', 'result.json': 'previous_result.json'}


def input_manifest(config, source_run=SOURCE_RUN):
    upstream = read(source_run / 'input_manifest.json')
    units, count = {}, 0
    for variant in config['variants']:
        for case in config['cases']:
            folder = source_run / variant / case
            for name in ('context.json', 'initial.json', 'chart.png'):
                if sha(folder / name) != upstream['cases'][case]['files'][name]:
                    raise ValueError('Frozen public input changed: ' + str(folder / name))
            registered, result = read(folder / 'register/accepted.json'), read(folder / 'result.json')
            if registered != result['registration'] or result['status'] != 'completed_candidate_diagnostic':
                raise ValueError('Candidate source inconsistent or incomplete')
            count += len(registered['candidates'])
            units[variant + '/' + case] = {'files': {name: sha(folder / name) for name in FILES},
                                           'candidate_count': len(registered['candidates'])}
    if count != config['expected_source_candidates']:
        raise ValueError('Frozen candidate population changed')
    return {'source_run': source_run.relative_to(PROJECT).as_posix(), 'units': units,
            'candidate_count': count, 'selection': 'all candidates from all 8 prior units, including errors; no gold-based filtering'}


def expand_unit(variant, case, source_run, output, api):
    source, folder = source_run / variant / case, output / variant / case
    folder.mkdir(parents=True)
    for source_name, target_name in FILES.items():
        shutil.copyfile(source / source_name, folder / target_name)
    context = read(folder / 'context.json')
    registered = read(folder / 'registration.json')
    initial = read(folder / 'initial.json')
    result = {'variant': variant, 'case': case, 'status': 'expanding', 'registration': registered,
              'expansions': [], 'candidate_set': {'chains': copy.deepcopy(initial['chains'])},
              'verification': None, 'submitted': False, 'actor_status': 'not_run',
              'source_scope': 'fixed_previous_candidates_not_regenerated'}
    dump(folder / 'result.json', result)
    try:
        for index, candidate in enumerate(registered['candidates']):
            destination = folder / ('expand_%02d' % index)
            entry = {'index': index, 'candidate_id': candidate['id'], 'status': 'started',
                     'data': None, 'empty_record': None, 'action_relation': None, 'adapted_chain': None}
            try:
                raw = api.call(destination, EXPAND, {**copy.deepcopy(context), 'candidate': copy.deepcopy(candidate)},
                               folder / 'chart.png', SCHEMA, 'expand')
                dump(destination / 'raw.json', {'content': raw})
                data = validate(json.loads(raw))
                dump(destination / 'accepted.json', data)
                chain = adapt(data, 'conditional_%02d' % index, context['options'])
                entry.update(status='accepted', data=data, empty_record=(data == EMPTY),
                             action_relation=action_relation(candidate, data), adapted_chain=chain)
                if chain is not None:
                    if chain['id'] in [c['id'] for c in result['candidate_set']['chains']]:
                        raise ValueError('Generated metadata ID collision')
                    result['candidate_set']['chains'].append(chain)
            except transport.LimitStop:
                entry['status'] = 'stopped_global_budget_or_transport'
                result['expansions'].append(entry)
                dump(folder / 'result.json', result)
                raise
            except Exception as exc:
                entry.update(status='interface_failed_no_retry', error={'type': type(exc).__name__, 'message': str(exc)})
            result['expansions'].append(entry)
            dump(folder / 'result.json', result)
        result['status'] = 'expanded_pending_verify'
    except transport.LimitStop:
        result['status'] = 'stopped_global_budget_or_transport'
        raise
    finally:
        dump(folder / 'candidate_set.json', result['candidate_set'])
        dump(folder / 'result.json', result)
    return result


def verify_unit(result, output, api):
    folder = output / result['variant'] / result['case']
    context = {**read(folder / 'context.json'), 'chains': result['candidate_set']['chains']}
    try:
        raw = api.call(folder / 'verify', downstream.VERIFY, context, folder / 'chart.png', records.SCHEMAS['verify'], 'verify')
        dump(folder / 'verify/raw.json', {'content': raw})
        data = json.loads(raw)
        records.validate('verify', data, context)
        dump(folder / 'verify/accepted.json', data)
        result['verification'], result['status'] = data, 'completed_candidate_diagnostic'
    except transport.LimitStop:
        result['status'] = 'stopped_global_budget_or_transport'
        raise
    except Exception as exc:
        result.update(status='verification_interface_failed_no_retry', error={'type': type(exc).__name__, 'message': str(exc)})
    finally:
        dump(folder / 'result.json', result)


def collect(config, output):
    return [read(output / v / c / 'result.json') for v in config['variants'] for c in config['cases']
            if (output / v / c / 'result.json').exists()]


def execute(config, source_run, output, api):
    summary = {'status': 'running', 'results': [], 'scope': config['scope'],
               'candidate_generation_calls': 0, 'ordinary_reread_arm': False,
               'browser_operations': 0, 'paid_api_requests': 0, 'new_natural_prefixes': 0}
    try:
        for variant in config['variants']:
            for case in config['cases']:
                print('EXPAND ' + variant + '/' + case, flush=True)
                result = expand_unit(variant, case, source_run, output, api)
                summary['results'] = collect(config, output)
                dump(output / 'summary.json', summary)
                print(json.dumps({'variant': variant, 'case': case,
                                  'nonempty': sum(e['empty_record'] is False for e in result['expansions']),
                                  'exact_action': sum((e['action_relation'] or {}).get('exact_match', False) for e in result['expansions'])}), flush=True)
        for result in summary['results']:
            print('VERIFY ' + result['variant'] + '/' + result['case'], flush=True)
            verify_unit(result, output, api)
            dump(output / 'summary.json', summary)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        summary['results'] = collect(config, output)
        dump(output / 'summary.json', summary)
    return summary


def preflight(api, output):
    health = api.http.get('http://127.0.0.1:8058/health', timeout=10, allow_redirects=False)
    models = api.http.get('http://127.0.0.1:8058/v1/models', timeout=10, allow_redirects=False).json()
    commands = {'gpu': ['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu', '--format=csv,noheader'],
                'processes': ['ps', '-p', '316818,319282,282313', '-o', 'pid,lstart,args']}
    probes = {}
    for key, cmd in commands.items():
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        probes[key] = {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    dump(output / 'service_preflight.json', {'utc': datetime.now(timezone.utc).isoformat(),
                                            'health_http': health.status_code, 'models': models, 'probes': probes})
    if health.status_code != 200 or api.config['model'] not in [m['id'] for m in models['data']]:
        raise ValueError('Authorized existing service unavailable; no fallback')
    if 'GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7' not in probes['gpu']['stdout']:
        raise ValueError('Authorized GPU not found')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.project.resolve() != PROJECT.resolve():
        raise ValueError('Unexpected project root')
    config = read(HERE / 'config.json')
    if config['max_request_attempts'] != 28 or config['max_browser_operations'] != 0 or config['concurrency'] != 1 or config['paid_api_allowed']:
        raise ValueError('Budget/resource bounds changed')
    check_dependencies()
    manifest = input_manifest(config)
    if args.output.exists():
        raise FileExistsError('No overwrite or quality rerun')
    with (HERE / 'LIVE_LOCK.json').open('x', encoding='utf-8') as f:
        json.dump({'output': str(args.output), 'fresh_attempt_cap': 28}, f)
    args.output.mkdir()
    ledger = transport.Ledger(args.output, config); ledger.save()
    api = transport.LocalAPI(config, ledger)
    sources = [HERE / n for n in ('run_panel.py', 'bindings.py', 'flat_prompt.py', 'flat_records.py', 'config.json', 'PROTOCOL.md')] + DEPENDENCIES
    snapshot = {}
    for source in sources:
        rel = source.relative_to(PROJECT)
        target = args.output / 'runtime_source' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        snapshot[rel.as_posix()] = sha(source)
    dump(args.output / 'source_hashes.json', snapshot)
    dump(args.output / 'config.json', config)
    dump(args.output / 'input_manifest.json', manifest)
    # Read-only provenance: counterquestion prompts are NOT part of this round's model messages.
    shutil.copyfile(SOURCE_RUN / 'runtime_source/research/candidate_registration_20260926/registration_prompts.py',
                    args.output / 'upstream_counterquestion_prompts.py')
    preflight(api, args.output)
    try:
        execute(config, SOURCE_RUN, args.output, api)
    finally:
        summary = read(args.output / 'summary.json')
        summary.update(request_attempts=ledger.data['request_attempts'],
                       source_preserved={p: sha(PROJECT / p) == h for p, h in snapshot.items()},
                       original_inputs_preserved=input_manifest(config) == manifest)
        dump(args.output / 'summary.json', summary)
        print(json.dumps({k: v for k, v in summary.items() if k != 'results'}), flush=True)


if __name__ == '__main__':
    main()
