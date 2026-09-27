"""Offline preparation and fixture replay for the revised completion protocol.

No model client, credential reader, paid request, or business action is present.
Legacy initial generations are reused unchanged, not relabeled as v2 results.
"""
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
CASE_IDS = ("b001", "b002", "pub013")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


core = module("completion_v2_core", HERE / "core.py")
prompts = module("completion_v2_prompts", HERE / "prompts.py")
public_inputs = module("completion_v2_public_inputs", RESEARCH / "obc140_runtime_aligned_20260924/public_inputs.py")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_case(task_id):
    if task_id not in CASE_IDS:
        raise ValueError("Only the fixed three development inputs are prepared")
    archive = RESEARCH / "obc140_runtime_aligned_20260924"
    public_path = archive / "prepared/tasks" / task_id / "public.json"
    initial_path = archive / "run/tasks" / task_id / "generation/round_001/validated.json"
    proposal_path = archive / "run/tasks" / task_id / "proposal/round_001/validated.json"
    chart = archive / "prepared/tasks" / task_id / "chart.jpeg"
    public = read(public_path)
    if set(public) != public_inputs.PUBLIC_KEYS:
        raise ValueError("Unexpected public task projection")
    public_inputs.assert_public(public)
    generated = read(initial_path)["generated"]
    public_inputs.assert_public(generated)
    action = read(proposal_path)["proposal"]["action"]
    if action.get("kind") != "select" or action.get("option") not in public["option_labels"]:
        raise ValueError("Archived proposal is not a public selection")
    # No old rationale, verifier, selected initial chain, or hidden answer is used.
    return {"task_id": task_id, "task": public,
            "base_arguments": core.import_initial(generated, public),
            "decision_reference": {"task_goal": public["user_goal"], "proposed_option": action["option"]},
            "reference_origin": "actual_archived_actor_proposal_not_executed_selection",
            "chart_path": str(chart), "chart_ref": task_id + ":" + digest(chart),
            "source_sha256": {str(p): digest(p) for p in (public_path, initial_path, proposal_path, chart)},
            "initial_generation_protocol": "legacy_observation_boundary_v4_reused_unchanged",
            "v2_model_results": "not_run"}


def validate_relations(arguments, public, reference):
    """Validate explicit relations; never infer a negative from a different option."""
    for chain in arguments["chains"]:
        relation = chain.get("proposal_relation")
        if relation is None:
            continue
        if not reference:
            raise core.SchemaError("proposal_relation requires an actual decision reference")
        if not isinstance(relation, dict) or relation.get("target_option") != reference["proposed_option"]:
            raise core.SchemaError("proposal_relation target differs from the actual proposal")
        if relation.get("stance") not in {"supports", "refutes", "alternative", "not_addressed"}:
            raise core.SchemaError("invalid proposal_relation stance")
        if not isinstance(relation.get("reason"), str) or not relation["reason"].strip():
            raise core.SchemaError("proposal_relation needs its own explanation")
        if relation["target_option"] not in public["option_labels"]:
            raise core.SchemaError("proposal_relation target is not public")


def arguments_view(arguments):
    return {key: deepcopy(arguments.get(key, [])) for key in ("rules", "chains", "refinements")}


def build_context(stage, inputs, result=None):
    result = result or {}
    public = deepcopy(inputs["task"])
    context = {"task": public, "state": {"view_mode": "static_chart_task_review",
               "current_selection": "", "options": list(public["option_labels"])},
               "history": [], "interpretation_rules": [],
               "public_task_leaf_paths": core.public_leaf_paths(public)}
    if stage in ("generation", "questions", "supplement"):
        reference = inputs.get("decision_reference")
        if reference:
            if reference["task_goal"] != public["user_goal"] or reference["proposed_option"] not in public["option_labels"]:
                raise core.SchemaError("decision reference must match the public task and actual supplied option")
            context["decision_reference"] = deepcopy(reference)
        if stage != "generation":
            context["initial_arguments"] = arguments_view(inputs["base_arguments"])
        if stage == "supplement":
            context["counterquestions"] = deepcopy(result["questions"])
    elif stage == "verification":
        context["arguments"] = arguments_view(result["combined"])
        for chain in context["arguments"]["chains"]:
            for key in ("question_ids", "relationship", "proposal_relation", "claim_kind"):
                chain.pop(key, None)
        for note in context["arguments"]["refinements"]:
            note.pop("question_ids", None)
        # No preference/role metadata, previous assessments, or questioner verdicts.
    else:
        raise ValueError("unknown stage")
    public_inputs.assert_public(context)
    return context


