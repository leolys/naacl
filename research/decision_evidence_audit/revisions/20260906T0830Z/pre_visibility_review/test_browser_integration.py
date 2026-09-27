from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from research.decision_evidence_audit.core import BudgetLedger, write_json
from research.decision_evidence_audit.models import ModelReply, RecordedModel
from research.decision_evidence_audit.runner import (
    BROWSER_LAUNCH_ARGS,
    BrowserExecutor,
    browser_executable,
    generate_checkpoint,
    managed_shell,
    read_jsonl,
    replay_and_run_unit,
    require_playwright,
)
from research.decision_evidence_audit.safe_shell import score_receipt


@contextmanager
def control_artifacts(name):
    destination = os.environ.get("DECISION_EVIDENCE_TEST_OUTPUT")
    if destination:
        root = Path(destination) / name
        root.mkdir(parents=True, exist_ok=False)
        yield str(root)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp


def raw_task(expected: str = "route_b") -> dict:
    return {
        "page_title": "Positive control",
        "workflow_instruction": (
            "Select Route B when the visible chart panel is magenta; select Route A when it is orange."
        ),
        "chart_reference": "The panel color is the complete evidence for this injected control.",
        "primary_action": {"field_label": "Route"},
        "action_space": [
            {"action_id": "route_a", "label": "Route A"},
            {"action_id": "route_b", "label": "Route B"},
        ],
        "expected_action_id": expected,
        "misleading_action_ids": ["route_a"],
    }


def public_task() -> dict:
    return {
        "task_alias": "dev01",
        "page_title": "Positive control",
        "user_goal": (
            "Select Route B when the visible chart panel is magenta; select Route A when it is orange."
        ),
        "chart_reference": "The panel color is the complete evidence for this injected control.",
        "primary_field_label": "Route",
        "option_labels": ["Route A", "Route B"],
    }


class SwitchBackend:
    def __init__(
        self, *, submit_without_selection: bool = False, initial_option: str = "Route A"
    ) -> None:
        self.submit_without_selection = submit_without_selection
        self.initial_option = initial_option

    @property
    def metadata(self):
        return {"kind": "injected_positive_control", "research_result": False}

    def complete(self, request):
        context = request.public_context
        if request.phase == "prefix":
            state = context["state"]
            links = [item["text"] for item in state.get("links", [])]
            if "Open Dashboard" in links:
                action = {"action": "click_link", "text": "Open Dashboard"}
            elif "Open Form" in links:
                action = {"action": "click_link", "text": "Open Form"}
            elif self.submit_without_selection or context.get("current_selection"):
                action = {"action": "click_button", "text": "Submit Form"}
            else:
                action = {
                    "action": "select_option",
                    "select_name": "primary_action",
                    "option_text": self.initial_option,
                }
            return ModelReply(json.dumps(action))
        if request.phase == "b2_decision":
            with Image.open(request.image_path).convert("RGB") as image:
                colors = list(image.getdata())
            magenta = sum(r > 220 and g < 80 and b > 220 for r, g, b in colors)
            orange = sum(r > 220 and 80 < g < 190 and b < 80 for r, g, b in colors)
            option = "Route B" if magenta > orange else "Route A"
            return ModelReply(
                json.dumps({"option_label": option, "reason": "visible panel-color control"})
            )
        raise RuntimeError(request.phase)


class FailingPrefixBackend:
    @property
    def metadata(self):
        return {"kind": "injected_prefix_failure", "research_result": False}

    def complete(self, request):
        raise RuntimeError("injected model failure")


