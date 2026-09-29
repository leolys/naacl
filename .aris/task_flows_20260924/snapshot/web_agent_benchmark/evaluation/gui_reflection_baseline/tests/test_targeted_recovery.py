from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from ..targeted_recovery import (
    AUTONOMOUS_EVIDENCE_PATH,
    CORRECT,
    DESCRIPTIVE_SYSTEM_CONTRAST,
    F0_NEUTRAL_RECHECK,
    F1_CHECKLIST,
    F2_AUDITED_VALUES,
    F3_OUTCOME_CONTRADICTION,
    F3_PRE_REATTEMPT_CONTRADICTION,
    EVIDENCE_REVIEW_REGIMES,
    HISTORY_CONTRAST,
    MISLEADING,
    NEUTRAL,
    NO_CHOICE,
    REFLECTION_TRAINING_CONTRAST,
    REPLICATION_CONTRAST,
    STANDARDIZED_MISTAKE,
    TraceReductionError,
    TargetedRecoveryRegistry,
    WORKFLOW_CONTRAST,
    UNKNOWN,
    RecoveryRun,
    analyze_run as analyze_event_trace,
    analyze_recovery_quartet,
    analyze_summary,
    classify_summary_for_testing,
    classify_summary_pair_for_testing,
    choice_role,
    compare_runs as compare_event_traces,
    compare_summaries,
    derive_run_from_events,
    validate_case_ladder,
)


_TEST_SCREENSHOT_DIRECTORY = tempfile.TemporaryDirectory()


def test_png_path(name):
    path = Path(_TEST_SCREENSHOT_DIRECTORY.name) / name
    if not path.exists():
        path.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        )
    return str(path)


def png_chunk(chunk_type, payload):
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def recovery_run(**overrides):
    values = {
        "run_id": "run:pair008:official:sft_t4_stateful",
        "trial_id": "trial:pair008:rep0",
        "pair_group_id": "pair:008",
        "condition": "sft_t4_stateful",
        "arm": "official",
        "task_id": "task:pair008:official",
        "task_instance_id": "task-instance:pair008:official",
        "chart_path": "targeted_recovery.py",
        "display_tokens": ("choice_0", "choice_1", "choice_2"),
        "choice_token_to_action_id": (
            ("choice_0", "wind"),
            ("choice_1", "hydro"),
            ("choice_2", "solar"),
        ),
        "correct_action_id": "solar",
        "misleading_action_ids": ("wind",),
        "checkpoint_id": "craigwu/gui-reflection-8b-sft",
        "checkpoint_stage": "sft",
        "reflection_training_status": "gui_reflection_sft",
        "history_mode": "native4",
        "workflow_mode": "feedback_retry",
        "renderer_build_id": "test-renderer-v1",
        "viewport_width": 1,
        "viewport_height": 1,
        "neutral_action_ids": ("hydro",),
        "evidence_level": "F0_neutral_recheck",
        "retry_presentation": "current_visible_retry",
        "ui_variant": "compact_recovery",
        "display_order": ("wind", "hydro", "solar"),
        "initial_selected_action_id": "wind",
        "feedback_observed": True,
        "contradiction_recognized": True,
        "actual_reversal_action_type": "PRESS_BACK",
        "reversal_returned_to_retry": True,
        "post_review_selected_action_ids": ("solar",),
        "final_review_observed": True,
        "final_selected_action_id": "solar",
        "final_submission_observed": True,
        "submission_id": "submission:1",
        "scorer_result_observed": True,
        "scorer_record_id": "scorer:1",
        "final_submission_success": True,
    }
    values.update(overrides)
    if "task_id" not in overrides:
        values["task_id"] = f"task:pair008:{values['arm']}"
    if "task_instance_id" not in overrides:
        values["task_instance_id"] = f"task-instance:pair008:{values['arm']}"
    if "review_regime" not in overrides:
        values["review_regime"] = (
            "not_applicable"
            if values["workflow_mode"] == "single_attempt"
            else EVIDENCE_REVIEW_REGIMES.get(
                values["evidence_level"], "neutral_recheck"
            )
        )
    if values["final_submission_observed"] is False:
        if "submission_id" not in overrides:
            values["submission_id"] = None
        if "scorer_result_observed" not in overrides:
            values["scorer_result_observed"] = False
        if "scorer_record_id" not in overrides:
            values["scorer_record_id"] = None
    if values["final_submission_success"] is None:
        if "scorer_result_observed" not in overrides:
            values["scorer_result_observed"] = False
        if "scorer_record_id" not in overrides:
            values["scorer_record_id"] = None
    if "run_id" not in overrides:
        values["run_id"] = (
            f"run:pair008:{values['arm']}:{values['condition']}"
        )
    return RecoveryRun(**values)


def recovery_base(**overrides):
    values = {
        "run_id": "run:pair008:official:sft_t4_stateful",
        "trial_id": "trial:pair008:rep0",
        "pair_group_id": "pair:008",
        "condition": "sft_t4_stateful",
        "arm": "official",
        "task_id": "task:pair008:official",
        "task_instance_id": "task-instance:pair008:official",
        "chart_path": "targeted_recovery.py",
        "display_tokens": ("choice_0", "choice_1", "choice_2"),
        "choice_token_to_action_id": (
            ("choice_0", "wind"),
            ("choice_1", "hydro"),
            ("choice_2", "solar"),
        ),
        "correct_action_id": "solar",
        "misleading_action_ids": ("wind",),
        "checkpoint_id": "craigwu/gui-reflection-8b-sft",
        "checkpoint_stage": "sft",
        "reflection_training_status": "gui_reflection_sft",
        "history_mode": "native4",
        "workflow_mode": "feedback_retry",
        "renderer_build_id": "test-renderer-v1",
        "viewport_width": 1,
        "viewport_height": 1,
        "neutral_action_ids": ("hydro",),
        "evidence_level": "F0_neutral_recheck",
        "retry_presentation": "current_visible_retry",
        "ui_variant": "compact_recovery",
        "display_order": ("wind", "hydro", "solar"),
    }
    values.update(overrides)
    if "task_id" not in overrides:
        values["task_id"] = f"task:pair008:{values['arm']}"
    if "task_instance_id" not in overrides:
        values["task_instance_id"] = f"task-instance:pair008:{values['arm']}"
    if "review_regime" not in overrides:
        values["review_regime"] = (
            "not_applicable"
            if values["workflow_mode"] == "single_attempt"
            else EVIDENCE_REVIEW_REGIMES.get(
                values["evidence_level"], "neutral_recheck"
            )
        )
    if "run_id" not in overrides:
        values["run_id"] = (
            f"run:pair008:{values['arm']}:{values['condition']}"
        )
    return values


def runner_event(event_index, event_type, **fields):
    action_to_control = {
        "wind": ("choice_0", 0),
        "hydro": ("choice_1", 1),
        "solar": ("choice_2", 2),
    }
    if event_type == "ui_selection":
        action_id = fields.get("action_id")
        token, position = action_to_control.get(action_id, ("choice_unknown", 99))
        fields.setdefault("choice_token", token)
        fields.setdefault("control_position", position)
        is_initial = event_index == 0
        fields.setdefault(
            "decision_state", "initial_decision" if is_initial else "retry_decision"
        )
        fields.setdefault(
            "input_artifact_path", test_png_path(f"input-{event_index}.png")
        )
        fields.setdefault("input_model_step_id", f"input-model-step-{event_index}")
        fields.setdefault("rendered_task_instance_id", "task-instance:pair008:official")
        fields.setdefault("rendered_chart_path", "targeted_recovery.py")
        fields.setdefault("rendered_ui_variant", "compact_recovery")
        fields.setdefault(
            "rendered_retry_presentation",
            None if is_initial else "current_visible_retry",
        )
        fields.setdefault(
            "rendered_feedback_spec_id", None if is_initial else F0_NEUTRAL_RECHECK
        )
        fields.setdefault("rendered_evidence_record_id", None)
        fields.setdefault("rendered_outcome_record_id", None)
        fields.setdefault("rendered_outcome_contradiction", None)
        if is_initial:
            fields.setdefault("rendered_provisional_action_id", None)
            fields.setdefault("rendered_provisional_choice_token", None)
            fields.setdefault("rendered_provisional_control_position", None)
        else:
            prior_action = "hydro" if event_index == 4 else "wind"
            prior_token, prior_position = action_to_control[prior_action]
            fields.setdefault("rendered_provisional_action_id", prior_action)
            fields.setdefault("rendered_provisional_choice_token", prior_token)
            fields.setdefault("rendered_provisional_control_position", prior_position)
        fields.setdefault("rendered_display_tokens", ["choice_0", "choice_1", "choice_2"])
        fields.setdefault("renderer_build_id", "test-renderer-v1")
        fields.setdefault("viewport_width", 1)
        fields.setdefault("viewport_height", 1)
        fields.setdefault("model_response_id", f"model-response-{event_index}")
        fields.setdefault("execution_receipt_id", f"execution-{event_index}")
        fields.setdefault("caused_by_model_step_id", fields["input_model_step_id"])
    if event_type == "screenshot_observation":
        fields.setdefault("model_step_id", f"model-step-{event_index}")
        fields.setdefault("feedback_spec_id", F0_NEUTRAL_RECHECK)
        fields.setdefault("rendered_evidence_record_id", None)
        fields.setdefault("rendered_outcome_record_id", None)
        fields.setdefault("rendered_outcome_contradiction", None)
        provisional_action = (
            "solar" if fields.get("observed_state") == "final_review" else "wind"
        )
        provisional_token, provisional_position = action_to_control[provisional_action]
        fields.setdefault("rendered_provisional_action_id", provisional_action)
        fields.setdefault("rendered_provisional_choice_token", provisional_token)
        fields.setdefault("rendered_provisional_control_position", provisional_position)
        fields.setdefault("rendered_task_instance_id", "task-instance:pair008:official")
        fields.setdefault("rendered_chart_path", "targeted_recovery.py")
        fields.setdefault("rendered_ui_variant", "compact_recovery")
        fields.setdefault("renderer_build_id", "test-renderer-v1")
        fields.setdefault("viewport_width", 1)
        fields.setdefault("viewport_height", 1)
        if fields.get("artifact_path") in {"review.png", "final.png"}:
            fields["artifact_path"] = test_png_path(fields["artifact_path"])
    if event_type == "ui_reversal":
        fields.setdefault("model_response_id", f"model-response-{event_index}")
        fields.setdefault("execution_receipt_id", f"execution-{event_index}")
        fields.setdefault("caused_by_model_step_id", f"model-step-{event_index - 1}")
    if event_type == "outcome_validation":
        provisional_action = fields.get("provisional_action_id")
        token, position = action_to_control.get(
            provisional_action, ("choice_unknown", 99)
        )
        fields.setdefault("provisional_choice_token", token)
        fields.setdefault("provisional_control_position", position)
    if event_type == "submission":
        action_id = fields.get("submitted_action_id")
        token, position = action_to_control.get(action_id, ("choice_unknown", 99))
        fields.setdefault("submitted_choice_token", token)
        fields.setdefault("submitted_control_position", position)
        fields.setdefault("model_response_id", f"model-response-{event_index}")
        fields.setdefault("execution_receipt_id", f"execution-{event_index}")
        fields.setdefault(
            "caused_by_model_step_id",
            "input-model-step-0" if event_index == 1 else f"model-step-{event_index - 1}",
        )
    return {
        "event_index": event_index,
        "event_type": event_type,
        "source": (
            "model"
            if event_type in {"model_thought", "model_message", "natural_language"}
            else "scorer"
            if event_type == "scorer_result"
            else "validator"
            if event_type == "outcome_validation"
            else "runner"
        ),
        "run_id": "run:pair008:official:sft_t4_stateful",
        "trial_id": "trial:pair008:rep0",
        "pair_group_id": "pair:008",
        "task_instance_id": "task-instance:pair008:official",
        "arm": "official",
        "condition": "sft_t4_stateful",
        **fields,
    }


