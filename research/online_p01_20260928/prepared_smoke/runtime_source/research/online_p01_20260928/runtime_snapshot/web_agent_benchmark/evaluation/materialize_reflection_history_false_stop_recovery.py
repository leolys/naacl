#!/usr/bin/env python3
"""Materialize the approved sequence-486 false-stop recovery offline."""

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
    audit_cell,
)
from web_agent_benchmark.evaluation.materialize_reflection_history_gpt64_recovery import (
    stable_prefix_audit,
    verify_preserved_inventory,
)
from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    DEFAULT_OUTPUT_ROOT,
    acquire_output_root_lock,
    aggregate,
    append_jsonl,
    read_jsonl,
    scheduled_cells,
    sha256_file,
    update_interface_stop_rule_state,
    validate_identity_evidence,
    write_json,
)


DEVIATION_RELATIVE_PATH = (
    Path("gate_reviews") / "gpt_false_stop_at_485_deviation.json"
)
MATERIALIZATION_RELATIVE_PATH = (
    Path("gate_reviews") / "gpt_false_stop_recovery_materialization.json"
)
AUDIT_RELATIVE_PATH = (
    Path("gate_reviews") / "gpt_false_stop_recovery_audit.json"
)
EXPECTED_DEVIATION_SHA256 = (
    "42716e52863f1f0cbfd6b5a8e025ed115ebedb177dca222a3b1a726416fe6350"
)
RECOVERY_CELL_ID = "2fc689b9498b60b0"
RECOVERY_SEQUENCE = 486
RECOVERY_ATTEMPT_DIR = Path("cells") / RECOVERY_CELL_ID / "attempt_01"
EXPECTED_DEPLOYMENT = "dedceaa0-7dbe-476c-a4e6-d50815171e8e"
EXPECTED_RAW_TREE_SHA256 = (
    "84e0a78e8ecb00a151d59436210c7d8f0bf8e837987af3cadf60db852b579d34"
)
EXPECTED_RAW_ARTIFACT_COUNT = 11
EXPECTED_ROOT_TREE_SHA256 = (
    "e4f5f9d6d434930295b1f9aa0fd320d12ec0f25d5ebc079a7a72991ef1886850"
)
EXPECTED_ROOT_ARTIFACT_COUNT = 8204
EXPECTED_COMPLETED_AFTER_RECOVERY = 486
EXPECTED_MISSING_AFTER_RECOVERY = 26
EXPECTED_HTTP_REQUEST_COUNT = 5
EXPECTED_INTERFACE_COUNTS = {
    "full_history": 4,
    "no_history": 2,
    "previous_step": 2,
    "structured_falsification": 3,
}
FORMAL_ROOT_RELATIVE_PATH = Path(
    "web_agent_benchmark/pair_evaluation_records/"
    "reflection_history_pilot_20260727_restart1"
)
EXPECTED_RAW_HASHES = {
    "runs.jsonl": "72421682905b0919ce9a2a18c6e34de5694a22684599796606d3f8c8e9c1220c",
    "model_identity_events.jsonl": (
        "f2dd3fbf121069bd9561b8904e8fd26bb359baff6dfc27b649470437b55452c5"
    ),
    "submissions.jsonl": (
        "4d17a460c3990b0ae8546a6ac95ffc4b9352feabb74b1da2effad806397ad5bf"
    ),
}
EXPECTED_FROZEN_HASHES = {
    "preregistered_cells.jsonl": (
        "cec5ff50737d2f39dd2cf63ff0eb598b2fd07b0c56526c7a78bcf4be20e6f490"
    ),
    "runtime_routes.json": (
        "861be3495cdca215ce7b0e3e9ae8340be026aa326569564a3d0e2f4a08bc10e8"
    ),
    "scheduling_deviation.json": (
        "fa7325dcf6d3e276f615ef1cdacd1f94160c29d293a744ced2d9cab6c720520e"
    ),
}
EXPECTED_AUXILIARY_PAUSE_HASHES = {
    "missing_cells.jsonl": (
        "5bbd49f5f22dc003dcfa093ac8b343edf002ab92753a894cc14797c616a90080"
    ),
    "run_progress.json": (
        "b6577f1ed5fe115b06e10c690a32d7b8778bd4f9d99c95b7024508a7a3e88154"
    ),
}
REVIEWED_CODE_PATHS = {
    "runner": (
        REPO_ROOT
        / "web_agent_benchmark/evaluation/run_reflection_history_pilot.py"
    ),
    "stage_auditor": (
        REPO_ROOT
        / "web_agent_benchmark/evaluation/audit_reflection_history_stage.py"
    ),
    "prior_materializer": (
        REPO_ROOT
        / "web_agent_benchmark/evaluation/"
        "materialize_reflection_history_gpt64_recovery.py"
    ),
}
EXPECTED_REVIEWED_CODE_HASHES = {
    "runner": (
        "84ec6791b809d14023c4004f8d4d098916824a8cebf577d47034ae06c472e333"
    ),
    "stage_auditor": (
        "d7afefa3784c90c4903602119d8034000b7a7127c92713ddacfb07b2d9e1aa37"
    ),
    "prior_materializer": (
        "605f0d996cbe71bff71f4aa41d50fab140d062230ac538ea298afc34ed7971b8"
    ),
}
SNAPSHOT_FILES = (
    "runs.jsonl",
    "attempt_manifest.jsonl",
    "checkpoint_manifest.jsonl",
    "scheduling_execution_log.jsonl",
)
REWRITTEN_RELATIVE_PATHS = {
    Path("runs.jsonl"),
    Path("attempt_manifest.jsonl"),
    Path("checkpoint_manifest.jsonl"),
    Path("scheduling_execution_log.jsonl"),
    Path("missing_cells.jsonl"),
    Path("run_progress.json"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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


def inventory_tree_sha256(inventory: list[dict[str, str]]) -> str:
    digest_lines = []
    for artifact in sorted(inventory, key=lambda item: item["path"]):
        digest_path = FORMAL_ROOT_RELATIVE_PATH / artifact["path"]
        digest_lines.append(
            f"{artifact['sha256']}  {digest_path.as_posix()}\n"
        )
    return hashlib.sha256(
        "".join(digest_lines).encode("utf-8")
    ).hexdigest()


def build_inventory(
    root: Path,
    files: list[Path],
) -> dict[str, Any]:
    artifacts = []
    for path in sorted(files):
        relative = path.resolve().relative_to(root.resolve())
        artifacts.append({
            "path": relative.as_posix(),
            "sha256": sha256_file(path),
        })
    return {
        "artifact_count": len(artifacts),
        "tree_sha256": inventory_tree_sha256(artifacts),
        "artifacts": artifacts,
    }


def immutable_cell_inventory(root: Path) -> dict[str, Any]:
    cell_root = root / "cells" / RECOVERY_CELL_ID
    files = sorted(path for path in cell_root.rglob("*") if path.is_file())
    return build_inventory(root, files)


def immutable_root_inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.resolve().relative_to(root.resolve())
        if relative == Path(".reflection_pilot_runner.lock"):
            continue
        if relative in REWRITTEN_RELATIVE_PATHS:
            continue
        files.append(path)
    return build_inventory(root, files)


def reviewed_code_hashes() -> dict[str, str]:
    return {
        name: sha256_file(path)
        for name, path in REVIEWED_CODE_PATHS.items()
    }


def recovery_artifact_hashes(root: Path) -> dict[str, str]:
    paths = (
        RECOVERY_ATTEMPT_DIR / "attempt_status.json",
        RECOVERY_ATTEMPT_DIR / "result.json",
        Path("cells") / RECOVERY_CELL_ID / "chosen_result.json",
        AUDIT_RELATIVE_PATH,
        Path("missing_cells.jsonl"),
        Path("run_progress.json"),
        Path("interface_error_stop_state.json"),
    )
    return {
        path.as_posix(): sha256_file(root / path)
        for path in paths
    }


def validate_existing_materialization(
    root: Path,
    report: dict[str, Any],
) -> None:
    deviation_path = root / DEVIATION_RELATIVE_PATH
    audit_path = root / AUDIT_RELATIVE_PATH
    deviation = load_json(deviation_path)
    require(
        report.get("event") == "gpt_false_stop_recovery_materialization"
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
        report.get("reviewed_code_hashes")
        == reviewed_code_hashes()
        == EXPECTED_REVIEWED_CODE_HASHES,
        "Reviewed recovery dependencies changed",
    )
    require(
        report.get("before_hashes")
        == deviation.get("pause_snapshot_hashes"),
        "Recovery before hashes differ from the deviation snapshot",
    )
    require(
        report.get("before_auxiliary_hashes")
        == EXPECTED_AUXILIARY_PAUSE_HASHES,
        "Recovery auxiliary pause hashes differ",
    )
    require(
        report.get("raw_child_hashes")
        == raw_hashes(root / RECOVERY_ATTEMPT_DIR)
        == EXPECTED_RAW_HASHES,
        "Recovery raw evidence binding is invalid",
    )
    require(
        report.get("raw_child_tree_sha256") == EXPECTED_RAW_TREE_SHA256,
        "Recovery raw tree binding is invalid",
    )
    require(
        report.get("after_hashes") == selected_hashes(root),
        "Recovery aggregate hashes changed",
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
        "One or more immutable sequence-486 artifacts changed",
    )
    preserved_root = report.get("preserved_root_artifact_inventory")
    require(
        isinstance(preserved_root, list)
        and len(preserved_root) == EXPECTED_ROOT_ARTIFACT_COUNT,
        "Preserved whole-root inventory count is invalid",
    )
    preserved_root_paths = [
        str(artifact.get("path") or "")
        for artifact in preserved_root
    ]
    require(
        len(set(preserved_root_paths)) == EXPECTED_ROOT_ARTIFACT_COUNT
        and all(preserved_root_paths),
        "Preserved whole-root inventory paths are not unique",
    )
    require(
        inventory_tree_sha256(preserved_root)
        == report.get("preserved_root_tree_sha256")
        == EXPECTED_ROOT_TREE_SHA256,
        "Preserved whole-root inventory tree is invalid",
    )
    require(
        not verify_preserved_inventory(root, preserved_root),
        "One or more pre-recovery root artifacts changed",
    )
    require(
        report.get("progress") == load_json(root / "run_progress.json"),
        "Reported progress differs from the physical progress file",
    )
    require(
        report.get("interface_stop_state")
        == load_json(root / "interface_error_stop_state.json"),
        "Reported stop state differs from the physical stop-state file",
    )
    audit = load_json(audit_path)
    require(
        audit.get("approved") is True and audit.get("errors") == [],
        "Stored recovery audit is not approved",
    )


def materialize(root: Path) -> dict[str, Any]:
    deviation_path = root / DEVIATION_RELATIVE_PATH
    materialization_path = root / MATERIALIZATION_RELATIVE_PATH
    audit_path = root / AUDIT_RELATIVE_PATH
    if materialization_path.exists():
        report = load_json(materialization_path)
        validate_existing_materialization(root, report)
        return report

    require(deviation_path.is_file(), "False-stop deviation is missing")
    require(
        sha256_file(deviation_path) == EXPECTED_DEVIATION_SHA256,
        "False-stop deviation hash changed",
    )
    deviation = load_json(deviation_path)
    require(
        reviewed_code_hashes() == EXPECTED_REVIEWED_CODE_HASHES,
        "Reviewed recovery dependency hash changed",
    )
    for name, expected in EXPECTED_FROZEN_HASHES.items():
        require(sha256_file(root / name) == expected, f"{name} hash changed")
    for name in SNAPSHOT_FILES:
        expected = deviation["pause_snapshot_hashes"][name]
        require(sha256_file(root / name) == expected, f"{name} pause hash changed")
    for name, expected in EXPECTED_AUXILIARY_PAUSE_HASHES.items():
        require(
            sha256_file(root / name) == expected,
            f"{name} auxiliary pause hash changed",
        )

    root_inventory_before = immutable_root_inventory(root)
    require(
        root_inventory_before["artifact_count"]
        == EXPECTED_ROOT_ARTIFACT_COUNT,
        "Pre-recovery whole-root artifact count changed",
    )
    require(
        root_inventory_before["tree_sha256"]
        == EXPECTED_ROOT_TREE_SHA256,
        "Pre-recovery whole-root artifact tree changed",
    )
    inventory_before = immutable_cell_inventory(root)
    require(
        inventory_before["artifact_count"] == EXPECTED_RAW_ARTIFACT_COUNT,
        "Sequence-486 raw artifact count changed",
    )
    require(
        inventory_before["tree_sha256"] == EXPECTED_RAW_TREE_SHA256,
        "Sequence-486 raw artifact tree changed",
    )
    attempt_dir = root / RECOVERY_ATTEMPT_DIR
    raw_before = raw_hashes(attempt_dir)
    require(raw_before == EXPECTED_RAW_HASHES, "Sequence-486 raw hashes changed")
    require(
        not (attempt_dir / "attempt_status.json").exists()
        and not (attempt_dir / "result.json").exists()
        and not (root / "cells" / RECOVERY_CELL_ID / "chosen_result.json").exists(),
        "Sequence 486 has already been partially materialized",
    )

    manifest = read_jsonl(root / "preregistered_cells.jsonl")
    ordered = scheduled_cells(manifest)
    require(
        len(ordered) >= RECOVERY_SEQUENCE
        and ordered[RECOVERY_SEQUENCE - 1]["cell_id"] == RECOVERY_CELL_ID,
        "Sequence 486 differs from the frozen schedule",
    )
    manifest_by_id = {str(cell["cell_id"]): cell for cell in manifest}
    cell = manifest_by_id[RECOVERY_CELL_ID]
    raw_rows = read_jsonl(attempt_dir / "runs.jsonl")
    require(len(raw_rows) == 1, "Sequence 486 must have one raw result")
    raw_row = raw_rows[0]
    require(
        raw_row.get("outcome") == "misleading_failure"
        and raw_row.get("error_attribution")
        == "chart_induced_intermediate_decision_error",
        "Sequence-486 raw outcome changed",
    )
    events = read_jsonl(attempt_dir / "model_identity_events.jsonl")
    require(
        len(events) == EXPECTED_HTTP_REQUEST_COUNT,
        "Sequence 486 identity event count changed",
    )
    require(
        all(
            event.get("event_type") == "http_request"
            and event.get("result") == "success"
            and event.get("status_code") == 200
            and event.get("identity_validated") is True
            and event.get("requested_deployment") == EXPECTED_DEPLOYMENT
            and event.get("response_model") == EXPECTED_DEPLOYMENT
            and event.get("hidden_prompt_terms_seen") == []
            for event in events
        ),
        "Sequence-486 identity event evidence is invalid",
    )
    identity = validate_identity_evidence(
        row=raw_row,
        identity_log=attempt_dir / "model_identity_events.jsonl",
        expected_deployment=EXPECTED_DEPLOYMENT,
    )
    require(identity["valid"] is True, "Sequence-486 identity audit failed")
    require(
        identity["identity_event_count"] == EXPECTED_HTTP_REQUEST_COUNT
        and identity["traced_model_action_count"]
        == EXPECTED_HTTP_REQUEST_COUNT,
        "Sequence-486 request/trace count changed",
    )
    submissions = read_jsonl(attempt_dir / "submissions.jsonl")
    require(
        len(submissions) == 1
        and submissions[0] == raw_row.get("submission"),
        "Sequence-486 submission differs from the raw result",
    )

    start_events = [
        event
        for event in read_jsonl(root / "scheduling_execution_log.jsonl")
        if event.get("event_type") == "cell_start"
        and int(event.get("execution_sequence") or 0) == RECOVERY_SEQUENCE
    ]
    finish_events = [
        event
        for event in read_jsonl(root / "scheduling_execution_log.jsonl")
        if event.get("event_type") == "cell_finish"
        and int(event.get("execution_sequence") or 0) == RECOVERY_SEQUENCE
    ]
    require(
        len(start_events) == 1
        and start_events[0].get("cell_id") == RECOVERY_CELL_ID
        and finish_events == [],
        "Sequence-486 scheduling evidence is invalid",
    )
    scheduling = {
        "execution_sequence": RECOVERY_SEQUENCE,
        "started_at": start_events[0]["started_at"],
        "original_condition_order": start_events[0][
            "original_condition_order"
        ],
        "model_queue": start_events[0]["model_queue"],
        "scheduling_deviation_sha256": start_events[0][
            "scheduling_deviation_sha256"
        ],
    }
    enriched = {
        **raw_row,
        "pilot_identity_audit": identity,
        "pilot_cell": cell,
        "pilot_attempt": 1,
        "pilot_attempt_dir": RECOVERY_ATTEMPT_DIR.as_posix(),
        "pilot_actual_http_request_count": EXPECTED_HTTP_REQUEST_COUNT,
        "pilot_availability_aborted": False,
        "pilot_availability_http_429": False,
        "pilot_formal_attempt_consumed": True,
        "pilot_recovery_provenance": {
            "event": "gpt_false_stop_materialization",
            "deviation_record": DEVIATION_RELATIVE_PATH.as_posix(),
            "no_model_request": True,
        },
    }
    require(
        audit_cell(root=root, cell=cell, row=enriched) == [],
        "Sequence-486 enriched row failed infrastructure audit",
    )

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
        "actual_http_request_count": EXPECTED_HTTP_REQUEST_COUNT,
        "outcome": raw_row["outcome"],
        "error_attribution": raw_row["error_attribution"],
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
    progress = aggregate(root, manifest)
    stop_state = update_interface_stop_rule_state(root, manifest)

    require(
        progress["completed_cells"] == EXPECTED_COMPLETED_AFTER_RECOVERY
        and progress["missing_cells"] == EXPECTED_MISSING_AFTER_RECOVERY,
        "Recovery aggregate did not produce the 486-cell prefix",
    )
    require(
        stop_state["triggered"] is False
        and stop_state["observed_interface_errors_by_condition"]
        == EXPECTED_INTERFACE_COUNTS,
        "Evidence-based interface stop state is invalid",
    )
    require(
        raw_hashes(attempt_dir) == raw_before,
        "Raw sequence-486 evidence changed during recovery",
    )
    preservation_errors = verify_preserved_inventory(
        root,
        inventory_before["artifacts"],
    )
    require(not preservation_errors, "; ".join(preservation_errors))
    root_preservation_errors = verify_preserved_inventory(
        root,
        root_inventory_before["artifacts"],
    )
    require(not root_preservation_errors, "; ".join(root_preservation_errors))
    audit = stable_prefix_audit(
        root,
        expected_completed=EXPECTED_COMPLETED_AFTER_RECOVERY,
    )
    write_json(audit_path, audit)
    require(audit["approved"], "Materialized 486-cell prefix failed audit")

    after_hashes = selected_hashes(root)
    report = {
        "event": "gpt_false_stop_recovery_materialization",
        "materialized_at": recovery_time,
        "deviation_sha256": sha256_file(deviation_path),
        "implementation_sha256": sha256_file(Path(__file__)),
        "reviewed_code_hashes": reviewed_code_hashes(),
        "cell_id": RECOVERY_CELL_ID,
        "execution_sequence": RECOVERY_SEQUENCE,
        "attempt": 1,
        "no_model_request": True,
        "raw_child_files_preserved": True,
        "raw_child_hashes": raw_hashes(attempt_dir),
        "raw_child_tree_sha256": EXPECTED_RAW_TREE_SHA256,
        "preserved_artifact_inventory": inventory_before["artifacts"],
        "preserved_artifact_count": inventory_before["artifact_count"],
        "preserved_root_artifact_inventory": root_inventory_before[
            "artifacts"
        ],
        "preserved_root_artifact_count": root_inventory_before[
            "artifact_count"
        ],
        "preserved_root_tree_sha256": root_inventory_before["tree_sha256"],
        "before_hashes": before_hashes,
        "before_auxiliary_hashes": {
            name: EXPECTED_AUXILIARY_PAUSE_HASHES[name]
            for name in sorted(EXPECTED_AUXILIARY_PAUSE_HASHES)
        },
        "after_hashes": after_hashes,
        "progress": progress,
        "interface_stop_state": stop_state,
        "audit_path": AUDIT_RELATIVE_PATH.as_posix(),
        "audit_sha256": sha256_file(audit_path),
        "audit_approved": audit["approved"],
        "recovery_artifact_hashes": recovery_artifact_hashes(root),
    }
    write_json(materialization_path, report)
    validate_existing_materialization(root, report)
    return report


def materialize_with_lock(root: Path) -> dict[str, Any]:
    lock = acquire_output_root_lock(root)
    require(lock is not None, "Another pilot process holds the formal-root lock")
    try:
        return materialize(root)
    finally:
        lock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    report = materialize_with_lock(root)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
