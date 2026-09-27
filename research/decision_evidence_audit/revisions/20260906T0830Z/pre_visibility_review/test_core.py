from __future__ import annotations

import json
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from research.decision_evidence_audit.core import (
    BeforeSubmitHook,
    BudgetExceeded,
    BudgetLedger,
    Checkpoint,
    IsolationError,
    assert_online_payload,
    public_browser_state,
    public_task_projection,
)
from research.decision_evidence_audit.models import ModelReply, RecordedModel, ScriptedMockBackend
from research.decision_evidence_audit.policies import crop_observation, run_policy
from research.decision_evidence_audit.runner import (
    BrowserExecutor,
    _close_unit_page,
    _submission_status,
    completed_chain_unit,
    managed_shell,
    pair_invariant_differences,
    run_multi_image_witness,
    run_smoke,
)
from research.decision_evidence_audit.safe_shell import make_app, score_receipt
from research.decision_evidence_audit.validate_run import (
    replay_artifact_required,
    request_text_for_hidden_scan,
    submission_consistency_errors,
    validate_run,
)


def task_fixture(*, expected: str = "route_b", hidden_marker: str = "secret-one") -> dict:
    return {
        "task_id": "hidden-task-id",
        "case_id": "hidden-case-id",
        "page_title": "Visible routing task",
        "workflow_instruction": "Use the chart to choose the supported route.",
        "chart_reference": "Review the displayed monthly values.",
        "misleader_type": hidden_marker,
        "ground_truth": {"private": hidden_marker},
        "intermediate_decision": {"private": hidden_marker},
        "primary_action": {"field_label": "Routing choice", "correct_action_id": expected},
        "companion_actions": [{"correct_value": hidden_marker}],
        "action_space": [
            {"action_id": "route_a", "label": "Route A", "role": "private-role-a"},
            {"action_id": "route_b", "label": "Route B", "role": "private-role-b"},
        ],
        "expected_action_id": expected,
        "misleading_action_ids": ["route_a" if expected == "route_b" else "route_b"],
        "fallback_scoring": {"private": hidden_marker},
        "completion_action": {"label": "Submit Form"},
    }


def form_state(selection: str = "Route A") -> dict:
    return {
        "url_path": "/task/dev01/form",
        "text": "Submit Decision",
        "links": [{"text": "Back to Dashboard", "path": "/task/dev01/dashboard"}],
        "buttons": [{"text": "Submit Form", "type": "submit"}],
        "selects": [
            {
                "name": "primary_action",
                "label": "Routing choice",
                "selected_text": selection,
                "options": [
                    {"text": "Select a route", "disabled": False, "selected": not selection},
                    {"text": "Route A", "disabled": False, "selected": selection == "Route A"},
                    {"text": "Route B", "disabled": False, "selected": selection == "Route B"},
                ],
            }
        ],
    }


