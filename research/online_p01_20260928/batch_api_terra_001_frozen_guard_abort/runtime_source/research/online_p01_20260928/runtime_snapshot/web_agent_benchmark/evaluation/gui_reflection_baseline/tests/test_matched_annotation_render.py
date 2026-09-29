from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from ..asset_variants import apply_asset_variant_case
from ..matched_annotation_render import (
    ASSET_VARIANT_ID,
    CASE_CONFIGS,
    generate,
)
from ..formal_path_policy import REPO_ROOT
from ..run_targeted_recovery_pilot import load_authoritative_case
from ..targeted_recovery_layout import derive_layout_case
from ..targeted_recovery_scorer import CanonicalSubmissionScorer
from ..targeted_recovery_validator import CanonicalOutcomeValidator


class MatchedAnnotationRenderTests(unittest.TestCase):
    def test_generated_pairs_differ_only_inside_title_mask(self) -> None:
        for slug in CASE_CONFIGS:
            with self.subTest(slug=slug):
                manifest = json.loads(
                    (
                        REPO_ROOT
                        / "web_agent_benchmark/evaluation/gui_reflection_baseline/"
                        f"assets/matched_annotation_v1/{slug}/manifest.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["asset_variant_id"], ASSET_VARIANT_ID)
                self.assertTrue(manifest["validation"]["source_rows_identical"])
                self.assertEqual(
                    manifest["validation"]["outside_allowed_title_mask_pixel_count"],
                    0,
                )
                self.assertGreater(manifest["validation"]["different_pixel_count"], 0)
                for arm in ("official", "clean"):
                    with Image.open(REPO_ROOT / manifest["assets"][arm]["path"]) as image:
                        self.assertEqual(image.format, "PNG")
                        self.assertEqual(image.size, (1000, 750))

    def test_variant_identity_matches_scorer_and_f3_validator(self) -> None:
        slug = "pub010"
        layout_id = "cyclic_shift_1"
        canonical = load_authoritative_case(task_set="strict_review94", slug=slug)
        layout = derive_layout_case(canonical, layout_id=layout_id)
        manifest_path = (
            REPO_ROOT
            / "web_agent_benchmark/evaluation/gui_reflection_baseline/"
            f"assets/matched_annotation_v1/{slug}/manifest.json"
        )
        variant, _manifest = apply_asset_variant_case(
            layout,
            manifest_path=manifest_path,
        )
        expected_pair = (
            "synthetic140:public39:pub010:asset_variant:"
            "matched_annotation_v1:layout:cyclic_shift_1"
        )
        self.assertEqual(variant["pair_group_id"], expected_pair)
        self.assertIn("matched_annotation_v1", variant["arms"]["official"]["chart_path"])

        scorer = CanonicalSubmissionScorer(
            task_set="strict_review94",
            slug=slug,
            layout_id=layout_id,
            asset_variant_id=ASSET_VARIANT_ID,
        )
        validator = CanonicalOutcomeValidator(
            task_set="strict_review94",
            slug=slug,
            layout_id=layout_id,
            asset_variant_id=ASSET_VARIANT_ID,
        )
        self.assertEqual(scorer.pair_group_id, expected_pair)
        self.assertEqual(validator.pair_group_id, expected_pair)
        self.assertEqual(scorer.task_instances, validator.task_instances)

    def test_generator_rejects_a_changed_canonical_heading(self) -> None:
        slug = "pub010"
        config = CASE_CONFIGS[slug]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for arm in ("official", "clean"):
                source_dir = (
                    root
                    / "web_agent_benchmark/benchmark_v2_open/assets"
                    / f"{arm}140"
                    / str(config["asset_dir"])
                )
                source_dir.mkdir(parents=True)
                (source_dir / "source.csv").write_text(
                    "year,tourists\n1880,993\n1891,2917\n",
                    encoding="utf-8",
                )
                title = str(config[f"{arm}_title"])
                if arm == "official":
                    title = "Changed heading"
                (source_dir / "source.html").write_text(
                    f"<html><body><h1>{title}</h1></body></html>",
                    encoding="utf-8",
                )
            with self.assertRaisesRegex(ValueError, "title changed"):
                generate(slug, root / "derived", repository_root=root)


if __name__ == "__main__":
    unittest.main()
