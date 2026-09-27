"""Archive actual review traces and local delivery metadata; zero model calls."""
from pathlib import Path
import copy
import json
import re
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def archive(skill, source_request, source_response, purpose, agent, status="ok", prompt=None):
    folder = PROJECT / ".aris/traces" / skill / "2026-09-25_generic_counterquestions"
    folder.mkdir(parents=True, exist_ok=True)
    prefix = folder / purpose
    if prefix.with_suffix(".request.json").exists():
        raise FileExistsError("Preserve existing review trace")
    if source_request:
        shutil.copyfile(source_request, prefix.with_suffix(".request.json"))
    else:
        dump(prefix.with_suffix(".request.json"), {"tool":"collaboration.followup_task", "agent_id":agent,
            "prompt":prompt,"model":"gpt-5.6-sol","reasoning_effort":"xhigh","purpose":purpose})
    if source_response:
        shutil.copyfile(source_response, prefix.with_suffix(".response.md"))
    else:
        prefix.with_suffix(".response.md").write_text(
            "Agent errored: You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at Sep 26th, 2026 7:24 PM.\n", encoding="utf-8")
    dump(prefix.with_suffix(".meta.json"), {"agent_id":agent,"model":"gpt-5.6-sol",
        "review_independence":"same-family","acceptance_status":"provisional","status":status,
        "semantic_acceptance":False,"purpose":purpose})
    if not (folder / "run.meta.json").exists():
        dump(folder / "run.meta.json", {"skill":skill,"run_id":"2026-09-25_generic_counterquestions",
            "project_dir":str(PROJECT),"executor":"Codex","executor_model":"not_runtime_verified",
            "review_independence":"same-family","acceptance_status":"provisional"})
    return str(folder)


def main():
    requests = HERE / "reviews"
    archive("research-refine", requests / "method_request.json", requests / "round1_method_review.md",
            "001-method", "/root/cq_method_adversary")
    followups = read(requests / "method_followups.json")
    archive("research-refine", None, requests / "round2_method_review.md", "002-method-refinement",
            "/root/cq_method_adversary", prompt=followups["messages"][1]["message"])
    archive("experiment-bridge", requests / "code_request.json", requests / "code_review.md",
            "001-code-gate", "/root/cq_code_gate")
    archive("research-refine", requests / "postrun_request.json", None,
            "003-postrun-semantic-unavailable", "/root/cq_method_adversary", "blocked_usage_limit")
    trace = PROJECT / ".aris/traces/render-html/2026-09-25_generic_counterquestions"
    trace.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(HERE / "COUNTERQUESTION_GENERAL_REVIEW.html.review.json", trace / "review.json")
    dump(trace / "run.meta.json", {"status":"REVIEW_UNAVAILABLE", "reason":"Actual reviewer route usage limit; no retry/downgrade",
        "review_independence":"same-family","acceptance_status":"provisional","model_calls":0})
    result_trace = PROJECT / ".aris/traces/result-to-claim/2026-09-25_generic_counterquestions"
    result_trace.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(requests / "POSTRUN_REVIEW_UNAVAILABLE.json", result_trace / "blocked_review.json")
    shutil.copyfile(HERE / "EVIDENCE_PRECHECK.json", result_trace / "evidence_precheck.json")
    shutil.copyfile(requests / "postrun_request.json", result_trace / "related_actual_postrun_request.json")
    dump(result_trace / "run.meta.json", {"status":"BLOCKED","verdict":"REVIEW_UNAVAILABLE",
        "fresh_claim_judgment_attempted":False,"reason":"Same reviewer service has returned usage-limit failures; do not resubmit or downgrade",
        "routing_action":"non-submission evidence report only; no expansion","semantic_verdict":None})

    summary = read(HERE / "run/summary.json")
    attempts = [read(p) for p in (HERE / "run/cases").rglob("attempt_*.json")]
    tests = ET.parse(HERE / "tests/offline_receipt_release.xml").getroot().find("testsuite")
    filelist = [p for p in HERE.rglob("*") if p.is_file() and not {"prepared","prepared_final","__pycache__",".pytest_cache"}.intersection(p.relative_to(HERE).parts)]
    secret_pattern = re.compile(r"sk-[A-Za-z0-9_-]{12,}")
    leaks = []
    for path in filelist:
        if path.suffix in {".json",".jsonl",".py",".md",".html",".xml",".txt"} and secret_pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            leaks.append(str(path.relative_to(HERE)))
    dump(HERE / "DELIVERY_CHECK.json", {"actual_requests":len(attempts),
        "all_http_200_stop":all(a.get("http_status")==200 and a.get("finish_reason")=="stop" for a in attempts),
        "models":sorted({a["response_model"] for a in attempts}), "summary_attempt_count_matches":len(attempts)==summary["request_attempts"],
        "test_count":int(tests.attrib["tests"]),"test_failures":int(tests.attrib["failures"]),
        "credential_pattern_file_matches":leaks,"postrun_semantic_review":"REVIEW_UNAVAILABLE",
        "new_model_calls":0})
    if leaks:
        raise ValueError("Credential-like content found; do not package")
    lines = ["# 本轮工件索引", "", "| File | Description |", "|---|---|"]
    for path in sorted(filelist):
        rel = path.relative_to(HERE).as_posix()
        desc = ("Actual immutable runtime/model artifact" if rel.startswith("run/") else
                "Offline test/review evidence" if rel.startswith(("tests/","reviews/")) else "Protocol / code / report / delivery")
        lines.append("| " + rel + " | " + desc + " |")
    (HERE / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"files_indexed":len(filelist),"credential_matches":len(leaks),"request_attempts":len(attempts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
