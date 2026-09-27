"""Mock-only checks for offline label alignment, not semantic accuracy."""
from export_original_labels_offline import align

OPTIONS = [{'token': 'option_0', 'action_id': 'route_a', 'label': 'Route A', 'role': 'correct'},
           {'token': 'option_1', 'action_id': 'route_b', 'label': 'Route B', 'role': 'misleading_trap'}]

def test_same_public_projection():
    result = align(OPTIONS, ['Route A', 'Route B'])
    assert result['supported']
    assert result['original_correct_label'] == 'Route A'

def test_reorder_cannot_silently_pass():
    assert not align(OPTIONS, ['Route B', 'Route A'])['supported']

def test_ambiguous_cannot_silently_pass():
    dup = [{**o, 'label': 'Same'} for o in OPTIONS]
    assert not align(dup, ['Same', 'Same'])['supported']

def test_native_review_role_preserved():
    native = [{'token': 'option_0', 'label': 'Route A', 'review_role': 'correct'},
              {'token': 'option_1', 'label': 'Route B', 'review_role': 'misleading'}]
    got = align(native, ['Route A', 'Route B'])
    assert got['supported']
    assert got['options'][1]['review_role'] == 'misleading'
    assert got['options'][1]['alignment_role'] == 'misleading_trap'
