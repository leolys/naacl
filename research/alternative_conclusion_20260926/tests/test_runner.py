"""Offline mocks only: these tests do not establish live model/browser behavior."""

import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location("alternative_diagnostic_test_" + name,
                                                 ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with mock.patch.dict(sys.modules, {"prompts": load_module("prompts"),
                                  "schemas": load_module("schemas")}):
    runner = load_module("runner")


def config():
    return {
        "endpoint": "http://127.0.0.1:8058/v1/chat/completions",
        "model": "Qwen3.8-27B", "temperature": 0.7, "top_p": 0.8,
        "top_k": 20, "seed": 12345, "enable_thinking": False,
        "max_output_tokens": {"initial": 2400, "actor": 1024},
        "http_timeout_seconds": 120, "service_attempts_per_call": 2,
        "max_request_attempts": 64, "max_browser_operations": 240,
    }


def public_state():
    # This fixture is the browser's public DOM projection, NOT a raw task/scorer.
    return {
        "url": "http://127.0.0.1:18000/task/example/form",
        "title": "Public task form",
        "elements": {"selects": [{"name": "primary_action",
            "selected_text": "Route A", "options": [
                {"value": "", "text": "Choose an option", "disabled": False},
                {"value": "a", "text": "Route A", "disabled": False},
                {"value": "b", "text": "Route B", "disabled": False},
                {"value": "c", "text": "Unavailable Route", "disabled": True},
            ]}], "buttons": [{"text": "Submit Form"}]},
    }


def response(status=200):
    item = mock.Mock()
    item.status_code = status
    item.json.return_value = {
        "id": "mock-id", "model": "Qwen3.8-27B", "created": 0,
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        "choices": [{"message": {"content": '{"chains": [], "notes": "mock"}'}}],
    }
    if status >= 400:
        item.raise_for_status.side_effect = runner.requests.HTTPError("mock HTTP " + str(status))
    return item


class LocalTransportMockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alternative-diagnostic-mock-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "mock.png"
        self.image.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXZkAAAAASUVORK5CYII="))
        self.cfg = config()
        self.ledger = runner.Ledger(self.root, self.cfg)
        self.http = mock.Mock()
        self.session_patch = mock.patch.object(runner.requests, "Session", return_value=self.http)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.sleep_patch = mock.patch.object(runner.time, "sleep")
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def call(self, api, name="call"):
        return api.call(self.root / name, "mock system", {"goal": "Public goal"},
                        self.image, runner.SCHEMAS["initial"], "initial")

    def test_reject_non_authorized_endpoint(self):
        for endpoint in ("https://api.apiyi.com/v1/chat/completions",
                         "http://example.com:8058/v1/chat/completions",
                         "http://127.0.0.1:8000/v1/chat/completions",
                         "http://127.0.0.1:8058/v1/chat/completions?redirect=elsewhere"):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    runner.LocalAPI(dict(self.cfg, endpoint=endpoint), self.ledger)
        self.http.post.assert_not_called()

    def test_single_image_schema_and_request_archive(self):
        self.http.post.return_value = response()
        api = runner.LocalAPI(self.cfg, self.ledger)
        returned = self.call(api)
        self.assertIn("chains", returned)
        self.assertFalse(self.http.trust_env)
        args, kwargs = self.http.post.call_args
        self.assertEqual(args, (self.cfg["endpoint"],))
        self.assertIs(kwargs["allow_redirects"], False)
        payload = kwargs["json"]
        blocks = payload["messages"][1]["content"]
        images = [block for block in blocks if block["type"] == "image_url"]
        self.assertEqual(len(images), 1)
        self.assertEqual(base64.b64decode(images[0]["image_url"]["url"].split(",", 1)[1]),
                         self.image.read_bytes())
        self.assertEqual(payload["structured_outputs"]["json"], runner.SCHEMAS["initial"])
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(payload["max_tokens"], 2400)
        archived = json.loads((self.root / "call" / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(archived, payload)
        self.assertNotIn("Authorization", json.dumps(archived))
        self.assertEqual(self.ledger.data["request_attempts"], 1)
        self.assertEqual(self.ledger.data["paid_api_requests"], 0)

    def test_explicit_503_then_success_counts_two_attempts(self):
        self.http.post.side_effect = [response(503), response(200)]
        api = runner.LocalAPI(self.cfg, self.ledger)
        self.call(api)
        self.assertEqual(self.http.post.call_count, 2)
        self.assertEqual(self.ledger.data["request_attempts"], 2)
        self.assertEqual([event["http_status"] for event in self.ledger.data["events"]], [503, 200])
        self.assertTrue((self.root / "call" / "response_01.json").exists())
        self.assertTrue((self.root / "call" / "response_02.json").exists())

    def test_explicit_503_does_not_exceed_two_attempts(self):
        self.http.post.side_effect = [response(503), response(503), response(200)]
        api = runner.LocalAPI(self.cfg, self.ledger)
        with self.assertRaises(runner.LimitStop):
            self.call(api)
        self.assertEqual(self.http.post.call_count, 2)
        self.assertEqual(self.ledger.data["request_attempts"], 2)
        self.assertFalse((self.root / "call" / "response_03.json").exists())
        self.assertEqual(self.ledger.blocked_reason, "model_service_http_503")

    def test_unknown_timeout_stops_without_resend_and_blocks_future_request(self):
        self.http.post.side_effect = runner.requests.ReadTimeout("mock unknown execution outcome")
        api = runner.LocalAPI(self.cfg, self.ledger)
        with self.assertRaises(runner.LimitStop):
            self.call(api)
        self.assertEqual(self.http.post.call_count, 1)
        self.assertEqual(self.ledger.data["request_attempts"], 1)
        self.assertEqual(self.ledger.data["events"][-1]["outcome"], "unknown_transport_no_retry")
        self.assertTrue(self.ledger.data.get("blocked_reason"))
        self.assertEqual(self.ledger.blocked_reason, self.ledger.data["blocked_reason"])
        self.http.post.side_effect = None
        self.http.post.return_value = response()
        with self.assertRaises(runner.LimitStop):
            self.call(api, "second_call")
        self.assertEqual(self.http.post.call_count, 1)
        self.assertEqual(self.ledger.data["request_attempts"], 1)

    def test_output_directory_not_overwritten(self):
        self.http.post.return_value = response()
        api = runner.LocalAPI(self.cfg, self.ledger)
        self.call(api)
        with self.assertRaises(FileExistsError):
            self.call(api)
        self.assertEqual(self.http.post.call_count, 1)

    def test_request_and_browser_budget_caps(self):
        # Boundary tests, not 304 real operations. Each successful mock event is accounted.
        with mock.patch.object(self.ledger, "save"):
            for index in range(64):
                self.ledger.event("request", {"mock_index": index})
            with self.assertRaises(runner.LimitStop):
                self.ledger.event("request", {"mock_index": 64})
        browser_ledger = runner.Ledger(self.root / "separate-browser-budget-test", self.cfg)
        with mock.patch.object(browser_ledger, "save"):
            for index in range(240):
                browser_ledger.event("browser", {"mock_index": index})
            with self.assertRaises(runner.LimitStop):
                browser_ledger.event("browser", {"mock_index": 240})
        self.assertEqual(self.ledger.data["request_attempts"], 64)
        self.assertEqual(browser_ledger.data["browser_operations"], 240)
        self.assertEqual(len(self.ledger.data["events"]) + len(browser_ledger.data["events"]), 304)
        self.http.post.assert_not_called()

    def test_actor_preserves_transport_global_stop_after_original_wrapper(self):
        self.ledger.block("mock unknown transport outcome")
        actor = runner.Actor.__new__(runner.Actor)
        actor.api = SimpleNamespace(ledger=self.ledger, config=self.cfg, last_metadata={})
        original_call = lambda *args, **kwargs: "unused"
        original_metadata = lambda: {}
        original_limit = lambda history: 1
        actor.client_module = SimpleNamespace(complete_vision=original_call,
                                              get_last_response_metadata=original_metadata)
        actor.original = SimpleNamespace(action_generation_attempt_limit=original_limit,
            llm_next_action=mock.Mock(side_effect=RuntimeError("original parser wrapped a transport exception")))
        actor.schema = {"type": "object"}
        env = SimpleNamespace(snapshot=lambda: (public_state(), self.image), history=[])
        with self.assertRaises(runner.LimitStop):
            actor.next(env, self.root / "mock_wrapped_actor")
        self.assertIs(actor.client_module.complete_vision, original_call)
        self.assertIs(actor.client_module.get_last_response_metadata, original_metadata)
        self.assertIs(actor.original.action_generation_attempt_limit, original_limit)
        self.http.post.assert_not_called()


class PublicProjectionAndScoreMockTests(unittest.TestCase):
    def test_clean_action_removes_metadata_without_mutation(self):
        action = {"action": "click_button", "text": "Submit Form", "_raw": "private parser metadata",
                  "_model": "mock", "_meta": {"debug": 1}}
        before = copy.deepcopy(action)
        self.assertEqual(runner.clean_action(action), {"action": "click_button", "text": "Submit Form"})
        self.assertEqual(action, before)

    def test_submit_detector_exact_public_action(self):
        self.assertTrue(runner.is_submit({"action": "click_button", "text": "Submit Form"}))
        # The original executor falls back from click_link to same-text buttons.
        self.assertTrue(runner.is_submit({"action": "click_link", "text": "Submit Form"}))
        for action in ({"action": "finish"}, {"action": "submit"},
                       {"action": "click_button", "text": "Open Form"},
                       {"action": "click_link", "text": "Open Form"},
                       {"action": "click_button", "text": "submit form"},
                       {"action": "select_option", "text": "Submit Form"}, {}):
            with self.subTest(action=action):
                self.assertFalse(runner.is_submit(action))

    def test_selected_option_remains_in_options(self):
        state = public_state()
        self.assertEqual(runner.options(state), ["Route A", "Route B"])
        self.assertEqual(runner.selected(state), "Route A")
        self.assertIn(runner.selected(state), runner.options(state))

    def test_public_context_takes_dom_projection_not_scorer_wrapper(self):
        raw_task = {"evaluation_hidden_from_agent": {"gold": "private-sentinel"},
                    "public_dom": public_state()}
        history = [{"action": {"action": "select_option", "text": "Route A"},
                    "receipt": {"executed": True, "current_selection": "Route A"}}]
        # The caller deliberately passes only DOM-visible state, not raw_task.
        context = runner.public_context(raw_task["public_dom"], history,
                                        {"action": "click_button", "text": "Submit Form", "_meta": "not-public"})
        self.assertEqual(set(context), {"goal", "state", "history", "options", "pending_proposal"})
        self.assertNotIn("private-sentinel", json.dumps(context))
        self.assertNotIn("evaluation_hidden_from_agent", json.dumps(context))
        self.assertNotIn("_meta", context["pending_proposal"])
        self.assertEqual(context["history"], history)
        self.assertEqual(context["options"], ["Route A", "Route B"])
        context["state"]["title"] = "changed copy"
        context["history"][0]["receipt"]["executed"] = False
        self.assertEqual(raw_task["public_dom"]["title"], "Public task form")
        self.assertTrue(history[0]["receipt"]["executed"])

    def test_score_only_from_fresh_offline_submission_receipts(self):
        with tempfile.TemporaryDirectory(prefix="diagnostic-score-mock-") as folder:
            path = Path(folder) / "mock_submissions.jsonl"
            rows = [
                {"selected_action_label": "Old Route", "evaluation_hidden_from_agent": {"outcome": "success"}},
                {"selected_action_label": "Route B", "evaluation_hidden_from_agent": {"outcome": "irrelevant_action_failure"}},
            ]
            runner.dump(Path(folder) / "unrelated_model_answer.json", {"claim": "success"})
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            result = runner.score(path, 1)
            self.assertTrue(result["submitted"])
            self.assertEqual(result["final_selection"], "Route B")
            self.assertEqual(result["outcome"], "irrelevant_action_failure")
            self.assertEqual(result["submission"], rows[1])
            self.assertEqual(runner.row_count(path), 2)

    def test_no_new_submission_never_success(self):
        with tempfile.TemporaryDirectory(prefix="diagnostic-score-mock-") as folder:
            path = Path(folder) / "mock_submissions.jsonl"
            expected = {"submitted": False, "final_selection": None,
                        "outcome": "not_submitted", "submission": None}
            self.assertEqual(runner.score(path, 0), expected)
            row = {"selected_action_label": "Old Route", "evaluation_hidden_from_agent": {"outcome": "success"}}
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            self.assertEqual(runner.score(path, 1), expected)


if __name__ == "__main__":
    unittest.main()
