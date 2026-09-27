"""Small offline display tests, not evaluation of model explanations."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("conditional_viewer", Path(__file__).with_name("build_review.py"))
viewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(viewer)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4nEAAAAASUVORK5CYII=")


class ViewerTests(unittest.TestCase):
    def fixture(self, root, candidates=True):
        folder = root / "registration" / "b002"
        folder.mkdir(parents=True)
        registration = {"candidates": [{"id": "A", "candidate": {"claim": "Candidate A", "option_label": "A"}, "visual_cues": ["source cue"], "reading_to_try": "source rule", "assumptions": []}, {"id": "B", "candidate": {"claim": "Candidate B", "option_label": "B"}, "visual_cues": [], "reading_to_try": "another rule", "assumptions": []}] if candidates else []}
        result = {"variant": "registration", "case": "b002", "status": "partial", "registration": registration, "expansions": [{"index": 0, "candidate_id": "A", "status": "accepted", "data": {"O": ["NEW O"], "B": "NEW B", "C": "A"}, "empty_record": False, "action_relation": {"expected": "A", "returned": "A", "exact_match": True}, "adapted_chain": {"id": "program-id"}}] if candidates else [], "verification": None, "submitted": False}
        old = {"expansions": [{"status": "accepted", "data": {"proposal_id": "A", "outcome": "unexpanded", "chains": [], "reason": "OLD REFUSAL"}}]}
        for name, value in (("context", {"goal": "public goal"}), ("initial", {"chains": []}), ("registration", registration), ("previous_result", old), ("result", result)):
            (folder / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
        (folder / "chart.png").write_bytes(PNG)
        stage = folder / "expand_00"
        stage.mkdir()
        request = {"messages": [{"role": "system", "content": "FULL SYSTEM TEXT"}, {"role": "user", "content": [{"type": "text", "text": "FULL USER TEXT"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG).decode()}}]}]}
        (stage / "request.json").write_text(json.dumps(request), encoding="utf-8")
        return folder, result

    def test_old_new_requests_and_caveats_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            self.fixture(run)
            text = viewer.build(run, Path(tmp) / "review").read_text(encoding="utf-8")
            for phrase in ("OLD REFUSAL", "NEW O", "NEW B", "FULL SYSTEM TEXT", "FULL USER TEXT", "不得把 14 个强结构输出算作 14 条有效新链", "本轮不重跑这一步反问", "此候选尚无本轮展开记录"):
                self.assertIn(phrase, text)
            self.assertEqual(text.count('src="data:image/png;base64,'), 1)
            self.assertNotIn('href="http', text)
            self.assertNotIn('<script', text)

    def test_image_hashes_preserve_text_and_do_not_mutate(self):
        value = {"image": "data:image/png;base64," + base64.b64encode(PNG).decode(), "system": "full text"}
        changed = viewer.image_hashes(value)
        self.assertIn(viewer.sha(PNG), changed["image"])
        self.assertEqual(changed["system"], "full text")
        self.assertTrue(value["image"].startswith("data:"))

    def test_zero_source_distinct_from_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            self.fixture(run, False)
            text = viewer.build(run, Path(tmp) / "review").read_text(encoding="utf-8")
            self.assertIn("原反问返回零候选", text)
            self.assertIn("候选来源文件缺失", text)
            self.assertIn("不能记为已执行核验失败", text)

    def test_index_scoped_annotations_and_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            folder, result = self.fixture(run)
            result["expansions"].append({"index": 1, "candidate_id": "B", "status": "accepted", "data": {"O": [], "B": "", "C": ""}, "empty_record": True, "adapted_chain": None})
            (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
            annotations = {"overview": ["<script>bad</script>"], "cases": {"b002": {"variants": {"registration": {"expansions": {"0": {"O": ["第一候选观察"], "B": "第一候选条件", "C": "第一结论"}, "1": {"O": [], "B": "", "C": "", "comment": "第二候选为空"}}}}}}}
            text = viewer.build(run, Path(tmp) / "review", annotations).read_text(encoding="utf-8")
            body = text.split('id="archive"')[0]
            self.assertEqual(body.count("第一候选观察"), 1)
            self.assertEqual(body.count("第二候选为空"), 1)
            self.assertIn("&lt;script&gt;", body)
            self.assertNotIn("<script>", body)
            self.assertEqual(viewer.record_counts(result), {"expansion_records": 2, "empty_records": 1, "adapted_records": 1})

    def test_image_shared_by_hash_and_difference_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            self.fixture(run)
            twin = run / "coverage" / "b002"
            twin.mkdir(parents=True)
            (twin / "chart.png").write_bytes(PNG)
            text = viewer.build(run, Path(tmp) / "review").read_text(encoding="utf-8")
            self.assertEqual(text.count('src="data:image/png;base64,'), 1)
            (twin / "chart.png").write_bytes(PNG + b"different")
            text = viewer.build(run, Path(tmp) / "review2").read_text(encoding="utf-8")
            self.assertIn("两个来源的图像 hash 不同", text)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            self.fixture(run)
            viewer.build(run, Path(tmp) / "review")
            with self.assertRaises(FileExistsError):
                viewer.build(run, Path(tmp) / "review")

    def test_verification_completion_unknown_and_unstarted_are_distinct(self):
        completed = {"status": "completed_candidate_diagnostic", "verification": {"checks": []}}
        stopped = {"status": "stopped_global_budget_or_transport", "verification": None}
        pending = {"status": "expanded_pending_verify", "verification": None}
        sent = {"verify/request.json": {"messages": []}}
        self.assertEqual(viewer.verification_state(completed, sent)[0], "已完成核验")
        self.assertEqual(viewer.verification_state(stopped, sent)[0], "已发送，结果未知")
        self.assertEqual(viewer.verification_state(pending, {})[0], "尚未发送核验")
        self.assertIn("不能认定服务端已完成或未完成", viewer.verification_state(stopped, sent)[1])
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            folder, result = self.fixture(run)
            result.update(stopped)
            (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
            (folder / "verify").mkdir()
            (folder / "verify" / "request.json").write_text(json.dumps(sent["verify/request.json"]), encoding="utf-8")
            text = viewer.build(run, Path(tmp) / "review").read_text(encoding="utf-8")
            self.assertGreaterEqual(text.count("已发送，结果未知"), 2)
            self.assertIn("因传输或全局限制停止", text)
            self.assertIn("stopped_global_budget_or_transport", text)


if __name__ == "__main__":
    unittest.main()
