#!/usr/bin/env python3
"""Embed local PNG screenshots into a generated HTML report.

This keeps the Markdown/regular HTML as the canonical, reviewable source while
producing one portable HTML file that can be copied to another computer.
Only local PNG files below the input HTML directory are accepted.
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import struct
import zlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IMG_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)("[^>]*>)', re.IGNORECASE)
ANCHOR_RE = re.compile(
    r'<a\b([^>]*?)\bhref="([^"]+)"([^>]*)>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
class ResourceAuditParser(HTMLParser):
    """Collect resource-bearing attributes independently of serialization."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[str] = []
        self.hrefs: list[tuple[str, str]] = []
        self.css: list[str] = []
        self.errors: list[str] = []
        self._inside_style = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        normalized = [(name.lower(), value or "") for name, value in attrs]
        values = {name: value for name, value in normalized}

        if tag in {"script", "link", "base", "iframe", "object", "embed"}:
            self.errors.append(f"forbidden resource-capable tag: {tag}")
        if tag == "meta" and "http-equiv" in values:
            self.errors.append("meta http-equiv is forbidden")
        if tag == "style":
            self._inside_style = True
        for name, value in normalized:
            if name.startswith("on"):
                self.errors.append(f"event-handler attribute is forbidden: {tag}[{name}]")
            if name in {"srcset", "poster", "data", "xlink:href", "background"}:
                self.errors.append(f"unsupported resource attribute: {tag}[{name}]")
            if name == "style":
                self.css.append(value)

        if tag == "img":
            src = values.get("src")
            if not src:
                self.errors.append("img without a non-empty src")
            else:
                self.images.append(src)
        elif "src" in values:
            self.errors.append(f"src is only allowed on img, found: {tag}[src]")

        if "href" in values:
            self.hrefs.append((tag, values["href"]))
            if tag != "a":
                self.errors.append(f"href is only allowed on a, found: {tag}[href]")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style":
            self._inside_style = False

    def handle_data(self, data: str) -> None:
        if self._inside_style:
            self.css.append(data)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)


def _audit_resources(document: str) -> ResourceAuditParser:
    parser = ResourceAuditParser()
    parser.feed(document)
    parser.close()
    _verify_css_is_offline("\n".join(parser.css))
    if parser.errors:
        raise ValueError("; ".join(parser.errors))
    return parser


def _verify_css_is_offline(css: str) -> None:
    """Reject every CSS form that can reference a non-embedded resource.

    CSS escapes are intentionally unsupported so escaped spellings cannot hide
    resource functions or URL schemes from this small stdlib-only verifier.
    """

    if "\\" in css:
        raise ValueError("CSS escapes are unsupported in a standalone report")
    without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL).lower()
    forbidden = {
        "@import": "CSS import",
        "image-set": "CSS image-set",
        "image(": "CSS image function",
        "cross-fade(": "CSS cross-fade function",
        "src(": "CSS source function",
        "url": "CSS url function",
        "http:": "HTTP CSS reference",
        "https:": "HTTPS CSS reference",
        "ftp:": "FTP CSS reference",
        "file:": "file CSS reference",
        "data:": "data CSS reference",
        "//": "protocol-relative CSS reference",
    }
    for token, label in forbidden.items():
        if token in without_comments:
            raise ValueError(f"{label} is forbidden in a standalone report")


