#!/usr/bin/env python3
"""Persistent HTTP wrapper around the official GUI_Reflection_Agent class."""

from __future__ import annotations

import argparse
import base64
import hashlib
from io import BytesIO
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import time
from typing import Any
import uuid

from PIL import Image


MAX_REQUEST_BYTES = 32 * 1024 * 1024


class CapturingModel:
    """Capture the unmodified model response while preserving official logic."""

    def __init__(self, wrapped: Any) -> None:
        self.wrapped = wrapped
        self.last_output = ""
        self.last_input_image_sha256: list[str] = []
        self.last_input_image_sizes: list[list[int]] = []
        self.last_question = ""
        self.last_question_sha256 = ""
        self.last_question_length = 0
        self.last_question_token_count: int | None = None
        self.last_output_token_count: int | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        question = args[0] if args else kwargs.get("question")
        if not isinstance(question, str):
            raise ValueError("official model call did not expose a text question")
        self.last_question = question
        self.last_question_sha256 = hashlib.sha256(
            question.encode("utf-8")
        ).hexdigest()
        self.last_question_length = len(question)
        tokenizer = getattr(self.wrapped, "tokenizer", None)
        self.last_question_token_count = None
        if tokenizer is not None:
            tokenized = tokenizer(question, add_special_tokens=False)
            input_ids = tokenized.get("input_ids")
            if isinstance(input_ids, list):
                self.last_question_token_count = len(input_ids)
        input_images = args[1] if len(args) > 1 else kwargs.get("input_images")
        if not isinstance(input_images, (list, tuple)) or not all(
            isinstance(image, Image.Image) for image in input_images
        ):
            raise ValueError("official model call did not expose an image sequence")
        self.last_input_image_sha256 = [
            _history_image_sha256(image) for image in input_images
        ]
        self.last_input_image_sizes = [
            [int(image.width), int(image.height)] for image in input_images
        ]
        output = self.wrapped(*args, **kwargs)
        self.last_output = str(output)
        self.last_output_token_count = None
        if tokenizer is not None:
            tokenized_output = tokenizer(self.last_output, add_special_tokens=False)
            output_ids = tokenized_output.get("input_ids")
            if isinstance(output_ids, list):
                self.last_output_token_count = len(output_ids)
        return output

    def __getattr__(self, name: str) -> Any:
        return getattr(self.wrapped, name)


def validate_official_inputs(official_repo: Path, model_path: Path) -> None:
    expected_agent = official_repo / "internvl_chat" / "gui_agent.py"
    expected_infer = official_repo / "internvl_chat" / "eval" / "infer.py"
    if not expected_agent.is_file() or not expected_infer.is_file():
        raise SystemExit(
            "--official-repo must be the penghao-wu/GUI_Reflection checkout "
            "containing internvl_chat/gui_agent.py and internvl_chat/eval/infer.py"
        )
    if not model_path.is_dir():
        raise SystemExit(
            "--model-path must point to the real GUI-Reflection checkpoint; "
            "ordinary InternVL fallback is disabled"
        )
    if not (model_path / "config.json").is_file():
        raise SystemExit(f"checkpoint is missing config.json: {model_path}")
    weight_files = list(model_path.glob("*.safetensors")) + list(model_path.glob("*.bin"))
    if not any(path.is_file() and path.stat().st_size > 0 for path in weight_files):
        raise SystemExit(
            f"checkpoint contains no local non-empty model weights: {model_path}; "
            "the adapter will not substitute another model"
        )


