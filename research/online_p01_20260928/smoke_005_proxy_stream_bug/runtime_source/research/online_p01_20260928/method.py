"""Action proposal checks and versioned, task-local interpretation views."""
from copy import deepcopy
from deps import core


def validate_actor(value):
    if not isinstance(value, dict) or not isinstance(value.get('action'), dict):
        raise ValueError('actor_requires_one_action_object')
    action = value['action']
    fields = {'open_link': ('label',), 'select': ('option',), 'fill': ('field', 'value'),
              'check': ('field', 'value'), 'select_field': ('field', 'option'),
              'submit': (), 'unresolved': ()}
    if action.get('kind') not in fields:
        raise ValueError('actor_unknown_action')
    for field in fields[action['kind']]:
        if field not in action:
            raise ValueError('actor_missing_action_field')
    if not isinstance(value.get('brief_basis'), str) or not isinstance(value.get('chart_dependent'), bool):
        raise ValueError('actor_requires_basis_and_chart_flag')
    for field in ('used_rules', 'supporting_chain_ids'):
        if not isinstance(value.get(field), list):
            raise ValueError('actor_requires_dependency_lists')
    return value


def should_hook(proposal, chart_seen, already_checked, current_selection=''):
    action = proposal['action']
    primary_proposal = action['kind'] == 'select' and bool(str(action.get('option', '')).strip())
    pending_submit = action['kind'] == 'submit' and bool(current_selection)
    return bool(chart_seen and not already_checked and (primary_proposal or pending_submit))


def arguments_view(combined):
    value = {key: deepcopy(combined.get(key, [])) for key in ('rules', 'chains', 'refinements')}
    for chain in value['chains']:
        chain.pop('question_ids', None)
        chain.pop('relationship', None)
    for refinement in value['refinements']:
        refinement.pop('question_ids', None)
    return value


def update_state(combined, verification, task, chart, previous=None):
    state = core.build_rule_state(combined, verification, task, chart)
    if previous is not None:
        if previous['scope'] != state['scope']:
            raise ValueError('cannot_update_across_task_or_chart_scope')
        state['version'] = previous['version'] + 1
        old = {r['rule_id']: r for r in previous['rules']}
        for record in state['rules']:
            prior = old[record['rule_id']]
            record['version'] = prior['version'] + 1
            record['history'] = deepcopy(prior['history']) + [{
                'event': 'reverification', 'version': record['version'],
                'previous_status': prior['status'], 'status': record['status'],
                'previous_checks': deepcopy(prior['checks'])}]
        for refinement in state['refinements']:
            refinement['target_rule_version'] = state['version']
    return state


def state_view(state, task, chart):
    if state['scope'] != {'task_id': task, 'chart_ref': chart}:
        raise ValueError('rule_scope_mismatch')
    # Match semantic conditions is the actor's explicit judgment, not a program
    # fabricated True. All statuses remain visible with their checks and history.
    return {'version': state['version'], 'same_task_and_image': True,
            'condition_applicability': 'actor_must_check', 'rules': deepcopy(state['rules']),
            'refinements': deepcopy(state['refinements'])}


def action_support(proposal, state, verification, selection):
    if proposal['action']['kind'] not in ('select', 'submit'):
        return []
    choice = proposal['action'].get('option') if proposal['action']['kind'] == 'select' else selection
    records = {r['rule_id']: r for r in state['rules']}
    checks = {c['target_id']: c for c in verification['checks']}
    uses = {}
    for use in proposal['used_rules']:
        if not isinstance(use, dict) or use.get('rule_id') in uses:
            return ['invalid_or_duplicate_rule_reference']
        record = records.get(use.get('rule_id'))
        if record is None or use.get('version') != record['version'] or record['status'] != 'active':
            return ['unknown_stale_or_nonactive_rule']
        if use.get('conditions_match') is not True or not str(use.get('basis', '')).strip():
            return ['rule_conditions_not_confirmed_by_actor']
        uses[use['rule_id']] = use
    chains = {c['chain_id']: c for c in state['chains']}
    supplied = proposal['supporting_chain_ids']
    if not supplied or len(supplied) != len(set(supplied)):
        return ['no_unique_supported_chain_cited']
    for chain_id in supplied:
        chain = chains.get(chain_id)
        check = checks.get(chain_id)
        if not chain or not check or chain['option_label'] != choice or chain['rule_id'] not in uses:
            return ['chain_does_not_support_proposed_choice']
        if any(check[dim]['status'] != 'supported' for dim in ('O', 'B', 'implication')):
            return ['chain_has_unresolved_or_refuted_premises']
    return []


def validate_challenge(challenge, public):
    if not isinstance(challenge, dict) or not str(challenge.get('reason', '')).strip() or not challenge.get('evidence'):
        return False
    core._evidence_list(challenge['evidence'], public)
    return True
