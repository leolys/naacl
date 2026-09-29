#!/usr/bin/env python3
"""Infrastructure-only audit for preregistered reflection-pilot gates."""

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

from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    CONCURRENCY_INCIDENT_FILENAME,
    DEFAULT_OUTPUT_ROOT,
    MODEL_CONFIGS,
    RUNNER_LOCK_FILENAME,
    build_manifest,
    classify_effective_interface_error,
    classify_stop_rule_interface_error,
    read_jsonl,
    review_provenance_spec,
    runtime_routes,
    scheduling_deviation_spec,
    sha256_file,
    write_json,
)
from web_agent_benchmark.evaluation.reflection_history import MEMORY_FIELDS


EXPECTED_BY_GATE = {2: 64, 3: 256, 4: 512}
FROZEN_MANIFEST_SHA256 = (
    "cec5ff50737d2f39dd2cf63ff0eb598b2fd07b0c56526c7a78bcf4be20e6f490"
)
FROZEN_SCHEDULING_SHA256 = (
    "fa7325dcf6d3e276f615ef1cdacd1f94160c29d293a744ced2d9cab6c720520e"
)
FROZEN_RUNTIME_ROUTES_SHA256 = (
    "861be3495cdca215ce7b0e3e9ae8340be026aa326569564a3d0e2f4a08bc10e8"
)
SECRET_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(rb"AIME_LITELLM_API_KEY\s*=\s*\S+", re.IGNORECASE),
    re.compile(rb"[\"']api[_-]?key[\"']?\s*[:=]\s*[\"'][^\"']{8,}", re.IGNORECASE),
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_IDENTITY_EVENT_RESULTS = {
    "success",
    "exception",
    "http_error",
    "non_json_response",
}
ALLOWED_BROWSER_ACTIONS = {
    "finish",
    "click_link",
    "click_button",
    "submit_form",
    "select_option",
}


def is_sha256(value: Any) -> bool:
    return bool(SHA256_PATTERN.fullmatch(str(value or "")))


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def canonical_action(value: dict[str, Any]) -> dict[str, str]:
    return {
        "action": str(value.get("action") or "").strip(),
        "text": str(value.get("text") or "").strip(),
        "select_name": str(value.get("select_name") or "").strip(),
        "option_text": str(
            value.get("option_text") or value.get("value") or ""
        ).strip(),
    }


def valid_frozen_action(action: dict[str, Any]) -> bool:
    normalized = canonical_action(action)
    kind = normalized["action"]
    if kind not in ALLOWED_BROWSER_ACTIONS:
        return False
    if kind in {"click_link", "click_button"}:
        return bool(normalized["text"])
    if kind == "select_option":
        return bool(normalized["select_name"] and normalized["option_text"])
    return True


def raw_action_semantics_match(action: dict[str, Any]) -> bool:
    parsed = extract_first_json_object(str(action.get("_raw") or ""))
    if parsed is None:
        return False
    if isinstance(parsed.get("action"), dict):
        raw_action = parsed["action"]
    else:
        raw_action = {
            key: value
            for key, value in parsed.items()
            if key != "memory_update"
        }
    return canonical_action(raw_action) == canonical_action(action)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_identity_events(
    events: list[dict[str, Any]],
    *,
    expected_deployment: str,
) -> list[str]:
    errors: list[str] = []
    for expected_index, event in enumerate(events, 1):
        if event.get("event_type") != "http_request":
            errors.append(f"event {expected_index}: invalid event_type")
        if event.get("request_index") != expected_index:
            errors.append(
                f"event {expected_index}: request_index is not contiguous"
            )
        if event.get("result") not in ALLOWED_IDENTITY_EVENT_RESULTS:
            errors.append(f"event {expected_index}: invalid result")
        if event.get("requested_deployment") != expected_deployment:
            errors.append(f"event {expected_index}: deployment differs")
        if not is_sha256(event.get("request_payload_sha256")):
            errors.append(f"event {expected_index}: payload hash missing")
        if event.get("hidden_prompt_terms_seen") != []:
            errors.append(f"event {expected_index}: internal metadata in request")
        if event.get("result") == "success":
            if event.get("response_model") != expected_deployment:
                errors.append(f"event {expected_index}: response model differs")
            if event.get("identity_validated") is not True:
                errors.append(f"event {expected_index}: identity not validated")
    return errors


