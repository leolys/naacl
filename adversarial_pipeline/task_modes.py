"""
Task-mode utilities for the adversarial generation pipeline.
"""

from __future__ import annotations

import re
from typing import Any


STRICT_ANSWERABLE = "strict_answerable"
ABSTENTION_AWARE = "abstention_aware"
SCOPE_REASONING = "scope_reasoning"

ALL_TASK_MODES = {
    STRICT_ANSWERABLE,
    ABSTENTION_AWARE,
    SCOPE_REASONING,
}

ABSTENTION_PATTERNS = [
    r"cannot be inferred",
    r"cannot infer",
    r"cannot determine",
    r"cannot be determined",
    r"cannot be determined exactly",
    r"inadequate information",
    r"insufficient information",
    r"unable to determine",
    r"not enough information",
    r"无法判断",
    r"无法推断",
    r"不能判断",
]

EXACT_LOOKUP_PREFIXES = (
    "what is",
    "what was",
    "according to the chart, what is",
    "according to the chart, what was",
    "based on the chart, what is",
    "based on the chart, what was",
    "how many",
    "how much",
    "what was the price",
    "what is the price",
    "what is the cost",
    "what was the cost",
    "what was the average",
    "what is the average",
)


def normalize_task_mode(task_mode: str | None) -> str:
    mode = (task_mode or STRICT_ANSWERABLE).strip().lower()
    if mode not in ALL_TASK_MODES:
        return STRICT_ANSWERABLE
    return mode


def options_have_abstention(options: dict[str, str] | None) -> bool:
    joined = " ".join((options or {}).values()).lower()
    return any(re.search(pattern, joined) for pattern in ABSTENTION_PATTERNS)


def looks_like_exact_lookup(question: str | None, options: dict[str, str] | None) -> bool:
    q = (question or "").strip().lower()
    q = re.sub(r"^(according to the chart|based on the chart|from the chart)[,:]?\s*", "", q)
    option_values = " ".join((options or {}).values()).lower()
    numeric_signal = bool(
        re.search(r"[$€£]|\d+(\.\d+)?|mbps|%|mph|kg|people|price|cost|average|total", option_values)
    )
    return numeric_signal and q.startswith(EXACT_LOOKUP_PREFIXES)


def build_task_mode_metadata(task_mode: str, error_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = error_profile or {}
    return {
        "task_mode": normalize_task_mode(task_mode),
        "allowed_task_modes": profile.get("allowed_task_modes", []),
        "default_task_mode": profile.get("default_task_mode"),
        "supports_abstention_option": profile.get("supports_abstention_option", False),
        "requires_qa_refactor": profile.get("qa_refactor_policy") == "required",
    }
