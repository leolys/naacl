"""Post-hoc first-selection comparison; no modification of before-submit."""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import shutil
from pathlib import Path

from PIL import Image
from .core import BudgetExceeded, canonical_state, current_selection, is_submit_proposal, visible_options, write_json
from .models import LocalQwenServiceBackend, ModelReply, RecordedModel
from .natural_prefix import BROWSER, MODEL_PATH, RunLedger, load_ledger, read
from .policies import _extract_object
from .runner import (BROWSER_LAUNCH_ARGS, BrowserExecutor, _extract_action,
                     capture_state, file_sha256, managed_shell, prefix_prompt, read_jsonl,
                     require_playwright, utc_now)
from .safe_shell import score_receipt

OLD = Path(__file__).resolve().parent / "runs/natural_prefix_20260907T0932Z"
CONDITIONS = ("H0", "H1", "H1+V")
ORDERS = (CONDITIONS, ("H1", "H1+V", "H0"), ("H1+V", "H0", "H1"), CONDITIONS)
HISTORY_INTRO = "\n\nExecuted action history and observed visible results, in time order:\n"
ADVICE_INTRO = ("\n\nIndependent chart-check model suggestion (not authoritative; "
                "use it as advice while deciding your next browser action):\n")
V_SYSTEM = ("You are checking a pending browser decision using only the user goal, visible options, "
            "and supplied screenshot. Never assume evaluator labels or unavailable data. Return JSON only.")


def actor_prompt(goal, state, history, strategy, advice=None):
    system, user = prefix_prompt(goal, state)
    if strategy != "H0":
        user += HISTORY_INTRO + json.dumps(history, ensure_ascii=False)
    if strategy == "H1+V":
        user += ADVICE_INTRO + json.dumps(advice, ensure_ascii=False)
    return system, user


def verification_prompt(goal, options):
    return V_SYSTEM, (
        f"User goal: {goal}\n"
        f"Visible decision options: {json.dumps(options, ensure_ascii=False)}\n"
        "Re-read the complete chart and check the goal semantics. Make an independent decision; "
        "the current selection is intentionally not shown. Return "
        '{"option_label":"exact visible option","reason":"brief visible-evidence reason"}.'
    )


def first_selection_source(directory):
    requests = [read(p) for p in sorted((directory / "prefix/requests").glob("*.json"))]
    prefix = read(directory / "prefix/prefix_result.json")
    successful = [r["action"] for r in prefix["executor_receipts"]
                  if r["phase"] == "prefix_action" and r["executed"]]
    index = next(i for i, a in enumerate(successful) if a["action"] == "select_option")
    actions = successful[:index + 1]
    # Source runs have one successful action per model request up to this point.
    if actions != prefix["executed_prefix"][:index + 1]:
        raise ValueError("source prefix contains ambiguous action alignment")
    for i, action in enumerate(actions):
        response = read(directory / "prefix/responses" / (requests[i]["request_id"] + ".json"))
        if _extract_action(response["text"]) != action:
            raise ValueError("source action/request alignment failed")
    after = requests[index + 1]
    if after["public_context"]["current_selection"] != actions[-1]["option_text"]:
        raise ValueError("first successful selection not reflected in next observation")
    history = [{"action": {"action": "goto", "text": requests[0]["public_context"]["state"]["url_path"]},
                "execution_succeeded": True, "result_state": requests[0]["public_context"]["state"]}]
    history += [{"action": action, "execution_succeeded": True,
                 "result_state": requests[i+1]["public_context"]["state"]} for i, action in enumerate(actions)]
    dashboard = next(q for q in requests[:index+1]
                     if q["public_context"]["state"]["url_path"].endswith("/dashboard"))
    return {"state": after["public_context"]["state"], "history": history, "actions": actions,
            "source_after_request": after["request_id"], "source_after_local_call": index+2,
            "source_first_selection_local_call": index+1,
            "screenshot": after["image_artifacts"][0], "dashboard": dashboard["image_artifacts"][0]}


