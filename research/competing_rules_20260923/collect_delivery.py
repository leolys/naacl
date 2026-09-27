"""Summarize immutable versions separately; never pool them as independent tasks."""
import json
from collections import Counter
from pathlib import Path

from engine import dump


def main():
    root = Path(__file__).resolve().parent
    versions = []
    for name in ("api_demo_20260923_v1", "api_demo_20260923_v2", "health004_format_supplement_20260923"):
        folder = root / "runs" / name
        rows = json.loads((folder / "offline_results.json").read_text(encoding="utf-8"))
        budget = json.loads((folder / "budget.json").read_text(encoding="utf-8"))
        attempts = [json.loads(p.read_text(encoding="utf-8")) for p in folder.rglob("attempt_*.json")]
        methods = {}
        for method in sorted({r["system"] for r in rows}):
            subset = [r for r in rows if r["system"] == method]
            methods[method] = {"trajectories": len(subset),
                "submitted": sum(r["final_score"]["real_submission"] for r in subset),
                "correct_primary_submitted": sum(r["final_score"]["primary_outcome"] == "success" for r in subset),
                "wrong_first_proposals": sum(r["first_correct"] is False for r in subset),
                "status_counts": dict(Counter(r["status"] for r in subset))}
        versions.append({"run": name, "methods": methods, "request_attempts": budget["attempts"],
            "browser_operations": budget["browser_operations"],
            "http_statuses": dict(Counter(str(a.get("http_status")) for a in attempts)),
            "failed_attempts_including_parse": sum(bool(a.get("error")) for a in attempts),
            "requested_models": dict(Counter(a.get("requested_model") for a in attempts)),
            "response_models": dict(Counter(a.get("response_model") for a in attempts)),
            "usage_model_names": dict(Counter((a.get("usage") or {}).get("model_name") for a in attempts)),
            "known_token_totals": {key: sum((a.get("usage") or {}).get(key, 0) for a in attempts)
                                   for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
            "attempts_missing_usage": sum(not a.get("usage") for a in attempts)})
    result = {"scope": "engineering costs pooled; scientific outcomes NOT pooled across versions",
        "versions": versions, "model_request_attempts": sum(v["request_attempts"] for v in versions),
        "browser_operations_model_runs": sum(v["browser_operations"] for v in versions),
        "engineering_browser_operations": 21, "failed_exact_replay_browser_operations": 4,
        "browser_operations_total": sum(v["browser_operations"] for v in versions) + 25,
        "catalog_GET_attempts_not_inference": {"total": 3, "success": 2, "failed": 1},
        "tokens_total": {k: sum(v["known_token_totals"][k] for v in versions)
                         for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "gpu_jobs": 0, "full140_trajectories": 0,
        "effectiveness_claim": "not_established", "persistence_causal_effect": "N/A",
        "original_official_end_to_end_score": "not_computed"}
    assert result["model_request_attempts"] <= 150 and result["browser_operations_total"] <= 300
    dump(root / "DELIVERY_COSTS.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
