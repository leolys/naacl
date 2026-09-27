"""Generate read-only Stage 2.5 dataset/run audits in a new destination.

The source release and historical run directories are never modified. Candidate
selection is a predeclared list and is not conditioned on historical model output.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .core import public_task_projection
from .runner import PAIR_INVARIANT_FIELDS, RELEASE_ROOT, REPOSITORY_ROOT, pair_invariant_differences
from .stage25_render_audit import DEFAULT_CANDIDATES, load_release_rows
from .validate_run import validate_run


HISTORICAL_RUNS = (
    "stage2_live_smoke_20260906T073005Z",
    "stage2_mock_smoke_20260906T0837Z",
    "stage2_live_smoke_20260906T1219Z",
    "stage2_live_smoke_20260906T1342Z",
)


def scoring_signature(row: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [
        (
            str(action.get("action_id") or ""),
            str(action.get("role") or ""),
            str(action.get("scoring_outcome") or ""),
        )
        for action in row.get("action_space") or []
    ]


def classify_pair_difference(left: dict[str, Any], right: dict[str, Any]) -> str:
    differences = pair_invariant_differences(left, right)
    if not differences:
        return "chart_only_in_audited_fields"
    left_public = public_task_projection(left, task_alias="audit")
    right_public = public_task_projection(right, task_alias="audit")
    public_changed = left_public != right_public
    score_semantics_changed = (
        str(left.get("expected_action_id") or "") != str(right.get("expected_action_id") or "")
        or scoring_signature(left) != scoring_signature(right)
    )
    if public_changed and score_semantics_changed:
        return "visible_target_or_options_and_scoring_semantics_changed"
    if public_changed:
        return "visible_option_wording_or_task_context_changed"
    if score_semantics_changed:
        return "hidden_action_id_or_scoring_mapping_changed"
    return "offline_metadata_or_explanation_changed"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = load_release_rows()

    pair_rows: list[dict[str, Any]] = []
    correct_positions: Counter[int] = Counter()
    for condition_slug in sorted(slug for condition, slug in rows if condition == "official140"):
        official = rows[("official140", condition_slug)]
        clean = rows[("clean140", condition_slug)]
        differences = pair_invariant_differences(official, clean)
        official_public = public_task_projection(official, task_alias="audit")
        clean_public = public_task_projection(clean, task_alias="audit")
        classification = classify_pair_difference(official, clean)
        if not differences:
            expected_id = str(official.get("expected_action_id") or "")
            expected_label = next(
                str(action.get("label") or "")
                for action in official.get("action_space") or []
                if str(action.get("action_id") or "") == expected_id
            )
            correct_positions[official_public["option_labels"].index(expected_label)] += 1
        pair_rows.append(
            {
                "task_slug": condition_slug,
                "different_fields": "|".join(differences),
                "public_projection_changed": str(official_public != clean_public).lower(),
                "visible_option_labels_changed": str(
                    official_public["option_labels"] != clean_public["option_labels"]
                ).lower(),
                "expected_action_id_changed": str(
                    official.get("expected_action_id") != clean.get("expected_action_id")
                ).lower(),
                "semantic_classification": classification,
            }
        )
    write_csv(output / "pair_field_differences.csv", pair_rows)

    candidate_rows: list[dict[str, Any]] = []
    for slug in DEFAULT_CANDIDATES:
        official = rows[("official140", slug)]
        clean = rows[("clean140", slug)]
        candidate_rows.append(
            {
                "task_slug": slug,
                "official_source": next(
                    str(path.relative_to(REPOSITORY_ROOT))
                    for path in (RELEASE_ROOT / "splits" / "official140").glob("*_tasks.jsonl")
                    if any(
                        json.loads(line).get("task_slug") == slug
                        for line in path.read_text(encoding="utf-8").splitlines()
                    )
                ),
                "pair_invariant": str(not pair_invariant_differences(official, clean)).lower(),
                "different_fields": "|".join(pair_invariant_differences(official, clean)),
                "workflow_instruction": str(official.get("workflow_instruction") or ""),
                "chart_reference": str(official.get("chart_reference") or ""),
                "visible_option_labels": " | ".join(
                    public_task_projection(official, task_alias="audit")["option_labels"]
                ),
                "task_readiness": str(official.get("task_readiness") or "legacy_unspecified"),
            }
        )
    write_csv(output / "candidate_spec_extract.csv", candidate_rows)

    classification_counts = Counter(row["semantic_classification"] for row in pair_rows)
    release_manifest = json.loads(
        (RELEASE_ROOT / "benchmark_manifest.json").read_text(encoding="utf-8")
    )
    dataset_summary = {
        "release_manifest_identity": {
            key: release_manifest.get(key)
            for key in ("release_id", "release_version", "status")
        },
        "pair_invariant_fields": list(PAIR_INVARIANT_FIELDS),
        "pairs_total": len(pair_rows),
        "chart_only_in_audited_fields": classification_counts["chart_only_in_audited_fields"],
        "differing_pairs": len(pair_rows)
        - classification_counts["chart_only_in_audited_fields"],
        "difference_classification_counts": dict(sorted(classification_counts.items())),
        "correct_option_position_after_public_label_sort": {
            str(index): correct_positions[index] for index in range(3)
        },
        "candidate_selection": {
            "slugs": list(DEFAULT_CANDIDATES),
            "selection_used_historical_model_outputs": False,
        },
    }
    (output / "dataset_summary.json").write_text(
        json.dumps(dataset_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    run_root = REPOSITORY_ROOT / "research" / "decision_evidence_audit" / "runs"
    historical = []
    for run_name in HISTORICAL_RUNS:
        report = validate_run(run_root / run_name)
        historical.append(
            {
                "run_id": run_name,
                "valid": report["valid"],
                "errors": report["errors"],
                "warnings": report["warnings"],
                "counts": report["counts"],
                "provenance": report["provenance"],
            }
        )
    (output / "historical_integrity_recompute.json").write_text(
        json.dumps({"source_runs_modified": False, "runs": historical}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(dataset_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
