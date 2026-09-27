"""
LLM client helpers for the adversarial pipeline.

Supported backends:
- `anthropic` (default): Claude Messages API
- `openai`: official OpenAI Responses API
- `openrouter`: OpenRouter chat-completions API
- `gateway`: internal chat-completions-style HTTP endpoint
- `hexin_openai`: Hexin OpenAI-compatible chat-completions gateway
- `qwen3_vl_http`: local Qwen3-VL HTTP inference server
- `llama32_vision_http`: local Llama-3.2 Vision HTTP inference server
- `kimik2_http`: Kimi K2.6 OpenAI-compatible chat-completions endpoint
- `aime_litellm`: AIME LiteLLM chat-completions/responses/messages endpoint
"""

from __future__ import annotations

import base64
import http.client
import json
import logging
import mimetypes
import os
import random
import ssl
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import requests
from openai import OpenAI
from urllib3.exceptions import InsecureRequestWarning

try:
    from anthropic import Anthropic
except Exception:  # pragma: no cover - only matters when anthropic isn't installed
    Anthropic = None


logger = logging.getLogger(__name__)


DEFAULT_BACKEND = os.environ.get("LLM_BACKEND", "anthropic").lower()
DEFAULT_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-7-sonnet-20250219")
DEFAULT_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4")
DEFAULT_OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL",
    "anthropic/claude-sonnet-4.6",
)
DEFAULT_GATEWAY_MODEL = os.environ.get("LLM_MODEL", "gpt-5")
DEFAULT_GATEWAY_URL = (
    os.environ.get("LLM_GATEWAY_URL")
    or "https://rtahz.10jqka.com.cn/llm-api-forward/forward/v1/completions"
)
DEFAULT_OPENROUTER_URL = os.environ.get(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)
DEFAULT_HEXIN_SETTINGS_PATH = Path(
    os.environ.get("HEXIN_SETTINGS_PATH", "/root/.claude/settings_hexin.json")
)
DEFAULT_HEXIN_MODEL = os.environ.get("HEXIN_MODEL", "gpt-5.4")
DEFAULT_HEXIN_URL = os.environ.get(
    "HEXIN_BASE_URL",
    "https://rtahz.10jqka.com.cn/llm-api-forward/forward/v1/chat/completions",
)
DEFAULT_QWEN3_VL_SERVER_URL = os.environ.get(
    "QWEN3_VL_SERVER_URL",
    "http://127.0.0.1:8045",
)
DEFAULT_QWEN3_VL_MODEL = os.environ.get("QWEN3_VL_MODEL", "qwen3_vl")
DEFAULT_QWEN3_VL_MODEL_PATH = os.environ.get("QWEN3_VL_MODEL_PATH", "")
DEFAULT_QWEN3_VL_MODEL_SIZE = os.environ.get("QWEN3_VL_MODEL_SIZE", "")
DEFAULT_LLAMA32_VISION_SERVER_URL = os.environ.get(
    "LLAMA32_VISION_SERVER_URL",
    "http://127.0.0.1:8047",
)
DEFAULT_LLAMA32_VISION_MODEL = os.environ.get("LLAMA32_VISION_MODEL", "llama3_2_vision")
DEFAULT_LLAMA32_VISION_MODEL_PATH = os.environ.get("LLAMA32_VISION_MODEL_PATH", "")
DEFAULT_LLAMA32_VISION_MODEL_SIZE = os.environ.get("LLAMA32_VISION_MODEL_SIZE", "")
DEFAULT_KIMIK2_BASE_URL = os.environ.get(
    "KIMIK2_BASE_URL",
    "http://10.240.24.60:8000/v1/chat/completions",
)
DEFAULT_KIMIK2_MODEL = os.environ.get("KIMIK2_MODEL", "kimik26")
DEFAULT_AIME_LITELLM_BASE_URL = os.environ.get(
    "AIME_LITELLM_BASE_URL",
    "https://aimemodeldev.myhexin.com/litellm/v1",
).rstrip("/")
DEFAULT_AIME_LITELLM_MODEL = os.environ.get(
    "AIME_LITELLM_MODEL",
    "gemini-3-pro-image-preview",
)
DEFAULT_AIME_LITELLM_HOST_HEADER = os.environ.get("AIME_LITELLM_HOST_HEADER", "")
DEFAULT_AIME_LITELLM_VERIFY_SSL = (
    os.environ.get("AIME_LITELLM_VERIFY_SSL", "true").lower() == "true"
)
DEFAULT_AIME_LITELLM_MAX_RETRIES = int(os.environ.get("AIME_LITELLM_MAX_RETRIES", "5"))
DEFAULT_AIME_LITELLM_REQUEST_DELAY_SEC = float(
    os.environ.get("AIME_LITELLM_REQUEST_DELAY_SEC", "1")
)
DEFAULT_AIME_LITELLM_HTTP_READ_TIMEOUT_SEC = float(
    os.environ.get("AIME_LITELLM_HTTP_READ_TIMEOUT_SEC", "900")
)
DEFAULT_AIME_LITELLM_EXTRA_BODY_JSON = os.environ.get("AIME_LITELLM_EXTRA_BODY_JSON", "")
DEFAULT_AIME_LITELLM_OMIT_TEMPERATURE = (
    os.environ.get("AIME_LITELLM_OMIT_TEMPERATURE", "false").lower() == "true"
)
DEFAULT_AIME_LITELLM_OMIT_TOP_P = (
    os.environ.get("AIME_LITELLM_OMIT_TOP_P", "false").lower() == "true"
)
DEFAULT_AIME_LITELLM_REASONING_CONTENT_FALLBACK = (
    os.environ.get("AIME_LITELLM_REASONING_CONTENT_FALLBACK", "false").lower() == "true"
)
DEFAULT_AIME_LITELLM_API_STYLE = os.environ.get(
    "AIME_LITELLM_API_STYLE", "chat_completions"
).lower()
DEFAULT_AIME_LITELLM_PROXY = os.environ.get("AIME_LITELLM_PROXY", "").strip()
DEFAULT_KIMIK2_MAX_RETRIES = int(os.environ.get("KIMIK2_MAX_RETRIES", "5"))
DEFAULT_KIMIK2_REQUEST_DELAY_SEC = float(os.environ.get("KIMIK2_REQUEST_DELAY_SEC", "2"))
DEFAULT_KIMIK2_HTTP_READ_TIMEOUT_SEC = float(
    os.environ.get("KIMIK2_HTTP_READ_TIMEOUT_SEC", "900")
)
KIMIK2_TRANSIENT_STATUS_CODES = {429, 502, 503, 504}
DEFAULT_HTTP_CONNECT_TIMEOUT_SEC = float(os.environ.get("LLM_HTTP_CONNECT_TIMEOUT_SEC", "20"))
DEFAULT_HTTP_READ_TIMEOUT_SEC = float(os.environ.get("LLM_HTTP_READ_TIMEOUT_SEC", "120"))
DEFAULT_OPENAI_TIMEOUT_SEC = float(os.environ.get("OPENAI_TIMEOUT_SEC", "180"))


