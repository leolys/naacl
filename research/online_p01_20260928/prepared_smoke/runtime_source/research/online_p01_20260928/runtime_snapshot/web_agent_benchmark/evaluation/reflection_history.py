#!/usr/bin/env python3
"""Cross-step history adapter for the controlled reflection pilot."""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from math import ceil
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit


CONDITIONS = {
    "no_history",
    "previous_step",
    "full_history",
    "structured_falsification",
}
MEMORY_FIELDS = (
    "current_hypothesis",
    "supporting_visible_evidence",
    "contradicting_visible_evidence",
    "tried_actions",
    "rejected_routes",
    "unresolved_question",
    "next_verification_target",
)
LIST_FIELDS = {
    "supporting_visible_evidence",
    "contradicting_visible_evidence",
    "tried_actions",
    "rejected_routes",
}
HIDDEN_KEYS = {
    "expected_action_id",
    "misleading_action_ids",
    "evaluation_hidden_from_agent",
    "review_role",
    "scoring_outcome",
    "misleader_type",
}
INTERNAL_METADATA_TERMS = (
    "expected_action_id",
    "misleading_action_ids",
    "evaluation_hidden_from_agent",
    "review_role",
    "scoring_outcome",
    "misleader_type",
    "task_readiness",
    "formal_scored_task",
    "ms_inappropriate_scale_functions",
    "ms_inappropriate_scale_range",
    "ms_unconventional_scale_directions",
    "categorical_encoding_for_continuous_data",
    "cherry_picking",
    "data_visual_disproportion",
    "dual_axis_distortion",
    "dual_encoding",
    "misleading_annotations",
    "misuse_of_cumulative_relationship",
    "small_size",
)
_DYNAMIC_QUERY_KEYS = {"_", "ts", "timestamp", "session", "session_id", "nonce"}
_TOKEN_PIECES = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def condition_from_env() -> str:
    condition = os.environ.get("WEB_AGENT_HISTORY_CONDITION", "").strip()
    if condition and condition not in CONDITIONS:
        raise ValueError(f"Unknown WEB_AGENT_HISTORY_CONDITION={condition!r}")
    return condition


def action_generation_attempt_limit(
    history_runtime: "HistoryRuntime | None",
) -> int:
    """Use one logical model call per browser step in the controlled pilot."""
    return 1 if history_runtime is not None else 3


def sanitize_visible_page_for_pilot(
    page: Any,
    history_runtime: "HistoryRuntime | None",
) -> dict[str, Any] | None:
    """Remove shell metadata badges before pilot screenshots and DOM capture."""
    if history_runtime is None:
        return None
    removed_count = int(page.evaluate(
        """() => {
          const nodes = Array.from(document.querySelectorAll('.chips'));
          nodes.forEach((node) => node.remove());
          return nodes.length;
        }"""
    ))
    return {
        "selector": ".chips",
        "removed_element_count": removed_count,
        "applied_before_screenshot_and_state_capture": True,
    }


def empty_memory() -> dict[str, Any]:
    return {name: [] if name in LIST_FIELDS else "" for name in MEMORY_FIELDS}


def normalize_memory(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result = empty_memory()
    for name in MEMORY_FIELDS:
        raw = source.get(name)
        if name in LIST_FIELDS:
            if isinstance(raw, list):
                result[name] = [str(item)[:500] for item in raw[:8]]
            elif raw:
                result[name] = [str(raw)[:500]]
        elif raw is not None:
            result[name] = str(raw)[:1000]
    return result


def normalize_text(value: Any, *, limit: int = 8000) -> str:
    return _WHITESPACE.sub(" ", str(value or "")).strip()[:limit]


def estimate_tokens(value: str) -> int:
    """Return one deterministic estimator shared by every model and condition."""
    pieces = _TOKEN_PIECES.findall(value)
    lexical_cost = sum(max(1, ceil(len(piece) / 4)) for piece in pieces)
    return max(lexical_cost, ceil(len(value.encode("utf-8")) / 4))


def assert_no_hidden_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in HIDDEN_KEYS:
                raise ValueError(f"Hidden evaluator field in history payload: {path}.{key}")
            assert_no_hidden_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_hidden_keys(child, path=f"{path}[{index}]")


def internal_metadata_terms_in(value: Any) -> list[str]:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, sort_keys=True)
    ).lower()
    return [term for term in INTERNAL_METADATA_TERMS if term in text]


