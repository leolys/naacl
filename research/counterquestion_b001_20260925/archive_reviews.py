"""Archive reviewer-authored full requests/reports; never invoke a reviewer or API."""
from pathlib import Path
import json
import shutil

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def archive(skill, prefix, request, response, agent, extra=()):
    root = PROJECT / ".aris/traces" / skill / "2026-09-25_b001_counterquestion"
    root.mkdir(parents=True, exist_ok=True)
    meta = {"skill": skill, "executor": "codex", "executor_family": "openai",
            "reviewer_model": "gpt-5.6-sol", "reasoning_effort": "xhigh",
            "review_independence": "same-family", "acceptance_status": "provisional",
            "agent_id": agent, "project_dir": str(PROJECT), "status": "ok"}
    for source, dest in [(request, prefix + ".request.json"), (response, prefix + ".response.md")] + list(extra):
        target = root / dest
        if target.exists():
            raise FileExistsError("Preserve existing reviewer trace")
        shutil.copyfile(HERE / source, target)
    (root / (prefix + ".meta.json")).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if not (root / "run.meta.json").exists():
        (root / "run.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(str(root))


if __name__ == "__main__":
    archive("experiment-bridge", "001-predeployment", "reviews/PREDEPLOY_REQUEST.json",
            "reviews/PREDEPLOY_REVIEW.md", "/root/b001_counterquestion_gate",
            [("reviews/PREDEPLOY_VERDICT.json", "001-predeployment.verdict.json"),
             ("reviews/GATE_FOLLOWUPS.json", "001-predeployment.followups.json")])
    archive("experiment-bridge", "002-postrun", "reviews/POSTRUN_REQUEST.json",
            "reviews/POSTRUN_REVIEW.md", "/root/b001_counterquestion_gate")
    archive("render-html", "001-final-v2", "reviews/RENDER_REQUEST.json",
            "reviews/RENDER_REVIEW.md", "/root/b001_counterquestion_view_review",
            [("B001_COUNTERQUESTION_REVIEW_v2.html.review.json", "001-final-v2.verdict.json"),
             ("reviews/RENDER_FOLLOWUPS.json", "001-final-v2.followups.json")])
