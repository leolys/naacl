"""Offline safety/continuation tests. All HTTP sessions are fakes."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import requests

import batch_runner as batch
from budget import BudgetedPanelAPI, EstimatedBudget

core = batch.core


class Response:
    def __init__(self, status=200, usage=None, content="{}", error=None):
        self.status_code = status
        self.body = {"model": "gpt-5.6-terra", "id": "offline-fake",
                     "choices": [{"finish_reason": "stop", "message": {"content": content}}]}
        if usage is not None:
            self.body["usage"] = usage
        if error is not None:
            self.body["error"] = error

    def json(self):
        return self.body


class Session:
    def __init__(self, budget, responses):
        self.proxies = {}
        self.budget, self.responses = budget, iter(responses)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        persisted = core.read(self.budget.path)
        assert persisted["request_attempts"] == self.calls
        assert persisted["events"][-1]["charged_estimated_usd"] == 0.2
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test_", dir=str(batch.HERE))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = core.read(batch.HERE / "config.json")

    def budget(self):
        return EstimatedBudget(self.root / "budget.json", self.config)

    def invoke(self, budget, responses):
        session = Session(budget, responses)
        api = BudgetedPanelAPI(self.config, budget, session=session)
        with patch.object(core.time, "sleep"):
            value = api.call(self.root / "phase" / "round_001", "fake", "proposal", "offline", {}, [])
        return session, value

    def test_reservation_precedes_http_and_alias_usage_ignores_cache_discount(self):
        budget = self.budget()
        session, value = self.invoke(budget, [Response(usage={"prompt_tokens": 0, "completion_tokens": 0,
            "billing_usage": {"openai_usage": {"input_tokens": 1000, "output_tokens": 100,
                "input_tokens_details": {"cached_tokens": 900}}}})])
        self.assertEqual(session.calls, 1)
        self.assertEqual(value, {})
        self.assertAlmostEqual(budget.value["estimated_ledger_usd"], 0.0037)
        self.assertEqual(budget.value["events"][0]["accounting_status"], "usage_reconciled")

    def test_all_transport_retries_are_charged_and_maximum_is_three(self):
        budget = self.budget()
        responses = [Response(503), Response(502), Response(200, {"input_tokens": 1000, "output_tokens": 100})]
        session, _ = self.invoke(budget, responses)
        self.assertEqual(session.calls, 3)
        self.assertEqual(budget.value["request_attempts"], 3)
        self.assertAlmostEqual(budget.value["estimated_ledger_usd"], 0.4037)

    def test_retry_budget_cannot_send_a_fourth_attempt(self):
        budget = self.budget()
        session = Session(budget, [Response(503)] * 4)
        api = BudgetedPanelAPI(self.config, budget, session=session)
        with patch.object(core.time, "sleep"), self.assertRaises(RuntimeError):
            api.call(self.root / "phase" / "round_001", "fake", "proposal", "offline", {}, [])
        self.assertEqual(session.calls, 3)
        self.assertEqual(budget.value["request_attempts"], 3)

    def test_unknown_outcome_is_not_resent_and_retains_reserve(self):
        budget = self.budget()
        session = Session(budget, [requests.ReadTimeout("offline")])
        api = BudgetedPanelAPI(self.config, budget, session=session)
        with self.assertRaises(core.UnknownRequestOutcome):
            api.call(self.root / "phase" / "round_001", "fake", "proposal", "offline", {}, [])
        self.assertEqual(session.calls, 1)
        self.assertEqual(self.budget().value["estimated_ledger_usd"], 0.2)

    def test_bad_json_is_not_quality_retried(self):
        budget = self.budget()
        session = Session(budget, [Response(content="not json")])
        api = BudgetedPanelAPI(self.config, budget, session=session)
        with self.assertRaises(RuntimeError):
            api.call(self.root / "phase" / "round_001", "fake", "proposal", "offline", {}, [])
        self.assertEqual(session.calls, 1)

    def test_missing_or_conflicting_usage_keeps_reservation(self):
        for usage in (None, {"prompt_tokens": 100, "input_tokens": 200, "output_tokens": 10}):
            with self.subTest(usage=usage):
                nested = self.root / ("case_" + str(len(list(self.root.iterdir()))))
                budget = EstimatedBudget(nested / "budget.json", self.config)
                session = Session(budget, [Response(usage=usage)])
                api = BudgetedPanelAPI(self.config, budget, session=session)
                api.call(nested / "round_001", "fake", "proposal", "offline", {}, [])
                self.assertEqual(budget.value["estimated_ledger_usd"], 0.2)
                self.assertEqual(budget.value["events"][0]["accounting_status"], "unknown_usage_reserve_retained")

    def test_money_cap_stops_before_network_and_stays_blocked(self):
        self.config["max_estimated_usd"] = 0.2
        budget = self.budget()
        self.invoke(budget, [Response()])
        api = BudgetedPanelAPI(self.config, budget, session=Session(budget, []))
        with self.assertRaises(core.ServiceStop):
            api.call(self.root / "second", "fake", "proposal", "offline", {}, [])
        self.assertEqual(api.session.calls, 0)
        reloaded = self.budget()
        self.assertEqual(reloaded.value["request_attempts"], 1)
        self.assertEqual(reloaded.value["blocked_reason"], "local_estimated_usd_budget_exhausted")

    def test_attempt_cap_survives_reload(self):
        self.config["max_request_attempts"] = 1
        budget = self.budget()
        self.invoke(budget, [Response(usage={"input_tokens": 1, "output_tokens": 1})])
        reloaded = self.budget()
        reloaded.current_folder = self.root / "second"
        with self.assertRaises(core.ServiceStop):
            reloaded.charge({"task_slug": "fake", "phase": "proposal", "round": "second", "attempt": 1})
        self.assertEqual(reloaded.value["request_attempts"], 1)

    def test_api_translation_is_rejected_without_charge(self):
        budget = self.budget()
        api = BudgetedPanelAPI(self.config, budget, session=Session(budget, []))
        with self.assertRaises(ValueError):
            api.call(self.root / "translation", "fake", "translation", "offline", {}, [])
        self.assertEqual(budget.value["request_attempts"], 0)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test_", dir=str(batch.HERE))
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "run"

    def test_lock_exclusion_and_crash_diagnostic(self):
        with batch.RunLock(self.output):
            with self.assertRaises(RuntimeError):
                with batch.RunLock(self.output):
                    self.fail("second lock acquired")
        self.assertFalse(self.output.with_name("run.lock").exists())
        with self.assertRaises(ValueError):
            with batch.RunLock(self.output):
                raise ValueError("simulated crash")
        self.assertTrue(self.output.with_name("run.lock").exists())

    def test_modified_public_task_rejected_before_freeze(self):
        entry = core.read(batch.PANEL / "catalog.json")["tasks"][1]
        data_root = Path(self.temporary.name) / "data_copy"
        for key in ("public_file", "chart_file", "offline_file"):
            destination = data_root / entry[key]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(batch.PANEL / entry[key], destination)
        catalog = {"tasks": [entry]}
        self.assertEqual(len(batch.input_manifest(catalog, data_root)), 1)
        public_path = data_root / entry["public_file"]
        modified = core.read(public_path)
        modified["option_labels"][0] += " modified"
        core.dump(public_path, modified)
        with self.assertRaisesRegex(ValueError, "public task differs from prepared dataset provenance"):
            batch.input_manifest(catalog, data_root)
        self.assertFalse(self.output.exists())

    def test_remapped_catalog_entry_rejected(self):
        entry = dict(core.read(batch.PANEL / "catalog.json")["tasks"][1])
        entry["alias"] = "task_999"
        with self.assertRaisesRegex(ValueError, "catalog/public/offline task identity mismatch"):
            batch.input_manifest({"tasks": [entry]}, batch.PANEL)

    def test_reordered_or_wrong_schema_catalog_rejected_before_freeze(self):
        data_root = Path(self.temporary.name) / "catalog_copy"
        config = core.read(batch.HERE / "config.json")
        for mutation in ("order", "schema"):
            with self.subTest(mutation=mutation):
                catalog = core.read(batch.PANEL / "catalog.json")
                if mutation == "order":
                    catalog["tasks"][1], catalog["tasks"][2] = catalog["tasks"][2], catalog["tasks"][1]
                else:
                    catalog["schema_version"] = "unknown"
                core.dump(data_root / "catalog.json", catalog)
                with self.assertRaisesRegex(ValueError, "fixed original 140 task catalog mismatch"):
                    batch.initialize(self.output, data_root, config)
                self.assertFalse(self.output.exists())

    def test_invalid_failed_cases_are_terminal_but_running_can_recover(self):
        for status in ("invalid", "failed"):
            record = {"status": {"proposal": "completed", "generation": status, "verification": "not_run"}}
            self.assertFalse(batch.eligible(record))
        record["status"]["generation"] = "running"
        self.assertTrue(batch.eligible(record))

    def test_prepare_reuse_resume_failure_skip_and_frozen_config(self):
        def forbidden(*args):
            self.fail("preparation must not construct API client")
        summary = batch.run(self.output, prepare_only=True, api_factory=forbidden)
        self.assertEqual(summary["total_tasks"], 140)
        self.assertEqual(summary["all_three_stages_complete"], 2)
        self.assertEqual(summary["request_attempts"], 0)
        for slug in batch.REUSED:
            row = core.read(self.output / "tasks" / slug / "record.json")
            self.assertEqual(row["translations"], {"items": {}})
            self.assertEqual(row["status"]["translation"], "not_run")
            self.assertNotIn("translation", row["stages"])
            self.assertFalse((self.output / "tasks" / slug / "translation").exists())
            self.assertEqual(set(row["provenance"]["reuse"]["source_phase_files_sha256"]), set(batch.PHASES))
        called = []
        class FailedAPI:
            def __init__(self, *args):
                pass
            def call(self, folder, slug, phase, *args):
                called.append((slug, phase))
                raise RuntimeError("offline fake failure")
        batch.run(self.output, resume=True, limit=1, api_factory=FailedAPI)
        batch.run(self.output, resume=True, limit=1, api_factory=FailedAPI)
        self.assertEqual(called, [("b002", "proposal"), ("b003", "proposal")])
        row = core.read(self.output / "tasks" / "b002" / "record.json")
        self.assertEqual(row["status"]["generation"], "not_run")
        altered = core.read(batch.HERE / "config.json")
        altered["temperature"] = 0.1
        with self.assertRaises(ValueError):
            batch.run(self.output, config=altered, resume=True, prepare_only=True)

    def test_service_stop_is_sticky_and_resume_does_not_construct_client(self):
        batch.run(self.output, prepare_only=True)
        def stopped(*args):
            raise core.ServiceStop("server_quota_exceeded")
        first = batch.run(self.output, resume=True, limit=1, api_factory=stopped)
        self.assertEqual(first["blocked_reason"], "server_quota_exceeded")
        def forbidden(*args):
            self.fail("blocked run must not create API client")
        second = batch.run(self.output, resume=True, api_factory=forbidden)
        self.assertEqual(second["blocked_reason"], "server_quota_exceeded")
        self.assertEqual(second["request_attempts"], 0)

    def test_interrupted_running_phase_with_no_parsed_result_never_resends(self):
        entry = core.read(batch.PANEL / "catalog.json")["tasks"][1]
        record = batch.parent.initial_record(entry, batch.PANEL)
        record["status"]["proposal"] = "running"
        record["stages"]["proposal"] = {"folder": "proposal/round_001"}
        calls = []
        class ForbiddenAPI:
            def call(self, *args):
                calls.append(args)
                raise AssertionError("unknown outcome must not be resent")
        batch.parent.execute_phase(record, "proposal", self.output, ForbiddenAPI(),
                                   core.read(batch.HERE / "config.json"))
        self.assertEqual(record["status"]["proposal"], "failed")
        self.assertEqual(record["error"], "interrupted_execution_outcome_unknown")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
