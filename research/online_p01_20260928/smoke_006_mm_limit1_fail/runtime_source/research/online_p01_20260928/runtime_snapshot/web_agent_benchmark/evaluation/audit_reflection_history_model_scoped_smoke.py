#!/usr/bin/env python3
"""Audit the four Sonnet cells used by the model-scoped Gate 1."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation.audit_reflection_history_stage import (
    audit_cell,
    audit_identity_events,
    secret_scan,
)
from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    DEFAULT_SMOKE_OUTPUT_ROOT,
    DEFAULT_SONNET_AUX_SMOKE_OUTPUT_ROOT,
    MODEL_CONFIGS,
    build_smoke_manifest,
    build_sonnet_auxiliary_smoke_manifest,
    is_retryable_interface_error,
    read_jsonl,
    runtime_routes,
    sha256_file,
    write_json,
)


SONNET_MODEL = "claude_sonnet_4_6_litellm"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def inspect_attempt_evidence(
    *,
    root: Path,
    expected_manifest: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    manifest_by_id = {
        str(cell["cell_id"]): cell for cell in expected_manifest
    }
    run_ids = {
        str((row.get("pilot_cell") or {}).get("cell_id") or "")
        for row in runs
    }
    attempts = read_jsonl(root / "attempt_manifest.jsonl")
    checkpoints = read_jsonl(root / "checkpoint_manifest.jsonl")
    attempt_dirs = sorted(root.glob("cells/*/attempt_*"))
    status_paths = sorted(root.glob("cells/*/attempt_*/attempt_status.json"))
    result_paths = sorted(root.glob("cells/*/attempt_*/result.json"))
    physical_dirs = {
        str(path.relative_to(root))
        for path in attempt_dirs
        if path.is_dir()
    }
    status_by_dir: dict[str, dict[str, Any]] = {}
    for path in status_paths:
        status = load_json(path)
        relative = str(status.get("attempt_dir") or "")
        if relative in status_by_dir:
            errors.append(f"{root.name}: duplicate attempt status {relative!r}")
        status_by_dir[relative] = status
        if path.parent.resolve() != (root / relative).resolve():
            errors.append(
                f"{root.name}: attempt status is not stored in declared path "
                f"{relative!r}"
            )
    manifest_by_dir: dict[str, dict[str, Any]] = {}
    for status in attempts:
        relative = str(status.get("attempt_dir") or "")
        if relative in manifest_by_dir:
            errors.append(
                f"{root.name}: duplicate attempt manifest record {relative!r}"
            )
        manifest_by_dir[relative] = status
    if manifest_by_dir != status_by_dir:
        errors.append(
            f"{root.name}: attempt manifest does not exactly match status files"
        )
    if physical_dirs != set(status_by_dir):
        errors.append(
            f"{root.name}: attempt directories do not exactly match status files"
        )
    result_dirs = {
        str(path.parent.relative_to(root)) for path in result_paths
    }
    if result_dirs != physical_dirs:
        errors.append(
            f"{root.name}: attempt directories do not exactly match result files"
        )

    consumed_by_cell: dict[str, list[tuple[int, str, dict[str, Any]]]] = {}
    attempt_results_by_dir: dict[str, dict[str, Any]] = {}
    for relative, status in status_by_dir.items():
        cell_id = str(status.get("cell_id") or "")
        cell = manifest_by_id.get(cell_id)
        if cell is None:
            errors.append(
                f"{root.name}: attempt status references unknown cell {cell_id!r}"
            )
            continue
        if cell_id not in run_ids:
            errors.append(
                f"{root.name}: attempt status has no aggregate result for {cell_id}"
            )
        if not relative.startswith(f"cells/{cell_id}/attempt_"):
            errors.append(f"{cell_id}: attempt directory belongs to another cell")
        attempt = int(status.get("attempt") or 0)
        if attempt not in {1, 2, 3}:
            errors.append(f"{cell_id}: invalid attempt index {attempt}")
        consumed = status.get("formal_attempt_consumed") is True
        aborted = status.get("availability_aborted") is True
        if consumed == aborted:
            errors.append(
                f"{cell_id}: consumed/availability flags are not complementary"
            )
        if consumed:
            consumed_by_cell.setdefault(cell_id, []).append(
                (attempt, relative, status)
            )
        attempt_path = root / relative
        events = read_jsonl(attempt_path / "model_identity_events.jsonl")
        request_count = int(status.get("actual_http_request_count") or 0)
        if len(events) != request_count:
            errors.append(f"{cell_id}: attempt event/request counts differ")
        deployment = str(MODEL_CONFIGS[cell["model"]]["deployment_id"])
        errors.extend(
            f"{cell_id}: HTTP {message}"
            for message in audit_identity_events(
                events,
                expected_deployment=deployment,
            )
        )
        result_path = attempt_path / "result.json"
        if result_path.is_file():
            attempt_row = load_json(result_path)
            attempt_results_by_dir[relative] = attempt_row
            if (attempt_row.get("pilot_cell") or {}).get("cell_id") != cell_id:
                errors.append(f"{cell_id}: attempt result cell differs from status")
            if int(attempt_row.get("pilot_attempt") or 0) != attempt:
                errors.append(
                    f"{cell_id}: attempt result index differs from status"
                )
            if attempt_row.get("pilot_attempt_dir") != relative:
                errors.append(
                    f"{cell_id}: attempt result directory differs from status"
                )
            if attempt_row.get("outcome") != status.get("outcome"):
                errors.append(
                    f"{cell_id}: attempt outcome differs from status"
                )
            if attempt_row.get("error_attribution") != status.get(
                "error_attribution"
            ):
                errors.append(
                    f"{cell_id}: attempt error attribution differs from status"
                )
            if int(
                attempt_row.get("pilot_actual_http_request_count") or 0
            ) != request_count:
                errors.append(
                    f"{cell_id}: attempt HTTP count differs from status"
                )
            errors.extend(
                f"{cell_id} attempt {attempt}: {message}"
                for message in audit_cell(
                    root=root,
                    cell=cell,
                    row=attempt_row,
                )
            )

    for cell_id, consumed in consumed_by_cell.items():
        indices = [attempt for attempt, _, _ in consumed]
        if len(indices) != len(set(indices)):
            errors.append(f"{cell_id}: duplicate consumed attempt index")
            continue
        ordered = sorted(consumed)
        if [attempt for attempt, _, _ in ordered] != list(
            range(1, len(ordered) + 1)
        ):
            errors.append(f"{cell_id}: consumed attempts are not contiguous")

    checkpoint_by_cell: dict[str, dict[str, Any]] = {}
    for checkpoint in checkpoints:
        cell_id = str(checkpoint.get("cell_id") or "")
        if cell_id in checkpoint_by_cell:
            errors.append(f"{root.name}: duplicate checkpoint for {cell_id}")
        checkpoint_by_cell[cell_id] = checkpoint
    if set(checkpoint_by_cell) != run_ids:
        errors.append(
            f"{root.name}: checkpoints do not exactly match aggregate results"
        )

    for row in runs:
        cell_id = str((row.get("pilot_cell") or {}).get("cell_id") or "")
        relative = str(row.get("pilot_attempt_dir") or "")
        status = status_by_dir.get(relative)
        if status is None:
            errors.append(f"{cell_id}: chosen result has no matching status")
            continue
        if status.get("formal_attempt_consumed") is not True:
            errors.append(f"{cell_id}: chosen result points to unconsumed attempt")
        if int(status.get("attempt") or 0) != int(
            row.get("pilot_attempt") or 0
        ):
            errors.append(f"{cell_id}: chosen attempt number differs from status")
        if status.get("cell_id") != cell_id:
            errors.append(f"{cell_id}: chosen status cell differs")
        request_count = int(row.get("pilot_actual_http_request_count") or 0)
        if request_count < 1:
            errors.append(f"{cell_id}: chosen attempt made zero HTTP requests")
        if int(status.get("actual_http_request_count") or 0) != request_count:
            errors.append(f"{cell_id}: chosen HTTP count differs from status")
        if status.get("outcome") != row.get("outcome"):
            errors.append(f"{cell_id}: chosen outcome differs from status")
        consumed = sorted(consumed_by_cell.get(cell_id) or [])
        chosen_attempt = int(row.get("pilot_attempt") or 0)
        if not consumed:
            errors.append(f"{cell_id}: no consumed attempts")
        else:
            max_consumed = consumed[-1][0]
            if chosen_attempt != max_consumed:
                errors.append(
                    f"{cell_id}: chosen attempt is not the final consumed attempt"
                )
            for prior_attempt, prior_relative, _ in consumed[:-1]:
                prior_row = attempt_results_by_dir.get(prior_relative)
                if prior_row is None or not is_retryable_interface_error(
                    prior_row
                ):
                    errors.append(
                        f"{cell_id}: consumed attempt {prior_attempt} before "
                        "the chosen attempt is not a retryable interface error"
                    )
            chosen_result_for_rule = attempt_results_by_dir.get(relative)
            if (
                chosen_attempt < 3
                and chosen_result_for_rule is not None
                and is_retryable_interface_error(chosen_result_for_rule)
            ):
                errors.append(
                    f"{cell_id}: retryable interface result was selected before "
                    "the retry budget was exhausted"
                )
        identity = row.get("pilot_identity_audit") or {}
        if identity.get("valid") is not True:
            errors.append(f"{cell_id}: chosen identity audit is not valid")
        result_path = root / relative / "result.json"
        if not result_path.is_file():
            errors.append(f"{cell_id}: chosen attempt result.json is missing")
        elif load_json(result_path) != row:
            errors.append(
                f"{cell_id}: chosen result differs from consumed attempt result"
            )
        events = read_jsonl(
            root / relative / "model_identity_events.jsonl"
        )
        if len(events) != request_count:
            errors.append(f"{cell_id}: chosen event/request counts differ")
        if any(event.get("result") != "success" for event in events):
            errors.append(
                f"{cell_id}: chosen attempt contains a non-success HTTP event"
            )
        deployment = str(
            MODEL_CONFIGS[(row.get("pilot_cell") or {}).get("model")][
                "deployment_id"
            ]
        )
        for index, event in enumerate(events, 1):
            if event.get("response_model") != deployment:
                errors.append(
                    f"{cell_id}: chosen event {index} response model differs"
                )
        checkpoint = checkpoint_by_cell.get(cell_id)
        if checkpoint is not None:
            expected_checkpoint = {
                "condition_order": (row.get("pilot_cell") or {}).get(
                    "condition_order"
                ),
                "attempt_count": len(consumed),
                "chosen_attempt": chosen_attempt,
                "outcome": row.get("outcome"),
                "error_attribution": row.get("error_attribution"),
            }
            for key, expected in expected_checkpoint.items():
                if checkpoint.get(key) != expected:
                    errors.append(
                        f"{cell_id}: checkpoint {key} differs from chosen result"
                    )
    return errors


def inspect_cells(
    *,
    root: Path,
    manifest_name: str,
    expected_manifest: list[dict[str, Any]],
    selected_cells: list[dict[str, Any]],
    experiment_kind: str,
    strict_cell_set: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    manifest_path = root / manifest_name
    if not manifest_path.is_file():
        return [], [f"{root.name}: {manifest_name} is missing"]
    if read_jsonl(manifest_path) != expected_manifest:
        errors.append(f"{root.name}: smoke manifest differs from frozen mapping")
    expected_manifest_ids = {
        str(cell["cell_id"]) for cell in expected_manifest
    }
    selected_ids = {str(cell["cell_id"]) for cell in selected_cells}
    runs = read_jsonl(root / "runs.jsonl")
    run_ids = [
        str((row.get("pilot_cell") or {}).get("cell_id") or "")
        for row in runs
    ]
    duplicate_run_ids = sorted(
        cell_id for cell_id, count in Counter(run_ids).items() if count > 1
    )
    if duplicate_run_ids:
        errors.append(f"{root.name}: duplicate run cells {duplicate_run_ids}")
    unknown_run_ids = sorted(set(run_ids) - expected_manifest_ids)
    if unknown_run_ids:
        errors.append(f"{root.name}: runs contain unknown cells {unknown_run_ids}")
    if strict_cell_set and set(run_ids) != selected_ids:
        errors.append(f"{root.name}: runs do not exactly match auxiliary cells")
    aggregate_rows = {
        cell_id: row for cell_id, row in zip(run_ids, runs)
    }
    chosen_paths = sorted(root.glob("cells/*/chosen_result.json"))
    chosen_ids = [path.parent.name for path in chosen_paths]
    unknown_chosen_ids = sorted(set(chosen_ids) - expected_manifest_ids)
    if unknown_chosen_ids:
        errors.append(
            f"{root.name}: chosen results contain unknown cells "
            f"{unknown_chosen_ids}"
        )
    if len(chosen_ids) != len(set(chosen_ids)):
        errors.append(f"{root.name}: duplicate chosen-result cells")
    if set(chosen_ids) != set(run_ids):
        errors.append(f"{root.name}: runs and chosen-result cells differ")
    if strict_cell_set and set(chosen_ids) != selected_ids:
        errors.append(
            f"{root.name}: chosen results do not exactly match auxiliary cells"
        )
    artifact_cell_ids = {
        path.name
        for path in (root / "cells").glob("*")
        if path.is_dir() and any(path.iterdir())
    }
    unknown_artifact_ids = sorted(artifact_cell_ids - expected_manifest_ids)
    if unknown_artifact_ids:
        errors.append(
            f"{root.name}: cell artifacts exist outside the manifest "
            f"{unknown_artifact_ids}"
        )
    if strict_cell_set and artifact_cell_ids != selected_ids:
        errors.append(
            f"{root.name}: artifact cells do not exactly match auxiliary cells"
        )
    errors.extend(
        inspect_attempt_evidence(
            root=root,
            expected_manifest=expected_manifest,
            runs=runs,
        )
    )

    config_path = root / "pilot_run_config.json"
    routes_path = root / "runtime_routes.json"
    if not config_path.is_file() or not routes_path.is_file():
        errors.append(f"{root.name}: non-formal run configuration is incomplete")
    else:
        config = load_json(config_path)
        routes = load_json(routes_path)
        expected_config = {
            "experiment_kind": experiment_kind,
            "manifest_path": manifest_name,
            "manifest_sha256": sha256_file(manifest_path),
            "runtime_routes_path": "runtime_routes.json",
            "runtime_routes_sha256": sha256_file(routes_path),
            "credentials_persisted": False,
        }
        if config != expected_config:
            errors.append(f"{root.name}: non-formal run configuration differs")
        if routes != runtime_routes():
            errors.append(f"{root.name}: runtime route configuration differs")
    forbidden_scheduling = [
        "preregistered_cells.jsonl",
        "scheduling_deviation.json",
        "scheduling_deviation.sha256",
        "scheduling_execution_log.jsonl",
    ]
    present_scheduling = [
        name for name in forbidden_scheduling if (root / name).exists()
    ]
    if present_scheduling:
        errors.append(
            f"{root.name}: formal scheduling artifacts are present "
            f"{present_scheduling}"
        )
    result_paths = [
        *chosen_paths,
        *sorted(root.glob("cells/*/attempt_*/result.json")),
    ]
    for path in result_paths:
        if "pilot_scheduling" in load_json(path):
            errors.append(
                f"{root.name}: non-formal result contains pilot_scheduling "
                f"({path.relative_to(root)})"
            )
    inspected: list[dict[str, Any]] = []
    for cell in selected_cells:
        cell_id = str(cell["cell_id"])
        chosen_path = root / "cells" / cell_id / "chosen_result.json"
        if not chosen_path.is_file():
            errors.append(f"{cell_id}: chosen result is missing")
            continue
        row = load_json(chosen_path)
        if aggregate_rows.get(cell_id) != row:
            errors.append(f"{cell_id}: aggregate row differs from chosen result")
        cell_errors = audit_cell(root=root, cell=cell, row=row)
        errors.extend(f"{cell_id}: {message}" for message in cell_errors)
        invalid_schema_steps = sum(
            1
            for step in row.get("trace") or []
            if isinstance(step, dict)
            and isinstance(step.get("action"), dict)
            and "_raw" in step["action"]
            and isinstance(step.get("pilot_history"), dict)
            and step["pilot_history"].get("schema_valid") is not True
        )
        inspected.append({
            "cell_id": cell_id,
            "source_root": display_path(root),
            "model": cell["model"],
            "benchmark": cell["benchmark"],
            "scenario": cell["scenario"],
            "slug": cell["slug"],
            "condition": cell["condition"],
            "outcome": row.get("outcome"),
            "trace_steps": len(row.get("trace") or []),
            "actual_http_requests": int(
                row.get("pilot_actual_http_request_count") or 0
            ),
            "identity_valid": (row.get("pilot_identity_audit") or {}).get(
                "valid"
            ),
            "invalid_schema_steps": invalid_schema_steps,
            "errors": cell_errors,
        })
    credential_hits, unreadable = secret_scan(root)
    if credential_hits:
        errors.append(f"{root.name}: credential-like text in {credential_hits}")
    if unreadable:
        errors.append(f"{root.name}: unreadable files in secret scan: {unreadable}")
    return inspected, errors


def audit(certified_root: Path, auxiliary_root: Path) -> dict[str, Any]:
    original_manifest = build_smoke_manifest()
    original_sonnet = [
        cell for cell in original_manifest if cell["model"] == SONNET_MODEL
    ]
    auxiliary_manifest = build_sonnet_auxiliary_smoke_manifest()
    original_rows, original_errors = inspect_cells(
        root=certified_root,
        manifest_name="instrumentation_smoke_cells.jsonl",
        expected_manifest=original_manifest,
        selected_cells=original_sonnet,
        experiment_kind="instrumentation_smoke_non_formal",
        strict_cell_set=False,
    )
    auxiliary_rows, auxiliary_errors = inspect_cells(
        root=auxiliary_root,
        manifest_name="sonnet_auxiliary_smoke_cells.jsonl",
        expected_manifest=auxiliary_manifest,
        selected_cells=auxiliary_manifest,
        experiment_kind="instrumentation_smoke_sonnet_auxiliary_non_formal",
        strict_cell_set=True,
    )
    cells = [*original_rows, *auxiliary_rows]
    errors = [*original_errors, *auxiliary_errors]
    conditions = {str(cell.get("condition") or "") for cell in cells}
    splits = [str(cell.get("benchmark") or "") for cell in cells]
    models = {str(cell.get("model") or "") for cell in cells}
    if conditions != {
        "no_history",
        "previous_step",
        "full_history",
        "structured_falsification",
    }:
        errors.append("Sonnet model-scoped smoke does not cover four conditions")
    if splits.count("official") != 2 or splits.count("clean") != 2:
        errors.append("Sonnet model-scoped smoke is not balanced across splits")
    if models != {SONNET_MODEL}:
        errors.append("model-scoped smoke contains a non-Sonnet model")
    if any(cell.get("outcome") == "agent_error" for cell in cells):
        errors.append("model-scoped smoke contains an agent_error")
    return {
        "gate": "Gate 1 Sonnet model-scoped instrumentation smoke",
        "scope": "Sonnet formal prefix only; this is not a GPT smoke approval",
        "approved": not errors and len(cells) == 4,
        "certified_manifest_sha256": (
            sha256_file(certified_root / "instrumentation_smoke_cells.jsonl")
            if (certified_root / "instrumentation_smoke_cells.jsonl").is_file()
            else None
        ),
        "auxiliary_manifest_sha256": (
            sha256_file(auxiliary_root / "sonnet_auxiliary_smoke_cells.jsonl")
            if (auxiliary_root / "sonnet_auxiliary_smoke_cells.jsonl").is_file()
            else None
        ),
        "completed_cells": len(cells),
        "conditions": sorted(conditions),
        "split_counts": {
            "official": splits.count("official"),
            "clean": splits.count("clean"),
        },
        "invalid_schema_step_count": sum(
            int(cell.get("invalid_schema_steps") or 0) for cell in cells
        ),
        "cells": cells,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--certified-root",
        type=Path,
        default=DEFAULT_SMOKE_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--auxiliary-root",
        type=Path,
        default=DEFAULT_SONNET_AUX_SMOKE_OUTPUT_ROOT,
    )
    args = parser.parse_args()
    certified_root = args.certified_root.resolve()
    auxiliary_root = args.auxiliary_root.resolve()
    report = audit(certified_root, auxiliary_root)
    write_json(auxiliary_root / "model_scoped_gate1_audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
