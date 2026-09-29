from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from ..build_targeted_recovery_cases import (
    build_targeted_recovery_cases,
    main,
    model_visible_projection,
    model_visible_review_projection,
    role_blind_display_order,
)
from ..formal_path_policy import REPO_ROOT
from ..run_formal_task import load_task_set_entries
from ..targeted_recovery import F2_AUDITED_VALUES, TargetedRecoveryRegistry


class TargetedRecoveryCaseBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entries = load_task_set_entries("smoke17")
        cls.cases = build_targeted_recovery_cases(cls.entries)
        cls.strict_cases = build_targeted_recovery_cases(
            load_task_set_entries("strict_review94")
        )

    def test_smoke17_builds_one_paired_case_per_entry(self) -> None:
        self.assertEqual(len(self.cases), 17)
        self.assertEqual(
            [case["pair_group_id"] for case in self.cases],
            [entry["pair_group_id"] for entry in self.entries],
        )
        for case in self.cases:
            self.assertEqual(set(case["arms"]), {"official", "clean"})
            for arm in ("official", "clean"):
                chart_path = REPO_ROOT / case["arms"][arm]["chart_path"]
                self.assertTrue(chart_path.is_file(), chart_path)

    def test_env008_contains_runner_facts_but_visible_cards_hide_roles(self) -> None:
        case = deepcopy(
            next(case for case in self.cases if case["slug"] == "env008")
        )
        runner = case["runner_only"]
        self.assertEqual(runner["ground_truth"]["ground_truth_entity"], "Solar")
        self.assertEqual(
            runner["misleading_action_ids"],
            ["misleading_route_wind_for_priority_contribution_review"],
        )
        self.assertEqual(
            set(case["model_visible_shared"]["action_cards"][0]),
            {"choice_token", "label"},
        )
        self.assertNotIn("ground_truth", case["model_visible_shared"])
        self.assertNotIn("role", case["model_visible_shared"])
        visible_payload = json.dumps(case["model_visible_shared"])
        for action_id in runner["display_order"]:
            self.assertNotIn(action_id, visible_payload)
        self.assertEqual(
            set(runner["choice_token_to_action_id"]),
            {"choice_0", "choice_1", "choice_2"},
        )

    def test_source_index_zero_shortcut_is_counterbalanced(self) -> None:
        source_positions = [
            case["runner_only"]["source_expected_action_index"]
            for case in self.cases
        ]
        self.assertEqual(set(source_positions), {0})
        display_positions = [
            case["runner_only"]["display_expected_action_index"]
            for case in self.cases
        ]
        counts = Counter(display_positions)
        self.assertEqual(set(counts), {0, 1, 2})
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_strict94_shortcut_is_also_counterbalanced(self) -> None:
        self.assertEqual(len(self.strict_cases), 94)
        self.assertEqual(
            {
                case["runner_only"]["source_expected_action_index"]
                for case in self.strict_cases
            },
            {0},
        )
        counts = Counter(
            case["runner_only"]["display_expected_action_index"]
            for case in self.strict_cases
        )
        self.assertEqual(set(counts), {0, 1, 2})
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_ordering_is_role_blind_deterministic_and_pair_shared(self) -> None:
        cards = [
            {"action_id": "source-0", "label": "A"},
            {"action_id": "source-1", "label": "B"},
            {"action_id": "source-2", "label": "C"},
        ]
        self.assertEqual(
            role_blind_display_order(cards, 1),
            [cards[1], cards[2], cards[0]],
        )
        self.assertEqual(
            build_targeted_recovery_cases(self.entries), self.cases
        )
        for case in self.cases:
            tokens = [
                card["choice_token"]
                for card in case["model_visible_shared"]["action_cards"]
            ]
            mapping = case["runner_only"]["choice_token_to_action_id"]
            self.assertEqual(
                [mapping[token] for token in tokens],
                case["runner_only"]["display_order"],
            )

    def test_layout_is_stable_across_task_sets(self) -> None:
        strict_by_pair = {
            case["pair_group_id"]: case for case in self.strict_cases
        }
        for smoke_case in self.cases:
            strict_case = strict_by_pair.get(smoke_case["pair_group_id"])
            if strict_case is None:
                continue
            self.assertEqual(
                smoke_case["layout_ordinal"], strict_case["layout_ordinal"]
            )
            self.assertEqual(
                smoke_case["runner_only"]["display_order"],
                strict_case["runner_only"]["display_order"],
            )

    def test_allowlist_projection_excludes_runner_and_source_secrets(self) -> None:
        case = deepcopy(
            next(case for case in self.cases if case["slug"] == "env008")
        )
        case["runner_only"]["projection_canary"] = "DO_NOT_RENDER_CANARY"
        projected = model_visible_projection(case, "official")
        self.assertEqual(
            set(projected), {"workflow_instruction", "chart_path", "action_cards"}
        )
        payload = json.dumps(projected)
        self.assertNotIn("DO_NOT_RENDER_CANARY", payload)
        self.assertNotIn("runner_only", payload)
        self.assertNotIn("source_references", payload)
        for action_id in case["runner_only"]["display_order"]:
            self.assertNotIn(action_id, payload)
        self.assertNotIn("ground_truth", payload)
        clean = model_visible_projection(case, "clean")
        self.assertEqual(projected["action_cards"], clean["action_cards"])
        self.assertNotEqual(projected["chart_path"], clean["chart_path"])

    def test_f2_review_projection_resolves_only_visible_approved_payload(self) -> None:
        case = deepcopy(
            next(case for case in self.cases if case["slug"] == "env008")
        )
        source_refs = [
            {
                "arm": arm,
                "artifact_path": case["source_references"][arm]["path"],
                "record_locator": f"line:{case['source_references'][arm]['line']}",
            }
            for arm in ("official", "clean")
        ]
        evidence_record_id = "evidence:env008:f2:v1"
        registry = TargetedRecoveryRegistry(
            repository_root=REPO_ROOT,
            cases=[case],
            conditions=[
                {
                    "condition_id": "candidate",
                    "checkpoint_id": "test-checkpoint",
                    "checkpoint_stage": "sft",
                    "reflection_training_status": "gui_reflection_sft",
                    "history_mode": "native4",
                    "workflow_mode": "feedback_retry",
                    "renderer_build_id": "test-renderer-v1",
                    "viewport_width": 1,
                    "viewport_height": 1,
                    "ui_variant": "compact_recovery",
                }
            ],
            approved_evidence_records=[
                {
                    "record_id": evidence_record_id,
                    "pair_group_id": case["pair_group_id"],
                    "evidence_level": F2_AUDITED_VALUES,
                    "source_refs": source_refs,
                    "review_status": "approved",
                    "reviewed_by": "reviewer_a",
                    "reviewed_at": "2026-08-30",
                    "model_visible_payload": {
                        "heading": "Audited chart values",
                        "facts": [
                            {
                                "subject": "Solar",
                                "relation": "value",
                                "object": "8",
                            }
                        ],
                    },
                }
            ],
        )
        projected = model_visible_review_projection(
            case,
            "official",
            evidence_level=F2_AUDITED_VALUES,
            evidence_record_id=evidence_record_id,
            registry=registry,
        )

        payload = json.dumps(projected)
        self.assertEqual(projected["review"]["evidence"]["facts"][0]["object"], "8")
        self.assertNotIn(evidence_record_id, payload)
        self.assertNotIn("reviewed_by", payload)
        self.assertNotIn("source_refs", payload)
        self.assertNotIn("expected_action_id", payload)

    def test_cli_emits_parseable_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "cases.jsonl"
            self.assertEqual(
                main(["--task-set", "smoke17", "--output", str(output)]), 0
            )
            rows = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(len(rows), 17)
        self.assertEqual(rows[0]["record_type"], "targeted_recovery_case")


if __name__ == "__main__":
    unittest.main()
