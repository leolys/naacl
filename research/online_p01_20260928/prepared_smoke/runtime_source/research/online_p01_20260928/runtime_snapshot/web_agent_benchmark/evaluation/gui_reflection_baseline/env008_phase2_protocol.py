"""Frozen cell matrix and direct behavioral labels for env008 phase 2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .targeted_recovery import F0_NEUTRAL_RECHECK, F3_PRE_REATTEMPT_CONTRADICTION
from .targeted_recovery_app import (
    PHASE2_BRANCH_INVALIDATION,
    PHASE2_BRANCH_NEUTRAL_CONTROL,
)


PHASE_ID = "env008_phase2"
UI_BUILD_ID = "compact-recovery-env008-phase2-v1"
Q1 = "q1_f3_position_matched"
Q2 = "q2_external_proposition_action"
Q3 = "q3_completion_only_first_action"
Q4 = "q4_branch_invalidation_matched"


@dataclass(frozen=True)
class Phase2CellSpec:
    key: str
    probe_id: str
    arm: str
    layout_id: str
    history_mode: str
    feedback_spec_id: str
    inherited_entity: str
    max_steps: int
    proposition_entity: str | None = None
    completion_negative_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _q1() -> list[Phase2CellSpec]:
    # Interleaving is frozen before execution.  Every layout receives a fresh,
    # same-phase F0/F3 pair in both data arms.
    order = (
        ("cyclic_shift_2", "official", F0_NEUTRAL_RECHECK),
        ("canonical", "clean", F0_NEUTRAL_RECHECK),
        ("cyclic_shift_1", "official", F0_NEUTRAL_RECHECK),
        ("cyclic_shift_2", "clean", F3_PRE_REATTEMPT_CONTRADICTION),
        ("canonical", "official", F3_PRE_REATTEMPT_CONTRADICTION),
        ("cyclic_shift_1", "clean", F3_PRE_REATTEMPT_CONTRADICTION),
        ("cyclic_shift_2", "official", F3_PRE_REATTEMPT_CONTRADICTION),
        ("canonical", "clean", F3_PRE_REATTEMPT_CONTRADICTION),
        ("cyclic_shift_1", "official", F3_PRE_REATTEMPT_CONTRADICTION),
        ("cyclic_shift_2", "clean", F0_NEUTRAL_RECHECK),
        ("canonical", "official", F0_NEUTRAL_RECHECK),
        ("cyclic_shift_1", "clean", F0_NEUTRAL_RECHECK),
    )
    return [
        Phase2CellSpec(
            key=f"q1_{layout}_{arm}_{'f3' if feedback == F3_PRE_REATTEMPT_CONTRADICTION else 'f0'}",
            probe_id=Q1,
            arm=arm,
            layout_id=layout,
            history_mode="native4",
            feedback_spec_id=feedback,
            inherited_entity="Wind",
            max_steps=4,
        )
        for layout, arm, feedback in order
    ]


def _q2() -> list[Phase2CellSpec]:
    # Hydroelectric is the predeclared wrong-but-inconsistent placebo.  It keeps
    # a successful Solar treatment from being misread as generic mismatch use.
    order = (
        ("Solar", "official", "native4"),
        ("Wind", "clean", "current_only"),
        ("Hydroelectric", "official", "native4"),
        ("Solar", "clean", "current_only"),
        ("Wind", "official", "native4"),
        ("Hydroelectric", "clean", "current_only"),
        ("Solar", "clean", "native4"),
        ("Wind", "official", "current_only"),
        ("Hydroelectric", "clean", "native4"),
        ("Solar", "official", "current_only"),
        ("Wind", "clean", "native4"),
        ("Hydroelectric", "official", "current_only"),
    )
    return [
        Phase2CellSpec(
            key=f"q2_p_{entity.lower()}_{arm}_{history}",
            probe_id=Q2,
            arm=arm,
            layout_id="cyclic_shift_2",
            history_mode=history,
            feedback_spec_id=F0_NEUTRAL_RECHECK,
            inherited_entity="Wind",
            proposition_entity=entity,
            max_steps=4,
        )
        for entity, arm, history in order
    ]


def _q3() -> list[Phase2CellSpec]:
    core = (
        ("Solar", "official", "native4", False),
        ("Solar", "clean", "current_only", False),
        ("Solar", "official", "current_only", False),
        ("Solar", "clean", "native4", False),
    )
    negative = (
        ("Wind", "clean", "native4", True),
        ("Wind", "official", "native4", True),
    )
    return [
        Phase2CellSpec(
            key=f"q3_final_{entity.lower()}_{arm}_{history}",
            probe_id=Q3,
            arm=arm,
            layout_id="cyclic_shift_2",
            history_mode=history,
            feedback_spec_id=F0_NEUTRAL_RECHECK,
            inherited_entity=entity,
            max_steps=1,
            completion_negative_control=negative_control,
        )
        for entity, arm, history, negative_control in (*core, *negative)
    ]


def _q4() -> list[Phase2CellSpec]:
    order = (
        ("Hydroelectric", "clean", PHASE2_BRANCH_NEUTRAL_CONTROL),
        ("Wind", "official", PHASE2_BRANCH_INVALIDATION),
        ("Hydroelectric", "official", PHASE2_BRANCH_INVALIDATION),
        ("Wind", "clean", PHASE2_BRANCH_NEUTRAL_CONTROL),
        ("Wind", "official", PHASE2_BRANCH_NEUTRAL_CONTROL),
        ("Hydroelectric", "clean", PHASE2_BRANCH_INVALIDATION),
        ("Wind", "clean", PHASE2_BRANCH_INVALIDATION),
        ("Hydroelectric", "official", PHASE2_BRANCH_NEUTRAL_CONTROL),
    )
    return [
        Phase2CellSpec(
            key=(
                f"q4_prev_{previous.lower()}_{arm}_"
                f"{'invalidation' if feedback == PHASE2_BRANCH_INVALIDATION else 'f0'}"
            ),
            probe_id=Q4,
            arm=arm,
            layout_id="cyclic_shift_2",
            history_mode="native4",
            feedback_spec_id=feedback,
            inherited_entity=previous,
            max_steps=4,
        )
        for previous, arm, feedback in order
    ]


def phase2_cells() -> tuple[Phase2CellSpec, ...]:
    cells = tuple((*_q1(), *_q2(), *_q3(), *_q4()))
    keys = [cell.key for cell in cells]
    if len(cells) != 38 or len(keys) != len(set(keys)):
        raise AssertionError("phase-2 frozen matrix must contain 38 unique cells")
    return cells


def direct_behavior_summary(
    *,
    spec: Phase2CellSpec,
    action_ids_by_entity: Mapping[str, str],
    model_ui_receipts: list[Mapping[str, Any]],
    raw_steps: list[Mapping[str, Any]],
    submission_success: bool | None,
) -> dict[str, Any]:
    """Summarize only server-observed actions, without reading model thought."""

    selections = [row for row in model_ui_receipts if row.get("kind") == "selection"]
    reversals = [
        row
        for row in model_ui_receipts
        if row.get("kind") in {"revision", "browser_back"}
    ]
    submissions = [
        row for row in model_ui_receipts if row.get("kind") == "submission"
    ]
    token_to_entity = {
        str(row.get("choice_token")): str(row.get("selected_entity"))
        for row in selections
        if row.get("choice_token") is not None and row.get("selected_entity") is not None
    }
    retry_selections = [
        row for row in selections if row.get("from_state") == "retry_decision"
    ]
    first_retry_entity = (
        token_to_entity.get(str(retry_selections[0].get("choice_token")))
        if retry_selections
        else None
    )
    inherited_action_id = action_ids_by_entity[spec.inherited_entity]
    first_retry_action_id = (
        action_ids_by_entity.get(first_retry_entity)
        if first_retry_entity is not None
        else None
    )
    effective_reversal = any(
        row.get("from_state") == "review" and row.get("to_state") == "retry_decision"
        for row in reversals
    )
    first_action_type = None
    if raw_steps:
        parsed = raw_steps[0].get("official_action_parsed")
        if isinstance(parsed, Mapping):
            first_action_type = parsed.get("action_type")
    return {
        "first_action_type": first_action_type,
        "review_consumed": bool(raw_steps),
        "effective_reversal": effective_reversal,
        "first_retry_entity": first_retry_entity,
        "first_retry_action_id": first_retry_action_id,
        "same_inherited_reentry": first_retry_action_id == inherited_action_id,
        "branch_exit": bool(
            first_retry_action_id is not None
            and first_retry_action_id != inherited_action_id
        ),
        "correct_action_rebinding": (
            first_retry_action_id == action_ids_by_entity["Solar"]
        ),
        "submission_observed": bool(submissions),
        "submission_success": submission_success,
        "full_recovery": bool(
            (
                spec.probe_id in {Q1, Q2}
                or (spec.probe_id == Q4 and spec.inherited_entity == "Wind")
            )
            and effective_reversal
            and first_retry_action_id == action_ids_by_entity["Solar"]
            and submissions
            and submission_success is True
        ),
        "completion_direct_confirm": bool(
            spec.probe_id == Q3
            and first_action_type == "CLICK"
            and submissions
            and submission_success is True
        ),
        "model_selection_count": len(selections),
        "model_reversal_count": len(reversals),
        "model_submission_count": len(submissions),
    }
