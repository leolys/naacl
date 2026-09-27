from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from research.decision_evidence_audit import core, models, policies, runner, safe_shell
from .api_backend import ApiConfig, ApiSpend, ApiStop, IntranetApiBackend, wire_payload
from .h_base import actor_prompt, public_history, VerifierModel
from .prepare import build_manifest, source_group


def config():
    return ApiConfig(model_id="test-model", authorized=True, authorization_reference="MOCK ONLY",
        owner_confirmed_model_identity="MOCK ONLY", official_model_documentation="MOCK ONLY",
        allowed_response_models=["test-model"], allowed_reported_routes=["test-route"],
        max_output_tokens=4096, reasoning_setting_confirmed=True,
        money_cap_usd="2.0", request_cost_ceiling_usd="0.5", cost_ceiling_basis="MOCK ONLY")


def response(**changes):
    data = dict(model="test-model", usage=dict(model_name="test-route", prompt_tokens=10, completion_tokens=8),
                choices=[dict(finish_reason="stop", message=dict(content='{"action":"finish"}'))])
    data.update(changes)
    return data


class FakeSession:
    def __init__(self, data=None, status=200, error=None):
        self.data, self.status, self.error = data or response(), status, error
        self.calls = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        from types import SimpleNamespace
        return SimpleNamespace(status_code=self.status, json=lambda: self.data)
    def close(self):
        pass


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name, color, size in (("a", "red", (31, 29)), ("b", "blue", (21, 19))):
            Image.new("RGB", size, color).save(self.root / f"{name}.png")
        self.req = models.OnlineRequest("request_1", "prefix", "system", "public user goal",
            (self.root / "a.png", self.root / "b.png"), ("a.png", "b.png"), {"user_goal": "Route A"})
        self.env = patch.dict(os.environ, {"MODEL_API_KEY": "test-credential-do-not-log"})
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def backend(self, session=None, cfg=None):
        return IntranetApiBackend(cfg or config(), artifact_dir=self.root / "wire", session=session or FakeSession())

    def test_default_refuses_before_transport(self):
        session = FakeSession()
        with self.assertRaises(PermissionError):
            self.backend(session, ApiConfig())
        self.assertEqual(session.calls, [])

    def test_two_images_order_and_exact_bytes_no_local_paths_on_wire(self):
        payload, meta = wire_payload(config(), self.req)
        content = payload["messages"][1]["content"]
        self.assertEqual(len(content), 3)
        for i, name in enumerate(("a", "b"), 1):
            url = content[i]["image_url"]["url"]
            self.assertEqual(base64.b64decode(url.split(",")[1]), (self.root / f"{name}.png").read_bytes())
        self.assertEqual([m["size"] for m in meta], [[31, 29], [21, 19]])
        self.assertNotIn(str(self.root), json.dumps(payload))
        self.assertEqual(payload["max_completion_tokens"], 4096)
        self.assertNotIn("temperature", payload)

    def test_hidden_context_is_rejected(self):
        self.req.public_context["ground_truth"] = "secret"
        with self.assertRaises(core.IsolationError):
            wire_payload(config(), self.req)

    def test_success_records_usage_wire_and_no_credentials(self):
        session = FakeSession()
        backend = self.backend(session)
        reply = backend.complete(self.req)
        self.assertEqual(reply.metadata["gateway_reported_route"], "test-route")
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(session.calls[0][1]["allow_redirects"])
        logs = "".join(p.read_text() for p in (self.root / "wire").rglob("*.json"))
        self.assertNotIn("test-credential-do-not-log", logs)
        self.assertIsNone(reply.metadata["observed_billed_usd"])

    def test_echoed_request_name_does_not_validate_gateway_route(self):
        session = FakeSession(response(usage={"model_name": "gpt-5.6-luna"}))
        backend = self.backend(session)
        with self.assertRaises(ApiStop):
            backend.complete(self.req)
        with self.assertRaises(ApiStop):
            backend.complete(self.req)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(backend.spend.entries[0]["status"], "identity_unverified_or_mismatch")

    def test_missing_route_not_silently_accepted(self):
        backend = self.backend(FakeSession(response(usage={"prompt_tokens": 10})))
        with self.assertRaises(ApiStop):
            backend.complete(self.req)

    def test_explicit_record_only_keeps_route_without_claiming_identity(self):
        cfg = config()
        cfg.identity_policy = "record_only"
        cfg.identity_waiver_reference = "MOCK explicit owner override"
        backend = self.backend(FakeSession(response(usage={"model_name": "different-route"})), cfg)
        result = backend.complete(self.req)
        self.assertFalse(result.metadata["identity_matches"])
        self.assertEqual(result.metadata["gateway_reported_route"], "different-route")
        self.assertIn("identity_unverified", backend.metadata["identity_status"])
        self.assertEqual(backend.spend.entries[0]["usage_settlement"], "unpriced_route_full_reservation_retained_identity_not_blocked")

    def test_identity_override_needs_explicit_reference(self):
        cfg = config()
        cfg.identity_policy = "record_only"
        with self.assertRaises(PermissionError):
            self.backend(cfg=cfg)

    def test_transport_failure_charged_no_retry_or_secret_error(self):
        session = FakeSession(error=RuntimeError("test-credential-do-not-log"))
        backend = self.backend(session)
        with self.assertRaises(ApiStop) as caught:
            backend.complete(self.req)
        self.assertNotIn("test-credential-do-not-log", str(caught.exception))
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(len(backend.spend.entries), 1)
        self.assertIsNone(backend.spend.entries[0]["observed_billed_usd"])

    def test_http_redirect_rejected_without_following(self):
        session = FakeSession(status=302)
        with self.assertRaises(ApiStop):
            self.backend(session).complete(self.req)
        self.assertEqual(len(session.calls), 1)

    def test_truncation_not_semantic_decision(self):
        data = response(choices=[dict(finish_reason="length", message=dict(content='{"action":'))])
        backend = self.backend(FakeSession(data))
        with self.assertRaises(ApiStop):
            backend.complete(self.req)
        self.assertTrue(backend.spend.entries[0]["output_truncated"])

    def test_dollar_and_call_limits_reserve_before_dispatch(self):
        cfg = config()
        cfg.money_cap_usd = "0.5"
        session = FakeSession()
        backend = self.backend(session, cfg)
        backend.complete(self.req)
        with self.assertRaises(core.BudgetExceeded):
            backend.complete(self.req)
        self.assertEqual(len(session.calls), 1)
        cfg.max_calls = 1
        cfg.money_cap_usd = "5"
        ledger = ApiSpend(cfg, self.root / "separate.json")
        ledger.reserve("1")
        with self.assertRaises(core.BudgetExceeded):
            ledger.reserve("2")

    def test_no_implicit_resume(self):
        backend = self.backend()
        backend.complete(self.req)
        with self.assertRaises(FileExistsError):
            self.backend()

    def test_verified_usage_settlement_not_unknown_cost_release(self):
        cfg = config()
        cfg.max_output_tokens = 100
        cfg.input_token_limit_for_reservation = 100
        cfg.input_token_cost_upper_usd = "0.001"
        cfg.output_token_cost_upper_usd = "0.001"
        cfg.request_cost_ceiling_usd = "0.5"
        cfg.money_cap_usd = "0.6"
        backend = self.backend(cfg=cfg)
        backend.complete(self.req)
        self.assertEqual(str(backend.spend.accounted_upper()), "0.018")
        backend.complete(self.req)
        self.assertEqual(str(backend.spend.accounted_upper()), "0.036")
        # A separate unknown-cost request must retain its full reservation.
        ledger = ApiSpend(cfg, self.root / "unknown.json")
        entry = ledger.reserve("unknown")
        ledger.settle_completed_usage(entry, {})
        self.assertEqual(str(ledger.accounted_upper()), "0.5")
        with self.assertRaises(core.BudgetExceeded):
            ledger.reserve("would_overrun")

    def test_usage_settlement_requires_sufficient_initial_reservation(self):
        cfg = config()
        cfg.input_token_limit_for_reservation = 1000
        cfg.input_token_cost_upper_usd = "1"
        cfg.output_token_cost_upper_usd = "1"
        with self.assertRaises(ValueError):
            self.backend(cfg=cfg)


