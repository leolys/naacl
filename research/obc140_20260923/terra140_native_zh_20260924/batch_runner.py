"""Frozen serial fixed-140 English O/B/C batch. Translation is a separate layer.

Preparation and tests do not read credentials or send requests. Only run() after
preparation constructs the API client. A crash leaves run.lock for manual audit;
never remove that lock or resend uncertain calls automatically.
"""
import argparse
import base64
from collections import Counter
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent
SOURCE_RUN = PANEL / "terra_citation_check_20260924" / "run"
sys.path.insert(0, str(PANEL))
sys.path.insert(0, str(SOURCE_RUN.parent))
import panel_core as core
import run_panel as parent
import citation_adapter
from budget import BudgetedPanelAPI, EstimatedBudget

PHASES = ("proposal", "generation", "verification")
REUSED = ("b001", "pub013")
OUT = HERE / "run"


class RunLock:
    def __init__(self, output):
        output = Path(output)
        self.path = output.with_name(output.name + ".lock")

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "created_at": parent.now(),
                           "note": "On crash, audit process and request artifacts before manual removal."}, handle)
        except FileExistsError as error:
            raise RuntimeError("runner lock exists; concurrent run or crash requires manual audit: " + str(self.path)) from error
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None:
            self.path.unlink()
        # An unexpected exception/interruption leaves diagnostic state on disk.


@contextmanager
def selected_validator():
    previous = parent.validate_stage
    parent.validate_stage = citation_adapter.validate_stage
    try:
        yield
    finally:
        parent.validate_stage = previous


def sources():
    return parent.sources() + [SOURCE_RUN.parent / "citation_adapter.py",
        PANEL / "apiyi_selection_20260924" / "analyze_usage.py",
        PANEL / "apiyi_selection_20260924" / "provider_rates.json",
        HERE / "batch_runner.py", HERE / "budget.py", HERE / "config.json"]


def source_key(path):
    return Path(path).relative_to(PANEL.parent).as_posix()


def check_config(config):
    exact = {"model": "gpt-5.6-terra", "endpoint": "https://api.apiyi.com/v1/chat/completions",
             "expected_tasks": 140, "concurrency": 1, "max_request_attempts": 450,
             "max_attempts_per_call": 3, "max_estimated_usd": 20,
             "attempt_reserve_usd": 0.2, "estimated_input_usd_per_m": 2.5,
             "estimated_output_usd_per_m": 12, "quality_retries": False,
             "api_phases": list(PHASES), "reused_tasks": list(REUSED),
             "business_actions_enabled": False, "gpu_enabled": False, "wandb": False,
             "translation_mode": "codex_native_separate_sidecar_no_api"}
    if any(config.get(key) != value for key, value in exact.items()):
        raise ValueError("configuration is outside authorized fixed batch")
    if set(config["phase_max_tokens"]) != set(PHASES):
        raise ValueError("only three API phases permitted")


