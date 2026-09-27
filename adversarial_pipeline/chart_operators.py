"""
Programmatic PIL/OpenCV chart operators for L2 exact_marks_required error types.

These operators directly edit the source chart image instead of asking the LLM
to redraw from scratch.  This guarantees data-mark fidelity and eliminates the
text→chart reconstruction loss that plagues LLM-generated matplotlib code.

Supported operators (all return a saved PNG at output_path):

  missingaxis(src, annotation, output_path)
      Paints over both axis lines and all tick+label regions.

  missingaxisticks(src, annotation, output_path)
      Paints over tick marks and tick labels only; axis line stays.

  missingaxistitle(src, annotation, output_path)
      Paints over the axis title/label text only.

  missingtitle(src, annotation, output_path)
      Paints over the chart title region.

  missinglegend(src, annotation, output_path)
      Paints over the legend bounding region.

  missingunits(src, annotation, output_path)
      Paints over unit-bearing axis tick labels (e.g. "Mbps", "%") while
      keeping numeric tick marks; falls back to missingaxisticks if no
      annotation bboxes are available.

  confusinglegend(src, annotation, output_path, *, shuffle_labels=True)
      Redraws legend labels in a shuffled order (colors stay, labels swap).

All operators:
  - Detect the dominant background color automatically.
  - Add a small margin (BBOX_PADDING px) around each painted region for
    cleaner coverage.
  - Do NOT modify data marks (bars, lines, points, pie slices).
  - Return True on success, False if the required annotation field is absent.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BBOX_PADDING = 4          # extra pixels around each painted bbox
MIN_REGION_DIM = 2        # skip bbox if width/height below this


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_image(src: str | Path) -> Image.Image:
    return Image.open(src).convert("RGBA")


def _detect_bg_color(img: Image.Image) -> tuple[int, int, int, int]:
    """
    Return the dominant background colour by sampling the four corners
    (10×10 pixel blocks) and taking the most common RGBA value.
    """
    arr = np.array(img)
    h, w = arr.shape[:2]
    sz = min(10, h // 4, w // 4)
    corners = np.concatenate([
        arr[:sz, :sz].reshape(-1, 4),
        arr[:sz, -sz:].reshape(-1, 4),
        arr[-sz:, :sz].reshape(-1, 4),
        arr[-sz:, -sz:].reshape(-1, 4),
    ])
    # Most common colour
    unique, counts = np.unique(corners, axis=0, return_counts=True)
    dominant = unique[counts.argmax()]
    return tuple(int(v) for v in dominant)


def _expand_bbox(bbox: dict, padding: int = BBOX_PADDING) -> dict:
    return {
        "x": bbox["x"] - padding,
        "y": bbox["y"] - padding,
        "w": bbox["w"] + 2 * padding,
        "h": bbox["h"] + 2 * padding,
    }


def _paint_bbox(draw: ImageDraw.ImageDraw, bbox: dict, color: tuple) -> None:
    """Paint a single bbox (x,y,w,h) with the given color."""
    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    if w < MIN_REGION_DIM or h < MIN_REGION_DIM:
        return
    x0, y0 = int(x), int(y)
    x1, y1 = int(x + w), int(y + h)
    draw.rectangle([x0, y0, x1, y1], fill=color)


def _save(img: Image.Image, output_path: str | Path) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Save as RGB PNG (drop alpha channel if added)
    img.convert("RGB").save(str(out), "PNG", dpi=(150, 150))


def _save_passthrough(src: str | Path, output_path: str | Path) -> None:
    """Write an unchanged copy for diagnostic workflows when an operator cannot run."""
    _save(_load_image(src), output_path)


# ---------------------------------------------------------------------------
# Public operators
# ---------------------------------------------------------------------------

def missingtitle(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
) -> bool:
    """Paint over the chart title."""
    gi = (annotation or {}).get("general_figure_info", {})
    title = gi.get("title", {})
    if not title.get("bbox"):
        return False

    img = _load_image(src)
    bg = _detect_bg_color(img)
    draw = ImageDraw.Draw(img)
    _paint_bbox(draw, _expand_bbox(title["bbox"]), bg)
    _save(img, output_path)
    return True


def missingaxistitle(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
) -> bool:
    """Paint over x-axis and y-axis title/label text."""
    gi = (annotation or {}).get("general_figure_info", {})
    painted = False
    img = _load_image(src)
    bg = _detect_bg_color(img)
    draw = ImageDraw.Draw(img)

    for axis_name in ("x_axis", "y_axis"):
        ax = gi.get(axis_name, {})
        label = ax.get("label", {})
        if label.get("bbox"):
            _paint_bbox(draw, _expand_bbox(label["bbox"]), bg)
            painted = True

    if not painted:
        return False
    _save(img, output_path)
    return True


def missingaxisticks(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
) -> bool:
    """Paint over tick labels (numbers/categories) on both axes."""
    gi = (annotation or {}).get("general_figure_info", {})
    img = _load_image(src)
    bg = _detect_bg_color(img)
    draw = ImageDraw.Draw(img)
    painted = False

    for axis_name in ("x_axis", "y_axis"):
        ax = gi.get(axis_name, {})
        major = ax.get("major_labels", {})
        for bbox in major.get("bboxes", []):
            _paint_bbox(draw, _expand_bbox(bbox), bg)
            painted = True
        minor = ax.get("minor_labels", {})
        for bbox in minor.get("bboxes", []):
            _paint_bbox(draw, _expand_bbox(bbox), bg)
            painted = True

    if not painted:
        return False
    _save(img, output_path)
    return True


def missingaxis(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
) -> bool:
    """
    Paint over both axis tick labels AND the axis line region.
    Uses the figure_info bbox to infer axis strip width/height.
    """
    gi = (annotation or {}).get("general_figure_info", {})
    img = _load_image(src)
    bg = _detect_bg_color(img)
    draw = ImageDraw.Draw(img)
    painted = False
    iw, ih = img.size

    # First, erase tick labels (same as missingaxisticks)
    for axis_name in ("x_axis", "y_axis"):
        ax = gi.get(axis_name, {})
        for label_set in (ax.get("major_labels", {}), ax.get("minor_labels", {})):
            for bbox in label_set.get("bboxes", []):
                _paint_bbox(draw, _expand_bbox(bbox), bg)
                painted = True

    # Then erase the axis strip (strip of pixels between figure edge and labels)
    fig_bbox = gi.get("figure_info", {}).get("bbox")
    if fig_bbox:
        fx, fy = int(fig_bbox["x"]), int(fig_bbox["y"])
        fw, fh = int(fig_bbox["w"]), int(fig_bbox["h"])

        # Left strip (y-axis line area)
        left_strip = {"x": 0, "y": fy, "w": fx, "h": fh}
        _paint_bbox(draw, left_strip, bg)

        # Bottom strip (x-axis line area)
        bottom_y = fy + fh
        bottom_strip = {"x": fx, "y": bottom_y, "w": fw, "h": ih - bottom_y}
        _paint_bbox(draw, bottom_strip, bg)
        painted = True

    if not painted:
        return False
    _save(img, output_path)
    return True


def missinglegend(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
) -> bool:
    """Paint over the entire legend region."""
    gi = (annotation or {}).get("general_figure_info", {})
    legend = gi.get("legend", {})
    if not legend:
        _save_passthrough(src, output_path)
        return False

    img = _load_image(src)
    bg = _detect_bg_color(img)
    draw = ImageDraw.Draw(img)
    painted = False

    # Try bbox-level legend region first
    if legend.get("bbox"):
        _paint_bbox(draw, _expand_bbox(legend["bbox"], BBOX_PADDING * 2), bg)
        painted = True
    else:
        # Fall back: paint all legend item label bboxes + colour patches
        for item in legend.get("items", []):
            label = item.get("label", {})
            if label.get("bbox"):
                _paint_bbox(draw, _expand_bbox(label["bbox"], BBOX_PADDING * 2), bg)
                painted = True
            if item.get("color_patch_bbox"):
                _paint_bbox(draw, _expand_bbox(item["color_patch_bbox"], BBOX_PADDING * 2), bg)
                painted = True

    if not painted:
        return False
    _save(img, output_path)
    return True


def missingunits(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
) -> bool:
    """
    Paint over unit-bearing tick labels (e.g. '%', 'Mbps', '$').
    Falls back to missingaxisticks if we can't identify unit labels.
    """
    gi = (annotation or {}).get("general_figure_info", {})
    img = _load_image(src)
    bg = _detect_bg_color(img)
    draw = ImageDraw.Draw(img)
    painted = False

    import re
    # Regex for labels that contain a non-numeric token (i.e. a unit)
    _unit_re = re.compile(r"[A-Za-z%$€£¥°]")

    for axis_name in ("x_axis", "y_axis"):
        ax = gi.get(axis_name, {})
        major = ax.get("major_labels", {})
        bboxes = major.get("bboxes", [])
        values = major.get("values", [])
        for bbox, val in zip(bboxes, values):
            if _unit_re.search(str(val)):
                _paint_bbox(draw, _expand_bbox(bbox), bg)
                painted = True

    if not painted:
        # No unit labels found — fall back to painting all tick labels
        return missingaxisticks(src, annotation, output_path)

    _save(img, output_path)
    return True


def confusinglegend(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
    *,
    shuffle_labels: bool = True,
    seed: int | None = 42,
) -> bool:
    """
    Swap legend label text while keeping colour patches in place.
    Requires annotation with legend item bboxes and PIL font.
    """
    gi = (annotation or {}).get("general_figure_info", {})
    legend = gi.get("legend", {})
    items = legend.get("items", [])
    if len(items) < 2:
        _save_passthrough(src, output_path)
        return False

    # Collect (bbox, text) for each label
    label_infos = []
    for item in items:
        label = item.get("label", {})
        if label.get("bbox") and label.get("text"):
            label_infos.append((label["bbox"], label["text"]))

    if len(label_infos) < 2:
        _save_passthrough(src, output_path)
        return False

    img = _load_image(src)
    bg = _detect_bg_color(img)
    draw = ImageDraw.Draw(img)

    # Shuffle the texts
    texts = [t for _, t in label_infos]
    if shuffle_labels:
        rng = random.Random(seed)
        shuffled = texts[:]
        while shuffled == texts:
            rng.shuffle(shuffled)
    else:
        shuffled = texts[::-1]

    # Load a basic font
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except Exception:
        font = ImageFont.load_default()

    for (bbox, _orig_text), new_text in zip(label_infos, shuffled):
        expanded = _expand_bbox(bbox)
        # Paint over old text
        _paint_bbox(draw, expanded, bg)
        # Draw new text at the same location
        x = int(bbox["x"])
        y = int(bbox["y"])
        draw.text((x, y), new_text, fill=(30, 30, 30, 255), font=font)

    _save(img, output_path)
    return True


# ---------------------------------------------------------------------------
# L1 VisualPerceptionLayer operators
# ---------------------------------------------------------------------------

def illegibletext(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
    *,
    blur_radius: float = 2.5,
    shrink_factor: float = 0.55,
    target_regions: str = "axis_labels",
) -> bool:
    """
    Degrade axis-label / tick text readability without removing it.

    Strategy (applied in order until enough text is found):
      1. Use annotation bboxes to shrink + blur each text label in-place.
      2. If no annotation, apply a Gaussian blur to the bottom 20% and
         left 15% of the image (typical axis label strips).

    ``target_regions`` controls which regions are degraded:
      - "axis_labels":  x/y tick labels only (default)
      - "all_text":     also degrade title and legend labels
    """
    from PIL import ImageFilter

    gi = (annotation or {}).get("general_figure_info", {})
    img = _load_image(src)
    bg = _detect_bg_color(img)

    bboxes: list[dict] = []
    for axis_name in ("x_axis", "y_axis"):
        ax = gi.get(axis_name, {})
        for lset in (ax.get("major_labels", {}), ax.get("minor_labels", {})):
            bboxes.extend(lset.get("bboxes", []))

    if target_regions == "all_text":
        title = gi.get("title", {})
        if title.get("bbox"):
            bboxes.append(title["bbox"])
        for item in gi.get("legend", {}).get("items", []):
            if item.get("label", {}).get("bbox"):
                bboxes.append(item["label"]["bbox"])

    if bboxes:
        # Per-bbox degradation: crop, shrink, blur, paste back
        for bbox in bboxes:
            x0, y0 = int(bbox["x"]), int(bbox["y"])
            x1, y1 = int(bbox["x"] + bbox["w"]), int(bbox["y"] + bbox["h"])
            if x1 - x0 < MIN_REGION_DIM or y1 - y0 < MIN_REGION_DIM:
                continue
            region = img.crop((x0, y0, x1, y1))
            # Shrink and re-enlarge to pixelate / lose sharpness
            new_w = max(1, int(region.width * shrink_factor))
            new_h = max(1, int(region.height * shrink_factor))
            small = region.resize((new_w, new_h), Image.LANCZOS)
            back = small.resize((region.width, region.height), Image.NEAREST)
            # Apply blur
            blurred = back.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            img.paste(blurred, (x0, y0))
    else:
        # No annotation — degrade axis strip regions heuristically
        iw, ih = img.size
        # Bottom 20%: x-axis labels
        bottom = img.crop((0, int(ih * 0.80), iw, ih))
        img.paste(bottom.filter(ImageFilter.GaussianBlur(radius=blur_radius)), (0, int(ih * 0.80)))
        # Left 15%: y-axis labels
        left = img.crop((0, 0, int(iw * 0.15), ih))
        img.paste(left.filter(ImageFilter.GaussianBlur(radius=blur_radius)), (0, 0))

    _save(img, output_path)
    return True


def indistinguishablecolors(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
    *,
    desaturation: float = 0.72,
) -> bool:
    """
    Shift data-mark colors toward gray so series become hard to distinguish.

    Approach: convert the data-mark region (figure_info bbox) to a
    partially-desaturated version.  Only the plot area is affected;
    axis labels and legend remain unchanged.

    ``desaturation`` in [0,1]: 1.0 = fully gray, 0.0 = no change.
    """
    gi = (annotation or {}).get("general_figure_info", {})
    fig_bbox = gi.get("figure_info", {}).get("bbox")
    img = _load_image(src)
    iw, ih = img.size

    if fig_bbox:
        x0 = max(0, int(fig_bbox["x"]))
        y0 = max(0, int(fig_bbox["y"]))
        x1 = min(iw, int(fig_bbox["x"] + fig_bbox["w"]))
        y1 = min(ih, int(fig_bbox["y"] + fig_bbox["h"]))
    else:
        # Fallback: use inner 70%×80% of image
        x0, y0 = int(iw * 0.15), int(ih * 0.10)
        x1, y1 = int(iw * 0.95), int(ih * 0.85)

    region = img.crop((x0, y0, x1, y1)).convert("RGB")
    arr = np.array(region, dtype=np.float32)

    # Desaturate: blend each pixel toward its grayscale value
    gray = arr.mean(axis=2, keepdims=True)
    desaturated = arr * (1 - desaturation) + gray * desaturation
    desaturated = np.clip(desaturated, 0, 255).astype(np.uint8)

    new_region = Image.fromarray(desaturated).convert("RGBA")
    img.paste(new_region, (x0, y0))
    _save(img, output_path)
    return True


def overusingcolors(
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
    *,
    hue_shift_step: int = 25,
) -> bool:
    """
    Randomly shift the hue of data-mark colors to create garish over-coloring.

    Each pixel in the plot area gets a hue rotation that varies by original
    hue bucket, pushing all colors into vivid, unrelated hues.
    """
    import colorsys

    gi = (annotation or {}).get("general_figure_info", {})
    fig_bbox = gi.get("figure_info", {}).get("bbox")
    img = _load_image(src)
    iw, ih = img.size

    if fig_bbox:
        x0 = max(0, int(fig_bbox["x"]))
        y0 = max(0, int(fig_bbox["y"]))
        x1 = min(iw, int(fig_bbox["x"] + fig_bbox["w"]))
        y1 = min(ih, int(fig_bbox["y"] + fig_bbox["h"]))
    else:
        x0, y0 = int(iw * 0.15), int(ih * 0.10)
        x1, y1 = int(iw * 0.95), int(ih * 0.85)

    region = img.crop((x0, y0, x1, y1)).convert("RGBA")
    arr = np.array(region, dtype=np.float32)

    # Shift hue by a fixed amount per pixel based on original hue bucket
    r, g, b, a = arr[:,:,0]/255, arr[:,:,1]/255, arr[:,:,2]/255, arr[:,:,3]
    h, s, v = np.vectorize(colorsys.rgb_to_hsv)(r, g, b)

    # Only modify pixels that are sufficiently saturated (skip white/gray bg)
    saturated = s > 0.15
    h[saturated] = (h[saturated] + hue_shift_step / 360.0) % 1.0

    nr, ng, nb = np.vectorize(colorsys.hsv_to_rgb)(h, s, v)
    new_arr = np.stack([
        np.clip(nr * 255, 0, 255).astype(np.uint8),
        np.clip(ng * 255, 0, 255).astype(np.uint8),
        np.clip(nb * 255, 0, 255).astype(np.uint8),
        a.astype(np.uint8),
    ], axis=2)

    new_region = Image.fromarray(new_arr)
    img.paste(new_region, (x0, y0))
    _save(img, output_path)
    return True


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

OPERATOR_MAP: dict[str, Any] = {
    # L2 metadata-erasure operators
    "missingaxis":      missingaxis,
    "missingaxisticks": missingaxisticks,
    "missingaxistitle": missingaxistitle,
    "missingtitle":     missingtitle,
    "missinglegend":    missinglegend,
    "missingunits":     missingunits,
    "confusinglegend":  confusinglegend,
    # L1 visual-encoding operators
    "illegibletext":           illegibletext,
    "indistinguishablecolors": indistinguishablecolors,
    "overusingcolors":         overusingcolors,
}


def apply_operator(
    error_type: str,
    src: str | Path,
    annotation: dict | None,
    output_path: str | Path,
    **kwargs: Any,
) -> bool:
    """
    Apply the programmatic operator for the given error_type.

    Returns True if the operator ran and saved a valid image.
    Returns False if the operator is not available or the annotation
    lacked the required fields (caller should fall back to LLM generation).
    """
    op = OPERATOR_MAP.get(error_type)
    if op is None:
        return False
    try:
        return bool(op(src, annotation, output_path, **kwargs))
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "chart_operators.apply_operator(%s) failed: %s", error_type, exc
        )
        return False
