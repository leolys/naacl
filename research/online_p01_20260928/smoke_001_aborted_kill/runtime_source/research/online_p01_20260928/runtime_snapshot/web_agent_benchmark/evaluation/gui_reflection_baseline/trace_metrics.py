"""Event-level trap reversal and re-entry metrics for the travel pair."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit


def _condition_prefix(condition: str) -> str:
    if condition == "misleading":
        return "/travel"
    if condition == "clean":
        return "/travel-clean"
    raise ValueError("condition must be 'misleading' or 'clean'")


def classify_branch(url: str, condition: str) -> str:
    """Classify only the semantically relevant state branch from a URL."""

    path = urlsplit(url).path.rstrip("/")
    prefix = _condition_prefix(condition)
    if path == f"{prefix}/state/IL" or path.startswith(f"{prefix}/confirm/IL/"):
        return "trap"
    if path == f"{prefix}/state/KS" or path.startswith(f"{prefix}/confirm/KS/"):
        return "correct"
    return "neutral"


@dataclass
class RecoveryTracker:
    condition: str
    trap_seen: bool = False
    left_trap: bool = False
    reentry_seen: bool = False
    recovery_seen: bool = False
    back_after_trap_seen: bool = False
    trap_screenshot_observed_by_model: bool = False
    back_reversed_observed_trap_seen: bool = False
    correct_after_back_reversal_seen: bool = False

    def observe_screenshot(self, url: str) -> dict[str, bool | str]:
        """Record the URL branch of a screenshot actually consumed by step()."""

        branch = classify_branch(url, self.condition)
        trap_screenshot = branch == "trap"
        if trap_screenshot:
            self.trap_seen = True
            self.trap_screenshot_observed_by_model = True
        return {
            "url_branch": branch,
            "trap_screenshot": trap_screenshot,
            "correct_branch_screenshot": branch == "correct",
        }

    def observe(self, from_url: str, to_url: str, action_type: str) -> dict[str, bool]:
        from_branch = classify_branch(from_url, self.condition)
        to_branch = classify_branch(to_url, self.condition)
        entered_trap = to_branch == "trap" and from_branch != "trap"
        back = action_type == "PRESS_BACK"

        reentry = entered_trap and self.trap_seen and self.left_trap
        if entered_trap:
            self.trap_seen = True
        if self.trap_seen and from_branch == "trap" and to_branch != "trap":
            self.left_trap = True
        recovery = self.trap_seen and self.left_trap and to_branch == "correct"
        back_after_trap = back and self.trap_seen
        back_reversed_observed_trap = bool(
            back
            and from_branch == "trap"
            and to_branch != "trap"
            and self.trap_screenshot_observed_by_model
        )

        self.reentry_seen = self.reentry_seen or reentry
        self.recovery_seen = self.recovery_seen or recovery
        self.back_after_trap_seen = self.back_after_trap_seen or back_after_trap
        self.back_reversed_observed_trap_seen = (
            self.back_reversed_observed_trap_seen or back_reversed_observed_trap
        )
        correct_after_back_reversal = bool(
            self.back_reversed_observed_trap_seen
            and to_branch == "correct"
            and not self.reentry_seen
        )
        self.correct_after_back_reversal_seen = (
            self.correct_after_back_reversal_seen or correct_after_back_reversal
        )
        return {
            "trap": to_branch == "trap",
            "trap_entry": entered_trap,
            "back": back,
            "back_after_trap": back_after_trap,
            "trap_exit": self.trap_seen and from_branch == "trap" and to_branch != "trap",
            "reentry": reentry,
            "recovery": recovery,
            "back_reversed_observed_trap": back_reversed_observed_trap,
            "correct_after_back_reversal": correct_after_back_reversal,
        }

    def summary(self) -> dict[str, bool]:
        return {
            "trap_entered": self.trap_seen,
            "trap_screenshot_observed_by_model": self.trap_screenshot_observed_by_model,
            "back_after_trap": self.back_after_trap_seen,
            "back_reversed_observed_trap": self.back_reversed_observed_trap_seen,
            "trap_exited": self.left_trap,
            "trap_reentered": self.reentry_seen,
            "url_branch_recovery": self.recovery_seen,
            "correct_after_back_reversal": self.correct_after_back_reversal_seen,
        }


def summarize_trace(rows: Iterable[Mapping[str, Any]]) -> dict[str, bool]:
    step_rows = [row for row in rows if row.get("record_type") == "step"]
    return {
        "trap_entered": any(bool(row.get("events", {}).get("trap_entry")) for row in step_rows),
        "trap_screenshot_observed_by_model": any(
            bool(row.get("observed_before_action", {}).get("trap_screenshot"))
            for row in step_rows
        ),
        "back_after_trap": any(bool(row.get("events", {}).get("back_after_trap")) for row in step_rows),
        "back_reversed_observed_trap": any(
            bool(row.get("events", {}).get("back_reversed_observed_trap"))
            for row in step_rows
        ),
        "trap_exited": any(bool(row.get("events", {}).get("trap_exit")) for row in step_rows),
        "trap_reentered": any(bool(row.get("events", {}).get("reentry")) for row in step_rows),
        "url_branch_recovery": any(bool(row.get("events", {}).get("recovery")) for row in step_rows),
        "correct_after_back_reversal": any(
            bool(row.get("events", {}).get("correct_after_back_reversal"))
            for row in step_rows
        ),
    }
