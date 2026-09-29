"""Lightweight policy middleware for web-agent rebuttal experiments.

This module is intentionally small and opt-in. It does not use hidden labels or
ground-truth fields; it only inspects visible page state, the proposed action,
and previous trace URLs/actions.
"""

from __future__ import annotations

import copy
import os
from collections import Counter
from typing import Any


POLICY_NAME = "chart_evidence_playbook_action_guard"
ENABLED_VALUES = {"1", "true", "yes", "on", "chart_evidence_action_guard", POLICY_NAME}


def policy_middleware_enabled() -> bool:
    raw = os.environ.get("WEB_AGENT_POLICY_MIDDLEWARE", "").strip().lower()
    return raw in ENABLED_VALUES


def sanitize_action(action: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in action.items() if not key.startswith("_")}


def _action_text(action: dict[str, Any]) -> str:
    return str(
        action.get("text")
        or action.get("button_text")
        or action.get("option_text")
        or action.get("value")
        or ""
    ).strip()


def _selected_ready(state: dict[str, Any]) -> bool:
    for select in (state.get("elements") or {}).get("selects") or []:
        selected = str(select.get("selected_text") or "").strip()
        if selected and not selected.lower().startswith("select a "):
            return True
    return False


def _submit_visible(state: dict[str, Any]) -> bool:
    for button in (state.get("elements") or {}).get("buttons") or []:
        if str(button.get("text") or "").strip().lower() == "submit form":
            return True
    return False


def _target_select_selected(state: dict[str, Any], action: dict[str, Any]) -> bool:
    if action.get("action") != "select_option":
        return False
    select_name = str(action.get("select_name") or "").strip()
    option_text = str(action.get("option_text") or "").strip()
    if not select_name or not option_text:
        return False
    for select in (state.get("elements") or {}).get("selects") or []:
        names = {str(select.get("name") or "").strip(), str(select.get("id") or "").strip()}
        if select_name in names and str(select.get("selected_text") or "").strip() == option_text:
            return True
    return False


def _visited(trace: list[dict[str, Any]], suffix: str) -> bool:
    return any(str(entry.get("url") or "").endswith(suffix) for entry in trace)


def apply_policy_middleware(
    *,
    action: dict[str, Any],
    state: dict[str, Any],
    trace: list[dict[str, Any]],
    step: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return the action to execute plus optional policy metadata for the trace."""

    if not policy_middleware_enabled():
        return action, None

    proposed_action = sanitize_action(action)
    executed_action = copy.deepcopy(action)
    events: list[dict[str, Any]] = [
        {
            "type": "playbook_guidance_active",
            "policy_type": "playbook",
            "policy_name": POLICY_NAME,
        }
    ]
    decision = "allow"

    current_url = str(state.get("url") or "")
    has_seen_dashboard = current_url.endswith("/dashboard") or _visited(trace, "/dashboard")
    has_seen_form = current_url.endswith("/form") or _visited(trace, "/form")
    selected_ready = _selected_ready(state)
    submit_visible = _submit_visible(state)
    kind = str(action.get("action") or "").strip()
    text = _action_text(action)

    if (
        kind in {"click_link", "click_button"}
        and text.lower() == "open dashboard"
        and has_seen_dashboard
        and has_seen_form
    ):
        events.append(
            {
                "type": "navigation_loop_risk",
                "policy_type": "action_guard",
                "reason": "dashboard_and_form_already_observed",
            }
        )
        if selected_ready and submit_visible:
            executed_action = {"action": "click_button", "text": "Submit Form"}
            decision = "rewrite"
            events.append(
                {
                    "type": "rewrite_to_submit",
                    "policy_type": "action_guard",
                    "reason": "form_option_already_selected",
                }
            )

    elif _target_select_selected(state, action) and submit_visible:
        executed_action = {"action": "click_button", "text": "Submit Form"}
        decision = "rewrite"
        events.append(
            {
                "type": "rewrite_redundant_select_to_submit",
                "policy_type": "action_guard",
                "reason": "requested_option_already_selected",
            }
        )

    elif kind == "finish" and selected_ready and submit_visible:
        executed_action = {"action": "click_button", "text": "Submit Form"}
        decision = "rewrite"
        events.append(
            {
                "type": "rewrite_finish_to_submit",
                "policy_type": "action_guard",
                "reason": "form_ready_but_not_submitted",
            }
        )

    return executed_action, {
        "enabled": True,
        "policy_name": POLICY_NAME,
        "step": step,
        "decision": decision,
        "proposed_action": proposed_action,
        "executed_action": sanitize_action(executed_action),
        "events": events,
    }


def policy_summary_from_trace(trace: list[dict[str, Any]]) -> dict[str, Any]:
    middleware_entries = [entry.get("policy_middleware") for entry in trace if entry.get("policy_middleware")]
    if not middleware_entries:
        return {}
    event_counter: Counter[str] = Counter()
    decision_counter: Counter[str] = Counter()
    for item in middleware_entries:
        decision_counter[str(item.get("decision") or "unknown")] += 1
        for event in item.get("events") or []:
            event_counter[str(event.get("type") or "unknown")] += 1
    return {
        "enabled": True,
        "policy_name": POLICY_NAME,
        "checked_steps": len(middleware_entries),
        "decision_counts": dict(decision_counter),
        "event_counts": dict(event_counter),
        "rewrite_count": decision_counter.get("rewrite", 0),
        "guard_event_count": sum(
            count for event, count in event_counter.items() if event != "playbook_guidance_active"
        ),
    }


def attach_policy_summary(row: dict[str, Any], trace: list[dict[str, Any]]) -> dict[str, Any]:
    summary = policy_summary_from_trace(trace)
    if summary:
        row["policy_middleware_summary"] = summary
    return row
