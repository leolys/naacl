"""Offline smoke check for the two-task model-selection reading views."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.4-mini")


def check():
    results = []
    output = HERE / "browser_qa"
    output.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
            headless=True)
        try:
            for model in MODELS:
                errors, network = [], []
                source = json.loads((HERE / "views" / (model + ".json")).read_text(encoding="utf-8"))
                records = {record["task_slug"]: record for record in source["tasks"]}
                context = browser.new_context(viewport={"width": 1500, "height": 1050})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: network.append(request.url)
                        if request.url.startswith(("http://", "https://")) else None)
                page.goto((HERE / "views" / (model + ".html")).as_uri())
                page.wait_for_selector(".task-row")
                assert page.locator(".task-row").count() == 2
                assert model in page.title()
                for task in ("b001", "pub013"):
                    page.fill("#search", task)
                    assert page.locator(".task-row").count() == 1
                    assert page.locator(".task-code").inner_text() == task
                    assert page.locator(".chart-button img").evaluate(
                        "n => n.complete && n.naturalWidth > 0")
                    if records[task]["status"]["generation"] == "completed":
                        assert page.locator("#chains-panel .chain").count() >= 1
                    else:
                        assert page.locator("#chains-panel .chain").count() == 0
                        assert page.locator("#chains-panel .empty").count() > 0
                    page.click('[data-language="zh"]')
                    assert page.locator("body").get_attribute("data-language") == "zh"
                    if records[task]["status"]["translation"] == "completed":
                        assert page.locator(".translated").count() > 0
                    else:
                        assert page.locator(".untranslated").count() > 0
                        assert page.locator(".original").count() > 0
                    page.locator(".chart-button").click()
                    assert page.locator("#chart-dialog").evaluate("n => n.open")
                    page.click("#zoom-close")
                    page.click('[data-language="en"]')
                    page.click('[data-language="zh"]')
                    page.screenshot(path=str(output / (model + "_" + task + ".png")))
                page.fill("#search", "")
                assert page.locator(".task-row").count() == 2
                page.set_viewport_size({"width": 760, "height": 1000})
                page.screenshot(path=str(output / (model + "_narrow.png")))
                assert not errors, errors
                assert not network, network
                results.append({"model": model, "status": "PASS", "tasks": 2,
                                "javascript_errors": errors, "network_requests": network})
                context.close()
            overview = browser.new_page(viewport={"width": 1500, "height": 1050})
            overview.goto((HERE / "SELECTION_REPORT_20260924.html").as_uri())
            assert "17" in overview.inner_text("body")
            assert overview.locator("table").count() >= 4
            overview.screenshot(path=str(output / "selection_report.png"))
            overview.close()
        finally:
            browser.close()
    report = {"scope": "offline_reading_ui_only_not_agent_experiment", "views": results,
              "model_requests": 0, "business_actions": 0,
              "checks": ["file_load", "two_tasks", "search", "embedded_images", "chains",
                         "Chinese_and_English", "zoom", "narrow_view", "no_network"]}
    (output / "browser_check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    check()
