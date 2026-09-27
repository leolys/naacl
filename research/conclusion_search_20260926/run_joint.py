"""Final bounded candidate-only diagnostic: one conclusion-first joint search."""
import argparse
import copy
import importlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_isolated as isolated
search, base, additional = isolated.search, isolated.base, isolated.additional

JOINT = '''Counterquestion: could this complete chart support another concrete task
conclusion beyond the supplied represented action labels? Explore the conclusion
space, not whether an earlier O, B, or C is wrong. You are not given earlier
arguments to attack. Public option order does not indicate correctness.

Rather than being assigned an option to defend, choose for yourself any further
concrete conclusion motivated by a locatable visible cue. Starting from that
possible C, articulate its actual visible O and the conditional B under which
it follows. Deliver up to TWO complete O-B-C candidate records directly in this
response. This is candidate discovery, not selection of a winning interpretation.
The applicability of an explicitly stated reading remains for the next verifier;
do not substitute an applicability verdict for the candidate's conditional C.
An assumption still needs public/visual motivation: do not invent business rules,
marks or values, change the task objective, or assume C as its own bridge.

The represented labels are previous candidate conclusions, not correct answers
or required actions. Do not repeat one merely to fill a quota. If the conclusions
you can motivate are already represented, or no additional candidate can be
articulated, return an empty list. Do not force opposition or extra candidates.
Write complete candidates in chains, not only in notes. Notes briefly describe
coverage or a remaining limitation, not a promise to deliver a chain later.
Use IDs n1/n2. The structure is:
{"chains":[{"id":"n1","O":[{"location":"visible location","content":"literal observation"}],
"B":{"rule":"conditional bridge","conditions":["adopted reading and scope"]},
"C":{"claim":"concrete candidate","option_label":"exact public option"}}],
"notes":"coverage or limits"}.
An empty chains list is permitted. Do not use uncertainty as a replacement C.
'''


def joint_context(context, initial):
    return {'goal': copy.deepcopy(context['goal']), 'state': isolated.without_action_state(context['state']),
            'options': copy.deepcopy(context['options']),
            'existing_conclusions': list(dict.fromkeys(c['C']['option_label'] for c in initial['chains']))}


def case_inputs(case):
    parent = HERE / 'run_isolated_001' / case
    initial = search.read(parent / 'shared_initial.json')
    if base.digest(parent / 'shared_initial.json') != search.read(parent / 'reuse_provenance.json')['initial_sha256']:
        raise ValueError('Reused initial chain bytes differ from recorded provenance')
    if case in ('official140', 'clean140'):
        checkpoint = search.read(parent / 'source_checkpoint.json')
        context = base.public_context(checkpoint['state'], checkpoint['history'], checkpoint['pending'])
        image = parent / 'public_chart_observation/chart.png'
        reference = HERE / 'run_chart_001' / case / 'public_chart_observation/chart.png'
        if base.digest(image) != base.digest(reference):
            raise ValueError('Joint comparison must keep the previous complete chart')
    else:
        isolated.validate_derived_context(HERE / 'transfer_inputs' / case, HERE / 'run_transfer_001' / case)
        context, image = search.read(parent / 'public_context.json'), parent / 'chart.png'
        if base.digest(image) != base.digest(HERE / 'run_transfer_001' / case / 'chart.png'):
            raise ValueError('Final static payload image differs from validated source')
        if context != search.read(HERE / 'run_transfer_001' / case / 'public_context.json'):
            raise ValueError('Static public context changed')
    return context, initial, image


