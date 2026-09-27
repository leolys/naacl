"""Offline wire audit and report rendering; never calls a tested model."""
from pathlib import Path
import argparse
import base64
import hashlib
import importlib.util
import json
import sys
import zipfile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import runner


def audit():
    run = HERE / "run"
    summary = runner.core.read(run / "summary.json")
    templates = runner.core.read(run / "prompt_templates.json")
    details, records = [], []
    for item in summary["cases"]:
        folder = run / "cases" / item["case_id"]
        record = runner.core.read(folder / "result.json")
        records.append(record)
        for stage in record["stages"]:
            request_path = folder / stage / "round_001/request.json"
            if not request_path.exists():
                details.append({"case": item["case_id"], "stage": stage, "request_archived": False})
                continue
            request = runner.core.read(request_path)
            messages = request["messages"]
            content = messages[1]["content"]
            context = json.loads(content[0]["text"])
            runner.public_inputs.assert_public(context)
            expected = runner.build_context(stage, record["inputs"], record)
            chart = folder / ("chart" + Path(record["inputs"]["chart_source"]).suffix)
            images = [c["image_url"]["url"] for c in content if c["type"] == "image_url"]
            row = {"case": item["case_id"], "stage": stage, "request_archived": True,
                "same_fixed_prompt": messages[0]["content"] == templates[stage],
                "actual_context_matches": context == expected,
                "one_unchanged_chart": len(images) == 1 and base64.b64decode(images[0].split(",", 1)[1]) == chart.read_bytes(),
                "private_key_guard": True,
                "model": request["model"], "temperature": request["temperature"], "max_tokens": request["max_tokens"]}
            if stage == "competitors":
                row["actual_questions_delivered"] = context["counterquestions"] == record["questions"]
            if stage == "verification":
                row["origin_fields_withheld"] = set(context) == {"task", "state", "history", "interpretation_rules", "arguments", "public_task_text_paths"}
            details.append(row)
    runtime = runner.core.read(run / "runtime.json")
    source_current = {p: runner.core.digest(p) == digest for p, digest in runtime["source_sha256"].items()}
    source_snapshot = {p: runner.core.digest(run / "runtime_source" / Path(p).relative_to(PROJECT)) == digest
                       for p, digest in runtime["source_sha256"].items()}
    checks = [v for row in details for v in row.values() if isinstance(v, bool)]
    preservation = [v for r in records for v in r["source_preservation"].values()]
    receipt = {"verdict": "PASS" if all(checks + preservation + list(source_current.values()) + list(source_snapshot.values())) else "FAIL",
        "scope": "wire/provenance integrity, not semantic validity", "requests_archived": len(details),
        "request_attempts": summary["request_attempts"], "checks": details,
        "current_runtime_sources_unchanged": source_current, "snapshots_match": source_snapshot,
        "all_original_sources_preserved": all(preservation), "new_model_calls": 0}
    runner.core.dump(HERE / "WIRE_AUDIT.json", receipt)
    runner.core.dump(HERE / "RESULTS_FULL.json", {"summary": summary, "records": records})
    print(json.dumps({k: receipt[k] for k in ("verdict", "requests_archived", "request_attempts")}, ensure_ascii=False))