@dataclass
class LLMClient:
    backend: str
    model: str
    anthropic_client: Any | None = None
    openai_client: OpenAI | None = None
    openrouter_url: str | None = None
    openrouter_api_key: str | None = None
    gateway_url: str | None = None
    gateway_api_key: str | None = None
    hexin_url: str | None = None
    hexin_settings_path: Path | None = None
    hexin_headers: dict[str, str] | None = None
    qwen3_vl_server_url: str | None = None
    qwen3_vl_model_path: str | None = None
    qwen3_vl_model_size: str | None = None
    llama32_vision_server_url: str | None = None
    llama32_vision_model_path: str | None = None
    llama32_vision_model_size: str | None = None
    kimik2_base_url: str | None = None
    kimik2_api_key: str | None = None
    aime_litellm_base_url: str | None = None
    aime_litellm_api_key: str | None = None
    aime_litellm_host_header: str | None = None
    aime_litellm_verify_ssl: bool = True
    aime_litellm_proxy: str | None = None


class KimiK2TransientError(RuntimeError):
    """Kimi K2.6 request failed in a way that is worth retrying."""


class AimeLiteLLMTransientError(RuntimeError):
    """AIME LiteLLM request failed in a way that is worth retrying."""


@dataclass
class _SimpleHTTPResponse:
    status_code: int
    text: str
    headers: dict[str, str]

    def json(self) -> dict[str, Any]:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)  # type: ignore[arg-type]