def run_case(case, out, api):
    context, initial, image = case_inputs(case)
    out.mkdir()
    base.dump(out / 'public_context.json', context)
    base.dump(out / 'shared_initial.json', initial)
    shutil.copyfile(image, out / 'chart.png')
    base.dump(out / 'reuse_provenance.json', {'source': str(image.parent), 'image_sha256': base.digest(image),
               'initial_sha256': base.digest(HERE/'run_isolated_001'/case/'shared_initial.json'),
               'new_natural_prefix': False, 'actor': 'not_run_candidate_only'})
    item = {'case': case, 'mode': 'static_public_task_transfer', 'initial': initial,
            'submitted': False, 'business_actions': 0, 'branches': {}}
    branch = {'status': 'started', 'stages': {}, 'submitted': False, 'actor_status': 'not_run_static_diagnostic'}
    item['branches']['joint_discovery'] = branch
    folder = out / 'joint_discovery'
    folder.mkdir()
    try:
        qcontext = joint_context(context, initial)
        schema = copy.deepcopy(base.SCHEMAS['initial'])
        schema['properties']['chains']['maxItems'] = 2
        raw = api.call(folder / 'discovery', JOINT + importlib.import_module('prompts').COMMON,
                       qcontext, image, schema, 'hypothesis')
        base.dump(folder / 'discovery/raw.json', {'content': raw})
        parsed = json.loads(raw)
        base.validate('initial', parsed, qcontext)
        if len(parsed['chains']) > 2:
            raise ValueError('Discovery exceeds two-candidate budget')
        base.dump(folder / 'discovery/accepted.json', parsed)
        new = copy.deepcopy(parsed['chains'])
        for chain in new:
            chain['id'] = 'joint_' + chain['id']
        branch['stages']['discovery'] = {'program_counterquestion': JOINT.splitlines()[0], 'response': parsed}
        branch['stages']['supplement'] = {'new_chains': new, 'source': 'single_joint_discovery_not_old_supplement'}
        base.dump(folder/'candidate_set.json', {'chains': copy.deepcopy(initial['chains']) + new,
                    'verification_status': 'not_run_candidate_only_diagnostic'})
        branch['verification_status'] = 'not_run_candidate_only_diagnostic'
        branch['new_action_labels'] = sorted({c['C']['option_label'] for c in new if c['C']['option_label'] is not None}
                                         - {c['C']['option_label'] for c in initial['chains']})
        branch['status'] = 'completed_static_only'
        item['status'] = 'completed_panel'
    except base.LimitStop:
        branch['status'] = 'stopped_by_global_limit_or_transport'
        raise
    except Exception as exc:
        branch.update(status='failed_no_quality_retry', error={'type': type(exc).__name__, 'message': str(exc)})
        item['status'] = 'failed_no_quality_retry'
    finally:
        base.dump(folder / 'result.json', branch)
        base.dump(out / 'result.json', item)
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    parent = HERE / 'run_isolated_001'
    if search.read(parent/'summary.json')['status'] != 'finished':
        raise ValueError('Wait for the fixed parent panel')
    inherited = search.read(parent/'ledger.json')
    if inherited.get('blocked_reason') or inherited['request_attempts'] + 8 > 100:
        raise ValueError('Need eight remaining attempts for four fixed generation calls including allowed retries')
    sources = search.read(parent/'source_hashes.json')
    for path, expected in sources.items():
        if base.digest(path) != expected:
            raise ValueError('Parent source changed: '+path)
    config, parent_config = search.read(HERE/'config.json'), search.read(parent/'config.json')
    for key in config:
        if key != 'strategies' and config[key] != parent_config[key]:
            raise ValueError('Fixed setting changed: '+key)
    for case in ('official140', 'clean140', 'b002', 'pub013'):
        case_inputs(case)
    if args.output.exists():
        raise FileExistsError('Preserve existing output')
    with (HERE/'LIVE_JOINT_LOCK.json').open('x', encoding='utf-8') as stream:
        json.dump({'output': str(args.output), 'parent': str(parent), 'scope': 'same_100_300_total'}, stream)
    args.output.mkdir()
    config.update(phase='joint_conclusion_discovery_candidate_only', strategies=['joint_discovery'])
    base.dump(args.output/'config.json', config)
    ledger = base.Ledger(args.output, config)
    ledger.data = copy.deepcopy(inherited)
    ledger.data['parent_ledger'] = str(parent/'ledger.json')
    ledger.save()
    starts = ledger.data['request_attempts']
    snapshots = {}
    for source in dict.fromkeys([HERE/'run_joint.py', HERE/'JOINT_ADDENDUM.md', HERE/'config.json']+[Path(p) for p in sources]):
        target = args.output/'runtime_source'/source.relative_to(args.project)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        snapshots[str(source)] = base.digest(source)
    base.dump(args.output/'source_hashes.json', snapshots)
    api = base.LocalAPI(config, ledger)
    if api.http.get('http://127.0.0.1:8058/health', timeout=10, allow_redirects=False).status_code != 200:
        raise ValueError('Existing service unavailable')
    summary = {'status': 'running', 'phase': config['phase'], 'results': [], 'new_natural_prefixes': 0, 'new_browser_operations': 0}
    try:
        for case in ('official140', 'clean140', 'b002', 'pub013'):
            print('START joint candidate-only '+case, flush=True)
            summary['results'].append(run_case(case, args.output/case, api))
            base.dump(args.output/'summary.json', summary)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        summary.update(request_attempts=ledger.data['request_attempts'], browser_operations=ledger.data['browser_operations'],
                       phase_request_attempts=ledger.data['request_attempts']-starts, phase_browser_operations=0,
                       source_preserved={p: base.digest(p)==sha for p, sha in snapshots.items()})
        base.dump(args.output/'summary.json', summary)
        print(json.dumps({k: v for k, v in summary.items() if k!='results'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
