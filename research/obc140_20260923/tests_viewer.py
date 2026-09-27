"""Offline fidelity and escaping tests; no browser, API, or network is required."""

import base64
import copy
import hashlib
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

import render_viewer


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=")


class InspectHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.payload = ""
        self.in_payload = False
        self.scripts = []
        self.meta = {}
        self.external_resources = []
        self.handlers = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            self.in_payload = attrs.get("id") == "review-data"
        if tag == "meta" and "name" in attrs:
            self.meta[attrs["name"]] = attrs.get("content")
        if tag in ("script", "img", "link", "iframe"):
            for key in ("src", "href"):
                if attrs.get(key, "").startswith(("http:", "https:", "//")):
                    self.external_resources.append(attrs[key])
        self.handlers.extend(key for key in attrs if key.startswith("on"))

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_payload = False

    def handle_data(self, data):
        if self.in_payload:
            self.payload += data


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = self.root / "original.png"
        self.image.write_bytes(PNG)
        self.task = {
            "task_slug": "public_001", "domain": "public", "chart_file": str(self.image),
            "public_task": {"page_title": "A chart", "user_goal": "Choose one.",
                            "option_labels": ["A", "B"]},
            "status": {"proposal": "not_run", "generation": "blocked",
                       "verification": "not_run", "translation": "not_run"},
            "proposal": None, "generated": None, "normalized": None,
            "verification": None, "rule_state": [], "translations": {"items": {}},
            "translation_items": [{"key": "public_task.user_goal", "text": "Choose one."}],
            "error": None, "offline_metadata": {"audited_mechanism": "unknown"},
            "provenance": {"source": "fixture"},
        }
        self.data = {"schema_version": render_viewer.SCHEMA_VERSION, "title": "OBC 审阅",
                     "generated_at": "2026-09-23T00:00:00Z",
                     "summary": {"total_tasks": 1, "generated": 0, "verified": 0,
                                 "translated": 0, "blocked_reason": "No API record"},
                     "tasks": [self.task]}

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, data=None, filename="review_data.json"):
        source = self.root / filename
        source.write_text(json.dumps(data or self.data, ensure_ascii=False), encoding="utf-8")
        rendered, provenance = render_viewer.build_html(source, rendered_at="2026-09-23T01:00:00Z")
        parser = InspectHTML()
        parser.feed(rendered)
        payload = json.loads(parser.payload)
        return rendered, provenance, parser, payload, source

    def test_full_source_fidelity_missing_stages_and_no_fabrication(self):
        output, meta, parser, payload, source = self.build()
        self.assertEqual(payload["catalog"], self.data)
        self.assertIsNone(payload["catalog"]["tasks"][0]["generated"])
        self.assertEqual(payload["catalog"]["tasks"][0]["translations"]["items"], {})
        self.assertIn("尚未翻译", output)
        self.assertIn("尚无生成解释链", output)
        self.assertEqual(meta["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(parser.meta["source-sha256"], meta["source_sha256"])
        self.assertEqual(parser.meta["source-path"], str(source.resolve()))
        self.assertEqual(parser.meta["generated-at"], "2026-09-23T01:00:00Z")

    def test_original_image_bytes_and_hash(self):
        _, _, _, payload, _ = self.build()
        asset = payload["assets"]["public_001"]
        self.assertEqual(base64.b64decode(asset["data_uri"].split(",", 1)[1]), PNG)
        self.assertEqual(asset["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual((asset["width"], asset["height"]), (1, 1))

    def test_hostile_text_stays_inert_and_roundtrips(self):
        attack = '</script><script>alert("x")</script><img src=x onerror=alert(1)> & \u2028 @@SOURCE_PATH@@'
        self.task["public_task"]["user_goal"] = attack
        self.task["translations"]["items"]["public_task.user_goal"] = attack
        self.data["title"] = attack
        output, _, parser, payload, _ = self.build(filename="source & quoted.json")
        self.assertEqual(payload["catalog"], self.data)
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(parser.handlers, [])
        self.assertEqual(parser.external_resources, [])
        self.assertNotIn(attack, output)
        self.assertIn("\\u003c/script\\u003e", parser.payload)

    def test_all_140_tasks_survive_even_when_blocked(self):
        self.data["tasks"] = [dict(copy.deepcopy(self.task), task_slug="task_%03d" % index)
                              for index in range(140)]
        self.data["summary"]["total_tasks"] = 140
        _, meta, _, payload, _ = self.build()
        self.assertEqual(meta["task_count"], 140)
        self.assertEqual(len(payload["catalog"]["tasks"]), 140)
        self.assertEqual(len(payload["assets"]), 140)
        self.assertTrue(all(t["generated"] is None for t in payload["catalog"]["tasks"]))

    def test_duplicate_rules_same_answer_and_extra_fields_preserved(self):
        candidate = {"rules": [{"id": "r1", "text": "Rule one", "conditions": ["visible"]},
                               {"id": "r1", "text": "Duplicate identifier"}],
                     "chains": [{"observations": [{"ref": "chart_1", "location": "axis", "content": "tick"}],
                                 "rule_id": "r1", "option_label": "A", "claim": "First", "extra": "kept"},
                                {"observations": [], "rule_id": "r1", "option_label": "A", "claim": "Second"}]}
        self.task["generated"] = candidate
        self.task["normalized"] = {"rules": [], "chains": []}
        self.task["verification_raw"] = {"unknown": "failed validation"}
        _, _, _, payload, _ = self.build()
        self.assertEqual(payload["catalog"]["tasks"][0], self.task)
        self.assertEqual(len(payload["catalog"]["tasks"][0]["generated"]["chains"]), 2)

    def test_missing_and_unsafe_images_are_explicit(self):
        self.task["chart_file"] = str(self.root / "missing.png")
        _, meta, _, payload, _ = self.build()
        self.assertIsNone(payload["assets"]["public_001"]["data_uri"])
        self.assertEqual(meta["chart_warnings"][0]["error_class"], "FileNotFoundError")
        svg = self.root / "not-raster.svg"
        svg.write_text('<svg onload="alert(1)"></svg>', encoding="utf-8")
        self.task["chart_file"] = str(svg)
        _, meta, _, _, _ = self.build()
        self.assertEqual(meta["chart_warnings"][0]["error_class"], "ValueError")
        for remote in ("https://example.invalid/chart.png", "//example.invalid/chart.png", "\\\\host\\chart.png"):
            self.task["chart_file"] = remote
            _, meta, _, payload, _ = self.build()
            self.assertEqual(meta["chart_warnings"][0]["error_class"], "ValueError")
            self.assertIsNone(payload["assets"]["public_001"]["data_uri"])

    def test_invalid_catalog_fails_clearly(self):
        self.data["tasks"].append(copy.deepcopy(self.task))
        with self.assertRaisesRegex(ValueError, "unique"):
            self.build()
        with self.assertRaisesRegex(ValueError, "schema_version"):
            render_viewer.validate_catalog({"schema_version": "wrong", "tasks": []})

    def test_offline_template_avoids_html_execution_sinks(self):
        output, _, parser, _, _ = self.build()
        self.assertNotIn("innerHTML", output)
        self.assertNotIn("outerHTML", output)
        self.assertNotIn("eval(", output)
        self.assertNotIn("fetch(", output)
        self.assertNotIn("XMLHttpRequest", output)
        self.assertEqual(parser.external_resources, [])
        self.assertEqual(parser.handlers, [])
        self.assertIn("connect-src 'none'", output)

    def test_render_never_overwrites_source(self):
        _, _, _, _, source = self.build()
        original = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            render_viewer.render(source, source)
        self.assertEqual(source.read_bytes(), original)
        destination = self.root / "result.html"
        meta = render_viewer.render(source, destination)
        self.assertTrue(destination.is_file())
        self.assertEqual(meta["task_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