class _SNIHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that connects to one host but uses another SNI name."""

    def __init__(
        self,
        host: str,
        *,
        port: int,
        server_hostname: str,
        context: ssl.SSLContext,
        timeout: float,
    ) -> None:
        super().__init__(host, port=port, timeout=timeout, context=context)
        self._sni_server_hostname = server_hostname

    def connect(self) -> None:
        sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._sni_server_hostname)


LAST_RESPONSE_METADATA: dict[str, Any] | None = None


def _set_last_response_metadata(metadata: dict[str, Any] | None) -> None:
    global LAST_RESPONSE_METADATA
    LAST_RESPONSE_METADATA = metadata


def get_last_response_metadata() -> dict[str, Any] | None:
    """Return metadata for the most recent LLM response in this process."""
    return LAST_RESPONSE_METADATA


def _http_timeout_tuple() -> tuple[float, float]:
    return (DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, DEFAULT_HTTP_READ_TIMEOUT_SEC)


def _safe_raise_for_status(response: requests.Response, provider_name: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body_preview = response.text[:800]
        raise RuntimeError(
            f"{provider_name} HTTP error {response.status_code}: {body_preview}"
        ) from exc


def _post_json_with_timeout(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict,
    provider_name: str,
    timeout: tuple[float, float] | None = None,
) -> dict:
    started = time.time()
    effective_timeout = timeout or _http_timeout_tuple()
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=effective_timeout,
        )
    except requests.Timeout as exc:
        raise RuntimeError(
            f"{provider_name} request timed out after connect/read timeouts "
            f"{effective_timeout}: {exc}"
        ) from exc
    except requests.ConnectionError as exc:
        raise RuntimeError(f"{provider_name} connection error: {exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"{provider_name} request failed: {exc}") from exc

    elapsed = time.time() - started
    logger.info(
        "%s response received: status=%s elapsed=%.2fs model=%s",
        provider_name,
        response.status_code,
        elapsed,
        payload.get("model"),
    )

    _safe_raise_for_status(response, provider_name)
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(
            f"{provider_name} returned non-JSON response with status {response.status_code}: "
            f"{response.text[:500]}"
        ) from exc


def _load_hexin_settings(settings_path: Path) -> dict[str, Any]:
    return json.loads(settings_path.read_text(encoding="utf-8"))


def _parse_header_lines(raw_headers: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in raw_headers.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def _build_hexin_headers(settings_path: Path) -> dict[str, str]:
    settings = _load_hexin_settings(settings_path)
    env = settings.get("env", {})
    custom_headers = _parse_header_lines(env.get("ANTHROPIC_CUSTOM_HEADERS", ""))
    return {
        "content-type": "application/json",
        "accept": "application/json",
        "Authorization": "Bearer dummy",
        **custom_headers,
    }


def make_judge_client() -> LLMClient:
    """
    Create an independent LLM client for the LLM Judge role.

    Uses JUDGE_LLM_BACKEND / JUDGE_LLM_MODEL env vars so the judge can run on
    a different model than the Forward/Reverse agents.  Falls back to the
    primary backend if no judge-specific env vars are set.

    Separation is important: a judge that shares the same model *and* the same
    inference context as the Forward Agent can self-consistently validate its
    own failures.  Using a different model or at least a fresh client instance
    breaks that coupling.
    """
    judge_backend = os.environ.get("JUDGE_LLM_BACKEND", "").lower() or DEFAULT_BACKEND
    judge_model = os.environ.get("JUDGE_LLM_MODEL", "")

    logger.info(
        "LLM Judge client init: backend=%s model=%s",
        judge_backend,
        judge_model or "(default for backend)",
    )

    if judge_backend == "anthropic":
        if Anthropic is None:
            raise RuntimeError("anthropic package is not installed.")
        api_key = os.environ.get("JUDGE_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        base_url = os.environ.get("JUDGE_ANTHROPIC_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return LLMClient(
            backend="anthropic",
            model=judge_model or DEFAULT_ANTHROPIC_MODEL,
            anthropic_client=Anthropic(**kwargs),
        )

    if judge_backend == "openai":
        api_key = os.environ.get("JUDGE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        base_url = (
            os.environ.get("JUDGE_OPENAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
        )
        kwargs = {"api_key": api_key, "timeout": DEFAULT_OPENAI_TIMEOUT_SEC}
        if base_url:
            kwargs["base_url"] = base_url
        return LLMClient(
            backend="openai",
            model=judge_model or DEFAULT_OPENAI_MODEL,
            openai_client=OpenAI(**kwargs),
        )

    if judge_backend == "hexin_openai":
        settings_path = Path(
            os.environ.get("JUDGE_HEXIN_SETTINGS_PATH", str(DEFAULT_HEXIN_SETTINGS_PATH))
        )
        if not settings_path.exists():
            raise RuntimeError(f"Judge Hexin settings file does not exist: {settings_path}")
        return LLMClient(
            backend="hexin_openai",
            model=judge_model or DEFAULT_HEXIN_MODEL,
            hexin_url=os.environ.get("JUDGE_HEXIN_BASE_URL", DEFAULT_HEXIN_URL),
            hexin_settings_path=settings_path,
            hexin_headers=_build_hexin_headers(settings_path),
        )

    # For other backends fall back to a fresh instance of the primary client
    return make_client()


def make_client() -> LLMClient:
    """Create a backend-aware client wrapper from environment variables."""
    backend = DEFAULT_BACKEND
    logger.info(
        "LLM client init: backend=%s http_proxy=%s https_proxy=%s HTTP_PROXY=%s HTTPS_PROXY=%s",
        backend,
        os.environ.get("http_proxy"),
        os.environ.get("https_proxy"),
        os.environ.get("HTTP_PROXY"),
        os.environ.get("HTTPS_PROXY"),
    )

    if backend == "anthropic":
        if Anthropic is None:
            raise RuntimeError(
                "anthropic package is not installed in the current Python environment."
            )
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return LLMClient(
            backend="anthropic",
            model=DEFAULT_ANTHROPIC_MODEL,
            anthropic_client=Anthropic(**kwargs),
        )

    if backend == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")
        kwargs = {"api_key": api_key, "timeout": DEFAULT_OPENAI_TIMEOUT_SEC}
        if base_url:
            kwargs["base_url"] = base_url
        return LLMClient(
            backend="openai",
            model=DEFAULT_OPENAI_MODEL,
            openai_client=OpenAI(**kwargs),
        )

    if backend == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")
        return LLMClient(
            backend="openrouter",
            model=DEFAULT_OPENROUTER_MODEL,
            openrouter_url=DEFAULT_OPENROUTER_URL,
            openrouter_api_key=api_key,
        )

    if backend == "gateway":
        return LLMClient(
            backend="gateway",
            model=DEFAULT_GATEWAY_MODEL,
            gateway_url=DEFAULT_GATEWAY_URL,
            gateway_api_key=os.environ.get("LLM_GATEWAY_API_KEY")
            or os.environ.get("OPENAI_API_KEY"),
        )

    if backend == "hexin_openai":
        if not DEFAULT_HEXIN_SETTINGS_PATH.exists():
            raise RuntimeError(
                f"HEXIN settings file does not exist: {DEFAULT_HEXIN_SETTINGS_PATH}"
            )
        return LLMClient(
            backend="hexin_openai",
            model=DEFAULT_HEXIN_MODEL,
            hexin_url=DEFAULT_HEXIN_URL,
            hexin_settings_path=DEFAULT_HEXIN_SETTINGS_PATH,
            hexin_headers=_build_hexin_headers(DEFAULT_HEXIN_SETTINGS_PATH),
        )

    if backend == "qwen3_vl_http":
        return LLMClient(
            backend="qwen3_vl_http",
            model=DEFAULT_QWEN3_VL_MODEL,
            qwen3_vl_server_url=DEFAULT_QWEN3_VL_SERVER_URL,
            qwen3_vl_model_path=DEFAULT_QWEN3_VL_MODEL_PATH,
            qwen3_vl_model_size=DEFAULT_QWEN3_VL_MODEL_SIZE,
        )

    if backend == "llama32_vision_http":
        return LLMClient(
            backend="llama32_vision_http",
            model=DEFAULT_LLAMA32_VISION_MODEL,
            llama32_vision_server_url=DEFAULT_LLAMA32_VISION_SERVER_URL,
            llama32_vision_model_path=DEFAULT_LLAMA32_VISION_MODEL_PATH,
            llama32_vision_model_size=DEFAULT_LLAMA32_VISION_MODEL_SIZE,
        )

    if backend == "kimik2_http":
        return LLMClient(
            backend="kimik2_http",
            model=DEFAULT_KIMIK2_MODEL,
            kimik2_base_url=DEFAULT_KIMIK2_BASE_URL,
            kimik2_api_key=os.environ.get("KIMIK2_API_KEY"),
        )

    if backend == "aime_litellm":
        api_key = os.environ.get("AIME_LITELLM_API_KEY")
        if not api_key:
            raise RuntimeError("AIME_LITELLM_API_KEY is not set.")
        return LLMClient(
            backend="aime_litellm",
            model=DEFAULT_AIME_LITELLM_MODEL,
            aime_litellm_base_url=DEFAULT_AIME_LITELLM_BASE_URL,
            aime_litellm_api_key=api_key,
            aime_litellm_host_header=DEFAULT_AIME_LITELLM_HOST_HEADER or None,
            aime_litellm_verify_ssl=DEFAULT_AIME_LITELLM_VERIFY_SSL,
            aime_litellm_proxy=DEFAULT_AIME_LITELLM_PROXY or None,
        )

    raise RuntimeError(f"Unsupported LLM_BACKEND: {backend}")


def _encode_image_bytes(image_path: str | Path) -> tuple[str, str]:
    path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "image/png"
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")
    return mime_type, b64


def _encode_image_data_url(image_path: str | Path) -> str:
    mime_type, b64 = _encode_image_bytes(image_path)
    return f"data:{mime_type};base64,{b64}"


def _extract_anthropic_text(response: Any) -> str:
    texts: list[str] = []
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            texts.append(getattr(block, "text", ""))
    if texts:
        return "\n".join(t for t in texts if t)
    raise RuntimeError(f"Could not extract text from Anthropic response: {response}")


def _extract_gateway_text(response_json: dict) -> str:
    if response_json.get("status_code") not in (None, "0", 0, 200, "200"):
        raise RuntimeError(
            "Gateway returned an application-level error: "
            f"status_code={response_json.get('status_code')}, "
            f"status_msg={response_json.get('status_msg')}, "
            f"trace_id={response_json.get('trace_id')}, "
            f"data={response_json.get('data')}"
        )

    if isinstance(response_json.get("data"), str) and not response_json.get("choices"):
        return response_json["data"]

    if isinstance(response_json.get("choices"), list) and response_json["choices"]:
        message = response_json["choices"][0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            if texts:
                return "\n".join(t for t in texts if t)

    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]

    raise RuntimeError(f"Could not extract text from gateway response: {response_json}")


def _extract_openrouter_text(response_json: dict) -> str:
    if isinstance(response_json.get("error"), dict):
        raise RuntimeError(f"OpenRouter returned an error: {response_json['error']}")

    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                    texts.append(item.get("text", ""))
            if texts:
                return "\n".join(t for t in texts if t)

    raise RuntimeError(f"Could not extract text from OpenRouter response: {response_json}")


def _extract_kimik2_text(response_json: dict) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise KimiK2TransientError(f"Kimi K2.6 response has no choices: {response_json}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    reasoning_content = message.get("reasoning_content")
    finish_reason = choices[0].get("finish_reason")
    logger.info(
        "Kimi K2.6 response parsed: content_present=%s reasoning_present=%s finish_reason=%s",
        bool(content),
        bool(reasoning_content),
        finish_reason,
    )
    if isinstance(content, str) and content.strip():
        return content
    if reasoning_content:
        raise KimiK2TransientError(
            "Kimi K2.6 returned reasoning_content but empty final content "
            f"(finish_reason={finish_reason})."
        )
    raise KimiK2TransientError(f"Kimi K2.6 returned empty content: {response_json}")


def _extract_aime_litellm_text(response_json: dict) -> str:
    if isinstance(response_json.get("error"), dict):
        raise RuntimeError(f"AIME LiteLLM returned an error: {response_json['error']}")
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AimeLiteLLMTransientError(f"AIME LiteLLM response has no choices: {response_json}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                texts.append(item.get("text", ""))
        if texts:
            return "\n".join(t for t in texts if t)
    reasoning_content = message.get("reasoning_content")
    if (
        DEFAULT_AIME_LITELLM_REASONING_CONTENT_FALLBACK
        and isinstance(reasoning_content, str)
        and reasoning_content.strip()
    ):
        logger.warning("AIME LiteLLM returned empty content; using reasoning_content fallback.")
        return reasoning_content
    raise AimeLiteLLMTransientError(f"AIME LiteLLM returned empty content: {response_json}")


def _extract_aime_litellm_responses_text(response_json: dict) -> str:
    if isinstance(response_json.get("error"), dict):
        raise RuntimeError(f"AIME LiteLLM returned an error: {response_json['error']}")
    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    texts: list[str] = []
    output = response_json.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "output_text" and isinstance(item.get("text"), str):
                texts.append(item["text"])
            content = item.get("content")
            if isinstance(content, list):
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    if content_item.get("type") in {"output_text", "text"} and isinstance(
                        content_item.get("text"), str
                    ):
                        texts.append(content_item["text"])
    joined = "\n".join(text for text in texts if text.strip())
    if joined.strip():
        return joined
    raise AimeLiteLLMTransientError(
        f"AIME LiteLLM responses endpoint returned empty content: {response_json}"
    )


def _extract_aime_litellm_messages_text(response_json: dict) -> str:
    if isinstance(response_json.get("error"), dict):
        raise RuntimeError(f"AIME LiteLLM returned an error: {response_json['error']}")
    texts: list[str] = []
    content = response_json.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text)
    if texts:
        return "\n".join(texts)
    raise AimeLiteLLMTransientError(
        f"AIME LiteLLM messages endpoint returned empty content: {response_json}"
    )


def _gateway_headers(client: LLMClient) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if client.gateway_api_key:
        headers["Authorization"] = f"Bearer {client.gateway_api_key}"
    return headers


def _openrouter_headers(client: LLMClient) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {client.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    if os.environ.get("OPENROUTER_HTTP_REFERER"):
        headers["HTTP-Referer"] = os.environ["OPENROUTER_HTTP_REFERER"]
    if os.environ.get("OPENROUTER_X_TITLE"):
        headers["X-Title"] = os.environ["OPENROUTER_X_TITLE"]
    return headers


def _hexin_headers(client: LLMClient) -> dict[str, str]:
    if not client.hexin_headers:
        raise RuntimeError("Hexin client is missing precomputed headers.")
    headers = dict(client.hexin_headers)
    headers["X-Trace-Id"] = os.environ.get("HEXIN_TRACE_ID", f"adv-pipeline-{uuid.uuid4().hex[:12]}")
    return headers


def _kimik2_headers(client: LLMClient) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if client.kimik2_api_key:
        headers["Authorization"] = f"Bearer {client.kimik2_api_key}"
    return headers


def _aime_litellm_headers(client: LLMClient) -> dict[str, str]:
    if not client.aime_litellm_api_key:
        raise RuntimeError("AIME LiteLLM client is missing API key.")
    return {
        "Authorization": f"Bearer {client.aime_litellm_api_key}",
        "Content-Type": "application/json",
    } | ({"Host": client.aime_litellm_host_header} if client.aime_litellm_host_header else {})


def _aime_litellm_proxies(client: LLMClient) -> dict[str, str] | None:
    if not client.aime_litellm_proxy:
        return None
    return {"http": client.aime_litellm_proxy, "https": client.aime_litellm_proxy}


def _aime_litellm_should_use_sni_tunnel(client: LLMClient, url: str) -> bool:
    if not client.aime_litellm_host_header:
        return False
    parsed = urlparse(url)
    return parsed.hostname not in {None, client.aime_litellm_host_header}


def _aime_litellm_post_sni_tunnel(
    *,
    client: LLMClient,
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: float,
) -> _SimpleHTTPResponse:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError(f"AIME LiteLLM SNI tunnel only supports https URLs: {url}")
    if not parsed.hostname:
        raise RuntimeError(f"AIME LiteLLM URL is missing hostname: {url}")
    port = parsed.port or 443
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    context = (
        ssl.create_default_context()
        if client.aime_litellm_verify_ssl
        else ssl._create_unverified_context()
    )
    conn = _SNIHTTPSConnection(
        parsed.hostname,
        port=port,
        server_hostname=str(client.aime_litellm_host_header),
        context=context,
        timeout=timeout,
    )
    try:
        conn.request(
            "POST",
            path,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        response = conn.getresponse()
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return _SimpleHTTPResponse(
            status_code=response.status,
            text=raw.decode(charset, errors="replace"),
            headers={key: value for key, value in response.headers.items()},
        )
    finally:
        conn.close()


def _kimik2_retry_sleep(attempt: int) -> None:
    base_delays = [3.0, 8.0, 20.0, 45.0, 90.0]
    delay = base_delays[min(attempt, len(base_delays) - 1)]
    delay += random.uniform(0.0, min(3.0, delay * 0.2))
    logger.warning("Kimi K2.6 transient failure; sleeping %.2fs before retry", delay)
    time.sleep(delay)


def _aime_litellm_retry_sleep(attempt: int) -> None:
    base_delays = [2.0, 6.0, 15.0, 35.0, 75.0]
    delay = base_delays[min(attempt, len(base_delays) - 1)]
    delay += random.uniform(0.0, min(2.0, delay * 0.2))
    logger.warning("AIME LiteLLM transient failure; sleeping %.2fs before retry", delay)
    time.sleep(delay)


def _aime_litellm_payload_with_extra_body(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge experimental AIME LiteLLM request body fields from the environment."""
    if DEFAULT_AIME_LITELLM_OMIT_TEMPERATURE and "temperature" in payload:
        payload = {key: value for key, value in payload.items() if key != "temperature"}
    if DEFAULT_AIME_LITELLM_OMIT_TOP_P and "top_p" in payload:
        payload = {key: value for key, value in payload.items() if key != "top_p"}
    raw = DEFAULT_AIME_LITELLM_EXTRA_BODY_JSON.strip()
    if not raw:
        return payload
    try:
        extra = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "AIME_LITELLM_EXTRA_BODY_JSON must be valid JSON object text: "
            f"{exc}"
        ) from exc
    if not isinstance(extra, dict):
        raise RuntimeError("AIME_LITELLM_EXTRA_BODY_JSON must decode to a JSON object.")
    return {**payload, **extra}