class ProjectionAndHookTests(unittest.TestCase):
    def test_hidden_label_swap_leaves_online_projection_and_html_equal_but_score_changes(self) -> None:
        first = task_fixture(expected="route_b", hidden_marker="secret-one")
        second = task_fixture(expected="route_a", hidden_marker="secret-two")
        projection_one = public_task_projection(first, task_alias="dev01")
        projection_two = public_task_projection(second, task_alias="dev01")
        self.assertEqual(projection_one, projection_two)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chart = root / "chart.png"
            Image.new("RGB", (40, 30), "white").save(chart)
            html_one = make_app(
                projection_one, chart_path=chart, output_path=root / "one.jsonl"
            ).test_client().get("/task/dev01/form").data
            html_two = make_app(
                projection_two, chart_path=chart, output_path=root / "two.jsonl"
            ).test_client().get("/task/dev01/form").data
        self.assertEqual(html_one, html_two)
        receipt = {"selected_option_token": "option_0", "selected_option_label": "Route A"}
        self.assertNotEqual(score_receipt(first, receipt), score_receipt(second, receipt))

    def test_visible_option_order_uses_only_public_labels(self) -> None:
        task = task_fixture()
        task["action_space"] = [task["action_space"][1], task["action_space"][0]]
        first = public_task_projection(task, task_alias="dev01")
        task["expected_action_id"] = "route_a"
        task["misleading_action_ids"] = ["route_b"]
        second = public_task_projection(task, task_alias="dev01")
        self.assertEqual(first["option_labels"], ["Route A", "Route B"])
        self.assertEqual(first, second)

    def test_safe_shell_never_renders_evaluator_fields_or_values(self) -> None:
        task = task_fixture(hidden_marker="DO_NOT_RENDER_SENTINEL")
        projection = public_task_projection(task, task_alias="dev01")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chart = root / "opaque.png"
            Image.new("RGB", (10, 10), "white").save(chart)
            client = make_app(
                projection, chart_path=chart, output_path=root / "receipts.jsonl"
            ).test_client()
            combined = b"".join(
                client.get(path).data
                for path in ("/task/dev01", "/task/dev01/dashboard", "/task/dev01/form")
            ).decode("utf-8")
        for forbidden in (
            "DO_NOT_RENDER_SENTINEL",
            "hidden-task-id",
            "hidden-case-id",
            "route_a",
            "route_b",
            "ground_truth",
            "misleader_type",
            "expected_action_id",
        ):
            self.assertNotIn(forbidden, combined)

    def test_public_browser_state_removes_host_control_values_and_extra_keys(self) -> None:
        raw = {
            "url": "http://127.0.0.1:9999/task/dev01/form?visible=1",
            "text": "Visible",
            "secret": "drop",
            "elements": {
                "links": [{"text": "Back", "href": "http://127.0.0.1:9999/task/dev01"}],
                "buttons": [{"text": "Submit Form", "type": "submit", "secret": "drop"}],
                "selects": [
                    {
                        "name": "primary_action",
                        "value": "option_0",
                        "selected_text": "Route A",
                        "options": [
                            {"text": "Route A", "value": "option_0", "selected": True}
                        ],
                    }
                ],
            },
        }
        visible = public_browser_state(raw)
        serialized = json.dumps(visible)
        self.assertEqual(visible["url_path"], "/task/dev01/form?visible=1")
        self.assertNotIn("127.0.0.1", serialized)
        self.assertNotIn("option_0", serialized)
        self.assertNotIn("secret", serialized)

    def test_online_key_guard_rejects_nested_scorer_field(self) -> None:
        with self.assertRaises(IsolationError):
            assert_online_payload({"visible": {"expected_action_id": "x"}})

    def test_hook_captures_first_submit_before_execution_for_any_state(self) -> None:
        for selection in ("Route A", "Route B", ""):
            hook = BeforeSubmitHook()
            state = form_state(selection)
            checkpoint = hook.inspect(
                task_alias="dev01",
                user_goal="Visible goal",
                state=state,
                current_screenshot="online/current.png",
                observed_screenshots=[{"kind": "form", "path": "online/current.png"}],
                visible_action_prefix=[],
                model_context=[],
                proposal={"action": "click_link", "text": "Submit Form"},
            )
            self.assertIsNotNone(checkpoint)
            self.assertEqual(checkpoint.proposal_status, "pending")
            self.assertIsNone(
                hook.inspect(
                    task_alias="dev01",
                    user_goal="Visible goal",
                    state=state,
                    current_screenshot="online/current.png",
                    observed_screenshots=[],
                    visible_action_prefix=[],
                    model_context=[],
                    proposal={"action": "submit_form"},
                )
            )

    def test_finish_and_ordinary_buttons_do_not_trigger(self) -> None:
        hook = BeforeSubmitHook()
        state = form_state()
        for action in (
            {"action": "finish"},
            {"action": "click_button", "text": "Back to Dashboard"},
        ):
            self.assertIsNone(
                hook.inspect(
                    task_alias="dev01",
                    user_goal="Visible goal",
                    state=state,
                    current_screenshot="x.png",
                    observed_screenshots=[],
                    visible_action_prefix=[],
                    model_context=[],
                    proposal=action,
                )
            )
        state_without_submit = form_state()
        state_without_submit["buttons"] = []
        self.assertIsNone(
            BeforeSubmitHook().inspect(
                task_alias="dev01",
                user_goal="Visible goal",
                state=state_without_submit,
                current_screenshot="x.png",
                observed_screenshots=[],
                visible_action_prefix=[],
                model_context=[],
                proposal={"action": "submit_form"},
            )
        )

    def test_budget_counts_failures_before_delegate_and_refuses_overrun(self) -> None:
        ledger = BudgetLedger(max_model_calls=1, max_browser_transitions=1)
        ledger.charge_model(phase="test", request_id="one")
        ledger.charge_transition(phase="test", action={"action": "bad"})
        with self.assertRaises(BudgetExceeded):
            ledger.charge_model(phase="test", request_id="two")
        with self.assertRaises(BudgetExceeded):
            ledger.charge_transition(phase="test", action={"action": "bad"})

    def test_known_release_pair_invariant_audit_detects_semantic_drift(self) -> None:
        left = task_fixture()
        right = task_fixture()
        right["workflow_instruction"] = "Changed goal"
        right["action_space"] = right["action_space"][:1]
        differences = pair_invariant_differences(left, right)
        self.assertIn("workflow_instruction", differences)
        self.assertIn("action_space", differences)


