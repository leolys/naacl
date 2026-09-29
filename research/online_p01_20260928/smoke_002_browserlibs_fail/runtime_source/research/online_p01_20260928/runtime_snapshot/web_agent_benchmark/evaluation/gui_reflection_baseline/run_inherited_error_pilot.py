#!/usr/bin/env python3
"""Run an inherited-error recovery quartet with a role-blind rotated layout.

Each cell first creates a real evaluator-owned Wind selection through the
browser, resets the official GUI-Reflection agent, and hands off the resulting
review screenshot.  Candidate/reference compare native-4 trajectory context
with a true current-only inference reset; this is a history contrast, not an
R+/R- reflection-training contrast.  F0 and F3 are separate probes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping
import uuid

from .asset_variants import apply_asset_variant_case
from .agent_runtime import AgentClient, HttpAgentClient, ManagedAgentServer
from .formal_path_policy import REPO_ROOT
from .run_targeted_recovery_pilot import (
    CHECKPOINT_ID,
    EXPECTED_MODEL_PATH,
    EXPECTED_OFFICIAL_REPO,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    build_browser_factory,
    cross_cell_checks,
    execution_complete,
    load_authoritative_case,
    run_cell,
    action_history_sha256,
    utc_now,
    verify_health,
    write_json,
)
from .run_travel_pair import verify_agent_service
from .targeted_recovery import (
    CURRENT_VISIBLE_RETRY,
    EVIDENCE_REVIEW_REGIMES,
    F0_NEUTRAL_RECHECK,
    F1_CHECKLIST,
    F2_AUDITED_VALUES,
    F3_OUTCOME_CONTRADICTION,
    F3_PRE_REATTEMPT_CONTRADICTION,
    FEEDBACK_RETRY,
    HISTORY_CONTRAST,
    STANDARDIZED_MISTAKE,
    TargetedRecoveryRegistry,
    analyze_recovery_quartet,
)
from .targeted_recovery_scorer import CanonicalSubmissionScorer
from .targeted_recovery_validator import CanonicalOutcomeValidator
from .targeted_recovery_layout import (
    LAYOUT_IDS,
    derive_layout_case as derive_role_blind_layout_case,
    layout_algorithm,
    layout_offset,
)


LAYOUT_ID = "cyclic_shift_1"
RENDERER_BUILD_ID = "compact-recovery-v4"
NATIVE4_CONDITION = "gui_reflection_sft_inherited_native4"
CURRENT_ONLY_CONDITION = "gui_reflection_sft_inherited_current_only"
CONTRAST_ID = "history:gui-reflection-sft-inherited:native4-vs-current-only"


def derive_layout_case(
    canonical_case: Mapping[str, Any], layout_id: str = LAYOUT_ID
) -> dict[str, Any]:
    """Backward-compatible wrapper around the generic role-blind layout."""

    return derive_role_blind_layout_case(canonical_case, layout_id=layout_id)


def condition_records(layout_id: str = LAYOUT_ID) -> list[dict[str, Any]]:
    shared = {
        "checkpoint_id": CHECKPOINT_ID,
        "checkpoint_stage": "sft",
        "reflection_training_status": "gui_reflection_sft",
        "workflow_mode": FEEDBACK_RETRY,
        "renderer_build_id": RENDERER_BUILD_ID,
        "viewport_width": VIEWPORT_WIDTH,
        "viewport_height": VIEWPORT_HEIGHT,
        "ui_variant": f"compact_recovery_v4_{layout_id}",
    }
    return [
        {
            "condition_id": NATIVE4_CONDITION,
            **shared,
            "history_mode": "native4",
        },
        {
            "condition_id": CURRENT_ONLY_CONDITION,
            **shared,
            "history_mode": "current_only",
        },
    ]


def approved_f2_record(case: Mapping[str, Any], *, layout_id: str) -> dict[str, Any]:
    source_refs: list[dict[str, str]] = []
    for arm in ("official", "clean"):
        chart_path = Path(str(case["arms"][arm]["chart_path"]))
        source_refs.extend(
            [
                {
                    "arm": arm,
                    "artifact_kind": "task_row",
                    "artifact_path": str(case["source_references"][arm]["path"]),
                    "record_locator": f"line:{case['source_references'][arm]['line']}",
                },
                {
                    "arm": arm,
                    "artifact_kind": "csv",
                    "artifact_path": chart_path.with_name("source.csv").as_posix(),
                    "record_locator": "rows:Solar,Wind,Hydroelectric",
                },
                {
                    "arm": arm,
                    "artifact_kind": "figure",
                    "artifact_path": chart_path.as_posix(),
                    "record_locator": "full_asset",
                },
            ]
        )
    return {
        "record_id": f"evidence:env008:{layout_id}:agent-cross-checked:f2:v2",
        "pair_group_id": str(case["pair_group_id"]),
        "evidence_level": F2_AUDITED_VALUES,
        "source_refs": source_refs,
        "evidence_kind": "agent-reviewed diagnostic evidence",
        "review_status": "agent_cross_checked",
        "reviewed_by": ["/root", "/root/env008_sample_designer"],
        "review_method": (
            "cross-check canonical official/clean task rows, CSV files, and figure assets"
        ),
        "reviewed_at": "2026-08-31",
        "reportable": False,
        "model_visible_payload": {
            "heading": "Reviewed source values",
            "facts": [
                {
                    "subject": "Solar",
                    "relation": "reported production percentage",
                    "object": "41.2%",
                },
                {
                    "subject": "Wind",
                    "relation": "reported production percentage",
                    "object": "29.8%",
                },
                {
                    "subject": "Hydroelectric",
                    "relation": "reported production percentage",
                    "object": "18.5%",
                },
            ],
        },
    }


def build_registry(
    case: Mapping[str, Any], layout_id: str = LAYOUT_ID
) -> TargetedRecoveryRegistry:
    canonical_pair = str(
        case.get("canonical_pair_group_id", case.get("pair_group_id", ""))
    )
    approved_evidence = (
        [approved_f2_record(case, layout_id=layout_id)]
        if canonical_pair == "synthetic140:environment35:env008"
        else []
    )
    return TargetedRecoveryRegistry(
        repository_root=REPO_ROOT,
        cases=[case],
        conditions=condition_records(layout_id),
        contrasts=[
            {
                "contrast_id": CONTRAST_ID,
                "contrast_axis": HISTORY_CONTRAST,
                "candidate_condition": NATIVE4_CONDITION,
                "reference_condition": CURRENT_ONLY_CONDITION,
            }
        ],
        approved_evidence_records=approved_evidence,
    )


def base_fields_for_cell(
    *,
    case: Mapping[str, Any],
    trial_id: str,
    run_id: str,
    arm: str,
    condition: str,
    evidence_level: str,
    layout_id: str = LAYOUT_ID,
) -> dict[str, Any]:
    misleading = list(case["runner_only"]["misleading_action_ids"])
    if len(misleading) != 1:
        raise ValueError("inherited pilot requires one canonical misleading action")
    return {
        "run_id": run_id,
        "trial_id": trial_id,
        "pair_group_id": case["pair_group_id"],
        "condition": condition,
        "arm": arm,
        "recovery_branch": STANDARDIZED_MISTAKE,
        "injected_mistake_action_id": misleading[0],
        "evidence_level": evidence_level,
        "evidence_record_id": (
            approved_f2_record(case, layout_id=layout_id)["record_id"]
            if evidence_level == F2_AUDITED_VALUES
            else None
        ),
        "review_regime": EVIDENCE_REVIEW_REGIMES[evidence_level],
        "retry_presentation": CURRENT_VISIBLE_RETRY,
        "training_recipe_match_id": None,
    }


def validate_interventions(
    results: Mapping[str, Mapping[str, Any]], *, evidence_level: str, layout_id: str
) -> list[str]:
    """Make real evaluator handoff receipts an execution-validity condition."""

    reasons: list[str] = []
    empty_action_digest = action_history_sha256([], [])
    seen_intervention_transactions: set[str] = set()
    seen_initial_outcome_ids: set[str] = set()
    for key, row in results.items():
        value = row.get("intervention_path")
        if not isinstance(value, str) or not Path(value).is_file():
            reasons.append(f"missing_intervention_receipt:{key}")
            continue
        try:
            receipt = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            reasons.append(f"invalid_intervention_receipt:{key}")
            continue
        ui = receipt.get("ui_receipt")
        execution = receipt.get("browser_execution")
        handoff = receipt.get("handoff_model_receipt")
        post_setup = receipt.get("post_setup_snapshot")
        if (
            receipt.get("run_id") != row.get("run_id")
            or receipt.get("pair_group_id") != row.get("pair_group_id")
            or receipt.get("task_instance_id") != row.get("task_instance_id")
            or receipt.get("arm") != row.get("arm")
            or receipt.get("layout_id") != layout_id
            or receipt.get("injected_action_id")
            != row.get("injected_mistake_action_id")
        ):
            reasons.append(f"intervention_identity_mismatch:{key}")
        if receipt.get("source") != "evaluator_intervention":
            reasons.append(f"wrong_intervention_source:{key}")
        if receipt.get("normalized_as_agent_selection") is not False:
            reasons.append(f"injected_selection_counted_as_agent:{key}")
        if not isinstance(ui, Mapping) or ui.get("kind") != "selection":
            reasons.append(f"missing_intervention_selection_post:{key}")
        elif (
            ui.get("choice_token") != receipt.get("raw_choice_token")
            or ui.get("control_position") != receipt.get("raw_control_position")
            or ui.get("from_state") != "initial_decision"
        ):
            reasons.append(f"intervention_raw_control_mismatch:{key}")
        else:
            transaction_id = ui.get("transaction_id")
            if not isinstance(transaction_id, str) or not transaction_id:
                reasons.append(f"missing_intervention_transaction:{key}")
            elif transaction_id in seen_intervention_transactions:
                reasons.append(f"reused_intervention_transaction:{key}")
            else:
                seen_intervention_transactions.add(transaction_id)
        if (
            not isinstance(post_setup, Mapping)
            or post_setup.get("visible_state") != "review"
            or post_setup.get("current_choice_token")
            != receipt.get("raw_choice_token")
            or post_setup.get("current_control_position")
            != receipt.get("raw_control_position")
            or post_setup.get("selection_count") != 1
            or post_setup.get("reversal_count") != 0
            or post_setup.get("submitted") is not False
        ):
            reasons.append(f"intervention_post_setup_state_mismatch:{key}")
        if (
            not isinstance(execution, Mapping)
            or not str(execution.get("from_url", "")).endswith("/decision")
            or not str(execution.get("to_url", "")).endswith("/review")
        ):
            reasons.append(f"intervention_browser_history_unproven:{key}")
        if not isinstance(handoff, Mapping):
            reasons.append(f"missing_post_intervention_reset_receipt:{key}")
        else:
            if (
                handoff.get("task_step_index") != 0
                or handoff.get("history_image_count_before") != 0
                or handoff.get("history_image_sha256_before") != []
                or handoff.get("action_count_before") != 0
                or handoff.get("memory_empty_before") is not True
                or handoff.get("action_history_sha256_before")
                != empty_action_digest
                or handoff.get("screenshot_png_sha256")
                != row.get("first_screenshot_sha256")
            ):
                reasons.append(f"post_intervention_reset_not_empty:{key}")
        outcome_id = receipt.get("outcome_record_id")
        if evidence_level in {
            F3_OUTCOME_CONTRADICTION,
            F3_PRE_REATTEMPT_CONTRADICTION,
        }:
            validator_path = row.get("validator_records_path")
            if (
                not isinstance(outcome_id, str)
                or not outcome_id
                or not isinstance(validator_path, str)
                or not Path(validator_path).is_file()
            ):
                reasons.append(f"missing_initial_f3_validation:{key}")
            if (
                not isinstance(post_setup, Mapping)
                or post_setup.get("outcome_record_id") != outcome_id
                or post_setup.get("outcome_choice_token")
                != receipt.get("raw_choice_token")
                or post_setup.get("outcome_contradiction") is not True
            ):
                reasons.append(f"initial_f3_not_attached_to_review:{key}")
            else:
                validator_rows = [
                    json.loads(line)
                    for line in Path(validator_path)
                    .read_text(encoding="utf-8")
                    .splitlines()
                    if line.strip()
                ]
                first_validator = validator_rows[0] if validator_rows else {}
                if (
                    first_validator.get("source")
                    != "canonical_outcome_validator"
                    or first_validator.get("outcome_record_id") != outcome_id
                    or first_validator.get("provisional_choice_token")
                    != receipt.get("raw_choice_token")
                    or first_validator.get("provisional_control_position")
                    != receipt.get("raw_control_position")
                    or first_validator.get("contradiction") is not True
                    or first_validator.get("layout_id") != layout_id
                    or first_validator.get("pair_group_id")
                    != receipt.get("pair_group_id")
                    or first_validator.get("task_instance_id")
                    != receipt.get("task_instance_id")
                    or first_validator.get("arm") != receipt.get("arm")
                    or first_validator.get("provisional_action_id")
                    != receipt.get("injected_action_id")
                ):
                    reasons.append(f"initial_f3_validation_mismatch:{key}")
                elif outcome_id in seen_initial_outcome_ids:
                    reasons.append(f"reused_initial_f3_validation:{key}")
                else:
                    seen_initial_outcome_ids.add(outcome_id)
        elif (
            outcome_id is not None
            or row.get("validator_records_path") is not None
            or (
                isinstance(post_setup, Mapping)
                and (
                    post_setup.get("outcome_record_id") is not None
                    or post_setup.get("outcome_choice_token") is not None
                    or post_setup.get("outcome_contradiction") is not None
                )
            )
        ):
            reasons.append(f"f0_contains_outcome_feedback:{key}")
        events_path = row.get("events_path")
        if not isinstance(events_path, str) or not Path(events_path).is_file():
            reasons.append(f"missing_normalized_events:{key}")
        else:
            events = [
                json.loads(line)
                for line in Path(events_path).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            pre_review_agent_selections = [
                event
                for event in events
                if event.get("event_type") == "ui_selection"
                and event.get("decision_state") == "initial_decision"
            ]
            if pre_review_agent_selections:
                reasons.append(f"standardized_trace_contains_agent_initial_choice:{key}")
    return reasons


def retry_current_cross_cell_checks(
    results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Pair the first model-visible retry frame across history conditions.

    The history treatment begins only after the first handoff step.  A
    post-reversal comparison is interpretable only if native4 and current-only
    receive byte-identical retry-current pixels within the same data arm.
    """

    checks: dict[str, Any] = {}
    for arm in ("official", "clean"):
        candidate_result = results.get(f"candidate_{arm}", {})
        reference_result = results.get(f"reference_{arm}", {})
        candidate_analysis = candidate_result.get("analysis")
        reference_analysis = reference_result.get("analysis")
        candidate_reversal = (
            candidate_analysis.get("reversal_action_type")
            if isinstance(candidate_analysis, Mapping)
            else None
        )
        reference_reversal = (
            reference_analysis.get("reversal_action_type")
            if isinstance(reference_analysis, Mapping)
            else None
        )
        rows: dict[str, dict[str, Any] | None] = {}
        for role in ("candidate", "reference"):
            result = results.get(f"{role}_{arm}", {})
            raw_steps_path = result.get("raw_steps_path")
            retry_row: dict[str, Any] | None = None
            if isinstance(raw_steps_path, str) and Path(raw_steps_path).is_file():
                try:
                    step_rows = [
                        json.loads(line)
                        for line in Path(raw_steps_path)
                        .read_text(encoding="utf-8")
                        .splitlines()
                        if line.strip()
                    ]
                except (OSError, json.JSONDecodeError):
                    step_rows = []
                retry_row = next(
                    (
                        row
                        for row in step_rows
                        if isinstance(row, dict)
                        and row.get("input_state") == "retry_decision"
                    ),
                    None,
                )
            rows[role] = retry_row
        candidate = rows["candidate"]
        reference = rows["reference"]
        def artifact_digest(row: Mapping[str, Any] | None) -> str | None:
            if not isinstance(row, Mapping):
                return None
            value = row.get("screenshot_path")
            if not isinstance(value, str):
                return None
            path = Path(value)
            if not path.is_file():
                return None
            return hashlib.sha256(path.read_bytes()).hexdigest()

        candidate_claimed_sha = (
            candidate.get("screenshot_sha256")
            if isinstance(candidate, Mapping)
            else None
        )
        reference_claimed_sha = (
            reference.get("screenshot_sha256")
            if isinstance(reference, Mapping)
            else None
        )
        candidate_sha = artifact_digest(candidate)
        reference_sha = artifact_digest(reference)
        checks[arm] = {
            "candidate_reversal_action_type": candidate_reversal,
            "reference_reversal_action_type": reference_reversal,
            "paired_no_reversal": (
                candidate_reversal is None and reference_reversal is None
            ),
            "candidate_retry_present": candidate is not None,
            "reference_retry_present": reference is not None,
            "candidate_retry_path": (
                candidate.get("screenshot_path")
                if isinstance(candidate, Mapping)
                else None
            ),
            "reference_retry_path": (
                reference.get("screenshot_path")
                if isinstance(reference, Mapping)
                else None
            ),
            "candidate_retry_sha256": candidate_sha,
            "reference_retry_sha256": reference_sha,
            "candidate_step_sha256": candidate_claimed_sha,
            "reference_step_sha256": reference_claimed_sha,
            "candidate_step_digest_matches_artifact": bool(
                candidate_sha and candidate_sha == candidate_claimed_sha
            ),
            "reference_step_digest_matches_artifact": bool(
                reference_sha and reference_sha == reference_claimed_sha
            ),
            "retry_pixel_identical": bool(
                isinstance(candidate_sha, str)
                and candidate_sha
                and isinstance(reference_sha, str)
                and reference_sha
                and candidate_sha == reference_sha
            ),
        }
    return checks