def _aime_litellm_content_for_responses(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if not isinstance(content, list):
        return [{"type": "input_text", "text": str(content)}]
    converted: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            converted.append({"type": "input_text", "text": item})
            continue
        if not isinstance(item, dict):
            converted.append({"type": "input_text", "text": str(item)})
            continue
        item_type = item.get("type")
        if item_type in {"text", "input_text"}:
            converted.append({"type": "input_text", "text": str(item.get("text", ""))})
        elif item_type in {"image_url", "input_image"}:
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            converted.append({"type": "input_image", "image_url": str(image_url or "")})
        else:
            converted.append({"type": "input_text", "text": json.dumps(item, ensure_ascii=False)})
    return converted


def _aime_litellm_payload_for_responses(payload: dict[str, Any]) -> dict[str, Any]:
    response_payload: dict[str, Any] = {
        "model": payload.get("model"),
        "input": [],
    }
    if payload.get("max_output_tokens") is not None:
        response_payload["max_output_tokens"] = payload["max_output_tokens"]
    elif payload.get("max_tokens") is not None:
        response_payload["max_output_tokens"] = payload["max_tokens"]

    for key in ("temperature", "top_p", "seed"):
        if key in payload:
            response_payload[key] = payload[key]

    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            response_payload["input"].append(
                {
                    "role": str(message.get("role", "user")),
                    "content": _aime_litellm_content_for_responses(message.get("content", "")),
                }
            )
    elif payload.get("input") is not None:
        response_payload["input"] = payload["input"]
    else:
        response_payload["input"] = str(payload.get("prompt", ""))

    return response_payload


def _aime_litellm_content_for_messages(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return [{"type": "text", "text": str(content)}]
    converted: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            converted.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict):
            converted.append({"type": "text", "text": str(item)})
            continue
        item_type = item.get("type")
        if item_type in {"text", "input_text"}:
            converted.append({"type": "text", "text": str(item.get("text", ""))})
            continue
        if item_type not in {"image_url", "input_image"}:
            converted.append({"type": "text", "text": json.dumps(item, ensure_ascii=False)})
            continue
        image_url = item.get("image_url")
        if isinstance(image_url, dict):
            image_url = image_url.get("url")
        image_url = str(image_url or "")
        if image_url.startswith("data:") and ";base64," in image_url:
            header, data = image_url.split(",", 1)
            media_type = header[5:].split(";", 1)[0] or "image/png"
            converted.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )
        else:
            converted.append(
                {"type": "image", "source": {"type": "url", "url": image_url}}
            )
    return converted


