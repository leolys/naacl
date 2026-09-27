"""Offline read-only aggregation; never supplies labels to the online model."""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parents[1] / "runs" / "stage2_live_smoke_20260906T1342Z"
OLD = HERE.parents[1] / "runs" / "stage2_live_smoke_20260906T1219Z"


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


manifest = read(RUN / "run_manifest.json")
budget = read(RUN / "budget.json")
prefixes = lines(RUN / "evaluator" / "prefixes.jsonl")
scores = lines(RUN / "evaluator" / "scores.jsonl")
requests = [read(p) for p in sorted((RUN / "online").glob("**/requests/*.json"))]
responses = [read(p) for p in sorted((RUN / "online").glob("**/responses/*.json"))]
browser_controls = [read(p) for p in sorted((HERE / "browser_controls").glob("**/control_budgets.json"))]
live_controls = {name: read(HERE / name / "summary.json")
                 for name in ("live_controls", "live_controls_retry1")}
control_budgets = [read(HERE / name / "budget.json") for name in live_controls]
units = []
for score in scores:
    unit_dir = RUN / "online" / "units" / score["unit_id"]
    result = read(unit_dir / "result.json")
    policy = result.get("policy") or {}
    units.append({
        **{k: score.get(k) for k in ("unit_id", "task_slug", "condition", "strategy",
                                    "selected_option_label", "terminal_score", "exclusion_reason")},
        **{k: policy.get(k) for k in ("original_selection", "recommended_option", "changed",
                                     "parse_status", "model_calls", "active_observations",
                                     "verification_metrics", "records")},
        **{k: result.get(k) for k in ("status", "submission_observed", "confirmation_observed",
                                     "original_proposal", "revision_action")},
        "replay": read(unit_dir / "replay.json") if (unit_dir / "replay.json").exists() else None,
    })
old_prefixes = {(p["task_slug"], p["condition"]): p
                for p in lines(OLD / "evaluator" / "prefixes.jsonl")}
prefix_comparison = []
for p in prefixes:
    prior = old_prefixes[(p["task_slug"], p["condition"])]
    prefix_comparison.append({
        "task_slug": p["task_slug"], "condition": p["condition"],
        "both_reached": p["checkpoint_reached"] and prior["checkpoint_reached"],
        "executed_prefix_equal": p["prefix_result"]["executed_prefix"] == prior["prefix_result"]["executed_prefix"],
        "pending_proposal_equal": p["prefix_result"]["pending_proposal"] == prior["prefix_result"]["pending_proposal"],
    })
mock_calls = sum(c.get("mock_calls", 0) for c in browser_controls)
control_transitions = sum(c["browser_transitions"] for c in browser_controls + control_budgets)
control_calls = sum(c["model_calls"] for c in control_budgets)
control_live = sum(c["live_calls"] for c in live_controls.values())
b3_metrics = Counter()
for u in units:
    if u["strategy"] == "B3":
        b3_metrics.update(u["verification_metrics"] or {})
aggregate = {
    "run_id": RUN.name,
    **{k: manifest.get(k) for k in ("started_at", "completed_at", "elapsed_seconds", "model",
                                   "real_model_smoke_status", "configured_units", "checkpoint_count",
                                   "submitted_units", "completed_chain_units", "outcome_counts", "run_errors")},
    "accounting": {
        "smoke_real_model_calls": budget["model_calls"],
        "smoke_browser_transitions": budget["browser_transitions"],
        "control_real_model_calls": control_live,
        "control_injected_calls": control_calls - control_live,
        "control_mock_calls": mock_calls,
        "control_browser_transitions": control_transitions,
        "all_real_model_calls": budget["model_calls"] + control_live,
        "all_counted_calls": budget["model_calls"] + control_calls + mock_calls,
        "all_browser_transitions": budget["browser_transitions"] + control_transitions,
        "request_files": len(requests), "response_files": len(responses),
        "response_errors": sum(not r.get("ok") for r in responses),
        "phase_counts": dict(Counter(r["phase"] for r in requests)),
        "smoke_usage": {k: sum(r.get("metadata", {}).get("usage", {}).get(k, 0) for r in responses)
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "smoke_image_count_distribution": dict(Counter(r.get("metadata", {}).get("vision_input", {}).get("image_count", 0) for r in responses)),
    },
    "b3_execution": dict(b3_metrics),
    "prefix_comparison_to_previous": prefix_comparison,
    "live_controls_all_attempts": live_controls,
    "units": units,
    "interpretation": "One two-task development engineering/diagnostic smoke. Both live synthetic control sets contain a failure; no semantic reliability, generalization, ranking or new-mechanism claim. Scores copied from finalized offline evaluator.",
}
print(json.dumps(aggregate, ensure_ascii=False, indent=2))
