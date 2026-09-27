"""Render predeclared candidate dashboards for offline eligibility inspection.

This script never calls a model or scorer and does not inspect prior model-run
outputs.  It records the actual safe-shell image geometry at the fixed stage-two
viewport so candidate readability is not inferred from source-image dimensions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .runner import BROWSER_LAUNCH_ARGS, RELEASE_ROOT, REPOSITORY_ROOT, managed_shell
from .safe_shell import build_shell_bundle


DEFAULT_CANDIDATES = (
    "env001",
    "env025",
    "pub010",
    "env008",
    "b035",
    "pub020",
    "pub023",
    "pub024",
    "b012",
    "b013",
    "b015",
    "env006",
    "env021",
    "env026",
)


def load_release_rows() -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for condition in ("official140", "clean140"):
        split = RELEASE_ROOT / "splits" / condition
        for path in split.glob("*_tasks.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                rows[(condition, str(row["task_slug"]))] = row
    return rows


def make_contact_sheet(items: list[dict[str, Any]], output: Path) -> None:
    panels: list[Image.Image] = []
    for item in items:
        image = Image.open(REPOSITORY_ROOT / item["screenshot"]).convert("RGB")
        image.thumbnail((620, 450))
        panel = Image.new("RGB", (640, 490), "white")
        panel.paste(image, ((640 - image.width) // 2, 30))
        ImageDraw.Draw(panel).text(
            (8, 8), f"{item['slug']} / {item['condition']}", fill="black"
        )
        panels.append(panel)
    sheet = Image.new("RGB", (1280, ((len(panels) + 1) // 2) * 490), (230, 230, 230))
    for index, panel in enumerate(panels):
        sheet.paste(panel, ((index % 2) * 640, (index // 2) * 490))
    sheet.save(output, quality=90)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser-executable", type=Path, required=True)
    parser.add_argument("--tasks", default=",".join(DEFAULT_CANDIDATES))
    args = parser.parse_args()

    slugs = [value.strip() for value in args.tasks.split(",") if value.strip()]
    rows = load_release_rows()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    audit: list[dict[str, Any]] = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(args.browser_executable.resolve()),
            args=list(BROWSER_LAUNCH_ARGS),
        )
        try:
            for slug in slugs:
                for condition in ("official140", "clean140"):
                    raw_task = rows[(condition, slug)]
                    bundle = build_shell_bundle(
                        raw_task, task_alias="candidate", repository_root=REPOSITORY_ROOT
                    )
                    with managed_shell(
                        bundle.public_task,
                        bundle.chart_path,
                        output / f"{slug}_{condition}_unused_receipts.jsonl",
                    ) as shell:
                        page = browser.new_page(viewport={"width": 1440, "height": 1100})
                        try:
                            page.goto(
                                f"{shell.base_url}/task/candidate/dashboard",
                                wait_until="networkidle",
                            )
                            chart = page.locator("img.chart")
                            rendered_box = chart.bounding_box()
                            natural = chart.evaluate(
                                "(element) => ({width: element.naturalWidth, "
                                "height: element.naturalHeight, complete: element.complete})"
                            )
                            target = output / f"{slug}_{condition}.png"
                            page.screenshot(path=str(target), full_page=True)
                            audit.append(
                                {
                                    "slug": slug,
                                    "condition": condition,
                                    "source": bundle.chart_path.relative_to(REPOSITORY_ROOT).as_posix(),
                                    "natural": natural,
                                    "rendered_box": rendered_box,
                                    "screenshot": target.relative_to(REPOSITORY_ROOT).as_posix(),
                                }
                            )
                        finally:
                            page.close()
        finally:
            browser.close()

    (output / "render_audit.json").write_text(
        json.dumps(
            {
                "model_calls": 0,
                "dashboard_navigations": len(audit),
                "viewport": [1440, 1100],
                "items": audit,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    make_contact_sheet(audit, output / "contact_sheet.jpg")
    print(json.dumps({"captured": len(audit), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
