import pytest
from format_replay import normalize


def test_explicit_submit_shortform_only():
    original = {"action": "submit", "brief_basis": "Choice complete"}
    assert normalize(original)["action"] == {"kind": "submit"}
    assert original["action"] == "submit"


def test_no_action_no_inferred_submit():
    for item in ({}, {"action": "select"}, {"action": "done"}, {"action": True}):
        with pytest.raises(ValueError):
            normalize(item)


def test_structured_action_unchanged():
    item = {"action": {"kind": "select", "option": "Route B"}}
    assert normalize(item) == item


def test_complete_flat_fill_preserves_model_value():
    item = {"action": "fill", "field": "note", "value": "model's exact visible basis"}
    assert normalize(item)["action"] == {"kind": "fill", "field": "note", "value": item["value"]}
    for bad in ({"action": "fill", "field": "note"}, {"action": "check", "field": "flag", "value": "true"}):
        with pytest.raises(ValueError):
            normalize(bad)
