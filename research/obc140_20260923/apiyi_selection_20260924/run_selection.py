"""Bounded APIYI development panel, reusing the previously audited public pipeline."""
import argparse
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent
sys.path.insert(0, str(PANEL))
import run_panel as runner
from panel_core import read, dump, PHASES, PanelAPI, PersistentBudget, ServiceStop

MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.4-mini")
TASKS = ("b001", "pub013")


def configuration(model):
    if model not in MODELS:
        raise ValueError("Model outside fixed comparison")
    result = read(PANEL / "config.json")
    result.update(protocol="apiyi_two_task_model_selection_20260924",
                  endpoint="https://api.apiyi.com/v1/chat/completions", model=model,
                  proxy=None, max_attempts_per_call=1, max_request_attempts=8,
                  selection_tasks=list(TASKS), selection_models=list(MODELS),
                  parent_run="runs/obc140_v4_20260923",
                  sampling_scope="two_known_development_tasks_not_full140")
    return result


def run(model, task, stop_after=None):
    if model not in MODELS or task not in TASKS:
        raise ValueError("Outside frozen panel")
    config = configuration(model)
    output = HERE / "runs" / model
    created = not output.exists()
    catalog = runner.initialize(output, PANEL, config, resume=not created)
    if created:
        shutil.copyfile(__file__, output / "runtime_source" / "run_selection.py")
        shutil.copyfile(HERE / "PLAN.md", output / "PLAN_snapshot.md")
    elif (output / "runtime_source" / "run_selection.py").read_bytes() != Path(__file__).read_bytes():
        raise ValueError("Pilot entrypoint changed; preserve old run")
    state = read(output / "run_state.json")
    if state.get("blocked_reason"):
        raise ServiceStop("prior_service_block_requires_review")
    # A provider quota/auth failure blocks the complete pilot, not just one alias.
    for other in MODELS:
        previous = read(HERE / "runs" / other / "run_state.json", {})
        if previous.get("blocked_reason"):
            raise ServiceStop("another_pilot_run_has_service_block")
    state.update(status="running", planned_tasks=2, planned_logical_calls=8,
                 prepared_catalog_slots=140, selected_task_slugs=list(TASKS), updated_at=runner.now())
    dump(output / "run_state.json", state)
    case_folder = output / "tasks" / task
    record = read(case_folder / "record.json")
    budget = PersistentBudget(output / "budget.json", config)
    try:
        api = PanelAPI(config, budget)
        for phase in PHASES:
            phase_index = PHASES.index(phase)
            if any(record["status"][p] != "completed" for p in PHASES[:phase_index]):
                break
            print(model, task, phase, record["status"][phase], flush=True)
            runner.execute_phase(record, phase, case_folder, api, config)
            if record["status"][phase] != "completed" or phase == stop_after:
                break
        state.update(status="paused_after_bounded_check", updated_at=runner.now())
    except ServiceStop as exc:
        state.update(status="blocked", blocked_reason=exc.category, updated_at=runner.now())
        print("GLOBAL_STOP", exc.category, flush=True)
    finally:
        dump(output / "run_state.json", state)
        runner.export_review(output, PANEL, catalog)
    result = {"model": model, "task": task, "status": read(case_folder / "record.json")["status"],
              "model_request_attempts": budget.value["request_attempts"], "scope": "two_task_development_only"}
    dump(output / "last_selected_case_summary.json", result)
    print(result, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--task", choices=TASKS, required=True)
    parser.add_argument("--stop-after", choices=PHASES)
    args = parser.parse_args()
    run(args.model, args.task, args.stop_after)