class CaptureBackend:
    def __init__(self, option: str) -> None:
        self.option = option
        self.requests = []

    @property
    def metadata(self):
        return {"kind": "test"}

    def complete(self, request):
        self.requests.append(request)
        return ModelReply(json.dumps({"option_label": self.option, "reason": "visible"}))


class PolicyTests(unittest.TestCase):
    def checkpoint(self, root: Path, selection: str = "Route A") -> Checkpoint:
        dashboard = root / "dashboard.png"
        current = root / "current.png"
        Image.new("RGB", (100, 100), "white").save(dashboard)
        Image.new("RGB", (100, 100), "white").save(current)
        return Checkpoint(
            checkpoint_version=1,
            task_alias="dev01",
            user_goal="Choose from visible evidence.",
            visible_options=["Route A", "Route B"],
            current_selection=selection,
            current_state=form_state(selection),
            current_screenshot="current.png",
            observed_screenshots=[{"kind": "dashboard", "path": "dashboard.png"}],
            visible_action_prefix=[],
            model_context=[],
            pending_proposal={"action": "click_button", "text": "Submit Form"},
        )

    def test_b0_is_exact_no_model_call_and_does_not_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backend = CaptureBackend("Route B")
            model = RecordedModel(backend, ledger=BudgetLedger())
            result = run_policy(
                "B0", self.checkpoint(root), model=model, artifact_root=root, unit_dir=root / "unit"
            )
        self.assertEqual(result.recommended_option, "Route A")
        self.assertFalse(result.changed)
        self.assertEqual(len(backend.requests), 0)

    def test_hidden_mutation_leaves_all_policy_requests_and_branches_identical(self) -> None:
        first = task_fixture(expected="route_a", hidden_marker="private-one")
        second = task_fixture(expected="route_b", hidden_marker="private-two")
        for strategy in ("B0", "B2", "B3", "B4"):
            executions = []
            for raw in (first, second):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    public = public_task_projection(raw, task_alias="dev01")
                    checkpoint = self.checkpoint(root)
                    checkpoint.user_goal = public["user_goal"]
                    checkpoint.visible_options = public["option_labels"]
                    ledger = BudgetLedger()
                    result = run_policy(strategy, checkpoint,
                                        model=RecordedModel(ScriptedMockBackend(), ledger=ledger),
                                        artifact_root=root, unit_dir=root / "unit")
                    requests = [json.loads(path.read_text()) for path in sorted(
                        (root / "unit" / "requests").glob("*.json"))]
                    executions.append((result.to_dict(), requests, ledger.to_dict()))
            self.assertEqual(executions[0], executions[1], strategy)
        self.assertNotEqual(score_receipt(first, {"selected_option_label": "Route A"}),
                            score_receipt(second, {"selected_option_label": "Route A"}))

    def test_b2_change_and_correct_no_change_controls(self) -> None:
        for initial, recommendation, expected_change in (
            ("Route A", "Route B", True),
            ("Route B", "Route B", False),
        ):
            with self.subTest(initial=initial):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    backend = CaptureBackend(recommendation)
                    model = RecordedModel(backend, ledger=BudgetLedger())
                    result = run_policy(
                        "B2",
                        self.checkpoint(root, initial),
                        model=model,
                        artifact_root=root,
                        unit_dir=root / "unit",
                    )
                    request_payload = json.loads(
                        next((root / "unit" / "requests").glob("*.json")).read_text()
                    )
                self.assertEqual(result.changed, expected_change)
                self.assertNotIn("current_selection", request_payload["public_context"])

    def test_crop_keeps_requested_axis_and_legend_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            target = root / "crop.png"
            image = Image.new("RGB", (100, 100), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((5, 10, 10, 90), fill="black")
            draw.rectangle((70, 10, 90, 25), fill="red")
            image.save(source)
            meta = crop_observation(source, target, [0, 0, 95, 95])
            with Image.open(target) as cropped:
                colors = {pixel for pixel in cropped.getdata()}
        self.assertEqual(meta["effective_region"], [0, 0, 95, 95])
        self.assertIn((0, 0, 0), colors)
        self.assertIn((255, 0, 0), colors)

    def test_b2_never_substitutes_a_choice_bearing_form_for_independent_chart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint = self.checkpoint(root)
            checkpoint.observed_screenshots = [{"kind": "form", "path": "current.png"}]
            backend = CaptureBackend("Route B")
            result = run_policy("B2", checkpoint, model=RecordedModel(backend, ledger=BudgetLedger()),
                                artifact_root=root, unit_dir=root / "unit")
            self.assertEqual(result.model_calls, 0)
            self.assertFalse(backend.requests)
            self.assertEqual(result.parse_status, "independent_chart_observation_unavailable_keep")
            self.assertFalse(result.changed)

    def test_other_policies_do_not_relabel_last_observation_as_dashboard(self) -> None:
        for strategy in ("B3", "B4"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                checkpoint = self.checkpoint(root)
                checkpoint.observed_screenshots = [{"kind": "form", "path": "current.png"}]
                backend = CaptureBackend("Route B")
                result = run_policy(strategy, checkpoint,
                                    model=RecordedModel(backend, ledger=BudgetLedger()),
                                    artifact_root=root, unit_dir=root / "unit")
                self.assertEqual(result.parse_status, "chart_observation_unavailable_keep")
                self.assertEqual(result.model_calls, 0)
                self.assertFalse(backend.requests)
                self.assertFalse(result.changed)

    def test_b3_can_use_two_observations_but_never_more_than_three_calls(self) -> None:
        class TwoCropBackend:
            def __init__(self) -> None:
                self.calls = 0
                self.requests = []

            @property
            def metadata(self):
                return {"kind": "two-crop-test"}

            def complete(self, request):
                self.calls += 1
                self.requests.append(request)
                if self.calls <= 2:
                    return ModelReply(
                        json.dumps(
                            {
                                "observe": {
                                    "screenshot_id": "dashboard",
                                    "region": [0, 0, 80, 80],
                                    "reason": f"crop-{self.calls}",
                                }
                            }
                        )
                    )
                return ModelReply(json.dumps({"option_label": "Route B", "reason": "visible"}))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backend = TwoCropBackend()
            model = RecordedModel(backend, ledger=BudgetLedger())
            result = run_policy(
                "B3", self.checkpoint(root), model=model, artifact_root=root, unit_dir=root / "unit"
            )
            self.assertTrue((root / "unit" / "observations" / "active_crop_01.png").is_file())
            self.assertTrue((root / "unit" / "observations" / "active_crop_02.png").is_file())
        self.assertEqual(result.model_calls, 3)
        self.assertEqual(result.active_observations, 2)
        self.assertEqual(result.recommended_option, "Route B")
        self.assertEqual([len(request.image_paths) for request in backend.requests], [2, 3, 4])


class FailingTarget:
    def __init__(self) -> None:
        self.calls = 0

    def count(self) -> int:
        return 1

    def click(self, timeout: int) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("injected first click failure")


class FakePage:
    def __init__(self) -> None:
        self.url = "http://127.0.0.1/task/dev01/form"
        self.target = FailingTarget()

    def get_by_role(self, role: str, name: str, exact: bool = True):
        return self.target

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        return None


class NoOpThenSelectLocator:
    def __init__(self) -> None:
        self.calls = 0
        self.selected_text = "Route A"

    @property
    def first(self):
        return self

    def evaluate_all(self, expression):
        return [{"index": 0, "name": "primary_action", "id": "primary_action",
                 "visible": True, "disabled": False, "labels": ["Route"],
                 "options": [{"text": label, "disabled": False} for label in ("Route A", "Route B")]}]

    def nth(self, index):
        return self

    def select_option(self, *, label: str, timeout: int) -> None:
        self.calls += 1
        if self.calls > 1:
            self.selected_text = label

    def evaluate(self, expression: str) -> str:
        return self.selected_text


class NoOpThenSelectPage:
    def __init__(self) -> None:
        self.url = "http://127.0.0.1/task/dev01/form"
        self.target = NoOpThenSelectLocator()

    def locator(self, selector: str):
        return self.target

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        return None


class ExecutorTests(unittest.TestCase):
    def test_path_containment_requires_task_path_boundary(self) -> None:
        page = FakePage()
        executor = BrowserExecutor(page, ledger=BudgetLedger(), task_alias="dev01")
        self.assertTrue(executor._contained())
        page.url = "http://127.0.0.1/task/dev01evil/form"
        self.assertFalse(executor._contained())

    def test_action_failure_is_counted_and_retried_once(self) -> None:
        ledger = BudgetLedger()
        page = FakePage()
        executor = BrowserExecutor(page, ledger=ledger, task_alias="dev01", max_attempts=2)
        receipt = executor.execute(
            {"action": "click_button", "text": "Apply Filter"}, phase="positive_control"
        )
        self.assertTrue(receipt["executed"])
        self.assertEqual(page.target.calls, 2)
        self.assertEqual(ledger.browser_transitions, 2)
        self.assertFalse(executor.receipts[0]["executed"])

    def test_irreversible_action_can_disable_retry(self) -> None:
        ledger = BudgetLedger()
        page = FakePage()
        executor = BrowserExecutor(page, ledger=ledger, task_alias="dev01", max_attempts=2)
        with self.assertRaises(RuntimeError):
            executor.execute(
                {"action": "click_button", "text": "Submit Form"},
                phase="final_submit",
                max_attempts=1,
            )
        self.assertEqual(page.target.calls, 1)
        self.assertEqual(ledger.browser_transitions, 1)

    def test_selection_noop_is_detected_counted_and_retried(self) -> None:
        ledger = BudgetLedger()
        page = NoOpThenSelectPage()
        executor = BrowserExecutor(page, ledger=ledger, task_alias="dev01", max_attempts=2)
        receipt = executor.execute(
            {
                "action": "select_option",
                "select_name": "primary_action",
                "option_text": "Route B",
            },
            phase="positive_control",
        )
        self.assertTrue(receipt["executed"])
        self.assertEqual(page.target.calls, 2)
        self.assertEqual(ledger.browser_transitions, 2)
        self.assertIn("selection_postcondition_failure", executor.receipts[0]["error"])


class FailureRetentionTests(unittest.TestCase):
    def test_scorer_reports_dataset_class_not_causal_visual_attribution(self) -> None:
        score = score_receipt(task_fixture(expected="route_b"), {"selected_option_label": "Route A"})
        self.assertEqual(score["outcome"], "misleading_failure")
        self.assertEqual(score["error_attribution"], "selected_dataset_misleading_option")

    def test_offline_validator_detects_tampered_outcome_selection_action_and_receipt(self) -> None:
        raw = task_fixture(expected="route_a")
        receipt = {"selected_option_label": "Route A"}
        action = {"action": "click_button", "text": "Submit Form"}
        checkpoint = {"current_selection": "Route A", "pending_proposal": action}
        result = {"strategy": "B0", "submission_receipt_public": receipt,
                  "selected_before_submit": "Route A", "executed_submission": {"action": action},
                  "revision_action": None,
                  "policy": {"changed": False, "recommended_option": "Route A", "original_selection": "Route A"}}
        score = {"selected_option_label": "Route A", "terminal_score": score_receipt(raw, receipt)}
        self.assertEqual(submission_consistency_errors(raw, result, checkpoint, score, [receipt]), [])
        for mutation in ("outcome", "selection", "action", "revision", "server_receipt"):
            changed_result, changed_score = copy.deepcopy(result), copy.deepcopy(score)
            receipts = [receipt]
            if mutation == "outcome":
                changed_score["terminal_score"]["outcome"] = "success_not_from_dataset"
            elif mutation == "selection":
                changed_result["selected_before_submit"] = "Route B"
            elif mutation == "action":
                changed_result["executed_submission"]["action"]["text"] = "Another Button"
            elif mutation == "revision":
                changed_result["revision_action"] = {"executed": True}
            else:
                receipts = []
            self.assertTrue(submission_consistency_errors(raw, changed_result, checkpoint, changed_score, receipts), mutation)

    def test_submission_status_retains_duplicate_and_missing_confirmation_failures(self) -> None:
        receipt = {"selected_option_label": "Route B"}
        self.assertEqual(
            _submission_status(
                receipt=None,
                duplicate_receipts=[receipt, receipt],
                submit_error="",
                confirmation_error="",
                screenshot_error="",
            ),
            "duplicate_submission_error",
        )
        self.assertEqual(
            _submission_status(
                receipt=receipt,
                duplicate_receipts=[],
                submit_error="",
                confirmation_error="confirmation_path_not_observed",
                screenshot_error="",
            ),
            "submitted_acknowledgement_error",
        )

    def test_committed_result_survives_page_close_failure(self) -> None:
        page = MagicMock()
        page.close.side_effect = RuntimeError("injected close failure")
        receipt = {"selected_option_label": "Route B"}
        result = {
            "status": "submitted",
            "submission_observed": True,
            "submission_receipt_public": receipt,
        }
        with tempfile.TemporaryDirectory() as tmp:
            unit_dir = Path(tmp) / "unit"
            _close_unit_page(page, result, unit_dir)
            written = json.loads((unit_dir / "result.json").read_text())
        self.assertEqual(written["status"], "submitted")
        self.assertTrue(written["submission_observed"])
        self.assertIn("injected close failure", written["page_close_error"])
        self.assertEqual(score_receipt(task_fixture(), receipt)["outcome"], "success")

    def test_checkpoint_early_failure_does_not_require_fake_replay_artifact(self) -> None:
        for status in ("unit_error", "not_run_prefix_or_shell_failure"):
            self.assertFalse(
                replay_artifact_required(
                    prefix_reached=True,
                    status=status,
                    result={"error_type": "RuntimeError", "error": "injected"},
                )
            )
        self.assertTrue(
            replay_artifact_required(
                prefix_reached=True,
                status="submitted",
                result={"submission_observed": True},
            )
        )

    def test_shell_health_failure_stops_server_and_closes_session(self) -> None:
        server = MagicMock()
        server.server_port = 4321
        thread = MagicMock()
        session = MagicMock()
        session.get.side_effect = RuntimeError("injected health failure")
        with (
            patch("research.decision_evidence_audit.runner.make_app", return_value=MagicMock()),
            patch("research.decision_evidence_audit.runner.make_server", return_value=server),
            patch("research.decision_evidence_audit.runner.threading.Thread", return_value=thread),
            patch("research.decision_evidence_audit.runner.requests.Session", return_value=session),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected health failure"):
                with managed_shell({}, Path("unused"), Path("unused")):
                    self.fail("health failure must prevent yielding the shell")
        session.close.assert_called_once_with()
        server.shutdown.assert_called_once_with()
        thread.join.assert_called_once_with(timeout=5)


class RunFinalizerTests(unittest.TestCase):
    def test_completed_chain_status_requires_clean_ack_confirmation_and_score(self) -> None:
        score = {"terminal_score": {"outcome": "success"}}
        self.assertTrue(
            completed_chain_unit(
                {"status": "submitted", "confirmation_observed": True}, score
            )
        )
        self.assertFalse(
            completed_chain_unit(
                {"status": "submitted_acknowledgement_error", "confirmation_observed": True},
                score,
            )
        )
        self.assertFalse(
            completed_chain_unit(
                {"status": "submitted", "confirmation_observed": False}, score
            )
        )
        self.assertFalse(
            completed_chain_unit(
                {"status": "submitted", "confirmation_observed": True},
                {"terminal_score": None},
            )
        )

    def test_preflight_rejection_does_not_leave_a_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            base = dict(
                max_model_calls=160,
                max_browser_transitions=800,
                prefix_max_model_calls=12,
                output_root=output_root,
                local_model_name="unused",
                max_output_tokens=64,
                temperature=0.0,
                top_p=1.0,
                seed=1,
                browser_executable=None,
            )
            missing_endpoint = SimpleNamespace(
                **base,
                tasks="env001",
                run_id="missing_endpoint",
                mode="live-local",
                local_model_url=None,
            )
            with self.assertRaises(ValueError):
                run_smoke(missing_endpoint)
            self.assertFalse((output_root / "missing_endpoint").exists())

            missing_task = SimpleNamespace(
                **base,
                tasks="not_a_task",
                run_id="missing_task",
                mode="mock",
                local_model_url=None,
            )
            with self.assertRaises(ValueError):
                run_smoke(missing_task)
            self.assertFalse((output_root / "missing_task").exists())

            duplicate_task = SimpleNamespace(
                **base,
                tasks="env001,env001",
                run_id="duplicate_task",
                mode="mock",
                local_model_url=None,
            )
            with self.assertRaises(ValueError):
                run_smoke(duplicate_task)
            self.assertFalse((output_root / "duplicate_task").exists())

    def test_browser_startup_failure_retains_entire_planned_grid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                tasks="env001,env025",
                max_model_calls=160,
                max_browser_transitions=800,
                prefix_max_model_calls=12,
                output_root=Path(tmp),
                run_id="injected_startup_failure",
                mode="mock",
                local_model_url=None,
                local_model_name="unused",
                max_output_tokens=64,
                temperature=0.0,
                top_p=1.0,
                seed=1,
                browser_executable=None,
            )
            with patch(
                "research.decision_evidence_audit.runner.require_playwright",
                side_effect=RuntimeError("injected browser startup failure"),
            ):
                run_root = run_smoke(args)
            manifest = json.loads((run_root / "run_manifest.json").read_text())
            validation = validate_run(run_root)
        self.assertEqual(manifest["configured_units"], 16)
        self.assertEqual(manifest["completed_units"], 16)
        self.assertEqual(manifest["checkpoint_count"], 0)
        self.assertEqual(manifest["run_status"], "completed_with_retained_errors")
        self.assertEqual(manifest["budget"]["model_calls"], 0)
        self.assertEqual(manifest["budget"]["browser_transitions"], 0)
        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(validation["counts"]["units"], 16)


class MultiImageWitnessTests(unittest.TestCase):
    class Backend:
        def __init__(self, *, image_count: int = 2) -> None:
            self.image_count = image_count
            self.seen_paths: tuple[Path, ...] = ()

        @property
        def metadata(self):
            return {"kind": "witness_test"}

        def complete(self, request):
            self.seen_paths = request.image_paths
            return ModelReply(
                text=json.dumps(
                    {
                        "panel_1": {"color": "red", "shape": "triangle"},
                        "panel_2": {"color": "blue", "shape": "circle"},
                    }
                ),
                metadata={
                    "vision_input": {
                        "image_count": self.image_count,
                        "original_image_sizes": [[512, 384], [512, 384]],
                        "server_protocol_version": "test-native-multi-image",
                    }
                },
            )

    def test_witness_is_one_budgeted_ordered_two_image_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = BudgetLedger(max_model_calls=2, max_browser_transitions=0)
            backend = self.Backend()
            result = run_multi_image_witness(
                model=RecordedModel(backend, ledger=ledger), run_root=root, seed=7
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["returned_input_image_count"], 2)
            self.assertEqual(result["model_calls"], 1)
            self.assertEqual(ledger.model_calls, 1)
            self.assertEqual([path.name for path in backend.seen_paths], ["panel_01.png", "panel_02.png"])
            self.assertTrue((root / "online" / "preflight_witness" / "result.json").is_file())

    def test_witness_fails_closed_on_wrong_server_image_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = BudgetLedger(max_model_calls=2, max_browser_transitions=0)
            result = run_multi_image_witness(
                model=RecordedModel(self.Backend(image_count=1), ledger=ledger),
                run_root=root,
                seed=7,
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["model_calls"], 1)


class ValidatorModelHistoryTests(unittest.TestCase):
    def test_only_traceable_b4_extraction_is_removed_from_hidden_scan(self) -> None:
        extraction = '{"title":"VISIBLE_MODEL_INFERENCE"}'
        with tempfile.TemporaryDirectory() as tmp:
            unit = Path(tmp) / "unit"
            request_path = unit / "requests" / "request_0002.json"
            response_path = unit / "responses" / "request_0001.json"
            response_path.parent.mkdir(parents=True)
            response_path.write_text(
                json.dumps({"ok": True, "text": extraction}), encoding="utf-8"
            )
            payload = {
                "phase": "b4_decision",
                "system_prompt": "Use prior extraction.",
                "user_prompt": f"Model-generated chart extraction: {extraction}",
                "public_context": {"model_extraction": extraction},
            }
            scanned, traced = request_text_for_hidden_scan(request_path, payload)
            self.assertEqual(traced, extraction)
            self.assertNotIn("visible_model_inference", scanned)
            response_path.unlink()
            scanned, traced = request_text_for_hidden_scan(request_path, payload)
            self.assertEqual(traced, "")
            self.assertIn("visible_model_inference", scanned)


if __name__ == "__main__":
    unittest.main()
