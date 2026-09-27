"""Fresh candidate-generation pilot; old runs remain historical references only."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import getpass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
PROJECT = RESEARCH.parent
for directory in (RESEARCH / 'obc140_20260923',
                  RESEARCH / 'obc140_20260923/terra140_native_zh_20260924',
                  RESEARCH / 'competing_rules_20260923',
                  RESEARCH / 'obc140_runtime_aligned_20260924'):
    sys.path.insert(0, str(directory))
import panel_core as wire
import public_inputs
from budget import BudgetedPanelAPI, EstimatedBudget


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


core = module('candidate_completion_v3_core', HERE / 'core.py')
prompts = module('candidate_completion_v3_prompts', HERE / 'prompts.py')
FIXED_IDS = ('b001', 'b002', 'pub013')
STAGES = ('generation', 'questions', 'supplement', 'verification')


def now():
    return datetime.now(timezone.utc).isoformat()


def load_case(task_id):
    if task_id not in FIXED_IDS:
        raise ValueError('Only the three preselected development cases are authorized')
    archive = RESEARCH / 'obc140_runtime_aligned_20260924'
    public_path = archive / 'prepared/tasks' / task_id / 'public.json'
    proposal_path = archive / 'run/tasks' / task_id / 'proposal/round_001/validated.json'
    chart_path = archive / 'prepared/tasks' / task_id / 'chart.jpeg'
    public = wire.read(public_path)
    if not isinstance(public, dict) or set(public) != public_inputs.PUBLIC_KEYS:
        raise ValueError('Unexpected public projection')
    public_inputs.assert_public(public)
    action = wire.read(proposal_path)['proposal']['action']
    if action.get('kind') != 'select' or action.get('option') not in public['option_labels']:
        raise ValueError('Archived actor reference is not a public selection proposal')
    return {'task_id': task_id, 'task': public,
            'decision_reference': {'task_goal': public['user_goal'], 'proposed_option': action['option']},
            'reference_origin': 'archived_actual_actor_proposal_not_executed_selection',
            'initial_generation_origin': 'fresh_this_run_no_archived_explanations',
            'chart_source': str(chart_path), 'chart_ref': task_id + ':' + wire.digest(chart_path),
            'source_sha256': {str(p): wire.digest(p) for p in (public_path, proposal_path, chart_path)}}


def arguments_view(arguments):
    return {key: copy.deepcopy(arguments.get(key, []))
            for key in ('rules', 'chains', 'refinements', 'unresolved_questions')}


def build_context(stage, inputs, result):
    context = wire.common_context(inputs['task'])
    context['public_task_leaf_paths'] = core.public_leaf_paths(inputs['task'])
    if stage in ('generation', 'questions', 'supplement'):
        context['decision_reference'] = copy.deepcopy(inputs['decision_reference'])
        if stage != 'generation':
            context['initial_arguments'] = arguments_view(result['initial_arguments'])
        if stage == 'supplement':
            context['counterquestions'] = copy.deepcopy(result['questions'])
    elif stage == 'verification':
        context['arguments'] = arguments_view(result['combined'])
        # Missing-question records are not evidence or independent judgments.
        context['arguments'].pop('unresolved_questions', None)
        for chain in context['arguments']['chains']:
            for key in ('question_ids', 'relationship', 'proposal_relation', 'claim_kind'):
                chain.pop(key, None)
        for note in context['arguments']['refinements']:
            note.pop('question_ids', None)
    else:
        raise ValueError('Unknown stage')
    public_inputs.assert_public(context)
    return context


def validate_relations(arguments, public, reference):
    for chain in arguments['chains']:
        relation = chain.get('proposal_relation')
        if relation is None:
            continue
        if not isinstance(relation, dict) or relation.get('target_option') != reference['proposed_option']:
            raise core.SchemaError('Relation must address the actual public actor proposal')
        if relation.get('stance') not in {'supports', 'refutes', 'alternative', 'not_addressed'}:
            raise core.SchemaError('Invalid proposal relation')
        if not isinstance(relation.get('reason'), str) or not relation['reason'].strip():
            raise core.SchemaError('Missing relation explanation')
        if relation['target_option'] not in public['option_labels']:
            raise core.SchemaError('Relation target is not a public option')


def validate_config(config):
    expected = {
        'protocol': 'explanation_completion_v3',
        'endpoint': 'https://api.apiyi.com/v1/chat/completions', 'model': 'gpt-5.6-terra',
        'temperature': 0, 'phase_max_tokens': {'generation': 4800, 'verification': 6000},
        'max_attempts_per_call': 2, 'max_request_attempts': 16, 'max_estimated_usd': 3.0,
        'attempt_reserve_usd': 0.25, 'estimated_input_usd_per_m': 2.5,
        'estimated_output_usd_per_m': 12, 'timeout_seconds': 120, 'proxy': None,
        'allow_trailing_json_closers': False, 'concurrency': 1, 'quality_retries': False,
        'browser_operations': 0, 'gpu_enabled': False, 'wandb': False,
        'fixed_cases': list(FIXED_IDS), 'planned_max_logical_calls': 12}
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError('Frozen authorized configuration changed')


def freeze_sources(output):
    paths = {Path(__file__), HERE / 'core.py', HERE / 'prompts.py', HERE / 'config.json',
             HERE / 'AUTHORIZATION.json', HERE / 'PROTOCOL.md',
             RESEARCH / 'explanation_completion_v2_20260926/core.py',
             RESEARCH / 'explanation_completion_20260925/core.py'}
    for mod in (wire, wire.engine, public_inputs, sys.modules['budget'],
                sys.modules['analyze_usage'], sys.modules['format_replay'],
                sys.modules['prompts_observation_v4']):
        paths.add(Path(mod.__file__).resolve())
    records = {}
    for path in sorted(paths, key=str):
        dest = output / 'runtime_source' / path.relative_to(PROJECT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        records[str(path)] = wire.digest(path)
    wire.dump(output / 'runtime.json', {'created_at': now(), 'executable': sys.executable,
        'python': sys.version, 'source_sha256': records,
        'credential_policy': 'process memory only; never serialize keys or Authorization headers'})
    wire.dump(output / 'prompt_templates.json', prompts.PROMPTS)


def claim_live_authorization(output):
    """One live launch per this authorization, regardless of the output name."""
    with (HERE / 'LIVE_AUTHORIZATION_CONSUMED.json').open('x', encoding='utf-8') as stream:
        json.dump({'started_at': now(), 'output': str(output), 'max_request_attempts': 16,
                   'max_estimated_usd': 3, 'new_live_launch_requires_new_authorization': True}, stream, indent=2)


def run(output, live=False, api_factory=BudgetedPanelAPI):
    output = Path(output).absolute().resolve()
    if output.parent != HERE or output.exists():
        raise ValueError('Use a fresh direct child output directory; prior outputs cannot be overwritten')
    config = wire.read(HERE / 'config.json')
    validate_config(config)
    if live and api_factory is BudgetedPanelAPI and not os.environ.get('MODEL_API_KEY'):
        raise ValueError('Missing authorized process credential')
    fixture = live and api_factory is not BudgetedPanelAPI
    evidence_mode = 'offline_fixture' if fixture else 'real_model' if live else 'preparation_only'
    inputs_all = [load_case(task) for task in FIXED_IDS]
    output.mkdir(parents=True, exist_ok=False)
    freeze_sources(output)
    budget = EstimatedBudget(output / 'budget.json', config)
    results = []
    summary = {'status': 'prepared_not_sent', 'evidence_mode': evidence_mode,
        'created_at': now(), 'planned_max_logical_calls': 12, 'global_stop': None,
        'browser_operations': 0, 'gpu_operations': 0, 'translation_api_calls': 0,
        'historical_comparison': 'descriptive_only_not_controlled_ablation',
        'semantic_success': 'not_inferred_from_structural_validation', 'cases': []}
    for inputs in inputs_all:
        folder = output / 'cases' / inputs['task_id']
        folder.mkdir(parents=True)
        shutil.copyfile(inputs['chart_source'], folder / 'chart.jpeg')
        wire.dump(folder / 'inputs.json', inputs)
        result = {'task_id': inputs['task_id'], 'status': 'prepared_not_sent',
            'evidence_mode': evidence_mode, 'stages': {},
            'generation': None, 'initial_arguments': None, 'questions': None,
            'supplement': None, 'combined': None, 'verification': None,
            'rule_state': None, 'failure': None, 'request_attempts': 0,
            'estimated_ledger_usd': 0, 'business_actions': 0}
        results.append(result)
        wire.dump(folder / 'prepared_first_context.json', build_context('generation', inputs, result))

    def save():
        budget.reconcile()
        for result in results:
            events = [e for e in budget.value['events'] if e['task_slug'] == result['task_id']]
            result['request_attempts'] = len(events)
            result['estimated_ledger_usd'] = sum(e['charged_estimated_usd'] for e in events)
            wire.dump(output / 'cases' / result['task_id'] / 'result.json', result)
        summary['cases'] = [{k: r[k] for k in ('task_id', 'status', 'request_attempts', 'failure')}
                            for r in results]
        summary['request_attempts'] = budget.value['request_attempts']
        summary['estimated_ledger_usd'] = budget.value['estimated_ledger_usd']
        summary['actual_bill_usd'] = None
        summary['source_preservation'] = {p: Path(p).exists() and wire.digest(p) == digest
                                         for inp in inputs_all for p, digest in inp['source_sha256'].items()}
        summary['runtime_source_preservation'] = {p: wire.digest(p) == digest for p, digest in
            wire.read(output / 'runtime.json')['source_sha256'].items()}
        wire.dump(output / 'summary.json', summary)

    save()
    if not live:
        return summary
    if not fixture:
        claim_live_authorization(output)
    summary['status'] = 'running'
    api = api_factory(config, budget)
    for inputs, result in zip(inputs_all, results):
        folder = output / 'cases' / result['task_id']
        if summary['global_stop']:
            result['status'] = 'not_attempted_global_stop'
            continue
        result['status'] = 'running'
        stage = None
        try:
            for stage in STAGES:
                result['stages'][stage] = {'status': 'running', 'started_at': now()}
                context = build_context(stage, inputs, result)
                wire.dump(folder / stage / 'input_context.json', context)
                save()
                if stage == 'supplement' and not result['questions']['questions']:
                    value = {'new_rules': [], 'new_chains': [], 'refinements': [], 'question_responses': []}
                    result['stages'][stage]['output_source'] = 'deterministic_empty_no_questions_no_model_call'
                else:
                    value = api.call(folder / stage / 'round_001', result['task_id'],
                        'verification' if stage == 'verification' else 'generation',
                        prompts.PROMPTS[stage], context, [('chart_1', folder / 'chart.jpeg')])
                    result['stages'][stage]['output_source'] = 'model_response' if not fixture else 'offline_fixture'
                wire.dump(folder / stage / 'raw.json', value)
                if stage == 'generation':
                    result['generation'] = value
                    result['initial_arguments'] = core.import_initial(value, inputs['task'])
                    validate_relations(result['initial_arguments'], inputs['task'], inputs['decision_reference'])
                    wire.dump(folder / 'initial_set.json', result['initial_arguments'])
                elif stage == 'questions':
                    result['questions'] = core.validate_questions(value, result['initial_arguments'], inputs['task'])
                elif stage == 'supplement':
                    result['combined'] = core.apply_supplement(value, result['initial_arguments'],
                                                             result['questions'], inputs['task'])
                    validate_relations(result['combined'], inputs['task'], inputs['decision_reference'])
                    result['supplement'] = value
                    wire.dump(folder / 'combined_arguments.json', result['combined'])
                else:
                    result['verification'] = core.validate_verification(value, result['combined'], inputs['task'])
                    result['rule_state'] = core.build_rule_state(result['combined'], result['verification'],
                        result['task_id'], inputs['chart_ref'], inputs['task'])
                    core.save_state(folder / 'rule_state.json', result['rule_state'])
                    if core.load_state(folder / 'rule_state.json') != result['rule_state']:
                        raise ValueError('State persistence changed content')
                    wire.dump(folder / 'state_reload_check.json', {'identical': True,
                        'actual_actor_use': 'not_run', 'cross_step_effectiveness': 'not_tested'})
                wire.dump(folder / stage / 'accepted.json', result[stage])
                result['stages'][stage].update(status='completed', finished_at=now())
                save()
                if stage == 'generation' and not result['initial_arguments']['chains']:
                    result['status'] = 'no_complete_candidate'
                    for pending in STAGES[1:]:
                        result['stages'][pending] = {'status': 'not_run_no_complete_candidate'}
                    break
            else:
                result['status'] = 'mock_completed' if fixture else 'completed'
        except (wire.ServiceStop, wire.UnknownRequestOutcome) as exc:
            result['failure'] = {'stage': stage, 'type': type(exc).__name__, 'reason': str(exc)}
            result['status'] = 'stopped_global'
            summary['global_stop'] = copy.deepcopy(result['failure'])
        except Exception as exc:
            result['failure'] = {'stage': stage, 'type': type(exc).__name__, 'reason': str(exc)}
            result['status'] = 'failed_stage_no_quality_retry'
        finally:
            if result['failure'] and stage in result['stages']:
                result['stages'][stage].update(status='failed', failure=result['failure'])
            result['finished_at'] = now()
            save()
    terminal = 'mock_completed' if fixture else 'completed'
    summary['status'] = ('stopped_global' if summary['global_stop'] else terminal
                         if all(r['status'] == terminal for r in results)
                         else 'completed_with_case_failures')
    summary['finished_at'] = now()
    save()
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--credential-prompt', action='store_true', help='Read the authorized key without echo')
    args = parser.parse_args()
    if args.credential_prompt:
        if not args.live:
            parser.error('Credential prompt only applies to authorized live execution')
        os.environ['MODEL_API_KEY'] = getpass.getpass('Authorized API key (not saved): ')
    try:
        summary = run(args.output, live=args.live)
        print(json.dumps({k: summary[k] for k in ('status', 'cases', 'request_attempts',
                                                'estimated_ledger_usd')}, ensure_ascii=False))
    finally:
        if args.credential_prompt:
            os.environ.pop('MODEL_API_KEY', None)
