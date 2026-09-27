"""Offline structural and isolation audit for a decision-evidence run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .core import (
    IsolationError,
    assert_online_payload,
    canonical_state,
    public_task_projection,
    state_digest,
    write_json,
)
from .runner import REPOSITORY_ROOT, STRATEGIES, file_sha256, find_task, task_spec_path
from .safe_shell import score_receipt
from .policies import _b3_output


def b3_metric_errors(policy: dict[str, Any], unit_dir: Path) -> list[str]:
    """Ordinary consistency checks for new counters; old runs remain readable."""
    metrics = policy.get("verification_metrics")
    if not metrics:
        return []
    records = policy.get("records") or []
    observations = [r for r in records if r.get("phase") == "active_observation"]
    replies = [r for r in records if r.get("phase") in {"plan", "followup"}]
    accepted = [r for r in records if r.get("phase") == "accepted_decision"]
    expected = {
        "invalid_outputs": sum(r.get("phase") == "invalid_output" for r in records),
        "observation_requests": sum(_b3_output(r.get("response", ""))[0] == "observe" for r in replies),
        "dispatched_observations": len(observations),
        "successful_crops": sum(bool(r.get("artifact") and r.get("result")) for r in observations),
        "tool_errors": sum("error" in r for r in observations),
        "rejected_observations": sum(r.get("phase") == "observation_rejected" for r in records),
        "accepted_decisions": len(accepted),
    }
    errors = []
    if metrics != expected:
        errors.append("B3 verification counters disagree with recorded events")
    if policy.get("active_observations") != expected["dispatched_observations"]:
        errors.append("B3 active observations must count actual tool dispatches")
    if len(replies) != policy.get("model_calls"):
        errors.append("B3 response-event count disagrees with model calls")
    if bool(accepted) != (policy.get("parse_status") == "valid"):
        errors.append("B3 accepted decision disagrees with parse status")
    if accepted and (len(accepted) != 1 or not replies
                     or _b3_output(replies[-1].get("response", ""))[0] != "decision"
                     or accepted[0].get("option_label") != policy.get("recommended_option")):
        errors.append("B3 accepted decision lacks matching final response/recommendation")
    for row in observations:
        if row.get("artifact") and not (unit_dir / row["artifact"]).is_file():
            errors.append("B3 claimed crop artifact is missing")
    return errors


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _scalars(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _scalars(child)
    elif isinstance(value, list):
        for child in value:
            yield from _scalars(child)
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped:
            yield stripped


def hidden_terms_for(mapping_rows: list[dict[str, Any]]) -> list[str]:
    """Return task-specific hidden strings that must not occur in online text artifacts."""

    hidden_fields = {
        "task_id",
        "case_id",
        "case_uid",
        "pair_group_id",
        "task_instance_id",
        "split",
        "misleader_type",
        "ground_truth",
        "intermediate_decision",
        "misleading_context",
        "expected_action_id",
        "misleading_action_ids",
        "fallback_scoring",
        "source_dataset",
        "release_id",
        "release_version",
        "review_role",
        "scoring_status",
        "task_readiness",
        "clean_benchmark_source",
        "chart_asset",
    }
    generic = {
        "correct",
        "misleading",
        "success",
        "none",
        "official",
        "clean",
        "environment",
        "formal_scored_task",
    }
    terms: set[str] = {"official140", "clean140"}
    seen: set[tuple[str, str]] = set()
    for mapping in mapping_rows:
        slug = str(mapping["task_slug"])
        condition = str(mapping["condition"])
        if (slug, condition) in seen:
            continue
        seen.add((slug, condition))
        raw = find_task(task_spec_path(condition, slug), slug)
        public_text = json.dumps(
            public_task_projection(raw, task_alias=str(mapping["task_alias"])),
            ensure_ascii=False,
        ).casefold()
        terms.add(slug)
        for key in hidden_fields:
            for term in _scalars(raw.get(key)):
                lowered = term.casefold()
                if len(lowered) >= 5 and lowered not in generic and lowered not in public_text:
                    terms.add(term)
        for action in raw.get("action_space") or []:
            for key in ("action_id", "role", "scoring_outcome"):
                for term in _scalars(action.get(key)):
                    lowered = term.casefold()
                    if len(lowered) >= 5 and lowered not in generic and lowered not in public_text:
                        terms.add(term)
    return sorted(terms, key=lambda value: (-len(value), value.casefold()))


def request_text_for_hidden_scan(
    request_path: Path, payload: dict[str, Any]
) -> tuple[str, str]:
    """Exclude only model history traceable to an earlier response in this unit."""

    raw_text = json.dumps(payload, ensure_ascii=False).casefold()
    if payload.get("phase") != "b4_decision":
        return raw_text, ""
    context = payload.get("public_context") or {}
    extraction = context.get("model_extraction")
    if not isinstance(extraction, str) or not extraction:
        return raw_text, ""
    response_dir = request_path.parent.parent / "responses"
    traced = False
    for response_path in response_dir.glob("*.json"):
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        response_text = response.get("text")
        if response.get("ok") is True and isinstance(response_text, str):
            if response_text[:12000] == extraction:
                traced = True
                break
    if not traced:
        return raw_text, ""
    sanitized = dict(payload)
    sanitized_context = dict(context)
    sanitized_context["model_extraction"] = ""
    sanitized["public_context"] = sanitized_context
    user_prompt = sanitized.get("user_prompt")
    if isinstance(user_prompt, str):
        sanitized["user_prompt"] = user_prompt.replace(extraction, "", 1)
    return json.dumps(sanitized, ensure_ascii=False).casefold(), extraction


def replay_artifact_required(
    *, prefix_reached: bool, status: str, result: dict[str, Any]
) -> bool:
    """Distinguish an unattempted/early replay failure from a missing artifact."""

    retained_before_replay = (
        status in {"unit_error", "not_run_prefix_or_shell_failure"}
        and bool(result.get("error_type") or result.get("error"))
    )
    return prefix_reached and not retained_before_replay


def request_response_pair_audit(run_root: Path) -> dict[str, Any]:
    """Pair every recorded request with exactly one explicit success/failure response."""

    errors: list[str] = []
    request_paths = sorted(
        path for path in (run_root / "online").rglob("*.json") if path.parent.name == "requests"
    )
    response_paths = sorted(
        path for path in (run_root / "online").rglob("*.json") if path.parent.name == "responses"
    )
    paired_responses: set[Path] = set()
    explicit_failures = 0
    request_ids: list[str] = []
    for request_path in request_paths:
        relative = request_path.relative_to(run_root).as_posix()
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{relative}: invalid request JSON ({exc})")
            continue
        request_id = str(request.get("request_id") or "")
        request_ids.append(request_id)
        if not request_id or request_id != request_path.stem:
            errors.append(f"{relative}: filename/request_id mismatch")
        response_path = request_path.parent.parent / "responses" / f"{request_path.stem}.json"
        if not response_path.is_file():
            errors.append(f"{relative}: missing paired response")
            continue
        paired_responses.add(response_path.resolve())
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(
                f"{response_path.relative_to(run_root).as_posix()}: invalid response JSON ({exc})"
            )
            continue
        if str(response.get("request_id") or "") != request_id:
            errors.append(f"{relative}: response request_id mismatch")
        if response.get("ok") is True:
            if not isinstance(response.get("text"), str):
                errors.append(f"{relative}: successful response has no text")
        elif response.get("ok") is False:
            explicit_failures += 1
            if not response.get("error_type") or "error" not in response:
                errors.append(f"{relative}: failed response lacks explicit error record")
        else:
            errors.append(f"{relative}: response does not declare ok=true/false")
    for response_path in response_paths:
        if response_path.resolve() not in paired_responses:
            errors.append(
                f"{response_path.relative_to(run_root).as_posix()}: response has no paired request"
            )
    return {
        "errors": errors,
        "requests": len(request_paths),
        "responses": len(response_paths),
        "paired": len(paired_responses),
        "explicit_failures": explicit_failures,
        "request_ids": request_ids,
    }


def replay_file_audit(
    *, run_root: Path, unit_dir: Path, checkpoint: dict[str, Any], replay: dict[str, Any]
) -> dict[str, Any]:
    """Recompute replay state/image evidence from persisted files where possible."""

    errors: list[str] = []
    original_state = checkpoint.get("current_state")
    restored_state = replay.get("restored_state")
    state_recomputed = isinstance(original_state, dict) and isinstance(restored_state, dict)
    if isinstance(original_state, dict):
        original_digest = state_digest(original_state)
        if replay.get("original_state_digest") != original_digest:
            errors.append("original state digest differs from checkpoint recomputation")
    else:
        errors.append("checkpoint has no persisted original state")
    if state_recomputed:
        restored_digest = state_digest(restored_state)
        state_equal = canonical_state(original_state) == canonical_state(restored_state)
        if replay.get("restored_state_digest") != restored_digest:
            errors.append("restored state digest differs from persisted-state recomputation")
        if replay.get("state_equal") is not state_equal:
            errors.append("recorded state_equal differs from persisted-state recomputation")
    else:
        state_equal = None

    original_relative = Path(str(checkpoint.get("current_screenshot") or ""))
    original_path = (run_root / original_relative).resolve()
    restored_path = (unit_dir / "screenshots" / "restored.png").resolve()
    image_recomputed = False
    screenshot_equal: bool | None = None
    if not original_path.is_relative_to(run_root.resolve()):
        errors.append("original screenshot path escapes run directory")
    elif not original_path.is_file():
        errors.append("original checkpoint screenshot is missing")
    elif not restored_path.is_file():
        errors.append("restored screenshot is missing")
    else:
        image_recomputed = True
        original_hash = file_sha256(original_path)
        restored_hash = file_sha256(restored_path)
        screenshot_equal = original_hash == restored_hash
        if replay.get("original_screenshot_sha256") != original_hash:
            errors.append("original screenshot hash differs from file recomputation")
        if replay.get("restored_screenshot_sha256") != restored_hash:
            errors.append("restored screenshot hash differs from file recomputation")
        if replay.get("screenshot_equal") is not screenshot_equal:
            errors.append("recorded screenshot_equal differs from file recomputation")
    return {
        "errors": errors,
        "state_recomputed": state_recomputed,
        "state_equal": state_equal,
        "image_recomputed": image_recomputed,
        "screenshot_equal": screenshot_equal,
    }


def submission_consistency_errors(
    raw_task: dict[str, Any], result: dict[str, Any], checkpoint: dict[str, Any],
    score: dict[str, Any], server_receipts: list[dict[str, Any]],
) -> list[str]:
    """Recompute terminal class offline and cross-check actual choice/action evidence.

    Historical error_attribution wording is deliberately not used as a causal
    judgment. Dataset outcome class, receipt, and execution consistency are checked.
    """

    errors = []
    receipt = result.get("submission_receipt_public") or {}
    selected = str(receipt.get("selected_option_label") or "")
    if receipt not in server_receipts:
        errors.append("public receipt does not match any actual server receipt")
    if (score.get("terminal_score") or {}).get("outcome") != score_receipt(raw_task, receipt)["outcome"]:
        errors.append("terminal outcome differs from receipt+dataset recomputation")
    if score.get("selected_option_label") != selected or result.get("selected_before_submit") != selected:
        errors.append("selected-before-submit/score/receipt disagreement")
    policy = result.get("policy") or {}
    original = checkpoint.get("current_selection")
    changed = policy.get("changed") is True
    recommendation = policy.get("recommended_option")
    if policy.get("original_selection") != original:
        errors.append("policy original selection differs from checkpoint")
    if changed != bool(recommendation and recommendation != original):
        errors.append("policy changed flag disagrees with recommendation")
    if selected != (recommendation if changed else original):
        errors.append("submitted selection differs from policy decision")
    revision = result.get("revision_action")
    if changed and (not isinstance(revision, dict) or not revision.get("executed")
                    or (revision.get("action") or {}).get("option_text") != recommendation):
        errors.append("changed policy lacks matching successful revision action")
    if not changed and revision is not None:
        errors.append("unchanged policy unexpectedly executed revision")
    if (result.get("executed_submission") or {}).get("action") != checkpoint.get("pending_proposal"):
        errors.append("executed submission differs from saved proposal")
    if result.get("strategy") == "B0" and (changed or recommendation != original):
        errors.append("B0 did not preserve original selection")
    return errors


def validate_run(run_root: Path, *, require_complete_submission: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    manifest_path = run_root / "run_manifest.json"
    budget_path = run_root / "budget.json"
    run_start_path = run_root / "evaluator" / "run_start.json"
    require(manifest_path.is_file(), "missing run_manifest.json")
    require(budget_path.is_file(), "missing budget.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    budget = json.loads(budget_path.read_text(encoding="utf-8")) if budget_path.is_file() else {}
    integrity_schema_version = int(manifest.get("integrity_schema_version") or 1)
    run_start = (
        json.loads(run_start_path.read_text(encoding="utf-8")) if run_start_path.is_file() else {}
    )
    if integrity_schema_version >= 2:
        require(run_start_path.is_file(), "integrity-v2 run is missing evaluator/run_start.json")
        config = run_start.get("run_config") or {}
        config_canonical = json.dumps(
            config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        recomputed_config_sha256 = hashlib.sha256(config_canonical.encode("utf-8")).hexdigest()
        require(
            run_start.get("run_config_sha256") == recomputed_config_sha256,
            "run-start config fingerprint differs from persisted config",
        )
        require(
            manifest.get("run_config_sha256") == recomputed_config_sha256,
            "manifest config fingerprint differs from run-start config",
        )
        require(
            run_start.get("source_fingerprint") == manifest.get("code_fingerprint"),
            "manifest start source fingerprint differs from run-start record",
        )
        require(
            manifest.get("runtime_source_unchanged") is True
            and (manifest.get("end_code_fingerprint") or {}).get("tree_sha256")
            == (manifest.get("code_fingerprint") or {}).get("tree_sha256"),
            "runtime source/config identity changed before finalization",
        )
    mappings = read_jsonl(run_root / "evaluator" / "unit_map.jsonl")
    scores = read_jsonl(run_root / "evaluator" / "scores.jsonl")
    prefixes = read_jsonl(run_root / "evaluator" / "prefixes.jsonl")
    score_by_unit = {str(row.get("unit_id")): row for row in scores}
    if require_complete_submission:
        require(not manifest.get("run_errors"), "complete smoke has retained run-level errors")

    witness = manifest.get("preflight_multi_image_witness") or {}
    witness_request_count = len(
        list((run_root / "online" / "preflight_witness" / "requests").glob("*.json"))
    )
    if manifest.get("model_mode") == "live-local":
        require(bool(witness.get("required")), "live smoke did not require the multi-image witness")
        require(witness_request_count == 1, "live smoke must record exactly one witness request")
        require(
            int(witness.get("model_calls") or 0) == witness_request_count,
            "witness request count differs from witness model calls",
        )
        if require_complete_submission:
            require(witness.get("status") == "passed", "complete live smoke requires a passed witness")
            require(
                witness.get("returned_input_image_count") == 2,
                "complete live smoke witness did not confirm two server images",
            )
            require(
                set((witness.get("content_checks") or {}))
                == {"panel_1_red_triangle", "panel_2_blue_circle"}
                and all((witness.get("content_checks") or {}).values()),
                "complete live smoke witness did not distinguish both panels",
            )

    require(len(mappings) == int(manifest.get("configured_units") or -1), "unit-map count mismatch")
    require(len(scores) == int(manifest.get("completed_units") or -1), "score count mismatch")
    reached_count = sum(bool(row.get("checkpoint_reached")) for row in prefixes)
    require(
        reached_count == int(manifest.get("checkpoint_count") if "checkpoint_count" in manifest else -1),
        "checkpoint count mismatch",
    )
    require(len({row.get("unit_id") for row in mappings}) == len(mappings), "duplicate unit_id")
    require(len({row.get("prefix_id") for row in prefixes}) == len(prefixes), "duplicate prefix_id")

    task_conditions = {
        (str(row["task_slug"]), str(row["condition"])) for row in mappings
    }
    expected_combinations = {
        (task, condition, strategy)
        for task, condition in task_conditions
        for strategy in STRATEGIES
    }
    combination_counts = Counter(
        (str(row["task_slug"]), str(row["condition"]), str(row["strategy"]))
        for row in mappings
    )
    actual_combinations = set(combination_counts)
    # Each observed task-condition must have all four stage-two strategies exactly once.
    require(
        expected_combinations == actual_combinations
        and all(count == 1 for count in combination_counts.values()),
        "task-condition-strategy grid is incomplete or duplicated",
    )
    mapping_prefixes = {str(row["prefix_id"]) for row in mappings}
    recorded_prefixes = {str(row.get("prefix_id")) for row in prefixes}
    require(mapping_prefixes == recorded_prefixes, "prefix rows do not cover the mapped grid")

    checkpoint_before_submit = 0
    for row in prefixes:
        result = row.get("prefix_result") or {}
        reached = bool(row.get("checkpoint_reached"))
        before_submit = (
            result.get("submission_count_before") == result.get("submission_count_after_capture")
            and result.get("submission_count_after_capture") == 0
        )
        clean = reached and before_submit and not result.get("errors")
        checkpoint_before_submit += int(clean)
        require(before_submit, f"{row.get('prefix_id')}: submission count changed during checkpoint capture")
        if not reached:
            require(bool(result.get("errors")), f"{row.get('prefix_id')}: no checkpoint and no failure reason")
        if require_complete_submission:
            require(clean, f"{row.get('prefix_id')}: complete smoke requires a clean checkpoint")

    per_strategy: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    replay_state_equal = 0
    replay_screenshot_equal = 0
    replay_states_recomputed = 0
    replay_images_recomputed = 0
    historical_replay_states_not_recomputable = 0
    submissions = 0
    observed_receipts = 0
    confirmations = 0
    online_request_count = 0
    unit_rows: list[dict[str, Any]] = []
    strategy_call_bounds = {"B0": (0, 0), "B2": (1, 1), "B3": (1, 3), "B4": (2, 2)}
    strategy_observation_bounds = {"B0": (0, 0), "B2": (0, 0), "B3": (0, 2), "B4": (0, 0)}
    prefix_by_id = {str(row["prefix_id"]): row for row in prefixes}
    actual_receipts = [row for path in (run_root / "server_receipts").glob("*.jsonl")
                       for row in read_jsonl(path)]
    for mapping in mappings:
        unit_id = str(mapping["unit_id"])
        strategy = str(mapping["strategy"])
        unit_dir = run_root / "online" / "units" / unit_id
        result_path = unit_dir / "result.json"
        replay_path = unit_dir / "replay.json"
        require(result_path.is_file(), f"{unit_id}: missing result.json")
        if not result_path.is_file():
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        status = str(result.get("status") or "")
        prefix_reached = bool((prefix_by_id.get(str(mapping["prefix_id"])) or {}).get("checkpoint_reached"))
        if replay_artifact_required(
            prefix_reached=prefix_reached, status=status, result=result
        ):
            require(
                replay_path.is_file(),
                f"{unit_id}: checkpoint exists but replay.json is missing without an early failure",
            )
        replay = json.loads(replay_path.read_text(encoding="utf-8")) if replay_path.is_file() else {}
        checkpoint_path = (
            run_root
            / "online"
            / "prefixes"
            / str(mapping["prefix_id"])
            / "checkpoint.json"
        )
        checkpoint = (
            json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if checkpoint_path.is_file()
            else {}
        )
        recomputed_replay = (
            replay_file_audit(
                run_root=run_root,
                unit_dir=unit_dir,
                checkpoint=checkpoint,
                replay=replay,
            )
            if replay
            else {
                "errors": [],
                "state_recomputed": False,
                "state_equal": None,
                "image_recomputed": False,
                "screenshot_equal": None,
            }
        )
        for error in recomputed_replay["errors"]:
            require(False, f"{unit_id}: {error}")
        if replay:
            replay_states_recomputed += int(recomputed_replay["state_recomputed"])
            replay_images_recomputed += int(recomputed_replay["image_recomputed"])
            historical_replay_states_not_recomputable += int(
                not recomputed_replay["state_recomputed"]
            )
            if integrity_schema_version >= 2:
                require(
                    recomputed_replay["state_recomputed"],
                    f"{unit_id}: integrity-v2 replay lacks persisted restored state",
                )
                require(
                    recomputed_replay["image_recomputed"],
                    f"{unit_id}: integrity-v2 replay image hashes cannot be recomputed",
                )
        state_ok = (
            recomputed_replay["state_equal"]
            if recomputed_replay["state_recomputed"]
            else replay.get("state_equal") is True if replay else False
        )
        shot_ok = (
            recomputed_replay["screenshot_equal"]
            if recomputed_replay["image_recomputed"]
            else replay.get("screenshot_equal") is True if replay else False
        )
        replay_state_equal += int(state_ok)
        replay_screenshot_equal += int(shot_ok)
        submitted = result.get("submission_observed") is True
        receipt_count = int(
            result.get("submission_receipt_count")
            if result.get("submission_receipt_count") is not None
            else submitted
        )
        confirmed = result.get("confirmation_observed") is True
        submissions += int(submitted)
        observed_receipts += receipt_count
        confirmations += int(confirmed)
        policy = result.get("policy") or {}
        calls = int(policy.get("model_calls") or 0)
        observations = int(policy.get("active_observations") or 0)
        request_count = len(list((unit_dir / "requests").glob("*.json")))
        if strategy == "B3":
            for error in b3_metric_errors(policy, unit_dir):
                require(False, f"{unit_id}: {error}")
            if policy and policy.get("parse_status") != "valid":
                warnings.append(f"{unit_id}: B3 produced no accepted verification decision; submission may be fallback")
        online_request_count += request_count
        score = score_by_unit.get(unit_id) or {}
        require(bool(score), f"{unit_id}: missing evaluator score row")
        outcome = str((score.get("terminal_score") or {}).get("outcome") or "unscored")
        if status in {"submitted", "submitted_acknowledgement_error"}:
            require(checkpoint_path.is_file(), f"{unit_id}: submitted unit has no checkpoint")
            if checkpoint_path.is_file():
                raw_task = find_task(
                    task_spec_path(str(mapping["condition"]), str(mapping["task_slug"])),
                    str(mapping["task_slug"]),
                )
                for error in submission_consistency_errors(raw_task, result, checkpoint, score, actual_receipts):
                    require(False, f"{unit_id}: {error}")
            require(state_ok, f"{unit_id}: replayed public state differs")
            require(shot_ok, f"{unit_id}: replayed screenshot differs")
            require(submitted, f"{unit_id}: no server-side submission receipt")
            require(receipt_count == 1, f"{unit_id}: submitted unit must have exactly one receipt")
            require(score.get("terminal_score") is not None, f"{unit_id}: submitted unit is unscored")
            if status == "submitted":
                require(confirmed, f"{unit_id}: confirmation page not observed")
            lo, hi = strategy_call_bounds[strategy]
            if policy.get("parse_status") in {
                "independent_chart_observation_unavailable_keep", "chart_observation_unavailable_keep"
            }:
                lo = hi = 0
                require(not policy.get("changed"), f"{unit_id}: unavailable independent chart cannot justify revision")
            require(lo <= calls <= hi, f"{unit_id}: {strategy} model_calls={calls} outside [{lo},{hi}]")
            require(request_count == calls, f"{unit_id}: request count differs from policy model_calls")
            lo, hi = strategy_observation_bounds[strategy]
            require(
                lo <= observations <= hi,
                f"{unit_id}: {strategy} active_observations={observations} outside [{lo},{hi}]",
            )
        elif status == "duplicate_submission_error":
            duplicate_receipts = result.get("duplicate_submission_receipts_public")
            require(submitted, f"{unit_id}: duplicate submission was not marked observed")
            require(receipt_count > 1, f"{unit_id}: duplicate submission lacks multiple receipts")
            require(
                isinstance(duplicate_receipts, list) and len(duplicate_receipts) == receipt_count,
                f"{unit_id}: duplicate receipt evidence/count mismatch",
            )
            require(
                score.get("terminal_score") is None and bool(score.get("exclusion_reason")),
                f"{unit_id}: duplicate submission must be excluded and unscored",
            )
        else:
            require(not submitted, f"{unit_id}: non-submitted status has a receipt")
            require(receipt_count == 0, f"{unit_id}: non-submitted status has receipt records")
            require(
                (score.get("terminal_score") is None and bool(score.get("exclusion_reason"))),
                f"{unit_id}: failed unit is not retained with an exclusion reason",
            )
        if require_complete_submission:
            require(result.get("status") == "submitted", f"{unit_id}: complete smoke requires submission")
        per_strategy[strategy]["units"] += 1
        per_strategy[strategy]["model_calls"] += calls
        per_strategy[strategy]["active_observations"] += observations
        for key, value in (policy.get("verification_metrics") or {}).items():
            per_strategy[strategy][key] += value
        per_strategy[strategy][outcome] += 1
        unit_rows.append(
            {
                **{key: mapping[key] for key in ("unit_id", "task_slug", "condition", "strategy")},
                "checkpoint_prefix": mapping["prefix_id"],
                "replay_state_equal": state_ok,
                "replay_screenshot_equal": shot_ok,
                "submission_observed": submitted,
                "submission_receipt_count": receipt_count,
                "confirmation_observed": confirmed,
                "model_calls": calls,
                "active_observations": observations,
                "verification_metrics": policy.get("verification_metrics") or {},
                "outcome": outcome,
            }
        )

    events = list(budget.get("events") or [])
    model_events = [event for event in events if event.get("kind") == "model_call"]
    transition_events = [event for event in events if event.get("kind") == "browser_transition"]
    require(
        len(model_events) == int(budget["model_calls"] if "model_calls" in budget else -1),
        "model-call ledger mismatch",
    )
    require(
        len(transition_events)
        == int(budget["browser_transitions"] if "browser_transitions" in budget else -1),
        "browser-transition ledger mismatch",
    )
    require(
        int(budget.get("model_calls") or 0) <= int(budget.get("max_model_calls") or 0),
        "model-call budget exceeded",
    )
    require(
        int(budget.get("browser_transitions") or 0)
        <= int(budget.get("max_browser_transitions") or 0),
        "browser-transition budget exceeded",
    )
    if integrity_schema_version >= 2:
        require(bool(budget.get("snapshot_bound_at")), "budget ledger was not bound at run start")
        require(
            int(budget.get("snapshot_writes") or 0) >= len(events) + 1,
            "budget ledger was not persisted at start and after every charged event",
        )
    prefix_request_count = sum(
        len(list((run_root / "online" / "prefixes" / str(row["prefix_id"]) / "requests").glob("*.json")))
        for row in prefixes
    )
    require(
        witness_request_count + prefix_request_count + online_request_count == len(model_events),
        "recorded request count differs from model-call ledger",
    )
    pair_audit = request_response_pair_audit(run_root)
    for error in pair_audit["errors"]:
        require(False, error)
    ledger_request_ids = [
        str(event.get("request_id") or "") for event in model_events
    ]
    require(
        Counter(pair_audit["request_ids"]) == Counter(ledger_request_ids),
        "request IDs differ from model-call ledger",
    )
    require(
        len(set(pair_audit["request_ids"])) == len(pair_audit["request_ids"]),
        "request IDs are not session-unique",
    )

    receipt_rows = sum(
        (read_jsonl(path) for path in (run_root / "server_receipts").glob("*.jsonl")), []
    )
    require(
        len(receipt_rows) == observed_receipts,
        "server receipt count differs from observed receipt records",
    )

    isolation_errors: list[str] = []
    online_json_files = sorted((run_root / "online").rglob("*.json"))
    for path in online_json_files:
        try:
            assert_online_payload(json.loads(path.read_text(encoding="utf-8")))
        except (IsolationError, json.JSONDecodeError) as exc:
            isolation_errors.append(f"{path.relative_to(run_root)}: {exc}")
    hidden_terms = hidden_terms_for(mappings)
    hidden_value_hits: list[dict[str, str]] = []
    allowed_model_history_hits: list[dict[str, str]] = []
    online_request_files = sorted(
        path for path in (run_root / "online").rglob("*.json") if path.parent.name == "requests"
    )
    for path in online_request_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_text = json.dumps(payload, ensure_ascii=False).casefold()
        text, verified_history = request_text_for_hidden_scan(path, payload)
        for term in hidden_terms:
            if term.casefold() in text:
                hidden_value_hits.append(
                    {"path": path.relative_to(run_root).as_posix(), "term": term}
                )
            elif verified_history and term.casefold() in raw_text:
                allowed_model_history_hits.append(
                    {"path": path.relative_to(run_root).as_posix(), "term": term}
                )
    image_reference_count = 0
    for request_path in online_request_files:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        artifacts = payload.get("image_artifacts")
        if artifacts is None and payload.get("image_artifact"):
            artifacts = [payload["image_artifact"]]
        require(isinstance(artifacts, list) and bool(artifacts), f"{request_path}: no image input")
        for artifact in artifacts or []:
            image_reference_count += 1
            relative = Path(str(artifact))
            candidate = (
                run_root / relative
                if relative.parts and relative.parts[0] == "online"
                else request_path.parent.parent / relative
            ).resolve()
            require(
                candidate.is_relative_to(run_root.resolve()),
                f"{request_path}: image input escapes the run directory",
            )
            require(
                candidate.is_relative_to(request_path.parent.parent.resolve()),
                f"{request_path}: image input crosses its prefix/unit boundary",
            )
            require(candidate.is_file(), f"{request_path}: missing image input {artifact}")
    image_metadata_hits: list[dict[str, str]] = []
    online_images = sorted(
        path
        for path in (run_root / "online").rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    )
    for path in online_images:
        with Image.open(path) as image:
            metadata = json.dumps(image.info, ensure_ascii=False, default=str).casefold()
        for term in hidden_terms:
            if term.casefold() in metadata:
                image_metadata_hits.append(
                    {"path": path.relative_to(run_root).as_posix(), "term": term}
                )
    require(not isolation_errors, f"online JSON key isolation errors: {isolation_errors}")
    require(not hidden_value_hits, f"task-specific hidden strings in online text: {hidden_value_hits}")
    require(not image_metadata_hits, f"task-specific hidden strings in online image metadata: {image_metadata_hits}")

    outcome_counts = Counter(
        str((row.get("terminal_score") or {}).get("outcome") or row.get("exclusion_reason") or "unknown")
        for row in scores
    )
    fingerprint_rows = (manifest.get("code_fingerprint") or {}).get("files") or []
    fingerprint_mismatches: list[dict[str, str]] = []
    for row in fingerprint_rows:
        relative = str(row.get("path") or "")
        candidate = REPOSITORY_ROOT / relative
        current = file_sha256(candidate) if candidate.is_file() else "missing"
        recorded = str(row.get("sha256") or "")
        if current != recorded:
            fingerprint_mismatches.append(
                {"path": relative, "recorded_sha256": recorded, "current_sha256": current}
            )
    if fingerprint_mismatches:
        warnings.append(
            "current source differs from the run-time fingerprint; validate this run as a historical artifact"
        )
    snapshot_mismatches: list[dict[str, str]] = []
    if run_start:
        snapshot_root = run_root / "evaluator" / "runtime_source_snapshot"
        for row in run_start.get("runtime_source_snapshot") or []:
            relative = str(row.get("path") or "")
            candidate = snapshot_root / relative
            current = file_sha256(candidate) if candidate.is_file() else "missing"
            recorded = str(row.get("sha256") or "")
            if current != recorded:
                snapshot_mismatches.append(
                    {"path": relative, "recorded_sha256": recorded, "snapshot_sha256": current}
                )
        require(not snapshot_mismatches, f"runtime source snapshot mismatch: {snapshot_mismatches}")
    if historical_replay_states_not_recomputable:
        warnings.append(
            f"historical schema lacks persisted restored_state for "
            f"{historical_replay_states_not_recomputable} replay(s); image hashes and original state "
            "were recomputed, but restored-state equality remains record-only"
        )
    report = {
        "run_id": run_root.name,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "units": len(mappings),
            "prefixes": len(prefixes),
            "checkpoint_before_submit": checkpoint_before_submit,
            "replay_state_equal": replay_state_equal,
            "replay_screenshot_equal": replay_screenshot_equal,
            "replay_states_recomputed_from_files": replay_states_recomputed,
            "replay_images_recomputed_from_files": replay_images_recomputed,
            "submissions_observed": submissions,
            "submission_receipts_observed": observed_receipts,
            "confirmations_observed": confirmations,
            "server_receipts": len(receipt_rows),
            "model_calls": len(model_events),
            "request_response_pairs": pair_audit["paired"],
            "explicit_failed_model_responses": pair_audit["explicit_failures"],
            "preflight_witness_model_calls": int(witness.get("model_calls") or 0),
            "browser_transitions": len(transition_events),
            "online_json_files_scanned": len(online_json_files),
            "online_images_metadata_scanned": len(online_images),
        },
        "budget_limits": {
            "model_calls": budget.get("max_model_calls"),
            "browser_transitions": budget.get("max_browser_transitions"),
        },
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "per_strategy": {
            strategy: dict(sorted(per_strategy[strategy].items())) for strategy in STRATEGIES
        },
        "isolation": {
            "online_key_errors": isolation_errors,
            "hidden_value_hits": hidden_value_hits,
            "allowed_model_history_hits": allowed_model_history_hits,
            "image_metadata_hits": image_metadata_hits,
            "task_specific_hidden_terms_checked": len(hidden_terms),
            "model_input_request_files_scanned": len(online_request_files),
            "model_input_image_references_checked": image_reference_count,
        },
        "provenance": {
            "integrity_schema_version": integrity_schema_version,
            "run_start_recorded": run_start_path.is_file(),
            "budget_persisted_from_start": bool(budget.get("snapshot_bound_at")),
            "recorded_source_files": len(fingerprint_rows),
            "current_tree_matches_recorded_files": not fingerprint_mismatches,
            "current_file_mismatches": fingerprint_mismatches,
            "runtime_source_snapshot_files": len(
                (run_start.get("runtime_source_snapshot") or []) if run_start else []
            ),
            "runtime_source_snapshot_mismatches": snapshot_mismatches,
        },
        "units": unit_rows,
        "interpretation": (
            "engineering-only scripted mock; outcomes are not evidence about visual reasoning"
            if manifest.get("model_mode") == "mock"
            else "exploratory clear-rule development cases; inspect actual errors and corrections individually, not population efficacy"
            if manifest.get("profile") == "clear-rule-probe"
            else "live-local engineering chain smoke; scientific interpretation still requires the approved pilot design"
        ),
        "complete_submission_required": require_complete_submission,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--write", action="store_true", help="write evaluator/validation.json")
    parser.add_argument(
        "--require-complete-submission",
        action="store_true",
        help="also require every prefix, replay, submission, and confirmation to complete",
    )
    args = parser.parse_args()
    report = validate_run(
        args.run_dir.resolve(), require_complete_submission=args.require_complete_submission
    )
    if args.write:
        write_json(args.run_dir.resolve() / "evaluator" / "validation.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
