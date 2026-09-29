"""Serial full-catalog entry. Preparation is offline; live needs a NEW authorization."""
from __future__ import annotations
import argparse
from copy import deepcopy
from pathlib import Path
import os
import shutil
import sys

from deps import HERE, PROJECT, wire, Budget, BudgetedPanelAPI
import original_env
import runner


AUTH_FIELDS = ('protocol', 'endpoint', 'model', 'task_ids', 'arms', 'systems',
               'max_request_attempts', 'max_browser_operations', 'max_estimated_usd',
               'max_actor_calls', 'max_reverification', 'interface_version')
OVERRIDE_FIELDS = set(AUTH_FIELDS) | {'concurrency', 'gpu_enabled', 'wandb'}


def plan(override):
    if not isinstance(override, dict) or set(override)-OVERRIDE_FIELDS:
        raise ValueError('unsupported_configuration_override')
    config = deepcopy(wire.read(HERE / 'config.json'))
    config.update(override)
    all_cases = original_env.catalog()
    if config['task_ids'] == 'all_original_140':
        config['task_ids'] = list(dict.fromkeys(c['task_id'] for c in all_cases))
    if len(config['task_ids']) != len(set(config['task_ids'])):
        raise ValueError('duplicate_task_ids')
    if config['concurrency'] != 1 or config['gpu_enabled'] or config.get('wandb'):
        raise ValueError('only_serial_no_gpu_no_wandb_supported')
    if not set(config['systems']) <= {'ordinary', 'online_completion'} or not config['systems']:
        raise ValueError('unknown_system')
    if len(config['systems']) != len(set(config['systems'])):
        raise ValueError('duplicate_system')
    if len(config['arms']) != len(set(config['arms'])):
        raise ValueError('duplicate_arm')
    lookup = {(c['task_id'], c['arm']): c for c in all_cases}
    cases = []
    for task in config['task_ids']:
        for arm in config['arms']:
            if (task, arm) not in lookup:
                raise ValueError('task_condition_not_in_original_catalog')
            cases.append(lookup[(task, arm)])
    return config, cases


def validate_mode(config, mode):
    version={'strict_v1':'v1', 'typed_scalars_v2':'v2'}.get(config.get('interface_version'))
    if version is None:
        raise ValueError('unsupported_interface_version')
    expected='online_explanation_completion_'+version+'_batch_'+('preparation_only' if mode=='prepare' else 'live')
    if config.get('protocol') != expected:
        raise ValueError('mode_specific_protocol_required:' + expected)


def authorize(config, authorization):
    validate_mode(config,'live')
    if authorization.get('authorized') is not True or not authorization.get('user_approval_reference'):
        raise ValueError('new_explicit_authorization_required')
    if any(authorization.get(k) != config.get(k) for k in AUTH_FIELDS):
        raise ValueError('authorization_scope_mismatch')
    for key in ('max_request_attempts', 'max_browser_operations', 'max_estimated_usd'):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or value <= 0:
            raise ValueError('new_positive_budget_required:' + key)
    for key in ('max_request_attempts', 'max_browser_operations', 'max_actor_calls', 'max_reverification'):
        if type(config[key]) is not int or config[key] < 0:
            raise ValueError('integer_limit_required:' + key)
    if not config['max_actor_calls'] or config['max_reverification'] > 1:
        raise ValueError('invalid_actor_or_reverification_limit')


def unchanged(output):
    for name, digest in wire.read(output / 'runtime.json')['sources'].items():
        path = Path(name)
        if not path.is_file() or wire.digest(path) != digest:
            raise ValueError('frozen_source_or_asset_changed:' + name)


