import copy
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidate_v3_runner_tests', HERE / 'runner.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


@pytest.fixture
def setup_run(tmp_path, monkeypatch):
    config = r.wire.read(HERE / 'config.json')
    r.wire.dump(tmp_path / 'config.json', config)
    monkeypatch.setattr(r, 'HERE', tmp_path)

    def freeze(output):
        r.wire.dump(output / 'runtime.json', {'source_sha256': {}, 'mode': 'test_fixture'})
        r.wire.dump(output / 'prompt_templates.json', r.prompts.PROMPTS)

    monkeypatch.setattr(r, 'freeze_sources', freeze)
    return tmp_path


class FixtureAPI:
    instances = []

    def __init__(self, config, budget):
        self.budget = budget
        self.calls = []
        self.instances.append(self)

    def call(self, folder, task_id, phase, prompt, context, images):
        folder.mkdir(parents=True)
        self.budget.current_folder = folder
        self.budget.charge({'task_slug': task_id, 'phase': phase, 'round': folder.name, 'attempt': 1})
        r.wire.dump(folder / 'response_01.json', {'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})
        self.budget.reconcile()
        self.budget.current_folder = None
        stage = folder.parent.name
        self.calls.append((task_id, stage, copy.deepcopy(context)))
        if stage == 'generation':
            return {'rules': [{'id': 'r1', 'text': 'Fixture interpretation, not actual chart analysis.',
                'component': 'fixture only', 'conditions': 'Synthetic interface test'}],
                'chains': [{'rule_id': 'r1', 'observations': [{'ref': 'chart_1', 'location': 'fixture',
                'content': 'Synthetic observation, not a model result.'}], 'task_evidence': [],
                'claim': 'The first public option is the fixture candidate.',
                'option_label': context['task']['option_labels'][0]}], 'unresolved_questions': []}
        if stage == 'questions':
            return {'questions': [], 'summary': 'Synthetic no-question response.'}
        if stage == 'verification':
            checks = []
            for chain in context['arguments']['chains']:
                checks.append({'target_id': chain['chain_id'],
                    'O': {'status': 'undetermined', 'evidence': [], 'reason': 'Fixture only.'},
                    'B_applicability': {'status': 'undetermined', 'evidence': [], 'reason': 'Fixture only.'},
                    'conditional_inference': {'status': 'valid',
                        'premise_ids': ['chain:' + chain['chain_id'], 'rule:' + chain['rule_id']],
                        'missing_premises': [], 'reason': 'Synthetic conditional check.'}})
            return {'schema_version': 'explanation_verification_v3', 'chain_checks': checks,
                    'refinement_checks': [], 'summary': 'Fixture only, not a scientific result.'}
        raise AssertionError('Zero questions should skip the supplement API call')


def test_prepare_no_client_or_credential(setup_run, monkeypatch):
    monkeypatch.delenv('MODEL_API_KEY', raising=False)

    def no_client(*args):
        raise AssertionError('Preparation must not construct an API client')

    summary = r.run(setup_run / 'prepare', api_factory=no_client)
    assert summary['request_attempts'] == 0
    assert summary['evidence_mode'] == 'preparation_only'
    for task_id in r.FIXED_IDS:
        context = r.wire.read(setup_run / 'prepare/cases' / task_id / 'prepared_first_context.json')
        assert 'initial_arguments' not in context
        assert 'base_arguments' not in context
        assert context['history'] == []
        assert context['state']['current_selection'] == ''
        assert set(context['decision_reference']) == {'task_goal', 'proposed_option'}


def test_fresh_chain_pipeline_and_empty_question_skip(setup_run):
    summary = r.run(setup_run / 'fixture', live=True, api_factory=FixtureAPI)
    assert summary['status'] == 'mock_completed'
    assert summary['request_attempts'] == 9
    for task_id in r.FIXED_IDS:
        result = r.wire.read(setup_run / 'fixture/cases' / task_id / 'result.json')
        assert result['initial_arguments']['chains'][0]['claim'].startswith('The first public option')
        assert result['combined']['chains'] == result['initial_arguments']['chains']
        assert result['rule_state']['action_authorized'] is False
        assert result['rule_state']['rules'][0]['status'] == 'pending'
        assert result['stages']['supplement']['output_source'].startswith('deterministic_empty')
    for _, stage, context in FixtureAPI.instances[-1].calls:
        if stage == 'verification':
            assert 'decision_reference' not in context
            assert 'counterquestions' not in context
            for chain in context['arguments']['chains']:
                assert not {'claim_kind', 'proposal_relation', 'relationship', 'question_ids'} & set(chain)


def test_no_candidate_is_explicit_stop_not_fabrication(setup_run):
    class EmptyAPI(FixtureAPI):
        def call(self, *args):
            value = super().call(*args)
            if args[0].parent.name == 'generation':
                return {'rules': [], 'chains': [], 'unresolved_questions': [
                    {'id': 'gap1', 'question': 'What item is shown?', 'reason': 'Fixture missing identity.'}]}
            return value

    summary = r.run(setup_run / 'empty', live=True, api_factory=EmptyAPI)
    assert summary['request_attempts'] == 3
    assert {x['status'] for x in summary['cases']} == {'no_complete_candidate'}
    assert all(len(x.calls) == 3 for x in EmptyAPI.instances[-1:])


def test_structure_failure_not_retried_or_silently_repaired(setup_run):
    class BadAPI(FixtureAPI):
        def call(self, *args):
            value = super().call(*args)
            if args[0].parent.name == 'generation':
                value['chains'][0]['claim_kind'] = 'underdetermined'
            return value

    summary = r.run(setup_run / 'bad', live=True, api_factory=BadAPI)
    assert summary['request_attempts'] == 3
    assert all(x['status'] == 'failed_stage_no_quality_retry' for x in summary['cases'])
    raw = r.wire.read(setup_run / 'bad/cases/b001/generation/raw.json')
    assert raw['chains'][0]['claim_kind'] == 'underdetermined'


def test_existing_output_and_expanded_budget_rejected(setup_run):
    existing = setup_run / 'existing'
    existing.mkdir()
    with pytest.raises(ValueError):
        r.run(existing)
    config = r.wire.read(setup_run / 'config.json')
    config['max_request_attempts'] = 17
    with pytest.raises(ValueError):
        r.validate_config(config)


def test_context_projection_rejects_hidden_public_field():
    inputs = r.load_case('b001')
    inputs['task']['gold'] = 'DO_NOT_SEND'
    with pytest.raises((ValueError, AssertionError)):
        r.build_context('generation', inputs, {})


def test_authorization_cannot_be_reset_by_another_output(setup_run):
    r.claim_live_authorization(setup_run / 'first')
    with pytest.raises(FileExistsError):
        r.claim_live_authorization(setup_run / 'second')
