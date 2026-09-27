"""Fixed full-set completion panel. --prepare never constructs a network client."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
RESEARCH = HERE.parent
for directory in (RESEARCH / "obc140_20260923", RESEARCH / "obc140_20260923/terra140_native_zh_20260924",
                  RESEARCH / "competing_rules_20260923", RESEARCH / "obc140_runtime_aligned_20260924"):
    sys.path.insert(0, str(directory))
import panel_core as wire
import public_inputs
from budget import BudgetedPanelAPI, EstimatedBudget

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

core = module("explanation_completion_core", HERE / "core.py")
prompts = module("explanation_completion_prompts", HERE / "prompts.py")
FIXED_IDS = ("b001", "b002", "pub013")
STAGES = ("questions", "supplement", "verification")

def now():
    return datetime.now(timezone.utc).isoformat()

def leaf_paths(value, prefix=""):
    if isinstance(value, dict):
        return {p: text for key, item in value.items() for p, text in
                leaf_paths(item, prefix + "/" + str(key).replace("~", "~0").replace("/", "~1")).items()}
    if isinstance(value, list):
        return {p: text for i, item in enumerate(value) for p, text in leaf_paths(item, prefix + "/" + str(i)).items()}
    return {prefix: value} if isinstance(value, str) and value.strip() else {}

def load_case(task_id):
    archive = RESEARCH / "obc140_runtime_aligned_20260924"
    public_path = archive / "prepared/tasks" / task_id / "public.json"
    generated_path = archive / "run/tasks" / task_id / "generation/round_001/validated.json"
    chart_path = archive / "prepared/tasks" / task_id / ("chart.png" if task_id == "health001" else "chart.jpeg")
    public = wire.read(public_path)
    if not isinstance(public, dict) or set(public) != public_inputs.PUBLIC_KEYS:
        raise ValueError("Unexpected public projection")
    public_inputs.assert_public(public)
    original = wire.read(generated_path)
    if not isinstance(original, dict) or not isinstance(original.get("generated"), dict):
        raise ValueError("Missing original generated set; do not fall back to a later normalized set")
    generated = copy.deepcopy(original["generated"])
    public_inputs.assert_public(generated)
    base = core.import_initial(generated, public)
    return {"task": public, "base_arguments": base, "initial_generated_raw": generated,
            "chart_source": str(chart_path), "chart_ref": task_id + ":" + wire.digest(chart_path),
            "source_sha256": {str(p): wire.digest(p) for p in (public_path, generated_path, chart_path)},
            "seed_provenance": {"mode": "entire_original_generated_set", "source": str(generated_path),
                "rules_read": len(generated["rules"]), "chains_read": len(generated["chains"]),
                "filtered_by_option": False, "old_verifier_read": False,
                "history_cost": "original proposal/generation reused; excluded from new-request ledger"}}

def arguments_view(arguments):
    # Provenance and question-response assessments are not verifier evidence.
    return {key: copy.deepcopy(arguments.get(key, [])) for key in ("rules", "chains", "refinements")}

def build_context(stage, inputs, result):
    context = wire.common_context(inputs["task"])
    context["public_task_leaf_paths"] = leaf_paths(inputs["task"])
    if stage in ("questions", "supplement"):
        context["initial_arguments"] = arguments_view(inputs["base_arguments"])
        if stage == "supplement":
            context["counterquestions"] = result["questions"]
    elif stage == "verification":
        context["arguments"] = arguments_view(result["combined"])
        # Strip generation dependency/provenance annotations, never O/B/C content.
        for chain in context["arguments"]["chains"]:
            chain.pop("question_ids", None)
            chain.pop("relationship", None)
        for record in context["arguments"]["refinements"]:
            record.pop("question_ids", None)
    else:
        raise ValueError("Unknown stage")
    public_inputs.assert_public(context)
    return context

def validate_config(config, manifest):
    required = {"endpoint": "https://api.apiyi.com/v1/chat/completions", "model": "gpt-5.6-terra",
                "temperature": 0, "phase_max_tokens": {"generation": 4800, "verification": 6000},
                "max_attempts_per_call": 2, "max_request_attempts": 12, "max_estimated_usd": 2.0,
                "attempt_reserve_usd": 0.25, "estimated_input_usd_per_m": 2.5,
                "estimated_output_usd_per_m": 12, "timeout_seconds": 120, "proxy": None,
                "allow_trailing_json_closers": False, "concurrency": 1, "quality_retries": False,
                "browser_operations": 0, "gpu_enabled": False, "wandb": False,
                "max_new_chains": 2, "max_refinements": 2, "max_questions": 3}
    if any(config.get(key) != value for key, value in required.items()):
        raise ValueError("Frozen authorized configuration changed")
    expected = [{"case_id": task + "_original", "task_id": task,
                 "chart": "research/obc140_runtime_aligned_20260924/prepared/tasks/" + task + "/chart.jpeg"}
                for task in FIXED_IDS]
    if manifest.get("cases") != expected or manifest.get("planned_logical_calls") != 9 or manifest.get("max_request_attempts") != 12 or manifest.get("max_estimated_usd") != 2.0:
        raise ValueError("Fixed panel or budget changed")

def runtime_sources():
    modules = (wire, wire.engine, public_inputs, core, prompts,
               sys.modules["budget"], sys.modules["analyze_usage"],
               sys.modules["format_replay"], sys.modules["prompts_observation_v4"])
    return sorted({Path(__file__), HERE / "config.json", HERE / "manifest.json",
                   HERE / "PROTOCOL.md", HERE / "AUTHORIZATION.json",
                   *(Path(mod.__file__).resolve() for mod in modules)}, key=str)

def freeze_sources(output):
    records = {}
    for path in runtime_sources():
        dest = output / "runtime_source" / path.relative_to(PROJECT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        records[str(path)] = wire.digest(path)
    wire.dump(output / "runtime.json", {"created_at": now(), "executable": sys.executable,
        "python": sys.version, "source_sha256": records,
        "credential_policy": "MODEL_API_KEY environment only; never serialized"})
    wire.dump(output / "prompt_templates.json", prompts.PROMPTS)

def run(output, live=False, api_factory=BudgetedPanelAPI):
    # This Windows Python may retain a relative path when resolving a missing leaf.
    output = Path(output).absolute().resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("Use a new output directory directly inside this experiment")
    config, manifest = wire.read(HERE / "config.json"), wire.read(HERE / "manifest.json")
    validate_config(config, manifest)
    if live and not os.environ.get("MODEL_API_KEY"):
        raise ValueError("Missing authorized process credential")
    fixture = live and api_factory is not BudgetedPanelAPI
    evidence_mode = "offline_fixture" if fixture else "real_model" if live else "preparation_only"
    inputs_all = [load_case(task) for task in FIXED_IDS]
    # Also audit existing multi-chain cases offline, never adding them to live panel.
    audits = [load_case(task) for task in ("b001", "b002", "env001", "health001", "pub013")]
    output.mkdir(parents=True, exist_ok=False)
    freeze_sources(output)
    wire.dump(output / "initial_set_audit.json", [{"task_id": task,
        "rule_count": len(value["base_arguments"]["rules"]),
        "chain_count": len(value["base_arguments"]["chains"]),
        "base_arguments": value["base_arguments"], "provenance": value["seed_provenance"],
        "source_sha256": value["source_sha256"]}
        for task, value in zip(("b001", "b002", "env001", "health001", "pub013"), audits)])
    budget = EstimatedBudget(output / "budget.json", config)
    results = []
    summary = {"status": "prepared_not_sent", "mode": "mock" if fixture else "live" if live else "prepare",
        "evidence_mode": evidence_mode,
        "created_at": now(), "planned_logical_calls": 9, "global_stop": None,
        "browser_operations": 0, "gpu_operations": 0, "translation_api_calls": 0,
        "semantic_success": "not_inferred_from_structural_validation", "cases": []}
    for task, inputs in zip(FIXED_IDS, inputs_all):
        folder = output / "cases" / task
        folder.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(inputs["chart_source"], folder / "chart.jpeg")
        wire.dump(folder / "inputs.json", inputs)
        wire.dump(folder / "initial_set.json", inputs["base_arguments"])
        result = {"task_id": task, "status": "prepared_not_sent", "stages": {}, "evidence_mode": evidence_mode,
            "questions": None, "supplement": None, "combined": None, "verification": None,
            "rule_state": None, "failure": None, "request_attempts": 0,
            "estimated_ledger_usd": 0, "browser_operations": 0}
        wire.dump(folder / "prepared_first_context.json", build_context("questions", inputs, result))
        results.append(result)

    def save():
        budget.reconcile()
        for result in results:
            events = [e for e in budget.value["events"] if e["task_slug"] == result["task_id"]]
            result["request_attempts"] = len(events)
            result["estimated_ledger_usd"] = sum(e["charged_estimated_usd"] for e in events)
            wire.dump(output / "cases" / result["task_id"] / "result.json", result)
        summary["cases"] = [{key: r[key] for key in ("task_id", "status", "request_attempts", "failure")} for r in results]
        summary["request_attempts"] = budget.value["request_attempts"]
        summary["estimated_ledger_usd"] = budget.value["estimated_ledger_usd"]
        summary["actual_bill_usd"] = None
        summary["source_preservation"] = {p: Path(p).exists() and wire.digest(p) == digest
             for inp in audits for p, digest in inp["source_sha256"].items()}
        summary["runtime_source_preservation"] = {p: wire.digest(p) == digest for p, digest in
             wire.read(output / "runtime.json")["source_sha256"].items()}
        wire.dump(output / "summary.json", summary)

    save()
    if not live:
        return summary
    summary["status"] = "running"
    api = api_factory(config, budget)
    for inputs, result in zip(inputs_all, results):
        folder = output / "cases" / result["task_id"]
        if summary["global_stop"]:
            result["status"] = "not_attempted_global_stop"
            continue
        result["status"] = "running"
        stage = None
        try:
            for stage in STAGES:
                result["stages"][stage] = {"status": "running", "started_at": now()}
                context = build_context(stage, inputs, result)
                wire.dump(folder / stage / "input_context.json", context)
                save()
                if stage == "supplement" and not result["questions"]["questions"]:
                    value = {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": []}
                    result["stages"][stage]["output_source"] = "deterministic_empty_no_questions_no_model_call"
                else:
                    value = api.call(folder / stage / "round_001", result["task_id"],
                                     "verification" if stage == "verification" else "generation",
                                     prompts.PROMPTS[stage], context, [("chart_1", folder / "chart.jpeg")])
                    result["stages"][stage]["output_source"] = "model_response"
                wire.dump(folder / stage / "raw.json", value)
                if stage == "questions":
                    result[stage] = core.validate_questions(value, inputs["base_arguments"], inputs["task"])
                elif stage == "supplement":
                    result["combined"] = core.apply_supplement(value, inputs["base_arguments"], result["questions"], inputs["task"])
                    result[stage] = value
                    wire.dump(folder / "combined_arguments.json", result["combined"])
                else:
                    result[stage] = core.validate_verification(value, result["combined"], inputs["task"])
                    result["rule_state"] = core.build_rule_state(result["combined"], result[stage], result["task_id"], inputs["chart_ref"])
                    core.save_state(folder / "rule_state.json", result["rule_state"])
                    restored = core.load_state(folder / "rule_state.json")
                    if restored != result["rule_state"]:
                        raise ValueError("Rule-state round trip changed content")
                    wire.dump(folder / "state_reload_check.json", {"identical": True,
                        "actual_actor_use": "not_run", "cross_step_effectiveness": "not_tested"})
                wire.dump(folder / stage / "accepted.json", result[stage])
                result["stages"][stage].update(status="completed", finished_at=now())
                save()
            result["status"] = "mock_completed" if fixture else "completed"
        except (wire.ServiceStop, wire.UnknownRequestOutcome) as exc:
            result["failure"] = {"stage": stage, "type": type(exc).__name__, "reason": str(exc)}
            result["status"] = "stopped_global"
            summary["global_stop"] = copy.deepcopy(result["failure"])
        except Exception as exc:
            result["status"] = "failed_stage_no_quality_retry"
            result["failure"] = {"stage": stage, "type": type(exc).__name__, "reason": str(exc)}
        finally:
            if result["failure"] and stage in result["stages"]:
                result["stages"][stage].update(status="failed", failure=result["failure"])
            result["finished_at"] = now()
            save()
    terminal = "mock_completed" if fixture else "completed"
    summary["status"] = "stopped_global" if summary["global_stop"] else (
        terminal if all(r["status"] == terminal for r in results) else "completed_with_case_failures")
    summary["finished_at"] = now()
    save()
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.output, live=args.live)
    print(json.dumps({k: summary[k] for k in ("status", "cases", "request_attempts", "estimated_ledger_usd")}, ensure_ascii=False))
