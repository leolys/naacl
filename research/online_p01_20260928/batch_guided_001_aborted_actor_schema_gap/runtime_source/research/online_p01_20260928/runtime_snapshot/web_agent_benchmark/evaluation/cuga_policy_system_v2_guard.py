"""Visible-evidence pre-submit guard for the CUGA policy-system v2 experiment."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable


GUARD_SCHEMA_VERSION = "presubmit_guard_v2.0"
MAX_GUARD_CALLS = 2
MAX_VISIBLE_TEXT_CHARS = 20_000
APPROVAL_CONFIDENCE = 0.75
OPERATIONS = {"max", "min", "comparison", "trend", "ratio", "other"}
SOURCES = {"label", "axis", "legend", "mark", "annotation"}
READABILITY = {"clear", "ambiguous", "unreadable"}
VERDICTS = {"approve", "reinspect", "unresolved"}
FORBIDDEN_INPUT_KEYS = {
    "task",
    "task_json",
    "ground_truth",
    "misleader_type",
    "expected_action_id",
    "misleading_action_ids",
    "correct_action",
    "evaluation_hidden_from_agent",
    "evaluator",
    "outcome",
}

GUARD_SYSTEM_PROMPT = """You are PreSubmitGuard, a policy verifier for a chart-grounded browser workflow.

Use only the supplied screenshot, visible page text, visible form options, and the agent's proposed option. Never assume hidden labels, task metadata, benchmark annotations, or an answer key. Build a compact evidence ledger from visibly readable evidence. Do not invent values. A visually salient mark or annotation is not sufficient when readable axes, labels, legends, or marks conflict with it.

Return exactly one JSON object with these fields and no markdown:
{
  "criterion": {
    "metric": "",
    "operation": "max|min|comparison|trend|ratio|other",
    "unit": null,
    "time_scope": null
  },
  "candidates": [
    {
      "entity": "",
      "value_or_relation": null,
      "source": "label|axis|legend|mark|annotation",
      "axis_or_legend": null,
      "readability": "clear|ambiguous|unreadable"
    }
  ],
  "computed_entity": null,
  "recommended_option": null,
  "proposed_option_supported": false,
  "confidence": 0.0,
  "conflicts": [],
  "verdict": "approve|reinspect|unresolved",
  "reason": ""
}

