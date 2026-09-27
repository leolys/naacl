"""V7: isolate candidate discovery from recorded action commitments, not task rules."""
import argparse
import copy
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_contract as contract
additional, search, base = contract.additional, contract.search, contract.base

ACTION_STATE_KEYS = frozenset(('selected', 'selected_text', 'current_selection', 'value', 'url'))


def without_action_state(value):
    if isinstance(value, dict):
        return {key: without_action_state(item) for key, item in value.items() if key not in ACTION_STATE_KEYS}
    if isinstance(value, list):
        return [without_action_state(item) for item in value]
    return copy.deepcopy(value)


def discovery_context(context):
    """Public page text/rules/options unchanged; no old candidate or action record."""
    result = {key: copy.deepcopy(context[key]) for key in ('goal', 'options', 'hypothesis_option', 'search_question')}
    result['state'] = without_action_state(context['state'])
    return result


def validate_derived_context(prepared, archived):
    manifest = search.read(prepared / 'manifest.json')
    if base.digest(prepared / 'public_context.json') != manifest['context_sha256']:
        raise ValueError('Prepared public context changed')
    if base.digest(prepared / 'chart.png') != manifest['png_sha256'] or base.digest(archived / 'chart.png') != manifest['png_sha256']:
        raise ValueError('Static image changed')
    original, derived = search.read(prepared / 'public_context.json'), search.read(archived / 'public_context.json')
    if original != derived:
        raise ValueError('Derived archive changed the public JSON object')
    return {'prepared_context_sha256': base.digest(prepared / 'public_context.json'),
            'archived_context_sha256': base.digest(archived / 'public_context.json'),
            'parsed_json_equal': True, 'png_sha256': manifest['png_sha256'],
            'serialization_note': 'Original manifest describes prepared bytes, not a reserialized archive.'}


class IsolatedAPI(contract.ContractAPI):
    def call(self, folder, system, context, image, schema, stage):
        if stage == 'hypothesis':
            context = discovery_context(context)
        return super().call(folder, system, context, image, schema, stage)


class IsolatedChartAPI(contract.ContractChartAPI):
    def call(self, folder, system, context, image, schema, stage):
        if stage == 'hypothesis':
            # Fetch and assert the identical chart before removing its ephemeral URL.
            image = self.chart_image(context, folder)
            return base.LocalAPI.call(self, folder, contract.contract_system(system, stage),
                                      discovery_context(context), image, schema, stage)
        return super().call(folder, system, context, image, schema, stage)


