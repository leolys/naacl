"""Runner-side records and qualitative analysis for targeted recovery runs.

The evaluator intentionally consumes action identifiers recorded by the UI.
It never infers a selection, reversal, or submission from model thoughts or
natural-language action descriptions.
"""

from __future__ import annotations

import copy
import csv
import os
import struct
import zlib
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping


CORRECT = "correct"
MISLEADING = "misleading"
NEUTRAL = "neutral_or_irrelevant"
NO_CHOICE = "none"
UNKNOWN = "unknown"

NATURAL_RECOVERY = "natural"
STANDARDIZED_MISTAKE = "standardized_mistake"
RECOVERY_BRANCHES = frozenset({NATURAL_RECOVERY, STANDARDIZED_MISTAKE})
HISTORY_ONLY_RETRY = "history_only_retry"
CURRENT_VISIBLE_RETRY = "current_visible_retry"
RETRY_PRESENTATIONS = frozenset({HISTORY_ONLY_RETRY, CURRENT_VISIBLE_RETRY})
REVERSAL_ACTION_TYPES = frozenset({"PRESS_BACK", "REVISE_SELECTION"})
SINGLE_ATTEMPT = "single_attempt"
FEEDBACK_RETRY = "feedback_retry"
WORKFLOW_MODES = frozenset({SINGLE_ATTEMPT, FEEDBACK_RETRY})
OFFICIAL_ARM = "official"
CLEAN_ARM = "clean"
ARMS = frozenset({OFFICIAL_ARM, CLEAN_ARM})

F0_NEUTRAL_RECHECK = "F0_neutral_recheck"
F1_CHECKLIST = "F1_checklist"
F2_AUDITED_VALUES = "F2_audited_values"
F3_OUTCOME_CONTRADICTION = "F3_outcome_contradiction"
F3_PRE_REATTEMPT_CONTRADICTION = "F3_pre_reattempt_contradiction"
EVIDENCE_LEVELS = (
    F0_NEUTRAL_RECHECK,
    F1_CHECKLIST,
    F2_AUDITED_VALUES,
    F3_OUTCOME_CONTRADICTION,
    F3_PRE_REATTEMPT_CONTRADICTION,
)
OUTCOME_FEEDBACK_LEVELS = frozenset(
    {F3_OUTCOME_CONTRADICTION, F3_PRE_REATTEMPT_CONTRADICTION}
)
AGENT_CROSS_CHECKED_NONREPORTABLE = "agent_cross_checked_nonreportable"
EVIDENCE_REVIEW_STATUSES = frozenset(
    {"not_applicable", "approved", AGENT_CROSS_CHECKED_NONREPORTABLE}
)
EVIDENCE_REVIEW_REGIMES = {
    F0_NEUTRAL_RECHECK: "neutral_recheck",
    F1_CHECKLIST: "checklist_recheck",
    F2_AUDITED_VALUES: "evidence_assisted_recheck",
    F3_OUTCOME_CONTRADICTION: "outcome_feedback",
    F3_PRE_REATTEMPT_CONTRADICTION: "pre_reattempt_outcome_feedback",
}

REPLICATION_CONTRAST = "replication"
WORKFLOW_CONTRAST = "workflow"
HISTORY_CONTRAST = "history"
REFLECTION_TRAINING_CONTRAST = "reflection_training"
DESCRIPTIVE_SYSTEM_CONTRAST = "descriptive_system"
CONTRAST_AXES = frozenset(
    {
        REPLICATION_CONTRAST,
        WORKFLOW_CONTRAST,
        HISTORY_CONTRAST,
        REFLECTION_TRAINING_CONTRAST,
        DESCRIPTIVE_SYSTEM_CONTRAST,
    }
)

UI_SELECTION_EVENT = "ui_selection"
SCREENSHOT_OBSERVATION_EVENT = "screenshot_observation"
UI_REVERSAL_EVENT = "ui_reversal"
OUTCOME_VALIDATION_EVENT = "outcome_validation"
SUBMISSION_EVENT = "submission"
SCORER_RESULT_EVENT = "scorer_result"
INTERFACE_CENSOR_EVENT = "interface_censor"
MODEL_ONLY_EVENT_TYPES = frozenset(
    {"model_thought", "model_message", "natural_language"}
)
REVIEW_STATE = "review"
FINAL_REVIEW_STATE = "final_review"
INITIAL_DECISION_STATE = "initial_decision"
RETRY_DECISION_STATE = "retry_decision"
EVENT_IDENTITY_FIELDS = (
    "run_id",
    "trial_id",
    "pair_group_id",
    "task_instance_id",
    "arm",
    "condition",
)
_COMMON_EVENT_FIELDS = frozenset(
    {"event_index", "event_type", "source", *EVENT_IDENTITY_FIELDS}
)
_EVENT_SPECIFIC_FIELDS = {
    UI_SELECTION_EVENT: frozenset(
        {
            "action_id",
            "choice_token",
            "control_position",
            "decision_state",
            "input_artifact_path",
            "input_model_step_id",
            "rendered_task_instance_id",
            "rendered_chart_path",
            "rendered_ui_variant",
            "rendered_retry_presentation",
            "rendered_feedback_spec_id",
            "rendered_evidence_record_id",
            "rendered_outcome_record_id",
            "rendered_outcome_contradiction",
            "rendered_provisional_action_id",
            "rendered_provisional_choice_token",
            "rendered_provisional_control_position",
            "rendered_display_tokens",
            "renderer_build_id",
            "viewport_width",
            "viewport_height",
            "model_response_id",
            "execution_receipt_id",
            "caused_by_model_step_id",
        }
    ),
    SCREENSHOT_OBSERVATION_EVENT: frozenset(
        {
            "observed_state",
            "artifact_path",
            "model_step_id",
            "feedback_spec_id",
            "rendered_evidence_record_id",
            "rendered_outcome_record_id",
            "rendered_outcome_contradiction",
            "rendered_provisional_action_id",
            "rendered_provisional_choice_token",
            "rendered_provisional_control_position",
            "rendered_task_instance_id",
            "rendered_chart_path",
            "rendered_ui_variant",
            "renderer_build_id",
            "viewport_width",
            "viewport_height",
        }
    ),
    UI_REVERSAL_EVENT: frozenset(
        {
            "action_type",
            "from_state",
            "to_state",
            "model_response_id",
            "execution_receipt_id",
            "caused_by_model_step_id",
        }
    ),
    OUTCOME_VALIDATION_EVENT: frozenset(
        {
            "provisional_action_id",
            "provisional_choice_token",
            "provisional_control_position",
            "outcome_record_id",
            "contradiction",
        }
    ),
    SUBMISSION_EVENT: frozenset(
        {
            "submitted_action_id",
            "submitted_choice_token",
            "submitted_control_position",
            "submission_id",
            "model_response_id",
            "execution_receipt_id",
            "caused_by_model_step_id",
        }
    ),
    SCORER_RESULT_EVENT: frozenset(
        {"submission_id", "scorer_record_id", "success"}
    ),
    INTERFACE_CENSOR_EVENT: frozenset({"reason"}),
    **{event_type: frozenset({"text"}) for event_type in MODEL_ONLY_EVENT_TYPES},
}


class TraceReductionError(ValueError):
    """Raised when an append-only runner trace is malformed or unverifiable."""


def choice_role(
    selected_action_id: str | None,
    *,
    correct_action_id: str,
    misleading_action_ids: tuple[str, ...] | list[str],
    neutral_action_ids: tuple[str, ...] | list[str] = (),
) -> str:
    """Classify one UI-recorded action id without interpreting model text."""

    if selected_action_id is None:
        return NO_CHOICE
    if selected_action_id == correct_action_id:
        return CORRECT
    if selected_action_id in misleading_action_ids:
        return MISLEADING
    if selected_action_id in neutral_action_ids:
        return NEUTRAL
    return UNKNOWN