def normalized_url(url: str) -> dict[str, str]:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _DYNAMIC_QUERY_KEYS
    ]
    return {"path": parts.path, "query": urlencode(sorted(query))}


def semantic_state(state: dict[str, Any]) -> dict[str, Any]:
    """Preserve visible task evidence while dropping DOM indices and local ports."""
    elements = state.get("elements") or {}
    result = {
        "url": normalized_url(str(state.get("url") or "")),
        "text": normalize_text(state.get("text")),
        "links": [
            {
                "text": normalize_text(item.get("text"), limit=500),
                "href": normalized_url(str(item.get("href") or "")),
            }
            for item in elements.get("links") or []
            if isinstance(item, dict)
        ],
        "buttons": [
            {
                "text": normalize_text(item.get("text"), limit=500),
                "type": str(item.get("type") or ""),
            }
            for item in elements.get("buttons") or []
            if isinstance(item, dict)
        ],
        "selects": [
            {
                "name": str(item.get("name") or item.get("id") or ""),
                "value": str(item.get("value") or ""),
                "label": normalize_text(item.get("label"), limit=500),
                "selected_text": normalize_text(item.get("selected_text"), limit=500),
                "options": [
                    {
                        "value": str(option.get("value") or ""),
                        "text": normalize_text(option.get("text"), limit=500),
                        "selected": bool(option.get("selected")),
                        "disabled": bool(option.get("disabled")),
                    }
                    for option in item.get("options") or []
                    if isinstance(option, dict)
                ],
            }
            for item in elements.get("selects") or []
            if isinstance(item, dict)
        ],
    }
    assert_no_hidden_keys(result)
    return result


