#!/usr/bin/env python3
"""Generate and bind the isolated env008 matched-render sensitivity assets.

The derived official and clean charts share every rendering parameter.  The
only arm-dependent input is the field used for bar geometry: ``bar_height``
for official and ``production_percentage`` for clean.  Printed labels always
come from ``production_percentage``.  These assets are diagnostic variants;
they never replace the benchmark_v2 canonical figures.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import platform
from typing import Any, Mapping

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, __version__ as PIL_VERSION

from .formal_path_policy import REPO_ROOT


ASSET_VARIANT_ID = "matched_render_v1"
LAYOUT_ID = "cyclic_shift_2"
CANVAS_SIZE = (1000, 750)
Y_DOMAIN = (0.0, 70.0)
FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
OFFICIAL_CSV = Path(
    "web_agent_benchmark/benchmark_v2_open/assets/official140/"
    "environment35/env008/source.csv"
)
CLEAN_CSV = Path(
    "web_agent_benchmark/benchmark_v2_open/assets/clean140/"
    "environment35/env008/source.csv"
)
DEFAULT_OUTPUT_DIR = Path(
    "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
    "env008_matched_render_v1"
)
EXPECTED_FIELDS = (
    "energy_source",
    "production_percentage",
    "color",
    "bar_height",
)
EXPECTED_CATEGORIES = (
    "Solar",
    "Wind",
    "Hydroelectric",
    "Biomass",
    "Geothermal",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {resolved}") from exc


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_FIELDS:
            raise ValueError(f"unexpected env008 CSV fields in {path}")
        rows = [dict(row) for row in reader]
    if tuple(row["energy_source"] for row in rows) != EXPECTED_CATEGORIES:
        raise ValueError(f"unexpected env008 category order in {path}")
    for row in rows:
        float(row["production_percentage"])
        float(row["bar_height"])
        color = row["color"]
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError(f"invalid color in {path}: {color!r}")
    return rows


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD_FONT_PATH if bold else FONT_PATH
    if not path.is_file():
        raise FileNotFoundError(path)
    return ImageFont.truetype(str(path), size=size)


def _centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: str | int,
) -> tuple[int, int, int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    x = int(round(xy[0] - width / 2 - box[0]))
    y = int(round(xy[1] - height / 2 - box[1]))
    draw.text((x, y), text, font=font, fill=fill)
    return (x + box[0], y + box[1], x + box[2], y + box[3])


def _render(
    rows: list[dict[str, str]], *, geometry_field: str
) -> tuple[Image.Image, Image.Image]:
    if geometry_field not in {"bar_height", "production_percentage"}:
        raise ValueError("unsupported geometry field")
    image = Image.new("RGB", CANVAS_SIZE, "white")
    mask = Image.new("L", CANVAS_SIZE, 0)
    draw = ImageDraw.Draw(image)
    mask_draw = ImageDraw.Draw(mask)
    title_font = _font(25, bold=True)
    tick_font = _font(12)
    category_font = _font(13)
    value_font = _font(18, bold=True)

    _centered_text(
        draw,
        (CANVAS_SIZE[0] / 2, 37),
        "Renewable Energy Production by Source",
        font=title_font,
        fill="black",
    )

    left, top, right, bottom = 82, 92, 965, 655
    draw.line((left, top, left, bottom), fill="black", width=2)
    draw.line((left, bottom, right, bottom), fill="black", width=2)
    plot_height = bottom - top
    for tick in range(0, 71, 5):
        y = int(round(bottom - (tick / Y_DOMAIN[1]) * plot_height))
        draw.line((left - 6, y, left, y), fill="black", width=1)
        text = str(tick)
        box = draw.textbbox((0, 0), text, font=tick_font)
        draw.text(
            (left - 10 - (box[2] - box[0]), y - (box[3] - box[1]) / 2),
            text,
            font=tick_font,
            fill="black",
        )

    centers = (168, 342, 516, 690, 864)
    bar_width = 112
    for row, center in zip(rows, centers):
        geometry_value = float(row[geometry_field])
        y_top = int(round(bottom - (geometry_value / Y_DOMAIN[1]) * plot_height))
        rectangle = (center - bar_width // 2, y_top, center + bar_width // 2, bottom)
        draw.rectangle(rectangle, fill=row["color"])
        mask_draw.rectangle(rectangle, fill=255)

        value_text = f"{float(row['production_percentage']):.1f}%"
        value_center = (center, y_top - 18)
        _centered_text(
            draw,
            value_center,
            value_text,
            font=value_font,
            fill="black",
        )
        _centered_text(
            mask_draw,
            value_center,
            value_text,
            font=value_font,
            fill=255,
        )
        _centered_text(
            draw,
            (center, bottom + 28),
            row["energy_source"],
            font=category_font,
            fill="black",
        )
    return image, mask


def _save_deterministic_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def generate(output_dir: Path, *, repository_root: Path = REPO_ROOT) -> dict[str, Any]:
    root = repository_root.resolve()
    official_csv = (root / OFFICIAL_CSV).resolve()
    clean_csv = (root / CLEAN_CSV).resolve()
    official_rows = _load_rows(official_csv)
    clean_rows = _load_rows(clean_csv)
    if official_rows != clean_rows:
        raise ValueError("env008 official/clean source CSV rows are not identical")
    for font_path in (FONT_PATH, BOLD_FONT_PATH):
        if not font_path.is_file():
            raise FileNotFoundError(font_path)

    output_dir = output_dir.resolve()
    _portable(output_dir, root)
    official, official_mask = _render(official_rows, geometry_field="bar_height")
    clean, clean_mask = _render(clean_rows, geometry_field="production_percentage")
    allowed_mask = ImageChops.lighter(official_mask, clean_mask).point(
        lambda value: 255 if value else 0
    )
    difference = ImageChops.difference(official, clean)
    outside_mask = ImageChops.multiply(
        difference,
        ImageOps.invert(allowed_mask).convert("RGB"),
    )
    if outside_mask.getbbox() is not None:
        raise ValueError("matched-render arms differ outside bar/value-label mask")
    diff_pixels = sum(
        pixel != (0, 0, 0) for pixel in difference.getdata()
    )
    if diff_pixels == 0:
        raise ValueError("matched-render official and clean assets are identical")

    official_path = output_dir / "official.png"
    clean_path = output_dir / "clean.png"
    official_mask_path = output_dir / "official_geometry_mask.png"
    clean_mask_path = output_dir / "clean_geometry_mask.png"
    allowed_mask_path = output_dir / "allowed_difference_mask.png"
    for rendered, path in (
        (official, official_path),
        (clean, clean_path),
        (official_mask, official_mask_path),
        (clean_mask, clean_mask_path),
        (allowed_mask, allowed_mask_path),
    ):
        _save_deterministic_png(rendered, path)

    rows_manifest = [
        {
            "energy_source": row["energy_source"],
            "production_percentage": float(row["production_percentage"]),
            "color": row["color"],
            "bar_height": float(row["bar_height"]),
        }
        for row in official_rows
    ]
    manifest = {
        "record_type": "env008_matched_render_asset_variant",
        "asset_variant_id": ASSET_VARIANT_ID,
        "layout_id": LAYOUT_ID,
        "canonical_pair_group_id": "synthetic140:environment35:env008",
        "identity_suffix": f"asset_variant:{ASSET_VARIANT_ID}",
        "inputs": {
            "official_csv": {
                "path": _portable(official_csv, root),
                "sha256": _sha256(official_csv),
            },
            "clean_csv": {
                "path": _portable(clean_csv, root),
                "sha256": _sha256(clean_csv),
            },
            "fields": list(EXPECTED_FIELDS),
            "rows": rows_manifest,
        },
        "renderer": {
            "implementation": "Pillow fixed-canvas env008 matched renderer v1",
            "python_version": platform.python_version(),
            "pillow_version": PIL_VERSION,
            "canvas": list(CANVAS_SIZE),
            "font_path": str(FONT_PATH),
            "font_sha256": _sha256(FONT_PATH),
            "bold_font_path": str(BOLD_FONT_PATH),
            "bold_font_sha256": _sha256(BOLD_FONT_PATH),
            "title": "Renewable Energy Production by Source",
            "axis_domain": list(Y_DOMAIN),
            "axis_ticks": list(range(0, 71, 5)),
            "category_order": list(EXPECTED_CATEGORIES),
            "printed_label_field": "production_percentage",
            "official_geometry_field": "bar_height",
            "clean_geometry_field": "production_percentage",
            "render_command": (
                "python3 -m web_agent_benchmark.evaluation.gui_reflection_baseline."
                "env008_matched_render"
            ),
        },
        "assets": {
            "official": {
                "path": _portable(official_path, root),
                "sha256": _sha256(official_path),
                "format": "PNG",
                "size": list(CANVAS_SIZE),
            },
            "clean": {
                "path": _portable(clean_path, root),
                "sha256": _sha256(clean_path),
                "format": "PNG",
                "size": list(CANVAS_SIZE),
            },
        },
        "validation": {
            "source_rows_identical": True,
            "shared_canvas_font_title_axis_ticks_margins_categories_colors": True,
            "printed_labels_from_production_percentage": True,
            "arm_dependent_inputs": {
                "official": ["bar_height"],
                "clean": ["production_percentage"],
            },
            "official_clean_diff_bbox": list(difference.getbbox() or ()),
            "different_pixel_count": diff_pixels,
            "outside_allowed_geometry_mask_pixel_count": 0,
            "allowed_mask_path": _portable(allowed_mask_path, root),
            "official_mask_path": _portable(official_mask_path, root),
            "clean_mask_path": _portable(clean_mask_path, root),
        },
        "reportable": False,
        "scope": "isolated D1 sensitivity; not a canonical benchmark_v2 replication",
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def apply_variant_case(
    layout_case: Mapping[str, Any],
    *,
    manifest_path: Path,
    repository_root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind validated D1 assets to a layout case under separate identities."""

    root = repository_root.resolve()
    manifest_path = manifest_path.resolve()
    _portable(manifest_path, root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("record_type") != "env008_matched_render_asset_variant":
        raise ValueError("matched-render manifest has wrong record_type")
    if manifest.get("asset_variant_id") != ASSET_VARIANT_ID:
        raise ValueError("matched-render manifest has wrong asset_variant_id")
    layout = layout_case.get("layout_intervention")
    if not isinstance(layout, Mapping) or layout.get("layout_id") != LAYOUT_ID:
        raise ValueError("D1 matched-render variant requires cyclic_shift_2")
    if manifest.get("layout_id") != LAYOUT_ID:
        raise ValueError("matched-render manifest layout mismatch")
    if manifest.get("canonical_pair_group_id") != layout_case.get(
        "canonical_pair_group_id"
    ):
        raise ValueError("matched-render manifest canonical pair mismatch")
    if manifest.get("identity_suffix") != f"asset_variant:{ASSET_VARIANT_ID}":
        raise ValueError("matched-render manifest identity suffix mismatch")
    if manifest.get("reportable") is not False:
        raise ValueError("matched-render diagnostic must remain non-reportable")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("matched-render manifest inputs are missing")
    if inputs.get("fields") != list(EXPECTED_FIELDS):
        raise ValueError("matched-render manifest input fields mismatch")
    source_rows: dict[str, list[dict[str, str]]] = {}
    for arm, expected_relative in (
        ("official", OFFICIAL_CSV),
        ("clean", CLEAN_CSV),
    ):
        record = inputs.get(f"{arm}_csv")
        if not isinstance(record, Mapping):
            raise ValueError(f"matched-render {arm} CSV provenance is missing")
        path_value = record.get("path")
        sha_value = record.get("sha256")
        if path_value != expected_relative.as_posix() or not isinstance(
            sha_value, str
        ):
            raise ValueError(f"matched-render {arm} CSV path mismatch")
        source_path = (root / expected_relative).resolve()
        if not source_path.is_file() or _sha256(source_path) != sha_value:
            raise ValueError(f"matched-render {arm} CSV digest mismatch")
        source_rows[arm] = _load_rows(source_path)
    if source_rows["official"] != source_rows["clean"]:
        raise ValueError("matched-render source CSV rows are not identical")
    normalized_rows = [
        {
            "energy_source": row["energy_source"],
            "production_percentage": float(row["production_percentage"]),
            "color": row["color"],
            "bar_height": float(row["bar_height"]),
        }
        for row in source_rows["official"]
    ]
    if inputs.get("rows") != normalized_rows:
        raise ValueError("matched-render manifest rows differ from canonical CSV")

    renderer = manifest.get("renderer")
    if not isinstance(renderer, Mapping):
        raise ValueError("matched-render renderer provenance is missing")
    expected_renderer_values = {
        "implementation": "Pillow fixed-canvas env008 matched renderer v1",
        "canvas": list(CANVAS_SIZE),
        "font_path": str(FONT_PATH),
        "font_sha256": _sha256(FONT_PATH),
        "bold_font_path": str(BOLD_FONT_PATH),
        "bold_font_sha256": _sha256(BOLD_FONT_PATH),
        "title": "Renewable Energy Production by Source",
        "axis_domain": list(Y_DOMAIN),
        "axis_ticks": list(range(0, 71, 5)),
        "category_order": list(EXPECTED_CATEGORIES),
        "printed_label_field": "production_percentage",
        "official_geometry_field": "bar_height",
        "clean_geometry_field": "production_percentage",
    }
    for field, expected in expected_renderer_values.items():
        if renderer.get(field) != expected:
            raise ValueError(f"matched-render renderer field mismatch: {field}")

    assets = manifest.get("assets")
    if not isinstance(assets, Mapping) or set(assets) != {"official", "clean"}:
        raise ValueError("matched-render manifest requires both assets")
    resolved_assets: dict[str, str] = {}
    loaded_assets: dict[str, Image.Image] = {}
    for arm in ("official", "clean"):
        record = assets.get(arm)
        if not isinstance(record, Mapping):
            raise ValueError(f"matched-render {arm} asset is missing")
        value = record.get("path")
        expected_sha = record.get("sha256")
        if not isinstance(value, str) or not isinstance(expected_sha, str):
            raise ValueError(f"matched-render {arm} asset provenance is invalid")
        path = (root / value).resolve()
        portable = _portable(path, root)
        if not path.is_file() or _sha256(path) != expected_sha:
            raise ValueError(f"matched-render {arm} asset digest mismatch")
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != CANVAS_SIZE:
                raise ValueError(f"matched-render {arm} asset format/size mismatch")
            loaded_assets[arm] = image.convert("RGB").copy()
        resolved_assets[arm] = portable

    expected_official, expected_official_mask = _render(
        source_rows["official"], geometry_field="bar_height"
    )
    expected_clean, expected_clean_mask = _render(
        source_rows["clean"], geometry_field="production_percentage"
    )
    for arm, expected_image in (
        ("official", expected_official),
        ("clean", expected_clean),
    ):
        if ImageChops.difference(loaded_assets[arm], expected_image).getbbox() is not None:
            raise ValueError(
                f"matched-render {arm} asset is not the canonical CSV re-render"
            )

    validation = manifest.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("matched-render validation record is missing")
    expected_allowed_mask = ImageChops.lighter(
        expected_official_mask, expected_clean_mask
    ).point(lambda value: 255 if value else 0)
    allowed_mask_value = validation.get("allowed_mask_path")
    if not isinstance(allowed_mask_value, str):
        raise ValueError("matched-render allowed mask path is missing")
    allowed_mask_path = (root / allowed_mask_value).resolve()
    _portable(allowed_mask_path, root)
    if not allowed_mask_path.is_file():
        raise ValueError("matched-render allowed mask is missing")
    with Image.open(allowed_mask_path) as image:
        actual_allowed_mask = image.convert("L").copy()
    if (
        actual_allowed_mask.size != CANVAS_SIZE
        or ImageChops.difference(actual_allowed_mask, expected_allowed_mask).getbbox()
        is not None
    ):
        raise ValueError("matched-render allowed mask does not match re-rendered geometry")
    actual_difference = ImageChops.difference(
        loaded_assets["official"], loaded_assets["clean"]
    )
    actual_outside = ImageChops.multiply(
        actual_difference,
        ImageOps.invert(actual_allowed_mask).convert("RGB"),
    )
    if actual_outside.getbbox() is not None:
        raise ValueError("matched-render assets differ outside declared geometry")
    actual_diff_pixels = sum(
        pixel != (0, 0, 0) for pixel in actual_difference.getdata()
    )
    if validation.get("different_pixel_count") != actual_diff_pixels:
        raise ValueError("matched-render different pixel count mismatch")
    if validation.get("official_clean_diff_bbox") != list(
        actual_difference.getbbox() or ()
    ):
        raise ValueError("matched-render difference bbox mismatch")
    if validation.get("outside_allowed_geometry_mask_pixel_count") != 0:
        raise ValueError("matched-render manifest reports an out-of-mask difference")

    variant = copy.deepcopy(dict(layout_case))
    suffix = f"asset_variant:{ASSET_VARIANT_ID}"
    canonical_pair = str(layout_case["canonical_pair_group_id"])
    variant["pair_group_id"] = f"{canonical_pair}:{suffix}:layout:{LAYOUT_ID}"
    for arm in ("official", "clean"):
        arm_record = variant["arms"][arm]
        current_task_instance = str(arm_record["task_instance_id"])
        layout_suffix = f":layout:{LAYOUT_ID}"
        if not current_task_instance.endswith(layout_suffix):
            raise ValueError("layout task identity lacks expected suffix")
        base_task_instance = current_task_instance[: -len(layout_suffix)]
        arm_record["task_instance_id"] = (
            f"{base_task_instance}:{suffix}:layout:{LAYOUT_ID}"
        )
        arm_record["chart_path"] = resolved_assets[arm]
    variant["asset_variant"] = {
        "asset_variant_id": ASSET_VARIANT_ID,
        "manifest_path": _portable(manifest_path, root),
        "scope": manifest.get("scope"),
    }
    return variant, manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    manifest = generate(output_dir)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
