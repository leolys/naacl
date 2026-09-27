"""No-network checks for the provider-only migration and bounded panel."""
import json

import pytest
import run_selection as pilot
from panel_core import read


def test_fixed_panel_and_call_cap():
    assert pilot.TASKS == ("b001", "pub013")
    assert len(pilot.MODELS) == 3
    assert sum(pilot.configuration(m)["max_request_attempts"] for m in pilot.MODELS) == 24
    assert all(pilot.configuration(m)["max_attempts_per_call"] == 1 for m in pilot.MODELS)


def test_original_prompt_and_inference_settings_are_unchanged():
    old = read(pilot.PANEL / "config.json")
    changed = {"protocol", "endpoint", "model", "proxy", "max_attempts_per_call", "max_request_attempts"}
    for model in pilot.MODELS:
        new = pilot.configuration(model)
        assert all(new[k] == v for k, v in old.items() if k not in changed)
        assert new["endpoint"] == "https://api.apiyi.com/v1/chat/completions"
        assert new["proxy"] is None
        assert "sk-" not in json.dumps(new)


def test_no_unlisted_model_or_task():
    with pytest.raises(ValueError):
        pilot.configuration("unlisted")
    with pytest.raises(ValueError):
        pilot.run("gpt-5.6-sol", "b002")


def test_both_selected_cases_exist_with_public_charts():
    catalog = read(pilot.PANEL / "catalog.json")
    indexed = {t["task_slug"]: t for t in catalog["tasks"]}
    for slug in pilot.TASKS:
        entry = indexed[slug]
        assert (pilot.PANEL / entry["chart_file"]).is_file()
        public = read(pilot.PANEL / entry["public_file"])
        record = {"public_task": public, "chart_file": str(pilot.PANEL / entry["chart_file"])}
        _, context, images = pilot.runner.phase_input("proposal", record)
        assert context["state"]["current_selection"] == "" and context["history"] == []
        assert len(images) == 1 and "ground_truth" not in json.dumps(context)
