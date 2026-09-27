"""Local-only rendering check. Never sends model or network requests."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--channel", default=None, help="Use an already installed browser, e.g. msedge")
    args = parser.parse_args()
    page_path = args.page.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    network, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=args.channel)
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
        page.on("request", lambda r: network.append(r.url) if r.url.startswith(("http:", "https:")) else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(page_path.as_uri(), wait_until="load")
        page.screenshot(path=str(out / "overview.png"))
        image_records = []
        for img in page.locator("img").all():
            img.scroll_into_view_if_needed()
            img.evaluate("img => img.decode()")
            image_records.append(img.evaluate("i => ({alt:i.alt, loaded:i.complete && i.naturalWidth>0, width:i.naturalWidth, height:i.naturalHeight})"))
        missing_anchors = page.locator('a[href^="#"]').evaluate_all(
            "links => links.map(x => x.getAttribute('href').slice(1)).filter(id => id && !document.getElementById(id))")
        page.locator("#case-b001-initial").scroll_into_view_if_needed()
        page.screenshot(path=str(out / "b001_initial.png"))
        page.locator("#case-pub013-supplement").scroll_into_view_if_needed()
        page.screenshot(path=str(out / "pub013_failure.png"))
        desktop_overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#overview").scroll_into_view_if_needed()
        page.screenshot(path=str(out / "mobile_overview.png"))
        mobile_overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        receipt = {"page": str(page_path), "browser_version": browser.version, "channel": args.channel,
                   "image_count": len(image_records), "images": image_records,
                   "network_requests": network, "page_errors": errors,
                   "missing_anchor_targets": missing_anchors,
                   "desktop_horizontal_overflow": desktop_overflow,
                   "mobile_horizontal_overflow": mobile_overflow,
                   "scope": "local presentation QA only, no model calls or business browser transitions"}
        receipt["passed"] = (len(image_records) == 3 and all(i["loaded"] for i in image_records)
                             and not any((network, errors, missing_anchors, desktop_overflow, mobile_overflow)))
        (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