def static_case(case, output, api):
    archived = HERE / 'run_transfer_001' / case
    provenance = validate_derived_context(HERE / 'transfer_inputs' / case, archived)
    context, initial = search.read(archived / 'public_context.json'), search.read(archived / 'shared_initial/accepted.json')
    out = output / case
    out.mkdir()
    base.dump(out / 'public_context.json', context)
    base.dump(out / 'shared_initial.json', initial)
    provenance['initial_sha256'] = base.digest(archived / 'shared_initial/accepted.json')
    base.dump(out / 'reuse_provenance.json', provenance)
    shutil.copyfile(archived / 'chart.png', out / 'chart.png')
    item = {'case': case, 'mode': 'static_public_task_transfer', 'initial': initial,
            'submitted': False, 'business_actions': 0, 'branches': {}}
    branch = {'status': 'started', 'stages': {}, 'submitted': False, 'actor_status': 'not_run_static_diagnostic'}
    item['protocol'] = 'V6 static contract continuation after pre-request serialization guard failure; no context isolation'
    item['branches']['contract_hypotheses'] = branch
    folder = out / 'contract_hypotheses'
    folder.mkdir()
    try:
        hypotheses = search.hypothesis_candidates(api, folder, context, out / 'chart.png')
        branch['stages']['hypotheses'] = hypotheses
        chains = copy.deepcopy(initial['chains']) + hypotheses['new_chains']
        branch['stages']['verification'] = additional.transfer_verify(api, folder / 'verification',
            {key: copy.deepcopy(context[key]) for key in ('goal', 'state', 'history', 'options')} | {'chains': chains}, out / 'chart.png')
        branch['new_action_labels'] = sorted({c['C']['option_label'] for c in hypotheses['new_chains']}
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
    parser.add_argument('--prior-run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    parent = HERE / 'run_contract_001'
    previous = search.read(parent / 'summary.json')
    if previous.get('error', {}).get('message') != 'Static revision must use exactly the prior public inputs':
        raise ValueError('This continuation is restricted to the recorded pre-request archive guard failure')
    if list((parent / 'b002').rglob('raw.json')) or (parent / 'pub013').exists():
        raise ValueError('Do not resample static contract outcomes')
    inherited = search.read(parent / 'ledger.json')
    if inherited.get('blocked_reason'):
        raise ValueError('Cannot resume a blocked model ledger')
    sources = search.read(parent / 'source_hashes.json')
    for path, expected in sources.items():
        if base.digest(path) != expected:
            raise ValueError('Parent source changed: ' + path)
    config = search.read(HERE / 'config.json')
    old_config = search.read(parent / 'config.json')
    for key in config:
        if key != 'strategies' and config[key] != old_config[key]:
            raise ValueError('Fixed configuration changed: ' + key)
    additional.assert_checkpoint_source(args.prior_run, HERE / 'run_live_001', config['arms'])
    # Validate both transfer assets before any inference, not after the GUI portion.
    for case in ('b002', 'pub013'):
        validate_derived_context(HERE / 'transfer_inputs' / case, HERE / 'run_transfer_001' / case)
    if args.output.exists():
        raise FileExistsError('Preserve existing output')
    with (HERE / 'LIVE_ISOLATED_LOCK.json').open('x', encoding='utf-8') as stream:
        json.dump({'output': str(args.output), 'parent': str(parent), 'scope': 'same_100_300_total'}, stream)
    args.output.mkdir()
    config.update(strategies=['symmetric_hypotheses'], phase='candidate_action_state_isolation', method_image='original_full_public_chart')
    base.dump(args.output / 'config.json', config)
    ledger = base.Ledger(args.output, config)
    ledger.data = copy.deepcopy(inherited)
    ledger.data['parent_ledger'] = str(parent / 'ledger.json')
    ledger.save()
    starts = (ledger.data['request_attempts'], ledger.data['browser_operations'])
    snapshots = {}
    for source in dict.fromkeys(list(HERE.glob('*.py')) + [HERE / 'ISOLATION_ADDENDUM.md', HERE / 'config.json'] + [Path(p) for p in sources]):
        target = args.output / 'runtime_source' / source.relative_to(args.project)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        snapshots[str(source)] = base.digest(source)
    base.dump(args.output / 'source_hashes.json', snapshots)
    os.environ.pop('WEB_AGENT_EXTRA_SYSTEM_PROMPT', None)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.project))
    api = IsolatedChartAPI(config, ledger)
    if api.http.get('http://127.0.0.1:8058/health', timeout=10, allow_redirects=False).status_code != 200:
        raise ValueError('Existing service unavailable')
    original = importlib.import_module('web_agent_benchmark.evaluation.run_public39')
    actor = base.Actor(original, api, search.read(search.BASE_DIR / 'browser_action_schema.json'))
    summary = {'status': 'running', 'phase': config['phase'], 'results': [], 'transfer_results': [], 'new_natural_prefixes': 0}
    try:
        for arm in config['arms']:
            summary['results'].append(search.run_arm(arm, args.prior_run, args.output, args.project, config, ledger, api, original, actor))
            base.dump(args.output / 'summary.json', summary)
        # These static inputs never had real history/current decisions: finish the
        # unrun V6 contract panel, not a fictitious history ablation on empty history.
        static_api = contract.ContractAPI(config, ledger)
        for case in ('b002', 'pub013'):
            print('START resumed contract static ' + case, flush=True)
            summary['transfer_results'].append(static_case(case, args.output, static_api))
            base.dump(args.output / 'summary.json', summary)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        summary.update(request_attempts=ledger.data['request_attempts'], browser_operations=ledger.data['browser_operations'],
                       phase_request_attempts=ledger.data['request_attempts']-starts[0], phase_browser_operations=ledger.data['browser_operations']-starts[1],
                       source_preserved={p: base.digest(p) == sha for p, sha in snapshots.items()})
        base.dump(args.output / 'summary.json', summary)
        print(json.dumps({k: v for k, v in summary.items() if k not in ('results', 'transfer_results')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
