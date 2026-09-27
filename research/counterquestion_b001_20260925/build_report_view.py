"""Render the Chinese report with the existing skill helper, embedding the one original raster."""
from pathlib import Path
import base64
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
HELPER = PROJECT / ".agents/skills/render-html/scripts/render_html.py"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source, record = HERE / "REPORT_ZH.md", HERE / "run/result.json"
    chart = HERE / "run/chart.jpeg"
    target = HERE / "B001_COUNTERQUESTION_REVIEW_v2.html"
    if target.exists():
        raise FileExistsError("Preserve this rendered version; choose a new explicit version")
    spec = importlib.util.spec_from_file_location("aris_html_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    code = module.main([str(source), "--out", str(target), "--offline", "--json", str(record),
                        "--state", str(HERE / "run/reading_zh.json"),
                        "--title", "b001 · 反问驱动竞争解释实测", "--eyebrow", "单样本开发诊断"])
    if code:
        raise RuntimeError("Report renderer failed")
    text = target.read_text(encoding="utf-8")
    marker = 'src="run/chart.jpeg"'
    if text.count(marker) != 1 or not chart.read_bytes().startswith(b"\xff\xd8\xff"):
        raise ValueError("Expected exactly one known JPEG report asset")
    # This is a deterministic final render step, not a manual change to the view.
    # Only our fixed local JPEG can be inlined; arbitrary model HTML is not accepted.
    text = text.replace(marker, 'src="data:image/jpeg;base64,' + base64.b64encode(chart.read_bytes()).decode("ascii") + '"')
    # Local presentation extension: constrain the original high-resolution raster
    # and long sidecar/path strings without modifying or resizing their source bytes.
    style = """<style>
    .layout { grid-template-columns: 260px minmax(0, 1fr); }
    main { min-width: 0; overflow-wrap: anywhere; }
    main img { display: block; width: 100%; max-width: 100%; height: auto; }
    main h1 { font-size: 28px; line-height: 1.4; overflow-wrap: anywhere; }
    main table { width: 100%; table-layout: fixed; }
    main td, main th, main code { overflow-wrap: anywhere; word-break: break-word; }
    main pre { max-width: 100%; white-space: pre-wrap; }
    @media (max-width: 900px) { .layout { grid-template-columns: minmax(0, 1fr); } }
    </style>"""
    text = text.replace("</head>", style + "\n</head>")
    target.write_text(text, encoding="utf-8")
    receipt = {"created_at": datetime.now(timezone.utc).isoformat(), "source": str(source),
               "source_sha256": digest(source), "record_sha256": digest(record),
               "chart_sha256": digest(chart), "html_sha256": digest(target),
               "renderer": str(HELPER), "offline": True, "embedded_original_images": 1}
    (HERE / "view_provenance_v2.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