def request_preview(stage, inputs, result=None):
    config = read(HERE / "config.json")
    image = "data:image/jpeg;base64," + base64.b64encode(Path(inputs["chart_path"]).read_bytes()).decode("ascii")
    return {"model": config["model_alias_for_future_authorized_validation"], "temperature": 0,
            "max_tokens": config["phase_max_tokens"]["verification" if stage == "verification" else "generation"],
            "messages": [{"role": "system", "content": prompts.GENERATOR if stage == "generation" else prompts.PROMPTS[stage]},
                         {"role": "user", "content": [
                             {"type": "text", "text": json.dumps(build_context(stage, inputs, result), ensure_ascii=False)},
                             {"type": "image_url", "image_url": {"url": image}}]}]}


def new_output(output):
    output = Path(output).absolute().resolve()
    # A fresh output cannot replace old experiments or user files.
    if output.parent != HERE or output.exists():
        raise ValueError("Use a new direct child directory of this v2 implementation")
    output.mkdir()
    return output


def prepare(output):
    output = new_output(output)
    records, sources = [], {}
    for task_id in CASE_IDS:
        inputs = load_case(task_id)
        sources.update(inputs["source_sha256"])
        write(output / task_id / "inputs.json", inputs)
        write(output / task_id / "questions_request_preview.json", request_preview("questions", inputs))
        write(output / task_id / "unverified_rule_state.json", core.build_rule_state(
            inputs["base_arguments"], None, task_id, inputs["chart_ref"], inputs["task"]))
        records.append({"task_id": task_id, "initial_chain_count": len(inputs["base_arguments"]["chains"]),
                        "new_verification": "not_run", "proposal_origin": inputs["reference_origin"]})
    for path in (HERE / "core.py", HERE / "prompts.py", HERE / "workflow.py", HERE / "config.json",
                 RESEARCH / "explanation_completion_20260925/core.py",
                 RESEARCH / "obc140_runtime_aligned_20260924/public_inputs.py"):
        sources[str(path)] = digest(path)
        relative = path.relative_to(RESEARCH)
        dest = output / "runtime_source" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write(path.read_bytes())
    summary = {"status": "prepared_not_sent", "evidence_mode": "preparation_only", "cases": records,
               "created_at": datetime.now(timezone.utc).isoformat(), "model_requests": 0,
               "gpu_operations": 0, "business_actions": 0, "source_sha256": sources,
               "source_preservation": {p: digest(p) == h for p, h in sources.items()},
               "v2_model_results": "not_run", "old_results_reinterpreted": False}
    write(output / "summary.json", summary)
    return summary


def replay_fixture(inputs, responses, output):
    """Only synthetic fixture replay. This function does not request a model verdict."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = {"mode": "offline_fixture", "evidence_mode": "offline_fixture",
              "model_requests": 0, "fixture_stages_consumed": 0, "status": "running",
              "actual_actor_use": "not_run", "business_actions": 0}
    stage = None
    try:
        for stage in ("questions", "supplement", "verification"):
            write(output / stage / "input_context.json", build_context(stage, inputs, result))
            if stage == "supplement" and not result["questions"]["questions"]:
                raw = {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": []}
            else:
                raw = deepcopy(responses[stage])
                result["fixture_stages_consumed"] += 1
            write(output / stage / "raw_fixture_response.json", raw)
            if stage == "questions":
                result[stage] = core.validate_questions(raw, inputs["base_arguments"], inputs["task"])
            elif stage == "supplement":
                result["combined"] = core.apply_supplement(raw, inputs["base_arguments"], result["questions"], inputs["task"])
                validate_relations(result["combined"], inputs["task"], inputs.get("decision_reference"))
                result[stage] = raw
            else:
                result[stage] = core.validate_verification(raw, result["combined"], inputs["task"])
                state = core.build_rule_state(result["combined"], result[stage], inputs["task_id"], inputs["chart_ref"], inputs["task"])
                state["evidence_mode"] = "offline_fixture"
                core.save_state(output / "rule_state.json", state)
                if core.load_state(output / "rule_state.json") != state:
                    raise ValueError("state reload changed content")
                result["state_reload_identical"] = True
            write(output / stage / "accepted_fixture.json", result[stage])
        result["status"] = "mock_completed"
    except Exception as exc:
        result.update(status="failed_offline_fixture", failure={"stage": stage, "type": type(exc).__name__, "reason": str(exc)})
    write(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps({key: result[key] for key in ("status", "cases", "model_requests", "v2_model_results")}, ensure_ascii=False))
