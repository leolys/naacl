"""Offline only: fake HTTP sessions, no real endpoint or gold/old answers."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import runner
import requests

core = runner.core


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="runtime_runner_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = core.read(HERE / "config.json")
        self.catalog, self.inputs = runner.read_inputs(HERE / "prepared")

    def record(self, slug):
        entry = next(row for row in self.catalog["tasks"] if row["task_slug"] == slug)
        return runner.initial_record(entry, HERE / "prepared", "MOCK_SYNTHETIC_NOT_MODEL_OUTPUT")

    def budget(self):
        return runner.EstimatedBudget(self.root / "budget.json", self.config)

    def test_user_authorized_caps_cannot_be_raised_by_config_and_cli(self):
        for changes in ({"max_estimated_usd": 21}, {"max_request_attempts": 451},
                        {"max_estimated_usd": 1000, "max_request_attempts": 9000}):
            config = {**self.config, **changes}
            with self.subTest(changes=changes), patch.dict(runner.os.environ, {"MODEL_API_KEY": "mock-only"}):
                with self.assertRaisesRegex(ValueError, "configuration differs"):
                    runner.authorize_live(config, (config["max_estimated_usd"], config["max_request_attempts"]))

    def test_fixed_three_sanity_full_pipeline_and_exact_payload(self):
        for slug in runner.MOCK_SLUGS:
            with self.subTest(slug=slug), patch.object(core.requests, "Session", side_effect=AssertionError("network forbidden")):
                record, session = self.record(slug), runner.MockSession()
                before = copy.deepcopy(record["public_task"])
                preview = runner.request_preview(record, self.config)
                api = runner.RuntimeAPI(self.config, self.budget(), session=session)
                with runner.selected_validator():
                    for phase in runner.PHASES:
                        runner.parent.execute_phase(record, phase, self.root / slug, api, self.config)
                        self.assertEqual(record["status"][phase], "completed")
                self.assertEqual(session.calls[0], preview)
                self.assertEqual(len(session.calls), 3)
                self.assertEqual(record["public_task"], before)
                self.assertEqual(record["status"]["translation"], "not_run")
                self.assertEqual(record["provenance"]["execution_mode"], "MOCK_SYNTHETIC_NOT_MODEL_OUTPUT")
                self.assertIsNone(record["verification"]["recommendation"])
                self.assertTrue(record["citation_adapter"]["moves"])
                for request in session.calls:
                    context = json.loads(request["messages"][1]["content"][0]["text"])
                    runner.assert_public(context)
                    self.assertEqual(context["task"], before)
                    self.assertIn("policy_tables", context["task"])
                    self.assertIn("page_instructions", context["task"])
                    self.assertEqual(context["history"], [])
                    self.assertEqual(len(request["messages"]), 2)
                    self.assertTrue(request["messages"][1]["content"][2]["image_url"]["url"].startswith("data:image/"))
                self.assertEqual(session.calls[0]["messages"][0]["content"], core.PROPOSAL_PROMPT)
                self.assertEqual(session.calls[1]["messages"][0]["content"], core.GENERATOR)
                self.assertEqual(session.calls[2]["messages"][0]["content"], core.VERIFIER)

    def test_old_hint_projection_not_reintroduced(self):
        b001 = self.record("b001")["public_task"]
        pub003 = self.record("pub003")["public_task"]
        for row in (b001, pub003):
            self.assertNotIn("misleading", row["user_goal"].lower())
            self.assertNotIn("misleading", row["page_title"].lower())
        self.assertNotIn("reversed", pub003["user_goal"].lower())

    def test_private_nested_field_blocked_before_session(self):
        row, session = self.record("b001"), runner.MockSession()
        prompt, context, images = runner.parent.phase_input("proposal", row)
        context["task"]["policy_tables"].append({"gold": "forbidden fixture"})
        api = runner.RuntimeAPI(self.config, self.budget(), session=session)
        with self.assertRaisesRegex(ValueError, "private keys"):
            api.call(self.root / "private", "b001", "proposal", prompt, context, images)
        self.assertEqual(session.calls, [])
        self.assertEqual(api.budget.value["request_attempts"], 0)

    def test_disabled_live_and_unconfirmed_budget_cannot_construct_client(self):
        disabled = {**self.config, "live_enabled": False, "max_request_attempts": 0, "max_estimated_usd": 0}
        with patch.object(runner, "RuntimeAPI", side_effect=AssertionError("client should not construct")):
            for config, confirmation in ((disabled, (20, 450)), (self.config, None), (self.config, (20, 449))):
                with self.subTest(confirmation=confirmation), self.assertRaises(ValueError):
                    runner.execute(self.root / "live", HERE / "prepared", config, confirmed_budget=confirmation)
        self.assertFalse((self.root / "live").exists())

    def test_live_requires_environment_credential(self):
        with patch.dict(runner.os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "credential"):
            runner.authorize_live(self.config, (20, 450))

    def test_unknown_outcome_no_resend_and_terminal(self):
        row, session = self.record("b001"), runner.MockSession()
        with patch.object(session, "post", side_effect=requests.ReadTimeout("mock unknown outcome")) as send:
            api = runner.RuntimeAPI(self.config, self.budget(), session=session)
            with runner.selected_validator():
                runner.parent.execute_phase(row, "proposal", self.root / "unknown", api, self.config)
                runner.parent.execute_phase(row, "proposal", self.root / "unknown", api, self.config)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(row["status"]["proposal"], "failed")
        self.assertEqual(row["error"], "request_outcome_unknown_no_auto_retry")
        self.assertEqual(api.budget.value["request_attempts"], 1)

    def test_semantic_failure_is_not_resampled(self):
        row, session = self.record("b001"), runner.MockSession()
        api = runner.RuntimeAPI(self.config, self.budget(), session=session)
        bad = runner.MockResponse({"action": {"kind": "select", "option": "not public"}})
        with patch.object(session, "post", return_value=bad) as send, runner.selected_validator():
            runner.parent.execute_phase(row, "proposal", self.root / "invalid", api, self.config)
            runner.parent.execute_phase(row, "proposal", self.root / "invalid", api, self.config)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(row["status"]["proposal"], "invalid")
        self.assertFalse(runner.eligible(row))

    def test_interrupted_request_without_parsed_never_resends(self):
        row = self.record("b001")
        row["status"]["proposal"] = "running"
        row["stages"]["proposal"] = {"folder": "proposal/round_001"}
        session = runner.MockSession()
        api = runner.RuntimeAPI(self.config, self.budget(), session=session)
        runner.parent.execute_phase(row, "proposal", self.root / "interrupted", api, self.config)
        self.assertEqual(session.calls, [])
        self.assertEqual(row["error"], "interrupted_execution_outcome_unknown")

    def test_prepared_input_tamper_detected_before_snapshot(self):
        real_read = core.read
        def changed(path, *args, **kwargs):
            value = real_read(path, *args, **kwargs)
            if str(path).replace("\\", "/").endswith("tasks/b001/public.json"):
                value["task_alias"] = "wrong_alias"
            return value
        with patch.object(core, "read", side_effect=changed), self.assertRaisesRegex(ValueError, "identity"):
            runner.read_inputs(HERE / "prepared")

    def test_wrong_public_contract_rejected(self):
        row = self.record("b001")["public_task"]
        row.pop("policy_tables")
        with self.assertRaisesRegex(ValueError, "contract"):
            runner.public_check(row)

    def test_prepare_archive_no_client_same_config_resume_and_frozen_identity(self):
        output = self.root / "preview"
        with patch.object(runner, "RuntimeAPI", side_effect=AssertionError("no client during preparation")):
            summary = runner.prepare_only(output, HERE / "prepared", self.config)
            repeated = runner.prepare_only(output, HERE / "prepared", self.config, resume=True)
        self.assertEqual(summary, repeated)
        self.assertEqual(summary["real_model_requests"], 0)
        self.assertEqual(summary["status"], "PREPARED_NOT_SENT")
        self.assertEqual(summary["pending_tasks"], 140)
        self.assertEqual(len(list(output.glob("tasks/*/proposal/request_preview.json"))), 140)
        self.assertEqual(len(list(output.glob("tasks/*/generation/request.json"))), 0)
        self.assertEqual(len(list(output.glob("tasks/*/verification/request.json"))), 0)
        with self.assertRaises(FileExistsError):
            runner.prepare_only(output, HERE / "prepared", self.config)
        changed = {**self.config, "timeout_seconds": self.config["timeout_seconds"] + 1}
        # A deliberate refused resume leaves a manual-audit lock, tested by the reused RunLock suite.
        with self.assertRaisesRegex(ValueError, "Frozen"):
            runner.initialize(output, HERE / "prepared", changed, "LIVE_PROTOCOL_PREPARED", resume=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