def _aime_litellm_payload_for_messages(payload: dict[str, Any]) -> dict[str, Any]:
    messages_payload: dict[str, Any] = {
        "model": payload.get("model"),
        "max_tokens": payload.get("max_output_tokens", payload.get("max_tokens", 4096)),
        "messages": [],
    }
    system_blocks: list[dict[str, Any]] = []
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "user"))
            content = _aime_litellm_content_for_messages(message.get("content", ""))
            if role == "system":
                system_blocks.extend(item for item in content if item.get("type") == "text")
            else:
                messages_payload["messages"].append({"role": role, "content": content})
    if system_blocks:
        messages_payload["system"] = system_blocks
    return messages_payload


def _gateway_post(client: LLMClient, payload: dict, timeout: int = 180) -> str:
    if not client.gateway_url:
        raise RuntimeError("Gateway client is missing gateway_url.")

    logger.info(
        "Gateway request: url=%s model=%s http_proxy=%s https_proxy=%s",
        client.gateway_url,
        payload.get("model"),
        os.environ.get("http_proxy"),
        os.environ.get("https_proxy"),
    )

    body = _post_json_with_timeout(
        url=client.gateway_url,
        headers=_gateway_headers(client),
        payload=payload,
        provider_name="Gateway",
        timeout=(DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, float(timeout)),
    )
    return _extract_gateway_text(body)


def _openrouter_post(client: LLMClient, payload: dict, timeout: int = 180) -> str:
    if not client.openrouter_url:
        raise RuntimeError("OpenRouter client is missing openrouter_url.")

    logger.info(
        "OpenRouter request: url=%s model=%s http_proxy=%s https_proxy=%s",
        client.openrouter_url,
        payload.get("model"),
        os.environ.get("http_proxy"),
        os.environ.get("https_proxy"),
    )

    body = _post_json_with_timeout(
        url=client.openrouter_url,
        headers=_openrouter_headers(client),
        payload=payload,
        provider_name="OpenRouter",
        timeout=(DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, float(timeout)),
    )
    return _extract_openrouter_text(body)


def _hexin_post(client: LLMClient, payload: dict, timeout: int = 180) -> str:
    if not client.hexin_url:
        raise RuntimeError("Hexin client is missing hexin_url.")

    logger.info(
        "Hexin request: url=%s model=%s http_proxy=%s https_proxy=%s",
        client.hexin_url,
        payload.get("model"),
        os.environ.get("http_proxy"),
        os.environ.get("https_proxy"),
    )

    body = _post_json_with_timeout(
        url=client.hexin_url,
        headers=_hexin_headers(client),
        payload=payload,
        provider_name="Hexin",
        timeout=(DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, float(timeout)),
    )
    return _extract_gateway_text(body)


