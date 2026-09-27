"""Offline synthetic fixtures only, not experiment evidence."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("search_review_test", ROOT / "build_search_review.py")
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXZkAAAAASUVORK5CYII=")


class SearchReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.output = self.root / "review"
        self.write("summary.json", {"status": "finished", "request_attempts": 3})
        self.write("config.json", {"model": "mock"})
        self.write("ledger.json", {"request_attempts": 3, "browser_operations": 0})

    def write(self, relative, value):
        path = self.run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_optional_phases_and_static_not_submission_failure(self):
        self.write("b002/result.json", {"mode": "static_public_task_transfer", "submitted": False,
            "branches": {"action_conclusion_only": {"status": "completed_static_only", "submitted": False,
                "stages": {"questions": {"questions": [], "summary": "covered"},
                           "supplement": {"new_chains": [], "question_responses": []}}}}})
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("不适用：静态无 Actor", text)
        self.assertIn("submitted=false 是诊断设计", text)
        self.assertIn("未运行或未提供本地工件", text)
        self.assertIn("实际返回零问，不是未调用", text)
        self.assertNotIn("<script", text.lower())

    def test_empty_hypothesis_notes_and_unaccepted_draft_retained(self):
        self.write("b002/public_context.json", {"options": ["A", "B", "C"]})
        self.write("b002/result.json", {"mode": "static_public_task_transfer", "branches": {
            "symmetric_hypotheses": {"status": "failed_no_quality_retry", "stages": {},
                "error": {"message": "wrong option"}}}})
        self.write("b002/symmetric_hypotheses/hypothesis_00/context.json", {"hypothesis_option": "A"})
        self.write("b002/symmetric_hypotheses/hypothesis_00/accepted.json", {"chains": [], "notes": "Important empty response explanation"})
        self.write("b002/symmetric_hypotheses/hypothesis_01/context.json", {"hypothesis_option": "B"})
        draft = {"chains": [{"id": "h1", "O": [], "B": {}, "C": {"claim": "Wrong A", "option_label": "A"}}], "notes": "wrong option draft"}
        self.write("b002/symmetric_hypotheses/hypothesis_01/response_01.json", {"choices": [{"message": {"content": json.dumps(draft)}}]})
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("程序模板3项；实际请求2项", text)
        self.assertIn("Important empty response explanation", text)
        self.assertIn("未被接口接纳的原始响应／草稿", text)
        self.assertIn("Wrong A", text)
        self.assertIn("未完成聚合／未记录", text)

    def test_requests_images_dedup_and_html_escape(self):
        self.write("official140/result.json", {"branches": {"action_conclusion_only": {"status": "completed"}}})
        directory = self.run / "official140"
        (directory / "source_checkpoint.png").write_bytes(PNG)
        uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        self.write("official140/action_conclusion_only/questions/request.json", {"text": "<script>alert(1)</script>", "image": uri})
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertEqual(text.count('src="data:image/png;base64,'), 1)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertIn("embedded-image-sha256:", text)
        bundle = (self.output / "RESULTS_FULL.json").read_text(encoding="utf-8")
        self.assertNotIn("data:image/png;base64,", bundle)

    def test_preserve_sources_and_reject_overwrite_or_inside_output(self):
        before = {p.relative_to(self.run): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        viewer.build(self.run, self.output)
        after = {p.relative_to(self.run): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        with self.assertRaises(FileExistsError):
            viewer.build(self.run, self.output)
        with self.assertRaises(ValueError):
            viewer.build(self.run, self.run / "new")

    def test_annotations_are_explicit_offline_not_fabricated(self):
        annotation = self.root / "annotations.json"
        annotation.write_text(json.dumps({"overview": "离线总评", "assessment": ["不代表留出成功"]}), encoding="utf-8")
        text = viewer.build(self.run, self.output, annotations=annotation).read_text(encoding="utf-8")
        self.assertIn("离线总评", text)
        self.assertIn("不代表留出成功", text)
        self.assertIn("不是独立人工确认", text)
        self.assertTrue((self.output / "PROVENANCE.json").exists())

    def test_contract_guard_before_static_call_is_not_model_failure(self):
        self.write("summary.json", {"status": "stopped", "error": {
            "type": "ValueError", "message": "Static revision must use exactly the prior public inputs"}})
        self.write("official140/result.json", {"branches": {"symmetric_hypotheses": {
            "submitted": True, "outcome": "success", "status": "completed"}}})
        (self.run / "b002").mkdir()
        phase, _ = viewer.phase_collect(self.run, "contract")
        self.assertEqual(phase["cases"]["b002"]["request_record_count"], 0)
        self.assertIn("pub013", phase["cases"])
        text = viewer.render({"contract": phase}, {}, {}, {})
        self.assertIn("模型请求前的工程守卫", text)
        self.assertIn("没有请求归档且没有结果", text)
        self.assertIn("Static revision must use exactly the prior public inputs", text)
        self.assertNotIn("未真实提交", text)

    def test_isolated_phase_distinguishes_gui_from_static_contract_continuation(self):
        self.write("official140/result.json", {"branches": {"symmetric_hypotheses": {
            "submitted": True, "outcome": "success", "status": "completed"}}})
        self.write("b002/result.json", {"mode": "static_public_task_transfer", "branches": {
            "contract_hypotheses": {"submitted": False, "status": "completed_static_only"}}})
        phase, _ = viewer.phase_collect(self.run, "isolated")
        self.assertIn("第七方案", viewer.design_label("isolated", phase["cases"]["official140"]))
        self.assertIn("第六方案", viewer.design_label("isolated", phase["cases"]["b002"]))
        text = viewer.render({"isolated": phase}, {}, {}, {})
        self.assertIn("不是该去上下文方案的迁移评测", text)
        self.assertIn("静态契约版首次工程续接", text)
        self.assertIn("候选发现去执行上下文", text)
        self.assertIn("不适用：静态无 Actor", text)

    def test_initial_request_failure_without_case_result_still_exposes_raw_output(self):
        self.write("b002/shared_initial/request.json", {"text": "public task"})
        self.write("b002/shared_initial/response_01.json", {"raw_body": "INITIAL_FAILURE_RAW_SENTINEL"})
        phase, _ = viewer.phase_collect(self.run, "transfer")
        text = viewer.render({"transfer": phase}, {}, {}, {})
        self.assertIn("有请求归档但缺少完整结果", text)
        self.assertIn("INITIAL_FAILURE_RAW_SENTINEL", text)

    def test_joint_discovery_is_one_generation_not_missing_verifier_or_actor(self):
        response = {"chains": [], "notes": "JOINT_EMPTY_NOTES_SENTINEL"}
        self.write("official140/result.json", {"mode": "static_public_task_transfer", "submitted": False,
            "branches": {"joint_discovery": {"status": "completed_static_only", "submitted": False,
                "verification_status": "not_run_candidate_only_diagnostic",
                "stages": {"discovery": {"program_counterquestion": "Could another conclusion follow?", "response": response},
                           "supplement": {"new_chains": [], "source": "single_joint_discovery_not_old_supplement"}}}}})
        self.write("official140/joint_discovery/discovery/request.json", {"system": "JOINT_PROMPT_SENTINEL"})
        self.write("official140/joint_discovery/discovery/accepted.json", response)
        phase, _ = viewer.phase_collect(self.run, "joint")
        self.assertTrue(viewer.is_static(phase["cases"]["official140"]))
        text = viewer.render({"joint": phase}, {}, {}, {})
        self.assertIn("JOINT_EMPTY_NOTES_SENTINEL", text)
        self.assertIn("JOINT_PROMPT_SENTINEL", text)
        self.assertIn("没有先行问题生成调用", text)
        self.assertIn("按设计没有独立核验，不能算核验失败", text)
        self.assertIn("不代表又执行了旧补充调用", text)
        self.assertNotIn("核验完整请求与响应：未运行或请求工件缺失", text)
        self.assertIn("不适用：静态无 Actor", text)


if __name__ == "__main__":
    unittest.main()