def protocol_registry(
    *,
    approved_evidence_records=(),
    extra_conditions=(),
    extra_contrasts=(),
):
    baseline_root = Path(__file__).resolve().parents[1]
    condition_values = {
        "checkpoint_id": "craigwu/gui-reflection-8b-sft",
        "checkpoint_stage": "sft",
        "reflection_training_status": "gui_reflection_sft",
        "history_mode": "native4",
        "workflow_mode": "feedback_retry",
        "renderer_build_id": "test-renderer-v1",
        "viewport_width": 1,
        "viewport_height": 1,
        "ui_variant": "compact_recovery",
    }
    conditions = [
        {"condition_id": condition, **condition_values}
        for condition in ("sft_t4_stateful", "candidate", "reference")
    ]
    conditions.extend({**condition_values, **condition} for condition in extra_conditions)
    contrasts = [
        {
            "contrast_id": "contrast:replication:candidate-v-reference",
            "contrast_axis": REPLICATION_CONTRAST,
            "candidate_condition": "candidate",
            "reference_condition": "reference",
        }
    ]
    contrasts.extend(extra_contrasts)
    case = {
        "record_type": "targeted_recovery_case",
        "pair_group_id": "pair:008",
        "model_visible_shared": {
            "workflow_instruction": "Choose the largest increase.",
            "action_cards": [
                {"choice_token": "choice_0", "label": "Wind"},
                {"choice_token": "choice_1", "label": "Hydro"},
                {"choice_token": "choice_2", "label": "Solar"},
            ],
        },
        "arms": {
            "official": {
                "task_id": "task:pair008:official",
                "task_instance_id": "task-instance:pair008:official",
                "chart_path": "targeted_recovery.py",
            },
            "clean": {
                "task_id": "task:pair008:clean",
                "task_instance_id": "task-instance:pair008:clean",
                "chart_path": "targeted_recovery.py",
            },
        },
        "source_references": {
            "official": {"path": "targeted_recovery.py", "line": 1},
            "clean": {"path": "targeted_recovery.py", "line": 1},
        },
        "runner_only": {
            "expected_action_id": "solar",
            "misleading_action_ids": ["wind"],
            "neutral_action_ids": ["hydro"],
            "display_order": ["wind", "hydro", "solar"],
            "choice_token_to_action_id": {
                "choice_0": "wind",
                "choice_1": "hydro",
                "choice_2": "solar",
            },
        },
    }
    return TargetedRecoveryRegistry(
        repository_root=baseline_root,
        cases=[case],
        conditions=conditions,
        contrasts=contrasts,
        approved_evidence_records=approved_evidence_records,
    )


def approved_f2_record(**overrides):
    values = {
        "record_id": "evidence:pair008:f2:v1",
        "pair_group_id": "pair:008",
        "evidence_level": F2_AUDITED_VALUES,
        "source_refs": [
            {
                "arm": "official",
                "artifact_path": "targeted_recovery.py",
                "record_locator": "line:1",
            },
            {
                "arm": "clean",
                "artifact_path": "targeted_recovery.py",
                "record_locator": "line:1",
            },
        ],
        "review_status": "approved",
        "reviewed_by": "reviewer_a",
        "reviewed_at": "2026-08-30",
        "model_visible_payload": {
            "heading": "Audited values",
            "facts": [
                {"subject": "Solar", "relation": "value", "object": "8"},
                {"subject": "Wind", "relation": "value", "object": "3"},
                {"subject": "Hydro", "relation": "value", "object": "5"},
            ],
        },
    }
    values.update(overrides)
    return values


def stable_recovery_events(base_fields, prefix):
    identity = {
        field: base_fields[field]
        for field in (
            "run_id",
            "trial_id",
            "pair_group_id",
            "task_instance_id",
            "arm",
            "condition",
        )
    }
    submission_id = f"submission:{prefix}"
    events = []

    def add(event_type, **fields):
        event_index = len(events)
        events.append(runner_event(event_index, event_type, **fields, **identity))

    render_identity = {
        "rendered_task_instance_id": base_fields["task_instance_id"],
        "rendered_chart_path": base_fields["chart_path"],
        "rendered_ui_variant": base_fields.get("ui_variant", "compact_recovery"),
        "renderer_build_id": base_fields["renderer_build_id"],
        "viewport_width": base_fields["viewport_width"],
        "viewport_height": base_fields["viewport_height"],
    }
    add(
        "ui_selection",
        action_id="wind",
        input_artifact_path=test_png_path(f"{prefix}-initial-input.png"),
        input_model_step_id=f"{prefix}:initial-input-step",
        rendered_display_tokens=list(base_fields["display_tokens"]),
        rendered_retry_presentation=None,
        rendered_feedback_spec_id=None,
        model_response_id=f"{prefix}:response-initial-selection",
        execution_receipt_id=f"{prefix}:execution-initial-selection",
        caused_by_model_step_id=f"{prefix}:initial-input-step",
        **render_identity,
    )
    if base_fields["evidence_level"] in {
        F3_OUTCOME_CONTRADICTION,
        F3_PRE_REATTEMPT_CONTRADICTION,
    }:
        add(
            "outcome_validation",
            provisional_action_id="wind",
            outcome_record_id=f"outcome:{prefix}:initial",
            contradiction=True,
        )
    add(
        "screenshot_observation",
        observed_state="review",
        artifact_path=test_png_path(f"{prefix}-review.png"),
        model_step_id=f"{prefix}:model-step-review",
        feedback_spec_id=base_fields["evidence_level"],
        rendered_evidence_record_id=base_fields.get("evidence_record_id"),
        rendered_outcome_record_id=(
            f"outcome:{prefix}:initial"
            if base_fields["evidence_level"]
            in {F3_OUTCOME_CONTRADICTION, F3_PRE_REATTEMPT_CONTRADICTION}
            else None
        ),
        rendered_outcome_contradiction=(
            True
            if base_fields["evidence_level"]
            in {F3_OUTCOME_CONTRADICTION, F3_PRE_REATTEMPT_CONTRADICTION}
            else None
        ),
        **render_identity,
    )
    add(
        "ui_reversal",
        action_type="PRESS_BACK",
        from_state="review",
        to_state="retry_decision",
        model_response_id=f"{prefix}:response-reversal",
        execution_receipt_id=f"{prefix}:execution-reversal",
        caused_by_model_step_id=f"{prefix}:model-step-review",
    )
    add(
        "ui_selection",
        action_id="solar",
        decision_state="retry_decision",
        input_artifact_path=test_png_path(f"{prefix}-retry-input.png"),
        input_model_step_id=f"{prefix}:retry-input-step",
        rendered_display_tokens=list(base_fields["display_tokens"]),
        rendered_retry_presentation=base_fields.get(
            "retry_presentation", "current_visible_retry"
        ),
        rendered_feedback_spec_id=(
            base_fields["evidence_level"]
            if base_fields.get("retry_presentation", "current_visible_retry")
            == "current_visible_retry"
            else None
        ),
        rendered_evidence_record_id=(
            base_fields.get("evidence_record_id")
            if base_fields.get("retry_presentation", "current_visible_retry")
            == "current_visible_retry"
            and base_fields["evidence_level"] == F2_AUDITED_VALUES
            else None
        ),
        rendered_outcome_record_id=(
            f"outcome:{prefix}:initial"
            if base_fields.get("retry_presentation", "current_visible_retry")
            == "current_visible_retry"
            and base_fields["evidence_level"]
            in {F3_OUTCOME_CONTRADICTION, F3_PRE_REATTEMPT_CONTRADICTION}
            else None
        ),
        rendered_outcome_contradiction=(
            True
            if base_fields.get("retry_presentation", "current_visible_retry")
            == "current_visible_retry"
            and base_fields["evidence_level"]
            in {F3_OUTCOME_CONTRADICTION, F3_PRE_REATTEMPT_CONTRADICTION}
            else None
        ),
        rendered_provisional_action_id="wind",
        rendered_provisional_choice_token="choice_0",
        rendered_provisional_control_position=0,
        model_response_id=f"{prefix}:response-retry-selection",
        execution_receipt_id=f"{prefix}:execution-retry-selection",
        caused_by_model_step_id=f"{prefix}:retry-input-step",
        **render_identity,
    )
    if base_fields["evidence_level"] == F3_OUTCOME_CONTRADICTION:
        add(
            "outcome_validation",
            provisional_action_id="solar",
            outcome_record_id=f"outcome:{prefix}:retry",
            contradiction=False,
        )
    add(
        "screenshot_observation",
        observed_state="final_review",
        artifact_path=test_png_path(f"{prefix}-final.png"),
        model_step_id=f"{prefix}:model-step-final-review",
        feedback_spec_id=base_fields["evidence_level"],
        rendered_evidence_record_id=base_fields.get("evidence_record_id"),
        rendered_outcome_record_id=(
            f"outcome:{prefix}:retry"
            if base_fields["evidence_level"] == F3_OUTCOME_CONTRADICTION
            else None
        ),
        rendered_outcome_contradiction=(
            False if base_fields["evidence_level"] == F3_OUTCOME_CONTRADICTION else None
        ),
        **render_identity,
    )
    add(
        "submission",
        submitted_action_id="solar",
        submission_id=submission_id,
        model_response_id=f"{prefix}:response-submission",
        execution_receipt_id=f"{prefix}:execution-submission",
        caused_by_model_step_id=f"{prefix}:model-step-final-review",
    )
    add(
        "scorer_result",
        submission_id=submission_id,
        scorer_record_id=f"scorer:{prefix}",
        success=True,
    )
    return events


