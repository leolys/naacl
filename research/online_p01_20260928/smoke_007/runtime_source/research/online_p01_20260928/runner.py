"""Original-environment online developer panel; --prepare never sends a model request."""
from __future__ import annotations
import argparse
from copy import deepcopy
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

from deps import HERE, PROJECT, SNAPSHOT, wire, core, public_inputs, Budget, BudgetedPanelAPI
from original_env import OriginalBrowser, catalog, MODULES
from method import (validate_actor, should_hook, arguments_view, update_state,
                    state_view, action_support, validate_challenge)
import prompts


def config_and_cases():
    config = wire.read(HERE / 'config.json')
    auth = wire.read(HERE / 'AUTHORIZATION.json')
    for key in ('endpoint', 'model', 'max_request_attempts', 'max_browser_operations', 'max_estimated_usd', 'task_ids', 'arms', 'systems'):
        if config[key] != auth[key]:
            raise ValueError('configuration_not_authorized:' + key)
    if config['concurrency'] != 1 or config['gpu_enabled'] or config['max_actor_calls'] > 8 or config['max_reverification'] > 1:
        raise ValueError('unsupported_compute_configuration')
    all_cases = catalog()
    cases = [next(c for c in all_cases if c['task_id'] == task and c['arm'] == arm)
             for task in config['task_ids'] for arm in config['arms']]
    return config, cases


def defense(api, folder, alias, context, chart, proposal):
    public = context['task']
    base_context = deepcopy(context)
    base_context['public_task_leaf_paths'] = core.public_leaf_paths(public)
    base_context['unexecuted_proposal'] = proposal
    generated = api.call(folder / 'generation', alias, 'generation', prompts.GENERATE, base_context, [('chart_1', chart)])
    combined = core.import_initial(generated, public)
    if len(combined['chains']) > 3 or len(combined['rules']) > 3:
        raise ValueError('initial_explanation_budget_exceeded')
    if {r['id'] for r in combined['rules']} != {c['rule_id'] for c in combined['chains']}:
        raise ValueError('initial_rules_must_have_chain_references')
    wire.dump(folder / 'initial_set.json', combined)
    cq = deepcopy(base_context)
    cq['initial_arguments'] = arguments_view(combined)
    questions = api.call(folder / 'questions', alias, 'generation', prompts.QUESTIONS, cq, [('chart_1', chart)])
    questions = core.validate_questions(questions, combined, public)
    if questions['questions']:
        cq['counterquestions'] = questions
        supplement = api.call(folder / 'supplement', alias, 'generation', prompts.SUPPLEMENT, cq, [('chart_1', chart)])
    else:
        supplement = {'new_rules': [], 'new_chains': [], 'refinements': [], 'question_responses': []}
        wire.dump(folder / 'supplement_skipped.json', {'reason': 'no_questions', 'model_call': False})
    combined = core.apply_supplement(supplement, combined, questions, public)
    wire.dump(folder / 'combined.json', combined)
    verify_context = deepcopy(context)
    verify_context['public_task_leaf_paths'] = core.public_leaf_paths(public)
    verify_context['arguments'] = arguments_view(combined)
    verdict = api.call(folder / 'verification', alias, 'verification', prompts.VERIFY, verify_context, [('chart_1', chart)])
    verdict = core.validate_verification(verdict, combined, public)
    wire.dump(folder / 'verified.json', verdict)
    return combined, verdict


