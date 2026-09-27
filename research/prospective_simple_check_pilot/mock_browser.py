"""Non-chart engineering fixtures ONLY; no benchmark tasks, GPU, or API service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from research.decision_evidence_audit import core, models, runner
from .harness import capture_pending, restore, run_branch, TransitionScope


class RouteMock:
    def __init__(self, *, initial_wrong=False, overwrite_check=False, crop=False, never_submit=False):
        self.initial_wrong, self.overwrite_check = initial_wrong, overwrite_check
        self.crop, self.never_submit = crop, never_submit
    @property
    def metadata(self):
        return dict(kind="scripted_nonchart_mock", research_result=False)
    def complete(self, request):
        ctx = request.public_context
        if request.phase.startswith("b2_") or request.phase.startswith("b3_"):
            if request.phase == "b3_plan" and self.crop:
                decision = dict(observe=dict(screenshot_id="dashboard", region=[0, 0, 90, 80], reason="fixture tool invocation"))
            else:
                decision = dict(option_label="Route A", reason="synthetic public task says Route A")
        else:
            state = ctx["state"]
            links = [x["text"] for x in state["links"]]
            if "Open Dashboard" in links:
                decision = dict(action="click_link", text="Open Dashboard")
            elif "Open Form" in links:
                decision = dict(action="click_link", text="Open Form")
            else:
                goal = "Route B" if "Route B" in ctx["user_goal"] else "Route A"
                if request.phase == "prefix" and self.initial_wrong:
                    goal = "Route B"
                if request.phase == "actor_continuation" and self.overwrite_check:
                    goal = "Route B"
                if self.never_submit:
                    goal = "Route B" if ctx["current_selection"] == "Route A" else "Route A"
                if ctx["current_selection"] != goal:
                    decision = dict(action="select_option", select_name="primary_action", option_text=goal)
                else:
                    decision = dict(action="click_button", text="Submit Form")
        return models.ModelReply(json.dumps(decision), dict(mock=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    ledger = core.BudgetLedger(max_model_calls=80, max_browser_transitions=150)
    ledger.bind_snapshot(root / "mock_budget.json")
    image = root / "synthetic_blank.png"
    Image.new("RGB", (300, 180), "white").save(image)
    results = []
    with runner.require_playwright()() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(args.browser),
                                     args=list(runner.BROWSER_LAUNCH_ARGS), timeout=20000)
        try:
            for goal in ("Route A", "Route B"):
                for initial in ("Route A", "Route B"):
                    directory = root / f"flow_{goal[-1]}_{initial[-1]}"
                    task = dict(task_alias="control", page_title="Route control", user_goal=f"Choose {goal} and submit.",
                                chart_reference="No chart interpretation required.", primary_field_label="Route",
                                option_labels=["Route A", "Route B"])
                    submissions = directory / "server_receipts.jsonl"
                    with runner.managed_shell(task, image, submissions) as server:
                        page = browser.new_page(viewport=dict(width=1440, height=1100))
                        executor = runner.BrowserExecutor(page, ledger=TransitionScope(ledger), task_alias="control")
                        executor.navigate(server.base_url + "/task/control", phase="fixture_setup")
                        executor.execute(dict(action="click_link", text="Open Dashboard"), phase="fixture_setup")
                        executor.execute(dict(action="click_link", text="Open Form"), phase="fixture_setup")
                        executor.execute(dict(action="select_option", select_name="primary_action", option_text=initial), phase="fixture_setup")
                        model = models.RecordedModel(RouteMock(), ledger=ledger)
                        cp, prefix = capture_pending(page, executor, model, goal=task["user_goal"], alias="control",
                                                     directory=directory / "prefix", max_calls=2)
                        assert cp is not None and cp.current_selection == goal
                        assert runner.line_count(submissions) == 0
                        result = run_branch(page, executor, model, cp, strategy="B0", directory=directory / "B0",
                                            prefix_receipts=executor.receipts[:], submission_path=submissions)
                        assert result["submitted"] and result["confirmation_observed"]
                        results.append(dict(fixture="public_route_control", goal=goal, initial=initial,
                                            actor_calls=len(prefix["timeline"]), final=result["actor_final_submission"]["option"], passed=True))
                        page.close()
            # A scripted wrong choice is ONLY a non-chart software fixture.
            # It is not an injected benchmark error or natural model-recovery result.
            directory = root / "three_layer_fixture"
            task = dict(task_alias="control", page_title="Route control", user_goal="Choose Route A and submit.",
                        chart_reference="No chart interpretation required.", primary_field_label="Route",
                        option_labels=["Route A", "Route B"])
            submissions = directory / "server_receipts.jsonl"
            with runner.managed_shell(task, image, submissions) as server:
                page = browser.new_page(viewport=dict(width=1440, height=1100))
                executor = runner.BrowserExecutor(page, ledger=TransitionScope(ledger), task_alias="control")
                executor.navigate(server.base_url + "/task/control", phase="mock_natural_prefix_start")
                model = models.RecordedModel(RouteMock(initial_wrong=True), ledger=ledger)
                cp, prefix = capture_pending(page, executor, model, goal=task["user_goal"], alias="control",
                                             directory=directory / "prefix")
                assert cp is not None and cp.current_selection == "Route B"
                assert runner.line_count(submissions) == 0
                history = executor.receipts[:]
                page.close()
                for name, strategy, backend, continuation_limit in (
                    ("B0", "B0", RouteMock(), 4),
                    ("B2_actor_overwrites", "B2", RouteMock(overwrite_check=True), 4),
                    ("B3_zero_crop", "B3", RouteMock(), 4),
                    ("B3_crop_tool", "B3", RouteMock(crop=True), 4),
                    ("B2_no_auto_submit", "B2", RouteMock(never_submit=True), 1)):
                    branch_dir = directory / name
                    page = browser.new_page(viewport=dict(width=1440, height=1100))
                    executor = runner.BrowserExecutor(page, ledger=ledger, task_alias="control")
                    assert restore(page, executor, cp, base_url=server.base_url, directory=branch_dir)
                    model = models.RecordedModel(backend, ledger=ledger)
                    result = run_branch(page, executor, model, cp, strategy=strategy, directory=branch_dir,
                        prefix_receipts=history, submission_path=submissions, max_continuation_calls=continuation_limit)
                    if name == "B2_no_auto_submit":
                        assert not result["submitted"] and result["actor_final_submission"] is None
                    else:
                        assert result["submitted"] and result["confirmation_observed"]
                    if name == "B2_actor_overwrites":
                        assert result["verifier_recommendation"] == "Route A"
                        assert result["executor_selection"] == "Route A"
                        assert result["actor_final_submission"]["option"] == "Route B"
                    if name.startswith("B3"):
                        assert result["policy"]["active_observations"] == int(name == "B3_crop_tool")
                        assert result["actor_final_submission"]["option"] == "Route A"
                    results.append(dict(fixture=name, passed=True, submitted=result["submitted"],
                                        recommendation=result["verifier_recommendation"],
                                        executed_selection=result["executor_selection"],
                                        final=result["actor_final_submission"]))
                    page.close()
        finally:
            browser.close()
    summary = dict(status="passed", scope="nonchart_scripted_engineering_only", results=results,
                   mock_model_calls=ledger.model_calls, real_model_calls=0, real_api_http_attempts=0,
                   actual_browser_transitions=ledger.browser_transitions,
                   note="Neither prospective task charts nor real models were used; no visual research claim.")
    core.write_json(root / "result.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
