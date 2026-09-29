from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from ..build_targeted_recovery_cases import (
    model_visible_projection,
    model_visible_review_projection,
)
from ..formal_path_policy import REPO_ROOT
from ..run_targeted_recovery_pilot import (
    EventCollector,
    WORKFLOW_ON,
    base_fields_for_cell,
    build_registry,
    load_authoritative_case,
    parse_final_action,
)
from ..run_inherited_error_pilot import (
    LAYOUT_ID,
    NATIVE4_CONDITION,
    approved_f2_record,
    base_fields_for_cell as inherited_base_fields_for_cell,
    build_registry as build_inherited_registry,
    derive_layout_case,
)
from ..targeted_recovery import (
    F0_NEUTRAL_RECHECK,
    F1_CHECKLIST,
    F2_AUDITED_VALUES,
    F3_OUTCOME_CONTRADICTION,
    F3_PRE_REATTEMPT_CONTRADICTION,
    derive_run_from_events,
)
from ..targeted_recovery_app import (
    CompactRecoveryApp,
    ManagedCompactRecoveryServer,
    TargetedPathPolicy,
)
from ..targeted_recovery_scorer import CanonicalSubmissionScorer
from ..targeted_recovery_validator import CanonicalOutcomeValidator


class CompactRecoveryAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_authoritative_case(task_set="smoke17", slug="env008")
        cls.official = model_visible_projection(cls.case, "official")
        cls.official_chart = (REPO_ROOT / cls.official["chart_path"]).resolve()

    def app(self, workflow_mode="feedback_retry") -> CompactRecoveryApp:
        visible = self.official
        if workflow_mode == "feedback_retry":
            visible = {
                **self.official,
                "review": {"feedback_spec_id": F0_NEUTRAL_RECHECK},
            }
        return CompactRecoveryApp(
            visible_case=visible,
            repository_root=REPO_ROOT,
            chart_path=self.official_chart,
            workflow_mode=workflow_mode,
        )

    def test_renderer_refuses_projection_chart_swap(self) -> None:
        clean = model_visible_projection(self.case, "clean")
        clean_chart = (REPO_ROOT / clean["chart_path"]).resolve()
        with self.assertRaisesRegex(ValueError, "does not match"):
            CompactRecoveryApp(
                visible_case=self.official,
                repository_root=REPO_ROOT,
                chart_path=clean_chart,
                workflow_mode="feedback_retry",
            )

    def test_http_one_reversal_flow_and_no_scorer_leak(self) -> None:
        app = self.app()
        opener = build_opener(ProxyHandler({}))
        server_manager = ManagedCompactRecoveryServer(app)
        try:
            server_manager.start()
        except PermissionError:
            self.skipTest("test sandbox forbids loopback sockets")
        try:
            server = server_manager
            initial = opener.open(server.start_url).read().decode("utf-8")
            for forbidden in (
                "expected_action_id",
                "misleading_action_ids",
                "correct_route_solar_for_priority_contribution_review",
                "misleading_route_wind_for_priority_contribution_review",
            ):
                self.assertNotIn(forbidden, initial)

            def post(leaf, fields=None):
                body = urlencode(fields or {}).encode("utf-8")
                request = Request(
                    f"{server.start_url.rsplit('/', 1)[0]}/{leaf}",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                return opener.open(request).read().decode("utf-8")

            review = post("choose", {"choice": "choice_1"})
            self.assertIn("Route Wind", review)
            retry = post("revise")
            self.assertIn("Previous selection", retry)
            self.assertIn("Route Wind", retry)
            final = post("choose", {"choice": "choice_0"})
            self.assertIn("Final review", final)
            self.assertNotIn("Revise selection", final)
            self.assertNotIn("If you identify a mistake", final)
            done = post("submit")
            self.assertIn("Decision submitted", done)
        finally:
            server_manager.close()

        receipts = app.receipts_since(0)
        self.assertEqual(
            [receipt["kind"] for receipt in receipts],
            ["selection", "revision", "selection", "submission"],
        )
        self.assertEqual(app.snapshot()["selection_count"], 2)
        self.assertEqual(app.snapshot()["reversal_count"], 1)
        self.assertTrue(app.snapshot()["submitted"])

    def test_single_attempt_selection_submission_are_atomic(self) -> None:
        app = self.app("single_attempt")
        app.decision_page()
        self.assertEqual(app.choose("choice_2"), "done")
        selection, submission = app.receipts_since(0)
        self.assertEqual(selection["kind"], "selection")
        self.assertEqual(submission["kind"], "submission")
        self.assertEqual(selection["transaction_id"], submission["transaction_id"])
        self.assertTrue(submission["atomic_with_selection"])

    def test_inherited_f0_names_previous_operator_without_error_hint(self) -> None:
        app = CompactRecoveryApp(
            visible_case={
                **self.official,
                "review": {"feedback_spec_id": F0_NEUTRAL_RECHECK},
            },
            repository_root=REPO_ROOT,
            chart_path=self.official_chart,
            workflow_mode="feedback_retry",
            inherited_selection=True,
        )
        self.assertEqual(app.choose("choice_1"), "review")
        html = app.review_page().decode("utf-8")
        self.assertIn("Inherited selection from previous operator", html)
        self.assertIn("Route Wind", html)
        for forbidden in ("identify a mistake", "conflicts", "wrong", "correct"):
            self.assertNotIn(forbidden, html.casefold())

    def test_f3_feedback_is_visible_on_review_retry_and_final_review(self) -> None:
        app = CompactRecoveryApp(
            visible_case={
                **self.official,
                "review": {"feedback_spec_id": F3_OUTCOME_CONTRADICTION},
            },
            repository_root=REPO_ROOT,
            chart_path=self.official_chart,
            workflow_mode="feedback_retry",
            inherited_selection=True,
            outcome_feedback_enabled=True,
        )
        app.choose("choice_1")
        with self.assertRaisesRegex(ValueError, "not attached"):
            app.review_page()
        app.set_outcome_feedback(
            record_id="outcome:wind", choice_token="choice_1", contradiction=True
        )
        review = app.review_page().decode("utf-8")
        self.assertIn("previous operator", review)
        self.assertIn("conflicts with the independently verified", review)
        app.revise()
        retry = app.decision_page().decode("utf-8")
        self.assertIn("Previous selection", retry)
        self.assertIn("conflicts with the independently verified", retry)
        app.choose("choice_0")
        with self.assertRaisesRegex(ValueError, "not attached"):
            app.review_page()
        app.set_outcome_feedback(
            record_id="outcome:solar", choice_token="choice_0", contradiction=False
        )
        final = app.review_page().decode("utf-8")
        self.assertIn("consistent with the independently verified", final)

    def test_f3_pre_reattempt_stops_feedback_before_final_review(self) -> None:
        app = CompactRecoveryApp(
            visible_case={
                **self.official,
                "review": {
                    "feedback_spec_id": F3_PRE_REATTEMPT_CONTRADICTION
                },
            },
            repository_root=REPO_ROOT,
            chart_path=self.official_chart,
            workflow_mode="feedback_retry",
            inherited_selection=True,
            outcome_feedback_enabled=True,
        )
        app.choose("choice_1")
        app.set_outcome_feedback(
            record_id="outcome:wind", choice_token="choice_1", contradiction=True
        )
        review = app.review_page().decode("utf-8")
        self.assertIn("inherited selection does not agree", review)
        self.assertIn("Submission status", review)
        self.assertIn("Not submitted", review)
        app.revise()
        retry = app.decision_page().decode("utf-8")
        self.assertIn("outcome check on the previous selection", retry)
        self.assertIn("does not agree", retry)
        app.choose("choice_0")
        final = app.review_page().decode("utf-8")
        self.assertIn("Final review", final)
        self.assertIn("Not submitted", final)
        self.assertIn("Confirm selection", final)
        self.assertNotIn("Independent outcome check", final)
        self.assertNotIn("does not agree", final)

    def test_f3_pre_refuses_a_noncontradictory_inherited_outcome(self) -> None:
        app = CompactRecoveryApp(
            visible_case={
                **self.official,
                "review": {
                    "feedback_spec_id": F3_PRE_REATTEMPT_CONTRADICTION
                },
            },
            repository_root=REPO_ROOT,
            chart_path=self.official_chart,
            workflow_mode="feedback_retry",
            inherited_selection=True,
            outcome_feedback_enabled=True,
        )
        app.choose("choice_1")
        app.set_outcome_feedback(
            record_id="outcome:not-a-contradiction",
            choice_token="choice_1",
            contradiction=False,
        )
        with self.assertRaisesRegex(ValueError, "requires a contradictory"):
            app.review_page()

    def test_f1_feedback_region_is_answer_neutral(self) -> None:
        app = CompactRecoveryApp(
            visible_case={
                **self.official,
                "review": {"feedback_spec_id": F1_CHECKLIST},
            },
            repository_root=REPO_ROOT,
            chart_path=self.official_chart,
            workflow_mode="feedback_retry",
            inherited_selection=True,
        )
        app.choose("choice_1")
        review = app.review_page().decode("utf-8")
        feedback = review.split("data-feedback-region='checklist'>", 1)[1].split(
            "</div>", 1
        )[0]
        self.assertIn("printed values", feedback)
        for forbidden in (
            "Solar",
            "41.2",
            "correct",
            "choice_0",
            "position",
        ):
            self.assertNotIn(forbidden.casefold(), feedback.casefold())
        app.revise()
        retry = app.decision_page().decode("utf-8")
        self.assertIn("Review checklist", retry)

    def test_f2_projection_uses_only_approved_visible_payload(self) -> None:
        derived = derive_layout_case(self.case, "cyclic_shift_2")
        registry = build_inherited_registry(derived, "cyclic_shift_2")
        evidence_id = approved_f2_record(
            derived, layout_id="cyclic_shift_2"
        )["record_id"]
        visible = model_visible_review_projection(
            derived,
            "official",
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id=evidence_id,
            registry=registry,
        )
        chart = (REPO_ROOT / visible["chart_path"]).resolve()
        app = CompactRecoveryApp(
            visible_case=visible,
            repository_root=REPO_ROOT,
            chart_path=chart,
            workflow_mode="feedback_retry",
            inherited_selection=True,
        )
        wind_token = next(
            token
            for token, action_id in derived["runner_only"][
                "choice_token_to_action_id"
            ].items()
            if action_id in derived["runner_only"]["misleading_action_ids"]
        )
        app.choose(wind_token)
        review = app.review_page().decode("utf-8")
        self.assertIn("Reviewed source values", review)
        self.assertIn("41.2%", review)
        self.assertIn("Solar</strong> — 41.2%", review)
        self.assertNotIn("reported production percentage</strong>", review)
        feedback = review.split(
            "data-feedback-region='reviewed-values'>", 1
        )[1].split("</div>", 1)[0]
        for forbidden in ("reviewed_by", "record_id", "choice_0", "ground_truth"):
            self.assertNotIn(forbidden, feedback)

        base = inherited_base_fields_for_cell(
            case=derived,
            trial_id="trial:f2-provenance",
            run_id="run:f2-provenance",
            arm="official",
            condition=NATIVE4_CONDITION,
            evidence_level=F2_AUDITED_VALUES,
            layout_id="cyclic_shift_2",
        )
        bound = registry.bind_base_fields(base)
        self.assertEqual(
            bound["evidence_review_status"],
            "agent_cross_checked_nonreportable",
        )
        self.assertIn("official:csv:", bound["evidence_source"])
        self.assertIn("clean:figure:", bound["evidence_source"])

    def test_f2_diagnostic_rejects_facts_not_bound_to_source_csv(self) -> None:
        derived = derive_layout_case(self.case, "cyclic_shift_2")
        forged = approved_f2_record(derived, layout_id="cyclic_shift_2")
        forged["model_visible_payload"]["facts"][0]["object"] = "999.9%"
        with patch(
            "web_agent_benchmark.evaluation.gui_reflection_baseline."
            "run_inherited_error_pilot.approved_f2_record",
            return_value=forged,
        ):
            with self.assertRaisesRegex(ValueError, "do not match canonical CSV"):
                build_inherited_registry(derived, "cyclic_shift_2")

    def test_path_policy_rejects_unknown_document(self) -> None:
        app = self.app()
        server_manager = ManagedCompactRecoveryServer(app)
        try:
            server_manager.start()
        except PermissionError:
            self.skipTest("test sandbox forbids loopback sockets")
        try:
            server = server_manager
            policy = TargetedPathPolicy.from_start_url(server.start_url)
            unknown = server.start_url.rsplit("/", 1)[0] + "/debug"
            with self.assertRaisesRegex(Exception, "escaped"):
                policy.assert_document_url(unknown)
            self.assertFalse(policy.is_allowed_request(unknown, "document"))
        finally:
            server_manager.close()


class TargetedCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_authoritative_case(task_set="smoke17", slug="env008")
        cls.registry = build_registry(cls.case)

    def test_collector_events_replay_to_stable_recovery(self) -> None:
        from PIL import Image

        base = base_fields_for_cell(
            pair_group_id=self.case["pair_group_id"],
            trial_id="trial:test",
            run_id="run:test:official:on",
            arm="official",
            condition=WORKFLOW_ON,
        )
        bound = self.registry.bind_base_fields(base)
        collector = EventCollector(bound)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = root / "initial.png"
            review = root / "review.png"
            retry = root / "retry.png"
            final = root / "final.png"
            for path in (initial, review, retry, final):
                Image.new("RGB", (1280, 960), "white").save(path)
            collector.selection(
                receipt={"choice_token": "choice_1", "control_position": 1},
                input_state="initial_decision",
                input_snapshot={"current_choice_token": None},
                screenshot_path=initial,
                model_step_id="step:0",
                model_response_id="response:0",
                execution_receipt_id="execution:0",
            )
            collector.observation(
                state="review",
                screenshot_path=review,
                model_step_id="step:1",
                provisional_token="choice_1",
            )
            collector.reversal(
                action_type="PRESS_BACK",
                receipt={"from_state": "review", "to_state": "retry_decision"},
                model_step_id="step:1",
                model_response_id="response:1",
                execution_receipt_id="execution:1",
            )
            collector.selection(
                receipt={"choice_token": "choice_0", "control_position": 0},
                input_state="retry_decision",
                input_snapshot={"current_choice_token": "choice_1"},
                screenshot_path=retry,
                model_step_id="step:2",
                model_response_id="response:2",
                execution_receipt_id="execution:2",
            )
            collector.observation(
                state="final_review",
                screenshot_path=final,
                model_step_id="step:3",
                provisional_token="choice_0",
            )
            claim = collector.submission(
                receipt={
                    "choice_token": "choice_0",
                    "control_position": 0,
                    "transaction_id": "submit1",
                },
                model_step_id="step:3",
                model_response_id="response:3",
                execution_receipt_id="execution:3",
            )
            scorer = CanonicalSubmissionScorer(task_set="smoke17", slug="env008")
            scorer_record = scorer.score(
                submission_id=claim["submission_id"],
                pair_group_id=bound["pair_group_id"],
                task_instance_id=bound["task_instance_id"],
                arm=bound["arm"],
                choice_token=claim["choice_token"],
                control_position=claim["control_position"],
            )
            collector.scorer_result(scorer_record)
            run = derive_run_from_events(bound, collector.events)

        self.assertEqual(scorer_record.selected_action_id, bound["correct_action_id"])
        self.assertTrue(scorer_record.success)
        self.assertTrue(run.reversal_returned_to_retry)
        self.assertEqual(
            run.initial_selected_action_id, bound["misleading_action_ids"][0]
        )
        self.assertEqual(run.final_selected_action_id, bound["correct_action_id"])
        self.assertTrue(run.final_submission_success)

    def test_final_action_parser_ignores_thought_action_words(self) -> None:
        action = parse_final_action(
            "<THOUGHT>: I should not PRESS_BACK.\n<ACTION>: CLICK[[500, 500]]",
            1280,
            960,
        )
        self.assertEqual(action.action_type, "CLICK")
        self.assertEqual(action.parameters, (640, 480))

    def test_role_blind_layout_is_independently_scored_and_validated(self) -> None:
        derived = derive_layout_case(self.case)
        cards = derived["model_visible_shared"]["action_cards"]
        self.assertEqual(
            [card["choice_token"] for card in cards],
            ["choice_1", "choice_2", "choice_0"],
        )
        self.assertEqual(derived["runner_only"]["display_expected_action_index"], 2)
        scorer = CanonicalSubmissionScorer(
            task_set="smoke17", slug="env008", layout_id=LAYOUT_ID
        )
        official_instance = derived["arms"]["official"]["task_instance_id"]
        score = scorer.score(
            submission_id="submission:test",
            pair_group_id=derived["pair_group_id"],
            task_instance_id=official_instance,
            arm="official",
            choice_token="choice_0",
            control_position=2,
        )
        self.assertTrue(score.success)
        with self.assertRaisesRegex(ValueError, "token/position"):
            scorer.score(
                submission_id="submission:bad",
                pair_group_id=derived["pair_group_id"],
                task_instance_id=official_instance,
                arm="official",
                choice_token="choice_0",
                control_position=0,
            )
        validator = CanonicalOutcomeValidator(
            task_set="smoke17", slug="env008", layout_id=LAYOUT_ID
        )
        wind = validator.validate(
            pair_group_id=derived["pair_group_id"],
            task_instance_id=official_instance,
            arm="official",
            choice_token="choice_1",
            control_position=0,
        )
        solar = validator.validate(
            pair_group_id=derived["pair_group_id"],
            task_instance_id=official_instance,
            arm="official",
            choice_token="choice_0",
            control_position=2,
        )
        self.assertTrue(wind.contradiction)
        self.assertFalse(solar.contradiction)

        l2 = derive_layout_case(self.case, "cyclic_shift_2")
        self.assertEqual(
            [
                card["choice_token"]
                for card in l2["model_visible_shared"]["action_cards"]
            ],
            ["choice_2", "choice_0", "choice_1"],
        )
        self.assertEqual(l2["runner_only"]["display_expected_action_index"], 1)
        l2_scorer = CanonicalSubmissionScorer(
            task_set="smoke17", slug="env008", layout_id="cyclic_shift_2"
        )
        l2_instance = l2["arms"]["official"]["task_instance_id"]
        l2_score = l2_scorer.score(
            submission_id="submission:l2",
            pair_group_id=l2["pair_group_id"],
            task_instance_id=l2_instance,
            arm="official",
            choice_token="choice_0",
            control_position=1,
        )
        self.assertTrue(l2_score.success)
        l2_validator = CanonicalOutcomeValidator(
            task_set="smoke17", slug="env008", layout_id="cyclic_shift_2"
        )
        l2_wind = l2_validator.validate(
            pair_group_id=l2["pair_group_id"],
            task_instance_id=l2_instance,
            arm="official",
            choice_token="choice_1",
            control_position=2,
        )
        self.assertTrue(l2_wind.contradiction)


if __name__ == "__main__":
    unittest.main()
