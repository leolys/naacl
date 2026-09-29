"""Reconstructed set-completion core for online defense (test-anchored rebuild).

Rebuilt for online_p01_20260928 against the frozen interface tests:
research/explanation_completion_20260925/tests/test_core.py (v1 contract),
research/online_defense_20260925/tests/{test_method,test_scalar_contract}.py,
METHOD_REVISED_ZH.md and METHOD_INTERFACE_V2_ADDENDUM.md. The original core.py
was omitted from the export; every behavior here is anchored to those tests.
v2 scalar rule: public-task citations must quote the exact typed JSON scalar.
"""
import copy
import json
import re
from pathlib import Path


class SchemaError(ValueError):
    pass


QUESTION_OUTCOMES = ('new_explanation', 'refined_existing', 'already_covered', 'unresolved')
CHAIN_KINDS = ('supports_action', 'challenges_support', 'underdetermined')
RELATIONSHIPS = ('compatible', 'competing', 'support_gap')
STATUSES = ('supported', 'refuted', 'undetermined')
FOCUSES = ('observations', 'rule_conditions', 'coverage')


def _public_leaf(public, pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise SchemaError('public_path_requires_json_pointer')
    value = public
    for raw in pointer.split('/')[1:]:
        key = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.match(r'^(0|[1-9][0-9]*)$', key):
                raise SchemaError('missing_public_path:' + pointer)
            index = int(key)
            if index >= len(value):
                raise SchemaError('missing_public_path:' + pointer)
            value = value[index]
        elif isinstance(value, dict):
            if key not in value:
                raise SchemaError('missing_public_path:' + pointer)
            value = value[key]
        else:
            raise SchemaError('missing_public_path:' + pointer)
    return value


def public_leaf_paths(public, prefix=''):
    pointers = []
    if isinstance(public, dict):
        for key, value in public.items():
            escaped = str(key).replace('~', '~0').replace('/', '~1')
            pointers.extend(public_leaf_paths(value, prefix + '/' + escaped))
    elif isinstance(public, list):
        for index, value in enumerate(public):
            pointers.extend(public_leaf_paths(value, prefix + '/' + str(index)))
    else:
        pointers.append(prefix)
    return pointers


def _is_scalar(value):
    return value is None or isinstance(value, (str, bool, int, float))


def _evidence(citation, public):
    if not isinstance(citation, dict):
        raise SchemaError('evidence_requires_object')
    ref = citation.get('ref')
    if ref == 'public_task':
        leaf = _public_leaf(public, citation.get('path'))
        if not _is_scalar(leaf):
            raise SchemaError('public_task citation must point at a scalar leaf')
        if 'content' not in citation:
            raise SchemaError('public_task_citation_requires_exact_public_leaf_content')
        content = citation['content']
        if type(content) is not type(leaf) or content != leaf:
            raise SchemaError('exact public leaf content required (typed scalar, no repair)')
        return citation
    if isinstance(ref, str) and ref.startswith('chart'):
        if not isinstance(citation.get('location'), str) or not citation['location'].strip():
            raise SchemaError('chart_citation_requires_location')
        if not isinstance(citation.get('content'), str) or not citation['content'].strip():
            raise SchemaError('chart_citation_requires_literal_content')
        return citation
    raise ValueError('unknown_evidence_ref:' + str(ref))


def _evidence_list(evidence, public):
    if not isinstance(evidence, list) or not evidence:
        raise SchemaError('evidence_requires_nonempty_list')
    return [_evidence(item, public) for item in evidence]


def _chart_observations(observations, public):
    if not isinstance(observations, list) or not observations:
        raise SchemaError('observations_require_chart_citations')
    for item in observations:
        ref = item.get('ref') if isinstance(item, dict) else None
        if not (isinstance(ref, str) and ref.startswith('chart')):
            raise SchemaError('observations must cite chart evidence only; public task leaf is task_evidence')
        _evidence(item, public)


def _task_evidence(items, public):
    for item in items:
        if not (isinstance(item, dict) and item.get('ref') == 'public_task'):
            raise SchemaError('task_evidence must cite public_task leaves only')
        _evidence(item, public)


def import_initial(raw, public):
    if isinstance(raw, dict) and isinstance(raw.get('generated'), dict):
        raw = raw['generated']
    if not isinstance(raw, dict) or not isinstance(raw.get('rules'), list) or not isinstance(raw.get('chains'), list):
        raise SchemaError('initial_set_requires_rules_and_chains')
    rules, seen = [], {}
    for rule in raw['rules']:
        if not isinstance(rule, dict) or not str(rule.get('id', '')).strip():
            raise SchemaError('rule_requires_id')
        if not isinstance(rule.get('text'), str) or not rule['text'].strip():
            raise SchemaError('rule_requires_selfcontained_text')
        if rule['id'] in seen:
            continue
        record = copy.deepcopy(rule)
        record.setdefault('component', '')
        record.setdefault('conditions', '')
        seen[rule['id']] = record
        rules.append(record)
    chains = []
    for index, chain in enumerate(raw['chains'], 1):
        if not isinstance(chain, dict):
            raise SchemaError('chain_requires_object')
        chain_id = str(chain.get('chain_id', '')).strip() or 'base_c%d' % index
        rule_id = chain.get('rule_id')
        if rule_id not in seen:
            raise SchemaError('missing rule reference: %s' % rule_id)
        _chart_observations(chain.get('observations'), public)
        _task_evidence(chain.get('task_evidence', []), public)
        record = copy.deepcopy(chain)
        record['chain_id'] = chain_id
        if not isinstance(record.get('claim'), str) or not record['claim'].strip():
            raise SchemaError('chain_requires_specific_claim')
        chains.append(record)
    return {'rules': rules, 'chains': chains, 'refinements': [],
            'initial_counts': {'rules': len(rules), 'chains': len(chains)}}


def validate_questions(questions, combined, public):
    if not isinstance(questions, dict) or not isinstance(questions.get('questions'), list):
        raise SchemaError('questions_requires_list')
    if not isinstance(questions.get('summary'), str) or not questions['summary'].strip():
        raise SchemaError('questions_requires_bounded_summary')
    if len(questions['questions']) > 3:
        raise SchemaError('at_most_three_questions')
    ids, chain_ids = set(), {c['chain_id'] for c in combined['chains']}
    for question in questions['questions']:
        if not isinstance(question, dict):
            raise SchemaError('question_requires_object')
        qid = str(question.get('id', '')).strip()
        if not qid or qid in ids:
            raise SchemaError('question_ids_must_be_unique_nonempty')
        ids.add(qid)
        targets = question.get('target_chain_ids')
        if not isinstance(targets, list) or not targets or any(t not in chain_ids for t in targets):
            raise SchemaError('question_target_chain_ids_must_reference_existing_chains')
        if question.get('focus') not in FOCUSES:
            raise SchemaError('unknown_question_focus')
        if not isinstance(question.get('question'), str) or not question['question'].strip():
            raise SchemaError('question_requires_checkable_text')
    return copy.deepcopy(questions)


def _validate_new_chain(chain, rules, combined, public):
    chain_id = str(chain.get('chain_id', '')).strip()
    if not re.match(r'^supp_c\d+$', chain_id):
        raise SchemaError('new_chain_ids_must_be_supp_cN')
    rule_id = chain.get('rule_id')
    if rule_id not in rules:
        raise SchemaError('new_chain_rule_reference_missing:%s' % rule_id)
    _chart_observations(chain.get('observations'), public)
    _task_evidence(chain.get('task_evidence', []), public)
    if chain.get('claim_kind') not in CHAIN_KINDS:
        raise SchemaError('unknown_claim_kind')
    if chain.get('relationship') not in RELATIONSHIPS:
        raise SchemaError('unknown_relationship')
    option = chain.get('option_label')
    if chain.get('relationship') == 'support_gap':
        if option is not None:
            raise SchemaError('non-action support gaps must not carry an alternative action')
    elif chain['claim_kind'] == 'supports_action':
        if option not in public.get('option_labels', []):
            raise SchemaError('supports_action_requires_exact_public_option')
    elif option is not None:
        raise SchemaError('non_action_chains_require_null_option')
    if not isinstance(chain.get('claim'), str) or not chain['claim'].strip():
        raise SchemaError('chain_requires_specific_claim')
    links = chain.get('question_ids')
    if not isinstance(links, list) or not links:
        raise SchemaError('new_records_must_link_actual_question_ids')
    return chain_id


def apply_supplement(supplement, combined, questions, public):
    if 'supplement_counts' in combined:
        raise SchemaError('a later supplement pass must not overwrite an earlier pass')
    if not isinstance(supplement, dict):
        raise SchemaError('supplement_requires_object')
    new_rules = supplement.get('new_rules', [])
    new_chains = supplement.get('new_chains', [])
    refinements = supplement.get('refinements', [])
    responses = supplement.get('question_responses', [])
    if questions['questions'] and not isinstance(responses, list):
        raise SchemaError('question_responses_require_list')
    if not questions['questions']:
        if new_rules or new_chains or refinements or responses:
            raise SchemaError('empty_questions_allow_only_empty_additions')
        combined = copy.deepcopy(combined)
        combined['supplement_counts'] = {'rules': 0, 'chains': 0, 'refinements': 0}
        combined['question_responses'] = []
        return combined
    rule_ids = {r['id'] for r in combined['rules']}
    rule_records = {r['id']: copy.deepcopy(r) for r in combined['rules']}
    for rule in new_rules:
        if not isinstance(rule, dict) or not re.match(r'^supp_r\d+$', str(rule.get('id', ''))):
            raise SchemaError('new_rule_ids_must_be_supp_rN')
        if rule['id'] in rule_ids:
            raise SchemaError('original_ids_cannot_be_reused_as_new_rules')
        if not isinstance(rule.get('text'), str) or not rule['text'].strip():
            raise SchemaError('rule_requires_selfcontained_text')
        rule_ids.add(rule['id'])
        record = copy.deepcopy(rule)
        record.setdefault('component', '')
        record.setdefault('conditions', '')
        rule_records[rule['id']] = record
    used = set()
    base_chain_ids = {c['chain_id'] for c in combined['chains']}
    chains = copy.deepcopy(combined['chains'])
    for chain in new_chains:
        chain_id = _validate_new_chain(chain, rule_ids, combined, public)
        used.add(chain['rule_id'])
        record = copy.deepcopy(chain)
        record['chain_id'] = chain_id
        chains.append(record)
    for rule_id in rule_records:
        if rule_id.startswith('supp_r') and rule_id not in used:
            raise SchemaError('every_new_rule_must_be_used_by_a_new_chain')
    refine_out = []
    refine_ids = set()
    base_by_id = {c['chain_id']: c for c in combined['chains']}
    for refinement in refinements:
        if not isinstance(refinement, dict) or not re.match(r'^refine_\d+$', str(refinement.get('id', ''))):
            raise SchemaError('refinement_ids_must_be_refine_N')
        if refinement['id'] in refine_ids:
            raise SchemaError('refinement_ids_must_be_unique')
        if refinement.get('target_chain_id') not in base_by_id:
            raise SchemaError('refinement_target_chain_must_be_initial_chain')
        refine_ids.add(refinement['id'])
        refine_out.append(copy.deepcopy(refinement))
    qids = [q['id'] for q in questions['questions']]
    if len(responses) != len(qids):
        raise SchemaError('exactly_one_response_per_actual_question')
    seen_q, record_links = set(), {}
    for response in responses:
        if not isinstance(response, dict) or response.get('question_id') not in qids:
            raise SchemaError('response_must_reference_actual_question')
        if response['question_id'] in seen_q:
            raise SchemaError('exactly_one_response_per_actual_question')
        seen_q.add(response['question_id'])
        outcome = response.get('outcome')
        if outcome not in QUESTION_OUTCOMES:
            raise SchemaError('unknown_question_outcome')
        record_ids = response.get('record_ids', [])
        covered = response.get('covered_chain_ids', [])
        if not isinstance(record_ids, list) or not isinstance(covered, list):
            raise SchemaError('response_link_fields_require_lists')
        for rid in record_ids:
            record_links.setdefault(rid, []).append(response['question_id'])
        if outcome in ('new_explanation', 'refined_existing'):
            if not record_ids:
                raise SchemaError('both directions: record_ids must cite the new or refined records')
        elif outcome == 'already_covered':
            if record_ids or not covered:
                raise SchemaError('already_covered requires empty record_ids and covered initial chains')
            if any(cid not in base_chain_ids for cid in covered):
                raise SchemaError('already_covered must cite existing initial chains')
        for cid in covered:
            if outcome == 'already_covered' and cid not in base_chain_ids:
                raise SchemaError('covered_chain_ids_must_cite_initial_chains')
    for record in refine_out:
        for qid in record.get('question_ids', []):
            if qid not in qids:
                raise SchemaError('refinement_question_ids_must_reference_actual_questions')
            if qid not in record_links.get(record['id'], []):
                raise SchemaError('both directions: response record_ids must match record question links')
    for record in chains:
        if record['chain_id'].startswith('supp_c'):
            for qid in record.get('question_ids', []):
                if qid not in record_links.get(record['chain_id'], []):
                    raise SchemaError('both directions: response record_ids must match record question links')
    out = copy.deepcopy(combined)
    out['rules'] = [rule_records[r['id']] for r in combined['rules']] + [rule_records[r['id']] for r in new_rules]
    out['chains'] = chains
    out['refinements'] = refine_out
    out['initial_counts'] = copy.deepcopy(combined['initial_counts'])
    out['supplement_counts'] = {'rules': len(new_rules), 'chains': len(new_chains), 'refinements': len(refine_out)}
    out['question_responses'] = copy.deepcopy(responses)
    return out


def validate_verification(verdict, combined, public):
    if not isinstance(verdict, dict) or not isinstance(verdict.get('checks'), list):
        raise SchemaError('verification_requires_checks')
    if not isinstance(verdict.get('summary'), str) or not verdict['summary'].strip():
        raise SchemaError('verification_requires_bounded_summary')
    targets = [c['chain_id'] for c in combined['chains']]
    targets += [r['id'] for r in combined.get('refinements', [])]
    seen = set()
    for check in verdict['checks']:
        if not isinstance(check, dict) or check.get('target_id') not in targets:
            raise SchemaError('check_target_must_be_actual_chain_or_refinement')
        if check['target_id'] in seen:
            raise SchemaError('exactly_one_check_per_target')
        seen.add(check['target_id'])
        for dim in ('O', 'B', 'implication'):
            component = check.get(dim)
            if not isinstance(component, dict) or component.get('status') not in STATUSES:
                raise SchemaError('check_dimensions_require_status')
            evidence = component.get('evidence', [])
            if component['status'] != 'undetermined':
                if not isinstance(evidence, list) or not evidence:
                    raise SchemaError('evidence reference required for supported/refuted judgments')
                _evidence_list(evidence, public)
    missing = [t for t in targets if t not in seen]
    if missing:
        raise SchemaError('full verification requires every chain and refinement: missing %s' % missing[:3])
    return copy.deepcopy(verdict)


def _aggregate(statuses):
    if 'refuted' in statuses:
        return 'revoked'
    if statuses and all(s == 'supported' for s in statuses):
        return 'active'
    if 'supported' in statuses and 'undetermined' in statuses:
        return 'disputed'
    return 'pending'


def _concrete_chart(chart):
    if not isinstance(chart, str) or not chart.strip() or re.match(r'^chart(_[0-9]+)?$', chart.strip()):
        raise SchemaError('rule state scope requires a concrete image reference, not a generic chart id')


def build_rule_state(combined, verification, task, chart):
    _concrete_chart(chart)
    if verification is not None:
        targets = {c['chain_id'] for c in combined['chains']} | {r['id'] for r in combined.get('refinements', [])}
        seen = set()
        if not isinstance(verification, dict) or not isinstance(verification.get('checks'), list):
            raise SchemaError('full verification requires checks for every chain and refinement')
        for check in verification['checks']:
            if not isinstance(check, dict) or check.get('target_id') not in targets or check['target_id'] in seen:
                raise SchemaError('full verification requires unique checks for every chain and refinement')
            seen.add(check['target_id'])
        if seen != targets:
            raise SchemaError('full verification requires every chain and refinement')
        checks = {c['target_id']: c for c in verification['checks']}
    else:
        checks = {}
    rules = []
    for rule in combined['rules']:
        chain_checks, b_statuses = [], []
        for chain in combined['chains']:
            if chain.get('rule_id') != rule['id']:
                continue
            check = checks.get(chain['chain_id'])
            if check is not None:
                chain_checks.append(copy.deepcopy(check))
                b_statuses.append(check['B']['status'])
        rules.append({'rule_id': rule['id'], 'version': 1, 'status': _aggregate(b_statuses),
                      'text': rule.get('text', ''), 'component': rule.get('component', ''),
                      'conditions': rule.get('conditions', ''), 'checks': chain_checks, 'history': []})
    refinements = []
    for refinement in combined.get('refinements', []):
        check = checks.get(refinement['id'])
        target = next(c for c in combined['chains'] if c['chain_id'] == refinement['target_chain_id'])
        asserted = []
        if check is not None:
            asserted = [dim for dim in ('O', 'B', 'implication') if check[dim]['status'] != 'undetermined']
            statuses = [check[dim]['status'] for dim in asserted]
            status = 'refuted' if 'refuted' in statuses else ('supported' if statuses and all(s == 'supported' for s in statuses) else 'undetermined')
        else:
            status = 'pending'
        rule = next(r for r in combined['rules'] if r['id'] == target['rule_id'])
        refinements.append({'id': refinement['id'], 'target_chain_id': refinement['target_chain_id'],
                            'target_rule_id': target['rule_id'], 'target_rule_version': 1,
                            'status': status, 'applied_to_original': False,
                            'asserted_dimensions': asserted,
                            'condition_note': refinement.get('condition_note', ''),
                            'added_observations': copy.deepcopy(refinement.get('added_observations', [])),
                            'added_task_evidence': copy.deepcopy(refinement.get('added_task_evidence', []))})
    return {'scope': {'task_id': task, 'chart_ref': chart}, 'version': 1,
            'rules': rules, 'chains': copy.deepcopy(combined['chains']), 'refinements': refinements}


def save_state(path, state):
    path = Path(path)
    if path.exists():
        raise FileExistsError('rule_state_files_are_write_once')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')


def load_state(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_rules(state, context):
    task = context.get('task_id')
    chart = context.get('chart_ref')
    if task is None or chart is None:
        applicability = 'unknown'
    elif (task, chart) == (state['scope']['task_id'], state['scope']['chart_ref']):
        applicability = 'applicable'
    else:
        applicability = 'inapplicable'
    conditions = context.get('conditions', {})
    rules = []
    for record in state['rules']:
        usable = (applicability == 'applicable' and record['status'] == 'active'
                  and conditions.get(record['rule_id']) is True)
        rules.append({'rule_id': record['rule_id'], 'version': record['version'], 'status': record['status'],
                      'applicability': applicability, 'usable': usable,
                      'text': record.get('text', ''), 'conditions': record.get('conditions', ''),
                      'checks': copy.deepcopy(record.get('checks', [])),
                      'history': copy.deepcopy(record.get('history', []))})
    return {'version': state['version'], 'same_task_and_image': applicability == 'applicable',
            'condition_applicability': 'actor_must_check', 'rules': rules,
            'refinements': copy.deepcopy(state.get('refinements', []))}


