from __future__ import annotations

import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from web_agent_benchmark.evaluation.gui_reflection_baseline.build_task_sets import (
    DEFAULT_DATASET_ROOT,
    PAIR_COMPARISON_FIELDS,
    READINESS_EXCLUSIONS,
    REVIEW_ISSUE_EXCLUSIONS,
    REPO_ROOT,
    build_task_sets,
    write_task_sets,
)


class TaskSetBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = build_task_sets(DEFAULT_DATASET_ROOT, REPO_ROOT)

    def test_expected_population_counts(self) -> None:
        self.assertEqual(len(self.result.full140), 140)
        self.assertEqual(len(self.result.chart_only114), 114)
        self.assertEqual(len(self.result.readiness95), 95)
        self.assertEqual(len(self.result.strict_review94), 94)
        self.assertEqual(len(self.result.smoke17), 17)
        self.assertEqual(
            self.result.summary["counts"],
            {
                "full140": 140,
                "chart_only114": 114,
                "readiness95": 95,
                "strict_review94": 94,
                "smoke17": 17,
            },
        )

    def test_chart_only_exclusions_are_derived_field_mismatches(self) -> None:
        excluded = {
            entry["slug"]
            for entry in self.result.full140
            if not entry["selected"]["chart_only114"]
        }
        expected = {
            *(f"b{number:03d}" for number in range(17, 35)),
            *(f"health{number:03d}" for number in range(6, 14)),
        }
        self.assertEqual(excluded, expected)

        for entry in self.result.full140:
            differences = entry["paired_non_chart_differences"]
            self.assertEqual(
                entry["selected"]["chart_only114"], not differences
            )
            self.assertTrue(set(differences).issubset(PAIR_COMPARISON_FIELDS))
            if entry["slug"] in expected:
                self.assertTrue(differences)
                self.assertEqual(
                    entry["exclusion_reasons"]["chart_only114"][0]["code"],
                    "paired_non_chart_field_mismatch",
                )

    def test_readiness95_excludes_19_flagged_chart_only_pairs(self) -> None:
        excluded = [
            entry
            for entry in self.result.chart_only114
            if not entry["selected"]["readiness95"]
        ]
        self.assertEqual(len(excluded), 19)
        for entry in excluded:
            statuses = {entry["official_readiness"], entry["clean_readiness"]}
            self.assertTrue(statuses.intersection(READINESS_EXCLUSIONS))
            issues = set(entry["official_review_issues"]) | set(
                entry["clean_review_issues"]
            )
            self.assertIn("gt_uncertain", issues)
            self.assertEqual(
                entry["exclusion_reasons"]["readiness95"][0]["code"],
                "excluded_task_readiness",
            )

    def test_strict_review_additionally_excludes_env032(self) -> None:
        readiness_ids = {
            entry["pair_group_id"] for entry in self.result.readiness95
        }
        strict_ids = {
            entry["pair_group_id"] for entry in self.result.strict_review94
        }
        additionally_excluded = [
            entry
            for entry in self.result.readiness95
            if entry["pair_group_id"] not in strict_ids
        ]
        self.assertEqual(readiness_ids - strict_ids, {
            "synthetic140:environment35:env032"
        })
        self.assertEqual(len(additionally_excluded), 1)
        env032 = additionally_excluded[0]
        self.assertEqual(env032["slug"], "env032")
        self.assertEqual(env032["official_readiness"], "formal_scored_task")
        self.assertEqual(env032["clean_readiness"], "formal_scored_task")
        review_issues = set(env032["official_review_issues"]) | set(
            env032["clean_review_issues"]
        )
        self.assertTrue(review_issues.intersection(REVIEW_ISSUE_EXCLUSIONS))
        self.assertTrue(env032["selected"]["smoke17"])
        self.assertEqual(
            env032["exclusion_reasons"]["strict_review94"][0]["code"],
            "excluded_review_issue",
        )
        conflicts = self.result.summary["metadata_conflicts"]
        self.assertEqual([item["slug"] for item in conflicts], ["env032"])

    def test_all_19_image_only_drafts_have_gt_uncertain_annotation(self) -> None:
        image_only = [
            entry
            for entry in self.result.chart_only114
            if "image_only_draft"
            in {entry["official_readiness"], entry["clean_readiness"]}
        ]
        self.assertEqual(len(image_only), 19)
        for entry in image_only:
            official_issues = set(entry["official_review_issues"])
            clean_issues = set(entry["clean_review_issues"])
            self.assertIn("gt_uncertain", official_issues)
            self.assertIn("gt_uncertain", clean_issues)

    def test_smoke_is_minimum_slug_per_ready_scenario_type(self) -> None:
        by_stratum: dict[tuple[str, str], list[str]] = defaultdict(list)
        for entry in self.result.readiness95:
            by_stratum[(entry["scenario"], entry["type"])].append(
                entry["slug"]
            )
        actual = {
            (entry["scenario"], entry["type"]): entry["slug"]
            for entry in self.result.smoke17
        }
        expected = {
            stratum: min(slugs) for stratum, slugs in by_stratum.items()
        }
        self.assertEqual(len(by_stratum), 17)
        self.assertEqual(actual, expected)

    def test_manifest_entries_have_paths_and_exclusion_reasons(self) -> None:
        required = {
            "scenario",
            "slug",
            "type",
            "official_path",
            "clean_path",
            "official_chart_path",
            "clean_chart_path",
            "official_review_issues",
            "clean_review_issues",
            "exclusion_reasons",
        }
        for entry in self.result.full140:
            self.assertTrue(required.issubset(entry))
            self.assertTrue((REPO_ROOT / entry["official_path"]).is_file())
            self.assertTrue((REPO_ROOT / entry["clean_path"]).is_file())
            self.assertTrue(
                (REPO_ROOT / entry["official_chart_path"]).is_file()
            )
            self.assertTrue((REPO_ROOT / entry["clean_chart_path"]).is_file())

    def test_written_outputs_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            write_task_sets(self.result, output_dir)
            expected_counts = self.result.summary["counts"]
            for name, expected_count in expected_counts.items():
                rows = [
                    json.loads(line)
                    for line in (output_dir / f"{name}.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                    if line.strip()
                ]
                self.assertEqual(len(rows), expected_count)
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["counts"], expected_counts)


if __name__ == "__main__":
    unittest.main()
