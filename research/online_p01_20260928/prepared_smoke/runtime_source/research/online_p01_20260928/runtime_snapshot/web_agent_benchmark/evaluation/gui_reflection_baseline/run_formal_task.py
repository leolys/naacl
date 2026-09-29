#!/usr/bin/env python3
"""Run official GUI-Reflection on one canonical formal benchmark task.

Only a viewport PNG and the canonical ``workflow_instruction`` are sent to the
agent.  URLs, task records, submission scores, and path-policy decisions remain
runner-side metadata.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
import json
import multiprocessing
from pathlib import Path
import socket
import sys
import time
from typing import Any, Callable, Iterable
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from .actions import ActionParseError
from .agent_runtime import (
    AgentClient,
    AgentRuntimeError,
    HttpAgentClient,
    ManagedAgentServer,
)
from .browser_executor import (
    BrowserExecutionError,
    BrowserExecutor,
    PlaywrightExecutor,
    ScreenshotFrame,
    SeleniumFirefoxExecutor,
    UnsupportedWebAction,
)
from .formal_path_policy import (
    ARM_SPLITS,
    DATASET_ROOT,
    REPO_ROOT,
    FormalPathPolicy,
    FormalShellSpec,
    shell_spec_for_scenario,
)
from .path_policy import NavigationBlocked
from .run_travel_pair import verify_agent_service


TASK_SET_DIR = Path(__file__).resolve().parent / "task_sets"
SUPPORTED_TASK_SETS = (
    "smoke17",
    "chart_only114",
    "readiness95",
    "strict_review94",
)

_CHIP_SANITIZER_JAVASCRIPT = """() => {
  const styleId = 'gui-reflection-formal-chip-sanitizer';
  let styleInjected = false;
  if (!document.getElementById(styleId)) {
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = '.chips { display: none !important; }';
    (document.head || document.documentElement).appendChild(style);
    styleInjected = true;
  }
  const nodes = Array.from(document.querySelectorAll('.chips'));
  nodes.forEach((node) => node.remove());
  return {
    selector: '.chips',
    removed_element_count: nodes.length,
    style_injected_this_step: styleInjected,
    applied_before_screenshot: true
  };
}"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"expected JSON object in {path}:{line_number}")
        rows.append(row)
    return rows


def resolve_task_set_path(value: str | Path) -> Path:
    candidate = Path(value)
    if candidate.is_file():
        return candidate.resolve()
    name = str(value)
    if name not in SUPPORTED_TASK_SETS:
        raise ValueError(
            f"unknown task set {name!r}; choose one of {SUPPORTED_TASK_SETS} "
            "or pass an existing JSONL path"
        )
    path = TASK_SET_DIR / f"{name}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"task set is missing: {path}")
    return path.resolve()


def load_task_set_entries(value: str | Path) -> list[dict[str, Any]]:
    return read_jsonl(resolve_task_set_path(value))


def select_task_set_entry(
    entries: Iterable[dict[str, Any]], slug: str
) -> dict[str, Any]:
    matches = [entry for entry in entries if entry.get("slug") == slug]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one task-set entry for slug {slug!r}, found {len(matches)}"
        )
    return matches[0]


def task_goal_from_record(record: dict[str, Any]) -> str:
    """Return only the canonical user-facing workflow instruction.

    In particular, no ground-truth, action role, misleader type, rationale, or
    scorer field is composed into the goal.
    """

    goal = record.get("workflow_instruction")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("canonical task record has no non-empty workflow_instruction")
    return goal.strip()


@dataclass(frozen=True)
class FormalTask:
    pair_group_id: str
    scenario: str
    scenario_key: str
    slug: str
    arm: str
    split: str
    task_id: str
    task_instance_id: str
    task_goal: str
    source_path: Path
    source_line: int


def _path_within_repo(path_value: str, repo_root: Path) -> Path:
    path = Path(path_value)
    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"task source escapes repository root: {resolved}") from exc
    return resolved


def _jsonl_line(path: Path, line_number: int) -> dict[str, Any]:
    if line_number <= 0:
        raise ValueError("task source line must be positive")
    for current, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if current == line_number:
            if not line.strip():
                raise ValueError(f"task source line is empty: {path}:{line_number}")
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"task source is not an object: {path}:{line_number}")
            return row
    raise ValueError(f"task source line does not exist: {path}:{line_number}")


