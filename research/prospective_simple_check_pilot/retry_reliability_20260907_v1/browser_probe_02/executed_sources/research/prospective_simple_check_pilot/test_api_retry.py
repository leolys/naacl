"""Transport fault injection; no real gateway, model, GPU, or benchmark resampling."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import requests
from PIL import Image

from research.decision_evidence_audit import core, models, runner
from .api_backend import ApiStop, IntranetApiBackend, retry_after_seconds
from .harness import capture_pending, run_branch
from .panel import ModelBudget, reported_usage, snapshot_sources
from .panel_controls import route_task
from .test_preparation import config, response


class SequenceSession:
    def __init__(self, events, on_call=None):
        self.events, self.calls, self.on_call = list(events), [], on_call

    def post(self, url, **kwargs):
        self.calls.append((url, copy.deepcopy(kwargs)))
        if self.on_call:
            self.on_call(len(self.calls))
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        status, data, headers = event
        def decode():
            if isinstance(data, Exception):
                raise data
            return data
        return SimpleNamespace(status_code=status, json=decode, headers=headers)

    def close(self):
        pass


def ok(text='{"action":"finish"}'):
    return (200, response(choices=[dict(finish_reason="stop", message=dict(content=text))]), {})


def failure(status=429, headers=None, code="rate_limit_exceeded"):
    return (status, {"error": {"code": code}}, headers or {})


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        Image.new("RGB", (20, 20), "red").save(self.root / "input.png")
        self.env = patch.dict(os.environ, {"MODEL_API_KEY": "unit-test-sensitive-value"})
        self.env.start()
        self.serial = 0

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def setup_model(self, events, *, cfg=None, model_cap=400, on_call=None):
        cfg = cfg or config()
        cfg.max_retries = 3
        self.serial += 1
        directory = self.root / str(self.serial)
        ledger = core.BudgetLedger()
        view = ModelBudget(ledger, "M_strong", model_cap)
        session, waits = SequenceSession(events, on_call), []
        backend = IntranetApiBackend(cfg, artifact_dir=directory / "wire", session=session,
            retry_charge=view.charge_model, sleep=waits.append, jitter=lambda a, b: 0, wall_clock=lambda: 0)
        model = models.RecordedModel(backend, ledger=view)
        return model, backend, session, ledger, waits, directory

    def call(self, model, directory):
        return model.call(phase="prefix", system_prompt="Return one ordinary action.", user_prompt="Route A",
            image_path=self.root / "input.png", image_artifact="input.png", public_context={"user_goal": "Route A"},
            request_dir=directory / "requests", response_dir=directory / "responses")

    def test_429_then_success_preserves_exact_payload_and_charges_each_attempt(self):
        model, backend, session, ledger, waits, directory = self.setup_model([failure(), failure(503), ok()])
        reply = self.call(model, directory)
        self.assertEqual(len(session.calls), 3)
        self.assertEqual(ledger.model_calls, 3)
        self.assertEqual(waits, [10, 20])
        self.assertEqual(reply.metadata["transport_attempt_count"], 3)
        self.assertEqual(len(list((directory / "requests").glob("*.json"))), 1)
        self.assertEqual(len(list((directory / "wire").glob("call_*/request.json"))), 3)
        self.assertEqual([e["request_id"] for e in ledger.events],
            ["M_strong/request_0001", "M_strong/request_0001__retry_1", "M_strong/request_0001__retry_2"])
        self.assertTrue(all(c == session.calls[0] for c in session.calls))
        self.assertEqual(str(backend.spend.accounted_upper()), "1.5")

    def test_serialized_images_do_not_change_between_transport_attempts(self):
        def mutate(count):
            if count == 1:
                Image.new("RGB", (20, 20), "blue").save(self.root / "input.png")
        model, _, session, _, _, directory = self.setup_model([failure(), ok()], on_call=mutate)
        self.call(model, directory)
        self.assertEqual(session.calls[0][1]["json"], session.calls[1][1]["json"])

    def test_exhaustion_stops_after_four_attempts_and_cannot_silently_reset(self):
        model, backend, session, ledger, waits, directory = self.setup_model([failure()] * 5)
        with self.assertRaises(ApiStop):
            self.call(model, directory)
        self.assertEqual((len(session.calls), ledger.model_calls, waits), (4, 4, [10, 20, 40]))
        self.assertTrue(backend.halted)
        self.assertEqual(backend.spend.entries[-1]["retry_stop_reason"], "retry_limit_exhausted")
        self.assertTrue((directory / "wire/transport_stop.json").is_file())
        with self.assertRaises(ApiStop):
            backend.complete(None)
        self.assertEqual(len(session.calls), 4)

    def test_transient_http_allowlist(self):
        for status in (408, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                model, _, session, _, _, directory = self.setup_model([failure(status), ok()])
                self.call(model, directory)
                self.assertEqual(len(session.calls), 2)

    def test_auth_redirect_client_and_nontransient_errors_do_not_retry(self):
        for status in (302, 400, 401, 402, 403, 404, 501):
            with self.subTest(status=status):
                model, _, session, _, waits, directory = self.setup_model([failure(status), ok()])
                with self.assertRaises(ApiStop):
                    self.call(model, directory)
                self.assertEqual((len(session.calls), waits), (1, []))

    def test_explicit_quota_error_does_not_retry_despite_429(self):
        model, _, session, _, waits, directory = self.setup_model([failure(code="insufficient_quota"), ok()])
        with self.assertRaises(ApiStop):
            self.call(model, directory)
        self.assertEqual((len(session.calls), waits), (1, []))

    def test_connection_and_timeout_errors_retry_without_logging_exception_text(self):
        for error in (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            with self.subTest(error=error):
                model, _, session, ledger, _, directory = self.setup_model([error("unit-test-sensitive-value"), ok()])
                self.call(model, directory)
                self.assertEqual((len(session.calls), ledger.model_calls), (2, 2))
                self.assertNotIn("unit-test-sensitive-value", "".join(p.read_text() for p in directory.rglob("*.json")))

    def test_tls_error_does_not_retry(self):
        model, _, session, _, waits, directory = self.setup_model([requests.exceptions.SSLError("bad certificate"), ok()])
        with self.assertRaises(ApiStop):
            self.call(model, directory)
        self.assertEqual((len(session.calls), waits), (1, []))

    def test_bad_or_truncated_200_responses_are_not_resampled(self):
        cases = [ValueError("not JSON"), {}, response(choices=[]),
                 response(choices=[dict(finish_reason="length", message={"content": "incomplete"})]),
                 response(choices=[dict(finish_reason="stop", message={"content": ""})])]
        for data in cases:
            with self.subTest(data=data):
                model, _, session, _, waits, directory = self.setup_model([(200, data, {}), ok()])
                with self.assertRaises(ApiStop):
                    self.call(model, directory)
                self.assertEqual((len(session.calls), waits), (1, []))

    def test_completed_semantic_text_is_returned_once_without_quality_filter(self):
        model, _, session, _, waits, directory = self.setup_model([ok("not a valid action JSON"), ok()])
        result = self.call(model, directory)
        self.assertEqual(result.text, "not a valid action JSON")
        self.assertEqual((len(session.calls), waits), (1, []))

    def test_retry_after_seconds_and_date_are_respected(self):
        for header, expected in (("35", 35), ("Thu, 01 Jan 1970 00:00:45 GMT", 45), ("invalid", 10)):
            with self.subTest(header=header):
                model, _, _, _, waits, directory = self.setup_model([failure(headers={"Retry-After": header}), ok()])
                self.call(model, directory)
                self.assertEqual(waits, [expected])
        self.assertIsNone(retry_after_seconds("-1", 0))
        self.assertIsNone(retry_after_seconds("1.5", 0))

    def test_long_retry_after_stops_instead_of_retrying_early(self):
        for header in ("120", "9" * 50):
            model, backend, session, _, waits, directory = self.setup_model([failure(headers={"Retry-After": header}), ok()])
            with self.assertRaises(ApiStop):
                self.call(model, directory)
            self.assertEqual((len(session.calls), waits), (1, []))
            self.assertEqual(backend.spend.entries[-1]["retry_stop_reason"], "retry_after_exceeds_bounded_wait")

    def test_jitter_is_recorded_without_exceeding_delay_bound(self):
        model, backend, _, _, waits, directory = self.setup_model([failure(), ok()])
        backend.jitter = lambda a, b: b
        self.call(model, directory)
        self.assertEqual(waits, [13])

    def test_shared_call_limit_prevents_an_extra_http_dispatch(self):
        model, backend, session, ledger, _, directory = self.setup_model([failure(), ok()], model_cap=1)
        with self.assertRaises(core.BudgetExceeded):
            self.call(model, directory)
        self.assertEqual((len(session.calls), len(backend.spend.entries), ledger.model_calls), (1, 1, 1))

    def test_money_limit_keeps_failed_reservation_and_prevents_retry(self):
        cfg = config()
        cfg.money_cap_usd = "0.5"
        model, backend, session, ledger, waits, directory = self.setup_model([failure(), ok()], cfg=cfg)
        with self.assertRaises(core.BudgetExceeded):
            self.call(model, directory)
        self.assertEqual((len(session.calls), ledger.model_calls), (1, 1))
        self.assertEqual(str(backend.spend.accounted_upper()), "0.5")
        self.assertEqual(waits, [])

    def test_money_stop_before_first_dispatch_is_classified_as_budget(self):
        cfg = config()
        cfg.money_cap_usd = "0.49"
        model, backend, session, _, waits, directory = self.setup_model([ok()], cfg=cfg)
        with self.assertRaises(core.BudgetExceeded):
            self.call(model, directory)
        self.assertEqual((session.calls, backend.spend.entries, waits), ([], [], []))
        stop = json.loads((directory / "wire/transport_stop.json").read_text())
        self.assertEqual(stop["stop_reason"], "budget_exhausted_before_another_dispatch")
        self.assertIsNone(stop["last_attempt_id"])

    def test_retry_configuration_cannot_omit_global_accounting(self):
        cfg = config()
        cfg.max_retries = 3
        with self.assertRaises(ValueError):
            IntranetApiBackend(cfg, artifact_dir=self.root / "bad", session=SequenceSession([]))
        cfg.max_retries = 4
        with self.assertRaises(ValueError):
            IntranetApiBackend(cfg, artifact_dir=self.root / "bad", retry_charge=lambda **k: None)

    def test_failure_diagnostics_omit_raw_body_and_sensitive_headers(self):
        data = {"error": {"code": "rate_limit_exceeded", "message": "unit-test-sensitive-value"}, "secret": "do not copy"}
        headers = {"Retry-After": "1", "Authorization": "unit-test-sensitive-value", "X-Request-ID": "trace-123"}
        model, _, _, _, _, directory = self.setup_model([(429, data, headers), ok()])
        self.call(model, directory)
        saved = json.loads((directory / "wire/call_0001/failure.json").read_text())
        self.assertEqual(saved["safe_response_headers"], {"retry-after": "1", "x-request-id": "trace-123"})
        self.assertFalse(saved["response_body_saved"])
        logs = "".join(p.read_text() for p in directory.rglob("*.json"))
        self.assertNotIn("unit-test-sensitive-value", logs)
        self.assertNotIn("do not copy", logs)

    def test_retry_failures_do_not_become_complete_token_usage(self):
        model, _, _, _, _, directory = self.setup_model([failure(), ok()])
        self.call(model, directory)
        report = reported_usage(directory)
        self.assertFalse(report["usage_complete"])
        self.assertEqual(report["unknown_retry_usage_records"], 1)
        self.assertEqual(report["response_records"], 1)
        self.assertEqual(report["prompt_tokens_reported"], 10)


def browser_probe(output, browser):
    """One public Route task: failed generation retry, then exactly one actual POST."""
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    snapshot_sources(root)
    task = route_task()
    chart = root / "blank.png"
    Image.new("RGB", (300, 180), "white").save(chart)
    submissions = root / "server_receipts.jsonl"
    ledger = core.BudgetLedger(max_model_calls=4, max_browser_transitions=10)
    ledger.bind_snapshot(root / "mock_budget.json")
    view = ModelBudget(ledger, "M_strong", 4)
    cfg = config()
    cfg.max_retries = 3
    session, waits = SequenceSession([failure(), ok('{"action":"click_button","text":"Submit Form"}')]), []
    with patch.dict(os.environ, {"MODEL_API_KEY": "mock-only"}):
        backend = IntranetApiBackend(cfg, artifact_dir=root / "api_wire", session=session,
            retry_charge=view.charge_model, sleep=waits.append, jitter=lambda a, b: 0)
        model = models.RecordedModel(backend, ledger=view)
        with runner.managed_shell(task, chart, submissions) as server, runner.require_playwright()() as pw:
            br = pw.chromium.launch(headless=True, executable_path=str(browser), args=list(runner.BROWSER_LAUNCH_ARGS))
            try:
                page = br.new_page(viewport=dict(width=1440, height=1100))
                executor = runner.BrowserExecutor(page, ledger=view, task_alias="control")
                executor.navigate(server.base_url + "/task/control", phase="control_setup")
                for action in (dict(action="click_link", text="Open Dashboard"),
                               dict(action="click_link", text="Open Form"),
                               dict(action="select_option", select_name="primary_action", option_text="Route A")):
                    executor.execute(action, phase="control_setup")
                cp, _ = capture_pending(page, executor, model, goal=task["user_goal"], alias="control",
                    directory=root / "prefix", max_calls=2)
                assert cp is not None and not submissions.exists()
                result = run_branch(page, executor, model, cp, strategy="B0", directory=root / "B0",
                    prefix_receipts=executor.receipts[:], submission_path=submissions)
                assert result["submitted"] and result["confirmation_observed"]
                assert len(result["server_receipts"]) == 1 and len(session.calls) == 2
                assert ledger.model_calls == 2 and ledger.browser_transitions == 5
                assert sum(r["phase"] == "actual_submit" for r in executor.receipts) == 1
                core.write_json(root / "execution_receipts.json", executor.receipts)
            finally:
                br.close()
        backend.close()
    result = dict(status="passed", scope="nonchart_scripted_retry_engineering_only",
        simulated_http_attempts=2, mock_model_call_attempts=ledger.model_calls,
        logical_actor_requests=1, simulated_retry_wait_seconds=waits, actual_browser_transitions=ledger.browser_transitions,
        actual_localhost_submissions=1, real_api_generation_calls=0, real_model_calls=0)
    core.write_json(root / "result.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    browser_probe(args.output, args.browser)