@dataclass(frozen=True)
class RecoveryRun:
    """One runner-side targeted-recovery trajectory.

    ``condition`` is deliberately an opaque experiment label.  In particular,
    this schema does not equate a temporal-history or reset ablation with a
    hypothetical "no GUI-Reflection" model.

    For natural recovery, ``initial_selected_action_id`` must be the actual
    provisional choice captured by the UI.  For a standardized-mistake probe,
    the runner-provided prior mistake belongs in
    ``injected_mistake_action_id`` and is never counted as agent behavior.
    """

    run_id: str
    trial_id: str
    pair_group_id: str
    condition: str
    arm: str
    task_id: str
    task_instance_id: str
    chart_path: str
    display_tokens: tuple[str, ...]
    choice_token_to_action_id: tuple[tuple[str, str], ...]
    correct_action_id: str
    misleading_action_ids: tuple[str, ...]
    checkpoint_id: str
    checkpoint_stage: str
    reflection_training_status: str
    history_mode: str
    workflow_mode: str
    renderer_build_id: str
    viewport_width: int
    viewport_height: int
    training_recipe_match_id: str | None = None
    training_recipe_review_status: str = "not_applicable"
    training_recipe_reviewed_by: str | None = None
    training_recipe_reviewed_at: str | None = None
    neutral_action_ids: tuple[str, ...] = ()
    recovery_branch: str = NATURAL_RECOVERY
    evidence_level: str | None = F0_NEUTRAL_RECHECK
    evidence_record_id: str | None = None
    evidence_source: str | None = None
    evidence_review_status: str = "not_applicable"
    evidence_reviewed_by: str | None = None
    evidence_reviewed_at: str | None = None
    review_regime: str = "neutral_recheck"
    retry_presentation: str = CURRENT_VISIBLE_RETRY
    ui_variant: str = "compact_recovery"
    display_order: tuple[str, ...] = ()
    initial_selected_action_id: str | None = None
    injected_mistake_action_id: str | None = None
    feedback_observed: bool = False
    contradiction_recognized: bool | None = None
    outcome_validation_observed: bool = False
    outcome_validated_action_ids: tuple[str, ...] = ()
    outcome_record_ids: tuple[str, ...] = ()
    outcome_contradictions: tuple[bool, ...] = ()
    actual_reversal_action_type: str | None = None
    reversal_returned_to_retry: bool | None = None
    reversal_from_state: str | None = None
    reversal_to_state: str | None = None
    post_review_selected_action_ids: tuple[str, ...] = ()
    final_review_observed: bool = False
    final_selected_action_id: str | None = None
    final_submission_observed: bool = False
    submission_id: str | None = None
    scorer_result_observed: bool = False
    scorer_record_id: str | None = None
    final_submission_success: bool | None = None
    interface_censored: bool = False
    error_attribution: str | None = None
    event_trace_reduced: bool = False
    trace_event_count: int = 0
    trace_last_event_index: int | None = None
    observed_artifact_paths: tuple[str, ...] = ()
    observed_model_step_ids: tuple[str, ...] = ()
    observed_model_response_ids: tuple[str, ...] = ()
    observed_execution_receipt_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "misleading_action_ids", tuple(self.misleading_action_ids)
        )
        object.__setattr__(self, "neutral_action_ids", tuple(self.neutral_action_ids))
        object.__setattr__(self, "display_order", tuple(self.display_order))
        object.__setattr__(self, "display_tokens", tuple(self.display_tokens))
        object.__setattr__(
            self,
            "choice_token_to_action_id",
            tuple(tuple(item) for item in self.choice_token_to_action_id),
        )
        object.__setattr__(
            self,
            "post_review_selected_action_ids",
            tuple(self.post_review_selected_action_ids),
        )
        object.__setattr__(
            self,
            "outcome_validated_action_ids",
            tuple(self.outcome_validated_action_ids),
        )
        object.__setattr__(self, "outcome_record_ids", tuple(self.outcome_record_ids))
        object.__setattr__(
            self, "outcome_contradictions", tuple(self.outcome_contradictions)
        )
        object.__setattr__(
            self, "observed_artifact_paths", tuple(self.observed_artifact_paths)
        )
        object.__setattr__(
            self, "observed_model_step_ids", tuple(self.observed_model_step_ids)
        )
        object.__setattr__(
            self,
            "observed_model_response_ids",
            tuple(self.observed_model_response_ids),
        )
        object.__setattr__(
            self,
            "observed_execution_receipt_ids",
            tuple(self.observed_execution_receipt_ids),
        )
        if not self.run_id:
            raise ValueError("run_id must be non-empty")
        if not self.trial_id:
            raise ValueError("trial_id must be non-empty")
        if not self.pair_group_id:
            raise ValueError("pair_group_id must be non-empty")
        if not self.condition:
            raise ValueError("condition must be non-empty")
        if not self.arm:
            raise ValueError("arm must be non-empty")
        if self.arm not in ARMS:
            raise ValueError(f"unknown arm {self.arm!r}; choose one of {sorted(ARMS)}")
        for field_name in ("task_id", "task_instance_id", "chart_path"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")
        if not self.correct_action_id:
            raise ValueError("correct_action_id must be non-empty")
        for field_name in (
            "checkpoint_id",
            "checkpoint_stage",
            "reflection_training_status",
            "history_mode",
            "workflow_mode",
            "renderer_build_id",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")
        for field_name in ("viewport_width", "viewport_height"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.recovery_branch not in RECOVERY_BRANCHES:
            raise ValueError(
                f"unknown recovery_branch {self.recovery_branch!r}; "
                f"choose one of {sorted(RECOVERY_BRANCHES)}"
            )
        if not self.review_regime:
            raise ValueError("review_regime must be non-empty")
        if self.evidence_level is not None and self.evidence_level not in EVIDENCE_LEVELS:
            raise ValueError(
                f"unknown evidence_level {self.evidence_level!r}; "
                f"choose one of {list(EVIDENCE_LEVELS)}"
            )
        if self.evidence_review_status not in EVIDENCE_REVIEW_STATUSES:
            raise ValueError(
                f"unknown evidence_review_status {self.evidence_review_status!r}; "
                f"choose one of {sorted(EVIDENCE_REVIEW_STATUSES)}"
            )
        if not self.training_recipe_review_status:
            raise ValueError("training_recipe_review_status must be non-empty")
        if self.training_recipe_review_status == "approved":
            if not self.training_recipe_match_id:
                raise ValueError(
                    "approved training recipe requires training_recipe_match_id"
                )
            if not self.training_recipe_reviewed_by:
                raise ValueError(
                    "approved training recipe requires training_recipe_reviewed_by"
                )
            if not self.training_recipe_reviewed_at:
                raise ValueError(
                    "approved training recipe requires training_recipe_reviewed_at"
                )
        is_f2 = self.evidence_level == F2_AUDITED_VALUES
        if is_f2 and not self.evidence_record_id:
            raise ValueError("F2 evidence requires evidence_record_id")
        if not is_f2 and self.evidence_record_id is not None:
            raise ValueError("evidence_record_id is reserved for F2 evidence")
        resolved_f2_statuses = {
            "approved",
            AGENT_CROSS_CHECKED_NONREPORTABLE,
        }
        if is_f2 and self.evidence_source is not None:
            if self.evidence_review_status not in resolved_f2_statuses:
                raise ValueError(
                    "resolved F2 evidence requires reviewed provenance"
                )
        if self.evidence_review_status in resolved_f2_statuses:
            if not is_f2 or not self.evidence_source:
                raise ValueError(
                    "reviewed evidence provenance is reserved for resolved F2 records"
                )
            if not self.evidence_reviewed_by:
                raise ValueError("reviewed evidence requires evidence_reviewed_by")
            if not self.evidence_reviewed_at:
                raise ValueError("reviewed evidence requires evidence_reviewed_at")
        if self.workflow_mode not in WORKFLOW_MODES:
            raise ValueError(
                f"unknown workflow_mode {self.workflow_mode!r}; "
                f"choose one of {sorted(WORKFLOW_MODES)}"
            )
        if self.workflow_mode == SINGLE_ATTEMPT:
            if self.evidence_level is not None or self.evidence_record_id is not None:
                raise ValueError(
                    "single_attempt requires evidence_level=None and no evidence record"
                )
            if self.review_regime != "not_applicable":
                raise ValueError(
                    "single_attempt requires review_regime='not_applicable'"
                )
        else:
            if self.evidence_level is None:
                raise ValueError("feedback_retry requires an evidence_level")
            expected_regime = EVIDENCE_REVIEW_REGIMES[self.evidence_level]
            if self.review_regime != expected_regime:
                raise ValueError(
                    f"{self.evidence_level} requires review_regime="
                    f"{expected_regime!r}"
                )
        if self.outcome_validation_observed:
            if self.evidence_level not in OUTCOME_FEEDBACK_LEVELS:
                raise ValueError("outcome validation is reserved for outcome feedback")
            outcome_lengths = {
                len(self.outcome_validated_action_ids),
                len(self.outcome_record_ids),
                len(self.outcome_contradictions),
            }
            if outcome_lengths == {0} or len(outcome_lengths) != 1:
                raise ValueError(
                    "observed outcome validation requires aligned non-empty records"
                )
            if any(not value for value in self.outcome_validated_action_ids):
                raise ValueError("validated outcome action ids must be non-empty")
            if any(not value for value in self.outcome_record_ids):
                raise ValueError("outcome record ids must be non-empty")
            if len(self.outcome_record_ids) != len(set(self.outcome_record_ids)):
                raise ValueError("outcome record ids must be unique within a run")
            if any(not isinstance(value, bool) for value in self.outcome_contradictions):
                raise ValueError("outcome contradictions must be boolean")
        elif (
            self.outcome_validated_action_ids
            or self.outcome_record_ids
            or self.outcome_contradictions
        ):
            raise ValueError(
                "outcome records require observed validation"
            )
        if (
            self.event_trace_reduced
            and self.evidence_level in OUTCOME_FEEDBACK_LEVELS
            and not self.outcome_validation_observed
        ):
            raise ValueError(
                "event-derived outcome feedback requires independent validation"
            )
        if self.retry_presentation not in RETRY_PRESENTATIONS:
            raise ValueError(
                f"unknown retry_presentation {self.retry_presentation!r}; "
                f"choose one of {sorted(RETRY_PRESENTATIONS)}"
            )

        role_lists = (
            ("misleading", self.misleading_action_ids),
            ("neutral", self.neutral_action_ids),
        )
        for name, values in role_lists:
            if any(not value for value in values):
                raise ValueError(f"{name} action ids must be non-empty")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} action ids must be unique")
        if self.correct_action_id in self.misleading_action_ids:
            raise ValueError("correct action cannot also be misleading")
        if self.correct_action_id in self.neutral_action_ids:
            raise ValueError("correct action cannot also be neutral")
        overlap = set(self.misleading_action_ids) & set(self.neutral_action_ids)
        if overlap:
            raise ValueError(
                f"misleading and neutral action ids overlap: {sorted(overlap)}"
            )

        known_actions = {
            self.correct_action_id,
            *self.misleading_action_ids,
            *self.neutral_action_ids,
        }
        if self.display_order:
            if len(self.display_order) != len(set(self.display_order)):
                raise ValueError("display_order must not contain duplicates")
            if set(self.display_order) != known_actions:
                raise ValueError(
                    "display_order must contain each scored action exactly once"
                )
        if (
            not self.display_tokens
            or len(self.display_tokens) != len(set(self.display_tokens))
            or any(not token for token in self.display_tokens)
        ):
            raise ValueError("display_tokens must be non-empty and unique")
        token_pairs = self.choice_token_to_action_id
        if any(
            len(pair) != 2
            or not isinstance(pair[0], str)
            or not pair[0]
            or not isinstance(pair[1], str)
            or not pair[1]
            for pair in token_pairs
        ):
            raise ValueError("choice token mapping must contain string pairs")
        token_map = dict(token_pairs)
        if len(token_map) != len(token_pairs):
            raise ValueError("choice token mapping contains duplicate tokens")
        if tuple(token_map) != self.display_tokens:
            raise ValueError("choice token mapping order must match display_tokens")
        if tuple(token_map.values()) != self.display_order:
            raise ValueError("choice token mapping must match canonical display_order")

        if self.recovery_branch == NATURAL_RECOVERY:
            if self.injected_mistake_action_id is not None:
                raise ValueError(
                    "natural recovery cannot have an injected mistake action"
                )
        else:
            if self.initial_selected_action_id is not None:
                raise ValueError(
                    "standardized-mistake probes cannot report the injected "
                    "choice as an actual initial selection"
                )
            if self.injected_mistake_action_id is None:
                raise ValueError(
                    "standardized-mistake probes require injected_mistake_action_id"
                )
            if self.workflow_mode != FEEDBACK_RETRY:
                raise ValueError(
                    "standardized-mistake probes require feedback_retry workflow"
                )
        if any(not action_id for action_id in self.post_review_selected_action_ids):
            raise ValueError(
                "post-review action ids must be non-empty"
            )
        if self.workflow_mode == SINGLE_ATTEMPT and (
            self.feedback_observed
            or self.reversal_returned_to_retry is not None
            or self.actual_reversal_action_type is not None
            or self.post_review_selected_action_ids
            or self.final_review_observed
        ):
            raise ValueError(
                "single_attempt cannot contain review or retry events"
            )
        if self.reversal_returned_to_retry is True and (
            self.actual_reversal_action_type not in REVERSAL_ACTION_TYPES
        ):
            raise ValueError(
                "an effective reversal requires PRESS_BACK or REVISE_SELECTION"
            )
        reversal_states = (self.reversal_from_state, self.reversal_to_state)
        if any(state is not None for state in reversal_states) and not all(
            state is not None for state in reversal_states
        ):
            raise ValueError("reversal from/to states must be recorded together")
        if self.actual_reversal_action_type is None and any(
            state is not None for state in reversal_states
        ):
            raise ValueError("reversal states require an observed reversal action")
        if self.event_trace_reduced:
            if self.trace_event_count <= 0:
                raise ValueError("an event-derived summary requires a non-empty trace")
            if self.trace_last_event_index != self.trace_event_count - 1:
                raise ValueError(
                    "event-derived trace metadata must cover contiguous indexes from 0"
                )
            if self.actual_reversal_action_type is not None and not all(
                state is not None for state in reversal_states
            ):
                raise ValueError(
                    "event-derived reversals require explicit from/to states"
                )
            if (self.feedback_observed or self.final_review_observed) and not (
                self.observed_artifact_paths and self.observed_model_step_ids
            ):
                raise ValueError(
                    "event-derived screenshot observations require artifacts "
                    "and model step ids"
                )
        elif self.trace_event_count or self.trace_last_event_index is not None:
            raise ValueError("trace metadata requires event_trace_reduced=True")
        if (
            self.final_submission_success is not None
            and not self.final_submission_observed
        ):
            raise ValueError(
                "submission success cannot be known without an observed submission"
            )
        if self.final_submission_observed and not self.submission_id:
            raise ValueError("an observed submission requires submission_id")
        if self.submission_id is not None and not self.final_submission_observed:
            raise ValueError("submission_id requires an observed submission")
        if (
            self.final_submission_success is not None
            and not isinstance(self.final_submission_success, bool)
        ):
            raise ValueError("submission success must be boolean when present")
        if self.scorer_result_observed:
            if not self.final_submission_observed or not self.submission_id:
                raise ValueError("scorer result requires an observed submission")
            if not self.scorer_record_id:
                raise ValueError("scorer result requires scorer_record_id")
            if self.final_submission_success is None:
                raise ValueError("observed scorer result requires boolean success")
        elif self.final_submission_success is not None:
            raise ValueError(
                "submission success requires a separate observed scorer result"
            )
        elif self.scorer_record_id is not None:
            raise ValueError("scorer_record_id requires an observed scorer result")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable runner record."""

        row = asdict(self)
        for key in (
            "misleading_action_ids",
            "neutral_action_ids",
            "display_order",
            "display_tokens",
            "choice_token_to_action_id",
            "outcome_validated_action_ids",
            "outcome_record_ids",
            "outcome_contradictions",
            "post_review_selected_action_ids",
            "observed_artifact_paths",
            "observed_model_step_ids",
            "observed_model_response_ids",
            "observed_execution_receipt_ids",
        ):
            row[key] = list(row[key])
        return row


def _required_nonempty_string(
    record: Mapping[str, Any], field_name: str, record_kind: str
) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"{record_kind} requires a non-empty string {field_name!r}"
        )
    return value


def _validated_iso_date(value: str, field_name: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO calendar date") from exc
    if parsed > date.today():
        raise ValueError(f"{field_name} cannot be in the future")
    return value


class TargetedRecoveryRegistry:
    """Canonical binding boundary for structural targeted-recovery analysis.

    The registry is constructed by the runner from canonical case manifests,
    a preregistered condition table, and separately reviewed F2/training
    records.  Run callers may identify a pair, arm, condition, and approved
    record, but cannot define action roles, model lineage, or review approval.
    This is a data-binding boundary, not authentication.  The future collector
    must own authoritative registry loading and event construction before any
    result can become experiment-reportable.
    """

    _EVIDENCE_PROVENANCE_FIELDS = frozenset(
        {
            "evidence_source",
            "evidence_review_status",
            "evidence_reviewed_by",
            "evidence_reviewed_at",
        }
    )
    _TRAINING_PROVENANCE_FIELDS = frozenset(
        {
            "training_recipe_review_status",
            "training_recipe_reviewed_by",
            "training_recipe_reviewed_at",
        }
    )

    def __init__(
        self,
        *,
        repository_root: str | os.PathLike[str],
        cases: Iterable[Mapping[str, Any]],
        conditions: Iterable[Mapping[str, Any]],
        contrasts: Iterable[Mapping[str, Any]] = (),
        approved_evidence_records: Iterable[Mapping[str, Any]] = (),
        approved_training_recipe_records: Iterable[Mapping[str, Any]] = (),
    ) -> None:
        self._cases: dict[str, dict[str, Any]] = {}
        self._conditions: dict[str, dict[str, Any]] = {}
        self._contrasts: dict[str, dict[str, str]] = {}
        self._evidence_records: dict[str, dict[str, Any]] = {}
        self._training_records: dict[str, dict[str, Any]] = {}
        self._repository_root = Path(repository_root).resolve()
        if not self._repository_root.is_dir():
            raise ValueError("registry repository_root must be an existing directory")

        for raw_case in cases:
            self._register_case(raw_case)
        if not self._cases:
            raise ValueError("targeted recovery registry requires canonical cases")
        for raw_condition in conditions:
            self._register_condition(raw_condition)
        if not self._conditions:
            raise ValueError("targeted recovery registry requires conditions")
        for raw_contrast in contrasts:
            self._register_contrast(raw_contrast)
        for raw_record in approved_evidence_records:
            self._register_evidence(raw_record)
        for raw_record in approved_training_recipe_records:
            self._register_training_recipe(raw_record)

    def _register_case(self, raw_case: Mapping[str, Any]) -> None:
        if raw_case.get("record_type") != "targeted_recovery_case":
            raise ValueError("canonical case has wrong record_type")
        pair_group_id = _required_nonempty_string(
            raw_case, "pair_group_id", "canonical case"
        )
        if pair_group_id in self._cases:
            raise ValueError(f"duplicate canonical pair_group_id {pair_group_id!r}")
        arms = raw_case.get("arms")
        model_visible_shared = raw_case.get("model_visible_shared")
        runner_only = raw_case.get("runner_only")
        source_references = raw_case.get("source_references")
        if not isinstance(arms, Mapping) or set(arms) != ARMS:
            raise ValueError(
                f"canonical case {pair_group_id!r} must contain official and clean arms"
            )
        if not isinstance(runner_only, Mapping):
            raise ValueError(f"canonical case {pair_group_id!r} has no runner_only data")
        if not isinstance(model_visible_shared, Mapping):
            raise ValueError(
                f"canonical case {pair_group_id!r} has no model_visible_shared data"
            )
        if not isinstance(source_references, Mapping) or set(source_references) != ARMS:
            raise ValueError(
                f"canonical case {pair_group_id!r} requires source refs for both arms"
            )
        correct = _required_nonempty_string(
            runner_only, "expected_action_id", "canonical case"
        )
        misleading_raw = runner_only.get("misleading_action_ids")
        neutral_raw = runner_only.get("neutral_action_ids")
        display_raw = runner_only.get("display_order")
        choice_map_raw = runner_only.get("choice_token_to_action_id")
        visible_cards_raw = model_visible_shared.get("action_cards")
        if not isinstance(misleading_raw, (list, tuple)) or not misleading_raw:
            raise ValueError("canonical case requires misleading_action_ids")
        if not isinstance(neutral_raw, (list, tuple)):
            raise ValueError("canonical case requires neutral_action_ids")
        if not isinstance(display_raw, (list, tuple)) or not display_raw:
            raise ValueError("canonical case requires display_order")
        if not isinstance(choice_map_raw, Mapping) or not choice_map_raw:
            raise ValueError("canonical case requires choice_token_to_action_id")
        if not isinstance(visible_cards_raw, (list, tuple)) or not visible_cards_raw:
            raise ValueError("canonical case requires model-visible action cards")
        misleading = tuple(misleading_raw)
        neutral = tuple(neutral_raw)
        display = tuple(display_raw)
        if any(not isinstance(value, str) or not value for value in (*misleading, *neutral, *display)):
            raise ValueError("canonical action ids must be non-empty strings")
        action_ids = {correct, *misleading, *neutral}
        if len(action_ids) != 1 + len(misleading) + len(neutral):
            raise ValueError("canonical action role sets overlap or contain duplicates")
        if len(display) != len(set(display)) or set(display) != action_ids:
            raise ValueError("canonical display_order does not match action roles")
        display_tokens: list[str] = []
        for card in visible_cards_raw:
            if not isinstance(card, Mapping) or set(card) != {
                "choice_token",
                "label",
            }:
                raise ValueError(
                    "canonical model-visible action cards require token and label"
                )
            display_tokens.append(
                _required_nonempty_string(card, "choice_token", "visible action card")
            )
            _required_nonempty_string(card, "label", "visible action card")
        if len(display_tokens) != len(set(display_tokens)):
            raise ValueError("canonical visible choice tokens must be unique")
        if set(choice_map_raw) != set(display_tokens):
            raise ValueError("canonical choice token mapping does not match visible cards")
        choice_map: list[tuple[str, str]] = []
        for token in display_tokens:
            action_id = choice_map_raw[token]
            if not isinstance(action_id, str) or not action_id:
                raise ValueError("canonical choice mapping has an invalid action id")
            choice_map.append((token, action_id))
        if tuple(action_id for _, action_id in choice_map) != display:
            raise ValueError(
                "canonical visible token order does not match display_order"
            )
        canonical_arms: dict[str, dict[str, str]] = {}
        for arm in sorted(ARMS):
            arm_record = arms[arm]
            if not isinstance(arm_record, Mapping) or set(arm_record) != {
                "task_id",
                "task_instance_id",
                "chart_path",
            }:
                raise ValueError(
                    f"canonical {arm} arm requires task_id, task_instance_id, chart_path"
                )
            task_id = _required_nonempty_string(
                arm_record, "task_id", f"canonical {arm} arm"
            )
            task_instance_id = _required_nonempty_string(
                arm_record, "task_instance_id", f"canonical {arm} arm"
            )
            chart_value = _required_nonempty_string(
                arm_record, "chart_path", f"canonical {arm} arm"
            )
            chart = Path(chart_value)
            resolved_chart = (
                chart.resolve()
                if chart.is_absolute()
                else (self._repository_root / chart).resolve()
            )
            try:
                portable_chart = resolved_chart.relative_to(
                    self._repository_root
                ).as_posix()
            except ValueError as exc:
                raise ValueError("canonical chart escapes repository_root") from exc
            if not resolved_chart.is_file():
                raise ValueError(
                    f"canonical chart does not exist: {portable_chart}"
                )
            canonical_arms[arm] = {
                "task_id": task_id,
                "task_instance_id": task_instance_id,
                "chart_path": portable_chart,
            }
        canonical_source_refs: dict[str, str] = {}
        for arm in sorted(ARMS):
            source_ref = source_references[arm]
            if not isinstance(source_ref, Mapping) or set(source_ref) != {
                "path",
                "line",
            }:
                raise ValueError("canonical source reference has a schema mismatch")
            source_value = _required_nonempty_string(
                source_ref, "path", "canonical source reference"
            )
            source_path = Path(source_value)
            resolved_source = (
                source_path.resolve()
                if source_path.is_absolute()
                else (self._repository_root / source_path).resolve()
            )
            try:
                portable_source = resolved_source.relative_to(
                    self._repository_root
                ).as_posix()
            except ValueError as exc:
                raise ValueError(
                    "canonical source reference escapes repository_root"
                ) from exc
            if not resolved_source.is_file():
                raise ValueError(
                    f"canonical source reference does not exist: {portable_source}"
                )
            line = source_ref.get("line")
            if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
                raise ValueError("canonical source line must be a positive integer")
            canonical_source_refs[arm] = f"{portable_source}#line:{line}"

        self._cases[pair_group_id] = {
            "correct_action_id": correct,
            "misleading_action_ids": misleading,
            "neutral_action_ids": neutral,
            "display_order": display,
            "display_tokens": tuple(display_tokens),
            "choice_token_to_action_id": tuple(choice_map),
            "arm_records": canonical_arms,
            "canonical_source_refs": canonical_source_refs,
        }

    def _register_condition(self, raw_condition: Mapping[str, Any]) -> None:
        fields = (
            "condition_id",
            "checkpoint_id",
            "checkpoint_stage",
            "reflection_training_status",
            "history_mode",
            "workflow_mode",
            "renderer_build_id",
            "viewport_width",
            "viewport_height",
            "ui_variant",
        )
        if set(raw_condition) != set(fields):
            raise ValueError(
                "condition record schema mismatch; "
                f"missing={sorted(set(fields) - set(raw_condition))}, "
                f"unknown={sorted(set(raw_condition) - set(fields))}"
            )
        string_fields = set(fields) - {
            "viewport_width",
            "viewport_height",
        }
        values: dict[str, Any] = {
            field: _required_nonempty_string(
                raw_condition, field, "condition record"
            )
            for field in string_fields
        }
        for field in ("viewport_width", "viewport_height"):
            value = raw_condition.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"condition record requires positive integer {field}")
            values[field] = value
        condition_id = values.pop("condition_id")
        if condition_id in self._conditions:
            raise ValueError(f"duplicate condition_id {condition_id!r}")
        if values["workflow_mode"] not in WORKFLOW_MODES:
            raise ValueError(
                f"condition {condition_id!r} has unknown workflow_mode"
            )
        self._conditions[condition_id] = values

    def _register_agent_cross_checked_evidence(
        self, raw_record: Mapping[str, Any]
    ) -> None:
        """Validate the non-reportable env008 F2 diagnostic against source CSVs."""

        record_kind = "agent-cross-checked F2 diagnostic record"
        record_id = _required_nonempty_string(raw_record, "record_id", record_kind)
        pair_group_id = _required_nonempty_string(
            raw_record, "pair_group_id", record_kind
        )
        if pair_group_id not in self._cases:
            raise ValueError(f"evidence record has unknown pair {pair_group_id!r}")
        if raw_record.get("evidence_level") != F2_AUDITED_VALUES:
            raise ValueError("agent-reviewed diagnostic uses the F2 protocol slot")
        if raw_record.get("evidence_kind") != "agent-reviewed diagnostic evidence":
            raise ValueError("F2 diagnostic has the wrong evidence_kind")
        if raw_record.get("review_status") != "agent_cross_checked":
            raise ValueError("F2 diagnostic requires agent_cross_checked status")
        if raw_record.get("reportable") is not False:
            raise ValueError("F2 diagnostic must be explicitly non-reportable")
        expected_method = (
            "cross-check canonical official/clean task rows, CSV files, and figure assets"
        )
        if raw_record.get("review_method") != expected_method:
            raise ValueError("F2 diagnostic review_method is not the declared cross-check")
        reviewed_by = raw_record.get("reviewed_by")
        if reviewed_by != ["/root", "/root/env008_sample_designer"]:
            raise ValueError("F2 diagnostic requires the two declared agent reviewers")
        reviewed_at = _validated_iso_date(
            _required_nonempty_string(raw_record, "reviewed_at", record_kind),
            "evidence reviewed_at",
        )

        case = self._cases[pair_group_id]
        expected_refs: dict[tuple[str, str], tuple[str, str]] = {}
        for arm in sorted(ARMS):
            task_ref = str(case["canonical_source_refs"][arm])
            task_path, task_locator = task_ref.rsplit("#", 1)
            figure_path = str(case["arm_records"][arm]["chart_path"])
            csv_path = Path(figure_path).with_name("source.csv").as_posix()
            expected_refs[(arm, "task_row")] = (task_path, task_locator)
            expected_refs[(arm, "csv")] = (
                csv_path,
                "rows:Solar,Wind,Hydroelectric",
            )
            expected_refs[(arm, "figure")] = (figure_path, "full_asset")

        source_refs = raw_record.get("source_refs")
        if not isinstance(source_refs, list) or len(source_refs) != len(expected_refs):
            raise ValueError(
                "F2 diagnostic requires task-row, CSV, and figure refs for both arms"
            )
        normalized_refs: dict[tuple[str, str], tuple[str, str]] = {}
        for source_ref in source_refs:
            if not isinstance(source_ref, Mapping) or set(source_ref) != {
                "arm",
                "artifact_kind",
                "artifact_path",
                "record_locator",
            }:
                raise ValueError("F2 diagnostic source ref has a schema mismatch")
            arm = _required_nonempty_string(source_ref, "arm", "F2 source ref")
            artifact_kind = _required_nonempty_string(
                source_ref, "artifact_kind", "F2 source ref"
            )
            key = (arm, artifact_kind)
            if key not in expected_refs or key in normalized_refs:
                raise ValueError("F2 diagnostic source refs are incomplete or duplicated")
            artifact_value = _required_nonempty_string(
                source_ref, "artifact_path", "F2 source ref"
            )
            artifact = Path(artifact_value)
            resolved = (
                artifact.resolve()
                if artifact.is_absolute()
                else (self._repository_root / artifact).resolve()
            )
            try:
                portable = resolved.relative_to(self._repository_root).as_posix()
            except ValueError as exc:
                raise ValueError("F2 diagnostic source escapes repository_root") from exc
            if not resolved.is_file():
                raise ValueError(f"F2 diagnostic source does not exist: {portable}")
            locator = _required_nonempty_string(
                source_ref, "record_locator", "F2 source ref"
            )
            normalized_refs[key] = (portable, locator)
        if normalized_refs != expected_refs:
            raise ValueError(
                "F2 diagnostic refs must exactly bind canonical task rows, CSVs, and figures"
            )

        csv_values: dict[str, dict[str, str]] = {}
        required_subjects = ("Solar", "Wind", "Hydroelectric")
        for arm in sorted(ARMS):
            csv_path = self._repository_root / expected_refs[(arm, "csv")][0]
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            values = {
                str(row.get("energy_source")): str(row.get("production_percentage"))
                for row in rows
                if row.get("energy_source") in required_subjects
            }
            if set(values) != set(required_subjects):
                raise ValueError("F2 diagnostic CSV lacks a required env008 subject")
            csv_values[arm] = {
                subject: f"{float(values[subject]):.1f}%"
                for subject in required_subjects
            }
        if csv_values[OFFICIAL_ARM] != csv_values[CLEAN_ARM]:
            raise ValueError("official and clean source CSV facts disagree")

        payload = raw_record.get("model_visible_payload")
        if not isinstance(payload, Mapping) or set(payload) != {"heading", "facts"}:
            raise ValueError("F2 diagnostic visible payload has a schema mismatch")
        if payload.get("heading") != "Reviewed source values":
            raise ValueError("F2 diagnostic has the wrong visible heading")
        facts = payload.get("facts")
        if not isinstance(facts, list) or len(facts) != len(required_subjects):
            raise ValueError("F2 diagnostic requires exactly three visible facts")
        fact_values: dict[str, str] = {}
        for fact in facts:
            if not isinstance(fact, Mapping) or set(fact) != {
                "subject",
                "relation",
                "object",
            }:
                raise ValueError("F2 diagnostic visible fact has a schema mismatch")
            subject = _required_nonempty_string(fact, "subject", "F2 fact")
            if fact.get("relation") != "reported production percentage":
                raise ValueError("F2 diagnostic fact has the wrong relation")
            value = _required_nonempty_string(fact, "object", "F2 fact")
            if subject in fact_values:
                raise ValueError("F2 diagnostic repeats a visible subject")
            fact_values[subject] = value
        if fact_values != csv_values[OFFICIAL_ARM]:
            raise ValueError("F2 diagnostic visible facts do not match canonical CSV rows")

        task_refs = [
            {
                "arm": arm,
                "artifact_path": expected_refs[(arm, "task_row")][0],
                "record_locator": expected_refs[(arm, "task_row")][1],
            }
            for arm in sorted(ARMS)
        ]
        # Reuse the legacy F2 payload/leakage validator, then replace its
        # provenance with the stronger diagnostic metadata.
        self._register_evidence(
            {
                "record_id": record_id,
                "pair_group_id": pair_group_id,
                "evidence_level": F2_AUDITED_VALUES,
                "source_refs": task_refs,
                "review_status": "approved",
                "reviewed_by": ";".join(reviewed_by),
                "reviewed_at": reviewed_at,
                "model_visible_payload": payload,
            }
        )
        stored = self._evidence_records[record_id]
        stored.update(
            evidence_kind="agent-reviewed diagnostic evidence",
            evidence_source=";".join(
                f"{arm}:{kind}:{path}#{locator}"
                for (arm, kind), (path, locator) in sorted(normalized_refs.items())
            ),
            evidence_review_status=AGENT_CROSS_CHECKED_NONREPORTABLE,
            evidence_reviewed_by=";".join(reviewed_by),
            evidence_reviewed_at=reviewed_at,
            review_method=expected_method,
            reportable=False,
        )

    def _register_evidence(self, raw_record: Mapping[str, Any]) -> None:
        record_kind = "approved F2 evidence record"
        fields = {
            "record_id",
            "pair_group_id",
            "evidence_level",
            "source_refs",
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "model_visible_payload",
        }
        diagnostic_fields = fields | {"evidence_kind", "review_method", "reportable"}
        if set(raw_record) == diagnostic_fields:
            self._register_agent_cross_checked_evidence(raw_record)
            return
        if set(raw_record) != fields:
            raise ValueError(
                f"{record_kind} schema mismatch; "
                f"missing={sorted(fields - set(raw_record))}, "
                f"unknown={sorted(set(raw_record) - fields)}"
            )
        record_id = _required_nonempty_string(raw_record, "record_id", record_kind)
        if record_id in self._evidence_records:
            raise ValueError(f"duplicate evidence record_id {record_id!r}")
        pair_group_id = _required_nonempty_string(
            raw_record, "pair_group_id", record_kind
        )
        if pair_group_id not in self._cases:
            raise ValueError(f"evidence record has unknown pair {pair_group_id!r}")
        if raw_record.get("evidence_level") != F2_AUDITED_VALUES:
            raise ValueError("approved evidence registry accepts only exact F2 level")
        if raw_record.get("review_status") != "approved":
            raise ValueError("evidence registry accepts only approved records")
        source_refs = raw_record.get("source_refs")
        if not isinstance(source_refs, list) or len(source_refs) != len(ARMS):
            raise ValueError("approved F2 evidence requires one source ref per arm")
        normalized_refs: dict[str, str] = {}
        for source_ref in source_refs:
            if not isinstance(source_ref, Mapping) or set(source_ref) != {
                "arm",
                "artifact_path",
                "record_locator",
            }:
                raise ValueError("F2 source ref has a schema mismatch")
            arm = _required_nonempty_string(source_ref, "arm", "F2 source ref")
            if arm not in ARMS or arm in normalized_refs:
                raise ValueError("F2 source refs must contain each arm exactly once")
            artifact_value = _required_nonempty_string(
                source_ref, "artifact_path", "F2 source ref"
            )
            artifact = Path(artifact_value)
            resolved = (
                artifact.resolve()
                if artifact.is_absolute()
                else (self._repository_root / artifact).resolve()
            )
            try:
                portable = resolved.relative_to(self._repository_root).as_posix()
            except ValueError as exc:
                raise ValueError("F2 source artifact escapes repository_root") from exc
            if not resolved.is_file():
                raise ValueError(f"F2 source artifact does not exist: {portable}")
            locator = _required_nonempty_string(
                source_ref, "record_locator", "F2 source ref"
            )
            normalized_refs[arm] = f"{portable}#{locator}"
        if set(normalized_refs) != ARMS:
            raise ValueError("F2 source refs must contain official and clean")
        reviewed_by = _required_nonempty_string(
            raw_record, "reviewed_by", record_kind
        )
        reviewed_at = _validated_iso_date(
            _required_nonempty_string(raw_record, "reviewed_at", record_kind),
            "evidence reviewed_at",
        )
        if normalized_refs != self._cases[pair_group_id]["canonical_source_refs"]:
            raise ValueError(
                "F2 source refs must exactly match the canonical case records"
            )
        payload = raw_record.get("model_visible_payload")
        if not isinstance(payload, Mapping) or set(payload) != {"heading", "facts"}:
            raise ValueError(
                "F2 model_visible_payload requires exactly heading and facts"
            )
        heading = _required_nonempty_string(
            payload, "heading", "F2 model_visible_payload"
        )
        facts = payload.get("facts")
        if not isinstance(facts, list) or not facts:
            raise ValueError("F2 model_visible_payload requires non-empty facts")
        normalized_facts: list[dict[str, str]] = []
        for fact in facts:
            if not isinstance(fact, Mapping) or set(fact) != {
                "subject",
                "relation",
                "object",
            }:
                raise ValueError(
                    "each F2 fact requires subject, relation, and object"
                )
            normalized_facts.append(
                {
                    field: _required_nonempty_string(
                        fact, field, "F2 model-visible fact"
                    )
                    for field in ("subject", "relation", "object")
                }
            )
        visible_text = " ".join(
            [heading]
            + [value for fact in normalized_facts for value in fact.values()]
        ).casefold()
        forbidden_fragments = (
            "action_id",
            "expected_action_id",
            "misleading_action_ids",
            "ground_truth",
            "correct action",
            "misleading action",
            "choice_0",
            "choice_1",
            "choice_2",
            "role=",
        )
        leaked = [term for term in forbidden_fragments if term in visible_text]
        if leaked:
            raise ValueError(
                f"F2 model-visible payload contains forbidden scorer text: {leaked}"
            )
        self._evidence_records[record_id] = {
            "record_id": record_id,
            "pair_group_id": pair_group_id,
            "evidence_level": F2_AUDITED_VALUES,
            "evidence_source": ";".join(
                f"{arm}:{normalized_refs[arm]}" for arm in sorted(ARMS)
            ),
            "evidence_review_status": "approved",
            "evidence_reviewed_by": reviewed_by,
            "evidence_reviewed_at": reviewed_at,
            "model_visible_payload": {
                "heading": heading,
                "facts": normalized_facts,
            },
        }

    def _register_contrast(self, raw_contrast: Mapping[str, Any]) -> None:
        fields = {
            "contrast_id",
            "contrast_axis",
            "candidate_condition",
            "reference_condition",
        }
        if set(raw_contrast) != fields:
            raise ValueError(
                "contrast record schema mismatch; "
                f"missing={sorted(fields - set(raw_contrast))}, "
                f"unknown={sorted(set(raw_contrast) - fields)}"
            )
        contrast_id = _required_nonempty_string(
            raw_contrast, "contrast_id", "contrast record"
        )
        if contrast_id in self._contrasts:
            raise ValueError(f"duplicate contrast_id {contrast_id!r}")
        contrast_axis = _required_nonempty_string(
            raw_contrast, "contrast_axis", "contrast record"
        )
        if contrast_axis not in CONTRAST_AXES:
            raise ValueError(f"contrast record has unknown axis {contrast_axis!r}")
        candidate_condition = _required_nonempty_string(
            raw_contrast, "candidate_condition", "contrast record"
        )
        reference_condition = _required_nonempty_string(
            raw_contrast, "reference_condition", "contrast record"
        )
        if candidate_condition == reference_condition:
            raise ValueError("contrast candidate/reference conditions must differ")
        unknown_conditions = {
            candidate_condition,
            reference_condition,
        } - set(self._conditions)
        if unknown_conditions:
            raise ValueError(
                f"contrast references unknown conditions: {sorted(unknown_conditions)}"
            )
        self._contrasts[contrast_id] = {
            "contrast_axis": contrast_axis,
            "candidate_condition": candidate_condition,
            "reference_condition": reference_condition,
        }

    def _register_training_recipe(self, raw_record: Mapping[str, Any]) -> None:
        record_kind = "approved training recipe record"
        fields = {
            "record_id",
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "candidate_checkpoint_id",
            "reference_checkpoint_id",
            "checkpoint_stage",
            "history_mode",
            "workflow_mode",
            "candidate_reflection_training_status",
            "reference_reflection_training_status",
        }
        if set(raw_record) != fields:
            raise ValueError(
                f"{record_kind} schema mismatch; "
                f"missing={sorted(fields - set(raw_record))}, "
                f"unknown={sorted(set(raw_record) - fields)}"
            )
        record_id = _required_nonempty_string(raw_record, "record_id", record_kind)
        if record_id in self._training_records:
            raise ValueError(f"duplicate training recipe record_id {record_id!r}")
        if raw_record.get("review_status") != "approved":
            raise ValueError("training recipe registry accepts only approved records")
        record = {
            field: _required_nonempty_string(raw_record, field, record_kind)
            for field in fields - {"record_id", "review_status", "reviewed_at"}
        }
        record["record_id"] = record_id
        record["review_status"] = "approved"
        record["reviewed_at"] = _validated_iso_date(
            _required_nonempty_string(raw_record, "reviewed_at", record_kind),
            "training recipe reviewed_at",
        )
        if record["workflow_mode"] not in WORKFLOW_MODES:
            raise ValueError("training recipe has unknown workflow_mode")
        if (
            record["candidate_reflection_training_status"]
            == record["reference_reflection_training_status"]
        ):
            raise ValueError("training recipe must bind distinct training statuses")
        self._training_records[record_id] = record

    @staticmethod
    def _reject_self_reported(
        base: Mapping[str, Any], forbidden: frozenset[str], kind: str
    ) -> None:
        supplied = sorted(set(base) & forbidden)
        if supplied:
            raise TraceReductionError(
                f"base_fields cannot self-report {kind}: {', '.join(supplied)}"
            )

    @staticmethod
    def _bind_expected(
        base: dict[str, Any], field_name: str, expected: Any, source: str
    ) -> None:
        if field_name in base:
            actual = base[field_name]
            if isinstance(expected, tuple) and isinstance(actual, list):
                actual = tuple(actual)
            if actual != expected:
                raise TraceReductionError(
                    f"base_fields {field_name} disagrees with {source}: "
                    f"{actual!r} != {expected!r}"
                )
        base[field_name] = expected

    def bind_base_fields(self, base_fields: Mapping[str, Any]) -> dict[str, Any]:
        """Resolve canonical roles, condition lineage, and approved provenance."""

        base = dict(base_fields)
        pair_group_id = _required_nonempty_string(base, "pair_group_id", "run base")
        arm = _required_nonempty_string(base, "arm", "run base")
        condition_id = _required_nonempty_string(base, "condition", "run base")
        if arm not in ARMS:
            raise TraceReductionError(f"unknown run arm {arm!r}")
        case = self._cases.get(pair_group_id)
        if case is None:
            raise TraceReductionError(f"pair {pair_group_id!r} is not canonical")
        condition = self._conditions.get(condition_id)
        if condition is None:
            raise TraceReductionError(
                f"condition {condition_id!r} is not preregistered"
            )
        for field_name in (
            "correct_action_id",
            "misleading_action_ids",
            "neutral_action_ids",
            "display_order",
            "display_tokens",
            "choice_token_to_action_id",
        ):
            expected = case[field_name]
            self._bind_expected(base, field_name, expected, "canonical case")
        for field_name, expected in case["arm_records"][arm].items():
            self._bind_expected(base, field_name, expected, "canonical arm")
        for field_name, expected in condition.items():
            self._bind_expected(base, field_name, expected, "condition registry")

        self._reject_self_reported(
            base, self._EVIDENCE_PROVENANCE_FIELDS, "evidence approval"
        )
        evidence_level = base.get("evidence_level")
        if evidence_level is not None and evidence_level not in EVIDENCE_LEVELS:
            raise TraceReductionError(f"unknown evidence_level {evidence_level!r}")
        evidence_record_id = base.get("evidence_record_id")
        if evidence_level == F2_AUDITED_VALUES:
            if not isinstance(evidence_record_id, str) or not evidence_record_id:
                raise TraceReductionError("F2 run requires evidence_record_id")
            evidence = self._evidence_records.get(evidence_record_id)
            if evidence is None:
                raise TraceReductionError(
                    f"F2 record {evidence_record_id!r} is not approved"
                )
            if evidence["pair_group_id"] != pair_group_id:
                raise TraceReductionError(
                    "F2 evidence record is bound to a different canonical case"
                )
            for field_name in self._EVIDENCE_PROVENANCE_FIELDS:
                base[field_name] = evidence[field_name]
        else:
            if evidence_record_id is not None:
                raise TraceReductionError(
                    "evidence_record_id is valid only for exact F2_audited_values"
                )
            base.update(
                evidence_source=None,
                evidence_review_status="not_applicable",
                evidence_reviewed_by=None,
                evidence_reviewed_at=None,
            )

        self._reject_self_reported(
            base, self._TRAINING_PROVENANCE_FIELDS, "training-recipe approval"
        )
        recipe_id = base.get("training_recipe_match_id")
        if recipe_id is None:
            base.update(
                training_recipe_review_status="not_applicable",
                training_recipe_reviewed_by=None,
                training_recipe_reviewed_at=None,
            )
        else:
            if not isinstance(recipe_id, str) or not recipe_id:
                raise TraceReductionError("training_recipe_match_id must be non-empty")
            recipe = self._training_records.get(recipe_id)
            if recipe is None:
                raise TraceReductionError(
                    f"training recipe {recipe_id!r} is not approved"
                )
            allowed_checkpoints = {
                recipe["candidate_checkpoint_id"],
                recipe["reference_checkpoint_id"],
            }
            if condition["checkpoint_id"] not in allowed_checkpoints:
                raise TraceReductionError(
                    "condition checkpoint is absent from the approved training recipe"
                )
            base.update(
                training_recipe_review_status="approved",
                training_recipe_reviewed_by=recipe["reviewed_by"],
                training_recipe_reviewed_at=recipe["reviewed_at"],
            )
        return base

    def evidence_payload(self, record_id: str, pair_group_id: str) -> Any:
        """Resolve renderer-visible F2 content only from an approved record."""

        record = self._evidence_records.get(record_id)
        if record is None or record["pair_group_id"] != pair_group_id:
            raise KeyError("approved evidence record not found for canonical case")
        return copy.deepcopy(record["model_visible_payload"])

    def resolve_contrast(self, contrast_id: str) -> dict[str, str]:
        """Resolve a preregistered, direction-sensitive condition contrast."""

        contrast = self._contrasts.get(contrast_id)
        if contrast is None:
            raise KeyError(f"contrast {contrast_id!r} is not preregistered")
        return dict(contrast)

    def validate_training_contrast(
        self, candidate: RecoveryRun, reference: RecoveryRun
    ) -> None:
        recipe_id = candidate.training_recipe_match_id
        if not recipe_id or recipe_id != reference.training_recipe_match_id:
            raise ValueError("reflection contrast requires one approved recipe id")
        recipe = self._training_records.get(recipe_id)
        if recipe is None:
            raise ValueError("reflection contrast recipe is not registry-approved")
        expected = {
            "candidate_checkpoint_id": candidate.checkpoint_id,
            "reference_checkpoint_id": reference.checkpoint_id,
            "checkpoint_stage": candidate.checkpoint_stage,
            "history_mode": candidate.history_mode,
            "workflow_mode": candidate.workflow_mode,
            "candidate_reflection_training_status": (
                candidate.reflection_training_status
            ),
            "reference_reflection_training_status": (
                reference.reflection_training_status
            ),
        }
        mismatches = {
            field: (actual, recipe[field])
            for field, actual in expected.items()
            if actual != recipe[field]
        }
        if mismatches:
            raise ValueError(
                f"reflection contrast disagrees with approved recipe: {mismatches}"
            )


_EVENT_DERIVED_RUN_FIELDS = frozenset(
    {
        "initial_selected_action_id",
        "feedback_observed",
        "contradiction_recognized",
        "outcome_validation_observed",
        "outcome_validated_action_ids",
        "outcome_record_ids",
        "outcome_contradictions",
        "actual_reversal_action_type",
        "reversal_returned_to_retry",
        "reversal_from_state",
        "reversal_to_state",
        "post_review_selected_action_ids",
        "final_review_observed",
        "final_selected_action_id",
        "final_submission_observed",
        "submission_id",
        "scorer_result_observed",
        "scorer_record_id",
        "final_submission_success",
        "interface_censored",
        "event_trace_reduced",
        "trace_event_count",
        "trace_last_event_index",
        "observed_artifact_paths",
        "observed_model_step_ids",
        "observed_model_response_ids",
        "observed_execution_receipt_ids",
    }
)


def _event_string(event: Mapping[str, Any], key: str, event_index: int) -> str:
    value = event.get(key)
    if not isinstance(value, str) or not value:
        raise TraceReductionError(
            f"event {event_index} requires a non-empty string {key!r}"
        )
    return value


def _canonical_action_from_control(
    event: Mapping[str, Any],
    *,
    action_field: str,
    token_field: str,
    position_field: str,
    event_index: int,
    base_fields: Mapping[str, Any],
) -> str:
    """Join a raw browser control receipt to the canonical action mapping."""

    reported_action = _event_string(event, action_field, event_index)
    choice_token = _event_string(event, token_field, event_index)
    position = event.get(position_field)
    if isinstance(position, bool) or not isinstance(position, int) or position < 0:
        raise TraceReductionError(
            f"event {event_index} requires a non-negative integer "
            f"{position_field!r}"
        )
    display_tokens = base_fields.get("display_tokens")
    raw_mapping = base_fields.get("choice_token_to_action_id")
    if not isinstance(display_tokens, (list, tuple)) or not display_tokens:
        raise TraceReductionError("base_fields requires canonical display_tokens")
    try:
        token_map = (
            dict(raw_mapping)
            if not isinstance(raw_mapping, Mapping)
            else dict(raw_mapping.items())
        )
    except (TypeError, ValueError) as exc:
        raise TraceReductionError(
            "base_fields has an invalid choice token mapping"
        ) from exc
    if position >= len(display_tokens) or display_tokens[position] != choice_token:
        raise TraceReductionError(
            f"event {event_index} raw control token/position is not canonical"
        )
    canonical_action = token_map.get(choice_token)
    if not isinstance(canonical_action, str) or not canonical_action:
        raise TraceReductionError(
            f"event {event_index} raw choice token is absent from canonical mapping"
        )
    if reported_action != canonical_action:
        raise TraceReductionError(
            f"event {event_index} action id disagrees with raw control receipt"
        )
    return canonical_action


def _require_runner_event(event: Mapping[str, Any], event_index: int) -> None:
    if event.get("source") != "runner":
        raise TraceReductionError(
            f"event {event_index} is structural evidence but source is not 'runner'"
        )


def _require_scorer_event(event: Mapping[str, Any], event_index: int) -> None:
    if event.get("source") != "scorer":
        raise TraceReductionError(
            f"event {event_index} is outcome evidence but source is not 'scorer'"
        )


def _require_validator_event(event: Mapping[str, Any], event_index: int) -> None:
    if event.get("source") != "validator":
        raise TraceReductionError(
            f"event {event_index} is F3 outcome evidence but source is not "
            "'validator'"
        )


def _validate_event_envelope(
    event: Mapping[str, Any],
    event_type: str,
    event_index: int,
    base_fields: Mapping[str, Any],
) -> None:
    specific_fields = _EVENT_SPECIFIC_FIELDS.get(event_type)
    if specific_fields is None:
        raise TraceReductionError(
            f"event {event_index} has unknown event_type {event_type!r}"
        )
    expected_fields = _COMMON_EVENT_FIELDS | specific_fields
    missing = sorted(expected_fields - set(event))
    unknown = sorted(set(event) - expected_fields)
    if missing or unknown:
        raise TraceReductionError(
            f"event {event_index} has schema mismatch; missing={missing}, "
            f"unknown={unknown}"
        )
    for field_name in EVENT_IDENTITY_FIELDS:
        actual = _event_string(event, field_name, event_index)
        expected = base_fields.get(field_name)
        if not isinstance(expected, str) or not expected:
            raise TraceReductionError(
                f"base_fields requires a non-empty {field_name!r}"
            )
        if actual != expected:
            raise TraceReductionError(
                f"event {event_index} {field_name} does not match run identity: "
                f"{actual!r} != {expected!r}"
            )
    if event_type in MODEL_ONLY_EVENT_TYPES:
        if event.get("source") != "model":
            raise TraceReductionError(
                f"event {event_index} model-only evidence must use source='model'"
            )
    elif event_type == SCORER_RESULT_EVENT:
        _require_scorer_event(event, event_index)
    elif event_type == OUTCOME_VALIDATION_EVENT:
        _require_validator_event(event, event_index)
    else:
        _require_runner_event(event, event_index)


def _is_png_screenshot_artifact(path: str) -> bool:
    """Validate and inflate the non-interlaced 8-bit PNGs browsers capture."""

    if not os.path.isfile(path):
        return False
    try:
        payload = Path(path).read_bytes()
    except OSError:
        return False
    if len(payload) < 8 or payload[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    offset = 8
    chunk_index = 0
    saw_ihdr = False
    saw_idat = False
    saw_iend = False
    idat_closed = False
    idat_payloads: list[bytes] = []
    width = 0
    height = 0
    channels = 0
    while offset < len(payload):
        if len(payload) - offset < 12:
            return False
        chunk_length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + chunk_length
        crc_end = data_end + 4
        if crc_end > len(payload):
            return False
        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            return False
        if chunk_index == 0:
            if chunk_type != b"IHDR" or chunk_length != 13:
                return False
            width, height = struct.unpack(">II", chunk_data[:8])
            if width <= 0 or height <= 0:
                return False
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
            compression_method = chunk_data[10]
            filter_method = chunk_data[11]
            interlace_method = chunk_data[12]
            channel_counts = {0: 1, 2: 3, 4: 2, 6: 4}
            if (
                bit_depth != 8
                or color_type not in channel_counts
                or compression_method != 0
                or filter_method != 0
                or interlace_method != 0
            ):
                return False
            channels = channel_counts[color_type]
            saw_ihdr = True
        elif chunk_type == b"IHDR":
            return False
        if chunk_type == b"IDAT":
            if idat_closed:
                return False
            saw_idat = True
            idat_payloads.append(chunk_data)
        elif saw_idat and chunk_type != b"IEND":
            idat_closed = True
        if chunk_type == b"IEND":
            if chunk_length != 0 or crc_end != len(payload):
                return False
            saw_iend = True
            break
        offset = crc_end
        chunk_index += 1
    if not (saw_ihdr and saw_idat and saw_iend):
        return False
    expected_row_bytes = width * channels
    expected_size = height * (expected_row_bytes + 1)
    if expected_size <= 0 or expected_size > 256 * 1024 * 1024:
        return False
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(
            b"".join(idat_payloads), expected_size + 1
        )
        if decompressor.unconsumed_tail:
            return False
        decoded += decompressor.flush()
    except zlib.error:
        return False
    if (
        not decompressor.eof
        or decompressor.unused_data
        or len(decoded) != expected_size
    ):
        return False
    row_stride = expected_row_bytes + 1
    return all(decoded[row * row_stride] <= 4 for row in range(height))


def _png_screenshot_dimensions(path: str) -> tuple[int, int] | None:
    """Return dimensions only after full PNG structural validation succeeds."""

    if not _is_png_screenshot_artifact(path):
        return None
    try:
        payload = Path(path).read_bytes()
    except OSError:
        return None
    return struct.unpack(">II", payload[16:24])


def _validate_render_receipt(
    event: Mapping[str, Any],
    *,
    event_index: int,
    base_fields: Mapping[str, Any],
    artifact_field: str,
    model_step_field: str,
) -> tuple[str, str]:
    """Validate a collector acknowledgement against registry-bound run data."""

    for event_field, base_field, label in (
        ("rendered_task_instance_id", "task_instance_id", "task instance"),
        ("rendered_chart_path", "chart_path", "chart"),
        ("rendered_ui_variant", "ui_variant", "UI variant"),
        ("renderer_build_id", "renderer_build_id", "renderer build"),
    ):
        actual = _event_string(event, event_field, event_index)
        if actual != base_fields.get(base_field):
            raise TraceReductionError(
                f"event {event_index} renders a different {label}"
            )
    for field_name in ("viewport_width", "viewport_height"):
        actual = event.get(field_name)
        expected = base_fields.get(field_name)
        if (
            isinstance(actual, bool)
            or not isinstance(actual, int)
            or actual <= 0
            or actual != expected
        ):
            raise TraceReductionError(
                f"event {event_index} {field_name} does not match render profile"
            )
    artifact_path = _event_string(event, artifact_field, event_index)
    model_step_id = _event_string(event, model_step_field, event_index)
    dimensions = _png_screenshot_dimensions(artifact_path)
    if dimensions is None:
        raise TraceReductionError(
            f"event {event_index} is not a valid PNG screenshot artifact: "
            f"{artifact_path!r}"
        )
    expected_dimensions = (
        base_fields.get("viewport_width"),
        base_fields.get("viewport_height"),
    )
    if dimensions != expected_dimensions:
        raise TraceReductionError(
            f"event {event_index} screenshot dimensions do not match viewport: "
            f"{dimensions!r} != {expected_dimensions!r}"
        )
    return artifact_path, model_step_id


def derive_run_from_events(
    base_fields: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
) -> RecoveryRun:
    """Reduce an append-only runner event trace to a :class:`RecoveryRun`.

    ``base_fields`` contains protocol identity and ground-truth role fields, but
    must not contain behavioral conclusions.  Those conclusions are derived
    only from contiguous events whose ``event_index`` starts at zero.

    Evidentiary event schemas are deliberately small, normalized, and
    source-tagged.  The schema does not authenticate the future collector:

    * ``ui_selection``: ``source='runner'``, a raw choice token/position joined
      to the canonical action map, an acknowledged decision screenshot, and
      model-response/execution receipts joined to that model input;
    * ``screenshot_observation``: ``source='runner'``, ``observed_state`` equal
      to ``review`` or ``final_review``, a unique ``model_step_id``, and a
      unique concrete PNG ``artifact_path``; its ``feedback_spec_id`` and
      rendered F2 record binding must match the registry-bound run;
    * ``ui_reversal``: ``source='runner'``, explicit state transition fields,
      and response/execution receipts joined to the review input;
    * ``outcome_validation``: ``source='validator'``, one unique F3 record per
      provisional choice, including raw control identity and polarity;
    * ``submission``: ``source='runner'``, a raw control receipt mapped to the
      submitted action and a unique ``submission_id``; a single-attempt
      submission must be atomic with its selection;
    * ``scorer_result``: ``source='scorer'`` and a later external scorer
      record joined by the same ``submission_id``, with ``scorer_record_id``
      and boolean ``success``;
    * ``interface_censor``: ``source='runner'``.

    Model thoughts/messages are accepted as inert audit events.  Their content
    is never parsed and cannot establish feedback, reversal, selection, or
    submission evidence.  Unknown event types and unverifiable screenshots
    fail closed.
    """

    protected = sorted(set(base_fields) & _EVENT_DERIVED_RUN_FIELDS)
    if protected:
        raise TraceReductionError(
            "base_fields cannot pre-fill event-derived fields: "
            + ", ".join(protected)
        )

    base = dict(base_fields)
    recovery_branch = base.get("recovery_branch", NATURAL_RECOVERY)
    injected_mistake = base.get("injected_mistake_action_id")

    initial_selection: str | None = None
    current_selection: str | None = (
        injected_mistake
        if recovery_branch == STANDARDIZED_MISTAKE
        else None
    )
    post_review_selections: list[str] = []
    last_post_review_selection_index: int | None = None
    feedback_observed = False
    outcome_validation_observed = False
    outcome_validated_action_ids: list[str] = []
    outcome_record_ids: list[str] = []
    outcome_contradictions: list[bool] = []
    current_outcome_validated = False
    latest_final_review_index: int | None = None
    observed_artifact_paths: list[str] = []
    observed_model_step_ids: list[str] = []
    observed_model_response_ids: list[str] = []
    observed_execution_receipt_ids: list[str] = []
    last_action_model_response_id: str | None = None
    last_action_execution_receipt_id: str | None = None
    reversal_action_type: str | None = None
    reversal_from_state: str | None = None
    reversal_to_state: str | None = None
    reversal_returned_to_retry: bool | None = None
    final_submission_observed = False
    submission_id: str | None = None
    scorer_result_observed = False
    scorer_record_id: str | None = None
    final_submission_success: bool | None = None
    submitted_action_id: str | None = None
    interface_censored = False
    event_count = 0

    for expected_index, raw_event in enumerate(events):
        event_count += 1
        if not isinstance(raw_event, Mapping):
            raise TraceReductionError(
                f"event {expected_index} must be a mapping"
            )
        event = raw_event
        event_index = event.get("event_index")
        if (
            isinstance(event_index, bool)
            or not isinstance(event_index, int)
            or event_index != expected_index
        ):
            raise TraceReductionError(
                "event_index must be contiguous and start at 0; "
                f"expected {expected_index}, got {event_index!r}"
            )
        event_type = _event_string(event, "event_type", event_index)
        _validate_event_envelope(event, event_type, event_index, base)

        if event_type in MODEL_ONLY_EVENT_TYPES:
            continue

        if scorer_result_observed and event_type != INTERFACE_CENSOR_EVENT:
            raise TraceReductionError(
                f"runner event {event_index} occurs after terminal scorer result"
            )
        if final_submission_observed and event_type not in {
            SCORER_RESULT_EVENT,
            INTERFACE_CENSOR_EVENT,
        }:
            raise TraceReductionError(
                f"runner event {event_index} occurs after terminal submission"
            )

        if event_type == UI_SELECTION_EVENT:
            decision_state = _event_string(event, "decision_state", event_index)
            expected_decision_state = (
                RETRY_DECISION_STATE if feedback_observed else INITIAL_DECISION_STATE
            )
            if decision_state != expected_decision_state:
                raise TraceReductionError(
                    f"event {event_index} selection has no acknowledged "
                    f"{expected_decision_state} input"
                )
            rendered_retry_presentation = event.get(
                "rendered_retry_presentation"
            )
            rendered_feedback_spec_id = event.get("rendered_feedback_spec_id")
            rendered_evidence_record_id = event.get(
                "rendered_evidence_record_id"
            )
            rendered_outcome_record_id = event.get("rendered_outcome_record_id")
            rendered_outcome_contradiction = event.get(
                "rendered_outcome_contradiction"
            )
            rendered_provisional_fields = (
                event.get("rendered_provisional_action_id"),
                event.get("rendered_provisional_choice_token"),
                event.get("rendered_provisional_control_position"),
            )
            if decision_state == INITIAL_DECISION_STATE:
                if (
                    rendered_retry_presentation is not None
                    or rendered_feedback_spec_id is not None
                    or rendered_evidence_record_id is not None
                    or rendered_outcome_record_id is not None
                    or rendered_outcome_contradiction is not None
                    or any(value is not None for value in rendered_provisional_fields)
                ):
                    raise TraceReductionError(
                        f"event {event_index} initial decision leaks retry feedback"
                    )
            else:
                rendered_provisional_action = _canonical_action_from_control(
                    event,
                    action_field="rendered_provisional_action_id",
                    token_field="rendered_provisional_choice_token",
                    position_field="rendered_provisional_control_position",
                    event_index=event_index,
                    base_fields=base,
                )
                if rendered_provisional_action != current_selection:
                    raise TraceReductionError(
                        f"event {event_index} retry renders a different prior choice"
                    )
                if rendered_retry_presentation != base.get("retry_presentation"):
                    raise TraceReductionError(
                        f"event {event_index} retry presentation does not match run"
                    )
                expected_retry_feedback = (
                    base.get("evidence_level")
                    if base.get("retry_presentation") == CURRENT_VISIBLE_RETRY
                    else None
                )
                if rendered_feedback_spec_id != expected_retry_feedback:
                    raise TraceReductionError(
                        f"event {event_index} retry feedback rendering is mismatched"
                    )
                if base.get("retry_presentation") == HISTORY_ONLY_RETRY:
                    if (
                        rendered_evidence_record_id is not None
                        or rendered_outcome_record_id is not None
                        or rendered_outcome_contradiction is not None
                    ):
                        raise TraceReductionError(
                            f"event {event_index} history-only retry renders evidence"
                        )
                elif base.get("evidence_level") == F2_AUDITED_VALUES:
                    if rendered_evidence_record_id != base.get("evidence_record_id"):
                        raise TraceReductionError(
                            f"event {event_index} retry renders the wrong F2 record"
                        )
                    if (
                        rendered_outcome_record_id is not None
                        or rendered_outcome_contradiction is not None
                    ):
                        raise TraceReductionError(
                            f"event {event_index} F2 retry renders outcome evidence"
                        )
                elif base.get("evidence_level") in OUTCOME_FEEDBACK_LEVELS:
                    if not current_outcome_validated:
                        raise TraceReductionError(
                            f"event {event_index} outcome-feedback retry has no "
                            "current outcome"
                        )
                    if (
                        rendered_outcome_record_id != outcome_record_ids[-1]
                        or rendered_outcome_contradiction
                        is not outcome_contradictions[-1]
                    ):
                        raise TraceReductionError(
                            f"event {event_index} retry renders the wrong F3 outcome"
                        )
                    if rendered_evidence_record_id is not None:
                        raise TraceReductionError(
                            f"event {event_index} F3 retry renders an F2 record"
                        )
                elif (
                    rendered_evidence_record_id is not None
                    or rendered_outcome_record_id is not None
                    or rendered_outcome_contradiction is not None
                ):
                    raise TraceReductionError(
                        f"event {event_index} retry renders an unexpected record"
                    )
            rendered_display_tokens = event.get("rendered_display_tokens")
            if isinstance(rendered_display_tokens, list):
                rendered_display_tokens = tuple(rendered_display_tokens)
            if rendered_display_tokens != tuple(base.get("display_tokens", ())):
                raise TraceReductionError(
                    f"event {event_index} renders a different choice layout"
                )
            input_artifact_path, input_model_step_id = _validate_render_receipt(
                event,
                event_index=event_index,
                base_fields=base,
                artifact_field="input_artifact_path",
                model_step_field="input_model_step_id",
            )
            model_response_id = _event_string(
                event, "model_response_id", event_index
            )
            execution_receipt_id = _event_string(
                event, "execution_receipt_id", event_index
            )
            caused_by_model_step_id = _event_string(
                event, "caused_by_model_step_id", event_index
            )
            if caused_by_model_step_id != input_model_step_id:
                raise TraceReductionError(
                    f"event {event_index} selection is not joined to its model input"
                )
            for value, observed, label in (
                (input_artifact_path, observed_artifact_paths, "artifact"),
                (input_model_step_id, observed_model_step_ids, "model_step_id"),
                (
                    model_response_id,
                    observed_model_response_ids,
                    "model_response_id",
                ),
                (
                    execution_receipt_id,
                    observed_execution_receipt_ids,
                    "execution_receipt_id",
                ),
            ):
                if value in observed:
                    raise TraceReductionError(
                        f"event {event_index} reuses {label} {value!r}"
                    )
                observed.append(value)
            last_action_model_response_id = model_response_id
            last_action_execution_receipt_id = execution_receipt_id
            action_id = _canonical_action_from_control(
                event,
                action_field="action_id",
                token_field="choice_token",
                position_field="control_position",
                event_index=event_index,
                base_fields=base,
            )
            if feedback_observed:
                if reversal_action_type is None:
                    raise TraceReductionError(
                        f"event {event_index} post-review selection requires "
                        "a prior observed reversal event"
                    )
                if latest_final_review_index is not None:
                    raise TraceReductionError(
                        f"event {event_index} selection occurs after final review"
                    )
                post_review_selections.append(action_id)
                last_post_review_selection_index = event_index
            else:
                if recovery_branch == STANDARDIZED_MISTAKE:
                    raise TraceReductionError(
                        "standardized-mistake traces cannot contain a "
                        "pre-review agent selection"
                    )
                if initial_selection is not None:
                    raise TraceReductionError(
                        "natural-recovery traces require exactly one "
                        "pre-review provisional selection"
                    )
                initial_selection = action_id
            current_selection = action_id
            current_outcome_validated = False
        elif event_type == SCREENSHOT_OBSERVATION_EVENT:
            observed_state = _event_string(
                event, "observed_state", event_index
            )
            if observed_state not in {REVIEW_STATE, FINAL_REVIEW_STATE}:
                raise TraceReductionError(
                    f"event {event_index} has unknown observed_state "
                    f"{observed_state!r}"
                )
            if observed_state == REVIEW_STATE:
                if recovery_branch == NATURAL_RECOVERY and initial_selection is None:
                    raise TraceReductionError(
                        f"event {event_index} review precedes the natural "
                        "provisional selection"
                    )
                if recovery_branch == STANDARDIZED_MISTAKE and injected_mistake is None:
                    raise TraceReductionError(
                        f"event {event_index} standardized review has no "
                        "injected mistake"
                    )
            else:
                if not feedback_observed:
                    raise TraceReductionError(
                        f"event {event_index} final review precedes initial review"
                    )
                if reversal_action_type is None:
                    raise TraceReductionError(
                        f"event {event_index} final review precedes reversal"
                    )
                if not post_review_selections:
                    raise TraceReductionError(
                        f"event {event_index} final review precedes retry selection"
                    )
            artifact_path, model_step_id = _validate_render_receipt(
                event,
                event_index=event_index,
                base_fields=base,
                artifact_field="artifact_path",
                model_step_field="model_step_id",
            )
            feedback_spec_id = _event_string(
                event, "feedback_spec_id", event_index
            )
            expected_feedback_spec = base.get("evidence_level")
            if feedback_spec_id != expected_feedback_spec:
                raise TraceReductionError(
                    f"event {event_index} feedback_spec_id does not match "
                    f"registered evidence level {expected_feedback_spec!r}"
                )
            rendered_provisional_action = _canonical_action_from_control(
                event,
                action_field="rendered_provisional_action_id",
                token_field="rendered_provisional_choice_token",
                position_field="rendered_provisional_control_position",
                event_index=event_index,
                base_fields=base,
            )
            if rendered_provisional_action != current_selection:
                raise TraceReductionError(
                    f"event {event_index} review renders a different provisional choice"
                )
            rendered_evidence_record_id = event.get(
                "rendered_evidence_record_id"
            )
            expected_evidence_record_id = base.get("evidence_record_id")
            if expected_feedback_spec == F2_AUDITED_VALUES:
                if (
                    not isinstance(rendered_evidence_record_id, str)
                    or not rendered_evidence_record_id
                    or rendered_evidence_record_id != expected_evidence_record_id
                ):
                    raise TraceReductionError(
                        f"event {event_index} does not bind the registered F2 record"
                    )
            elif rendered_evidence_record_id is not None:
                raise TraceReductionError(
                    f"event {event_index} renders an evidence record outside F2"
                )
            rendered_outcome_record_id = event.get("rendered_outcome_record_id")
            rendered_outcome_contradiction = event.get(
                "rendered_outcome_contradiction"
            )
            if expected_feedback_spec == F3_OUTCOME_CONTRADICTION:
                if not current_outcome_validated:
                    raise TraceReductionError(
                        f"event {event_index} renders F3 before validator evidence"
                    )
                if rendered_outcome_record_id != outcome_record_ids[-1]:
                    raise TraceReductionError(
                        f"event {event_index} renders the wrong F3 outcome record"
                    )
                if rendered_outcome_contradiction is not outcome_contradictions[-1]:
                    raise TraceReductionError(
                        f"event {event_index} renders the wrong F3 contradiction"
                    )
            elif expected_feedback_spec == F3_PRE_REATTEMPT_CONTRADICTION:
                if observed_state == REVIEW_STATE:
                    if not current_outcome_validated:
                        raise TraceReductionError(
                            f"event {event_index} renders pre-reattempt F3 before "
                            "validator evidence"
                        )
                    if rendered_outcome_record_id != outcome_record_ids[-1]:
                        raise TraceReductionError(
                            f"event {event_index} renders the wrong pre-reattempt "
                            "F3 outcome record"
                        )
                    if (
                        rendered_outcome_contradiction
                        is not outcome_contradictions[-1]
                    ):
                        raise TraceReductionError(
                            f"event {event_index} renders the wrong pre-reattempt "
                            "F3 contradiction"
                        )
                elif (
                    rendered_outcome_record_id is not None
                    or rendered_outcome_contradiction is not None
                ):
                    raise TraceReductionError(
                        f"event {event_index} final review must not render the "
                        "pre-reattempt outcome"
                    )
            elif (
                rendered_outcome_record_id is not None
                or rendered_outcome_contradiction is not None
            ):
                raise TraceReductionError(
                    f"event {event_index} renders outcome evidence outside F3"
                )
            if artifact_path in observed_artifact_paths:
                raise TraceReductionError(
                    f"event {event_index} reuses screenshot artifact {artifact_path!r}"
                )
            if model_step_id in observed_model_step_ids:
                raise TraceReductionError(
                    f"event {event_index} reuses model_step_id {model_step_id!r}"
                )
            observed_artifact_paths.append(artifact_path)
            observed_model_step_ids.append(model_step_id)
            if observed_state == REVIEW_STATE:
                if feedback_observed:
                    raise TraceReductionError(
                        f"event {event_index} duplicates the initial review observation"
                    )
                if recovery_branch == NATURAL_RECOVERY:
                    if initial_selection is None:
                        raise TraceReductionError(
                            f"event {event_index} review precedes the natural "
                            "provisional selection"
                        )
                elif injected_mistake is None:
                    raise TraceReductionError(
                        f"event {event_index} standardized review has no "
                        "injected mistake"
                    )
                feedback_observed = True
            else:
                if not feedback_observed:
                    raise TraceReductionError(
                        f"event {event_index} final review precedes initial review"
                    )
                if reversal_action_type is None:
                    raise TraceReductionError(
                        f"event {event_index} final review precedes reversal"
                    )
                if not post_review_selections:
                    raise TraceReductionError(
                        f"event {event_index} final review precedes retry selection"
                    )
                if latest_final_review_index is not None:
                    raise TraceReductionError(
                        f"event {event_index} duplicates final review"
                    )
                latest_final_review_index = event_index
        elif event_type == OUTCOME_VALIDATION_EVENT:
            if base.get("evidence_level") not in OUTCOME_FEEDBACK_LEVELS:
                raise TraceReductionError(
                    f"event {event_index} outcome validation is reserved for "
                    "outcome feedback"
                )
            if (
                base.get("evidence_level")
                == F3_PRE_REATTEMPT_CONTRADICTION
                and post_review_selections
            ):
                raise TraceReductionError(
                    f"event {event_index} pre-reattempt F3 cannot validate the "
                    "retry selection"
                )
            if current_outcome_validated:
                raise TraceReductionError(
                    f"event {event_index} duplicates validation for one choice"
                )
            if current_selection is None:
                raise TraceReductionError(
                    f"event {event_index} outcome validation has no provisional choice"
                )
            provisional_action_id = _canonical_action_from_control(
                event,
                action_field="provisional_action_id",
                token_field="provisional_choice_token",
                position_field="provisional_control_position",
                event_index=event_index,
                base_fields=base,
            )
            if provisional_action_id != current_selection:
                raise TraceReductionError(
                    f"event {event_index} validates a different provisional choice"
                )
            outcome_record_id = _event_string(
                event, "outcome_record_id", event_index
            )
            if outcome_record_id in outcome_record_ids:
                raise TraceReductionError(
                    f"event {event_index} reuses outcome_record_id"
                )
            contradiction = event.get("contradiction")
            if not isinstance(contradiction, bool):
                raise TraceReductionError(
                    f"event {event_index} contradiction must be boolean"
                )
            outcome_validated_action_ids.append(provisional_action_id)
            outcome_record_ids.append(outcome_record_id)
            outcome_contradictions.append(contradiction)
            current_outcome_validated = True
            outcome_validation_observed = True
        elif event_type == UI_REVERSAL_EVENT:
            model_response_id = _event_string(
                event, "model_response_id", event_index
            )
            execution_receipt_id = _event_string(
                event, "execution_receipt_id", event_index
            )
            caused_by_model_step_id = _event_string(
                event, "caused_by_model_step_id", event_index
            )
            if (
                not observed_model_step_ids
                or caused_by_model_step_id != observed_model_step_ids[-1]
            ):
                raise TraceReductionError(
                    f"event {event_index} reversal is not joined to review input"
                )
            for value, observed, label in (
                (
                    model_response_id,
                    observed_model_response_ids,
                    "model_response_id",
                ),
                (
                    execution_receipt_id,
                    observed_execution_receipt_ids,
                    "execution_receipt_id",
                ),
            ):
                if value in observed:
                    raise TraceReductionError(
                        f"event {event_index} reuses {label} {value!r}"
                    )
                observed.append(value)
            last_action_model_response_id = model_response_id
            last_action_execution_receipt_id = execution_receipt_id
            if reversal_action_type is not None:
                raise TraceReductionError(
                    "RecoveryRun can summarize only one observed reversal action"
                )
            if not feedback_observed:
                raise TraceReductionError(
                    f"event {event_index} reversal precedes observed review"
                )
            if post_review_selections or latest_final_review_index is not None:
                raise TraceReductionError(
                    f"event {event_index} reversal occurs after retry evidence"
                )
            reversal_action_type = _event_string(
                event, "action_type", event_index
            )
            reversal_from_state = _event_string(
                event, "from_state", event_index
            )
            reversal_to_state = _event_string(event, "to_state", event_index)
            reversal_returned_to_retry = bool(
                feedback_observed
                and reversal_action_type in REVERSAL_ACTION_TYPES
                and reversal_from_state == REVIEW_STATE
                and reversal_to_state == RETRY_DECISION_STATE
            )
        elif event_type == SUBMISSION_EVENT:
            model_response_id = _event_string(
                event, "model_response_id", event_index
            )
            execution_receipt_id = _event_string(
                event, "execution_receipt_id", event_index
            )
            caused_by_model_step_id = _event_string(
                event, "caused_by_model_step_id", event_index
            )
            if (
                not observed_model_step_ids
                or caused_by_model_step_id != observed_model_step_ids[-1]
            ):
                raise TraceReductionError(
                    f"event {event_index} submission is not joined to latest input"
                )
            if base.get("workflow_mode") == SINGLE_ATTEMPT:
                if (
                    model_response_id != last_action_model_response_id
                    or execution_receipt_id != last_action_execution_receipt_id
                ):
                    raise TraceReductionError(
                        f"event {event_index} single-attempt submission must be "
                        "atomic with the selection"
                    )
            else:
                for value, observed, label in (
                    (
                        model_response_id,
                        observed_model_response_ids,
                        "model_response_id",
                    ),
                    (
                        execution_receipt_id,
                        observed_execution_receipt_ids,
                        "execution_receipt_id",
                    ),
                ):
                    if value in observed:
                        raise TraceReductionError(
                            f"event {event_index} reuses {label} {value!r}"
                        )
                    observed.append(value)
            if final_submission_observed:
                raise TraceReductionError("trace contains multiple submissions")
            submitted_action_id = _canonical_action_from_control(
                event,
                action_field="submitted_action_id",
                token_field="submitted_choice_token",
                position_field="submitted_control_position",
                event_index=event_index,
                base_fields=base,
            )
            submission_id = _event_string(event, "submission_id", event_index)
            if post_review_selections and latest_final_review_index is None:
                raise TraceReductionError(
                    f"event {event_index} submission precedes final review"
                )
            final_submission_observed = True
        elif event_type == SCORER_RESULT_EVENT:
            if not final_submission_observed or submission_id is None:
                raise TraceReductionError(
                    f"event {event_index} scorer result precedes submission"
                )
            scorer_submission_id = _event_string(
                event, "submission_id", event_index
            )
            if scorer_submission_id != submission_id:
                raise TraceReductionError(
                    f"event {event_index} scorer submission_id does not match "
                    f"{submission_id!r}"
                )
            scorer_record_id = _event_string(
                event, "scorer_record_id", event_index
            )
            success = event.get("success")
            if not isinstance(success, bool):
                raise TraceReductionError(
                    f"event {event_index} scorer success must be boolean"
                )
            scorer_result_observed = True
            final_submission_success = success
        elif event_type == INTERFACE_CENSOR_EVENT:
            interface_censored = True
        else:  # pragma: no cover - event schema already rejects this branch
            raise AssertionError(f"unhandled event_type: {event_type}")

    if event_count == 0:
        raise TraceReductionError("event trace must be non-empty")

    final_review_observed = bool(
        latest_final_review_index is not None
        and last_post_review_selection_index is not None
        and latest_final_review_index > last_post_review_selection_index
    )
    final_selected_action_id = (
        submitted_action_id
        if final_submission_observed
        else current_selection
    )

    return RecoveryRun(
        **base,
        initial_selected_action_id=initial_selection,
        feedback_observed=feedback_observed,
        contradiction_recognized=None,
        outcome_validation_observed=outcome_validation_observed,
        outcome_validated_action_ids=tuple(outcome_validated_action_ids),
        outcome_record_ids=tuple(outcome_record_ids),
        outcome_contradictions=tuple(outcome_contradictions),
        actual_reversal_action_type=reversal_action_type,
        reversal_returned_to_retry=reversal_returned_to_retry,
        reversal_from_state=reversal_from_state,
        reversal_to_state=reversal_to_state,
        post_review_selected_action_ids=tuple(post_review_selections),
        final_review_observed=final_review_observed,
        final_selected_action_id=final_selected_action_id,
        final_submission_observed=final_submission_observed,
        submission_id=submission_id,
        scorer_result_observed=scorer_result_observed,
        scorer_record_id=scorer_record_id,
        final_submission_success=final_submission_success,
        interface_censored=interface_censored,
        event_trace_reduced=True,
        trace_event_count=event_count,
        trace_last_event_index=event_count - 1,
        observed_artifact_paths=tuple(observed_artifact_paths),
        observed_model_step_ids=tuple(observed_model_step_ids),
        observed_model_response_ids=tuple(observed_model_response_ids),
        observed_execution_receipt_ids=tuple(observed_execution_receipt_ids),
    )


@dataclass(frozen=True)
class RecoveryAnalysis:
    run_id: str
    trial_id: str
    pair_group_id: str
    condition: str
    arm: str
    task_id: str
    task_instance_id: str
    chart_path: str
    recovery_branch: str
    evidence_level: str | None
    evidence_record_id: str | None
    evidence_source: str | None
    evidence_review_status: str
    evidence_reviewed_by: str | None
    evidence_reviewed_at: str | None
    review_regime: str
    retry_presentation: str
    ui_variant: str
    renderer_build_id: str
    viewport_width: int
    viewport_height: int
    checkpoint_id: str
    checkpoint_stage: str
    reflection_training_status: str
    history_mode: str
    workflow_mode: str
    training_recipe_match_id: str | None
    training_recipe_review_status: str
    training_recipe_reviewed_by: str | None
    training_recipe_reviewed_at: str | None
    initial_role: str
    opportunity_role: str
    eligibility_source: str
    initial_susceptible: bool
    visual_recovery_eligible: bool
    retry_role: str
    last_post_review_role: str
    final_role: str
    correct_action_switch: bool | None
    ordered_recovery: bool | None
    full_recovery: bool | None
    same_misleading_reentry: bool | None
    selection_state_consistent: bool | None
    scorer_consistent: bool | None
    outcome_record_ids: tuple[str, ...]
    outcome_contradictions: tuple[bool, ...]
    outcome_validator_consistent: bool | None
    reversal_action_type: str | None
    event_trace_replayed: bool
    reportable: bool
    trajectory_label: str
    diagnostic_labels: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["diagnostic_labels"] = list(self.diagnostic_labels)
        row["outcome_record_ids"] = list(self.outcome_record_ids)
        row["outcome_contradictions"] = list(self.outcome_contradictions)
        return row


def _analyze_summary(
    run: RecoveryRun, *, event_trace_replayed: bool
) -> RecoveryAnalysis:
    """Classify one summary; reportability is supplied only by trace replay."""

    role_kwargs = {
        "correct_action_id": run.correct_action_id,
        "misleading_action_ids": run.misleading_action_ids,
        "neutral_action_ids": run.neutral_action_ids,
    }
    initial_role = choice_role(run.initial_selected_action_id, **role_kwargs)
    if run.recovery_branch == NATURAL_RECOVERY:
        opportunity_action_id = run.initial_selected_action_id
        eligibility_source = "actual_initial_choice"
    else:
        opportunity_action_id = run.injected_mistake_action_id
        eligibility_source = "runner_injected_mistake"
    opportunity_role = choice_role(opportunity_action_id, **role_kwargs)
    post_choices = run.post_review_selected_action_ids
    post_roles = [choice_role(action_id, **role_kwargs) for action_id in post_choices]
    retry_role = choice_role(
        post_choices[0] if post_choices else None, **role_kwargs
    )
    last_post_role = choice_role(
        post_choices[-1] if post_choices else None, **role_kwargs
    )
    final_role = choice_role(run.final_selected_action_id, **role_kwargs)
    susceptible = opportunity_role == MISLEADING
    eligible = (
        susceptible
        and run.workflow_mode == FEEDBACK_RETRY
        and run.feedback_observed
    )

    expected_current_action_id = (
        post_choices[-1] if post_choices else opportunity_action_id
    )
    if run.final_selected_action_id is None:
        selection_state_consistent = (
            False if run.final_submission_observed else None
        )
    elif expected_current_action_id is None:
        selection_state_consistent = False
    else:
        selection_state_consistent = (
            run.final_selected_action_id == expected_current_action_id
        )

    if not run.final_submission_observed or run.final_submission_success is None:
        scorer_consistent: bool | None = None
    elif final_role in {CORRECT, MISLEADING, NEUTRAL}:
        scorer_consistent = run.final_submission_success == (final_role == CORRECT)
    else:
        scorer_consistent = False

    if not run.outcome_validation_observed:
        outcome_validator_consistent: bool | None = None
    else:
        outcome_validator_consistent = all(
            choice_role(action_id, **role_kwargs) in {CORRECT, MISLEADING, NEUTRAL}
            and contradiction
            == (choice_role(action_id, **role_kwargs) != CORRECT)
            for action_id, contradiction in zip(
                run.outcome_validated_action_ids,
                run.outcome_contradictions,
            )
        )

    effective_reversal = bool(
        run.feedback_observed
        and run.reversal_returned_to_retry is True
        and run.actual_reversal_action_type in REVERSAL_ACTION_TYPES
    )

    diagnostic_labels: list[str] = []
    if (
        selection_state_consistent is False
        or scorer_consistent is False
        or outcome_validator_consistent is False
    ):
        trajectory_label = "measurement_inconsistency"
        correct_action_switch: bool | None = None
        ordered_recovery: bool | None = None
        full_recovery: bool | None = None
        same_reentry: bool | None = None
        if selection_state_consistent is False:
            diagnostic_labels.append("selection_state_inconsistency")
        if scorer_consistent is False:
            diagnostic_labels.append("scorer_inconsistency")
        if outcome_validator_consistent is False:
            diagnostic_labels.append("outcome_validator_inconsistency")
        if run.interface_censored:
            diagnostic_labels.append("interface_censored")
    elif run.interface_censored:
        trajectory_label = "interface_censored"
        correct_action_switch = None
        ordered_recovery = None
        full_recovery = None
        same_reentry = None
    elif run.workflow_mode == SINGLE_ATTEMPT:
        correct_action_switch = None
        ordered_recovery = None
        full_recovery = None
        same_reentry = None
        if opportunity_role == CORRECT:
            trajectory_label = "single_attempt_correct_choice"
        elif opportunity_role == MISLEADING:
            trajectory_label = "single_attempt_misleading_choice"
        elif opportunity_role == NEUTRAL:
            trajectory_label = "single_attempt_neutral_choice"
        elif opportunity_role == NO_CHOICE:
            trajectory_label = "single_attempt_no_choice"
        else:
            trajectory_label = "single_attempt_unknown_choice"
    elif susceptible and not run.feedback_observed:
        trajectory_label = "review_not_observed"
        correct_action_switch = None
        ordered_recovery = None
        full_recovery = None
        same_reentry = None
        diagnostic_labels.append("review_not_observed")
    elif not susceptible:
        correct_action_switch = None
        ordered_recovery = None
        full_recovery = None
        same_reentry = None
        if opportunity_role == CORRECT:
            if MISLEADING in post_roles:
                if last_post_role == CORRECT:
                    trajectory_label = (
                        "review_induced_transient_misleading_regression"
                    )
                else:
                    trajectory_label = "review_induced_misleading_regression"
                diagnostic_labels.append("correct_initial_choice_regressed")
            elif NEUTRAL in post_roles:
                if last_post_role == CORRECT:
                    trajectory_label = "review_induced_transient_neutral_regression"
                else:
                    trajectory_label = "review_induced_neutral_regression"
                diagnostic_labels.append("correct_initial_choice_regressed")
            elif last_post_role == CORRECT:
                trajectory_label = "correct_choice_maintained_after_review"
            elif last_post_role == UNKNOWN:
                trajectory_label = "review_induced_unknown_choice"
            elif run.final_submission_success is True:
                trajectory_label = "initial_correct_confirmed"
            else:
                trajectory_label = "initial_correct_not_completed"
        elif opportunity_role == NEUTRAL:
            if last_post_role == CORRECT:
                trajectory_label = "neutral_error_corrected_nonvisual"
            elif last_post_role == MISLEADING:
                trajectory_label = "neutral_error_switched_to_misleading"
            else:
                trajectory_label = "neutral_error_not_visual_deception_eligible"
        elif opportunity_role == NO_CHOICE:
            trajectory_label = "no_visual_recovery_opportunity"
        else:
            trajectory_label = "unknown_choice_not_visual_deception_eligible"
    else:
        same_reentry = bool(
            effective_reversal
            and any(
                action_id == opportunity_action_id for action_id in post_choices
            )
        )
        correct_action_switch = last_post_role == CORRECT
        ordered_recovery = bool(
            effective_reversal
            and correct_action_switch
            and run.final_review_observed
            and not same_reentry
            and len(post_choices) == 1
        )
        if (
            ordered_recovery
            and run.final_submission_observed
            and run.final_submission_success is None
        ):
            full_recovery = None
        else:
            full_recovery = bool(
                ordered_recovery
                and run.final_submission_observed
                and run.final_submission_success is True
                and final_role == CORRECT
            )

        if run.reversal_returned_to_retry is False:
            trajectory_label = "reversal_failed"
        elif post_choices and not effective_reversal:
            trajectory_label = "reversal_unverified"
        elif not post_choices:
            trajectory_label = "recovery_incomplete"
        elif same_reentry:
            trajectory_label = "same_misleading_reentry"
        elif len(post_choices) > 1 and correct_action_switch:
            trajectory_label = "eventual_correct_action_after_multiple_attempts"
        elif correct_action_switch and not run.final_review_observed:
            trajectory_label = "correct_switch_not_observed"
        elif full_recovery is True:
            trajectory_label = "stable_recovery"
        elif ordered_recovery and not run.final_submission_observed:
            trajectory_label = "corrected_but_no_submit"
        elif ordered_recovery and full_recovery is None:
            trajectory_label = "corrected_but_submission_unscored"
        elif correct_action_switch:
            trajectory_label = "correct_action_switch_without_ordered_recovery"
        elif last_post_role == MISLEADING:
            trajectory_label = "different_misleading_reentry"
        elif last_post_role == NEUTRAL:
            trajectory_label = "retry_neutral_error"
        else:
            trajectory_label = "retry_unknown_action"

        if run.reversal_returned_to_retry is False:
            diagnostic_labels.append("reversal_failed")
        elif not effective_reversal:
            diagnostic_labels.append("reversal_unverified")
        if run.contradiction_recognized is True and not correct_action_switch:
            diagnostic_labels.append("feedback_understood_but_action_not_rebound")
        if correct_action_switch and not ordered_recovery:
            diagnostic_labels.append("correct_switch_without_ordered_recovery")
        if ordered_recovery and full_recovery is not True:
            diagnostic_labels.append("corrected_but_not_completed")
        if same_reentry:
            diagnostic_labels.append("same_misleading_reentry")
        if len(post_choices) > 1:
            diagnostic_labels.append("multiple_post_review_selections")

    return RecoveryAnalysis(
        run_id=run.run_id,
        trial_id=run.trial_id,
        pair_group_id=run.pair_group_id,
        condition=run.condition,
        arm=run.arm,
        task_id=run.task_id,
        task_instance_id=run.task_instance_id,
        chart_path=run.chart_path,
        recovery_branch=run.recovery_branch,
        evidence_level=run.evidence_level,
        evidence_record_id=run.evidence_record_id,
        evidence_source=run.evidence_source,
        evidence_review_status=run.evidence_review_status,
        evidence_reviewed_by=run.evidence_reviewed_by,
        evidence_reviewed_at=run.evidence_reviewed_at,
        review_regime=run.review_regime,
        retry_presentation=run.retry_presentation,
        ui_variant=run.ui_variant,
        renderer_build_id=run.renderer_build_id,
        viewport_width=run.viewport_width,
        viewport_height=run.viewport_height,
        checkpoint_id=run.checkpoint_id,
        checkpoint_stage=run.checkpoint_stage,
        reflection_training_status=run.reflection_training_status,
        history_mode=run.history_mode,
        workflow_mode=run.workflow_mode,
        training_recipe_match_id=run.training_recipe_match_id,
        training_recipe_review_status=run.training_recipe_review_status,
        training_recipe_reviewed_by=run.training_recipe_reviewed_by,
        training_recipe_reviewed_at=run.training_recipe_reviewed_at,
        initial_role=initial_role,
        opportunity_role=opportunity_role,
        eligibility_source=eligibility_source,
        initial_susceptible=susceptible,
        visual_recovery_eligible=eligible,
        retry_role=retry_role,
        last_post_review_role=last_post_role,
        final_role=final_role,
        correct_action_switch=correct_action_switch,
        ordered_recovery=ordered_recovery,
        full_recovery=full_recovery,
        same_misleading_reentry=same_reentry,
        selection_state_consistent=selection_state_consistent,
        scorer_consistent=scorer_consistent,
        outcome_record_ids=run.outcome_record_ids,
        outcome_contradictions=run.outcome_contradictions,
        outcome_validator_consistent=outcome_validator_consistent,
        reversal_action_type=run.actual_reversal_action_type,
        event_trace_replayed=event_trace_replayed,
        # A single trace can be replayed and classified, but the targeted
        # protocol reports condition effects only from a complete quartet.
        reportable=False,
        trajectory_label=trajectory_label,
        diagnostic_labels=tuple(diagnostic_labels),
    )


def analyze_summary(run: RecoveryRun) -> RecoveryAnalysis:
    """Return an explicitly censored view of an unverified supplied summary.

    This helper never makes the summary reportable, even if its
    ``event_trace_reduced`` flag was hand-filled.  Experimental analysis must
    call :func:`analyze_run`, which accepts and replays the event trace itself.
    """

    classified = _analyze_summary(run, event_trace_replayed=False)
    return replace(
        classified,
        correct_action_switch=None,
        ordered_recovery=None,
        full_recovery=None,
        same_misleading_reentry=None,
        reportable=False,
        trajectory_label="unverified_summary",
        diagnostic_labels=(
            *classified.diagnostic_labels,
            f"unverified_classifier_label:{classified.trajectory_label}",
        ),
    )


def classify_summary_for_testing(run: RecoveryRun) -> RecoveryAnalysis:
    """Exercise pure classification logic; never use this in an exporter."""

    return _analyze_summary(run, event_trace_replayed=False)


def analyze_run(
    base_fields: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
    *,
    registry: TargetedRecoveryRegistry | None = None,
) -> RecoveryAnalysis:
    """Replay one raw trace; canonical binding requires ``registry``.

    A registered result is trace-verified but remains case-level
    ``reportable=False`` until it participates in a complete quartet.
    """

    bound = (
        registry.bind_base_fields(base_fields)
        if registry is not None
        else dict(base_fields)
    )
    run = derive_run_from_events(bound, events)
    classified = _analyze_summary(run, event_trace_replayed=True)
    if registry is not None:
        return replace(
            classified,
            diagnostic_labels=(
                *classified.diagnostic_labels,
                "canonical_registry_bound",
            ),
        )
    return replace(
        classified,
        correct_action_switch=None,
        ordered_recovery=None,
        full_recovery=None,
        same_misleading_reentry=None,
        reportable=False,
        trajectory_label="unverified_case_registry",
        diagnostic_labels=(
            *classified.diagnostic_labels,
            "canonical_registry_not_bound",
        ),
    )


@dataclass(frozen=True)
class RecoveryComparison:
    candidate_run_id: str
    reference_run_id: str
    candidate_trial_id: str
    reference_trial_id: str
    pair_group_id: str
    arm: str
    task_id: str
    task_instance_id: str
    chart_path: str
    recovery_branch: str
    ui_variant: str
    renderer_build_id: str
    viewport_width: int
    viewport_height: int
    candidate_evidence_level: str | None
    reference_evidence_level: str | None
    candidate_evidence_record_id: str | None
    reference_evidence_record_id: str | None
    candidate_evidence_source: str | None
    reference_evidence_source: str | None
    candidate_evidence_review_status: str
    reference_evidence_review_status: str
    candidate_evidence_reviewed_by: str | None
    reference_evidence_reviewed_by: str | None
    candidate_evidence_reviewed_at: str | None
    reference_evidence_reviewed_at: str | None
    candidate_review_regime: str
    reference_review_regime: str
    candidate_retry_presentation: str
    reference_retry_presentation: str
    candidate_checkpoint_id: str
    reference_checkpoint_id: str
    candidate_checkpoint_stage: str
    reference_checkpoint_stage: str
    candidate_reflection_training_status: str
    reference_reflection_training_status: str
    candidate_history_mode: str
    reference_history_mode: str
    candidate_workflow_mode: str
    reference_workflow_mode: str
    candidate_training_recipe_match_id: str | None
    reference_training_recipe_match_id: str | None
    candidate_training_recipe_review_status: str
    reference_training_recipe_review_status: str
    candidate_training_recipe_reviewed_by: str | None
    reference_training_recipe_reviewed_by: str | None
    candidate_training_recipe_reviewed_at: str | None
    reference_training_recipe_reviewed_at: str | None
    candidate_reversal_action_type: str | None
    reference_reversal_action_type: str | None
    candidate_condition: str
    reference_condition: str
    contrast_axis: str
    event_traces_replayed: bool
    reportable: bool
    category: str
    comparable: bool
    comparison_scope: str
    candidate_trajectory: str
    reference_trajectory: str
    correct_action_switch_contrast: str
    ordered_recovery_contrast: str
    full_recovery_contrast: str
    final_submission_success_contrast: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ALWAYS_MATCHED_FIELDS = (
    "trial_id",
    "pair_group_id",
    "arm",
    "task_id",
    "task_instance_id",
    "chart_path",
    "correct_action_id",
    "misleading_action_ids",
    "neutral_action_ids",
    "recovery_branch",
    "ui_variant",
    "renderer_build_id",
    "viewport_width",
    "viewport_height",
    "display_order",
    "display_tokens",
    "choice_token_to_action_id",
)
_RETRY_MATCHED_FIELDS = (
    "evidence_level",
    "evidence_record_id",
    "evidence_source",
    "evidence_review_status",
    "evidence_reviewed_by",
    "evidence_reviewed_at",
    "review_regime",
    "retry_presentation",
)


def _validate_matched_runs(
    candidate: RecoveryRun,
    reference: RecoveryRun,
    *,
    contrast_axis: str,
) -> None:
    if contrast_axis not in CONTRAST_AXES:
        raise ValueError(
            f"unknown contrast_axis {contrast_axis!r}; "
            f"choose one of {sorted(CONTRAST_AXES)}"
        )
    matched_fields = list(_ALWAYS_MATCHED_FIELDS)
    if (
        candidate.workflow_mode == FEEDBACK_RETRY
        and reference.workflow_mode == FEEDBACK_RETRY
    ):
        matched_fields.extend(_RETRY_MATCHED_FIELDS)
    if contrast_axis == REPLICATION_CONTRAST:
        matched_fields.extend(
            (
                "checkpoint_id",
                "checkpoint_stage",
                "reflection_training_status",
                "history_mode",
                "workflow_mode",
                "training_recipe_match_id",
                "training_recipe_review_status",
                "training_recipe_reviewed_by",
                "training_recipe_reviewed_at",
            )
        )
    elif contrast_axis == WORKFLOW_CONTRAST:
        matched_fields.extend(
            (
                "checkpoint_id",
                "checkpoint_stage",
                "reflection_training_status",
                "history_mode",
                "training_recipe_match_id",
                "training_recipe_review_status",
                "training_recipe_reviewed_by",
                "training_recipe_reviewed_at",
            )
        )
    elif contrast_axis == HISTORY_CONTRAST:
        matched_fields.extend(
            (
                "checkpoint_id",
                "checkpoint_stage",
                "reflection_training_status",
                "workflow_mode",
                "training_recipe_match_id",
                "training_recipe_review_status",
                "training_recipe_reviewed_by",
                "training_recipe_reviewed_at",
            )
        )
    elif contrast_axis == REFLECTION_TRAINING_CONTRAST:
        matched_fields.extend(
            (
                "checkpoint_stage",
                "history_mode",
                "workflow_mode",
                "training_recipe_match_id",
                "training_recipe_review_status",
                "training_recipe_reviewed_by",
                "training_recipe_reviewed_at",
            )
        )
    mismatches = {
        field: (getattr(candidate, field), getattr(reference, field))
        for field in matched_fields
        if getattr(candidate, field) != getattr(reference, field)
    }
    if candidate.recovery_branch == STANDARDIZED_MISTAKE:
        if candidate.injected_mistake_action_id != reference.injected_mistake_action_id:
            mismatches["injected_mistake_action_id"] = (
                candidate.injected_mistake_action_id,
                reference.injected_mistake_action_id,
            )
    if candidate.run_id == reference.run_id:
        mismatches["run_id"] = (
            candidate.run_id,
            "candidate and reference require distinct run ids",
        )
    if (
        contrast_axis == WORKFLOW_CONTRAST
        and candidate.workflow_mode == reference.workflow_mode
    ):
        mismatches["workflow_mode"] = (
            candidate.workflow_mode,
            "expected a different reference workflow_mode",
        )
    if (
        contrast_axis == HISTORY_CONTRAST
        and candidate.history_mode == reference.history_mode
    ):
        mismatches["history_mode"] = (
            candidate.history_mode,
            "expected a different reference history_mode",
        )
    if contrast_axis == REFLECTION_TRAINING_CONTRAST:
        if (
            candidate.reflection_training_status
            == reference.reflection_training_status
        ):
            mismatches["reflection_training_status"] = (
                candidate.reflection_training_status,
                "expected different reflection-training statuses",
            )
        if (
            not candidate.training_recipe_match_id
            or candidate.training_recipe_review_status != "approved"
            or reference.training_recipe_review_status != "approved"
        ):
            mismatches["training_recipe_provenance"] = (
                candidate.training_recipe_match_id,
                candidate.training_recipe_review_status,
                reference.training_recipe_review_status,
                "reflection_training contrast requires an approved matched recipe",
            )
    if mismatches:
        raise ValueError(
            f"recovery runs are not matched for contrast_axis="
            f"{contrast_axis!r}: {mismatches}"
        )


def _compare_summaries(
    candidate: RecoveryRun,
    reference: RecoveryRun,
    *,
    contrast_axis: str,
    event_traces_replayed: bool,
) -> RecoveryComparison:
    """Compare two summaries under one explicitly declared contrast axis.

    The function uses the neutral terms ``candidate`` and ``reference``.  It
    makes no claim that either checkpoint or context ablation removes
    GUI-Reflection training.
    """

    _validate_matched_runs(
        candidate, reference, contrast_axis=contrast_axis
    )
    candidate_analysis = _analyze_summary(
        candidate, event_trace_replayed=event_traces_replayed
    )
    reference_analysis = _analyze_summary(
        reference, event_trace_replayed=event_traces_replayed
    )

    if (
        candidate_analysis.selection_state_consistent is False
        or reference_analysis.selection_state_consistent is False
        or candidate_analysis.scorer_consistent is False
        or reference_analysis.scorer_consistent is False
    ):
        category = "measurement_inconsistency"
        comparable = False
        comparison_scope = "not_comparable"
    elif candidate.interface_censored or reference.interface_censored:
        category = "interface_censored"
        comparable = False
        comparison_scope = "not_comparable"
    elif contrast_axis == DESCRIPTIVE_SYSTEM_CONTRAST:
        category = "descriptive_noncausal"
        comparable = False
        comparison_scope = "descriptive_noncausal"
    elif candidate.workflow_mode != reference.workflow_mode:
        category = "workflow_mode_contrast"
        comparable = True
        comparison_scope = "whole_trajectory_workflow_contrast"
    elif (
        candidate.recovery_branch == NATURAL_RECOVERY
        and candidate.workflow_mode == SINGLE_ATTEMPT
    ):
        initial_pair = (
            candidate_analysis.initial_role,
            reference_analysis.initial_role,
        )
        if initial_pair == (CORRECT, CORRECT):
            category = "both_single_attempt_correct_choice"
        elif initial_pair == (MISLEADING, MISLEADING):
            category = "both_single_attempt_misleading_choice"
        elif initial_pair == (NEUTRAL, NEUTRAL):
            category = "both_single_attempt_neutral_choice"
        else:
            category = "single_attempt_initial_choice_divergence"
        comparable = True
        comparison_scope = "whole_trajectory_single_attempt"
    elif candidate.recovery_branch == NATURAL_RECOVERY:
        initial_pair = (
            candidate_analysis.initial_role,
            reference_analysis.initial_role,
        )
        if initial_pair == (CORRECT, MISLEADING):
            category = "candidate_prevents_initial_deception"
            comparable = True
            comparison_scope = "whole_trajectory_only"
        elif initial_pair == (MISLEADING, CORRECT):
            category = "reference_prevents_initial_deception"
            comparable = True
            comparison_scope = "whole_trajectory_only"
        elif initial_pair == (CORRECT, CORRECT):
            candidate_regressed = candidate_analysis.trajectory_label.startswith(
                "review_induced_"
            )
            reference_regressed = reference_analysis.trajectory_label.startswith(
                "review_induced_"
            )
            if candidate_regressed and reference_regressed:
                category = "both_review_induced_regression"
            elif candidate_regressed:
                category = "candidate_only_review_induced_regression"
            elif reference_regressed:
                category = "reference_only_review_induced_regression"
            else:
                category = "both_prevent_initial_deception"
            comparable = True
            comparison_scope = "whole_trajectory_prevention"
        elif initial_pair != (MISLEADING, MISLEADING):
            category = "not_comparable_different_eligibility"
            comparable = False
            comparison_scope = "not_comparable"
        elif not (
            candidate_analysis.visual_recovery_eligible
            and reference_analysis.visual_recovery_eligible
        ):
            category = "not_comparable_review_opportunity"
            comparable = False
            comparison_scope = "not_comparable"
        else:
            category = _compare_eligible_recovery(
                candidate_analysis, reference_analysis
            )
            comparable = True
            comparison_scope = "matched_natural_recovery"
    elif not (
        candidate_analysis.visual_recovery_eligible
        and reference_analysis.visual_recovery_eligible
    ):
        category = "not_comparable_standardized_recovery_opportunity"
        comparable = False
        comparison_scope = "not_comparable"
    else:
        category = _compare_eligible_recovery(
            candidate_analysis, reference_analysis
        )
        comparable = True
        comparison_scope = "matched_standardized_mistake_recovery"

    if comparison_scope.startswith("matched_"):
        switch_contrast = _boolean_contrast(
            candidate_analysis.correct_action_switch,
            reference_analysis.correct_action_switch,
            "correct_action_switch",
        )
        ordered_contrast = _boolean_contrast(
            candidate_analysis.ordered_recovery,
            reference_analysis.ordered_recovery,
            "ordered_recovery",
        )
        full_contrast = _boolean_contrast(
            candidate_analysis.full_recovery,
            reference_analysis.full_recovery,
            "full_recovery",
        )
    elif comparison_scope == "whole_trajectory_prevention":
        switch_contrast = "not_applicable_no_recovery_opportunity"
        ordered_contrast = "not_applicable_no_recovery_opportunity"
        full_contrast = "not_applicable_no_recovery_opportunity"
    elif comparison_scope in {
        "whole_trajectory_only",
        "whole_trajectory_workflow_contrast",
    }:
        switch_contrast = "not_comparable_different_recovery_opportunity"
        ordered_contrast = "not_comparable_different_recovery_opportunity"
        full_contrast = "not_comparable_different_recovery_opportunity"
    else:
        switch_contrast = "not_comparable"
        ordered_contrast = "not_comparable"
        full_contrast = "not_comparable"

    if category in {"interface_censored", "measurement_inconsistency"}:
        final_submission_contrast = "final_submission_success_censored"
    elif category == "descriptive_noncausal":
        final_submission_contrast = "descriptive_noncausal"
    else:
        final_submission_contrast = _boolean_contrast(
            _submission_success_value(candidate),
            _submission_success_value(reference),
            "final_submission_success",
        )

    return RecoveryComparison(
        candidate_run_id=candidate.run_id,
        reference_run_id=reference.run_id,
        candidate_trial_id=candidate.trial_id,
        reference_trial_id=reference.trial_id,
        pair_group_id=candidate.pair_group_id,
        arm=candidate.arm,
        task_id=candidate.task_id,
        task_instance_id=candidate.task_instance_id,
        chart_path=candidate.chart_path,
        recovery_branch=candidate.recovery_branch,
        ui_variant=candidate.ui_variant,
        renderer_build_id=candidate.renderer_build_id,
        viewport_width=candidate.viewport_width,
        viewport_height=candidate.viewport_height,
        candidate_evidence_level=candidate.evidence_level,
        reference_evidence_level=reference.evidence_level,
        candidate_evidence_record_id=candidate.evidence_record_id,
        reference_evidence_record_id=reference.evidence_record_id,
        candidate_evidence_source=candidate.evidence_source,
        reference_evidence_source=reference.evidence_source,
        candidate_evidence_review_status=candidate.evidence_review_status,
        reference_evidence_review_status=reference.evidence_review_status,
        candidate_evidence_reviewed_by=candidate.evidence_reviewed_by,
        reference_evidence_reviewed_by=reference.evidence_reviewed_by,
        candidate_evidence_reviewed_at=candidate.evidence_reviewed_at,
        reference_evidence_reviewed_at=reference.evidence_reviewed_at,
        candidate_review_regime=candidate.review_regime,
        reference_review_regime=reference.review_regime,
        candidate_retry_presentation=candidate.retry_presentation,
        reference_retry_presentation=reference.retry_presentation,
        candidate_checkpoint_id=candidate.checkpoint_id,
        reference_checkpoint_id=reference.checkpoint_id,
        candidate_checkpoint_stage=candidate.checkpoint_stage,
        reference_checkpoint_stage=reference.checkpoint_stage,
        candidate_reflection_training_status=(
            candidate.reflection_training_status
        ),
        reference_reflection_training_status=(
            reference.reflection_training_status
        ),
        candidate_history_mode=candidate.history_mode,
        reference_history_mode=reference.history_mode,
        candidate_workflow_mode=candidate.workflow_mode,
        reference_workflow_mode=reference.workflow_mode,
        candidate_training_recipe_match_id=candidate.training_recipe_match_id,
        reference_training_recipe_match_id=reference.training_recipe_match_id,
        candidate_training_recipe_review_status=(
            candidate.training_recipe_review_status
        ),
        reference_training_recipe_review_status=(
            reference.training_recipe_review_status
        ),
        candidate_training_recipe_reviewed_by=(
            candidate.training_recipe_reviewed_by
        ),
        reference_training_recipe_reviewed_by=(
            reference.training_recipe_reviewed_by
        ),
        candidate_training_recipe_reviewed_at=(
            candidate.training_recipe_reviewed_at
        ),
        reference_training_recipe_reviewed_at=(
            reference.training_recipe_reviewed_at
        ),
        candidate_reversal_action_type=(
            candidate.actual_reversal_action_type
        ),
        reference_reversal_action_type=(
            reference.actual_reversal_action_type
        ),
        candidate_condition=candidate.condition,
        reference_condition=reference.condition,
        contrast_axis=contrast_axis,
        event_traces_replayed=event_traces_replayed,
        # One arm is not the protocol's official/clean quartet.
        reportable=False,
        category=category,
        comparable=comparable,
        comparison_scope=comparison_scope,
        candidate_trajectory=candidate_analysis.trajectory_label,
        reference_trajectory=reference_analysis.trajectory_label,
        correct_action_switch_contrast=switch_contrast,
        ordered_recovery_contrast=ordered_contrast,
        full_recovery_contrast=full_contrast,
        final_submission_success_contrast=final_submission_contrast,
    )


def compare_summaries(
    candidate: RecoveryRun,
    reference: RecoveryRun,
    *,
    contrast_axis: str,
) -> RecoveryComparison:
    """Return an explicitly censored comparison of unverified summaries."""

    classified = _compare_summaries(
        candidate,
        reference,
        contrast_axis=contrast_axis,
        event_traces_replayed=False,
    )
    return replace(
        classified,
        category="unverified_summary_comparison",
        comparable=False,
        comparison_scope="unverified_summary",
        event_traces_replayed=False,
        reportable=False,
        correct_action_switch_contrast="unverified_summary",
        ordered_recovery_contrast="unverified_summary",
        full_recovery_contrast="unverified_summary",
        final_submission_success_contrast="unverified_summary",
    )


def classify_summary_pair_for_testing(
    candidate: RecoveryRun,
    reference: RecoveryRun,
    *,
    contrast_axis: str,
) -> RecoveryComparison:
    """Exercise pure pair classification; never use this in an exporter."""

    return _compare_summaries(
        candidate,
        reference,
        contrast_axis=contrast_axis,
        event_traces_replayed=False,
    )


def compare_runs(
    candidate_base_fields: Mapping[str, Any],
    candidate_events: Iterable[Mapping[str, Any]],
    reference_base_fields: Mapping[str, Any],
    reference_events: Iterable[Mapping[str, Any]],
    *,
    contrast_axis: str,
    registry: TargetedRecoveryRegistry | None = None,
) -> RecoveryComparison:
    """Replay one arm pair; final reporting requires a complete quartet."""

    candidate_base = (
        registry.bind_base_fields(candidate_base_fields)
        if registry is not None
        else dict(candidate_base_fields)
    )
    reference_base = (
        registry.bind_base_fields(reference_base_fields)
        if registry is not None
        else dict(reference_base_fields)
    )
    candidate = derive_run_from_events(candidate_base, candidate_events)
    reference = derive_run_from_events(reference_base, reference_events)
    if registry is not None and contrast_axis == REFLECTION_TRAINING_CONTRAST:
        registry.validate_training_contrast(candidate, reference)
    compared = _compare_summaries(
        candidate,
        reference,
        contrast_axis=contrast_axis,
        event_traces_replayed=True,
    )
    if registry is not None:
        return compared
    return replace(
        compared,
        reportable=False,
        comparable=False,
        category="unverified_case_registry",
        comparison_scope="unverified_case_registry",
        correct_action_switch_contrast="unverified_case_registry",
        ordered_recovery_contrast="unverified_case_registry",
        full_recovery_contrast="unverified_case_registry",
        final_submission_success_contrast="unverified_case_registry",
    )


QUARTET_CELL_KEYS = (
    "candidate_official",
    "reference_official",
    "candidate_clean",
    "reference_clean",
)

PUBLICATION_BLOCKERS = (
    "authoritative_registry_loader_pending",
    "compact_renderer_browser_collector_pending",
    "model_action_execution_receipts_pending",
    "immutable_capture_receipts_pending",
    "model_input_history_binding_pending",
)


@dataclass(frozen=True)
class RecoveryQuartet:
    """One structurally complete candidate/reference × official/clean bundle.

    ``protocol_complete`` means only that synthetic/raw records satisfy this
    module's schema.  ``reportable`` remains false until an authoritative
    registry loader and browser collector authenticate how those records were
    produced.
    """

    pair_group_id: str
    trial_id: str
    contrast_id: str
    contrast_axis: str
    candidate_condition: str
    reference_condition: str
    recovery_branch: str
    review_regime: str
    retry_presentation: str
    ui_variant: str
    evidence_level: str | None
    evidence_record_id: str | None
    candidate_evidence_level: str | None
    reference_evidence_level: str | None
    candidate_evidence_record_id: str | None
    reference_evidence_record_id: str | None
    observed_cells: tuple[str, ...]
    event_traces_replayed: bool
    protocol_complete: bool
    reportable: bool
    official_comparison: RecoveryComparison
    clean_comparison: RecoveryComparison
    cell_analyses: Mapping[str, RecoveryAnalysis]
    run_ids: tuple[str, ...]
    submission_ids: tuple[str, ...]
    scorer_record_ids: tuple[str, ...]
    outcome_record_ids: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    model_step_ids: tuple[str, ...]
    model_response_ids: tuple[str, ...]
    execution_receipt_ids: tuple[str, ...]
    publication_blockers: tuple[str, ...]
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_group_id": self.pair_group_id,
            "trial_id": self.trial_id,
            "contrast_id": self.contrast_id,
            "contrast_axis": self.contrast_axis,
            "candidate_condition": self.candidate_condition,
            "reference_condition": self.reference_condition,
            "recovery_branch": self.recovery_branch,
            "review_regime": self.review_regime,
            "retry_presentation": self.retry_presentation,
            "ui_variant": self.ui_variant,
            "evidence_level": self.evidence_level,
            "evidence_record_id": self.evidence_record_id,
            "candidate_evidence_level": self.candidate_evidence_level,
            "reference_evidence_level": self.reference_evidence_level,
            "candidate_evidence_record_id": self.candidate_evidence_record_id,
            "reference_evidence_record_id": self.reference_evidence_record_id,
            "observed_cells": list(self.observed_cells),
            "event_traces_replayed": self.event_traces_replayed,
            "protocol_complete": self.protocol_complete,
            "reportable": self.reportable,
            "official_comparison": self.official_comparison.to_dict(),
            "clean_comparison": self.clean_comparison.to_dict(),
            "cell_analyses": {
                key: analysis.to_dict()
                for key, analysis in self.cell_analyses.items()
            },
            "run_ids": list(self.run_ids),
            "submission_ids": list(self.submission_ids),
            "scorer_record_ids": list(self.scorer_record_ids),
            "outcome_record_ids": list(self.outcome_record_ids),
            "artifact_paths": list(self.artifact_paths),
            "model_step_ids": list(self.model_step_ids),
            "model_response_ids": list(self.model_response_ids),
            "execution_receipt_ids": list(self.execution_receipt_ids),
            "publication_blockers": list(self.publication_blockers),
            "reasons": list(self.reasons),
        }


def _raw_quartet_cell(
    cells: Mapping[str, Mapping[str, Any]], key: str
) -> tuple[Mapping[str, Any], Iterable[Mapping[str, Any]]]:
    raw_cell = cells.get(key)
    if not isinstance(raw_cell, Mapping) or set(raw_cell) != {
        "base_fields",
        "events",
    }:
        raise ValueError(
            f"quartet cell {key!r} must contain only base_fields and raw events"
        )
    base_fields = raw_cell.get("base_fields")
    events = raw_cell.get("events")
    if not isinstance(base_fields, Mapping):
        raise ValueError(f"quartet cell {key!r} has no base_fields mapping")
    if isinstance(events, (str, bytes, Mapping)) or not isinstance(events, Iterable):
        raise ValueError(f"quartet cell {key!r} has no raw event iterable")
    return base_fields, events


def analyze_recovery_quartet(
    cells: Mapping[str, Mapping[str, Any]],
    *,
    contrast_id: str,
    registry: TargetedRecoveryRegistry,
) -> RecoveryQuartet:
    """Replay a structurally complete case quartet without publishing it.

    The result is deliberately ``reportable=False`` while the authoritative
    loader, renderer, collector, and receipt stores remain unimplemented.
    """

    if not isinstance(registry, TargetedRecoveryRegistry):
        raise TypeError("a TargetedRecoveryRegistry is required")
    try:
        contrast = registry.resolve_contrast(contrast_id)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    contrast_axis = contrast["contrast_axis"]
    if set(cells) != set(QUARTET_CELL_KEYS):
        raise ValueError(
            "quartet requires exactly candidate/reference × official/clean; "
            f"missing={sorted(set(QUARTET_CELL_KEYS) - set(cells))}, "
            f"unknown={sorted(set(cells) - set(QUARTET_CELL_KEYS))}"
        )

    runs: dict[str, RecoveryRun] = {}
    for key in QUARTET_CELL_KEYS:
        base_fields, events = _raw_quartet_cell(cells, key)
        bound = registry.bind_base_fields(base_fields)
        runs[key] = derive_run_from_events(bound, events)

    expected_arms = {
        "candidate_official": OFFICIAL_ARM,
        "reference_official": OFFICIAL_ARM,
        "candidate_clean": CLEAN_ARM,
        "reference_clean": CLEAN_ARM,
    }
    mismatches: dict[str, Any] = {}
    for key, expected_arm in expected_arms.items():
        if runs[key].arm != expected_arm:
            mismatches[f"{key}.arm"] = (runs[key].arm, expected_arm)

    candidate_condition = runs["candidate_official"].condition
    reference_condition = runs["reference_official"].condition
    if runs["candidate_clean"].condition != candidate_condition:
        mismatches["candidate_condition_across_arms"] = (
            candidate_condition,
            runs["candidate_clean"].condition,
        )
    if runs["reference_clean"].condition != reference_condition:
        mismatches["reference_condition_across_arms"] = (
            reference_condition,
            runs["reference_clean"].condition,
        )
    if candidate_condition != contrast["candidate_condition"]:
        mismatches["candidate_condition_role"] = (
            candidate_condition,
            contrast["candidate_condition"],
        )
    if reference_condition != contrast["reference_condition"]:
        mismatches["reference_condition_role"] = (
            reference_condition,
            contrast["reference_condition"],
        )

    run_ids = [run.run_id for run in runs.values()]
    if len(run_ids) != len(set(run_ids)):
        mismatches["run_id"] = "all four run ids must be unique"

    symmetric_fields = (
        "pair_group_id",
        "trial_id",
        "recovery_branch",
        "ui_variant",
        "renderer_build_id",
        "viewport_width",
        "viewport_height",
        "display_order",
        "display_tokens",
        "choice_token_to_action_id",
        "injected_mistake_action_id",
    )
    first_run = runs[QUARTET_CELL_KEYS[0]]
    for field_name in symmetric_fields:
        values = {
            key: getattr(run, field_name) for key, run in runs.items()
        }
        if any(value != getattr(first_run, field_name) for value in values.values()):
            mismatches[field_name] = values

    role_provenance_fields = (
        "evidence_level",
        "evidence_record_id",
        "evidence_source",
        "evidence_review_status",
        "evidence_reviewed_by",
        "evidence_reviewed_at",
        "review_regime",
        "retry_presentation",
        "checkpoint_id",
        "checkpoint_stage",
        "reflection_training_status",
        "history_mode",
        "workflow_mode",
        "training_recipe_match_id",
        "training_recipe_review_status",
        "training_recipe_reviewed_by",
        "training_recipe_reviewed_at",
    )
    for role in ("candidate", "reference"):
        official = runs[f"{role}_official"]
        clean = runs[f"{role}_clean"]
        for field_name in role_provenance_fields:
            if getattr(official, field_name) != getattr(clean, field_name):
                mismatches[f"{role}.{field_name}"] = (
                    getattr(official, field_name),
                    getattr(clean, field_name),
                )

    globally_unique_fields = {
        "submission_id": [
            run.submission_id for run in runs.values() if run.submission_id
        ],
        "scorer_record_id": [
            run.scorer_record_id for run in runs.values() if run.scorer_record_id
        ],
        "outcome_record_id": [
            record_id
            for run in runs.values()
            for record_id in run.outcome_record_ids
        ],
        "artifact_path": [
            path for run in runs.values() for path in run.observed_artifact_paths
        ],
        "model_step_id": [
            step_id for run in runs.values() for step_id in run.observed_model_step_ids
        ],
        "model_response_id": [
            response_id
            for run in runs.values()
            for response_id in run.observed_model_response_ids
        ],
        "execution_receipt_id": [
            receipt_id
            for run in runs.values()
            for receipt_id in run.observed_execution_receipt_ids
        ],
    }
    for field_name, values in globally_unique_fields.items():
        if len(values) != len(set(values)):
            mismatches[field_name] = "identifiers/artifacts must be unique across quartet"
    if mismatches:
        raise ValueError(f"quartet symmetry validation failed: {mismatches}")

    official_candidate = runs["candidate_official"]
    official_reference = runs["reference_official"]
    clean_candidate = runs["candidate_clean"]
    clean_reference = runs["reference_clean"]
    if contrast_axis == REFLECTION_TRAINING_CONTRAST:
        registry.validate_training_contrast(
            official_candidate, official_reference
        )
        registry.validate_training_contrast(clean_candidate, clean_reference)
    official_comparison = _compare_summaries(
        official_candidate,
        official_reference,
        contrast_axis=contrast_axis,
        event_traces_replayed=True,
    )
    clean_comparison = _compare_summaries(
        clean_candidate,
        clean_reference,
        contrast_axis=contrast_axis,
        event_traces_replayed=True,
    )
    cell_analyses = {
        key: _analyze_summary(run, event_trace_replayed=True)
        for key, run in runs.items()
    }
    candidate_evidence_level = official_candidate.evidence_level
    reference_evidence_level = official_reference.evidence_level
    candidate_evidence_record_id = official_candidate.evidence_record_id
    reference_evidence_record_id = official_reference.evidence_record_id
    shared_evidence_level = (
        candidate_evidence_level
        if candidate_evidence_level == reference_evidence_level
        else None
    )
    shared_evidence_record_id = (
        candidate_evidence_record_id
        if candidate_evidence_record_id == reference_evidence_record_id
        else None
    )
    shared_review_regime = (
        official_candidate.review_regime
        if official_candidate.review_regime == official_reference.review_regime
        else "mixed_by_contrast"
    )
    publication_blockers = PUBLICATION_BLOCKERS
    if contrast_axis == REFLECTION_TRAINING_CONTRAST:
        publication_blockers = (
            *publication_blockers,
            "stage_matched_training_recipe_artifact_pending",
        )
    if (
        candidate_evidence_level in OUTCOME_FEEDBACK_LEVELS
        or reference_evidence_level in OUTCOME_FEEDBACK_LEVELS
    ):
        publication_blockers = (
            *publication_blockers,
            "independent_f3_validator_store_pending",
        )
    if first_run.recovery_branch == STANDARDIZED_MISTAKE:
        publication_blockers = (
            *publication_blockers,
            "standardized_mistake_intervention_receipt_pending",
        )
    return RecoveryQuartet(
        pair_group_id=first_run.pair_group_id,
        trial_id=first_run.trial_id,
        contrast_id=contrast_id,
        contrast_axis=contrast_axis,
        candidate_condition=candidate_condition,
        reference_condition=reference_condition,
        recovery_branch=first_run.recovery_branch,
        review_regime=shared_review_regime,
        retry_presentation=first_run.retry_presentation,
        ui_variant=first_run.ui_variant,
        evidence_level=shared_evidence_level,
        evidence_record_id=shared_evidence_record_id,
        candidate_evidence_level=candidate_evidence_level,
        reference_evidence_level=reference_evidence_level,
        candidate_evidence_record_id=candidate_evidence_record_id,
        reference_evidence_record_id=reference_evidence_record_id,
        observed_cells=QUARTET_CELL_KEYS,
        event_traces_replayed=True,
        protocol_complete=True,
        reportable=False,
        official_comparison=official_comparison,
        clean_comparison=clean_comparison,
        cell_analyses=cell_analyses,
        run_ids=tuple(run_ids),
        submission_ids=tuple(globally_unique_fields["submission_id"]),
        scorer_record_ids=tuple(globally_unique_fields["scorer_record_id"]),
        outcome_record_ids=tuple(globally_unique_fields["outcome_record_id"]),
        artifact_paths=tuple(globally_unique_fields["artifact_path"]),
        model_step_ids=tuple(globally_unique_fields["model_step_id"]),
        model_response_ids=tuple(globally_unique_fields["model_response_id"]),
        execution_receipt_ids=tuple(
            globally_unique_fields["execution_receipt_id"]
        ),
        publication_blockers=publication_blockers,
        reasons=publication_blockers,
    )


AUTONOMOUS_EVIDENCE_PATH = (
    F0_NEUTRAL_RECHECK,
    F1_CHECKLIST,
    F2_AUDITED_VALUES,
)


@dataclass(frozen=True)
class RecoveryLadderValidation:
    pair_group_id: str
    trial_id: str
    declared_stage_plan: tuple[str, ...]
    protocol_complete_autonomous_prefix: tuple[str, ...]
    reportable_autonomous_prefix: tuple[str, ...]
    invalid_levels: tuple[str, ...]
    outcome_probe_protocol_complete: bool
    outcome_probe_reportable: bool
    experiment_reportable: bool
    all_planned_complete: bool
    publication_blockers: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        for field_name in (
            "declared_stage_plan",
            "protocol_complete_autonomous_prefix",
            "reportable_autonomous_prefix",
            "invalid_levels",
            "publication_blockers",
            "reasons",
        ):
            row[field_name] = list(row[field_name])
        return row


def validate_case_ladder(
    cells_by_level: Mapping[str, Mapping[str, Mapping[str, Any]] | None],
    *,
    declared_stage_plan: Iterable[str],
    contrast_id: str,
    registry: TargetedRecoveryRegistry,
) -> RecoveryLadderValidation:
    """Replay every supplied level, then validate prefix closure and F3."""

    plan = tuple(declared_stage_plan)
    if not plan or len(plan) != len(set(plan)):
        raise ValueError("declared_stage_plan must be non-empty and unique")
    if not isinstance(registry, TargetedRecoveryRegistry):
        raise TypeError("a TargetedRecoveryRegistry is required")
    try:
        contrast = registry.resolve_contrast(contrast_id)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    if contrast["contrast_axis"] == WORKFLOW_CONTRAST:
        raise ValueError(
            "evidence ladder excludes workflow contrast: its single-attempt "
            "reference has no review evidence; analyze one workflow quartet instead"
        )
    unknown = set(plan) - set(EVIDENCE_LEVELS)
    if unknown:
        raise ValueError(f"declared_stage_plan has unknown levels: {sorted(unknown)}")
    if set(cells_by_level) != set(plan):
        raise ValueError(
            "ladder entries must exactly match declared_stage_plan; "
            f"missing={sorted(set(plan) - set(cells_by_level))}, "
            f"unknown={sorted(set(cells_by_level) - set(plan))}"
        )

    autonomous_plan = tuple(level for level in plan if level in AUTONOMOUS_EVIDENCE_PATH)
    if autonomous_plan:
        highest = max(AUTONOMOUS_EVIDENCE_PATH.index(level) for level in autonomous_plan)
        required_prefix = AUTONOMOUS_EVIDENCE_PATH[: highest + 1]
        if autonomous_plan != required_prefix:
            raise ValueError(
                "autonomous evidence plan must be prefix-closed F0→F1→F2"
            )

    quartets: dict[str, RecoveryQuartet | None] = {}
    for level in plan:
        raw_cells = cells_by_level[level]
        quartets[level] = (
            None
            if raw_cells is None
            else analyze_recovery_quartet(
                raw_cells,
                contrast_id=contrast_id,
                registry=registry,
            )
        )

    nonempty = [quartet for quartet in quartets.values() if quartet is not None]
    if not nonempty:
        raise ValueError("ladder has no observed quartet")
    publication_blockers = tuple(
        dict.fromkeys(
            blocker
            for quartet in nonempty
            for blocker in quartet.publication_blockers
        )
    )
    pair_group_id = nonempty[0].pair_group_id
    trial_id = nonempty[0].trial_id
    contrast_axis = nonempty[0].contrast_axis
    resolved_contrast_id = nonempty[0].contrast_id
    candidate_condition = nonempty[0].candidate_condition
    reference_condition = nonempty[0].reference_condition
    recovery_branch = nonempty[0].recovery_branch
    retry_presentation = nonempty[0].retry_presentation
    ui_variant = nonempty[0].ui_variant
    reasons: list[str] = []
    invalid: list[str] = []

    def valid_quartet(level: str, quartet: RecoveryQuartet | None) -> bool:
        return bool(
            quartet is not None
            and quartet.protocol_complete
            and quartet.evidence_level == level
            and quartet.pair_group_id == pair_group_id
            and quartet.trial_id == trial_id
            and quartet.contrast_axis == contrast_axis
            and quartet.contrast_id == resolved_contrast_id
            and quartet.candidate_condition == candidate_condition
            and quartet.reference_condition == reference_condition
            and quartet.recovery_branch == recovery_branch
            and quartet.retry_presentation == retry_presentation
            and quartet.ui_variant == ui_variant
            and quartet.review_regime == EVIDENCE_REVIEW_REGIMES[level]
        )

    reused_identity_levels: set[str] = set()
    seen_identities: dict[str, set[str]] = {
        "run_id": set(),
        "submission_id": set(),
        "scorer_record_id": set(),
        "outcome_record_id": set(),
        "artifact_path": set(),
        "model_step_id": set(),
        "model_response_id": set(),
        "execution_receipt_id": set(),
    }
    for level in plan:
        quartet = quartets[level]
        if quartet is None:
            continue
        identities = {
            "run_id": set(quartet.run_ids),
            "submission_id": set(quartet.submission_ids),
            "scorer_record_id": set(quartet.scorer_record_ids),
            "outcome_record_id": set(quartet.outcome_record_ids),
            "artifact_path": set(quartet.artifact_paths),
            "model_step_id": set(quartet.model_step_ids),
            "model_response_id": set(quartet.model_response_ids),
            "execution_receipt_id": set(quartet.execution_receipt_ids),
        }
        reused = {
            kind: sorted(values & seen_identities[kind])
            for kind, values in identities.items()
            if values & seen_identities[kind]
        }
        if reused:
            reused_identity_levels.add(level)
            reasons.append(f"{level}: identities reused across ladder levels: {reused}")
        for kind, values in identities.items():
            seen_identities[kind].update(values)

    prefix: list[str] = []
    autonomous_blocked = False
    for level in autonomous_plan:
        quartet = quartets[level]
        valid = valid_quartet(level, quartet) and level not in reused_identity_levels
        if autonomous_blocked or not valid:
            autonomous_blocked = True
            invalid.append(level)
            reasons.append(f"{level}: incomplete or mismatched quartet")
        else:
            prefix.append(level)

    outcome_probe_protocol_complete = False
    planned_outcome_levels = [
        level for level in plan if level in OUTCOME_FEEDBACK_LEVELS
    ]
    if len(planned_outcome_levels) > 1:
        raise ValueError(
            "one ladder may declare only one outcome-feedback probe variant"
        )
    if planned_outcome_levels:
        outcome_level = planned_outcome_levels[0]
        outcome = quartets[outcome_level]
        outcome_probe_protocol_complete = valid_quartet(
            outcome_level, outcome
        ) and outcome_level not in reused_identity_levels
        if not outcome_probe_protocol_complete:
            invalid.append(outcome_level)
            reasons.append(
                f"{outcome_level} outcome-feedback probe is incomplete or mismatched"
            )

    return RecoveryLadderValidation(
        pair_group_id=pair_group_id,
        trial_id=trial_id,
        declared_stage_plan=plan,
        protocol_complete_autonomous_prefix=tuple(prefix),
        reportable_autonomous_prefix=(),
        invalid_levels=tuple(invalid),
        outcome_probe_protocol_complete=outcome_probe_protocol_complete,
        outcome_probe_reportable=False,
        experiment_reportable=False,
        all_planned_complete=not invalid,
        publication_blockers=publication_blockers,
        reasons=tuple([*reasons, *publication_blockers]),
    )


def _compare_eligible_recovery(
    candidate: RecoveryAnalysis, reference: RecoveryAnalysis
) -> str:
    if candidate.full_recovery is True and reference.full_recovery is True:
        return "both_full_recovery"
    if candidate.full_recovery is True:
        return "candidate_only_full_recovery"
    if reference.full_recovery is True:
        return "reference_only_full_recovery"
    if candidate.ordered_recovery is True and reference.ordered_recovery is True:
        return "both_ordered_recovery_without_full_completion"
    if candidate.ordered_recovery is True:
        return "candidate_only_ordered_recovery"
    if reference.ordered_recovery is True:
        return "reference_only_ordered_recovery"
    if (
        candidate.correct_action_switch is True
        and reference.correct_action_switch is True
    ):
        return "both_correct_action_switch_without_ordered_recovery"
    if candidate.correct_action_switch is True:
        return "candidate_only_correct_action_switch"
    if reference.correct_action_switch is True:
        return "reference_only_correct_action_switch"
    if (
        candidate.same_misleading_reentry is True
        and reference.same_misleading_reentry is True
    ):
        return "both_same_misleading_reentry"
    if candidate.same_misleading_reentry is True:
        return "candidate_same_misleading_reentry"
    if reference.same_misleading_reentry is True:
        return "reference_same_misleading_reentry"
    return "neither_recovers"


def _boolean_contrast(
    candidate: bool | None, reference: bool | None, milestone: str
) -> str:
    if candidate is None or reference is None:
        return f"{milestone}_censored"
    if candidate and reference:
        return f"both_{milestone}"
    if candidate:
        return f"candidate_only_{milestone}"
    if reference:
        return f"reference_only_{milestone}"
    return f"neither_{milestone}"


def _submission_success_value(run: RecoveryRun) -> bool | None:
    if run.final_submission_observed and run.final_submission_success is None:
        return None
    return bool(
        run.final_submission_observed and run.final_submission_success is True
    )
