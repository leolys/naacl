"""Offline fixtures; no model/SSH/browser access."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("proposal_builder_test", ROOT / "builder.py")
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXZkAAAAASUVORK5CYII=")


def proposal(pid="p1"):
    return {"id": pid, "candidate": {"claim": "Choose A conditionally", "option_label": "A"},
            "visual_cues": ["located mark"], "reading_to_try": "A public reading",
            "assumptions": ["Mapping applies"]}


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.output = self.root / "review"
        self.write("summary.json", {"status": "finished", "browser_operations": 0})
        self.write("config.json", {"model": "mock"})
        self.write("ledger.json", {"request_attempts": 4, "browser_operations": 0})

    def write(self, name, data):
        path = self.run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_unexpanded_proposal_preserved_with_actual_reason(self):
        self.write("b002/result.json", {"proposals": {"proposals": [proposal()], "notes": "Real proposal notes"},
            "expansions": [{"status": "accepted", "data": {"proposal_id": "p1", "outcome": "unexpanded",
                "chains": [], "reason": "SPECIFIC_GAP"}}], "candidate_set": {"chains": [], "proposal_links": [
                    {"proposal_id": "p1", "expansion_status": "accepted", "outcome": "unexpanded", "chain_ids": []}]},
            "verification_status": "not_run_no_complete_chains"})
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("Choose A conditionally", text)
        self.assertIn("SPECIFIC_GAP", text)
        self.assertIn("模型明确返回 unexpanded", text)
        self.assertIn("没有完整链，按协议不执行核验", text)
        self.assertIn("纯候选验证，没有执行纠错", text)

    def test_interface_failure_raw_not_erased_or_counted_as_zero_proposals(self):
        self.write("b002/propose/request.json", {"text": "request"})
        self.write("b002/propose/response_01.json", {"raw": "<script>BAD_DRAFT</script>"})
        self.write("b002/result.json", {"status": "interface_failed_no_retry", "proposals": None,
                                       "error": {"message": "not JSON"}})
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("BAD_DRAFT", text)
        self.assertNotIn("<script>", text)
        self.assertIn("不能写成模型提出零条", text)

    def test_changed_candidate_retained_and_signals_not_semantic_gate(self):
        chain = {"id": "proposal_00_h1", "O": [{"location": "top", "content": "mark"}],
                 "B": {"rule": "conditional", "conditions": []}, "C": {"claim": "Choose B", "option_label": "B"}}
        self.write("pub013/result.json", {"proposals": {"proposals": [proposal()], "notes": "x"},
            "expansions": [{"status": "accepted", "data": {"outcome": "expanded", "chains": [chain], "reason": "retargeted"}}],
            "candidate_set": {"chains": [chain], "proposal_links": [{"proposal_id": "p1", "expansion_status": "accepted",
                "outcome": "expanded", "chain_ids": ["proposal_00_h1"], "same_action_label": False, "same_claim_text": False}]}})
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("Choose B", text)
        self.assertIn("same_action_label", text)
        self.assertIn("不是语义一致／忠实性的裁决", text)

    def test_zero_proposals_differ_from_missing_propose_call(self):
        self.write("pub013/result.json", {"proposals": {"proposals": [], "notes": "None apparent"}, "expansions": []})
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("模型实际返回零提案，不是未调用", text)
        self.assertIn("没有结构接纳的提案输出", text)

    def test_single_embedded_image_raw_requests_hashed_and_sources_immutable(self):
        self.write("b002/initial.json", {"chains": [], "notes": "initial"})
        (self.run / "b002/chart.png").write_bytes(PNG)
        uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        self.write("b002/propose/request.json", {"image": uri})
        self.write("b002/expand_00/request.json", {"image": uri})
        before = {p.relative_to(self.run): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertEqual(text.count('src="data:image/png;base64,'), 1)
        self.assertIn("embedded-image-sha256:", text)
        self.assertNotIn("<script", text.lower())
        after = {p.relative_to(self.run): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        with self.assertRaises(FileExistsError):
            viewer.build(self.run, self.output)

    def test_missing_expansion_is_not_interface_failure(self):
        self.write("b002/result.json", {"proposals": {"proposals": [proposal()], "notes": "x"}, "expansions": []})
        bundle, _ = viewer.collect(self.run)
        self.assertEqual(viewer.counts(bundle["cases"]["b002"])["not_recorded"], 1)
        self.assertEqual(viewer.counts(bundle["cases"]["b002"])["interface_failed"], 0)
        text = viewer.build(self.run, self.output).read_text(encoding="utf-8")
        self.assertIn("未运行／没有展开调用记录", text)


if __name__ == "__main__":
    unittest.main()
