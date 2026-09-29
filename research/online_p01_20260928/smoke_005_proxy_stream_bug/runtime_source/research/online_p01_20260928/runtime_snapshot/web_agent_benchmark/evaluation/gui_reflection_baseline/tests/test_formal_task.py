from __future__ import annotations

import json
import unittest

from ..formal_path_policy import FormalPathPolicy, shell_spec_for_scenario
from ..path_policy import NavigationBlocked
from ..run_formal_task import (
    FormalPlaywrightExecutor,
    load_formal_task,
    load_task_set_entries,
    task_goal_from_record,
)


def fake_png(width: int = 1280, height: int = 960) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.expressions: list[str] = []

    def evaluate(self, expression: str):
        self.expressions.append(expression)
        return {
            "removed_element_count": 2,
            "style_injected_this_step": True,
        }

    def screenshot(self, **_kwargs):
        return fake_png()


class FormalTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entries = load_task_set_entries("smoke17")

    def test_task_pointer_and_goal_use_only_canonical_instruction(self) -> None:
        entry = next(item for item in self.entries if item["slug"] == "b001")
        task = load_formal_task(entry, "official")
        raw = json.loads(
            task.source_path.read_text(encoding="utf-8").splitlines()[
                task.source_line - 1
            ]
        )
        self.assertEqual(task.task_goal, raw["workflow_instruction"])
        self.assertFalse(hasattr(task, "ground_truth"))
        self.assertFalse(hasattr(task, "misleader_type"))
        self.assertFalse(hasattr(task, "action_space"))

        synthetic = {
            "workflow_instruction": "Visible user goal",
            "ground_truth": {"secret": "DO_NOT_LEAK"},
            "misleader_type": "SECRET_TYPE",
            "action_space": [{"role": "correct"}],
        }
        self.assertEqual(task_goal_from_record(synthetic), "Visible user goal")

    def test_environment_and_health_sanitize_both_arms(self) -> None:
        for scenario, slug in (
            ("environment_climate_water_energy", "env001"),
            ("health", "health001"),
        ):
            spec = shell_spec_for_scenario(scenario)
            self.assertTrue(spec.sanitize_chips)
            for arm in ("official", "clean"):
                policy = FormalPathPolicy.from_base_url(
                    spec.base_url(arm), scenario, arm, slug
                )
                self.assertTrue(policy.sanitize_chips)

        public = shell_spec_for_scenario("public39")
        self.assertFalse(public.sanitize_chips)

    def test_chips_are_removed_before_viewport_screenshot(self) -> None:
        policy = FormalPathPolicy.from_base_url(
            "http://127.0.0.1:18233",
            "environment35",
            "official",
            "env001",
        )
        executor = FormalPlaywrightExecutor(policy)
        page = _FakePage(policy.start_url)
        executor._page = page
        frame = executor.screenshot()
        self.assertEqual((frame.width, frame.height), (1280, 960))
        self.assertEqual(len(page.expressions), 1)
        self.assertIn("querySelectorAll('.chips')", page.expressions[0])
        self.assertTrue(executor.last_sanitizer_record["sanitizer_applied"])
        self.assertEqual(
            executor.last_sanitizer_record["removed_element_count"], 2
        )

    def test_forbidden_document_is_rejected_before_sanitizer_script(self) -> None:
        policy = FormalPathPolicy.from_base_url(
            "http://127.0.0.1:18233",
            "environment35",
            "official",
            "env001",
        )
        executor = FormalPlaywrightExecutor(policy)
        page = _FakePage("http://127.0.0.1:18233/")
        executor._page = page
        with self.assertRaises(NavigationBlocked):
            executor.screenshot()
        self.assertEqual(page.expressions, [])


if __name__ == "__main__":
    unittest.main()
