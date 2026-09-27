"""Offline migration regressions: no model requests or browser transitions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.path_compat import OLD_PROJECT, OLD_STORAGE, PROJECT_ROOT, resolve_path


class PathCompatibilityTests(unittest.TestCase):
    def test_project_and_storage(self):
        self.assertEqual(resolve_path(OLD_PROJECT), PROJECT_ROOT)
        self.assertEqual(resolve_path(OLD_PROJECT + "/research/a.json"), PROJECT_ROOT / "research/a.json")
        self.assertEqual(resolve_path(OLD_STORAGE + "/code_generation/liyisheng/8H100conda"),
                         Path("/mnt/data/code_generation/liyisheng/8H100conda"))

    def test_current_relative_and_unrelated(self):
        for value in ("/mnt/data/lys/example", "relative/file.png", "/tmp/hipilot/sharestorage/a",
                      "/hipilot/sharestorage_extra/file", "/other/data/file"):
            self.assertEqual(resolve_path(value), Path(value))
        self.assertEqual(resolve_path("x.png", base=OLD_PROJECT), PROJECT_ROOT / "x.png")

    def test_missing_stays_missing(self):
        path = resolve_path(OLD_PROJECT + "/__migration_test_missing__/not_an_asset.png")
        self.assertFalse(path.exists())
        with self.assertRaises(FileNotFoundError):
            path.read_bytes()

    def test_reader_leaves_json_evidence_unchanged(self):
        from research.postpilot_attribution_diagnostic.offline_audit import read
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = json.dumps({"source_directory": OLD_PROJECT + "/old_run", "score": "success"}).encode()
            (root / "record.json").write_bytes(content)
            with patch("research.path_compat.PROJECT_ROOT", root):
                result = read(OLD_PROJECT + "/record.json")
            self.assertEqual(result["source_directory"], OLD_PROJECT + "/old_run")
            self.assertEqual((root / "record.json").read_bytes(), content)

    def test_backbone_path_alias_is_not_model_or_decoding_waiver(self):
        from research.prospective_simple_check_pilot.resume_panel import assert_same_backbones
        old = {"M_small": {"weights": OLD_STORAGE + "/datasets/model-A", "temperature": 0},
               "M_strong": {"model": "unchanged"}}
        new = copy.deepcopy(old)
        new["M_small"]["weights"] = "/mnt/data/datasets/model-A"
        assert_same_backbones(old, new)
        for key, value in (("weights", "/mnt/data/datasets/model-B"), ("temperature", 1)):
            changed = copy.deepcopy(new)
            changed["M_small"][key] = value
            with self.assertRaises(ValueError):
                assert_same_backbones(old, changed)
        changed = copy.deepcopy(new)
        changed["M_strong"]["model"] = "different-model"
        with self.assertRaises(ValueError):
            assert_same_backbones(old, changed)

    def test_policy_copies_legacy_image_without_changing_checkpoint(self):
        from PIL import Image
        from research.decision_evidence_audit.policies import _observed_path, _copy_observation
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (7, 9), "white").save(root / "chart.png")
            checkpoint = SimpleNamespace(observed_screenshots=[{"kind": "dashboard", "path": OLD_PROJECT + "/chart.png"}])
            original = copy.deepcopy(checkpoint.observed_screenshots)
            with patch("research.path_compat.PROJECT_ROOT", root):
                source = _observed_path(checkpoint, kind="dashboard", artifact_root=Path("/"))
                _copy_observation(source, root / "copy.png")
            self.assertEqual((root / "chart.png").read_bytes(), (root / "copy.png").read_bytes())
            self.assertEqual(checkpoint.observed_screenshots, original)

    def test_control_and_budget_sources_accept_alias_but_reject_different_source(self):
        from research.prospective_simple_check_pilot import panel
        from research.decision_evidence_audit.core import BudgetLedger
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            old_config = {"M_small": {"weights": OLD_STORAGE + "/datasets/model-A"}, "M_strong": {"model": "same"}}
            (source / "MODEL_CONFIG.json").write_text(json.dumps(old_config))
            (source / "budget.json").write_text(json.dumps({"events": [], "model_calls": 0, "browser_transitions": 0}))
            (source / "progress.json").write_text(json.dumps({"rows": []}))
            controls = [{"kind": "nonchart_public_route", "target": a, "initial": b, "passed": True}
                        for a in ("Route A", "Route B") for b in ("Route A", "Route B")]
            controls += [{"kind": "ordered_two_images", "order_index": i, "passed": True} for i in (0, 1)]
            for name in panel.BACKBONES:
                folder = source / "online/controls" / name
                folder.mkdir(parents=True)
                (folder / "results.json").write_text(json.dumps(controls))
            (source / "api_wire").mkdir()
            (source / "api_wire/api_spend.json").write_text(json.dumps({"entries": [{"status": "completed", "usage_cost_upper_usd": "0"}]}))
            cfg = copy.deepcopy(old_config)
            cfg["M_small"]["weights"] = "/mnt/data/datasets/model-A"
            cfg.update(qualified_controls_source=OLD_PROJECT + "/source", carry_in_budget_source=str(source))
            original = (source / "MODEL_CONFIG.json").read_bytes()
            with patch("research.path_compat.PROJECT_ROOT", root):
                ledger = BudgetLedger()
                panel.carry_in_budget(ledger, OLD_PROJECT + "/source")
                self.assertEqual(panel.prior_control_usage(cfg, root), [0])
                cfg["carry_in_budget_source"] = OLD_PROJECT + "/different"
                with self.assertRaises(ValueError):
                    panel.prior_control_usage(cfg, root)
            self.assertEqual(original, (source / "MODEL_CONFIG.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
