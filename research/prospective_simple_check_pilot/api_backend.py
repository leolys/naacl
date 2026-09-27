"""Explicit opt-in chat-completions backend with bounded transport-only retries.

Gateway identity is a reported claim, not cryptographic proof of model weights.
This adapter is unqualified for a real gateway until authorized control calls pass.
"""
from __future__ import annotations

import base64
import json
import math
import os
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
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
    enforce_money_cap: bool = True
    money_limit_waiver_reference: str | None = None
    request_cost_ceiling_usd: str | None = None
    cost_ceiling_basis: str | None = None
    # Optional usage settlement, only with a verified gateway pricing upper bound.
    # Defaults keep the old fixed-reservation behavior unchanged.
    input_token_cost_upper_usd: str | None = None
    output_token_cost_upper_usd: str | None = None
    input_token_limit_for_reservation: int | None = None
    identity_policy: str = "require_match"
    identity_waiver_reference: str | None = None
    usage_priced_routes: list[str] = field(default_factory=list)
    # Old configurations retain their original no-retry behavior.
    max_retries: int = 0
    retry_base_seconds: float = 10.0
    retry_jitter_seconds: float = 3.0
    retry_max_wait_seconds: float = 60.0

    def missing(self, *, check_credential=True):
        missing = [name for name in (
            "model_id", "authorization_reference", "owner_confirmed_model_identity",
            "official_model_documentation", "allowed_response_models", "allowed_reported_routes",
            "max_output_tokens", "request_cost_ceiling_usd", "cost_ceiling_basis")
                   if not getattr(self, name)]
        if type(self.enforce_money_cap) is not bool:
            missing.append("boolean_enforce_money_cap")
        if self.enforce_money_cap and not self.money_cap_usd:
            missing.append("money_cap_usd")
        if self.enforce_money_cap is False and not self.money_limit_waiver_reference:
            missing.append("explicit_money_limit_waiver_reference")
        if not self.authorized:
            missing.append("authorization_for_exact_endpoint_model_and_this_panel")
        if not self.reasoning_setting_confirmed:
            missing.append("fixed_reasoning_and_sampling_configuration")
        if self.identity_policy not in {"require_match", "record_only"}:
            missing.append("valid_identity_policy")
        if self.identity_policy == "record_only" and not self.identity_waiver_reference:
            missing.append("explicit_identity_waiver_reference")
        if check_credential and not os.environ.get(self.credential_env, "").strip():
            missing.append(f"credential_environment:{self.credential_env}")
        return missing


class ApiStop(RuntimeError):
    """Stop the entire panel, not just this branch, on route/transport uncertainty."""


class _TransientFailure(Exception):
    """Internal transport classification; never a model-output quality judgment."""
    def __init__(self, reason, retry_after=None):
        self.reason, self.retry_after = reason, retry_after
        super().__init__(reason)


RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}
RETRY_CONFIG_FIELDS = {"max_retries", "retry_base_seconds", "retry_jitter_seconds", "retry_max_wait_seconds"}
PERMANENT_ERROR_CODES = {"insufficient_quota", "quota_exceeded", "billing_hard_limit_reached",
                         "invalid_api_key", "authentication_error", "permission_denied"}


