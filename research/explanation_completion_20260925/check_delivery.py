"""Offline wire, browser and package checks. Never sends model requests."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def dump(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)

def audit(run):
    run = Path(run).absolute()
    summary, ledger = read(run / "summary.json"), read(run / "budget.json")
    prompts = read(run / "prompt_templates.json")
    records, attempts = [], []
    for request in sorted(run.glob("cases/*/*/round_001/request.json")):
        folder, task, stage = request.parent, request.parents[2].name, request.parents[1].name
        payload = read(request)
        content = payload["messages"][1]["content"]
        context = json.loads(content[0]["text"])
        inputs = read(run / "cases" / task / "inputs.json")
        image = next(x for x in content if x["type"] == "image_url")["image_url"]["url"]
        chart = base64.b64decode(image.split(",", 1)[1])
        raw_chart = (run / "cases" / task / "chart.jpeg").read_bytes()
        match = (payload["messages"][0]["content"] == prompts[stage]
                 and context == read(folder.parent / "input_context.json") and chart == raw_chart)
        if stage in ("questions", "supplement"):
            match = match and context["initial_arguments"]["chains"] == inputs["base_arguments"]["chains"]
            match = match and context["initial_arguments"]["rules"] == inputs["base_arguments"]["rules"]
        if stage == "verification":
            match = match and "counterquestions" not in context and "question_responses" not in context["arguments"]
        forbidden = {"gold", "ground_truth", "correct_value", "misleader_type", "evaluation_hidden_from_agent",
                     "base_proposal", "verification_raw", "source_sha256"}
        def no_private(value):
            if isinstance(value, dict):
                return not (set(value) & forbidden) and all(no_private(v) for v in value.values())
            return all(no_private(v) for v in value) if isinstance(value, list) else True
        match = match and no_private(context)
        records.append({"task_id": task, "stage": stage, "wire_matches_saved_context_and_prompt": match,
                        "original_image_bytes": chart == raw_chart,
                        "initial_chain_count": len(context.get("initial_arguments", {}).get("chains", []))})
        attempts += [read(p) for p in sorted(folder.glob("attempt_*.json"))]
    result = {"verdict": "PASS" if all(r["wire_matches_saved_context_and_prompt"] for r in records)
              and len(attempts) == ledger["request_attempts"] == summary["request_attempts"]
              and all(summary["source_preservation"].values()) and all(summary["runtime_source_preservation"].values()) else "FAIL",
              "requests": records, "attempts": attempts, "request_attempts": len(attempts),
              "cost": ledger["estimated_ledger_usd"], "actual_invoice": None,
              "scope": "wire/provenance checks only; no semantic correctness or coverage verdict"}
    dump(HERE / "WIRE_AUDIT.json", result)
    print(json.dumps({k: result[k] for k in ("verdict", "request_attempts", "cost")}))

def browser(view_dir=None):
    from playwright.sync_api import sync_playwright
    view_dir = Path(view_dir or HERE).absolute()
    target = view_dir / "EXPLANATION_COMPLETION_REVIEW.html"
    errors, network = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda req: network.append(req.url) if req.url.startswith(("http:", "https:")) else None)
        page.goto(target.as_uri(), wait_until="load")
        page.screenshot(path=str(view_dir / "VIEW_TOP.png"))
        images = page.locator("main img").evaluate_all("es=>es.map(e=>({loaded:e.complete&&e.naturalWidth>0,embedded:e.src.startsWith('data:image/')}))")
        page.locator("details").evaluate_all("es=>es.forEach(e=>e.open=true)")
        dimensions = page.evaluate("({scroll:document.documentElement.scrollWidth,width:innerWidth})")
        browser.close()
    result = {"verdict": "PASS" if len(images) == 3 and all(i["loaded"] and i["embedded"] for i in images)
              and not errors and not network and dimensions["scroll"] == dimensions["width"] else "FAIL",
              "images": images, "errors": errors, "network_requests": network, "dimensions": dimensions,
              "business_browser_actions": 0, "model_calls": 0}
    dump(view_dir / "BROWSER_CHECK.json", result)
    print(json.dumps(result))

def package():
    target = HERE.parent / "EXPLANATION_COMPLETION_20260925.zip"
    excluded = {"__pycache__", ".pytest_cache", "prepared", "prepared_final"}
    files = sorted(p for p in HERE.rglob("*") if p.is_file() and not excluded.intersection(p.relative_to(HERE).parts))
    pattern = re.compile(rb"sk-[A-Za-z0-9_-]{18,}")
    leaked = [str(p) for p in files if p.suffix in {".py", ".json", ".md", ".html", ".txt"} and pattern.search(p.read_bytes())]
    if leaked:
        raise ValueError("Credential-like strings detected; package withheld")
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, HERE.name + "/" + path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(target) as archive:
        error = archive.testzip()
    result = {"archive": str(target), "files": len(files), "integrity_error": error,
              "credential_like_hits": len(leaked), "bytes": target.stat().st_size,
              "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    dump(HERE / "PACKAGE_CHECK.json", result)
    print(json.dumps(result))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["audit", "browser", "package"])
    parser.add_argument("--run", type=Path, default=HERE / "run")
    parser.add_argument("--view-dir", type=Path, default=HERE)
    args = parser.parse_args()
    if args.mode == "audit":
        audit(args.run)
    elif args.mode == "browser":
        browser(args.view_dir)
    else:
        package()
