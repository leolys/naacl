"""Two-case Terra citation compatibility validation; at most eight fresh requests."""
import argparse
from collections import Counter
from contextlib import contextmanager
import copy
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent
sys.path.insert(0, str(PANEL))
import run_panel as runner
import panel_core as core
import citation_adapter

TASKS = ("b001", "pub013")
OUT = HERE / "run"
OLD = PANEL / "apiyi_selection_20260924" / "runs"


def configuration():
    result = core.read(OLD / "gpt-5.6-terra" / "config_snapshot.json")
    result.update(protocol="terra_public_task_citation_v1_20260924",
                  max_request_attempts=8, max_attempts_per_call=1,
                  expected_tasks=2, source_catalog_tasks=140,
                  selection_models=["gpt-5.6-terra"], selection_tasks=list(TASKS),
                  parent_run=str(OLD / "gpt-5.6-terra"),
                  sampling_scope="two_known_tasks_citation_compatibility_only",
                  citation_adapter=citation_adapter.VERSION)
    return result


def sources():
    return runner.sources() + [Path(__file__), HERE / "citation_adapter.py", HERE / "PLAN.md"]


def initialize():
    config = configuration()
    catalog = core.read(PANEL / "catalog.json")
    selected = [entry for entry in catalog["tasks"] if entry["task_slug"] in TASKS]
    if len(selected) != 2 or {entry["task_slug"] for entry in selected} != set(TASKS):
        raise ValueError("fixed two-case catalog unavailable")
    hashes = {path.name: core.digest(path) for path in sources()}
    if OUT.exists():
        if core.read(OUT / "config_snapshot.json") != config:
            raise ValueError("changed config cannot resume")
        if core.read(OUT / "runtime.json")["source_sha256"] != hashes:
            raise ValueError("changed source cannot resume")
        if core.read(OUT / "catalog_snapshot.json") != selected:
            raise ValueError("changed task manifest cannot resume")
    else:
        OUT.mkdir(parents=True, exist_ok=False)
        core.dump(OUT / "config_snapshot.json", config)
        core.dump(OUT / "catalog_snapshot.json", selected)
        core.dump(OUT / "runtime.json", {"created_at": runner.now(), "python": sys.version,
                  "source_sha256": hashes, "model_identity_scope": "requested and gateway alias only"})
        (OUT / "runtime_source").mkdir()
        for path in sources():
            shutil.copyfile(path, OUT / "runtime_source" / path.name)
        for entry in selected:
            record = runner.initial_record(entry, PANEL)
            core.dump(OUT / "tasks" / entry["task_slug"] / "record.json", record)
        core.dump(OUT / "run_state.json", {"status": "prepared", "blocked_reason": None,
                  "planned_tasks": 2, "planned_logical_calls": 8, "adapter": citation_adapter.VERSION})
    for entry in selected:
        record = core.read(OUT / "tasks" / entry["task_slug"] / "record.json")
        if record["public_task"] != core.read(PANEL / entry["public_file"]):
            raise ValueError("public input changed")
        core.engine.assert_public(record["public_task"])
        expected = core.read(PANEL / entry["offline_file"])["provenance"]["chart_sha256"]
        if core.digest(record["chart_file"]) != expected:
            raise ValueError("chart changed")
    return config


@contextmanager
def selected_validator():
    # Only this serial process sees the replacement; original files stay untouched.
    previous = runner.validate_stage
    runner.validate_stage = citation_adapter.validate_stage
    try:
        yield
    finally:
        runner.validate_stage = previous


def export():
    tasks = [core.read(OUT / "tasks" / task / "record.json") for task in TASKS]
    budget = core.read(OUT / "budget.json", {"request_attempts": 0})
    summary = {"total_tasks": 2, "request_attempts": budget["request_attempts"],
               "browser_operations": 0, "protocol": "new_fresh_compatibility_run_not_old_result_repair",
               "all_four_stages_complete": sum(all(row["status"][p] == "completed"
                    for p in core.PHASES) for row in tasks),
               "phase_status_counts": {p: dict(Counter(row["status"][p] for row in tasks)) for p in core.PHASES}}
    for field, phase in (("proposed", "proposal"), ("generated", "generation"),
                         ("verified", "verification"), ("translated", "translation")):
        summary[field] = sum(row["status"][phase] == "completed" for row in tasks)
    core.dump(OUT / "summary.json", summary)
    core.dump(OUT / "review_data.json", {"schema_version": "obc140_review_v1",
        "title": "Terra 通用引用兼容验证 · 2 个开发任务", "generated_at": runner.now(),
        "summary": summary, "tasks": tasks,
        "protocol": "static four-stage fresh run; task evidence separate from visual evidence; no submission"})
    return summary


def replay_old():
    results = []
    for model in ("gpt-5.6-sol", "gpt-5.6-terra"):
        for task in TASKS:
            folder = OLD / model / "tasks" / task
            record = core.read(folder / "record.json")
            raw_path = folder / "verification" / "round_001" / "parsed.json"
            raw = core.read(raw_path)
            row = {"model": model, "task": task, "source": str(raw_path),
                   "source_sha256": core.digest(raw_path), "new_model_requests": 0}
            for name, validator in (("old", core.validate_stage), ("adapted", citation_adapter.validate_stage)):
                try:
                    value = validator("verification", copy.deepcopy(raw), copy.deepcopy(record), configuration())
                    row[name] = {"status": "accepted_by_schema", "result": value}
                except (ValueError, KeyError, TypeError) as error:
                    row[name] = {"status": "rejected_by_schema", "reason": str(error)}
            results.append(row)
    path = HERE / "offline_replay.json"
    if path.exists():
        raise FileExistsError("Preserve prior offline replay; do not overwrite")
    core.dump(path, {"mode": "deterministic_reinterpretation_not_new_model_output",
                    "adapter": citation_adapter.VERSION, "results": results, "model_requests": 0})
    print({"offline_replay_cases": len(results), "model_requests": 0})


def run(task):
    if task not in TASKS:
        raise ValueError("outside fixed tasks")
    config = initialize()
    state = core.read(OUT / "run_state.json")
    if state.get("blocked_reason"):
        raise core.ServiceStop("prior_service_block_requires_review")
    budget = core.PersistentBudget(OUT / "budget.json", config)
    folder = OUT / "tasks" / task
    record = core.read(folder / "record.json")
    state.update(status="running", current_task=task, updated_at=runner.now())
    core.dump(OUT / "run_state.json", state)
    try:
        api = core.PanelAPI(config, budget)
        with selected_validator():
            for index, phase in enumerate(core.PHASES):
                if any(record["status"][p] != "completed" for p in core.PHASES[:index]):
                    break
                print(task, phase, record["status"][phase], flush=True)
                runner.execute_phase(record, phase, folder, api, config)
                if record["status"][phase] != "completed":
                    break
        state.update(status="stopped_after_fixed_case", updated_at=runner.now())
    except core.ServiceStop as error:
        state.update(status="blocked", blocked_reason=error.category, updated_at=runner.now())
        print("GLOBAL_STOP", error.category, flush=True)
    finally:
        core.dump(OUT / "run_state.json", state)
        summary = export()
    print({"task": task, "status": record["status"], "attempts_total": summary["request_attempts"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", choices=TASKS)
    group.add_argument("--offline-replay", action="store_true")
    args = parser.parse_args()
    if args.offline_replay:
        replay_old()
    else:
        run(args.task)