class ProtocolTests(unittest.TestCase):
    def test_manifest_pairs_schedule_exclusions_and_scope(self):
        manifest = build_manifest()
        self.assertEqual(len(manifest["rows"]), 8)
        self.assertEqual(len(manifest["case_interleaved_order"]), 32)
        self.assertEqual(sum(len(x["strategies"]) for x in manifest["case_interleaved_order"]), 96)
        self.assertEqual(len({r["original_source_group"] for r in manifest["rows"]}), 8)
        self.assertFalse(set(r["task_slug"] for r in manifest["rows"]) & set(manifest["exclusions"]))
        self.assertEqual(source_group({"case_id": "environment_rewrite/base_source/relabel"}), "base_source")
        self.assertTrue(all(not r["non_chart_differences"] for r in manifest["rows"]))
        self.assertEqual(sum(r["offline_mechanism"] == "misleading_annotations" for r in manifest["rows"]), 1)

    def test_history_is_bounded_real_receipts_not_invented_reasons(self):
        receipts = [dict(action=dict(action="finish"), executed=False, error=str(i), invented_reason="omit") for i in range(6)]
        self.assertEqual([x["error"] for x in public_history(receipts)], ["2", "3", "4", "5"])
        self.assertNotIn("invented_reason", json.dumps(public_history(receipts)))
        system, user, context = actor_prompt("Select Route A", {}, receipts)
        self.assertIn("A non-empty selection alone does not mean", user)
        self.assertIn("you may revise", user)
        self.assertNotIn("must submit", user)
        self.assertIn("public execution history", system)

    def test_b2_blind_and_b3_bounded_actual_receipts(self):
        class Capture:
            def call(self, **kwargs):
                self.kwargs = kwargs
        captured = Capture()
        history = [dict(action={"action": "select_option", "option_text": "Route B"}, executed=True)]
        verifier = VerifierModel(captured, history)
        ctx = dict(user_goal="Route A", visible_options=["Route A", "Route B"])
        verifier.call(phase="b2_decision", system_prompt="check", user_prompt=json.dumps(ctx), public_context=ctx)
        self.assertEqual(captured.kwargs["public_context"], ctx)
        self.assertNotIn("recent_executed", captured.kwargs["user_prompt"])
        ctx = dict(current_selection="Route B", prior_agent_responses=["old"], visible_action_prefix=[{"action": "finish"}])
        verifier.call(phase="b3_plan", system_prompt="check", user_prompt=json.dumps(ctx), public_context=ctx)
        self.assertNotIn("prior_agent_responses", captured.kwargs["public_context"])
        self.assertEqual(captured.kwargs["public_context"]["recent_executed_actions_and_public_receipts"], history)
        self.assertIn("FINAL RECOMMENDED", captured.kwargs["system_prompt"])

    def test_hidden_gold_mutation_does_not_change_public_task(self):
        a = dict(workflow_instruction="Choose Route A", action_space=[dict(label="Route A"), dict(label="Route B")])
        b = dict(a, expected_action_id="opposite", ground_truth={"secret": "changed"}, misleading_context={"mechanism": "changed"})
        self.assertEqual(core.public_task_projection(a, task_alias="control"), core.public_task_projection(b, task_alias="control"))


if __name__ == "__main__":
    unittest.main()
