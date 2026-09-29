"""Auditable visual-history fixtures for the env008 phase-2 premise probe."""

from __future__ import annotations

from io import BytesIO
import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont


VIEWPORT = (1280, 960)
HISTORY_MODEL_SIZE = (448, 448)
PROPOSITION_ENTITIES = ("Solar", "Wind", "Hydroelectric")
REGULAR_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

# The only treatment-bearing pixels are the entity value on H0.  This mask is
# intentionally larger than the rendered glyphs, but smaller than the static
# proposition panel; pair validation rejects every changed pixel outside it.
PROPOSITION_TEXT_MASK_BBOX = (850, 415, 1220, 485)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_proposition_frame(base_decision_png: bytes, entity: str) -> bytes:
    """Turn one canonical decision screenshot into a fixed H0 record page."""

    if entity not in PROPOSITION_ENTITIES:
        raise ValueError(f"unsupported proposition entity: {entity!r}")
    with Image.open(BytesIO(base_decision_png)).convert("RGB") as source:
        if source.size != VIEWPORT:
            raise ValueError(
                f"proposition fixture requires viewport {VIEWPORT}, got {source.size}"
            )
        image = source.copy()
    draw = ImageDraw.Draw(image)
    regular = ImageFont.truetype(str(REGULAR_FONT), 24)
    small = ImageFont.truetype(str(REGULAR_FONT), 19)
    bold = ImageFont.truetype(str(BOLD_FONT), 26)
    entity_font = ImageFont.truetype(str(BOLD_FONT), 38)

    # Cover only the existing action-panel interior.  The chart, instruction,
    # header and outer panel geometry remain canonical for this arm/layout.
    draw.rounded_rectangle(
        (842, 192, 1254, 890),
        radius=10,
        fill=(255, 255, 255),
        outline=(203, 214, 229),
        width=2,
    )
    draw.text((868, 222), "Prior proposition record", font=bold, fill=(23, 34, 53))
    draw.rounded_rectangle(
        (868, 330, 1228, 530),
        radius=10,
        fill=(241, 246, 252),
        outline=(138, 162, 191),
        width=2,
    )
    draw.text((894, 360), "Identified source", font=regular, fill=(62, 74, 93))
    draw.text((894, 423), entity, font=entity_font, fill=(16, 44, 82))
    draw.text(
        (868, 586),
        "Recorded by the previous operator",
        font=small,
        fill=(62, 74, 93),
    )
    draw.rounded_rectangle(
        (868, 770, 1228, 850),
        radius=10,
        fill=(29, 93, 168),
        outline=(22, 74, 134),
        width=2,
    )
    draw.text((925, 794), "Continue to routing", font=regular, fill=(255, 255, 255))
    return _png(image)


def resize_as_official_history(
    png: bytes, annotation: tuple[int, int] | None = None
) -> Image.Image:
    """Apply the official annotation and 448x448 history transform."""

    with Image.open(BytesIO(png)).convert("RGB") as image:
        if annotation is not None:
            x, y = annotation
            rgba = image.convert("RGBA")
            overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            radius = 15
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(255, 0, 0, 127),
            )
            image = Image.alpha_composite(rgba, overlay).convert("RGB")
        return image.resize(HISTORY_MODEL_SIZE)


def rgb_protocol_sha256(image: Image.Image) -> str:
    rgb = image.convert("RGB")
    digest = hashlib.sha256()
    digest.update(b"gui-reflection-history-rgb-v1\0")
    digest.update(rgb.width.to_bytes(8, "big"))
    digest.update(rgb.height.to_bytes(8, "big"))
    digest.update(rgb.tobytes())
    return digest.hexdigest()


def official_history_input_sha256(
    png: bytes, annotation: tuple[int, int] | None = None
) -> str:
    return rgb_protocol_sha256(resize_as_official_history(png, annotation))


def diff_audit(left_png: bytes, right_png: bytes) -> dict[str, Any]:
    """Verify that a proposition pair differs only inside the declared mask."""

    with Image.open(BytesIO(left_png)).convert("RGB") as left, Image.open(
        BytesIO(right_png)
    ).convert("RGB") as right:
        if left.size != VIEWPORT or right.size != VIEWPORT:
            raise ValueError("fixture pair has an unexpected viewport")
        diff = ImageChops.difference(left, right)
        bbox = diff.getbbox()
        outside = diff.copy()
        mask = Image.new("L", VIEWPORT, 0)
        ImageDraw.Draw(mask).rectangle(PROPOSITION_TEXT_MASK_BBOX, fill=255)
        outside.paste((0, 0, 0), mask=mask)
        outside_bbox = outside.getbbox()

    transformed_left = resize_as_official_history(left_png)
    transformed_right = resize_as_official_history(right_png)
    transformed_diff = ImageChops.difference(transformed_left, transformed_right)
    transformed_bbox = transformed_diff.getbbox()
    sx = HISTORY_MODEL_SIZE[0] / VIEWPORT[0]
    sy = HISTORY_MODEL_SIZE[1] / VIEWPORT[1]
    x0, y0, x1, y1 = PROPOSITION_TEXT_MASK_BBOX
    transformed_mask_bbox = (
        max(0, int(x0 * sx) - 2),
        max(0, int(y0 * sy) - 2),
        min(HISTORY_MODEL_SIZE[0], int(x1 * sx) + 3),
        min(HISTORY_MODEL_SIZE[1], int(y1 * sy) + 3),
    )
    transformed_outside = transformed_diff.copy()
    transformed_mask = Image.new("L", HISTORY_MODEL_SIZE, 0)
    ImageDraw.Draw(transformed_mask).rectangle(transformed_mask_bbox, fill=255)
    transformed_outside.paste((0, 0, 0), mask=transformed_mask)
    transformed_outside_bbox = transformed_outside.getbbox()
    return {
        "raw_diff_bbox": list(bbox) if bbox is not None else [],
        "raw_mask_bbox": list(PROPOSITION_TEXT_MASK_BBOX),
        "raw_diff_outside_mask_bbox": (
            list(outside_bbox) if outside_bbox is not None else []
        ),
        "raw_diff_within_mask": bbox is not None and outside_bbox is None,
        "model_448_diff_bbox": (
            list(transformed_bbox) if transformed_bbox is not None else []
        ),
        "model_448_mask_bbox": list(transformed_mask_bbox),
        "model_448_diff_outside_mask_bbox": (
            list(transformed_outside_bbox)
            if transformed_outside_bbox is not None
            else []
        ),
        "model_448_diff_within_mask": (
            transformed_bbox is not None and transformed_outside_bbox is None
        ),
    }
