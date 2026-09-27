"""Offline integrity, full-coverage, and public-boundary checks for original140."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from prepare_catalog import (
    DEFAULT_SOURCE, DOMAINS, PUBLIC_KEYS, companion_audit, digest, load_sources,
    prepare_catalog, project_public, read_json,
)


def fingerprint_tree(directory):
    return {str(path.relative_to(directory)): digest(path.read_bytes())
            for path in directory.rglob("*") if path.is_file()}


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_before = fingerprint_tree(DEFAULT_SOURCE)
        cls.temp = tempfile.TemporaryDirectory(prefix="obc140_catalog_tests_")
        cls.output = Path(cls.temp.name)
        cls.catalog = prepare_catalog(DEFAULT_SOURCE, cls.output)
        cls.rows, cls.source_hashes = load_sources(DEFAULT_SOURCE)
        cls.by_slug = {row["raw"]["task_slug"]: row for row in cls.rows}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_140_official_rows_in_four_domains_and_fixed_order(self):
        self.assertEqual(self.catalog["condition"], "official140")
        self.assertEqual(self.catalog["schema_version"], "obc140_v1")
        self.assertEqual(self.catalog["base_task_count"], 140)
        tasks = self.catalog["tasks"]
        self.assertEqual(len(tasks), 140)
        self.assertEqual(dict(Counter(task["domain"] for task in tasks)), DOMAINS)
        self.assertEqual([task["task_slug"] for task in tasks], sorted(self.by_slug))
        self.assertEqual([task["alias"] for task in tasks], ["task_%03d" % i for i in range(1, 141)])
        for task in tasks:
            self.assertEqual(set(task), {"task_slug", "domain", "alias", "chart_file", "public_file", "offline_file"})
            self.assertNotIn("clean140", json.dumps(task))

    def test_public_allowlist_for_every_task(self):
        forbidden = {"action_id", "expected_action_id", "misleading_action_ids", "ground_truth",
                     "misleading_context", "rationale", "correct_value", "correct_action_id",
                     "role", "scoring_outcome", "csv_path", "html_path", "misleader_type"}
        for task in self.catalog["tasks"]:
            with self.subTest(task=task["task_slug"]):
                raw = self.by_slug[task["task_slug"]]["raw"]
                public = read_json(self.output / task["public_file"])
                self.assertEqual(set(public), PUBLIC_KEYS)
                self.assertEqual(public, project_public(raw, task["alias"]))
                self.assertEqual(public["user_goal"], raw["workflow_instruction"])
                self.assertEqual(public["option_labels"], sorted(str(item["label"]) for item in raw["action_space"]))
                serialized = json.dumps(public)
                for option in raw["action_space"]:
                    self.assertNotIn(option["action_id"], serialized)
                for field in public["companion_fields"]:
                    self.assertFalse(set(field) & forbidden)
                    self.assertEqual(set(field), {"field", "label", "type", "required"} |
                                     ({"value"} if field["type"] == "readonly" else set()))
                    self.assertNotEqual(field["type"], "hidden")

    def test_all_original_chart_bytes_and_raw_rows_preserved(self):
        for task in self.catalog["tasks"]:
            with self.subTest(task=task["task_slug"]):
                source = self.by_slug[task["task_slug"]]
                chart_bytes = (self.output / task["chart_file"]).read_bytes()
                self.assertEqual(chart_bytes, source["chart"].read_bytes())
                self.assertEqual(digest(chart_bytes), source["entry"]["assets"]["figure_path"]["sha256"])
                offline = read_json(self.output / task["offline_file"])
                self.assertEqual(offline["raw"], source["raw"])
                self.assertEqual(offline["original_mechanism"], source["entry"]["original_mechanism"])
                self.assertEqual(offline["audited_mechanism"], source["entry"]["audited_mechanism"])
                self.assertEqual(offline["provenance"]["chart_sha256"], digest(chart_bytes))

    def test_companion_audit_and_no_select_answers_or_invented_options(self):
        audit = read_json(self.output / "preparation_audit.json")
        self.assertEqual(audit["companion_type_counts"], {
            "hidden": 163, "select": 55, "text": 30, "checkbox": 9, "readonly": 222})
        self.assertEqual(audit["readonly_count"], 222)
        self.assertEqual(audit["select_field_count"], 55)
        self.assertEqual(audit["select_task_count"], 37)
        self.assertEqual(audit["unknown_visible_types"], [])
        for task in self.catalog["tasks"]:
            public = read_json(self.output / task["public_file"])
            source = self.by_slug[task["task_slug"]]["raw"]
            fields = {item["field_id"]: item for item in source.get("companion_actions", [])}
            for item in public["companion_fields"]:
                self.assertEqual(item["type"], fields[item["field"]].get("input_type", "text"))
                if item["type"] == "readonly":
                    self.assertEqual(item["value"], fields[item["field"]]["correct_value"])
                else:
                    self.assertNotIn("value", item)
                    self.assertNotIn("options", item)

    def test_hidden_scoring_poison_does_not_change_public_projection(self):
        for row in self.rows:
            raw = row["raw"]
            poisoned = copy.deepcopy(raw)
            poisoned["expected_action_id"] = "SECRET_GOLD"
            poisoned["ground_truth"] = {"secret": "SECRET_GOLD"}
            poisoned["misleading_context"] = {"secret": "SECRET_MECHANISM"}
            for field in poisoned.get("companion_actions", []):
                field["rationale"] = "SECRET_RATIONALE"
                if field.get("input_type") != "readonly":
                    field["correct_value"] = "SECRET_COMPANION_ANSWER"
            for action in poisoned["action_space"]:
                action.update(action_id="SECRET_ACTION_ID", role="SECRET_ROLE", rationale="SECRET_RATIONALE")
            self.assertEqual(project_public(raw, "task_999"), project_public(poisoned, "task_999"))
            self.assertEqual(raw, row["raw"])

    def test_rejects_unknown_visible_type_or_unreviewed_readonly_field(self):
        row = copy.deepcopy(self.rows[0])
        row["raw"]["companion_actions"] = [{"field_id": "answer", "input_type": "radio"}]
        with self.assertRaisesRegex(ValueError, "Unsupported companion type"):
            project_public(row["raw"], "task_999")
        with self.assertRaisesRegex(ValueError, "Unsupported companion type"):
            companion_audit([row])
        row["raw"]["companion_actions"] = [{"field_id": "answer", "input_type": "readonly", "correct_value": "gold"}]
        with self.assertRaisesRegex(ValueError, "Unreviewed readonly"):
            companion_audit([row])

    def test_idempotent_preparation_does_not_rewrite_any_prepared_file(self):
        before = {str(path): (path.stat().st_mtime_ns, digest(path.read_bytes()))
                  for path in self.output.rglob("*") if path.is_file()}
        self.assertEqual(prepare_catalog(DEFAULT_SOURCE, self.output), self.catalog)
        after = {str(path): (path.stat().st_mtime_ns, digest(path.read_bytes()))
                 for path in self.output.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_conflicting_prepared_data_is_never_overwritten(self):
        task = self.catalog["tasks"][0]
        for relative in (task["public_file"], task["chart_file"], task["offline_file"],
                         "catalog.json", "preparation_audit.json"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory(prefix="obc140_conflict_") as folder:
                destination = Path(folder)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"preexisting user data")
                before = fingerprint_tree(destination)
                with self.assertRaisesRegex(ValueError, "Refusing to change"):
                    prepare_catalog(DEFAULT_SOURCE, destination)
                self.assertEqual(fingerprint_tree(destination), before)

    def test_original_snapshot_unmodified_and_zero_api_calls(self):
        self.assertEqual(fingerprint_tree(DEFAULT_SOURCE), self.source_before)
        for source, expected in self.source_hashes.items():
            self.assertEqual(digest(Path(source).read_bytes()), expected)
        audit = read_json(self.output / "preparation_audit.json")
        self.assertEqual(audit["api_calls_by_preparation"], 0)
        self.assertFalse(audit["originals_modified"])
        self.assertFalse(audit["gold_modified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
