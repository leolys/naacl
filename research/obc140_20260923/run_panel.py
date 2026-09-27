"""Resumable serial 140-task static OBC generation; no browser or submission."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

from panel_core import (HERE, PREVIOUS, PHASES, GENERATOR, VERIFIER, PROPOSAL_PROMPT,
                        TRANSLATION_PROMPT, PanelAPI, PersistentBudget, ServiceStop,
                        UnknownRequestOutcome,
                        common_context, digest, dump, read, translation_items, validate_stage)


def now():
    return datetime.now(timezone.utc).isoformat()


def sources():
    return [HERE / "panel_core.py", HERE / "run_panel.py", HERE / "prepare_catalog.py",
            PREVIOUS / "engine.py", PREVIOUS / "format_replay.py",
            PREVIOUS / "adapter.py", PREVIOUS / "prompts_observation_v4.py"]


def initial_record(entry, data_root):
    public = read(data_root / entry["public_file"])
    common_context(public)  # strict online-key check before making a run
    return {"task_slug": entry["task_slug"], "domain": entry["domain"],
            "chart_file": str((data_root / entry["chart_file"]).resolve()), "public_task": public,
            "status": {phase: "not_run" for phase in PHASES}, "stages": {},
            "proposal": None, "generated": None, "normalized": None,
            "verification": None, "rule_state": [], "translations": {"items": {}},
            "translation_items": [], "error": None,
            "provenance": {"protocol": "static_chart_task_review", "history": [],
                           "business_actions_executed": False, "submit_executed": False}}


def initialize(output, data_root, config, resume=False):
    catalog = read(data_root / "catalog.json")
    if (catalog.get("base_task_count") != config["expected_tasks"] or len(catalog["tasks"]) != 140
            or len({e["task_slug"] for e in catalog["tasks"]}) != 140
            or catalog.get("condition") != config["condition"]):
        raise ValueError("fixed140 original catalog mismatch")
    if config["concurrency"] != 1 or config["business_actions_enabled"] or config["gpu_enabled"]:
        raise ValueError("only serial static generation is authorized by this runner")
    hashes = {p.name: digest(p) for p in sources()}
    if output.exists():
        if not resume:
            raise FileExistsError("Run exists; use explicit resume, never overwrite")
        runtime = read(output / "runtime.json")
        if read(output / "config_snapshot.json") != config or runtime["source_sha256"] != hashes:
            raise ValueError("config/source changed; cannot silently resume different protocol")
        if runtime["catalog_sha256"] != digest(data_root / "catalog.json"):
            raise ValueError("catalog changed since run start")
    else:
        output.mkdir(parents=True, exist_ok=False)
        dump(output / "config_snapshot.json", config)
        dump(output / "catalog_snapshot.json", catalog)
        dump(output / "runtime.json", {"created_at": now(), "python": sys.version,
             "source_sha256": hashes, "catalog_sha256": digest(data_root / "catalog.json"),
             "model_identity_scope": "requested and gateway-reported alias only"})
        for p in sources():
            (output / "runtime_source").mkdir(exist_ok=True)
            shutil.copyfile(p, output / "runtime_source" / p.name)
        for entry in catalog["tasks"]:
            dump(output / "tasks" / entry["task_slug"] / "record.json", initial_record(entry, data_root))
        dump(output / "run_state.json", {"status": "prepared", "blocked_reason": None,
             "created_at": now(), "planned_tasks": 140, "planned_logical_calls": 560})
    # Compare all current inputs to immutable initial records before any new request.
    for entry in catalog["tasks"]:
        record = read(output / "tasks" / entry["task_slug"] / "record.json")
        if record["public_task"] != read(data_root / entry["public_file"]):
            raise ValueError("prepared public input changed")
        offline = read(data_root / entry["offline_file"])
        expected = offline.get("provenance", {}).get("chart_sha256")
        if expected and digest(record["chart_file"]) != expected:
            raise ValueError("chart differs from prepared provenance")
    return catalog


def phase_input(phase, record):
    common = common_context(record["public_task"])
    images = [("chart_1", record["chart_file"])]
    if phase == "proposal":
        return PROPOSAL_PROMPT, {k: v for k, v in common.items() if k != "interpretation_rules"}, images
    if phase == "generation":
        return GENERATOR, {**common, "proposal": record["proposal"]}, images
    if phase == "verification":
        return VERIFIER, {**common, "arguments": record["normalized"]}, images
    if phase == "translation":
        record["translation_items"] = translation_items(record)
        return TRANSLATION_PROMPT, {"items": record["translation_items"]}, []
    raise ValueError("unknown phase")


def execute_phase(record, phase, case_folder, api, config, retry_service=False):
    status = record["status"][phase]
    previous = record["stages"].get(phase, {})
    if status in {"completed", "invalid", "failed"}:
        return
    if status == "blocked" and not retry_service:
        raise ServiceStop(previous.get("error_category", "service_restoration_required"))
    phase_root = case_folder / phase
    # Crash after sending a request is NOT permission to silently resample.
    if status == "running":
        folder = case_folder / previous["folder"]
        if (folder / "parsed.json").is_file():
            value = read(folder / "parsed.json")
        else:
            record["status"][phase] = "failed"
            record["stages"][phase]["error_category"] = "interrupted_execution_outcome_unknown"
            record["error"] = "interrupted_execution_outcome_unknown"
            dump(case_folder / "record.json", record)
            return
    else:
        folder = phase_root / ("round_%03d" % (len(list(phase_root.glob("round_*"))) + 1))
        prompt, context, images = phase_input(phase, record)
        record["status"][phase] = "running"
        record["stages"][phase] = {"folder": folder.relative_to(case_folder).as_posix(), "started_at": now()}
        dump(case_folder / "record.json", record)
        try:
            value = api.call(folder, record["task_slug"], phase, prompt, context, images)
        except ServiceStop as exc:
            record["status"][phase] = "blocked"
            record["stages"][phase]["error_category"] = exc.category
            record["error"] = exc.category
            dump(case_folder / "record.json", record)
            raise
        except Exception as exc:
            record["status"][phase] = "failed"
            category = ("request_outcome_unknown_no_auto_retry" if isinstance(exc, UnknownRequestOutcome)
                        else "model_request_or_parse_failed")
            record["stages"][phase]["error_category"] = category
            record["stages"][phase]["exception_type"] = type(exc).__name__
            record["error"] = category
            dump(case_folder / "record.json", record)
            return
    try:
        additions = validate_stage(phase, value, record, config)
        record.update(additions)
        record["status"][phase] = "completed"
        record["stages"][phase]["finished_at"] = now()
        record["error"] = next((record["stages"].get(p, {}).get("error_category")
            for p in PHASES if record["status"][p] in {"failed", "invalid", "blocked"}), None)
        dump(folder / "validated.json", additions)
    except Exception as exc:
        record["status"][phase] = "invalid"
        record["stages"][phase]["error_category"] = "structural_validation_failed"
        record["stages"][phase]["exception_type"] = type(exc).__name__
        record["error"] = "structural_validation_failed"
        record[phase + "_invalid_raw"] = value
    dump(case_folder / "record.json", record)


def export_review(output, data_root, catalog):
    """Human-facing offline merge; never fed back into any online phase."""
    tasks = []
    for entry in catalog["tasks"]:
        row = read(output / "tasks" / entry["task_slug"] / "record.json")
        offline = read(data_root / entry["offline_file"])
        row["offline_metadata"] = {k: offline.get(k) for k in (
            "original_mechanism", "audited_mechanism", "original_plot", "audit_note", "review_records", "evidence_limit_flags")}
        tasks.append(row)
    state = read(output / "run_state.json")
    budget = read(output / "budget.json", {"request_attempts": 0})
    summary = {"total_tasks": len(tasks), "generated": sum(t["status"]["generation"] == "completed" for t in tasks),
               "verified": sum(t["status"]["verification"] == "completed" for t in tasks),
               "translated": sum(t["status"]["translation"] == "completed" for t in tasks),
               "proposed": sum(t["status"]["proposal"] == "completed" for t in tasks),
               "request_attempts": budget["request_attempts"], "browser_operations": 0,
               "blocked_reason": state.get("blocked_reason"), "run_status": state["status"],
               "all_four_stages_complete": sum(all(t["status"][p] == "completed" for p in PHASES) for t in tasks),
               "phase_status_counts": {p: dict(Counter(t["status"][p] for t in tasks)) for p in PHASES}}
    review = {"schema_version": "obc140_review_v1", "title": "140任务 O／B／C 与竞争解释：中英人工阅览",
              "generated_at": now(), "summary": summary, "tasks": tasks,
              "protocol": "static original-chart task review; no web actions or submission"}
    dump(output / "review_data.json", review)
    dump(output / "summary.json", summary)
    return summary


def run(output, data_root, config, resume=False, service_restored=False, limit=None,
        stop_after=None, prepare_only=False, api_factory=PanelAPI):
    output, data_root = Path(output).resolve(), Path(data_root).resolve()
    catalog = initialize(output, data_root, config, resume)
    state = read(output / "run_state.json")
    if prepare_only:
        return export_review(output, data_root, catalog)
    if state.get("blocked_reason") and not service_restored:
        raise ServiceStop("service_restoration_must_be_confirmed_before_resume")
    budget = PersistentBudget(output / "budget.json", config)
    state.update(status="running", blocked_reason=None, updated_at=now())
    dump(output / "run_state.json", state)
    seen = 0
    try:
        api = api_factory(config, budget)
        for entry in catalog["tasks"]:
            case_folder = output / "tasks" / entry["task_slug"]
            record = read(case_folder / "record.json")
            if all(record["status"][p] == "completed" for p in PHASES):
                continue
            if limit is not None and seen >= limit:
                break
            seen += 1
            for phase in PHASES:
                if phase == "generation" and record["status"]["proposal"] != "completed":
                    continue
                if phase == "verification" and record["status"]["generation"] != "completed":
                    continue
                # Translate obtainable public/returned records even when a non-service stage failed.
                print(entry["task_slug"], phase, record["status"][phase], flush=True)
                execute_phase(record, phase, case_folder, api, config, retry_service=service_restored)
                if stop_after == phase:
                    break
            export_review(output, data_root, catalog)
        if limit is None and stop_after is None:
            interim = export_review(output, data_root, catalog)
            status = "completed" if interim["all_four_stages_complete"] == len(catalog["tasks"]) else "finished_with_incomplete_stages"
        else:
            status = "paused_after_bounded_check"
        state.update(status=status, updated_at=now())
    except ServiceStop as exc:
        state.update(status="blocked", blocked_reason=exc.category, updated_at=now())
        print("GLOBAL_STOP", exc.category, flush=True)
    finally:
        dump(output / "run_state.json", state)
        summary = export_review(output, data_root, catalog)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--data", default=str(HERE))
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--service-restored", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--stop-after", choices=PHASES)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    run(args.output, args.data, read(args.config), args.resume, args.service_restored,
        args.limit, args.stop_after, args.prepare_only)


if __name__ == "__main__":
    main()
