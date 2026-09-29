from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from ..actions import ParsedAction
from ..agent_runtime import StepResult
from ..browser_executor import ExecutionResult, ScreenshotFrame
from ..run_formal_task import load_task_set_entries
from ..run_formal_taskset import execute_taskset, summarize_results


class _FakeAgent:
    def __init__(self) -> None:
        self.resets: list[str] = []
        self.goals: list[str] = []

    def reset(self, task_id: str) -> None:
        self.resets.append(task_id)

    def step(
        self,
        _screenshot_png: bytes,
        task_goal: str,
        _task_id: str,
        _viewport_width: int,
        _viewport_height: int,
    ) -> StepResult:
        self.goals.append(task_goal)
        action = ParsedAction("WAIT", (), "WAIT")
        return StepResult(action, "WAIT", "wait")


class _FakeBrowser:
    def __init__(self, policy) -> None:
        self.policy = policy
        self.started: list[str] = []
        self.closed = False
        self.last_sanitizer_record = {
            "required": policy.sanitize_chips,
            "sanitizer_applied": policy.sanitize_chips,
        }

    def start(self, start_url: str) -> None:
        self.started.append(start_url)

    def screenshot(self) -> ScreenshotFrame:
        return ScreenshotFrame(b"png", 1280, 960, self.policy.start_url)

    def execute(self, _action: ParsedAction) -> ExecutionResult:
        return ExecutionResult(
            self.policy.start_url,
            self.policy.start_url,
            None,
            None,
            (),
        )

    def close(self) -> None:
        self.closed = True


class FormalTasksetTests(unittest.TestCase):
    def test_summary_reports_arm_rates_and_paired_transitions(self) -> None:
        results = [
            {
                "pair_group_id": "pair-a",
                "arm": "official",
                "status": "submitted",
                "outcome": "misleading_failure",
            },
            {
                "pair_group_id": "pair-a",
                "arm": "clean",
                "status": "submitted",
                "outcome": "success",
            },
            {
                "pair_group_id": "pair-b",
                "arm": "clean",
                "status": "submitted",
                "outcome": "irrelevant_action_failure",
            },
            {
                "pair_group_id": "pair-b",
                "arm": "official",
                "status": "submitted",
                "outcome": "success",
            },
        ]
        summary = summarize_results(results)
        self.assertEqual(summary["success_by_arm"]["official"]["success"], 1)
        self.assertEqual(summary["success_by_arm"]["clean"]["success"], 1)
        self.assertEqual(summary["paired"]["complete_pair_count"], 2)
        self.assertEqual(
            summary["paired"]["clean_success_official_non_success"], 1
        )
        self.assertEqual(summary["paired"]["directed_vulnerability"], 1)
        self.assertEqual(summary["paired"]["clean_regression"], 1)
        self.assertEqual(summary["paired"]["clean_minus_official_success_pp"], 0.0)

    def test_every_task_gets_reset_and_a_new_executor_and_timeouts_remain(self) -> None:
        entries = load_task_set_entries("smoke17")[:2]
        agent = _FakeAgent()
        browsers: list[_FakeBrowser] = []

        def factory(_task, policy):
            browser = _FakeBrowser(policy)
            browsers.append(browser)
            return browser

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            results = execute_taskset(
                entries=entries,
                arms=("official", "clean"),
                agent=agent,
                browser_factory=factory,
                base_url_resolver=lambda arm, spec: spec.base_url(arm),
                submission_path_resolver=lambda arm, spec: (
                    root / "submissions" / arm / f"{spec.key}.jsonl"
                ),
                run_dir=root / "run",
                max_steps=1,
            )

        self.assertEqual(len(results), 4)
        self.assertEqual([row["status"] for row in results], ["timeout"] * 4)
        self.assertEqual([row["outcome"] for row in results], ["agent_timeout"] * 4)
        self.assertEqual(
            [row["arm"] for row in results],
            ["official", "clean", "clean", "official"],
        )
        self.assertEqual(len(agent.resets), 4)
        self.assertEqual(len(set(agent.resets)), 4)
        self.assertEqual(len(browsers), 4)
        self.assertEqual(len({id(browser) for browser in browsers}), 4)
        self.assertTrue(all(browser.closed for browser in browsers))
        self.assertTrue(all(len(browser.started) == 1 for browser in browsers))

    def test_invalid_task_pointer_is_retained(self) -> None:
        entry = dict(load_task_set_entries("smoke17")[0])
        entry["official_line"] = 999999
        agent = _FakeAgent()
        browser_calls: list[object] = []

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            results = execute_taskset(
                entries=[entry],
                arms=("official",),
                agent=agent,
                browser_factory=lambda task, policy: browser_calls.append(
                    (task, policy)
                ),
                base_url_resolver=lambda arm, spec: spec.base_url(arm),
                submission_path_resolver=lambda arm, spec: root / "none.jsonl",
                run_dir=root / "run",
                max_steps=1,
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "invalid_task")
        self.assertEqual(results[0]["outcome"], "invalid_run")
        self.assertEqual(browser_calls, [])


if __name__ == "__main__":
    unittest.main()