def load_formal_task(
    entry: dict[str, Any],
    arm: str,
    *,
    repo_root: Path = REPO_ROOT,
    dataset_root: Path = DATASET_ROOT,
) -> FormalTask:
    if arm not in ARM_SPLITS:
        raise ValueError(f"unknown paired arm: {arm!r}")
    scenario = str(entry.get("scenario") or "")
    spec = shell_spec_for_scenario(scenario)
    slug = str(entry.get("slug") or "")
    spec.validate_slug(slug)

    path_key = f"{arm}_path"
    line_key = f"{arm}_line"
    if not entry.get(path_key):
        raise ValueError(f"task-set entry omitted {path_key}")
    source_path = _path_within_repo(str(entry[path_key]), repo_root)
    expected_path = spec.tasks_path(arm, dataset_root).resolve()
    if source_path != expected_path:
        raise ValueError(
            f"task-set source for {arm}/{slug} is not the canonical release file: "
            f"{source_path} != {expected_path}"
        )
    source_line = int(entry.get(line_key, 0))
    record = _jsonl_line(source_path, source_line)

    expected_split = ARM_SPLITS[arm]
    checks = {
        "task_slug": slug,
        "scenario": scenario,
        "pair_group_id": str(entry.get("pair_group_id") or ""),
        "split": expected_split,
    }
    mismatches = {
        key: (record.get(key), expected)
        for key, expected in checks.items()
        if record.get(key) != expected
    }
    if mismatches:
        raise ValueError(
            f"task-set pointer mismatch at {source_path}:{source_line}: {mismatches}"
        )
    task_id = str(record.get("task_id") or "")
    if not task_id:
        raise ValueError(f"canonical task has no task_id: {source_path}:{source_line}")
    task_instance_id = str(
        record.get("task_instance_id")
        or f"{expected_split}:{spec.key}:{slug}"
    )
    return FormalTask(
        pair_group_id=checks["pair_group_id"],
        scenario=scenario,
        scenario_key=spec.key,
        slug=slug,
        arm=arm,
        split=expected_split,
        task_id=task_id,
        task_instance_id=task_instance_id,
        task_goal=task_goal_from_record(record),
        source_path=source_path,
        source_line=source_line,
    )


def _not_required_sanitizer_record() -> dict[str, Any]:
    return {
        "required": False,
        "sanitizer_applied": False,
        "selector": None,
        "removed_element_count": 0,
        "applied_before_screenshot": False,
    }


def _required_sanitizer_record(payload: Any) -> dict[str, Any]:
    result = dict(payload) if isinstance(payload, dict) else {}
    return {
        "required": True,
        "sanitizer_applied": True,
        "selector": ".chips",
        "removed_element_count": int(result.get("removed_element_count", 0)),
        "style_injected_this_step": bool(
            result.get("style_injected_this_step", False)
        ),
        "applied_before_screenshot": True,
    }


class FormalPlaywrightExecutor(PlaywrightExecutor):
    """Playwright coordinate executor with the symmetric chips sanitizer."""

    policy: FormalPathPolicy

    def __init__(self, policy: FormalPathPolicy, **kwargs: Any) -> None:
        super().__init__(policy, **kwargs)
        self.last_sanitizer_record = _not_required_sanitizer_record()

    def screenshot(self) -> ScreenshotFrame:
        if self._page is None:
            raise BrowserExecutionError("browser has not been started")
        # Containment precedes even the narrowly scoped sanitizer.  A page
        # reached outside the assigned task is terminated without DOM access
        # and, critically, without entering the model's screenshot history.
        self.policy.assert_document_url(self._page.url)
        if self.policy.sanitize_chips:
            payload = self._page.evaluate(_CHIP_SANITIZER_JAVASCRIPT)
            self.last_sanitizer_record = _required_sanitizer_record(payload)
        else:
            self.last_sanitizer_record = _not_required_sanitizer_record()
        return super().screenshot()


