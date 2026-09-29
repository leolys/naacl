"""Independent canonical scorer for compact targeted-recovery submissions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import uuid

from .build_targeted_recovery_cases import build_targeted_recovery_cases
from .formal_path_policy import REPO_ROOT
from .run_formal_task import load_task_set_entries


@dataclass(frozen=True)
class ScorerRecord:
    scorer_record_id: str
    submission_id: str
    pair_group_id: str
    task_instance_id: str
    arm: str
    layout_id: str
    submitted_choice_token: str
    submitted_control_position: int
    selected_action_id: str
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": "targeted_scorer_result",
            "scorer_record_id": self.scorer_record_id,
            "submission_id": self.submission_id,
            "pair_group_id": self.pair_group_id,
            "task_instance_id": self.task_instance_id,
            "arm": self.arm,
            "layout_id": self.layout_id,
            "submitted_choice_token": self.submitted_choice_token,
            "submitted_control_position": self.submitted_control_position,
            "selected_action_id": self.selected_action_id,
            "success": self.success,
        }


class CanonicalSubmissionScorer:
    """Reload scorer truth from canonical task pointers, independently of a run registry."""

    def __init__(
        self,
        *,
        task_set: str | Path,
        slug: str,
        layout_id: str = "canonical",
        asset_variant_id: str | None = None,
    ) -> None:
        entries = [
            entry
            for entry in load_task_set_entries(task_set)
            if entry.get("slug") == slug
        ]
        if len(entries) != 1:
            raise ValueError(f"scorer expected one canonical entry for {slug!r}")
        cases = build_targeted_recovery_cases(entries, repo_root=REPO_ROOT)
        if len(cases) != 1:
            raise ValueError("scorer canonical loader did not produce one case")
        case = cases[0]
        runner_only = case["runner_only"]
        layout_offsets = {
            "canonical": 0,
            "cyclic_shift_1": 1,
            "cyclic_shift_2": 2,
        }
        if layout_id not in layout_offsets:
            raise ValueError(f"unsupported scorer layout_id {layout_id!r}")
        self.layout_id = layout_id
        canonical_pair_group_id = str(case["pair_group_id"])
        if asset_variant_id is not None:
            if not asset_variant_id or ":" in asset_variant_id:
                raise ValueError("asset_variant_id must be one non-empty identity segment")
            canonical_pair_group_id = (
                f"{canonical_pair_group_id}:asset_variant:{asset_variant_id}"
            )
        self.pair_group_id = canonical_pair_group_id
        if layout_id != "canonical":
            self.pair_group_id = f"{self.pair_group_id}:layout:{layout_id}"
        self.expected_action_id = str(runner_only["expected_action_id"])
        self.choice_token_to_action_id = dict(
            runner_only["choice_token_to_action_id"]
        )
        canonical_tokens = tuple(
            card["choice_token"] for card in case["model_visible_shared"]["action_cards"]
        )
        offset = layout_offsets[layout_id] % len(canonical_tokens)
        self.display_tokens = canonical_tokens[offset:] + canonical_tokens[:offset]
        self.task_instances = {}
        for arm in ("official", "clean"):
            task_instance = str(case["arms"][arm]["task_instance_id"])
            if asset_variant_id is not None:
                task_instance = f"{task_instance}:asset_variant:{asset_variant_id}"
            if layout_id != "canonical":
                task_instance = f"{task_instance}:layout:{layout_id}"
            self.task_instances[arm] = task_instance

    def score(
        self,
        *,
        submission_id: str,
        pair_group_id: str,
        task_instance_id: str,
        arm: str,
        choice_token: str,
        control_position: int,
    ) -> ScorerRecord:
        if pair_group_id != self.pair_group_id:
            raise ValueError("submission pair does not match canonical scorer")
        if arm not in self.task_instances:
            raise ValueError("submission arm is unknown to canonical scorer")
        if task_instance_id != self.task_instances[arm]:
            raise ValueError("submission task instance does not match canonical scorer")
        if (
            isinstance(control_position, bool)
            or not isinstance(control_position, int)
            or control_position < 0
            or control_position >= len(self.display_tokens)
        ):
            raise ValueError("submission control position is invalid")
        if self.display_tokens[control_position] != choice_token:
            raise ValueError("submission raw token/position do not match canonical layout")
        action_id = self.choice_token_to_action_id.get(choice_token)
        if not action_id:
            raise ValueError("submission token is absent from canonical scorer mapping")
        return ScorerRecord(
            scorer_record_id=f"scorer:{uuid.uuid4().hex}",
            submission_id=submission_id,
            pair_group_id=pair_group_id,
            task_instance_id=task_instance_id,
            arm=arm,
            layout_id=self.layout_id,
            submitted_choice_token=choice_token,
            submitted_control_position=control_position,
            selected_action_id=action_id,
            success=action_id == self.expected_action_id,
        )
