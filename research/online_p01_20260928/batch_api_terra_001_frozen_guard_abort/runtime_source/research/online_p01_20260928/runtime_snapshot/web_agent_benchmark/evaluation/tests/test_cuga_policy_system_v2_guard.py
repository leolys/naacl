from __future__ import annotations

import asyncio
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVALUATION_ROOT = REPO_ROOT / "web_agent_benchmark" / "evaluation"
CUGA_SRC = REPO_ROOT / "external_tools" / "cuga-agent" / "src"
sys.path.insert(0, str(EVALUATION_ROOT))
sys.path.insert(0, str(CUGA_SRC))

from cuga_policy_system_v2_guard import (  # noqa: E402
    APPROVAL_CONFIDENCE,
    VisibleEvidenceGuard,
    approval_reasons,
    assert_guard_input_has_no_hidden_fields,
    build_guard_messages,
    parse_guard_response,
    validate_guard_response,
)


def response(**overrides):
    value = {
        "criterion": {
            "metric": "visible score",
            "operation": "max",
            "unit": None,
            "time_scope": None,
        },
        "candidates": [
            {
                "entity": "Alpha",
                "value_or_relation": 10,
                "source": "label",
                "axis_or_legend": None,
                "readability": "clear",
            }
        ],
        "computed_entity": "Alpha",
        "recommended_option": "Choose Alpha",
        "proposed_option_supported": True,
        "confidence": 0.9,
        "conflicts": [],
        "verdict": "approve",
        "reason": "The visible label is largest.",
    }
    value.update(overrides)
    return value


class FakeStateGuard(VisibleEvidenceGuard):
    async def _visible_state(self, page, proposed_option):
        return {
            "visible_text": "Visible chart and form",
            "visible_options": ["Choose Alpha", "Choose Beta"],
            "actual_options": [],
            "proposed_option": proposed_option,
            "raw_proposed_option": proposed_option,
            "screenshot_bytes": b"png",
        }


class GuardContractTests(unittest.TestCase):
    def test_frozen_playbook_hash_and_always_trigger(self):
        from cuga.backend.cuga_graph.policy.agent import PolicyAgent, PolicyContext
        from cuga.backend.cuga_graph.policy.folder_loader import (
            create_playbook_from_markdown,
            parse_markdown_with_frontmatter,
        )
        from cuga.backend.cuga_graph.policy.models import AlwaysTrigger, PolicyType

        path = EVALUATION_ROOT / "cuga_policy_system" / "chart_verification_playbook_v2.md"
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            "06012867be220f82e344b09fd38a4cf2c044ce15103ac4cf5e6e4a6fbfe3d0ec",
        )
        frontmatter, content = parse_markdown_with_frontmatter(str(path))
        policy = create_playbook_from_markdown(str(path), frontmatter, content)
        self.assertEqual(policy.id, "rebuttal_chart_verification_playbook_v2")
        self.assertEqual(len(policy.triggers), 1)
        self.assertIsInstance(policy.triggers[0], AlwaysTrigger)

        class FakeStorage:
            async def list_policies(self, policy_type=None, enabled_only=True):
                return [policy] if policy_type == PolicyType.PLAYBOOK else []

        matches = asyncio.run(
            PolicyAgent(storage=FakeStorage()).match_policies_by_type(
                PolicyContext(user_input="any visible chart task"), PolicyType.PLAYBOOK
            )
        )
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].matched)
        self.assertEqual(matches[0].confidence, 1.0)

    def test_schema_and_json_fence_parsing(self):
        parsed = parse_guard_response("```json\n" + __import__("json").dumps(response()) + "\n```")
        self.assertEqual(parsed["recommended_option"], "Choose Alpha")
        with self.assertRaises(ValueError):
            validate_guard_response(response(confidence=1.1))

    def test_exact_mapping_and_confidence_threshold(self):
        approved, reasons = approval_reasons(
            response(), ["Choose Alpha", "Choose Beta"], "Choose Alpha"
        )
        self.assertTrue(approved)
        self.assertEqual(reasons, [])

        approved, reasons = approval_reasons(
            response(confidence=APPROVAL_CONFIDENCE - 0.01),
            ["Choose Alpha", "Choose Beta"],
            "Choose Alpha",
        )
        self.assertFalse(approved)
        self.assertIn("confidence_below_threshold", reasons)

        approved, reasons = approval_reasons(
            response(recommended_option="choose alpha"),
            ["Choose Alpha", "Choose Beta"],
            "Choose Alpha",
        )
        self.assertFalse(approved)
        self.assertIn("recommendation_not_visible_exact_option", reasons)

    def test_hidden_input_fields_are_rejected(self):
        assert_guard_input_has_no_hidden_fields(
            {
                "phase": "primary_select",
                "visible_options": ["A", "B"],
                "proposed_option": "A",
            }
        )
        with self.assertRaises(ValueError):
            assert_guard_input_has_no_hidden_fields({"ground_truth": "A"})

    def test_message_contains_only_visible_contract(self):
        messages = build_guard_messages(
            phase="pre_submit",
            visible_page_text="Chart label 10",
            visible_options=["Choose Alpha", "Choose Beta"],
            proposed_option="Choose Alpha",
            screenshot_bytes=b"png",
        )
        serialized = str(messages)
        self.assertIn("visible_page_text", serialized)
        self.assertNotIn("ground_truth", serialized)
        self.assertNotIn("misleader_type", serialized)

    def test_one_block_then_unresolved_allow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = FakeStateGuard(
                run_dir=Path(temp_dir),
                repo_root=REPO_ROOT,
                model="gpt-5.4",
                max_calls=0,
            )
            guard.latest_response = response(
                recommended_option="Choose Beta",
                proposed_option_supported=False,
                verdict="reinspect",
                confidence=0.6,
            )
            allowed_first, feedback = asyncio.run(
                guard.before_primary_selection(object(), "Choose Alpha")
            )
            allowed_second, _ = asyncio.run(
                guard.before_primary_selection(object(), "Choose Alpha")
            )
            self.assertFalse(allowed_first)
            self.assertIsNotNone(feedback)
            self.assertTrue(allowed_second)
            self.assertEqual(guard.block_count, 1)
            self.assertEqual(guard.unresolved_count, 1)
            self.assertEqual(guard.final_state, "unresolved")

    def test_guard_error_fails_open(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = FakeStateGuard(
                run_dir=Path(temp_dir),
                repo_root=REPO_ROOT,
                model="gpt-5.4",
                max_calls=0,
            )
            allowed, feedback = asyncio.run(guard.before_submit(object(), "Choose Alpha"))
            self.assertTrue(allowed)
            self.assertIsNone(feedback)
            self.assertTrue(guard.has_guard_error)
            self.assertEqual(guard.final_state, "guard_error")


if __name__ == "__main__":
    unittest.main()
