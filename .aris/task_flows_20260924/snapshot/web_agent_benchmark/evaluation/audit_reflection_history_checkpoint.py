#!/usr/bin/env python3
"""Audit pilot infrastructure checkpoints without exposing treatment effects."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation.analyze_reflection_history_pilot import (
    validate_analysis_inputs,
)
from web_agent_benchmark.evaluation.audit_reflection_history_stage import (
    audit as audit_stage,
)
from web_agent_benchmark.evaluation.reflection_history import MEMORY_FIELDS
from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    DEFAULT_OUTPUT_ROOT,
    MODEL_CONFIGS,
    classify_effective_interface_error,
    read_jsonl,
    scheduled_cells,
    sha256_file,
    write_json,
)


SECRET_PATTERN = re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{16,}")
CHECKPOINTS = {64: "Gate 2", 256: "Gate 3", 512: "Gate 4"}
STAGE_GATES = {64: 2, 256: 3, 512: 4}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def model_action_steps(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for step in row.get("trace") or []
        if isinstance(step, dict)
        and isinstance(step.get("action"), dict)
        and "_raw" in step["action"]
    ]


def scan_secrets(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {
            ".json",
            ".jsonl",
            ".md",
            ".log",
            ".txt",
        }:
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SECRET_PATTERN.search(value):
            hits.append(str(path.relative_to(root)))
    return hits


def history_metadata_errors(
    *,
    cell_id: str,
    action_index: int,
    cell: dict[str, Any],
    history: Any,
) -> tuple[list[str], bool, bool]:
    prefix = f"{cell_id} action {action_index}"
    if not isinstance(history, dict):
        return [f"{prefix}: pilot history metadata is missing"], False, False
    required = {
        "condition",
        "history_chars",
        "history_tokens_estimated",
        "history_records_available",
        "history_records_injected",
        "retained_step_ids",
        "history_truncated",
        "history_payload_sha256",
        "state_hash",
        "action_signature",
        "memory_update",
        "schema_valid",
        "execution_status",
    }
    errors = [
        f"{prefix}: pilot history field {key!r} is missing"
        for key in sorted(required - set(history))
    ]
    condition = str(cell.get("condition") or "")
    if history.get("condition") != condition:
        errors.append(f"{prefix}: history condition differs from assigned condition")
    try:
        available = int(history["history_records_available"])
        injected = int(history["history_records_injected"])
        history_chars = int(history["history_chars"])
        history_tokens = int(history["history_tokens_estimated"])
    except (KeyError, TypeError, ValueError):
        return errors + [f"{prefix}: history counters are invalid"], False, False
    retained = history.get("retained_step_ids")
    if not isinstance(retained, list) or not all(
        isinstance(value, int) for value in retained
    ):
        errors.append(f"{prefix}: retained_step_ids is not an integer list")
        retained = []
    if len(retained) != injected or len(set(retained)) != len(retained):
        errors.append(f"{prefix}: retained step IDs differ from injected count")
    if any(value < 0 or value >= available for value in retained):
        errors.append(f"{prefix}: retained step ID is outside available history")
    if available != action_index:
        errors.append(
            f"{prefix}: available history {available} differs from prior "
            f"decision count {action_index}"
        )
    if history_chars < 0 or history_tokens < 0:
        errors.append(f"{prefix}: history size counters are negative")
    token_limit = int(cell.get("history_token_limit") or 3000)
    if history_tokens > token_limit:
        errors.append(f"{prefix}: history exceeds token limit")
    for key in ("history_payload_sha256", "state_hash"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(history.get(key) or "")):
            errors.append(f"{prefix}: {key} is not a SHA-256 digest")
    if not str(history.get("action_signature") or ""):
        errors.append(f"{prefix}: action signature is empty")
    memory = history.get("memory_update")
    if not isinstance(memory, dict) or set(memory) != set(MEMORY_FIELDS):
        errors.append(f"{prefix}: memory_update does not match frozen schema")
    truncated = bool(history.get("history_truncated"))
    if condition == "no_history":
        if injected != 0 or retained:
            errors.append(f"{prefix}: no_history injected records")
    elif condition == "previous_step":
        wanted = 0 if available == 0 else 1
        if injected != wanted:
            errors.append(f"{prefix}: previous_step injection differs")
        if retained and retained != [available - 1]:
            errors.append(f"{prefix}: previous_step retained the wrong step")
    elif condition == "full_history":
        if injected > available or (not truncated and injected != available):
            errors.append(f"{prefix}: full_history injection differs")
        if retained != sorted(retained):
            errors.append(f"{prefix}: full_history retained IDs are unordered")
    elif condition == "structured_falsification":
        wanted = 0 if available == 0 else 1
        if injected != wanted:
            errors.append(f"{prefix}: structured ledger injection differs")
        if retained and retained != [available - 1]:
            errors.append(f"{prefix}: structured ledger retained the wrong step")
    else:
        errors.append(f"{prefix}: unknown condition {condition!r}")
    return errors, history.get("schema_valid") is not True, truncated


def audit(
    root: Path,
    *,
    expected_completed: int,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    stage_report = audit_stage(root, STAGE_GATES[expected_completed])
    if not stage_report.get("approved_by_automated_audit"):
        errors.extend(
            f"stage audit: {message}"
            for message in stage_report.get("errors") or []
        )
    manifest_path = root / "preregistered_cells.jsonl"
    runs_path = root / "runs.jsonl"
    if not manifest_path.exists():
        return {
            "approved": False,
            "errors": ["preregistered_cells.jsonl is missing"],
        }
    manifest = read_jsonl(manifest_path)
    rows = read_jsonl(runs_path)
    if len(manifest) != 512:
        errors.append(f"manifest has {len(manifest)} cells, expected 512")
    if len(rows) != expected_completed:
        errors.append(
            f"runs.jsonl has {len(rows)} rows, expected {expected_completed}"
        )

    try:
        validation = validate_analysis_inputs(
            root,
            manifest,
            rows,
            allow_incomplete=True,
        )
    except Exception as exc:
        validation = {"error": f"{type(exc).__name__}: {exc}"}
        errors.append(f"analysis input validation failed: {exc}")

    scheduled = scheduled_cells(manifest)
    expected_ids = {
        str(cell["cell_id"]) for cell in scheduled[:expected_completed]
    }
    observed_ids = {
        str((row.get("pilot_cell") or {}).get("cell_id") or "")
        for row in rows
    }
    if observed_ids != expected_ids:
        errors.append("completed rows are not the expected frozen schedule prefix")
    chosen_ids = {
        path.parent.name
        for path in (root / "cells").glob("*/chosen_result.json")
    }
    if chosen_ids != observed_ids:
        errors.append(
            "chosen_result files differ from the frozen runs.jsonl checkpoint"
        )
    schedule_events = read_jsonl(root / "scheduling_execution_log.jsonl")
    starts = {
        (
            str(event.get("cell_id") or ""),
            int(event.get("execution_sequence") or 0),
        )
        for event in schedule_events
        if event.get("event_type") == "cell_start"
    }
    terminals = {
        (
            str(event.get("cell_id") or ""),
            int(event.get("execution_sequence") or 0),
        )
        for event in schedule_events
        if event.get("event_type") in {"cell_finish", "cell_abort"}
    }
    unresolved_starts = sorted(starts - terminals)
    if unresolved_starts:
        errors.append(
            f"checkpoint has {len(unresolved_starts)} in-flight scheduling starts"
        )
    touched_outside_prefix = sorted(
        cell_id
        for cell_id, _ in starts
        if cell_id not in expected_ids
    )
    if touched_outside_prefix:
        errors.append(
            "checkpoint touched cells beyond the frozen completed prefix: "
            + ", ".join(touched_outside_prefix[:5])
        )

    interface_errors = 0
    failure_classifications: Counter[str] = Counter()
    invalid_schema_steps = 0
    invalid_schema_by_model_condition: Counter[str] = Counter()
    truncation_steps = 0
    condition_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    identity_failures: list[str] = []
    for row in rows:
        cell = row.get("pilot_cell") or {}
        cell_id = str(cell.get("cell_id") or "")
        condition = str(cell.get("condition") or "")
        model = str(cell.get("model") or "")
        condition_counts[condition] += 1
        model_counts[model] += 1
        expected_deployment = str(
            (MODEL_CONFIGS.get(model) or {}).get("deployment_id") or ""
        )
        identity = row.get("pilot_identity_audit") or {}
        failure_classification = classify_effective_interface_error(
            output_root=root,
            row=row,
        )
        failure_classifications[
            str(failure_classification["category"])
        ] += 1
        is_interface = bool(
            failure_classification["is_interface_error"]
        )
        untraced_non_interface_failure = (
            failure_classification["category"]
            in {"non_interface_harness", "non_interface_parser"}
        )
        errors.extend(
            f"{cell_id}: interface classification: {message}"
            for message in (
                failure_classification.get("classification_errors") or []
            )
        )
        interface_errors += int(is_interface)
        if identity.get("valid") is not True:
            identity_failures.append(cell_id)
            if not is_interface and not untraced_non_interface_failure:
                errors.append(
                    f"{cell_id}: invalid model identity was accepted as a "
                    "non-interface result"
                )
        attempt_relative = str(row.get("pilot_attempt_dir") or "")
        attempt_dir = root / attempt_relative
        identity_events = read_jsonl(
            attempt_dir / "model_identity_events.jsonl"
        )
        request_count = int(row.get("pilot_actual_http_request_count") or 0)
        if len(identity_events) != request_count:
            errors.append(
                f"{cell_id}: identity event count {len(identity_events)} "
                f"differs from HTTP request count {request_count}"
            )
        for event_index, event in enumerate(identity_events):
            event_prefix = f"{cell_id} request {event_index}"
            if event.get("event_type") != "http_request":
                errors.append(f"{event_prefix}: event type is not http_request")
            if event.get("requested_deployment") != expected_deployment:
                errors.append(f"{event_prefix}: requested UUID differs")
            if not re.fullmatch(
                r"[0-9a-f]{64}",
                str(event.get("request_payload_sha256") or ""),
            ):
                errors.append(f"{event_prefix}: request payload hash is invalid")
            if event.get("hidden_prompt_terms_seen") != []:
                errors.append(
                    f"{event_prefix}: internal metadata appears in exact payload"
                )
            if event.get("result") == "success":
                if event.get("response_model") != expected_deployment:
                    errors.append(f"{event_prefix}: response UUID differs")
                if event.get("identity_validated") is not True:
                    errors.append(f"{event_prefix}: identity was not validated")
            elif event.get("identity_validated") is True:
                errors.append(
                    f"{event_prefix}: failed request is marked identity-valid"
                )

        trace = [
            step for step in row.get("trace") or [] if isinstance(step, dict)
        ]
        if (
            (not trace or request_count == 0)
            and not (
                untraced_non_interface_failure and request_count > 0
            )
        ):
            errors.append(
                f"{cell_id}: formal row contains no auditable model decision request"
            )
        if (
            request_count != len(trace)
            and not untraced_non_interface_failure
        ):
            errors.append(
                f"{cell_id}: HTTP request count {request_count} differs from "
                f"{len(trace)} trace decision steps"
            )
        for trace_index, step in enumerate(trace):
            if step.get("pilot_hidden_terms_seen") != []:
                errors.append(
                    f"{cell_id} trace {trace_index}: internal metadata appears "
                    "in full DOM text before the model request"
                )
            screenshot = Path(str(step.get("screenshot") or ""))
            if not screenshot.is_file():
                errors.append(
                    f"{cell_id} trace {trace_index}: screenshot is missing"
                )
            sanitization = step.get("pilot_ui_sanitization")
            if not isinstance(sanitization, dict) or sanitization.get(
                "applied_before_screenshot_and_state_capture"
            ) is not True:
                errors.append(
                    f"{cell_id} trace {trace_index}: UI sanitization is not auditable"
                )

        actions = model_action_steps(row)
        for action_index, step in enumerate(actions):
            action = step["action"]
            metadata = action.get("_response_metadata") or {}
            if metadata.get("requested_deployment") != expected_deployment:
                errors.append(
                    f"{cell_id} action {action_index}: requested UUID differs"
                )
            if metadata.get("response_model") != expected_deployment:
                errors.append(
                    f"{cell_id} action {action_index}: response UUID differs"
                )
            if metadata.get("identity_validated") is not True:
                errors.append(
                    f"{cell_id} action {action_index}: identity is not validated"
                )
            if metadata.get("hidden_prompt_terms_seen") != []:
                errors.append(
                    f"{cell_id} action {action_index}: internal metadata appears "
                    "in the exact model request payload"
                )
            history_errors, invalid_schema, truncated = history_metadata_errors(
                cell_id=cell_id,
                action_index=action_index,
                cell=cell,
                history=step.get("pilot_history"),
            )
            errors.extend(history_errors)
            invalid_schema_steps += int(invalid_schema)
            if invalid_schema:
                invalid_schema_by_model_condition[f"{model}|{condition}"] += 1
            truncation_steps += int(truncated)

    if identity_failures:
        warnings.append(
            f"{len(identity_failures)} final interface rows lack valid identity "
            "evidence and remain fail-closed"
        )
    if invalid_schema_steps:
        warnings.append(
            f"{invalid_schema_steps} model steps returned an invalid pilot schema"
        )
    secret_hits = scan_secrets(root)
    if secret_hits:
        errors.append(f"credential-like text found in {secret_hits}")

    manifest_sha = sha256_file(manifest_path)
    preregistration = load_json(root / "preregistration.json")
    if manifest_sha != preregistration.get("manifest_sha256"):
        errors.append("manifest SHA differs from preregistration")
    return {
        "gate": CHECKPOINTS.get(
            expected_completed,
            f"Checkpoint {expected_completed}",
        ),
        "effect_results_blinded": True,
        "approved": not errors,
        "expected_completed": expected_completed,
        "actual_completed": len(rows),
        "remaining": len(manifest) - len(rows),
        "manifest_sha256": manifest_sha,
        "condition_cell_counts": dict(sorted(condition_counts.items())),
        "model_cell_counts": dict(sorted(model_counts.items())),
        "interface_error_count": interface_errors,
        "failure_classification_counts": dict(
            sorted(failure_classifications.items())
        ),
        "identity_failure_count": len(identity_failures),
        "invalid_schema_step_count": invalid_schema_steps,
        "invalid_schema_steps_by_model_condition": dict(
            sorted(invalid_schema_by_model_condition.items())
        ),
        "history_truncation_step_count": truncation_steps,
        "input_validation": validation,
        "stage_audit": stage_report,
        "secret_hits": secret_hits,
        "warnings": warnings,
        "errors": errors,
    }


def write_report(root: Path, report: dict[str, Any]) -> None:
    count = int(report.get("expected_completed") or 0)
    stem = f"gate_checkpoint_{count:03d}_infrastructure_audit"
    write_json(root / f"{stem}.json", report)
    lines = [
        f"# {report.get('gate', 'Checkpoint')} Infrastructure Audit",
        "",
        f"- Approved: **{report.get('approved')}**",
        f"- Completed: `{report.get('actual_completed')}/{report.get('expected_completed')}`",
        f"- Effect results blinded: `{report.get('effect_results_blinded')}`",
        f"- Manifest SHA-256: `{report.get('manifest_sha256')}`",
        f"- Interface-error rows: `{report.get('interface_error_count')}`",
        f"- Identity failures kept fail-closed: `{report.get('identity_failure_count')}`",
        f"- Invalid schema steps: `{report.get('invalid_schema_step_count')}`",
        f"- History truncation steps: `{report.get('history_truncation_step_count')}`",
    ]
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in report["warnings"])
    if report.get("errors"):
        lines.extend(["", "## Blocking Errors", ""])
        lines.extend(f"- {item}" for item in report["errors"])
    (root / f"{stem}.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--expected-completed",
        type=int,
        choices=sorted(CHECKPOINTS),
        required=True,
    )
    args = parser.parse_args()
    root = args.root.resolve()
    report = audit(
        root,
        expected_completed=args.expected_completed,
    )
    write_report(root, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
