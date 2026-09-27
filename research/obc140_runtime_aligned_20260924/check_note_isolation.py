"""Headless offline reader check; no task browser or user browser profile used."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def main():
    catalog = json.loads((HERE / "prepared/catalog.json").read_text(encoding="utf-8"))
    suffix = "|".join(sorted(row["task_slug"] for row in catalog["tasks"]))
    old_key = "obc140-notes-v1:" + suffix
    new_key = "obc140-runtime-dom-v1-20260924-notes:" + suffix
    external = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True,
            executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
        try:
            page = browser.new_page()
            page.on("request", lambda request: external.append(request.url)
                    if request.url.startswith(("http://", "https://")) else None)
            page.goto((HERE / "OBC140_TERRA_ZH_REVIEW.html").as_uri() + "#b001")
            page.evaluate("([oldKey,newKey]) => { localStorage.removeItem(newKey); localStorage.setItem(oldKey,JSON.stringify({b001:{status:'unreviewed',text:'OLD_RUN_SENTINEL',updated_at:'test'}})); }", [old_key, new_key])
            page.reload()
            assert page.locator("#note-text").input_value() == ""
            page.locator("#note-text").fill("NEW_RUN_SENTINEL")
            page.reload()
            assert page.locator("#note-text").input_value() == "NEW_RUN_SENTINEL"
            persisted = page.evaluate("([oldKey,newKey]) => [JSON.parse(localStorage.getItem(oldKey)),JSON.parse(localStorage.getItem(newKey))]", [old_key, new_key])
            assert persisted[0]["b001"]["text"] == "OLD_RUN_SENTINEL"
            assert persisted[1]["b001"]["text"] == "NEW_RUN_SENTINEL"
            assert not external
        finally:
            browser.close()
    result = {"status": "PASS", "old_notes_not_inherited": True, "new_notes_persist": True,
              "old_notes_preserved": True, "external_requests": external,
              "scope": "isolated headless reader profile; not the user's browser; no business actions or model calls"}
    (HERE / "note_isolation_check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
