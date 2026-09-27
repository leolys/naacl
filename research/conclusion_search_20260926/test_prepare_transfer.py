import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image


SPEC = importlib.util.spec_from_file_location("prepare_transfer", Path(__file__).with_name("prepare_transfer.py"))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def sample_public():
    return {
        "task_alias": "task_example", "page_title": "Route intake",
        "user_goal": "Route the item with the largest displayed value.",
        "chart_reference": "Use the chart.", "primary_field_label": "Route",
        "option_labels": ["Route A", "Route B"], "companion_fields": [],
        "completion_label": "Submit Form", "policy_tables": [],
        "page_instructions": [],
    }


def test_context_has_exact_public_shape_and_no_alias():
    public = sample_public()
    context = M.make_context(public)
    assert set(context) == {"goal", "state", "history", "options", "pending_proposal"}
    assert context["state"]["task"] == {k: v for k, v in public.items() if k != "task_alias"}
    assert "task_alias" in public  # original object was not modified
    assert context["history"] == []
    assert context["state"]["current_selection"] == ""
    assert context["pending_proposal"] is None
    assert context["options"] == public["option_labels"]


@pytest.mark.parametrize("key", ["gold", "decision_reference", "scoring_outcome", "task_id"])
def test_forbidden_nested_keys_are_rejected(key):
    public = sample_public()
    public["companion_fields"] = [{key: "must not reach online context"}]
    with pytest.raises(ValueError, match="Forbidden online key"):
        M.make_context(public)


def test_unexpected_projection_is_rejected():
    public = sample_public()
    public["old_explanation"] = "not public task"
    with pytest.raises(ValueError, match="Unexpected public projection"):
        M.make_context(public)


def test_prepare_preserves_pixels_source_and_refuses_overwrite(tmp_path):
    workspace = tmp_path / "workspace"
    originals = {}
    for case_id in M.FIXED_CASES:
        source = workspace / M.SOURCE_RELATIVE / case_id
        source.mkdir(parents=True)
        (source / "public.json").write_text(json.dumps(sample_public()), encoding="utf-8")
        image = Image.new("RGB", (17, 11), (32, 110, 204))
        image.putpixel((3, 4), (230, 11, 80))
        image.save(source / "chart.jpeg", format="JPEG")
        originals[case_id] = (source / "chart.jpeg").read_bytes()
    output = tmp_path / "output"
    manifest = M.prepare(workspace, output)
    assert manifest["fixed_cases"] == list(M.FIXED_CASES)
    for record in manifest["cases"]:
        case_id = record["case_id"]
        assert record["decoded_rgb_equal"] is True
        assert record["jpeg_decoded_rgb_sha256"] == record["png_decoded_rgb_sha256"]
        assert (output / case_id / "source_chart.jpeg").read_bytes() == originals[case_id]
        assert (workspace / M.SOURCE_RELATIVE / case_id / "chart.jpeg").read_bytes() == originals[case_id]
        context = json.loads((output / case_id / "public_context.json").read_text(encoding="utf-8"))
        M.assert_public(context)
        assert str(workspace) not in json.dumps(context)
    snapshot = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        M.prepare(workspace, output)
    assert (output / "manifest.json").read_bytes() == snapshot
