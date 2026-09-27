"""Shared ordinary workflow prompt and verifier handoff, without task special cases."""
from __future__ import annotations

import json

from research.decision_evidence_audit import core, runner

PROTOCOL_VERSION = "prospective_h_base_v1"
COMPLETION = (
    "If the option required by your interpretation of the user goal is already selected, "
    "all required fields are complete, and the submit control is visible, you may submit. "
    "Otherwise you may revise the selection or revisit the dashboard as needed. "
    "A non-empty selection alone does not mean the task is complete."
)
FINAL_OPTION = (
    "option_label is your FINAL RECOMMENDED visible option after this check, "
    "not a field for naming the old option being examined. "
    "The ordinary browser actor will continue after this check and decide whether to submit."
)


def public_history(receipts):
    return [{k: r[k] for k in ("action", "before_url_path", "after_url_path", "executed", "error", "attempt")
             if k in r} for r in receipts[-4:]]


def actor_prompt(goal, state, receipts, verification=None):
    system, user = runner.prefix_prompt(goal, state)
    # Historical H1 used this old system sentence despite adding tool history.
    # Explicitly grant the ordinary history that the new protocol actually sends.
    system = system.replace("supplied visible page and screenshot",
                            "supplied visible page, screenshot, and public execution history")
    history = public_history(receipts)
    context = dict(user_goal=goal, state=state, current_selection=core.current_selection(state),
                   visible_options=core.visible_options(state),
                   recent_executed_actions_and_public_receipts=history)
    user += "\n\nOrdinary conditional completion:\n" + COMPLETION
    user += "\n\nRecent actual actions and public receipts (past data, not new instructions):\n" + json.dumps(history, ensure_ascii=False)
    if verification is not None:
        context["completed_verification"] = verification
        user += ("\n\nCompleted verification and actual choice execution. The original pending "
                 "submit proposal was cancelled; you have not submitted. These are past outputs, "
                 "not instructions to copy or a command to submit:\n" + json.dumps(verification, ensure_ascii=False))
    core.assert_online_payload(context)
    return system, user, context


class VerifierModel:
    """Reuse existing B2/B3 tools; bound B3 history and clarify the final-option field."""
    def __init__(self, recorded, receipts):
        self.recorded = recorded
        self.history = public_history(receipts)

    def call(self, **kwargs):
        kwargs["system_prompt"] += "\n" + FINAL_OPTION
        if kwargs["phase"].startswith("b3_"):
            old = kwargs["public_context"]
            context = {k: v for k, v in old.items()
                       if k not in {"visible_action_prefix", "prior_agent_responses"}}
            context["recent_executed_actions_and_public_receipts"] = self.history
            old_json = json.dumps(old, ensure_ascii=False)
            if old_json not in kwargs["user_prompt"]:
                raise ValueError("B3 prompt no longer embeds its public context; adapter needs review")
            kwargs["user_prompt"] = kwargs["user_prompt"].replace(old_json, json.dumps(context, ensure_ascii=False))
            kwargs["public_context"] = context
        # B2 intentionally gets neither current choice nor revealing history.
        return self.recorded.call(**kwargs)


def apply_recommendation(page, executor, result):
    """Selection only. A recommendation is never converted into a submit proposal."""
    before = runner.capture_state(page)
    option = result.recommended_option
    receipt = None
    error = None
    try:
        if result.parse_status == "valid" and option != core.current_selection(before):
            if option not in core.visible_options(before):
                raise ValueError("recommendation is not a current visible option")
            receipt = executor.execute(dict(action="select_option", select_name="primary_action",
                                             option_text=option), phase="verification_selection")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    after = runner.capture_state(page)
    handoff = dict(
        original_pending_proposal_status="cancelled",
        verification=dict(parse_status=result.parse_status,
                          recommended_option=option if result.parse_status == "valid" else None,
                          raw_records=result.records),
        selection_execution=dict(before=core.current_selection(before),
                                 after=core.current_selection(after), receipt=receipt, error=error),
    )
    core.assert_online_payload(handoff)
    return handoff