class FormalSeleniumFirefoxExecutor(SeleniumFirefoxExecutor):
    """Selenium coordinate executor with the same symmetric sanitizer."""

    policy: FormalPathPolicy

    def __init__(self, policy: FormalPathPolicy, **kwargs: Any) -> None:
        super().__init__(policy, **kwargs)
        self.last_sanitizer_record = _not_required_sanitizer_record()

    def screenshot(self) -> ScreenshotFrame:
        if self._driver is None:
            raise BrowserExecutionError("browser has not been started")
        self.policy.assert_document_url(self._driver.current_url)
        if self.policy.sanitize_chips:
            payload = self._driver.execute_script(
                f"return ({_CHIP_SANITIZER_JAVASCRIPT})()"
            )
            self.last_sanitizer_record = _required_sanitizer_record(payload)
        else:
            self.last_sanitizer_record = _not_required_sanitizer_record()
        return super().screenshot()


def sanitizer_record(browser: BrowserExecutor) -> dict[str, Any]:
    value = getattr(browser, "last_sanitizer_record", None)
    if isinstance(value, dict):
        return dict(value)
    return _not_required_sanitizer_record()


def build_browser(
    *,
    policy: FormalPathPolicy,
    backend: str = "playwright",
    viewport_width: int = 1280,
    viewport_height: int = 960,
    headed: bool = False,
    browser_executable: str | None = None,
    firefox_binary: str | None = None,
    geckodriver: str | None = None,
    firefox_library_path: str | None = None,
    action_wait_ms: int = 700,
    long_press_ms: int = 800,
) -> BrowserExecutor:
    common = {
        "viewport_width": viewport_width,
        "viewport_height": viewport_height,
        "headed": headed,
        "action_wait_ms": action_wait_ms,
        "long_press_ms": long_press_ms,
    }
    if backend == "playwright":
        return FormalPlaywrightExecutor(
            policy,
            browser_executable=browser_executable,
            **common,
        )
    if backend == "selenium-firefox":
        return FormalSeleniumFirefoxExecutor(
            policy,
            firefox_binary=firefox_binary,
            geckodriver=geckodriver,
            firefox_library_path=firefox_library_path,
            **common,
        )
    raise ValueError(f"unsupported browser backend: {backend!r}")


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _line in handle)