@unittest.skipUnless(os.environ.get("RUN_DECISION_EVIDENCE_BROWSER_TEST") == "1", "opt-in browser test")
class BrowserIntegrationTests(unittest.TestCase):
    def test_checkpoint_replay_true_revision_submit_b0_and_illegal_control(self) -> None:
        sync_playwright = require_playwright()
        with control_artifacts(self._testMethodName) as tmp:
            root = Path(tmp)
            chart = root / "chart.png"
            image = Image.new("RGB", (500, 300), (255, 0, 255))
            image.save(chart)
            receipts = root / "receipts.jsonl"
            ledger = BudgetLedger(max_model_calls=50, max_browser_transitions=100)
            model = RecordedModel(SwitchBackend(), ledger=ledger)
            with managed_shell(public_task(), chart, receipts) as shell:
                with sync_playwright() as playwright:
                    kwargs = {"headless": True, "args": list(BROWSER_LAUNCH_ARGS)}
                    executable = browser_executable(None)
                    if executable:
                        kwargs["executable_path"] = str(executable)
                    browser = playwright.chromium.launch(**kwargs)
                    try:
                        checkpoint, prefix = generate_checkpoint(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            user_goal=public_task()["user_goal"],
                            model=model,
                            ledger=ledger,
                            run_root=root,
                            prefix_dir=root / "online" / "prefix",
                            submission_path=receipts,
                            max_model_calls=8,
                        )
                        self.assertIsNotNone(checkpoint)
                        self.assertEqual(prefix["submission_count_after_capture"], 0)
                        self.assertEqual(checkpoint.current_selection, "Route A")
                        # Execute the exact original actions without a hook. This
                        # is a regression witness, not another resampled prefix.
                        direct_page = browser.new_page(viewport={"width": 1440, "height": 1100})
                        direct = BrowserExecutor(direct_page, ledger=ledger, task_alias="dev01")
                        direct.navigate(f"{shell.base_url}/task/dev01", phase="no_hook_start")
                        for action in checkpoint.visible_action_prefix:
                            direct.execute(action, phase="no_hook_prefix")
                        direct.execute(checkpoint.pending_proposal, phase="no_hook_submit", max_attempts=1)
                        direct_receipt = read_jsonl(receipts)[-1]
                        direct_page.close()
                        calls_before_b0 = ledger.model_calls
                        b0_result, b0_receipt = replay_and_run_unit(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            checkpoint=checkpoint,
                            strategy="B0",
                            model=model,
                            ledger=ledger,
                            run_root=root,
                            unit_dir=root / "online" / "b0",
                            submission_path=receipts,
                        )
                        self.assertEqual(b0_result["status"], "submitted")
                        self.assertEqual(b0_receipt["selected_option_label"], "Route A")
                        self.assertEqual(ledger.model_calls, calls_before_b0)
                        self.assertEqual(b0_result["original_proposal"]["status"], "executed")
                        self.assertEqual(
                            {k: v for k, v in direct_receipt.items() if k != "timestamp"},
                            {k: v for k, v in b0_receipt.items() if k != "timestamp"},
                        )
                        self.assertEqual([r["action"] for r in direct.receipts],
                                         [r["action"] for r in b0_result["executor_receipts"]])
                        changed_result, changed_receipt = replay_and_run_unit(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            checkpoint=checkpoint,
                            strategy="B2",
                            model=model,
                            ledger=ledger,
                            run_root=root,
                            unit_dir=root / "online" / "b2",
                            submission_path=receipts,
                        )
                        self.assertEqual(changed_result["status"], "submitted")
                        self.assertEqual(changed_receipt["selected_option_label"], "Route B")
                        self.assertEqual(score_receipt(raw_task(), changed_receipt)["outcome"], "success")
                        self.assertEqual(
                            changed_result["original_proposal"]["status"],
                            "cancelled_for_visible_revision",
                        )
                        self.assertTrue(changed_result["confirmation_observed"])
                    finally:
                        write_json(root / "initial_control_budget.json", ledger.to_dict())
                        browser.close()


            no_change_receipts = root / "no_change_receipts.jsonl"
            no_change_ledger = BudgetLedger(max_model_calls=20, max_browser_transitions=50)
            no_change_model = RecordedModel(
                SwitchBackend(initial_option="Route B"), ledger=no_change_ledger
            )
            with managed_shell(public_task(), chart, no_change_receipts) as shell:
                with sync_playwright() as playwright:
                    kwargs = {"headless": True, "args": list(BROWSER_LAUNCH_ARGS)}
                    executable = browser_executable(None)
                    if executable:
                        kwargs["executable_path"] = str(executable)
                    browser = playwright.chromium.launch(**kwargs)
                    try:
                        checkpoint, _ = generate_checkpoint(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            user_goal=public_task()["user_goal"],
                            model=no_change_model,
                            ledger=no_change_ledger,
                            run_root=root,
                            prefix_dir=root / "online" / "no_change_prefix",
                            submission_path=no_change_receipts,
                            max_model_calls=8,
                        )
                        self.assertIsNotNone(checkpoint)
                        self.assertEqual(checkpoint.current_selection, "Route B")
                        result, receipt = replay_and_run_unit(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            checkpoint=checkpoint,
                            strategy="B2",
                            model=no_change_model,
                            ledger=no_change_ledger,
                            run_root=root,
                            unit_dir=root / "online" / "no_change_b2",
                            submission_path=no_change_receipts,
                        )
                        self.assertEqual(result["status"], "submitted")
                        self.assertFalse(result["policy"]["changed"])
                        self.assertEqual(receipt["selected_option_label"], "Route B")
                        self.assertEqual(score_receipt(raw_task(), receipt)["outcome"], "success")
                    finally:
                        browser.close()

            illegal_receipts = root / "illegal_receipts.jsonl"
            illegal_ledger = BudgetLedger(max_model_calls=20, max_browser_transitions=50)
            illegal_model = RecordedModel(
                SwitchBackend(submit_without_selection=True), ledger=illegal_ledger
            )
            with managed_shell(public_task(), chart, illegal_receipts) as shell:
                with sync_playwright() as playwright:
                    kwargs = {"headless": True, "args": list(BROWSER_LAUNCH_ARGS)}
                    executable = browser_executable(None)
                    if executable:
                        kwargs["executable_path"] = str(executable)
                    browser = playwright.chromium.launch(**kwargs)
                    try:
                        checkpoint, _ = generate_checkpoint(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            user_goal=public_task()["user_goal"],
                            model=illegal_model,
                            ledger=illegal_ledger,
                            run_root=root,
                            prefix_dir=root / "online" / "illegal_prefix",
                            submission_path=illegal_receipts,
                            max_model_calls=6,
                        )
                        self.assertIsNotNone(checkpoint)
                        result, receipt = replay_and_run_unit(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            checkpoint=checkpoint,
                            strategy="B0",
                            model=illegal_model,
                            ledger=illegal_ledger,
                            run_root=root,
                            unit_dir=root / "online" / "illegal_b0",
                            submission_path=illegal_receipts,
                        )
                        self.assertEqual(result["status"], "submitted")
                        self.assertEqual(receipt["selected_option_label"], "")
                        self.assertEqual(
                            score_receipt(raw_task(), receipt)["outcome"], "completion_failure"
                        )
                    finally:
                        browser.close()

            failure_receipts = root / "failure_receipts.jsonl"
            failure_ledger = BudgetLedger(max_model_calls=20, max_browser_transitions=50)
            failure_model = RecordedModel(FailingPrefixBackend(), ledger=failure_ledger)
            with managed_shell(public_task(), chart, failure_receipts) as shell:
                with sync_playwright() as playwright:
                    kwargs = {"headless": True, "args": list(BROWSER_LAUNCH_ARGS)}
                    executable = browser_executable(None)
                    if executable:
                        kwargs["executable_path"] = str(executable)
                    browser = playwright.chromium.launch(**kwargs)
                    try:
                        checkpoint, result = generate_checkpoint(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias="dev01",
                            user_goal=public_task()["user_goal"],
                            model=failure_model,
                            ledger=failure_ledger,
                            run_root=root,
                            prefix_dir=root / "online" / "failure_prefix",
                            submission_path=failure_receipts,
                            max_model_calls=6,
                        )
                        self.assertIsNone(checkpoint)
                        self.assertEqual(result["submission_count_after_capture"], 0)
                        self.assertEqual(result["errors"][0]["kind"], "prefix_runtime_failure")
                        self.assertEqual(failure_ledger.model_calls, 1)
                        self.assertTrue(
                            (root / "online" / "failure_prefix" / "prefix_result.json").is_file()
                        )
                        response = json.loads(
                            next(
                                (root / "online" / "failure_prefix" / "responses").glob("*.json")
                            ).read_text()
                        )
                        self.assertFalse(response["ok"])
                    finally:
                        browser.close()


            write_json(root / "control_budgets.json", {
                "evaluation_type": "simulation_only", "real_model_calls": 0,
                "mock_calls": sum(x.model_calls for x in (ledger, no_change_ledger, illegal_ledger, failure_ledger)),
                "browser_transitions": sum(x.browser_transitions for x in (ledger, no_change_ledger, illegal_ledger, failure_ledger)),
                "ledgers": [x.to_dict() for x in (ledger, no_change_ledger, illegal_ledger, failure_ledger)],
            })

    def test_exact_public_select_resolution_and_rejections(self) -> None:
        with control_artifacts(self._testMethodName) as tmp:
            root = Path(tmp)
            chart = root / "chart.png"
            Image.new("RGB", (60, 40), "white").save(chart)
            ledger = BudgetLedger(max_model_calls=0, max_browser_transitions=80)
            with managed_shell(public_task(), chart, root / "receipts.jsonl") as shell:
                with require_playwright()() as playwright:
                    executable = browser_executable(None)
                    kwargs = {"headless": True, "args": list(BROWSER_LAUNCH_ARGS)}
                    if executable:
                        kwargs["executable_path"] = str(executable)
                    browser = playwright.chromium.launch(**kwargs)
                    try:
                        page = browser.new_page()
                        executor = BrowserExecutor(page, ledger=ledger, task_alias="dev01")
                        executor.navigate(f"{shell.base_url}/task/dev01/form", phase="select_control_start")
                        for identifier in ("primary_action", "Route"):
                            receipt = executor.execute({"action": "select_option", "select_name": identifier,
                                                        "option_text": "Route B"}, phase="select_control")
                            self.assertTrue(receipt["executed"])
                            self.assertEqual(page.locator("select").input_value(), "option_1")
                        # Distinct id and a label containing punctuation/quotes.
                        page.locator("select").evaluate("el => { el.id = 'route:id'; el.labels; }")
                        executor.execute({"action": "select_option", "select_name": "route:id",
                                          "option_text": "Route A"}, phase="select_control")
                        page.locator("label").first.evaluate(
                            "el => { el.htmlFor = 'route:id'; el.innerText = 'Route [one] \"quoted\"'; }")
                        executor.execute({"action": "select_option", "select_name": 'Route [one] "quoted"',
                                          "option_text": "Route B"}, phase="select_control")
                        # Real DOM change listener undoes the first selection;
                        # the common postcondition must observe and retry it.
                        page.locator("select").evaluate("""el => el.addEventListener('change',
                            () => { el.value = 'option_1'; }, {once: true})""")
                        before = ledger.browser_transitions
                        executor.execute({"action": "select_option", "select_name": "primary_action",
                                          "option_text": "Route A"}, phase="selection_noop_control")
                        self.assertEqual(ledger.browser_transitions - before, 2)
                        self.assertEqual(page.locator("select").input_value(), "option_0")
                        for identifier, option in (("missing", "Route B"), ("primary_action", "not an option")):
                            with self.assertRaises(RuntimeError):
                                executor.execute({"action": "select_option", "select_name": identifier,
                                                  "option_text": option}, phase="invalid_select_control")
                            self.assertEqual(page.locator("select").input_value(), "option_0")
                        page.locator("select").evaluate("el => el.after(el.cloneNode(true))")
                        page.locator("select").last.evaluate("""el => {
                            el.id = 'route:two'; const label = document.createElement('label');
                            label.htmlFor = el.id; label.innerText = 'Route [one] "quoted"';
                            el.before(label);
                        }""")
                        for identifier in ("primary_action", 'Route [one] "quoted"'):
                            with self.assertRaises(RuntimeError):
                                executor.execute({"action": "select_option", "select_name": identifier,
                                                  "option_text": "Route B"}, phase="ambiguous_select_control")
                        page.screenshot(path=str(root / "final_controls.png"))
                        self.assertFalse((root / "receipts.jsonl").exists())
                    finally:
                        write_json(root / "control_budgets.json", {
                            "evaluation_type": "simulation_only", "real_model_calls": 0,
                            "mock_calls": 0, "browser_transitions": ledger.browser_transitions,
                            "ledgers": [ledger.to_dict()], "executor_receipts": executor.receipts,
                        })
                        browser.close()


if __name__ == "__main__":
    unittest.main()