def load_official_agent(official_repo: Path, model_path: Path, temporal_len: int) -> Any:
    validate_official_inputs(official_repo, model_path)
    internvl_root = official_repo / "internvl_chat"
    sys.path.insert(0, str(internvl_root))
    try:
        from gui_agent import (  # type: ignore
            GUI_Reflection_Agent,
            SYSTEM_PROMPT,
            parse_action_output,
        )
    except Exception as exc:
        raise SystemExit(f"failed to import official GUI_Reflection_Agent: {exc}") from exc
    agent = GUI_Reflection_Agent(str(model_path), temporal_len=temporal_len)
    agent.model = CapturingModel(agent.model)
    agent._phase3_official_system_prompt = str(SYSTEM_PROMPT)
    agent._phase3_official_parse_action_output = parse_action_output
    # infer.Model deterministically inserts these same two ids into the mutable
    # generation dictionary on its first call.  Materialize them at service load
    # so the first Phase-3 cell and every later cell have byte-identical decoding
    # configuration; this does not change the values used by official inference.
    tokenizer = agent.model.wrapped.tokenizer
    agent.generation_config["eos_token_id"] = [
        int(tokenizer.eos_token_id),
        int(tokenizer.convert_tokens_to_ids(["<|im_end|>"])[0]),
    ]
    return agent


class AgentHTTPServer(HTTPServer):
    agent: Any
    active_task_id: str | None
    official_repo: Path
    model_path: Path
    temporal_len: int
    task_step_index: int
    allow_fixture_prime: bool
    allow_memory_prime: bool
    allow_controller_call: bool
    controller_call_index: int


def _valid_typed_id(value: object, prefix: str) -> bool:
    """Return whether *value* is a canonical, type-prefixed random identifier."""

    if not isinstance(value, str) or not value.startswith(prefix):
        return False
    suffix = value[len(prefix) :]
    return len(suffix) == 32 and all(character in "0123456789abcdef" for character in suffix)


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _history_image_sha256(image: Image.Image) -> str:
    """Digest a history frame by dimensions and canonical RGB pixels."""

    rgb = image.convert("RGB")
    digest = hashlib.sha256()
    digest.update(b"gui-reflection-history-rgb-v1\0")
    digest.update(rgb.width.to_bytes(8, "big"))
    digest.update(rgb.height.to_bytes(8, "big"))
    digest.update(rgb.tobytes())
    return digest.hexdigest()


