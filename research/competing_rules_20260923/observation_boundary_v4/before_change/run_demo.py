"""Run only the fixed public demo bundle; offline evaluation occurs after all actors stop."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
import traceback
from pathlib import Path

from adapter import BrowserTask, score_summary
from engine import API, ACTOR, VERIFIER, Budget, RuleStore, append, dump, verify, validate_verification
from format_replay import normalize


def one_run(api, budget, config, case_dir, system, output):
    output.mkdir(parents=True, exist_ok=False)
    store = RuleStore()
    result = {"system": system, "case_alias": case_dir.name, "actor_calls": 0,
              "verification_events": [], "first_proposal": None, "receipt": None,
              "status": "not_started", "continued_after_verification": False}
    handoff = None
    checked = False
    extra_used = 0
    try:
        with BrowserTask(case_dir, output / "browser", config.get("browser_executable"), budget) as browser:
            for step in range(config["max_actor_calls"]):
                observation = browser.snapshot("actor_input_%02d" % step)
                state = observation["state"]
                context = {"task": browser.public_task, "state": state, "history": browser.history}
                if system == "competing_persistent":
                    context["interpretation_rules"] = store.read("chart_1", browser.public_task["primary_field_label"])
                    if handoff:
                        context["previous_verification_and_execution"] = handoff
                images = [("chart_1", browser.chart_path), ("page_%02d" % step, observation["screenshot"])]
                step_dir = output / ("step_%02d" % step)
                proposal = api.call(step_dir / "actor", "actor", ACTOR, context, images)
                result["actor_calls"] += 1
                if config.get("normalize_explicit_action_container"):
                    original_proposal = proposal
                    proposal = normalize(proposal)
                    if proposal != original_proposal:
                        dump(step_dir / "action_representation_normalization.json", {
                            "original": original_proposal, "normalized": proposal,
                            "rule": "exact complete named-action fields; representation change only, no action/value inference"})
                action = proposal.get("action")
                if not isinstance(action, dict):
                    raise ValueError("actor did not return a single action")
                if action.get("kind") == "select" and result["first_proposal"] is None:
                    result["first_proposal"] = proposal
                if handoff:
                    result["continued_after_verification"] = True
                invalid = store.invalid_dependencies(proposal) if checked else []
                initial_check = system == "competing_persistent" and not checked and action.get("kind") == "select"
                challenge = (system == "competing_persistent" and checked and
                             proposal.get("challenge_previous_verification") is True and bool(proposal.get("new_evidence")))
                if invalid and not challenge:
                    handoff = {"unexecuted_proposal": action, "dependency_problem": invalid,
                               "instruction": "These explicitly cited rules are not active. Re-derive from valid evidence or present new evidence challenging the old check. No action was executed."}
                    dump(step_dir / "blocked_dependency.json", handoff)
                    continue
                if initial_check or challenge:
                    if checked and extra_used >= config["max_extra_verifications"]:
                        result["status"] = "unresolved_reverification_budget"
                        break
                    if checked:
                        extra_used += 1
                    # No proposal from evaluator, no auto-submit, no wrong-state filtering.
                    verdict = verify(api, step_dir / "defense", browser.public_task, state,
                                     browser.history, images, proposal, store, config)
                    checked = True
                    if verdict["recommendation"] is None and extra_used < config["max_extra_verifications"]:
                        extra_used += 1
                        candidates = json.loads((step_dir / "defense" / "normalized_candidates.json").read_text(encoding="utf-8"))
                        revised = api.call(step_dir / "additional_check", "additional_check", VERIFIER,
                            {"task": browser.public_task, "state": state, "history": browser.history,
                             "arguments": candidates, "previous_check": verdict,
                             "instruction": "Re-examine unresolved visible evidence once. New certainty is not required."}, images)
                        verdict = validate_verification(candidates, revised, state["options"], observed_refs=[ref for ref, _ in images])
                        store.update(candidates, verdict, metric=browser.public_task["primary_field_label"])
                    recommendation = verdict["recommendation"]
                    event = {"step": step, "proposed_action": action, "verification": verdict,
                             "decision": "UNRESOLVED" if recommendation is None else
                               "KEEP" if recommendation == action.get("option", state["current_selection"]) else "REVISE",
                             "applied_selection": None, "selection_execution": None}
                    if recommendation is not None:
                        event["selection_execution"] = browser.execute({"kind": "select", "option": recommendation}, source="verification_application")
                        event["applied_selection"] = browser.state()["current_selection"]
                    result["verification_events"].append(event)
                    handoff = event
                    dump(step_dir / "handoff.json", handoff)
                    dump(step_dir / "rule_state.json", store.records)
                    if recommendation is None:
                        result["status"] = "unresolved_visual_evidence"
                        break
                    # A filled selection does not become a submit proposal. Actor must continue.
                    continue
                execution = browser.execute(action)
                append(output / "actor_execution.jsonl", {"step": step, "proposal": proposal, "execution": execution})
                if execution.get("submitted"):
                    result["status"] = "submitted"
                    result["receipt"] = browser.receipt
                    break
            else:
                result["status"] = "actor_call_limit"
            result["last_public_state"] = browser.state()
            result["history"] = browser.history
    except Exception as exc:
        result["status"] = "error"
        result["error"] = type(exc).__name__ + ": " + str(exc)
        (output / "exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
    result["rules"] = store.records
    result["finished_at"] = time.time()
    dump(output / "trajectory.json", result)
    return result


def offline_evaluate(data, output, results):
    scored = []
    manifest = json.loads((data / "offline" / "manifest.json").read_text(encoding="utf-8"))
    meta = {item["task_alias"]: item for item in manifest["tasks"]}
    for result in results:
        alias = result["case_alias"]
        raw = json.loads((data / alias / "offline" / "raw.json").read_text(encoding="utf-8"))
        correct_label = next(a["label"] for a in raw["action_space"] if a["action_id"] == raw["expected_action_id"])
        first = (result.get("first_proposal") or {}).get("action", {}).get("option")
        score = score_summary(raw, result.get("receipt"))
        scored.append({"task": meta[alias]["task_slug"], "condition": meta[alias]["condition"],
                       "case_alias": alias, "system": result["system"], "status": result["status"],
                       "first_option": first, "first_correct": first == correct_label if first else None,
                       "verification_events": [{"decision": e["decision"],
                          "recommendation": e["verification"]["recommendation"],
                          "recommendation_correct": e["verification"]["recommendation"] == correct_label
                             if e["verification"]["recommendation"] else None,
                          "applied_selection": e["applied_selection"]} for e in result["verification_events"]],
                       "final_score": score, "actor_calls": result["actor_calls"],
                       "genuine_later_semantic_judgment_count": 0,
                       "persistence_effect": "not_applicable_native_single_decision",
                       "error": result.get("error")})
    dump(output / "offline_results.json", scored)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/demo.json")
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    data, output = Path(args.data), Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((data / "offline" / "manifest.json").read_text(encoding="utf-8"))
    if len(manifest["tasks"]) != 6 or config["systems"] != ["ordinary", "competing_persistent"]:
        raise ValueError("This entry point only runs the precommitted 12 development trajectories")
    if set(t["task_slug"] for t in manifest["tasks"]) != set(config["task_ids"]):
        raise ValueError("manifest/config mismatch")
    dump(output / "config_snapshot.json", config)
    dump(output / "runtime.json", {"python": sys.version, "platform": platform.platform(),
         "packages": {p: importlib.metadata.version(p) for p in ("requests", "Pillow", "Flask", "playwright")},
         "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}})
    source_dir = output / "runtime_source"
    source_dir.mkdir()
    import shutil
    for p in Path(__file__).parent.glob("*.py"):
        shutil.copy2(p, source_dir / p.name)
    budget = Budget(output, config)
    api = API(config, budget)
    results = []
    for task in manifest["tasks"]:
        for system in config["systems"]:
            alias = task["task_alias"]
            print("START", alias, system, flush=True)
            result = one_run(api, budget, config, data / alias, system, output / (alias + "_" + system))
            results.append(result)
            print("END", alias, system, result["status"], "attempts", budget.attempts, flush=True)
    # This is the first step that consults hidden correct actions for evaluation.
    offline_evaluate(data, output, results)
    print("DONE", len(results), "trajectories; attempts", budget.attempts, "browser operations", budget.operations, flush=True)


if __name__ == "__main__":
    main()