def _validate_png(payload: bytes, label: str) -> None:
    """Validate a bounded, non-interlaced PNG through decoded scanlines."""

    if len(payload) > 50 * 1024 * 1024:
        raise ValueError(f"PNG exceeds the 50 MiB safety limit: {label}")
    if not payload.startswith(PNG_SIGNATURE):
        raise ValueError(f"invalid PNG signature: {label}")

    pos = len(PNG_SIGNATURE)
    first_chunk = True
    ihdr: tuple[int, int, int, int] | None = None
    idat_parts: list[bytes] = []
    seen_iend = False

    while pos < len(payload):
        if len(payload) - pos < 12:
            raise ValueError(f"truncated PNG chunk: {label}")
        length = struct.unpack(">I", payload[pos : pos + 4])[0]
        kind = payload[pos + 4 : pos + 8]
        data_start = pos + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise ValueError(f"PNG chunk exceeds file bounds: {label}")
        if not re.fullmatch(rb"[A-Za-z]{4}", kind):
            raise ValueError(f"invalid PNG chunk type: {label}")

        data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"PNG chunk CRC mismatch: {label}")

        if first_chunk and kind != b"IHDR":
            raise ValueError(f"PNG does not start with IHDR: {label}")
        first_chunk = False

        if kind == b"IHDR":
            if ihdr is not None or length != 13:
                raise ValueError(f"invalid or duplicate PNG IHDR: {label}")
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", data)
            )
            if not width or not height or width > 20000 or height > 20000:
                raise ValueError(f"PNG dimensions are outside safety bounds: {label}")
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if color_type not in valid_depths or bit_depth not in valid_depths[color_type]:
                raise ValueError(f"invalid PNG color type or bit depth: {label}")
            if compression != 0 or filtering != 0 or interlace != 0:
                raise ValueError(f"unsupported PNG encoding mode: {label}")
            ihdr = (width, height, bit_depth, color_type)
        elif kind == b"IDAT":
            if ihdr is None:
                raise ValueError(f"PNG IDAT precedes IHDR: {label}")
            idat_parts.append(data)
        elif kind == b"IEND":
            if length != 0 or not idat_parts:
                raise ValueError(f"invalid PNG IEND or missing IDAT: {label}")
            seen_iend = True
            pos = crc_end
            break

        pos = crc_end

    if ihdr is None or not seen_iend or pos != len(payload):
        raise ValueError(f"PNG is incomplete or has trailing data: {label}")

    width, height, bit_depth, color_type = ihdr
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    row_bytes = (width * channels * bit_depth + 7) // 8
    expected_raw_size = height * (row_bytes + 1)
    if expected_raw_size > 200 * 1024 * 1024:
        raise ValueError(f"decoded PNG exceeds the 200 MiB safety limit: {label}")

    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(b"".join(idat_parts), expected_raw_size + 1)
    raw += decompressor.flush()
    if (
        not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
        or len(raw) != expected_raw_size
    ):
        raise ValueError(f"PNG scanline stream is invalid: {label}")
    if any(raw[offset] > 4 for offset in range(0, expected_raw_size, row_bytes + 1)):
        raise ValueError(f"PNG contains an invalid scanline filter: {label}")


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _verify_standalone(document: str, expected_images: int) -> None:
    audit = _audit_resources(document)
    sources = audit.images
    if len(sources) != expected_images:
        raise ValueError(f"expected {expected_images} embedded sources, found {len(sources)}")
    for src in sources:
        prefix = "data:image/png;base64,"
        if not src.startswith(prefix):
            raise ValueError(f"non-embedded resource dependency remains: {src[:120]}")
        payload = base64.b64decode(src[len(prefix) :], validate=True)
        _validate_png(payload, "embedded image")

    for _, href in audit.hrefs:
        parsed = urlsplit(html.unescape(href).strip())
        if href.startswith("#") or parsed.scheme in {"http", "https", "mailto", "tel"}:
            continue
        raise ValueError(f"local hyperlink dependency remains: {href}")



def build(input_html: Path, output_html: Path) -> tuple[int, int, list[str]]:
    input_html = input_html.resolve()
    output_html = output_html.resolve()
    asset_root = input_html.parent.resolve()
    source = input_html.read_text(encoding="utf-8")

    source_audit = _audit_resources(source)
    regex_sources = [match.group(2) for match in IMG_RE.finditer(source)]
    if regex_sources != source_audit.images:
        raise ValueError(
            "input image serialization is unsupported; refusing a partial embed"
        )

    embedded_paths: list[str] = []

    def embed_image(match: re.Match[str]) -> str:
        src = html.unescape(match.group(2))
        parsed = urlsplit(src)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError(f"image src must be a plain local path: {src}")

        asset = (asset_root / unquote(parsed.path)).resolve()
        if not _is_within(asset, asset_root):
            raise ValueError(f"image escapes the report directory: {src}")
        payload = asset.read_bytes()
        _validate_png(payload, src)

        encoded = base64.b64encode(payload).decode("ascii")
        embedded_paths.append(src)
        return f'{match.group(1)}data:image/png;base64,{encoded}{match.group(3)}'

    standalone = IMG_RE.sub(embed_image, source)

    stripped_links = 0

    def strip_local_anchor(match: re.Match[str]) -> str:
        nonlocal stripped_links
        href = html.unescape(match.group(2)).strip()
        parsed = urlsplit(href)
        if href.startswith("#") or parsed.scheme in {"http", "https", "mailto", "tel"}:
            return match.group(0)
        stripped_links += 1
        label = match.group(4)
        return (
            '<span title="该补充材料未包含在本独立展示文件中">'
            f"{label}（项目内补充材料）</span>"
        )

    standalone = ANCHOR_RE.sub(strip_local_anchor, standalone)

    manifest = "\n".join(f"  {item}" for item in embedded_paths)
    marker = (
        "\n<!-- standalone-bundle\n"
        f"embedded_png_count={len(embedded_paths)}\n"
        f"stripped_local_link_count={stripped_links}\n"
        f"{manifest}\n"
        "-->\n"
    )
    standalone = standalone.replace("</html>", f"{marker}</html>")

    _verify_standalone(standalone, len(embedded_paths))
    output_html.write_text(standalone, encoding="utf-8")
    return len(embedded_paths), stripped_links, embedded_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_html", type=Path)
    parser.add_argument("output_html", type=Path)
    args = parser.parse_args()

    count, stripped, _ = build(args.input_html, args.output_html)
    size = args.output_html.stat().st_size
    print(
        f"wrote {args.output_html.resolve()} "
        f"({size} bytes, {count} embedded PNGs, {stripped} local links stripped, "
        "standalone verified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