def single_attempt_events(base_fields, prefix):
    identity = {
        field: base_fields[field]
        for field in (
            "run_id",
            "trial_id",
            "pair_group_id",
            "task_instance_id",
            "arm",
            "condition",
        )
    }
    submission_id = f"submission:{prefix}"
    return [
        runner_event(
            0,
            "ui_selection",
            action_id="wind",
            input_artifact_path=test_png_path(f"{prefix}-initial-input.png"),
            input_model_step_id=f"{prefix}:initial-input-step",
            rendered_task_instance_id=base_fields["task_instance_id"],
            rendered_chart_path=base_fields["chart_path"],
            rendered_ui_variant=base_fields.get("ui_variant", "compact_recovery"),
            rendered_display_tokens=list(base_fields["display_tokens"]),
            renderer_build_id=base_fields["renderer_build_id"],
            viewport_width=base_fields["viewport_width"],
            viewport_height=base_fields["viewport_height"],
            model_response_id=f"{prefix}:response-initial-selection",
            execution_receipt_id=f"{prefix}:execution-initial-selection",
            caused_by_model_step_id=f"{prefix}:initial-input-step",
            **identity,
        ),
        runner_event(
            1,
            "submission",
            submitted_action_id="wind",
            submission_id=submission_id,
            model_response_id=f"{prefix}:response-initial-selection",
            execution_receipt_id=f"{prefix}:execution-initial-selection",
            caused_by_model_step_id=f"{prefix}:initial-input-step",
            **identity,
        ),
        runner_event(
            2,
            "scorer_result",
            submission_id=submission_id,
            scorer_record_id=f"scorer:{prefix}",
            success=False,
            **identity,
        ),
    ]


def quartet_cells(*, evidence_level=F0_NEUTRAL_RECHECK, evidence_record_id=None):
    cells = {}
    for role, condition in (("candidate", "candidate"), ("reference", "reference")):
        for arm in ("official", "clean"):
            key = f"{role}_{arm}"
            base = recovery_base(
                run_id=f"run:pair008:{key}:{evidence_level}",
                arm=arm,
                condition=condition,
                evidence_level=evidence_level,
                evidence_record_id=evidence_record_id,
            )
            cells[key] = {
                "base_fields": base,
                "events": stable_recovery_events(base, f"{key}-{evidence_level}"),
            }
    return cells


def analyze_run(run):
    """Exercise pure summary classification without claiming reportability."""

    return classify_summary_for_testing(run)


def compare_runs(candidate, reference, *, contrast_axis=REPLICATION_CONTRAST):
    """Exercise unverified comparison logic in unit tests."""

    return classify_summary_pair_for_testing(
        candidate, reference, contrast_axis=contrast_axis
    )


