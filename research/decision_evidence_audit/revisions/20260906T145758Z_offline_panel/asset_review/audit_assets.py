"""Read-only primary-asset audit; stdout only, never reads method outputs.

Run with the existing misleading_webagent_eval Python environment. This checks
metadata equality, not image semantics; the latter is recorded after view_image
inspection in candidate_qualification.md. No model, browser, network or GPU use.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[5]
RELEASE = ROOT / "web_agent_benchmark/benchmark_v2_open"
SELECTED = ("b003", "b011", "b012", "env003", "env004", "env027", "pub030")
REVIEWED_OTHERS = ("b013", "pub001", "pub009", "pub020", "pub031", "pub032", "health001", "env035")
# The existing runner's audited fields, not a new release contract.
FIELDS = ("task_id", "case_id", "page_title", "workflow_instruction", "chart_reference",
          "ground_truth", "intermediate_decision", "primary_action", "companion_actions",
          "action_space", "expected_action_id", "misleading_action_ids",
          "fallback_scoring", "completion_action")


def main() -> None:
    indexed = {}
    for arm in ("official140", "clean140"):
        for path in sorted((RELEASE / "splits" / arm).glob("*_tasks.jsonl")):
            for line_number, text in enumerate(path.read_text().splitlines(), 1):
                row = json.loads(text)
                indexed[(arm, row["task_slug"])] = (row, path, line_number)
    results = []
    for slug in SELECTED + REVIEWED_OTHERS:
        official, _, _ = indexed[("official140", slug)]
        clean, _, _ = indexed[("clean140", slug)]
        arms = []
        for arm in ("official140", "clean140"):
            row, path, line_number = indexed[(arm, slug)]
            figure = ROOT / row["chart_asset"]["figure_path"]
            with Image.open(figure) as im:
                size, mode = list(im.size), im.mode
            source_dir = "official_benchmark_v1" if arm == "official140" else "clean_benchmark_v1"
            source_path = ROOT / "web_agent_benchmark" / source_dir / path.name
            source_matches = []
            if source_path.exists():
                for source_line, raw in enumerate(source_path.read_text().splitlines(), 1):
                    source = json.loads(raw)
                    if source.get("case_id") == row.get("case_id"):
                        source_matches.append({
                            "source_file": str(source_path.relative_to(ROOT)),
                            "line": source_line,
                            "task_id_matches": source.get("task_id") == row.get("task_id"),
                            "public_goal_matches": source.get("workflow_instruction") == row.get("workflow_instruction"),
                        })
            arms.append({
                "condition": arm, "spec_file": str(path.relative_to(ROOT)), "line": line_number,
                "figure_path": str(figure.relative_to(ROOT)), "image_size": size, "image_mode": mode,
                "source_row_matches": source_matches,
            })
        results.append({
            "task_slug": slug, "proposed": slug in SELECTED, "case_id": official.get("case_id"),
            "readiness": official.get("task_readiness", "legacy_unspecified"),
            "source_dataset_field": official.get("source_dataset"),
            "pair_differences_in_runner_fields": [f for f in FIELDS if official.get(f) != clean.get(f)],
            "workflow_instruction": official.get("workflow_instruction"),
            "chart_reference": official.get("chart_reference"),
            "option_labels": sorted(a["label"] for a in official["action_space"]),
            "completion_label": official.get("completion_action", {}).get("label"),
            "hidden_companions_count": sum(a.get("input_type") == "hidden" for a in official.get("companion_actions", [])),
            "arms": arms,
        })
    print(json.dumps({
        "reference_run": "stage2_live_smoke_20260906T1342Z",
        "selected_base_tasks": len(SELECTED), "inspected_asset_pairs": len(results),
        "method_results_read": False, "model_calls": 0, "browser_transitions": 0,
        "pair_checks_are_not_image_semantics_checks": True, "results": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
