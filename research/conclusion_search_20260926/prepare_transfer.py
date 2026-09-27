"""Offline packaging of fixed historical public tasks; never loads answers.

JPEG-to-PNG is transport encoding only: RGB dimensions and pixel bytes are
verified identical after decoding. The original JPEG is preserved verbatim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image


FIXED_CASES = ("b002", "pub013")
SOURCE_RELATIVE = Path("research/obc140_runtime_aligned_20260924/prepared/tasks")
EXPECTED_PUBLIC_KEYS = {
    "task_alias", "page_title", "user_goal", "chart_reference",
    "primary_field_label", "option_labels", "companion_fields",
    "completion_label", "policy_tables", "page_instructions",
}
FORBIDDEN_KEYS = {
    "gold", "ground_truth", "correct_value", "correct_action_id",
    "expected_action_id", "misleader_type", "misleading_context", "rationale",
    "csv_path", "source_csv", "misleading_action_ids", "scoring_outcome",
    "error_attribution", "action_space", "condition", "spec", "workflow_spec",
    "workflow_instruction", "action_id", "outcome", "evaluation_hidden_from_agent",
    "decision_reference", "initial_chains", "chains", "verification", "rule_state",
    "task_id", "task_alias", "chart_source", "source_sha256", "source_pages",
}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def assert_public(value, path="$"):
    if isinstance(value, dict):
        bad = set(value) & FORBIDDEN_KEYS
        if bad:
            raise ValueError("Forbidden online key at %s: %s" % (path, sorted(bad)))
        for key, item in value.items():
            assert_public(item, path + "." + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_public(item, "%s[%d]" % (path, index))


def make_context(public: dict) -> dict:
    if set(public) != EXPECTED_PUBLIC_KEYS:
        raise ValueError("Unexpected public projection keys")
    if not isinstance(public["user_goal"], str) or not public["user_goal"].strip():
        raise ValueError("Missing public user goal")
    options = public["option_labels"]
    if not isinstance(options, list) or not options or any(
            not isinstance(option, str) or not option for option in options):
        raise ValueError("Missing public options")
    if len(options) != len(set(options)):
        raise ValueError("Duplicate public option labels")
    # Only the synthetic task alias is removed. Business language is unchanged.
    task = {key: value for key, value in public.items() if key != "task_alias"}
    context = {
        "goal": public["user_goal"],
        "state": {
            "view_mode": "static_fullchart_public_task",
            "task": task,
            "current_selection": "",
        },
        "history": [],
        "options": list(options),
        "pending_proposal": None,
    }
    assert_public(context)
    return context


def save_json(path: Path, value):
    # New-only output: this helper cannot overwrite prior artifacts.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def prepare(workspace: Path, output: Path) -> dict:
    workspace = workspace.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Refusing to overwrite output: " + str(output))
    # Validate both public inputs before creating any output directory.
    inputs = []
    for case_id in FIXED_CASES:
        source = workspace / SOURCE_RELATIVE / case_id
        public_path = source / "public.json"
        chart_path = source / "chart.jpeg"
        public_bytes = public_path.read_bytes()
        chart_bytes = chart_path.read_bytes()
        public = json.loads(public_bytes.decode("utf-8"))
        context = make_context(public)
        with Image.open(chart_path) as image:
            if image.format != "JPEG":
                raise ValueError("Expected original JPEG: " + str(chart_path))
            rgb = image.convert("RGB")
            rgb.load()
        inputs.append((case_id, public_path, chart_path, public_bytes,
                       chart_bytes, context, rgb))

    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": "conclusion_search_transfer_inputs_v1",
        "selection": "fixed_historical_development_cases_not_holdout",
        "fixed_cases": list(FIXED_CASES),
        "online_context_keys": ["goal", "state", "history", "options", "pending_proposal"],
        "actor_selection_executed": False,
        "business_submission_executed": False,
        "source_inputs_unchanged": True,
        "model_service_max_pixels": 1605632,
        "service_processing_note": (
            "Full RGB PNG is transmitted without local resizing; the existing model "
            "service applies its own max_pixels preprocessing."
        ),
        "encoding_note": (
            "JPEG decoded to RGB then losslessly encoded as PNG for the existing "
            "image/png client. Decoded RGB bytes and dimensions are checked equal. "
            "No crop, resize, annotation or chart-content edit."
        ),
        "provenance_online": False,
        "cases": [],
    }
    for case_id, public_path, chart_path, public_bytes, chart_bytes, context, rgb in inputs:
        case_dir = output / case_id
        case_dir.mkdir()
        source_copy = case_dir / "source_chart.jpeg"
        shutil.copyfile(chart_path, source_copy)
        if source_copy.read_bytes() != chart_bytes:
            raise ValueError("Original JPEG preservation failed")
        png_path = case_dir / "chart.png"
        # Exclusive open makes the no-overwrite invariant local to this write.
        with png_path.open("xb") as stream:
            rgb.save(stream, format="PNG")
        with Image.open(png_path) as decoded:
            png_rgb = decoded.convert("RGB")
            png_rgb.load()
        same_size = png_rgb.size == rgb.size
        same_pixels = png_rgb.tobytes() == rgb.tobytes()
        if not same_size or not same_pixels:
            raise ValueError("Transport encoding changed decoded RGB pixels")
        context_path = case_dir / "public_context.json"
        save_json(context_path, context)
        case_manifest = {
            "case_id": case_id,
            "public_source": str(public_path),
            "chart_source": str(chart_path),
            "public_source_sha256": digest(public_bytes),
            "original_jpeg_sha256": digest(chart_bytes),
            "preserved_jpeg_sha256": digest(source_copy.read_bytes()),
            "png_sha256": digest(png_path.read_bytes()),
            "jpeg_decoded_rgb_sha256": digest(rgb.tobytes()),
            "png_decoded_rgb_sha256": digest(png_rgb.tobytes()),
            "decoded_rgb_equal": same_pixels,
            "dimensions_equal": same_size,
            "width": rgb.width,
            "height": rgb.height,
            "pixel_count": rgb.width * rgb.height,
            "context_file": "public_context.json",
            "context_sha256": digest(context_path.read_bytes()),
            "image_file": "chart.png",
            "preserved_original_file": "source_chart.jpeg",
            "source_public_keys_removed": ["task_alias"],
            "old_actor_proposal_included": False,
            "old_explanations_included": False,
            "hidden_scores_included": False,
        }
        # Confirm original files still match bytes read before preparation.
        if public_path.read_bytes() != public_bytes or chart_path.read_bytes() != chart_bytes:
            raise ValueError("Source changed during offline preparation")
        save_json(case_dir / "manifest.json", case_manifest)
        manifest["cases"].append(case_manifest)
    save_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "transfer_inputs")
    args = parser.parse_args()
    manifest = prepare(args.workspace, args.output)
    print(json.dumps({"output": str(args.output.resolve()),
                      "cases": [{"case_id": item["case_id"],
                                 "size": [item["width"], item["height"]],
                                 "decoded_rgb_equal": item["decoded_rgb_equal"]}
                                for item in manifest["cases"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
