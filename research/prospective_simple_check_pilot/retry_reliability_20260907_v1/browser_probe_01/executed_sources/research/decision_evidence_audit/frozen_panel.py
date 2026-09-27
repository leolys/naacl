"""Run the user-approved, frozen synthetic panel; not natural benchmark recovery.

No service startup, GPU allocation, downloads, answer inference, or prompt tuning.
The old B3 policy is loaded from its saved source, with projection at every call.
"""
from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import json
import shutil
import sys
from pathlib import Path

from .core import (BudgetLedger, Checkpoint, append_jsonl, current_selection,
                   is_submit_proposal, visible_options, write_json)
from .models import LocalQwenServiceBackend, RecordedModel
from .runner import (BROWSER_LAUNCH_ARGS, BrowserExecutor, capture_state, managed_shell,
                     read_jsonl, require_playwright, run_multi_image_witness, utc_now)

ROOT = Path(__file__).resolve().parents[2]
PANEL = Path(__file__).resolve().parent / "revisions/20260906T145758Z_offline_panel"
BROWSER = Path("/tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def reference_policy(panel_dir=PANEL):
    name = "research.decision_evidence_audit._frozen_panel_b3_reference"
    source = panel_dir / "B3_REFERENCE.py"
    if name not in sys.modules or Path(sys.modules[name].__file__) != source:
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


class PanelLedger(BudgetLedger):
    """Reuse existing persistent budget; attach timestamps and unit ownership."""
    unit_id = "engineering"

    def _annotate(self):
        self.events[-1].update(timestamp=utc_now(), unit_id=self.unit_id)
        self._persist_snapshot()

    def charge_model(self, **kwargs):
        super().charge_model(**kwargs)
        self._annotate()

    def charge_transition(self, **kwargs):
        super().charge_transition(**kwargs)
        self._annotate()


def open_ledger(root):
    path = root / "budget.json"
    ledger = PanelLedger(**read(path)) if path.exists() else PanelLedger(
        max_model_calls=80, max_browser_transitions=200)
    if (ledger.max_model_calls, ledger.max_browser_transitions) != (80, 200):
        raise ValueError("panel budget must remain 80 calls / 200 transitions")
    ledger.bind_snapshot(path)
    return ledger


class ProjectedModel(RecordedModel):
    def __init__(self, backend, *, ledger, payload, events_path, panel_dir=PANEL):
        super().__init__(backend, ledger=ledger)
        self.payload = copy.deepcopy(payload)
        self.events_path = events_path
        self.panel_dir = panel_dir
        self.rounds = 0

    def call(self, **kwargs):
        original = kwargs["public_context"]
        projected = copy.deepcopy(original)
        # Immutable, pre-generated public evidence. Own verification responses
        # and tool feedback remain in subsequent rounds, not the initial choice.
        for key in ("user_goal", "visible_options", "current_selection",
                    "visible_action_prefix", "prior_agent_responses"):
            projected[key] = copy.deepcopy(self.payload["public_context"][key])
        if "diagnostic_color_fact" in self.payload["public_context"]:
            projected["diagnostic_color_fact"] = self.payload["public_context"]["diagnostic_color_fact"]
        old_json = json.dumps(original, ensure_ascii=False)
        if kwargs["user_prompt"].count(old_json) != 1:
            raise ValueError("reference context boundary not uniquely present")
        kwargs["user_prompt"] = kwargs["user_prompt"].replace(
            old_json, json.dumps(projected, ensure_ascii=False))
        kwargs["public_context"] = projected
        images, artifacts = list(kwargs["image_path"]), list(kwargs["image_artifact"])
        for index, alias in enumerate(self.payload["image_artifacts"]):
            if images[index].read_bytes() != (self.panel_dir / alias).read_bytes():
                raise ValueError("observed input differs from frozen panel image")
            target = kwargs["request_dir"].parent / alias
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(images[index], target)
            elif target.read_bytes() != images[index].read_bytes():
                raise ValueError("saved panel image mismatch")
            images[index], artifacts[index] = target, alias
        kwargs["image_path"], kwargs["image_artifact"] = images, artifacts
        if self.rounds == 0:
            actual = {key: kwargs[key] for key in ("system_prompt", "user_prompt", "public_context")}
            actual["image_artifacts"] = artifacts
            if actual != self.payload:
                raise ValueError("first request differs from frozen model_payload")
        self.rounds += 1
        append_jsonl(self.events_path, {"event": "model_attempt_started", "round": self.rounds,
                                      "timestamp": utc_now(), "phase": kwargs["phase"]})
        try:
            reply = super().call(**kwargs)
        except Exception as exc:
            append_jsonl(self.events_path, {"event": "model_attempt_failed", "round": self.rounds,
                "timestamp": utc_now(), "error_type": type(exc).__name__, "error": str(exc)})
            raise
        append_jsonl(self.events_path, {"event": "model_attempt_finished", "round": self.rounds,
            "timestamp": utc_now(), "request_id": reply.metadata["request_id"]})
        return reply


def fixture_checkpoint(payload, initial):
    context = payload["public_context"]
    return Checkpoint(
        checkpoint_version=1, task_alias="control", user_goal=context["user_goal"],
        visible_options=context["visible_options"], current_selection=initial, current_state={},
        current_screenshot=payload["image_artifacts"][0],
        observed_screenshots=[{"kind": "dashboard", "path": payload["image_artifacts"][1]}],
        visible_action_prefix=[{"action": "select_option", "select_name": "route", "option_text": initial}],
        model_context=[{"response": '{"action":"click_button","text":"Submit Form"}'}],
        pending_proposal={"action": "click_button", "text": "Submit Form"})


def public_fixture(payload):
    context = payload["public_context"]
    return dict(task_alias="control", page_title="Panel color routing",
                user_goal=context["user_goal"], chart_reference="Panel color routing",
                primary_field_label="Route", option_labels=context["visible_options"])


def logged_action(executor, root, *, phase, action=None, url=None):
    append_jsonl(root / "execution_events.jsonl", {"event": "action_started", "timestamp": utc_now(),
        "phase": phase, "action": action, "url": url})
    before = len(executor.receipts)
    try:
        if url is not None:
            return executor.navigate(url, phase=phase)
        # Retry accounting stays in the shared executor. POST is never retried.
        return executor.execute(action, phase=phase, max_attempts=1)
    finally:
        for receipt in executor.receipts[before:]:
            append_jsonl(root / "execution_events.jsonl", {
                "event": "action_finished", "timestamp": utc_now(), **receipt})


def prepare_browser(page, shell, public, initial, ledger, root, *, short=False):
    executor = BrowserExecutor(page, ledger=ledger, task_alias="control", max_attempts=1)
    url = f"{shell.base_url}/task/control" + ("/form" if short else "")
    logged_action(executor, root, phase="injected_state_start", url=url)
    if not short:
        for label in ("Open Dashboard", "Open Form"):
            logged_action(executor, root, phase="injected_prefix", action={"action": "click_link", "text": label})
    logged_action(executor, root, phase="injected_initial_selection", action={
        "action": "select_option", "select_name": "primary_action", "option_text": initial})
    state = capture_state(page)
    if visible_options(state) != public["option_labels"] or current_selection(state) != initial:
        raise RuntimeError("initial browser state / option order mismatch")
    if not is_submit_proposal({"action": "click_button", "text": "Submit Form"}, state):
        raise RuntimeError("business submit not available")
    write_json(root / "execution_before.json", state)
    page.screenshot(path=str(root / "execution_before.png"))
    return executor


def submit_decision(executor, label, initial, root, receipts):
    before = len(read_jsonl(receipts)) if receipts.exists() else 0
    if before:
        raise RuntimeError("submission existed before this unit's pending proposal")
    if label != initial:
        logged_action(executor, root, phase="revision", action={
            "action": "select_option", "select_name": "primary_action", "option_text": label})
    else:
        append_jsonl(root / "execution_events.jsonl", {"event": "keep_existing_selection",
            "timestamp": utc_now(), "option_label": label, "browser_transition": False})
    state = capture_state(executor.page)
    write_json(root / "execution_after_selection.json", state)
    if current_selection(state) != label:
        raise RuntimeError("recommended label != actual pre-submit selection")
    submit_error = None
    try:
        logged_action(executor, root, phase="business_submit", action={"action": "click_button", "text": "Submit Form"})
    except Exception as exc:
        # A POST could have committed before the browser raised. Read receipt,
        # never blindly re-send it. Preserve uncertainty and the original error.
        submit_error = f"{type(exc).__name__}: {exc}"
    rows = read_jsonl(receipts) if receipts.exists() else []
    confirmed = False
    terminal_errors = []
    try:
        confirmed = (executor.page.url.endswith("/confirmation")
                     and executor.page.get_by_role("heading", name="Submission received", exact=True).count() > 0)
    except Exception as exc:
        terminal_errors.append(f"confirmation: {type(exc).__name__}: {exc}")
    try:
        executor.page.screenshot(path=str(root / "execution_terminal.png"))
    except Exception as exc:
        terminal_errors.append(f"screenshot: {type(exc).__name__}: {exc}")
    return dict(status="submitted" if len(rows) == 1 and confirmed and submit_error is None else "execution_incomplete",
                selected_before_submit=current_selection(state), receipt_count=len(rows),
                receipt=rows[0] if len(rows) == 1 else None, confirmation_observed=confirmed,
                submit_error=submit_error, terminal_observation_errors=terminal_errors,
                executor_receipts=executor.receipts)


def close_page_preserving_result(page, result):
    if page is not None:
        try:
            page.close()
        except Exception as exc:
            result["page_cleanup_error"] = f"{type(exc).__name__}: {exc}"


def initialize(root):
    root.mkdir(parents=True, exist_ok=False)
    archive_inputs(root)
    panel = read(root / "frozen_inputs/control_panel.json")
    write_json(root / "run_manifest.json", {"created_at": utc_now(), "reference": str(PANEL),
        "panel_version": panel["version"], "authorization": "User: 好的我授权你真实运行 (2026-09-07)",
        "evaluation_type": "simulation_only_synthetic_injected_control_with_real_browser_submission",
        "natural_recovery": False, "model_calls_cap": 80, "browser_transitions_cap": 200,
        "scope": "24 frozen color units + one ordered-image witness + 8 browser engineering transitions",
        "gpu": "physical GPU0 only; must be free or separately confirmed dedicated service",
        "automatic_service_start": False})
    for unit in panel["units"]:
        write_json(root / "units" / unit["unit_id"] / "result.json", {
            **unit, "status": "not_run", "live_inference": False})
    open_ledger(root)


def archive_inputs(root):
    target = root / "frozen_inputs"
    target.mkdir(exist_ok=False)
    for name in ("control_panel.json", "panel_online_requests.json", "B3_REFERENCE.py",
                 "EXPERIMENT_PLAN.md", "CONTROL_FREEZE.md"):
        shutil.copy2(PANEL / name, target / name)
    shutil.copytree(PANEL / "panel_images", target / "panel_images")


def browser_controls(root):
    """Exactly 8 transitions, zero mock/real model calls; real label/POST checks."""
    directory = root / "browser_controls"
    directory.mkdir(exist_ok=False)
    ledger = open_ledger(root)
    panel_dir = root / "frozen_inputs"
    payloads = read(panel_dir / "panel_online_requests.json")
    rows = []
    with require_playwright()() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(BROWSER_LAUNCH_ARGS))
        try:
            # Both orders and both mapping directions, without consulting gold.
            for number, state_id, initial, target in (
                (1, "state_01", "Route A", "Route B"), (2, "state_05", "Route B", "Route A")):
                unit = directory / f"check_{number:02d}"
                unit.mkdir()
                payload = next(row["model_payload"] for row in payloads if row["state_id"] == state_id)
                ledger.unit_id = f"engineering_{number}"
                receipts = unit / "post_receipts.jsonl"
                public = public_fixture(payload)
                with managed_shell(public, panel_dir / payload["image_artifacts"][1], receipts) as shell:
                    page = browser.new_page(viewport={"width": 1440, "height": 1100})
                    try:
                        executor = prepare_browser(page, shell, public, initial, ledger, unit, short=True)
                        result = submit_decision(executor, target, initial, unit, receipts)
                        result["injected_target_not_model_decision"] = target
                        result["passed"] = (result["status"] == "submitted" and result["receipt"]["selected_option_label"] == target)
                        write_json(unit / "result.json", result)
                        rows.append(result)
                    finally:
                        page.close()
        finally:
            browser.close()
            write_json(directory / "summary.json", {"cases": rows, "model_calls": 0,
                "browser_transitions": sum(e["kind"] == "browser_transition" and e.get("unit_id", "").startswith("engineering_") for e in ledger.events),
                "passed": len(rows) == 2 and all(r["passed"] for r in rows)})
    return len(rows) == 2 and all(r["passed"] for r in rows)


