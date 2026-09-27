"""Bounded O/B-only verification and fresh decisions; old artifacts read-only."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from bindings import HERE, PROJECT, SOURCE, DEPENDENCIES, read, dump, sha, check_dependencies, transport
from prompts_ob import VERIFY, DECIDE
from records_ob import project, decision_input, SCHEMAS, validate

SOURCE_FILES = ('context.json', 'chart.png', 'candidate_set.json', 'registration.json', 'initial.json', 'result.json')


def manifest(config, source=SOURCE):
    frozen = read(source / 'input_manifest.json')
    units = {}
    for v in config['variants']:
        for c in config['cases']:
            key = v + '/' + c
            folder = source / key
            for name in ('context.json', 'chart.png', 'initial.json'):
                if sha(folder / name) != frozen['units'][key]['files'][name]:
                    raise ValueError('Public input hash drift')
            result = read(folder / 'result.json')
            candidate_set = read(folder / 'candidate_set.json')
            if candidate_set != result['candidate_set'] or any(x['status'] != 'accepted' for x in result['expansions']):
                raise ValueError('Incomplete or inconsistent source expansion')
            units[key] = {'files': {n: sha(folder / n) for n in SOURCE_FILES},
                          'records': len(candidate_set['chains']),
                          'observations': sum(len(x['O']) for x in candidate_set['chains'])}
    return {'source': str(source.relative_to(PROJECT)), 'units': units,
            'selection': 'all eight frozen units, including zero upstream candidates, without outcome filtering'}


def call_stage(api, folder, stage, context, image):
    system = VERIFY if stage == 'ob_verify' else DECIDE
    raw = api.call(folder, system, context, image, SCHEMAS[stage], stage)
    dump(folder / 'raw.json', {'content': raw})
    data = validate(stage, json.loads(raw), context)
    dump(folder / 'accepted.json', data)
    return data


def execute(config, source, output, api):
    summary = {'status': 'running', 'scope': config['scope'], 'results': [],
               'submitted': False, 'browser_operations': 0, 'paid_api_requests': 0,
               'candidate_generation_calls': 0, 'persistent_rules_generated': 0}
    dump(output / 'summary.json', summary)
    try:
        # Prepare all fixed units before any model calls.
        for v in config['variants']:
            for c in config['cases']:
                folder = output / v / c
                folder.mkdir(parents=True)
                for name in SOURCE_FILES:
                    shutil.copyfile(source / v / c / name, folder / ('source_' + name))
                original = read(folder / 'source_candidate_set.json')
                projected = project(read(folder / 'source_context.json'), original)
                dump(folder / 'projected.json', projected)
                dump(folder / 'provenance_map.json', [
                    {'id': new['id'], 'source_id': old['id'], 'source_C': old['C']}
                    for new, old in zip(projected['records'], original['chains'])])
                r = {'variant': v, 'case': c, 'status': 'prepared', 'verification': None,
                     'decision': None, 'submitted': False, 'source_C_sent_as_field': False}
                summary['results'].append(r)
                dump(folder / 'result.json', r)
        dump(output / 'summary.json', summary)
        # Fixed unit order; one review and one fresh selection per unit.
        for r in summary['results']:
            folder = output / r['variant'] / r['case']
            projected = read(folder / 'projected.json')
            stage = 'ob_verify'
            try:
                print('VERIFY ' + r['variant'] + '/' + r['case'], flush=True)
                r['verification'] = call_stage(api, folder / stage, stage, projected, folder / 'source_chart.png')
                r['status'] = 'verified_pending_decision'
                dump(folder / 'result.json', r)
                dump(output / 'summary.json', summary)
                stage = 'decide'
                print('DECIDE ' + r['variant'] + '/' + r['case'], flush=True)
                context = decision_input(projected, r['verification'])
                r['decision'] = call_stage(api, folder / stage, stage, context, folder / 'source_chart.png')
                r['status'] = 'completed_ob_diagnostic'
                print(json.dumps({'unit': r['variant'] + '/' + r['case'], 'decision': r['decision']}), flush=True)
            except transport.LimitStop:
                r.update(status='stopped_transport_or_budget', stopped_stage=stage)
                raise
            except Exception as exc:
                r.update(status=stage + '_interface_failed_no_quality_retry',
                         error={'type': type(exc).__name__, 'message': str(exc)})
            finally:
                dump(folder / 'result.json', r)
                dump(output / 'summary.json', summary)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        dump(output / 'summary.json', summary)
    return summary


def preflight(api, output):
    health = api.http.get('http://127.0.0.1:8058/health', timeout=10, allow_redirects=False)
    models = api.http.get('http://127.0.0.1:8058/v1/models', timeout=10, allow_redirects=False).json()
    probes = {}
    for k, cmd in {
        'gpu': ['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu', '--format=csv,noheader'],
        'processes': ['ps', '-p', '316818,319282,282313', '-o', 'pid,lstart,args']
    }.items():
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        probes[k] = {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    dump(output / 'service_preflight.json', {'utc': datetime.now(timezone.utc).isoformat(),
         'health_http': health.status_code, 'models': models, 'probes': probes})
    if health.status_code != 200 or api.config['model'] not in [m['id'] for m in models['data']]:
        raise ValueError('Existing authorized service unavailable; no fallback')
    if 'GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7' not in probes['gpu']['stdout']:
        raise ValueError('GPU identity changed')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    config = read(HERE / 'config.json')
    if config['max_request_attempts'] != 20 or config['max_browser_operations'] != 0 or config['paid_api_allowed'] or config['concurrency'] != 1:
        raise ValueError('Resource bounds changed')
    check_dependencies()
    inputs = manifest(config)
    if args.output.exists():
        raise FileExistsError('No overwrite')
    with (HERE / 'LIVE_LOCK.json').open('x', encoding='utf-8') as f:
        json.dump({'output': str(args.output), 'cap': 20, 'scope': config['scope']}, f)
    args.output.mkdir()
    dump(args.output / 'config.json', config)
    dump(args.output / 'input_manifest.json', inputs)
    sources = [HERE / n for n in ('run_panel.py', 'bindings.py', 'prompts_ob.py', 'records_ob.py', 'config.json', 'PROTOCOL.md')] + DEPENDENCIES
    hashes = {}
    for file in sources:
        rel = file.relative_to(PROJECT)
        target = args.output / 'runtime_source' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        hashes[rel.as_posix()] = sha(file)
    dump(args.output / 'source_hashes.json', hashes)
    ledger = transport.Ledger(args.output, config)
    ledger.save()
    api = transport.LocalAPI(config, ledger)
    dump(args.output / 'summary.json', {'status': 'preflight', 'results': []})
    try:
        preflight(api, args.output)
        execute(config, SOURCE, args.output, api)
    except Exception as exc:
        summary = read(args.output / 'summary.json')
        if summary['status'] != 'stopped':
            summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
            dump(args.output / 'summary.json', summary)
        raise
    finally:
        summary = read(args.output / 'summary.json')
        summary.update(request_attempts=ledger.data['request_attempts'],
                       source_preserved={k: sha(PROJECT / k) == h for k, h in hashes.items()},
                       original_inputs_preserved=manifest(config) == inputs)
        dump(args.output / 'summary.json', summary)
        print(json.dumps({k: v for k, v in summary.items() if k != 'results'}), flush=True)


if __name__ == '__main__':
    main()
