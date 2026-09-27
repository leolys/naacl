"""Render canonical OBC review JSON as a self-contained, offline HTML viewer.

Usage: python render_viewer.py review_data.json --out review_viewer.html
The source JSON is never modified. All chart bytes are embedded unchanged.
Only the Python standard library is required; no API or network calls occur.
"""

import argparse
import base64
import hashlib
import html
import json
import re
import struct
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "obc140_review_v1"
TEMPLATE_PATH = Path(__file__).with_name("viewer_template.html")
FIELD_LABELS = {
    "task_alias": "任务别名", "chart_reference": "图表标题引用",
    "page_title": "页面标题", "user_goal": "用户目标",
    "primary_field_label": "主要决策字段", "option_labels": "可选答案",
    "companion_fields": "配套字段", "completion_label": "完成按钮",
    "observations": "观察", "ref": "图像引用", "location": "图中位置",
    "content": "观察内容", "rule_id": "规则编号", "chain_id": "解释链编号",
    "option_label": "对应答案", "claim": "结论", "text": "规则内容",
    "component": "作用环节", "conditions": "适用条件", "id": "编号",
    "action": "拟采取的行动", "brief_basis": "简要依据",
    "used_rule_ids": "采用的规则编号", "new_evidence": "新增证据",
    "uncertainty": "不确定性", "recommendation": "核验建议",
    "checks": "核验记录", "reason": "理由", "rationale": "理由",
    "status": "状态", "label": "标签", "name": "名称", "value": "值",
    "O": "O · 观察核验", "B": "B · 规则核验", "C": "C · 结论核验",
    "O_reason": "观察核验理由", "B_reason": "规则核验理由",
    "C_reason": "结论核验理由", "rules": "规则", "chains": "解释链",
    "original_mechanism": "原机制记录", "audited_mechanism": "审计后机制",
    "task_slug": "任务编号", "domain": "领域", "validated": "校验结果",
    "rule_state": "规则状态", "source": "来源", "confidence": "置信度",
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_json(value):
    """JSON text for a non-executable script element, including hostile strings."""
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            .replace("&", "\\u0026").replace("<", "\\u003c")
            .replace(">", "\\u003e").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def validate_catalog(data):
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Source must use schema_version=" + SCHEMA_VERSION)
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("Source tasks must be a list")
    seen = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("Every task must be an object")
        slug = task.get("task_slug")
        if not isinstance(slug, str) or not slug or slug in seen:
            raise ValueError("Task identifiers must be nonempty unique strings")
        seen.add(slug)
        for field in ("status", "translations"):
            if task.get(field) is not None and not isinstance(task[field], dict):
                raise ValueError("Task " + slug + ": " + field + " must be an object")
    return data


def image_format(raw):
    """Only raster formats are permitted; SVG and arbitrary markup are rejected."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Unsupported raster image format")


def collect_assets(data, source_dir):
    assets = {}
    warnings = []
    for task in data["tasks"]:
        slug = task["task_slug"]
        raw_path = task.get("chart_file")
        asset = {"source_path": raw_path, "data_uri": None, "error": None}
        try:
            if not isinstance(raw_path, str) or not raw_path:
                raise FileNotFoundError("Chart path missing")
            # Network URLs and UNC paths must not trigger network access during rendering.
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw_path) or raw_path.startswith(("\\\\", "//")):
                raise ValueError("Network chart locations are not allowed")
            path = Path(raw_path)
            if not path.is_absolute():
                path = source_dir / path
            path = path.resolve()
            raw = path.read_bytes()
            mime = image_format(raw)
            asset.update({"resolved_path": str(path), "sha256": sha256(raw),
                          "byte_count": len(raw), "mime_type": mime,
                          "data_uri": "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")})
            if mime == "image/png" and len(raw) >= 24:
                asset["width"], asset["height"] = struct.unpack(">II", raw[16:24])
        except (OSError, ValueError) as exc:
            # Do not surface operating-system exception text or arbitrary error strings.
            asset["error"] = type(exc).__name__
            warnings.append({"task_slug": slug, "error_class": type(exc).__name__})
        assets[slug] = asset
    return assets, warnings


def build_html(source_path, *, template_path=None, field_labels=None, rendered_at=None):
    source_path = Path(source_path).resolve()
    source_bytes = source_path.read_bytes()
    data = validate_catalog(json.loads(source_bytes.decode("utf-8-sig")))
    assets, warnings = collect_assets(data, source_path.parent)
    timestamp = rendered_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    labels = dict(FIELD_LABELS)
    supplied_labels = data.get("field_labels", {})
    if isinstance(supplied_labels, dict):
        labels.update({str(k): str(v) for k, v in supplied_labels.items()})
    if field_labels:
        labels.update({str(k): str(v) for k, v in field_labels.items()})
    provenance = {"source_path": str(source_path), "source_sha256": sha256(source_bytes),
                  "rendered_at": timestamp, "source_generated_at": data.get("generated_at"),
                  "task_count": len(data["tasks"]), "chart_warnings": warnings}
    payload = {"catalog": data, "assets": assets, "render": provenance, "field_labels": labels}
    replacements = {
        "@@TITLE@@": html.escape(str(data.get("title") or "140 个任务 · O/B/C 人工审阅"), quote=True),
        "@@SOURCE_PATH@@": html.escape(str(source_path), quote=True),
        "@@SOURCE_SHA256@@": provenance["source_sha256"],
        "@@RENDERED_AT@@": html.escape(timestamp, quote=True),
        "@@REVIEW_DATA@@": safe_json(payload),
    }
    template = Path(template_path or TEMPLATE_PATH).read_text(encoding="utf-8")
    for token in replacements:
        if token not in template:
            raise ValueError("Template is missing required token " + token)
    # A single pass prevents source content containing token text from being substituted.
    output = re.sub(r"@@(?:TITLE|SOURCE_PATH|SOURCE_SHA256|RENDERED_AT|REVIEW_DATA)@@",
                    lambda match: replacements[match.group()], template)
    return output, provenance


def render(source_path, output_path, **kwargs):
    output, provenance = build_html(source_path, **kwargs)
    output_path = Path(output_path).resolve()
    if output_path == Path(source_path).resolve():
        raise ValueError("Output must not overwrite the source JSON")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Canonical review_data.json")
    parser.add_argument("--out", type=Path, help="Standalone HTML; defaults to review_viewer.html")
    parser.add_argument("--field-labels", type=Path, help="Optional JSON object of Chinese field labels")
    args = parser.parse_args()
    labels = None
    if args.field_labels:
        labels = json.loads(args.field_labels.read_text(encoding="utf-8-sig"))
        if not isinstance(labels, dict):
            parser.error("--field-labels must contain a JSON object")
    out = args.out or args.source.with_name("review_viewer.html")
    result = render(args.source, out, field_labels=labels)
    print(json.dumps({"output": str(out.resolve()), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
