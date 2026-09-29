"""Pilot-only fail-closed validation for AIME deployment identity."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web_agent_benchmark.evaluation.reflection_history import (
    internal_metadata_terms_in,
)


def _append_identity_event(event: dict[str, Any]) -> None:
    raw_path = os.environ.get("WEB_AGENT_MODEL_IDENTITY_LOG", "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def install_aime_identity_guard() -> None:
    """Install pilot-only AIME identity, request-count, and payload guards."""
    if os.environ.get("AIME_LITELLM_STRICT_MODEL_IDENTITY", "false").lower() != "true":
        return

    from adversarial_pipeline import llm_client

    if getattr(llm_client, "_reflection_identity_guard_installed", False):
        return

    original_post = llm_client.requests.post
    original_set_metadata = llm_client._set_last_response_metadata
    original_messages_payload = llm_client._aime_litellm_payload_for_messages
    identity: dict[str, Any] | None = None
    request_count = 0

    def guarded_post(*args: Any, **kwargs: Any) -> Any:
        nonlocal identity, request_count
        url = str(args[0] if args else kwargs.get("url") or "")
        payload = kwargs.get("json")
        is_aime = "/litellm/" in url and isinstance(payload, dict)
        request_count += int(is_aime)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_index": request_count if is_aime else None,
            "request_payload_sha256": (
                hashlib.sha256(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                if is_aime
                else None
            ),
            "hidden_prompt_terms_seen": (
                internal_metadata_terms_in(payload) if is_aime else []
            ),
            "requested_deployment": (
                str(payload.get("model") or "") if isinstance(payload, dict) else ""
            ),
            "api_path": (
                "/" + url.split("/litellm/", 1)[1].split("?", 1)[0]
                if "/litellm/" in url
                else ""
            ),
        }
        try:
            response = original_post(*args, **kwargs)
        except Exception as exc:
            if is_aime:
                _append_identity_event({
                    **event,
                    "event_type": "http_request",
                    "result": "exception",
                    "exception_type": type(exc).__name__,
                    "identity_validated": False,
                })
            raise
        if (
            not is_aime
            or not (200 <= int(response.status_code) < 300)
        ):
            if is_aime:
                _append_identity_event({
                    **event,
                    "event_type": "http_request",
                    "result": "http_error",
                    "status_code": int(response.status_code),
                    "identity_validated": False,
                })
            return response
        try:
            body = response.json()
        except Exception:
            _append_identity_event({
                **event,
                "event_type": "http_request",
                "result": "non_json_response",
                "status_code": int(response.status_code),
                "identity_validated": False,
            })
            return response
        requested = str(payload.get("model") or "")
        returned = str(body.get("model") or "")
        identity = {
            **event,
            "event_type": "http_request",
            "result": "success",
            "status_code": int(response.status_code),
            "requested_deployment": requested,
            "response_model": returned,
            "identity_validated": bool(requested and requested == returned),
            "response_id": body.get("id"),
        }
        _append_identity_event(identity)
        if not identity["identity_validated"]:
            raise llm_client.AimeLiteLLMTransientError(
                "AIME LiteLLM model identity mismatch: "
                f"requested={requested!r} response_model={returned!r}"
            )
        return response

    def guarded_set_metadata(metadata: dict[str, Any] | None) -> None:
        nonlocal identity
        if metadata is None:
            identity = None
            original_set_metadata(None)
            return
        merged = dict(metadata)
        if identity:
            merged.update(identity)
        original_set_metadata(merged)

    def guarded_messages_payload(payload: dict[str, Any]) -> dict[str, Any]:
        converted = original_messages_payload(payload)
        for key in ("top_p", "seed"):
            if key in payload:
                converted[key] = payload[key]
        return converted

    llm_client.requests.post = guarded_post
    llm_client._set_last_response_metadata = guarded_set_metadata
    llm_client._aime_litellm_payload_for_messages = guarded_messages_payload
    llm_client._reflection_identity_guard_installed = True
