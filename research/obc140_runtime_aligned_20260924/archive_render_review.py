"""Preserve full view-fidelity instructions and response separately from model runs."""
from pathlib import Path
import argparse
import json
import shutil

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / ".aris/traces/render-html/2026-09-24_runtime_aligned"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    metadata = {"skill": "render-html", "run_id": OUT.name, "executor": "codex",
        "executor_family": "openai", "reviewer_model": "gpt-5.6-sol", "reasoning_effort": "xhigh",
        "review_independence": "same-family", "acceptance_status": "provisional",
        "project_dir": str(HERE.parents[1])}
    if args.final:
        for source, target in (
            ("reviews/FINAL_RENDER_REVIEW_REQUEST.json", "002-final.request.json"),
            ("reviews/FINAL_RENDER_SCOPE_UPDATE.json", "002-final.scope-update.json"),
            ("reviews/FINAL_RENDER_REVIEW.md", "002-final.response.md"),
            ("OBC140_TERRA_ZH_REVIEW.html.review.json", "002-final.verdict.json"),
        ):
            destination = OUT / target
            if destination.exists():
                raise FileExistsError("Preserve existing final review trace: " + str(destination))
            shutil.copyfile(HERE / source, destination)
        (OUT / "002-final.meta.json").write_text(json.dumps({**metadata, "call_number": 2,
            "purpose": "final-frozen-view-fidelity", "agent_id": "/root/runtime_view_fidelity",
            "status": "ok"}, indent=2) + "\n", encoding="utf-8")
        print(str(OUT))
        return
    (OUT / "run.meta.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(HERE / "reviews/RENDER_REVIEW_REQUEST.json", OUT / "001-preview.request.json")
    shutil.copyfile(HERE / "reviews/PREVIEW_RENDER_REVIEW.md", OUT / "001-preview.response.md")
    shutil.copyfile(HERE / "PREVIEW_IN_PROGRESS.html.review.json", OUT / "001-preview.verdict.json")
    (OUT / "001-preview.meta.json").write_text(json.dumps({**metadata, "call_number": 1,
        "purpose": "preview-fidelity", "agent_id": "/root/runtime_view_fidelity", "status": "ok"}, indent=2) + "\n", encoding="utf-8")
    print(str(OUT))


if __name__ == "__main__":
    main()
