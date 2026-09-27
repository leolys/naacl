"""Targeted accounting tests; optional real-browser, scripted two-backbone fixture."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from research.decision_evidence_audit import core, models, runner
from .api_backend import ApiStop
from .mock_browser import RouteMock
from .panel import (BACKBONES, PREPARED, ModelBudget, PrefixTransitions, PrefixTransitionLimit,
                    cost, initial_rows, load_raw, execute_schedule, offline_report,
                    public_unit, readiness, validate_schedule, snapshot_sources, reported_usage, verification_attempts)
from .panel_controls import qualify, route_task


def fixture_manifest():
    schedule = []
    for arm in ("official140", "clean140"):
        for name in BACKBONES:
            schedule.append(dict(ordinal=len(schedule) + 1, task_slug="synthetic_route", arm=arm,
                                 model=name, strategies=["B0", "B2", "B3"], task_alias="control"))
    return dict(rows=[dict(task_slug="synthetic_route", public_task=route_task())], case_interleaved_order=schedule)


def fixture_raw(_row, _arm):
    return dict(action_space=[dict(label="Route A", action_id="a"), dict(label="Route B", action_id="b")],
                expected_action_id="a", misleading_action_ids=["b"])


class PanelTests(unittest.TestCase):
    def test_per_backbone_and_shared_budget_count_once(self):
        ledger = core.BudgetLedger(max_model_calls=3)
        a, b = ModelBudget(ledger, "M_small", 1), ModelBudget(ledger, "M_strong", 2)
        a.charge_model(phase="prefix", request_id="r1")
        with self.assertRaises(core.BudgetExceeded):
            a.charge_model(phase="prefix", request_id="r2")
        b.charge_model(phase="prefix", request_id="r1")
        self.assertEqual(ledger.model_calls, 2)
        self.assertEqual([e["request_id"] for e in ledger.events], ["M_small/r1", "M_strong/r1"])

    def test_controls_not_free_and_failures_not_released(self):
        ledger = core.BudgetLedger(max_model_calls=50)
        view = ModelBudget(ledger, "M_small", 17)
        for i in range(16):
            view.charge_model(phase="control", request_id=str(i))
        with self.assertRaises(core.BudgetExceeded):
            view.charge_model(phase="control", request_id="blocked")
        view.section = "panel"
        view.charge_model(phase="prefix", request_id="last")
        with self.assertRaises(core.BudgetExceeded):
            view.charge_model(phase="prefix", request_id="blocked_again")
        self.assertEqual(ledger.model_calls, 17)

    def test_actual_replay_cost_and_global_transition_cap(self):
        ledger = core.BudgetLedger(max_browser_transitions=1)
        view = ModelBudget(ledger, "M_small", 400)
        view.charge_transition(phase="replay_initial", action=dict(action="goto", url="/task/control"))
        with self.assertRaises(core.BudgetExceeded):
            view.charge_transition(phase="actual_submit", action=dict(action="click_button", text="Submit Form"))
        self.assertEqual(cost(ledger.events), dict(model_call_attempts=0, browser_transitions=1, replay_transitions=1))

    def test_prepared_schedule_retained_and_all_rows_exist_before_execution(self):
        manifest = json.loads((PREPARED / "TASK_MANIFEST.json").read_text())
        original = copy.deepcopy(manifest)
        validate_schedule(manifest)
        table = initial_rows(manifest["case_interleaved_order"])
        self.assertEqual(len(table), 96)
        self.assertTrue(all(r["status"] == "not_run" for r in table))
        self.assertEqual(manifest, original)

    def test_no_single_model_panel_or_duplicate_unit(self):
        manifest = fixture_manifest()
        manifest["case_interleaved_order"].pop()
        with self.assertRaises(ValueError):
            validate_schedule(manifest)

    def test_preparation_config_still_denies_generation(self):
        cfg = json.loads((PREPARED / "MODEL_CONFIG.json").read_text())
        self.assertIn("money_cap_usd", readiness(cfg, check_credential=False))
        self.assertIn("this_panel_local_service_or_GPU_permission", readiness(cfg, check_credential=False))

    def test_offline_dataset_lookup_and_public_projection_all_preselected_arms(self):
        manifest = json.loads((PREPARED / "TASK_MANIFEST.json").read_text())
        for row in manifest["rows"]:
            for arm in ("official140", "clean140"):
                raw = load_raw(row, arm)
                public, path = public_unit(row, arm)
                self.assertEqual(core.public_task_projection(raw, task_alias=row["task_alias"]), public)
                self.assertTrue(path.is_file())

    def test_zero_error_checkpoint_recovery_is_na_and_unrun_not_failure(self):
        manifest = fixture_manifest()
        rows = initial_rows(manifest["case_interleaved_order"])
        with tempfile.TemporaryDirectory() as temp:
            report = offline_report(manifest, dict(rows=rows), core.BudgetLedger(), Path(temp), raw_loader=fixture_raw, mock=True)
            for group in report["groups"]:
                self.assertEqual(group["checkpoint_count"], 0)
                for strategy in group["strategies"]:
                    self.assertEqual(strategy["recovery_fraction"], "N/A")
                    self.assertEqual(strategy["outcomes"], {"not_run": 1})

    def test_reported_tokens_include_shared_prefix_and_keep_missing_usage_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core.write_json(root / "prefix/responses/a.json", dict(metadata=dict(usage=dict(prompt_tokens=100, completion_tokens=20))))
            core.write_json(root / "B2/responses/b.json", dict(metadata=dict(usage=dict(prompt_tokens=50, completion_tokens=10))))
            core.write_json(root / "B2/responses/c.json", dict(ok=False, error_type="ApiStop"))
            usage = reported_usage(root / "prefix", root / "B2")
            self.assertEqual(usage["prompt_tokens_reported"], 150)
            self.assertEqual(usage["completion_tokens_reported"], 30)
            self.assertEqual(usage["missing_token_records"], 1)
            self.assertFalse(usage["usage_complete"])

    def test_failed_verifier_call_not_counted_as_unrun(self):
        ledger = core.BudgetLedger()
        view = ModelBudget(ledger, "M_strong", 400)
        view.section = "panel"
        view.charge_model(phase="b3_plan", request_id="failed_remote_response")
        self.assertEqual(verification_attempts(ledger.events), 1)

    def test_correct_receipt_without_confirmation_is_not_recovery(self):
        manifest = fixture_manifest()
        rows = initial_rows(manifest["case_interleaved_order"])
        for row in rows:
            row.update(prefix_started=True, checkpoint_reached=True, checkpoint_selection="Route B",
                submitted=True, server_receipts=[{"selected_option_label": "Route A"}], confirmation_observed=False)
        with tempfile.TemporaryDirectory() as temp:
            report = offline_report(manifest, dict(rows=rows), core.BudgetLedger(), Path(temp), raw_loader=fixture_raw, mock=True)
            for group in report["groups"]:
                for strategy in group["strategies"]:
                    self.assertEqual(strategy["recovered_from_shared_error"], 0)
                    self.assertEqual(strategy["submitted_without_confirmed_completion"], 1)

    def test_local_prefix_cap_is_distinct_from_global_exhaustion(self):
        ledger = core.BudgetLedger(max_browser_transitions=2)
        scope = PrefixTransitions(ModelBudget(ledger, "M_small", 400), cap=1)
        scope.charge_transition(phase="initial", action={"action": "goto", "url": "/task/control"})
        with self.assertRaises(PrefixTransitionLimit):
            scope.charge_transition(phase="initial", action={"action": "goto", "url": "/task/control"})
        self.assertEqual(ledger.browser_transitions, 1)

    def test_api_stop_preserves_remaining_rows_and_does_not_fallback(self):
        manifest = fixture_manifest()
        # Start this fixture with the strong backend, then a local one; stop must reach neither retry nor local.
        for unit in manifest["case_interleaved_order"]:
            unit["model"] = "M_strong" if unit["model"] == "M_small" else "M_small"
        ledger = core.BudgetLedger()
        views = {name: ModelBudget(ledger, name, 400) for name in BACKBONES}
        model = Mock()
        def fail(*args, **kwargs):
            views["M_strong"].charge_model(phase="prefix", request_id="failed")
            raise ApiStop("scripted route mismatch")
        executor = Mock(receipts=[])
        with tempfile.TemporaryDirectory() as temp, patch.object(runner, "managed_shell", return_value=nullcontext(SimpleNamespace(base_url="http://localhost"))), \
                patch.object(runner, "BrowserExecutor", return_value=executor), \
                patch("research.prospective_simple_check_pilot.panel.capture_pending", side_effect=fail) as capture:
            result = execute_schedule(Mock(), manifest, {name: model for name in BACKBONES}, views, ledger,
                Path(temp), resolve_public=lambda row, arm: (route_task(), Path(temp) / "unused.png"))
        self.assertEqual(capture.call_count, 1)
        self.assertEqual(ledger.model_calls, 1)
        self.assertEqual(len(result["rows"]), 12)
        self.assertEqual(sum(r["prefix_started"] for r in result["rows"]), 3)
        self.assertTrue(all(not r["verification_executed"] and not r["submitted"] for r in result["rows"]))


class ImageRouteMock(RouteMock):
    def complete(self, request):
        if request.phase == "multi_image_control":
            colors = []
            for path in request.image_paths:
                with Image.open(path) as im:
                    colors.append("red" if im.getpixel((0, 0))[0] > im.getpixel((0, 0))[2] else "blue")
            return models.ModelReply(json.dumps(dict(colors=colors)), dict(mock=True))
        return super().complete(request)


def browser_fixture(output, browser_path):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    snapshot_sources(root)
    ledger = core.BudgetLedger(max_model_calls=90, max_browser_transitions=200)
    ledger.bind_snapshot(root / "mock_budget.json")
    backends = {name: ImageRouteMock() for name in BACKBONES}
    views = {name: ModelBudget(ledger, name, 45) for name in BACKBONES}
    recorded = {name: models.RecordedModel(backends[name], ledger=views[name]) for name in BACKBONES}
    blank = root / "blank.png"
    Image.new("RGB", (300, 180), "white").save(blank)
    manifest = fixture_manifest()
    with runner.require_playwright()() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(browser_path), args=list(runner.BROWSER_LAUNCH_ARGS), timeout=20000)
        try:
            for name in BACKBONES:
                controls = qualify(browser, recorded[name], views[name], root / "online" / "controls" / name)
                assert len(controls) == 6 and all(r["passed"] for r in controls)
            # Software-only intentional contrast; never used on benchmark tasks.
            backends["M_small"].initial_wrong = True
            result = execute_schedule(browser, manifest, recorded, views, ledger, root,
                resolve_public=lambda row, arm: (row["public_task"], blank))
        finally:
            browser.close()
    summary = offline_report(manifest, result, ledger, root, raw_loader=fixture_raw, mock=True)
    assert not (root / "stop.json").exists(), "unexpected scheduler stop; inspect artifacts"
    assert len(result["prefixes"]) == 4 and len(result["rows"]) == 12
    assert all(r["submitted"] and r["confirmation_observed"] for r in result["rows"])
    for row in result["rows"]:
        expected_prefix = "Route B" if row["model"] == "M_small" else "Route A"
        assert row["checkpoint_selection"] == expected_prefix
        if row["strategy"] == "B0":
            assert row["actor_final_submission"]["option"] == expected_prefix
            assert row["incremental_cost"]["model_call_attempts"] == 0
        else:
            assert row["verifier_recommendation"] == row["executor_selection"] == row["actor_final_submission"]["option"] == "Route A"
        assert row["independent_deployment_cost"]["model_call_attempts"] == row["prefix_cost"]["model_call_attempts"] + row["incremental_cost"]["model_call_attempts"]
        assert row["independent_deployment_cost"]["replay_transitions"] == 0
    # Costs partition exactly, including setup controls and physical replay.
    core.write_json(root / "result.json", dict(status="passed", real_model_calls=0, real_api_generation_calls=0,
        mock_model_calls=ledger.model_calls, actual_browser_transitions=ledger.browser_transitions,
        control_scenarios=12, synthetic_prefixes=4, synthetic_strategy_trajectories=12,
        actual_localhost_submit_receipts=20, scope="scripted_nonchart_engineering_only"))
    print(json.dumps(json.loads((root / "result.json").read_text()), indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    browser_fixture(args.output, args.browser)
