"""Build a new runtime-aligned fixed140 input bundle without model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import shutil

from public_inputs import VERSION, extract, verify_bindings, advisory_flags

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
OLD = HERE.parent / "obc140_20260923"
FLOW = WORKSPACE / ".aris/task_flows_20260924"
OLD_RUN = OLD / "terra140_native_zh_20260924"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError("Existing prepared output differs; use a new output directory: " + str(path))
    else:
        path.write_bytes(data)


def copy_same(source, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if digest(source) != digest(dest):
            raise FileExistsError("Refuse overwrite: " + str(dest))
    else:
        shutil.copyfile(source, dest)


def build(output):
    output = Path(output).resolve()
    if output == OLD.resolve() or OLD.resolve() in output.parents:
        raise ValueError("New protocol must be outside old experiment directory")
    catalog = read(OLD / "catalog.json")
    source_audit = read(FLOW / "RUNTIME_AUDIT.json")
    dom_root = Path(source_audit["receipt_dir"])
    runtime = {row["slug"]: row for row in read(FLOW / "RUNTIME_TASKS.json") if row["arm"] == "official140"}
    if len(catalog["tasks"]) != 140 or len(runtime) != 140:
        raise ValueError("Expected original fixed140 scope")
    entries, audit_rows, frozen_inputs = [], [], {}
    # Plan every projection before writing so missing DOMs cannot look complete.
    prepared = []
    for old_entry in catalog["tasks"]:
        slug, domain, alias = (old_entry[key] for key in ("task_slug", "domain", "alias"))
        pages, sources = {}, {}
        for page in ("home", "dashboard", "form"):
            path = dom_root / (domain + "_official140") / (slug + "_" + page + ".html")
            pages[page] = path.read_text(encoding="utf-8")
            sources[page] = path
            frozen_inputs[str(path)] = digest(path)
        public, bindings = extract(pages, alias)
        count = verify_bindings(public, bindings, pages)
        original_runtime = runtime[slug]
        if public["user_goal"] != original_runtime["goal"] or public["page_title"] != original_runtime["title"]:
            raise ValueError("DOM disagrees with independent runtime inventory: " + slug)
        if public["option_labels"] != [row["label"] for row in original_runtime["options"]]:
            raise ValueError("DOM option labels/order disagree with runtime inventory: " + slug)
        before = read(OLD / old_entry["public_file"])
        chart = OLD / old_entry["chart_file"]
        original_chart = FLOW / "snapshot" / original_runtime["spec"]["chart_asset"]["figure_path"]
        if digest(chart) != digest(original_chart):
            raise ValueError("Original chart copies differ: " + slug)
        frozen_inputs[str(chart)] = digest(chart)
        frozen_inputs[str(OLD / old_entry["public_file"])] = digest(OLD / old_entry["public_file"])
        frozen_inputs[str(OLD_RUN / "run/tasks" / slug / "record.json")] = digest(OLD_RUN / "run/tasks" / slug / "record.json")
        changes = [{"field": key, "old": before.get(key), "new": public.get(key)}
                   for key in sorted(set(before) | set(public)) if before.get(key) != public.get(key)]
        flags = advisory_flags(public)
        entry = {"task_slug": slug, "domain": domain, "alias": alias,
                 "public_file": "tasks/%s/public.json" % slug,
                 "chart_file": "tasks/%s/chart%s" % (slug, chart.suffix.lower()),
                 "source_file": "tasks/%s/provenance.json" % slug,
                 "old_results_reusable": before == public,
                 "model_status": "not_run"}
        audit_row = {"task_slug": slug, "domain": domain, "public_before": before, "public_after": public,
                     "changed_fields": [row["field"] for row in changes], "changes": changes,
                     "advisory_flags": flags, "bindings_checked": count,
                     "model_status": "not_run", "old_results_reusable": before == public,
                     "rerun_reason": "public_context_changed" if changes else "exact_public_context_unchanged"}
        prepared.append((entry, audit_row, sources, chart, bindings))
    source_files = [OLD / "catalog.json", FLOW / "RUNTIME_TASKS.json", FLOW / "RUNTIME_AUDIT.json",
                    OLD_RUN / "OBC140_TERRA_ZH_REVIEW.html", OLD_RUN / "REPORT.md",
                    OLD / "OBC140_TERRA_NATIVE_ZH_20260924.zip"]
    for path in source_files:
        frozen_inputs[str(path)] = digest(path)
    for entry, audit_row, sources, chart, bindings in prepared:
        slug = entry["task_slug"]
        put(output / entry["public_file"], audit_row["public_after"])
        copy_same(chart, output / entry["chart_file"])
        for page, path in sources.items():
            copy_same(path, output / "sources" / slug / (page + ".html"))
        put(output / entry["source_file"], {"protocol": VERSION,
            "origin": "archived_original_nonreview_HTML_GET_responses",
            "not_an_agent_trajectory": True, "source_pages": {page: str(path) for page, path in sources.items()},
            "field_bindings": bindings, "original_chart_sha256": digest(chart),
            "public_sha256": digest(output / entry["public_file"]),
            "old_record": str(OLD_RUN / "run/tasks" / slug / "record.json")})
        entries.append(entry)
        audit_rows.append(audit_row)
    counts = Counter(field for row in audit_rows for field in row["changed_fields"])
    new_catalog = {"protocol": VERSION, "base_task_count": 140, "condition": "official140", "tasks": entries}
    summary = {"task_count": 140, "changed_tasks": sum(bool(row["changes"]) for row in audit_rows),
               "changed_field_counts": dict(sorted(counts.items())),
               "same_goal_and_title": sum(not ({"page_title", "user_goal"} & set(row["changed_fields"])) for row in audit_rows),
               "rerun_required": [row["task_slug"] for row in audit_rows if row["changes"]],
               "advisory_flagged_tasks": [row["task_slug"] for row in audit_rows if row["advisory_flags"]],
               "all_inputs_extracted_from_nonreview_DOM": True,
               "all_images_unchanged": True, "model_calls": 0, "api_translation_calls": 0,
               "browser_business_actions": 0, "old_results_imported_as_new": 0,
               "meaning": "Input fidelity checks, not blanket no-hint certification or model performance"}
    put(output / "catalog.json", new_catalog)
    put(output / "input_comparison.json", {"protocol": VERSION, "summary": summary, "tasks": audit_rows})
    put(output / "source_preservation.json", frozen_inputs)
    put(output / "rerun_manifest.json", {"protocol": VERSION, "status": "prepared_not_run",
        "selection_basis": "all changed public inputs, independent of model outputs or gold",
        "tasks": summary["rerun_required"], "reuse_allowed": [],
        "normal_logical_calls_upper_bound": 3 * len(summary["rerun_required"]),
        "fixed_sanity_tasks": ["b001", "pub003", "env008"],
        "sanity_reason": "title/goal leakage, goal/completion-label leakage, unchanged-goal contextual alignment; not chosen for outcome",
        "translation": "native Chinese presentation only; no additional APIYI calls",
        "real_execution_requires": "confirmed new batch budget and available authorized credential"})
    return summary


def check_preservation(output):
    expected = read(Path(output) / "source_preservation.json")
    changed = [name for name, value in expected.items() if digest(name) != value]
    if changed:
        raise ValueError("Preserved source changed: " + repr(changed))
    return {"checked_files": len(expected), "changed_files": []}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "prepared")
    parser.add_argument("--check-preservation", action="store_true")
    args = parser.parse_args()
    result = check_preservation(args.output) if args.check_preservation else build(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
