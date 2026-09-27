"""Render the new two-case results without changing canonical model records."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import render_viewer

LABELS = {"ref": "来源引用", "location": "来源内位置",
          "task_evidence": "公开任务文字引用（非图像观察）",
          "source_kind": "来源类型", "source_field": "公开字段位置",
          "source_text": "请求中实际公开字段原文",
          "binding_status": "来源绑定状态（不代表转述含义已验证）"}


def make(check_browser=False):
    destination = HERE / "TERRA_CITATION_REVIEW.html"
    provenance = render_viewer.render(HERE / "run" / "review_data.json", destination,
                                      field_labels=LABELS)
    (HERE / "view_provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    if check_browser:
        from playwright.sync_api import sync_playwright
        issues, external = [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True,
                executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 1080})
                page.on("pageerror", lambda error: issues.append(str(error)))
                page.on("request", lambda req: external.append(req.url)
                        if req.url.startswith(("http://", "https://")) else None)
                page.goto(destination.as_uri())
                assert page.locator(".task-row").count() == 2
                for task in ("b001", "pub013"):
                    page.fill("#search", task)
                    assert page.locator(".task-code").inner_text() == task
                    assert page.locator(".chart-button img").evaluate(
                        "n => n.complete && n.naturalWidth > 0")
                    page.click('[data-language="zh"]')
                    page.locator("#chains-panel").scroll_into_view_if_needed()
                    page.screenshot(path=str(HERE / ("view_" + task + ".png")))
                assert not issues, issues
                assert not external, external
            finally:
                browser.close()
        (HERE / "browser_check.json").write_text(json.dumps({"status": "PASS", "tasks": 2,
            "scope": "offline_reading_only", "javascript_errors": issues, "external_requests": external,
            "model_requests": 0, "business_actions": 0}, indent=2), encoding="utf-8")
    print(json.dumps({"html": str(destination), "provenance": provenance}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-check", action="store_true")
    make(parser.parse_args().browser_check)