Use an option label exactly as supplied when recommended_option is not null. Set approve only when visible evidence supports the proposed option. Use reinspect when one more visible-evidence inspection could resolve the decision, and unresolved when the available visible evidence remains insufficient or contradictory."""


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assert_type(value: Any, expected: type | tuple[type, ...], field: str) -> None:
    if not isinstance(value, expected):
        raise ValueError(f"{field} has invalid type {type(value).__name__}")


def _nullable_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    _assert_type(value, str, field)
    return value


def validate_guard_response(value: Any) -> dict[str, Any]:
    """Validate and normalize the frozen guard response contract."""

    _assert_type(value, dict, "response")
    required = {
        "criterion",
        "candidates",
        "computed_entity",
        "recommended_option",
        "proposed_option_supported",
        "confidence",
        "conflicts",
        "verdict",
        "reason",
    }
    missing = required - set(value)
    if missing:
        raise ValueError(f"guard response missing fields: {sorted(missing)}")

    criterion = value["criterion"]
    _assert_type(criterion, dict, "criterion")
    for field in ("metric", "operation", "unit", "time_scope"):
        if field not in criterion:
            raise ValueError(f"criterion missing field: {field}")
    _assert_type(criterion["metric"], str, "criterion.metric")
    _assert_type(criterion["operation"], str, "criterion.operation")
    if criterion["operation"] not in OPERATIONS:
        raise ValueError(f"unsupported operation: {criterion['operation']!r}")

    candidates = value["candidates"]
    _assert_type(candidates, list, "candidates")
    normalized_candidates: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        _assert_type(candidate, dict, f"candidates[{index}]")
        fields = {"entity", "value_or_relation", "source", "axis_or_legend", "readability"}
        missing_candidate = fields - set(candidate)
        if missing_candidate:
            raise ValueError(
                f"candidates[{index}] missing fields: {sorted(missing_candidate)}"
            )
        _assert_type(candidate["entity"], str, f"candidates[{index}].entity")
        _assert_type(candidate["source"], str, f"candidates[{index}].source")
        _assert_type(candidate["readability"], str, f"candidates[{index}].readability")
        if candidate["source"] not in SOURCES:
            raise ValueError(f"unsupported candidate source: {candidate['source']!r}")
        if candidate["readability"] not in READABILITY:
            raise ValueError(f"unsupported readability: {candidate['readability']!r}")
        value_or_relation = candidate["value_or_relation"]
        if value_or_relation is not None and not isinstance(value_or_relation, (str, int, float)):
            raise ValueError(f"candidates[{index}].value_or_relation must be scalar or null")
        normalized_candidates.append(
            {
                "entity": candidate["entity"],
                "value_or_relation": value_or_relation,
                "source": candidate["source"],
                "axis_or_legend": _nullable_string(
                    candidate["axis_or_legend"], f"candidates[{index}].axis_or_legend"
                ),
                "readability": candidate["readability"],
            }
        )

    if isinstance(value["confidence"], bool) or not isinstance(value["confidence"], (int, float)):
        raise ValueError("confidence must be numeric")
    confidence = float(value["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    _assert_type(value["proposed_option_supported"], bool, "proposed_option_supported")
    _assert_type(value["conflicts"], list, "conflicts")
    if not all(isinstance(item, str) for item in value["conflicts"]):
        raise ValueError("conflicts must contain strings")
    _assert_type(value["verdict"], str, "verdict")
    if value["verdict"] not in VERDICTS:
        raise ValueError(f"unsupported verdict: {value['verdict']!r}")
    _assert_type(value["reason"], str, "reason")

    return {
        "criterion": {
            "metric": criterion["metric"],
            "operation": criterion["operation"],
            "unit": _nullable_string(criterion["unit"], "criterion.unit"),
            "time_scope": _nullable_string(criterion["time_scope"], "criterion.time_scope"),
        },
        "candidates": normalized_candidates,
        "computed_entity": _nullable_string(value["computed_entity"], "computed_entity"),
        "recommended_option": _nullable_string(value["recommended_option"], "recommended_option"),
        "proposed_option_supported": value["proposed_option_supported"],
        "confidence": confidence,
        "conflicts": list(value["conflicts"]),
        "verdict": value["verdict"],
        "reason": value["reason"],
    }


def parse_guard_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("guard response does not contain a JSON object")
    return validate_guard_response(json.loads(text[start : end + 1]))


def assert_guard_input_has_no_hidden_fields(payload: dict[str, Any]) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            lowered = {str(key).lower() for key in value}
            overlap = lowered & FORBIDDEN_INPUT_KEYS
            if overlap:
                raise ValueError(f"hidden guard input fields detected: {sorted(overlap)}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)


def build_guard_messages(
    *,
    phase: str,
    visible_page_text: str,
    visible_options: list[str],
    proposed_option: str | None,
    screenshot_bytes: bytes,
) -> list[dict[str, Any]]:
    payload = {
        "phase": phase,
        "visible_page_text": visible_page_text[:MAX_VISIBLE_TEXT_CHARS],
        "visible_options": visible_options,
        "proposed_option": proposed_option,
    }
    assert_guard_input_has_no_hidden_fields(payload)
    image_url = "data:image/png;base64," + base64.b64encode(screenshot_bytes).decode("ascii")
    return [
        {"role": "system", "content": GUARD_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Visible-only audit input:\n" + json.dumps(payload, ensure_ascii=False),
                },
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]


def approval_reasons(
    response: dict[str, Any],
    visible_options: list[str],
    proposed_option: str | None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    recommended = response.get("recommended_option")
    if response.get("verdict") != "approve":
        reasons.append("verdict_not_approve")
    if float(response.get("confidence") or 0.0) < APPROVAL_CONFIDENCE:
        reasons.append("confidence_below_threshold")
    if not response.get("proposed_option_supported"):
        reasons.append("proposed_option_not_supported")
    if not isinstance(recommended, str) or recommended not in visible_options:
        reasons.append("recommendation_not_visible_exact_option")
    if proposed_option is None or recommended != proposed_option:
        reasons.append("recommendation_does_not_match_proposal")
    return not reasons, reasons


class VisibleEvidenceGuard:
    """Stateful, at-most-two-call guard for one browser task."""

    def __init__(
        self,
        *,
        run_dir: Path,
        repo_root: Path,
        model: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[Any]] | None = None,
        max_calls: int = MAX_GUARD_CALLS,
    ) -> None:
        self.run_dir = run_dir
        self.repo_root = repo_root
        self.model = model
        self.llm_call = llm_call
        self.max_calls = max_calls
        self.events: list[dict[str, Any]] = []
        self.logical_call_count = 0
        self.http_attempt_count = 0
        self.block_count = 0
        self.unresolved_count = 0
        self.has_guard_error = False
        self.final_state = "not_called"
        self.latest_response: dict[str, Any] | None = None
        self._client: Any = None

    async def _default_llm_call(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        from openai import AsyncOpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        if not api_key or not base_url:
            raise RuntimeError("OPENAI_API_KEY and OPENAI_BASE_URL are required for PreSubmitGuard")
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                timeout=float(os.environ.get("CUGA_GUARD_TIMEOUT_SEC", "180")),
                max_retries=0,
            )
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=1600,
        )
        content = response.choices[0].message.content or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        usage = response.usage.model_dump(mode="json") if response.usage is not None else None
        return {
            "content": content,
            "metadata": {
                "response_id": response.id,
                "response_model": response.model,
                "usage": usage,
            },
        }

    async def _invoke_llm(self, messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        caller = self.llm_call or self._default_llm_call
        result = caller(messages)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, str):
            return result, {}
        if not isinstance(result, dict) or not isinstance(result.get("content"), str):
            raise ValueError("guard LLM callable must return a string or {'content': str}")
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        return result["content"], metadata

    async def _visible_state(self, page: Any, proposed_option: str | None) -> dict[str, Any]:
        body = page.locator("body")
        visible_text = await body.inner_text(timeout=5000)
        option_rows = await page.locator("select#primary_action option").evaluate_all(
            """els => els.map(el => ({
                label: (el.textContent || '').trim(),
                value: el.value || '',
                disabled: !!el.disabled
            }))"""
        )
        actual_options = [
            {"label": str(row.get("label") or ""), "value": str(row.get("value") or "")}
            for row in option_rows
            if str(row.get("value") or "") and not bool(row.get("disabled"))
        ]
        visible_options = [row["label"] for row in actual_options if row["label"]]
        resolved_proposal = proposed_option
        if proposed_option is not None and proposed_option not in visible_options:
            value_matches = [row["label"] for row in actual_options if row["value"] == proposed_option]
            if len(value_matches) == 1:
                resolved_proposal = value_matches[0]
        screenshot_bytes = await page.screenshot(full_page=True, type="png")
        return {
            "visible_text": visible_text,
            "visible_options": visible_options,
            "actual_options": actual_options,
            "proposed_option": resolved_proposal,
            "raw_proposed_option": proposed_option,
            "screenshot_bytes": screenshot_bytes,
        }

    async def _new_guard_event(
        self,
        *,
        page: Any,
        phase: str,
        proposed_option: str | None,
    ) -> dict[str, Any]:
        self.logical_call_count += 1
        call_index = self.logical_call_count
        state = await self._visible_state(page, proposed_option)
        guard_dir = self.run_dir / "guard"
        guard_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = guard_dir / f"guard_call_{call_index:02d}_{phase}.png"
        visible_text_path = guard_dir / f"guard_call_{call_index:02d}_{phase}_visible.txt"
        input_path = guard_dir / f"guard_call_{call_index:02d}_{phase}_input.json"
        screenshot_path.write_bytes(state["screenshot_bytes"])
        visible_text_path.write_text(state["visible_text"], encoding="utf-8")
        input_record = {
            "schema_version": GUARD_SCHEMA_VERSION,
            "phase": phase,
            "visible_page_text_sha256": _sha256(state["visible_text"].encode("utf-8")),
            "visible_page_text_chars": len(state["visible_text"]),
            "visible_page_text_prompt_chars": min(
                len(state["visible_text"]), MAX_VISIBLE_TEXT_CHARS
            ),
            "visible_options": state["visible_options"],
            "proposed_option": state["proposed_option"],
            "raw_proposed_option": state["raw_proposed_option"],
            "screenshot_sha256": _sha256(state["screenshot_bytes"]),
        }
        assert_guard_input_has_no_hidden_fields(input_record)
        input_path.write_text(
            json.dumps(input_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        messages = build_guard_messages(
            phase=phase,
            visible_page_text=state["visible_text"],
            visible_options=state["visible_options"],
            proposed_option=state["proposed_option"],
            screenshot_bytes=state["screenshot_bytes"],
        )
        event: dict[str, Any] = {
            "schema_version": GUARD_SCHEMA_VERSION,
            "event_type": "guard_call",
            "call_index": call_index,
            "phase": phase,
            "model": self.model,
            "input": {
                **input_record,
                "screenshot_path": _display_path(screenshot_path, self.repo_root),
                "visible_page_text_path": _display_path(visible_text_path, self.repo_root),
                "input_manifest_path": _display_path(input_path, self.repo_root),
            },
            "http_attempts": [],
        }
        for attempt in range(1, 3):
            self.http_attempt_count += 1
            started = time.monotonic()
            attempt_record: dict[str, Any] = {"attempt": attempt}
            try:
                raw, metadata = await self._invoke_llm(messages)
                response = parse_guard_response(raw)
                attempt_record.update(
                    {
                        "status": "ok",
                        "latency_sec": round(time.monotonic() - started, 3),
                        "metadata": metadata,
                    }
                )
                event["http_attempts"].append(attempt_record)
                event["response"] = response
                event["raw_response_sha256"] = _sha256(raw.encode("utf-8"))
                event["latency_sec"] = round(
                    sum(float(item.get("latency_sec") or 0.0) for item in event["http_attempts"]),
                    3,
                )
                self.latest_response = response
                return event
            except Exception as exc:
                attempt_record.update(
                    {
                        "status": "error",
                        "latency_sec": round(time.monotonic() - started, 3),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                event["http_attempts"].append(attempt_record)
        event["guard_error"] = True
        event["latency_sec"] = round(
            sum(float(item.get("latency_sec") or 0.0) for item in event["http_attempts"]), 3
        )
        self.has_guard_error = True
        return event

    async def _check(
        self,
        *,
        page: Any,
        phase: str,
        proposed_option: str | None,
        prefer_reuse: bool = False,
    ) -> tuple[bool, str | None]:
        if not prefer_reuse and self.logical_call_count < self.max_calls:
            event = await self._new_guard_event(
                page=page,
                phase=phase,
                proposed_option=proposed_option,
            )
        else:
            state = await self._visible_state(page, proposed_option)
            event = {
                "schema_version": GUARD_SCHEMA_VERSION,
                "event_type": "guard_reuse",
                "phase": phase,
                "call_index": None,
                "reused_call_index": self.logical_call_count if self.latest_response else None,
                "input": {
                    "visible_options": state["visible_options"],
                    "proposed_option": state["proposed_option"],
                    "raw_proposed_option": state["raw_proposed_option"],
                },
                "response": self.latest_response,
                "guard_error": self.latest_response is None,
            }
            if self.latest_response is None:
                self.has_guard_error = True

        response = event.get("response")
        if not isinstance(response, dict):
            event["decision"] = "fail_open_guard_error"
            self.final_state = "guard_error"
            self.events.append(event)
            return True, None

        visible_options = list(event.get("input", {}).get("visible_options") or [])
        resolved_proposal = event.get("input", {}).get("proposed_option")
        approved, reasons = approval_reasons(response, visible_options, resolved_proposal)
        event["approval_reasons"] = reasons
        if approved:
            event["decision"] = "allow_approved"
            self.final_state = "approved"
            self.events.append(event)
            return True, None

        if self.block_count == 0:
            self.block_count += 1
            event["decision"] = "block_once"
            self.final_state = "blocked_once_pending_reinspection"
            self.events.append(event)
            feedback = {
                "policy": "Evidence-First Chart Decision Playbook",
                "guard": "PreSubmitGuard",
                "decision": "blocked_once",
                "instruction": (
                    "Re-observe the visible chart and form once, rebuild the evidence ledger, "
                    "and then propose the option again. Do not assume the guard is correct."
                ),
                "ledger": response,
            }
            return False, json.dumps(feedback, ensure_ascii=False)

        self.unresolved_count += 1
        event["decision"] = "allow_unresolved_after_one_block"
        self.final_state = "unresolved"
        self.events.append(event)
        return True, None

    async def before_primary_selection(
        self, page: Any, proposed_option: str | None
    ) -> tuple[bool, str | None]:
        return await self._check(
            page=page,
            phase="primary_select",
            proposed_option=proposed_option,
        )

    async def before_submit(
        self, page: Any, selected_option: str | None
    ) -> tuple[bool, str | None]:
        return await self._check(
            page=page,
            phase="pre_submit",
            proposed_option=selected_option,
            prefer_reuse=self.latest_response is not None,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": GUARD_SCHEMA_VERSION,
            "enabled": True,
            "guard_call_count": self.logical_call_count,
            "guard_http_attempt_count": self.http_attempt_count,
            "guard_block_count": self.block_count,
            "guard_unresolved_count": self.unresolved_count,
            "guard_final_state": self.final_state,
            "has_guard_error": self.has_guard_error,
            "total_latency_sec": round(
                sum(
                    float(event.get("latency_sec") or 0.0)
                    for event in self.events
                    if event.get("event_type") == "guard_call"
                ),
                3,
            ),
        }


class GuardedPlaywrightToolImplProvider:
    """Wrap CUGA's Playwright tool provider without changing CUGA source."""

    def __init__(self, guard: VisibleEvidenceGuard) -> None:
        self.guard = guard

    @staticmethod
    async def _locator_for_bid(page: Any, bid: str) -> Any:
        locator = page.locator(f'[bid="{bid}"]').first
        if await locator.count() == 0:
            return None
        return locator

    @staticmethod
    async def _is_primary_select(page: Any, bid: str) -> bool:
        locator = await GuardedPlaywrightToolImplProvider._locator_for_bid(page, bid)
        if locator is None:
            return False
        return bool(
            await locator.evaluate(
                "el => el.tagName === 'SELECT' && (el.id === 'primary_action' || el.name === 'primary_action')"
            )
        )

    @staticmethod
    async def _is_submit(page: Any, bid: str) -> bool:
        locator = await GuardedPlaywrightToolImplProvider._locator_for_bid(page, bid)
        if locator is None:
            return False
        return bool(
            await locator.evaluate(
                """el => {
                    const text = (el.innerText || el.value || '').trim().toLowerCase();
                    return (el.tagName === 'BUTTON' || el.tagName === 'INPUT') &&
                        (el.type === 'submit' || text === 'submit form');
                }"""
            )
        )

    @staticmethod
    async def _selected_primary_option(page: Any) -> str | None:
        locator = page.locator("select#primary_action").first
        if await locator.count() == 0:
            return None
        value = await locator.evaluate(
            "el => el.selectedOptions && el.selectedOptions[0] ? el.selectedOptions[0].textContent.trim() : null"
        )
        return str(value) if value else None

    def implementations(self) -> dict[str, Callable[..., Any]]:
        from cuga.backend.browser_env.tools.providers import PlaywrightToolImplProvider
        from cuga.backend.cuga_graph.nodes.browser.action_agent.tools.alert import Alert

        implementations = PlaywrightToolImplProvider().implementations()
        select_impl = implementations["select_option"]
        click_impl = implementations["click"]

        async def guarded_select_option(
            *,
            bid: str,
            options: str | list[str],
            config: dict[str, Any] | None = None,
        ) -> Any:
            page = (config or {}).get("configurable", {}).get("page")
            if page is not None and await self._is_primary_select(page, bid):
                proposed = options[0] if isinstance(options, list) and options else options
                proposed_text = str(proposed) if proposed is not None else None
                allowed, feedback = await self.guard.before_primary_selection(page, proposed_text)
                if not allowed:
                    return Alert(message=feedback or "PreSubmitGuard blocked this selection once")
            return await select_impl(bid=bid, options=options, config=config)

        async def guarded_click(
            *,
            bid: str,
            button: str = "left",
            modifiers: list[str] | None = None,
            config: dict[str, Any] | None = None,
        ) -> Any:
            page = (config or {}).get("configurable", {}).get("page")
            if page is not None and await self._is_submit(page, bid):
                selected = await self._selected_primary_option(page)
                allowed, feedback = await self.guard.before_submit(page, selected)
                if not allowed:
                    return Alert(message=feedback or "PreSubmitGuard blocked submission once")
            return await click_impl(
                bid=bid,
                button=button,
                modifiers=modifiers,
                config=config,
            )

        implementations["select_option"] = guarded_select_option
        implementations["click"] = guarded_click
        return implementations
