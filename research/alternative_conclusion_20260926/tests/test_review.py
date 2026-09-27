"""Synthetic file fixtures only; no actual API, browser, or scoring execution."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alternative_review", ROOT / "build_review.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXZkAAAAASUVORK5CYII=")


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alternative-review-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.output = self.root / "review"
        self.write("summary.json", {"status": "finished"})
        self.write("config.json", {"model": "mock-model"})
        self.write("ledger.json", {"request_attempts": 1, "browser_operations": 2})

    def write(self, path, data):
        path = self.run / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def image(self, path):
        path = self.run / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)

    def test_standalone_and_missing_status_explicit(self):
        path = review.build(self.run, self.output)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("<script", text.lower())
        self.assertNotIn('src="http', text)
        self.assertIn("未运行／没有结构接纳的核验结果", text)
        self.assertIn("1 个已知开发例", text)
        self.assertIn("并非历史 v3", text)
        self.assertIn("不是独立模型／人工裁决", review.verification_html({"checks": [{"chain_id": "c1"}]}))
        self.assertTrue((self.output / "RESULTS_FULL.json").exists())
        self.assertTrue((self.output / "PROVENANCE.json").exists())

    def test_preserves_original_artifacts(self):
        before = {path.relative_to(self.run): path.read_bytes() for path in self.run.rglob("*") if path.is_file()}
        review.build(self.run, self.output)
        after = {path.relative_to(self.run): path.read_bytes() for path in self.run.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        with self.assertRaises(FileExistsError):
            review.build(self.run, self.output)
        with self.assertRaises(ValueError):
            review.build(self.run, self.run / "inside")

    def test_model_text_and_notes_escaped(self):
        evil = '<script>alert("test")</script><img src=x onerror=alert(1)>'
        chain = {"id": evil, "O": [{"location": evil, "content": evil}],
                 "B": {"rule": evil, "conditions": [evil]}, "C": {"claim": evil, "option_label": evil}}
        self.write("official140/result.json", {"initial": {"chains": [chain], "notes": evil}})
        notes = self.root / "notes.json"
        notes.write_text(json.dumps({"arms": {"official140": {"overview": evil}}}), encoding="utf-8")
        text = review.build(self.run, self.output, notes).read_text(encoding="utf-8")
        self.assertNotIn(evil, text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("Codex 离线翻译／分析", text)

    def test_image_deduplication_request_reference_and_full_bytes(self):
        self.image("official140/prefix/state_001.png")
        self.image("official140/old_questions/state_001.png")
        self.write("official140/prefix/actor_00/request.json", {"messages": [{"content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG).decode()}}]}]})
        digest = hashlib.sha256(PNG).hexdigest()
        self.write("official140/prefix/actor_00/image_identity.json", {"sha256": digest})
        self.write("official140/prefix/actor_00/accepted.json", {"action": "finish"})
        text = review.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertEqual(text.count('src="data:image/png;base64,'), 1)
        self.assertIn("embedded-image-sha256:" + digest, text)
        self.assertIn('href="#image-' + digest + '"', text)
        data = json.loads((self.output / "RESULTS_FULL.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["images"]), 1)
        self.assertEqual(data["images"][digest]["bytes"], len(PNG))
        self.assertNotIn("data:image/png;base64,", json.dumps(data))

    def test_invalid_json_raw_retained(self):
        path = self.run / "official140/shared_initial/response_01.json"
        path.parent.mkdir(parents=True)
        path.write_text("{malformed <script>}", encoding="utf-8")
        text = review.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("invalid_json", text)
        self.assertIn("{malformed &lt;script&gt;}", text)
        self.assertIn("没有 accepted.json", text)

    def test_reused_response_explicit_not_new_call(self):
        self.write("official140/prefix/actor_00/reused_response_origin.json",
                   {"source": "previous-infrastructure-failure/actor_00", "request_equal": True})
        self.write("official140/prefix/actor_00/accepted.json", {"action": "click_link", "text": "Open Dashboard"})
        text = review.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("复用已保存响应，非新模型调用", text)
        self.assertIn("reused_response_origin.json", text)

    def test_top_level_notes_precede_result_table_and_arm_caveat(self):
        notes = self.root / "root_notes.json"
        notes.write_text(json.dumps({"overview": "本轮并未取得预期纠错。",
                                     "assessment": ["保持失败结果，不重新挑选。"]}), encoding="utf-8")
        text = review.build(self.run, self.output, notes).read_text(encoding="utf-8")
        self.assertLess(text.index("本轮并未取得预期纠错。"), text.index("<table>"))
        self.assertIn("保持失败结果，不重新挑选。", text)
        self.assertIn("未注入请求文本；原图中的既有文字照常可见", text)
        self.assertNotIn("不是在线模型输入的提示", text)

    def test_no_supplement_and_no_submission_not_invented(self):
        result = {"status": "completed_panel", "branches": {"alternative_conclusion": {
            "status": "actor_finished_or_call_limit", "submitted": False,
            "final_selection": None, "outcome": "not_submitted",
            "stages": {"questions": {"questions": [], "summary": "Already covered."},
                       "supplement": {"new_chains": [], "question_responses": []}}}}}
        self.write("official140/result.json", result)
        self.write("official140/alternative_conclusion/supplement_skipped.json",
                   {"reason": "zero_questions", "result": {"new_chains": [], "question_responses": []}})
        text = review.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("实际返回零个问题", text)
        self.assertIn("没有生成／接纳新的完整解释链", text)
        self.assertIn("补充阶段按零问题规则跳过，未调用模型", text)
        self.assertIn("未真实提交", text)

    def test_three_dimensions_separate_and_original_claim_preserved(self):
        chain = {"id": "c1", "O": [{"location": "top", "content": "Blue mark"}],
                 "B": {"rule": "If blue means requested, choose A", "conditions": ["mapping applies"]},
                 "C": {"claim": "Choose A", "option_label": "A"}}
        result = {"initial": {"chains": [chain], "notes": "conditional"},
                  "branches": {"initial_only": {"stages": {"verification": {"checks": [{
                      "chain_id": "c1", "O_status": "supported", "B_status": "uncertain",
                      "inference": "valid", "reason": "Independent judgments", "visible_evidence": ["top"]}]}}}}}
        self.write("official140/result.json", result)
        text = review.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("Choose A", text)
        self.assertIn("给定前提下推导成立", text)
        self.assertIn("尚不能确定适用性／支持", text)


if __name__ == "__main__":
    unittest.main()
