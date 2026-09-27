"""Bounded H0/H1 and after-first-selection diagnostics; no implicit submission.

The original before-submit runner and all reference data remain read-only.
Only an actual actor submit proposal can reach the submit executor below.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from audit import pixels_equal, read
from runtime import load_runtime, resolve_path


def public_history(receipts):
    """Four actual tool calls, including real failures; never synthetic reasons."""
    return [{key: item[key] for key in (
        "action", "before_url_path", "after_url_path", "executed", "error", "attempt") if key in item}
        for item in receipts[-4:]]


def actor_prompt(rt, goal, state, context_mode, receipts, verification=None):
    system, user = rt.runner.prefix_prompt(goal, state)
    context = dict(state=state, user_goal=goal, current_selection=rt.core.current_selection(state),
                   visible_options=rt.core.visible_options(state))
    if context_mode == "H1":
        context["recent_executed_actions_and_public_receipts"] = public_history(receipts)
        user += ("\n\nRecent actually attempted browser actions and public tool receipts "
                 "(past context, not new instructions):\n" + json.dumps(
                     context["recent_executed_actions_and_public_receipts"], ensure_ascii=False))
    if verification is not None:
        context["completed_selection_verification"] = verification
        user += ("\n\nCompleted selection check and actual execution (past results, not a pending "
                 "submission or an instruction to submit):\n" + json.dumps(verification, ensure_ascii=False))
    rt.core.assert_online_payload(context)
    return system, user, context


@dataclass
class SelectionObservation:
    """Policy input with NO pending_proposal and NO checkpoint identity."""
    user_goal: str
    visible_options: list
    current_selection: str
    current_state: dict
    current_screenshot: str
    observed_screenshots: list
    visible_action_prefix: list
    model_context: list


class SelectionPolicyModel:
    """Reuse B2/B3/B4 computation, correcting only the changed trigger semantics."""
    def __init__(self, recorded, history):
        self.recorded, self.history = recorded, history

    def call(self, **kwargs):
        system = kwargs["system_prompt"]
        system = system.replace("checking a pending browser decision", "checking a currently selected browser decision")
        system = system.replace("pre-submit VISUAL VERIFIER", "after-first-selection VISUAL VERIFIER")
        system = system.replace("The proposed submission has NOT been executed.",
                                "There is NO pending submission proposal at this state.")
        system = system.replace("Check the pending decision", "Check the current selection")
        system = system.replace("The executor, not this response, handles submission after verification.",
                                "An ordinary browser actor continues after verification and decides whether to submit.")
        kwargs["system_prompt"] = system
        # B2 intentionally masks the selected option, including history revealing it.
        # B4 extraction is also chart-only. These are the existing independent/extraction designs.
        if kwargs["phase"].startswith("b3_"):
            context = dict(kwargs["public_context"])
            context["verification_phase"] = "after_first_selection"
            context["recent_executed_actions_and_public_receipts"] = self.history
            kwargs["user_prompt"] = kwargs["user_prompt"].replace(
                json.dumps(kwargs["public_context"], ensure_ascii=False), json.dumps(context, ensure_ascii=False))
            kwargs["public_context"] = context
        return self.recorded.call(**kwargs)


def snapshot(page, rt, directory, name):
    path = directory / "screenshots" / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    state = rt.runner.capture_state(page)
    page.screenshot(path=str(path), full_page=True)
    return state, path


def execute_normal(executor, action, *, phase, submit=False):
    return executor.execute(action, phase=phase, max_attempts=1 if submit else None)


def reconstruct(rt, page, executor, base_url, source, directory):
    old_root = resolve_path(source["source_run"])
    observed = []
    expected_observations = source["observed_screenshots"]
    checks = []
    for index, receipt in enumerate(source["replay_receipts"]):
        action = receipt["action"]
        if index == 0:
            executor.navigate(base_url + action["text"], phase="replay_initial_navigation")
        else:
            execute_normal(executor, action, phase="replay_source_action")
        state, shot = snapshot(page, rt, directory, f"replay_{index:02d}")
        # The old sequence has one observation per successful action here.
        if index < len(expected_observations):
            expected = expected_observations[index]
            same = pixels_equal(shot, old_root / expected["path"])
            checks.append(dict(index=index, original=str(old_root / expected["path"]),
                               rebuilt=str(shot), all_pixels_equal=same))
        observed.append(dict(kind=rt.runner.screenshot_kind(state["url_path"]), path=str(shot)))
    expected_state = source["request_after_selection"]["public_context"]["state"]
    proof = dict(source_state_request=source["source_state_request"], replay_receipts=executor.receipts,
                 expected_state=expected_state, rebuilt_state=state,
                 public_state_equal=state == expected_state, image_checks=checks,
                 all_images_equal=len(checks) == len(expected_observations) and all(x["all_pixels_equal"] for x in checks))
    rt.core.write_json(directory / "reconstruction.json", proof)
    supported = proof["public_state_equal"] and proof["all_images_equal"]
    return supported, observed, state, shot


def continue_actor(rt, page, executor, model, goal, alias, directory, receipts_path,
                   context_mode, observed, max_calls, verification=None):
    timeline, contexts = [], []
    hook = rt.core.BeforeSubmitHook()
    calls_before = model.ledger.model_calls
    receipt_offset = rt.runner.line_count(receipts_path)
    result = dict(status="actor_call_limit", checkpoint_reached=False, submitted=False,
                  confirmation_observed=False, timeline=timeline)
    for step in range(max_calls):
        before, shot = snapshot(page, rt, directory, f"actor_{step:02d}_before")
        observed.append(dict(kind=rt.runner.screenshot_kind(before["url_path"]), path=str(shot)))
        system, user, public = actor_prompt(rt, goal, before, context_mode, executor.receipts, verification)
        entry = dict(step=step, state_before=before, screenshot_before=str(shot))
        timeline.append(entry)
        try:
            reply = model.call(phase="prefix", system_prompt=system, user_prompt=user, image_path=shot,
                               image_artifact=str(shot.relative_to(directory)), public_context=public,
                               request_dir=directory / "requests", response_dir=directory / "responses")
            action = rt.runner._extract_action(reply.text)
            entry.update(request_id=reply.metadata["request_id"], response=reply.text, action=action)
            contexts.append(dict(response=reply.text, proposed_action=action))
            cp = hook.inspect(task_alias=alias, user_goal=goal, state=before, current_screenshot=str(shot),
                              observed_screenshots=observed,
                              visible_action_prefix=[x["action"] for x in executor.receipts if x["executed"] and x["action"]["action"] != "goto"],
                              model_context=contexts, proposal=action)
            if cp is not None:
                # This is a REAL model proposal. No policy is invoked as a submit stand-in.
                result["checkpoint_reached"] = True
                result["checkpoint_selection"] = rt.core.current_selection(before)
                rt.core.write_json(directory / "before_submit_checkpoint.json", cp.to_dict())
                entry["receipt"] = execute_normal(executor, action, phase="actor_submit", submit=True)
                result["status"] = "submit_attempted"
            elif action["action"] == "finish":
                result["status"] = "finish_without_submit"
            elif action["action"] == "invalid":
                entry["error"] = "invalid_model_action"
            else:
                entry["receipt"] = execute_normal(executor, action, phase="actor_action")
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            result["status"] = "actor_runtime_failure"
            break
        after, after_shot = snapshot(page, rt, directory, f"actor_{step:02d}_after")
        entry.update(state_after=after, screenshot_after=str(after_shot))
        rt.core.write_json(directory / "actor_timeline.json", timeline)
        if cp is not None or action["action"] == "finish":
            break
    new_receipts = rt.runner.read_rows_after(receipts_path, receipt_offset)
    result["server_receipts"] = new_receipts
    result["submitted"] = len(new_receipts) == 1
    final_state, final_shot = snapshot(page, rt, directory, "terminal")
    result["confirmation_observed"] = final_state["url_path"].endswith("/confirmation")
    result["final_selection"] = (new_receipts[-1]["selected_option_label"] if new_receipts
                                 else rt.core.current_selection(final_state))
    result["final_screenshot"] = str(final_shot)
    if result["submitted"] and result["confirmation_observed"]:
        result["status"] = ("submitted_with_runtime_error" if any(x.get("error") for x in timeline)
                            else "submitted_confirmed")
    elif len(new_receipts) > 1:
        result["status"] = "duplicate_submission_failure"
    result["actor_calls"] = model.ledger.model_calls - calls_before
    return result


def chart_branch(rt, browser, model, ledger, source, bundle, output, method):
    alias, goal = bundle.public_task["task_alias"], bundle.public_task["user_goal"]
    directory = output / "online" / source["prefix_id"] / method
    receipts_path = output / "server_receipts" / f"{source['prefix_id']}_{method}.jsonl"
    directory.mkdir(parents=True)
    calls_before, transitions_before = ledger.model_calls, ledger.browser_transitions
    result = dict(method=method, status="not_started", verification_executed=False,
                  initial_selection=source["request_after_selection"]["public_context"]["current_selection"],
                  checkpoint_reached=False, submitted=False)
    with rt.runner.managed_shell(bundle.public_task, bundle.chart_path, receipts_path) as server:
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        executor = rt.runner.BrowserExecutor(page, ledger=ledger, task_alias=alias)
        try:
            supported, observed, state, shot = reconstruct(rt, page, executor, server.base_url, source, directory)
            result["reconstruction_supported"] = supported
            if not supported:
                result["status"] = "reconstruction_unsupported"
                return result
            verification = None
            result["immediate_selection"] = rt.core.current_selection(state)
            if method in ("A2", "A3", "A4"):
                observation = SelectionObservation(goal, rt.core.visible_options(state), rt.core.current_selection(state),
                    state, str(shot), observed, [x["action"] for x in executor.receipts if x["executed"]], [])
                result["verification_executed"] = True
                result["status"] = "verification_running"
                policy = rt.policies.run_policy("B" + method[1:], observation,
                    model=SelectionPolicyModel(model, public_history(executor.receipts)),
                    artifact_root=output, unit_dir=directory / "verification")
                result["verification"] = policy.to_dict()
                revision_receipts = []
                # Identical selector executor for actor and verifier recommendations.
                if policy.recommended_option and policy.recommended_option != rt.core.current_selection(state):
                    action = dict(action="select_option", select_name="primary_action", option_text=policy.recommended_option)
                    revision_receipts.append(execute_normal(executor, action, phase="verification_selection"))
                checked_state, checked_shot = snapshot(page, rt, directory, "immediately_after_verification")
                result["immediate_selection"] = rt.core.current_selection(checked_state)
                verification = dict(recommended_option=policy.recommended_option, parse_status=policy.parse_status,
                                    model_outputs=policy.records, actual_revision_receipts=public_history(revision_receipts),
                                    selection_after_execution=result["immediate_selection"])
                rt.core.write_json(directory / "verification_handoff.json", verification)
                result["status"] = "verification_completed"
            context_mode = method if method in ("H0", "H1") else "H1"
            result.update(continue_actor(rt, page, executor, model, goal, alias, directory, receipts_path,
                                         context_mode, observed, 4, verification))
            first_action = next((x.get("action", {}) for x in result["timeline"]), {})
            result["next_action_changed_selection"] = (first_action.get("action") == "select_option"
                and first_action.get("option_text") != result["immediate_selection"]
                and bool(result["timeline"][0].get("receipt", {}).get("executed")))
        except Exception as exc:
            result["status"] = "verification_failure" if result["status"] == "verification_running" else "branch_runtime_failure"
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            result.update(model_calls=ledger.model_calls - calls_before,
                          browser_transitions=ledger.browser_transitions - transitions_before,
                          executor_receipts=executor.receipts)
            rt.core.write_json(directory / "result.json", result)
            page.close()
    return result


def run_controls(rt, browser, model, ledger, output):
    chart = output / "control_route_card.png"
    im = Image.new("RGB", (640, 240), "white")
    ImageDraw.Draw(im).text((30, 90), "Route selector: follow the explicit user goal. No chart.", fill="black")
    im.save(chart)
    rows = []
    for target, initial in (("Route A", "Route A"), ("Route A", "Route B"), ("Route B", "Route A"), ("Route B", "Route B")):
        number = len(rows) // 2 + 1
        task = dict(task_alias="control", page_title="Route workflow control",
                    user_goal=f"Choose {target} in the route selector and submit the decision form.",
                    chart_reference="This is a route workflow control, not a chart interpretation task.",
                    primary_field_label="Route", option_labels=["Route A", "Route B"])
        for mode in ("H0", "H1"):
            directory = output / "online" / f"control_{number:02d}" / mode
            receipts_path = output / "server_receipts" / f"control_{number:02d}_{mode}.jsonl"
            calls_before, transitions_before = ledger.model_calls, ledger.browser_transitions
            with rt.runner.managed_shell(task, chart, receipts_path) as server:
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                executor = rt.runner.BrowserExecutor(page, ledger=ledger, task_alias="control")
                result = dict(status="setup_failure", submitted=False)
                try:
                    executor.navigate(server.base_url + "/task/control", phase="control_setup")
                    for action in (dict(action="click_link", text="Open Dashboard"), dict(action="click_link", text="Open Form"),
                                   dict(action="select_option", select_name="primary_action", option_text=initial)):
                        execute_normal(executor, action, phase="control_setup")
                    state, shot = snapshot(page, rt, directory, "control_initial")
                    result = continue_actor(rt, page, executor, model, task["user_goal"], "control", directory,
                                            receipts_path, mode, [], 2)
                    result.update(initial_state=state, initial_screenshot=str(shot))
                except Exception as exc:
                    result["error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    result.update(control_id=number, context_mode=mode, explicit_target=target, initial_selection=initial,
                                  model_calls=ledger.model_calls - calls_before,
                                  browser_transitions=ledger.browser_transitions - transitions_before,
                                  executor_receipts=executor.receipts)
                    result["correctly_completed"] = bool(result.get("submitted") and result.get("confirmation_observed") and result.get("final_selection") == target)
                    rt.core.write_json(directory / "result.json", result)
                    rows.append(result)
                    page.close()
            print(f"control {number} {mode}: {result['status']}", flush=True)
    return rows


def offline_labels(rt, raw_task, result):
    def correct(label):
        return rt.safe_shell.score_receipt(raw_task, {"selected_option_label": label})["outcome"] == "success" if label else None
    out = {key + "_correct": correct(result.get(key)) for key in (
        "initial_selection", "immediate_selection", "checkpoint_selection", "final_selection")}
    events = []
    for receipt in result.get("executor_receipts", []):
        action = receipt["action"]
        if receipt["executed"] and action["action"] == "select_option":
            events.append(dict(phase=receipt["phase"], selection=action["option_text"], correct=correct(action["option_text"])))
    out["selection_events"] = events
    out["score"] = (rt.safe_shell.score_receipt(raw_task, result["server_receipts"][0])
                    if result.get("submitted") else {"outcome": "not_submitted"})
    previous = correct(result.get("initial_selection"))
    counts = dict(wrong_selections=0, ordinary_self_corrections=0, verification_corrections=0, correct_to_wrong=0)
    for event in events:
        if event["phase"].startswith("replay"):
            continue
        if event["correct"] is False:
            counts["wrong_selections"] += 1
        if previous is False and event["correct"] is True:
            counts["verification_corrections" if event["phase"] == "verification_selection" else "ordinary_self_corrections"] += 1
        if previous is True and event["correct"] is False:
            counts["correct_to_wrong"] += 1
        previous = event["correct"]
    out["event_counts"] = counts
    return out


class DiagnosticMock:
    """Engineering-only backend: explicit nonchart controls or retain current chart choice."""
    def __init__(self, rt):
        self.rt, self.fallback = rt, rt.models.ScriptedMockBackend()

    @property
    def metadata(self):
        return dict(kind="diagnostic_scripted_mock", research_result=False)

    def complete(self, request):
        if request.phase == "prefix":
            context = request.public_context
            goal, current = context["user_goal"], context["current_selection"]
            if goal.startswith("Choose Route "):
                target = goal.split(" in the route selector")[0].removeprefix("Choose ")
                action = (dict(action="select_option", select_name="primary_action", option_text=target)
                          if current != target else dict(action="click_button", text="Submit Form"))
            else:
                action = dict(action="click_button", text="Submit Form")
            return self.rt.models.ModelReply(json.dumps(action), {"mock": True})
        return self.fallback.complete(request)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=["mock", "live-local"], required=True)
    parser.add_argument("--authorized-live", action="store_true", help="Only pass after explicit authorization for THIS panel")
    parser.add_argument("--local-model-url", default="http://127.0.0.1:8045")
    parser.add_argument("--browser-executable", required=True)
    args = parser.parse_args()
    args.session_root = resolve_path(args.session_root)
    args.source_run = resolve_path(args.source_run)
    args.audit_dir = resolve_path(args.audit_dir)
    if args.mode == "live-local" and not args.authorized_live:
        parser.error("explicit authorization for this panel must be recorded before live inference")
    rt = load_runtime(args.source_run)
    output = (args.session_root / args.run_id).resolve()
    output.mkdir(parents=True, exist_ok=False)
    # One ordinary cumulative cost read, not a new experiment review system.
    prior_transitions = prior_real_calls = 0
    for path in args.session_root.glob("*/budget.json"):
        prior = read(path)
        prior_transitions += prior["browser_transitions"]
        manifest = read(path.parent / "run_manifest.json")
        if manifest["mode"] == "live-local":
            prior_real_calls += prior["model_calls"]
    ledger = rt.core.BudgetLedger(max_model_calls=200 - prior_real_calls,
                                 max_browser_transitions=800 - prior_transitions)
    ledger.bind_snapshot(output / "budget.json")
    manifest = dict(mode=args.mode, started_at=rt.runner.utc_now(), source_run=str(args.source_run.resolve()),
                    runtime_source=str(rt.snapshot), command=sys.argv, python=sys.version, platform=platform.platform(),
                    status="running", prior_browser_transitions=prior_transitions, prior_real_model_calls=prior_real_calls,
                    actor_protocol="unchanged legacy prefix_prompt; H1 adds at most 4 real tool receipts",
                    diagnostic="retrospective_after_first_selection", concurrency=1,
                    viewport=[1440, 1100], browser_executable=args.browser_executable,
                    authorized_live=args.authorized_live)
    rt.core.write_json(output / "run_manifest.json", manifest)
    for source in Path(__file__).parent.glob("*.py"):
        destination = output / "implementation" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shared_source = Path(__file__).resolve().parents[1] / "path_compat.py"
    shutil.copy2(shared_source, output / "implementation/path_compat.py")
    rows, controls = [], []
    try:
        backend = (DiagnosticMock(rt) if args.mode == "mock" else rt.models.LocalQwenServiceBackend(
            server_url=args.local_model_url, max_output_tokens=1024, temperature=0.0, top_p=1.0, seed=12345))
        model = rt.models.RecordedModel(backend, ledger=ledger)
        manifest["model"] = model.metadata
        rt.core.write_json(output / "run_manifest.json", manifest)
        if args.mode == "live-local":
            manifest["multi_image_witness"] = rt.runner.run_multi_image_witness(model=model, run_root=output, seed=12345)
            if manifest["multi_image_witness"]["status"] != "passed":
                raise RuntimeError("existing native multi-image service check failed; no panel was started")
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        with rt.runner.require_playwright()() as playwright:
            browser = playwright.chromium.launch(executable_path=args.browser_executable, headless=True,
                                                  args=list(rt.runner.BROWSER_LAUNCH_ARGS))
            try:
                controls = run_controls(rt, browser, model, ledger, output)
                rt.core.write_json(output / "evaluator/controls.json", controls)
                sources = read(args.audit_dir / "FIRST_SELECTION_SOURCES.json")
                for source in sources:
                    raw = rt.runner.find_task(rt.runner.task_spec_path(source["condition"], source["task_slug"]), source["task_slug"])
                    bundle = rt.safe_shell.build_shell_bundle(raw, task_alias=source["task_alias"], repository_root=rt.snapshot)
                    for method in ("H0", "H1", "A2", "A3", "A4"):
                        result = chart_branch(rt, browser, model, ledger, source, bundle, output, method)
                        row = dict(prefix_id=source["prefix_id"], task_slug=source["task_slug"], condition=source["condition"],
                                   evidence_conflict=source["task_slug"] == "env008", **result,
                                   evaluation=offline_labels(rt, raw, result))
                        rows.append(row)
                        rt.core.write_json(output / "evaluator/chart_results.json", rows)
                        print(f"{source['prefix_id']} {method}: {result['status']}, calls={result['model_calls']}, transitions={result['browser_transitions']}", flush=True)
                # A0 is a reference to an actual H1 trajectory, never a duplicate call or submit.
                rt.core.write_json(output / "evaluator/A0_reuse.json", [dict(prefix_id=r["prefix_id"],
                    source_method="H1", diagnostic_method="A0", additional_calls=0, additional_transitions=0,
                    result_path=f"online/{r['prefix_id']}/H1/result.json") for r in rows if r["method"] == "H1"])
                manifest["status"] = "panel_finished"
            finally:
                browser.close()
    except Exception as exc:
        manifest.update(status="runtime_failure", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        manifest.update(completed_at=rt.runner.utc_now(), budget=ledger.to_dict(),
                        chart_branches=len(rows), control_branches=len(controls))
        rt.core.write_json(output / "run_manifest.json", manifest)
        rt.core.write_json(output / "evaluator/chart_results.json", rows)
        rt.core.write_json(output / "evaluator/controls.json", controls)


if __name__ == "__main__":
    main()
