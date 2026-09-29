#!/usr/bin/env python3
"""Run a paired formal task set with a fresh browser/session per task."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, Iterable
import uuid

from .agent_runtime import (
    AgentClient,
    AgentRuntimeError,
    HttpAgentClient,
    ManagedAgentServer,
)
from .browser_executor import BrowserExecutor
from .formal_path_policy import (
    REPO_ROOT,
    FormalPathPolicy,
    FormalShellSpec,
    shell_spec_for_scenario,
)
from .run_formal_task import (
    FormalTask,
    ManagedFormalShell,
    add_agent_arguments,
    add_browser_arguments,
    append_jsonl,
    browser_from_args,
    load_formal_task,
    load_task_set_entries,
    run_formal_task,
    validate_common_args,
)
from .run_travel_pair import verify_agent_service


BrowserFactory = Callable[[FormalTask, FormalPathPolicy], BrowserExecutor]
BaseUrlResolver = Callable[[str, FormalShellSpec], str]
SubmissionPathResolver = Callable[[str, FormalShellSpec], Path]


def parse_arms(raw: str) -> tuple[str, ...]:
    if raw == "both":
        return ("official", "clean")
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not values or any(value not in {"official", "clean"} for value in values):
        raise ValueError("arms must be 'both', 'official', 'clean', or a comma list")
    return tuple(dict.fromkeys(values))


def parse_scenarios(raw: str | None) -> set[str] | None:
    if not raw or raw == "all":
        return None
    result: set[str] = set()
    for value in raw.split(","):
        value = value.strip()
        if value:
            result.add(shell_spec_for_scenario(value).key)
    if not result:
        raise ValueError("no scenarios selected")
    return result


def filter_entries(
    entries: Iterable[dict[str, Any]],
    scenario_keys: set[str] | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for entry in entries:
        spec = shell_spec_for_scenario(str(entry.get("scenario") or ""))
        if scenario_keys is None or spec.key in scenario_keys:
            selected.append(entry)
    return selected


def _invalid_task_result(
    entry: dict[str, Any], arm: str, exc: Exception
) -> dict[str, Any]:
    return {
        "record_type": "run_summary",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pair_group_id": str(entry.get("pair_group_id") or ""),
        "scenario": str(entry.get("scenario") or ""),
        "slug": str(entry.get("slug") or ""),
        "arm": arm,
        "status": "invalid_task",
        "outcome": "invalid_run",
        "error_attribution": "invalid_task_set_pointer",
        "submission_observed": False,
        "error": repr(exc),
    }


def execute_taskset(
    *,
    entries: list[dict[str, Any]],
    arms: tuple[str, ...],
    agent: AgentClient,
    browser_factory: BrowserFactory,
    base_url_resolver: BaseUrlResolver,
    submission_path_resolver: SubmissionPathResolver,
    run_dir: Path,
    max_steps: int,
    common_metadata: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    """Execute paired arms adjacently with counterbalanced first arm.

    ``browser_factory`` is invoked inside the task loop, and ``run_formal_task``
    calls ``agent.reset`` and closes that executor.  Consequently no browser
    context/session or official-agent history crosses a task boundary.  With
    two arms, even entries use the requested order and odd entries reverse it,
    preventing a full-arm time block from being confounded with chart arm.
    """

    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "runs.jsonl"
    results: list[dict[str, Any]] = []
    for entry_index, entry in enumerate(entries):
        pair_arm_order = (
            arms
            if len(arms) < 2 or entry_index % 2 == 0
            else tuple(reversed(arms))
        )
        for arm in pair_arm_order:
            try:
                task = load_formal_task(entry, arm, repo_root=repo_root)
                spec = shell_spec_for_scenario(task.scenario)
                base_url = base_url_resolver(arm, spec)
                policy = FormalPathPolicy.from_base_url(
                    base_url, task.scenario, arm, task.slug
                )
                # A new object here is the browser/session isolation boundary.
                browser = browser_factory(task, policy)
                trace_jsonl = (
                    run_dir
                    / "traces"
                    / arm
                    / spec.key
                    / f"{task.slug}.jsonl"
                )
                screenshot_dir = (
                    run_dir
                    / "screenshots"
                    / arm
                    / spec.key
                    / task.slug
                )
                result = run_formal_task(
                    task=task,
                    agent=agent,
                    browser=browser,
                    policy=policy,
                    submissions_jsonl=submission_path_resolver(arm, spec),
                    trace_jsonl=trace_jsonl,
                    screenshot_dir=screenshot_dir,
                    max_steps=max_steps,
                    metadata={
                        "taskset_requested_arms": list(arms),
                        "pair_arm_order": list(pair_arm_order),
                        **(common_metadata or {}),
                    },
                )
            except Exception as exc:  # Keep invalid cells in paired accounting.
                result = _invalid_task_result(entry, arm, exc)
            results.append(result)
            append_jsonl(results_path, result)
    return results


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, Counter[str]] = {}
    rows_by_pair: dict[str, dict[str, dict[str, Any]]] = {}
    for row in results:
        arm = str(row.get("arm") or "")
        by_arm.setdefault(arm, Counter())[str(row.get("outcome") or "unknown")] += 1
        pair_group_id = str(row.get("pair_group_id") or "")
        if pair_group_id and arm in {"official", "clean"}:
            rows_by_pair.setdefault(pair_group_id, {})[arm] = row

    arm_success = {}
    for arm, counts in sorted(by_arm.items()):
        cell_count = sum(counts.values())
        success_count = counts.get("success", 0)
        arm_success[arm] = {
            "n": cell_count,
            "success": success_count,
            "success_rate": success_count / cell_count if cell_count else None,
        }

    complete_pairs = [
        pair for pair in rows_by_pair.values() if {"official", "clean"} <= pair.keys()
    ]
    paired_counts = Counter()
    for pair in complete_pairs:
        official_outcome = str(pair["official"].get("outcome") or "unknown")
        clean_outcome = str(pair["clean"].get("outcome") or "unknown")
        official_success = official_outcome == "success"
        clean_success = clean_outcome == "success"
        if official_success and clean_success:
            paired_counts["both_success"] += 1
        elif not official_success and clean_success:
            paired_counts["clean_success_official_non_success"] += 1
        elif official_success and not clean_success:
            paired_counts["clean_regression"] += 1
        else:
            paired_counts["both_non_success"] += 1
        if clean_success and official_outcome == "misleading_failure":
            paired_counts["directed_vulnerability"] += 1

    official_rate = arm_success.get("official", {}).get("success_rate")
    clean_rate = arm_success.get("clean", {}).get("success_rate")
    clean_minus_official_pp = (
        100 * (float(clean_rate) - float(official_rate))
        if official_rate is not None and clean_rate is not None
        else None
    )
    return {
        "run_count": len(results),
        "status_counts": dict(Counter(str(row.get("status")) for row in results)),
        "outcome_counts": dict(Counter(str(row.get("outcome")) for row in results)),
        "outcomes_by_arm": {
            arm: dict(counts) for arm, counts in sorted(by_arm.items())
        },
        "success_by_arm": arm_success,
        "paired": {
            "complete_pair_count": len(complete_pairs),
            "both_success": paired_counts["both_success"],
            "clean_success_official_non_success": paired_counts[
                "clean_success_official_non_success"
            ],
            "clean_regression": paired_counts["clean_regression"],
            "both_non_success": paired_counts["both_non_success"],
            "directed_vulnerability": paired_counts["directed_vulnerability"],
            "clean_minus_official_success_pp": clean_minus_official_pp,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-set",
        required=True,
        help="smoke17, chart_only114, readiness95, strict_review94, or JSONL path",
    )
    parser.add_argument("--arms", default="both")
    parser.add_argument(
        "--scenarios",
        help="comma-separated public39,business47,environment35,health19",
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--port-offset", type=int, default=0)
    parser.add_argument("--shell-startup-timeout", type=float, default=30.0)
    add_browser_arguments(parser)
    add_agent_arguments(parser)
    args = parser.parse_args(argv)
    validate_common_args(parser, args)
    try:
        args.arm_list = parse_arms(args.arms)
        args.scenario_keys = parse_scenarios(args.scenarios)
    except ValueError as exc:
        parser.error(str(exc))
    if args.shell_startup_timeout <= 0:
        parser.error("--shell-startup-timeout must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = (args.output_root / run_id).resolve()
    entries = filter_entries(
        load_task_set_entries(args.task_set), args.scenario_keys
    )
    if not entries:
        print("GUI-Reflection task-set run has no selected tasks", file=sys.stderr)
        return 2

    needed_specs: list[FormalShellSpec] = []
    seen_keys: set[str] = set()
    for entry in entries:
        spec = shell_spec_for_scenario(str(entry.get("scenario") or ""))
        if spec.key not in seen_keys:
            needed_specs.append(spec)
            seen_keys.add(spec.key)

    managed_shells: list[ManagedFormalShell] = []
    managed_agent: ManagedAgentServer | None = None
    try:
        submission_paths: dict[tuple[str, str], Path] = {}
        for arm in args.arm_list:
            for spec in needed_specs:
                submissions = (
                    run_dir / "shell_submissions" / arm / f"{spec.key}.jsonl"
                )
                submission_paths[(arm, spec.key)] = submissions
                shell = ManagedFormalShell(
                    spec=spec,
                    arm=arm,
                    base_url=spec.base_url(arm, args.port_offset),
                    tasks_path=spec.tasks_path(arm),
                    submissions_path=submissions,
                    work_dir=run_dir / "shells" / arm / spec.key,
                    startup_timeout_seconds=args.shell_startup_timeout,
                )
                shell.start()
                managed_shells.append(shell)

        if args.agent_url:
            client: AgentClient = HttpAgentClient(
                args.agent_url, args.agent_request_timeout
            )
        else:
            agent_log = args.agent_log or (run_dir / "agent.log")
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

        def browser_factory(
            _task: FormalTask, policy: FormalPathPolicy
        ) -> BrowserExecutor:
            return browser_from_args(args, policy)

        results = execute_taskset(
            entries=entries,
            arms=args.arm_list,
            agent=client,
            browser_factory=browser_factory,
            base_url_resolver=lambda arm, spec: spec.base_url(
                arm, args.port_offset
            ),
            submission_path_resolver=lambda arm, spec: submission_paths[
                (arm, spec.key)
            ],
            run_dir=run_dir,
            max_steps=args.max_steps,
            common_metadata={
                "task_set": str(args.task_set),
                "browser_backend": args.browser_backend,
                "viewport": [args.viewport_width, args.viewport_height],
                "agent_health": health,
                "shell_provenance": "managed_canonical_release_file",
            },
        )
        summary = {
            "run_id": run_id,
            "task_set": str(args.task_set),
            "arms": list(args.arm_list),
            "requested_pair_count": len(entries),
            **summarize_results(results),
        }
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {"run_dir": str(run_dir), **summary},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, RuntimeError, AgentRuntimeError) as exc:
        print(f"GUI-Reflection formal task-set failed: {exc}", file=sys.stderr)
        return 2
    finally:
        if managed_agent is not None:
            managed_agent.close()
        for shell in reversed(managed_shells):
            shell.close()


if __name__ == "__main__":
    raise SystemExit(main())