def compare_old_inputs(root):
    observations = read_jsonl(OLD / "live_20260907T1202Z/model_input_observations.jsonl")
    actual = {o["payload"]["image_paths"][0]: o for o in observations}
    pairs, flags = [], []
    for ep in ("episode_01", "episode_02"):
        directory = OLD / "units" / ep
        qs = [read(p) for p in sorted((directory / "prefix/requests").glob("*.json"))]
        for group in ((4, 6, 8), (5, 7), (3, 5)):
            for a, b in itertools.combinations(group, 2):
                x, y = qs[a-1], qs[b-1]
                px, py = [OLD / q["image_artifacts"][0] for q in (x, y)]
                ox, oy = actual[str(px)], actual[str(py)]
                def payload_content(o):
                    return {k: v for k, v in o["payload"].items() if k not in ("image_paths", "image_path")}
                with Image.open(px) as ix, Image.open(py) as iy:
                    pixels_equal = ix.mode == iy.mode and ix.size == iy.size and ix.tobytes() == iy.tobytes()
                pairs.append({"episode": ep, "local_calls": [a, b], "group": list(group),
                    "system_equal": x["system_prompt"] == y["system_prompt"],
                    "user_equal": x["user_prompt"] == y["user_prompt"],
                    "public_state_equal": x["public_context"]["state"] == y["public_context"]["state"],
                    "selected_text": [q["public_context"]["current_selection"] for q in (x, y)],
                    "image_file_bytes_equal": px.read_bytes() == py.read_bytes(), "image_pixels_equal": pixels_equal,
                    "service_payload_except_path_equal": payload_content(ox) == payload_content(oy),
                    "processor_tensor_shapes_equal": ox["processor_tensor_shapes"] == oy["processor_tensor_shapes"],
                    "image_grid_equal": ox["image_grid_thw"] == oy["image_grid_thw"],
                    "request_id_and_image_path_differ": x["request_id"] != y["request_id"] and px != py})
        for i, q in enumerate(qs, 1):
            for select in q["public_context"]["state"]["selects"]:
                selected = [o["text"] for o in select["options"] if o["selected"]]
                flags.append({"episode": ep, "local_call": i, "selected_text": select["selected_text"],
                              "selected_flags": selected, "consistent": selected == [select["selected_text"]],
                              "screenshot": q["image_artifacts"][0]})
    write_json(root / "OLD_INPUT_COMPARISON.json", {"pairs": pairs, "selected_flags": flags,
        "processed_tensor_values": "not retained in old run; equality checked for original pixels, text, shapes, grid and processing configuration only"})


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "preparation.json").open("x") as stream:
        json.dump({"started_at": utc_now(), "protocol_version": 1}, stream)
    compare_old_inputs(root)
    units = []
    for i in range(1, 5):
        old = OLD / "units" / f"episode_{i:02d}"
        directory = root / "sources" / f"episode_{i:02d}"
        directory.mkdir(parents=True)
        source = first_selection_source(old)
        shutil.copy2(OLD / source["screenshot"], directory / "first_selection.png")
        shutil.copy2(OLD / source["dashboard"], directory / "dashboard.png")
        source["screenshot"], source["dashboard"] = "first_selection.png", "dashboard.png"
        write_json(directory / "state.json", source)
        shutil.copy2(old / "public_task.json", directory / "public_task.json")
        chart = next(old.glob("chart_original.*"))
        shutil.copy2(chart, directory / chart.name)
        shutil.copytree(old / "evaluator", directory / "evaluator")
        for strategy in ORDERS[i-1]:
            uid = f"unit_{len(units)+1:02d}"
            entry = {"unit_id": uid, "source_episode": f"episode_{i:02d}", "strategy": strategy}
            units.append(entry)
            write_json(root / "units" / uid / "result.json", {**entry, "status": "not_run"})
    write_json(root / "manifest.json", {"version": 1, "source_run": str(OLD), "units": units,
        "max_calls_per_unit_including_verifier": 6, "max_real_model_calls": 80, "max_browser_transitions": 240})
    ledger = RunLedger(max_model_calls=80, max_browser_transitions=240)
    ledger.bind_snapshot(root / "budget.json")
    source_dir = root / "executed_sources"
    source_dir.mkdir()
    for name in ("first_selection_diagnostic.py", "runner.py", "core.py", "models.py", "policies.py", "safe_shell.py", "natural_prefix.py"):
        shutil.copy2(Path(__file__).parent / name, source_dir / name)