def retry_current_check_reasons(checks: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for arm in ("official", "clean"):
        row = checks.get(arm)
        if not isinstance(row, Mapping):
            reasons.append(f"missing_retry_pair_check:{arm}")
            continue
        if row.get("paired_no_reversal") is True:
            if row.get("candidate_retry_present") or row.get("reference_retry_present"):
                reasons.append(f"retry_frame_without_reversal:{arm}")
            continue
        if row.get("candidate_retry_present") is not True:
            reasons.append(f"missing_native4_retry_frame:{arm}")
        if row.get("reference_retry_present") is not True:
            reasons.append(f"missing_current_only_retry_frame:{arm}")
        if row.get("candidate_step_digest_matches_artifact") is not True:
            reasons.append(f"native4_retry_digest_mismatch:{arm}")
        if row.get("reference_step_digest_matches_artifact") is not True:
            reasons.append(f"current_only_retry_digest_mismatch:{arm}")
        if row.get("retry_pixel_identical") is not True:
            reasons.append(f"retry_frame_pixel_mismatch:{arm}")
    return reasons


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", default="smoke17")
    parser.add_argument("--slug", default="env008")
    parser.add_argument(
        "--evidence-level",
        choices=(
            F0_NEUTRAL_RECHECK,
            F1_CHECKLIST,
            F2_AUDITED_VALUES,
            F3_OUTCOME_CONTRADICTION,
            F3_PRE_REATTEMPT_CONTRADICTION,
        ),
        required=True,
    )
    parser.add_argument("--layout-id", choices=LAYOUT_IDS, default=LAYOUT_ID)
    parser.add_argument(
        "--asset-variant-manifest",
        type=Path,
        help="bind a validated, separately identified chart asset variant",
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--f2-trigger-summary",
        type=Path,
        help="complete L2 interleaved summary required before an F2 diagnostic run",
    )
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--agent-url")
    parser.add_argument("--official-repo", type=Path, default=EXPECTED_OFFICIAL_REPO)
    parser.add_argument("--model-path", type=Path, default=EXPECTED_MODEL_PATH)
    parser.add_argument(
        "--agent-python", default="/tmp/gui-reflection-model-env/bin/python"
    )
    parser.add_argument("--agent-port", type=int, default=38093)
    parser.add_argument("--agent-startup-timeout", type=float, default=900.0)
    parser.add_argument("--agent-request-timeout", type=float, default=300.0)
    parser.add_argument(
        "--browser-backend",
        choices=("playwright", "selenium-firefox"),
        default="selenium-firefox",
    )
    parser.add_argument("--browser-executable")
    parser.add_argument(
        "--firefox-binary",
        default="/tmp/gui-reflection-firefox/usr/lib/firefox/firefox",
    )
    parser.add_argument(
        "--geckodriver", default="/tmp/gui-reflection-firefox/usr/bin/geckodriver"
    )
    parser.add_argument(
        "--firefox-library-path",
        default=(
            "/tmp/gui-reflection-firefox/usr/lib/x86_64-linux-gnu:"
            "/tmp/gui-reflection-firefox/usr/lib/firefox"
        ),
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--action-wait-ms", type=int, default=700)
    parser.add_argument("--long-press-ms", type=int, default=800)
    args = parser.parse_args(argv)
    if args.max_steps <= 0:
        parser.error("--max-steps must be positive")
    return args


def validate_f2_trigger_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"F2 trigger summary does not exist: {path}")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("F2 trigger summary is not valid JSON") from exc
    if (
        not isinstance(summary, Mapping)
        or summary.get("record_type")
        != "env008_l2_f1_f3_pre_interleaved_panel"
        or summary.get("layout_id") != "cyclic_shift_2"
        or summary.get("execution_complete") is not True
    ):
        raise ValueError("F2 trigger requires a complete canonical L2 interleaved panel")
    blocks = summary.get("blocks")
    f1 = blocks.get(F1_CHECKLIST) if isinstance(blocks, Mapping) else None
    if not isinstance(f1, Mapping) or f1.get("execution_complete") is not True:
        raise ValueError("F2 trigger requires a complete F1 block")
    cell_results = f1.get("cell_results")
    if not isinstance(cell_results, Mapping) or set(cell_results) != {
        "candidate_official",
        "reference_official",
        "candidate_clean",
        "reference_clean",
    }:
        raise ValueError("F2 trigger F1 block is not a complete quartet")
    premise_failures: list[str] = []
    for key, result in cell_results.items():
        analysis = result.get("analysis") if isinstance(result, Mapping) else None
        if not isinstance(analysis, Mapping):
            raise ValueError(f"F2 trigger cell {key} lacks structured analysis")
        if (
            analysis.get("reversal_action_type") not in {"PRESS_BACK", "REVISE_SELECTION"}
            or analysis.get("retry_role") != "correct"
        ):
            premise_failures.append(str(key))
    if not premise_failures:
        raise ValueError(
            "F2 is not triggered: every F1 cell reversed and selected Solar on retry"
        )
    return {
        "record_type": "env008_f2_trigger_decision",
        "triggered": True,
        "rule": "any complete F1 cell lacks effective reversal or first correct retry",
        "source_summary": str(path.resolve()),
        "source_panel_id": summary.get("panel_id"),
        "premise_failure_cells": premise_failures,
    }


def cell_order_for_block(
    *, layout_id: str, evidence_level: str
) -> tuple[tuple[str, str, str], ...]:
    base = (
        ("candidate_official", "official", NATIVE4_CONDITION),
        ("reference_official", "official", CURRENT_ONLY_CONDITION),
        ("reference_clean", "clean", CURRENT_ONLY_CONDITION),
        ("candidate_clean", "clean", NATIVE4_CONDITION),
    )
    evidence_rank = {
        F0_NEUTRAL_RECHECK: 0,
        F1_CHECKLIST: 1,
        F2_AUDITED_VALUES: 2,
        F3_OUTCOME_CONTRADICTION: 3,
        F3_PRE_REATTEMPT_CONTRADICTION: 3,
    }[evidence_level]
    return (
        tuple(reversed(base))
        if (layout_offset(layout_id) + evidence_rank) % 2
        else base
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.evidence_level == F2_AUDITED_VALUES and args.slug != "env008":
        raise SystemExit("the audited F2 value record is specific to env008")
    trigger_decision: dict[str, Any] | None = None
    if args.evidence_level == F2_AUDITED_VALUES:
        if args.f2_trigger_summary is None:
            raise SystemExit("F2 requires --f2-trigger-summary from the complete F1 panel")
        trigger_decision = validate_f2_trigger_summary(args.f2_trigger_summary)
        if args.layout_id != "cyclic_shift_2":
            raise SystemExit("phase-1 triggered F2 is restricted to cyclic_shift_2")
    elif args.f2_trigger_summary is not None:
        raise SystemExit("--f2-trigger-summary is valid only for F2")
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pilot_id = f"{run_stamp}_{uuid.uuid4().hex[:8]}"
    run_dir = (args.output_root / pilot_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    if args.official_repo.resolve() != EXPECTED_OFFICIAL_REPO:
        raise SystemExit("inherited pilot requires the audited official repository")
    if args.model_path.resolve() != EXPECTED_MODEL_PATH:
        raise SystemExit("inherited pilot requires the audited GUI-Reflection SFT")

    canonical_case = load_authoritative_case(task_set=args.task_set, slug=args.slug)
    case = derive_layout_case(canonical_case, args.layout_id)
    asset_variant_manifest: dict[str, Any] | None = None
    asset_variant_id: str | None = None
    if args.asset_variant_manifest is not None:
        manifest_path = args.asset_variant_manifest
        if not manifest_path.is_absolute():
            manifest_path = REPO_ROOT / manifest_path
        case, asset_variant_manifest = apply_asset_variant_case(
            case,
            manifest_path=manifest_path,
        )
        value = asset_variant_manifest.get("asset_variant_id")
        if not isinstance(value, str) or not value:
            raise SystemExit("asset variant manifest has no identity")
        asset_variant_id = value
    registry = build_registry(case, args.layout_id)
    scorer = CanonicalSubmissionScorer(
        task_set=args.task_set,
        slug=args.slug,
        layout_id=args.layout_id,
        asset_variant_id=asset_variant_id,
    )
    validator = (
        CanonicalOutcomeValidator(
            task_set=args.task_set,
            slug=args.slug,
            layout_id=args.layout_id,
            asset_variant_id=asset_variant_id,
        )
        if args.evidence_level
        in {F3_OUTCOME_CONTRADICTION, F3_PRE_REATTEMPT_CONTRADICTION}
        else None
    )
    trial_id = f"trial:{case['pair_group_id']}:{args.evidence_level}:{pilot_id}"
    write_json(run_dir / "canonical_case.json", canonical_case)
    write_json(run_dir / "derived_layout_case.json", case)
    write_json(run_dir / "conditions.json", condition_records(args.layout_id))
    if asset_variant_manifest is not None:
        write_json(run_dir / "asset_variant_manifest.json", asset_variant_manifest)
    if args.evidence_level == F2_AUDITED_VALUES:
        write_json(
            run_dir / "approved_f2_evidence.json",
            approved_f2_record(case, layout_id=args.layout_id),
        )
        write_json(run_dir / "f2_trigger_decision.json", trigger_decision)

    managed_agent: ManagedAgentServer | None = None
    try:
        if args.agent_url:
            client: AgentClient = HttpAgentClient(
                args.agent_url, args.agent_request_timeout
            )
        else:
            managed_agent = ManagedAgentServer(
                official_repo=args.official_repo,
                model_path=args.model_path,
                port=args.agent_port,
                log_path=run_dir / "model_server.log",
                python_executable=args.agent_python,
                temporal_len=4,
                startup_timeout_seconds=args.agent_startup_timeout,
                request_timeout_seconds=args.agent_request_timeout,
            )
            client = managed_agent.start()
        health = verify_agent_service(client)  # type: ignore[arg-type]
        verify_health(
            health, official_repo=args.official_repo, model_path=args.model_path
        )
        write_json(run_dir / "agent_health.json", health)
        browser_factory = build_browser_factory(args)
        cell_order = cell_order_for_block(
            layout_id=args.layout_id,
            evidence_level=args.evidence_level,
        )
        write_json(
            run_dir / "run_manifest.json",
            {
                "pilot_id": pilot_id,
                "trial_id": trial_id,
                "task_set": args.task_set,
                "slug": args.slug,
                "evidence_level": args.evidence_level,
                "f2_trigger_decision": trigger_decision,
                "recovery_branch": STANDARDIZED_MISTAKE,
                "layout_id": args.layout_id,
                "layout_algorithm": layout_algorithm(args.layout_id),
                "cell_order": [key for key, _arm, _condition in cell_order],
                "contrast_id": CONTRAST_ID,
                "contrast_axis": HISTORY_CONTRAST,
                "checkpoint_id": CHECKPOINT_ID,
                "temporal_len": 4,
                "renderer_build_id": RENDERER_BUILD_ID,
                "asset_variant_id": asset_variant_id,
                "asset_variant_scope": (
                    asset_variant_manifest.get("scope")
                    if asset_variant_manifest is not None
                    else None
                ),
                "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
                "max_steps": args.max_steps,
                "browser_backend": args.browser_backend,
                "evaluator_intervention": "real coordinate POST before agent reset",
            },
        )
        results: dict[str, dict[str, Any]] = {}
        quartet_cells: dict[str, dict[str, Any]] = {}
        for key, arm, condition in cell_order:
            run_id = f"run:{case['pair_group_id']}:{args.evidence_level}:{pilot_id}:{key}"
            base = base_fields_for_cell(
                case=case,
                trial_id=trial_id,
                run_id=run_id,
                arm=arm,
                condition=condition,
                evidence_level=args.evidence_level,
                layout_id=args.layout_id,
            )
            result = run_cell(
                case=case,
                registry=registry,
                base_fields=base,
                agent=client,
                scorer=scorer,
                browser_factory=browser_factory,
                cell_dir=run_dir / "cells" / key,
                max_steps=args.max_steps,
                outcome_validator=validator,
                layout_id=args.layout_id,
            )
            results[key] = result
            events = [
                json.loads(line)
                for line in Path(result["events_path"])
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            quartet_cells[key] = {"base_fields": base, "events": events}

        quartet_error: str | None = None
        quartet_record: dict[str, Any] | None = None
        try:
            quartet_record = analyze_recovery_quartet(
                quartet_cells, contrast_id=CONTRAST_ID, registry=registry
            ).to_dict()
        except Exception as exc:
            quartet_error = repr(exc)
        checks = cross_cell_checks(results)
        complete, completion_reasons = execution_complete(results, checks)
        retry_checks = retry_current_cross_cell_checks(results)
        retry_reasons = retry_current_check_reasons(retry_checks)
        intervention_reasons = validate_interventions(
            results,
            evidence_level=args.evidence_level,
            layout_id=args.layout_id,
        )
        completion_reasons.extend(retry_reasons)
        completion_reasons.extend(intervention_reasons)
        complete = complete and not retry_reasons and not intervention_reasons
        summary = {
            "pilot_id": pilot_id,
            "trial_id": trial_id,
            "pair_group_id": case["pair_group_id"],
            "evidence_level": args.evidence_level,
            "layout_id": args.layout_id,
            "asset_variant_id": asset_variant_id,
            "contrast": "native4 vs true current-only inference history",
            "cell_results": results,
            "cross_cell_checks": checks,
            "retry_current_cross_cell_checks": retry_checks,
            "retry_current_validation_reasons": retry_reasons,
            "intervention_validation_reasons": intervention_reasons,
            "execution_complete": complete,
            "execution_incomplete_reasons": completion_reasons,
            "quartet": quartet_record,
            "quartet_error": quartet_error,
            "interpretation_limits": [
                "the inherited misleading choice is evaluator-owned, not model initial behavior",
                "history contrast does not identify reflection-training causality",
                "feedback blocks are sequential diagnostic probes, not a causal ladder",
                "one case and one fixed layout per block are qualitative evidence",
                *(
                    [
                        "asset variant is a controlled diagnostic, not a canonical "
                        "benchmark release render"
                    ]
                    if asset_variant_manifest is not None
                    else []
                ),
            ],
        }
        write_json(run_dir / "summary.json", summary)
        print(str(run_dir))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if quartet_error is None and complete else 2
    except Exception as exc:
        write_json(run_dir / "fatal_error.json", {"timestamp": utc_now(), "error": repr(exc)})
        print(f"inherited recovery pilot failed: {exc}", file=sys.stderr)
        print(str(run_dir), file=sys.stderr)
        return 2
    finally:
        if managed_agent is not None:
            managed_agent.close()


if __name__ == "__main__":
    raise SystemExit(main())