def one_run(api, budget, config, case, system, output, browser_factory=OriginalBrowser):
    output.mkdir(parents=True, exist_ok=False)
    result = {'case': case, 'system': system, 'status': 'started', 'actor_calls': 0,
              'hook_events': [], 'rule_reads': [], 'action_records': [], 'submitted': False,
              'evidence_mode': 'real_model' if isinstance(api, BudgetedPanelAPI) else 'scripted_control',
              'persistence_causal_effect': 'not_established_by_this_panel'}
    state = combined = verdict = feedback = None
    extra = 0
    stage = 'browser_open'
    wire.dump(output / 'result.json', result)
    try:
        with browser_factory(case, output / 'browser', budget, config['browser_executable']) as browser:
            for step in range(config['max_actor_calls']):
                stage = 'actor'
                context, images = browser.snapshot()
                current = context['state']
                chart_ref = wire.digest(browser.chart) if browser.chart else None
                if state is not None:
                    context['interpretation_rules'] = state_view(state, case['alias'], chart_ref)
                    context['verified_arguments'] = {'arguments': arguments_view(combined), 'verification': verdict}
                    result['rule_reads'].append({'step': step, 'state_version': state['version'],
                        'provided_to_actor': True, 'causal_use_proven': False})
                if feedback is not None:
                    context['previous_verification_or_execution'] = feedback
                public_inputs.assert_public(context)
                step_dir = output / ('step_%02d' % step)
                proposal = validate_actor(api.call(step_dir / 'actor', case['alias'], 'proposal', prompts.ACTOR, context, images))
                result['actor_calls'] += 1
                action = proposal['action']
                record = {'step': step, 'proposal': proposal, 'selection_before': current['current_selection'],
                          'executed': False, 'execution': None, 'rule_version': state['version'] if state else None}
                result['action_records'].append(record)
                if system == 'online_completion' and should_hook(proposal, browser.chart is not None, state is not None, current['current_selection']):
                    if browser.public is None:
                        raise ValueError('complete_public_task_not_yet_observed')
                    stage = 'defense'
                    event = {'step': step, 'timing': 'before_first_chart_action_execution',
                             'pending_action': action, 'selection_at_hook': current['current_selection'],
                             'old_results_used': False}
                    result['hook_events'].append(event)
                    wire.dump(step_dir / 'hook.json', event)
                    combined, verdict = defense(api, step_dir / 'defense', case['alias'], context, browser.chart, proposal)
                    state = update_state(combined, verdict, case['alias'], chart_ref)
                    wire.dump(output / ('rule_state_v%d.json' % state['version']), state)
                    state = wire.read(output / ('rule_state_v%d.json' % state['version']))
                    feedback = {'pending_action_not_executed': action,
                                'instruction': 'Check the recorded evidence and re-derive your next action. No selection or submission was made by the verifier.'}
                    event['verification'] = verdict
                    event['rule_version'] = state['version']
                    continue
                if system == 'online_completion' and state is not None:
                    if proposal.get('challenge') is not None and validate_challenge(proposal['challenge'], browser.public):
                        if extra >= config['max_reverification']:
                            result['status'] = 'unresolved_reverification_budget'
                            break
                        extra += 1
                        stage = 'reverification'
                        ctx = {'task': browser.public, 'state': current, 'history': browser.history,
                               'public_task_leaf_paths': core.public_leaf_paths(browser.public),
                               'arguments': arguments_view(combined), 'challenge': proposal['challenge']}
                        verdict = core.validate_verification(api.call(step_dir / 'reverification', case['alias'],
                            'verification', prompts.VERIFY, ctx, [('chart_1', browser.chart)]), combined, browser.public)
                        state = update_state(combined, verdict, case['alias'], chart_ref, state)
                        wire.dump(output / ('rule_state_v%d.json' % state['version']), state)
                        state = wire.read(output / ('rule_state_v%d.json' % state['version']))
                        feedback = {'instruction': 'New evidence was checked. Re-derive using the new rule version; no action executed.'}
                        continue
                    problems = action_support(proposal, state, verdict, current['current_selection'])
                    if problems:
                        record['blocked'] = problems
                        feedback = {'unexecuted_action': action, 'dependency_problems': problems,
                                    'instruction': 'Supply supported applicable dependencies, present actual new evidence for rechecking, or return unresolved. No action executed.'}
                        continue
                if action['kind'] == 'unresolved':
                    result['status'] = 'unresolved_public_evidence'
                    break
                stage = 'execution'
                receipt = browser.execute(action)
                record.update(executed=True, execution=receipt)
                if state and action['kind'] == 'select':
                    result.setdefault('post_verification_choices', []).append({'step': step, 'recommended_option': action['option'],
                        'execution_ok': receipt['ok'], 'observed_selection_after': receipt.get('observed_selection_after'),
                        'rule_version': state['version']})
                feedback = None
                if receipt['submitted']:
                    result.update(status='submitted', submitted=True)
                    break
            else:
                result['status'] = 'actor_call_limit'
            context, _ = browser.snapshot()
            result['last_public_state'] = context['state']
            result['history'] = browser.history
    except (wire.ServiceStop, wire.UnknownRequestOutcome) as exc:
        budget.value['blocked_reason'] = str(exc)
        budget.save()
        result['status'] = 'global_stop'
        result['error'] = {'stage': stage, 'type': type(exc).__name__, 'category': str(exc)}
    except Exception as exc:
        result['status'] = 'engineering_or_response_failure'
        result['error'] = {'stage': stage, 'type': type(exc).__name__, 'category': str(exc)}
        (output / 'exception.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        wire.dump(output / 'result.json', result)
    return result


def offline_score(output, results):
    scores = []
    for unit, result in results:
        receipt = unit / 'browser/private/submissions.jsonl'
        rows = [json.loads(x) for x in receipt.read_text(encoding='utf-8').splitlines() if x.strip()] if receipt.exists() else []
        if len(rows) > 1:
            raise ValueError('more_than_one_submission_in_unit')
        row = rows[0] if rows else {}
        scores.append({'unit': unit.name, 'case': result['case'], 'system': result['system'], 'status': result['status'],
            'server_receipt_count': len(rows), 'selected_action_label': row.get('selected_action_label'),
            'original_evaluation': row.get('evaluation_hidden_from_agent', row.get('evaluation')),
            'actor_calls': result['actor_calls'], 'hook_count': len(result['hook_events']),
            'rule_reads': len(result['rule_reads']), 'causal_persistence_effect': 'not_established'})
    wire.dump(output / 'offline_scores.json', scores)
    return scores


def freeze(output, config, cases):
    sources = list(HERE.glob('*.py')) + [HERE / 'config.json', HERE / 'PROTOCOL.md', HERE / 'AUTHORIZATION.json']
    sources += [Path(core.__file__), Path(prompts.completion.__file__), Path(public_inputs.__file__), Path(wire.__file__),
                Path(sys.modules['budget'].__file__), Path(sys.modules['engine'].__file__), Path(sys.modules['prompts_observation_v4'].__file__)]
    sources += list((SNAPSHOT / 'web_agent_benchmark').glob('*/*_app.py'))
    inventory = PROJECT / '.aris/task_flows_20260924/RUNTIME_TASKS.json'
    sources.append(inventory)
    records = wire.read(inventory)
    for case in cases:
        sources.append(SNAPSHOT / 'web_agent_benchmark/benchmark_v2_open/splits' / case['arm'] / (case['domain'] + '_tasks.jsonl'))
        row = next(r for r in records if r['slug'] == case['task_id'] and r['arm'] == case['arm'])
        sources.append(SNAPSHOT / row['spec']['chart_asset']['figure_path'])
    hashes = {}
    for path in dict.fromkeys(sources):
        dest = output / 'runtime_source' / path.relative_to(PROJECT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        hashes[str(path)] = wire.digest(path)
    wire.dump(output / 'runtime.json', {'executable': sys.executable, 'python': sys.version,
        'sources': hashes, 'packages': {name: importlib.metadata.version(name) for name in ('requests','Flask','playwright','Pillow')}})
    wire.dump(output / 'config.json', config)
    wire.dump(output / 'manifest.json', cases)
    wire.dump(output / 'prompts.json', prompts.PROMPTS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['prepare', 'live'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    output = args.output.absolute()
    if output.parent != HERE:
        raise ValueError('output_must_be_new_directory_under_this_experiment')
    config, cases = config_and_cases()
    if args.resume:
        if not output.exists() or wire.read(output / 'config.json') != config or wire.read(output / 'manifest.json') != cases:
            raise ValueError('resume_config_or_manifest_mismatch')
        if any(not Path(p).is_file() or wire.digest(p) != h for p,h in wire.read(output / 'runtime.json')['sources'].items()):
            raise ValueError('resume_source_changed_use_new_version')
    else:
        output.mkdir(parents=True, exist_ok=False)
        freeze(output, config, cases)
    if args.mode == 'prepare':
        wire.dump(output / 'batch_manifest_not_authorized.json', {'cases': catalog(), 'mode': 'preparation_only',
                  'count': len(catalog()), 'live_authorized': False})
        print('Prepared 12 developer units; 280 original task-condition entries only, no model calls.', flush=True)
        return
    if not os.environ.get('MODEL_API_KEY'):
        raise ValueError('missing_authorized_process_credential')
    budget = Budget(HERE / 'live_budget.json', config)
    api = BudgetedPanelAPI(config, budget)
    results = []
    for case in cases:
        for system in config['systems']:
            if any(not Path(p).is_file() or wire.digest(p) != h for p,h in wire.read(output / 'runtime.json')['sources'].items()):
                raise ValueError('frozen_code_or_input_changed_stop_before_next_unit')
            unit = output / (case['task_id'] + '_' + case['arm'] + '_' + system)
            if unit.exists():
                result = wire.read(unit / 'result.json')
                if not result or result['status'] == 'started':
                    raise ValueError('incomplete_unit_no_automatic_replay')
            else:
                print('START', unit.name, flush=True)
                result = one_run(api, budget, config, case, system, unit)
                print('END', unit.name, result['status'], 'attempts', budget.value['request_attempts'], flush=True)
            results.append((unit, result))
            wire.dump(output / 'progress.json', [{'unit': p.name, 'status': r['status']} for p,r in results])
            if result['status'] == 'global_stop':
                break
        if results and results[-1][1]['status'] == 'global_stop':
            break
    scores = offline_score(output, results)
    wire.dump(output / 'summary.json', {'units': len(results), 'planned': len(cases)*len(config['systems']), 'scores': scores,
        'budget': budget.value, 'engineering_completion_not_research_success': True})
    print('DONE', len(results), 'units', flush=True)


if __name__ == '__main__':
    main()
