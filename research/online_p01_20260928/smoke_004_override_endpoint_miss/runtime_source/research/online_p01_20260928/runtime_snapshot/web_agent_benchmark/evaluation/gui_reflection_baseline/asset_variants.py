"""Validated dispatch for compact-evaluation chart asset variants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .env008_matched_render import apply_variant_case as apply_env008_variant
from .formal_path_policy import REPO_ROOT
from .matched_annotation_render import (
    RECORD_TYPE as MATCHED_ANNOTATION_RECORD_TYPE,
    apply_variant_case as apply_matched_annotation_variant,
)


def apply_asset_variant_case(
    layout_case: Mapping[str, Any],
    *,
    manifest_path: Path,
    repository_root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record_type = manifest.get("record_type")
    if record_type == "env008_matched_render_asset_variant":
        return apply_env008_variant(
            layout_case,
            manifest_path=manifest_path,
            repository_root=repository_root,
        )
    if record_type == MATCHED_ANNOTATION_RECORD_TYPE:
        return apply_matched_annotation_variant(
            layout_case,
            manifest_path=manifest_path,
            repository_root=repository_root,
        )
    raise ValueError(f"unsupported asset variant record_type: {record_type!r}")
