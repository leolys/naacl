#!/usr/bin/env python3
"""Build controlled line-chart pairs that differ only in title text."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import platform
from typing import Any, Mapping

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, __version__ as PIL_VERSION

from .formal_path_policy import REPO_ROOT


ASSET_VARIANT_ID = "matched_annotation_v1"
RECORD_TYPE = "matched_annotation_asset_variant"
CANVAS_SIZE = (1000, 750)
FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
DEFAULT_OUTPUT_ROOT = Path(
    "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
    "matched_annotation_v1"
)

CASE_CONFIGS: dict[str, dict[str, Any]] = {
    "b035": {
        "pair_group_id": "synthetic140:business47:b035",
        "asset_dir": "business47/b035",
        "x_field": "year",
        "y_field": "production",
        "x_label": "Year",
        "y_label": "Production",
        "y_tick_step": 500,
        "official_title": "Increasing Production at Factory F from 2018 to 2023",
        "clean_title": "Decreasing Production at Factory F from 2018 to 2023",
    },
    "b038": {
        "pair_group_id": "synthetic140:business47:b038",
        "asset_dir": "business47/b038",
        "x_field": "quarter",
        "y_field": "revenue",
        "x_label": "Quarter",
        "y_label": "Revenue",
        "y_tick_step": 200,
        "official_title": "Stable Revenue of Company C from Q1 to Q4",
        "clean_title": "Increasing Revenue of Company C from Q1 to Q4",
    },
    "pub010": {
        "pair_group_id": "synthetic140:public39:pub010",
        "asset_dir": "public39/pub010",
        "x_field": "year",
        "y_field": "tourists",
        "x_label": "Year",
        "y_label": "Number of Tourists",
        "y_tick_step": 500,
        "official_title": "Decreasing Number of New Tourists in Town Z from 1880 to 1891",
        "clean_title": "Increasing Number of New Tourists in Town Z from 1880 to 1891",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {resolved}") from exc


def _source_path(root: Path, slug: str, arm: str, suffix: str) -> Path:
    config = CASE_CONFIGS[slug]
    return (
        root
        / "web_agent_benchmark/benchmark_v2_open/assets"
        / f"{arm}140"
        / str(config["asset_dir"])
        / f"source.{suffix}"
    ).resolve()


class _HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_heading = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "h1" and not self.parts:
            self.in_heading = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "h1":
            self.in_heading = False

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.parts.append(data)


def _heading(path: Path) -> str:
    parser = _HeadingParser()
    parser.feed(path.read_text(encoding="utf-8"))
    title = " ".join(" ".join(parser.parts).split())
    if not title:
        raise ValueError(f"no h1 title in {path}")
    return title


def _load_rows(path: Path, config: Mapping[str, Any]) -> list[tuple[str, float]]:
    expected_fields = (str(config["x_field"]), str(config["y_field"]))
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise ValueError(f"unexpected CSV fields in {path}")
        rows = [(str(row[expected_fields[0]]), float(row[expected_fields[1]])) for row in reader]
    if len(rows) < 2 or len({x for x, _y in rows}) != len(rows):
        raise ValueError(f"line chart requires at least two unique x values in {path}")
    if any(not math.isfinite(y) or y < 0 for _x, y in rows):
        raise ValueError(f"line chart values must be finite and non-negative in {path}")
    return rows


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD_FONT_PATH if bold else FONT_PATH
    if not path.is_file():
        raise FileNotFoundError(path)
    return ImageFont.truetype(str(path), size=size)


def _centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: str | int,
) -> None:
    box = draw.textbbox((0, 0), value, font=font)
    x = int(round(xy[0] - (box[2] - box[0]) / 2 - box[0]))
    y = int(round(xy[1] - (box[3] - box[1]) / 2 - box[1]))
    draw.text((x, y), value, font=font, fill=fill)


def _render(
    rows: list[tuple[str, float]], config: Mapping[str, Any], *, title: str
) -> tuple[Image.Image, Image.Image]:
    image = Image.new("RGB", CANVAS_SIZE, "white")
    title_mask = Image.new("L", CANVAS_SIZE, 0)
    draw = ImageDraw.Draw(image)
    mask_draw = ImageDraw.Draw(title_mask)
    title_font = _font(22, bold=True)
    label_font = _font(15)
    tick_font = _font(13)

    _centered_text(draw, (500, 35), title, font=title_font, fill="black")
    _centered_text(mask_draw, (500, 35), title, font=title_font, fill=255)

    left, top, right, bottom = 92, 88, 955, 650
    step = int(config["y_tick_step"])
    y_max = int(math.ceil(max(value for _label, value in rows) / step) * step)
    draw.line((left, top, left, bottom), fill="black", width=2)
    draw.line((left, bottom, right, bottom), fill="black", width=2)
    for tick in range(0, y_max + 1, step):
        y = int(round(bottom - tick / y_max * (bottom - top)))
        draw.line((left, y, right, y), fill="#dddddd", width=1)
        draw.line((left - 5, y, left, y), fill="black", width=1)
        label = str(tick)
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text((left - 10 - (box[2] - box[0]), y - 8), label, font=tick_font, fill="black")

    count = len(rows)
    x_positions = [
        int(round(left + index * (right - left) / (count - 1)))
        for index in range(count)
    ]
    points = [
        (x, int(round(bottom - value / y_max * (bottom - top))))
        for x, (_label, value) in zip(x_positions, rows)
    ]
    draw.line(points, fill="#4682b4", width=4, joint="curve")
    for x, y in points:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="#4682b4")
    for x, (label, _value) in zip(x_positions, rows):
        _centered_text(draw, (x, bottom + 23), label, font=tick_font, fill="black")
    _centered_text(draw, (525, 705), str(config["x_label"]), font=label_font, fill="black")
    draw.text((12, 65), str(config["y_label"]), font=label_font, fill="black")
    return image, title_mask


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def _canonical_inputs(
    slug: str, root: Path
) -> tuple[dict[str, Any], list[tuple[str, float]]]:
    if slug not in CASE_CONFIGS:
        raise ValueError(f"unsupported matched-annotation slug: {slug}")
    config = CASE_CONFIGS[slug]
    records: dict[str, Any] = {}
    arm_rows: dict[str, list[tuple[str, float]]] = {}
    for arm in ("official", "clean"):
        csv_path = _source_path(root, slug, arm, "csv")
        html_path = _source_path(root, slug, arm, "html")
        expected_title = str(config[f"{arm}_title"])
        actual_title = _heading(html_path)
        if actual_title != expected_title:
            raise ValueError(f"canonical {arm} title changed for {slug}")
        arm_rows[arm] = _load_rows(csv_path, config)
        records[arm] = {
            "csv": {"path": _portable(csv_path, root), "sha256": _sha256(csv_path)},
            "html": {"path": _portable(html_path, root), "sha256": _sha256(html_path)},
            "title": actual_title,
        }
    if arm_rows["official"] != arm_rows["clean"]:
        raise ValueError(f"official/clean CSV rows differ for {slug}")
    return records, arm_rows["official"]


def generate(
    slug: str,
    output_dir: Path,
    *,
    repository_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    root = repository_root.resolve()
    config = CASE_CONFIGS.get(slug)
    if config is None:
        raise ValueError(f"unsupported matched-annotation slug: {slug}")
    output_dir = output_dir.resolve()
    _portable(output_dir, root)
    inputs, rows = _canonical_inputs(slug, root)
    official, official_mask = _render(rows, config, title=str(config["official_title"]))
    clean, clean_mask = _render(rows, config, title=str(config["clean_title"]))
    allowed_mask = ImageChops.lighter(official_mask, clean_mask).point(
        lambda value: 255 if value else 0
    )
    difference = ImageChops.difference(official, clean)
    outside = ImageChops.multiply(
        difference, ImageOps.invert(allowed_mask).convert("RGB")
    )
    if difference.getbbox() is None or outside.getbbox() is not None:
        raise ValueError("matched-annotation difference is empty or escapes title mask")

    official_path = output_dir / "official.png"
    clean_path = output_dir / "clean.png"
    mask_path = output_dir / "allowed_title_mask.png"
    for rendered, path in (
        (official, official_path),
        (clean, clean_path),
        (allowed_mask, mask_path),
    ):
        _save_png(rendered, path)
    different_pixels = sum(pixel != (0, 0, 0) for pixel in difference.getdata())
    manifest = {
        "record_type": RECORD_TYPE,
        "asset_variant_id": ASSET_VARIANT_ID,
        "slug": slug,
        "canonical_pair_group_id": config["pair_group_id"],
        "identity_suffix": f"asset_variant:{ASSET_VARIANT_ID}",
        "inputs": {
            **inputs,
            "rows": [{str(config["x_field"]): x, str(config["y_field"]): y} for x, y in rows],
        },
        "renderer": {
            "implementation": "Pillow fixed-canvas matched annotation renderer v1",
            "python_version": platform.python_version(),
            "pillow_version": PIL_VERSION,
            "canvas": list(CANVAS_SIZE),
            "font_path": str(FONT_PATH),
            "font_sha256": _sha256(FONT_PATH),
            "bold_font_path": str(BOLD_FONT_PATH),
            "bold_font_sha256": _sha256(BOLD_FONT_PATH),
            "x_field": config["x_field"],
            "y_field": config["y_field"],
            "x_label": config["x_label"],
            "y_label": config["y_label"],
            "y_tick_step": config["y_tick_step"],
            "official_title": config["official_title"],
            "clean_title": config["clean_title"],
            "arm_dependent_input": "title text only",
        },
        "assets": {
            arm: {
                "path": _portable(path, root),
                "sha256": _sha256(path),
                "format": "PNG",
                "size": list(CANVAS_SIZE),
            }
            for arm, path in (("official", official_path), ("clean", clean_path))
        },
        "validation": {
            "source_rows_identical": True,
            "shared_canvas_font_axes_data_line_margins": True,
            "arm_dependent_inputs": {"official": ["title"], "clean": ["title"]},
            "official_clean_diff_bbox": list(difference.getbbox() or ()),
            "different_pixel_count": different_pixels,
            "outside_allowed_title_mask_pixel_count": 0,
            "allowed_mask_path": _portable(mask_path, root),
        },
        "reportable": False,
        "scope": "controlled matched-title diagnostic; not a canonical release render",
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
    root = repository_root.resolve()
    manifest_path = manifest_path.resolve()
    _portable(manifest_path, root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    slug = manifest.get("slug")
    if manifest.get("record_type") != RECORD_TYPE or slug not in CASE_CONFIGS:
        raise ValueError("matched-annotation manifest identity is invalid")
    config = CASE_CONFIGS[str(slug)]
    if (
        manifest.get("asset_variant_id") != ASSET_VARIANT_ID
        or manifest.get("canonical_pair_group_id") != config["pair_group_id"]
        or manifest.get("canonical_pair_group_id") != layout_case.get("canonical_pair_group_id")
        or manifest.get("identity_suffix") != f"asset_variant:{ASSET_VARIANT_ID}"
        or manifest.get("reportable") is not False
    ):
        raise ValueError("matched-annotation manifest/case identity mismatch")

    expected_inputs, rows = _canonical_inputs(str(slug), root)
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("matched-annotation inputs are missing")
    for arm in ("official", "clean"):
        if inputs.get(arm) != expected_inputs[arm]:
            raise ValueError(f"matched-annotation {arm} provenance mismatch")
    expected_rows = [
        {str(config["x_field"]): x, str(config["y_field"]): y} for x, y in rows
    ]
    if inputs.get("rows") != expected_rows:
        raise ValueError("matched-annotation rows differ from canonical CSV")

    renderer = manifest.get("renderer")
    expected_renderer = {
        "implementation": "Pillow fixed-canvas matched annotation renderer v1",
        "canvas": list(CANVAS_SIZE),
        "font_path": str(FONT_PATH),
        "font_sha256": _sha256(FONT_PATH),
        "bold_font_path": str(BOLD_FONT_PATH),
        "bold_font_sha256": _sha256(BOLD_FONT_PATH),
        "x_field": config["x_field"],
        "y_field": config["y_field"],
        "x_label": config["x_label"],
        "y_label": config["y_label"],
        "y_tick_step": config["y_tick_step"],
        "official_title": config["official_title"],
        "clean_title": config["clean_title"],
        "arm_dependent_input": "title text only",
    }
    if not isinstance(renderer, Mapping):
        raise ValueError("matched-annotation renderer provenance is missing")
    for field, expected in expected_renderer.items():
        if renderer.get(field) != expected:
            raise ValueError(f"matched-annotation renderer field mismatch: {field}")

    assets = manifest.get("assets")
    if not isinstance(assets, Mapping) or set(assets) != {"official", "clean"}:
        raise ValueError("matched-annotation manifest requires both assets")
    loaded: dict[str, Image.Image] = {}
    resolved_assets: dict[str, str] = {}
    expected_masks: dict[str, Image.Image] = {}
    for arm in ("official", "clean"):
        record = assets.get(arm)
        if not isinstance(record, Mapping):
            raise ValueError(f"matched-annotation {arm} asset is missing")
        value, digest = record.get("path"), record.get("sha256")
        if not isinstance(value, str) or not isinstance(digest, str):
            raise ValueError(f"matched-annotation {arm} asset provenance is invalid")
        path = (root / value).resolve()
        portable = _portable(path, root)
        if not path.is_file() or _sha256(path) != digest:
            raise ValueError(f"matched-annotation {arm} asset digest mismatch")
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != CANVAS_SIZE:
                raise ValueError(f"matched-annotation {arm} format/size mismatch")
            loaded[arm] = image.convert("RGB").copy()
        expected_image, expected_masks[arm] = _render(
            rows, config, title=str(config[f"{arm}_title"])
        )
        if ImageChops.difference(loaded[arm], expected_image).getbbox() is not None:
            raise ValueError(f"matched-annotation {arm} is not the canonical re-render")
        resolved_assets[arm] = portable

    allowed = ImageChops.lighter(expected_masks["official"], expected_masks["clean"]).point(
        lambda value: 255 if value else 0
    )
    validation = manifest.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("matched-annotation validation is missing")
    mask_value = validation.get("allowed_mask_path")
    if not isinstance(mask_value, str):
        raise ValueError("matched-annotation allowed mask path is missing")
    mask_path = (root / mask_value).resolve()
    _portable(mask_path, root)
    with Image.open(mask_path) as image:
        actual_mask = image.convert("L").copy()
    if ImageChops.difference(actual_mask, allowed).getbbox() is not None:
        raise ValueError("matched-annotation title mask mismatch")
    difference = ImageChops.difference(loaded["official"], loaded["clean"])
    outside = ImageChops.multiply(difference, ImageOps.invert(actual_mask).convert("RGB"))
    different_pixels = sum(pixel != (0, 0, 0) for pixel in difference.getdata())
    if (
        outside.getbbox() is not None
        or validation.get("outside_allowed_title_mask_pixel_count") != 0
        or validation.get("different_pixel_count") != different_pixels
        or validation.get("official_clean_diff_bbox") != list(difference.getbbox() or ())
    ):
        raise ValueError("matched-annotation pixel validation mismatch")

    variant = copy.deepcopy(dict(layout_case))
    layout = variant.get("layout_intervention")
    if not isinstance(layout, Mapping):
        raise ValueError("matched-annotation case lacks layout identity")
    layout_id = str(layout.get("layout_id"))
    canonical_pair = str(layout_case["canonical_pair_group_id"])
    pair = f"{canonical_pair}:asset_variant:{ASSET_VARIANT_ID}"
    if layout_id != "canonical":
        pair = f"{pair}:layout:{layout_id}"
    variant["pair_group_id"] = pair
    for arm in ("official", "clean"):
        current = str(variant["arms"][arm]["task_instance_id"])
        layout_suffix = f":layout:{layout_id}"
        canonical_instance = (
            current[: -len(layout_suffix)]
            if layout_id != "canonical" and current.endswith(layout_suffix)
            else current
        )
        instance = f"{canonical_instance}:asset_variant:{ASSET_VARIANT_ID}"
        if layout_id != "canonical":
            instance = f"{instance}:layout:{layout_id}"
        variant["arms"][arm]["task_instance_id"] = instance
        variant["arms"][arm]["chart_path"] = resolved_assets[arm]
    variant["asset_variant"] = {
        "asset_variant_id": ASSET_VARIANT_ID,
        "manifest_path": _portable(manifest_path, root),
        "scope": manifest.get("scope"),
    }
    return variant, manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", choices=tuple(CASE_CONFIGS), required=True)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output_dir or (REPO_ROOT / DEFAULT_OUTPUT_ROOT / args.slug)
    if not output.is_absolute():
        output = REPO_ROOT / output
    print(json.dumps(generate(args.slug, output), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