def _run_live(root, server_url):
    snapshot_sources(root)
    ledger = open_ledger(root)
    backend = LocalQwenServiceBackend(server_url=server_url, model_name="Qwen3-VL-8B-Instruct",
                                     max_output_tokens=1024, temperature=0, top_p=1, seed=12345)
    write_json(root / "model.json", backend.metadata)
    if (Path(str(backend.health.get("model_path", ""))).name != "Qwen3-VL-8B-Instruct"
            or backend.health.get("model_size") != "8b"
            or backend.health.get("max_pixels") != 1003520
            or backend.health.get("native_multi_image") is not True):
        raise RuntimeError("running service does not match the frozen model/image configuration")
    panel_dir = root / "frozen_inputs"
    panel = read(panel_dir / "control_panel.json")
    payloads = {row["unit_id"]: row["model_payload"] for row in read(panel_dir / "panel_online_requests.json")}
    initial_choices = {row["state_id"]: row["initial_selection"] for row in panel["states"]}
    ledger.unit_id = "ordered_image_witness"
    witness = run_multi_image_witness(model=RecordedModel(backend, ledger=ledger), run_root=root, seed=12345)
    if witness["status"] != "passed":
        raise RuntimeError("ordered-image witness failed; see online/preflight_witness/result.json")
    policy = reference_policy(panel_dir)
    with require_playwright()() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(BROWSER_LAUNCH_ARGS))
        try:
            for state_id in panel["execution_state_order"]:
                for entry in (u for u in panel["units"] if u["state_id"] == state_id):
                    unit = root / "units" / entry["unit_id"]
                    ledger.unit_id = entry["unit_id"]
                    initial, payload = initial_choices[state_id], payloads[entry["unit_id"]]
                    result = {**entry, "status": "started", "started_at": utc_now(),
                              "live_inference": False, "injected_initial_selection": initial}
                    write_json(unit / "result.json", result)
                    calls_before, steps_before = ledger.model_calls, ledger.browser_transitions
                    page = None
                    try:
                        receipts = unit / "post_receipts.jsonl"
                        public = public_fixture(payload)
                        with managed_shell(public, panel_dir / payload["image_artifacts"][1], receipts) as shell:
                            page = browser.new_page(viewport={"width": 1440, "height": 1100})
                            executor = prepare_browser(page, shell, public, initial, ledger, unit)
                            cp = fixture_checkpoint(payload, initial)
                            write_json(unit / "injected_checkpoint.json", cp.to_dict())
                            model = ProjectedModel(backend, ledger=ledger, payload=payload,
                                                   events_path=unit / "model_events.jsonl", panel_dir=panel_dir)
                            decision = policy.run_policy("B3", cp, model=model, artifact_root=panel_dir, unit_dir=unit / "policy")
                            result["policy"] = decision.to_dict()
                            write_json(unit / "policy_result.json", result["policy"])
                            if decision.recommended_option not in cp.visible_options:
                                raise RuntimeError("policy output is not an executable visible label")
                            result.update(submit_decision(executor, decision.recommended_option, initial, unit, receipts))
                    except Exception as exc:
                        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
                        # Preserve partial evidence and retain ALL unstarted rows.
                        result["execution_events_path"] = "execution_events.jsonl"
                    finally:
                        close_page_preserving_result(page, result)
                        result.update(finished_at=utc_now(), model_calls=ledger.model_calls-calls_before,
                                      browser_transitions=ledger.browser_transitions-steps_before,
                                      live_inference=ledger.model_calls > calls_before)
                        write_json(unit / "result.json", result)
                        print(entry["unit_id"], entry["mode"], result["status"], flush=True)
                    # Stop on infrastructure/interface conflict, not semantic failure.
                    if result["status"] != "submitted":
                        return False
        finally:
            browser.close()
    return True