def freeze_extra(output, paths):
    record = wire.read(output / 'runtime.json')
    for path in dict.fromkeys(paths):
        path = Path(path).resolve()
        destination = output / 'runtime_source' / path.relative_to(PROJECT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        record['sources'][str(path)] = wire.digest(path)
    wire.dump(output / 'runtime.json', record)


def imported_project_sources():
    """Include inherited adapter/format/usage helpers, not just direct imports."""
    paths=[]
    for loaded in tuple(sys.modules.values()):
        name=getattr(loaded,'__file__',None)
        if not name:
            continue
        path=Path(name).resolve()
        if (path.is_file() and path.suffix=='.py' and path.is_relative_to(PROJECT)
                and '.venv' not in path.parts):
            paths.append(path)
    return paths


def terminal_result(unit):
    result = wire.read(unit / 'result.json')
    if not result or result.get('status') == 'started':
        raise ValueError('incomplete_unit_no_automatic_replay')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mode', required=True, choices=['prepare', 'live'])
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    config, cases = plan(wire.read(args.config))
    validate_mode(config, args.mode)
    runtime = HERE / 'runtime_snapshot'
    if not runtime.is_dir():
        raise ValueError('isolated_original_runtime_not_prepared')
    # Imported original web modules must resolve against this immutable mirror,
    # including pub005's original runtime override, NOT the raw spec's figure.
    sys.path.insert(0, str(runtime))
    original_env.SNAPSHOT = runner.SNAPSHOT = runtime
    interface_version = config.get('interface_version', 'strict_v1')
    if interface_version == 'typed_scalars_v2':
        import prompts_v2
        runner.prompts = prompts_v2
    elif interface_version != 'strict_v1':
        raise ValueError('unsupported_interface_version')
    output = args.output.resolve()
    if output.parent != HERE:
        raise ValueError('output_must_be_new_directory_under_this_experiment')
    authorization = wire.read(args.authorization) if args.authorization else {}
    if args.mode == 'live':
        authorize(config, authorization)
        if not os.environ.get('MODEL_API_KEY'):
            raise ValueError('missing_authorized_process_credential')
    if args.resume:
        if (not output.exists() or wire.read(output / 'config.json') != config
                or wire.read(output / 'manifest.json') != cases):
            raise ValueError('resume_config_or_manifest_mismatch')
        if args.mode == 'live' and wire.read(output / 'authorization.json') != authorization:
            raise ValueError('resume_authorization_mismatch')
        if args.mode == 'live' and not (output / 'budget.json').is_file():
            raise ValueError('resume_missing_original_budget_ledger')
        unchanged(output)
    else:
        output.mkdir(parents=True, exist_ok=False)
        runner.freeze(output, config, cases)
        # Freeze ALL original runtime resources: renderer-selected overrides can
        # differ from spec chart_asset. None of these private files go to a model.
        sources = [p for p in runtime.rglob('*') if p.is_file()] + imported_project_sources()
        sources.append(args.config.resolve())
        if args.authorization:
            sources.append(args.authorization.resolve())
        freeze_extra(output, sources)
        wire.dump(output / 'authorization.json', authorization)
    if args.mode == 'prepare':
        wire.dump(output / 'readiness.json', {'mode': 'offline_preparation_only',
            'base_tasks': len(config['task_ids']), 'conditions': len(cases),
            'planned_agent_runs': len(cases) * len(config['systems']),
            'model_requests': 0, 'browser_operations': 0, 'live_authorized': False,
            'next': 'New explicit task/model/budget authorization and new output directory required.'})
        print('PREPARED', len(cases), 'conditions;', len(cases) * len(config['systems']),
              'planned runs; no live authorization inherited.', flush=True)
        return
    budget = Budget(output / 'budget.json', config)
    api = BudgetedPanelAPI(config, budget)
    results = []
    for case in cases:
        for system in config['systems']:
            unchanged(output)
            unit = output / (case['task_id'] + '_' + case['arm'] + '_' + system)
            if unit.exists():
                result = terminal_result(unit)
            else:
                if budget.value.get('blocked_reason'):
                    break
                print('START', unit.name, flush=True)
                result = runner.one_run(api, budget, config, case, system, unit)
                print('END', unit.name, result['status'], flush=True)
            results.append((unit, result))
            wire.dump(output / 'progress.json', [{'unit': p.name, 'status': r['status']} for p, r in results])
            if result['status'] == 'global_stop':
                break
        if budget.value.get('blocked_reason'):
            break
    scores = runner.offline_score(output, results)
    wire.dump(output / 'summary.json', {'units': len(results), 'planned': len(cases)*len(config['systems']),
        'scores': scores, 'budget': budget.value, 'engineering_completion_not_research_success': True})
    print('DONE', len(results), 'units', flush=True)


if __name__ == '__main__':
    main()
