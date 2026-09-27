"""Four natural prefixes followed only by unchanged B0 submission.

Reuses the existing agent, hook, replay and executor without changing their
prompts or allowing a strategy grid. Preparation/evaluation stay offline.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .core import BudgetLedger, write_json
from .models import LocalQwenServiceBackend, RecordedModel, ScriptedMockBackend
from .runner import (BROWSER_LAUNCH_ARGS, find_task, generate_checkpoint,
                     managed_shell, pair_invariant_differences, read_jsonl,
                     replay_and_run_unit, require_playwright, task_spec_path, utc_now)
from .safe_shell import build_shell_bundle, score_receipt

ROOT = Path(__file__).resolve().parents[2]
TASKS = ("b011", "env027")
ORDER = (("b011", "official140"), ("b011", "clean140"),
         ("env027", "clean140"), ("env027", "official140"))
BROWSER = Path("/tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell")
MODEL_PATH = "/hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct"
PREFIX_CALL_CAP = 8  # 4 prefixes <=32 + 4 charged mock-control calls <=40.


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def unit_directory(root, task, condition):
    # Image artifact paths are recorded as public request metadata. Keep those
    # paths neutral as well as the actual model-visible text and pixels.
    return root / "units" / f"episode_{ORDER.index((task, condition))+1:02d}"


class RunLedger(BudgetLedger):
    scope = "unassigned"
    unit_id = "startup"

    def _annotate(self):
        self.events[-1].update(scope=self.scope, unit_id=self.unit_id, timestamp=utc_now())
        self._persist_snapshot()

    def charge_model(self, *, phase, request_id):
        super().charge_model(phase=phase, request_id=request_id)
        self._annotate()

    def charge_transition(self, *, phase, action):
        super().charge_transition(phase=phase, action=action)
        self._annotate()


def load_ledger(root):
    ledger = RunLedger(**read(root / "budget.json"))
    ledger.bind_snapshot(root / "budget.json")
    return ledger


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "run_manifest.json", {
        "created_at": utc_now(), "base_tasks": list(TASKS),
        "order": [{"task": t, "condition": c} for t, c in ORDER],
        "configured_units": 4, "strategy": "B0", "prefix_model_call_cap": PREFIX_CALL_CAP,
        "max_model_calls_including_mock_control": 40, "max_browser_transitions": 160,
        "viewport": {"width": 1440, "height": 1100}, "screenshots": "existing runner full_page=True",
        "agent_context": "existing prefix_prompt: current visible state and one current screenshot only; no multi-turn history replay to the prefix model",
        "checkpoint_history": "all prior observed screenshots, public actions and raw replies saved, not claimed to be all supplied to each prefix request",
        "model_plan": {"model_path": MODEL_PATH, "temperature": 0.0, "top_p": 1.0,
                       "seed": 12345, "max_output_tokens": 1024, "max_pixels": 1003520},
        "evaluation_scope": "release-spec primary-routing safe-shell adaptation, development only",
        "no_reason_or_gold_option_override": True, "no_strategy_grid": True,
    })
    for slug, condition in ORDER:
        uid = f"{slug}_{condition}"
        write_json(unit_directory(root, slug, condition) / "result.json", {
            "unit_id": uid, "task_slug": slug, "condition": condition,
            "status": "not_run", "reason": "pending_authorized_service",
            "checkpoint_reached": False, "real_model_calls": 0, "browser_transitions": 0})
    pairs = []
    for index, slug in enumerate(TASKS):
        raw_pair = []
        for condition in ("official140", "clean140"):
            raw = find_task(task_spec_path(condition, slug), slug)
            raw_pair.append(raw)
            unit = unit_directory(root, slug, condition)
            bundle = build_shell_bundle(raw, task_alias=f"n{index+1:02d}", repository_root=ROOT)
            write_json(unit / "evaluator/task_spec.json", raw)
            write_json(unit / "public_task.json", bundle.public_task)
            shutil.copy2(bundle.chart_path, unit / ("chart_original" + bundle.chart_path.suffix))
        differences = pair_invariant_differences(*raw_pair)
        pairs.append({"task": slug, "nonchart_differences": differences})
    write_json(root / "pair_checks.json", pairs)
    if any(p["nonchart_differences"] for p in pairs):
        raise ValueError("non-chart fields differ; prepared rows retained, no model execution")
    source = root / "source"
    source.mkdir()
    for name in ("natural_prefix.py", "runner.py", "core.py", "models.py", "safe_shell.py", "policies.py"):
        shutil.copy2(Path(__file__).parent / name, source / name)
    for relative in ("adversarial_pipeline/llm_client.py", "web_agent_benchmark/evaluation/qwen3_vl_server.py"):
        shutil.copy2(ROOT / relative, source / Path(relative).name)
    ledger = RunLedger(max_model_calls=40, max_browser_transitions=160)
    ledger.bind_snapshot(root / "budget.json")
    summarize(root)


def online_episode(*, browser, public, chart, root, directory, model, ledger):
    """No raw task, scorer or paired arm is an argument to online control."""
    directory.mkdir(parents=True, exist_ok=True)
    receipts_path = directory / "post_receipts.jsonl"
    with managed_shell(public, chart, receipts_path) as shell:
        checkpoint, prefix = generate_checkpoint(
            browser=browser, base_url=shell.base_url, task_alias=public["task_alias"],
            user_goal=public["user_goal"], model=model, ledger=ledger, run_root=root,
            prefix_dir=directory / "prefix", submission_path=receipts_path,
            max_model_calls=PREFIX_CALL_CAP)
        if checkpoint is None:
            return {"status": "no_checkpoint", "checkpoint_reached": False,
                    "prefix_errors": prefix["errors"]}
        continuation, _ = replay_and_run_unit(
            browser=browser, base_url=shell.base_url, task_alias=public["task_alias"],
            checkpoint=checkpoint, strategy="B0", model=model, ledger=ledger,
            run_root=root, unit_dir=directory / "B0", submission_path=receipts_path)
        return {"status": continuation["status"], "checkpoint_reached": True,
                "prefix_errors": prefix["errors"],
                "checkpoint_selection": checkpoint.current_selection,
                "pending_proposal": checkpoint.pending_proposal,
                "continuation": continuation}


def summarize(root):
    rows = [read(unit_directory(root, t, c) / "result.json") for t, c in ORDER]
    budget = read(root / "budget.json")
    events = budget["events"]
    result = {
        "evaluation_type": "simulation_only", "configured_units": 4,
        "real_model_status": "attempted" if any(r["status"] != "not_run" for r in rows) else "not_run",
        "checkpoint_count": sum(r["checkpoint_reached"] for r in rows),
        "submitted": sum(r["status"] == "submitted" for r in rows),
        "real_model_calls": sum(e["kind"] == "model_call" and e.get("scope") == "live" for e in events),
        "mock_control_calls": sum(e["kind"] == "model_call" and e.get("scope") == "mock_control" for e in events),
        "total_charged_model_events": budget["model_calls"],
        "browser_transitions": budget["browser_transitions"], "rows": rows,
    }
    write_json(root / "execution_summary.json", result)
    return result


def browser_control(root):
    """One visibly labelled mock control; separate from the four live rows."""
    control = root / "engineering_control"
    control.mkdir(exist_ok=False)
    ledger = load_ledger(root)
    ledger.scope, ledger.unit_id = "mock_control", "engineering_control"
    model = RecordedModel(ScriptedMockBackend(), ledger=ledger)
    source_unit = unit_directory(root, "b011", "official140")
    result = {"status": "not_run", "mock_not_agent_evidence": True}
    try:
        with require_playwright()() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(BROWSER_LAUNCH_ARGS))
            try:
                result.update(online_episode(browser=browser, public=read(source_unit / "public_task.json"),
                    chart=next(source_unit.glob("chart_original.*")), root=root, directory=control,
                    model=model, ledger=ledger))
            finally:
                browser.close()
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        write_json(control / "result.json", result)
        summarize(root)
    return result["status"] == "submitted"


def live(root, server_url):
    # Failed readiness checks spend no inference and do not consume a live run.
    # Preserve each check; the actual live attempt is created once below.
    probes = root / "service_checks"
    probes.mkdir(exist_ok=True)
    probe_path = probes / f"check_{len(list(probes.glob('check_*.json')))+1:03d}.json"
    try:
        backend = LocalQwenServiceBackend(server_url=server_url, max_output_tokens=1024,
            temperature=0.0, top_p=1.0, seed=12345)
        if backend.health.get("model_path") != MODEL_PATH or backend.health.get("max_pixels") != 1003520:
            raise ValueError("service model path or image budget differs from planned existing Qwen setup")
    except Exception as exc:
        probe = {"time": utc_now(), "status": "unavailable", "error_type": type(exc).__name__, "error": str(exc)}
        write_json(probe_path, probe)
        for t, c in ORDER:
            path = unit_directory(root, t, c) / "result.json"
            row = read(path)
            if row["status"] == "not_run":
                row["reason"] = "no_available_authorized_local_model_service"
                write_json(path, row)
        summarize(root)
        return False
    write_json(probe_path, {"time": utc_now(), "status": "available", "metadata": backend.metadata})
    with (root / "live_attempt.json").open("x") as stream:
        json.dump({"started_at": utc_now(), "status": "started"}, stream)
    ledger = load_ledger(root)
    ledger.scope = "live"
    model = RecordedModel(backend, ledger=ledger)
    write_json(root / "model_metadata.json", model.metadata)
    infrastructure_error = ""
    try:
        with require_playwright()() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(BROWSER_LAUNCH_ARGS))
            try:
                for slug, condition in ORDER:
                    uid = f"{slug}_{condition}"
                    directory = unit_directory(root, slug, condition)
                    row = read(directory / "result.json")
                    before_calls, before_steps = ledger.model_calls, ledger.browser_transitions
                    ledger.unit_id = uid
                    row.update(status="started", reason="", started_at=utc_now())
                    write_json(directory / "result.json", row)
                    try:
                        row.update(online_episode(browser=browser, public=read(directory / "public_task.json"),
                            chart=next(directory.glob("chart_original.*")), root=root,
                            directory=directory, model=model, ledger=ledger))
                    except Exception as exc:
                        row.update(status="unit_error", error_type=type(exc).__name__, error=str(exc))
                    finally:
                        row.update(real_model_calls=ledger.model_calls-before_calls,
                            browser_transitions=ledger.browser_transitions-before_steps, finished_at=utc_now())
                        write_json(directory / "result.json", row)
                        summarize(root)
                    print(uid, row["status"], row["real_model_calls"], flush=True)
            finally:
                browser.close()
    except Exception as exc:
        infrastructure_error = f"{type(exc).__name__}: {exc}"
    finally:
        attempt = read(root / "live_attempt.json")
        attempt.update(finished_at=utc_now(), status="infrastructure_failed" if infrastructure_error else "completed_all_units_attempted",
                       infrastructure_error=infrastructure_error)
        write_json(root / "live_attempt.json", attempt)
        # Evaluation only after every online unit has finished or been skipped.
        for t, c in ORDER:
            directory = unit_directory(root, t, c)
            row = read(directory / "result.json")
            if row["status"] == "not_run":
                row["reason"] = infrastructure_error or "not_attempted"
                write_json(directory / "result.json", row)
            receipts = read_jsonl(directory / "post_receipts.jsonl") if (directory / "post_receipts.jsonl").exists() else []
            raw = read(directory / "evaluator/task_spec.json")
            write_json(directory / "evaluator/terminal_score.json", {"actual_receipt_count": len(receipts),
                "score": score_receipt(raw, receipts[0]) if len(receipts) == 1 else None})
        result = summarize(root)
    return result["submitted"] == 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "browser-control", "live"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-model-url", default="http://127.0.0.1:8045")
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == "prepare":
        prepare(root)
        return 0
    return 0 if (browser_control(root) if args.command == "browser-control" else live(root, args.local_model_url)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