class UnitLedger:
    """Delegate all accounting to the run ledger, with a six-call local cap."""
    def __init__(self, ledger, call_limit=6, transition_limit=18):
        self.ledger, self.call_limit, self.transition_limit = ledger, call_limit, transition_limit
        self.start_calls, self.start_steps = ledger.model_calls, ledger.browser_transitions

    @property
    def calls(self):
        return self.ledger.model_calls - self.start_calls

    @property
    def steps(self):
        return self.ledger.browser_transitions - self.start_steps

    def charge_model(self, **kwargs):
        if self.calls >= self.call_limit:
            raise BudgetExceeded("unit model-call cap reached")
        self.ledger.charge_model(**kwargs)

    def charge_transition(self, **kwargs):
        if self.steps >= self.transition_limit:
            raise BudgetExceeded("unit browser transition cap reached")
        self.ledger.charge_transition(**kwargs)


def online_unit(browser, public, source, source_dir, directory, root, strategy, backend, ledger):
    # No evaluator spec, score or paired arm enters this online function.
    local = UnitLedger(ledger)
    model = RecordedModel(backend, ledger=local)
    history = copy.deepcopy(source["history"])
    events, advice = [], None
    result = {"status": "started", "initial_selection": current_selection(source["state"])}
    chart = next(source_dir.glob("chart_original.*"))
    receipts_path = directory / "post_receipts.jsonl"
    page = executor = None
    try:
        with managed_shell(public, chart, receipts_path) as shell:
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            executor = BrowserExecutor(page, ledger=local, task_alias=public["task_alias"])
            executor.navigate(shell.base_url + "/task/" + public["task_alias"], phase="replay_start")
            start_state = capture_state(page)
            replay_steps = []
            for idx, action in enumerate(source["actions"]):
                executor.execute(action, phase="replay_prefix")
                state = capture_state(page)
                replay_steps.append({"action": action, "observed_state": state,
                    "matches_source_result": canonical_state(state) == canonical_state(history[idx+1]["result_state"])})
            state = capture_state(page)
            shot = directory / "screenshots/restored.png"
            shot.parent.mkdir(parents=True)
            page.screenshot(path=str(shot), full_page=True)
            replay = {"steps": replay_steps,
                      "start_state_equal": canonical_state(start_state) == canonical_state(history[0]["result_state"]),
                      "state_equal": canonical_state(state) == canonical_state(source["state"]),
                      "screenshot_equal": file_sha256(shot) == file_sha256(source_dir / "first_selection.png"),
                      "restored_state": state, "executor_receipts": copy.deepcopy(executor.receipts)}
            write_json(directory / "replay.json", replay)
            if not (replay["start_state_equal"] and replay["state_equal"] and replay["screenshot_equal"] and all(s["matches_source_result"] for s in replay_steps)):
                raise ValueError("first-selection replay mismatch")
            if strategy == "H1+V":
                # Copy only a dashboard that the source actor really observed.
                dashboard = directory / "screenshots/dashboard.png"
                shutil.copy2(source_dir / "dashboard.png", dashboard)
                system, user = verification_prompt(public["user_goal"], visible_options(state))
                reply = model.call(phase="verification", system_prompt=system, user_prompt=user,
                    image_path=dashboard, image_artifact=dashboard.relative_to(root).as_posix(),
                    public_context={"user_goal": public["user_goal"], "visible_options": visible_options(state)},
                    request_dir=directory / "requests", response_dir=directory / "responses")
                parsed = _extract_object(reply.text)
                label = parsed.get("option_label")
                advice = {"raw_response": reply.text,
                          "parsed_option_label": label if isinstance(label, str) and label in visible_options(state) else None,
                          "parse_status": "valid" if isinstance(label, str) and label in visible_options(state) else "invalid"}
                write_json(directory / "verification.json", advice)
            while local.calls < 6:
                state = capture_state(page)
                image = directory / "screenshots" / f"actor_{len(events):02d}.png"
                page.screenshot(path=str(image), full_page=True)
                system, user = actor_prompt(public["user_goal"], state, history, strategy, advice)
                context = {"state": state, "user_goal": public["user_goal"]}
                if strategy != "H0":
                    context["executed_history"] = copy.deepcopy(history)
                if strategy == "H1+V":
                    context["verification_advice"] = advice
                reply = model.call(phase="actor", system_prompt=system, user_prompt=user,
                    image_path=image, image_artifact=image.relative_to(root).as_posix(), public_context=context,
                    request_dir=directory / "requests", response_dir=directory / "responses")
                action = _extract_action(reply.text)
                event = {"request_id": reply.metadata["request_id"], "raw_response": reply.text,
                         "parsed_action": action, "before_state": state, "executed": False}
                events.append(event)
                write_json(directory / "events.json", events)
                is_submit = is_submit_proposal(action, state)
                if action.get("action") in ("invalid", "finish"):
                    event["error"] = "invalid_model_action" if action["action"] == "invalid" else "finish_without_submission"
                    write_json(directory / "events.json", events)
                    if action["action"] == "finish":
                        result["status"] = "finish_without_submission"
                        break
                    continue
                error = ""
                try:
                    executor.execute(action, phase="actor_submit" if is_submit else "actor_action",
                                     max_attempts=1 if is_submit else None)
                    event["executed"] = True
                except Exception as exc:
                    error = str(exc)
                    event["error"] = error
                after = capture_state(page)
                event["after_state"] = after
                event["after_selection"] = current_selection(after)
                history.append({"action": action, "execution_succeeded": event["executed"], "result_state": after})
                write_json(directory / "events.json", events)
                receipts = read_jsonl(receipts_path) if receipts_path.exists() else []
                if is_submit or receipts:
                    result.update(status=("submitted" if len(receipts) == 1 and not error and after["url_path"].endswith("/confirmation")
                                          else "submission_error"), receipt_count=len(receipts),
                                  confirmation_observed=after["url_path"].endswith("/confirmation"))
                    break
            else:
                result["status"] = "model_call_limit"
            result["final_observed_state"] = capture_state(page)
            page.screenshot(path=str(directory / "screenshots/final.png"), full_page=True)
            result["executor_receipts"] = executor.receipts
    except Exception as exc:
        result.update(status="unit_error", error_type=type(exc).__name__, error=str(exc))
    finally:
        if executor is not None:
            result["executor_receipts"] = executor.receipts
        if page is not None:
            try:
                page.close()
            except Exception as exc:
                result["page_close_error"] = str(exc)
        result.update(model_calls=local.calls, browser_transitions=local.steps, events=events,
                      verification=advice, finished_at=utc_now())
    return result


