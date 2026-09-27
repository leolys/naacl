"""Explicit monetary waiver never resets call limits or model configuration."""
import copy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

from research.decision_evidence_audit.core import BudgetExceeded
from .api_backend import ApiSpend
from .resume_panel import assert_same_backbones
from .test_preparation import config


class MoneyWaiverTests(unittest.TestCase):
    def test_explicit_waiver_required(self):
        cfg = config()
        cfg.enforce_money_cap = False
        cfg.money_cap_usd = None
        self.assertIn("explicit_money_limit_waiver_reference", cfg.missing(check_credential=False))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ApiSpend(cfg, Path(tmp) / "spend.json")

    def test_waiver_removes_only_dollar_stop(self):
        cfg = config()
        cfg.enforce_money_cap = False
        cfg.money_limit_waiver_reference = "test-only authorization"
        cfg.money_cap_usd = "0.01"
        cfg.max_calls = 2
        self.assertEqual(cfg.missing(check_credential=False), [])
        with tempfile.TemporaryDirectory() as tmp:
            spend = ApiSpend(cfg, Path(tmp) / "spend.json")
            spend.reserve("first")
            spend.reserve("second")
            with self.assertRaises(BudgetExceeded):
                spend.reserve("third")
            self.assertIsNone(spend.cap)
            self.assertGreater(spend.accounted_upper(), 0)

    def test_original_dollar_limit_remains_default(self):
        cfg = config()
        cfg.money_cap_usd = "0.01"
        with tempfile.TemporaryDirectory() as tmp:
            spend = ApiSpend(cfg, Path(tmp) / "spend.json")
            with self.assertRaises(BudgetExceeded):
                spend.reserve("first")

    def test_backbone_comparison_is_symmetric(self):
        old = dict(M_small={"model": "unchanged"}, M_strong=asdict(config()))
        new = copy.deepcopy(old)
        new["M_strong"].pop("temperature")
        with self.assertRaises(ValueError):
            assert_same_backbones(old, new)
        with self.assertRaises(ValueError):
            assert_same_backbones(new, old)
        new = copy.deepcopy(old)
        new["M_strong"].update(enforce_money_cap=False, money_limit_waiver_reference="user", money_cap_usd=None)
        assert_same_backbones(old, new)


if __name__ == "__main__":
    unittest.main()
