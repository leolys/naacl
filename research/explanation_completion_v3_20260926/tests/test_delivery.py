"""Offline delivery tests: source preservation, XSS, missing stages, deduplication."""
import base64
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1] / "delivery.py"
SPEC = importlib.util.spec_from_file_location("candidate_v3_delivery", MODULE)
delivery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(delivery)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.images = []
        self.ids = []
        self.anchors = []
        self.dangerous_attrs = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if tag == "img":
            self.images.append(attrs.get("src"))
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.anchors.append(attrs.get("href"))
        self.dangerous_attrs.extend(k for k in attrs if k.lower().startswith("on"))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.history = self.root / "old_missing"
        self.image = b"\xff\xd8\xfftest-original-chart-bytes"
        self.image_sha = hashlib.sha256(self.image).hexdigest()
        self.attack = '</pre><script>alert("raw")</script><img src=x onerror=alert(1)>'
        self.dump(self.run / "summary.json", {"status": "completed", "request_attempts": 12,
            "estimated_ledger_usd": 0.5, "evidence_mode": "real_model"})
        self.dump(self.run / "budget.json", {"estimated_ledger_usd": 0.5, "actual_bill_usd": None})
        self.dump(self.run / "runtime.json", {"model": "test-model"})
        self.dump(self.run / "prompt_templates.json", {"generation": self.attack})
        for cid in delivery.CASE_IDS:
            self.make_case(cid)

    def tearDown(self):
        self.temp.cleanup()

    def dump(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def make_case(self, cid):
        folder = self.run / "cases" / cid
        rule = {"id": "r1", "text": "If printed numbers encode value, choose A.",
                "conditions": "Printed numbers encode value."}
        chain = {"chain_id": "base_c1", "observations": [{"ref": "chart_1", "location": "label",
                 "content": self.attack}], "rule_id": "r1", "claim": "Choose A.", "option_label": "A"}
        initial = {"rules": [rule], "chains": [chain], "unresolved_questions": [
            {"id": "u1", "question": "Which encoding?", "reason": "Initially unclear."}]}
        check = {"target_id": "base_c1", "O": {"status": "supported", "reason": "Visible."},
                 "B_applicability": {"status": "undetermined", "reason": "Missing condition."},
                 "conditional_inference": {"status": "valid", "reason": "Follows conditionally.",
                                           "premise_ids": ["chain:base_c1"], "missing_premises": []}}
        state = {"rules": [{"rule_id": "r1", "version": 1, "rule": rule, "status": "pending",
                            "history": [{"event": "candidate_recorded"}]}],
                 "unresolved_questions": initial["unresolved_questions"], "chains": [chain]}
        result = {"task_id": cid, "status": "completed", "stages": {
            stage: {"status": "completed"} for stage in delivery.STAGES}, "generation": initial,
            "initial_arguments": initial, "questions": {"questions": [{"id": "q1", "focus": "coverage",
                "question": "Anything missing?", "target_chain_ids": ["base_c1"]}]},
            "supplement": {"new_rules": [], "new_chains": [], "refinements": [],
                "question_responses": [{"question_id": "q1", "outcome": "unresolved", "reason": self.attack}]},
            "combined": initial, "verification": {"chain_checks": [check], "refinement_checks": []},
            "rule_state": state, "failure": None, "request_attempts": 4, "estimated_ledger_usd": 0.1}
        self.dump(folder / "inputs.json", {"task": {"page_title": cid, "user_goal": self.attack,
                  "chart_reference": "Full image.", "option_labels": ["A", "B"]},
                  "chart_ref": cid + ":" + self.image_sha, "decision_reference": {"metric": "value"}})
        self.dump(folder / "initial_set.json", initial)
        self.dump(folder / "combined_arguments.json", initial)
        self.dump(folder / "result.json", result)
        self.dump(folder / "rule_state.json", state)
        (folder / "chart.jpeg").write_bytes(self.image)
        for stage in delivery.STAGES:
            self.dump(folder / stage / "raw.json", {"model_text": self.attack, "whole": "kept"})
            self.dump(folder / stage / "input_context.json", {"stage": stage})
            self.dump(folder / stage / "accepted.json", {"valid": True})
            self.dump(folder / stage / "round_001" / "request.json", {
                "input": [{"type": "input_image", "image_url": "data:image/jpeg;base64," +
                           base64.b64encode(self.image).decode()}], "prompt": self.attack})
            self.dump(folder / stage / "round_001" / "response_01.json", {"text": self.attack})
            self.dump(folder / stage / "round_001" / "attempt_01.json", {"status": "succeeded"})

    def bundle(self, **kwargs):
        return delivery.load_bundle(self.run, history_run=self.history,
                                    history_notes=self.root / "missing_notes.json", **kwargs)

    def test_text_is_escaped_and_page_has_no_active_external_dependencies(self):
        page = delivery.render_html(self.bundle())
        parsed = PageParser()
        parsed.feed(page)
        self.assertNotIn("script", parsed.tags)
        self.assertNotIn("iframe", parsed.tags)
        self.assertEqual([], parsed.dangerous_attrs)
        self.assertNotIn(self.attack, page)
        self.assertIn("&lt;script&gt;", page)
        self.assertTrue(all(src.startswith("data:image/jpeg;base64,") for src in parsed.images))
        self.assertTrue(all(ref.startswith("#") for ref in parsed.anchors))
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
        self.assertTrue(all(ref[1:] in parsed.ids for ref in parsed.anchors))

    def test_images_deduplicated_and_request_payload_provenance_preserved(self):
        bundle = self.bundle()
        self.assertEqual(1, len(bundle["images"]))
        page = delivery.render_html(bundle)
        self.assertEqual(1, page.count("data:image/jpeg;base64,"))
        portable = delivery.portable_bundle(bundle)
        self.assertNotIn("data:image/jpeg;base64,", json.dumps(portable))
        request = portable["cases"][0]["records"]["generation/round_001/request.json"]
        self.assertEqual(self.image_sha, request["input"][0]["image_url"]["_embedded_image_reference"])
        self.assertEqual(self.attack, request["prompt"])
        self.assertEqual(self.image, base64.b64decode(bundle["images"][self.image_sha]["data_base64"]))

    def test_missing_and_failed_generation_are_explicit_and_raw_is_retained(self):
        folder = self.run / "cases" / "b001"
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        result.update(status="failed_stage_no_quality_retry", initial_arguments=None, generation=None,
                      questions=None, supplement=None, verification=None, rule_state=None,
                      failure={"stage": "generation", "error": self.attack})
        result["stages"]["generation"]["status"] = "failed"
        self.dump(folder / "result.json", result)
        (folder / "initial_set.json").unlink()
        (folder / "rule_state.json").unlink()
        bundle = self.bundle()
        page = delivery.render_html(bundle)
        self.assertIn("没有通过接口校验的初始解释集合", page)
        self.assertIn("未获得有效结果", page)
        self.assertIn("generation/raw.json", page)
        self.assertIn("未通过校验的真实原文", page)
        self.assertIn("本例真实失败信息", page)
        self.assertIn("缺失文件", page)
        self.assertEqual(self.attack, bundle["cases"][0]["records"]["generation/raw.json"]["model_text"])

    def test_malformed_raw_json_stays_visible(self):
        path = self.run / "cases" / "b001" / "generation" / "raw.json"
        path.write_text(self.attack, encoding="utf-8")
        bundle = self.bundle()
        record = bundle["cases"][0]["records"]["generation/raw.json"]
        self.assertEqual(self.attack, record["_raw_file_text"])
        self.assertIn("无法解析", delivery.render_html(bundle))

    def test_refinement_support_is_not_invented_as_three_chain_dimensions(self):
        card = delivery.verification_card({"target_id": "refine_1", "support": {
            "status": "supported", "reason": "The condition note is supported.", "evidence": []}}, refinement=True)
        self.assertIn("细化内容的独立证据支持", card)
        self.assertIn("The condition note is supported.", card)
        self.assertNotIn("B_applicability", card)

    def test_three_dimensions_notes_and_historical_limits(self):
        note_path = self.root / "notes.json"
        self.dump(note_path, {"cases": {"b001": {"overview": "中文概要", "chains": {
            "base_c1": {"O": ["观察译文"], "B": "规则译文", "conditions": ["条件译文"],
                        "C": "候选译文"}}, "assessment": ["审阅备注"]}}})
        self.history = self.run
        page = delivery.render_html(self.bundle(notes_path=note_path))
        for expected in ("观察译文", "规则译文", "候选译文", "审阅备注", "B_applicability",
                         "conditional_inference", "同一模型的独立请求核验", "2026-09-25 历史结果",
                         "不是受控 A/B 实验", "初始生成时记录的未解问题", "非 API 输出", "不是独立人工确认"):
            self.assertIn(expected, page)
        self.assertEqual(1, page.count("data:image/jpeg;base64,"))

    def test_export_refuses_overwrite_and_does_not_mutate_sources(self):
        source = self.run / "cases" / "b001" / "generation" / "round_001" / "request.json"
        before = source.read_bytes()
        output = self.root / "delivery"
        result = delivery.write_delivery(self.run, output, history_run=self.history,
                                         history_notes=self.root / "missing_notes.json")
        self.assertEqual(3, len(result["files"]))
        self.assertEqual(before, source.read_bytes())
        self.assertTrue((output / "RESULTS_FULL.json").is_file())
        with self.assertRaises(FileExistsError):
            delivery.write_delivery(self.run, output)


if __name__ == "__main__":
    unittest.main()
