"""Role-blind cyclic layouts for compact targeted-recovery cases."""

from __future__ import annotations

import copy
from typing import Any, Mapping


LAYOUT_OFFSETS = {
    "canonical": 0,
    "cyclic_shift_1": 1,
    "cyclic_shift_2": 2,
}
LAYOUT_IDS = tuple(LAYOUT_OFFSETS)


def layout_offset(layout_id: str) -> int:
    try:
        return LAYOUT_OFFSETS[layout_id]
    except KeyError as exc:
        raise ValueError(f"unsupported layout_id {layout_id!r}") from exc


def layout_algorithm(layout_id: str) -> str:
    offset = layout_offset(layout_id)
    return (
        "canonical visible-card order"
        if offset == 0
        else f"rotate visible-card sequence left by {offset} position(s)"
    )


def rotate_sequence(values: list[Any] | tuple[Any, ...], layout_id: str) -> list[Any]:
    items = list(values)
    if not items:
        raise ValueError("cannot lay out an empty sequence")
    offset = layout_offset(layout_id) % len(items)
    return items[offset:] + items[:offset]


def derive_layout_case(
    canonical_case: Mapping[str, Any], *, layout_id: str
) -> dict[str, Any]:
    """Derive one fixed layout without consulting action ids or roles."""

    case = copy.deepcopy(dict(canonical_case))
    cards = list(case["model_visible_shared"]["action_cards"])
    if len(cards) != 3:
        raise ValueError("env008 phase-1 layouts require exactly three cards")
    canonical_pair = str(case["pair_group_id"])
    case["canonical_pair_group_id"] = canonical_pair
    if layout_id == "canonical":
        pair_group_id = canonical_pair
    else:
        pair_group_id = f"{canonical_pair}:layout:{layout_id}"
    case["pair_group_id"] = pair_group_id
    case["layout_intervention"] = {
        "layout_id": layout_id,
        "algorithm": layout_algorithm(layout_id),
        "role_blind": True,
    }
    for arm in ("official", "clean"):
        canonical_instance = str(case["arms"][arm]["task_instance_id"])
        case["arms"][arm]["task_instance_id"] = (
            canonical_instance
            if layout_id == "canonical"
            else f"{canonical_instance}:layout:{layout_id}"
        )
    rotated_cards = rotate_sequence(cards, layout_id)
    case["model_visible_shared"]["action_cards"] = rotated_cards
    token_map = dict(case["runner_only"]["choice_token_to_action_id"])
    display_order = [token_map[card["choice_token"]] for card in rotated_cards]
    case["runner_only"]["display_order"] = display_order
    expected = str(case["runner_only"]["expected_action_id"])
    case["runner_only"]["display_expected_action_index"] = display_order.index(
        expected
    )
    return case