def _kimik2_post(client: LLMClient, payload: dict, timeout: float | None = None) -> str:
    if not client.kimik2_base_url:
        raise RuntimeError("Kimi K2.6 client is missing kimik2_base_url.")
    max_retries = max(0, DEFAULT_KIMIK2_MAX_RETRIES)
    request_delay = max(0.0, DEFAULT_KIMIK2_REQUEST_DELAY_SEC)
    read_timeout = float(timeout or DEFAULT_KIMIK2_HTTP_READ_TIMEOUT_SEC)
    if request_delay:
        time.sleep(request_delay)

    session = requests.Session()
    session.trust_env = False
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        started = time.time()
        try:
            response = session.post(
                client.kimik2_base_url,
                headers=_kimik2_headers(client),
                json=payload,
                timeout=(DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, read_timeout),
            )
            elapsed = time.time() - started
            logger.info(
                "Kimi K2.6 response received: status=%s elapsed=%.2fs model=%s attempt=%s/%s",
                response.status_code,
                elapsed,
                payload.get("model"),
                attempt + 1,
                max_retries + 1,
            )
            if response.status_code in KIMIK2_TRANSIENT_STATUS_CODES:
                last_error = KimiK2TransientError(
                    f"Kimi K2.6 transient HTTP {response.status_code}: {response.text[:800]}"
                )
                if attempt < max_retries:
                    _kimik2_retry_sleep(attempt)
                    continue
                raise last_error
            _safe_raise_for_status(response, "Kimi K2.6")
            if not response.text.strip():
                raise KimiK2TransientError("Kimi K2.6 returned an empty response body.")
            try:
                body = response.json()
            except Exception as exc:
                raise KimiK2TransientError(
                    f"Kimi K2.6 returned non-JSON response: {response.text[:500]}"
                ) from exc
            _set_last_response_metadata(
                {
                    "provider": "kimik2_http",
                    "model": payload.get("model"),
                    "usage": body.get("usage"),
                    "id": body.get("id"),
                    "created": body.get("created"),
                    "finish_reason": (
                        body.get("choices", [{}])[0].get("finish_reason")
                        if isinstance(body.get("choices"), list)
                        and body.get("choices")
                        else None
                    ),
                }
            )
            return _extract_kimik2_text(body)
        except (requests.Timeout, requests.ConnectionError, KimiK2TransientError) as exc:
            last_error = exc
            logger.warning(
                "Kimi K2.6 request attempt %s/%s failed: %r",
                attempt + 1,
                max_retries + 1,
                exc,
            )
            if attempt < max_retries:
                _kimik2_retry_sleep(attempt)
                continue
            raise RuntimeError(
                f"Kimi K2.6 request failed after {max_retries + 1} attempts: {last_error}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Kimi K2.6 request failed: {exc}") from exc
    raise RuntimeError(f"Kimi K2.6 request failed after retries: {last_error}")


def _aime_litellm_post(client: LLMClient, payload: dict, timeout: float | None = None) -> str:
    if not client.aime_litellm_base_url:
        raise RuntimeError("AIME LiteLLM client is missing base_url.")
    payload = _aime_litellm_payload_with_extra_body(payload)
    api_style = DEFAULT_AIME_LITELLM_API_STYLE
    if api_style not in {"chat_completions", "responses", "messages"}:
        raise RuntimeError(
            "AIME_LITELLM_API_STYLE must be 'chat_completions', 'responses', or 'messages'."
        )
    if api_style == "responses":
        payload = _aime_litellm_payload_for_responses(payload)
        url = f"{client.aime_litellm_base_url.rstrip('/')}/responses"
    elif api_style == "messages":
        payload = _aime_litellm_payload_for_messages(payload)
        url = f"{client.aime_litellm_base_url.rstrip('/')}/messages"
    else:
        url = f"{client.aime_litellm_base_url.rstrip('/')}/chat/completions"
    max_retries = max(0, DEFAULT_AIME_LITELLM_MAX_RETRIES)
    request_delay = max(0.0, DEFAULT_AIME_LITELLM_REQUEST_DELAY_SEC)
    read_timeout = float(timeout or DEFAULT_AIME_LITELLM_HTTP_READ_TIMEOUT_SEC)
    if not client.aime_litellm_verify_ssl:
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    if request_delay:
        time.sleep(request_delay)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        started = time.time()
        try:
            headers = _aime_litellm_headers(client)
            if _aime_litellm_should_use_sni_tunnel(client, url):
                response = _aime_litellm_post_sni_tunnel(
                    client=client,
                    url=url,
                    headers=headers,
                    payload=payload,
                    timeout=read_timeout,
                )
            else:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=(DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, read_timeout),
                    verify=client.aime_litellm_verify_ssl,
                    proxies=_aime_litellm_proxies(client),
                )
            elapsed = time.time() - started
            logger.info(
                "AIME LiteLLM response received: status=%s elapsed=%.2fs model=%s attempt=%s/%s",
                response.status_code,
                elapsed,
                payload.get("model"),
                attempt + 1,
                max_retries + 1,
            )
            if response.status_code in KIMIK2_TRANSIENT_STATUS_CODES:
                last_error = AimeLiteLLMTransientError(
                    f"AIME LiteLLM transient HTTP {response.status_code}: {response.text[:800]}"
                )
                if attempt < max_retries:
                    _aime_litellm_retry_sleep(attempt)
                    continue
                raise last_error
            _safe_raise_for_status(response, "AIME LiteLLM")
            if not response.text.strip():
                raise AimeLiteLLMTransientError("AIME LiteLLM returned an empty response body.")
            body = response.json()
            _set_last_response_metadata(
                {
                    "provider": "aime_litellm",
                    "model": payload.get("model"),
                    "api_style": api_style,
                    "usage": body.get("usage"),
                    "id": body.get("id"),
                    "created": body.get("created"),
                    "finish_reason": body.get("stop_reason") or (
                        body.get("choices", [{}])[0].get("finish_reason")
                        if isinstance(body.get("choices"), list) and body.get("choices")
                        else None
                    ),
                    "trace_id": response.headers.get("x-trace-id") or response.headers.get("X-Trace-Id"),
                }
            )
            if api_style == "responses":
                return _extract_aime_litellm_responses_text(body)
            if api_style == "messages":
                return _extract_aime_litellm_messages_text(body)
            return _extract_aime_litellm_text(body)
        except (requests.Timeout, requests.ConnectionError, AimeLiteLLMTransientError) as exc:
            last_error = exc
            logger.warning(
                "AIME LiteLLM request attempt %s/%s failed: %r",
                attempt + 1,
                max_retries + 1,
                exc,
            )
            if attempt < max_retries:
                _aime_litellm_retry_sleep(attempt)
                continue
            raise RuntimeError(
                f"AIME LiteLLM request failed after {max_retries + 1} attempts: {last_error}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"AIME LiteLLM request failed: {exc}") from exc
    raise RuntimeError(f"AIME LiteLLM request failed after retries: {last_error}")


def _qwen3_vl_post(client: LLMClient, payload: dict, timeout: int = 300) -> str:
    if not client.qwen3_vl_server_url:
        raise RuntimeError("Qwen3-VL HTTP client is missing qwen3_vl_server_url.")
    url = f"{client.qwen3_vl_server_url.rstrip('/')}/complete"
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=(DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, float(timeout)),
        )
    except requests.Timeout as exc:
        raise RuntimeError(f"Qwen3-VL HTTP request timed out: {exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Qwen3-VL HTTP request failed: {exc}") from exc
    _safe_raise_for_status(response, "Qwen3-VL HTTP")
    body = response.json()
    if body.get("ok") is False:
        raise RuntimeError(f"Qwen3-VL HTTP returned an error: {body.get('error')}")
    prompt_tokens = int(body.get("input_token_count") or 0)
    completion_tokens = int(body.get("output_token_count") or 0)
    _set_last_response_metadata(
        {
            "provider": "qwen3_vl_http",
            "model": client.model,
            "model_path": body.get("model_path"),
            "model_size": body.get("model_size"),
            "generation_config": body.get("generation_config"),
            "elapsed_seconds": body.get("elapsed_seconds"),
            "vision_input": {
                "image_count": body.get("input_image_count"),
                "original_image_sizes": body.get("original_image_sizes"),
                "max_pixels_per_image": body.get("max_pixels_per_image"),
                "server_protocol_version": body.get("server_protocol_version"),
            },
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    )
    output_text = body.get("output_text")
    if not isinstance(output_text, str):
        raise RuntimeError(f"Could not extract text from Qwen3-VL HTTP response: {body}")
    return output_text


def _llama32_vision_post(client: LLMClient, payload: dict, timeout: int = 300) -> str:
    if not client.llama32_vision_server_url:
        raise RuntimeError("Llama-3.2 Vision HTTP client is missing llama32_vision_server_url.")
    url = f"{client.llama32_vision_server_url.rstrip('/')}/complete"
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=(DEFAULT_HTTP_CONNECT_TIMEOUT_SEC, float(timeout)),
        )
    except requests.Timeout as exc:
        raise RuntimeError(f"Llama-3.2 Vision HTTP request timed out: {exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Llama-3.2 Vision HTTP request failed: {exc}") from exc
    _safe_raise_for_status(response, "Llama-3.2 Vision HTTP")
    body = response.json()
    if body.get("ok") is False:
        raise RuntimeError(f"Llama-3.2 Vision HTTP returned an error: {body.get('error')}")
    output_text = body.get("output_text")
    if not isinstance(output_text, str):
        raise RuntimeError(f"Could not extract text from Llama-3.2 Vision HTTP response: {body}")
    return output_text


