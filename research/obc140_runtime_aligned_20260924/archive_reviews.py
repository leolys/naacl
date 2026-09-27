"""Materialize reviewer artifacts without inventing lost pre-compaction prompts."""
from pathlib import Path
import json
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / ".aris/traces/experiment-bridge/2026-09-24_runtime_aligned"


def put(name, value):
    path = OUT / name
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise FileExistsError("Existing trace differs: " + str(path))
    path.write_text(content, encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    put("run.meta.json", {"skill": "experiment-bridge", "run_id": OUT.name,
        "executor": "codex", "executor_model": "not independently recorded",
        "executor_family": "openai", "review_independence": "same-family",
        "acceptance_status": "provisional", "project_dir": str(ROOT),
        "trace_scope": "Full preserved sanity instructions and written response; older review reports retained with missing prompt disclosure"})
    requests = json.loads((HERE / "reviews/LIVE_REVIEW_REQUESTS.json").read_text(encoding="utf-8"))
    put("003-sanity.request.json", {"call_number": 3, "purpose": "three-case-live-sanity",
        "tool": "followup_task", "model": "gpt-5.6-sol", "reasoning_effort": "xhigh",
        "files_referenced": [str(HERE / "run"), str(HERE / "sanity_request_checks.json")],
        "prompt": requests["messages"][0]["payload"], "followup_messages": requests["messages"][1:]})
    for number, name, purpose in ((1, "INPUT_BOUNDARY_REVIEW", "input-boundary"),
                                   (2, "LIVE_CODE_REVIEW", "live-code"),
                                   (3, "SANITY_LIVE_REVIEW", "sanity")):
        shutil.copyfile(HERE / "reviews" / (name + ".md"), OUT / ("%03d-%s.response.md" % (number, purpose)))
        put("%03d-%s.meta.json" % (number, purpose), {"call_number": number,
            "purpose": purpose, "model": "gpt-5.6-sol", "reviewer_family": "openai",
            "review_independence": "same-family", "acceptance_status": "provisional",
            "status": "ok", "prompt_trace": "full visible instructions" if number == 3 else
            "not available in post-compaction executor context; report retained; no prompt reconstruction presented as verbatim"})
    print(str(OUT))


if __name__ == "__main__":
    main()