def live(root, url):
    backend = LocalQwenServiceBackend(server_url=url, max_output_tokens=1024, temperature=0, top_p=1, seed=12345)
    if backend.health["model_path"] != MODEL_PATH or backend.health["max_pixels"] != 1003520:
        raise ValueError("unexpected local model configuration")
    with (root / "live_attempt.json").open("x") as stream:
        json.dump({"started_at": utc_now()}, stream)
    write_json(root / "model_metadata.json", backend.metadata)
    ledger = load_ledger(root)
    ledger.scope = "live"
    manifest = read(root / "manifest.json")
    infrastructure_error = ""
    try:
        with require_playwright()() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(BROWSER_LAUNCH_ARGS))
            try:
                for entry in manifest["units"]:
                    ledger.unit_id = entry["unit_id"]
                    directory = root / "units" / entry["unit_id"]
                    source_dir = root / "sources" / entry["source_episode"]
                    result = online_unit(browser, read(source_dir / "public_task.json"), read(source_dir / "state.json"),
                        source_dir, directory, root, entry["strategy"], backend, ledger)
                    write_json(directory / "result.json", {**entry, **result})
                    print(entry["unit_id"], entry["source_episode"], entry["strategy"], result["status"], result["model_calls"], flush=True)
            finally:
                browser.close()
    except Exception as exc:
        infrastructure_error = f"{type(exc).__name__}: {exc}"
    finally:
        # All scoring belongs after the online run, never the controller.
        for entry in manifest["units"]:
            directory = root / "units" / entry["unit_id"]
            source_dir = root / "sources" / entry["source_episode"]
            row = read(directory / "result.json")
            if row["status"] == "not_run":
                row["reason"] = infrastructure_error or "not_attempted"
                write_json(directory / "result.json", row)
            receipts = read_jsonl(directory / "post_receipts.jsonl") if (directory / "post_receipts.jsonl").exists() else []
            task = read(source_dir / "evaluator/task_spec.json")
            write_json(directory / "evaluator/terminal_score.json", {
                "actual_receipt_count": len(receipts), "score": score_receipt(task, receipts[0]) if len(receipts) == 1 else None})
        write_json(root / "execution_summary.json", {"finished_at": utc_now(),
            "rows": [read(root / "units" / e["unit_id"] / "result.json") for e in manifest["units"]],
            "budget": read(root / "budget.json")})
        attempt = read(root / "live_attempt.json")
        attempt.update(finished_at=utc_now(), status="infrastructure_failed" if infrastructure_error else "completed_all_units_attempted",
                       infrastructure_error=infrastructure_error)
        write_json(root / "live_attempt.json", attempt)


