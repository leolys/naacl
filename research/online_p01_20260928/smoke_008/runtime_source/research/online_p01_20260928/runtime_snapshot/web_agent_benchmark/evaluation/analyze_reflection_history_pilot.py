#!/usr/bin/env python3
"""Analyze the preregistered cross-step reflection pilot after result freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from web_agent_benchmark.evaluation.reflection_cycle_metrics import (
    analyze_cycles,
    is_submission,
)
from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    CONDITIONS,
    DEFAULT_OUTPUT_ROOT,
    REPO_ROOT,
    SCENARIOS,
    SCHEDULING_MODEL_ORDER,
    classify_effective_interface_error,
    classify_stop_rule_interface_error,
    is_stop_rule_interface_error,
    read_jsonl,
    runtime_routes,
    sha256_file,
    write_json,
    write_jsonl,
)


BOOTSTRAP_SEED = 20260727
BOOTSTRAP_SAMPLES = 2000
PUBLIC_ACTION_FIELDS = ("action", "text", "select_name", "option_text")
STRICT_FAIL_CLOSED_POLICY = "first_schema_warning_blocks_browser_action"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_specs() -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for benchmark in ("official", "clean"):
        for scenario, config in SCENARIOS.items():
            path = (
                REPO_ROOT
                / "web_agent_benchmark"
                / f"{benchmark}_benchmark_v1"
                / config["tasks_file"]
            )
            for row in read_jsonl(path):
                slug = str(row.get("official_slug") or row.get("slug") or "")
                result[(benchmark, scenario, slug)] = row
    return result


def selected_action_id(row: dict[str, Any]) -> str:
    return str(
        row.get("selected_action_id")
        or (row.get("submission") or {}).get("selected_action_id")
        or ""
    )


def schema_step_records(row: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    for index, step in enumerate(row.get("trace") or []):
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        pilot = step.get("pilot_history")
        if (
            isinstance(action, dict)
            and "_raw" in action
            and isinstance(pilot, dict)
            and "schema_valid" in pilot
        ):
            records.append((index, step))
    return records


def public_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        key: action[key]
        for key in PUBLIC_ACTION_FIELDS
        if key in action and action[key] not in (None, "")
    }


def step_submission(
    row: dict[str, Any],
    index: int,
) -> dict[str, Any] | None:
    trace = row.get("trace") or []
    if index < 0 or index >= len(trace):
        return None
    step = trace[index]
    explicit = step.get("submission")
    if isinstance(explicit, dict) and explicit:
        return explicit
    run_submission = row.get("submission")
    if (
        index == len(trace) - 1
        and isinstance(run_submission, dict)
        and run_submission
        and is_submission(step)
    ):
        return run_submission
    return None


def submission_action_id(submission: dict[str, Any] | None) -> str:
    return str((submission or {}).get("selected_action_id") or "")


def schema_cell_diagnostics(
    row: dict[str, Any],
    misleading_ids: list[str],
) -> dict[str, Any]:
    records = schema_step_records(row)
    applicable = bool(records)
    warning_records = [
        (index, step)
        for index, step in records
        if (step.get("pilot_history") or {}).get("schema_valid") is not True
    ]
    trace = row.get("trace") or []
    selected = selected_action_id(row)
    primary_cycle = analyze_cycles({
        **row,
        "selected_action_id": selected,
        "misleading_action_ids_for_analysis": misleading_ids,
    })
    primary_harmful = bool(selected and selected in set(misleading_ids))
    base = {
        "schema_compliance_applicable": applicable,
        "schema_step_count": len(records),
        "schema_warning_step_count": len(warning_records),
        "schema_compliant_cell": (
            not warning_records if applicable else None
        ),
        "first_schema_warning_step": (
            warning_records[0][0]
            if warning_records
            else None
        ),
        "first_schema_warning_runner_step": (
            warning_records[0][1].get("step")
            if warning_records
            else None
        ),
        "strict_fail_closed": {
            "policy": STRICT_FAIL_CLOSED_POLICY,
            "schema_blocked": False,
            "blocked_step": None,
            "blocked_runner_step": None,
            "terminal_schema_failure_step": None,
            "blocked_proposed_action": None,
            "blocked_action_would_submit": False,
            "blocked_submission_evidence": None,
            "blocked_action_would_be_harmful": False,
            "model_request_count": len(records),
            "outcome": row.get("outcome"),
            "error_attribution": row.get("error_attribution"),
            "interface_error": is_stop_rule_interface_error(row),
            "agent_error_class": classify_stop_rule_interface_error(
                row
            )["category"],
            "selected_action_id": selected,
            "harmful_submission": primary_harmful,
            **usage(row),
            **primary_cycle,
        },
    }
    if not warning_records:
        return base

    warning_index, warning_step = warning_records[0]
    prefix = trace[:warning_index]
    prior_submission: dict[str, Any] | None = None
    for index in range(warning_index):
        if submission := step_submission(row, index):
            prior_submission = submission
    prior_selected = submission_action_id(prior_submission)
    retained_terminal = prior_submission is not None
    prefix_outcome = row.get("outcome") if retained_terminal else "schema_blocked"
    prefix_error_attribution = (
        row.get("error_attribution")
        if retained_terminal
        else "schema_parser_policy_block"
    )
    prefix_cycle = analyze_cycles({
        **row,
        "trace": prefix,
        "outcome": prefix_outcome,
        "selected_action_id": prior_selected,
        "misleading_action_ids_for_analysis": misleading_ids,
    })
    explicit_blocked_submission = warning_step.get("submission")
    has_explicit_blocked_submission = bool(
        isinstance(explicit_blocked_submission, dict)
        and explicit_blocked_submission
    )
    blocked_would_submit = (
        has_explicit_blocked_submission or is_submission(warning_step)
    )
    blocked_submission = (
        step_submission(row, warning_index)
        if blocked_would_submit
        else None
    )
    blocked_selected = submission_action_id(blocked_submission)
    blocked_would_be_harmful: bool | None
    if not blocked_would_submit:
        blocked_would_be_harmful = False
    elif blocked_submission is None or not blocked_selected:
        blocked_would_be_harmful = None
    else:
        blocked_would_be_harmful = blocked_selected in set(misleading_ids)
    strict_usage = usage({"trace": trace[: warning_index + 1]})
    base["strict_fail_closed"] = {
        "policy": STRICT_FAIL_CLOSED_POLICY,
        "schema_blocked": True,
        "blocked_step": warning_index,
        "blocked_runner_step": warning_step.get("step"),
        "terminal_schema_failure_step": warning_index,
        "blocked_proposed_action": public_action(
            warning_step.get("action") or {}
        ),
        "blocked_action_would_submit": blocked_would_submit,
        "blocked_submission_evidence": (
            "explicit_step_submission"
            if has_explicit_blocked_submission
            else (
                "deterministic_action_rule"
                if blocked_would_submit
                else None
            )
        ),
        "blocked_action_would_be_harmful": blocked_would_be_harmful,
        "model_request_count": sum(
            index <= warning_index for index, _ in records
        ),
        "outcome": prefix_outcome,
        "error_attribution": prefix_error_attribution,
        "interface_error": False,
        "selected_action_id": prior_selected,
        "harmful_submission": bool(
            prior_selected and prior_selected in set(misleading_ids)
        ),
        **strict_usage,
        **prefix_cycle,
    }
    return base


def usage(row: dict[str, Any]) -> dict[str, int]:
    result = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for step in row.get("trace") or []:
        metadata = (step.get("action") or {}).get("_response_metadata") or {}
        step_usage = metadata.get("usage") or {}
        prompt = int(
            step_usage.get("prompt_tokens")
            or step_usage.get("input_tokens")
            or 0
        )
        completion = int(
            step_usage.get("completion_tokens")
            or step_usage.get("output_tokens")
            or 0
        )
        result["prompt_tokens"] += prompt
        result["completion_tokens"] += completion
        result["total_tokens"] += int(
            step_usage.get("total_tokens")
            or prompt + completion
        )
    return result


def enrich(
    rows: list[dict[str, Any]],
    *,
    output_root: Path | None = None,
) -> list[dict[str, Any]]:
    specs = task_specs()
    output: list[dict[str, Any]] = []
    for row in rows:
        cell = row.get("pilot_cell") or {}
        key = (str(cell.get("benchmark")), str(cell.get("scenario")), str(cell.get("slug")))
        task = specs.get(key, {})
        misleading_ids = [str(value) for value in task.get("misleading_action_ids") or []]
        action_id = selected_action_id(row)
        cycle_input = {
            **row,
            "selected_action_id": action_id,
            "misleading_action_ids_for_analysis": misleading_ids,
        }
        cycle = analyze_cycles(cycle_input)
        token_usage = usage(row)
        schema = schema_cell_diagnostics(row, misleading_ids)
        failure_classification = (
            classify_effective_interface_error(
                output_root=output_root,
                row=row,
            )
            if output_root is not None
            else classify_stop_rule_interface_error(row)
        )
        schema["strict_fail_closed"]["interface_error"] = bool(
            failure_classification["is_interface_error"]
        )
        schema["strict_fail_closed"]["agent_error_class"] = str(
            failure_classification["category"]
        )
        schema_steps = [
            (step.get("pilot_history") or {}).get("schema_valid") is True
            for _, step in schema_step_records(row)
        ]
        output.append({
            "cell_id": cell.get("cell_id"),
            "condition_order": cell.get("condition_order"),
            "benchmark": cell.get("benchmark"),
            "scenario": cell.get("scenario"),
            "slug": cell.get("slug"),
            "stratum": cell.get("stratum"),
            "model": cell.get("model"),
            "condition": cell.get("condition"),
            "repetition": cell.get("repetition"),
            "outcome": row.get("outcome"),
            "error_attribution": row.get("error_attribution"),
            "interface_error": bool(
                failure_classification["is_interface_error"]
            ),
            "agent_error_class": str(
                failure_classification["category"]
            ),
            "selected_action_id": action_id,
            "harmful_submission": bool(action_id and action_id in misleading_ids),
            "schema_valid_rate": mean(schema_steps) if schema_steps else None,
            **schema,
            "history_tokens_max": max(
                [
                    int((step.get("pilot_history") or {}).get("history_tokens_estimated") or 0)
                    for step in row.get("trace") or []
                ],
                default=0,
            ),
            "history_truncation_count": sum(
                bool((step.get("pilot_history") or {}).get("history_truncated"))
                for step in row.get("trace") or []
            ),
            "pilot_attempt": row.get("pilot_attempt"),
            "pilot_attempt_dir": row.get("pilot_attempt_dir"),
            **cycle,
            **token_usage,
        })
    return output


def rate(rows: list[dict[str, Any]], key: str) -> float:
    return mean(bool(row.get(key)) for row in rows) if rows else 0.0


def group_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["model"]), str(row["benchmark"]), str(row["condition"]))].append(row)
    output: list[dict[str, Any]] = []
    for (model, benchmark, condition), group in sorted(groups.items()):
        output.append({
            "model": model,
            "benchmark": benchmark,
            "condition": condition,
            "n": len(group),
            "success_rate": rate(group, "task_success"),
            "cycle_incidence": rate(group, "state_action_cycle_incidence"),
            "harmful_submission_rate": rate(group, "harmful_submission"),
            "agent_error_rate": rate(group, "agent_error"),
            "avg_steps": mean(float(row["step_count"]) for row in group),
            "avg_recurrence_count": mean(
                float(row["state_action_recurrence_count"]) for row in group
            ),
            "schema_valid_rate": mean(
                value
                for row in group
                if (value := row.get("schema_valid_rate")) is not None
            ) if any(row.get("schema_valid_rate") is not None for row in group) else None,
            "avg_prompt_tokens": mean(float(row["prompt_tokens"]) for row in group),
            "avg_completion_tokens": mean(float(row["completion_tokens"]) for row in group),
        })
    return output


def schema_compliance_summary(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["model"]),
            str(row["benchmark"]),
            str(row["condition"]),
        )
        groups[key].append(row)
    output: list[dict[str, Any]] = []
    for (model, benchmark, condition), group in sorted(groups.items()):
        applicable = [
            row
            for row in group
            if row.get("schema_compliance_applicable") is True
        ]
        compliant = [
            row
            for row in applicable
            if row.get("schema_compliant_cell") is True
        ]
        warning_cells = [
            row
            for row in applicable
            if row.get("schema_compliant_cell") is False
        ]
        schema_steps = sum(
            int(row.get("schema_step_count") or 0)
            for row in group
        )
        warning_steps = sum(
            int(row.get("schema_warning_step_count") or 0)
            for row in group
        )
        truncation_cells = sum(
            int(row.get("history_truncation_count") or 0) > 0
            for row in group
        )
        blocked = [
            row.get("strict_fail_closed") or {}
            for row in group
            if (row.get("strict_fail_closed") or {}).get("schema_blocked")
        ]
        output.append({
            "model": model,
            "benchmark": benchmark,
            "condition": condition,
            "cell_count": len(group),
            "applicable_cell_count": len(applicable),
            "not_applicable_cell_count": len(group) - len(applicable),
            "compliant_cell_count": len(compliant),
            "warning_cell_count": len(warning_cells),
            "warning_cell_rate": (
                len(warning_cells) / len(applicable)
                if applicable
                else None
            ),
            "warning_cell_rate_all_cells": (
                len(warning_cells) / len(group)
                if group
                else None
            ),
            "cell_compliance_rate": (
                len(compliant) / len(applicable)
                if applicable
                else None
            ),
            "schema_step_count": schema_steps,
            "schema_warning_step_count": warning_steps,
            "schema_warning_step_rate": (
                warning_steps / schema_steps
                if schema_steps
                else None
            ),
            "step_compliance_rate": (
                (schema_steps - warning_steps) / schema_steps
                if schema_steps
                else None
            ),
            "history_truncation_step_count": sum(
                int(row.get("history_truncation_count") or 0)
                for row in group
            ),
            "history_truncation_cell_count": truncation_cells,
            "strict_fail_closed_blocked_cell_count": len(blocked),
            "blocked_submit_action_count": sum(
                item.get("blocked_action_would_submit") is True
                for item in blocked
            ),
            "proven_harmful_blocked_submit_count": sum(
                item.get("blocked_action_would_be_harmful") is True
                for item in blocked
            ),
            "unknown_harm_blocked_submit_count": sum(
                item.get("blocked_action_would_submit") is True
                and item.get("blocked_action_would_be_harmful") is None
                for item in blocked
            ),
        })
    return output


def apply_strict_fail_closed_policy(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        strict = row.get("strict_fail_closed") or {}
        transformed = dict(row)
        for key, value in strict.items():
            if key in transformed:
                transformed[key] = value
        transformed["strict_fail_closed_policy"] = strict.get("policy")
        transformed["schema_blocked"] = bool(strict.get("schema_blocked"))
        transformed["blocked_step"] = strict.get("blocked_step")
        transformed["blocked_runner_step"] = strict.get(
            "blocked_runner_step"
        )
        transformed["blocked_proposed_action"] = strict.get(
            "blocked_proposed_action"
        )
        transformed["blocked_action_would_submit"] = strict.get(
            "blocked_action_would_submit"
        )
        transformed["blocked_submission_evidence"] = strict.get(
            "blocked_submission_evidence"
        )
        transformed["blocked_action_would_be_harmful"] = strict.get(
            "blocked_action_would_be_harmful"
        )
        transformed["strict_fail_closed_model_request_count"] = strict.get(
            "model_request_count"
        )
        output.append(transformed)
    if [row.get("cell_id") for row in output] != [
        row.get("cell_id") for row in rows
    ]:
        raise RuntimeError("Strict fail-closed sensitivity changed cell identity")
    original_weights = Counter(
        (row.get("model"), row.get("benchmark"), row.get("condition"))
        for row in rows
    )
    transformed_weights = Counter(
        (row.get("model"), row.get("benchmark"), row.get("condition"))
        for row in output
    )
    if transformed_weights != original_weights:
        raise RuntimeError("Strict fail-closed sensitivity changed group weights")
    return output


def validate_analysis_inputs(
    output_root: Path,
    manifest: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    allow_incomplete: bool,
) -> dict[str, Any]:
    manifest_path = output_root / "preregistered_cells.jsonl"
    preregistration = json.loads(
        (output_root / "preregistration.json").read_text(encoding="utf-8")
    )
    actual_hash = sha256_file(manifest_path)
    if actual_hash != preregistration.get("manifest_sha256"):
        raise RuntimeError("Manifest SHA-256 differs from frozen preregistration")
    run_config_path = output_root / "pilot_run_config.json"
    routes_path = output_root / "runtime_routes.json"
    if not run_config_path.exists() or not routes_path.exists():
        raise RuntimeError("Runtime route freeze files are missing")
    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    if sha256_file(routes_path) != run_config.get("runtime_routes_sha256"):
        raise RuntimeError("Runtime route SHA-256 differs from frozen run config")
    if json.loads(routes_path.read_text(encoding="utf-8")) != runtime_routes():
        raise RuntimeError("Runtime route content differs from current frozen route")
    scheduling_validation: dict[str, Any] | None = None
    scheduling_relative = run_config.get("scheduling_deviation_path")
    if len(manifest) == 512 and not scheduling_relative:
        raise RuntimeError("Formal pilot lacks frozen scheduling deviation")
    if scheduling_relative:
        scheduling_path = output_root / str(scheduling_relative)
        if not scheduling_path.exists():
            raise RuntimeError("Scheduling deviation file is missing")
        scheduling_sha = sha256_file(scheduling_path)
        if scheduling_sha != run_config.get("scheduling_deviation_sha256"):
            raise RuntimeError("Scheduling deviation SHA-256 differs from run config")
        scheduling = json.loads(scheduling_path.read_text(encoding="utf-8"))
        if scheduling.get("manifest_sha256") != actual_hash:
            raise RuntimeError("Scheduling deviation refers to another manifest")
        if scheduling.get("model_queue_order") != list(SCHEDULING_MODEL_ORDER):
            raise RuntimeError("Scheduling model queue order changed")
        queue_ids = [
            str(cell_id)
            for queue in scheduling.get("queues") or []
            for cell_id in queue.get("cell_ids") or []
        ]
        if queue_ids != [
            str(cell["cell_id"])
            for model in SCHEDULING_MODEL_ORDER
            for cell in manifest
            if cell["model"] == model
        ]:
            raise RuntimeError("Scheduling queues differ from stable manifest partition")

        schedule_log = read_jsonl(
            output_root
            / str(
                run_config.get(
                    "scheduling_execution_log",
                    "scheduling_execution_log.jsonl",
                )
            )
        )
        starts = [
            event
            for event in schedule_log
            if event.get("event_type") == "cell_start"
        ]
        finish_events = [
            event
            for event in schedule_log
            if event.get("event_type") == "cell_finish"
        ]
        finishes = {
            (
                str(event.get("cell_id") or ""),
                int(event.get("execution_sequence") or 0),
            )
            for event in finish_events
        }
        if len(finishes) != len(finish_events):
            raise RuntimeError("Scheduling log contains duplicate finish events")
        model_rank = {
            model: index for index, model in enumerate(SCHEDULING_MODEL_ORDER)
        }
        manifest_by_id_for_schedule = {
            str(cell["cell_id"]): cell for cell in manifest
        }
        previous_rank = -1
        previous_sequence = 0
        previous_order_by_model: dict[str, int] = {}
        seen_sequences: set[int] = set()
        start_keys: set[tuple[str, int]] = set()
        for event in starts:
            cell_id = str(event.get("cell_id") or "")
            if cell_id not in manifest_by_id_for_schedule:
                raise RuntimeError(f"Scheduling log contains unknown cell {cell_id}")
            cell = manifest_by_id_for_schedule[cell_id]
            sequence = int(event.get("execution_sequence") or 0)
            if sequence != previous_sequence + 1 or sequence in seen_sequences:
                raise RuntimeError("Scheduling execution sequence is invalid")
            previous_sequence = sequence
            seen_sequences.add(sequence)
            start_keys.add((cell_id, sequence))
            model = str(cell["model"])
            rank = model_rank[model]
            if rank < previous_rank:
                raise RuntimeError("Scheduling log switched back to an earlier model queue")
            previous_rank = rank
            order = int(cell["condition_order"])
            if order < previous_order_by_model.get(model, -1):
                raise RuntimeError(
                    f"Scheduling log changed relative order for {model}"
                )
            previous_order_by_model[model] = order
            if int(event.get("original_condition_order") or 0) != order:
                raise RuntimeError("Scheduling log condition_order differs")
            if event.get("model_queue") != model:
                raise RuntimeError("Scheduling log model queue differs")
            if event.get("scheduling_deviation_sha256") != scheduling_sha:
                raise RuntimeError("Scheduling start event SHA differs")

        for row in rows:
            scheduling_row = row.get("pilot_scheduling")
            if not isinstance(scheduling_row, dict):
                raise RuntimeError(
                    f"Result lacks scheduling record for "
                    f"{(row.get('pilot_cell') or {}).get('cell_id')}"
                )
            cell_id = str((row.get("pilot_cell") or {}).get("cell_id") or "")
            sequence = int(scheduling_row.get("execution_sequence") or 0)
            if (cell_id, sequence) not in start_keys:
                raise RuntimeError(
                    f"Result lacks matching scheduling start event for {cell_id}"
                )
            if (cell_id, sequence) not in finishes:
                raise RuntimeError(
                    f"Result lacks matching scheduling finish event for {cell_id}"
                )
            if (
                scheduling_row.get("scheduling_deviation_sha256")
                != scheduling_sha
            ):
                raise RuntimeError(
                    f"Result scheduling SHA differs for {cell_id}"
                )
        scheduling_validation = {
            "scheduling_deviation_sha256": scheduling_sha,
            "cell_start_events": len(starts),
            "cell_finish_events": len(finishes),
            "model_queue_order": list(SCHEDULING_MODEL_ORDER),
        }
    manifest_ids = [str(cell.get("cell_id") or "") for cell in manifest]
    if len(manifest_ids) != len(set(manifest_ids)):
        raise RuntimeError("Duplicate cell_id in preregistered manifest")
    manifest_by_id = {str(cell["cell_id"]): cell for cell in manifest}

    row_ids = [
        str((row.get("pilot_cell") or {}).get("cell_id") or "")
        for row in rows
    ]
    if len(row_ids) != len(set(row_ids)):
        duplicates = [
            cell_id
            for cell_id, count in Counter(row_ids).items()
            if count > 1
        ]
        raise RuntimeError(f"Duplicate result cell_id(s): {duplicates}")
    unknown = sorted(set(row_ids) - set(manifest_ids))
    if unknown:
        raise RuntimeError(f"Result contains unknown cell_id(s): {unknown}")
    missing = sorted(set(manifest_ids) - set(row_ids))
    if missing and not allow_incomplete:
        raise RuntimeError(f"Results are missing {len(missing)} preregistered cells")

    for row in rows:
        pilot_cell = row.get("pilot_cell") or {}
        cell_id = str(pilot_cell.get("cell_id") or "")
        expected = manifest_by_id[cell_id]
        if pilot_cell != expected:
            changed = {
                key: {"expected": expected.get(key), "actual": pilot_cell.get(key)}
                for key in sorted(set(expected) | set(pilot_cell))
                if expected.get(key) != pilot_cell.get(key)
            }
            raise RuntimeError(f"Frozen pilot_cell mismatch for {cell_id}: {changed}")
        attempt = int(row.get("pilot_attempt") or 0)
        relative = str(row.get("pilot_attempt_dir") or "")
        expected_prefix = f"cells/{cell_id}/attempt_"
        if attempt not in {1, 2, 3} or not relative.startswith(expected_prefix):
            raise RuntimeError(f"Chosen attempt does not belong to cell {cell_id}")
        chosen_path = output_root / "cells" / cell_id / "chosen_result.json"
        if not chosen_path.exists():
            raise RuntimeError(f"Missing chosen_result.json for {cell_id}")
        chosen = json.loads(chosen_path.read_text(encoding="utf-8"))
        if chosen != row:
            raise RuntimeError(f"runs.jsonl row differs from chosen result for {cell_id}")
        identity_audit = row.get("pilot_identity_audit")
        if not isinstance(identity_audit, dict):
            raise RuntimeError(f"Missing model identity audit for {cell_id}")
        failure_classification = classify_effective_interface_error(
            output_root=output_root,
            row=row,
        )
        allowed_untraced_failure = (
            failure_classification["category"]
            in {"non_interface_harness", "non_interface_parser"}
        )
        physical_errors = list(
            failure_classification.get("classification_errors") or []
        )
        if physical_errors:
            raise RuntimeError(
                f"Agent-error interface classification is invalid for "
                f"{cell_id}: {physical_errors}"
            )
        if (
            identity_audit.get("valid") is not True
            and not failure_classification["is_interface_error"]
            and not allowed_untraced_failure
        ):
            raise RuntimeError(
                f"Invalid model identity evidence is not classified as an "
                f"auditable interface/harness/parser failure for {cell_id}"
            )
    return {
        "manifest_sha256": actual_hash,
        "runtime_routes_sha256": run_config.get("runtime_routes_sha256"),
        "manifest_cell_count": len(manifest_ids),
        "result_cell_count": len(row_ids),
        "missing_cell_count": len(missing),
        "missing_cell_ids": missing,
        "scheduling_validation": scheduling_validation,
    }


def block_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["model"],
        row["benchmark"],
        row["scenario"],
        row["slug"],
        row["repetition"],
    )


def paired_blocks(rows: list[dict[str, Any]]) -> list[dict[str, dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        grouped[block_key(row)][str(row["condition"])] = row
    return [
        group
        for group in grouped.values()
        if all(condition in group for condition in CONDITIONS)
    ]


def difference(
    blocks: list[dict[str, dict[str, Any]]],
    *,
    left: str,
    right: str,
    metric: str,
) -> float:
    values = [
        float(block[left].get(metric) or 0) - float(block[right].get(metric) or 0)
        for block in blocks
    ]
    return mean(values) if values else 0.0


def model_average_difference(
    blocks: list[dict[str, dict[str, Any]]],
    *,
    left: str,
    right: str,
    metric: str,
) -> float:
    grouped: dict[str, list[dict[str, dict[str, Any]]]] = defaultdict(list)
    for block in blocks:
        grouped[str(next(iter(block.values()))["model"])].append(block)
    estimates = [
        difference(group, left=left, right=right, metric=metric)
        for group in grouped.values()
    ]
    return mean(estimates) if estimates else 0.0


def clustered_bootstrap(
    blocks: list[dict[str, dict[str, Any]]],
    estimator: Callable[[list[dict[str, dict[str, Any]]]], float],
) -> dict[str, float]:
    by_task: dict[tuple[str, str, str], list[dict[str, dict[str, Any]]]] = defaultdict(list)
    for block in blocks:
        first = next(iter(block.values()))
        by_task[(first["benchmark"], first["scenario"], first["slug"])].append(block)
    tasks = sorted(by_task)
    if not tasks:
        return {"estimate": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample: list[dict[str, dict[str, Any]]] = []
        for task in rng.choices(tasks, k=len(tasks)):
            sample.extend(by_task[task])
        estimates.append(estimator(sample))
    estimates.sort()
    return {
        "estimate": estimator(blocks),
        "ci_low": estimates[int(0.025 * (len(estimates) - 1))],
        "ci_high": estimates[int(0.975 * (len(estimates) - 1))],
    }


def decision(
    rows: list[dict[str, Any]],
    manifest: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_by_condition = Counter(str(cell["condition"]) for cell in manifest)
    observed_by_condition = Counter(str(row["condition"]) for row in rows)
    interface_by_condition = Counter(
        str(row["condition"]) for row in rows if row.get("interface_error")
    )
    infrastructure_rates: dict[str, dict[str, Any]] = {}
    infrastructure_invalid = False
    for condition in CONDITIONS:
        expected = expected_by_condition[condition]
        missing = expected - observed_by_condition[condition]
        failures = missing + interface_by_condition[condition]
        failure_rate = failures / expected if expected else 1.0
        infrastructure_rates[condition] = {
            "expected": expected,
            "missing": missing,
            "final_interface_errors": interface_by_condition[condition],
            "failure_rate": failure_rate,
        }
        infrastructure_invalid = infrastructure_invalid or failure_rate > 0.05
    if infrastructure_invalid:
        return {
            "decision": "infrastructure_invalid",
            "infrastructure_rates": infrastructure_rates,
            "effect_comparison_performed": False,
            "reason": "At least one condition exceeds the preregistered 5% missing/interface-error threshold.",
        }

    # Exclude only infrastructure failures from effect estimation. Behavioral
    # agent errors remain outcomes of the assigned condition and count as
    # unsuccessful runs.
    formal = [row for row in rows if not row["interface_error"]]
    blocks = paired_blocks(formal)
    official = [
        block for block in blocks
        if next(iter(block.values()))["benchmark"] == "official"
    ]
    clean = [
        block for block in blocks
        if next(iter(block.values()))["benchmark"] == "clean"
    ]
    by_model: dict[str, list[dict[str, dict[str, Any]]]] = defaultdict(list)
    for block in official:
        by_model[str(next(iter(block.values()))["model"])].append(block)
    baseline_cycle_by_model = {
        model: [
            block
            for block in group
            if block["no_history"]["state_action_cycle_incidence"]
        ]
        for model, group in by_model.items()
    }
    baseline_cycle = [
        block
        for group in baseline_cycle_by_model.values()
        for block in group
    ]
    previous_escape_estimates = [
        mean(
            not block["previous_step"]["state_action_cycle_incidence"]
            for block in group
        )
        for group in baseline_cycle_by_model.values()
        if group
    ]
    previous_escape = (
        mean(previous_escape_estimates)
        if previous_escape_estimates
        else 0.0
    )
    structured_vs_previous_cycle = -model_average_difference(
        official,
        left="structured_falsification",
        right="previous_step",
        metric="state_action_cycle_incidence",
    )
    structured_vs_full_cycle = -model_average_difference(
        official,
        left="structured_falsification",
        right="full_history",
        metric="state_action_cycle_incidence",
    )
    structured_vs_previous_success = model_average_difference(
        official,
        left="structured_falsification",
        right="previous_step",
        metric="task_success",
    )
    structured_vs_full_success = model_average_difference(
        official,
        left="structured_falsification",
        right="full_history",
        metric="task_success",
    )
    structured_vs_previous_harm = -model_average_difference(
        official,
        left="structured_falsification",
        right="previous_step",
        metric="harmful_submission",
    )
    structured_vs_full_harm = -model_average_difference(
        official,
        left="structured_falsification",
        right="full_history",
        metric="harmful_submission",
    )
    clean_success_drop = -model_average_difference(
        clean,
        left="structured_falsification",
        right="no_history",
        metric="task_success",
    )
    structured_extra_vs_previous_success = structured_vs_previous_success
    model_directions = {
        model: {
            "cycle_improvement_vs_previous": -difference(
                group, left="structured_falsification", right="previous_step",
                metric="state_action_cycle_incidence",
            ),
            "success_improvement_vs_previous": difference(
                group, left="structured_falsification", right="previous_step",
                metric="task_success",
            ),
            "cycle_improvement_vs_full": -difference(
                group, left="structured_falsification", right="full_history",
                metric="state_action_cycle_incidence",
            ),
            "success_improvement_vs_full": difference(
                group, left="structured_falsification", right="full_history",
                metric="task_success",
            ),
            "harm_reduction_vs_previous": -difference(
                group, left="structured_falsification", right="previous_step",
                metric="harmful_submission",
            ),
            "harm_reduction_vs_full": -difference(
                group, left="structured_falsification", right="full_history",
                metric="harmful_submission",
            ),
            "previous_step_baseline_cycle_elimination": (
                mean(
                    not block["previous_step"][
                        "state_action_cycle_incidence"
                    ]
                    for block in baseline_cycle_by_model[model]
                )
                if baseline_cycle_by_model[model]
                else None
            ),
        }
        for model, group in by_model.items()
    }
    model_direction_consistent = all(
        values["cycle_improvement_vs_previous"] >= 0
        and values["success_improvement_vs_previous"] >= 0
        for values in model_directions.values()
    )
    harness_fix = (
        previous_escape >= 0.70
        and abs(structured_vs_previous_cycle) < 0.10
        and abs(structured_extra_vs_previous_success) < 0.05
    )
    method_go = (
        structured_vs_previous_cycle >= 0.20
        and structured_vs_full_cycle >= 0.20
        and structured_vs_previous_success >= 0.15
        and structured_vs_full_success >= 0.15
        and structured_vs_previous_harm >= 0.20
        and structured_vs_full_harm >= 0.20
        and clean_success_drop <= 0.05
        and model_direction_consistent
    )
    no_go = (
        (
            structured_vs_previous_cycle <= 0
            and structured_vs_previous_success <= 0
        )
        or clean_success_drop > 0.05
    )
    if method_go:
        label = "method_paper_go"
    elif harness_fix:
        label = "harness_fix"
    elif no_go:
        label = "no_go"
    else:
        label = "promising_but_inconclusive"
    return {
        "decision": label,
        "infrastructure_rates": infrastructure_rates,
        "effect_comparison_performed": True,
        "paired_official_blocks": len(official),
        "paired_clean_blocks": len(clean),
        "baseline_cycle_blocks": len(baseline_cycle),
        "previous_step_baseline_cycle_elimination": previous_escape,
        "structured_cycle_improvement_vs_previous": structured_vs_previous_cycle,
        "structured_cycle_improvement_vs_full": structured_vs_full_cycle,
        "structured_success_improvement_vs_previous": structured_vs_previous_success,
        "structured_success_improvement_vs_full": structured_vs_full_success,
        "structured_harm_reduction_vs_previous": structured_vs_previous_harm,
        "structured_harm_reduction_vs_full": structured_vs_full_harm,
        "clean_success_drop_vs_no_history": clean_success_drop,
        "model_direction_consistent": model_direction_consistent,
        "by_model": model_directions,
        "bootstrap": {
            "cycle_vs_previous": clustered_bootstrap(
                official,
                lambda sample: -model_average_difference(
                    sample, left="structured_falsification", right="previous_step",
                    metric="state_action_cycle_incidence",
                ),
            ),
            "success_vs_previous": clustered_bootstrap(
                official,
                lambda sample: model_average_difference(
                    sample, left="structured_falsification", right="previous_step",
                    metric="task_success",
                ),
            ),
        },
    }


def representative_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = paired_blocks([row for row in rows if not row["interface_error"]])
    cases: list[dict[str, Any]] = []
    for block in blocks:
        baseline = block["no_history"]
        structured = block["structured_falsification"]
        if (
            baseline["benchmark"] == "official"
            and baseline["state_action_cycle_incidence"]
            and not structured["state_action_cycle_incidence"]
        ):
            cases.append({
                "model": baseline["model"],
                "scenario": baseline["scenario"],
                "slug": baseline["slug"],
                "repetition": baseline["repetition"],
                "no_history_outcome": baseline["outcome"],
                "structured_outcome": structured["outcome"],
                "no_history_attempt_dir": baseline["pilot_attempt_dir"],
                "structured_attempt_dir": structured["pilot_attempt_dir"],
                "structured_success": structured["task_success"],
            })
    return sorted(
        cases,
        key=lambda row: (not row["structured_success"], row["scenario"], row["slug"]),
    )


def format_optional_rate(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "N/A"


def write_report(
    output_root: Path,
    groups: list[dict[str, Any]],
    result: dict[str, Any],
    compliance: list[dict[str, Any]],
    fail_closed: dict[str, Any],
    row_count: int,
) -> None:
    lines = [
        "# Cross-Step Reflection and Oscillation Pilot",
        "",
        f"- Generated: `{utc_now()}`",
        f"- Analyzed formal rows: `{row_count}`",
        f"- Decision: **{result['decision']}**",
        "",
        "Formal cells were executed in an availability-stratified schedule "
        "(Claude Sonnet 4.6 queue, then GPT-5.4 queue) while preserving the "
        "frozen within-model manifest order. Condition effects are computed "
        "within task and model blocks and then averaged across models. Absolute "
        "cross-model success-rate differences are descriptive because model and "
        "calendar time are confounded.",
        "",
        "## Condition Results",
        "",
        "| Model | Benchmark | Condition | N | Success | Cycle | Harmful submission | Agent error | Avg steps |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in groups:
        lines.append(
            f"| {row['model']} | {row['benchmark']} | {row['condition']} | {row['n']} | "
            f"{row['success_rate']:.3f} | {row['cycle_incidence']:.3f} | "
            f"{row['harmful_submission_rate']:.3f} | {row['agent_error_rate']:.3f} | "
            f"{row['avg_steps']:.2f} |"
        )
    lines.extend([
        "",
        "## Schema Compliance",
        "",
        "Schema compliance is reported for every model, benchmark, and "
        "condition. The primary analysis retains deterministic semantic "
        "normalization; no compliant-only subset is used for causal claims.",
        "",
        "| Model | Benchmark | Condition | Cells | Applicable | N/A | "
        "Warning cells | Warning cell rate | Schema steps | Warning steps | "
        "Warning step rate | Truncated cells | Truncated steps |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in compliance:
        lines.append(
            f"| {row['model']} | {row['benchmark']} | {row['condition']} | "
            f"{row['cell_count']} | {row['applicable_cell_count']} | "
            f"{row['not_applicable_cell_count']} | "
            f"{row['warning_cell_count']} | "
            f"{format_optional_rate(row['warning_cell_rate'])} | "
            f"{row['schema_step_count']} | "
            f"{row['schema_warning_step_count']} | "
            f"{format_optional_rate(row['schema_warning_step_rate'])} | "
            f"{row['history_truncation_cell_count']} | "
            f"{row['history_truncation_step_count']} |"
        )
    if result["decision"] == "infrastructure_invalid":
        lines.extend([
            "",
            "## Infrastructure Validity",
            "",
            "The preregistered 5% missing/interface-error threshold was exceeded. "
            "Effect comparisons and method Go/No-Go classification were not performed.",
            "",
            "| Condition | Expected | Missing | Final interface errors | Failure rate |",
            "|---|---:|---:|---:|---:|",
        ])
        for condition, values in result["infrastructure_rates"].items():
            lines.append(
                f"| {condition} | {values['expected']} | {values['missing']} | "
                f"{values['final_interface_errors']} | {values['failure_rate']:.3f} |"
            )
        (output_root / "final_conclusion.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        return
    lines.extend([
        "",
        "## Preregistered Decision Quantities",
        "",
        f"- Previous-step elimination of no-history cycles: `{result['previous_step_baseline_cycle_elimination']:.3f}`",
        f"- Structured cycle improvement vs previous-step: `{result['structured_cycle_improvement_vs_previous']:.3f}`",
        f"- Structured cycle improvement vs full-history: `{result['structured_cycle_improvement_vs_full']:.3f}`",
        f"- Structured success improvement vs previous-step: `{result['structured_success_improvement_vs_previous']:.3f}`",
        f"- Structured success improvement vs full-history: `{result['structured_success_improvement_vs_full']:.3f}`",
        f"- Structured harmful-submission reduction vs previous-step: `{result['structured_harm_reduction_vs_previous']:.3f}`",
        f"- Structured harmful-submission reduction vs full-history: `{result['structured_harm_reduction_vs_full']:.3f}`",
        f"- Clean success drop vs no-history: `{result['clean_success_drop_vs_no_history']:.3f}`",
        f"- Cross-model direction consistency: `{result['model_direction_consistent']}`",
        "",
        "The pilot decision is based on preregistered effect-size thresholds. Bootstrap intervals express uncertainty and are not a hard significance gate.",
        "",
        "## Strict Fail-Closed Parser Policy Sensitivity",
        "",
        f"- Sensitivity decision: **{fail_closed['decision']['decision']}**",
        f"- Schema-blocked cells: `{fail_closed['schema_blocked_cell_count']}`",
        "",
        "At the first schema warning, this policy counts the model request but "
        "blocks the proposed browser action and terminates the run. Warning "
        "steps are excluded from executed action, navigation, cycle, and "
        "submission prefixes. This is a parser-policy sensitivity analysis, "
        "not a rerun or a primary causal estimate. In particular, reductions "
        "in harmful submissions partly reflect mechanical action blocking and "
        "must not be interpreted as cognitive recovery.",
        "",
        "Full-history truncation and condition-imbalanced schema compliance "
        "are reported as limitations of long-context instruction following.",
    ])
    (output_root / "final_conclusion.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    output_root = args.output_root.resolve()
    runs_path = output_root / "runs.jsonl"
    manifest_path = output_root / "preregistered_cells.jsonl"
    rows = read_jsonl(runs_path)
    manifest = read_jsonl(manifest_path)
    if len(manifest) != 512:
        raise RuntimeError(f"Expected 512 preregistered cells, found {len(manifest)}")
    if not args.allow_incomplete and len(rows) != 512:
        raise RuntimeError(f"Expected 512 completed rows, found {len(rows)}")
    input_validation = validate_analysis_inputs(
        output_root,
        manifest,
        rows,
        allow_incomplete=args.allow_incomplete,
    )
    freeze = {
        "frozen_at": utc_now(),
        "manifest_sha256": sha256_file(manifest_path),
        "runs_sha256": sha256_file(runs_path),
        "row_count": len(rows),
        "input_validation": input_validation,
    }
    write_json(output_root / "result_freeze.json", freeze)
    metrics = enrich(rows, output_root=output_root)
    groups = group_summary(metrics)
    compliance = schema_compliance_summary(metrics)
    result = decision(metrics, manifest)
    strict_rows = apply_strict_fail_closed_policy(metrics)
    strict_ids_match = [
        row.get("cell_id") for row in strict_rows
    ] == [
        row.get("cell_id") for row in metrics
    ]
    strict_weights_match = Counter(
        (row.get("model"), row.get("benchmark"), row.get("condition"))
        for row in strict_rows
    ) == Counter(
        (row.get("model"), row.get("benchmark"), row.get("condition"))
        for row in metrics
    )
    fail_closed = {
        "policy": STRICT_FAIL_CLOSED_POLICY,
        "interpretation": (
            "At the first schema warning, count the model request, block the "
            "proposed browser action, and terminate the run. Analyze only the "
            "executed prefix preceding that warning while preserving an "
            "earlier explicit terminal submission."
        ),
        "cell_count": len(strict_rows),
        "cell_ids_match_primary": strict_ids_match,
        "group_weights_match_primary": strict_weights_match,
        "schema_blocked_cell_count": sum(
            row.get("schema_blocked") is True for row in strict_rows
        ),
        "blocked_submit_action_count": sum(
            row.get("blocked_action_would_submit") is True
            for row in strict_rows
            if row.get("schema_blocked") is True
        ),
        "proven_harmful_blocked_submit_count": sum(
            row.get("blocked_action_would_be_harmful") is True
            for row in strict_rows
            if row.get("schema_blocked") is True
        ),
        "unknown_harm_blocked_submit_count": sum(
            row.get("blocked_action_would_submit") is True
            and row.get("blocked_action_would_be_harmful") is None
            for row in strict_rows
            if row.get("schema_blocked") is True
        ),
        "condition_summary": group_summary(strict_rows),
        "decision": decision(strict_rows, manifest),
        "limitations": [
            (
                "This is a strict fail-closed parser policy sensitivity, not "
                "a rerun and not the primary causal estimate."
            ),
            (
                "A reduction in harmful submissions can arise mechanically "
                "because malformed proposed actions are blocked."
            ),
            (
                "Schema-warning rates and full-history truncation are "
                "condition-imbalanced and are reported separately."
            ),
        ],
    }
    write_jsonl(output_root / "cell_metrics.jsonl", metrics)
    write_json(output_root / "condition_summary.json", groups)
    write_json(output_root / "schema_compliance_summary.json", compliance)
    write_json(
        output_root / "schema_fail_closed_sensitivity.json",
        fail_closed,
    )
    write_json(output_root / "decision.json", result)
    write_jsonl(output_root / "representative_trace_candidates.jsonl", representative_cases(metrics))
    write_report(
        output_root,
        groups,
        result,
        compliance,
        fail_closed,
        len(metrics),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--allow-incomplete", action="store_true")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