class EventTraceReducerTests(unittest.TestCase):
    def test_real_trace_derives_stable_recovery(self) -> None:
        events = [
            runner_event(0, "ui_selection", action_id="wind"),
            runner_event(
                1,
                "screenshot_observation",
                observed_state="review",
                artifact_path="review.png",
            ),
            runner_event(
                2,
                "ui_reversal",
                action_type="PRESS_BACK",
                from_state="review",
                to_state="retry_decision",
            ),
            runner_event(3, "ui_selection", action_id="solar"),
            runner_event(
                4,
                "screenshot_observation",
                observed_state="final_review",
                artifact_path="final.png",
            ),
            runner_event(
                5,
                "submission",
                submitted_action_id="solar",
                submission_id="submission:1",
            ),
            runner_event(
                6,
                "scorer_result",
                submission_id="submission:1",
                scorer_record_id="scorer:1",
                success=True,
            ),
        ]

        run = derive_run_from_events(recovery_base(), events)

        self.assertEqual(run.initial_selected_action_id, "wind")
        self.assertTrue(run.feedback_observed)
        self.assertEqual(run.actual_reversal_action_type, "PRESS_BACK")
        self.assertEqual(run.reversal_from_state, "review")
        self.assertEqual(run.reversal_to_state, "retry_decision")
        self.assertTrue(run.reversal_returned_to_retry)
        self.assertEqual(run.post_review_selected_action_ids, ("solar",))
        self.assertTrue(run.final_review_observed)
        self.assertEqual(run.final_selected_action_id, "solar")
        self.assertTrue(run.final_submission_observed)
        self.assertEqual(run.submission_id, "submission:1")
        self.assertTrue(run.scorer_result_observed)
        self.assertEqual(run.scorer_record_id, "scorer:1")
        self.assertTrue(run.final_submission_success)
        self.assertTrue(run.event_trace_reduced)
        self.assertEqual(run.trace_event_count, 7)
        self.assertEqual(run.trace_last_event_index, 6)
        self.assertEqual(
            run.observed_artifact_paths,
            (
                test_png_path("input-0.png"),
                test_png_path("review.png"),
                test_png_path("input-3.png"),
                test_png_path("final.png"),
            ),
        )
        self.assertEqual(
            run.observed_model_step_ids,
            (
                "input-model-step-0",
                "model-step-1",
                "input-model-step-3",
                "model-step-4",
            ),
        )
        summary_analysis = analyze_run(run)
        self.assertFalse(summary_analysis.event_trace_replayed)
        self.assertEqual(summary_analysis.trajectory_label, "stable_recovery")
        reportable_analysis = analyze_event_trace(
            recovery_base(), events, registry=protocol_registry()
        )
        self.assertTrue(reportable_analysis.event_trace_replayed)
        self.assertFalse(reportable_analysis.reportable)
        self.assertEqual(reportable_analysis.trajectory_label, "stable_recovery")

    def test_model_thought_cannot_fabricate_feedback(self) -> None:
        events = [
            runner_event(0, "ui_selection", action_id="wind"),
            runner_event(
                1,
                "model_thought",
                text="I saw the review and pressed Back",
            ),
        ]

        run = derive_run_from_events(recovery_base(), events)

        self.assertFalse(run.feedback_observed)
        self.assertIsNone(run.actual_reversal_action_type)
        self.assertEqual(run.post_review_selected_action_ids, ())
        self.assertEqual(run.observed_artifact_paths, (test_png_path("input-0.png"),))
        self.assertEqual(analyze_run(run).trajectory_label, "review_not_observed")

    def test_model_event_cannot_smuggle_structural_fields(self) -> None:
        event = runner_event(
            0,
            "model_thought",
            text="I selected Solar",
        )
        event["action_id"] = "solar"
        with self.assertRaisesRegex(TraceReductionError, "unknown=.*action_id"):
            derive_run_from_events(recovery_base(), [event])

    def test_screenshot_observation_without_artifact_fails_closed(self) -> None:
        events = [
            runner_event(0, "ui_selection", action_id="wind"),
            runner_event(
                1,
                "screenshot_observation",
                observed_state="review",
                artifact_path="missing.png",
            ),
        ]

        with self.assertRaisesRegex(TraceReductionError, "valid PNG"):
            derive_run_from_events(recovery_base(), events)

    def test_existing_non_png_and_reused_screenshot_are_rejected(self) -> None:
        source_file = str(Path(__file__).resolve().parents[1] / "targeted_recovery.py")
        with self.assertRaisesRegex(TraceReductionError, "valid PNG"):
            derive_run_from_events(
                recovery_base(),
                [
                    runner_event(0, "ui_selection", action_id="wind"),
                    runner_event(
                        1,
                        "screenshot_observation",
                        observed_state="review",
                        artifact_path=source_file,
                    ),
                ],
            )

        same_png = test_png_path("same-review.png")
        events = [
            runner_event(0, "ui_selection", action_id="wind"),
            runner_event(
                1,
                "screenshot_observation",
                observed_state="review",
                artifact_path=same_png,
            ),
            runner_event(
                2,
                "ui_reversal",
                action_type="PRESS_BACK",
                from_state="review",
                to_state="retry_decision",
            ),
            runner_event(3, "ui_selection", action_id="solar"),
            runner_event(
                4,
                "screenshot_observation",
                observed_state="final_review",
                artifact_path=same_png,
            ),
        ]
        with self.assertRaisesRegex(TraceReductionError, "reuses screenshot"):
            derive_run_from_events(recovery_base(), events)

    def test_crc_valid_png_with_undecodable_pixels_is_rejected(self) -> None:
        bad_png = Path(_TEST_SCREENSHOT_DIRECTORY.name) / "bad-idat.png"
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
        bad_png.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"IDAT", b"not-zlib-data")
            + png_chunk(b"IEND", b"")
        )
        with self.assertRaisesRegex(TraceReductionError, "valid PNG"):
            derive_run_from_events(
                recovery_base(),
                [
                    runner_event(0, "ui_selection", action_id="wind"),
                    runner_event(
                        1,
                        "screenshot_observation",
                        observed_state="review",
                        artifact_path=str(bad_png),
                    ),
                ],
            )

    def test_event_identity_prevents_cross_run_replay(self) -> None:
        event = runner_event(0, "ui_selection", action_id="wind")
        event["pair_group_id"] = "pair:other"
        with self.assertRaisesRegex(TraceReductionError, "does not match run identity"):
            derive_run_from_events(recovery_base(), [event])

    def test_untrusted_structural_event_cannot_count_as_feedback(self) -> None:
        untrusted = runner_event(
            1,
            "screenshot_observation",
            observed_state="review",
            artifact_path="review.png",
        )
        untrusted["source"] = "model"
        events = [runner_event(0, "ui_selection", action_id="wind"), untrusted]

        with self.assertRaisesRegex(TraceReductionError, "source is not"):
            derive_run_from_events(recovery_base(), events)

    def test_submission_cannot_self_report_success(self) -> None:
        event = runner_event(
            0,
            "submission",
            submitted_action_id="solar",
            submission_id="submission:self-scored",
        )
        event["success"] = True
        with self.assertRaisesRegex(TraceReductionError, "unknown=.*success"):
            derive_run_from_events(recovery_base(), [event])

    def test_unscored_submission_remains_unscored(self) -> None:
        events = [
            runner_event(0, "ui_selection", action_id="wind"),
            runner_event(
                1,
                "screenshot_observation",
                observed_state="review",
                artifact_path="review.png",
            ),
            runner_event(
                2,
                "ui_reversal",
                action_type="PRESS_BACK",
                from_state="review",
                to_state="retry_decision",
            ),
            runner_event(3, "ui_selection", action_id="solar"),
            runner_event(
                4,
                "screenshot_observation",
                observed_state="final_review",
                artifact_path="final.png",
            ),
            runner_event(
                5,
                "submission",
                submitted_action_id="solar",
                submission_id="submission:unscored",
            ),
        ]

        run = derive_run_from_events(recovery_base(), events)
        analysis = analyze_event_trace(
            recovery_base(), events, registry=protocol_registry()
        )

        self.assertTrue(run.final_submission_observed)
        self.assertFalse(run.scorer_result_observed)
        self.assertIsNone(run.final_submission_success)
        self.assertIsNone(analysis.full_recovery)
        self.assertEqual(
            analysis.trajectory_label, "corrected_but_submission_unscored"
        )

    def test_scorer_result_requires_external_source_and_matching_submission(self) -> None:
        base = recovery_base(
            workflow_mode="single_attempt",
            evidence_level=None,
        )
        wrong_source_events = single_attempt_events(base, "wrong-scorer-source")
        wrong_source = wrong_source_events[-1]
        wrong_source["source"] = "runner"
        with self.assertRaisesRegex(TraceReductionError, "source is not 'scorer'"):
            derive_run_from_events(base, wrong_source_events)

        mismatch_events = single_attempt_events(base, "mismatched-scorer")
        mismatch_events[-1]["submission_id"] = "submission:other"
        with self.assertRaisesRegex(TraceReductionError, "does not match"):
            derive_run_from_events(base, mismatch_events)

    def test_scorer_result_cannot_precede_submission_or_omit_boolean(self) -> None:
        with self.assertRaisesRegex(TraceReductionError, "precedes submission"):
            derive_run_from_events(
                recovery_base(),
                [
                    runner_event(
                        0,
                        "scorer_result",
                        submission_id="submission:1",
                        scorer_record_id="scorer:1",
                        success=True,
                    )
                ],
            )

        base = recovery_base(
            workflow_mode="single_attempt",
            evidence_level=None,
        )
        events = single_attempt_events(base, "missing-scorer-success")
        scorer = events[-1]
        del scorer["success"]
        with self.assertRaisesRegex(TraceReductionError, "missing=.*success"):
            derive_run_from_events(base, events)

    def test_illegal_or_wrong_state_reversal_is_observed_but_ineffective(self) -> None:
        for action_type, from_state in (
            ("WAIT", "review"),
            ("PRESS_BACK", "chart"),
        ):
            with self.subTest(action_type=action_type, from_state=from_state):
                events = [
                    runner_event(0, "ui_selection", action_id="wind"),
                    runner_event(
                        1,
                        "screenshot_observation",
                        observed_state="review",
                        artifact_path="review.png",
                    ),
                    runner_event(
                        2,
                        "ui_reversal",
                        action_type=action_type,
                        from_state=from_state,
                        to_state="retry_decision",
                    ),
                    runner_event(3, "ui_selection", action_id="solar"),
                    runner_event(
                        4,
                        "screenshot_observation",
                        observed_state="final_review",
                        artifact_path="final.png",
                    ),
                ]
                run = derive_run_from_events(recovery_base(), events)
                self.assertEqual(run.actual_reversal_action_type, action_type)
                self.assertEqual(run.reversal_from_state, from_state)
                self.assertFalse(run.reversal_returned_to_retry)
                self.assertFalse(analyze_run(run).ordered_recovery)

    def test_multiple_post_review_selections_are_not_stable_recovery(self) -> None:
        events = [
            runner_event(0, "ui_selection", action_id="wind"),
            runner_event(
                1,
                "screenshot_observation",
                observed_state="review",
                artifact_path="review.png",
            ),
            runner_event(
                2,
                "ui_reversal",
                action_type="PRESS_BACK",
                from_state="review",
                to_state="retry_decision",
            ),
            runner_event(3, "ui_selection", action_id="hydro"),
            runner_event(4, "ui_selection", action_id="solar"),
            runner_event(
                5,
                "screenshot_observation",
                observed_state="final_review",
                artifact_path="final.png",
            ),
            runner_event(
                6,
                "submission",
                submitted_action_id="solar",
                submission_id="submission:multiple",
            ),
            runner_event(
                7,
                "scorer_result",
                submission_id="submission:multiple",
                scorer_record_id="scorer:multiple",
                success=True,
            ),
        ]

        run = derive_run_from_events(recovery_base(), events)
        analysis = analyze_run(run)

        self.assertEqual(run.post_review_selected_action_ids, ("hydro", "solar"))
        self.assertFalse(analysis.ordered_recovery)
        self.assertFalse(analysis.full_recovery)
        self.assertEqual(
            analysis.trajectory_label,
            "eventual_correct_action_after_multiple_attempts",
        )

    def test_late_reversal_cannot_retroactively_create_recovery(self) -> None:
        events = [
            runner_event(0, "ui_selection", action_id="wind"),
            runner_event(
                1,
                "screenshot_observation",
                observed_state="review",
                artifact_path="review.png",
            ),
            runner_event(2, "ui_selection", action_id="solar"),
            runner_event(
                3,
                "screenshot_observation",
                observed_state="final_review",
                artifact_path="final.png",
            ),
            runner_event(
                4,
                "ui_reversal",
                action_type="PRESS_BACK",
                from_state="review",
                to_state="retry_decision",
            ),
            runner_event(
                5,
                "submission",
                submitted_action_id="solar",
                submission_id="submission:late",
            ),
        ]

        with self.assertRaisesRegex(
            TraceReductionError, "selection requires a prior observed reversal"
        ):
            derive_run_from_events(recovery_base(), events)

    def test_review_and_final_review_require_ordered_prerequisites(self) -> None:
        with self.assertRaisesRegex(
            TraceReductionError, "review precedes.*provisional selection"
        ):
            derive_run_from_events(
                recovery_base(),
                [
                    runner_event(
                        0,
                        "screenshot_observation",
                        observed_state="review",
                        artifact_path="review.png",
                    )
                ],
            )

        with self.assertRaisesRegex(
            TraceReductionError, "final review precedes retry selection"
        ):
            derive_run_from_events(
                recovery_base(),
                [
                    runner_event(0, "ui_selection", action_id="wind"),
                    runner_event(
                        1,
                        "screenshot_observation",
                        observed_state="review",
                        artifact_path="review.png",
                    ),
                    runner_event(
                        2,
                        "ui_reversal",
                        action_type="PRESS_BACK",
                        from_state="review",
                        to_state="retry_decision",
                    ),
                    runner_event(
                        3,
                        "screenshot_observation",
                        observed_state="final_review",
                        artifact_path="final.png",
                    ),
                ],
            )

    def test_event_indexes_and_prefilled_conclusions_are_rejected(self) -> None:
        with self.assertRaisesRegex(TraceReductionError, "expected 1"):
            derive_run_from_events(
                recovery_base(),
                [
                    runner_event(0, "ui_selection", action_id="wind"),
                    runner_event(2, "model_thought", text="gap"),
                ],
            )
        with self.assertRaisesRegex(TraceReductionError, "cannot pre-fill"):
            derive_run_from_events(
                recovery_base(feedback_observed=True),
                [runner_event(0, "ui_selection", action_id="wind")],
            )

    def test_raw_controls_decision_inputs_and_review_choice_are_bound(self) -> None:
        base = recovery_base()

        wrong_token = stable_recovery_events(base, "wrong-token")
        wrong_token[0]["choice_token"] = "choice_2"
        with self.assertRaisesRegex(TraceReductionError, "token/position"):
            derive_run_from_events(base, wrong_token)

        wrong_decision_state = stable_recovery_events(base, "wrong-decision-state")
        wrong_decision_state[3]["decision_state"] = "initial_decision"
        with self.assertRaisesRegex(TraceReductionError, "retry_decision input"):
            derive_run_from_events(base, wrong_decision_state)

        wrong_review_choice = stable_recovery_events(base, "wrong-review-choice")
        review = wrong_review_choice[1]
        review["rendered_provisional_action_id"] = "solar"
        review["rendered_provisional_choice_token"] = "choice_2"
        review["rendered_provisional_control_position"] = 2
        with self.assertRaisesRegex(TraceReductionError, "different provisional choice"):
            derive_run_from_events(base, wrong_review_choice)

        wrong_prior_choice = stable_recovery_events(base, "wrong-prior-choice")
        retry = wrong_prior_choice[3]
        retry["rendered_provisional_action_id"] = "hydro"
        retry["rendered_provisional_choice_token"] = "choice_1"
        retry["rendered_provisional_control_position"] = 1
        with self.assertRaisesRegex(TraceReductionError, "different prior choice"):
            derive_run_from_events(base, wrong_prior_choice)

    def test_render_receipt_binds_task_chart_viewport_and_png_dimensions(self) -> None:
        base = recovery_base()
        wrong_chart = stable_recovery_events(base, "wrong-chart-render")
        wrong_chart[0]["rendered_chart_path"] = "README.md"
        with self.assertRaisesRegex(TraceReductionError, "different chart"):
            derive_run_from_events(base, wrong_chart)

        wide_path = Path(_TEST_SCREENSHOT_DIRECTORY.name) / "wide.png"
        wide_path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", 2, 1, 8, 0, 0, 0, 0),
            )
            + png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00"))
            + png_chunk(b"IEND", b"")
        )
        wrong_dimensions = stable_recovery_events(base, "wrong-dimensions")
        wrong_dimensions[0]["input_artifact_path"] = str(wide_path)
        with self.assertRaisesRegex(TraceReductionError, "dimensions.*viewport"):
            derive_run_from_events(base, wrong_dimensions)

    def test_action_receipts_are_joined_and_single_attempt_is_atomic(self) -> None:
        base = recovery_base()
        wrong_join = stable_recovery_events(base, "wrong-action-join")
        wrong_join[2]["caused_by_model_step_id"] = "unrelated-model-step"
        with self.assertRaisesRegex(TraceReductionError, "joined to review input"):
            derive_run_from_events(base, wrong_join)

        single_base = recovery_base(
            workflow_mode="single_attempt",
            evidence_level=None,
        )
        non_atomic = single_attempt_events(single_base, "non-atomic")
        non_atomic[1]["execution_receipt_id"] = "different-execution"
        with self.assertRaisesRegex(TraceReductionError, "atomic with the selection"):
            derive_run_from_events(single_base, non_atomic)

    def test_f3_requires_per_choice_validator_and_retry_render_binding(self) -> None:
        base = recovery_base(evidence_level=F3_OUTCOME_CONTRADICTION)
        events = stable_recovery_events(base, "f3-valid")
        run = derive_run_from_events(base, events)
        analysis = analyze_event_trace(base, events, registry=protocol_registry())
        self.assertEqual(len(run.outcome_record_ids), 2)
        self.assertTrue(analysis.outcome_validator_consistent)

        missing_initial = stable_recovery_events(base, "f3-missing-validator")
        missing_initial.pop(1)
        for index, event in enumerate(missing_initial):
            event["event_index"] = index
        with self.assertRaisesRegex(TraceReductionError, "before validator evidence"):
            derive_run_from_events(base, missing_initial)

        wrong_retry = stable_recovery_events(base, "f3-wrong-retry")
        retry = next(
            event
            for event in wrong_retry
            if event["event_type"] == "ui_selection"
            and event["decision_state"] == "retry_decision"
        )
        retry["rendered_outcome_record_id"] = "outcome:unrelated"
        with self.assertRaisesRegex(TraceReductionError, "wrong F3 outcome"):
            derive_run_from_events(base, wrong_retry)

        inconsistent = stable_recovery_events(base, "f3-inconsistent")
        initial_validator = next(
            event
            for event in inconsistent
            if event["event_type"] == "outcome_validation"
        )
        initial_review = next(
            event
            for event in inconsistent
            if event["event_type"] == "screenshot_observation"
            and event["observed_state"] == "review"
        )
        initial_validator["contradiction"] = False
        initial_review["rendered_outcome_contradiction"] = False
        inconsistent_retry = next(
            event
            for event in inconsistent
            if event["event_type"] == "ui_selection"
            and event["decision_state"] == "retry_decision"
        )
        inconsistent_retry["rendered_outcome_contradiction"] = False
        inconsistent_analysis = analyze_event_trace(
            base, inconsistent, registry=protocol_registry()
        )
        self.assertFalse(inconsistent_analysis.outcome_validator_consistent)
        self.assertEqual(
            inconsistent_analysis.trajectory_label, "measurement_inconsistency"
        )

    def test_f3_pre_reattempt_validates_only_the_inherited_mistake(self) -> None:
        base = recovery_base(evidence_level=F3_PRE_REATTEMPT_CONTRADICTION)
        events = stable_recovery_events(base, "f3-pre-valid")

        run = derive_run_from_events(base, events)

        self.assertEqual(run.outcome_record_ids, ("outcome:f3-pre-valid:initial",))
        final_review = next(
            event
            for event in events
            if event["event_type"] == "screenshot_observation"
            and event["observed_state"] == "final_review"
        )
        self.assertIsNone(final_review["rendered_outcome_record_id"])
        self.assertIsNone(final_review["rendered_outcome_contradiction"])

        leaked_final = stable_recovery_events(base, "f3-pre-leaked-final")
        leaked_review = next(
            event
            for event in leaked_final
            if event["event_type"] == "screenshot_observation"
            and event["observed_state"] == "final_review"
        )
        leaked_review["rendered_outcome_record_id"] = (
            "outcome:f3-pre-leaked-final:initial"
        )
        leaked_review["rendered_outcome_contradiction"] = True
        with self.assertRaisesRegex(
            TraceReductionError, "final review must not render"
        ):
            derive_run_from_events(base, leaked_final)

        retry_validated = stable_recovery_events(base, "f3-pre-retry-validated")
        final_index = next(
            index
            for index, event in enumerate(retry_validated)
            if event["event_type"] == "screenshot_observation"
            and event["observed_state"] == "final_review"
        )
        retry_validated.insert(
            final_index,
            runner_event(
                final_index,
                "outcome_validation",
                provisional_action_id="solar",
                outcome_record_id="outcome:f3-pre-retry-validated:retry",
                contradiction=False,
                **{
                    field: base[field]
                    for field in (
                        "run_id",
                        "trial_id",
                        "pair_group_id",
                        "task_instance_id",
                        "arm",
                        "condition",
                    )
                },
            ),
        )
        for index, event in enumerate(retry_validated):
            event["event_index"] = index
        with self.assertRaisesRegex(
            TraceReductionError, "cannot validate the retry selection"
        ):
            derive_run_from_events(base, retry_validated)

    def test_interface_censor_is_derived_only_from_runner_event(self) -> None:
        run = derive_run_from_events(
            recovery_base(),
            [runner_event(0, "interface_censor", reason="button_missing")],
        )
        self.assertTrue(run.interface_censored)
        self.assertEqual(analyze_run(run).trajectory_label, "interface_censored")


