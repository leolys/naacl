from evaluate import paired, state


def result(choice=None, status='completed'):
    return {'status': status, 'choice': {'option_label': choice}}


LABEL = {'original_correct_label': 'A', 'options': [
    {'label': 'A', 'alignment_role': 'correct'}, {'label': 'B', 'alignment_role': 'misleading_trap'},
    {'label': 'C', 'alignment_role': 'neutral_or_irrelevant'}]}


def test_original_domain_alignment_does_not_require_native_role_name():
    from evaluate import HERE, read
    labels = read(HERE / 'offline/labels.json')['tasks']
    for task in labels.values():
        for option in task['options']:
            got = state(result(option['label']), task)
            assert got in ('target', 'trap', 'other')


def test_state_not_null_is_not_automatically_correct():
    assert state(result('A'), LABEL) == 'target'
    assert state(result('B'), LABEL) == 'trap'
    assert state(result('C'), LABEL) == 'other'
    assert state(result(), LABEL) == 'no_option'
    assert state(result(status='interface_failed'), LABEL) == 'interface_failed'


def test_null_in_common_and_engineering_separate():
    ids = ['one', 'two', 'three', 'four']
    left = dict(zip(ids, [result(), result(status='interface_failed'), result('A'), result('B')]))
    right = dict(zip(ids, [result('A'), result('A'), result('C'), result('A')]))
    units = {key: {'family': 'x' if key != 'four' else 'y'} for key in ids}
    got = paired(left, right, ids, units, {key: LABEL for key in ids})
    assert got['net_target'] == 2
    assert got['positive_net_families'] == 2
    assert got['common_parsed_including_null'] == {'n': 3, 'net_target': 1}
    assert got['both_nonnull_auxiliary'] == {'n': 2, 'net_target': 0}
    assert got['broad_transitions']['null_or_failure_to_target'] == 2
    assert got['broad_transitions']['target_to_wrong'] == 1
    assert got['broad_transitions']['wrong_to_target'] == 1
