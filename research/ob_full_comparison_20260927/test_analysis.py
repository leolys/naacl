import importlib.util
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import state, pair, known_usage


LABEL = {'original_correct_label': 'A', 'options': [{'label': 'A', 'alignment_role': 'target'},
    {'label': 'B', 'alignment_role': 'misleading_trap'}, {'label': 'C', 'alignment_role': 'other'}]}


def result(option):
    return {'status': 'completed', 'choice': {'option_label': option, 'basis': 'synthetic test'}}


def test_scoring_states_preserve_null_and_failure():
    assert [state(result(v), LABEL) for v in ('A', 'B', 'C', None)] == ['target', 'trap', 'other', 'no_option']
    assert state({'status': 'interface_failed'}, LABEL) == 'interface_failed'
    assert state({'status': 'not_completed'}, LABEL) == 'not_completed'
    with pytest.raises(ValueError):
        state(result('hidden option'), LABEL)


def test_transitions_do_not_call_abstention_a_wrong_action():
    units = {str(i): {'family': 'synthetic'} for i in range(4)}
    labels = {k: LABEL for k in units}
    left = dict(zip(units, [result('B'), result('A'), result(None), result('A')]))
    right = dict(zip(units, [result('A'), result(None), result('A'), result('B')]))
    value = pair(left, right, list(units), units, labels)
    assert value['net_target'] == 0
    assert value['broad_transitions'] == {'wrong_to_target': 1, 'target_to_null_or_failure': 1,
                                         'null_or_failure_to_target': 1, 'target_to_wrong': 1}
    assert value['common_parsed_including_null']['n'] == 4
    assert value['both_nonnull_auxiliary']['n'] == 2


def test_usage_missing_fields_not_zero():
    assert not known_usage(None)
    assert not known_usage({})
    assert not known_usage({'total_tokens': 5})
    assert not known_usage({'prompt_tokens': True, 'completion_tokens': 0, 'total_tokens': 1})
    assert known_usage({'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
