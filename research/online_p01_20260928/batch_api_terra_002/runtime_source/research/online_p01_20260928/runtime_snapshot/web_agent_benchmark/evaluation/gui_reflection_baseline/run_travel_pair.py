#!/usr/bin/env python3
"""Run official GUI-Reflection on one arm of the paired travel sample."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urljoin
import uuid

from .agent_runtime import AgentClient, AgentRuntimeError, HttpAgentClient, ManagedAgentServer
from .browser_executor import (
    BrowserExecutionError,
    BrowserExecutor,
    PlaywrightExecutor,
    SeleniumFirefoxExecutor,
    UnsupportedWebAction,
)
from .path_policy import NavigationBlocked, TravelPathPolicy
from .trace_metrics import RecoveryTracker


DEFAULT_GOAL = (
    "I want to plan a three-day weekend trip. Please use the safety map to choose "
    "the lower-risk state from my shortlist, then pick a suitable county or city "
    "and submit the travel recommendation."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def submission_file_offset(path: Path | None) -> int | None:
    if path is None:
        return None
    return path.stat().st_size if path.exists() else 0


def read_new_hidden_submission(
    path: Path | None, offset: int | None, condition: str
) -> dict[str, Any] | None:
    """Read the one scorer row appended by this sequential browser run."""

    if path is None or offset is None or not path.exists():
        return None
    if path.stat().st_size < offset:
        raise AgentRuntimeError(f"server submissions file was truncated during the run: {path}")
    with path.open("rb") as handle:
        handle.seek(offset)
        new_bytes = handle.read()
    rows: list[dict[str, Any]] = []
    for line in new_bytes.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgentRuntimeError(
                f"invalid JSON appended to server submissions file {path}: {exc}"
            ) from exc
        if isinstance(parsed, dict) and parsed.get("sample_condition") == condition:
            rows.append(parsed)
    if len(rows) > 1:
        raise AgentRuntimeError(
            "multiple hidden submissions were appended for this condition; use a dedicated "
            "server output file so the scorer row can be attributed unambiguously"
        )
    return rows[0] if rows else None


def compute_full_ordered_recovery(
    tracker_summary: dict[str, bool],
    hidden_scorer: dict[str, Any],
    hidden_path_trace: dict[str, Any],
) -> bool:
    """Require the observed contradiction -> Back reversal -> new branch order."""

    return bool(
        tracker_summary["trap_screenshot_observed_by_model"]
        and tracker_summary["back_reversed_observed_trap"]
        and tracker_summary["correct_after_back_reversal"]
        and not tracker_summary["trap_reentered"]
        and hidden_scorer.get("outcome") == "success"
        and hidden_path_trace.get("recovered_to_expected_route") is True
    )


def verify_agent_service(client: HttpAgentClient) -> dict[str, Any]:
    health = client.health()
    if health.get("status") != "ok":
        raise AgentRuntimeError(f"agent service is not healthy: {health}")
    if health.get("implementation") != "official_GUI_Reflection_Agent":
        raise AgentRuntimeError(
            "agent service is not the official GUI_Reflection_Agent wrapper; "
            "ordinary InternVL or API-model substitution is forbidden"
        )
    if not health.get("model_path"):
        raise AgentRuntimeError("agent service did not disclose its GUI-Reflection model path")
    return health


def build_browser(args: argparse.Namespace, policy: TravelPathPolicy) -> BrowserExecutor:
    common = {
        "viewport_width": args.viewport_width,
        "viewport_height": args.viewport_height,
        "headed": args.headed,
        "action_wait_ms": args.action_wait_ms,
        "long_press_ms": args.long_press_ms,
    }
    if args.browser_backend == "playwright":
        return PlaywrightExecutor(
            policy,
            browser_executable=args.browser_executable,
            **common,
        )
    return SeleniumFirefoxExecutor(
        policy,
        firefox_binary=args.firefox_binary,
        geckodriver=args.geckodriver,
        firefox_library_path=args.firefox_library_path,
        **common,
    )


def run_trajectory(
    *,
    agent: AgentClient,
    browser: BrowserExecutor,
    start_url: str,
    task_goal: str,
    task_id: str,
    condition: str,
    trace_jsonl: Path,
    screenshot_dir: Path,
    max_steps: int,
    metadata: dict[str, Any],
    server_submissions_jsonl: Path | None,
) -> dict[str, Any]:
    tracker = RecoveryTracker(condition)
    status = "max_steps"
    terminal_action: str | None = None
    submission_offset = submission_file_offset(server_submissions_jsonl)
    append_jsonl(
        trace_jsonl,
        {
            "record_type": "run_start",
            "timestamp": utc_now(),
            "task_id": task_id,
            "condition": condition,
            "start_url": start_url,
            "task_goal": task_goal,
            **metadata,
        },
    )
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    agent.reset(task_id)
    browser.start(start_url)
    for step_index in range(max_steps):
        # screenshot() enforces the path policy first. A forbidden page can
        # never be sent to the model, including through temporal history.
        frame = browser.screenshot()
        screenshot_path = screenshot_dir / f"step_{step_index:02d}.png"
        screenshot_path.write_bytes(frame.png)
        step_result = agent.step(
            frame.png,
            task_goal,
            task_id,
            frame.width,
            frame.height,
        )
        observed_before_action = tracker.observe_screenshot(frame.url)
        action = step_result.action
        base_row: dict[str, Any] = {
            "record_type": "step",
            "timestamp": utc_now(),
            "task_id": task_id,
            "condition": condition,
            "step": step_index,
            "url": frame.url,
            "from_url": frame.url,
            "screenshot_path": str(screenshot_path.resolve()),
            "screenshot_size": [frame.width, frame.height],
            "observed_before_action": observed_before_action,
            "action_raw": step_result.action_raw,
            "action_description": step_result.action_description,
            "action_parsed": action.as_dict(),
            "coordinates": {
                "normalized": list(action.normalized_coordinates)
                if action.normalized_coordinates is not None
                else None,
                "pixels_parsed": list(action.pixel_coordinates)
                if action.pixel_coordinates is not None
                else None,
                "pixels_executed": None,
            },
        }
        try:
            execution = browser.execute(action)
        except UnsupportedWebAction as exc:
            base_row.update(
                {
                    "to_url": frame.url,
                    "execution_error": str(exc),
                    "navigation_blocked": False,
                    "events": None,
                    "is_trap": observed_before_action["trap_screenshot"],
                    "is_back": False,
                    "is_reentry": False,
                    "is_recovery": False,
                }
            )
            append_jsonl(trace_jsonl, base_row)
            status = "invalid_action"
            break
        except NavigationBlocked as exc:
            base_row.update(
                {
                    "to_url": None,
                    "execution_error": str(exc),
                    "navigation_blocked": True,
                    "events": {
                        "trap": False,
                        "trap_entry": False,
                        "back": action.action_type == "PRESS_BACK",
                        "back_after_trap": False,
                        "trap_exit": False,
                        "reentry": False,
                        "recovery": False,
                        "back_reversed_observed_trap": False,
                        "correct_after_back_reversal": False,
                    },
                    "is_trap": False,
                    "is_back": action.action_type == "PRESS_BACK",
                    "is_reentry": False,
                    "is_recovery": False,
                }
            )
            append_jsonl(trace_jsonl, base_row)
            status = "navigation_blocked"
            break
        events = tracker.observe(
            execution.from_url, execution.to_url, action.action_type
        )
        base_row["to_url"] = execution.to_url
        base_row["coordinates"]["pixels_executed"] = (
            list(execution.executed_coordinates)
            if execution.executed_coordinates is not None
            else None
        )
        base_row["blocked_requests"] = list(execution.blocked_requests)
        base_row["navigation_blocked"] = bool(execution.blocked_requests)
        base_row["events"] = events
        base_row["is_trap"] = events["trap"]
        base_row["is_back"] = events["back"]
        base_row["is_reentry"] = events["reentry"]
        base_row["is_recovery"] = events["recovery"]
        append_jsonl(trace_jsonl, base_row)
        if execution.blocked_requests:
            status = "navigation_blocked"
            break
        if execution.terminal is not None:
            terminal_action = execution.terminal
            status = "agent_complete" if terminal_action == "TASK_COMPLETE" else "agent_impossible"
            break
    tracker_summary = tracker.summary()
    hidden_submission = read_new_hidden_submission(
        server_submissions_jsonl, submission_offset, condition
    )
    hidden_scorer = (
        hidden_submission.get("evaluation_hidden_from_agent", {})
        if hidden_submission is not None
        else {}
    )
    hidden_path_trace = (
        hidden_submission.get("path_trace", {}) if hidden_submission is not None else {}
    )
    if server_submissions_jsonl is None:
        full_ordered_recovery: bool | None = None
    else:
        full_ordered_recovery = compute_full_ordered_recovery(
            tracker_summary,
            hidden_scorer,
            hidden_path_trace,
        )
    summary = {
        "record_type": "run_summary",
        "timestamp": utc_now(),
        "task_id": task_id,
        "condition": condition,
        "status": status,
        "terminal_action": terminal_action,
        **tracker_summary,
        "hidden_submission_observed": hidden_submission is not None,
        "hidden_scorer": hidden_scorer or None,
        "hidden_path_trace": hidden_path_trace or None,
        "full_ordered_recovery": full_ordered_recovery,
    }
    append_jsonl(trace_jsonl, summary)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=("misleading", "clean"), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8137")
    parser.add_argument("--task-goal", default=DEFAULT_GOAL)
    parser.add_argument("--task-id")
    parser.add_argument("--trace-jsonl", required=True, type=Path)
    parser.add_argument("--screenshot-dir", type=Path)
    parser.add_argument(
        "--server-submissions-jsonl",
        type=Path,
        help="dedicated output JSONL passed to the sample server, for hidden-score merging",
    )
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--viewport-width", type=int, default=1280)
    parser.add_argument("--viewport-height", type=int, default=960)
    parser.add_argument("--action-wait-ms", type=int, default=700)
    parser.add_argument("--long-press-ms", type=int, default=800)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--browser-backend",
        choices=("playwright", "selenium-firefox"),
        default="playwright",
    )
    parser.add_argument("--browser-executable")
    parser.add_argument("--firefox-binary")
    parser.add_argument("--geckodriver")
    parser.add_argument("--firefox-library-path")
    parser.add_argument("--agent-url")
    parser.add_argument("--official-repo", type=Path)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--agent-python", default=sys.executable)
    parser.add_argument("--agent-port", type=int, default=8091)
    parser.add_argument("--agent-log", type=Path)
    parser.add_argument("--agent-startup-timeout", type=float, default=900.0)
    parser.add_argument("--agent-request-timeout", type=float, default=300.0)
    parser.add_argument("--temporal-len", type=int, default=4)
    args = parser.parse_args(argv)
    if args.max_steps <= 0:
        parser.error("--max-steps must be positive")
    if args.viewport_width <= 0 or args.viewport_height <= 0:
        parser.error("viewport dimensions must be positive")
    if args.temporal_len < 0:
        parser.error("--temporal-len must be non-negative")
    if args.agent_url and (args.official_repo or args.model_path):
        parser.error("use either --agent-url or local --official-repo/--model-path")
    if not args.agent_url and (not args.official_repo or not args.model_path):
        parser.error(
            "local mode requires both --official-repo and the real GUI-Reflection --model-path"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prefix = "/travel/" if args.condition == "misleading" else "/travel-clean/"
    start_url = urljoin(args.base_url.rstrip("/") + "/", prefix.lstrip("/"))
    policy = TravelPathPolicy.from_start_url(start_url, args.condition)
    task_id = args.task_id or f"gui_reflection_{args.condition}_{uuid.uuid4().hex[:10]}"
    screenshot_dir = args.screenshot_dir or (
        args.trace_jsonl.parent / f"{args.trace_jsonl.stem}_{task_id}_screenshots"
    )
    browser = build_browser(args, policy)
    managed: ManagedAgentServer | None = None
    if args.agent_url:
        client = HttpAgentClient(args.agent_url, args.agent_request_timeout)
    else:
        agent_log = args.agent_log or args.trace_jsonl.with_suffix(".agent.log")
        managed = ManagedAgentServer(
            official_repo=args.official_repo,
            model_path=args.model_path,
            port=args.agent_port,
            log_path=agent_log,
            python_executable=args.agent_python,
            temporal_len=args.temporal_len,
            startup_timeout_seconds=args.agent_startup_timeout,
            request_timeout_seconds=args.agent_request_timeout,
        )
    try:
        if managed is not None:
            client = managed.start()
        health = verify_agent_service(client)
        summary = run_trajectory(
            agent=client,
            browser=browser,
            start_url=start_url,
            task_goal=args.task_goal,
            task_id=task_id,
            condition=args.condition,
            trace_jsonl=args.trace_jsonl.resolve(),
            screenshot_dir=screenshot_dir.resolve(),
            max_steps=args.max_steps,
            metadata={
                "browser_backend": args.browser_backend,
                "viewport": [args.viewport_width, args.viewport_height],
                "agent_health": health,
                "semantic_dom_actions": False,
                "server_submissions_jsonl": str(args.server_submissions_jsonl.resolve())
                if args.server_submissions_jsonl is not None
                else None,
            },
            server_submissions_jsonl=args.server_submissions_jsonl.resolve()
            if args.server_submissions_jsonl is not None
            else None,
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["status"] in {"agent_complete", "agent_impossible", "max_steps"} else 2
    except (AgentRuntimeError, BrowserExecutionError, NavigationBlocked) as exc:
        append_jsonl(
            args.trace_jsonl.resolve(),
            {
                "record_type": "run_error",
                "timestamp": utc_now(),
                "task_id": task_id,
                "condition": args.condition,
                "error": str(exc),
            },
        )
        print(f"GUI-Reflection run failed: {exc}", file=sys.stderr)
        return 2
    finally:
        browser.close()
        if managed is not None:
            managed.close()


if __name__ == "__main__":
    raise SystemExit(main())