def verified_reuse(entry, data_root, config):
    """Verify actual original requests, public input, image bytes and runtime code."""
    slug = entry["task_slug"]
    folder = SOURCE_RUN / "tasks" / slug
    source_path = folder / "record.json"
    original = core.read(source_path)
    prepared = parent.initial_record(entry, data_root)
    if original["public_task"] != prepared["public_task"]:
        raise ValueError("reused public input mismatch: " + slug)
    source_config = core.read(SOURCE_RUN / "config_snapshot.json")
    for key in ("condition", "model", "endpoint", "temperature", "competitors",
                "allow_trailing_json_closers", "cap_candidates_by_generation_order",
                "defense_prompt_profile", "citation_adapter", "concurrency"):
        if source_config[key] != config[key]:
            raise ValueError("reused config mismatch: " + key)
    source_runtime = core.read(SOURCE_RUN / "runtime.json")
    for name, expected in source_runtime["source_sha256"].items():
        if core.digest(SOURCE_RUN / "runtime_source" / name) != expected:
            raise ValueError("historical source snapshot changed: " + name)
    for path in parent.sources() + [SOURCE_RUN.parent / "citation_adapter.py"]:
        if core.digest(path) != source_runtime["source_sha256"][path.name]:
            raise ValueError("reused runtime differs from current code: " + path.name)
    chart_hash = core.digest(prepared["chart_file"])
    phase_files = {}
    for phase in PHASES:
        if original["status"][phase] != "completed":
            raise ValueError("reused phase is not completed")
        original_stage = original["stages"][phase]
        phase_folder = folder / original_stage["folder"]
        if phase_folder.resolve().parent != (folder / phase).resolve():
            raise ValueError("invalid reused stage folder")
        prompt, context, images = parent.phase_input(phase, prepared)
        request = core.read(phase_folder / "request.json")
        archived_context = core.read(phase_folder / "context.json")
        content = request["messages"][1]["content"]
        if (request["model"] != config["model"] or request["temperature"] != config["temperature"]
                or request["max_tokens"] != config["phase_max_tokens"][phase]
                or request["messages"][0] != {"role": "system", "content": prompt}
                or len(request["messages"]) != 2 or len(content) != 3
                or request["messages"][1]["role"] != "user"
                or content[0]["type"] != "text" or json.loads(content[0]["text"]) != context
                or content[1] != {"type": "text", "text": "Observation chart_1"}
                or content[2]["type"] != "image_url"
                or archived_context["context"] != context
                or archived_context["phase"] != phase
                or len(archived_context["images"]) != 1
                or archived_context["images"][0]["sha256"] != chart_hash
                or archived_context["images"][0]["ref"] != "chart_1"):
            raise ValueError("reused request/context mismatch: " + slug + "/" + phase)
        data_url = content[2]["image_url"]["url"]
        if hashlib.sha256(base64.b64decode(data_url.split(",", 1)[1], validate=True)).hexdigest() != chart_hash:
            raise ValueError("reused submitted image mismatch")
        raw = core.read(phase_folder / "parsed.json")
        additions = citation_adapter.validate_stage(phase, copy.deepcopy(raw), prepared, config)
        if core.read(phase_folder / "validated.json") != additions:
            raise ValueError("reused validation artifact mismatch")
        if any(original.get(key) != value for key, value in additions.items()):
            raise ValueError("reused record differs from phase artifacts")
        prepared.update(additions)
        prepared["status"][phase] = "completed"
        prepared["stages"][phase] = copy.deepcopy(original_stage)
        phase_files[phase] = {str(path.resolve()): core.digest(path)
                             for path in sorted(phase_folder.iterdir()) if path.is_file()}
    prepared["provenance"] = copy.deepcopy(original["provenance"])
    prepared["provenance"]["reuse"] = {
        "source_record": str(source_path.resolve()), "source_record_sha256": core.digest(source_path),
        "source_run": str(SOURCE_RUN.resolve()), "source_runtime": source_runtime,
        "source_config_sha256": core.digest(SOURCE_RUN / "config_snapshot.json"),
        "source_runtime_sha256": core.digest(SOURCE_RUN / "runtime.json"),
        "source_phase_files_sha256": phase_files, "phases": list(PHASES),
        "api_translation_imported": False, "new_api_requests": 0,
        "validation": "source snapshots, config, exact prompts, public context, image bytes and three stage results verified",
    }
    prepared["native_translation_status"] = "not_run"
    return prepared


def input_manifest(catalog, data_root):
    rows = []
    for entry in catalog["tasks"]:
        public_path, chart_path = data_root / entry["public_file"], data_root / entry["chart_file"]
        public = core.read(public_path)
        core.common_context(public)
        public_hash, chart_hash = core.digest(public_path), core.digest(chart_path)
        offline = core.read(data_root / entry["offline_file"])
        if (any(offline[key] != entry[key] for key in ("task_slug", "domain", "alias"))
                or public["task_alias"] != entry["alias"] or offline["condition"] != "official140"):
            raise ValueError("catalog/public/offline task identity mismatch")
        provenance = offline["provenance"]
        if provenance["public_sha256"] != public_hash:
            raise ValueError("public task differs from prepared dataset provenance")
        if provenance["chart_sha256"] != chart_hash:
            raise ValueError("chart differs from prepared dataset provenance")
        rows.append({"task_slug": entry["task_slug"], "public_path": str(public_path.resolve()),
                     "public_sha256": public_hash, "chart_path": str(chart_path.resolve()),
                     "chart_sha256": chart_hash})
    return rows