def read_new_submission(
    path: Path, offset: int, task_id: str
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    matches: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index < offset or not line.strip():
                continue
            row = json.loads(line)
            if row.get("task_id") == task_id:
                matches.append(row)
    return matches[-1] if matches else None


def _outcome_without_submission(status: str) -> tuple[str, str]:
    if status == "timeout":
        return "agent_timeout", "no_submission_within_max_steps"
    if status == "invalid_action":
        return "invalid_action", "invalid_gui_reflection_action"
    if status == "agent_error":
        return "agent_error", "gui_reflection_runtime_error"
    if status == "navigation_blocked":
        return "invalid_run", "navigation_containment_violation"
    if status == "agent_impossible":
        return "completion_failure", "agent_declared_task_impossible"
    if status == "agent_complete_without_submission":
        return "completion_failure", "agent_completed_without_submission"
    if status == "browser_error":
        return "invalid_run", "browser_execution_error"
    return "invalid_run", "runner_error"


def run_formal_task(
    *,
    task: FormalTask,
    agent: AgentClient,
    browser: BrowserExecutor,
    policy: FormalPathPolicy,
    submissions_jsonl: Path,
    trace_jsonl: Path,
    screenshot_dir: Path,
    max_steps: int = 20,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one isolated task and always retain timeout/invalid outcomes."""

    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if policy.arm != task.arm or policy.task_slug != task.slug:
        raise ValueError("task and formal path policy identify different arms/tasks")

    submission_offset = line_count(submissions_jsonl)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    append_jsonl(
        trace_jsonl,
        {
            "record_type": "run_start",
            "timestamp": utc_now(),
            "pair_group_id": task.pair_group_id,
            "task_id": task.task_id,
            "task_instance_id": task.task_instance_id,
            "scenario": task.scenario,
            "scenario_key": task.scenario_key,
            "slug": task.slug,
            "arm": task.arm,
            "split": task.split,
            "start_url": policy.start_url,
            "task_goal": task.task_goal,
            "model_input_fields": ["viewport_screenshot_png", "task_goal"],
            "semantic_dom_actions": False,
            "sanitizer_required": policy.sanitize_chips,
            **(metadata or {}),
        },
    )

    status = "timeout"
    terminal_action: str | None = None
    error: str | None = None
    steps_completed = 0
    sanitizer_was_applied = False
    try:
        # The official agent owns screenshot/action history and its memory bank;
        # reset is therefore mandatory before every task instance.
        agent.reset(task.task_instance_id)
        browser.start(policy.start_url)
        for step_index in range(max_steps):
            try:
                frame = browser.screenshot()
            except (NavigationBlocked, BrowserExecutionError) as exc:
                status = (
                    "navigation_blocked"
                    if isinstance(exc, NavigationBlocked)
                    else "browser_error"
                )
                error = str(exc)
                append_jsonl(
                    trace_jsonl,
                    {
                        "record_type": "step_error",
                        "timestamp": utc_now(),
                        "task_instance_id": task.task_instance_id,
                        "step": step_index,
                        "phase": "screenshot",
                        "status": status,
                        "error": error,
                    },
                )
                break

            sanitization = sanitizer_record(browser)
            sanitizer_was_applied = sanitizer_was_applied or bool(
                sanitization.get("sanitizer_applied")
            )
            screenshot_path = screenshot_dir / f"step_{step_index:02d}.png"
            screenshot_path.write_bytes(frame.png)
            try:
                step_result = agent.step(
                    frame.png,
                    task.task_goal,
                    task.task_instance_id,
                    frame.width,
                    frame.height,
                )
            except ActionParseError as exc:
                status = "invalid_action"
                error = str(exc)
                append_jsonl(
                    trace_jsonl,
                    {
                        "record_type": "step_error",
                        "timestamp": utc_now(),
                        "task_instance_id": task.task_instance_id,
                        "step": step_index,
                        "phase": "agent_step",
                        "url": frame.url,
                        "screenshot_path": str(screenshot_path.resolve()),
                        "sanitizer": sanitization,
                        "status": status,
                        "error": error,
                    },
                )
                break
            except AgentRuntimeError as exc:
                status = "agent_error"
                error = str(exc)
                append_jsonl(
                    trace_jsonl,
                    {
                        "record_type": "step_error",
                        "timestamp": utc_now(),
                        "task_instance_id": task.task_instance_id,
                        "step": step_index,
                        "phase": "agent_step",
                        "url": frame.url,
                        "screenshot_path": str(screenshot_path.resolve()),
                        "sanitizer": sanitization,
                        "status": status,
                        "error": error,
                    },
                )
                break

            action = step_result.action
            step_row: dict[str, Any] = {
                "record_type": "step",
                "timestamp": utc_now(),
                "task_instance_id": task.task_instance_id,
                "step": step_index,
                "url": frame.url,
                "from_url": frame.url,
                "screenshot_path": str(screenshot_path.resolve()),
                "screenshot_size": [frame.width, frame.height],
                "sanitizer": sanitization,
                "sanitizer_applied": bool(
                    sanitization.get("sanitizer_applied")
                ),
                "action_raw": step_result.action_raw,
                "action_description": step_result.action_description,
                "action_parsed": action.as_dict(),
                "coordinates": {
                    "normalized": (
                        list(action.normalized_coordinates)
                        if action.normalized_coordinates is not None
                        else None
                    ),
                    "pixels_parsed": (
                        list(action.pixel_coordinates)
                        if action.pixel_coordinates is not None
                        else None
                    ),
                    "pixels_executed": None,
                },
            }
            try:
                execution = browser.execute(action)
            except UnsupportedWebAction as exc:
                status = "invalid_action"
                error = str(exc)
                step_row.update(
                    {
                        "to_url": frame.url,
                        "status": status,
                        "execution_error": error,
                        "navigation_blocked": False,
                    }
                )
                append_jsonl(trace_jsonl, step_row)
                break
            except NavigationBlocked as exc:
                status = "navigation_blocked"
                error = str(exc)
                step_row.update(
                    {
                        "to_url": None,
                        "status": status,
                        "execution_error": error,
                        "navigation_blocked": True,
                    }
                )
                append_jsonl(trace_jsonl, step_row)
                break
            except BrowserExecutionError as exc:
                status = "browser_error"
                error = str(exc)
                step_row.update(
                    {
                        "to_url": None,
                        "status": status,
                        "execution_error": error,
                        "navigation_blocked": False,
                    }
                )
                append_jsonl(trace_jsonl, step_row)
                break

            steps_completed = step_index + 1
            step_row["to_url"] = execution.to_url
            step_row["coordinates"]["pixels_executed"] = (
                list(execution.executed_coordinates)
                if execution.executed_coordinates is not None
                else None
            )
            step_row["blocked_requests"] = list(execution.blocked_requests)
            step_row["navigation_blocked"] = bool(execution.blocked_requests)
            step_row["reached_confirmation"] = policy.is_confirmation_url(
                execution.to_url
            )
            append_jsonl(trace_jsonl, step_row)

            if execution.blocked_requests:
                status = "navigation_blocked"
                error = "browser blocked one or more out-of-policy requests"
                break
            if policy.is_confirmation_url(execution.to_url):
                status = "submitted"
                break
            if execution.terminal == "TASK_COMPLETE":
                terminal_action = execution.terminal
                status = "agent_complete_without_submission"
                break
            if execution.terminal == "TASK_IMPOSSIBLE":
                terminal_action = execution.terminal
                status = "agent_impossible"
                break
    except AgentRuntimeError as exc:
        status = "agent_error"
        error = str(exc)
    except (NavigationBlocked, BrowserExecutionError) as exc:
        status = (
            "navigation_blocked"
            if isinstance(exc, NavigationBlocked)
            else "browser_error"
        )
        error = str(exc)
    except Exception as exc:  # Preserve the cell instead of dropping it.
        status = "runner_error"
        error = repr(exc)
    finally:
        try:
            browser.close()
        except Exception as exc:
            if error is None:
                error = f"browser close failed: {exc!r}"
                status = "runner_error"

    submission = read_new_submission(
        submissions_jsonl, submission_offset, task.task_id
    )
    evaluation = (
        submission.get("evaluation_hidden_from_agent", {})
        if isinstance(submission, dict)
        else {}
    )
    if evaluation.get("outcome"):
        outcome = str(evaluation["outcome"])
        error_attribution = str(evaluation.get("error_attribution", ""))
    else:
        outcome, error_attribution = _outcome_without_submission(status)

    summary = {
        "record_type": "run_summary",
        "timestamp": utc_now(),
        "pair_group_id": task.pair_group_id,
        "task_id": task.task_id,
        "task_instance_id": task.task_instance_id,
        "scenario": task.scenario,
        "scenario_key": task.scenario_key,
        "slug": task.slug,
        "arm": task.arm,
        "split": task.split,
        "status": status,
        "outcome": outcome,
        "error_attribution": error_attribution,
        "terminal_action": terminal_action,
        "steps_completed": steps_completed,
        "submission_observed": submission is not None,
        "selected_action_id": (
            str(submission.get("selected_action_id", ""))
            if isinstance(submission, dict)
            else ""
        ),
        "selected_action_label": (
            str(submission.get("selected_action_label", ""))
            if isinstance(submission, dict)
            else ""
        ),
        "sanitizer_required": policy.sanitize_chips,
        "sanitizer_applied": sanitizer_was_applied,
        "semantic_dom_actions": False,
        "error": error,
    }
    append_jsonl(trace_jsonl, summary)
    return summary


def shell_health_payload(base_url: str, timeout_seconds: float = 2.0) -> dict[str, Any] | None:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(
            f"{base_url.rstrip('/')}/health", timeout=timeout_seconds
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def assert_shell_health(spec: FormalShellSpec, base_url: str) -> dict[str, Any]:
    payload = shell_health_payload(base_url)
    if not payload or not payload.get("ok"):
        raise RuntimeError(f"formal shell is not healthy at {base_url}/health")
    count = int(payload.get(spec.health_count_field, -1))
    if count != spec.task_count:
        raise RuntimeError(
            f"formal shell at {base_url} reports {count} {spec.key} tasks; "
            f"expected {spec.task_count}"
        )
    return payload


def _serve_formal_shell(
    scenario_key: str,
    tasks_path_value: str,
    submissions_path_value: str,
    summary_path_value: str,
    auxiliary_path_value: str,
    host: str,
    port: int,
    log_path_value: str,
) -> None:
    """Spawn target for a non-review formal Flask shell."""

    spec = shell_spec_for_scenario(scenario_key)
    tasks_path = Path(tasks_path_value)
    submissions_path = Path(submissions_path_value)
    summary_path = Path(summary_path_value)
    auxiliary_path = Path(auxiliary_path_value)
    log_path = Path(log_path_value)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_handle:
        with redirect_stdout(log_handle), redirect_stderr(log_handle):
            module = importlib.import_module(spec.module_name)
            if spec.key == "public39":
                app = module.make_app(
                    submissions_path,
                    tasks_path,
                    summary_path,
                    review_ui=False,
                )
            elif spec.key == "business47":
                app = module.make_app(
                    tasks_path,
                    submissions_path,
                    summary_path,
                    manual_review_path=auxiliary_path,
                    review_ui=False,
                )
            else:
                app = module.make_app(
                    tasks_path,
                    submissions_path,
                    review_ui=False,
                )
            app.run(
                host=host,
                port=port,
                debug=False,
                use_reloader=False,
                threaded=False,
            )


@dataclass
class ManagedFormalShell:
    spec: FormalShellSpec
    arm: str
    base_url: str
    tasks_path: Path
    submissions_path: Path
    work_dir: Path
    startup_timeout_seconds: float = 30.0
    process: Any = None

    def start(self) -> dict[str, Any]:
        if not self.tasks_path.is_file():
            raise FileNotFoundError(f"formal shell task file is missing: {self.tasks_path}")
        task_rows = read_jsonl(self.tasks_path)
        if len(task_rows) != self.spec.task_count:
            raise RuntimeError(
                f"{self.tasks_path} contains {len(task_rows)} rows; "
                f"expected {self.spec.task_count}"
            )
        parsed_base = self.base_url.rsplit(":", 1)
        if len(parsed_base) != 2:
            raise ValueError(f"managed shell requires host:port base URL: {self.base_url}")
        host = "127.0.0.1"
        port = int(parsed_base[-1])
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
        except OSError as exc:
            raise RuntimeError(
                f"refusing to reuse occupied port {port}: the shell health endpoint "
                "cannot prove which paired task file it serves"
            ) from exc
        finally:
            probe.close()

        self.work_dir.mkdir(parents=True, exist_ok=True)
        summary_path = self.work_dir / "shell_summary.md"
        auxiliary_path = self.work_dir / "business_manual_review.md"
        log_path = self.work_dir / "shell.log"
        context = multiprocessing.get_context("spawn")
        self.process = context.Process(
            target=_serve_formal_shell,
            args=(
                self.spec.key,
                str(self.tasks_path.resolve()),
                str(self.submissions_path.resolve()),
                str(summary_path.resolve()),
                str(auxiliary_path.resolve()),
                host,
                port,
                str(log_path.resolve()),
            ),
            name=f"gui-reflection-{self.arm}-{self.spec.key}",
        )
        self.process.start()
        deadline = time.monotonic() + self.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.process.exitcode is not None:
                raise RuntimeError(
                    f"formal shell {self.arm}/{self.spec.key} exited with "
                    f"code {self.process.exitcode}; see {log_path}"
                )
            payload = shell_health_payload(self.base_url)
            if payload:
                return assert_shell_health(self.spec, self.base_url)
            time.sleep(0.2)
        self.close()
        raise RuntimeError(
            f"formal shell {self.arm}/{self.spec.key} was not ready within "
            f"{self.startup_timeout_seconds:g}s; see {log_path}"
        )

    def close(self) -> None:
        if self.process is not None and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=10)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=5)
        self.process = None

    def __enter__(self) -> "ManagedFormalShell":
        self.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()


def add_browser_arguments(parser: argparse.ArgumentParser) -> None:
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


def add_agent_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent-url")
    parser.add_argument("--official-repo", type=Path)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--agent-python", default=sys.executable)
    parser.add_argument("--agent-port", type=int, default=8091)
    parser.add_argument("--agent-log", type=Path)
    parser.add_argument("--agent-startup-timeout", type=float, default=900.0)
    parser.add_argument("--agent-request-timeout", type=float, default=300.0)
    parser.add_argument("--temporal-len", type=int, default=4)


def validate_common_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
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
            "local mode requires both --official-repo and the real "
            "GUI-Reflection --model-path"
        )


def browser_from_args(
    args: argparse.Namespace, policy: FormalPathPolicy
) -> BrowserExecutor:
    return build_browser(
        policy=policy,
        backend=args.browser_backend,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        headed=args.headed,
        browser_executable=args.browser_executable,
        firefox_binary=args.firefox_binary,
        geckodriver=args.geckodriver,
        firefox_library_path=args.firefox_library_path,
        action_wait_ms=args.action_wait_ms,
        long_press_ms=args.long_press_ms,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--arm", choices=("official", "clean"), required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--port-offset", type=int, default=0)
    parser.add_argument("--start-shell", action="store_true")
    parser.add_argument("--submissions-jsonl", required=True, type=Path)
    parser.add_argument("--trace-jsonl", required=True, type=Path)
    parser.add_argument("--screenshot-dir", type=Path)
    parser.add_argument("--shell-work-dir", type=Path)
    add_browser_arguments(parser)
    add_agent_arguments(parser)
    args = parser.parse_args(argv)
    validate_common_args(parser, args)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    managed_shell: ManagedFormalShell | None = None
    managed_agent: ManagedAgentServer | None = None
    browser: BrowserExecutor | None = None
    try:
        entry = select_task_set_entry(
            load_task_set_entries(args.task_set), args.slug
        )
        task = load_formal_task(entry, args.arm)
        spec = shell_spec_for_scenario(task.scenario)
        base_url = args.base_url or spec.base_url(args.arm, args.port_offset)
        policy = FormalPathPolicy.from_base_url(
            base_url, task.scenario, task.arm, task.slug
        )
        shell_provenance = "external_unverified_tasks_file"
        if args.start_shell:
            shell_work_dir = args.shell_work_dir or (
                args.trace_jsonl.parent
                / f"{task.arm}_{task.scenario_key}_shell"
            )
            managed_shell = ManagedFormalShell(
                spec=spec,
                arm=task.arm,
                base_url=base_url,
                tasks_path=spec.tasks_path(task.arm),
                submissions_path=args.submissions_jsonl.resolve(),
                work_dir=shell_work_dir.resolve(),
            )
            managed_shell.start()
            shell_provenance = "managed_canonical_release_file"
        else:
            assert_shell_health(spec, base_url)

        if args.agent_url:
            client: AgentClient = HttpAgentClient(
                args.agent_url, args.agent_request_timeout
            )
        else:
            agent_log = args.agent_log or args.trace_jsonl.with_suffix(
                ".agent.log"
            )
            managed_agent = ManagedAgentServer(
                official_repo=args.official_repo,
                model_path=args.model_path,
                port=args.agent_port,
                log_path=agent_log,
                python_executable=args.agent_python,
                temporal_len=args.temporal_len,
                startup_timeout_seconds=args.agent_startup_timeout,
                request_timeout_seconds=args.agent_request_timeout,
            )
            client = managed_agent.start()
        health = verify_agent_service(client)  # type: ignore[arg-type]
        browser = browser_from_args(args, policy)
        screenshot_dir = args.screenshot_dir or (
            args.trace_jsonl.parent
            / f"{args.trace_jsonl.stem}_{task.arm}_{task.slug}_screenshots"
        )
        summary = run_formal_task(
            task=task,
            agent=client,
            browser=browser,
            policy=policy,
            submissions_jsonl=args.submissions_jsonl.resolve(),
            trace_jsonl=args.trace_jsonl.resolve(),
            screenshot_dir=screenshot_dir.resolve(),
            max_steps=args.max_steps,
            metadata={
                "browser_backend": args.browser_backend,
                "viewport": [args.viewport_width, args.viewport_height],
                "agent_health": health,
                "shell_provenance": shell_provenance,
            },
        )
        browser = None  # run_formal_task closed it.
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, AgentRuntimeError) as exc:
        print(f"GUI-Reflection formal task failed: {exc}", file=sys.stderr)
        return 2
    finally:
        if browser is not None:
            browser.close()
        if managed_agent is not None:
            managed_agent.close()
        if managed_shell is not None:
            managed_shell.close()


if __name__ == "__main__":
    raise SystemExit(main())
