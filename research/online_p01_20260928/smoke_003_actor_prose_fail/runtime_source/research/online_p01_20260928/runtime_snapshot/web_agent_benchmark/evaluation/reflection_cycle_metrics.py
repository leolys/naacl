#!/usr/bin/env python3
"""Cycle metrics for controlled cross-step reflection runs."""

from __future__ import annotations

from collections import Counter
from typing import Any


NAVIGATION_ACTIONS = {"click_link", "back_to_dashboard", "open_dashboard", "open_form"}
SUBMIT_ACTIONS = {"submit_form"}
MAX_CYCLE_PERIOD = 3
MAX_CYCLE_WINDOW = 6


def step_pair(step: dict[str, Any]) -> tuple[str, str] | None:
    pilot = step.get("pilot_history") or {}
    state_hash = str(pilot.get("state_hash") or "")
    action_signature = str(pilot.get("action_signature") or "")
    return (state_hash, action_signature) if state_hash and action_signature else None


def is_submission(step: dict[str, Any]) -> bool:
    action = step.get("action") or {}
    kind = str(action.get("action") or "")
    text = str(action.get("text") or "").strip().lower()
    return kind in SUBMIT_ACTIONS or (
        kind == "click_button" and text in {"submit form", "submit", "confirm submission"}
    )


def locate_cycles(trace: list[dict[str, Any]]) -> list[dict[str, int]]:
    pairs = [step_pair(step) for step in trace]
    cycles: list[dict[str, int]] = []
    for end in range(len(pairs)):
        for period in range(1, MAX_CYCLE_PERIOD + 1):
            start = end - (2 * period) + 1
            if start < 0:
                continue
            first = pairs[start : start + period]
            second = pairs[start + period : end + 1]
            if None not in first and first == second:
                cycles.append({"start": start, "end": end, "period": period})
                break
    deduplicated: list[dict[str, int]] = []
    for cycle in cycles:
        if deduplicated and cycle["start"] <= deduplicated[-1]["end"]:
            if cycle["end"] > deduplicated[-1]["end"]:
                deduplicated[-1]["end"] = cycle["end"]
            continue
        deduplicated.append(cycle)
    return deduplicated


def analyze_cycles(row: dict[str, Any]) -> dict[str, Any]:
    trace = row.get("trace") or []
    pairs = [step_pair(step) for step in trace]
    valid_pairs = [pair for pair in pairs if pair is not None]
    recurrence_count = sum(
        count - 1 for count in Counter(valid_pairs).values() if count > 1
    )
    cycles = locate_cycles(trace)
    cycle = cycles[0] if cycles else None

    long_range_revisit_count = 0
    seen_at: dict[tuple[str, str], int] = {}
    for index, pair in enumerate(pairs):
        if pair is None:
            continue
        previous = seen_at.get(pair)
        if previous is not None and index - previous > MAX_CYCLE_WINDOW:
            long_range_revisit_count += 1
        seen_at[pair] = index

    navigation_cycle_count = 0
    for item in cycles:
        actions = {
            str((trace[index].get("action") or {}).get("action") or "")
            for index in range(item["start"], item["end"] + 1)
        }
        if actions and actions.issubset(NAVIGATION_ACTIONS):
            navigation_cycle_count += 1

    submission_steps = [index for index, step in enumerate(trace) if is_submission(step)]
    submission_step = submission_steps[0] if submission_steps else None
    escape_step: int | None = None
    steps_to_escape: int | None = None
    if cycle:
        component = {
            pair
            for pair in pairs[cycle["start"] : cycle["end"] + 1]
            if pair is not None
        }
        for index in range(cycle["end"] + 1, len(trace)):
            if pairs[index] is not None and pairs[index] not in component:
                escape_step = index
                steps_to_escape = index - cycle["end"]
                break

    submitted_after_cycle = bool(
        cycle and submission_step is not None and submission_step > cycle["end"]
    )
    misleading_ids = set(row.get("misleading_action_ids_for_analysis") or [])
    selected_action = str(row.get("selected_action_id") or "")
    trace_agent_error_count = sum(
        1
        for step in trace
        if str((step.get("action") or {}).get("action") or "") == "agent_error"
        or str((step.get("pilot_history") or {}).get("execution_status") or "") == "failed"
    )
    return {
        "state_action_cycle_incidence": bool(cycles),
        "state_action_recurrence_count": recurrence_count,
        "long_range_revisit_count": long_range_revisit_count,
        "repeated_state_action_count": recurrence_count,
        "abab_cycle_count": sum(1 for item in cycles if item["period"] == 2),
        "navigation_cycle_count": navigation_cycle_count,
        "cycle_start_step": cycle["start"] if cycle else None,
        "cycle_end_step": cycle["end"] if cycle else None,
        "cycle_period": cycle["period"] if cycle else None,
        "escape_step": escape_step,
        "steps_to_escape": steps_to_escape,
        "escaped_before_submission": bool(
            escape_step is not None
            and (submission_step is None or escape_step < submission_step)
        ),
        "submission_step": submission_step,
        "submitted_after_cycle": submitted_after_cycle,
        "harmful_submission_after_cycle": bool(
            submitted_after_cycle
            and selected_action
            and selected_action in misleading_ids
        ),
        "trace_agent_error_count": trace_agent_error_count,
        "step_count": len(trace),
        "task_success": row.get("outcome") == "success",
        "agent_error": row.get("outcome") == "agent_error" or trace_agent_error_count > 0,
    }
