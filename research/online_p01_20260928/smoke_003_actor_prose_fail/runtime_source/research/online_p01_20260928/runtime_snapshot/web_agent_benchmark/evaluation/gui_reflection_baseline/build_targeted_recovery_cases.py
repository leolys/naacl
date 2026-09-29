#!/usr/bin/env python3
"""Build runner-side cases for the targeted GUI recovery evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence, TypeVar

from .formal_path_policy import REPO_ROOT
from .run_formal_task import FormalTask, load_formal_task, load_task_set_entries
from .targeted_recovery import (
    EVIDENCE_LEVELS,
    F2_AUDITED_VALUES,
    TargetedRecoveryRegistry,
)


T = TypeVar("T")
LAYOUT_UNIVERSE_PATH = Path(__file__).resolve().parent / "task_sets" / "full140.jsonl"


def role_blind_display_order(items: Sequence[T], ordinal: int) -> list[T]:
    """Rotate source items without accepting or inspecting action roles.

    For a fixed action-space size, consecutive ordinals place every source
    position in every display position equally often (up to one remainder).
    """

    if ordinal < 0:
        raise ValueError("ordinal must be non-negative")
    values = list(items)
    if not values:
        raise ValueError("cannot order an empty action space")
    offset = ordinal % len(values)
    return values[offset:] + values[:offset]


def _canonical_layout_ranks(path: Path = LAYOUT_UNIVERSE_PATH) -> dict[str, int]:
    """Return stable, population-wide ranks used only for UI permutation.

    Ranking the full paired population makes a case's layout independent of
    whether it is run in smoke17, strict_review94, or the full population.
    """

    pair_ids: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        pair_group_id = row.get("pair_group_id") if isinstance(row, dict) else None
        if not isinstance(pair_group_id, str) or not pair_group_id:
            raise ValueError(
                f"layout universe has no pair_group_id at {path}:{line_number}"
            )
        pair_ids.append(pair_group_id)
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError(f"layout universe contains duplicate pair ids: {path}")
    return {
        pair_group_id: rank
        for rank, pair_group_id in enumerate(sorted(pair_ids))
    }


def _source_record(task: FormalTask) -> dict[str, Any]:
    lines = task.source_path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[task.source_line - 1])
    if not isinstance(row, dict):
        raise ValueError(
            f"expected object at {task.source_path}:{task.source_line}"
        )
    return row


def _portable_asset_path(value: Any, repo_root: Path) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("chart asset has no non-empty figure_path")
    raw_path = Path(value)
    path = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    try:
        portable = path.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"chart asset escapes repository root: {path}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"chart asset is missing: {path}")
    return portable


def _action_cards(record: dict[str, Any]) -> list[dict[str, str]]:
    raw_actions = record.get("action_space")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("canonical task has no non-empty action_space")
    cards: list[dict[str, str]] = []
    for index, raw_action in enumerate(raw_actions):
        if not isinstance(raw_action, dict):
            raise ValueError(f"action_space[{index}] is not an object")
        action_id = raw_action.get("action_id")
        label = raw_action.get("label")
        if not isinstance(action_id, str) or not action_id:
            raise ValueError(f"action_space[{index}] has no action_id")
        if not isinstance(label, str) or not label:
            raise ValueError(f"action_space[{index}] has no label")
        # Only fields visible on the compact UI enter the ordering helper.
        cards.append({"action_id": action_id, "label": label})
    action_ids = [card["action_id"] for card in cards]
    if len(action_ids) != len(set(action_ids)):
        raise ValueError("action_space action_ids must be unique")
    return cards


def _paired_field_mismatches(
    official: dict[str, Any], clean: dict[str, Any]
) -> dict[str, tuple[Any, Any]]:
    fields = (
        "workflow_instruction",
        "action_space",
        "expected_action_id",
        "misleading_action_ids",
        "ground_truth",
        "intermediate_decision",
    )
    return {
        field: (official.get(field), clean.get(field))
        for field in fields
        if official.get(field) != clean.get(field)
    }


def _validate_and_classify_actions(
    record: dict[str, Any], cards: list[dict[str, str]]
) -> tuple[str, list[str], list[str], dict[str, str]]:
    action_ids = [card["action_id"] for card in cards]
    expected_action_id = record.get("expected_action_id")
    if not isinstance(expected_action_id, str) or not expected_action_id:
        raise ValueError("canonical task has no expected_action_id")
    if expected_action_id not in action_ids:
        raise ValueError("expected_action_id is absent from action_space")

    raw_misleading = record.get("misleading_action_ids")
    if not isinstance(raw_misleading, list) or not raw_misleading:
        raise ValueError("canonical task has no misleading_action_ids")
    misleading_action_ids = [str(value) for value in raw_misleading]
    if len(misleading_action_ids) != len(set(misleading_action_ids)):
        raise ValueError("misleading_action_ids must be unique")
    unknown_misleading = set(misleading_action_ids) - set(action_ids)
    if unknown_misleading:
        raise ValueError(
            f"misleading action ids absent from action_space: {sorted(unknown_misleading)}"
        )
    if expected_action_id in misleading_action_ids:
        raise ValueError("expected action cannot also be misleading")

    neutral_action_ids = [
        action_id
        for action_id in action_ids
        if action_id != expected_action_id
        and action_id not in misleading_action_ids
    ]
    roles_by_action_id = {
        action_id: (
            "correct"
            if action_id == expected_action_id
            else "misleading"
            if action_id in misleading_action_ids
            else "neutral_or_irrelevant"
        )
        for action_id in action_ids
    }
    return (
        expected_action_id,
        misleading_action_ids,
        neutral_action_ids,
        roles_by_action_id,
    )


def model_visible_projection(
    case: dict[str, Any], arm: str
) -> dict[str, Any]:
    """Return the only case projection eligible for a page renderer.

    The combined case manifest is runner-side.  Callers must use this allowlist
    projection instead of passing the manifest, ``runner_only``, or
    ``source_references`` to a template, debug page, or model prompt.
    """

    if arm not in {"official", "clean"}:
        raise ValueError(f"unknown targeted arm: {arm!r}")
    if case.get("record_type") != "targeted_recovery_case":
        raise ValueError("expected a targeted_recovery_case record")
    shared = case.get("model_visible_shared")
    arms = case.get("arms")
    if not isinstance(shared, dict) or not isinstance(arms, dict):
        raise ValueError("targeted case is missing visible or arm data")
    arm_record = arms.get(arm)
    if not isinstance(arm_record, dict):
        raise ValueError(f"targeted case is missing arm {arm!r}")
    workflow_instruction = shared.get("workflow_instruction")
    raw_cards = shared.get("action_cards")
    chart_path = arm_record.get("chart_path")
    if not isinstance(workflow_instruction, str) or not workflow_instruction:
        raise ValueError("visible workflow instruction is missing")
    if not isinstance(chart_path, str) or not chart_path:
        raise ValueError("visible chart path is missing")
    if not isinstance(raw_cards, list) or not raw_cards:
        raise ValueError("visible action cards are missing")
    action_cards: list[dict[str, str]] = []
    for card in raw_cards:
        if not isinstance(card, dict) or set(card) != {"choice_token", "label"}:
            raise ValueError("visible action cards must contain only token and label")
        token = card.get("choice_token")
        label = card.get("label")
        if not isinstance(token, str) or not token:
            raise ValueError("visible choice token is missing")
        if not isinstance(label, str) or not label:
            raise ValueError("visible action label is missing")
        action_cards.append({"choice_token": token, "label": label})
    return {
        "workflow_instruction": workflow_instruction,
        "chart_path": chart_path,
        "action_cards": action_cards,
    }


def model_visible_review_projection(
    case: dict[str, Any],
    arm: str,
    *,
    evidence_level: str,
    evidence_record_id: str | None = None,
    registry: TargetedRecoveryRegistry | None = None,
) -> dict[str, Any]:
    """Return a review-state projection without exposing scorer provenance.

    F2 content can enter the renderer only through the approved registry.  The
    renderer remains responsible for contextual HTML escaping and for emitting
    the acknowledged feedback/record binding in the collector trace.
    """

    if evidence_level not in EVIDENCE_LEVELS:
        raise ValueError(f"unknown evidence_level: {evidence_level!r}")
    projection = model_visible_projection(case, arm)
    review: dict[str, Any] = {"feedback_spec_id": evidence_level}
    if evidence_level == F2_AUDITED_VALUES:
        if not isinstance(evidence_record_id, str) or not evidence_record_id:
            raise ValueError("F2 review requires evidence_record_id")
        if not isinstance(registry, TargetedRecoveryRegistry):
            raise ValueError("F2 review requires TargetedRecoveryRegistry")
        pair_group_id = case.get("pair_group_id")
        if not isinstance(pair_group_id, str) or not pair_group_id:
            raise ValueError("targeted case has no pair_group_id")
        review["evidence"] = registry.evidence_payload(
            evidence_record_id, pair_group_id
        )
    elif evidence_record_id is not None:
        raise ValueError("evidence_record_id is valid only for F2 review")
    return {**projection, "review": review}


def build_targeted_recovery_cases(
    entries: Iterable[dict[str, Any]], *, repo_root: Path = REPO_ROOT
) -> list[dict[str, Any]]:
    """Build paired cases while keeping scorer facts explicitly runner-only."""

    cases: list[dict[str, Any]] = []
    seen_pair_ids: set[str] = set()
    layout_ranks = _canonical_layout_ranks()
    for ordinal, entry in enumerate(entries):
        official_task = load_formal_task(entry, "official", repo_root=repo_root)
        clean_task = load_formal_task(entry, "clean", repo_root=repo_root)
        pair_group_id = official_task.pair_group_id
        if pair_group_id in seen_pair_ids:
            raise ValueError(f"duplicate pair_group_id: {pair_group_id}")
        seen_pair_ids.add(pair_group_id)
        if clean_task.pair_group_id != pair_group_id:
            raise ValueError("official and clean tasks have different pair ids")
        if pair_group_id not in layout_ranks:
            raise ValueError(
                f"pair {pair_group_id!r} is absent from the layout universe"
            )
        layout_ordinal = layout_ranks[pair_group_id]

        official = _source_record(official_task)
        clean = _source_record(clean_task)
        mismatches = _paired_field_mismatches(official, clean)
        if mismatches:
            raise ValueError(
                f"pair {pair_group_id!r} is not matched for targeted recovery: "
                f"{sorted(mismatches)}"
            )

        cards = _action_cards(official)
        displayed_cards = role_blind_display_order(cards, layout_ordinal)
        (
            expected_action_id,
            misleading_action_ids,
            neutral_action_ids,
            roles_by_action_id,
        ) = _validate_and_classify_actions(official, cards)
        source_action_order = [card["action_id"] for card in cards]
        display_order = [card["action_id"] for card in displayed_cards]
        # The browser page receives opaque position tokens rather than canonical
        # action ids.  The token-to-action mapping remains runner-side so action
        # roles cannot leak through HTML form values or URLs.
        visible_cards = [
            {"choice_token": f"choice_{position}", "label": card["label"]}
            for position, card in enumerate(displayed_cards)
        ]
        choice_token_to_action_id = {
            visible_card["choice_token"]: source_card["action_id"]
            for visible_card, source_card in zip(visible_cards, displayed_cards)
        }

        official_chart_path = _portable_asset_path(
            (official.get("chart_asset") or {}).get("figure_path"), repo_root
        )
        clean_chart_path = _portable_asset_path(
            (clean.get("chart_asset") or {}).get("figure_path"), repo_root
        )
        for arm, actual in (
            ("official", official_chart_path),
            ("clean", clean_chart_path),
        ):
            entry_value = entry.get(f"{arm}_chart_path")
            if entry_value and str(entry_value) != actual:
                raise ValueError(
                    f"task-set {arm}_chart_path disagrees with canonical record: "
                    f"{entry_value!r} != {actual!r}"
                )

        case = {
            "record_type": "targeted_recovery_case",
            "pair_group_id": pair_group_id,
            "ordinal": ordinal,
            "layout_ordinal": layout_ordinal,
            "scenario": official_task.scenario,
            "slug": official_task.slug,
            "model_visible_shared": {
                "workflow_instruction": official["workflow_instruction"],
                "action_cards": visible_cards,
            },
            "arms": {
                "official": {
                    "task_id": official_task.task_id,
                    "task_instance_id": official_task.task_instance_id,
                    "chart_path": official_chart_path,
                },
                "clean": {
                    "task_id": clean_task.task_id,
                    "task_instance_id": clean_task.task_instance_id,
                    "chart_path": clean_chart_path,
                },
            },
            "runner_only": {
                "case_id": official.get("case_id"),
                "misleader_type": official.get("misleader_type"),
                "plot_type": official.get("plot_type"),
                "reasoning_operation": official.get("reasoning_operation"),
                "expected_action_id": expected_action_id,
                "misleading_action_ids": misleading_action_ids,
                "neutral_action_ids": neutral_action_ids,
                "roles_by_action_id": roles_by_action_id,
                "ground_truth": official.get("ground_truth"),
                "intermediate_decision": official.get("intermediate_decision"),
                "source_action_order": source_action_order,
                "display_order": display_order,
                "choice_token_to_action_id": choice_token_to_action_id,
                "source_expected_action_index": source_action_order.index(
                    expected_action_id
                ),
                "display_expected_action_index": display_order.index(
                    expected_action_id
                ),
                "review_issues": {
                    "official": list(entry.get("official_review_issues") or []),
                    "clean": list(entry.get("clean_review_issues") or []),
                },
                "audited_values_status": "manual_evidence_pending",
            },
            "source_references": {
                "official": {
                    "path": str(entry["official_path"]),
                    "line": int(entry["official_line"]),
                },
                "clean": {
                    "path": str(entry["clean_path"]),
                    "line": int(entry["clean_line"]),
                },
            },
        }
        cases.append(case)
    return cases


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-set",
        required=True,
        help="smoke17, chart_only114, readiness95, strict_review94, or JSONL path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSONL here; omit to write cases to stdout",
    )
    return parser.parse_args(argv)


def _jsonl(cases: Iterable[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n"
        for case in cases
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = build_targeted_recovery_cases(load_task_set_entries(args.task_set))
    payload = _jsonl(cases)
    if args.output is None:
        sys.stdout.write(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"wrote {len(cases)} targeted recovery cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
