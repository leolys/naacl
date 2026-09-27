#!/usr/bin/env python3
"""Render the Chinese successful-resistance appendix preview to HTML and PDF."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import markdown


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    REPO_ROOT / "paper/appendix_successful_resistance_trace_chinese_20260711.md"
)
DEFAULT_HTML = (
    REPO_ROOT / "paper/appendix_successful_resistance_trace_chinese_20260711.html"
)
DEFAULT_PDF = (
    REPO_ROOT / "paper/appendix_successful_resistance_trace_chinese_20260711.pdf"
)


CSS = r"""
@page {
  size: A4;
  margin: 16mm 15mm 18mm;
}

html {
  color: #1f2937;
  background: #ffffff;
}

body {
  max-width: 180mm;
  margin: 0 auto;
  font-family: "Droid Sans Fallback", "Noto Sans CJK SC", sans-serif;
  font-size: 10.5pt;
  line-height: 1.62;
  letter-spacing: 0;
}

h1, h2, h3 {
  color: #111827;
  font-weight: 700;
  line-height: 1.3;
  break-after: avoid;
}

h1 {
  margin: 0 0 9mm;
  padding-bottom: 4mm;
  border-bottom: 1.2pt solid #334155;
  font-size: 21pt;
}

h2 {
  margin: 9mm 0 3mm;
  font-size: 15pt;
}

h3 {
  margin: 6mm 0 2mm;
  font-size: 12pt;
}

p {
  margin: 0 0 3mm;
  text-align: justify;
}

blockquote {
  margin: 0 0 7mm;
  padding: 3mm 4mm;
  border-left: 3pt solid #2563a6;
  background: #f4f7fa;
  color: #334155;
}

blockquote p {
  margin: 0;
}

table {
  width: 100%;
  margin: 3mm 0 6mm;
  border-collapse: collapse;
  font-size: 9pt;
  line-height: 1.45;
}

thead {
  display: table-header-group;
}

tr {
  break-inside: avoid;
}

th, td {
  padding: 2.2mm 2.4mm;
  border: 0.5pt solid #aab4c0;
  vertical-align: top;
}

th {
  background: #eef2f6;
  color: #111827;
  font-weight: 700;
  text-align: left;
}

code {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 0.88em;
  color: #123b63;
  overflow-wrap: anywhere;
}

img {
  display: block;
  width: 100%;
  height: auto;
  margin: 4mm auto 2mm;
  border: 0.6pt solid #cbd5e1;
  break-inside: avoid;
}

ul, ol {
  margin: 2mm 0 4mm 6mm;
  padding-left: 5mm;
}

li {
  margin-bottom: 1.4mm;
}

em {
  color: #475569;
}

a {
  color: inherit;
  text-decoration: none;
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--chrome", type=Path)
    return parser.parse_args()


def find_chrome() -> Path:
    candidates = sorted(
        Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome")
    )
    if not candidates:
        raise FileNotFoundError("No Playwright Chromium executable found")
    return candidates[-1]


def render_html(source: Path, output: Path) -> None:
    body = markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="{output.parent.resolve().as_uri()}/">
  <title>附录中文审阅版：Agent 如何克服误导性视觉证据</title>
  <style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def render_pdf(chrome: Path, html: Path, pdf: Path) -> None:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(chrome),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf.resolve()}",
            html.resolve().as_uri(),
        ],
        check=True,
    )


def main() -> None:
    args = parse_args()
    chrome = args.chrome or find_chrome()
    render_html(args.input, args.html)
    render_pdf(chrome, args.html, args.pdf)
    print(f"html={args.html}")
    print(f"pdf={args.pdf}")


if __name__ == "__main__":
    main()