def complete_text(
    client: LLMClient,
    system_prompt: str,
    user_text: str,
    *,
    model: str | None = None,
    max_output_tokens: int = 4096,
) -> str:
    """Send a text-only prompt and return the model output text."""
    _set_last_response_metadata(None)
    chosen_model = model or client.model

    if client.backend == "anthropic":
        if not client.anthropic_client:
            raise RuntimeError("Anthropic backend selected but no Anthropic client is available.")
        response = client.anthropic_client.messages.create(
            model=chosen_model,
            system=system_prompt,
            max_tokens=max_output_tokens,
            messages=[{"role": "user", "content": user_text}],
        )
        return _extract_anthropic_text(response)

    if client.backend == "openai":
        if not client.openai_client:
            raise RuntimeError("OpenAI backend selected but no OpenAI client is available.")
        response = client.openai_client.responses.create(
            model=chosen_model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                },
            ],
            max_output_tokens=max_output_tokens,
        )
        return response.output_text

    if client.backend == "openrouter":
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "reasoning": {"enabled": os.environ.get("OPENROUTER_ENABLE_REASONING", "true").lower() == "true"},
        }
        if max_output_tokens:
            payload["max_tokens"] = max_output_tokens
        return _openrouter_post(client, payload)

    if client.backend == "hexin_openai":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        }
        if chosen_model.startswith("gpt-5"):
            payload["max_completion_tokens"] = max_output_tokens
        else:
            payload["max_tokens"] = max_output_tokens
        return _hexin_post(client, payload)

    if client.backend == "kimik2_http":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "max_tokens": max_output_tokens,
            "n": 1,
            "chat_template_kwargs": {
                "thinking": os.environ.get("KIMIK2_ENABLE_THINKING", "true").lower() == "true"
            },
        }
        return _kimik2_post(client, payload)

    if client.backend == "aime_litellm":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "max_tokens": max_output_tokens,
        }
        return _aime_litellm_post(client, payload)

    payload = {
        "model": chosen_model,
        "stream": False,
        "max_tokens": max_output_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    }
    return _gateway_post(client, payload)


