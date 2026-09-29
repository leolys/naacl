#!/usr/bin/env python3
"""Materialize the approved GPT64 checkpoint-overrun recovery without an LLM call."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation.audit_reflection_history_stage import (
    audit as audit_stage,
    audit_cell,
)
from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    DEFAULT_OUTPUT_ROOT,
    MODEL_CONFIGS,
    acquire_output_root_lock,
    aggregate,
    append_jsonl,
    read_jsonl,
    scheduled_cells,
    sha256_file,
    validate_identity_evidence,
    write_json,
)


DEVIATION_RELATIVE_PATH = (
    Path("gate_reviews") / "gpt64_checkpoint_overrun_deviation.json"
)
MATERIALIZATION_RELATIVE_PATH = (
    Path("gate_reviews") / "gpt64_overrun_recovery_materialization.json"
)
AUDIT_RELATIVE_PATH = (
    Path("gate_reviews") / "gpt64_overrun_recovery_audit.json"
)
EXPECTED_DEVIATION_SHA256 = (
    "1a0386e0851fb0f0e25dd4402c70607960935e61eb5e1baf2fd650e9a4d9a122"
)
RECOVERY_CELL_ID = "cba724288d893d02"
RECOVERY_SEQUENCE = 332
RECOVERY_ATTEMPT_DIR = Path("cells") / RECOVERY_CELL_ID / "attempt_01"
EXPECTED_DEPLOYMENT = "dedceaa0-7dbe-476c-a4e6-d50815171e8e"
EXPECTED_RAW_HASHES = {
    "runs.jsonl": "c46c81a0e7175a04f6adcdc34f299eb81f9253568339836e34f1676265c58b45",
    "model_identity_events.jsonl": (
        "8ecb79b55eba7a5b41f94b4e1b945769a6cd312384b06f7757821f451f5b8139"
    ),
    "submissions.jsonl": (
        "bbfb19c21ad5fa59151d6f080cb71bda048a310c6af79cecc94426f498d63494"
    ),
}
SNAPSHOT_FILES = (
    "runs.jsonl",
    "attempt_manifest.jsonl",
    "checkpoint_manifest.jsonl",
    "scheduling_execution_log.jsonl",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def recovery_sequence_ids(root: Path) -> list[str]:
    starts = [
        event
        for event in read_jsonl(root / "scheduling_execution_log.jsonl")
        if event.get("event_type") == "cell_start"
        and 321 <= int(event.get("execution_sequence") or 0) <= 332
    ]
    starts.sort(key=lambda event: int(event["execution_sequence"]))
    require(
        [int(event["execution_sequence"]) for event in starts]
        == list(range(321, 333)),
        "Recovery sequence starts are not exactly 321-332",
    )
    return [str(event["cell_id"]) for event in starts]


def recovery_inventory(root: Path, cell_ids: list[str]) -> dict[str, Any]:
    files = sorted(
        path
        for cell_id in cell_ids
        for path in (root / "cells" / cell_id).rglob("*")
        if path.is_file()
    )
    digest_lines = []
    artifacts = []
    for path in files:
        relative = path.resolve().relative_to(root.resolve())
        try:
            digest_path = path.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            digest_path = relative
        digest = sha256_file(path)
        digest_lines.append(f"{digest}  {digest_path.as_posix()}\n")
        artifacts.append({
            "path": relative.as_posix(),
            "sha256": digest,
        })
    tree_sha256 = hashlib.sha256(
        "".join(digest_lines).encode("utf-8")
    ).hexdigest()
    return {
        "artifact_count": len(files),
        "tree_sha256": tree_sha256,
        "artifacts": artifacts,
    }


def verify_preserved_inventory(
    root: Path,
    inventory: list[dict[str, str]],
) -> list[str]:
    errors = []
    for artifact in inventory:
        path = root / artifact["path"]
        if not path.is_file():
            errors.append(f"missing preserved artifact: {artifact['path']}")
        elif sha256_file(path) != artifact["sha256"]:
            errors.append(f"mutated preserved artifact: {artifact['path']}")
    return errors


def selected_hashes(root: Path) -> dict[str, str]:
    return {
        name: sha256_file(root / name)
        for name in SNAPSHOT_FILES
    }


def raw_hashes(attempt_dir: Path) -> dict[str, str]:
    return {
        name: sha256_file(attempt_dir / name)
        for name in EXPECTED_RAW_HASHES
    }


def recovery_artifact_hashes(root: Path) -> dict[str, str]:
    relative_paths = (
        RECOVERY_ATTEMPT_DIR / "attempt_status.json",
        RECOVERY_ATTEMPT_DIR / "result.json",
        Path("cells") / RECOVERY_CELL_ID / "chosen_result.json",
        AUDIT_RELATIVE_PATH,
    )
    return {
        path.as_posix(): sha256_file(root / path)
        for path in relative_paths
    }


def validate_existing_materialization(
    root: Path,
    report: dict[str, Any],
) -> None:
    deviation_path = root / DEVIATION_RELATIVE_PATH
    audit_path = root / AUDIT_RELATIVE_PATH
    require(
        report.get("event") == "gpt64_overrun_recovery_materialization"
        and report.get("no_model_request") is True,
        "Recovery record identity is invalid",
    )
    require(
        report.get("deviation_sha256") == EXPECTED_DEVIATION_SHA256
        == sha256_file(deviation_path),
        "Recovery record is not bound to the approved deviation",
    )
    require(
        report.get("cell_id") == RECOVERY_CELL_ID
        and report.get("execution_sequence") == RECOVERY_SEQUENCE
        and report.get("attempt") == 1,
        "Recovery record cell/sequence/attempt binding is invalid",
    )
    require(
        report.get("implementation_sha256") == sha256_file(Path(__file__)),
        "Recovery implementation changed after materialization",
    )
    require(
        report.get("raw_child_hashes")
        == raw_hashes(root / RECOVERY_ATTEMPT_DIR)
        == EXPECTED_RAW_HASHES,
        "Recovery raw evidence binding is invalid",
    )
    deviation = load_json(deviation_path)
    before_hashes = report.get("before_hashes") or {}
    require(
        all(
            before_hashes.get(name)
            == deviation["pause_snapshot_hashes"].get(name)
            for name in SNAPSHOT_FILES
        )
        and set(before_hashes) == set(SNAPSHOT_FILES),
        "Recovery before aggregate hashes differ from the pause snapshot",
    )
    require(
        report.get("after_hashes") == selected_hashes(root),
        "Recovery after aggregate hashes changed",
    )
    require(
        report.get("audit_sha256") == sha256_file(audit_path),
        "Recovery audit hash changed",
    )
    require(
        report.get("recovery_artifact_hashes")
        == recovery_artifact_hashes(root),
        "Recovery artifact inventory changed",
    )
    preserved = report.get("preserved_artifact_inventory")
    require(
        isinstance(preserved, list)
        and not verify_preserved_inventory(root, preserved),
        "One or more pre-existing overrun artifacts changed",
    )
    audit = load_json(audit_path)
    require(
        audit.get("approved") is True and audit.get("errors") == [],
        "Stored recovery audit is not approved",
    )


def stable_prefix_audit(root: Path, *, expected_completed: int) -> dict[str, Any]:
    stage = audit_stage(
        root,
        4,
        expected_completed_override=expected_completed,
    )
    errors = [
        f"stage audit: {message}" for message in stage.get("errors") or []
    ]
    manifest = read_jsonl(root / "preregistered_cells.jsonl")
    rows = read_jsonl(root / "runs.jsonl")
    ordered = scheduled_cells(manifest)
    expected_ids = [
        str(cell["cell_id"]) for cell in ordered[:expected_completed]
    ]
    expected_id_set = set(expected_ids)
    expected_aggregate_order = [
        str(cell["cell_id"])
        for cell in manifest
        if str(cell["cell_id"]) in expected_id_set
    ]
    row_ids = [
        str((row.get("pilot_cell") or {}).get("cell_id") or "")
        for row in rows
    ]
    row_by_id = {
        str((row.get("pilot_cell") or {}).get("cell_id") or ""): row
        for row in rows
    }
    if len(rows) != expected_completed:
        errors.append(
            f"runs.jsonl has {len(rows)} rows, expected {expected_completed}"
        )
    if len(row_by_id) != len(rows):
        errors.append("runs.jsonl contains duplicate cell IDs")
    if set(row_ids) != expected_id_set:
        errors.append("runs.jsonl is not the frozen schedule prefix")
    if row_ids != expected_aggregate_order:
        errors.append("runs.jsonl is not in manifest-filtered aggregate order")

    chosen_paths = sorted((root / "cells").glob("*/chosen_result.json"))
    chosen_by_id = {
        path.parent.name: load_json(path) for path in chosen_paths
    }
    if set(chosen_by_id) != expected_id_set:
        errors.append("chosen results differ from the frozen schedule prefix")
    for cell_id, row in row_by_id.items():
        chosen = chosen_by_id.get(cell_id)
        if chosen != row:
            errors.append(f"{cell_id}: aggregate row differs from chosen result")

    attempt_rows = read_jsonl(root / "attempt_manifest.jsonl")
    status_paths = sorted((root / "cells").glob("*/attempt_*/attempt_status.json"))
    status_records = [(path, load_json(path)) for path in status_paths]
    status_by_dir = {}
    for path, status in status_records:
        relative = str(status.get("attempt_dir") or "")
        if relative in status_by_dir:
            errors.append(f"duplicate attempt status directory {relative}")
        status_by_dir[relative] = status
        if path.parent.resolve() != (root / relative).resolve():
            errors.append(
                f"{relative}: status file is not in its declared directory"
            )
    manifest_by_dir = {
        str(row.get("attempt_dir") or ""): row for row in attempt_rows
    }
    if len(manifest_by_dir) != len(attempt_rows):
        errors.append("duplicate attempt manifest directories")
    if status_by_dir != manifest_by_dir:
        errors.append("attempt manifest differs from attempt status files")

    for cell_id, row in row_by_id.items():
        attempt_dir = str(row.get("pilot_attempt_dir") or "")
        status = status_by_dir.get(attempt_dir)
        if status is None:
            errors.append(f"{cell_id}: chosen attempt has no status")
            continue
        if status.get("formal_attempt_consumed") is not True:
            errors.append(f"{cell_id}: chosen attempt is not consumed")
        if status.get("cell_id") != cell_id:
            errors.append(f"{cell_id}: chosen status belongs to another cell")
        if int(status.get("attempt") or 0) != int(row.get("pilot_attempt") or 0):
            errors.append(f"{cell_id}: chosen attempt index differs from status")
        if int(status.get("actual_http_request_count") or 0) != int(
            row.get("pilot_actual_http_request_count") or 0
        ):
            errors.append(f"{cell_id}: chosen HTTP count differs from status")
        if status.get("outcome") != row.get("outcome"):
            errors.append(f"{cell_id}: chosen outcome differs from status")
        result_path = root / attempt_dir / "result.json"
        if not result_path.is_file():
            errors.append(f"{cell_id}: chosen attempt result is missing")
            continue
        expected_result = dict(row)
        expected_result.pop("pilot_scheduling", None)
        if load_json(result_path) != expected_result:
            errors.append(f"{cell_id}: chosen result differs from attempt result")

    checkpoints = read_jsonl(root / "checkpoint_manifest.jsonl")
    checkpoint_ids = [str(row.get("cell_id") or "") for row in checkpoints]
    if len(checkpoints) != expected_completed:
        errors.append(
            f"checkpoint manifest has {len(checkpoints)} rows, "
            f"expected {expected_completed}"
        )
    if len(set(checkpoint_ids)) != len(checkpoint_ids):
        errors.append("checkpoint manifest contains duplicate cells")
    if checkpoint_ids != expected_ids:
        errors.append("checkpoint manifest is not in frozen execution order")
    for checkpoint in checkpoints:
        cell_id = str(checkpoint.get("cell_id") or "")
        row = row_by_id.get(cell_id)
        if row is None:
            errors.append(f"{cell_id}: checkpoint has no aggregate result")
            continue
        cell = row.get("pilot_cell") or {}
        scheduling = row.get("pilot_scheduling") or {}
        expected = {
            "condition_order": cell.get("condition_order"),
            "chosen_attempt": row.get("pilot_attempt"),
            "outcome": row.get("outcome"),
            "error_attribution": row.get("error_attribution"),
            "scheduling_execution_sequence": scheduling.get(
                "execution_sequence"
            ),
        }
        for key, value in expected.items():
            if checkpoint.get(key) != value:
                errors.append(f"{cell_id}: checkpoint {key} differs")

    return {
        "audit": "stable GPT64 overrun recovery prefix",
        "generated_at": utc_now(),
        "expected_completed": expected_completed,
        "approved": not errors,
        "stage_audit_approved": stage.get("approved_by_automated_audit"),
        "stage_audit": stage,
        "completed_rows": len(rows),
        "attempt_status_rows": len(status_paths),
        "checkpoint_rows": len(checkpoints),
        "errors": errors,
    }


def materialize(root: Path) -> dict[str, Any]:
    deviation_path = root / DEVIATION_RELATIVE_PATH
    materialization_path = root / MATERIALIZATION_RELATIVE_PATH
    audit_path = root / AUDIT_RELATIVE_PATH
    if materialization_path.exists():
        report = load_json(materialization_path)
        validate_existing_materialization(root, report)
        return report

    require(deviation_path.is_file(), "Checkpoint-overrun deviation is missing")
    require(
        sha256_file(deviation_path) == EXPECTED_DEVIATION_SHA256,
        "Checkpoint-overrun deviation hash changed",
    )
    deviation = load_json(deviation_path)
    for name, expected in deviation["frozen_source_hashes"].items():
        require(sha256_file(root / name) == expected, f"{name} hash changed")
    for name in SNAPSHOT_FILES:
        expected = deviation["pause_snapshot_hashes"][name]
        require(sha256_file(root / name) == expected, f"{name} pause hash changed")

    cell_ids = recovery_sequence_ids(root)
    inventory_before = recovery_inventory(root, cell_ids)
    require(
        inventory_before["tree_sha256"]
        == deviation["pause_snapshot_hashes"][
            "overrun_cells_321_332_tree_sha256"
        ],
        "Overrun cell artifact tree changed",
    )
    require(
        inventory_before["artifact_count"]
        == deviation["pause_snapshot_hashes"][
            "overrun_cells_321_332_artifact_count"
        ],
        "Overrun artifact count changed",
    )

    attempt_dir = root / RECOVERY_ATTEMPT_DIR
    raw_before = raw_hashes(attempt_dir)
    require(raw_before == EXPECTED_RAW_HASHES, "Sequence-332 raw evidence changed")
    require(
        not (attempt_dir / "attempt_status.json").exists()
        and not (attempt_dir / "result.json").exists()
        and not (root / "cells" / RECOVERY_CELL_ID / "chosen_result.json").exists(),
        "Sequence 332 has already been partially materialized",
    )

    manifest = read_jsonl(root / "preregistered_cells.jsonl")
    manifest_by_id = {str(cell["cell_id"]): cell for cell in manifest}
    cell = manifest_by_id[RECOVERY_CELL_ID]
    raw_rows = read_jsonl(attempt_dir / "runs.jsonl")
    require(len(raw_rows) == 1, "Sequence 332 does not have exactly one raw row")
    raw_row = raw_rows[0]
    identity = validate_identity_evidence(
        row=raw_row,
        identity_log=attempt_dir / "model_identity_events.jsonl",
        expected_deployment=EXPECTED_DEPLOYMENT,
    )
    require(identity["valid"] is True, "Sequence-332 identity audit failed")
    require(
        identity["identity_event_count"] == 6
        and identity["traced_model_action_count"] == 6,
        "Sequence-332 model-call count changed",
    )
    enriched = {
        **raw_row,
        "pilot_identity_audit": identity,
        "pilot_cell": cell,
        "pilot_attempt": 1,
        "pilot_attempt_dir": RECOVERY_ATTEMPT_DIR.as_posix(),
        "pilot_actual_http_request_count": 6,
        "pilot_availability_aborted": False,
        "pilot_availability_http_429": False,
        "pilot_formal_attempt_consumed": True,
        "pilot_recovery_provenance": {
            "event": "gpt64_checkpoint_overrun_materialization",
            "deviation_record": DEVIATION_RELATIVE_PATH.as_posix(),
            "no_model_request": True,
        },
    }
    require(
        audit_cell(root=root, cell=cell, row=enriched) == [],
        "Sequence-332 enriched row failed the approved stage audit",
    )

    start_events = [
        event
        for event in read_jsonl(root / "scheduling_execution_log.jsonl")
        if event.get("event_type") == "cell_start"
        and int(event.get("execution_sequence") or 0) == RECOVERY_SEQUENCE
    ]
    require(
        len(start_events) == 1
        and start_events[0].get("cell_id") == RECOVERY_CELL_ID,
        "Sequence-332 scheduling start is invalid",
    )
    scheduling = {
        "execution_sequence": RECOVERY_SEQUENCE,
        "started_at": start_events[0]["started_at"],
        "original_condition_order": start_events[0]["original_condition_order"],
        "model_queue": start_events[0]["model_queue"],
        "scheduling_deviation_sha256": start_events[0][
            "scheduling_deviation_sha256"
        ],
    }
    recovery_time = utc_now()
    status = {
        "timestamp": recovery_time,
        "cell_id": RECOVERY_CELL_ID,
        "attempt": 1,
        "return_code": None,
        "timed_out": False,
        "cleanup_status": "recovered_after_parent_interruption",
        "duration_sec": None,
        "port": None,
        "row_count": 1,
        "actual_http_request_count": 6,
        "outcome": "misleading_failure",
        "error_attribution": "chart_induced_intermediate_decision_error",
        "identity_audit": identity,
        "availability_aborted": False,
        "formal_attempt_consumed": True,
        "attempt_dir": RECOVERY_ATTEMPT_DIR.as_posix(),
    }
    chosen = {**enriched, "pilot_scheduling": scheduling}
    checkpoint = {
        "timestamp": recovery_time,
        "cell_id": RECOVERY_CELL_ID,
        "condition_order": cell["condition_order"],
        "attempt_count": 1,
        "chosen_attempt": 1,
        "outcome": chosen["outcome"],
        "error_attribution": chosen["error_attribution"],
        "scheduling_execution_sequence": RECOVERY_SEQUENCE,
        "recovered_from_child_artifacts": True,
    }
    finish = {
        "event_type": "cell_finish",
        "cell_id": RECOVERY_CELL_ID,
        "execution_sequence": RECOVERY_SEQUENCE,
        "finished_at": recovery_time,
        "outcome": chosen["outcome"],
        "chosen_attempt": 1,
        "recovered_from_child_artifacts": True,
        "recovered_bookkeeping": True,
    }

    before_hashes = selected_hashes(root)
    write_json(attempt_dir / "attempt_status.json", status)
    append_jsonl(root / "attempt_manifest.jsonl", status)
    write_json(attempt_dir / "result.json", enriched)
    write_json(root / "cells" / RECOVERY_CELL_ID / "chosen_result.json", chosen)
    append_jsonl(root / "checkpoint_manifest.jsonl", checkpoint)
    append_jsonl(root / "scheduling_execution_log.jsonl", finish)
    aggregate(root, manifest)
    raw_after = raw_hashes(attempt_dir)
    require(raw_after == raw_before, "Raw child evidence changed during recovery")
    preservation_errors = verify_preserved_inventory(
        root,
        inventory_before["artifacts"]
    )
    require(
        not preservation_errors,
        "; ".join(preservation_errors),
    )
    audit = stable_prefix_audit(root, expected_completed=332)
    write_json(audit_path, audit)
    require(audit["approved"], "Materialized 332-cell prefix failed audit")
    after_hashes = selected_hashes(root)
    implementation_sha256 = sha256_file(Path(__file__))
    audit_sha256 = sha256_file(audit_path)
    artifact_hashes = recovery_artifact_hashes(root)
    report = {
        "event": "gpt64_overrun_recovery_materialization",
        "materialized_at": recovery_time,
        "deviation_sha256": sha256_file(deviation_path),
        "implementation_sha256": implementation_sha256,
        "cell_id": RECOVERY_CELL_ID,
        "execution_sequence": RECOVERY_SEQUENCE,
        "attempt": 1,
        "no_model_request": True,
        "raw_child_files_preserved": raw_after == raw_before,
        "raw_child_hashes": raw_after,
        "preserved_artifact_inventory": inventory_before["artifacts"],
        "preserved_artifact_count": inventory_before["artifact_count"],
        "preserved_artifact_tree_sha256": inventory_before["tree_sha256"],
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
        "audit_path": AUDIT_RELATIVE_PATH.as_posix(),
        "audit_sha256": audit_sha256,
        "audit_approved": audit["approved"],
        "recovery_artifact_hashes": artifact_hashes,
    }
    write_json(materialization_path, report)
    validate_existing_materialization(root, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    lock = acquire_output_root_lock(root)
    require(lock is not None, "Another pilot process holds the formal-root lock")
    try:
        report = materialize(root)
    finally:
        lock.close()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