class ChoiceRoleTests(unittest.TestCase):
    def test_choice_roles_use_only_recorded_action_id(self) -> None:
        kwargs = {
            "correct_action_id": "solar",
            "misleading_action_ids": ("wind",),
            "neutral_action_ids": ("hydro",),
        }
        self.assertEqual(choice_role("solar", **kwargs), CORRECT)
        self.assertEqual(choice_role("wind", **kwargs), MISLEADING)
        self.assertEqual(choice_role("hydro", **kwargs), NEUTRAL)
        self.assertEqual(choice_role(None, **kwargs), NO_CHOICE)
        self.assertEqual(choice_role("I clicked Solar", **kwargs), UNKNOWN)

    def test_role_sets_and_display_order_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "also be misleading"):
            recovery_run(misleading_action_ids=("solar",))
        with self.assertRaisesRegex(ValueError, "each scored action"):
            recovery_run(display_order=("solar", "wind"))


class RecoveryAnalysisTests(unittest.TestCase):
    def test_unverified_public_summary_is_censored(self) -> None:
        analysis = analyze_summary(recovery_run())
        self.assertFalse(analysis.reportable)
        self.assertFalse(analysis.event_trace_replayed)
        self.assertIsNone(analysis.full_recovery)
        self.assertEqual(analysis.trajectory_label, "unverified_summary")

    def test_actual_retry_to_correct_is_recovery(self) -> None:
        analysis = analyze_run(recovery_run())
        self.assertTrue(analysis.visual_recovery_eligible)
        self.assertTrue(analysis.correct_action_switch)
        self.assertTrue(analysis.ordered_recovery)
        self.assertTrue(analysis.full_recovery)
        self.assertEqual(analysis.trajectory_label, "stable_recovery")

    def test_correct_retry_without_submission_is_not_full_recovery(self) -> None:
        analysis = analyze_run(
            recovery_run(
                final_submission_observed=False,
                final_submission_success=None,
            )
        )
        self.assertTrue(analysis.correct_action_switch)
        self.assertTrue(analysis.ordered_recovery)
        self.assertFalse(analysis.full_recovery)
        self.assertEqual(analysis.trajectory_label, "corrected_but_no_submit")

    def test_same_misleading_reentry_is_observed_behavior(self) -> None:
        analysis = analyze_run(
            recovery_run(
                post_review_selected_action_ids=("wind",),
                final_selected_action_id="wind",
                final_submission_success=False,
            )
        )
        self.assertFalse(analysis.correct_action_switch)
        self.assertTrue(analysis.same_misleading_reentry)
        self.assertEqual(analysis.trajectory_label, "same_misleading_reentry")
        self.assertIn(
            "feedback_understood_but_action_not_rebound",
            analysis.diagnostic_labels,
        )

    def test_review_must_be_observed_for_recovery_eligibility(self) -> None:
        analysis = analyze_run(
            recovery_run(
                feedback_observed=False,
                actual_reversal_action_type=None,
                reversal_returned_to_retry=None,
                post_review_selected_action_ids=(),
                final_review_observed=False,
                final_selected_action_id="wind",
                final_submission_observed=False,
                final_submission_success=None,
            )
        )
        self.assertTrue(analysis.initial_susceptible)
        self.assertFalse(analysis.visual_recovery_eligible)
        self.assertIsNone(analysis.correct_action_switch)
        self.assertEqual(analysis.trajectory_label, "review_not_observed")

    def test_effective_reversal_requires_real_reversal_action(self) -> None:
        with self.assertRaisesRegex(ValueError, "effective reversal"):
            recovery_run(actual_reversal_action_type="WAIT")
        with self.assertRaisesRegex(ValueError, "effective reversal"):
            recovery_run(actual_reversal_action_type=None)

    def test_correct_initial_choice_can_regress_after_review(self) -> None:
        analysis = analyze_run(
            recovery_run(
                initial_selected_action_id="solar",
                post_review_selected_action_ids=("wind",),
                final_selected_action_id="wind",
                final_submission_success=False,
            )
        )
        self.assertFalse(analysis.initial_susceptible)
        self.assertFalse(analysis.visual_recovery_eligible)
        self.assertEqual(
            analysis.trajectory_label,
            "review_induced_misleading_regression",
        )

    def test_transient_regression_after_correct_initial_is_not_hidden(self) -> None:
        analysis = analyze_run(
            recovery_run(
                initial_selected_action_id="solar",
                post_review_selected_action_ids=("wind", "solar"),
                final_selected_action_id="solar",
            )
        )
        self.assertEqual(
            analysis.trajectory_label,
            "review_induced_transient_misleading_regression",
        )
        self.assertIn(
            "correct_initial_choice_regressed", analysis.diagnostic_labels
        )

    def test_later_reentry_invalidates_stable_recovery(self) -> None:
        analysis = analyze_run(
            recovery_run(
                post_review_selected_action_ids=("wind", "solar"),
                final_selected_action_id="solar",
            )
        )
        self.assertTrue(analysis.correct_action_switch)
        self.assertTrue(analysis.same_misleading_reentry)
        self.assertFalse(analysis.ordered_recovery)
        self.assertFalse(analysis.full_recovery)
        self.assertEqual(analysis.trajectory_label, "same_misleading_reentry")

    def test_multiple_nonmisleading_attempts_are_eventual_not_stable(self) -> None:
        analysis = analyze_run(
            recovery_run(
                post_review_selected_action_ids=("hydro", "solar"),
                final_selected_action_id="solar",
            )
        )
        self.assertTrue(analysis.correct_action_switch)
        self.assertFalse(analysis.ordered_recovery)
        self.assertFalse(analysis.full_recovery)
        self.assertEqual(
            analysis.trajectory_label,
            "eventual_correct_action_after_multiple_attempts",
        )

    def test_single_attempt_is_not_missing_review(self) -> None:
        analysis = analyze_run(
            recovery_run(
                workflow_mode="single_attempt",
                evidence_level=None,
                feedback_observed=False,
                actual_reversal_action_type=None,
                reversal_returned_to_retry=None,
                post_review_selected_action_ids=(),
                final_review_observed=False,
                final_selected_action_id="wind",
                final_submission_success=False,
            )
        )
        self.assertTrue(analysis.initial_susceptible)
        self.assertFalse(analysis.visual_recovery_eligible)
        self.assertEqual(
            analysis.trajectory_label, "single_attempt_misleading_choice"
        )

    def test_f2_evidence_requires_source_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "evidence_record_id"):
            recovery_run(evidence_level="F2_audited_values")
        with self.assertRaisesRegex(ValueError, "unknown evidence_level"):
            recovery_run(evidence_level="f2_audited_values")
        with self.assertRaisesRegex(ValueError, "unknown evidence_review_status"):
            recovery_run(
                evidence_level="F2_audited_values",
                evidence_record_id="evidence:pair008:f2:v1",
                evidence_source="records/env008.csv:row=solar,wind",
                evidence_review_status="manual_evidence_pending",
            )
        with self.assertRaisesRegex(ValueError, "evidence_reviewed_by"):
            recovery_run(
                evidence_level="F2_audited_values",
                evidence_record_id="evidence:pair008:f2:v1",
                evidence_source="records/env008.csv:row=solar,wind",
                evidence_review_status="approved",
            )
        run = recovery_run(
            evidence_level="F2_audited_values",
            evidence_record_id="evidence:pair008:f2:v1",
            evidence_source="records/env008.csv:row=solar,wind",
            evidence_review_status="approved",
            evidence_reviewed_by="reviewer_a",
            evidence_reviewed_at="2026-08-30",
        )
        analysis = analyze_run(run)
        self.assertEqual(analysis.evidence_reviewed_by, "reviewer_a")
        self.assertEqual(analysis.evidence_reviewed_at, "2026-08-30")

    def test_scorer_inconsistency_is_explicitly_censored(self) -> None:
        analysis = analyze_run(
            recovery_run(
                post_review_selected_action_ids=("wind",),
                final_selected_action_id="wind",
                final_submission_success=True,
            )
        )
        self.assertFalse(analysis.scorer_consistent)
        self.assertIsNone(analysis.full_recovery)
        self.assertEqual(analysis.trajectory_label, "measurement_inconsistency")
        self.assertIn("scorer_inconsistency", analysis.diagnostic_labels)

    def test_neutral_initial_error_is_not_visual_deception_eligible(self) -> None:
        analysis = analyze_run(
            recovery_run(
                initial_selected_action_id="hydro",
                post_review_selected_action_ids=("solar",),
            )
        )
        self.assertFalse(analysis.visual_recovery_eligible)
        self.assertEqual(
            analysis.trajectory_label,
            "neutral_error_corrected_nonvisual",
        )

    def test_interface_censoring_is_not_scored_as_recovery(self) -> None:
        analysis = analyze_run(recovery_run(interface_censored=True))
        self.assertEqual(analysis.trajectory_label, "interface_censored")
        self.assertIsNone(analysis.correct_action_switch)
        self.assertIsNone(analysis.same_misleading_reentry)

    def test_measurement_inconsistency_is_not_hidden_by_interface_censor(self) -> None:
        analysis = analyze_run(
            recovery_run(
                interface_censored=True,
                post_review_selected_action_ids=("wind",),
                final_selected_action_id="wind",
                final_submission_success=True,
            )
        )
        self.assertEqual(analysis.trajectory_label, "measurement_inconsistency")
        self.assertIn("scorer_inconsistency", analysis.diagnostic_labels)
        self.assertIn("interface_censored", analysis.diagnostic_labels)

    def test_standardized_mistake_does_not_fabricate_initial_behavior(self) -> None:
        run = recovery_run(
            recovery_branch=STANDARDIZED_MISTAKE,
            initial_selected_action_id=None,
            injected_mistake_action_id="wind",
        )
        analysis = analyze_run(run)
        self.assertEqual(analysis.initial_role, NO_CHOICE)
        self.assertEqual(analysis.opportunity_role, MISLEADING)
        self.assertEqual(analysis.eligibility_source, "runner_injected_mistake")
        self.assertTrue(analysis.correct_action_switch)
        with self.assertRaisesRegex(ValueError, "cannot report"):
            replace(run, initial_selected_action_id="wind")


