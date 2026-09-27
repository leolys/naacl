"""Recorded model boundary used by the stage-two smoke harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests

from .core import BudgetLedger, assert_online_payload, write_json


@dataclass
class OnlineRequest:
    request_id: str
    phase: str
    system_prompt: str
    user_prompt: str
    image_paths: tuple[Path, ...]
    image_artifacts: tuple[str, ...]
    public_context: dict[str, Any] = field(default_factory=dict)

    @property
    def image_path(self) -> Path:
        """Backward-compatible access for single-image test backends."""

        return self.image_paths[0]

    def log_payload(self) -> dict[str, Any]:
        payload = {
            "request_id": self.request_id,
            "phase": self.phase,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "image_artifacts": list(self.image_artifacts),
            "public_context": self.public_context,
        }
        assert_online_payload(payload)
        return payload


@dataclass
class ModelReply:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelBackend(Protocol):
    @property
    def metadata(self) -> dict[str, Any]: ...

    def complete(self, request: OnlineRequest) -> ModelReply: ...


class RecordedModel:
    def __init__(self, backend: ModelBackend, *, ledger: BudgetLedger) -> None:
        self.backend = backend
        self.ledger = ledger
        self._ordinal = 0

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self.backend.metadata)

    def call(
        self,
        *,
        phase: str,
        system_prompt: str,
        user_prompt: str,
        image_path: Path | list[Path] | tuple[Path, ...],
        image_artifact: str | list[str] | tuple[str, ...],
        public_context: dict[str, Any],
        request_dir: Path,
        response_dir: Path,
    ) -> ModelReply:
        self._ordinal += 1
        request_id = f"request_{self._ordinal:04d}"
        image_paths = (image_path,) if isinstance(image_path, Path) else tuple(image_path)
        image_artifacts = (
            (image_artifact,) if isinstance(image_artifact, str) else tuple(image_artifact)
        )
        if not image_paths or len(image_paths) != len(image_artifacts):
            raise ValueError("model request needs matching non-empty image paths and artifacts")
        request = OnlineRequest(
            request_id=request_id,
            phase=phase,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_paths=image_paths,
            image_artifacts=image_artifacts,
            public_context=public_context,
        )
        request_payload = request.log_payload()
        self.ledger.charge_model(phase=phase, request_id=request_id)
        write_json(request_dir / f"{request_id}.json", request_payload)
        try:
            reply = self.backend.complete(request)
        except Exception as exc:
            write_json(
                response_dir / f"{request_id}.json",
                {
                    "request_id": request_id,
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise
        # The recorder owns the pairing identifier; backend metadata must not
        # be able to replace it with a stale or unrelated request id.
        reply.metadata = {**reply.metadata, "request_id": request_id}
        write_json(
            response_dir / f"{request_id}.json",
            {
                "request_id": request_id,
                "ok": True,
                "text": reply.text,
                "metadata": reply.metadata,
            },
        )
        return reply


class ScriptedMockBackend:
    """Visible-state-only mock for engineering smoke tests, not a research model."""

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "kind": "scripted_visible_state_mock",
            "research_result": False,
            "note": "No visual semantics are inferred by this backend.",
        }

    def complete(self, request: OnlineRequest) -> ModelReply:
        context = request.public_context
        if request.phase == "prefix":
            state = context.get("state") or {}
            link_texts = [str(item.get("text") or "") for item in state.get("links") or []]
            if "Open Dashboard" in link_texts:
                text = json.dumps({"action": "click_link", "text": "Open Dashboard"})
            elif "Open Form" in link_texts:
                text = json.dumps({"action": "click_link", "text": "Open Form"})
            else:
                current = str(context.get("current_selection") or "")
                options = list(context.get("visible_options") or [])
                if not current and options:
                    text = json.dumps(
                        {
                            "action": "select_option",
                            "select_name": "primary_action",
                            "option_text": options[0],
                        },
                        ensure_ascii=False,
                    )
                else:
                    text = json.dumps({"action": "click_button", "text": "Submit Form"})
            return ModelReply(text=text, metadata={"mock": True})
        if request.phase == "b2_decision":
            options = list(context.get("visible_options") or [])
            return ModelReply(
                text=json.dumps(
                    {"option_label": options[0] if options else "", "reason": "mock-first-visible-option"},
                    ensure_ascii=False,
                ),
                metadata={"mock": True},
            )
        if request.phase == "b3_plan":
            width = int(context.get("image_width") or 1)
            height = int(context.get("image_height") or 1)
            return ModelReply(
                text=json.dumps(
                    {
                        "observe": {
                            "screenshot_id": "dashboard",
                            "region": [0, 0, width, max(1, int(height * 0.8))],
                            "reason": "mock-crop-tool-exercise",
                        }
                    }
                ),
                metadata={"mock": True},
            )
        if request.phase == "b3_decision":
            current = str(context.get("current_selection") or "")
            options = list(context.get("visible_options") or [])
            return ModelReply(
                text=json.dumps(
                    {"option_label": current or (options[0] if options else ""), "reason": "mock-keep"},
                    ensure_ascii=False,
                ),
                metadata={"mock": True},
            )
        if request.phase == "b4_extract":
            return ModelReply(
                text=json.dumps(
                    {
                        "title": "not semantically parsed by mock",
                        "axes": [],
                        "units": [],
                        "legend": [],
                        "values": [],
                        "range": None,
                        "uncertainty": "mock extraction",
                    }
                ),
                metadata={"mock": True},
            )
        if request.phase == "b4_decision":
            current = str(context.get("current_selection") or "")
            options = list(context.get("visible_options") or [])
            return ModelReply(
                text=json.dumps(
                    {"option_label": current or (options[0] if options else ""), "reason": "mock-keep"},
                    ensure_ascii=False,
                ),
                metadata={"mock": True},
            )
        raise RuntimeError(f"unsupported mock phase: {request.phase}")


class LocalQwenServiceBackend:
    """Reuse an already-running loopback Qwen3-VL service; never starts a model."""

    def __init__(
        self,
        *,
        server_url: str,
        model_name: str = "qwen3_vl",
        max_output_tokens: int = 1024,
        temperature: float = 0.0,
        top_p: float = 1.0,
        seed: int = 12345,
    ) -> None:
        parsed = urlsplit(server_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("live smoke accepts only an already-running loopback HTTP model service")
        session = requests.Session()
        session.trust_env = False
        response = session.get(f"{server_url.rstrip('/')}/health", timeout=3)
        response.raise_for_status()
        health = response.json()
        if not (health.get("ok") or health.get("status") == "ok"):
            raise RuntimeError("loopback model health response is not ready")
        self.server_url = server_url.rstrip("/")
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.seed = seed
        self.health = {
            key: value
            for key, value in health.items()
            if key
            in {
                "ok",
                "status",
                "model",
                "model_path",
                "model_size",
                "implementation",
                "max_pixels",
                "load_seconds",
                "native_multi_image",
                "server_protocol_version",
            }
        }

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "kind": "already_running_local_qwen3_vl_http",
            "server_url": self.server_url,
            "model": self.model_name,
            "health": self.health,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "max_output_tokens": self.max_output_tokens,
            "automatic_retries": 0,
        }

    def complete(self, request: OnlineRequest) -> ModelReply:
        from adversarial_pipeline.llm_client import (
            LLMClient,
            complete_vision,
            get_last_response_metadata,
        )

        client = LLMClient(
            backend="qwen3_vl_http",
            model=self.model_name,
            qwen3_vl_server_url=self.server_url,
            qwen3_vl_model_path=str(self.health.get("model_path") or ""),
            qwen3_vl_model_size=str(self.health.get("model_size") or ""),
        )
        text = complete_vision(
            client,
            request.system_prompt,
            request.user_prompt,
            request.image_paths[0] if len(request.image_paths) == 1 else request.image_paths,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
        )
        return ModelReply(text=text, metadata=get_last_response_metadata() or {})
