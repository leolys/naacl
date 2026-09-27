"""Offline, read-only aggregation of finalized smoke and control artifacts."""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parents[1] / "runs" / "stage2_live_smoke_20260906T1219Z"


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


manifest = read(RUN / "run_manifest.json")
budget = read(RUN / "budget.json")
prefixes = lines(RUN / "evaluator" / "prefixes.jsonl")
scores = lines(RUN / "evaluator" / "scores.jsonl")
responses = [read(p) for p in sorted((RUN / "online").glob("**/responses/*.json"))]
requests = [read(p) for p in sorted((RUN / "online").glob("**/requests/*.json"))]
controls = [read(p) for p in sorted((HERE / "browser_controls").glob("**/control_budgets.json"))]
units = []
for score in scores:
    unit_id = score["unit_id"]
    result = read(RUN / "online" / "units" / unit_id / "result.json")
    policy = result.get("policy") or {}
    replay_path = RUN / "online" / "units" / unit_id / "replay.json"
    units.append({
        "unit_id": unit_id,
        "task_slug": score["task_slug"],
        "condition": score["condition"],
        "strategy": score["strategy"],
        "original_selection": policy.get("original_selection"),
        "recommended_option": policy.get("recommended_option"),
        "final_selection": score.get("selected_option_label"),
        "changed": policy.get("changed"),
        "parse_status": policy.get("parse_status"),
        "policy_calls": policy.get("model_calls"),
        "active_observations": policy.get("active_observations"),
        "successful_crops": sum(bool(r.get("artifact") and r.get("result"))
                                for r in policy.get("records", []) if r.get("phase") == "active_observation"),
        "observation_dispatch_errors": sum("error" in r for r in policy.get("records", [])
                                           if r.get("phase") == "active_observation"),
        "policy_records": policy.get("records"),
        "original_proposal": result.get("original_proposal"),
        "revision_action": result.get("revision_action"),
        "submission_observed": result.get("submission_observed"),
        "confirmation_observed": result.get("confirmation_observed"),
        "status": result.get("status"),
        "score": score.get("terminal_score"),
        "exclusion_reason": score.get("exclusion_reason"),
        "replay": read(replay_path) if replay_path.exists() else None,
    })
mock_calls = sum(c.get("mock_calls", 0) for c in controls)
control_transitions = sum(c["browser_transitions"] for c in controls)
aggregate = {
    "run_id": RUN.name,
    "started_at": manifest["started_at"],
    "completed_at": manifest["completed_at"],
    "elapsed_seconds": manifest["elapsed_seconds"],
    "model": manifest["model"],
    "real_model_smoke_status": manifest["real_model_smoke_status"],
    "configured_units": manifest["configured_units"],
    "checkpoint_count": manifest["checkpoint_count"],
    "submitted_units": manifest["submitted_units"],
    "completed_chain_units": manifest["completed_chain_units"],
    "outcome_counts": manifest["outcome_counts"],
    "run_errors": manifest["run_errors"],
    "accounting": {
        "real_model_calls": budget["model_calls"],
        "live_browser_transitions": budget["browser_transitions"],
        "control_mock_calls": mock_calls,
        "control_browser_transitions": control_transitions,
        "all_calls_including_control_mocks": budget["model_calls"] + mock_calls,
        "all_browser_transitions": budget["browser_transitions"] + control_transitions,
        "request_files": len(requests),
        "response_files": len(responses),
        "response_errors": sum(not r.get("ok") for r in responses),
        "phase_counts": dict(Counter(r["phase"] for r in requests)),
        "browser_phase_counts": dict(Counter(e["phase"] for e in budget["events"] if e["kind"] == "browser_transition")),
        "usage": {key: sum(r.get("metadata", {}).get("usage", {}).get(key, 0) for r in responses)
                  for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "image_inputs": sum(r.get("metadata", {}).get("vision_input", {}).get("image_count", 0) for r in responses),
        "image_count_distribution": dict(Counter(r.get("metadata", {}).get("vision_input", {}).get("image_count", 0) for r in responses)),
    },
    "prefixes": [{k: p.get(k) for k in ("prefix_id", "task_slug", "condition", "checkpoint_reached", "prefix_result")} for p in prefixes],
    "units": units,
    "b3_execution": {
        "units": sum(u["strategy"] == "B3" for u in units),
        "accepted_decisions": sum(u["strategy"] == "B3" and u["parse_status"] == "valid" for u in units),
        "successful_crops": sum(u["successful_crops"] for u in units if u["strategy"] == "B3"),
        "observation_dispatch_errors": sum(u["observation_dispatch_errors"] for u in units if u["strategy"] == "B3"),
        "note": "Legacy active_observations counts failed dispatches too, including responses with no observe object; it is not a count of successful visual observations.",
    },
    "interpretation": "Two-task development smoke only; not a hypothesis or generalization test. Scores copied from finalized offline evaluator, not generated by this aggregator.",
}
print(json.dumps(aggregate, ensure_ascii=False, indent=2))
