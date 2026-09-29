from __future__ import annotations

import base64
from io import BytesIO
import hashlib
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import ProxyHandler

from PIL import Image

from web_agent_benchmark.evaluation.gui_reflection_baseline.agent_runtime import (
    AgentRuntimeError,
    FixtureHistoryFrame,
    HttpAgentClient,
    OFFICIAL_DETERMINISTIC_GENERATION_CONFIG,
    StepResult,
    _rgb_image_sha256,
)
from web_agent_benchmark.evaluation.gui_reflection_baseline.actions import ParsedAction
from web_agent_benchmark.evaluation.gui_reflection_baseline.model_server import (
    Handler,
    _history_image_sha256,
)


def png_bytes(width: int = 24, height: int = 16) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color=(20, 30, 40)).save(output, format="PNG")
    return output.getvalue()


def prompt_receipt_fields(memory: str = "") -> dict[str, object]:
    segment = f"<MEMORY> (stored memory content): {memory}\n"
    question = "<image>\n" + segment + "<PAST ACTIONS> (past actions): []\n"
    return {
        "memory_text_sha256_before": hashlib.sha256(
            memory.encode("utf-8")
        ).hexdigest(),
        "memory_text_length_before": len(memory),
        "model_call_question_sha256": hashlib.sha256(
            question.encode("utf-8")
        ).hexdigest(),
        "model_call_question_length": len(question),
        "model_call_memory_segment_sha256": hashlib.sha256(
            segment.encode("utf-8")
        ).hexdigest(),
        "model_call_memory_segment_occurrences": 1,
    }


class FakeTokenizer:
    def __call__(self, value: str, **_kwargs: object) -> dict[str, list[int]]:
        return {"input_ids": list(range(max(1, len(value.split()))))}


class FakeModel:
    last_output = ""

    def __init__(self) -> None:
        self.tokenizer = FakeTokenizer()

    def __call__(
        self,
        question: str,
        images: list[Image.Image],
        generation_config: dict[str, object],
        **_kwargs: object,
    ) -> str:
        self.last_question = question
        self.last_question_sha256 = hashlib.sha256(question.encode("utf-8")).hexdigest()
        self.last_question_length = len(question)
        self.last_question_token_count = len(
            self.tokenizer(question, add_special_tokens=False)["input_ids"]
        )
        self.last_input_image_sha256 = [_history_image_sha256(image) for image in images]
        self.last_input_image_sizes = [[image.width, image.height] for image in images]
        self.last_output = "EVIDENCE_JSON: {\"records\":[]}\n<ACTION>: PRESS_BACK"
        self.last_output_token_count = len(
            self.tokenizer(self.last_output, add_special_tokens=False)["input_ids"]
        )
        generation_config["eos_token_id"] = [7, 8]
        return self.last_output


class FakeOfficialAgent:
    def __init__(self) -> None:
        self.model = FakeModel()
        self.generation_config = dict(OFFICIAL_DETERMINISTIC_GENERATION_CONFIG)
        self._phase3_official_system_prompt = "official fake system"
        self._phase3_official_parse_action_output = lambda _raw, _width, _height: {
            "action_type": "PRESS_BACK",
            "parameters": [],
        }
        self.reset()

    def reset(self) -> None:
        self._actions: list[str] = []
        self._action_desc: list[str] = []
        self.history_images: list[Image.Image] = []
        self.history_images_annos: list[tuple[int, int] | None] = []
        self.memory = ""

    def step(self, image: Image.Image, goal: str) -> dict[str, object]:
        del goal
        memory_segment = f"<MEMORY> (stored memory content): {self.memory}\n"
        question = (
            "<image>\n" + memory_segment + "<PAST ACTIONS> (past actions): []\n"
        )
        self.model.last_question = question
        self.model.last_question_sha256 = hashlib.sha256(
            question.encode("utf-8")
        ).hexdigest()
        self.model.last_question_length = len(question)
        model_images = [item.resize((448, 448)) for item in self.history_images] + [image]
        self.model.last_input_image_sha256 = [
            _history_image_sha256(item) for item in model_images
        ]
        self.model.last_input_image_sizes = [
            [item.width, item.height] for item in model_images
        ]
        self.model.last_output = (
            "<THOUGHT>: wait</THOUGHT>\n<ACTION DESC>: wait\n<ACTION>: WAIT"
        )
        self._actions.append("WAIT")
        self._action_desc.append("wait")
        self.history_images.append(image)
        self.history_images_annos.append(None)
        # Model inference in the official repository mutates this dictionary.
        self.generation_config["eos_token_id"] = [7, 8]
        return {"action_type": "WAIT", "parameters": []}