def complete_vision(
    client: LLMClient,
    system_prompt: str,
    user_text: str,
    image_path: str | Path | Sequence[str | Path],
    *,
    model: str | None = None,
    max_output_tokens: int = 2048,
    temperature: float | None = None,
    top_p: float | None = None,
    seed: int | None = None,
) -> str:
    """Send one or more local images and return the model output text.

    Native multi-image input is currently supported only by the local
    Qwen3-VL service. Other providers keep their existing one-image contract.
    """
    _set_last_response_metadata(None)
    chosen_model = model or client.model
    if isinstance(image_path, (str, Path)):
        image_paths = [Path(image_path)]
    else:
        image_paths = [Path(path) for path in image_path]
    if not image_paths:
        raise ValueError("at least one image is required")
    if client.backend != "qwen3_vl_http" and len(image_paths) != 1:
        raise ValueError(
            f"backend {client.backend!r} does not support native multi-image input"
        )
    primary_image_path = image_paths[0]
    decoding_kwargs = {}
    if temperature is not None:
        decoding_kwargs["temperature"] = temperature
    if top_p is not None:
        decoding_kwargs["top_p"] = top_p

    if client.backend == "anthropic":
        if not client.anthropic_client:
            raise RuntimeError("Anthropic backend selected but no Anthropic client is available.")
        mime_type, b64 = _encode_image_bytes(primary_image_path)
        response = client.anthropic_client.messages.create(
            model=chosen_model,
            system=system_prompt,
            max_tokens=max_output_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": b64,
                            },
                        },
                    ],
                }
            ],
            **decoding_kwargs,
        )
        return _extract_anthropic_text(response)

    image_data_url = _encode_image_data_url(primary_image_path)

    if client.backend == "openai":
        if not client.openai_client:
            raise RuntimeError("OpenAI backend selected but no OpenAI client is available.")
        response = client.openai_client.responses.create(
            model=chosen_model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_text},
                        {"type": "input_image", "image_url": image_data_url},
                    ],
                },
            ],
            max_output_tokens=max_output_tokens,
            **decoding_kwargs,
        )
        return response.output_text

    if client.backend == "openrouter":
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
            "reasoning": {"enabled": os.environ.get("OPENROUTER_ENABLE_REASONING", "true").lower() == "true"},
        }
        if max_output_tokens:
            payload["max_tokens"] = max_output_tokens
        payload.update(decoding_kwargs)
        if seed is not None:
            payload["seed"] = seed
        return _openrouter_post(client, payload)

    if client.backend == "hexin_openai":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
        }
        if chosen_model.startswith("gpt-5"):
            payload["max_completion_tokens"] = max_output_tokens
        else:
            payload["max_tokens"] = max_output_tokens
        payload.update(decoding_kwargs)
        if seed is not None:
            payload["seed"] = seed
        return _hexin_post(client, payload)

    if client.backend == "kimik2_http":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
            "max_tokens": max_output_tokens,
            "n": 1,
            "chat_template_kwargs": {
                "thinking": os.environ.get("KIMIK2_ENABLE_THINKING", "true").lower() == "true"
            },
        }
        payload.update(decoding_kwargs)
        if seed is not None:
            payload["seed"] = seed
        return _kimik2_post(client, payload)

    if client.backend == "aime_litellm":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
            "max_tokens": max_output_tokens,
        }
        payload.update(decoding_kwargs)
        if seed is not None:
            payload["seed"] = seed
        return _aime_litellm_post(client, payload)

    if client.backend == "qwen3_vl_http":
        generation_config: dict[str, Any] = {
            "do_sample": os.environ.get("QWEN3_VL_DO_SAMPLE", "false").lower() == "true",
        }
        if temperature is not None:
            generation_config["temperature"] = temperature
        if top_p is not None:
            generation_config["top_p"] = top_p
        payload = {
            "model": chosen_model,
            "model_path": client.qwen3_vl_model_path,
            "model_size": client.qwen3_vl_model_size,
            "system_prompt": system_prompt,
            "user_text": user_text,
            "image_paths": [str(path.resolve()) for path in image_paths],
            "max_output_tokens": max_output_tokens,
            "generation_config": generation_config,
        }
        if seed is not None:
            payload["seed"] = seed
        return _qwen3_vl_post(
            client,
            payload,
            timeout=int(os.environ.get("QWEN3_VL_HTTP_READ_TIMEOUT_SEC", "600")),
        )

    if client.backend == "llama32_vision_http":
        generation_config = {
            "do_sample": os.environ.get("LLAMA32_VISION_DO_SAMPLE", "false").lower() == "true",
        }
        if temperature is not None:
            generation_config["temperature"] = temperature
        if top_p is not None:
            generation_config["top_p"] = top_p
        payload = {
            "model": chosen_model,
            "model_path": client.llama32_vision_model_path,
            "model_size": client.llama32_vision_model_size,
            "system_prompt": system_prompt,
            "user_text": user_text,
            "image_path": str(Path(image_path).resolve()),
            "max_output_tokens": max_output_tokens,
            "generation_config": generation_config,
        }
        if seed is not None:
            payload["seed"] = seed
        return _llama32_vision_post(
            client,
            payload,
            timeout=int(os.environ.get("LLAMA32_VISION_HTTP_READ_TIMEOUT_SEC", "900")),
        )

    payload = {
        "model": chosen_model,
        "stream": False,
        "max_tokens": max_output_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
    }
    payload.update(decoding_kwargs)
    if seed is not None:
        payload["seed"] = seed
    return _gateway_post(client, payload)


def complete_multivision(
    client: LLMClient,
    system_prompt: str,
    user_text: str,
    image_paths: list[str | Path],
    *,
    model: str | None = None,
    max_output_tokens: int = 2048,
) -> str:
    """Send a prompt with multiple local images and return the model output text."""
    _set_last_response_metadata(None)
    chosen_model = model or client.model
    image_urls = [_encode_image_data_url(p) for p in image_paths]

    if client.backend == "anthropic":
        if not client.anthropic_client:
            raise RuntimeError("Anthropic backend selected but no Anthropic client is available.")
        content = [{"type": "text", "text": user_text}]
        for path in image_paths:
            mime_type, b64 = _encode_image_bytes(path)
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64,
                    },
                }
            )
        response = client.anthropic_client.messages.create(
            model=chosen_model,
            system=system_prompt,
            max_tokens=max_output_tokens,
            messages=[{"role": "user", "content": content}],
        )
        return _extract_anthropic_text(response)

    if client.backend == "openai":
        if not client.openai_client:
            raise RuntimeError("OpenAI backend selected but no OpenAI client is available.")
        user_content = [{"type": "input_text", "text": user_text}]
        user_content.extend({"type": "input_image", "image_url": url} for url in image_urls)
        response = client.openai_client.responses.create(
            model=chosen_model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": user_content},
            ],
            max_output_tokens=max_output_tokens,
        )
        return response.output_text

    if client.backend == "openrouter":
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}]
                    + [{"type": "image_url", "image_url": {"url": url}} for url in image_urls],
                },
            ],
            "reasoning": {"enabled": os.environ.get("OPENROUTER_ENABLE_REASONING", "true").lower() == "true"},
        }
        if max_output_tokens:
            payload["max_tokens"] = max_output_tokens
        return _openrouter_post(client, payload)

    if client.backend == "hexin_openai":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}]
                    + [{"type": "image_url", "image_url": {"url": url}} for url in image_urls],
                },
            ],
        }
        if chosen_model.startswith("gpt-5"):
            payload["max_completion_tokens"] = max_output_tokens
        else:
            payload["max_tokens"] = max_output_tokens
        return _hexin_post(client, payload)

    if client.backend == "kimik2_http":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}]
                    + [{"type": "image_url", "image_url": {"url": url}} for url in image_urls],
                },
            ],
            "max_tokens": max_output_tokens,
            "n": 1,
            "chat_template_kwargs": {
                "thinking": os.environ.get("KIMIK2_ENABLE_THINKING", "true").lower() == "true"
            },
        }
        return _kimik2_post(client, payload)

    if client.backend == "aime_litellm":
        payload = {
            "model": chosen_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}]
                    + [{"type": "image_url", "image_url": {"url": url}} for url in image_urls],
                },
            ],
            "max_tokens": max_output_tokens,
        }
        return _aime_litellm_post(client, payload)

    payload = {
        "model": chosen_model,
        "stream": False,
        "max_tokens": max_output_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}]
                + [{"type": "image_url", "image_url": {"url": url}} for url in image_urls],
            },
        ],
    }
    return _gateway_post(client, payload)
