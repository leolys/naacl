"""Offline structural and isolation audit for a decision-evidence run directory."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .core import IsolationError, assert_online_payload, public_task_projection, write_json
from .runner import CONDITION_FILES, REPOSITORY_ROOT, STRATEGIES, file_sha256, find_task


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
        raw = find_task(CONDITION_FILES[condition], slug)
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


def validate_run(run_root: Path, *, require_complete_submission: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    manifest_path = run_root / "run_manifest.json"
    budget_path = run_root / "budget.json"
    require(manifest_path.is_file(), "missing run_manifest.json")
    require(budget_path.is_file(), "missing budget.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    budget = json.loads(budget_path.read_text(encoding="utf-8")) if budget_path.is_file() else {}
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
    submissions = 0
    observed_receipts = 0
    confirmations = 0
    online_request_count = 0
    unit_rows: list[dict[str, Any]] = []
    strategy_call_bounds = {"B0": (0, 0), "B2": (1, 1), "B3": (1, 3), "B4": (2, 2)}
    strategy_observation_bounds = {"B0": (0, 0), "B2": (0, 0), "B3": (0, 2), "B4": (0, 0)}
    prefix_by_id = {str(row["prefix_id"]): row for row in prefixes}
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
        state_ok = replay.get("state_equal") is True if replay else False
        shot_ok = replay.get("screenshot_equal") is True if replay else False
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
        online_request_count += request_count
        score = score_by_unit.get(unit_id) or {}
        require(bool(score), f"{unit_id}: missing evaluator score row")
        outcome = str((score.get("terminal_score") or {}).get("outcome") or "unscored")
        if status in {"submitted", "submitted_acknowledgement_error"}:
            require(state_ok, f"{unit_id}: replayed public state differs")
            require(shot_ok, f"{unit_id}: replayed screenshot differs")
            require(submitted, f"{unit_id}: no server-side submission receipt")
            require(receipt_count == 1, f"{unit_id}: submitted unit must have exactly one receipt")
            require(score.get("terminal_score") is not None, f"{unit_id}: submitted unit is unscored")
            if status == "submitted":
                require(confirmed, f"{unit_id}: confirmation page not observed")
            lo, hi = strategy_call_bounds[strategy]
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
    prefix_request_count = sum(
        len(list((run_root / "online" / "prefixes" / str(row["prefix_id"]) / "requests").glob("*.json")))
        for row in prefixes
    )
    require(
        witness_request_count + prefix_request_count + online_request_count == len(model_events),
        "recorded request count differs from model-call ledger",
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
            "submissions_observed": submissions,
            "submission_receipts_observed": observed_receipts,
            "confirmations_observed": confirmations,
            "server_receipts": len(receipt_rows),
            "model_calls": len(model_events),
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
            "recorded_source_files": len(fingerprint_rows),
            "current_tree_matches_recorded_files": not fingerprint_mismatches,
            "current_file_mismatches": fingerprint_mismatches,
        },
        "units": unit_rows,
        "interpretation": (
            "engineering-only scripted mock; outcomes are not evidence about visual reasoning"
            if manifest.get("model_mode") == "mock"
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
