"""Seven-candidate webpage qualification, zero model calls and no GPU service.

Scripted option exercise is an engineering check, never an agent prediction.
Original release tasks/images and the shared runner are not modified.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from .core import BudgetExceeded, BudgetLedger, current_selection, visible_options, write_json
from .runner import (BROWSER_LAUNCH_ARGS, BrowserExecutor, capture_state, find_task,
                     managed_shell, pair_invariant_differences, read_jsonl,
                     require_playwright, task_spec_path, utc_now)
from .safe_shell import build_shell_bundle, score_receipt

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ("b003", "b011", "b012", "env003", "env004", "env027", "pub030")
CONDITIONS = ("official140", "clean140")
BROWSER = Path("/tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell")
PRIOR = Path(__file__).parent / "revisions/20260906T145758Z_offline_panel/asset_review"
SENSITIVE_TERMS = ("expected_action_id", "misleading_action_ids", "ground_truth", "correct_value",
                   "misleader_type", "task_readiness", "official140", "clean140", "figure_path")


class QualificationLedger(BudgetLedger):
    unit_id = "startup"

    def charge_transition(self, *, phase, action):
        used = sum(e.get("unit_id") == self.unit_id for e in self.events)
        if used >= 8:
            raise BudgetExceeded(f"per-unit transition limit exhausted: {self.unit_id}")
        super().charge_transition(phase=phase, action=action)
        self.events[-1].update(unit_id=self.unit_id, timestamp=utc_now())
        self._persist_snapshot()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def option_exercise(public, index):
    """Rotate public option order; selection plan cannot depend on hidden answers."""
    labels = list(public["option_labels"])
    offset = index % len(labels)
    return labels[offset:] + labels[:offset]


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    manifest = {"created_at": utc_now(), "candidates": list(CANDIDATES),
        "conditions": list(CONDITIONS), "model_calls_authorized": 0,
        "browser_transition_cap": 112, "per_unit_transition_cap": 8,
        "viewport": {"width": 1440, "height": 1100}, "device_scale_factor": 1,
        "selection": "Exercise every public label in rotated order; submit the last label.",
        "semantic_agent_results": "not_run", "qualification": "safe_shell_adapter_not_native_full_portal"}
    write_json(root / "run_manifest.json", manifest)
    for index, slug in enumerate(CANDIDATES):
        for condition in CONDITIONS:
            uid = f"{slug}_{condition}"
            write_json(root / "units" / uid / "result.json", {
                "unit_id": uid, "task_slug": slug, "condition": condition,
                "status": "not_run", "model_calls": 0, "browser_transitions": 0})
    (root / "source").mkdir(exist_ok=True)
    for name in ("web_qualification.py", "core.py", "runner.py", "safe_shell.py"):
        shutil.copy2(Path(__file__).parent / name, root / "source" / name)
    shutil.copy2(PRIOR / "proposed_split.json", root / "source/prior_proposed_split.json")
    pairs = []
    for index, slug in enumerate(CANDIDATES):
        raw_pair = []
        for condition in CONDITIONS:
            unit = root / "units" / f"{slug}_{condition}"
            raw = find_task(task_spec_path(condition, slug), slug)
            raw_pair.append(raw)
            bundle = build_shell_bundle(raw, task_alias=f"q{index+1:02d}", repository_root=ROOT)
            write_json(unit / "evaluator/task_spec.json", raw)
            write_json(unit / "public_task.json", bundle.public_task)
            write_json(unit / "execution_plan.json", {"scripted_not_model": True,
                "option_exercise": option_exercise(bundle.public_task, index)})
            shutil.copy2(bundle.chart_path, unit / ("chart_original" + bundle.chart_path.suffix))
            write_json(unit / "evaluator/source.json", {"spec": str(task_spec_path(condition, slug)),
                "chart_path": str(bundle.chart_path), "task_readiness": raw.get("task_readiness", "legacy_unspecified"),
                "hidden_companions": [c.get("field_id") for c in raw.get("companion_actions", []) if c.get("input_type") == "hidden"]})
        pairs.append({"task_slug": slug, "nonchart_field_differences": pair_invariant_differences(*raw_pair)})
    write_json(root / "pair_field_checks.json", pairs)
    ledger = QualificationLedger(max_model_calls=0, max_browser_transitions=112)
    ledger.bind_snapshot(root / "budget.json")


def capture(page, unit, name):
    """Normal viewport is the measurement; full-page capture is offline supplement."""
    state = capture_state(page)
    write_json(unit / f"{name}_state.json", state)
    (unit / f"{name}.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(unit / f"{name}_viewport.png"))
    page.screenshot(path=str(unit / f"{name}_fullpage.png"), full_page=True)
    geometry = page.locator("img.chart").evaluate_all("""els => els.map(el => {
      const r=el.getBoundingClientRect(); const st=getComputedStyle(el);
      return {src_path:new URL(el.src).pathname, complete:el.complete,
        natural_width:el.naturalWidth,natural_height:el.naturalHeight,
        rect:{x:r.x,y:r.y,width:r.width,height:r.height}, object_fit:st.objectFit,
        viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY}};
    })""")
    write_json(unit / f"{name}_geometry.json", geometry)
    return state


def run_unit(root, slug, condition, index, browser, ledger):
    uid = f"{slug}_{condition}"
    unit = root / "units" / uid
    result = read(unit / "result.json")
    result.update(status="started", started_at=utc_now())
    write_json(unit / "result.json", result)
    public = read(unit / "public_task.json")
    plan = read(unit / "execution_plan.json")["option_exercise"]
    chart = next(unit.glob("chart_original.*"))
    ledger.unit_id = uid
    before = ledger.browser_transitions
    context = None
    executor = None
    resource_rows = []
    chart_responses = []
    try:
        with managed_shell(public, chart, unit / "post_receipts.jsonl") as shell:
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
            page = context.new_page()
            def response_log(response):
                path = urlsplit(response.url).path
                row = {"path": path, "status": response.status, "method": response.request.method}
                if path.endswith("/chart") and response.status == 200:
                    row["body_matches_original"] = response.body() == chart.read_bytes()
                    chart_responses.append(row)
                resource_rows.append(row)
            page.on("response", response_log)
            executor = BrowserExecutor(page, ledger=ledger, task_alias=public["task_alias"], max_attempts=1)
            executor.navigate(f"{shell.base_url}/task/{public['task_alias']}", phase="task")
            capture(page, unit, "task")
            executor.execute({"action":"click_link","text":"Open Dashboard"}, phase="dashboard")
            capture(page, unit, "dashboard")
            executor.execute({"action":"click_link","text":"Open Form"}, phase="form")
            state = capture(page, unit, "form")
            result["visible_options_match"] = visible_options(state) == public["option_labels"]
            if not result["visible_options_match"]:
                raise RuntimeError("rendered options differ from public projection")
            selections = []
            for label in plan:
                executor.execute({"action":"select_option","select_name":"primary_action","option_text":label}, phase="option_mapping")
                actual = current_selection(capture_state(page))
                selections.append({"requested": label, "observed": actual, "matched": actual == label})
                write_json(unit / "selection_checks.json", selections)
            capture(page, unit, "before_submit")
            # Exactly one POST. If acknowledgement fails, preserve any receipt below.
            result["scripted_submitted_label"] = plan[-1]
            executor.execute({"action":"click_button","text":"Submit Form"}, phase="submit")
            result["confirmation_observed"] = page.url.endswith("/confirmation") and page.get_by_role("heading", name="Submission received", exact=True).count() > 0
            capture(page, unit, "confirmation")
            result["status"] = "submitted" if result["confirmation_observed"] else "confirmation_missing"
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        if context is not None:
            try:
                context.close()
            except Exception as exc:
                result["cleanup_error"] = str(exc)
        receipts = read_jsonl(unit / "post_receipts.jsonl") if (unit / "post_receipts.jsonl").exists() else []
        result.update(finished_at=utc_now(), browser_transitions=ledger.browser_transitions-before,
            receipt_count=len(receipts), receipt=receipts[0] if len(receipts)==1 else None,
            chart_transport_matches=bool(chart_responses) and all(r["body_matches_original"] for r in chart_responses))
        result["receipt_matches_scripted_label"] = len(receipts)==1 and receipts[0]["selected_option_label"] == result.get("scripted_submitted_label")
        write_json(unit / "browser_actions.json", executor.receipts if executor else [])
        write_json(unit / "network.json", resource_rows)
        surfaces = {p.name:p.read_text(encoding="utf-8") for p in unit.glob("*.html")}
        surfaces.update({p.name:p.read_text(encoding="utf-8") for p in unit.glob("*_state.json")})
        surfaces["network_paths"] = json.dumps(resource_rows)
        result["surface_key_or_condition_hits"] = [
            {"surface":name,"term":term} for name,content in surfaces.items()
            for term in SENSITIVE_TERMS if term.casefold() in content.casefold()]
        write_json(unit / "result.json", result)
        # Evaluator is used only after browser execution is complete.
        raw = read(unit / "evaluator/task_spec.json")
        write_json(unit / "evaluator/terminal_score.json", {"source": "actual_receipt_scripted_selection_not_agent", "score": score_receipt(raw, receipts[0]) if len(receipts)==1 else None})
        write_json(unit / "evaluator/offline_label_lookup.json", [{"label":label,
            "action_ids":[a["action_id"] for a in raw["action_space"] if a["label"]==label],
            "lookup_not_browser_submission":score_receipt(raw,{"selected_option_label":label})} for label in public["option_labels"]])
    print(uid, result["status"], result["browser_transitions"], flush=True)


def run(root):
    attempt = {"started_at": utc_now(), "status": "started"}
    with (root / "run_attempt.json").open("x") as stream:
        json.dump(attempt, stream)
    ledger_data = read(root / "budget.json")
    ledger = QualificationLedger(**ledger_data)
    ledger.bind_snapshot(root / "budget.json")
    try:
        with require_playwright()() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(BROWSER_LAUNCH_ARGS))
            try:
                for index, slug in enumerate(CANDIDATES):
                    for condition in CONDITIONS:
                        run_unit(root, slug, condition, index, browser, ledger)
            finally:
                browser.close()
        attempt["status"] = "completed_all_units_attempted"
    except Exception as exc:
        attempt.update(status="infrastructure_failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        attempt["finished_at"] = utc_now()
        write_json(root / "run_attempt.json", attempt)
        rows = []
        for slug in CANDIDATES:
            for condition in CONDITIONS:
                path = root / "units" / f"{slug}_{condition}" / "result.json"
                row = read(path)
                if row["status"] == "not_run":
                    row["reason"] = attempt.get("error", attempt["status"])
                    write_json(path, row)
                rows.append(row)
        summary = {"evaluation_type":"simulation_only", "scripted_web_qualification":True,
            "base_tasks":7, "configured_units":14, "submitted":sum(r["status"]=="submitted" for r in rows),
            "model_calls":ledger.model_calls, "browser_transitions":ledger.browser_transitions,
            "visual_qualification":"requires_researcher_screenshot_review", "rows":rows}
        write_json(root / "execution_summary.json", summary)
        print(json.dumps({k:v for k,v in summary.items() if k!="rows"}), flush=True)
    return all(r["status"] == "submitted" for r in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == "prepare":
        prepare(root)
        return 0
    return 0 if run(root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
