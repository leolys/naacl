"""HTTP and managed-subprocess clients for a persistent official agent."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import ipaddress
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Protocol, Sequence
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from PIL import Image

from .actions import KNOWN_ACTIONS, ParsedAction, action_from_server, parse_official_action


class AgentRuntimeError(RuntimeError):
    """The official-model service could not start or answer correctly."""


OFFICIAL_DETERMINISTIC_GENERATION_CONFIG: dict[str, Any] = {
    "max_new_tokens": 1024,
    "do_sample": False,
    "temperature": 0.0,
    "top_k": 0,
    "top_p": 1.0,
    "repetition_penalty": 1.0,
    "num_beams": 1,
}


def _empty_action_history_sha256() -> str:
    payload = json.dumps(
        {"actions": [], "action_descriptions": []},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _action_history_sha256(
    actions: Sequence[str], action_descriptions: Sequence[str]
) -> str:
    payload = json.dumps(
        {
            "actions": list(actions),
            "action_descriptions": list(action_descriptions),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _rgb_image_sha256(png: bytes) -> str:
    image = Image.open(BytesIO(png)).convert("RGB")
    digest = hashlib.sha256()
    digest.update(b"gui-reflection-history-rgb-v1\0")
    digest.update(image.width.to_bytes(8, "big"))
    digest.update(image.height.to_bytes(8, "big"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_official_generation_config(config: object) -> None:
    if not isinstance(config, dict):
        raise AgentRuntimeError("agent receipt generation_config must be an object")
    allowed_keys = set(OFFICIAL_DETERMINISTIC_GENERATION_CONFIG) | {"eos_token_id"}
    if not set(config).issubset(allowed_keys):
        raise AgentRuntimeError("agent receipt generation_config has unsupported fields")
    if set(OFFICIAL_DETERMINISTIC_GENERATION_CONFIG).difference(config):
        raise AgentRuntimeError("agent receipt generation_config is incomplete")

    integer_fields = {"max_new_tokens": 1024, "top_k": 0, "num_beams": 1}
    for field_name, expected in integer_fields.items():
        value = config[field_name]
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            raise AgentRuntimeError(
                "agent receipt generation_config is not the official deterministic config"
            )
    if config["do_sample"] is not False:
        raise AgentRuntimeError(
            "agent receipt generation_config is not the official deterministic config"
        )
    float_fields = {
        "temperature": 0.0,
        "top_p": 1.0,
        "repetition_penalty": 1.0,
    }
    for field_name, expected in float_fields.items():
        value = config[field_name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != expected:
            raise AgentRuntimeError(
                "agent receipt generation_config is not the official deterministic config"
            )
    if "eos_token_id" in config:
        eos_token_id = config["eos_token_id"]
        if (
            not isinstance(eos_token_id, list)
            or len(eos_token_id) != 2
            or any(
                isinstance(token_id, bool)
                or not isinstance(token_id, int)
                or token_id < 0
                for token_id in eos_token_id
            )
        ):
            raise AgentRuntimeError(
                "agent receipt generation_config has invalid service eos_token_id"
            )


@dataclass(frozen=True)
class StepResult:
    action: ParsedAction
    action_raw: str
    action_description: str
    receipt: dict[str, Any] | None = None


@dataclass(frozen=True)
class ControllerCallResult:
    output_raw: str
    official_action_parsed: dict[str, Any]
    receipt: dict[str, Any]


@dataclass(frozen=True)
class FixtureHistoryFrame:
    screenshot_png: bytes
    viewport_width: int
    viewport_height: int
    annotation: tuple[int, int] | None = None


class AgentClient(Protocol):
    def reset(self, task_id: str) -> None: ...

    def step(
        self,
        screenshot_png: bytes,
        task_goal: str,
        task_id: str,
        viewport_width: int,
        viewport_height: int,
    ) -> StepResult: ...


class HttpAgentClient:
    def __init__(self, base_url: str, timeout_seconds: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        hostname = urlsplit(self.base_url).hostname
        is_loopback = hostname == "localhost"
        if hostname and not is_loopback:
            try:
                is_loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                pass
        # Proxy environment variables are needed for checkpoint downloads on this
        # server, but the persistent model service is normally on loopback.  Use a
        # client-local no-proxy opener so health/step calls cannot leak to or fail
        # through the external proxy, without mutating the process environment.
        self._open = build_opener(ProxyHandler({})).open if is_loopback else urlopen
        self._active_task_id: str | None = None
        self._next_task_step_index = 0
        self._seen_response_ids: set[str] = set()
        self._expected_initial_memory: str | None = ""
        self._next_controller_call_index = 0

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with self._open(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AgentRuntimeError(f"agent service returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AgentRuntimeError(f"agent service request failed: {exc}") from exc
        if not isinstance(decoded, dict):
            raise AgentRuntimeError("agent service response must be a JSON object")
        return decoded

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def reset(self, task_id: str) -> None:
        response = self._request("POST", "/reset", {"task_id": task_id})
        if (
            response.get("status") != "reset"
            or response.get("task_id") != task_id
            or response.get("next_task_step_index") != 0
        ):
            raise AgentRuntimeError(f"unexpected reset response: {response}")
        self._active_task_id = task_id
        self._next_task_step_index = 0
        self._expected_initial_memory = ""
        self._next_controller_call_index = 0

    def controller_call(
        self,
        *,
        screenshot_png: bytes,
        question: str,
        stage_id: str,
        task_id: str,
        viewport_width: int,
        viewport_height: int,
    ) -> ControllerCallResult:
        """Call the frozen premise controller without mutating agent history."""

        if self._active_task_id != task_id or self._next_task_step_index != 0:
            raise AgentRuntimeError(
                "controller call requires the active reset-empty official agent"
            )
        request_id = "ctrl_" + uuid.uuid4().hex
        response = self._request(
            "POST",
            "/controller-call",
            {
                "request_id": request_id,
                "task_id": task_id,
                "stage_id": stage_id,
                "question": question,
                "screenshot_png_base64": base64.b64encode(screenshot_png).decode(
                    "ascii"
                ),
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
            },
        )
        raw = response.get("output_raw")
        official_action_parsed = response.get("official_action_parsed")
        receipt = response.get("receipt")
        if (
            response.get("status") != "completed"
            or not isinstance(raw, str)
            or not raw.strip()
            or not isinstance(official_action_parsed, dict)
            or set(official_action_parsed) != {"action_type", "parameters"}
            or official_action_parsed.get("action_type")
            not in KNOWN_ACTIONS | {"INVALID"}
            or not isinstance(official_action_parsed.get("parameters"), list)
            or not isinstance(receipt, dict)
        ):
            raise AgentRuntimeError("agent service omitted controller-call output/receipt")
        required = {
            "schema_version",
            "request_id",
            "response_id",
            "task_id",
            "controller_call_index",
            "stage_id",
            "source",
            "question_sha256",
            "question_length",
            "question_token_count",
            "system_prompt_sha256",
            "screenshot_png_sha256",
            "viewport",
            "model_call_input_image_sha256",
            "model_call_input_image_sizes",
            "generation_config",
            "output_sha256",
            "output_length",
            "output_token_count",
            "official_action_parser",
            "official_action_parsed_sha256",
            "latency_ms",
            "agent_state_empty_before",
            "agent_state_unchanged",
            "task_step_index_after",
        }
        if required.difference(receipt):
            raise AgentRuntimeError("controller-call receipt is incomplete")
        response_id = self._typed_id(
            receipt.get("response_id"), "ctrlresp_", "controller response_id"
        )
        integer_positive = (
            "question_length",
            "question_token_count",
            "output_length",
            "output_token_count",
        )
        if (
            receipt.get("schema_version")
            != "gui_reflection_controller_call_receipt.v2"
            or receipt.get("request_id") != request_id
            or receipt.get("task_id") != task_id
            or receipt.get("controller_call_index")
            != self._next_controller_call_index
            or receipt.get("stage_id") != stage_id
            or receipt.get("source")
            != "premise_aware_controller_v1_same_checkpoint"
            or receipt.get("question_sha256") != _text_sha256(question)
            or receipt.get("question_length") != len(question)
            or receipt.get("screenshot_png_sha256")
            != hashlib.sha256(screenshot_png).hexdigest()
            or receipt.get("viewport")
            != {"width": viewport_width, "height": viewport_height}
            or receipt.get("model_call_input_image_sha256")
            != [_rgb_image_sha256(screenshot_png)]
            or receipt.get("model_call_input_image_sizes")
            != [[viewport_width, viewport_height]]
            or receipt.get("output_sha256") != _text_sha256(raw)
            or receipt.get("output_length") != len(raw)
            or receipt.get("official_action_parser")
            != "GUI_Reflection.parse_action_output"
            or receipt.get("official_action_parsed_sha256")
            != hashlib.sha256(
                json.dumps(
                    official_action_parsed,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            or not _is_sha256(receipt.get("system_prompt_sha256"))
            or any(
                isinstance(receipt.get(field), bool)
                or not isinstance(receipt.get(field), int)
                or int(receipt[field]) <= 0
                for field in integer_positive
            )
            or isinstance(receipt.get("latency_ms"), bool)
            or not isinstance(receipt.get("latency_ms"), int)
            or receipt.get("latency_ms") < 0
            or receipt.get("agent_state_empty_before") is not True
            or receipt.get("agent_state_unchanged") is not True
            or receipt.get("task_step_index_after") != 0
        ):
            raise AgentRuntimeError("controller-call receipt does not match sent input")
        _validate_official_generation_config(receipt["generation_config"])
        if response_id in self._seen_response_ids:
            raise AgentRuntimeError("controller-call receipt reused a response_id")
        self._seen_response_ids.add(response_id)
        self._next_controller_call_index += 1
        return ControllerCallResult(
            output_raw=raw,
            official_action_parsed=dict(official_action_parsed),
            receipt=dict(receipt),
        )

    def prime_memory_fixture(
        self,
        *,
        fixture_id: str,
        task_id: str,
        memory_content: str,
    ) -> dict[str, Any]:
        """Install explicit evaluator-owned memory after a fresh reset."""

        if self._active_task_id != task_id or self._next_task_step_index != 0:
            raise AgentRuntimeError(
                "memory fixture requires the active task at freshly reset step zero"
            )
        if (
            not fixture_id
            or not isinstance(memory_content, str)
            or not memory_content.strip()
        ):
            raise AgentRuntimeError("memory fixture fields are incomplete")
        request_id = "memprime_" + uuid.uuid4().hex
        response = self._request(
            "POST",
            "/prime-memory-fixture",
            {
                "request_id": request_id,
                "fixture_id": fixture_id,
                "task_id": task_id,
                "memory_content": memory_content,
            },
        )
        receipt = response.get("receipt")
        if response.get("status") != "primed" or not isinstance(receipt, dict):
            raise AgentRuntimeError("agent service omitted memory-prime receipt")
        stored_memory = "['{}']".format(memory_content)
        if (
            receipt.get("schema_version")
            != "gui_reflection_memory_fixture_receipt.v1"
            or receipt.get("request_id") != request_id
            or receipt.get("fixture_id") != fixture_id
            or receipt.get("task_id") != task_id
            or receipt.get("source") != "evaluator_memory_fixture"
            or receipt.get("normalized_as_agent_reasoning") is not False
            or receipt.get("normalized_as_agent_memory") is not False
            or receipt.get("memory_content_sha256") != _text_sha256(memory_content)
            or receipt.get("memory_content_length") != len(memory_content)
            or receipt.get("stored_memory_sha256") != _text_sha256(stored_memory)
            or receipt.get("stored_memory_length") != len(stored_memory)
            or receipt.get("storage_format")
            != "official_first_MEMORIZE_list_string"
            or receipt.get("memory_empty_before") is not True
            or receipt.get("memory_empty_after") is not False
            or receipt.get("history_image_count_after") != 0
            or receipt.get("action_count_after") != 0
            or receipt.get("action_history_sha256_after")
            != _empty_action_history_sha256()
            or receipt.get("next_task_step_index") != 0
        ):
            raise AgentRuntimeError("memory-prime receipt does not match sent input")
        self._expected_initial_memory = stored_memory
        return dict(receipt)

    def prime_history_fixture(
        self,
        *,
        fixture_id: str,
        task_id: str,
        frames: Sequence[FixtureHistoryFrame],
        actions: Sequence[str],
        action_descriptions: Sequence[str],
    ) -> dict[str, Any]:
        """Install an explicit evaluator-owned history fixture after reset."""

        if self._active_task_id != task_id or self._next_task_step_index != 0:
            raise AgentRuntimeError(
                "history fixture requires the active task at freshly reset step zero"
            )
        if (
            not fixture_id
            or not frames
            or len(frames) != len(actions)
            or len(frames) != len(action_descriptions)
        ):
            raise AgentRuntimeError("history fixture fields are incomplete or misaligned")
        request_id = "prime_" + uuid.uuid4().hex
        response = self._request(
            "POST",
            "/prime-history-fixture",
            {
                "request_id": request_id,
                "fixture_id": fixture_id,
                "task_id": task_id,
                "frames": [
                    {
                        "screenshot_png_base64": base64.b64encode(
                            frame.screenshot_png
                        ).decode("ascii"),
                        "viewport_width": frame.viewport_width,
                        "viewport_height": frame.viewport_height,
                        "annotation": (
                            list(frame.annotation)
                            if frame.annotation is not None
                            else None
                        ),
                    }
                    for frame in frames
                ],
                "actions": list(actions),
                "action_descriptions": list(action_descriptions),
            },
        )
        receipt = response.get("receipt")
        if response.get("status") != "primed" or not isinstance(receipt, dict):
            raise AgentRuntimeError("agent service omitted fixture-prime receipt")
        expected_raw = [
            hashlib.sha256(frame.screenshot_png).hexdigest() for frame in frames
        ]
        expected_rgb = [_rgb_image_sha256(frame.screenshot_png) for frame in frames]
        expected_annotations = [
            list(frame.annotation) if frame.annotation is not None else None
            for frame in frames
        ]
        expected_action_digest = _action_history_sha256(actions, action_descriptions)
        expected_viewport = {
            "width": frames[0].viewport_width,
            "height": frames[0].viewport_height,
        }
        if (
            receipt.get("schema_version")
            != "gui_reflection_history_fixture_receipt.v1"
            or receipt.get("request_id") != request_id
            or receipt.get("fixture_id") != fixture_id
            or receipt.get("task_id") != task_id
            or receipt.get("source") != "evaluator_trajectory_fixture"
            or receipt.get("normalized_as_agent_reasoning") is not False
            or receipt.get("normalized_as_agent_selection") is not False
            or receipt.get("frame_count") != len(frames)
            or receipt.get("raw_png_sha256") != expected_raw
            or receipt.get("history_rgb_sha256") != expected_rgb
            or receipt.get("history_image_annotations") != expected_annotations
            or receipt.get("action_history_sha256") != expected_action_digest
            or receipt.get("memory_empty_after") is not True
            or receipt.get("viewport") != expected_viewport
            or receipt.get("next_task_step_index") != len(frames)
        ):
            raise AgentRuntimeError("fixture-prime receipt does not match sent inputs")
        self._next_task_step_index = len(frames)
        return dict(receipt)

    @staticmethod
    def _typed_id(value: object, prefix: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.startswith(prefix):
            raise AgentRuntimeError(f"agent receipt has invalid {field_name}")
        suffix = value[len(prefix) :]
        if len(suffix) != 32 or any(
            character not in "0123456789abcdef" for character in suffix
        ):
            raise AgentRuntimeError(f"agent receipt has invalid {field_name}")
        return value

    def _validate_step_receipt(
        self,
        receipt: object,
        *,
        request_id: str,
        screenshot_png: bytes,
        task_goal: str,
        task_id: str,
        viewport_width: int,
        viewport_height: int,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict):
            raise AgentRuntimeError("agent service omitted receipt object")
        required_keys = {
            "schema_version",
            "request_id",
            "response_id",
            "task_id",
            "task_step_index",
            "screenshot_png_sha256",
            "task_goal_sha256",
            "viewport",
            "history_image_count_before",
            "history_image_sha256_before",
            "history_image_annotations_before",
            "model_call_input_image_sha256",
            "model_call_input_image_sizes",
            "action_count_before",
            "action_history_sha256_before",
            "memory_empty_before",
            "memory_text_sha256_before",
            "memory_text_length_before",
            "model_call_question_sha256",
            "model_call_question_length",
            "model_call_memory_segment_sha256",
            "model_call_memory_segment_occurrences",
            "generation_config",
        }
        missing = required_keys.difference(receipt)
        if missing:
            raise AgentRuntimeError(
                "agent receipt is missing fields: " + ", ".join(sorted(missing))
            )
        if receipt["schema_version"] != "gui_reflection_step_receipt.v1":
            raise AgentRuntimeError("agent receipt has unsupported schema_version")
        echoed_request_id = self._typed_id(receipt["request_id"], "req_", "request_id")
        if echoed_request_id != request_id:
            raise AgentRuntimeError("agent receipt request_id does not match this request")
        response_id = self._typed_id(receipt["response_id"], "resp_", "response_id")
        if response_id in self._seen_response_ids:
            raise AgentRuntimeError("agent receipt reused a response_id")
        if receipt["task_id"] != task_id:
            raise AgentRuntimeError("agent receipt task_id does not match this request")
        if receipt["task_step_index"] != self._next_task_step_index:
            raise AgentRuntimeError("agent receipt task_step_index is not the expected next step")
        expected_screenshot_hash = hashlib.sha256(screenshot_png).hexdigest()
        if receipt["screenshot_png_sha256"] != expected_screenshot_hash:
            raise AgentRuntimeError("agent receipt screenshot_png_sha256 does not match sent bytes")
        expected_goal_hash = hashlib.sha256(task_goal.encode("utf-8")).hexdigest()
        if receipt["task_goal_sha256"] != expected_goal_hash:
            raise AgentRuntimeError("agent receipt task_goal_sha256 does not match sent task goal")
        if receipt["viewport"] != {"width": viewport_width, "height": viewport_height}:
            raise AgentRuntimeError("agent receipt viewport does not match this request")
        action_count = receipt["action_count_before"]
        history_count = receipt["history_image_count_before"]
        if (
            isinstance(action_count, bool)
            or not isinstance(action_count, int)
            or action_count != self._next_task_step_index
        ):
            raise AgentRuntimeError("agent receipt action_count_before is inconsistent")
        if (
            isinstance(history_count, bool)
            or not isinstance(history_count, int)
            or not 0 <= history_count <= action_count
        ):
            raise AgentRuntimeError("agent receipt history_image_count_before is inconsistent")
        history_hashes = receipt["history_image_sha256_before"]
        if (
            not isinstance(history_hashes, list)
            or len(history_hashes) != history_count
            or any(not _is_sha256(history_hash) for history_hash in history_hashes)
        ):
            raise AgentRuntimeError(
                "agent receipt history_image_sha256_before is inconsistent"
            )
        annotations = receipt["history_image_annotations_before"]
        if (
            not isinstance(annotations, list)
            or len(annotations) != history_count
            or any(
                value is not None
                and (
                    not isinstance(value, list)
                    or len(value) != 2
                    or any(
                        isinstance(coordinate, bool)
                        or not isinstance(coordinate, int)
                        or coordinate < 0
                        for coordinate in value
                    )
                )
                for value in annotations
            )
        ):
            raise AgentRuntimeError(
                "agent receipt history_image_annotations_before is inconsistent"
            )
        model_input_hashes = receipt["model_call_input_image_sha256"]
        model_input_sizes = receipt["model_call_input_image_sizes"]
        if (
            not isinstance(model_input_hashes, list)
            or len(model_input_hashes) != history_count + 1
            or any(not _is_sha256(value) for value in model_input_hashes)
            or not isinstance(model_input_sizes, list)
            or len(model_input_sizes) != history_count + 1
            or any(
                not isinstance(size, list)
                or len(size) != 2
                or any(
                    isinstance(dimension, bool)
                    or not isinstance(dimension, int)
                    or dimension <= 0
                    for dimension in size
                )
                for size in model_input_sizes
            )
        ):
            raise AgentRuntimeError(
                "agent receipt model-call input image binding is inconsistent"
            )
        if (
            model_input_hashes[-1] != _rgb_image_sha256(screenshot_png)
            or model_input_sizes[-1] != [viewport_width, viewport_height]
        ):
            raise AgentRuntimeError(
                "agent receipt current model-call image does not match sent screenshot"
            )
        action_history_hash = receipt["action_history_sha256_before"]
        if not _is_sha256(action_history_hash):
            raise AgentRuntimeError(
                "agent receipt action_history_sha256_before is invalid"
            )
        if not isinstance(receipt["memory_empty_before"], bool):
            raise AgentRuntimeError("agent receipt memory_empty_before must be boolean")
        memory_hash = receipt["memory_text_sha256_before"]
        memory_length = receipt["memory_text_length_before"]
        if (
            not _is_sha256(memory_hash)
            or isinstance(memory_length, bool)
            or not isinstance(memory_length, int)
            or memory_length < 0
            or (memory_length == 0) is not receipt["memory_empty_before"]
        ):
            raise AgentRuntimeError("agent receipt memory digest is inconsistent")
        question_hash = receipt["model_call_question_sha256"]
        question_length = receipt["model_call_question_length"]
        if (
            not _is_sha256(question_hash)
            or isinstance(question_length, bool)
            or not isinstance(question_length, int)
            or question_length <= 0
            or not _is_sha256(receipt["model_call_memory_segment_sha256"])
            or receipt["model_call_memory_segment_occurrences"] != 1
        ):
            raise AgentRuntimeError("agent receipt model-call prompt binding is invalid")
        if self._next_task_step_index == 0:
            expected_memory = self._expected_initial_memory
            if expected_memory is None:
                raise AgentRuntimeError("agent client lost initial memory expectation")
            if (
                memory_hash != _text_sha256(expected_memory)
                or memory_length != len(expected_memory)
                or receipt["memory_empty_before"] is (len(expected_memory) > 0)
            ):
                raise AgentRuntimeError(
                    "agent receipt step zero memory does not match reset/fixture state"
                )
            expected_segment = (
                f"<MEMORY> (stored memory content): {expected_memory}\n"
            )
            if receipt["model_call_memory_segment_sha256"] != _text_sha256(
                expected_segment
            ):
                raise AgentRuntimeError(
                    "agent receipt prompt does not bind the expected initial memory"
                )
            if history_hashes:
                raise AgentRuntimeError("agent receipt step zero must have empty image history")
            if action_history_hash != _empty_action_history_sha256():
                raise AgentRuntimeError("agent receipt step zero must have empty action history")
        _validate_official_generation_config(receipt["generation_config"])
        try:
            json.dumps(receipt["generation_config"], allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise AgentRuntimeError(
                "agent receipt generation_config is not finite JSON"
            ) from exc
        self._seen_response_ids.add(response_id)
        return dict(receipt)

    def step(
        self,
        screenshot_png: bytes,
        task_goal: str,
        task_id: str,
        viewport_width: int,
        viewport_height: int,
    ) -> StepResult:
        if self._active_task_id != task_id:
            raise AgentRuntimeError("call reset(task_id) before step for this task")
        if (
            isinstance(viewport_width, bool)
            or not isinstance(viewport_width, int)
            or viewport_width <= 0
            or isinstance(viewport_height, bool)
            or not isinstance(viewport_height, int)
            or viewport_height <= 0
        ):
            raise AgentRuntimeError("viewport dimensions must be positive integers")
        request_id = "req_" + uuid.uuid4().hex
        response = self._request(
            "POST",
            "/step",
            {
                "request_id": request_id,
                "task_id": task_id,
                "task_goal": task_goal,
                "screenshot_png_base64": base64.b64encode(screenshot_png).decode("ascii"),
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
            },
        )
        receipt = self._validate_step_receipt(
            response.get("receipt"),
            request_id=request_id,
            screenshot_png=screenshot_png,
            task_goal=task_goal,
            task_id=task_id,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        raw = response.get("action_raw")
        if not isinstance(raw, str) or not raw.strip():
            raise AgentRuntimeError("agent service omitted non-empty action_raw")
        parsed_payload = response.get("action_parsed")
        if isinstance(parsed_payload, dict):
            action = action_from_server(
                parsed_payload, raw, viewport_width, viewport_height
            )
        else:
            action = parse_official_action(raw, viewport_width, viewport_height)
        description = response.get("action_description", "")
        self._next_task_step_index += 1
        return StepResult(action, raw, str(description), receipt)


class ManagedAgentServer:
    """Launch the official GUI_Reflection_Agent once and reuse it per step."""

    def __init__(
        self,
        *,
        official_repo: Path,
        model_path: Path,
        port: int,
        log_path: Path,
        python_executable: str = sys.executable,
        temporal_len: int = 4,
        allow_fixture_prime: bool = False,
        allow_memory_prime: bool = False,
        allow_controller_call: bool = False,
        startup_timeout_seconds: float = 900.0,
        request_timeout_seconds: float = 300.0,
    ) -> None:
        self.official_repo = official_repo.resolve()
        self.model_path = model_path.resolve()
        self.port = port
        self.log_path = log_path.resolve()
        self.python_executable = python_executable
        self.temporal_len = temporal_len
        self.allow_fixture_prime = bool(allow_fixture_prime)
        self.allow_memory_prime = bool(allow_memory_prime)
        self.allow_controller_call = bool(allow_controller_call)
        self.startup_timeout_seconds = startup_timeout_seconds
        self.client = HttpAgentClient(
            f"http://127.0.0.1:{port}", timeout_seconds=request_timeout_seconds
        )
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None

    def start(self) -> HttpAgentClient:
        if not self.official_repo.is_dir():
            raise AgentRuntimeError(f"official GUI-Reflection repo not found: {self.official_repo}")
        if not self.model_path.is_dir():
            raise AgentRuntimeError(
                "GUI-Reflection model path not found; no ordinary InternVL fallback is permitted: "
                f"{self.model_path}"
            )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("ab")
        server_script = Path(__file__).with_name("model_server.py")
        command = [
            self.python_executable,
            str(server_script),
            "--official-repo",
            str(self.official_repo),
            "--model-path",
            str(self.model_path),
            "--port",
            str(self.port),
            "--temporal-len",
            str(self.temporal_len),
        ]
        if self.allow_fixture_prime:
            command.append("--allow-fixture-prime")
        if self.allow_memory_prime:
            command.append("--allow-memory-prime")
        if self.allow_controller_call:
            command.append("--allow-controller-call")
        self._process = subprocess.Popen(
            command,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + self.startup_timeout_seconds
        last_error = "service has not answered yet"
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise AgentRuntimeError(
                    f"official agent server exited with code {self._process.returncode}; "
                    f"see {self.log_path}"
                )
            try:
                health = self.client.health()
                if health.get("status") == "ok":
                    if health.get("implementation") != "official_GUI_Reflection_Agent":
                        raise AgentRuntimeError(
                            f"port {self.port} is not the official GUI-Reflection service"
                        )
                    served_repo = Path(str(health.get("official_repo", ""))).resolve()
                    if served_repo != self.official_repo:
                        raise AgentRuntimeError(
                            f"port {self.port} serves a different official repo: {served_repo}"
                        )
                    served_model = Path(str(health.get("model_path", ""))).resolve()
                    if served_model != self.model_path:
                        raise AgentRuntimeError(
                            f"port {self.port} serves a different model: {served_model}"
                        )
                    if health.get("temporal_len") != self.temporal_len:
                        raise AgentRuntimeError(
                            f"port {self.port} uses temporal_len={health.get('temporal_len')!r}, "
                            f"expected {self.temporal_len}"
                        )
                    if bool(health.get("fixture_history_prime_enabled")) != (
                        self.allow_fixture_prime
                    ):
                        raise AgentRuntimeError(
                            "port fixture-history capability does not match request"
                        )
                    if bool(health.get("fixture_memory_prime_enabled")) != (
                        self.allow_memory_prime
                    ):
                        raise AgentRuntimeError(
                            "port fixture-memory capability does not match request"
                        )
                    if bool(health.get("controller_call_enabled")) != (
                        self.allow_controller_call
                    ):
                        raise AgentRuntimeError(
                            "port controller-call capability does not match request"
                        )
                    if health.get("model_call_input_receipts") is not True:
                        raise AgentRuntimeError(
                            "port does not expose exact model-call image receipts"
                        )
                    if health.get("model_call_prompt_receipts") is not True:
                        raise AgentRuntimeError(
                            "port does not expose exact model-call prompt receipts"
                        )
                    return self.client
            except AgentRuntimeError as exc:
                last_error = str(exc)
            time.sleep(0.25)
        raise AgentRuntimeError(
            f"official agent server did not become ready within "
            f"{self.startup_timeout_seconds:g}s ({last_error}); see {self.log_path}"
        )

    def close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
        if self._log_handle is not None:
            self._log_handle.close()
        self._process = None
        self._log_handle = None

    def __enter__(self) -> HttpAgentClient:
        return self.start()

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()