def run_live(root, server_url):
    # One attempt, no crash-resume stitching. All global errors and pending rows
    # retain a cause; raw POST and model records remain independently available.
    path = root / "live_attempt.json"
    result = {"started_at": utc_now(), "server_url": server_url, "status": "started"}
    with path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream)
    try:
        success = _run_live(root, server_url)
        result["status"] = "completed" if success else "stopped_on_unit_infrastructure_failure"
    except Exception as exc:
        success = False
        result.update(status="infrastructure_failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        result["finished_at"] = utc_now()
        write_json(path, result)
        for file in (root / "units").glob("*/result.json"):
            unit = read(file)
            if unit["status"] == "not_run":
                unit["not_run_reason"] = result.get("error", result["status"])
                write_json(file, unit)
        summarize(root)
    return success


def summarize(root):
    """Offline only: constructed fixture answers never feed policy/executor."""
    panel_dir = root / "frozen_inputs"
    panel = read(panel_dir / "control_panel.json")
    states = {s["state_id"]: s for s in panel["states"]}
    rows = []
    for state_id in panel["execution_state_order"]:
        for entry in (u for u in panel["units"] if u["state_id"] == state_id):
            result = read(root / "units" / entry["unit_id"] / "result.json")
            policy = result.get("policy", {})
            raw = next((r["response"] for r in reversed(policy.get("records", [])) if "response" in r), None)
            if raw is None:
                response_files = sorted((root / "units" / entry["unit_id"] / "policy/responses").glob("*.json"))
                if response_files:
                    last_response = read(response_files[-1])
                    raw = last_response.get("text") if last_response.get("ok") else None
            kind, parsed, _ = reference_policy(panel_dir)._b3_output(raw) if raw is not None else (None, {}, "")
            receipt = result.get("receipt") or {}
            expected = states[state_id]["expected_option_offline_only"]
            label = parsed.get("option_label") if kind == "decision" else None
            row = dict(unit_id=entry["unit_id"], state_id=state_id, mode=entry["mode"],
                status=result["status"], initial_selection=states[state_id]["initial_selection"],
                expected_option_offline_only=expected, raw_response=raw, raw_label=label,
                parse_status=policy.get("parse_status"), reason=parsed.get("reason"),
                recommended_option=policy.get("recommended_option"),
                submitted_option=receipt.get("selected_option_label"),
                confirmation_observed=result.get("confirmation_observed"),
                valid_decision_correct=(label == expected) if policy.get("parse_status") == "valid" else None,
                submitted_correct=(receipt.get("selected_option_label") == expected) if receipt else None,
                model_calls=result.get("model_calls", 0), browser_transitions=result.get("browser_transitions", 0),
                active_observations=policy.get("active_observations"),
                attribution=("requires_raw_evidence_review_not_inferred_from_reason" if raw is not None else
                             "attempted_no_raw_response" if result.get("model_calls", 0) > 0 else
                             "not_run" if result["status"] == "not_run" else "pre_inference_failure"),
                error=result.get("error"), not_run_reason=result.get("not_run_reason"))
            rows.append(row)
    output = root / "evaluator"
    write_json(output / "unit_results.json", rows)
    with (output / "unit_results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    budget = read(root / "budget.json")
    summary = {"evaluation_type": "simulation_only", "configured_units": 24,
        "units_with_model_calls": sum(r["model_calls"] > 0 for r in rows),
        "submitted_units": sum(r["status"] == "submitted" for r in rows),
        "not_run_units": sum(r["status"] == "not_run" for r in rows),
        "budget": budget, "rows": rows, "natural_benchmark_recovery_claim": False}
    write_json(root / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"budget", "rows"}}, ensure_ascii=False))


def snapshot_sources(root):
    """Ordinary source copies; no new hashing scheme or project-wide contract."""
    paths = [Path(__file__), PANEL / "B3_REFERENCE.py"]
    paths += [Path(__file__).parent / f"{name}.py" for name in ("core", "models", "runner", "safe_shell")]
    paths += [ROOT / "adversarial_pipeline/llm_client.py", ROOT / "web_agent_benchmark/evaluation/qwen3_vl_server.py"]
    for path in paths:
        target = root / "executed_sources" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        shutil.copy2(path, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "archive-inputs", "browser-controls", "live", "summarize"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-model-url", default="http://127.0.0.1:8045")
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == "prepare":
        initialize(root)
        return 0
    if not (root / "run_manifest.json").is_file():
        parser.error("prepare a fresh directory first")
    if args.command == "archive-inputs":
        archive_inputs(root)
        return 0
    if args.command == "browser-controls":
        return 0 if browser_controls(root) else 1
    if args.command == "summarize":
        summarize(root)
        return 0
    return 0 if run_live(root, args.local_model_url) else 1


if __name__ == "__main__":
    raise SystemExit(main())
