"""Small mock checks: label agreement is not execution success."""
from score_choices_offline import label_class

ALIGNMENT = {'supported': True, 'options': [
    {'label': 'Route A', 'alignment_role': 'correct'},
    {'label': 'Route B', 'alignment_role': 'misleading_trap'},
    {'label': 'Route C', 'alignment_role': 'neutral_or_irrelevant'}]}

def test_label_classes():
    assert label_class('Route A', ALIGNMENT) == 'matches_original_target'
    assert label_class('Route B', ALIGNMENT) == 'original_trap_option'
    assert label_class('Route C', ALIGNMENT) == 'other_original_option'

def test_no_choice_not_a_wrong_public_option():
    assert label_class(None, ALIGNMENT) == 'no_option'
    assert label_class('Unavailable', ALIGNMENT) == 'not_a_public_option'

def test_unsupported_stays_unscored():
    assert label_class('Route A', {'supported': False}) == 'unsupported_mapping'
