"""Small renderer regression tests. These do not validate model research claims."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("registration_review", Path(__file__).with_name("build_review.py"))
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4nEAAAAASUVORK5CYII=")


class ViewerTests(unittest.TestCase):
    def test_hash_redaction_preserves_all_text(self):
        value = {"messages": [{"role": "system", "content": "system instructions"}, {"role": "user", "content": [{"type": "text", "text": "full public evidence"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG).decode()}}]}]}
        rendered = review.redact_images(value)
        self.assertEqual(rendered["messages"][0]["content"], "system instructions")
        self.assertEqual(rendered["messages"][1]["content"][0]["text"], "full public evidence")
        self.assertIn(hashlib.sha256(PNG).hexdigest(), rendered["messages"][1]["content"][1]["image_url"]["url"])
        self.assertTrue(value["messages"][1]["content"][1]["image_url"]["url"].startswith("data:"))

    def make_fixture(self, root, registration=None):
        case = root / "registration" / "pub001_misleading"
        case.mkdir(parents=True)
        initial = {"chains": [{"id": "old", "O": [{"location": "plot", "content": "O text"}], "B": {"rule": "B text", "conditions": []}, "C": {"claim": "C text", "option_label": "Route A"}}]}
        result = {"variant": "registration", "case": "pub001_misleading", "status": "partial", "registration": registration, "expansions": [], "candidate_set": initial, "verification": None, "submitted": False}
        for name, value in (("initial", initial), ("context", {"goal": "public goal"}), ("result", result)):
            (case / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
        (case / "chart.png").write_bytes(PNG)
        stage = case / "register"
        stage.mkdir()
        (stage / "request.json").write_text(json.dumps({"messages": [{"role": "system", "content": "do not omit me"}, {"role": "user", "content": "public user text"}]}), encoding="utf-8")
        return case, result

    def test_zero_candidates_and_failed_registration_distinguished(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            self.make_fixture(root, {"candidates": []})
            output = review.build(root, Path(tmp) / "review")
            text = output.read_text(encoding="utf-8")
            self.assertIn("模型返回零候选", text)
            self.assertIn("候选登记未完成", text)
            self.assertIn("没有展开调用记录", text)
            self.assertIn("do not omit me", text)
            self.assertIn("public user text", text)
            self.assertIn("不保证其判断可靠", text)
            self.assertNotIn('<script src=', text)
            self.assertNotIn('href="http', text)

    def test_candidates_are_not_named_new_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            candidate = {"id": "r1", "candidate": {"claim": "Route A", "option_label": "Route A"}, "visual_cues": ["bar"], "reading_to_try": "height", "assumptions": []}
            self.make_fixture(root, {"candidates": [candidate, candidate]})
            output = review.build(root, Path(tmp) / "review")
            text = output.read_text(encoding="utf-8")
            self.assertEqual(text.count('登记候选 r1</h4>'), 2)
            self.assertIn("登记候选数", text)
            self.assertNotIn("新增有效解释路径数</th>", text)

    def test_html_escape_and_annotation_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            self.make_fixture(root, {"candidates": []})
            annotations = {"overview": ["<script>alert(1)</script>"], "cases": {"pub001_misleading": {"initial_chains": {"old": {"O": ["中文观察"], "B": "中文桥接", "C": "中文结论"}}}}}
            text = review.build(root, Path(tmp) / "review", annotations).read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", text)
            self.assertNotIn("<script>alert", text)
            self.assertIn("离线中文阅览注释（非模型原文）", text)
            self.assertIn("O text", text)
            self.assertIn("中文观察", text)

    def test_same_case_image_shared_and_divergence_disclosed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            self.make_fixture(root, {"candidates": []})
            twin = root / "coverage" / "pub001_misleading"
            twin.mkdir(parents=True)
            (twin / "chart.png").write_bytes(PNG)
            text = review.build(root, Path(tmp) / "review").read_text(encoding="utf-8")
            self.assertEqual(text.count('src="data:image/png;base64,'), 1)
            (twin / "chart.png").write_bytes(PNG + b"different")
            text = review.build(root, Path(tmp) / "review2").read_text(encoding="utf-8")
            self.assertIn("两个版本的图像 hash 不同", text)
            self.assertEqual(text.count('src="data:image/png;base64,'), 2)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            self.make_fixture(root, {"candidates": []})
            review.build(root, Path(tmp) / "review")
            with self.assertRaises(FileExistsError):
                review.build(root, Path(tmp) / "review")

    def test_same_chain_id_has_expansion_scoped_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            case, result = self.make_fixture(root, {"candidates": []})
            chain = {"id": "c1", "O": [], "B": {"rule": "raw rule", "conditions": []}, "C": {"claim": "raw claim", "option_label": "Route A"}}
            result["expansions"] = [{"status": "accepted", "data": {"outcome": "expanded", "chains": [chain]}} for _ in range(2)]
            (case / "result.json").write_text(json.dumps(result), encoding="utf-8")
            translations = {"expand_00/c1": {"C": "第一轮专属结论"}, "expand_01/c1": {"C": "第二轮专属结论"}, "c1": {"C": "旧版备用结论"}}
            annotations = {"cases": {"pub001_misleading": {"variants": {"registration": {"new_chains": translations}}}}}
            text = review.build(root, Path(tmp) / "review", annotations).read_text(encoding="utf-8")
            body = text.split('id="archive"')[0]
            self.assertEqual(body.count("第一轮专属结论"), 1)
            self.assertEqual(body.count("第二轮专属结论"), 1)
            self.assertNotIn("旧版备用结论", body)
            del translations["expand_01/c1"]
            text = review.build(root, Path(tmp) / "review2", annotations).read_text(encoding="utf-8")
            body = text.split('id="archive"')[0]
            self.assertIn("第一轮专属结论", body)
            self.assertIn("旧版备用结论", body)


if __name__ == "__main__":
    unittest.main()