def _action_history_sha256(actions: object, descriptions: object) -> str:
    """Digest both official action-history arrays without lossy pairing."""

    payload = json.dumps(
        {
            "actions": list(actions) if actions is not None else [],
            "action_descriptions": list(descriptions) if descriptions is not None else [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Handler(BaseHTTPRequestHandler):
    server: AgentHTTPServer

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("agent_http: " + fmt % args + "\n")

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body size is invalid")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._send(404, {"error": "not found"})
            return
        self._send(
            200,
            {
                "status": "ok",
                "implementation": "official_GUI_Reflection_Agent",
                "official_repo": str(self.server.official_repo),
                "model_path": str(self.server.model_path),
                "temporal_len": self.server.temporal_len,
                "fixture_history_prime_enabled": self.server.allow_fixture_prime,
                "fixture_memory_prime_enabled": self.server.allow_memory_prime,
                "controller_call_enabled": self.server.allow_controller_call,
                "model_call_input_receipts": True,
                "model_call_prompt_receipts": True,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            if self.path == "/reset":
                self._reset(payload)
            elif self.path == "/prime-history-fixture":
                self._prime_history_fixture(payload)
            elif self.path == "/prime-memory-fixture":
                self._prime_memory_fixture(payload)
            elif self.path == "/controller-call":
                self._controller_call(payload)
            elif self.path == "/step":
                self._step(payload)
            else:
                self._send(404, {"error": "not found"})
        except (ValueError, KeyError, TypeError, base64.binascii.Error) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(500, {"error": f"official agent step failed: {exc}"})

    def _reset(self, payload: dict[str, Any]) -> None:
        task_id = payload.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        self.server.agent.reset()
        self.server.active_task_id = task_id
        self.server.task_step_index = 0
        self.server.controller_call_index = 0
        self._send(
            200,
            {"status": "reset", "task_id": task_id, "next_task_step_index": 0},
        )

    @staticmethod
    def _fixture_annotation(value: object, image: Image.Image) -> list[int] | None:
        if value is None:
            return None
        if (
            not isinstance(value, list)
            or len(value) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
        ):
            raise ValueError("fixture annotation must be null or [x, y]")
        x, y = value
        if not 0 <= x < image.width or not 0 <= y < image.height:
            raise ValueError("fixture annotation is outside its screenshot")
        return [x, y]

    def _prime_history_fixture(self, payload: dict[str, Any]) -> None:
        """Install an evaluator-owned, non-model history fixture for diagnostics.

        This endpoint is disabled by default and never invokes the model.  It exists
        only to make a controlled GUI-Reflection history treatment explicit and
        receipt-backed; callers must not normalize the fixture as model reasoning or
        model selection.
        """

        if not self.server.allow_fixture_prime:
            raise ValueError("fixture history priming is disabled")
        task_id = payload.get("task_id")
        if task_id != self.server.active_task_id:
            raise ValueError("task_id is not active; call /reset before fixture prime")
        fixture_id = payload.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("fixture_id must be a non-empty string")
        request_id = payload.get("request_id")
        if not _valid_typed_id(request_id, "prime_"):
            raise ValueError(
                "request_id must have the form prime_<32 lowercase hex characters>"
            )
        frames = payload.get("frames")
        actions = payload.get("actions")
        descriptions = payload.get("action_descriptions")
        if (
            not isinstance(frames, list)
            or not frames
            or len(frames) > self.server.temporal_len
        ):
            raise ValueError("fixture frames must fit the configured temporal history")
        if (
            not isinstance(actions, list)
            or not isinstance(descriptions, list)
            or len(actions) != len(frames)
            or len(descriptions) != len(frames)
            or any(not isinstance(value, str) or not value.strip() for value in actions)
            or any(
                not isinstance(value, str) or not value.strip()
                for value in descriptions
            )
        ):
            raise ValueError("fixture actions/descriptions must align with frames")
        agent = self.server.agent
        if (
            self.server.task_step_index != 0
            or list(getattr(agent, "_actions", ()))
            or list(getattr(agent, "_action_desc", ()))
            or list(getattr(agent, "history_images", ()))
            or bool(getattr(agent, "memory", ""))
        ):
            raise ValueError("fixture prime requires a freshly reset empty agent")

        decoded_images: list[Image.Image] = []
        raw_png_sha256: list[str] = []
        history_rgb_sha256: list[str] = []
        annotations: list[list[int] | None] = []
        viewport: list[int] | None = None
        for frame in frames:
            if not isinstance(frame, dict) or set(frame) != {
                "screenshot_png_base64",
                "viewport_width",
                "viewport_height",
                "annotation",
            }:
                raise ValueError("fixture frame has an unsupported shape")
            image_bytes = base64.b64decode(
                frame["screenshot_png_base64"], validate=True
            )
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            expected_size = [
                _positive_integer(frame["viewport_width"], "viewport_width"),
                _positive_integer(frame["viewport_height"], "viewport_height"),
            ]
            if [image.width, image.height] != expected_size:
                raise ValueError("fixture screenshot size does not match its viewport")
            if viewport is None:
                viewport = expected_size
            elif viewport != expected_size:
                raise ValueError("all fixture frames must have the same viewport")
            decoded_images.append(image)
            raw_png_sha256.append(hashlib.sha256(image_bytes).hexdigest())
            history_rgb_sha256.append(_history_image_sha256(image))
            annotations.append(self._fixture_annotation(frame["annotation"], image))

        agent._actions.extend(str(value) for value in actions)
        agent._action_desc.extend(str(value) for value in descriptions)
        for image, annotation in zip(decoded_images, annotations):
            agent.history_images.append(image)
            agent.history_images_annos.append(
                None if annotation is None else tuple(annotation)
            )
        self.server.task_step_index = len(frames)
        receipt = {
            "schema_version": "gui_reflection_history_fixture_receipt.v1",
            "request_id": request_id,
            "fixture_id": fixture_id,
            "task_id": task_id,
            "source": "evaluator_trajectory_fixture",
            "normalized_as_agent_reasoning": False,
            "normalized_as_agent_selection": False,
            "frame_count": len(frames),
            "raw_png_sha256": raw_png_sha256,
            "history_rgb_sha256": history_rgb_sha256,
            "history_image_annotations": annotations,
            "action_history_sha256": _action_history_sha256(actions, descriptions),
            "memory_empty_after": not bool(getattr(agent, "memory", "")),
            "viewport": {"width": viewport[0], "height": viewport[1]},
            "next_task_step_index": self.server.task_step_index,
        }
        self._send(200, {"status": "primed", "receipt": receipt})

    def _controller_call(self, payload: dict[str, Any]) -> None:
        """Run one frozen-controller prompt on the same checkpoint.

        This diagnostic endpoint never invokes ``GUI_Reflection_Agent.step`` and
        must leave its memory/action/image histories untouched.  The caller gets
        no DOM, scorer, token-role map, or evaluator truth through this endpoint.
        """

        if not self.server.allow_controller_call:
            raise ValueError("controller calls are disabled")
        task_id = payload.get("task_id")
        if task_id != self.server.active_task_id:
            raise ValueError("task_id is not active; call /reset before controller call")
        request_id = payload.get("request_id")
        if not _valid_typed_id(request_id, "ctrl_"):
            raise ValueError(
                "request_id must have the form ctrl_<32 lowercase hex characters>"
            )
        stage_id = payload.get("stage_id")
        if stage_id not in {
            "evidence_and_reversal",
            "target_action_binding",
            "submission_check",
        }:
            raise ValueError("stage_id is not a frozen premise-controller stage")
        question = payload.get("question")
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question) > 16384
            or question.count("<image>") != 1
        ):
            raise ValueError("controller question must contain exactly one <image>")
        screenshot_base64 = payload.get("screenshot_png_base64")
        if not isinstance(screenshot_base64, str):
            raise ValueError("screenshot_png_base64 must be a string")
        image_bytes = base64.b64decode(screenshot_base64, validate=True)
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        expected_size = (
            _positive_integer(payload["viewport_width"], "viewport_width"),
            _positive_integer(payload["viewport_height"], "viewport_height"),
        )
        if image.size != expected_size:
            raise ValueError("controller screenshot size does not match its viewport")

        agent = self.server.agent
        state_before = {
            "task_step_index": self.server.task_step_index,
            "actions": list(getattr(agent, "_actions", ())),
            "action_descriptions": list(getattr(agent, "_action_desc", ())),
            "history_image_sha256": [
                _history_image_sha256(value)
                for value in list(getattr(agent, "history_images", ()))
            ],
            "history_annotations": [
                None if value is None else [int(value[0]), int(value[1])]
                for value in list(getattr(agent, "history_images_annos", ()))
            ],
            "memory": str(getattr(agent, "memory", "")),
        }
        if (
            state_before["task_step_index"] != 0
            or state_before["actions"]
            or state_before["action_descriptions"]
            or state_before["history_image_sha256"]
            or state_before["history_annotations"]
            or state_before["memory"]
        ):
            raise ValueError("controller call requires reset-empty official agent state")
        system_prompt = str(getattr(agent, "_phase3_official_system_prompt", ""))
        if not system_prompt:
            raise ValueError("official controller system prompt is unavailable")
        generation_config = dict(getattr(agent, "generation_config", {}))
        started = time.perf_counter()
        raw = agent.model(
            question,
            [image],
            generation_config,
            system_message=system_prompt,
        )
        official_parser = getattr(
            agent, "_phase3_official_parse_action_output", None
        )
        if not callable(official_parser):
            raise ValueError("official controller action parser is unavailable")
        official_action_parsed = official_parser(
            str(raw), image.width, image.height
        )
        if (
            not isinstance(official_action_parsed, dict)
            or not isinstance(official_action_parsed.get("action_type"), str)
            or not isinstance(official_action_parsed.get("parameters"), list)
        ):
            raise ValueError("official controller action parser returned invalid data")
        official_action_json = json.dumps(
            official_action_parsed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        latency_ms = int(round((time.perf_counter() - started) * 1000))
        state_after = {
            "task_step_index": self.server.task_step_index,
            "actions": list(getattr(agent, "_actions", ())),
            "action_descriptions": list(getattr(agent, "_action_desc", ())),
            "history_image_sha256": [
                _history_image_sha256(value)
                for value in list(getattr(agent, "history_images", ()))
            ],
            "history_annotations": [
                None if value is None else [int(value[0]), int(value[1])]
                for value in list(getattr(agent, "history_images_annos", ()))
            ],
            "memory": str(getattr(agent, "memory", "")),
        }
        if state_after != state_before:
            raise ValueError("controller call mutated official agent state")
        model_hashes = list(getattr(agent.model, "last_input_image_sha256", ()))
        model_sizes = list(getattr(agent.model, "last_input_image_sizes", ()))
        if model_hashes != [_history_image_sha256(image)] or model_sizes != [
            [image.width, image.height]
        ]:
            raise ValueError("controller model image receipt is incomplete")
        question_sha = hashlib.sha256(question.encode("utf-8")).hexdigest()
        if getattr(agent.model, "last_question_sha256", None) != question_sha:
            raise ValueError("controller model question receipt is incomplete")
        response_id = "ctrlresp_" + uuid.uuid4().hex
        receipt = {
            "schema_version": "gui_reflection_controller_call_receipt.v2",
            "request_id": request_id,
            "response_id": response_id,
            "task_id": task_id,
            "controller_call_index": self.server.controller_call_index,
            "stage_id": stage_id,
            "source": "premise_aware_controller_v1_same_checkpoint",
            "question_sha256": question_sha,
            "question_length": len(question),
            "question_token_count": getattr(
                agent.model, "last_question_token_count", None
            ),
            "system_prompt_sha256": hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest(),
            "screenshot_png_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "viewport": {"width": image.width, "height": image.height},
            "model_call_input_image_sha256": model_hashes,
            "model_call_input_image_sizes": model_sizes,
            "generation_config": generation_config,
            "output_sha256": hashlib.sha256(str(raw).encode("utf-8")).hexdigest(),
            "output_length": len(str(raw)),
            "output_token_count": getattr(agent.model, "last_output_token_count", None),
            "official_action_parser": "GUI_Reflection.parse_action_output",
            "official_action_parsed_sha256": hashlib.sha256(
                official_action_json.encode("utf-8")
            ).hexdigest(),
            "latency_ms": latency_ms,
            "agent_state_empty_before": True,
            "agent_state_unchanged": True,
            "task_step_index_after": self.server.task_step_index,
        }
        self.server.controller_call_index += 1
        self._send(
            200,
            {
                "status": "completed",
                "output_raw": str(raw),
                "official_action_parsed": official_action_parsed,
                "receipt": receipt,
            },
        )

    def _prime_memory_fixture(self, payload: dict[str, Any]) -> None:
        """Install evaluator-owned memory in the official agent storage format.

        The endpoint is disabled by default, requires a freshly reset agent, and
        never calls the model.  Its receipt makes the intervention distinguishable
        from a model-emitted ``MEMORIZE`` action.
        """

        if not self.server.allow_memory_prime:
            raise ValueError("fixture memory priming is disabled")
        task_id = payload.get("task_id")
        if task_id != self.server.active_task_id:
            raise ValueError("task_id is not active; call /reset before memory prime")
        fixture_id = payload.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("fixture_id must be a non-empty string")
        request_id = payload.get("request_id")
        if not _valid_typed_id(request_id, "memprime_"):
            raise ValueError(
                "request_id must have the form memprime_<32 lowercase hex characters>"
            )
        memory_content = payload.get("memory_content")
        if (
            not isinstance(memory_content, str)
            or not memory_content.strip()
            or len(memory_content) > 4096
            or any(character in memory_content for character in ("\x00", "\r", "\n"))
        ):
            raise ValueError(
                "memory_content must be a non-empty single-line string of at most 4096 characters"
            )
        agent = self.server.agent
        if (
            self.server.task_step_index != 0
            or list(getattr(agent, "_actions", ()))
            or list(getattr(agent, "_action_desc", ()))
            or list(getattr(agent, "history_images", ()))
            or bool(getattr(agent, "memory", ""))
        ):
            raise ValueError("memory prime requires a freshly reset empty agent")

        # This is exactly the representation produced by the official
        # GUI_Reflection_Agent after its first MEMORIZE action.
        stored_memory = "['{}']".format(memory_content)
        agent.memory = stored_memory
        empty_action_digest = _action_history_sha256([], [])
        receipt = {
            "schema_version": "gui_reflection_memory_fixture_receipt.v1",
            "request_id": request_id,
            "fixture_id": fixture_id,
            "task_id": task_id,
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
            "action_history_sha256_after": empty_action_digest,
            "next_task_step_index": 0,
        }
        self._send(200, {"status": "primed", "receipt": receipt})

    def _step(self, payload: dict[str, Any]) -> None:
        task_id = payload.get("task_id")
        if task_id != self.server.active_task_id:
            raise ValueError("task_id is not active; call /reset before /step")
        request_id = payload.get("request_id")
        if not _valid_typed_id(request_id, "req_"):
            raise ValueError("request_id must have the form req_<32 lowercase hex characters>")
        goal = payload.get("task_goal")
        screenshot_base64 = payload.get("screenshot_png_base64")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("task_goal must be a non-empty string")
        if not isinstance(screenshot_base64, str):
            raise ValueError("screenshot_png_base64 must be a string")
        image_bytes = base64.b64decode(screenshot_base64, validate=True)
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        expected_size = (
            _positive_integer(payload["viewport_width"], "viewport_width"),
            _positive_integer(payload["viewport_height"], "viewport_height"),
        )
        if image.size != expected_size:
            raise ValueError(
                f"screenshot size {image.size} does not match declared viewport {expected_size}"
            )

        # Capture these values before agent.step mutates all four histories.  In
        # particular, infer.Model may also add eos_token_id to generation_config,
        # so the receipt records the exact configuration supplied for this call.
        actions_before = list(getattr(self.server.agent, "_actions", ()))
        action_descriptions_before = list(
            getattr(self.server.agent, "_action_desc", ())
        )
        history_images_before = list(
            getattr(self.server.agent, "history_images", ())
        )
        history_annotations_before = list(
            getattr(self.server.agent, "history_images_annos", ())
        )
        if len(history_annotations_before) != len(history_images_before):
            raise ValueError("official agent history image/annotation arrays are misaligned")
        action_count_before = len(actions_before)
        history_image_count_before = len(history_images_before)
        history_image_sha256_before = [
            _history_image_sha256(history_image)
            for history_image in history_images_before
        ]
        action_history_sha256_before = _action_history_sha256(
            actions_before, action_descriptions_before
        )
        memory_before = str(getattr(self.server.agent, "memory", ""))
        memory_empty_before = not bool(memory_before)
        memory_text_sha256_before = hashlib.sha256(
            memory_before.encode("utf-8")
        ).hexdigest()
        memory_text_length_before = len(memory_before)
        generation_config = dict(getattr(self.server.agent, "generation_config", {}))
        task_step_index = self.server.task_step_index
        parsed = self.server.agent.step(image, goal)
        raw = self.server.agent.model.last_output
        model_call_hashes = list(
            getattr(self.server.agent.model, "last_input_image_sha256", ())
        )
        model_call_sizes = list(
            getattr(self.server.agent.model, "last_input_image_sizes", ())
        )
        if (
            len(model_call_hashes) != history_image_count_before + 1
            or len(model_call_sizes) != history_image_count_before + 1
        ):
            raise ValueError("captured model-call image receipt is incomplete")
        model_question = getattr(self.server.agent.model, "last_question", None)
        model_question_sha256 = getattr(
            self.server.agent.model, "last_question_sha256", None
        )
        model_question_length = getattr(
            self.server.agent.model, "last_question_length", None
        )
        if not isinstance(model_question, str):
            raise ValueError("captured model-call question receipt is incomplete")
        expected_memory_segment = (
            f"<MEMORY> (stored memory content): {memory_before}\n"
        )
        memory_segment_occurrences = model_question.count(expected_memory_segment)
        if (
            model_question_sha256
            != hashlib.sha256(model_question.encode("utf-8")).hexdigest()
            or model_question_length != len(model_question)
            or memory_segment_occurrences != 1
        ):
            raise ValueError("captured model-call memory binding is incomplete")
        description = ""
        if getattr(self.server.agent, "_action_desc", None):
            description = str(self.server.agent._action_desc[-1])
        response_id = "resp_" + uuid.uuid4().hex
        receipt = {
            "schema_version": "gui_reflection_step_receipt.v1",
            "request_id": request_id,
            "response_id": response_id,
            "task_id": task_id,
            "task_step_index": task_step_index,
            "screenshot_png_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "task_goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
            "viewport": {"width": expected_size[0], "height": expected_size[1]},
            "history_image_count_before": history_image_count_before,
            "history_image_sha256_before": history_image_sha256_before,
            "history_image_annotations_before": [
                None if value is None else [int(value[0]), int(value[1])]
                for value in history_annotations_before
            ],
            "model_call_input_image_sha256": model_call_hashes,
            "model_call_input_image_sizes": model_call_sizes,
            "action_count_before": action_count_before,
            "action_history_sha256_before": action_history_sha256_before,
            "memory_empty_before": memory_empty_before,
            "memory_text_sha256_before": memory_text_sha256_before,
            "memory_text_length_before": memory_text_length_before,
            "model_call_question_sha256": model_question_sha256,
            "model_call_question_length": model_question_length,
            "model_call_question_token_count": getattr(
                self.server.agent.model, "last_question_token_count", None
            ),
            "model_call_output_token_count": getattr(
                self.server.agent.model, "last_output_token_count", None
            ),
            "model_call_memory_segment_sha256": hashlib.sha256(
                expected_memory_segment.encode("utf-8")
            ).hexdigest(),
            "model_call_memory_segment_occurrences": memory_segment_occurrences,
            "generation_config": generation_config,
        }
        self.server.task_step_index += 1
        self._send(
            200,
            {
                "action_raw": raw,
                "action_description": description,
                "action_parsed": parsed,
                "receipt": receipt,
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-repo", required=True, type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--temporal-len", type=int, default=4)
    parser.add_argument(
        "--allow-fixture-prime",
        action="store_true",
        help="enable the receipt-backed evaluator history-fixture endpoint",
    )
    parser.add_argument(
        "--allow-memory-prime",
        action="store_true",
        help="enable the receipt-backed evaluator memory-fixture endpoint",
    )
    parser.add_argument(
        "--allow-controller-call",
        action="store_true",
        help="enable same-checkpoint receipt-backed premise-controller calls",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if args.temporal_len < 0:
        raise SystemExit("--temporal-len must be non-negative")
    official_repo = args.official_repo.resolve()
    model_path = args.model_path.resolve()
    agent = load_official_agent(official_repo, model_path, args.temporal_len)
    server = AgentHTTPServer((args.host, args.port), Handler)
    server.agent = agent
    server.active_task_id = None
    server.official_repo = official_repo
    server.model_path = model_path
    server.temporal_len = args.temporal_len
    server.task_step_index = 0
    server.allow_fixture_prime = bool(args.allow_fixture_prime)
    server.allow_memory_prime = bool(args.allow_memory_prime)
    server.allow_controller_call = bool(args.allow_controller_call)
    server.controller_call_index = 0
    print(
        json.dumps(
            {
                "status": "ready",
                "host": args.host,
                "port": args.port,
                "implementation": "official_GUI_Reflection_Agent",
                "model_path": str(model_path),
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
