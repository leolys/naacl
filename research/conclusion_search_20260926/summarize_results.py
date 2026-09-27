"""Offline accounting only. Never sends candidate interpretations to a model."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(root):
    phases = []
    previous = {"request_attempts": 0, "browser_operations": 0, "events": []}
    rows = []
    for name in ("run_live_001", "run_chart_001", "run_transfer_001", "run_contract_001", "run_isolated_001", "run_joint_001"):
        directory = root / name
        if not (directory / "summary.json").is_file():
            continue
        summary, ledger = read(directory / "summary.json"), read(directory / "ledger.json")
        assert ledger["events"][:len(previous["events"])] == previous["events"], "Inherited events changed"
        phases.append({"phase": name, "status": summary["status"],
                       "requests": ledger["request_attempts"] - previous["request_attempts"],
                       "browser_operations": ledger["browser_operations"] - previous["browser_operations"],
                       "all_snapshotted_sources_preserved": all(summary.get("source_preserved", {}).values())})
        for case in ("official140", "clean140", "b002", "pub013"):
            if not (directory / case / "result.json").is_file():
                continue
            result = read(directory / case / "result.json")
            initial_path = directory / case / "shared_initial.json"
            initial = read(initial_path) if initial_path.exists() else result.get("initial", {})
            old_labels = {c["C"]["option_label"] for c in initial.get("chains", [])}
            for method, branch in result.get("branches", {}).items():
                folder = directory / case / method
                stages = branch.get("stages", {})
                hypotheses = stages.get("hypotheses")
                new_chains = (hypotheses or stages.get("supplement", {})).get("new_chains", [])
                hypothesis_calls = sorted(folder.glob("hypothesis_*/raw.json"))
                accepted = [read(p.parent / "accepted.json") for p in hypothesis_calls if (p.parent / "accepted.json").exists()]
                # Partial accepted records are counted separately; not an aggregated successful stage.
                partial_count = sum(len(p.get("chains", [])) for p in accepted)
                verification = stages.get("verification", {})
                rows.append({"phase": name, "case": case, "method": method,
                             "status": branch.get("status"), "static_only": result.get("mode") == "static_public_task_transfer",
                             "initial_chains": len(initial.get("chains", [])), "initial_action_labels": sorted(old_labels),
                             "model_questions": len(stages["questions"]["questions"]) if "questions" in stages else None,
                             "hypothesis_calls": len(hypothesis_calls), "accepted_hypothesis_calls": len(accepted),
                             "partial_hypothesis_chain_records": partial_count,
                             "aggregated_new_chains": len(new_chains) if "hypotheses" in stages or "supplement" in stages else None,
                             "new_action_labels": sorted({c["C"]["option_label"] for c in new_chains} - old_labels),
                             "verification_executed": bool(verification), "actor_calls": len(branch.get("continuation", [])),
                             "submitted": branch.get("submitted", False), "final_selection": branch.get("final_selection"),
                             "outcome": branch.get("outcome"), "error": branch.get("error"),
                             "selection_changes": [e["receipt"]["current_selection"] for e in branch.get("continuation", [])
                                                   if e.get("action", {}).get("action") == "select_option" and e.get("receipt", {}).get("executed")]})
        previous = ledger
    requests = [event for event in previous["events"] if event["kind"] == "request"]
    browsers = [event for event in previous["events"] if event["kind"] == "browser"]
    assert len(requests) == previous["request_attempts"]
    assert len(browsers) == previous["browser_operations"]
    usage = {k: sum((e.get("usage") or {}).get(k, 0) or 0 for e in requests)
             for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return {"phases": phases, "rows": rows,
            "totals": {"request_attempts": len(requests), "browser_operations": len(browsers),
                       "request_stage_counts": dict(Counter(e.get("stage") for e in requests)),
                       "http_status_counts": dict(Counter(str(e.get("http_status")) for e in requests)),
                       "retry_attempts": sum(e.get("attempt", 1) > 1 for e in requests), "usage": usage,
                       "browser_source_counts": dict(Counter(e.get("source") for e in browsers)),
                       "real_submissions": sum(r["submitted"] for r in rows), "new_natural_prefixes": 0,
                       "paid_api_requests": 0},
            "interpretation": "Development observations; no pooled success-rate estimate across adaptive variants or shared checkpoints."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = summarize(args.root)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data["totals"], ensure_ascii=False))
