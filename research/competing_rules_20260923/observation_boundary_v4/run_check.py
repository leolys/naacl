"""Five-case paired O/B/implication MODULE diagnostic, never a submission test.

Old cases reuse actual saved public inputs. New cases obtain one ordinary actor
proposal from an initial real form; no proposed action is executed. Every case
uses both frozen prompt profiles, with alternating order fixed in CASES below.
Only after all modules finish may the original hidden labels be consulted.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import engine
from adapter import BrowserTask, public_projection
from engine import API, ACTOR, Budget, RuleStore, dump
from format_replay import normalize


PROFILES = ("legacy", "observation_boundary_v4")
CASES = (
    {"task_slug": "pub013", "family": "public39", "task_alias": "case01", "source": "saved",
     "source_folder": "runs/api_demo_20260923_v2/case01_competing_persistent", "source_step": "step_00"},
    {"task_slug": "health004", "family": "health19", "task_alias": "case03", "source": "saved",
     "source_folder": "runs/health004_format_supplement_20260923/case03_competing_persistent", "source_step": "step_00"},
    {"task_slug": "b046", "family": "business47", "task_alias": "case05", "source": "saved",
     "source_folder": "runs/api_demo_20260923_v2/case05_competing_persistent", "source_step": "step_00"},
    {"task_slug": "pub031", "family": "public39", "task_alias": "diag04", "source": "new"},
    {"task_slug": "b001", "family": "business47", "task_alias": "diag05", "source": "new"},
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def profile_order(case_index):
    return PROFILES if case_index % 2 == 0 else tuple(reversed(PROFILES))


def profile_config(config, profile):
    if profile not in PROFILES:
        raise ValueError("Unsupported fixed prompt profile")
    copied = copy.deepcopy(config)
    copied["defense_prompt_profile"] = profile
    return copied


def validate_config(config):
    if config.get("task_ids") != [case["task_slug"] for case in CASES]:
        raise ValueError("Config task_ids must match the frozen five-case order")
    if config.get("profiles") != list(PROFILES) or config.get("condition") != "official140":
        raise ValueError("Config must name the two frozen profiles and original chart condition")
    for field, fixed in (("temperature", 0), ("max_tokens", 2200),
                         ("timeout_seconds", 120), ("max_attempts_per_call", 3), ("competitors", 2)):
        if config.get(field) != fixed:
            raise ValueError("This diagnostic fixes %s=%s" % (field, fixed))
    if not 0 < config.get("max_request_attempts", 0) <= 60:
        raise ValueError("Total request-attempt cap must not exceed 60")
    if not 0 < config.get("max_browser_operations", 0) <= 30:
        raise ValueError("Total browser-operation cap must not exceed 30")
    # Fail before inference if the main engine has not wired the requested contrast.
    dispatch = getattr(engine, "defense_prompts", None)
    if dispatch is None:
        raise RuntimeError("engine.defense_prompts(config) is not implemented")
    old = dispatch(profile_config(config, "legacy"))
    new = dispatch(profile_config(config, "observation_boundary_v4"))
    if old != (engine.GENERATOR, engine.VERIFIER):
        raise ValueError("Legacy profile is not the exact original generator/verifier pair")
    if new == old:
        raise ValueError("The new profile does not change the promised prompt contrast")


def prepare_new_case(case, source_raw, destination):
    """Offline projection/copy only; choice of cases is already frozen above."""
    source_raw, destination = Path(source_raw), Path(destination)
    split = source_raw / "splits" / "official140" / (case["family"] + "_tasks.jsonl")
    rows = [line for line in split.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("task_slug") == case["task_slug"]]
    if len(rows) != 1:
        raise ValueError("Expected exactly one fixed original task")
    raw = json.loads(rows[0])
    name = Path(raw["chart_asset"]["figure_path"]).name
    image = source_raw / "assets" / "official140" / case["family"] / case["task_slug"] / name
    public = public_projection(raw, case["task_alias"])
    chart = destination / ("chart" + image.suffix.lower())
    if destination.exists():
        if read_json(destination / "public.json") != public or sha256(chart) != sha256(image):
            raise ValueError("Existing prepared case differs; refusing overwrite")
        if read_json(destination / "offline" / "raw.json") != raw:
            raise ValueError("Existing offline source differs; refusing overwrite")
    else:
        destination.mkdir(parents=True)
        dump(destination / "public.json", public)
        shutil.copyfile(image, chart)
        (destination / "offline").mkdir()
        (destination / "offline" / "raw.json").write_text(rows[0] + "\n", encoding="utf-8")
        dump(destination / "offline" / "provenance.json", {
            "source_split": str(split.resolve()), "source_chart": str(image.resolve()),
            "task_slug": case["task_slug"], "chart_sha256": sha256(image),
            "source_row_sha256_without_newline": hashlib.sha256(rows[0].encode("utf-8")).hexdigest(),
            "gold_used_to_choose_case_or_proposal": False,
        })
    return destination


def wire_bindings(request, context_record):
    content = request["messages"][1]["content"]
    if json.loads(content[0]["text"]) != context_record["context"]:
        raise ValueError("Saved readable context differs from actual wire context")
    tail = content[1:]
    if len(tail) % 2:
        raise ValueError("Unsupported image envelope")
    bindings = {}
    for offset in range(0, len(tail), 2):
        label, item = tail[offset:offset + 2]
        if label.get("type") != "text" or not label["text"].startswith("Observation ") or item.get("type") != "image_url":
            raise ValueError("Unsupported image envelope")
        ref = label["text"][len("Observation "):]
        uri = item["image_url"]["url"]
        if ref in bindings or not uri.startswith("data:image/") or ";base64," not in uri:
            raise ValueError("Invalid or duplicate image")
        binary = base64.b64decode(uri.split(";base64,", 1)[1], validate=True)
        bindings[ref] = hashlib.sha256(binary).hexdigest()
    if list(bindings) != [entry["ref"] for entry in context_record["images"]] or "chart_1" not in bindings:
        raise ValueError("Saved image manifest differs from actual image request")
    return bindings


def save_shared(public_input, images, folder, provenance):
    """One immutable pair input; only image file location is made portable."""
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "images").mkdir()
    copied, image_manifest = [], []
    for ref, path in images:
        path = Path(path)
        target = folder / "images" / (ref + path.suffix.lower())
        shutil.copyfile(path, target)
        copied.append((ref, target))
        image_manifest.append({"ref": ref, "file": str(target.resolve()), "sha256": sha256(target)})
    engine.assert_public(public_input)
    dump(folder / "public_input.json", public_input)
    dump(folder / "images.json", image_manifest)
    dump(folder / "provenance.offline.json", provenance)
    return {"public_input": public_input, "images": copied, "image_sha256": image_manifest}


def saved_case(case, folder, root=ROOT):
    source = Path(root) / case["source_folder"]
    generator = source / case["source_step"] / "defense" / "generate"
    context_record, request = read_json(generator / "context.json"), read_json(generator / "request.json")
    context = context_record["context"]
    bindings = wire_bindings(request, context_record)
    if set(context) != {"task", "state", "history", "interpretation_rules", "proposal"}:
        raise ValueError("Unsupported saved generator context projection")
    if context["interpretation_rules"]:
        raise ValueError("This diagnostic only supports the saved initial no-rule state")
    if context["proposal"].get("action", {}).get("kind") != "select":
        raise ValueError("Saved initial proposal is not a selection")
    data_dir = Path(root) / "data" / case["task_alias"]
    if read_json(data_dir / "public.json") != context["task"]:
        raise ValueError("Task no longer matches actual saved public input")
    charts = list(data_dir.glob("chart.*"))
    if len(charts) != 1:
        raise ValueError("Expected one original chart")
    images = []
    for entry in context_record["images"]:
        basename = Path(entry["file"].replace("\\", "/")).name
        image = charts[0] if entry["ref"] == "chart_1" else source / "browser" / basename
        if not image.is_file() or sha256(image) != bindings[entry["ref"]]:
            raise ValueError("Saved actually supplied image bytes are unavailable")
        images.append((entry["ref"], image))
    return save_shared(copy.deepcopy(context), images, folder, {
        "source_kind": "saved_actual_generator_input", "source_context": str((generator / "context.json").resolve()),
        "source_wire_request": str((generator / "request.json").resolve()),
        "source_context_sha256": sha256(generator / "context.json"), "source_wire_sha256": sha256(generator / "request.json"),
        "restoration_attempted": False, "new_prefix_sample": False, "condition": "official140",
        "task_slug": case["task_slug"],
    })


def fresh_case(case, case_data, folder, api, budget, config):
    preparation = folder.parent / "ordinary_proposal"
    with BrowserTask(case_data, preparation / "browser", config.get("browser_executable"), budget) as browser:
        observation = browser.snapshot("ordinary_actor_input")
        context = {"task": browser.public_task, "state": observation["state"], "history": browser.history}
        images = [("chart_1", browser.chart_path), ("page_00", observation["screenshot"])]
        original = api.call(preparation / "actor", "ordinary_proposal", ACTOR, context, images)
        proposal = normalize(original)
        dump(preparation / "normalized_proposal.json", proposal)
        if proposal["action"].get("kind") != "select" or proposal["action"].get("option") not in context["state"]["options"]:
            raise ValueError("Ordinary actor did not propose a valid selection; no synthetic proposal may replace it")
        public_input = {**context, "interpretation_rules": [], "proposal": proposal}
        shared = save_shared(public_input, images, folder, {
            "source_kind": "one_fresh_ordinary_actor_proposal", "source_actor_request": str((preparation / "actor" / "request.json").resolve()),
            "source_actor_response": str((preparation / "actor" / "parsed.json").resolve()),
            "proposal_executed": False, "business_submission_executed": False,
            "condition": "official140", "task_slug": case["task_slug"],
        })
        if browser.receipt is not None or any(record["source"] != "deterministic_setup" for record in browser.history):
            raise RuntimeError("Preparation unexpectedly executed a business action")
        return shared


def module_failure_stage(folder):
    if not (folder / "generate" / "parsed.json").exists():
        return "generation_call_or_parse_failure"
    if not (folder / "normalized_candidates.json").exists():
        return "candidate_normalization_failure"
    if not (folder / "verify" / "request.json").exists():
        return "before_verifier_failure"
    if not (folder / "verify" / "parsed.json").exists():
        return "verifier_call_or_parse_failure"
    return "verifier_validation_failure"


def run_module(case, profile, shared, api, budget, config, folder):
    folder.mkdir(parents=True, exist_ok=False)
    specific = profile_config(config, profile)
    store, context = RuleStore(), copy.deepcopy(shared["public_input"])
    before_attempts = budget.attempts
    result = {"task_slug": case["task_slug"], "task_alias": case["task_alias"], "profile": profile,
              "status": "not_started", "recommendation": None,
              "business_action_executed": False, "submitted": False,
              "source_first_proposal": context["proposal"], "source_kind": case["source"]}
    try:
        verdict = engine.verify(api, folder, context["task"], context["state"], context["history"],
                                shared["images"], context["proposal"], store, specific)
        result.update(status="completed", verification=verdict, recommendation=verdict.get("recommendation"))
    except Exception as exc:
        result.update(status=module_failure_stage(folder), error=type(exc).__name__ + ": " + str(exc))
    result["request_attempts"] = budget.attempts - before_attempts
    result["generator_attempts"] = len(list((folder / "generate").glob("attempt_*.json")))
    result["verifier_attempts"] = len(list((folder / "verify").glob("attempt_*.json")))
    result["verifier_executed"] = result["verifier_attempts"] > 0
    result["rule_store"] = store.records
    dump(folder / "module_result.json", result)
    return result


def pair_evidence(folder, shared):
    paths = {profile: folder / profile / "generate" / "context.json" for profile in PROFILES}
    existing = {profile: read_json(path) for profile, path in paths.items() if path.is_file()}
    expected = shared["public_input"]
    generated_contexts = {profile: item["context"] == expected for profile, item in existing.items()}
    image_proofs = {}
    for profile, item in existing.items():
        image_proofs[profile] = [
            {"ref": entry["ref"], "sha256": sha256(entry["file"])} for entry in item["images"]]
    proof = {"same_public_generator_context_by_profile": generated_contexts,
             "same_image_refs_and_hashes": len(image_proofs) == 2 and image_proofs[PROFILES[0]] == image_proofs[PROFILES[1]],
             "generator_contexts_equal": len(existing) == 2 and all(generated_contexts.values()),
             "verifier_candidates_may_differ_as_generated_outputs": True,
             "image_hashes": image_proofs,
             "no_claim_of_equal_verifier_candidate_content": True}
    dump(folder / "paired_input_proof.json", proof)
    if len(existing) == 2 and not (proof["same_image_refs_and_hashes"] and proof["generator_contexts_equal"]):
        raise RuntimeError("Paired module inputs differ beyond prompt profile")
    return proof


def offline_scores(results, cases, prepared_paths):
    """No receipt scoring: only offline proposal/recommendation agreement."""
    by_slug = {case["task_slug"]: case for case in cases}
    scored = []
    for result in results:
        row = copy.deepcopy(result)
        raw = read_json(Path(prepared_paths[row["task_slug"]]) / "offline" / "raw.json")
        labels = [item["label"] for item in raw["action_space"] if item["action_id"] == raw["expected_action_id"]]
        if len(labels) != 1:
            raise ValueError("Cannot uniquely resolve original offline label")
        proposed = (row.get("source_first_proposal") or {}).get("action", {}).get("option")
        recommendation = row.get("recommendation")
        row["offline_evaluation"] = {
            "original_label_agreement_of_source_proposal": proposed == labels[0] if proposed else None,
            "original_label_agreement_of_recommendation": recommendation == labels[0] if recommendation is not None else None,
            "original_expected_label": labels[0], "actual_submission": False,
            "end_to_end_success": "not_applicable_module_diagnostic", "natural_recovery_rate": "not_applicable",
            "condition": "official140", "source_kind": by_slug[row["task_slug"]]["source"],
        }
        scored.append(row)
    return scored


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-raw", default=str(ROOT.parents[1] / ".aris" / "dataset_inventory_20260918" / "raw"))
    parser.add_argument("--data", default=str(HERE / "data"))
    args = parser.parse_args()
    config, output = read_json(args.config), Path(args.output)
    validate_config(config)
    output.mkdir(parents=True, exist_ok=False)
    order = [{"task_slug": case["task_slug"], "profiles": list(profile_order(index)), "source": case["source"]}
             for index, case in enumerate(CASES)]
    dump(output / "frozen_protocol.json", {
        "kind": "paired_observation_rule_implication_module_diagnostic", "cases": CASES,
        "order": order, "planned_module_calls": 20, "planned_new_ordinary_proposal_calls": 2,
        "hard_attempt_cap": config["max_request_attempts"], "hard_browser_cap": config["max_browser_operations"],
        "natural_trajectory_or_end_to_end_comparison": False, "no_submit": True,
        "no_reselection_based_on_answers_or_module_outcomes": True,
    })
    dump(output / "config_snapshot.json", config)
    source_snapshot = output / "runtime_source"
    source_snapshot.mkdir()
    sources = [ROOT / name for name in ("engine.py", "run_demo.py", "prompts_observation_v4.py", "adapter.py", "format_replay.py")]
    sources.append(Path(__file__))
    for path in sources:
        if not path.is_file():
            raise FileNotFoundError("Required runtime source is absent: " + str(path))
        shutil.copy2(path, source_snapshot / path.name)
    dump(output / "runtime.json", {"python": sys.version, "platform": platform.platform(), "created_at": time.time(),
         "packages": {name: importlib.metadata.version(name) for name in ("requests", "Pillow", "Flask", "playwright")},
         "source_sha256": {path.name: sha256(path) for path in sources}})
    data_paths = {}
    for case in CASES:
        data_paths[case["task_slug"]] = ROOT / "data" / case["task_alias"] if case["source"] == "saved" else prepare_new_case(
            case, Path(args.source_raw), Path(args.data) / case["task_alias"])
    budget = Budget(output, config)
    dump(output / "budget.json", {"attempts": 0, "browser_operations": 0, "events": []})
    api = API(config, budget)
    results = []
    for index, case in enumerate(CASES):
        case_folder = output / case["task_slug"]
        case_folder.mkdir()
        print("PREPARE", case["task_slug"], case["source"], flush=True)
        try:
            shared = saved_case(case, case_folder / "shared_input") if case["source"] == "saved" else fresh_case(
                case, data_paths[case["task_slug"]], case_folder / "shared_input", api, budget, config)
        except Exception as exc:
            for profile in profile_order(index):
                row = {"task_slug": case["task_slug"], "task_alias": case["task_alias"], "profile": profile,
                       "status": "unsupported_source_or_ordinary_proposal", "error": type(exc).__name__ + ": " + str(exc),
                       "generator_attempts": 0, "verifier_attempts": 0, "verifier_executed": False,
                       "business_action_executed": False, "submitted": False}
                results.append(row)
            dump(output / "module_results_unscored.json", results)
            print("UNSUPPORTED", case["task_slug"], str(exc), flush=True)
            continue
        for profile in profile_order(index):
            print("MODULE", case["task_slug"], profile, flush=True)
            row = run_module(case, profile, shared, api, budget, config, case_folder / profile)
            results.append(row)
            dump(output / "module_results_unscored.json", results)
            print("END", case["task_slug"], profile, row["status"], "attempts", budget.attempts, flush=True)
        pair_evidence(case_folder, shared)
    # No gold is consulted by any actor/generator/verifier branch above.
    scored = offline_scores(results, CASES, data_paths)
    dump(output / "offline_results.json", scored)
    dump(output / "completion.json", {"recorded_module_slots": len(results), "request_attempts": budget.attempts,
         "browser_operations": budget.operations, "submitted_actions": 0,
         "completed_modules": sum(row["status"] == "completed" for row in results),
         "source_tasks_added": 2, "end_to_end_outcomes_measured": False})
    print("DONE", len(results), "module slots", budget.attempts, "attempts", budget.operations, "browser operations", flush=True)


if __name__ == "__main__":
    main()