def initialize(output, data_root, config, resume=False):
    check_config(config)
    catalog = core.read(data_root / "catalog.json")
    if (catalog.get("schema_version") != "obc140_v1"
            or catalog["base_task_count"] != 140 or len(catalog["tasks"]) != 140
            or len({entry["task_slug"] for entry in catalog["tasks"]}) != 140
            or [entry["task_slug"] for entry in catalog["tasks"]]
               != sorted(entry["task_slug"] for entry in catalog["tasks"])
            or [entry["alias"] for entry in catalog["tasks"]]
               != ["task_%03d" % index for index in range(1, 141)]
            or catalog["condition"] != config["condition"]):
        raise ValueError("fixed original 140 task catalog mismatch")
    hashes = {source_key(path): core.digest(path) for path in sources()}
    inputs = input_manifest(catalog, data_root)
    reuse = {entry["task_slug"]: verified_reuse(entry, data_root, config)
             for entry in catalog["tasks"] if entry["task_slug"] in REUSED}
    if set(reuse) != set(REUSED):
        raise ValueError("both reused cases must be present")
    if output.exists():
        if not resume:
            raise FileExistsError("Run exists; explicit --resume required")
        runtime = core.read(output / "runtime.json")
        if (core.read(output / "config_snapshot.json") != config
                or runtime["source_sha256"] != hashes
                or core.read(output / "catalog_snapshot.json") != catalog
                or core.read(output / "inputs_snapshot.json") != inputs):
            raise ValueError("frozen config, runtime or inputs changed; audit required")
        for key, expected in hashes.items():
            if core.digest(output / "runtime_source" / key) != expected:
                raise ValueError("run source snapshot changed")
        for slug, row in reuse.items():
            stored = core.read(output / "tasks" / slug / "record.json")
            if stored != row:
                raise ValueError("reused English record changed; keep native translations in sidecar")
    else:
        output.mkdir(parents=True, exist_ok=False)
        core.dump(output / "config_snapshot.json", config)
        core.dump(output / "catalog_snapshot.json", catalog)
        core.dump(output / "inputs_snapshot.json", inputs)
        core.dump(output / "runtime.json", {"created_at": parent.now(), "python": sys.version,
            "source_sha256": hashes, "catalog_sha256": core.digest(data_root / "catalog.json"),
            "source_run": str(SOURCE_RUN.resolve()),
            "model_identity_scope": "requested and gateway-reported alias only"})
        for path in sources():
            destination = output / "runtime_source" / source_key(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        for entry in catalog["tasks"]:
            slug = entry["task_slug"]
            case_folder = output / "tasks" / slug
            row = reuse.get(slug) or parent.initial_record(entry, data_root)
            row["native_translation_status"] = "not_run"
            core.dump(case_folder / "record.json", row)
            if slug in reuse:
                for phase in PHASES:
                    shutil.copytree(SOURCE_RUN / "tasks" / slug / phase, case_folder / phase)
        core.dump(output / "run_state.json", {"status": "prepared", "blocked_reason": None,
            "created_at": parent.now(), "planned_tasks": 140, "reused_tasks": list(REUSED),
            "planned_new_tasks": 138, "planned_logical_calls": 414,
            "api_translation_enabled": False, "browser_operations": 0})
    for entry in catalog["tasks"]:
        row = core.read(output / "tasks" / entry["task_slug"] / "record.json")
        if (row["public_task"] != core.read(data_root / entry["public_file"])
                or Path(row["chart_file"]).resolve() != (data_root / entry["chart_file"]).resolve()
                or row["status"]["translation"] != "not_run"
                or row.get("translations") != {"items": {}}):
            raise ValueError("English input/translation separation changed")
    return catalog


def eligible(record):
    states = [record["status"][phase] for phase in PHASES]
    return not (all(status == "completed" for status in states)
                or any(status in {"invalid", "failed"} for status in states))


def export(output, catalog):
    rows = [core.read(output / "tasks" / entry["task_slug"] / "record.json") for entry in catalog["tasks"]]
    budget = core.read(output / "budget.json", {"request_attempts": 0, "estimated_ledger_usd": 0, "events": []})
    state = core.read(output / "run_state.json")
    summary = {"total_tasks": len(rows), "reused_tasks": list(REUSED),
        "request_attempts": budget["request_attempts"], "estimated_ledger_usd": budget["estimated_ledger_usd"],
        "actual_charge_usd": None, "estimate_is_invoice": False,
        "unresolved_usage_attempts": sum(event["accounting_status"] != "usage_reconciled" for event in budget["events"]),
        "browser_operations": 0, "api_translation_requests": 0, "translated": 0,
        "run_status": state["status"], "blocked_reason": state.get("blocked_reason"),
        "all_three_stages_complete": sum(all(row["status"][p] == "completed" for p in PHASES) for row in rows),
        "terminal_failed_tasks": sum(any(row["status"][p] in {"failed", "invalid"} for p in PHASES) for row in rows),
        "pending_tasks": sum(eligible(row) for row in rows),
        "phase_status_counts": {phase: dict(Counter(row["status"][phase] for row in rows)) for phase in core.PHASES}}
    for field, phase in (("proposed", "proposal"), ("generated", "generation"), ("verified", "verification")):
        summary[field] = sum(row["status"][phase] == "completed" for row in rows)
    core.dump(output / "summary.json", summary)
    core.dump(output / "review_data.json", {"schema_version": "obc140_review_v1",
        "title": "Terra 140 static O/B/C: English source records", "generated_at": parent.now(),
        "summary": summary, "tasks": rows,
        "protocol": "static chart/task only; three API stages; native Chinese separate; no browser or submission"})
    return summary


def run(output=OUT, data_root=PANEL, config=None, resume=False, limit=None,
        prepare_only=False, api_factory=BudgetedPanelAPI):
    output, data_root = Path(output).resolve(), Path(data_root).resolve()
    config = core.read(HERE / "config.json") if config is None else config
    if limit is not None and limit < 1:
        raise ValueError("--limit must be positive and counts newly attempted cases")
    with RunLock(output):
        catalog = initialize(output, data_root, config, resume)
        budget = EstimatedBudget(output / "budget.json", config)
        state = core.read(output / "run_state.json")
        if prepare_only:
            return export(output, catalog)
        if state.get("blocked_reason") or budget.value.get("blocked_reason"):
            # There is intentionally no flag that silently clears a quota/auth/budget stop.
            state.update(status="blocked", blocked_reason=state.get("blocked_reason") or budget.value["blocked_reason"])
            core.dump(output / "run_state.json", state)
            return export(output, catalog)
        seen = 0
        state.update(status="running", updated_at=parent.now())
        core.dump(output / "run_state.json", state)
        try:
            api = None
            with selected_validator():
                for entry in catalog["tasks"]:
                    folder = output / "tasks" / entry["task_slug"]
                    record = core.read(folder / "record.json")
                    if not eligible(record):
                        continue
                    if limit is not None and seen >= limit:
                        break
                    seen += 1
                    if api is None:
                        api = api_factory(config, budget)
                    for index, phase in enumerate(PHASES):
                        if any(record["status"][previous] != "completed" for previous in PHASES[:index]):
                            break
                        print(entry["task_slug"], phase, record["status"][phase], flush=True)
                        parent.execute_phase(record, phase, folder, api, config)
                        if record["status"][phase] != "completed":
                            break
                    export(output, catalog)
            interim = export(output, catalog)
            status = ("paused_after_bounded_check" if interim["pending_tasks"] else
                      "completed" if interim["all_three_stages_complete"] == 140 else "finished_with_terminal_failures")
            state.update(status=status, updated_at=parent.now(), last_invocation_new_cases=seen)
        except core.ServiceStop as error:
            state.update(status="blocked", blocked_reason=error.category, updated_at=parent.now())
            print("GLOBAL_STOP", error.category, flush=True)
        finally:
            budget.reconcile()
            core.dump(output / "run_state.json", state)
        return export(output, catalog)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not args.prepare_only and not OUT.exists():
        parser.error("first create frozen snapshots with --prepare-only")
    print(json.dumps(run(resume=args.resume, limit=args.limit, prepare_only=args.prepare_only), ensure_ascii=False))


if __name__ == "__main__":
    main()