def interface_error_threshold(
    rows: list[dict[str, Any]],
    manifest: list[dict[str, Any]],
    *,
    root: Path | None = None,
) -> tuple[dict[str, int], dict[str, int], list[str]]:
    final_cells = Counter(str(cell["condition"]) for cell in manifest)
    allowed = {
        condition: int(count * 0.05)
        for condition, count in final_cells.items()
    }
    observed = Counter(
        str((row.get("pilot_cell") or {}).get("condition") or "")
        for row in rows
        if (
            classify_effective_interface_error(
                output_root=root,
                row=row,
            )["is_interface_error"]
            if root is not None
            else classify_stop_rule_interface_error(row)[
                "is_interface_error"
            ]
        )
    )
    errors = [
        (
            f"{condition}: interface errors {observed[condition]} exceed "
            f"the preregistered final 5% ceiling ({allowed[condition]}/"
            f"{final_cells[condition]})"
        )
        for condition in sorted(final_cells)
        if observed[condition] > allowed[condition]
    ]
    return dict(observed), allowed, errors


def auditable_actions(row: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    result: list[tuple[int, dict[str, Any]]] = []
    for index, step in enumerate(row.get("trace") or []):
        action = step.get("action") if isinstance(step, dict) else None
        if isinstance(action, dict) and "_raw" in action:
            result.append((index, action))
    return result


def audit_history_step(
    *,
    cell: dict[str, Any],
    step_index: int,
    step: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    history = step.get("pilot_history")
    if not isinstance(history, dict):
        return [f"step {step_index}: missing pilot_history"]
    if history.get("condition") != cell["condition"]:
        errors.append(f"step {step_index}: condition metadata differs")
    memory = history.get("memory_update")
    if not isinstance(memory, dict) or set(memory) != set(MEMORY_FIELDS):
        errors.append(f"step {step_index}: normalized memory schema invalid")
    available = int(history.get("history_records_available") or 0)
    injected = int(history.get("history_records_injected") or 0)
    truncated = history.get("history_truncated") is True
    condition = cell["condition"]
    if condition == "no_history" and injected != 0:
        errors.append(f"step {step_index}: no_history injected {injected}")
    elif condition == "previous_step":
        wanted = 0 if available == 0 else 1
        if injected != wanted:
            errors.append(
                f"step {step_index}: previous_step injected {injected}, expected {wanted}"
            )
    elif condition == "full_history":
        if injected > available:
            errors.append(f"step {step_index}: full_history exceeds available records")
        if not truncated and injected != available:
            errors.append(
                f"step {step_index}: untruncated full_history omitted records"
            )
    elif condition == "structured_falsification":
        wanted = 0 if available == 0 else 1
        if injected != wanted:
            errors.append(
                f"step {step_index}: structured ledger injected {injected}, "
                f"expected {wanted}"
            )
    if int(history.get("history_tokens_estimated") or 0) > int(
        cell["history_token_limit"]
    ):
        errors.append(f"step {step_index}: history token limit exceeded")
    for key in ("history_payload_sha256", "state_hash", "action_signature"):
        value = str(history.get(key) or "")
        minimum = 1 if key == "action_signature" else 64
        if (
            key == "action_signature"
            and len(value) < minimum
        ) or (
            key != "action_signature"
            and not is_sha256(value)
        ):
            errors.append(f"step {step_index}: missing {key}")
    return errors


def audit_cell(
    *,
    root: Path,
    cell: dict[str, Any],
    row: dict[str, Any],
) -> list[str]:
    cell_id = str(cell["cell_id"])
    errors: list[str] = []
    if row.get("pilot_cell") != cell:
        errors.append("pilot_cell differs from frozen manifest")
    expected_deployment = str(MODEL_CONFIGS[cell["model"]]["deployment_id"])
    identity = row.get("pilot_identity_audit") or {}
    failure_classification = classify_effective_interface_error(
        output_root=root,
        row=row,
    )
    interface_error = bool(
        failure_classification["is_interface_error"]
    )
    untraced_non_interface_failure = (
        failure_classification["category"]
        in {"non_interface_harness", "non_interface_parser"}
    )
    errors.extend(
        "interface classification: " + message
        for message in (
            failure_classification.get("classification_errors") or []
        )
    )
    if identity.get("expected_deployment") != expected_deployment:
        errors.append("identity audit deployment differs")
    if (
        identity.get("valid") is not True
        and not interface_error
        and not untraced_non_interface_failure
    ):
        errors.append("invalid model identity on non-interface result")

    actions = auditable_actions(row)
    for step_index, action in actions:
        if not valid_frozen_action(action):
            errors.append(f"step {step_index}: frozen action schema invalid")
        if not raw_action_semantics_match(action):
            errors.append(
                f"step {step_index}: normalized action differs from raw output"
            )
        metadata = action.get("_response_metadata") or {}
        if metadata.get("requested_deployment") != expected_deployment:
            errors.append(f"step {step_index}: requested deployment differs")
        if metadata.get("response_model") != expected_deployment:
            errors.append(f"step {step_index}: response model differs")
        if metadata.get("identity_validated") is not True:
            errors.append(f"step {step_index}: model identity not validated")
        if not is_sha256(metadata.get("request_payload_sha256")):
            errors.append(f"step {step_index}: request payload hash missing")
        if metadata.get("hidden_prompt_terms_seen") != []:
            errors.append(
                f"step {step_index}: internal metadata in full request payload"
            )

    trace = row.get("trace") or []
    failed_generation_steps = 0
    for step_index, step in enumerate(trace):
        if not isinstance(step, dict):
            errors.append(f"step {step_index}: malformed trace step")
            continue
        step_action = step.get("action") or {}
        failed_generation = (
            step_action.get("action") == "agent_error"
            and "_raw" not in step_action
            and row.get("error_attribution") == "llm_action_generation_error"
        )
        failed_generation_steps += int(failed_generation)
        if not failed_generation:
            errors.extend(
                audit_history_step(cell=cell, step_index=step_index, step=step)
            )
        sanitization = step.get("pilot_ui_sanitization") or {}
        if (
            sanitization.get("applied_before_screenshot_and_state_capture")
            is not True
        ):
            errors.append(f"step {step_index}: UI sanitization timing invalid")
        if step.get("pilot_hidden_terms_seen") != []:
            errors.append(
                f"step {step_index}: internal metadata in full DOM text"
            )
        screenshot = Path(str(step.get("screenshot") or ""))
        if not screenshot.is_file():
            errors.append(f"step {step_index}: screenshot missing")

    attempt_dir = root / str(row.get("pilot_attempt_dir") or "")
    expected_attempt_prefix = root / "cells" / cell_id
    try:
        belongs_to_cell = attempt_dir.resolve().is_relative_to(
            expected_attempt_prefix.resolve()
        )
    except OSError:
        belongs_to_cell = False
    if not belongs_to_cell:
        errors.append("pilot_attempt_dir does not belong to the result cell")
    events = read_jsonl(attempt_dir / "model_identity_events.jsonl")
    actual_requests = int(row.get("pilot_actual_http_request_count") or 0)
    if len(events) != actual_requests:
        errors.append("identity events differ from actual HTTP request count")
    expected_model_calls = len(actions) + failed_generation_steps
    if (
        actual_requests != expected_model_calls
        and not untraced_non_interface_failure
    ):
        errors.append(
            "HTTP request count differs from parsed plus failed model calls"
        )
    errors.extend(
        f"HTTP {message}"
        for message in audit_identity_events(
            events,
            expected_deployment=expected_deployment,
        )
    )
    if actual_requests > int(cell["max_steps"]):
        errors.append(
            f"attempt made {actual_requests} HTTP requests, exceeding max_steps"
        )
    return errors


def secret_scan(root: Path) -> tuple[list[str], list[str]]:
    hits: list[str] = []
    unreadable: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError as exc:
            unreadable.append(
                f"{path.relative_to(root)}: {type(exc).__name__}: {exc}"
            )
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            hits.append(str(path.relative_to(root)))
    return hits, unreadable


def audit(
    root: Path,
    gate: int,
    *,
    expected_completed_override: int | None = None,
) -> dict[str, Any]:
    expected_completed = (
        int(expected_completed_override)
        if expected_completed_override is not None
        else EXPECTED_BY_GATE[gate]
    )
    manifest_path = root / "preregistered_cells.jsonl"
    manifest = read_jsonl(manifest_path)
    expected_manifest = build_manifest()
    rows = read_jsonl(root / "runs.jsonl")
    errors: list[str] = []
    actual_manifest_sha = (
        sha256_file(manifest_path) if manifest_path.exists() else ""
    )
    if manifest != expected_manifest:
        errors.append("formal manifest differs from regenerated preregistration")
    if len(manifest) != 512:
        errors.append(f"formal manifest has {len(manifest)} cells, expected 512")
    if actual_manifest_sha != FROZEN_MANIFEST_SHA256:
        errors.append("formal manifest differs from preregistered constant")
    if len(rows) != expected_completed:
        errors.append(
            f"completed result count is {len(rows)}, expected {expected_completed}"
        )
    preregistration_path = root / "preregistration.json"
    route_path = root / "runtime_routes.json"
    config_path = root / "pilot_run_config.json"
    scheduling_path = root / "scheduling_deviation.json"
    scheduling_digest_path = root / "scheduling_deviation.sha256"
    provenance_path = root / "review_provenance.json"
    runner_lock_path = root / RUNNER_LOCK_FILENAME
    incident_path = root / CONCURRENCY_INCIDENT_FILENAME
    if incident_path.exists():
        try:
            incident = load_json(incident_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(
                f"concurrency incident marker is unreadable: "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            if incident.get("excluded_from_analysis") is True:
                errors.append("formal root is quarantined by concurrency incident")
    required_freeze_files = (
        preregistration_path,
        route_path,
        config_path,
        scheduling_path,
        scheduling_digest_path,
        provenance_path,
        runner_lock_path,
    )
    if any(not path.is_file() for path in required_freeze_files):
        errors.append("one or more experiment freeze files are missing")
        config: dict[str, Any] = {}
        scheduling: dict[str, Any] = {}
    else:
        preregistration = load_json(preregistration_path)
        config = load_json(config_path)
        scheduling = load_json(scheduling_path)
        if load_json(provenance_path) != review_provenance_spec():
            errors.append("review provenance differs from frozen recovery record")
        runner_lock = load_json(runner_lock_path)
        if (
            not isinstance(runner_lock.get("pid"), int)
            or runner_lock["pid"] <= 0
            or not str(runner_lock.get("acquired_at") or "")
            or Path(str(runner_lock.get("output_root") or "")).resolve()
            != root.resolve()
        ):
            errors.append("runner lock metadata is invalid")
        if preregistration.get("manifest_sha256") != actual_manifest_sha:
            errors.append("preregistration manifest hash differs")
        if config.get("manifest_sha256") != actual_manifest_sha:
            errors.append("pilot config manifest hash differs")
        if load_json(route_path) != runtime_routes():
            errors.append("runtime route content drifted")
        route_sha = sha256_file(route_path)
        if route_sha != FROZEN_RUNTIME_ROUTES_SHA256:
            errors.append("runtime route differs from frozen constant")
        if route_sha != config.get("runtime_routes_sha256"):
            errors.append("runtime route hash differs from pilot config")
        expected_scheduling = scheduling_deviation_spec(
            manifest,
            manifest_sha256=actual_manifest_sha,
        )
        for key, value in expected_scheduling.items():
            if scheduling.get(key) != value:
                errors.append(f"scheduling deviation differs at {key!r}")
        scheduling_sha = sha256_file(scheduling_path)
        if scheduling_sha != FROZEN_SCHEDULING_SHA256:
            errors.append("scheduling deviation differs from frozen constant")
        if config.get("scheduling_deviation_sha256") != scheduling_sha:
            errors.append("scheduling hash differs from pilot config")
        expected_digest = f"{scheduling_sha}  {scheduling_path.name}\n"
        if scheduling_digest_path.read_text(encoding="utf-8") != expected_digest:
            errors.append("scheduling SHA-256 sidecar differs")

    manifest_by_id = {str(cell["cell_id"]): cell for cell in manifest}
    row_ids = [
        str((row.get("pilot_cell") or {}).get("cell_id") or "")
        for row in rows
    ]
    duplicate_ids = sorted(
        key for key, count in Counter(row_ids).items() if count > 1
    )
    if duplicate_ids:
        errors.append(f"duplicate result cells: {duplicate_ids}")
    unknown_ids = sorted(set(row_ids) - set(manifest_by_id))
    if unknown_ids:
        errors.append(f"unknown result cells: {unknown_ids}")
    scheduled_ids = [
        str(cell_id)
        for queue in scheduling.get("queues") or []
        for cell_id in queue.get("cell_ids") or []
    ]
    expected_prefix = scheduled_ids[:expected_completed]
    if len(scheduled_ids) != 512 or len(set(scheduled_ids)) != 512:
        errors.append("scheduling deviation does not cover 512 unique cells")
    if set(row_ids) != set(expected_prefix):
        errors.append("completed results are not the frozen schedule prefix")
    chosen_paths = sorted(root.glob("cells/*/chosen_result.json"))
    chosen_ids = [path.parent.name for path in chosen_paths]
    if (
        len(chosen_ids) != expected_completed
        or set(chosen_ids) != set(expected_prefix)
    ):
        errors.append(
            "chosen_result files do not exactly match the frozen schedule prefix"
        )

    cell_errors: dict[str, list[str]] = {}
    for row in rows:
        cell_id = str((row.get("pilot_cell") or {}).get("cell_id") or "")
        if cell_id not in manifest_by_id:
            continue
        chosen_path = root / "cells" / cell_id / "chosen_result.json"
        if not chosen_path.is_file():
            errors.append(f"{cell_id}: chosen_result.json is missing")
        elif load_json(chosen_path) != row:
            errors.append(f"{cell_id}: aggregate row differs from chosen result")
        found = audit_cell(
            root=root,
            cell=manifest_by_id[cell_id],
            row=row,
        )
        if found:
            cell_errors[cell_id] = found
            errors.extend(f"{cell_id}: {message}" for message in found)

    attempts = read_jsonl(root / "attempt_manifest.jsonl")
    attempt_dirs = sorted(root.glob("cells/*/attempt_*"))
    status_paths = sorted(root.glob("cells/*/attempt_*/attempt_status.json"))
    result_paths = sorted(root.glob("cells/*/attempt_*/result.json"))
    unexpected_attempt_cells = sorted({
        path.parent.name
        for path in attempt_dirs
        if path.parent.name not in set(expected_prefix)
    })
    unexpected_status_cells = sorted({
        path.parents[1].name
        for path in status_paths
        if path.parents[1].name not in set(expected_prefix)
    })
    unexpected_result_cells = sorted({
        path.parents[1].name
        for path in result_paths
        if path.parents[1].name not in set(expected_prefix)
    })
    if unexpected_attempt_cells:
        errors.append(
            "formal attempt directories exist outside the schedule prefix: "
            f"{unexpected_attempt_cells}"
        )
    if unexpected_status_cells:
        errors.append(
            "attempt status files exist outside the schedule prefix: "
            f"{unexpected_status_cells}"
        )
    if unexpected_result_cells:
        errors.append(
            "attempt result files exist outside the schedule prefix: "
            f"{unexpected_result_cells}"
        )
    missing_status = [
        str(path.relative_to(root))
        for path in attempt_dirs
        if path.is_dir() and not (path / "attempt_status.json").is_file()
    ]
    if missing_status:
        errors.append(f"attempt directories lack status: {missing_status}")
    status_records = [(path, load_json(path)) for path in status_paths]
    statuses = [status for _, status in status_records]
    attempt_manifest_by_dir = {
        str(status.get("attempt_dir") or ""): status for status in attempts
    }
    status_files_by_dir = {
        str(status.get("attempt_dir") or ""): status for status in statuses
    }
    if (
        len(attempt_manifest_by_dir) != len(attempts)
        or len(status_files_by_dir) != len(statuses)
        or attempt_manifest_by_dir != status_files_by_dir
    ):
        errors.append("attempt_manifest does not exactly match attempt status files")
    consumed_by_cell: dict[str, list[int]] = {}
    seen_attempt_dirs: set[str] = set()
    for status_path, status in status_records:
        cell_id = str(status.get("cell_id") or "")
        cell = manifest_by_id.get(cell_id)
        attempt = int(status.get("attempt") or 0)
        relative_dir = str(status.get("attempt_dir") or "")
        if status_path.parent.resolve() != (root / relative_dir).resolve():
            errors.append(
                f"{cell_id}: attempt status is not physically stored in "
                f"its declared attempt_dir"
            )
        if cell is None:
            errors.append(f"attempt status references unknown cell {cell_id!r}")
            continue
        if relative_dir in seen_attempt_dirs:
            errors.append(f"duplicate attempt directory {relative_dir!r}")
        seen_attempt_dirs.add(relative_dir)
        expected_prefix_path = f"cells/{cell_id}/attempt_"
        if not relative_dir.startswith(expected_prefix_path):
            errors.append(f"{cell_id}: attempt directory belongs to another cell")
        if attempt not in {1, 2, 3}:
            errors.append(f"{cell_id}: invalid consumed-attempt index {attempt}")
        consumed = status.get("formal_attempt_consumed") is True
        availability_aborted = status.get("availability_aborted") is True
        if consumed == availability_aborted:
            errors.append(
                f"{cell_id}: consumed/availability flags are not complementary"
            )
        if consumed:
            consumed_by_cell.setdefault(cell_id, []).append(attempt)
        request_count = int(status.get("actual_http_request_count") or 0)
        if request_count > int(cell["max_steps"]):
            errors.append(
                f"{cell_id}: attempt HTTP count exceeds max_steps"
            )
        attempt_path = root / relative_dir
        events = read_jsonl(attempt_path / "model_identity_events.jsonl")
        if len(events) != request_count:
            errors.append(f"{cell_id}: attempt event/request counts differ")
        deployment = str(MODEL_CONFIGS[cell["model"]]["deployment_id"])
        errors.extend(
            f"{cell_id}: {message}"
            for message in audit_identity_events(
                events,
                expected_deployment=deployment,
            )
        )
        attempt_result = attempt_path / "result.json"
        if attempt_result.is_file():
            attempt_row = load_json(attempt_result)
            for message in audit_cell(root=root, cell=cell, row=attempt_row):
                errors.append(f"{cell_id} attempt {attempt}: {message}")
    for cell_id, indices in consumed_by_cell.items():
        if len(indices) > 3 or len(indices) != len(set(indices)):
            errors.append(f"{cell_id}: invalid consumed retry count/duplicates")
        elif sorted(indices) != list(range(1, max(indices) + 1)):
            errors.append(f"{cell_id}: consumed attempts are not contiguous")
    for row in rows:
        cell_id = str((row.get("pilot_cell") or {}).get("cell_id") or "")
        relative_dir = str(row.get("pilot_attempt_dir") or "")
        chosen_status = status_files_by_dir.get(relative_dir)
        if chosen_status is None:
            errors.append(f"{cell_id}: chosen result has no matching attempt status")
            continue
        if chosen_status.get("formal_attempt_consumed") is not True:
            errors.append(f"{cell_id}: chosen result points to unconsumed attempt")
        if int(chosen_status.get("attempt") or 0) != int(
            row.get("pilot_attempt") or 0
        ):
            errors.append(f"{cell_id}: chosen attempt number differs from status")
        if chosen_status.get("cell_id") != cell_id:
            errors.append(f"{cell_id}: chosen status cell differs")
        if int(chosen_status.get("actual_http_request_count") or 0) != int(
            row.get("pilot_actual_http_request_count") or 0
        ):
            errors.append(f"{cell_id}: chosen HTTP count differs from status")
        if chosen_status.get("outcome") != row.get("outcome"):
            errors.append(f"{cell_id}: chosen outcome differs from status")
        attempt_result_path = root / relative_dir / "result.json"
        if not attempt_result_path.is_file():
            errors.append(f"{cell_id}: chosen attempt result.json is missing")
        else:
            attempt_result = load_json(attempt_result_path)
            chosen_without_schedule = dict(row)
            chosen_without_schedule.pop("pilot_scheduling", None)
            if attempt_result != chosen_without_schedule:
                errors.append(
                    f"{cell_id}: chosen result differs from consumed attempt result"
                )

    execution_events = read_jsonl(root / "scheduling_execution_log.jsonl")
    unknown_event_types = sorted({
        str(event.get("event_type") or "")
        for event in execution_events
        if event.get("event_type") not in {
            "cell_start",
            "cell_finish",
            "cell_abort",
        }
    })
    if unknown_event_types:
        errors.append(
            f"schedule contains unknown event types: {unknown_event_types}"
        )
    starts = [
        event for event in execution_events
        if event.get("event_type") == "cell_start"
    ]
    finishes = [
        event for event in execution_events
        if event.get("event_type") == "cell_finish"
    ]
    aborts = [
        event for event in execution_events
        if event.get("event_type") == "cell_abort"
    ]
    if len(finishes) != expected_completed:
        errors.append(
            "schedule finish count differs from completed result count"
        )
    if len(starts) != len(finishes) + len(aborts):
        errors.append(
            "schedule start count differs from finish-plus-abort count"
        )
    start_by_sequence = {
        int(event.get("execution_sequence") or 0): event for event in starts
    }
    terminal_events = [*finishes, *aborts]
    terminal_by_sequence = {
        int(event.get("execution_sequence") or 0): event
        for event in terminal_events
    }
    if (
        len(start_by_sequence) != len(starts)
        or len(terminal_by_sequence) != len(terminal_events)
    ):
        errors.append("schedule contains duplicate execution sequences")
    expected_execution_sequences = set(range(1, len(starts) + 1))
    if set(start_by_sequence) != expected_execution_sequences:
        errors.append("schedule start sequences are not contiguous from one")
    if set(terminal_by_sequence) != set(start_by_sequence):
        errors.append("every schedule start must have exactly one terminal event")
    row_by_id = {
        str((row.get("pilot_cell") or {}).get("cell_id") or ""): row
        for row in rows
    }
    scheduling_sha = (
        sha256_file(scheduling_path) if scheduling_path.is_file() else ""
    )
    completed_index = 0
    for sequence in sorted(start_by_sequence):
        start = start_by_sequence.get(sequence)
        terminal = terminal_by_sequence.get(sequence)
        if not start or not terminal:
            errors.append(f"schedule sequence {sequence} is incomplete")
            continue
        if completed_index >= len(expected_prefix):
            errors.append(
                f"schedule sequence {sequence} started beyond the checkpoint prefix"
            )
            continue
        expected_cell_id = expected_prefix[completed_index]
        if start.get("cell_id") != expected_cell_id:
            errors.append(f"schedule sequence {sequence} start cell differs")
        if terminal.get("cell_id") != start.get("cell_id"):
            errors.append(f"schedule sequence {sequence} terminal cell differs")
        expected_cell = manifest_by_id.get(expected_cell_id) or {}
        if start.get("scheduling_deviation_sha256") != scheduling_sha:
            errors.append(f"{expected_cell_id}: start scheduling hash differs")
        if start.get("original_condition_order") != expected_cell.get(
            "condition_order"
        ):
            errors.append(f"{expected_cell_id}: start condition order differs")
        if start.get("model_queue") != expected_cell.get("model"):
            errors.append(f"{expected_cell_id}: start model queue differs")
        if terminal.get("event_type") == "cell_abort":
            chosen_for_aborted_sequence = [
                cell_id
                for cell_id, row in row_by_id.items()
                if int(
                    ((row.get("pilot_scheduling") or {}).get(
                        "execution_sequence"
                    ))
                    or 0
                )
                == sequence
            ]
            if chosen_for_aborted_sequence:
                errors.append(
                    f"schedule sequence {sequence} abort became a chosen result"
                )
            continue

        row = row_by_id.get(expected_cell_id)
        scheduling_metadata = (row or {}).get("pilot_scheduling") or {}
        if scheduling_metadata.get("execution_sequence") != sequence:
            errors.append(f"{expected_cell_id}: row schedule sequence differs")
        if scheduling_metadata.get("scheduling_deviation_sha256") != scheduling_sha:
            errors.append(f"{expected_cell_id}: row scheduling hash differs")
        if scheduling_metadata.get("original_condition_order") != expected_cell.get(
            "condition_order"
        ):
            errors.append(f"{expected_cell_id}: original condition order differs")
        if terminal.get("outcome") != (row or {}).get("outcome"):
            errors.append(f"{expected_cell_id}: finish outcome differs")
        if terminal.get("chosen_attempt") != (row or {}).get("pilot_attempt"):
            errors.append(f"{expected_cell_id}: finish chosen attempt differs")
        completed_index += 1
    if completed_index != expected_completed:
        errors.append(
            f"schedule completed {completed_index} cells, expected "
            f"{expected_completed}"
        )

    credentials, unreadable_files = secret_scan(root)
    if credentials:
        errors.append(f"credential-like text found in: {credentials}")
    if unreadable_files:
        errors.append(f"unreadable files prevent secret audit: {unreadable_files}")

    interface_errors_by_condition, interface_error_ceiling, threshold_errors = (
        interface_error_threshold(rows, manifest, root=root)
    )
    errors.extend(threshold_errors)
    interface_errors = sum(interface_errors_by_condition.values())
    failure_classifications = Counter(
        str(
            classify_effective_interface_error(
                output_root=root,
                row=row,
            )["category"]
        )
        for row in rows
    )
    invalid_schema_by_model_condition: Counter[str] = Counter()
    for row in rows:
        cell = row.get("pilot_cell") or {}
        key = f"{cell.get('model', '')}|{cell.get('condition', '')}"
        for step in row.get("trace") or []:
            if not isinstance(step, dict):
                continue
            action = step.get("action")
            history = step.get("pilot_history")
            if (
                isinstance(action, dict)
                and "_raw" in action
                and isinstance(history, dict)
                and history.get("schema_valid") is not True
            ):
                invalid_schema_by_model_condition[key] += 1
    report = {
        "gate": (
            gate
            if expected_completed_override is None
            else f"recovery_prefix_{expected_completed}"
        ),
        "review_scope": "infrastructure_only",
        "effect_labels_unblinded": False,
        "approved_by_automated_audit": not errors,
        "expected_completed_cells": expected_completed,
        "completed_cells": len(rows),
        "manifest_cells": len(manifest),
        "manifest_sha256": actual_manifest_sha or None,
        "schedule_prefix_valid": set(row_ids) == set(expected_prefix),
        "interface_error_count": interface_errors,
        "interface_errors_by_condition": interface_errors_by_condition,
        "interface_error_ceiling_by_condition": interface_error_ceiling,
        "failure_classification_counts": dict(
            sorted(failure_classifications.items())
        ),
        "invalid_schema_step_count": sum(
            invalid_schema_by_model_condition.values()
        ),
        "invalid_schema_steps_by_model_condition": dict(
            sorted(invalid_schema_by_model_condition.items())
        ),
        "attempt_record_count": len(attempts),
        "cell_error_count": len(cell_errors),
        "credential_hits": credentials,
        "unreadable_files": unreadable_files,
        "errors": errors,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--gate", type=int, choices=EXPECTED_BY_GATE, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    report = audit(root, args.gate)
    output = root / f"gate{args.gate}_infrastructure_audit.json"
    write_json(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["approved_by_automated_audit"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
