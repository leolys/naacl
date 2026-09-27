"""Runtime-DOM public input adapter for the existing three-stage API pipeline.

prepare: archives PREPARED_NOT_SENT proposal wire bodies, never creates a client.
mock: synthetic three-stage fixtures using the unchanged real payload/validator.
live: needs the authorized config, matching explicit budget confirmation and
MODEL_API_KEY. No old chains reused. Preparation and mock never use credentials.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent / "obc140_20260923"
NATIVE = PANEL / "terra140_native_zh_20260924"
CITATION = PANEL / "terra_citation_check_20260924"
for path in (PANEL, NATIVE, CITATION, HERE):
    sys.path.insert(0, str(path))
import panel_core as core
import run_panel as parent
import citation_adapter
from budget import BudgetedPanelAPI, EstimatedBudget
from batch_runner import RunLock
from public_inputs import VERSION, PUBLIC_KEYS, assert_public

PHASES = ("proposal", "generation", "verification")
MOCK_SLUGS = ("b001", "pub003", "env008")


def check_config(config):
    expected = {"protocol": "runtime_dom_public_v1_three_static_api_stages",
        "condition": "official140", "expected_tasks": 140, "model": "gpt-5.6-terra",
        "live_enabled": True, "max_estimated_usd": 20, "max_request_attempts": 450,
        "endpoint": "https://api.apiyi.com/v1/chat/completions", "proxy": None,
        "temperature": 0, "phase_max_tokens": {"proposal": 700, "generation": 2200, "verification": 2200},
        "max_attempts_per_call": 3, "concurrency": 1, "competitors": 2,
        "defense_prompt_profile": "observation_boundary_v4", "citation_adapter": "public_task_citation_v1",
        "allow_trailing_json_closers": True, "cap_candidates_by_generation_order": True,
        "quality_retries": False, "reused_tasks": [], "api_phases": list(PHASES),
        "business_actions_enabled": False, "gpu_enabled": False, "wandb": False,
        "translation_mode": "codex_native_separate_sidecar_no_api",
        "attempt_reserve_usd": 0.2, "estimated_input_usd_per_m": 2.5, "estimated_output_usd_per_m": 12}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Fixed runtime-aligned protocol configuration differs")


def authorize_live(config, confirmed_budget):
    check_config(config)
    expected = (config["max_estimated_usd"], config["max_request_attempts"])
    if (config.get("live_enabled") is not True or min(expected) <= 0
            or confirmed_budget is None or tuple(confirmed_budget) != expected):
        raise ValueError("Live disabled: explicit authorized budget configuration and confirmation required")
    if not os.environ.get("MODEL_API_KEY"):
        raise ValueError("Live disabled: MODEL_API_KEY credential is absent")


def public_check(public):
    if set(public) != PUBLIC_KEYS:
        raise ValueError("Wrong runtime public field contract")
    assert_public(public)


def read_inputs(data_root):
    """Check the current input bundle, never task answers or old model records."""
    data_root = Path(data_root).resolve()
    catalog = core.read(data_root / "catalog.json")
    entries = catalog["tasks"]
    if (catalog.get("protocol") != VERSION or catalog.get("condition") != "official140"
            or catalog.get("base_task_count") != 140 or len(entries) != 140
            or len({entry["task_slug"] for entry in entries}) != 140
            or [entry["task_slug"] for entry in entries] != sorted(entry["task_slug"] for entry in entries)
            or [entry["alias"] for entry in entries] != ["task_%03d" % i for i in range(1, 141)]):
        raise ValueError("Expected fixed original runtime-aligned 140 catalog")
    rows = []
    for entry in entries:
        paths = {key: (data_root / entry[key]).resolve() for key in ("public_file", "chart_file", "source_file")}
        if any(data_root not in path.parents for path in paths.values()):
            raise ValueError("Input path leaves prepared bundle")
        public, provenance = core.read(paths["public_file"]), core.read(paths["source_file"])
        public_check(public)
        if (public["task_alias"] != entry["alias"] or provenance["protocol"] != VERSION
                or core.digest(paths["public_file"]) != provenance["public_sha256"]
                or core.digest(paths["chart_file"]) != provenance["original_chart_sha256"]):
            raise ValueError("Prepared public/image identity differs from bundle provenance")
        rows.append({"task_slug": entry["task_slug"], **{
            key: {"path": str(path), "sha256": core.digest(path)} for key, path in paths.items()}})
    return catalog, rows


def initial_record(entry, data_root, mode):
    public = core.read(Path(data_root) / entry["public_file"])
    public_check(public)
    return {"task_slug": entry["task_slug"], "domain": entry["domain"],
        "chart_file": str((Path(data_root) / entry["chart_file"]).resolve()), "public_task": public,
        "status": {phase: "not_run" for phase in core.PHASES}, "stages": {},
        "proposal": None, "generated": None, "normalized": None, "verification": None,
        "rule_state": [], "translations": {"items": {}}, "translation_items": [], "error": None,
        "provenance": {"protocol": VERSION, "execution_mode": mode,
            "history": [], "old_results_reused": False, "business_actions_executed": False,
            "submit_executed": False, "scope": "static original chart plus archived three-page public text"}}


def request_preview(record, config):
    """Same wire layout as PanelAPI; verified against the fake-session wire body."""
    prompt, context, images = parent.phase_input("proposal", record)
    assert_public(context)
    content = [{"type": "text", "text": json.dumps(context, ensure_ascii=False)}]
    for ref, filename in images:
        path = Path(filename)
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        content.extend([{"type": "text", "text": "Observation " + ref},
            {"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," +
                base64.b64encode(path.read_bytes()).decode("ascii")}}])
    return {"model": config["model"], "temperature": config["temperature"],
        "max_tokens": config["phase_max_tokens"]["proposal"],
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": content}]}


def sources():
    return parent.sources() + [CITATION / "citation_adapter.py", NATIVE / "budget.py",
        NATIVE / "batch_runner.py", PANEL / "apiyi_selection_20260924/analyze_usage.py",
        HERE / "runner.py", HERE / "public_inputs.py", HERE / "prepare.py"]


def initialize(output, data_root, config, mode, resume=False):
    check_config(config)
    output, data_root = Path(output).resolve(), Path(data_root).resolve()
    if output == PANEL or PANEL in output.parents or output == data_root or data_root in output.parents:
        raise ValueError("Output must be separate from old runs and prepared inputs")
    catalog, inputs = read_inputs(data_root)
    hashes = {path.relative_to(HERE.parent).as_posix(): core.digest(path) for path in sources()}
    if output.exists():
        if not resume:
            raise FileExistsError("Output exists; explicit same-protocol --resume required")
        runtime = core.read(output / "runtime.json")
        if (core.read(output / "config_snapshot.json") != config
                or runtime["source_sha256"] != hashes or runtime["execution_mode"] != mode
                or core.read(output / "inputs_snapshot.json") != inputs
                or core.read(output / "catalog_snapshot.json") != catalog):
            raise ValueError("Frozen configuration, source, inputs or mode changed")
        for key, value in hashes.items():
            if core.digest(output / "runtime_source" / key) != value:
                raise ValueError("Frozen source snapshot changed")
    else:
        output.mkdir(parents=True, exist_ok=False)
        core.dump(output / "config_snapshot.json", config)
        core.dump(output / "catalog_snapshot.json", catalog)
        core.dump(output / "inputs_snapshot.json", inputs)
        core.dump(output / "runtime.json", {"created_at": parent.now(), "python": sys.version,
            "execution_mode": mode, "source_sha256": hashes, "model_identity_scope": "gateway alias only"})
        for source in sources():
            dest = output / "runtime_source" / source.relative_to(HERE.parent)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        for entry in catalog["tasks"]:
            row = initial_record(entry, data_root, mode)
            case = output / "tasks" / entry["task_slug"]
            core.dump(case / "record.json", row)
            core.dump(case / "proposal/request_preview.json", request_preview(row, config))
            core.dump(case / "proposal/preview_status.json", {"status": "PREPARED_NOT_SENT", "model_calls": 0})
        core.dump(output / "prompt_templates.json", {
            "status": "TEMPLATES_ONLY_NOT_SENT",
            "generation": {"system": parent.GENERATOR, "requires": "actual validated proposal"},
            "verification": {"system": parent.VERIFIER, "requires": "actual normalized generation"},
            "note": "No downstream request or model proposal fabricated during preparation"})
        core.dump(output / "run_state.json", {"status": "PREPARED_NOT_SENT", "mode": mode,
            "planned_tasks": 140, "planned_logical_calls_upper_bound": 420,
            "blocked_reason": None, "browser_operations": 0, "api_translation_requests": 0,
            "old_results_reused": 0, "real_model_requests": 0})
    for entry in catalog["tasks"]:
        expected = initial_record(entry, data_root, mode)
        actual = core.read(output / "tasks" / entry["task_slug"] / "record.json")
        if any(actual[key] != expected[key] for key in ("public_task", "chart_file", "provenance")):
            raise ValueError("Record no longer matches new runtime-aligned input protocol")
    return catalog


class RuntimeAPI(BudgetedPanelAPI):
    def call(self, folder, task_id, phase, prompt, context, images):
        public_check(context["task"])
        assert_public(context)
        return super().call(folder, task_id, phase, prompt, context, images)


@contextmanager
def selected_validator():
    previous = parent.validate_stage
    def validate(phase, value, record, config):
        public_check(record["public_task"])
        return citation_adapter.validate_stage(phase, value, record, config)
    parent.validate_stage = validate
    try:
        yield
    finally:
        parent.validate_stage = previous


def eligible(record):
    states = [record["status"][phase] for phase in PHASES]
    return not (all(status == "completed" for status in states) or
                any(status in {"invalid", "failed"} for status in states))


def export(output, catalog):
    rows = [core.read(output / "tasks" / entry["task_slug"] / "record.json") for entry in catalog["tasks"]]
    budget = core.read(output / "budget.json", {"request_attempts": 0, "estimated_ledger_usd": 0})
    state = core.read(output / "run_state.json")
    mock = state["mode"] == "MOCK_SYNTHETIC_NOT_MODEL_OUTPUT"
    summary = {**state, "total_tasks": len(rows), "request_attempts": budget["request_attempts"],
        "real_model_requests": 0 if mock else budget["request_attempts"],
        "mock_requests": budget["request_attempts"] if mock else 0,
        "accounting_mode": "mock_fixture_usage_not_provider_charge" if mock else "estimated_provider_usage_not_invoice",
        "estimated_ledger_usd": budget["estimated_ledger_usd"], "actual_charge_usd": None,
        "all_three_stages_complete": sum(all(row["status"][p] == "completed" for p in PHASES) for row in rows),
        "pending_tasks": sum(eligible(row) for row in rows),
        "phase_status_counts": {phase: dict(Counter(row["status"][phase] for row in rows)) for phase in core.PHASES}}
    core.dump(output / "summary.json", summary)
    return summary


def prepare_only(output, data_root, config, resume=False):
    output = Path(output).resolve()
    with RunLock(output):
        catalog = initialize(output, data_root, config, "LIVE_PROTOCOL_PREPARED", resume)
        return export(output, catalog)


class MockResponse:
    status_code = 200
    def __init__(self, value):
        self.value = value
    def json(self):
        return {"id": "MOCK_SYNTHETIC_NOT_MODEL_OUTPUT", "model": "gpt-5.6-terra",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(self.value)}}]}


class MockSession:
    """Structural fixtures only. Never observes chart content or reads a gold."""
    def __init__(self):
        self.proxies, self.calls = {}, []
    def post(self, endpoint, json, **kwargs):
        self.calls.append(copy.deepcopy(json))
        context = core.json.loads(json["messages"][1]["content"][0]["text"])
        option = context["task"]["option_labels"][0]
        if "arguments" in context:
            value = {"checks": [{"chain_id": chain["chain_id"], "O": "undetermined", "B": "undetermined",
                "implication": "undetermined", "reason": "MOCK: structural fixture, no visual judgment",
                "evidence": [{"ref": "chart_1", "location": "whole image", "content": "MOCK: unexamined image"},
                    {"ref": "task", "location": "user_goal", "content": "MOCK: task field binding"}]}
                for chain in context["arguments"]["chains"]],
                "recommendation": None, "unresolved_reason": "MOCK ONLY: no task answer inferred"}
        elif "proposal" in context:
            value = {"rules": [{"id": "r1", "text": "MOCK: interpretation requires visible evidence",
                "component": "mock component", "conditions": "mock fixture only"}],
                "chains": [{"rule_id": "r1", "option_label": option, "claim": "MOCK: untested consequence",
                    "observations": [{"ref": "chart_1", "location": "whole image", "text": "MOCK: no visual fact asserted"}]}]}
        else:
            value = {"action": {"kind": "select", "option": option}, "brief_basis": "MOCK: first public option, not a model decision",
                "used_rule_ids": [], "new_evidence": "", "challenge_previous_verification": False}
        return MockResponse(value)


def execute(output, data_root, config, *, mock=False, confirmed_budget=None, resume=False, limit=None, sanity=False):
    if not mock:
        authorize_live(config, confirmed_budget)
    check_config(config)
    output = Path(output).resolve()
    with RunLock(output):
        mode = "MOCK_SYNTHETIC_NOT_MODEL_OUTPUT" if mock else "LIVE_PROTOCOL_PREPARED"
        catalog = initialize(output, data_root, config, mode, resume)
        accounting = {**config, "max_request_attempts": 9, "max_estimated_usd": 2} if mock else config
        budget = EstimatedBudget(output / "budget.json", accounting)
        state = core.read(output / "run_state.json")
        if state.get("blocked_reason") or budget.value.get("blocked_reason"):
            state.update(status="blocked", blocked_reason=state.get("blocked_reason") or budget.value["blocked_reason"])
            core.dump(output / "run_state.json", state)
            return export(output, catalog)
        state.update(status="running", mode=mode, updated_at=parent.now())
        core.dump(output / "run_state.json", state)
        count, api = 0, None
        try:
            with selected_validator():
                selected = ([next(row for row in catalog["tasks"] if row["task_slug"] == slug) for slug in MOCK_SLUGS]
                            if mock or sanity else catalog["tasks"])
                for entry in selected:
                    case = output / "tasks" / entry["task_slug"]
                    record = core.read(case / "record.json")
                    if not eligible(record):
                        continue
                    if limit is not None and count >= limit:
                        break
                    count += 1
                    if api is None:
                        api = RuntimeAPI(config, budget, session=MockSession()) if mock else RuntimeAPI(config, budget)
                    for index, phase in enumerate(PHASES):
                        if any(record["status"][previous] != "completed" for previous in PHASES[:index]):
                            break
                        parent.execute_phase(record, phase, case, api, config)
                        if record["status"][phase] != "completed":
                            break
                    export(output, catalog)
            summary = export(output, catalog)
            state.update(status="MOCK_FINISHED_NOT_RESEARCH_RESULT" if mock else
                "paused" if summary["pending_tasks"] else "completed_with_terminal_records", updated_at=parent.now())
        except core.ServiceStop as error:
            state.update(status="blocked", blocked_reason=error.category)
        finally:
            budget.reconcile()
            core.dump(output / "run_state.json", state)
        return export(output, catalog)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "mock", "live"))
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--data", type=Path, default=HERE / "prepared")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", "--max-new-cases", dest="limit", type=int)
    parser.add_argument("--sanity", action="store_true", help="Fixed b001, pub003, env008 order; no other task")
    parser.add_argument("--confirm-budget", type=float, nargs=2, metavar=("USD", "ATTEMPTS"))
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.output is None:
        args.output = HERE / {"prepare": "request_previews", "mock": "mock_run", "live": "run"}[args.command]
    config = core.read(args.config)
    result = (prepare_only(args.output, args.data, config, args.resume) if args.command == "prepare" else
        execute(args.output, args.data, config, mock=args.command == "mock", confirmed_budget=args.confirm_budget,
                resume=args.resume, limit=args.limit, sanity=args.sanity))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
