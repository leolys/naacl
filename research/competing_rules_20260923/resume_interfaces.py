"""Bounded engineering continuation of an already recorded interface failure.

Selection is by explicit interface-exception predicates, across every matching
arm, never by gold or outcome. No prefixes/candidates/checks are resampled.
New challenges stop unresolved: this narrow repair is not an expanded protocol.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time

from PIL import Image, ImageChops

from adapter import BrowserTask, score_summary
from engine import API, ACTOR, Budget, RuleStore, append, dump, parse_json, validate_verification
from format_replay import normalize


TARGET_ERROR = "ValueError: evidence must reference actual chart observation"
ACTION_ERROR = "ValueError: actor did not return a single action"
PROTOCOL = "saved-interface-continuation-v1"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matching_sources(run):
    """Only a mechanical exception predicate; never open scoring data here."""
    sources = []
    for folder in sorted(Path(run).glob("case*")):
        path = folder / "trajectory.json"
        if not path.is_file():
            continue
        error = read_json(path).get("error")
        if error == TARGET_ERROR:
            sources.append(folder)
        elif error == ACTION_ERROR:
            actors = sorted(folder.glob("step_*/actor/parsed.json"))
            if actors and read_json(actors[-1]).get("action") in ("select", "fill", "check"):
                sources.append(folder)
    return sources


def remaining_config(original_config, requested_config, original_budget, prior_browser_ops):
    if not isinstance(prior_browser_ops, int) or prior_browser_ops < 0:
        raise ValueError("prior-browser-ops must be a nonnegative integer")
    # A repair may not silently change model, image protocol or task controls.
    allowed_differences = {"max_request_attempts", "max_browser_operations"}
    if {k: v for k, v in original_config.items() if k not in allowed_differences} != {
            k: v for k, v in requested_config.items() if k not in allowed_differences}:
        raise ValueError("Continuation configuration differs from original outside budget caps")
    request_cap = min(150, original_config["max_request_attempts"], requested_config["max_request_attempts"])
    browser_cap = min(300, original_config["max_browser_operations"], requested_config["max_browser_operations"])
    result = copy.deepcopy(original_config)
    result["max_request_attempts"] = max(0, request_cap - original_budget["attempts"])
    result["max_browser_operations"] = max(0, browser_cap - original_budget["browser_operations"] - prior_browser_ops)
    return result


def wire_image_bindings(request, recorded_context):
    """Check readable archive against the actual transmitted user text/images."""
    messages = request.get("messages", [])
    if len(messages) != 2 or messages[1].get("role") != "user":
        raise ValueError("unsupported archived request envelope")
    content = messages[1].get("content")
    if not isinstance(content, list) or not content or content[0].get("type") != "text":
        raise ValueError("missing actual user context")
    if json.loads(content[0]["text"]) != recorded_context["context"]:
        raise ValueError("context archive differs from actual wire text")
    remainder = content[1:]
    if len(remainder) % 2:
        raise ValueError("unsupported observation wire format")
    bindings = {}
    for index in range(0, len(remainder), 2):
        label, image = remainder[index:index + 2]
        if label.get("type") != "text" or not str(label.get("text", "")).startswith("Observation ") or image.get("type") != "image_url":
            raise ValueError("unsupported observation wire format")
        ref = label["text"][len("Observation "):]
        uri = image.get("image_url", {}).get("url", "")
        if not ref or ref in bindings or not uri.startswith("data:image/") or ";base64," not in uri:
            raise ValueError("invalid or duplicate actual image reference")
        raw = base64.b64decode(uri.split(";base64,", 1)[1], validate=True)
        bindings[ref] = hashlib.sha256(raw).hexdigest()
    archive_refs = [item.get("ref") for item in recorded_context["images"]]
    if list(bindings) != archive_refs or "chart_1" not in bindings:
        raise ValueError("image archive differs from actual wire observations")
    return bindings


def load_source(folder, case_data):
    folder, case_data = Path(folder), Path(case_data)
    original = read_json(folder / "trajectory.json")
    if original.get("error") != TARGET_ERROR:
        raise ValueError("source does not have the exact eligible interface failure")
    verifier_paths = sorted(folder.glob("step_*/defense/verify/parsed.json"))
    if not verifier_paths:
        raise ValueError("no saved completed verifier output")
    verifier_file = verifier_paths[-1]
    step_dir = verifier_file.parent.parent.parent
    step = int(step_dir.name.split("_")[-1])
    actor_dirs = sorted(folder.glob("step_*/actor/parsed.json"))
    if not actor_dirs or actor_dirs[-1].parent.parent != step_dir:
        raise ValueError("verifier is not at the terminal failed source step")
    if original.get("actor_calls") != step + 1:
        raise ValueError("actor call count does not match the terminal source step")
    context_file = verifier_file.parent / "context.json"
    request_file = verifier_file.parent / "request.json"
    inputs, request = read_json(context_file), read_json(request_file)
    bindings = wire_image_bindings(request, inputs)
    chart_files = list(case_data.glob("chart.*"))
    if len(chart_files) != 1:
        raise ValueError("exactly one current chart asset is required")
    source_images = {}
    for entry in inputs["images"]:
        ref = entry["ref"]
        filename = Path(str(entry["file"]).replace("\\", "/")).name
        path = chart_files[0] if ref == "chart_1" else folder / "browser" / filename
        if not path.is_file() or digest(path) != bindings[ref]:
            raise ValueError("actual supplied image bytes cannot be reconstructed: " + ref)
        source_images[ref] = path
    page_refs = [ref for ref in bindings if ref != "chart_1"]
    if page_refs != ["page_%02d" % step]:
        raise ValueError("unsupported verifier observation set")
    verdict = read_json(verifier_file)
    response_files = sorted(verifier_file.parent.glob("response_*.json"))
    if not response_files:
        raise ValueError("missing actual verifier response archive")
    response = read_json(response_files[-1])
    if parse_json(response["choices"][0]["message"]["content"]) != verdict:
        raise ValueError("saved parsed verdict differs from actual API response")
    candidates_file = step_dir / "defense" / "normalized_candidates.json"
    candidates = read_json(candidates_file)
    if inputs["context"].get("arguments") != candidates:
        raise ValueError("normalized candidates differ from actual verifier input")
    public = read_json(case_data / "public.json")
    if inputs["context"].get("task") != public:
        raise ValueError("public task differs from actual verifier input")
    files = {"trajectory": folder / "trajectory.json", "verifier_context": context_file,
             "verifier_wire_request": request_file, "verifier_parsed": verifier_file,
             "verifier_response": response_files[-1], "normalized_candidates": candidates_file,
             "actor_proposal": step_dir / "actor" / "parsed.json"}
    return {"original": original, "step": step, "inputs": inputs, "candidates": candidates,
            "verdict": verdict, "proposal": read_json(files["actor_proposal"]),
            "observed_refs": tuple(bindings), "page_image": source_images[page_refs[0]],
            "source_files": {key: {"file": str(path.resolve()), "sha256": digest(path)} for key, path in files.items()},
            "wire_image_sha256": bindings}


def load_flat_source(folder, case_data):
    """A saved explicit named action, not a fresh choice or generated payload."""
    folder, case_data = Path(folder), Path(case_data)
    original = read_json(folder / "trajectory.json")
    if original.get("error") != ACTION_ERROR:
        raise ValueError("source does not have the exact eligible action-container failure")
    actor_files = sorted(folder.glob("step_*/actor/parsed.json"))
    if not actor_files:
        raise ValueError("saved terminal actor proposal is missing")
    actor_file = actor_files[-1]
    actor_dir, step_dir = actor_file.parent, actor_file.parent.parent
    step = int(step_dir.name.split("_")[-1])
    if original.get("actor_calls") != step + 1:
        raise ValueError("actor call count does not match saved source step")
    proposal = read_json(actor_file)
    if proposal.get("action") not in ("select", "fill", "check"):
        raise ValueError("this branch excludes zero-argument or inferred actions")
    normalized = normalize(proposal)
    inputs, request = read_json(actor_dir / "context.json"), read_json(actor_dir / "request.json")
    bindings = wire_image_bindings(request, inputs)
    chart_files = list(case_data.glob("chart.*"))
    if len(chart_files) != 1:
        raise ValueError("exactly one unchanged chart is required")
    source_images = {}
    for entry in inputs["images"]:
        ref = entry["ref"]
        filename = Path(str(entry["file"]).replace("\\", "/")).name
        path = chart_files[0] if ref == "chart_1" else folder / "browser" / filename
        if not path.is_file() or digest(path) != bindings[ref]:
            raise ValueError("saved actor input image cannot be reconstructed: " + ref)
        source_images[ref] = path
    page_refs = [ref for ref in bindings if ref != "chart_1"]
    if page_refs != ["page_%02d" % step]:
        raise ValueError("unsupported actor observation set")
    response_files = sorted(actor_dir.glob("response_*.json"))
    if not response_files or parse_json(read_json(response_files[-1])["choices"][0]["message"]["content"]) != proposal:
        raise ValueError("saved proposal differs from actual actor response")
    if inputs["context"].get("task") != read_json(case_data / "public.json"):
        raise ValueError("task differs from actual actor request")
    paths = {"trajectory": folder / "trajectory.json", "actor_proposal": actor_file,
             "actor_context": actor_dir / "context.json", "actor_wire_request": actor_dir / "request.json",
             "actor_response": response_files[-1]}
    return {"original": original, "step": step, "inputs": inputs, "proposal": proposal,
            "normalized_proposal": normalized, "observed_refs": tuple(bindings),
            "page_image": source_images[page_refs[0]], "wire_image_sha256": bindings,
            "source_files": {key: {"file": str(path.resolve()), "sha256": digest(path)} for key, path in paths.items()}}


def restore_exact(browser, source, output):
    expected = source["inputs"]["context"]
    for record in expected["history"]:
        if record.get("source") == "deterministic_setup":
            continue
        result = browser.execute(record["action"], source=record["source"])
        # Exact public receipt equality below is stronger than a generic ok check.
        if result != record["result"]:
            raise RuntimeError("replayed execution receipt differs from recorded public receipt")
    snap = browser.snapshot("restored_saved_verifier_input")
    with Image.open(source["page_image"]) as old, Image.open(snap["screenshot"]) as new:
        old_rgb, new_rgb = old.convert("RGB"), new.convert("RGB")
        equal_pixels = old_rgb.size == new_rgb.size and ImageChops.difference(old_rgb, new_rgb).getbbox() is None
    proof = {"state_equal": snap["state"] == expected["state"],
             "history_equal": browser.history == expected["history"],
             "screenshot_pixels_equal": equal_pixels,
             "source_page_image": str(Path(source["page_image"]).resolve()),
             "restored_page_image": snap["screenshot"],
             "source_state": expected["state"], "restored_state": snap["state"]}
    dump(Path(output) / "restoration_proof.json", proof)
    if not all(proof[key] for key in ("state_equal", "history_equal", "screenshot_pixels_equal")):
        raise RuntimeError("same public state/history/page pixels not established; verdict cannot be applied")
    return proof


def resume_one(api, budget, config, folder, data, output):
    output.mkdir(parents=True, exist_ok=False)
    original = read_json(folder / "trajectory.json")
    case_data = data / original["case_alias"]
    result = {"protocol": PROTOCOL, "source_run": str(folder.resolve()),
              "system": original["system"], "case_alias": original["case_alias"],
              "same_logical_trajectory_not_independent_sample": True,
              "selection_predicate": TARGET_ERROR, "source_actor_calls": original.get("actor_calls", 0),
              "new_actor_calls": 0, "verification_events": [], "receipt": None,
              "status": "not_supported", "first_proposal": original.get("first_proposal")}
    store = RuleStore()
    phase = "saved_source_validation"
    try:
        source = load_source(folder, case_data)
        dump(output / "source_evidence.json", {key: value for key, value in source.items() if key in ("source_files", "wire_image_sha256", "observed_refs")})
        verdict = validate_verification(source["candidates"], source["verdict"], source["inputs"]["context"]["state"]["options"],
                                        observed_refs=source["observed_refs"])
        store.records = copy.deepcopy(original.get("rules", []))
        store.version = max([record.get("version", 0) for record in store.records] or [0])
        metric = source["inputs"]["context"]["task"]["primary_field_label"]
        if store.read("chart_1", metric) != source["inputs"]["context"].get("interpretation_rules", []):
            raise ValueError("cannot reconstruct prior rule state exactly")
        store.update(source["candidates"], verdict, metric=metric)
        dump(output / "reused_saved_verdict.json", verdict)
        dump(output / "saved_candidates.json", source["candidates"])
        dump(output / "rule_state_after_saved_verdict.json", store.records)
        remaining = config["max_actor_calls"] - original["actor_calls"]
        if remaining < 0:
            raise ValueError("original actor calls exceed unchanged limit")
        result["remaining_original_actor_calls"] = remaining
        phase = "state_restoration"
        with BrowserTask(case_data, output / "browser", config.get("browser_executable"), budget) as browser:
            result["restoration"] = restore_exact(browser, source, output)
            rec = verdict.get("recommendation")
            proposed = source["proposal"].get("action", {})
            event = {"step": source["step"], "proposed_action": proposed,
                     "verification": verdict, "decision": "UNRESOLVED" if rec is None else
                     "KEEP" if rec == proposed.get("option", browser.state()["current_selection"]) else "REVISE",
                     "applied_selection": None, "selection_execution": None,
                     "reused_saved_verifier_output_no_new_check_call": True}
            if rec is not None:
                phase = "saved_recommendation_application"
                event["selection_execution"] = browser.execute({"kind": "select", "option": rec}, source="verification_application")
                event["applied_selection"] = browser.state()["current_selection"]
                if not event["selection_execution"].get("ok"):
                    raise RuntimeError("saved recommendation selection execution failed")
            result["verification_events"].append(event)
            result["last_public_state"] = browser.state()
            result["history"] = copy.deepcopy(browser.history)
            dump(output / "verification_handoff.json", event)
            handoff = event
            if rec is None:
                result["status"] = "unresolved_saved_verdict"
            else:
                for offset in range(remaining):
                    phase = "actor_continuation"
                    step = source["step"] + offset + 1
                    observation = browser.snapshot("actor_input_%02d" % step)
                    context = {"task": browser.public_task, "state": observation["state"], "history": browser.history,
                               "interpretation_rules": store.read("chart_1", metric),
                               "previous_verification_and_execution": handoff}
                    images = [("chart_1", browser.chart_path), ("page_%02d" % step, observation["screenshot"])]
                    step_dir = output / ("step_%02d" % step)
                    proposal = api.call(step_dir / "actor", "actor", ACTOR, context, images)
                    result["new_actor_calls"] += 1
                    normalized = normalize(proposal)
                    dump(step_dir / "normalized_action_representation.json", normalized)
                    invalid = store.invalid_dependencies(normalized)
                    challenge = normalized.get("challenge_previous_verification") is True and bool(normalized.get("new_evidence"))
                    if challenge:
                        result["status"] = "unresolved_new_challenge"
                        dump(step_dir / "unexecuted_challenge.json", normalized)
                        break
                    if invalid:
                        handoff = {"unexecuted_proposal": normalized["action"], "dependency_problem": invalid,
                                   "instruction": "These explicitly cited rules are not active. Re-derive from valid evidence or present new evidence challenging the old check. No action was executed."}
                        dump(step_dir / "blocked_dependency.json", handoff)
                        continue
                    execution = browser.execute(normalized["action"])
                    result["last_public_state"] = browser.state()
                    result["history"] = copy.deepcopy(browser.history)
                    append(output / "actor_execution.jsonl", {"step": step, "proposal": proposal,
                           "normalized_proposal": normalized, "execution": execution})
                    if execution.get("submitted"):
                        result["status"] = "submitted"
                        result["receipt"] = browser.receipt
                        break
                else:
                    result["status"] = "remaining_actor_call_limit"
            result["last_public_state"] = browser.state()
            result["history"] = browser.history
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["failure_phase"] = phase
        result["status"] = "error" if phase in {"actor_continuation", "saved_recommendation_application"} else "not_supported"
    result["rules"] = store.records
    result["actor_calls_logical_total"] = result["source_actor_calls"] + result["new_actor_calls"]
    result["finished_at"] = time.time()
    dump(output / "trajectory.json", result)
    return result


def resume_flat_one(api, budget, config, folder, data, output):
    """Execute a stored complete flat action, then normal bounded continuation."""
    output.mkdir(parents=True, exist_ok=False)
    original = read_json(folder / "trajectory.json")
    case_data = data / original["case_alias"]
    result = {"protocol": PROTOCOL, "repair_kind": "explicit_flat_action_container",
              "source_run": str(folder.resolve()), "system": original["system"],
              "case_alias": original["case_alias"], "same_logical_trajectory_not_independent_sample": True,
              "selection_predicate": ACTION_ERROR + "; action in select/fill/check",
              "source_actor_calls": original.get("actor_calls", 0), "new_actor_calls": 0,
              "verification_events": copy.deepcopy(original.get("verification_events", [])),
              "receipt": None, "status": "not_supported", "first_proposal": original.get("first_proposal")}
    store, phase = RuleStore(), "saved_source_validation"
    try:
        source = load_flat_source(folder, case_data)
        context = source["inputs"]["context"]
        metric = context["task"]["primary_field_label"]
        full = original["system"] == "competing_persistent"
        if original["system"] not in ("ordinary", "competing_persistent"):
            raise ValueError("unsupported original system")
        handoff = context.get("previous_verification_and_execution")
        if full:
            if not handoff or not context.get("interpretation_rules") or not any(
                    item.get("source") == "verification_application" and item.get("action", {}).get("kind") == "select"
                    for item in context["history"]):
                raise ValueError("full-method action lacks prior completed verification; never bypass the first verifier")
            store.records = copy.deepcopy(original.get("rules", []))
            store.version = max([item.get("version", 0) for item in store.records] or [0])
            if store.read("chart_1", metric) != context["interpretation_rules"]:
                raise ValueError("cannot reconstruct exact prior rule state")
        dump(output / "source_evidence.json", {key: value for key, value in source.items() if key in ("source_files", "wire_image_sha256", "observed_refs")})
        dump(output / "saved_actor_proposal.json", source["proposal"])
        dump(output / "normalized_saved_proposal.json", source["normalized_proposal"])
        remaining = config["max_actor_calls"] - original["actor_calls"]
        if remaining < 0:
            raise ValueError("original actor calls exceed unchanged limit")
        result["remaining_original_actor_calls"] = remaining
        phase = "state_restoration"
        with BrowserTask(case_data, output / "browser", config.get("browser_executable"), budget) as browser:
            result["restoration"] = restore_exact(browser, source, output)
            proposal = source["normalized_proposal"]
            invalid = store.invalid_dependencies(proposal) if full else []
            challenge = full and proposal.get("challenge_previous_verification") is True and bool(proposal.get("new_evidence"))
            if challenge:
                result["status"] = "unresolved_new_challenge"
            else:
                if invalid:
                    handoff = {"unexecuted_proposal": proposal["action"], "dependency_problem": invalid,
                               "instruction": "These explicitly cited rules are not active. Re-derive from valid evidence or present new evidence challenging the old check. No action was executed."}
                    dump(output / "blocked_saved_dependency.json", handoff)
                else:
                    phase = "saved_action_execution"
                    execution = browser.execute(proposal["action"], source="saved_api_proposal_format_replay")
                    result["saved_proposal_execution"] = execution
                    append(output / "actor_execution.jsonl", {"step": source["step"], "proposal": source["proposal"],
                           "normalized_proposal": proposal, "execution": execution, "existing_call_reused": True})
                result["last_public_state"] = browser.state()
                result["history"] = copy.deepcopy(browser.history)
                for offset in range(remaining):
                    phase = "actor_continuation"
                    step = source["step"] + offset + 1
                    snap = browser.snapshot("actor_input_%02d" % step)
                    inputs = {"task": browser.public_task, "state": snap["state"], "history": browser.history}
                    if full:
                        inputs["interpretation_rules"] = store.read("chart_1", metric)
                        inputs["previous_verification_and_execution"] = handoff
                    images = [("chart_1", browser.chart_path), ("page_%02d" % step, snap["screenshot"])]
                    step_dir = output / ("step_%02d" % step)
                    raw_proposal = api.call(step_dir / "actor", "actor", ACTOR, inputs, images)
                    result["new_actor_calls"] += 1
                    proposal = normalize(raw_proposal)
                    dump(step_dir / "normalized_action_representation.json", proposal)
                    invalid = store.invalid_dependencies(proposal) if full else []
                    challenge = full and proposal.get("challenge_previous_verification") is True and bool(proposal.get("new_evidence"))
                    if challenge:
                        result["status"] = "unresolved_new_challenge"
                        dump(step_dir / "unexecuted_challenge.json", proposal)
                        break
                    if invalid:
                        handoff = {"unexecuted_proposal": proposal["action"], "dependency_problem": invalid,
                                   "instruction": "These explicitly cited rules are not active. Re-derive from valid evidence or present new evidence challenging the old check. No action was executed."}
                        dump(step_dir / "blocked_dependency.json", handoff)
                        continue
                    execution = browser.execute(proposal["action"])
                    result["last_public_state"] = browser.state()
                    result["history"] = copy.deepcopy(browser.history)
                    append(output / "actor_execution.jsonl", {"step": step, "proposal": raw_proposal,
                           "normalized_proposal": proposal, "execution": execution})
                    if execution.get("submitted"):
                        result["status"] = "submitted"
                        result["receipt"] = browser.receipt
                        break
                else:
                    result["status"] = "remaining_actor_call_limit"
            result["last_public_state"] = browser.state()
            result["history"] = browser.history
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["failure_phase"] = phase
        result["status"] = "error" if phase in {"actor_continuation", "saved_action_execution"} else "not_supported"
    result["rules"] = store.records
    result["actor_calls_logical_total"] = result["source_actor_calls"] + result["new_actor_calls"]
    result["finished_at"] = time.time()
    dump(output / "trajectory.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--data", default="data")
    parser.add_argument("--config", required=True)
    parser.add_argument("--prior-browser-ops", type=int, required=True,
                        help="All other already incurred operations not in original run, including controls and format replay")
    args = parser.parse_args()
    run, output, data = Path(args.run), Path(args.output), Path(args.data)
    if not (run / "offline_results.json").is_file():
        raise RuntimeError("Original fixed panel is not complete; no continuation is allowed yet")
    original_config = read_json(run / "config_snapshot.json")
    original_budget = read_json(run / "budget.json")
    config = remaining_config(original_config, read_json(args.config), original_budget, args.prior_browser_ops)
    output.mkdir(parents=True, exist_ok=False)
    sources = matching_sources(run)
    dump(output / "continuation_protocol.json", {
        "protocol": PROTOCOL, "selection_predicates": [TARGET_ERROR, ACTION_ERROR + "; saved action in select/fill/check"],
        "eligible_sources": [str(path.resolve()) for path in sources],
        "source_run": str(run.resolve()), "original_budget": original_budget,
        "prior_other_browser_operations": args.prior_browser_ops,
        "remaining_config": config, "new_challenges": "stop_unresolved_without_new_check_call",
        "independent_samples_added": 0,
    })
    snapshot = output / "runtime_source"
    snapshot.mkdir()
    for filename in ("resume_interfaces.py", "engine.py", "adapter.py", "format_replay.py"):
        shutil.copy2(Path(__file__).parent / filename, snapshot / filename)
    budget = Budget(output, config)
    api = API(config, budget) if sources else None
    results = []
    for source in sources:
        print("CONTINUE", source.name, flush=True)
        resumer = resume_one if read_json(source / "trajectory.json").get("error") == TARGET_ERROR else resume_flat_one
        result = resumer(api, budget, config, source, data, output / source.name)
        results.append(result)
        dump(output / "results_unscored.json", results)
        print("END", source.name, result["status"], "new attempts", budget.attempts, flush=True)
    # Only after every continuation actor has stopped: consult original scoring.
    for result in results:
        raw = read_json(data / result["case_alias"] / "offline" / "raw.json")
        result["offline_score"] = score_summary(raw, result.get("receipt"))
    dump(output / "results.json", results)
    dump(output / "combined_cost.json", {
        "original_request_attempts": original_budget["attempts"], "new_request_attempts": budget.attempts,
        "total_request_attempts": original_budget["attempts"] + budget.attempts,
        "original_browser_operations": original_budget["browser_operations"],
        "other_prior_browser_operations": args.prior_browser_ops, "continuation_browser_operations": budget.operations,
        "total_browser_operations": original_budget["browser_operations"] + args.prior_browser_ops + budget.operations,
        "independent_samples_added": 0,
    })
    print(json.dumps({"eligible": len(sources), "new_attempts": budget.attempts,
                      "new_browser_operations": budget.operations,
                      "submitted": sum(r["status"] == "submitted" for r in results)}))


if __name__ == "__main__":
    main()
