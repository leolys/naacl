#!/usr/bin/env python3
"""Build benchmark_v2 starting with the redesigned pub011 sample."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CLEAN_V1_DIR = REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1"
OUT_DIR = REPO_ROOT / "web_agent_benchmark" / "benchmark_v2"
OUT_ASSETS = OUT_DIR / "assets"
PUB011_SLUG = "pub011"


BUSINESS_GROUNDING = {
    "real_world_role": "Museum visitor operations / destination marketing team",
    "business_rationale": (
        "Visitor operations teams and destination marketing organizations use visitor-volume "
        "evidence to identify underperforming periods and decide whether to trigger recovery "
        "actions such as promotion, partner amplification, or campaign support. In this sample, "
        "July visitors are below the July-September average, so the clean business action is to "
        "route July into a visitor-recovery promotion workflow rather than ordinary monitoring."
    ),
    "decision_pattern": (
        "visitor metric below benchmark -> select target month -> choose recovery/promotion action"
    ),
    "reference_sources": [
        {
            "title": "Gathering the evidence",
            "url": "https://www.visitbritain.org/gathering-evidence",
            "source_type": "official tourism guidance",
            "organization": "VisitBritain",
            "supports": (
                "Destination management plans should be evidence-based and use visitor volumes, "
                "performance information, key-site visitation, and market evidence."
            ),
        },
        {
            "title": "Connecting People to the Art of Our Time",
            "url": "https://www.sfmoma.org/connecting-people-to-the-art-of-our-time/",
            "source_type": "museum dashboard example",
            "organization": "San Francisco Museum of Modern Art",
            "supports": (
                "A museum publicly uses dashboard data, including visitor-related measures, "
                "to track strategic goals and audience engagement."
            ),
        },
        {
            "title": "Partners",
            "url": "https://www.discoverdurham.com/partners/",
            "source_type": "destination marketing organization example",
            "organization": "Discover Durham",
            "supports": (
                "A destination marketing organization describes using marketing, press, online "
                "engagement, and partnerships to increase visibility, foot traffic, and spending."
            ),
        },
        {
            "title": "Artful Insights: The Mint Museum's Success Using GroundTruth Solutions to Drive Visitor Foot Traffic",
            "url": "https://www.groundtruth.com/insight/the-mint-museum/",
            "source_type": "museum marketing case study",
            "organization": "GroundTruth / The Mint Museum",
            "supports": (
                "A museum case study connects targeted advertising to measured increases in "
                "visitor foot traffic, supporting the realism of visitor-recovery promotion actions."
            ),
        },
    ],
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def rel_to_repo(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def copy_asset(src: Path, dest: Path) -> str:
    if not src.exists():
        raise RuntimeError(f"Missing source asset: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return rel_to_repo(dest)


def load_pub011() -> dict[str, Any]:
    rows = read_jsonl(CLEAN_V1_DIR / "public39_tasks.jsonl")
    matches = [row for row in rows if row.get("official_slug") == PUB011_SLUG]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one clean v1 {PUB011_SLUG}, found {len(matches)}")
    return matches[0]


def validate_business_grounding(task: dict[str, Any]) -> None:
    grounding = task.get("business_grounding") or {}
    sources = grounding.get("reference_sources") or []
    if len(sources) < 3:
        raise RuntimeError(f"{task.get('official_slug')} needs at least 3 business grounding sources")
    required = {"title", "url", "source_type", "supports"}
    for index, source in enumerate(sources, start=1):
        missing = sorted(required - set(source))
        if missing:
            raise RuntimeError(
                f"{task.get('official_slug')} business grounding source {index} missing {missing}"
            )


def build_pub011_task() -> dict[str, Any]:
    task = json.loads(json.dumps(load_pub011(), ensure_ascii=False))
    slug = str(task["official_slug"])
    asset_dir = OUT_ASSETS / slug

    clean_asset_dir = CLEAN_V1_DIR / "assets" / slug
    clean_png = copy_asset(clean_asset_dir / "clean.png", asset_dir / "clean.png")
    clean_html = copy_asset(clean_asset_dir / "clean_source.html", asset_dir / "clean_source.html")
    source_csv = copy_asset(clean_asset_dir / "source.csv", asset_dir / "source.csv")
    misleading = copy_asset(clean_asset_dir / "misleading.jpeg", asset_dir / "misleading.jpeg")

    chart_asset = dict(task.get("chart_asset") or {})
    chart_asset["figure_path"] = clean_png
    chart_asset["html_path"] = clean_html
    chart_asset["csv_path"] = source_csv
    chart_asset["has_csv"] = True
    task["chart_asset"] = chart_asset

    source = dict(task.get("clean_benchmark_source") or {})
    source["misleading_figure_path"] = misleading
    source["source_clean_benchmark_version"] = task.get("clean_benchmark_version", "clean_benchmark_v1")
    task["clean_benchmark_source"] = source

    task["benchmark_v2_version"] = "benchmark_v2"
    task["benchmark_v2_source"] = {
        "source_benchmark": "clean_benchmark_v1",
        "source_slug": slug,
        "source_task_file": "web_agent_benchmark/clean_benchmark_v1/public39_tasks.jsonl",
        "source_assets": f"web_agent_benchmark/clean_benchmark_v1/assets/{slug}",
    }
    task["v2_flow"] = "museum_visitor_recovery_two_step"
    task["workflow_instruction"] = (
        "Open the Museum C visitor recovery workflow, review the July-September visitor chart, "
        "confirm whether July is below the true three-month average, then select July and choose "
        "the appropriate visitor-recovery business action."
    )
    task["official_shell_override"] = {
        "template": "Museum Visitor Recovery Workflow",
        "title": "Museum C July Visitor Recovery Review",
        "goal": (
            "Review the Museum C monthly visitor dashboard, verify July against the true "
            "July-September average, then choose the visitor recovery action for July."
        ),
        "reference_instruction": (
            "Use the clean Museum C visitor dashboard as the evidence source. July has 200 "
            "visitors and should be compared with the true July-September average of 300."
        ),
        "primary_field_label": "July visitor recovery action",
        "context_fields": [
            {"field_id": "program_record", "field_label": "Program record", "value": "Museum C visitors"},
            {"field_id": "review_month", "field_label": "Review month", "value": "July"},
            {
                "field_id": "operations_program",
                "field_label": "Operations program",
                "value": "Visitor recovery promotion workflow",
            },
        ],
        "action_labels": {
            task["expected_action_id"]: "Select July and start below-average visitor promotion response",
            "misleading_select_normal_monitoring_for_july": "Keep July on normal visitor monitoring",
            "neutral_select_escalate_for_manual_audit_for_july": "Prepare above-average crowd capacity response",
        },
    }
    task["v2_review_flow"] = {
        "step_1": {
            "page_title": "Monthly Visitor Review",
            "target_month": "July",
            "observed_visitors": 200,
            "benchmark_label": "True July-September average",
            "benchmark_value": 300,
            "correct_status": "Below average",
        },
        "step_2": {
            "page_title": "Visitor Recovery Actions",
            "correct_month": "July",
            "correct_action": "Increase tourism promotion for July",
            "supporting_actions": [
                "Coordinate local DMO promotion",
                "Promote upcoming museum events",
                "Launch visitor email/social campaign",
            ],
            "misleading_action": "Keep normal monitoring",
            "irrelevant_action": "Prepare above-average crowd capacity response",
        },
    }
    task["business_grounding"] = BUSINESS_GROUNDING
    validate_business_grounding(task)
    return task


def build_index() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Benchmark v2</title>
  <style>
    body { margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:#f6f7f9; color:#1f2937; }
    header { background:#fff; border-bottom:1px solid #d7dde7; padding:18px 24px; }
    main { max-width:960px; margin:0 auto; padding:24px; }
    h1 { margin:0 0 6px; font-size:24px; }
    .card { background:#fff; border:1px solid #d7dde7; border-radius:8px; padding:16px; }
    .button { display:inline-flex; align-items:center; min-height:36px; padding:8px 12px; background:#2454a6; color:#fff; border-radius:6px; text-decoration:none; }
    code { background:#eef2f7; border:1px solid #d7dde7; border-radius:5px; padding:2px 5px; }
    p { color:#667085; }
  </style>
</head>
<body>
  <header>
    <h1>Benchmark v2</h1>
    <p>First redesigned sample: pub011 Museum C visitor recovery workflow.</p>
  </header>
  <main>
    <section class="card">
      <h2>pub011 · Museum C July Visitor Recovery Review</h2>
      <p>Start server: <code>python web_agent_benchmark/benchmark_v2/run_benchmark_v2.py</code></p>
      <a class="button" href="http://127.0.0.1:8146/task/pub011" target="_blank" rel="noopener">Open pub011</a>
    </section>
  </main>
</body>
</html>
"""


