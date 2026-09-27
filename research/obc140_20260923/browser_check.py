"""Offline Edge acceptance of the generated viewer; no model or task actions."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def check(html, output):
    html, output = Path(html).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, unexpected_network = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
            headless=True)
        context = browser.new_context(viewport={"width": 1500, "height": 1080}, accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("request", lambda req: unexpected_network.append(req.url)
                if req.url.startswith(("http://", "https://")) else None)
        page.goto(html.as_uri(), wait_until="load")
        page.wait_for_selector(".task-row")
        assert page.locator(".task-row").count() == 140
        assert "商业" in page.locator(".task-heading").inner_text()
        page.screenshot(path=str(output / "viewer_desktop.png"), full_page=False)
        for domain, count in [("business47", 47), ("environment35", 35), ("health19", 19), ("public39", 39)]:
            page.select_option("#domain-filter", domain)
            assert page.locator(".task-row").count() == count
        page.select_option("#domain-filter", "")
        for slug in ("pub013", "b046", "health004"):
            page.fill("#search", slug)
            assert page.locator(".task-row").count() == 1
            assert page.locator(".task-code").inner_text() == slug
            assert page.locator(".chart-button img").evaluate("n => n.complete && n.naturalWidth > 0")
        page.fill("#search", "pub013")
        page.locator(".chart-button").click()
        assert page.locator("#chart-dialog").evaluate("n => n.open")
        page.screenshot(path=str(output / "viewer_chart_zoom.png"), full_page=False)
        page.click("#zoom-close")
        page.select_option("#note-status", "needs_review")
        page.fill("#note-text", "QA 临时笔记：检查导出和导入，不是人工审核结论。")
        with page.expect_download() as download_info:
            page.click("#export-notes")
        download_path = output / "qa_notes_export.json"
        download_info.value.save_as(str(download_path))
        exported = json.loads(download_path.read_text(encoding="utf-8"))
        assert exported["notes"]["pub013"]["status"] == "needs_review"
        page.fill("#note-text", "")
        page.set_input_files("#notes-file", str(download_path))
        page.wait_for_function("document.getElementById('note-text').value.includes('QA 临时笔记')")
        page.click('[data-language="zh"]')
        assert page.locator("body").get_attribute("data-language") == "zh"
        page.fill("#search", "")
        page.select_option("#status-filter", "generated")
        expected = page.locator("#review-data").evaluate(
            "n => JSON.parse(n.textContent).catalog.tasks.filter(t=>t.status.generation==='completed').length")
        assert page.locator(".task-row").count() == expected
        page.select_option("#status-filter", "")
        page.set_viewport_size({"width": 760, "height": 1000})
        page.screenshot(path=str(output / "viewer_narrow.png"), full_page=False)
        assert not errors, errors
        assert not unexpected_network, unexpected_network
        browser.close()
    result = {"status": "PASS", "tasks": 140, "domain_counts": [47, 35, 19, 39],
              "checks": ["file_url_load", "all_tasks", "domain_filter", "task_search", "original_chart",
                         "zoom", "notes_export_import", "language_switch", "generation_filter", "narrow_view"],
              "javascript_errors": errors, "external_network_requests": unexpected_network,
              "qa_only": True, "model_requests": 0, "business_browser_operations": 0}
    (output / "browser_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("html")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    check(args.html, args.output)