def retry_after_seconds(value, now):
    """RFC 9110 delay-seconds or HTTP-date. Invalid values use local backoff."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"\d+", value):
        # Avoid numeric overflow on an untrusted response header.
        return float(value) if len(value) <= 12 else float("inf")
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, parsed.timestamp() - now)
    except (TypeError, ValueError, OverflowError):
        return None


def http_failure_metadata(response, token):
    """Small allowlisted diagnostics, not raw bodies/headers or authentication data."""
    headers = getattr(response, "headers", {})
    allowed = {"retry-after", "x-request-id", "request-id", "x-litellm-call-id"}
    kept = {k.lower(): redact(str(v), token)[:256] for k, v in headers.items() if k.lower() in allowed}
    try:
        body = response.json()
    except (ValueError, TypeError):
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    codes = {}
    if isinstance(error, dict):
        for key in ("type", "code"):
            value = error.get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
                codes[key] = redact(value, token)
    return dict(http_status=response.status_code, safe_response_headers=kept,
                error_identifiers=codes, response_body_saved=False)


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
        if type(config.enforce_money_cap) is not bool or (not config.enforce_money_cap and not config.money_limit_waiver_reference):
            raise ValueError("disabling monetary enforcement requires an explicit owner waiver")
        self.cap = Decimal(config.money_cap_usd or "0") if config.enforce_money_cap else None
        if (not self.ceiling.is_finite() or self.ceiling <= 0 or
                (self.cap is not None and (not self.cap.is_finite() or self.cap <= 0))):
            raise ValueError("positive finite authorized spending limits required")
        self.entries = []
        rates = (config.input_token_cost_upper_usd, config.output_token_cost_upper_usd,
                 config.input_token_limit_for_reservation)
        self.rates = None
        if any(value is not None for value in rates):
            if any(value is None for value in rates):
                raise ValueError("usage settlement needs both rates and an input upper bound")
            inp, out = Decimal(rates[0]), Decimal(rates[1])
            if not all(x.is_finite() and x > 0 for x in (inp, out)) or type(rates[2]) is not int or rates[2] <= 0:
                raise ValueError("positive finite verified token rates and limit required")
            if inp * rates[2] + out * config.max_output_tokens > self.ceiling:
                raise ValueError("request reservation does not cover the configured token-cost upper bound")
            self.rates = (inp, out)

    def accounted_upper(self):
        return sum((Decimal(e.get("usage_cost_upper_usd", e["reserved_usd"])) for e in self.entries), Decimal("0"))

    def settle_completed_usage(self, entry, usage):
        if self.rates is None:
            return
        inp, out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if type(inp) is not int or type(out) is not int or inp < 0 or out < 0:
            entry["usage_settlement"] = "unknown_usage_full_reservation_retained"
            return
        if inp > self.config.input_token_limit_for_reservation or out > self.config.max_output_tokens:
            raise ApiStop("returned usage exceeds the qualified token envelope")
        entry["usage_cost_upper_usd"] = str(self.rates[0] * inp + self.rates[1] * out)
        entry["usage_settlement"] = "reported_usage_times_verified_upper_rates_not_invoice"

    def check_available(self):
        if len(self.entries) >= self.config.max_calls or (self.cap is not None and self.accounted_upper() + self.ceiling > self.cap):
            raise BudgetExceeded("API call or conservative dollar reservation cap reached")

    def reserve(self, request_id):
        self.check_available()
        self.entries.append(dict(request_id=request_id, reserved_usd=str(self.ceiling),
                                 status="dispatch_pending", observed_billed_usd=None))
        self.persist()
        return self.entries[-1]

    def persist(self):
        write_json(self.path, dict(calls_reserved=len(self.entries),
                                  reserved_usd=str(self.ceiling * len(self.entries)),
                                  accounted_upper_usd=str(self.accounted_upper()),
                                  money_cap_usd=str(self.cap) if self.cap is not None else None,
                                  enforce_money_cap=self.config.enforce_money_cap,
                                  money_limit_waiver_reference=self.config.money_limit_waiver_reference,
                                  monetary_scope="historical accounting convention; not an invoice or verified actual spend",
                                  basis=self.config.cost_ceiling_basis,
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
    def __init__(self, config: ApiConfig, *, artifact_dir: Path, session=None, retry_charge=None,
                 sleep=time.sleep, jitter=random.uniform, wall_clock=time.time):
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
        if type(config.max_retries) is not int or not 0 <= config.max_retries <= 3:
            raise ValueError("max_retries must be an integer from 0 to 3")
        if config.max_retries and not callable(retry_charge):
            raise ValueError("retries require the shared model-call budget callback")
        for value in (config.retry_base_seconds, config.retry_jitter_seconds, config.retry_max_wait_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("retry delays must be nonnegative finite numbers")
        if not 0 < config.retry_max_wait_seconds <= 60:
            raise ValueError("retry wait must be bounded by 60 seconds")
        self.config, self.artifact_dir = config, artifact_dir
        self.retry_charge, self.sleep, self.jitter, self.wall_clock = retry_charge, sleep, jitter, wall_clock
        self.spend = ApiSpend(config, artifact_dir / "api_spend.json")
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.proxies = ({"http": config.proxy_url, "https": config.proxy_url}
                                if config.proxy_url else {})
        self.halted = False

    @property
    def metadata(self):
        return dict(kind="intranet_chat_completions", configuration=asdict(self.config),
                    identity_status=("requested_model_gateway_backend_identity_unverified" if self.config.identity_policy == "record_only"
                                     else "owner_confirmation_plus_gateway_report_not_weight_attestation"),
                    automatic_retries=self.config.max_retries, automatic_fallback=False,
                    retry_semantics="same serialized text/images/parameters; transport failures only; every attempt charged")

    def close(self):
        self.session.close()

    def complete(self, request, *, prior_transport_attempts=0):
        if type(prior_transport_attempts) is not int or not 0 <= prior_transport_attempts <= self.config.max_retries:
            raise ValueError("prior transport attempts must fit the same logical request retry allowance")
        if self.halted:
            raise ApiStop("API backend halted; no automatic continuation or fallback")
        token = os.environ.get(self.config.credential_env, "").strip()
        if not token:
            raise PermissionError("credential environment is empty")
        payload, images = wire_payload(self.config, request)
        # Construct once: retries cannot pick up changed screenshot files or add error feedback.
        encoded_payload = json.dumps(payload, ensure_ascii=False)
        start_index, started = len(self.spend.entries), time.monotonic()
        last = None
        try:
            for attempt in range(1, self.config.max_retries + 2 - prior_transport_attempts):
                self.spend.check_available()
                attempt_id = request.request_id if attempt == 1 else f"{request.request_id}__retry_{attempt - 1}"
                if attempt > 1:
                    # RecordedModel charged the first attempt; extra physical calls are not free.
                    self.retry_charge(phase=request.phase, request_id=attempt_id)
                entry = self.spend.reserve(attempt_id)
                last = entry
                entry.update(logical_request_id=request.request_id, attempt=attempt,
                             prior_transport_attempts=prior_transport_attempts,
                             logical_transport_attempt=attempt + prior_transport_attempts)
                root = self.artifact_dir / f"call_{len(self.spend.entries):04d}"
                write_json(root / "request.json", dict(request_id=attempt_id,
                    logical_request_id=request.request_id, attempt=attempt,
                    endpoint=self.config.base_url.rstrip("/") + self.config.endpoint,
                    payload=json.loads(encoded_payload), supplied_images=images))
                try:
                    reply = self._complete_once(json.loads(encoded_payload), images, token, entry, root)
                except _TransientFailure as exc:
                    if attempt + prior_transport_attempts > self.config.max_retries:
                        entry["retry_stop_reason"] = "retry_limit_exhausted"
                        raise ApiStop("transport retries exhausted") from None
                    self.spend.check_available()  # Do not wait when no further reservation can fit.
                    hint = retry_after_seconds(exc.retry_after, self.wall_clock())
                    if hint is not None and hint > self.config.retry_max_wait_seconds:
                        entry["retry_stop_reason"] = "retry_after_exceeds_bounded_wait"
                        raise ApiStop("server requested a longer wait; no early retry") from None
                    local_delay = min(self.config.retry_max_wait_seconds,
                        self.config.retry_base_seconds * (2 ** (attempt + prior_transport_attempts - 1))
                        + self.jitter(0, self.config.retry_jitter_seconds))
                    delay = max(local_delay, hint or 0.0)
                    entry.update(retry_scheduled=True, retry_wait_seconds=delay,
                                 retry_reason=exc.reason)
                    self.spend.persist()
                    print(f"[api retry] logical={request.request_id} next_attempt={attempt + 1} "
                          f"wait_seconds={delay:.3f} reason={exc.reason}", flush=True)
                    self.sleep(delay)
                    continue
                reply.metadata.update(transport_attempt_count=attempt,
                    transport_attempts=[dict(e) for e in self.spend.entries[start_index:]],
                    elapsed_seconds=time.monotonic() - started)
                return reply
        except Exception as exc:
            self.halted = True
            if isinstance(exc, BudgetExceeded) and last is not None:
                last["retry_stop_reason"] = "budget_exhausted_before_another_dispatch"
            write_json(self.artifact_dir / "transport_stop.json", dict(
                logical_request_id=request.request_id, error_type=type(exc).__name__,
                last_attempt_id=last["request_id"] if last else None,
                stop_reason=("budget_exhausted_before_another_dispatch" if isinstance(exc, BudgetExceeded)
                             else (last or {}).get("retry_stop_reason", "non_retryable_failure")),
                completed_reply_returned=False, automatic_resume=False,
                note="Request and browser timeline retained; no business action or fallback is executed here."))
            if isinstance(exc, BudgetExceeded):
                raise
            raise ApiStop("API stopped; inspect sanitized wire/ledger artifacts") from None
        finally:
            self.spend.persist()

    def _complete_once(self, payload, images, token, entry, root):
        """One HTTP attempt. Caller alone decides bounded retries; no browser writes."""
        start = time.monotonic()
        try:
            response = self.session.post(self.config.base_url.rstrip("/") + self.config.endpoint,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                json=payload, timeout=self.config.timeout_seconds, allow_redirects=False)
            if response.status_code != 200:
                diagnostics = http_failure_metadata(response, token)
                entry.update(status="http_failure", **diagnostics)
                write_json(root / "failure.json", diagnostics)
                permanent = any(v.lower() in PERMANENT_ERROR_CODES for v in diagnostics["error_identifiers"].values())
                if response.status_code in RETRYABLE_HTTP and not permanent:
                    raise _TransientFailure(f"http_{response.status_code}",
                        diagnostics["safe_response_headers"].get("retry-after"))
                raise ApiStop("non-retryable HTTP failure")
            data = redact(response.json(), token)
            write_json(root / "response.json", data)
            usage = data.get("usage") or {}
            returned = data.get("model")
            route = usage.get("model_name") if isinstance(usage, dict) else None
            entry.update(requested_model=self.config.model_id, response_model=returned,
                         gateway_reported_route=route, usage=usage)
            matches = returned in self.config.allowed_response_models and route in self.config.allowed_reported_routes
            entry.update(identity_policy=self.config.identity_policy, identity_matches=matches)
            if not matches and self.config.identity_policy == "require_match":
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
            if self.config.identity_policy == "require_match" or route in self.config.usage_priced_routes:
                self.spend.settle_completed_usage(entry, usage)
            else:
                entry["usage_settlement"] = "unpriced_route_full_reservation_retained_identity_not_blocked"
            entry["status"] = "completed"
            return ModelReply(content, dict(requested_model=self.config.model_id, response_model=returned,
                gateway_reported_route=route, usage=usage, finish_reason=finish, output_truncated=False,
                identity_policy=self.config.identity_policy, identity_matches=matches,
                supplied_images=images, provider_preprocessing="not_reported",
                wire_artifact=str(root), elapsed_seconds=time.monotonic() - start,
                reserved_usd=entry["reserved_usd"], usage_cost_upper_usd=entry.get("usage_cost_upper_usd"),
                observed_billed_usd=None))
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            entry.update(status="transport_or_response_failure", error_type=type(exc).__name__)
            if isinstance(exc, requests.exceptions.SSLError):
                raise ApiStop("TLS failure is not a retryable overload") from None
            raise _TransientFailure(type(exc).__name__) from None
        except Exception as exc:
            if entry["status"] in {"dispatch_pending", "response_received"}:
                entry["status"] = "transport_or_response_failure"
            entry["error_type"] = type(exc).__name__
            # Do not expose requests exceptions: they can contain tokens, URLs, and response bodies.
            raise
        finally:
            entry["elapsed_seconds"] = time.monotonic() - start
            self.spend.persist()
