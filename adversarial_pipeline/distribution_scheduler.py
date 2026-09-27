"""
Distribution-aware scheduler driven by taxonomy profiles and task modes.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from task_modes import (
    ABSTENTION_AWARE,
    SCOPE_REASONING,
    STRICT_ANSWERABLE,
    looks_like_exact_lookup,
    normalize_task_mode,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = Path(__file__).parent / "error_type_profiles.json"

SCOPE_SIGNAL_PATTERNS = (
    r"\btrend\b",
    r"\bincrease\b",
    r"\bdecrease\b",
    r"\brise\b",
    r"\bfall\b",
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\bconclude\b",
    r"\bsuggest\b",
    r"\bbest supported\b",
    r"\bmost supported\b",
    r"\bwhich statement\b",
    r"\bwhat can be concluded\b",
)

SINGLE_TARGET_LOOKUP_PATTERN = re.compile(
    r"\b(?:in|for|of|at|among)\s+[A-Za-z][A-Za-z0-9\-\s]{1,40}\??",
    re.IGNORECASE,
)


@dataclass
class SchedulerConfig:
    target_counts: dict[str, int]
    current_counts: dict[str, int]
    requested_error_types: list[str]
    task_mode_override: str | None = None


def _requested_order_index(error_type: str, scheduler_config: SchedulerConfig | None) -> int:
    if not scheduler_config or not scheduler_config.requested_error_types:
        return 10_000
    try:
        return scheduler_config.requested_error_types.index(error_type)
    except ValueError:
        return 10_000


def load_error_type_profiles(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    profile_path = Path(path) if path else DEFAULT_PROFILE_PATH
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    profiles = {item["error_type"]: item for item in raw["profiles"]}
    return profiles


def load_distribution_target_config(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def count_error_types_in_dataset(dataset_json: str | Path | None) -> dict[str, int]:
    if not dataset_json:
        return {}
    path = Path(dataset_json)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("qa_pairs", [])
    return dict(Counter(str(row.get("error_type", "UNKNOWN")) for row in rows))


def build_scheduler_config(
    *,
    profiles: dict[str, dict[str, Any]],
    current_dataset_json: str | Path | None = None,
    target_config: dict[str, Any] | None = None,
    target_error_types: list[str] | None = None,
    target_count_per_type: int | None = None,
    floor_per_error_type: int | None = None,
    task_mode_override: str | None = None,
) -> SchedulerConfig:
    current_counts = count_error_types_in_dataset(current_dataset_json)
    requested_error_types = [e for e in (target_error_types or []) if e in profiles]
    target_counts: dict[str, int] = {}

    if target_config:
        explicit = target_config.get("explicit_error_type_targets", {})
        for error_type, target in explicit.items():
            if error_type in profiles:
                target_counts[error_type] = int(target)
        if not target_counts and target_config.get("floor_per_error_type") is not None:
            floor = int(target_config["floor_per_error_type"])
            for error_type in profiles:
                target_counts[error_type] = max(current_counts.get(error_type, 0), floor)
    elif requested_error_types:
        count = int(target_count_per_type or 1)
        target_counts = {
            error_type: max(current_counts.get(error_type, 0), count)
            for error_type in requested_error_types
        }
    elif floor_per_error_type is not None:
        floor = int(floor_per_error_type)
        target_counts = {
            error_type: max(current_counts.get(error_type, 0), floor)
            for error_type in profiles
        }

    return SchedulerConfig(
        target_counts=target_counts,
        current_counts=current_counts,
        requested_error_types=requested_error_types,
        task_mode_override=normalize_task_mode(task_mode_override) if task_mode_override else None,
    )


def compute_remaining_targets(
    config: SchedulerConfig,
    success_counts_by_error: dict[str, int],
) -> dict[str, int]:
    remaining: dict[str, int] = {}
    if not config.target_counts:
        return remaining
    for error_type, target in config.target_counts.items():
        base = config.current_counts.get(error_type, 0)
        generated = success_counts_by_error.get(error_type, 0)
        remaining[error_type] = max(0, target - (base + generated))
    return remaining


def _is_single_series_chart(chart_type: str | None) -> bool:
    return (chart_type or "") in {"bar_chart", "line_chart"}


def _question_has_scope_signal(question: str | None) -> bool:
    text = (question or "").strip().lower()
    return any(re.search(pattern, text) for pattern in SCOPE_SIGNAL_PATTERNS)


def _question_is_single_target_lookup(sample: dict[str, Any]) -> bool:
    question = sample.get("question")
    options = sample.get("options")
    if not looks_like_exact_lookup(question, options):
        return False
    return bool(SINGLE_TARGET_LOOKUP_PATTERN.search(question or ""))


def _matches_scheduler_heuristic(sample: dict[str, Any], heuristic: str) -> bool:
    chart_type = sample.get("chart_type")
    exact_lookup = looks_like_exact_lookup(sample.get("question"), sample.get("options"))
    single_target_lookup = _question_is_single_target_lookup(sample)
    has_scope_signal = _question_has_scope_signal(sample.get("question"))

    if heuristic == "bar_exact_lookup_single_target":
        return chart_type == "bar_chart" and exact_lookup and single_target_lookup
    if heuristic == "single_series_exact_lookup":
        return _is_single_series_chart(chart_type) and exact_lookup
    if heuristic == "single_target_lookup":
        return single_target_lookup
    if heuristic == "trend_or_scope_question":
        return has_scope_signal
    if heuristic == "non_exact_or_scope_question":
        return (not exact_lookup) or has_scope_signal
    if heuristic == "multi_series_context":
        return chart_type in {"multi_series_chart", "stacked_bar_chart"}
    if heuristic == "line_or_multi_series_context":
        return chart_type in {"line_chart", "multi_series_chart", "stacked_bar_chart"}
    if heuristic == "context_rich_chart":
        return chart_type in {"multi_series_chart", "stacked_bar_chart", "line_chart"}
    return False


def _compatible_with_sample(sample: dict[str, Any], profile: dict[str, Any]) -> bool:
    compatible_chart_types = profile.get("compatible_chart_types", [])
    if compatible_chart_types and sample.get("chart_type") not in compatible_chart_types:
        return False
    if profile.get("requires_multi_series") and sample.get("chart_type") not in {
        "multi_series_chart",
        "stacked_bar_chart",
    }:
        return False
    exact_lookup_policy = profile.get("exact_lookup_policy", "allow")
    qa_refactor_policy = profile.get("qa_refactor_policy", "none")
    if looks_like_exact_lookup(sample.get("question"), sample.get("options")):
        if exact_lookup_policy == "disallow" and qa_refactor_policy not in {"required", "recommended"}:
            return False
        if exact_lookup_policy in {"requires_refactor", "abstention_preferred"} and qa_refactor_policy == "none":
            return False
    for heuristic in profile.get("scheduler_hard_avoid_heuristics") or []:
        if _matches_scheduler_heuristic(sample, heuristic):
            return False
    return True


def _score_profile_for_sample(
    *,
    sample: dict[str, Any],
    error_type: str,
    profile: dict[str, Any],
    remaining: int,
    scheduler_config: SchedulerConfig | None,
    attempt_counts_by_error: dict[str, int] | None,
    failed_counts_by_error: dict[str, int] | None,
) -> tuple[float, list[str]]:
    exact_lookup = looks_like_exact_lookup(sample.get("question"), sample.get("options"))
    chart_type = sample.get("chart_type", "multi_series_chart")
    task_mode = normalize_task_mode(
        (scheduler_config.task_mode_override if scheduler_config and scheduler_config.task_mode_override else profile.get("default_task_mode"))
        or STRICT_ANSWERABLE
    )
    score = 0.0
    reasons: list[str] = []

    score += remaining * 3.0
    reasons.append(f"remaining={remaining}")

    if chart_type in (profile.get("compatible_chart_types") or []):
        score += 6.0
        reasons.append(f"chart_type_match={chart_type}")

    if profile.get("requires_multi_series"):
        if chart_type in {"multi_series_chart", "stacked_bar_chart"}:
            score += 3.0
            reasons.append("multi_series_match")
    else:
        score += 1.0

    if exact_lookup:
        reasons.append("exact_lookup")
        if task_mode == STRICT_ANSWERABLE:
            score += 5.0
            reasons.append("strict_exact_lookup_bonus")
        elif task_mode == ABSTENTION_AWARE:
            score += 1.5
            reasons.append("abstention_exact_lookup")
        elif task_mode == SCOPE_REASONING:
            score += 2.0
            reasons.append("scope_exact_lookup_refactor")

        if error_type == "Missing_Data":
            score -= 7.0
            reasons.append("missing_data_exact_lookup_penalty")
            if chart_type in {"line_chart", "bar_chart"}:
                score -= 3.0
                reasons.append("single_series_missing_data_penalty")
        elif error_type == "Cherry_Picking":
            score += 6.0
            reasons.append("cherry_picking_refactor_bonus")
        elif error_type == "inconsistentticklabels":
            score += 8.0
            reasons.append("tick_spacing_exact_lookup_bonus")
    else:
        if task_mode == SCOPE_REASONING:
            score += 4.0
            reasons.append("scope_non_exact_bonus")
        elif task_mode == ABSTENTION_AWARE:
            score += 2.0
            reasons.append("abstention_non_exact_bonus")
        else:
            score += 2.0
            reasons.append("strict_non_exact_bonus")

    structure_policy = profile.get("structure_policy", "preserve")
    if structure_policy in {"subset_allowed", "omission_allowed"}:
        if chart_type in {"line_chart", "multi_series_chart", "bar_chart"}:
            score += 2.0
            reasons.append(f"{structure_policy}_chart_bonus")

    for heuristic in profile.get("scheduler_bonuses") or []:
        if _matches_scheduler_heuristic(sample, heuristic):
            score += 4.0
            reasons.append(f"scheduler_bonus={heuristic}")

    for heuristic in profile.get("scheduler_penalties") or []:
        if _matches_scheduler_heuristic(sample, heuristic):
            score -= 5.0
            reasons.append(f"scheduler_penalty={heuristic}")

    order_index = _requested_order_index(error_type, scheduler_config)
    if order_index < 10_000:
        order_bonus = max(0.0, 3.0 - float(order_index))
        score += order_bonus
        reasons.append(f"requested_order_bonus={order_bonus:.1f}")

    attempts = (attempt_counts_by_error or {}).get(error_type, 0)
    failures = (failed_counts_by_error or {}).get(error_type, 0)
    if attempts:
        score -= attempts * 2.5
        reasons.append(f"attempt_penalty={attempts * 2.5:.1f}")
    if failures:
        score -= failures * 7.5
        reasons.append(f"failure_penalty={failures * 7.5:.1f}")

    return score, reasons


def build_attack_request(
    sample: dict[str, Any],
    *,
    profiles: dict[str, dict[str, Any]],
    scheduler_config: SchedulerConfig | None,
    success_counts_by_error: dict[str, int],
    attempt_counts_by_error: dict[str, int] | None = None,
    failed_counts_by_error: dict[str, int] | None = None,
    excluded_error_types: set[str] | None = None,
    legacy_disallowed_error_types: list[str] | None = None,
) -> dict[str, Any]:
    excluded = excluded_error_types or set()
    legacy_disallowed = legacy_disallowed_error_types or []

    if scheduler_config and scheduler_config.target_counts:
        remaining = compute_remaining_targets(scheduler_config, success_counts_by_error)
        ranked = [
            error_type
            for error_type, _ in sorted(remaining.items(), key=lambda kv: (-kv[1], kv[0]))
            if remaining[error_type] > 0 and error_type not in excluded
        ]
    else:
        ranked = [e for e in profiles if e not in excluded]
        remaining = {}

    compatible_ranked = [
        e for e in ranked
        if e in profiles and _compatible_with_sample(sample, profiles[e])
    ]
    if not compatible_ranked:
        return {
            "scheduler_mode": "profiled" if scheduler_config and scheduler_config.target_counts else "legacy_quota",
            "chart_type": sample.get("chart_type", "multi_series_chart"),
            "task": sample.get("task", ""),
            "difficulty": sample.get("difficulty", ""),
            "target_error_type": None,
            "task_mode": normalize_task_mode(
                (scheduler_config.task_mode_override if scheduler_config and scheduler_config.task_mode_override else None)
                or STRICT_ANSWERABLE
            ),
            "error_profile": {},
            "preferred_layers": [],
            "preferred_error_types": [],
            "disallowed_error_types": legacy_disallowed,
            "already_attempted_error_types": sorted(excluded),
            "selection_score": None,
            "selection_reason": "no profile-compatible error type for this sample",
            "quota_remaining_snapshot": {},
        }

    scored_candidates: list[tuple[float, int, str, list[str]]] = []
    for error_type in compatible_ranked:
        candidate_profile = profiles[error_type]
        score, reasons = _score_profile_for_sample(
            sample=sample,
            error_type=error_type,
            profile=candidate_profile,
            remaining=remaining.get(error_type, 0),
            scheduler_config=scheduler_config,
            attempt_counts_by_error=attempt_counts_by_error,
            failed_counts_by_error=failed_counts_by_error,
        )
        scored_candidates.append(
            (score, _requested_order_index(error_type, scheduler_config), error_type, reasons)
        )

    scored_candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    preferred_error_types = [item[2] for item in scored_candidates[:6]]
    target_error_type = preferred_error_types[0] if preferred_error_types else None
    target_profile = profiles.get(target_error_type, {}) if target_error_type else {}
    requested_override = scheduler_config.task_mode_override if scheduler_config else None
    if requested_override and requested_override in (target_profile.get("allowed_task_modes") or []):
        task_mode = requested_override
    else:
        task_mode = target_profile.get("default_task_mode", STRICT_ANSWERABLE)
    task_mode = normalize_task_mode(task_mode)

    exact_lookup = looks_like_exact_lookup(sample.get("question"), sample.get("options"))
    exact_lookup_policy = target_profile.get("exact_lookup_policy", "allow")
    allowed_task_modes = target_profile.get("allowed_task_modes") or []

    if exact_lookup and exact_lookup_policy in {"requires_refactor", "abstention_preferred"}:
        if target_profile.get("supports_abstention_option") and ABSTENTION_AWARE in allowed_task_modes:
            task_mode = ABSTENTION_AWARE
        elif SCOPE_REASONING in allowed_task_modes:
            task_mode = SCOPE_REASONING

    if target_profile.get("supports_abstention_option") and task_mode == STRICT_ANSWERABLE:
        task_mode = ABSTENTION_AWARE
    if target_profile.get("default_task_mode") == SCOPE_REASONING:
        task_mode = SCOPE_REASONING

    preferred_layers = []
    for error_type in preferred_error_types:
        layer_code = profiles.get(error_type, {}).get("layer_code")
        if layer_code and layer_code not in preferred_layers:
            preferred_layers.append(layer_code)

    top_reasons = []
    top_score = None
    if scored_candidates:
        top_score = scored_candidates[0][0]
        top_reasons = scored_candidates[0][3]

    return {
        "scheduler_mode": "profiled" if scheduler_config and scheduler_config.target_counts else "legacy_quota",
        "chart_type": sample.get("chart_type", "multi_series_chart"),
        "task": sample.get("task", ""),
        "difficulty": sample.get("difficulty", ""),
        "target_error_type": target_error_type,
        "task_mode": task_mode,
        "error_profile": target_profile,
        "preferred_layers": preferred_layers,
        "preferred_error_types": preferred_error_types,
        "disallowed_error_types": ["plottingerror"],
        "already_attempted_error_types": sorted(excluded),
        "quota_remaining_snapshot": {e: remaining.get(e, 0) for e in preferred_error_types},
        "selection_score": top_score,
        "selection_reason": "; ".join(top_reasons),
        "scheduler_note": (
            "When target_error_type is provided, treat it as the requested category to implement. "
            "Only deviate if the sample structure makes it impossible, and explain why."
        ),
    }
