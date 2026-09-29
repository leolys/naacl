"""Independent canonical outcome validator for exact F3 recovery probes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import uuid

from .build_targeted_recovery_cases import build_targeted_recovery_cases
from .formal_path_policy import REPO_ROOT
from .run_formal_task import load_task_set_entries


@dataclass(frozen=True)
class OutcomeValidationRecord:
    outcome_record_id: str
    pair_group_id: str
    task_instance_id: str
    arm: str
    layout_id: str
    provisional_choice_token: str
    provisional_control_position: int
    provisional_action_id: str
    contradiction: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": "targeted_outcome_validation",
            "source": "canonical_outcome_validator",
            "outcome_record_id": self.outcome_record_id,
            "pair_group_id": self.pair_group_id,
            "task_instance_id": self.task_instance_id,
            "arm": self.arm,
            "layout_id": self.layout_id,
            "provisional_choice_token": self.provisional_choice_token,
            "provisional_control_position": self.provisional_control_position,
            "provisional_action_id": self.provisional_action_id,
            "contradiction": self.contradiction,
        }


class CanonicalOutcomeValidator:
    """Reload canonical truth separately from the renderer and run registry."""

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
            raise ValueError(f"validator expected one canonical entry for {slug!r}")
        cases = build_targeted_recovery_cases(entries, repo_root=REPO_ROOT)
        if len(cases) != 1:
            raise ValueError("validator canonical loader did not produce one case")
        layout_offsets = {
            "canonical": 0,
            "cyclic_shift_1": 1,
            "cyclic_shift_2": 2,
        }
        if layout_id not in layout_offsets:
            raise ValueError(f"unsupported validator layout_id {layout_id!r}")
        case = cases[0]
        runner_only = case["runner_only"]
        canonical_tokens = tuple(
            card["choice_token"]
            for card in case["model_visible_shared"]["action_cards"]
        )
        self.layout_id = layout_id
        offset = layout_offsets[layout_id] % len(canonical_tokens)
        self.display_tokens = canonical_tokens[offset:] + canonical_tokens[:offset]
        self.choice_token_to_action_id = dict(
            runner_only["choice_token_to_action_id"]
        )
        self.expected_action_id = str(runner_only["expected_action_id"])
        canonical_pair = str(case["pair_group_id"])
        if asset_variant_id is not None:
            if not asset_variant_id or ":" in asset_variant_id:
                raise ValueError("asset_variant_id must be one non-empty identity segment")
            canonical_pair = f"{canonical_pair}:asset_variant:{asset_variant_id}"
        self.pair_group_id = (
            canonical_pair
            if layout_id == "canonical"
            else f"{canonical_pair}:layout:{layout_id}"
        )
        self.task_instances = {}
        for arm in ("official", "clean"):
            task_instance = str(case["arms"][arm]["task_instance_id"])
            if asset_variant_id is not None:
                task_instance = f"{task_instance}:asset_variant:{asset_variant_id}"
            if layout_id != "canonical":
                task_instance = f"{task_instance}:layout:{layout_id}"
            self.task_instances[arm] = task_instance

    def validate(
        self,
        *,
        pair_group_id: str,
        task_instance_id: str,
        arm: str,
        choice_token: str,
        control_position: int,
    ) -> OutcomeValidationRecord:
        if pair_group_id != self.pair_group_id:
            raise ValueError("outcome pair does not match canonical validator")
        if arm not in self.task_instances:
            raise ValueError("outcome arm is unknown to canonical validator")
        if task_instance_id != self.task_instances[arm]:
            raise ValueError("outcome task instance does not match canonical validator")
        if (
            isinstance(control_position, bool)
            or not isinstance(control_position, int)
            or control_position < 0
            or control_position >= len(self.display_tokens)
        ):
            raise ValueError("outcome control position is invalid")
        if self.display_tokens[control_position] != choice_token:
            raise ValueError("outcome token/position do not match derived layout")
        action_id = self.choice_token_to_action_id.get(choice_token)
        if not action_id:
            raise ValueError("outcome token is absent from canonical validator mapping")
        return OutcomeValidationRecord(
            outcome_record_id=f"outcome:{uuid.uuid4().hex}",
            pair_group_id=pair_group_id,
            task_instance_id=task_instance_id,
            arm=arm,
            layout_id=self.layout_id,
            provisional_choice_token=choice_token,
            provisional_control_position=control_position,
            provisional_action_id=action_id,
            contradiction=action_id != self.expected_action_id,
        )