def render():
    helper = PROJECT / ".agents/skills/render-html/scripts/render_html.py"
    spec = importlib.util.spec_from_file_location("cq_render_helper", helper)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    target = HERE / "COUNTERQUESTION_GENERAL_REVIEW.html"
    if target.exists():
        raise FileExistsError("Choose a new explicit render version, do not overwrite")
    source = HERE / "REPORT_ZH.md"
    code = module.main([str(source), "--out", str(target), "--offline", "--json", str(HERE / "RESULTS_FULL.json"),
                        "--title", "反问驱动竞争解释 · 六条件开发诊断", "--eyebrow", "证据优先 · 允许无竞争"])
    if code:
        raise RuntimeError("Renderer failed")
    view = target.read_text(encoding="utf-8")
    manifest = runner.core.read(HERE / "manifest.json")
    embedded = []
    for case in manifest["cases"]:
        suffix = Path(case["chart"]).suffix
        rel = "run/cases/" + case["case_id"] + "/chart" + suffix
        chart = HERE / rel
        marker = 'src="' + rel + '"'
        if view.count(marker) != 1:
            raise ValueError("Expected one chart in report: " + rel)
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        view = view.replace(marker, 'src="data:' + mime + ';base64,' + base64.b64encode(chart.read_bytes()).decode("ascii") + '"')
        embedded.append({"source": rel, "sha256": runner.core.digest(chart)})
    css = """<style>
    .layout {grid-template-columns:260px minmax(0,1fr)}
    main {min-width:0;overflow-wrap:anywhere}
    main img {display:block;width:100%;max-width:100%;height:auto}
    main h1 {font-size:28px;line-height:1.4;overflow-wrap:anywhere}
    main table {width:100%;table-layout:fixed}
    main td,main th,main code {overflow-wrap:anywhere;word-break:break-word}
    main pre {max-width:100%;white-space:pre-wrap}
    @media(max-width:900px){.layout{grid-template-columns:minmax(0,1fr)}}
    </style>"""
    target.write_text(view.replace("</head>", css + "\n</head>"), encoding="utf-8")
    runner.core.dump(HERE / "VIEW_PROVENANCE.json", {"source": str(source), "source_sha256": runner.core.digest(source),
        "result_sha256": runner.core.digest(HERE / "RESULTS_FULL.json"), "html_sha256": runner.core.digest(target),
        "embedded_original_images": embedded, "offline": True, "renderer": str(helper), "model_calls": 0})


def browser_check():
    from playwright.sync_api import sync_playwright
    target = HERE / "COUNTERQUESTION_GENERAL_REVIEW.html"
    errors, external = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("request", lambda req: external.append(req.url) if req.url.startswith(("http:", "https:")) else None)
        page.goto(target.as_uri(), wait_until="load")
        page.screenshot(path=str(HERE / "VIEW_TOP.png"))
        images = page.locator("main img").evaluate_all("els => els.map(e=>({loaded:e.complete&&e.naturalWidth>0,embedded:e.src.startsWith('data:image/'),width:e.naturalWidth,height:e.naturalHeight}))")
        page.locator("details").evaluate_all("els => els.forEach(e=>e.open=true)")
        dimensions = page.evaluate("({scroll:document.documentElement.scrollWidth,viewport:innerWidth})")
        browser.close()
    receipt = {"verdict": "PASS" if not errors and not external and len(images) == 6 and all(i["loaded"] and i["embedded"] for i in images) and dimensions["scroll"] == dimensions["viewport"] else "FAIL",
        "images": images, "js_errors": errors, "external_requests": external, "dimensions_all_details_open": dimensions,
        "business_browser_actions": 0, "model_calls": 0}
    runner.core.dump(HERE / "BROWSER_CHECK.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


def package():
    target = HERE.parent / "COUNTERQUESTION_GENERAL_20260925.zip"
    if target.exists():
        raise FileExistsError("Do not overwrite archive")
    exclude = {"prepared", "prepared_final", "__pycache__", ".pytest_cache"}
    files = sorted(p for p in HERE.rglob("*") if p.is_file() and not exclude.intersection(p.relative_to(HERE).parts))
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "counterquestion_general_20260925/" + path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
    runner.core.dump(HERE / "PACKAGE_CHECK.json", {"archive": str(target), "files": len(files), "integrity_error": bad,
        "bytes": target.stat().st_size, "sha256": runner.core.digest(target)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["audit", "render", "browser", "package"])
    args = parser.parse_args()
    {"audit": audit, "render": render, "browser": browser_check, "package": package}[args.mode]()