def state_hash(state: dict[str, Any]) -> str:
    serialized = json.dumps(
        semantic_state(state),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def action_signature(action: dict[str, Any]) -> str:
    payload = {
        "action": str(action.get("action") or ""),
        "text": normalize_text(action.get("text"), limit=500),
        "select_name": str(action.get("select_name") or ""),
        "option_text": normalize_text(
            action.get("option_text") or action.get("value"),
            limit=500,
        ),
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def output_contract_text() -> str:
    """Common instruction supplied unchanged in all four conditions."""
    return (
        "\n\nControlled cross-step memory protocol:\n"
        "Return exactly one JSON object with keys `action` and `memory_update`. "
        "`action` must contain exactly one allowed browser action. `memory_update` "
        "must contain current_hypothesis, supporting_visible_evidence, "
        "contradicting_visible_evidence, tried_actions, rejected_routes, "
        "unresolved_question, and next_verification_target. Use only visible evidence "
        "from pages already shown. Never infer hidden labels, scoring, expected actions, "
        "or benchmark metadata. Update memory in this same response. Use prior visible "
        "evidence to avoid repeating an already disproven route, whether or not a "
        "prior-history record is supplied."
    )


def _structured_truncate(value: Any, token_limit: int) -> tuple[Any, bool]:
    """Shrink values, never serialized JSON bytes, until the payload fits."""
    payload = deepcopy(value)
    truncated = False
    while estimate_tokens(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    ) > token_limit:
        strings: list[tuple[int, Any, Any]] = []
        lists: list[tuple[int, list[Any]]] = []

        def collect(current: Any) -> None:
            if isinstance(current, dict):
                for key, child in current.items():
                    if isinstance(child, str) and child:
                        strings.append((len(child), current, key))
                    else:
                        collect(child)
            elif isinstance(current, list):
                if current:
                    lists.append((len(current), current))
                for index, child in enumerate(current):
                    if isinstance(child, str) and child:
                        strings.append((len(child), current, index))
                    else:
                        collect(child)

        collect(payload)
        if strings:
            _, container, key = max(strings, key=lambda item: item[0])
            text = str(container[key])
            container[key] = text[: max(0, len(text) // 2)]
            truncated = True
            continue
        if lists:
            _, target = max(lists, key=lambda item: item[0])
            target.pop()
            truncated = True
            continue
        payload = {"truncated": True}
        truncated = True
        break
    return payload, truncated


@dataclass
class HistoryRuntime:
    condition: str
    token_limit: int = 3000
    records: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "HistoryRuntime | None":
        condition = condition_from_env()
        if not condition:
            return None
        token_limit = int(os.environ.get("WEB_AGENT_HISTORY_TOKEN_LIMIT", "3000"))
        if token_limit < 256:
            raise ValueError("WEB_AGENT_HISTORY_TOKEN_LIMIT must be at least 256")
        return cls(condition=condition, token_limit=token_limit)

    @staticmethod
    def _history_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "step": record["step"],
            "observation": record["observation"],
            "executed_action": record["executed_action"],
            "memory_update": record["memory_update"],
        }

    def _metadata(
        self,
        serialized: str,
        retained_steps: list[int],
        truncated: bool,
    ) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "history_chars": len(serialized),
            "history_tokens_estimated": estimate_tokens(serialized),
            "history_records_available": len(self.records),
            "history_records_injected": len(retained_steps),
            "retained_step_ids": retained_steps,
            "history_truncated": truncated,
            "history_payload_sha256": hashlib.sha256(
                serialized.encode("utf-8")
            ).hexdigest(),
        }

    def history_payload(self) -> tuple[str, dict[str, Any]]:
        if self.condition == "no_history" or not self.records:
            return "", self._metadata("", [], False)

        if self.condition == "previous_step":
            payload: Any = self._history_record(self.records[-1])
        elif self.condition == "structured_falsification":
            payload = {"evidence_ledger": self.records[-1]["memory_update"]}
        else:
            payload = [self._history_record(record) for record in self.records]

        truncated = False
        if self.condition == "full_history":
            while len(payload) > 1:
                serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if estimate_tokens(serialized) <= self.token_limit:
                    break
                payload.pop(0)
                truncated = True
        payload, structured_truncated = _structured_truncate(payload, self.token_limit)
        truncated = truncated or structured_truncated
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        assert_no_hidden_keys(payload)
        retained_steps = (
            [int(item["step"]) for item in payload if isinstance(item, dict) and "step" in item]
            if isinstance(payload, list)
            else (
                [int(self.records[-1]["step"])]
                if isinstance(payload, dict) and payload != {"truncated": True}
                else []
            )
        )
        label = {
            "previous_step": "Previous-step record",
            "full_history": "Full cross-step history",
            "structured_falsification": "Structured falsification ledger",
        }[self.condition]
        prompt = (
            f"\n\n{label} (visible evidence and executed actions only):\n"
            f"{serialized}"
        )
        return prompt, self._metadata(serialized, retained_steps, truncated)

    def normalize_response(
        self,
        parsed: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        schema_valid = isinstance(parsed.get("action"), dict) and isinstance(
            parsed.get("memory_update"),
            dict,
        )
        if isinstance(parsed.get("action"), dict):
            action = dict(parsed["action"])
        else:
            action = dict(parsed)
            action.pop("memory_update", None)
        return action, normalize_memory(parsed.get("memory_update")), schema_valid

    def record(
        self,
        *,
        step: int,
        state: dict[str, Any],
        action: dict[str, Any],
        memory_update: dict[str, Any],
        execution_status: str,
    ) -> dict[str, Any]:
        record = {
            "step": step,
            "observation": semantic_state(state),
            "state_hash": state_hash(state),
            "executed_action": {
                "signature": action_signature(action),
                "action": str(action.get("action") or ""),
                "text": str(action.get("text") or ""),
                "select_name": str(action.get("select_name") or ""),
                "option_text": str(action.get("option_text") or action.get("value") or ""),
            },
            "memory_update": normalize_memory(memory_update),
            "execution_status": execution_status,
        }
        self.records.append(record)
        return record


def attach_pilot_request(
    user_text: str,
    runtime: HistoryRuntime | None,
) -> tuple[str, dict[str, Any]]:
    if runtime is None:
        return user_text, {}
    history_text, metadata = runtime.history_payload()
    return f"{user_text}{output_contract_text()}{history_text}", metadata


def unpack_pilot_response(
    parsed: dict[str, Any],
    runtime: HistoryRuntime | None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if runtime is None:
        return parsed, {}, True
    return runtime.normalize_response(parsed)