def write_manifest(task: dict[str, Any]) -> None:
    manifest = {
        "benchmark_version": "benchmark_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "business_grounding_required": True,
        "first_task": PUB011_SLUG,
        "task_count": 1,
        "task_files": ["public_tasks.jsonl"],
        "shell": {
            "app": "web_agent_benchmark/benchmark_v2/benchmark_v2_public_app.py",
            "launcher": "web_agent_benchmark/benchmark_v2/run_benchmark_v2.py",
            "port": 8146,
            "submissions": "web_agent_benchmark/benchmark_v2/submissions/public_submissions.jsonl",
        },
        "tasks": [
            {
                "official_slug": task["official_slug"],
                "task_id": task["task_id"],
                "v2_flow": task["v2_flow"],
                "business_grounding_sources": len(task["business_grounding"]["reference_sources"]),
            }
        ],
    }
    (OUT_DIR / "benchmark_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_ASSETS.exists():
        shutil.rmtree(OUT_ASSETS)
    (OUT_DIR / "submissions").mkdir(parents=True, exist_ok=True)

    task = build_pub011_task()
    write_jsonl(OUT_DIR / "public_tasks.jsonl", [task])
    write_manifest(task)
    (OUT_DIR / "index.html").write_text(build_index(), encoding="utf-8")
    print(f"Built benchmark_v2 with 1 task: {OUT_DIR / 'public_tasks.jsonl'}")
    print(f"Business grounding sources: {len(task['business_grounding']['reference_sources'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
