"""Small prospective workflow adapter. Not a model launcher or paid-panel CLI."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from research.decision_evidence_audit import core, runner, policies
from .h_base import actor_prompt, VerifierModel, apply_recommendation
from .api_backend import ApiStop


class TransitionScope:
    """Count actual retries against both the existing ledger and this prefix limit."""
    def __init__(self, ledger, cap=20):
        self.ledger, self.cap, self.used = ledger, cap, 0

    def charge_transition(self, **kwargs):
        if self.used >= self.cap:
            raise core.BudgetExceeded("per-prefix browser transition cap reached")
        self.ledger.charge_transition(**kwargs)
        self.used += 1


def snapshot(page, directory, name):
    state = runner.capture_state(page)
    shot = directory / "screenshots" / f"{name}.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shot), full_page=True)
    return state, shot


def capture_pending(page, executor, model, *, goal, alias, directory, max_calls=12,
                    prior_history=(), receipt_offset=0, observed=(), verification=None):
    """Stop on the first real submit proposal. Never execute it inside this function.

    Also used for <=4 ordinary actor calls AFTER verification; caller executes
    an actual returned proposal without sending it through verification again.
    """
    directory = Path(directory).resolve()
    if not 0 <= max_calls <= (4 if verification is not None else 12):
        raise ValueError("prefix/continuation model-call allowance is outside the protocol")
    observed = list(observed)
    contexts, timeline = [], []
    hook = core.BeforeSubmitHook()
    status = "prefix_call_limit" if verification is None else "continuation_call_limit"
    checkpoint = None
    for step in range(max_calls):
        state, shot = snapshot(page, directory, f"{step:02d}_before")
        observed.append(dict(kind=runner.screenshot_kind(state["url_path"]), path=str(shot)))
        history = list(prior_history) + executor.receipts[receipt_offset:]
        system, user, public = actor_prompt(goal, state, history, verification)
        row = dict(step=step, state_before=state, screenshot_before=str(shot))
        timeline.append(row)
        try:
            reply = model.call(phase="prefix" if verification is None else "actor_continuation",
                system_prompt=system, user_prompt=user, image_path=shot,
                image_artifact=str(shot.relative_to(directory)), public_context=public,
                request_dir=directory / "requests", response_dir=directory / "responses")
            action = runner._extract_action(reply.text)
            row.update(response=reply.text, request_id=reply.metadata["request_id"], action=action)
            contexts.append(dict(response=reply.text, proposed_action=action))
            checkpoint = hook.inspect(task_alias=alias, user_goal=goal, state=state,
                current_screenshot=str(shot), observed_screenshots=observed,
                visible_action_prefix=[r["action"] for r in history if r.get("executed") and r["action"]["action"] != "goto"],
                model_context=contexts, proposal=action)
            if checkpoint is not None:
                status = "before_submit_pending"
                break
            if action["action"] == "finish":
                status = "finish_without_submit"
                break
            if action["action"] == "invalid":
                row["error"] = "invalid_model_action"
                continue
            row["receipt"] = executor.execute(action, phase="ordinary_actor_action")
            after, after_shot = snapshot(page, directory, f"{step:02d}_after")
            row.update(state_after=after, screenshot_after=str(after_shot))
        except Exception as exc:
            row.update(error_type=type(exc).__name__, error=str(exc))
            status = "runtime_failure"
            if isinstance(exc, (ApiStop, core.BudgetExceeded)):
                core.write_json(directory / "prefix_result.json", dict(status=status, checkpoint_reached=False, timeline=timeline))
                raise
            # Failures are logged, never retried with another model/prompt.
            break
        finally:
            core.write_json(directory / "timeline.json", timeline)
    if checkpoint:
        core.write_json(directory / "checkpoint.json", checkpoint.to_dict())
    result = dict(status=status, checkpoint_reached=checkpoint is not None,
                  current_selection=core.current_selection(runner.capture_state(page)), timeline=timeline)
    core.write_json(directory / "prefix_result.json", result)
    return checkpoint, result


def restore(page, executor, checkpoint, *, base_url, directory):
    executor.navigate(f"{base_url}/task/{checkpoint.task_alias}", phase="replay_initial")
    for action in checkpoint.visible_action_prefix:
        executor.execute(action, phase="replay_action")
    state, shot = snapshot(page, directory, "restored")
    with Image.open(checkpoint.current_screenshot) as a, Image.open(shot) as b:
        equal = a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()
    proof = dict(public_state_equal=state == checkpoint.current_state, screenshot_pixels_equal=equal,
                 physical_replay_receipts=list(executor.receipts),
                 logical_history_source="original natural prefix receipts; physical replay not duplicated as logical history")
    core.write_json(directory / "replay.json", proof)
    return proof["public_state_equal"] and proof["screenshot_pixels_equal"]


def run_branch(page, executor, model, checkpoint, *, strategy, directory, prefix_receipts,
               submission_path, max_continuation_calls=4):
    """Caller MUST restore and compare the shared public state before branching."""
    if strategy not in {"B0", "B2", "B3"}:
        raise ValueError("Only the three specified prospective strategies are supported")
    if max_continuation_calls > 4 or max_continuation_calls < 0:
        raise ValueError("continuation allowance must be 0..4")
    state, shot = snapshot(page, directory, "branch_start")
    with Image.open(checkpoint.current_screenshot) as a, Image.open(shot) as b:
        same = a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()
    if state != checkpoint.current_state or not same:
        return dict(status="unsupported_restore", submitted=False, verification_executed=False)
    offset = runner.line_count(submission_path)
    receipt_offset = len(executor.receipts)
    result = dict(strategy=strategy, original_pending_proposal_status="pending", verifier_recommendation=None,
                  executor_selection=core.current_selection(state), actor_final_submission=None,
                  verification_executed=False, submitted=False)
    try:
        pending = checkpoint
        if strategy != "B0":
            result["original_pending_proposal_status"] = "cancelled"
            # This input is a genuine pending checkpoint, NOT after-first-selection.
            policy = policies.run_policy(strategy, checkpoint,
                model=VerifierModel(model, prefix_receipts), artifact_root=Path("/"), unit_dir=directory / "verification")
            result["policy"] = policy.to_dict()
            result["verification_executed"] = policy.model_calls > 0
            result["verifier_recommendation"] = policy.recommended_option if policy.parse_status == "valid" else None
            handoff = apply_recommendation(page, executor, policy)
            core.write_json(directory / "handoff.json", handoff)
            result["executor_selection"] = handoff["selection_execution"]["after"]
            pending, continuation = capture_pending(page, executor, model,
                goal=checkpoint.user_goal, alias=checkpoint.task_alias, directory=directory / "continuation",
                max_calls=max_continuation_calls, prior_history=prefix_receipts,
                receipt_offset=receipt_offset, observed=checkpoint.observed_screenshots, verification=handoff)
            result["continuation"] = continuation
        if pending is not None:
            result["actor_final_submission"] = dict(option=pending.current_selection, proposal=pending.pending_proposal)
            result["submit_execution"] = executor.execute(pending.pending_proposal, phase="actual_submit", max_attempts=1)
            if strategy == "B0":
                result["original_pending_proposal_status"] = "executed"
            result["status"] = "submit_attempted"
        else:
            result["status"] = "no_actor_submit_proposal"
    except Exception as exc:
        result.update(status="branch_runtime_failure", error_type=type(exc).__name__, error=str(exc))
        if isinstance(exc, (ApiStop, core.BudgetExceeded)):
            core.write_json(directory / "branch_result.json", result)
            raise
    receipts = runner.read_rows_after(submission_path, offset)
    result["server_receipts"] = receipts
    result["submitted"] = len(receipts) == 1
    result["final_state"] = runner.capture_state(page)
    result["confirmation_observed"] = result["final_state"]["url_path"].endswith("/confirmation")
    core.write_json(directory / "branch_result.json", result)
    return result
