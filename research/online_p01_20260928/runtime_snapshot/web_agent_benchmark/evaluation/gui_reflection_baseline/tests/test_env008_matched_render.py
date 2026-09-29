from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from ..env008_matched_render import (
    ASSET_VARIANT_ID,
    CLEAN_CSV,
    LAYOUT_ID,
    OFFICIAL_CSV,
    apply_variant_case,
    generate,
)
from ..formal_path_policy import REPO_ROOT
from ..run_targeted_recovery_pilot import load_authoritative_case
from ..targeted_recovery_layout import derive_layout_case
from ..targeted_recovery_scorer import CanonicalSubmissionScorer


CSV_TEXT = """energy_source,production_percentage,color,bar_height
Solar,41.2,#FFD700,40
Wind,29.8,#87CEEB,68
Hydroelectric,18.5,#4169E1,52
Biomass,7.2,#228B22,22
Geothermal,3.3,#8B4513,35
"""


class Env008MatchedRenderTests(unittest.TestCase):
    def test_generator_limits_arm_difference_to_declared_geometry_mask(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (OFFICIAL_CSV, CLEAN_CSV):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(CSV_TEXT, encoding="utf-8")
            output = root / "derived"
            manifest = generate(output, repository_root=root)

            self.assertEqual(manifest["asset_variant_id"], ASSET_VARIANT_ID)
            self.assertEqual(
                manifest["validation"]["outside_allowed_geometry_mask_pixel_count"],
                0,
            )
            self.assertGreater(
                manifest["validation"]["different_pixel_count"],
                0,
            )
            for arm in ("official", "clean"):
                with Image.open(root / manifest["assets"][arm]["path"]) as image:
                    self.assertEqual(image.format, "PNG")
                    self.assertEqual(image.size, (1000, 750))

    def test_variant_uses_separate_pair_task_asset_and_scorer_identities(self) -> None:
        canonical = load_authoritative_case(task_set="smoke17", slug="env008")
        layout = derive_layout_case(canonical, layout_id=LAYOUT_ID)
        manifest_path = (
            REPO_ROOT
            / "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
            "env008_matched_render_v1/manifest.json"
        )
        variant, manifest = apply_variant_case(
            layout,
            manifest_path=manifest_path,
        )
        self.assertEqual(manifest["asset_variant_id"], ASSET_VARIANT_ID)
        self.assertEqual(
            variant["pair_group_id"],
            "synthetic140:environment35:env008:asset_variant:"
            "matched_render_v1:layout:cyclic_shift_2",
        )
        self.assertNotEqual(
            variant["arms"]["official"]["chart_path"],
            layout["arms"]["official"]["chart_path"],
        )
        self.assertNotEqual(
            variant["arms"]["clean"]["task_instance_id"],
            layout["arms"]["clean"]["task_instance_id"],
        )

        scorer = CanonicalSubmissionScorer(
            task_set="smoke17",
            slug="env008",
            layout_id=LAYOUT_ID,
            asset_variant_id=ASSET_VARIANT_ID,
        )
        record = scorer.score(
            submission_id="submission:d1:test",
            pair_group_id=variant["pair_group_id"],
            task_instance_id=variant["arms"]["official"]["task_instance_id"],
            arm="official",
            choice_token="choice_0",
            control_position=1,
        )
        self.assertTrue(record.success)
        with self.assertRaisesRegex(ValueError, "pair"):
            scorer.score(
                submission_id="submission:d1:canonical-mixup",
                pair_group_id=layout["pair_group_id"],
                task_instance_id=variant["arms"]["official"]["task_instance_id"],
                arm="official",
                choice_token="choice_0",
                control_position=1,
            )

    def test_manifest_asset_digest_is_enforced(self) -> None:
        canonical = load_authoritative_case(task_set="smoke17", slug="env008")
        layout = derive_layout_case(canonical, layout_id=LAYOUT_ID)
        source_manifest_path = (
            REPO_ROOT
            / "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
            "env008_matched_render_v1/manifest.json"
        )
        manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        manifest["assets"]["official"]["sha256"] = "0" * 64
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            dir=source_manifest_path.parent,
            delete=False,
        ) as handle:
            json.dump(manifest, handle)
            tampered_path = Path(handle.name)
        try:
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                apply_variant_case(layout, manifest_path=tampered_path)
        finally:
            tampered_path.unlink()

    def test_self_consistent_asset_substitution_is_rejected_by_rerender(self) -> None:
        canonical = load_authoritative_case(task_set="smoke17", slug="env008")
        layout = derive_layout_case(canonical, layout_id=LAYOUT_ID)
        asset_dir = (
            REPO_ROOT
            / "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
            "env008_matched_render_v1"
        )
        source_manifest_path = asset_dir / "manifest.json"
        manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        with Image.open(asset_dir / "official.png") as source:
            altered = source.convert("RGB").copy()
        altered.putpixel((0, 0), (0, 0, 0))
        with tempfile.NamedTemporaryFile(
            suffix=".png", dir=asset_dir, delete=False
        ) as handle:
            altered_path = Path(handle.name)
        altered.save(altered_path, format="PNG")
        manifest["assets"]["official"]["path"] = altered_path.relative_to(
            REPO_ROOT
        ).as_posix()
        manifest["assets"]["official"]["sha256"] = hashlib.sha256(
            altered_path.read_bytes()
        ).hexdigest()
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            dir=asset_dir,
            delete=False,
        ) as handle:
            json.dump(manifest, handle)
            altered_manifest_path = Path(handle.name)
        try:
            with self.assertRaisesRegex(ValueError, "canonical CSV re-render"):
                apply_variant_case(layout, manifest_path=altered_manifest_path)
        finally:
            altered_manifest_path.unlink()
            altered_path.unlink()

    def test_bold_font_provenance_is_required(self) -> None:
        canonical = load_authoritative_case(task_set="smoke17", slug="env008")
        layout = derive_layout_case(canonical, layout_id=LAYOUT_ID)
        asset_dir = (
            REPO_ROOT
            / "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
            "env008_matched_render_v1"
        )
        manifest = json.loads((asset_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["renderer"].pop("bold_font_sha256")
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            dir=asset_dir,
            delete=False,
        ) as handle:
            json.dump(manifest, handle)
            incomplete_manifest_path = Path(handle.name)
        try:
            with self.assertRaisesRegex(ValueError, "bold_font_sha256"):
                apply_variant_case(layout, manifest_path=incomplete_manifest_path)
        finally:
            incomplete_manifest_path.unlink()


if __name__ == "__main__":
    unittest.main()
