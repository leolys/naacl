"""One frozen, serial panel using existing local service and immutable old inputs."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lean_prompts import PROMPTS
from records import SCHEMAS, validate, assemble
from prepare_inputs import read, dump, sha

BASE_DIR = HERE.parent/'alternative_conclusion_20260926'
spec = importlib.util.spec_from_file_location('proposal_transport_base', BASE_DIR/'runner.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def check_inputs(project, inputs, manifest, cases):
    if set(manifest['cases']) != set(cases):
        raise ValueError('Panel changed')
    for case in cases:
        entry = manifest['cases'][case]
        for name, expected in entry['files'].items():
            if sha(inputs/case/name) != expected:
                raise ValueError('Prepared payload changed: '+case+'/'+name)
        for name, expected in entry['source_files'].items():
            if sha(project/name) != expected:
                raise ValueError('Immutable source changed: '+name)


def call(api, folder, stage, context, image):
    raw = api.call(folder, PROMPTS[stage], context, image, SCHEMAS[stage], stage)
    dump(folder/'raw.json', {'content': raw})
    parsed = json.loads(raw)
    validate(stage, parsed, context)
    dump(folder/'accepted.json', parsed)
    return parsed


def run_case(case, inputs, output, api):
    source = inputs/case
    context, initial = read(source/'context.json'), read(source/'initial.json')
    out = output/case
    out.mkdir()
    for name in ('context.json', 'initial.json', 'chart.png'):
        shutil.copyfile(source/name, out/name)
    image = out/'chart.png'
    result = {'case':case, 'status':'started', 'proposals':None, 'expansions':[],
              'candidate_set':None, 'verification':None, 'actor_status':'not_run_candidate_diagnostic',
              'submitted':False, 'new_natural_prefix':False}
    try:
        proposal_context = {**copy.deepcopy(context), 'existing_action_labels': list(dict.fromkeys(c['C']['option_label'] for c in initial['chains']))}
        proposals = call(api, out/'propose', 'propose', proposal_context, image)
        result['proposals'] = proposals
        dump(out/'result.json', result)  # Persist proposals before any expansion.
        for index, proposal in enumerate(proposals['proposals']):
            folder = out/('expand_%02d' % index)
            try:
                data = call(api, folder, 'expand', {**copy.deepcopy(context), 'proposal':copy.deepcopy(proposal)}, image)
                result['expansions'].append({'status':'accepted','data':data})
            except base.LimitStop:
                raise
            except Exception as exc:
                result['expansions'].append({'status':'interface_failed_no_retry','error':{'type':type(exc).__name__,'message':str(exc)}})
            dump(out/'result.json', result)
        candidates = assemble(initial, proposals, result['expansions'])
        result['candidate_set'] = candidates
        dump(out/'candidate_set.json', candidates)
        # Check every complete chain, including duplicates/changed candidates. Never silently discard.
        if candidates['chains']:
            result['verification'] = call(api, out/'verify', 'verify', {**copy.deepcopy(context), 'chains':candidates['chains']}, image)
        else:
            result['verification_status'] = 'not_run_no_complete_chains'
        result['status'] = 'completed_candidate_diagnostic'
    except base.LimitStop:
        result['status'] = 'stopped_global_budget_or_transport'
        raise
    except Exception as exc:
        result.update(status='interface_failed_no_retry', error={'type':type(exc).__name__,'message':str(exc)})
    finally:
        dump(out/'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config, inputs = read(HERE/'config.json'), HERE/'inputs'
    manifest = read(inputs/'manifest.json')
    if config['max_request_attempts'] != 24 or config['max_browser_operations'] != 0 or config['concurrency'] != 1:
        raise ValueError('Frozen diagnostic bounds changed')
    check_inputs(args.project, inputs, manifest, config['cases'])
    # Verify reused transport against its prior runtime snapshot; never import changed dependencies unnoticed.
    old_sources = read(HERE.parent/'conclusion_search_20260926/run_joint_001/source_hashes.json')
    dependencies = [BASE_DIR/name for name in ('runner.py','prompts.py','schemas.py')]
    for path in dependencies:
        if sha(path) != old_sources[str(path)]:
            raise ValueError('Frozen transport dependency changed')
    if args.output.exists():
        raise FileExistsError('No replacement or quality rerun')
    with (HERE/'LIVE_LOCK.json').open('x', encoding='utf-8') as stream:
        json.dump({'output':str(args.output),'scope':'fresh 24-attempt user-authorized panel'},stream)
    args.output.mkdir()
    ledger = base.Ledger(args.output, config)
    ledger.save()
    api = base.LocalAPI(config, ledger)
    snapshot = {}
    for source in [HERE/name for name in ('run.py','lean_prompts.py','records.py','prepare_inputs.py','config.json','PROTOCOL.md')]+dependencies:
        target = args.output/'runtime_source'/source.relative_to(args.project)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        snapshot[source.relative_to(args.project).as_posix()] = sha(source)
    dump(args.output/'source_hashes.json', snapshot)
    dump(args.output/'config.json', config)
    dump(args.output/'input_manifest.json', manifest)
    health = api.http.get('http://127.0.0.1:8058/health',timeout=10,allow_redirects=False)
    models = api.http.get('http://127.0.0.1:8058/v1/models',timeout=10,allow_redirects=False).json()
    dump(args.output/'service_preflight.json',{'health_http':health.status_code,'models':models})
    if health.status_code != 200 or config['model'] not in [m['id'] for m in models['data']]:
        raise ValueError('Existing authorized service unavailable; no fallback')
    summary = {'status':'running','results':[], 'scope':'candidate_generation_not_task_recovery',
               'previous_panel_budget_reused':False,'browser_operations':0,'paid_api_requests':0}
    try:
        for case in config['cases']:
            print('START '+case,flush=True)
            result = run_case(case,inputs,args.output,api)
            summary['results'].append(result)
            dump(args.output/'summary.json',summary)
            print(json.dumps({'case':case,'status':result['status'],'proposals':len((result['proposals'] or {}).get('proposals',[])),
                              'expanded':sum(e.get('data',{}).get('outcome')=='expanded' for e in result['expansions'])}),flush=True)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped',error={'type':type(exc).__name__,'message':str(exc)})
        raise
    finally:
        summary.update(request_attempts=ledger.data['request_attempts'],
                       unstarted_cases=[case for case in config['cases'] if not (args.output/case/'result.json').exists()],
                       source_preserved={path:sha(args.project/path)==expected for path,expected in snapshot.items()})
        dump(args.output/'summary.json',summary)
        print(json.dumps({k:v for k,v in summary.items() if k!='results'}),flush=True)


if __name__ == '__main__':
    main()
