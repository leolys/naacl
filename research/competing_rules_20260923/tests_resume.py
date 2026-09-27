"""Offline resumer checks only; never invoke API or browser."""
import base64
import copy
import hashlib
import json

import pytest

from resume_interfaces import ACTION_ERROR, TARGET_ERROR, matching_sources, remaining_config, wire_image_bindings


def config():
    return {"model": "unchanged-model", "temperature": 0, "max_actor_calls": 7,
            "max_request_attempts": 150, "max_browser_operations": 300}


def test_remaining_budget_includes_prior_controls_and_replay():
    result = remaining_config(config(), config(), {"attempts": 44, "browser_operations": 61}, 26)
    assert result["max_request_attempts"] == 106
    assert result["max_browser_operations"] == 213


def test_budget_cannot_be_raised_or_model_changed():
    requested = dict(config(), max_request_attempts=500, max_browser_operations=900)
    result = remaining_config(config(), requested, {"attempts": 140, "browser_operations": 290}, 26)
    assert result["max_request_attempts"] == 10
    assert result["max_browser_operations"] == 0
    with pytest.raises(ValueError):
        remaining_config(config(), dict(config(), model="new-model"), {"attempts": 0, "browser_operations": 0}, 0)


def test_exact_exception_selection_includes_all_arms_without_gold(tmp_path):
    for name, error in (("case01_ordinary", TARGET_ERROR), ("case02_full", TARGET_ERROR),
                        ("case03_full", TARGET_ERROR + " extra"), ("case04_full", None)):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "trajectory.json").write_text(json.dumps({"error": error}), encoding="utf-8")
    assert [path.name for path in matching_sources(tmp_path)] == ["case01_ordinary", "case02_full"]


def test_flat_named_actions_selected_but_zero_argument_replay_not_duplicated(tmp_path):
    for name, action in (("case01_ordinary", "fill"), ("case02_full", "check"),
                         ("case03_full", "select"), ("case04_full", "submit"), ("case05_full", "observe")):
        directory = tmp_path / name
        (directory / "step_01" / "actor").mkdir(parents=True)
        (directory / "trajectory.json").write_text(json.dumps({"error": ACTION_ERROR}), encoding="utf-8")
        (directory / "step_01" / "actor" / "parsed.json").write_text(json.dumps({"action": action}), encoding="utf-8")
    assert [path.name for path in matching_sources(tmp_path)] == ["case01_ordinary", "case02_full", "case03_full"]


def request_fixture():
    context = {"task": {"task_alias": "case01"}, "state": {"current_selection": ""}}
    content = [{"type": "text", "text": json.dumps(context)}]
    for ref, content_bytes in (("chart_1", b"chart-bytes"), ("page_00", b"page-bytes")):
        content += [{"type": "text", "text": "Observation " + ref},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(content_bytes).decode()}}]
    request = {"messages": [{"role": "system", "content": "original"}, {"role": "user", "content": content}]}
    archive = {"context": context, "images": [{"ref": "chart_1", "file": "chart.png"}, {"ref": "page_00", "file": "page.png"}]}
    return request, archive


def test_actual_wire_binds_chart_and_page_not_archive_only():
    request, archive = request_fixture()
    result = wire_image_bindings(request, archive)
    assert result == {"chart_1": hashlib.sha256(b"chart-bytes").hexdigest(), "page_00": hashlib.sha256(b"page-bytes").hexdigest()}


def test_reject_context_mismatch():
    request, archive = request_fixture()
    archive = copy.deepcopy(archive)
    archive["context"]["state"]["current_selection"] = "changed"
    with pytest.raises(ValueError, match="wire text"):
        wire_image_bindings(request, archive)


def test_reject_fabricated_image_reference():
    request, archive = request_fixture()
    archive["images"][1]["ref"] = "unobserved_page"
    with pytest.raises(ValueError, match="wire observations"):
        wire_image_bindings(request, archive)