def browser_control(root):
    """Three explicit mock controls; public labels only, no research scoring."""
    base = root / "engineering_control"
    base.mkdir(exist_ok=False)
    ledger = load_ledger(root)
    ledger.scope = "mock_control"
    source_dir = root / "sources/episode_01"
    public, source = read(source_dir / "public_task.json"), read(source_dir / "state.json")
    labels = public["option_labels"]
    submit = {"action": "click_button", "text": "Submit Form"}
    def select(label):
        return {"action": "select_option", "select_name": public["primary_field_label"], "option_text": label}
    plans = {
        "H0": [submit],
        "H1": [select(labels[0]), submit],
        "H1+V": [{"option_label": labels[0], "reason": "scripted plumbing control, not visual judgment"},
                 select(labels[0]), select(source["actions"][-1]["option_text"]), submit],
    }
    class Backend:
        metadata = {"kind": "explicit_scripted_mock"}
        def __init__(self, actions):
            self.actions = iter(actions)
        def complete(self, request):
            return ModelReply(json.dumps(next(self.actions)), {"mock": True})
    results = []
    with require_playwright()() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(BROWSER_LAUNCH_ARGS))
        try:
            for i, strategy in enumerate(CONDITIONS, 1):
                ledger.unit_id = f"control_{i:02d}"
                directory = base / ledger.unit_id
                directory.mkdir()
                result = online_unit(browser, public, source, source_dir, directory, root, strategy,
                                     Backend(plans[strategy]), ledger)
                write_json(directory / "result.json", {"strategy": strategy, "mock_not_agent_evidence": True, **result})
                results.append(result)
        finally:
            browser.close()
    write_json(base / "summary.json", {"mock_not_agent_evidence": True, "rows": results})
    return all(r["status"] == "submitted" for r in results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "browser-control", "live"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-model-url", default="http://127.0.0.1:8047")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.output.resolve())
    elif args.command == "browser-control":
        if not browser_control(args.output.resolve()):
            raise SystemExit(1)
    else:
        live(args.output.resolve(), args.local_model_url)


if __name__ == "__main__":
    main()
