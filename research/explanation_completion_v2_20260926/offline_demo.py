"""Synthetic Route A/B interface fixture, never a model response or chart result."""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("completion_v2_demo_workflow", HERE / "workflow.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def fixture():
    public = {"user_goal": "Choose the route with the greater quantity.", "option_labels": ["Route A", "Route B"]}
    observation = {"ref": "chart_1", "location": "two route marks",
                   "content": "The Route A mark is above the Route B mark."}
    rules = [{"id": "r1", "text": "If upward position encodes greater quantity, select the upper mark.",
              "component": "position", "conditions": "Upward position encodes greater quantity."},
             {"id": "r2", "text": "If downward position encodes greater quantity, select the lower mark.",
              "component": "position", "conditions": "Downward position encodes greater quantity."}]
    raw = {"rules": rules, "chains": [
        {"observations": [deepcopy(observation)], "rule_id": "r1", "option_label": "Route A",
         "claim": "Under the upward-value reading, Route A has greater quantity; select Route A."},
        {"observations": [deepcopy(observation)], "rule_id": "r2", "option_label": "Route B",
         "claim": "Under the downward-value reading, Route B has greater quantity; select Route B."}]}
    base = workflow.core.import_initial(raw, public)
    inputs = {"task_id": "synthetic_route_fixture", "task": public, "base_arguments": base,
              "chart_ref": "synthetic_fixture_not_a_real_image", "evidence_mode": "offline_fixture",
              "decision_reference": {"task_goal": public["user_goal"], "proposed_option": "Route A"}}
    responses = {
        "questions": {"questions": [{"id": "q1", "target_chain_ids": ["base_c1", "base_c2"],
                          "focus": "coverage", "question": "Are both position readings already expressed?"}],
                      "summary": "Synthetic fixture; not model coverage assessment."},
        "supplement": {"new_rules": [], "new_chains": [], "refinements": [], "question_responses": [
            {"question_id": "q1", "outcome": "already_covered", "record_ids": [],
             "covered_chain_ids": ["base_c1", "base_c2"], "reason": "Fixture already includes both readings."}]},
        "verification": {"schema_version": "explanation_verification_v2", "chain_checks": [],
                         "refinement_checks": [], "summary": "Synthetic interface assertions, not a visual finding."}}
    for chain in base["chains"]:
        responses["verification"]["chain_checks"].append({"target_id": chain["chain_id"],
            "O": {"status": "supported", "evidence": [deepcopy(observation)],
                  "reason": "Assumed by this synthetic test fixture, not independently observed."},
            "B_applicability": {"status": "undetermined", "evidence": [],
                                "reason": "This fixture supplies no axis mapping evidence."},
            "conditional_inference": {"status": "valid",
                "premise_ids": ["chain:" + chain["chain_id"], "rule:" + chain["rule_id"]],
                "missing_premises": [], "reason": "Under this stated direction assumption the corresponding route follows."}})
    return inputs, responses


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute().resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("Use a fresh direct child directory for the synthetic demo")
    inputs, responses = fixture()
    result = workflow.replay_fixture(inputs, responses, output)
    workflow.write(output / "fixture_source.json", {"evidence_mode": "offline_fixture", "inputs": inputs, "responses": responses})
    print(json.dumps({k: result[k] for k in ("status", "evidence_mode", "model_requests", "fixture_stages_consumed")}, ensure_ascii=False))