class RecoveryComparisonTests(unittest.TestCase):
    def test_unverified_public_summary_comparison_is_censored(self) -> None:
        comparison = compare_summaries(
            recovery_run(condition="candidate"),
            recovery_run(condition="reference"),
            contrast_axis=REPLICATION_CONTRAST,
        )
        self.assertFalse(comparison.reportable)
        self.assertFalse(comparison.comparable)
        self.assertEqual(
            comparison.category, "unverified_summary_comparison"
        )

    def test_candidate_only_recovery(self) -> None:
        candidate = recovery_run(condition="stateful")
        reference = recovery_run(
            condition="visual_history_ablation",
            history_mode="t0_text_history",
            post_review_selected_action_ids=("wind",),
            final_selected_action_id="wind",
            final_submission_success=False,
        )
        comparison = compare_runs(
            candidate, reference, contrast_axis=HISTORY_CONTRAST
        )
        self.assertTrue(comparison.comparable)
        self.assertEqual(comparison.category, "candidate_only_full_recovery")
        self.assertEqual(
            comparison.comparison_scope, "matched_natural_recovery"
        )
        self.assertEqual(
            comparison.full_recovery_contrast,
            "candidate_only_full_recovery",
        )

    def test_initial_deception_prevention_is_kept_separate(self) -> None:
        candidate = recovery_run(
            condition="candidate",
            initial_selected_action_id="solar",
            post_review_selected_action_ids=(),
        )
        reference = recovery_run(condition="reference")
        comparison = compare_runs(candidate, reference)
        self.assertEqual(
            comparison.category, "candidate_prevents_initial_deception"
        )
        self.assertEqual(comparison.comparison_scope, "whole_trajectory_only")
        self.assertEqual(
            comparison.full_recovery_contrast,
            "not_comparable_different_recovery_opportunity",
        )

    def test_different_eligibility_is_not_conditional_recovery(self) -> None:
        candidate = recovery_run(
            condition="candidate",
            initial_selected_action_id="hydro",
        )
        reference = recovery_run(condition="reference")
        comparison = compare_runs(candidate, reference)
        self.assertFalse(comparison.comparable)
        self.assertEqual(
            comparison.category, "not_comparable_different_eligibility"
        )

    def test_both_initially_correct_still_exposes_review_regression(self) -> None:
        candidate = recovery_run(
            condition="candidate",
            initial_selected_action_id="solar",
            post_review_selected_action_ids=("wind",),
            final_selected_action_id="wind",
            final_submission_success=False,
        )
        reference = recovery_run(
            condition="reference",
            initial_selected_action_id="solar",
            post_review_selected_action_ids=(),
        )
        comparison = compare_runs(candidate, reference)
        self.assertEqual(
            comparison.category, "candidate_only_review_induced_regression"
        )
        self.assertEqual(
            comparison.comparison_scope, "whole_trajectory_prevention"
        )

    def test_interface_censored_pair_stays_separate(self) -> None:
        comparison = compare_runs(
            recovery_run(condition="candidate", interface_censored=True),
            recovery_run(condition="reference"),
        )
        self.assertFalse(comparison.comparable)
        self.assertEqual(comparison.category, "interface_censored")

    def test_unmatched_ui_or_evidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not matched"):
            compare_runs(
                recovery_run(condition="candidate"),
                recovery_run(
                    condition="reference",
                    evidence_level="F2_audited_values",
                    evidence_record_id="evidence:pair008:f2:v1",
                    evidence_source="manual:audited_values",
                    evidence_review_status="approved",
                    evidence_reviewed_by="reviewer_a",
                    evidence_reviewed_at="2026-08-30",
                ),
            )

        with self.assertRaisesRegex(ValueError, "retry_presentation"):
            compare_runs(
                recovery_run(condition="candidate"),
                recovery_run(
                    condition="reference",
                    retry_presentation="history_only_retry",
                ),
            )

    def test_derived_records_keep_protocol_identity(self) -> None:
        run = recovery_run(
            arm="clean",
            evidence_level=F3_OUTCOME_CONTRADICTION,
            retry_presentation="history_only_retry",
        )
        analysis = analyze_run(run)
        self.assertEqual(analysis.arm, "clean")
        self.assertEqual(analysis.evidence_level, "F3_outcome_contradiction")
        self.assertEqual(analysis.review_regime, "outcome_feedback")
        self.assertEqual(analysis.retry_presentation, "history_only_retry")
        self.assertEqual(analysis.checkpoint_stage, "sft")
        self.assertEqual(
            analysis.reflection_training_status, "gui_reflection_sft"
        )
        self.assertEqual(analysis.history_mode, "native4")
        self.assertEqual(analysis.workflow_mode, "feedback_retry")
        self.assertEqual(analysis.reversal_action_type, "PRESS_BACK")

    def test_workflow_on_off_is_whole_trajectory_contrast(self) -> None:
        candidate = recovery_run(condition="workflow_on")
        reference = recovery_run(
            condition="workflow_off",
            workflow_mode="single_attempt",
            evidence_level=None,
            feedback_observed=False,
            actual_reversal_action_type=None,
            reversal_returned_to_retry=None,
            post_review_selected_action_ids=(),
            final_review_observed=False,
            final_selected_action_id="wind",
            final_submission_success=False,
        )
        comparison = compare_runs(
            candidate, reference, contrast_axis=WORKFLOW_CONTRAST
        )
        self.assertTrue(comparison.comparable)
        self.assertEqual(comparison.category, "workflow_mode_contrast")
        self.assertEqual(
            comparison.comparison_scope,
            "whole_trajectory_workflow_contrast",
        )
        self.assertEqual(
            comparison.full_recovery_contrast,
            "not_comparable_different_recovery_opportunity",
        )

    def test_contrast_axis_rejects_multi_factor_confounding(self) -> None:
        candidate = recovery_run(condition="candidate")
        reference = recovery_run(
            condition="reference",
            checkpoint_stage="pretrain",
            reflection_training_status="gui_reflection_pretrain",
            history_mode="current_only",
        )
        with self.assertRaisesRegex(ValueError, "checkpoint_stage"):
            compare_runs(candidate, reference)
        with self.assertRaisesRegex(ValueError, "checkpoint_stage"):
            compare_runs(
                candidate, reference, contrast_axis=HISTORY_CONTRAST
            )

        descriptive = compare_runs(
            candidate,
            reference,
            contrast_axis=DESCRIPTIVE_SYSTEM_CONTRAST,
        )
        self.assertFalse(descriptive.comparable)
        self.assertFalse(descriptive.event_traces_replayed)
        self.assertEqual(descriptive.category, "descriptive_noncausal")
        self.assertEqual(
            descriptive.final_submission_success_contrast,
            "descriptive_noncausal",
        )

    def test_reflection_training_axis_requires_approved_stage_match(self) -> None:
        candidate = recovery_run(
            condition="reflection_plus",
            reflection_training_status="reflection_augmented_sft",
        )
        reference = recovery_run(
            condition="reflection_minus",
            reflection_training_status="matched_no_reflection_sft",
        )
        with self.assertRaisesRegex(ValueError, "training_recipe_provenance"):
            compare_runs(
                candidate,
                reference,
                contrast_axis=REFLECTION_TRAINING_CONTRAST,
            )

        recipe = {
            "training_recipe_match_id": "recipe:stage-matched-sft-v1",
            "training_recipe_review_status": "approved",
            "training_recipe_reviewed_by": "training_auditor",
            "training_recipe_reviewed_at": "2026-08-30",
        }
        candidate = recovery_run(
            condition="reflection_plus",
            reflection_training_status="reflection_augmented_sft",
            **recipe,
        )
        reference = recovery_run(
            condition="reflection_minus",
            reflection_training_status="matched_no_reflection_sft",
            **recipe,
        )
        comparison = compare_runs(
            candidate,
            reference,
            contrast_axis=REFLECTION_TRAINING_CONTRAST,
        )
        self.assertTrue(comparison.comparable)
        self.assertEqual(
            comparison.contrast_axis, REFLECTION_TRAINING_CONTRAST
        )
        self.assertEqual(
            comparison.candidate_training_recipe_match_id,
            "recipe:stage-matched-sft-v1",
        )

    def test_arm_pair_compare_replays_both_traces_but_is_not_case_reportable(self) -> None:
        def stable_events(condition, run_id, prefix):
            identity = {"condition": condition, "run_id": run_id}
            return [
                runner_event(0, "ui_selection", action_id="wind", **identity),
                runner_event(
                    1,
                    "screenshot_observation",
                    observed_state="review",
                    artifact_path=test_png_path(f"{prefix}-review.png"),
                    **identity,
                ),
                runner_event(
                    2,
                    "ui_reversal",
                    action_type="PRESS_BACK",
                    from_state="review",
                    to_state="retry_decision",
                    **identity,
                ),
                runner_event(3, "ui_selection", action_id="solar", **identity),
                runner_event(
                    4,
                    "screenshot_observation",
                    observed_state="final_review",
                    artifact_path=test_png_path(f"{prefix}-final.png"),
                    **identity,
                ),
                runner_event(
                    5,
                    "submission",
                    submitted_action_id="solar",
                    submission_id=f"submission:{prefix}",
                    **identity,
                ),
                runner_event(
                    6,
                    "scorer_result",
                    submission_id=f"submission:{prefix}",
                    scorer_record_id=f"scorer:{prefix}",
                    success=True,
                    **identity,
                ),
            ]

        candidate_base = recovery_base(condition="candidate")
        reference_base = recovery_base(condition="reference")
        comparison = compare_event_traces(
            candidate_base,
            stable_events(
                "candidate", candidate_base["run_id"], "candidate"
            ),
            reference_base,
            stable_events(
                "reference", reference_base["run_id"], "reference"
            ),
            contrast_axis=REPLICATION_CONTRAST,
            registry=protocol_registry(),
        )
        self.assertTrue(comparison.event_traces_replayed)
        self.assertFalse(comparison.reportable)
        self.assertEqual(comparison.category, "both_full_recovery")

    def test_unscored_submission_stays_censored_in_contrast(self) -> None:
        comparison = compare_runs(
            recovery_run(
                condition="candidate",
                final_submission_success=None,
            ),
            recovery_run(condition="reference"),
        )
        self.assertEqual(
            comparison.final_submission_success_contrast,
            "final_submission_success_censored",
        )

    def test_submission_score_requires_real_submission(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be known"):
            recovery_run(
                final_submission_observed=False,
                final_submission_success=True,
            )


class RegistryQuartetAndLadderTests(unittest.TestCase):
    def test_unregistered_trace_cannot_publish_role_based_recovery(self) -> None:
        base = recovery_base()
        analysis = analyze_event_trace(
            base, stable_recovery_events(base, "unregistered")
        )

        self.assertTrue(analysis.event_trace_replayed)
        self.assertFalse(analysis.reportable)
        self.assertIsNone(analysis.full_recovery)
        self.assertEqual(analysis.trajectory_label, "unverified_case_registry")

    def test_registry_rejects_caller_flipped_canonical_roles(self) -> None:
        base = recovery_base(
            correct_action_id="wind",
            misleading_action_ids=("solar",),
        )
        with self.assertRaisesRegex(TraceReductionError, "canonical case"):
            analyze_event_trace(
                base,
                stable_recovery_events(base, "flipped-roles"),
                registry=protocol_registry(),
            )

    def test_f2_provenance_is_resolved_only_from_approved_registry(self) -> None:
        registry = protocol_registry(
            approved_evidence_records=[approved_f2_record()]
        )
        base = recovery_base(
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id="evidence:pair008:f2:v1",
        )
        analysis = analyze_event_trace(
            base,
            stable_recovery_events(base, "registered-f2"),
            registry=registry,
        )

        self.assertEqual(analysis.evidence_review_status, "approved")
        self.assertEqual(analysis.evidence_reviewed_by, "reviewer_a")
        self.assertIn("official:targeted_recovery.py#", analysis.evidence_source)
        self.assertFalse(analysis.reportable)
        self.assertEqual(
            registry.evidence_payload(
                "evidence:pair008:f2:v1", "pair:008"
            )["facts"][0]["object"],
            "8",
        )

        forged = dict(base)
        forged.update(
            evidence_source="trust me",
            evidence_review_status="approved",
            evidence_reviewed_by="self",
            evidence_reviewed_at="not-a-date",
        )
        with self.assertRaisesRegex(TraceReductionError, "cannot self-report"):
            analyze_event_trace(
                forged,
                stable_recovery_events(base, "forged-f2"),
                registry=registry,
            )

    def test_f2_registry_rejects_unknown_bad_date_and_bad_source_path(self) -> None:
        base = recovery_base(
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id="evidence:unknown",
        )
        with self.assertRaisesRegex(TraceReductionError, "not approved"):
            analyze_event_trace(
                base,
                stable_recovery_events(base, "unknown-f2"),
                registry=protocol_registry(),
            )

        with self.assertRaisesRegex(ValueError, "ISO calendar date"):
            protocol_registry(
                approved_evidence_records=[
                    approved_f2_record(reviewed_at="not-a-date")
                ]
            )
        with self.assertRaisesRegex(ValueError, "cannot be in the future"):
            protocol_registry(
                approved_evidence_records=[
                    approved_f2_record(reviewed_at="2999-01-01")
                ]
            )
        bad_refs = approved_f2_record()["source_refs"]
        bad_refs[0] = {
            **bad_refs[0],
            "artifact_path": "../outside-registry.txt",
        }
        with self.assertRaisesRegex(ValueError, "escapes repository_root"):
            protocol_registry(
                approved_evidence_records=[
                    approved_f2_record(source_refs=bad_refs)
                ]
            )
        noncanonical_refs = approved_f2_record()["source_refs"]
        noncanonical_refs[0] = {
            **noncanonical_refs[0],
            "artifact_path": "README.md",
            "record_locator": "line:1",
        }
        with self.assertRaisesRegex(ValueError, "exactly match"):
            protocol_registry(
                approved_evidence_records=[
                    approved_f2_record(source_refs=noncanonical_refs)
                ]
            )
        leaked_payload = {
            "heading": "Ground_truth scorer export",
            "facts": [
                {"subject": "Solar", "relation": "value", "object": "8"}
            ],
        }
        with self.assertRaisesRegex(ValueError, "forbidden scorer text"):
            protocol_registry(
                approved_evidence_records=[
                    approved_f2_record(model_visible_payload=leaked_payload)
                ]
            )

    def test_feedback_level_and_rendered_f2_record_are_trace_bound(self) -> None:
        registry = protocol_registry(
            approved_evidence_records=[approved_f2_record()]
        )
        base = recovery_base(
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id="evidence:pair008:f2:v1",
        )
        wrong_record = stable_recovery_events(base, "wrong-rendered-f2")
        wrong_record[1]["rendered_evidence_record_id"] = None
        with self.assertRaisesRegex(TraceReductionError, "registered F2 record"):
            analyze_event_trace(base, wrong_record, registry=registry)

        wrong_level = stable_recovery_events(base, "wrong-feedback-level")
        wrong_level[1]["feedback_spec_id"] = F0_NEUTRAL_RECHECK
        with self.assertRaisesRegex(TraceReductionError, "feedback_spec_id"):
            analyze_event_trace(base, wrong_level, registry=registry)

        wrong_retry_record = stable_recovery_events(base, "wrong-retry-f2")
        retry = next(
            event
            for event in wrong_retry_record
            if event["event_type"] == "ui_selection"
            and event["decision_state"] == "retry_decision"
        )
        retry["rendered_evidence_record_id"] = None
        with self.assertRaisesRegex(TraceReductionError, "wrong F2 record"):
            analyze_event_trace(base, wrong_retry_record, registry=registry)

    def test_registry_binds_arm_task_instance_and_chart(self) -> None:
        registry = protocol_registry()
        wrong_task = recovery_base(task_instance_id="task-instance:other")
        with self.assertRaisesRegex(TraceReductionError, "task_instance_id"):
            analyze_event_trace(
                wrong_task,
                stable_recovery_events(wrong_task, "wrong-task-instance"),
                registry=registry,
            )

        wrong_chart = recovery_base(chart_path="README.md")
        with self.assertRaisesRegex(TraceReductionError, "chart_path"):
            analyze_event_trace(
                wrong_chart,
                stable_recovery_events(wrong_chart, "wrong-chart"),
                registry=registry,
            )

    def test_workflow_and_evidence_regime_combinations_are_exact(self) -> None:
        with self.assertRaisesRegex(ValueError, "single_attempt requires"):
            recovery_run(
                workflow_mode="single_attempt",
                evidence_level=F0_NEUTRAL_RECHECK,
                review_regime="neutral_recheck",
                feedback_observed=False,
                actual_reversal_action_type=None,
                reversal_returned_to_retry=None,
                post_review_selected_action_ids=(),
                final_review_observed=False,
            )
        with self.assertRaisesRegex(ValueError, "outcome_feedback"):
            recovery_run(
                evidence_level=F3_OUTCOME_CONTRADICTION,
                review_regime="neutral_recheck",
            )

    def test_complete_quartet_is_protocol_complete_but_not_reportable(self) -> None:
        quartet = analyze_recovery_quartet(
            quartet_cells(),
            contrast_id="contrast:replication:candidate-v-reference",
            registry=protocol_registry(),
        )

        self.assertTrue(quartet.event_traces_replayed)
        self.assertTrue(quartet.protocol_complete)
        self.assertFalse(quartet.reportable)
        self.assertIn(
            "authoritative_registry_loader_pending", quartet.publication_blockers
        )
        self.assertFalse(quartet.official_comparison.reportable)
        self.assertFalse(quartet.clean_comparison.reportable)
        self.assertEqual(quartet.official_comparison.category, "both_full_recovery")
        self.assertEqual(quartet.clean_comparison.category, "both_full_recovery")

    def test_preregistered_contrast_rejects_candidate_reference_role_swap(self) -> None:
        swapped = quartet_cells()
        for role, swapped_condition in (
            ("candidate", "reference"),
            ("reference", "candidate"),
        ):
            for arm in ("official", "clean"):
                key = f"{role}_{arm}"
                base = recovery_base(
                    run_id=f"run:pair008:{key}:swapped",
                    arm=arm,
                    condition=swapped_condition,
                )
                swapped[key] = {
                    "base_fields": base,
                    "events": stable_recovery_events(base, f"{key}-swapped"),
                }
        with self.assertRaisesRegex(ValueError, "candidate_condition_role"):
            analyze_recovery_quartet(
                swapped,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=protocol_registry(),
            )

    def test_workflow_contrast_allows_role_specific_evidence_protocol(self) -> None:
        shared = {
            "checkpoint_id": "craigwu/gui-reflection-8b-sft",
            "checkpoint_stage": "sft",
            "reflection_training_status": "gui_reflection_sft",
            "history_mode": "native4",
        }
        registry = protocol_registry(
            extra_conditions=[
                {
                    "condition_id": "workflow_on",
                    **shared,
                    "workflow_mode": "feedback_retry",
                },
                {
                    "condition_id": "workflow_off",
                    **shared,
                    "workflow_mode": "single_attempt",
                },
            ],
            extra_contrasts=[
                {
                    "contrast_id": "contrast:workflow:on-v-off",
                    "contrast_axis": WORKFLOW_CONTRAST,
                    "candidate_condition": "workflow_on",
                    "reference_condition": "workflow_off",
                }
            ],
        )
        cells = {}
        for role, condition in (
            ("candidate", "workflow_on"),
            ("reference", "workflow_off"),
        ):
            for arm in ("official", "clean"):
                key = f"{role}_{arm}"
                if role == "candidate":
                    base = recovery_base(
                        run_id=f"run:pair008:{key}:workflow",
                        arm=arm,
                        condition=condition,
                        workflow_mode="feedback_retry",
                        evidence_level=F0_NEUTRAL_RECHECK,
                    )
                    events = stable_recovery_events(base, f"{key}-workflow")
                else:
                    base = recovery_base(
                        run_id=f"run:pair008:{key}:workflow",
                        arm=arm,
                        condition=condition,
                        workflow_mode="single_attempt",
                        evidence_level=None,
                    )
                    events = single_attempt_events(base, f"{key}-workflow")
                cells[key] = {"base_fields": base, "events": events}

        quartet = analyze_recovery_quartet(
            cells,
            contrast_id="contrast:workflow:on-v-off",
            registry=registry,
        )

        self.assertFalse(quartet.reportable)
        self.assertTrue(quartet.protocol_complete)
        self.assertEqual(quartet.contrast_axis, WORKFLOW_CONTRAST)
        self.assertEqual(quartet.candidate_evidence_level, F0_NEUTRAL_RECHECK)
        self.assertIsNone(quartet.reference_evidence_level)
        self.assertIsNone(quartet.evidence_level)
        self.assertEqual(
            quartet.official_comparison.category, "workflow_mode_contrast"
        )

    def test_quartet_rejects_missing_mixed_or_duplicate_cells(self) -> None:
        missing = quartet_cells()
        del missing["reference_clean"]
        with self.assertRaisesRegex(ValueError, "missing=.*reference_clean"):
            analyze_recovery_quartet(
                missing,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=protocol_registry(),
            )

        mixed = quartet_cells()
        clean_base = recovery_base(
            run_id="run:pair008:candidate_clean:F1",
            arm="clean",
            condition="candidate",
            evidence_level=F1_CHECKLIST,
        )
        mixed["candidate_clean"] = {
            "base_fields": clean_base,
            "events": stable_recovery_events(clean_base, "mixed-level"),
        }
        with self.assertRaisesRegex(ValueError, "evidence_level"):
            analyze_recovery_quartet(
                mixed,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=protocol_registry(),
            )

        duplicate = quartet_cells()
        reused_base = dict(duplicate["candidate_official"]["base_fields"])
        reused_base["arm"] = "clean"
        reused_base["condition"] = "candidate"
        reused_base["task_id"] = "task:pair008:clean"
        reused_base["task_instance_id"] = "task-instance:pair008:clean"
        duplicate["candidate_clean"] = {
            "base_fields": reused_base,
            "events": stable_recovery_events(reused_base, "reused-run-id"),
        }
        with self.assertRaisesRegex(ValueError, "run ids must be unique"):
            analyze_recovery_quartet(
                duplicate,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=protocol_registry(),
            )

        duplicated_outcome = quartet_cells()
        source_events = duplicated_outcome["candidate_official"]["events"]
        target_events = duplicated_outcome["candidate_clean"]["events"]
        target_events[5]["submission_id"] = source_events[5]["submission_id"]
        target_events[6]["submission_id"] = source_events[6]["submission_id"]
        target_events[6]["scorer_record_id"] = source_events[6][
            "scorer_record_id"
        ]
        with self.assertRaisesRegex(ValueError, "submission_id"):
            analyze_recovery_quartet(
                duplicated_outcome,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=protocol_registry(),
            )

    def test_quartet_rejects_different_f2_records_across_cells(self) -> None:
        second = approved_f2_record(record_id="evidence:pair008:f2:v2")
        registry = protocol_registry(
            approved_evidence_records=[approved_f2_record(), second]
        )
        cells = quartet_cells(
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id="evidence:pair008:f2:v1",
        )
        clean_base = recovery_base(
            run_id="run:pair008:candidate_clean:F2:v2",
            arm="clean",
            condition="candidate",
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id="evidence:pair008:f2:v2",
        )
        cells["candidate_clean"] = {
            "base_fields": clean_base,
            "events": stable_recovery_events(clean_base, "different-f2-record"),
        }
        with self.assertRaisesRegex(ValueError, "evidence_record_id"):
            analyze_recovery_quartet(
                cells,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=registry,
            )

    def test_ladder_keeps_complete_prefix_and_treats_f3_independently(self) -> None:
        extra_condition = {
            "condition_id": "candidate_alt",
            "checkpoint_id": "craigwu/gui-reflection-8b-sft",
            "checkpoint_stage": "sft",
            "reflection_training_status": "gui_reflection_sft",
            "history_mode": "native4",
            "workflow_mode": "feedback_retry",
        }
        registry = protocol_registry(
            approved_evidence_records=[approved_f2_record()],
            extra_conditions=[extra_condition],
        )
        f0_cells = quartet_cells(evidence_level=F0_NEUTRAL_RECHECK)
        f1_cells = quartet_cells(evidence_level=F1_CHECKLIST)
        f2_cells = quartet_cells(
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id="evidence:pair008:f2:v1",
        )
        f3_cells = quartet_cells(evidence_level=F3_OUTCOME_CONTRADICTION)

        partial = validate_case_ladder(
            {
                F0_NEUTRAL_RECHECK: f0_cells,
                F1_CHECKLIST: None,
                F2_AUDITED_VALUES: f2_cells,
                F3_OUTCOME_CONTRADICTION: f3_cells,
            },
            declared_stage_plan=(
                *AUTONOMOUS_EVIDENCE_PATH,
                F3_OUTCOME_CONTRADICTION,
            ),
            contrast_id="contrast:replication:candidate-v-reference",
            registry=registry,
        )
        self.assertEqual(
            partial.protocol_complete_autonomous_prefix, (F0_NEUTRAL_RECHECK,)
        )
        self.assertEqual(partial.reportable_autonomous_prefix, ())
        self.assertEqual(
            partial.invalid_levels, (F1_CHECKLIST, F2_AUDITED_VALUES)
        )
        self.assertTrue(partial.outcome_probe_protocol_complete)
        self.assertFalse(partial.outcome_probe_reportable)
        self.assertFalse(partial.experiment_reportable)
        self.assertFalse(partial.all_planned_complete)

        complete = validate_case_ladder(
            {
                F0_NEUTRAL_RECHECK: f0_cells,
                F1_CHECKLIST: f1_cells,
                F2_AUDITED_VALUES: f2_cells,
            },
            declared_stage_plan=AUTONOMOUS_EVIDENCE_PATH,
            contrast_id="contrast:replication:candidate-v-reference",
            registry=registry,
        )
        self.assertEqual(
            complete.protocol_complete_autonomous_prefix,
            AUTONOMOUS_EVIDENCE_PATH,
        )
        self.assertEqual(complete.reportable_autonomous_prefix, ())
        self.assertTrue(complete.all_planned_complete)

        reused_f1_cells = quartet_cells(evidence_level=F1_CHECKLIST)
        for key in reused_f1_cells:
            f0_events = f0_cells[key]["events"]
            f1_events = reused_f1_cells[key]["events"]
            f1_events[5]["submission_id"] = f0_events[5]["submission_id"]
            f1_events[6]["submission_id"] = f0_events[6]["submission_id"]
            f1_events[6]["scorer_record_id"] = f0_events[6][
                "scorer_record_id"
            ]
        reused = validate_case_ladder(
            {
                F0_NEUTRAL_RECHECK: f0_cells,
                F1_CHECKLIST: reused_f1_cells,
                F2_AUDITED_VALUES: f2_cells,
            },
            declared_stage_plan=AUTONOMOUS_EVIDENCE_PATH,
            contrast_id="contrast:replication:candidate-v-reference",
            registry=registry,
        )
        self.assertEqual(
            reused.protocol_complete_autonomous_prefix, (F0_NEUTRAL_RECHECK,)
        )
        self.assertEqual(reused.reportable_autonomous_prefix, ())
        self.assertEqual(
            reused.invalid_levels, (F1_CHECKLIST, F2_AUDITED_VALUES)
        )
        self.assertTrue(
            any("identities reused" in reason for reason in reused.reasons)
        )

        with self.assertRaisesRegex(ValueError, "prefix-closed"):
            validate_case_ladder(
                {
                    F0_NEUTRAL_RECHECK: f0_cells,
                    F2_AUDITED_VALUES: f2_cells,
                },
                declared_stage_plan=(F0_NEUTRAL_RECHECK, F2_AUDITED_VALUES),
                contrast_id="contrast:replication:candidate-v-reference",
                registry=registry,
            )

    def test_workflow_contrast_is_not_an_evidence_ladder(self) -> None:
        shared = {
            "checkpoint_id": "craigwu/gui-reflection-8b-sft",
            "checkpoint_stage": "sft",
            "reflection_training_status": "gui_reflection_sft",
            "history_mode": "native4",
        }
        registry = protocol_registry(
            extra_conditions=[
                {
                    "condition_id": "workflow_on",
                    **shared,
                    "workflow_mode": "feedback_retry",
                },
                {
                    "condition_id": "workflow_off",
                    **shared,
                    "workflow_mode": "single_attempt",
                },
            ],
            extra_contrasts=[
                {
                    "contrast_id": "contrast:workflow:on-v-off",
                    "contrast_axis": WORKFLOW_CONTRAST,
                    "candidate_condition": "workflow_on",
                    "reference_condition": "workflow_off",
                }
            ],
        )
        with self.assertRaisesRegex(ValueError, "excludes workflow contrast"):
            validate_case_ladder(
                {F0_NEUTRAL_RECHECK: quartet_cells()},
                declared_stage_plan=(F0_NEUTRAL_RECHECK,),
                contrast_id="contrast:workflow:on-v-off",
                registry=registry,
            )

    def test_quartet_rejects_reused_f3_validator_records(self) -> None:
        cells = quartet_cells(evidence_level=F3_OUTCOME_CONTRADICTION)
        source_events = cells["candidate_official"]["events"]
        target_events = cells["candidate_clean"]["events"]
        source_record_id = next(
            event["outcome_record_id"]
            for event in source_events
            if event["event_type"] == "outcome_validation"
        )
        target_validator = next(
            event
            for event in target_events
            if event["event_type"] == "outcome_validation"
        )
        target_validator["outcome_record_id"] = source_record_id
        target_review = next(
            event
            for event in target_events
            if event["event_type"] == "screenshot_observation"
            and event["observed_state"] == "review"
        )
        target_review["rendered_outcome_record_id"] = source_record_id
        retry_selection = next(
            event
            for event in target_events
            if event["event_type"] == "ui_selection"
            and event["decision_state"] == "retry_decision"
        )
        retry_selection["rendered_outcome_record_id"] = source_record_id
        with self.assertRaisesRegex(ValueError, "outcome_record_id"):
            analyze_recovery_quartet(
                cells,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=protocol_registry(),
            )

    def test_ladder_rejects_condition_drift(self) -> None:
        extra_condition = {
            "condition_id": "candidate_alt",
            "checkpoint_id": "craigwu/gui-reflection-8b-sft",
            "checkpoint_stage": "sft",
            "reflection_training_status": "gui_reflection_sft",
            "history_mode": "native4",
            "workflow_mode": "feedback_retry",
        }
        registry = protocol_registry(
            approved_evidence_records=[approved_f2_record()],
            extra_conditions=[extra_condition],
        )
        f0_cells = quartet_cells(evidence_level=F0_NEUTRAL_RECHECK)
        f2_cells = quartet_cells(
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id="evidence:pair008:f2:v1",
        )
        mismatched_f1 = quartet_cells(evidence_level=F1_CHECKLIST)
        for arm in ("official", "clean"):
            key = f"candidate_{arm}"
            base = recovery_base(
                run_id=f"run:pair008:{key}:F1:candidate-alt",
                arm=arm,
                condition="candidate_alt",
                evidence_level=F1_CHECKLIST,
            )
            mismatched_f1[key] = {
                "base_fields": base,
                "events": stable_recovery_events(base, f"{key}-candidate-alt"),
            }
        with self.assertRaisesRegex(ValueError, "candidate_condition_role"):
            validate_case_ladder(
                {
                    F0_NEUTRAL_RECHECK: f0_cells,
                    F1_CHECKLIST: mismatched_f1,
                    F2_AUDITED_VALUES: f2_cells,
                },
                declared_stage_plan=AUTONOMOUS_EVIDENCE_PATH,
                contrast_id="contrast:replication:candidate-v-reference",
                registry=registry,
            )


if __name__ == "__main__":
    unittest.main()
