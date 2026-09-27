"""Explicit opt-in chat-completions backend. No discovery, aliases, retries, or GPU work.

Gateway identity is a reported claim, not cryptographic proof of model weights.
This adapter is unqualified for a real gateway until authorized control calls pass.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image

from research.decision_evidence_audit.core import BudgetExceeded, write_json
from research.decision_evidence_audit.models import ModelReply, OnlineRequest


@dataclass
class ApiConfig:
    base_url: str = "https://aimemodeldev.myhexin.com/litellm"
    endpoint: str = "/v1/chat/completions"
    model_id: str | None = None
    credential_env: str = "MODEL_API_KEY"
    proxy_url: str | None = None
    authorized: bool = False
    authorization_reference: str | None = None
    owner_confirmed_model_identity: str | None = None
    official_model_documentation: str | None = None
    allowed_response_models: list[str] = field(default_factory=list)
    allowed_reported_routes: list[str] = field(default_factory=list)
    max_output_tokens: int | None = None
    output_limit_field: str = "max_completion_tokens"
    reasoning_effort: str | None = None
    reasoning_setting_confirmed: bool = False
    temperature: float | None = None
    image_detail: str = "high"
    timeout_seconds: float = 120.0
    max_calls: int = 400
    money_cap_usd: str | None = None
    request_cost_ceiling_usd: str | None = None
    cost_ceiling_basis: str | None = None

    def missing(self, *, check_credential=True):
        missing = [name for name in (
            "model_id", "authorization_reference", "owner_confirmed_model_identity",
            "official_model_documentation", "allowed_response_models", "allowed_reported_routes",
            "max_output_tokens", "money_cap_usd", "request_cost_ceiling_usd", "cost_ceiling_basis")
                   if not getattr(self, name)]
        if not self.authorized:
            missing.append("authorization_for_exact_endpoint_model_and_this_panel")
        if not self.reasoning_setting_confirmed:
            missing.append("fixed_reasoning_and_sampling_configuration")
        if check_credential and not os.environ.get(self.credential_env, "").strip():
            missing.append(f"credential_environment:{self.credential_env}")
        return missing


class ApiStop(RuntimeError):
    """Stop the entire panel, not just this branch, on route/transport uncertainty."""


class ApiSpend:
    """Serial conservative reservation, including unknown-cost failures.

    A ceiling needs an authorized provider/gateway billing basis. This is NOT a
    guessed price or a substitute for the provider's hard spending limit.
    Never release an unknown reservation or call it an observed invoice charge.
    """
    def __init__(self, config: ApiConfig, path: Path):
        if path.exists():
            raise FileExistsError("API ledger already exists; implicit resume is unsupported")
        self.config, self.path = config, path
        self.ceiling = Decimal(config.request_cost_ceiling_usd or "0")
        self.cap = Decimal(config.money_cap_usd or "0")
        if not self.ceiling.is_finite() or not self.cap.is_finite() or self.ceiling <= 0 or self.cap <= 0:
            raise ValueError("positive finite authorized spending limits required")
        self.entries = []

    def reserve(self, request_id):
        if len(self.entries) >= self.config.max_calls or self.ceiling * (len(self.entries) + 1) > self.cap:
            raise BudgetExceeded("API call or conservative dollar reservation cap reached")
        self.entries.append(dict(request_id=request_id, reserved_usd=str(self.ceiling),
                                 status="dispatch_pending", observed_billed_usd=None))
        self.persist()
        return self.entries[-1]

    def persist(self):
        write_json(self.path, dict(calls_reserved=len(self.entries),
                                  reserved_usd=str(self.ceiling * len(self.entries)),
                                  money_cap_usd=str(self.cap), basis=self.config.cost_ceiling_basis,
                                  observed_billed_total_usd=None, entries=self.entries))


def redact(value, token):
    if isinstance(value, str):
        if token:
            value = value.replace(token, "[REDACTED]")
        return re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED_KEY]", value)
    if isinstance(value, list):
        return [redact(x, token) for x in value]
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.casefold() in {"authorization", "api_key", "token", "key"}
                    else redact(v, token)) for k, v in value.items()}
    return value


def wire_payload(config: ApiConfig, request: OnlineRequest):
    """Only recorder-approved text/images, never filenames, manifests or evaluator data."""
    request.log_payload()  # Reuse the established online allowlist check.
    if len(request.image_paths) != len(request.image_artifacts) or not request.image_paths:
        raise ValueError("ordered image inputs are required")
    parts = [dict(type="text", text=request.user_prompt)]
    images = []
    for index, path in enumerate(request.image_paths):
        with Image.open(path) as im:
            size, fmt = list(im.size), im.format
        mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(fmt)
        if not mime:
            raise ValueError("unsupported image format; no silent conversion")
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        parts.append(dict(type="image_url", image_url=dict(url=f"data:{mime};base64,{data}", detail=config.image_detail)))
        images.append(dict(index=index, size=size, format=fmt, detail=config.image_detail,
                           artifact=request.image_artifacts[index], local_preprocessing="none"))
    if config.output_limit_field not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError("unsupported output limit field; qualify another adapter explicitly")
    payload = dict(model=config.model_id, stream=False, messages=[
        dict(role="system", content=request.system_prompt), dict(role="user", content=parts)])
    payload[config.output_limit_field] = config.max_output_tokens
    if config.reasoning_effort is not None:
        payload["reasoning_effort"] = config.reasoning_effort
    if config.temperature is not None:
        payload["temperature"] = config.temperature
    return payload, images


class IntranetApiBackend:
    def __init__(self, config: ApiConfig, *, artifact_dir: Path, session=None):
        missing = config.missing()
        if missing:
            raise PermissionError("API not authorized/configured: " + ", ".join(missing))
        url = urlsplit(config.base_url)
        if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
            raise ValueError("explicit HTTPS gateway without embedded credentials required")
        if config.endpoint != "/v1/chat/completions":
            raise ValueError("only chat-completions is implemented; no endpoint fallback")
        if config.max_calls <= 0 or config.max_output_tokens <= 0 or config.timeout_seconds <= 0:
            raise ValueError("positive explicit call, output, and timeout limits required")
        if config.image_detail not in {"high", "low", "auto"}:
            raise ValueError("unknown image detail")
        self.config, self.artifact_dir = config, artifact_dir
        self.spend = ApiSpend(config, artifact_dir / "api_spend.json")
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.proxies = ({"http": config.proxy_url, "https": config.proxy_url}
                                if config.proxy_url else {})
        self.halted = False

    @property
    def metadata(self):
        return dict(kind="intranet_chat_completions", configuration=asdict(self.config),
                    identity_status="owner_confirmation_plus_gateway_report_not_weight_attestation",
                    automatic_retries=0, automatic_fallback=False)

    def close(self):
        self.session.close()

    def complete(self, request):
        if self.halted:
            raise ApiStop("API backend halted; no automatic continuation or fallback")
        token = os.environ.get(self.config.credential_env, "").strip()
        if not token:
            raise PermissionError("credential environment is empty")
        payload, images = wire_payload(self.config, request)
        entry = self.spend.reserve(request.request_id)
        ordinal = len(self.spend.entries)
        root = self.artifact_dir / f"call_{ordinal:04d}"
        write_json(root / "request.json", dict(request_id=request.request_id,
            endpoint=self.config.base_url.rstrip("/") + self.config.endpoint,
            payload=payload, supplied_images=images))  # Deliberately excludes headers.
        start = time.monotonic()
        try:
            response = self.session.post(self.config.base_url.rstrip("/") + self.config.endpoint,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                json=payload, timeout=self.config.timeout_seconds, allow_redirects=False)
            if response.status_code != 200:
                entry.update(status="http_failure", http_status=response.status_code)
                raise ApiStop(f"API HTTP {response.status_code}; no response body or credentials in exception")
            data = redact(response.json(), token)
            write_json(root / "response.json", data)
            usage = data.get("usage") or {}
            returned = data.get("model")
            route = usage.get("model_name") if isinstance(usage, dict) else None
            entry.update(requested_model=self.config.model_id, response_model=returned,
                         gateway_reported_route=route, usage=usage)
            if returned not in self.config.allowed_response_models or route not in self.config.allowed_reported_routes:
                entry["status"] = "identity_unverified_or_mismatch"
                raise ApiStop("Gateway response model/route is missing or outside the authorized identities")
            choices = data.get("choices") or []
            if data.get("error") or len(choices) != 1:
                raise ApiStop("API response does not contain exactly one completion")
            choice = choices[0]
            finish = choice.get("finish_reason")
            content = (choice.get("message") or {}).get("content")
            entry.update(status="response_received", finish_reason=finish,
                         output_truncated=finish in {"length", "max_tokens"})
            if not isinstance(content, str) or not content.strip() or finish != "stop":
                raise ApiStop("Completion is empty, truncated, filtered, or has an unqualified finish reason")
            entry["status"] = "completed"
            return ModelReply(content, dict(requested_model=self.config.model_id, response_model=returned,
                gateway_reported_route=route, usage=usage, finish_reason=finish, output_truncated=False,
                supplied_images=images, provider_preprocessing="not_reported",
                wire_artifact=str(root), elapsed_seconds=time.monotonic() - start,
                reserved_usd=entry["reserved_usd"], observed_billed_usd=None))
        except Exception as exc:
            self.halted = True
            if entry["status"] in {"dispatch_pending", "response_received"}:
                entry["status"] = "transport_or_response_failure"
            entry["error_type"] = type(exc).__name__
            # Do not expose requests exceptions: they can contain tokens, URLs, and response bodies.
            raise ApiStop("API stopped; inspect sanitized wire/ledger artifacts") from None
        finally:
            entry["elapsed_seconds"] = time.monotonic() - start
            self.spend.persist()
