"""Offline read-only browser check and portable archive; no model requests."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
VIEW = HERE / "B001_COUNTERQUESTION_REVIEW_v2.html"
DEST = HERE.parent / "B001_COUNTERQUESTION_20260925.zip"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(browser_only=False):
    if DEST.exists() and not browser_only:
        raise FileExistsError("Never overwrite a previous delivery archive")
    errors, network = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("request", lambda req: network.append(req.url) if req.url.startswith(("http://", "https://")) else None)
        page.goto(VIEW.as_uri(), wait_until="load")
        images = page.locator("img").evaluate_all("xs=>xs.map(x=>({complete:x.complete,width:x.naturalWidth,height:x.naturalHeight,embedded:x.src.startsWith('data:image/jpeg;base64,')}))")
        if len(images) != 1 or not all(x["complete"] and x["width"] > 0 and x["embedded"] for x in images):
            raise ValueError("Original embedded chart did not load")
        page.screenshot(path=str(HERE / "view_top_v2.png"), full_page=False)
        headings = page.locator("h1,h2,h3").all_text_contents()
        page.locator("details").evaluate_all("xs=>xs.forEach(x=>x.open=true)")
        text = page.locator("body").inner_text()
        if any(word not in text for word in ("q1", "q2", "q3", "counterquestions", "verification")):
            raise ValueError("Missing report/record content")
        layout = page.evaluate("({scroll:document.documentElement.scrollWidth,viewport:window.innerWidth})")
        if layout["scroll"] > layout["viewport"] + 2:
            raise ValueError("Horizontal report overflow")
        page.locator("img").screenshot(path=str(HERE / "view_chart_v2.png"))
        browser.close()
    if errors or network:
        raise ValueError("Offline viewer errors or external requests")
    receipt = {"status": "PASS", "images": images, "headings": headings,
               "javascript_errors": errors, "external_requests": network, "html_sha256": sha(VIEW),
               "model_calls": 0, "business_browser_actions": 0,
               "layout": layout, "scope": "local report rendering only, not GUI task execution"}
    (HERE / "browser_check_v2.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if browser_only:
        print(json.dumps(receipt, ensure_ascii=False))
        return
    files = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or any(part in {"__pycache__", ".pytest_cache", "prepared"} for part in path.relative_to(HERE).parts):
            continue
        if path.name in {"PACKAGE_INDEX.json", "PACKAGE_CHECK.json"}:
            continue
        if path.suffix in {".json", ".jsonl", ".md", ".py", ".html", ".xml", ".txt"}:
            content = path.read_bytes()
            if re.search(rb"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9_-]{16,}", content, re.I):
                raise ValueError("Possible credential; archive not created: " + str(path.relative_to(HERE)))
        files.append(path)
    index = [{"path": path.relative_to(HERE).as_posix(), "sha256": sha(path), "bytes": path.stat().st_size} for path in files]
    index_path = HERE / "PACKAGE_INDEX.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(DEST, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files + [index_path]:
            archive.write(path, HERE.name + "/" + path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(DEST) as archive:
        if archive.testzip() is not None or archive.read(HERE.name + "/" + VIEW.name) != VIEW.read_bytes():
            raise ValueError("Archive integrity failure")
    result = {"status": "PASS", "archive": str(DEST), "files": len(files) + 1,
              "bytes": DEST.stat().st_size, "sha256": sha(DEST), "viewer_byte_identity": True}
    (HERE / "PACKAGE_CHECK.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-only", action="store_true")
    main(parser.parse_args().browser_only)