class HttpAgentClientTests(unittest.TestCase):
    def test_loopback_requests_ignore_proxy_environment(self) -> None:
        proxy_environment = {
            "HTTP_PROXY": "http://127.0.0.1:1",
            "HTTPS_PROXY": "http://127.0.0.1:1",
            "http_proxy": "http://127.0.0.1:1",
            "https_proxy": "http://127.0.0.1:1",
            "NO_PROXY": "",
            "no_proxy": "",
        }
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"status": "ok"}'
        opener = MagicMock()
        opener.open.return_value = response
        module = "web_agent_benchmark.evaluation.gui_reflection_baseline.agent_runtime"
        with (
            patch.dict(os.environ, proxy_environment, clear=False),
            patch(f"{module}.build_opener", return_value=opener) as build_opener,
            patch(f"{module}.urlopen", side_effect=AssertionError("proxy-aware urlopen used")),
        ):
            client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)
            self.assertEqual(client.health(), {"status": "ok"})

        handler = build_opener.call_args.args[0]
        self.assertIsInstance(handler, ProxyHandler)
        self.assertEqual(handler.proxies, {})
        opener.open.assert_called_once()

    def test_server_receipt_records_actual_pre_step_inputs_and_reset_scope(self) -> None:
        screenshot = png_bytes()
        goal = "Choose the largest increase"
        server = SimpleNamespace(
            agent=FakeOfficialAgent(), active_task_id=None, task_step_index=0
        )
        handler = object.__new__(Handler)
        handler.server = server
        responses: list[tuple[int, dict[str, object]]] = []
        handler._send = lambda status, payload: responses.append((status, payload))

        handler._reset({"task_id": "env008:official"})

        def perform_step(request_number: int) -> dict[str, object]:
            handler._step(
                {
                    "request_id": "req_" + f"{request_number:032x}",
                    "task_id": server.active_task_id,
                    "task_goal": goal,
                    "screenshot_png_base64": base64.b64encode(screenshot).decode("ascii"),
                    "viewport_width": 24,
                    "viewport_height": 16,
                }
            )
            self.assertEqual(responses[-1][0], 200)
            receipt = responses[-1][1]["receipt"]
            assert isinstance(receipt, dict)
            return receipt

        first_receipt = perform_step(1)
        second_receipt = perform_step(2)
        handler._reset({"task_id": "env008:clean"})
        after_reset_receipt = perform_step(3)

        self.assertTrue(first_receipt["request_id"].startswith("req_"))
        self.assertTrue(first_receipt["response_id"].startswith("resp_"))
        self.assertEqual(
            first_receipt["screenshot_png_sha256"], hashlib.sha256(screenshot).hexdigest()
        )
        self.assertEqual(
            first_receipt["task_goal_sha256"],
            hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(first_receipt["viewport"], {"width": 24, "height": 16})
        self.assertEqual(first_receipt["task_step_index"], 0)
        self.assertEqual(first_receipt["history_image_count_before"], 0)
        self.assertEqual(first_receipt["history_image_sha256_before"], [])
        self.assertEqual(first_receipt["history_image_annotations_before"], [])
        self.assertEqual(len(first_receipt["model_call_input_image_sha256"]), 1)
        self.assertEqual(first_receipt["model_call_input_image_sizes"], [[24, 16]])
        self.assertEqual(first_receipt["action_count_before"], 0)
        empty_action_history = json.dumps(
            {"actions": [], "action_descriptions": []},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            first_receipt["action_history_sha256_before"],
            hashlib.sha256(empty_action_history).hexdigest(),
        )
        self.assertIs(first_receipt["memory_empty_before"], True)
        self.assertEqual(
            first_receipt["memory_text_sha256_before"], hashlib.sha256(b"").hexdigest()
        )
        self.assertEqual(first_receipt["memory_text_length_before"], 0)
        self.assertEqual(first_receipt["model_call_memory_segment_occurrences"], 1)
        self.assertEqual(
            first_receipt["generation_config"],
            OFFICIAL_DETERMINISTIC_GENERATION_CONFIG,
        )

        self.assertEqual(second_receipt["task_step_index"], 1)
        self.assertEqual(second_receipt["history_image_count_before"], 1)
        self.assertEqual(len(second_receipt["history_image_sha256_before"]), 1)
        self.assertRegex(second_receipt["history_image_sha256_before"][0], r"^[0-9a-f]{64}$")
        self.assertEqual(second_receipt["action_count_before"], 1)
        self.assertNotEqual(
            second_receipt["action_history_sha256_before"],
            first_receipt["action_history_sha256_before"],
        )
        self.assertEqual(
            second_receipt["generation_config"]["eos_token_id"], [7, 8]
        )
        self.assertEqual(after_reset_receipt["task_id"], "env008:clean")
        self.assertEqual(after_reset_receipt["task_step_index"], 0)
        self.assertEqual(after_reset_receipt["history_image_count_before"], 0)
        self.assertEqual(after_reset_receipt["history_image_sha256_before"], [])
        self.assertEqual(after_reset_receipt["action_count_before"], 0)
        self.assertEqual(
            after_reset_receipt["action_history_sha256_before"],
            first_receipt["action_history_sha256_before"],
        )

    def test_server_fixture_prime_is_explicit_and_requires_empty_state(self) -> None:
        screenshot = png_bytes()
        server = SimpleNamespace(
            agent=FakeOfficialAgent(),
            active_task_id="task-a",
            task_step_index=0,
            allow_fixture_prime=True,
            temporal_len=4,
        )
        handler = object.__new__(Handler)
        handler.server = server
        responses: list[tuple[int, dict[str, object]]] = []
        handler._send = lambda status, payload: responses.append((status, payload))
        payload = {
            "request_id": "prime_" + "1" * 32,
            "fixture_id": "fixture-a",
            "task_id": "task-a",
            "frames": [
                {
                    "screenshot_png_base64": base64.b64encode(screenshot).decode("ascii"),
                    "viewport_width": 24,
                    "viewport_height": 16,
                    "annotation": [3, 4],
                }
            ],
            "actions": ["PRESS_ENTER"],
            "action_descriptions": ["Continue"],
        }
        handler._prime_history_fixture(payload)
        self.assertEqual(responses[-1][0], 200)
        receipt = responses[-1][1]["receipt"]
        assert isinstance(receipt, dict)
        self.assertEqual(receipt["source"], "evaluator_trajectory_fixture")
        self.assertIs(receipt["normalized_as_agent_reasoning"], False)
        self.assertIs(receipt["normalized_as_agent_selection"], False)
        self.assertEqual(receipt["history_image_annotations"], [[3, 4]])
        self.assertEqual(server.task_step_index, 1)
        self.assertEqual(server.agent._actions, ["PRESS_ENTER"])
        self.assertEqual(server.agent.history_images_annos, [(3, 4)])
        with self.assertRaisesRegex(ValueError, "freshly reset"):
            handler._prime_history_fixture(payload)

    def test_server_memory_prime_is_explicit_and_prompt_bound(self) -> None:
        screenshot = png_bytes()
        server = SimpleNamespace(
            agent=FakeOfficialAgent(),
            active_task_id="task-a",
            task_step_index=0,
            allow_memory_prime=True,
        )
        handler = object.__new__(Handler)
        handler.server = server
        responses: list[tuple[int, dict[str, object]]] = []
        handler._send = lambda status, payload: responses.append((status, payload))
        memory_content = "Recompute the requested printed metric before choosing a route."
        handler._prime_memory_fixture(
            {
                "request_id": "memprime_" + "1" * 32,
                "fixture_id": "memory-a",
                "task_id": "task-a",
                "memory_content": memory_content,
            }
        )
        receipt = responses[-1][1]["receipt"]
        assert isinstance(receipt, dict)
        stored_memory = "['{}']".format(memory_content)
        self.assertEqual(server.agent.memory, stored_memory)
        self.assertEqual(receipt["source"], "evaluator_memory_fixture")
        self.assertIs(receipt["normalized_as_agent_memory"], False)
        handler._step(
            {
                "request_id": "req_" + "2" * 32,
                "task_id": "task-a",
                "task_goal": "Choose the largest increase",
                "screenshot_png_base64": base64.b64encode(screenshot).decode("ascii"),
                "viewport_width": 24,
                "viewport_height": 16,
            }
        )
        step_receipt = responses[-1][1]["receipt"]
        assert isinstance(step_receipt, dict)
        self.assertEqual(
            step_receipt["memory_text_sha256_before"],
            hashlib.sha256(stored_memory.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(step_receipt["model_call_memory_segment_occurrences"], 1)

    def test_server_controller_call_is_same_checkpoint_and_state_isolated(self) -> None:
        screenshot = png_bytes()
        server = SimpleNamespace(
            agent=FakeOfficialAgent(),
            active_task_id="task-a",
            task_step_index=0,
            controller_call_index=0,
            allow_controller_call=True,
        )
        handler = object.__new__(Handler)
        handler.server = server
        responses: list[tuple[int, dict[str, object]]] = []
        handler._send = lambda status, payload: responses.append((status, payload))
        question = "<image>\nExtract visible printed values."
        handler._controller_call(
            {
                "request_id": "ctrl_" + "1" * 32,
                "task_id": "task-a",
                "stage_id": "evidence_and_reversal",
                "question": question,
                "screenshot_png_base64": base64.b64encode(screenshot).decode("ascii"),
                "viewport_width": 24,
                "viewport_height": 16,
            }
        )
        self.assertEqual(responses[-1][0], 200)
        receipt = responses[-1][1]["receipt"]
        assert isinstance(receipt, dict)
        self.assertEqual(receipt["controller_call_index"], 0)
        self.assertIs(receipt["agent_state_unchanged"], True)
        self.assertEqual(receipt["task_step_index_after"], 0)
        self.assertEqual(server.agent._actions, [])
        self.assertEqual(server.agent.history_images, [])
        self.assertEqual(server.controller_call_index, 1)

    def test_client_rejects_missing_receipt(self) -> None:
        client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)
        with patch.object(
            client,
            "_request",
            side_effect=[
                {
                    "status": "reset",
                    "task_id": "task-a",
                    "next_task_step_index": 0,
                },
                {"action_raw": "WAIT", "action_description": "wait"},
            ],
        ):
            client.reset("task-a")
            with self.assertRaisesRegex(AgentRuntimeError, "omitted receipt object"):
                client.step(png_bytes(), "goal", "task-a", 24, 16)

    def test_client_rejects_receipt_for_another_request(self) -> None:
        screenshot = png_bytes()
        client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)

        def response(method: str, path: str, payload: object = None) -> dict[str, object]:
            del method
            if path == "/reset":
                return {
                    "status": "reset",
                    "task_id": "task-a",
                    "next_task_step_index": 0,
                }
            return {
                "action_raw": "WAIT",
                "action_description": "wait",
                "receipt": {
                    "schema_version": "gui_reflection_step_receipt.v1",
                    "request_id": "req_" + "0" * 32,
                    "response_id": "resp_" + "1" * 32,
                    "task_id": "task-a",
                    "task_step_index": 0,
                    "screenshot_png_sha256": hashlib.sha256(screenshot).hexdigest(),
                    "task_goal_sha256": hashlib.sha256(b"goal").hexdigest(),
                    "viewport": {"width": 24, "height": 16},
                    "history_image_count_before": 0,
                    "history_image_sha256_before": [],
                    "history_image_annotations_before": [],
                    "model_call_input_image_sha256": [_rgb_image_sha256(screenshot)],
                    "model_call_input_image_sizes": [[24, 16]],
                    "action_count_before": 0,
                    "action_history_sha256_before": hashlib.sha256(
                        b'{"actions":[],"action_descriptions":[]}'
                    ).hexdigest(),
                    "memory_empty_before": True,
                    **prompt_receipt_fields(),
                    "generation_config": OFFICIAL_DETERMINISTIC_GENERATION_CONFIG,
                },
            }

        with patch.object(client, "_request", side_effect=response):
            client.reset("task-a")
            with self.assertRaisesRegex(AgentRuntimeError, "does not match this request"):
                client.step(screenshot, "goal", "task-a", 24, 16)

    def test_client_rejects_nonempty_step_zero_and_changed_generation(self) -> None:
        screenshot = png_bytes()
        request_id = "req_" + "2" * 32

        def receipt(response_digit: str) -> dict[str, object]:
            return {
                "schema_version": "gui_reflection_step_receipt.v1",
                "request_id": request_id,
                "response_id": "resp_" + response_digit * 32,
                "task_id": "task-a",
                "task_step_index": 0,
                "screenshot_png_sha256": hashlib.sha256(screenshot).hexdigest(),
                "task_goal_sha256": hashlib.sha256(b"goal").hexdigest(),
                "viewport": {"width": 24, "height": 16},
                "history_image_count_before": 0,
                "history_image_sha256_before": [],
                "history_image_annotations_before": [],
                "model_call_input_image_sha256": [_rgb_image_sha256(screenshot)],
                "model_call_input_image_sizes": [[24, 16]],
                "action_count_before": 0,
                "action_history_sha256_before": hashlib.sha256(
                    b'{"actions":[],"action_descriptions":[]}'
                ).hexdigest(),
                "memory_empty_before": True,
                **prompt_receipt_fields(),
                "generation_config": dict(OFFICIAL_DETERMINISTIC_GENERATION_CONFIG),
            }

        mutations = [
            (
                "nonempty memory",
                lambda value: value.update(memory_empty_before=False),
                "memory digest is inconsistent",
            ),
            (
                "nonempty action history",
                lambda value: value.update(action_history_sha256_before="f" * 64),
                "step zero must have empty action history",
            ),
            (
                "sampling",
                lambda value: value["generation_config"].update(do_sample=True),
                "not the official deterministic config",
            ),
            (
                "beam search",
                lambda value: value["generation_config"].update(num_beams=2),
                "not the official deterministic config",
            ),
        ]
        for index, (label, mutate, expected_error) in enumerate(mutations, start=3):
            with self.subTest(label=label):
                client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)
                candidate = receipt(f"{index:x}")
                mutate(candidate)
                with self.assertRaisesRegex(AgentRuntimeError, expected_error):
                    client._validate_step_receipt(
                        candidate,
                        request_id=request_id,
                        screenshot_png=screenshot,
                        task_goal="goal",
                        task_id="task-a",
                        viewport_width=24,
                        viewport_height=16,
                    )

    def test_client_rejects_history_digest_count_mismatch(self) -> None:
        screenshot = png_bytes()
        client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)
        client._next_task_step_index = 1
        candidate = {
            "schema_version": "gui_reflection_step_receipt.v1",
            "request_id": "req_" + "a" * 32,
            "response_id": "resp_" + "b" * 32,
            "task_id": "task-a",
            "task_step_index": 1,
            "screenshot_png_sha256": hashlib.sha256(screenshot).hexdigest(),
            "task_goal_sha256": hashlib.sha256(b"goal").hexdigest(),
            "viewport": {"width": 24, "height": 16},
            "history_image_count_before": 1,
            "history_image_sha256_before": [],
            "history_image_annotations_before": [None],
            "model_call_input_image_sha256": ["d" * 64, _rgb_image_sha256(screenshot)],
            "model_call_input_image_sizes": [[448, 448], [24, 16]],
            "action_count_before": 1,
            "action_history_sha256_before": "c" * 64,
            "memory_empty_before": True,
            **prompt_receipt_fields(),
            "generation_config": dict(OFFICIAL_DETERMINISTIC_GENERATION_CONFIG),
        }
        with self.assertRaisesRegex(
            AgentRuntimeError, "history_image_sha256_before is inconsistent"
        ):
            client._validate_step_receipt(
                candidate,
                request_id="req_" + "a" * 32,
                screenshot_png=screenshot,
                task_goal="goal",
                task_id="task-a",
                viewport_width=24,
                viewport_height=16,
            )

    def test_step_result_old_three_argument_construction_remains_valid(self) -> None:
        action = ParsedAction("WAIT", (), "WAIT")
        result = StepResult(action, "WAIT", "wait")
        self.assertIsNone(result.receipt)

    def test_client_validates_fixture_prime_receipt_and_advances_step(self) -> None:
        screenshot = png_bytes()
        frame = FixtureHistoryFrame(screenshot, 24, 16, (3, 4))
        client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)

        def response(method: str, path: str, payload: object = None) -> dict[str, object]:
            del method
            assert isinstance(payload, dict)
            if path == "/reset":
                return {
                    "status": "reset",
                    "task_id": "task-a",
                    "next_task_step_index": 0,
                }
            self.assertEqual(path, "/prime-history-fixture")
            action_digest = hashlib.sha256(
                b'{"actions":["PRESS_ENTER"],"action_descriptions":["Continue"]}'
            ).hexdigest()
            return {
                "status": "primed",
                "receipt": {
                    "schema_version": "gui_reflection_history_fixture_receipt.v1",
                    "request_id": payload["request_id"],
                    "fixture_id": "fixture-a",
                    "task_id": "task-a",
                    "source": "evaluator_trajectory_fixture",
                    "normalized_as_agent_reasoning": False,
                    "normalized_as_agent_selection": False,
                    "frame_count": 1,
                    "raw_png_sha256": [hashlib.sha256(screenshot).hexdigest()],
                    "history_rgb_sha256": [_rgb_image_sha256(screenshot)],
                    "history_image_annotations": [[3, 4]],
                    "action_history_sha256": action_digest,
                    "memory_empty_after": True,
                    "viewport": {"width": 24, "height": 16},
                    "next_task_step_index": 1,
                },
            }

        with patch.object(client, "_request", side_effect=response):
            client.reset("task-a")
            receipt = client.prime_history_fixture(
                fixture_id="fixture-a",
                task_id="task-a",
                frames=[frame],
                actions=["PRESS_ENTER"],
                action_descriptions=["Continue"],
            )
        self.assertEqual(receipt["frame_count"], 1)
        self.assertEqual(client._next_task_step_index, 1)

    def test_client_validates_memory_prime_receipt_without_advancing_step(self) -> None:
        client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)
        memory_content = "Verify printed values and remap the entity to its route."
        stored_memory = "['{}']".format(memory_content)

        def response(method: str, path: str, payload: object = None) -> dict[str, object]:
            del method
            assert isinstance(payload, dict)
            if path == "/reset":
                return {
                    "status": "reset",
                    "task_id": "task-a",
                    "next_task_step_index": 0,
                }
            self.assertEqual(path, "/prime-memory-fixture")
            return {
                "status": "primed",
                "receipt": {
                    "schema_version": "gui_reflection_memory_fixture_receipt.v1",
                    "request_id": payload["request_id"],
                    "fixture_id": "memory-a",
                    "task_id": "task-a",
                    "source": "evaluator_memory_fixture",
                    "normalized_as_agent_reasoning": False,
                    "normalized_as_agent_memory": False,
                    "memory_content_sha256": hashlib.sha256(
                        memory_content.encode("utf-8")
                    ).hexdigest(),
                    "memory_content_length": len(memory_content),
                    "stored_memory_sha256": hashlib.sha256(
                        stored_memory.encode("utf-8")
                    ).hexdigest(),
                    "stored_memory_length": len(stored_memory),
                    "storage_format": "official_first_MEMORIZE_list_string",
                    "memory_empty_before": True,
                    "memory_empty_after": False,
                    "history_image_count_after": 0,
                    "action_count_after": 0,
                    "action_history_sha256_after": hashlib.sha256(
                        b'{"actions":[],"action_descriptions":[]}'
                    ).hexdigest(),
                    "next_task_step_index": 0,
                },
            }

        with patch.object(client, "_request", side_effect=response):
            client.reset("task-a")
            receipt = client.prime_memory_fixture(
                fixture_id="memory-a",
                task_id="task-a",
                memory_content=memory_content,
            )
        self.assertEqual(receipt["stored_memory_length"], len(stored_memory))
        self.assertEqual(client._next_task_step_index, 0)
        self.assertEqual(client._expected_initial_memory, stored_memory)

    def test_client_validates_controller_call_receipt(self) -> None:
        screenshot = png_bytes()
        question = "<image>\nExtract visible printed values."
        raw = "EVIDENCE_JSON: {\"records\":[]}\n<ACTION>: PRESS_BACK"
        official_action = {"action_type": "PRESS_BACK", "parameters": []}
        official_action_hash = hashlib.sha256(
            json.dumps(
                official_action,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        client = HttpAgentClient("http://127.0.0.1:8091", timeout_seconds=2)

        def response(method: str, path: str, payload: object = None) -> dict[str, object]:
            del method
            assert isinstance(payload, dict)
            if path == "/reset":
                return {
                    "status": "reset",
                    "task_id": "task-a",
                    "next_task_step_index": 0,
                }
            self.assertEqual(path, "/controller-call")
            return {
                "status": "completed",
                "output_raw": raw,
                "official_action_parsed": official_action,
                "receipt": {
                    "schema_version": "gui_reflection_controller_call_receipt.v2",
                    "request_id": payload["request_id"],
                    "response_id": "ctrlresp_" + "1" * 32,
                    "task_id": "task-a",
                    "controller_call_index": 0,
                    "stage_id": "evidence_and_reversal",
                    "source": "premise_aware_controller_v1_same_checkpoint",
                    "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
                    "question_length": len(question),
                    "question_token_count": 6,
                    "system_prompt_sha256": "a" * 64,
                    "screenshot_png_sha256": hashlib.sha256(screenshot).hexdigest(),
                    "viewport": {"width": 24, "height": 16},
                    "model_call_input_image_sha256": [_rgb_image_sha256(screenshot)],
                    "model_call_input_image_sizes": [[24, 16]],
                    "generation_config": dict(OFFICIAL_DETERMINISTIC_GENERATION_CONFIG),
                    "output_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "output_length": len(raw),
                    "output_token_count": 7,
                    "official_action_parser": "GUI_Reflection.parse_action_output",
                    "official_action_parsed_sha256": official_action_hash,
                    "latency_ms": 12,
                    "agent_state_empty_before": True,
                    "agent_state_unchanged": True,
                    "task_step_index_after": 0,
                },
            }

        with patch.object(client, "_request", side_effect=response):
            client.reset("task-a")
            result = client.controller_call(
                screenshot_png=screenshot,
                question=question,
                stage_id="evidence_and_reversal",
                task_id="task-a",
                viewport_width=24,
                viewport_height=16,
            )
        self.assertEqual(result.output_raw, raw)
        self.assertEqual(result.official_action_parsed, official_action)
        self.assertEqual(client._next_controller_call_index, 1)
        self.assertEqual(client._next_task_step_index, 0)


if __name__ == "__main__":
    unittest.main()
