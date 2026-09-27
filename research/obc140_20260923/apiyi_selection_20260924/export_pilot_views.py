"""Export per-model two-task pilot JSON and offline HTML views.

The canonical 140-slot run exports are read-only inputs. This script copies the
complete b001/pub013 task records into a derived two-task JSON and delegates HTML
rendering to the existing parent render_viewer.py/template without modifying it.
No API, browser, GPU, or network access is used.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
import render_viewer


MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.4-mini")
TASKS = ("b001", "pub013")
PHASES = ("proposal", "generation", "verification", "translation")
VIEWS = HERE / "views"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def read_source(model):
    if model not in MODELS:
        raise ValueError("Model outside frozen pilot")
    path = HERE / "runs" / model / "review_data.json"
    raw = path.read_bytes()
    data = render_viewer.validate_catalog(json.loads(raw.decode("utf-8-sig")))
    return path, raw, data


def selected_tasks(data):
    indexed = {}
    for task in data["tasks"]:
        slug = task["task_slug"]
        if slug in TASKS:
            if slug in indexed:
                raise ValueError("Duplicate selected task: " + slug)
            indexed[slug] = task
    missing = [slug for slug in TASKS if slug not in indexed]
    if missing:
        raise ValueError("Selected tasks missing: " + ", ".join(missing))
    # Fixed task order is part of the pilot; every field is copied unchanged.
    return [copy.deepcopy(indexed[slug]) for slug in TASKS]


def stage_status_counts(tasks, phase):
    return dict(Counter(task.get("status", {}).get(phase, "not_run") for task in tasks))


def build_summary(tasks, source_summary):
    summary = {
        "total_tasks": len(tasks),
        "proposed": sum(task.get("status", {}).get("proposal") == "completed" for task in tasks),
        "generated": sum(task.get("status", {}).get("generation") == "completed" for task in tasks),
        "verified": sum(task.get("status", {}).get("verification") == "completed" for task in tasks),
        "translated": sum(task.get("status", {}).get("translation") == "completed" for task in tasks),
        "all_four_stages_complete": sum(
            all(task.get("status", {}).get(phase) == "completed" for phase in PHASES)
            for task in tasks
        ),
        "phase_status_counts": {phase: stage_status_counts(tasks, phase) for phase in PHASES},
    }
    # These are run-level facts, not recomputed task-content claims.
    for key in ("request_attempts", "browser_operations", "blocked_reason", "run_status"):
        if key in source_summary:
            summary[key] = copy.deepcopy(source_summary[key])
    return summary


def derive(model, source_path, source_raw, source):
    tasks = selected_tasks(source)
    derived = copy.deepcopy(source)
    derived["title"] = model + "『2任务选型小样本』"
    derived["summary"] = build_summary(tasks, source.get("summary", {}))
    derived["tasks"] = tasks
    derived["derived_view"] = {
        "kind": "apiyi_two_task_model_selection_view",
        "model": model,
        "derived_scope": "one_model_two_fixed_development_tasks_b001_pub013",
        "selected_task_slugs": list(TASKS),
        "derived_task_count": len(tasks),
        "parent_prepared_task_slots": len(source["tasks"]),
        "parent_source_path": str(source_path.resolve()),
        "parent_source_sha256": sha256(source_raw),
        "parent_source_generated_at": source.get("generated_at"),
        "content_policy": "complete_existing_task_records_only_no_cross_model_merge_no_content_repair",
        "scope_notice": "This is a two-task development sample, not six independent tasks and not a completed 140-task run.",
    }
    validate_derived(model, source, derived)
    return derived


def validate_derived(model, source, derived):
    if derived.get("title") != model + "『2任务选型小样本』":
        raise ValueError("Pilot title mismatch")
    if derived.get("summary", {}).get("total_tasks") != 2 or len(derived.get("tasks", [])) != 2:
        raise ValueError("Derived view must contain exactly two tasks")
    if [task.get("task_slug") for task in derived["tasks"]] != list(TASKS):
        raise ValueError("Derived task order/scope mismatch")
    source_by_slug = {task["task_slug"]: task for task in source["tasks"]}
    for task in derived["tasks"]:
        if task != source_by_slug[task["task_slug"]]:
            raise ValueError("Selected task content was altered: " + task["task_slug"])
    expected = build_summary(derived["tasks"], source.get("summary", {}))
    if derived["summary"] != expected:
        raise ValueError("Derived summary is not computed from the two selected records")
    provenance = derived.get("derived_view", {})
    if provenance.get("model") != model or provenance.get("derived_task_count") != 2:
        raise ValueError("Derived provenance mismatch")


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def export_model(model, rendered_at=None):
    source_path, source_raw, source = read_source(model)
    derived = derive(model, source_path, source_raw, source)
    json_path = VIEWS / (model + ".json")
    html_path = VIEWS / (model + ".html")
    json_text = json.dumps(derived, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    atomic_write(json_path, json_text)
    html_text, render_meta = render_viewer.build_html(json_path, rendered_at=rendered_at)
    atomic_write(html_path, html_text)

    # Post-write safety/fidelity checks over primary artifacts.
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    validate_derived(model, source, saved)
    if source_path.read_bytes() != source_raw:
        raise RuntimeError("Canonical run export changed during derived export; rerun after it is stable")
    if render_meta["task_count"] != 2 or render_meta["chart_warnings"]:
        raise ValueError("Rendered pilot must contain two readable local chart assets")
    if source_raw == json_path.read_bytes():
        raise ValueError("Derived JSON unexpectedly aliases the canonical 140-slot export")
    return {
        "model": model,
        "source": str(source_path),
        "parent_source_sha256": sha256(source_raw),
        "json": str(json_path.resolve()),
        "json_sha256": sha256(json_path.read_bytes()),
        "html": str(html_path.resolve()),
        "html_sha256": sha256(html_path.read_bytes()),
        "tasks": list(TASKS),
        "task_count": 2,
        "all_four_stages_complete": saved["summary"]["all_four_stages_complete"],
        "rendered_at": render_meta["rendered_at"],
        "render_safety_check": "PASS",
        "independent_html_review": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", choices=MODELS,
                        help="Export one model; repeat as needed. Default: all frozen models.")
    args = parser.parse_args()
    models = tuple(args.model) if args.model else MODELS
    results = [export_model(model) for model in models]
    print(json.dumps({"exported": results,
                      "notice": "Derived two-task views only; no independent HTML review claimed."},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
