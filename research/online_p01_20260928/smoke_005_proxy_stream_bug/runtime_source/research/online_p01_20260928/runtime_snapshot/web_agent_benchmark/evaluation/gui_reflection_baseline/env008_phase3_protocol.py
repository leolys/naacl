"""Frozen env008 Phase-3 mechanism-panel specification.

The 50 rows are within-case experimental conditions, not independent tasks.
No row is a canonical benchmark replication or a held-out example.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

from .targeted_recovery import F0_NEUTRAL_RECHECK, F3_PRE_REATTEMPT_CONTRADICTION


PHASE_ID = "env008_phase3"
UI_BUILD_ID = "compact-recovery-env008-phase3-v1"
PROTOCOL_VERSION = "env008-phase3-50cell-v3"

BLOCK_MEMORY = "M_memory_consumption"
BLOCK_METHOD = "A_method_bundle"
BLOCK_ROLE = "R_role_counterfactual"
BLOCK_COMPLETION = "C_completion_history"

METHOD_CURRENT_ONLY = "same_checkpoint_current_only"
METHOD_OFFICIAL = "official_gui_reflection_native4"
METHOD_PREMISE = "premise_aware_controller_v1"

MEMORY_TEXTS: dict[str, str | None] = {
    "M0_empty": None,
    "M1_action_only": (
        "Prior route note. Entity: Wind. Status: rejected action. Retry rule: do "
        "not repeat that route; carefully inspect the current dashboard now."
    ),
    "M2_premise_specific": (
        "Prior premise note. Entity: Wind. Status: contradicted premise. Retry "
        "rule: recompute from printed values; inspect the current dashboard carefully."
    ),
    "M3_irrelevant_noisy": (
        "Prior interface note. Entity: Wind. Status: ordinary card. Retry rule: "
        "note the page layout and header; carefully inspect the current dashboard."
    ),
}

# Each three-character vector is indexed by Solar/Wind/Hydroelectric.  Levels
# denote role (0 correct, 1 misleading, 2 neutral), chart x-position, action-card
# position, and chart-color index respectively.  Across the 18 entity profiles,
# entity/R/X/P/C are pairwise orthogonal (every 3x3 combination occurs twice).
ROLE_CONFIGS: tuple[dict[str, str], ...] = (
    {"config_id": "r0", "R": "012", "X": "120", "P": "201", "C": "210"},
    {"config_id": "r1", "R": "012", "X": "201", "P": "120", "C": "021"},
    {"config_id": "r2", "R": "120", "X": "012", "P": "120", "C": "102"},
    {"config_id": "r3", "R": "120", "X": "120", "P": "012", "C": "021"},
    {"config_id": "r4", "R": "201", "X": "012", "P": "012", "C": "210"},
    {"config_id": "r5", "R": "201", "X": "201", "P": "201", "C": "102"},
)

LAYOUT_BY_CARD_VECTOR = {
    "012": "canonical",
    "201": "cyclic_shift_1",
    "120": "cyclic_shift_2",
}


@dataclass(frozen=True)
class Phase3CellSpec:
    key: str
    block_id: str
    arm: str
    method_id: str
    feedback_spec_id: str
    layout_id: str
    inherited_entity: str
    max_ui_actions: int
    max_backbone_calls: int
    memory_condition: str | None = None
    role_config_id: str | None = None
    role_vector: str | None = None
    chart_position_vector: str | None = None
    card_position_vector: str | None = None
    color_vector: str | None = None
    correct_entity: str | None = None
    misleading_entity: str | None = None
    neutral_entity: str | None = None
    completion_history: str | None = None
    completion_final_entity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _memory_cells() -> list[Phase3CellSpec]:
    return [
        Phase3CellSpec(
            key=f"m_{condition.lower()}_{arm}",
            block_id=BLOCK_MEMORY,
            arm=arm,
            method_id=METHOD_OFFICIAL,
            feedback_spec_id=F0_NEUTRAL_RECHECK,
            layout_id="cyclic_shift_2",
            inherited_entity="Wind",
            max_ui_actions=4,
            max_backbone_calls=4,
            memory_condition=condition,
        )
        for condition in MEMORY_TEXTS
        for arm in ("official", "clean")
    ]


def _method_cells() -> list[Phase3CellSpec]:
    return [
        Phase3CellSpec(
            key=f"a_{method}_{arm}_{'f3' if feedback == F3_PRE_REATTEMPT_CONTRADICTION else 'f0'}",
            block_id=BLOCK_METHOD,
            arm=arm,
            method_id=method,
            feedback_spec_id=feedback,
            layout_id="cyclic_shift_2",
            inherited_entity="Wind",
            max_ui_actions=4,
            max_backbone_calls=4,
        )
        for feedback in (F3_PRE_REATTEMPT_CONTRADICTION,)
        for method in (METHOD_CURRENT_ONLY, METHOD_OFFICIAL, METHOD_PREMISE)
        for arm in ("official", "clean")
    ]


def _role_cells() -> list[Phase3CellSpec]:
    rows: list[Phase3CellSpec] = []
    entities = ("Solar", "Wind", "Hydroelectric")
    for config in ROLE_CONFIGS:
        role_to_entity = {
            int(level): entity for entity, level in zip(entities, config["R"])
        }
        correct = role_to_entity[0]
        misleading = role_to_entity[1]
        neutral = role_to_entity[2]
        layout = LAYOUT_BY_CARD_VECTOR[config["P"]]
        for method in (METHOD_OFFICIAL, METHOD_PREMISE):
            for arm in ("official", "clean"):
                rows.append(
                    Phase3CellSpec(
                        key=f"r_{config['config_id']}_{method}_{arm}",
                        block_id=BLOCK_ROLE,
                        arm=arm,
                        method_id=method,
                        feedback_spec_id=F0_NEUTRAL_RECHECK,
                        layout_id=layout,
                        inherited_entity=misleading,
                        max_ui_actions=4,
                        max_backbone_calls=4,
                        role_config_id=config["config_id"],
                        role_vector=config["R"],
                        chart_position_vector=config["X"],
                        card_position_vector=config["P"],
                        color_vector=config["C"],
                        correct_entity=correct,
                        misleading_entity=misleading,
                        neutral_entity=neutral,
                    )
                )
    return rows


def _completion_cells() -> list[Phase3CellSpec]:
    return [
        Phase3CellSpec(
            key=f"c_{history}_{final_entity.lower()}_{arm}",
            block_id=BLOCK_COMPLETION,
            arm=arm,
            method_id=METHOD_OFFICIAL,
            feedback_spec_id=F0_NEUTRAL_RECHECK,
            layout_id="cyclic_shift_2",
            inherited_entity=final_entity,
            max_ui_actions=1,
            max_backbone_calls=1,
            completion_history=history,
            completion_final_entity=final_entity,
        )
        for history in ("H0_empty", "H2_recent_selection", "H2_revision_chain")
        for final_entity in ("Solar", "Wind")
        for arm in ("official", "clean")
    ]


def phase3_cells() -> tuple[Phase3CellSpec, ...]:
    """Return a content-address interleaving frozen before any model output."""

    all_cells = (*_memory_cells(), *_method_cells(), *_role_cells(), *_completion_cells())
    cells = tuple(
        sorted(
            all_cells,
            key=lambda cell: hashlib.sha256(
                f"{PROTOCOL_VERSION}|{cell.key}".encode("utf-8")
            ).hexdigest(),
        )
    )
    keys = [cell.key for cell in cells]
    counts = {
        block: sum(cell.block_id == block for cell in cells)
        for block in (BLOCK_MEMORY, BLOCK_METHOD, BLOCK_ROLE, BLOCK_COMPLETION)
    }
    if len(cells) != 50 or len(keys) != len(set(keys)):
        raise AssertionError("phase-3 matrix must contain 50 unique cells")
    if counts != {
        BLOCK_MEMORY: 8,
        BLOCK_METHOD: 6,
        BLOCK_ROLE: 24,
        BLOCK_COMPLETION: 12,
    }:
        raise AssertionError(f"phase-3 block counts are invalid: {counts}")
    return cells


def memory_protocol_audit() -> dict[str, Any]:
    forbidden = (
        "solar",
        "hydroelectric",
        "41.2",
        "29.8",
        "18.5",
        "correct answer",
        "choice_",
        "choose solar",
    )
    nonempty = {
        key: value for key, value in MEMORY_TEXTS.items() if value is not None
    }
    word_counts = {key: len(value.split()) for key, value in nonempty.items()}
    violations = {
        key: [fragment for fragment in forbidden if fragment in value.casefold()]
        for key, value in nonempty.items()
    }
    wind_counts = {key: value.count("Wind") for key, value in nonempty.items()}
    return {
        "single_entry_template": all(
            value.startswith("Prior ")
            and ". Entity: Wind. Status: " in value
            and ". Retry rule: " in value
            for value in nonempty.values()
        ),
        "word_counts": word_counts,
        "word_count_range": max(word_counts.values()) - min(word_counts.values()),
        "wind_counts": wind_counts,
        "forbidden_fragments": violations,
        "passed": bool(
            all(not row for row in violations.values())
            and set(wind_counts.values()) == {1}
            and max(word_counts.values()) - min(word_counts.values()) <= 5
        ),
    }
