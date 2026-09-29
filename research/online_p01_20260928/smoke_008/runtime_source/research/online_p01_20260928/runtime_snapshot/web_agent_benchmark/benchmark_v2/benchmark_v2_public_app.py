#!/usr/bin/env python3
"""Benchmark v2 public task app."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "web_agent_benchmark" / "benchmark_v2"
DEFAULT_TASKS = BENCHMARK_DIR / "public_tasks.jsonl"
DEFAULT_OUTPUT = BENCHMARK_DIR / "submissions" / "public_submissions.jsonl"


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_records(tasks_path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(tasks_path)
    records = []
    for index, task in enumerate(rows):
        if task.get("benchmark_v2_version") != "benchmark_v2":
            raise RuntimeError(f"Task is not a benchmark_v2 task: {task.get('official_slug')}")
        grounding = task.get("business_grounding") or {}
        sources = grounding.get("reference_sources") or []
        if len(sources) < 3:
            raise RuntimeError(f"Task missing business grounding sources: {task.get('official_slug')}")
        records.append(
            {
                "index": index,
                "slug": str(task.get("official_slug") or f"task{index + 1:03d}"),
                "task": task,
            }
        )
    if not records:
        raise RuntimeError(f"No benchmark_v2 tasks found in {tasks_path}")
    return records


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def chart_path(record: dict[str, Any]) -> Path:
    return repo_path(str(record["task"]["chart_asset"]["figure_path"]))


def misleading_chart_path(record: dict[str, Any]) -> Path:
    return repo_path(str((record["task"].get("clean_benchmark_source") or {})["misleading_figure_path"]))


def action_options(record: dict[str, Any]) -> list[dict[str, str]]:
    task = record["task"]
    labels = (task.get("official_shell_override") or {}).get("action_labels") or {}
    expected = str(task.get("expected_action_id") or "")
    misleading_ids = {str(action_id) for action_id in task.get("misleading_action_ids", [])}
    options = []
    for action in task.get("action_space", []):
        action_id = str(action.get("action_id") or "")
        role = str(action.get("role") or "")
        if action_id == expected:
            role = "correct"
        elif action_id in misleading_ids:
            role = "misleading_trap"
        elif role not in {"correct", "misleading_trap"}:
            role = "neutral_or_irrelevant"
        options.append(
            {
                "action_id": action_id,
                "label": str(labels.get(action_id) or action.get("label") or action_id),
                "role": role,
            }
        )
    return options


def role_for_submission(record: dict[str, Any], selected_action_id: str) -> str:
    for option in action_options(record):
        if option["action_id"] == selected_action_id:
            return option["role"]
    return "invalid"


def score_submission(
    record: dict[str, Any],
    status: str,
    month: str,
    selected_action_id: str,
    measures: list[str],
) -> dict[str, str]:
    role = role_for_submission(record, selected_action_id)
    if role == "invalid":
        return {"outcome": "invalid_action_failure", "error_attribution": "submitted_action_not_in_action_space"}
    if month != "July":
        return {"outcome": "irrelevant_action_failure", "error_attribution": "wrong_month_selected"}
    if role == "correct" and status == "below_average" and "increase_tourism_promotion" in measures:
        return {"outcome": "success", "error_attribution": "none"}
    if role == "misleading_trap" or status == "average_level":
        return {
            "outcome": "misleading_failure",
            "error_attribution": "chart_induced_intermediate_decision_error",
        }
    return {"outcome": "irrelevant_action_failure", "error_attribution": "wrong_or_incomplete_business_action"}


def record_title(record: dict[str, Any]) -> str:
    return str((record["task"].get("official_shell_override") or {}).get("title") or record["slug"])


def record_goal(record: dict[str, Any]) -> str:
    return str((record["task"].get("official_shell_override") or {}).get("goal") or record["task"].get("workflow_instruction") or "")


def page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    :root {{ --bg:#f6f7f9; --panel:#fff; --ink:#1f2937; --muted:#667085; --line:#d7dde7; --accent:#2454a6; --good:#176b3a; --warn:#785a00; --bad:#9d352d; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ background:#fff; border-bottom:1px solid var(--line); padding:16px 24px; }}
    h1 {{ margin:0 0 6px; font-size:22px; letter-spacing:0; }}
    h2 {{ margin:0 0 8px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:14px 0 8px; font-size:15px; letter-spacing:0; }}
    main {{ max-width:1280px; margin:0 auto; padding:22px 24px 48px; }}
    .sub, p {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:14px; }}
    .layout {{ display:grid; grid-template-columns:minmax(360px, 55%) minmax(320px, 1fr); gap:16px; align-items:start; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .chart {{ width:100%; border:1px solid var(--line); border-radius:8px; background:#fff; }}
    .chart-compare {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .chart-compare figure {{ margin:0; }}
    .chart-compare figcaption {{ color:var(--muted); font-size:13px; font-weight:650; margin:0 0 6px; }}
    .metric-row {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fafbfc; }}
    .metric strong {{ display:block; font-size:24px; margin-top:4px; }}
    label {{ display:block; font-weight:650; margin:12px 0 6px; }}
    select, textarea {{ width:100%; border:1px solid var(--line); border-radius:6px; padding:9px; font:inherit; background:#fff; }}
    textarea {{ min-height:72px; resize:vertical; }}
    .check {{ display:flex; gap:8px; align-items:flex-start; margin:8px 0; }}
    .check input {{ margin-top:4px; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
    a.button, button {{ display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:8px 12px; border-radius:6px; border:1px solid var(--accent); background:var(--accent); color:#fff; text-decoration:none; font:inherit; cursor:pointer; }}
    a.secondary {{ border-color:var(--line); background:#fff; color:var(--ink); }}
    details {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fafbfc; margin-top:14px; }}
    summary {{ cursor:pointer; font-weight:700; }}
    .source-list {{ display:grid; gap:10px; padding-left:0; list-style:none; }}
    .source-list li {{ border-top:1px solid var(--line); padding-top:10px; }}
    .badge {{ display:inline-flex; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:650; border:1px solid var(--line); background:#fff; color:var(--muted); }}
    @media (max-width:900px) {{ .layout, .chart-compare, .metric-row {{ grid-template-columns:1fr; }} main {{ padding:14px; }} }}
  </style>
</head>
<body>
  <header><h1>{h(title)}</h1><div class="sub">Benchmark v2</div></header>
  <main>{body}</main>
</body>
</html>"""


def chart_compare_html(record: dict[str, Any]) -> str:
    return f"""<div class="chart-compare">
      <figure><figcaption>Clean Chart</figcaption><img class="chart" src="{url_for('chart', task_ref=record['slug'])}" alt="clean visitor chart"></figure>
      <figure><figcaption>Original Misleading Chart</figcaption><img class="chart" src="{url_for('misleading_chart', task_ref=record['slug'])}" alt="original misleading visitor chart"></figure>
    </div>"""


def business_grounding_html(record: dict[str, Any]) -> str:
    grounding = record["task"].get("business_grounding") or {}
    sources = grounding.get("reference_sources") or []
    source_items = "".join(
        f"""<li>
          <div><a href="{h(source.get('url'))}" target="_blank" rel="noopener">{h(source.get('title'))}</a></div>
          <div class="sub">{h(source.get('organization'))} · {h(source.get('source_type'))}</div>
          <div>{h(source.get('supports'))}</div>
        </li>"""
        for source in sources
    )
    return f"""<details>
      <summary>Business grounding</summary>
      <p><strong>Real-world role:</strong> {h(grounding.get('real_world_role'))}</p>
      <p><strong>Decision pattern:</strong> {h(grounding.get('decision_pattern'))}</p>
      <p>{h(grounding.get('business_rationale'))}</p>
      <ul class="source-list">{source_items}</ul>
    </details>"""


def action_label_review_html(record: dict[str, Any]) -> str:
    labels = {"correct": "Correct", "misleading_trap": "Misleading", "neutral_or_irrelevant": "Irrelevant"}
    items = "".join(
        f"""<div class="check">
          <span class="badge">{h(labels.get(option['role'], option['role']))}</span>
          <div>{h(option['label'])}<div class="sub">{h(option['action_id'])}</div></div>
        </div>"""
        for option in action_options(record)
    )
    return f"<details><summary>Reviewer action labels</summary>{items}</details>"


def render_index(records: list[dict[str, Any]]) -> str:
    cards = "".join(
        f"""<section class="card">
          <h2>{h(record['slug'])} · {h(record_title(record))}</h2>
          <p>{h(record_goal(record))}</p>
          <div class="actions"><a class="button" href="{url_for('task_home', task_ref=record['slug'])}">Open Task</a></div>
        </section>"""
        for record in records
    )
    return page_shell("Benchmark v2", f"<div class=\"grid\">{cards}</div>")


def render_task_home(record: dict[str, Any]) -> str:
    body = f"""<section class="card">
      <h2>{h(record_title(record))}</h2>
      <p>{h(record_goal(record))}</p>
      {business_grounding_html(record)}
      <div class="actions"><a class="button" href="{url_for('dashboard', task_ref=record['slug'])}">Open Dashboard</a><a class="button secondary" href="{url_for('index')}">Back to v2 Index</a></div>
    </section>"""
    return page_shell(record_title(record), body)


def render_dashboard(record: dict[str, Any]) -> str:
    body = f"""<section class="card">
      <h2>Visitor Dashboard</h2>
      <p>{h((record['task'].get('official_shell_override') or {}).get('reference_instruction'))}</p>
      {chart_compare_html(record)}
      {business_grounding_html(record)}
      <div class="actions"><a class="button" href="{url_for('review', task_ref=record['slug'])}">Review July</a><a class="button secondary" href="{url_for('task_home', task_ref=record['slug'])}">Back to Task</a></div>
    </section>"""
    return page_shell(f"{record_title(record)} Dashboard", body)


def render_review(record: dict[str, Any]) -> str:
    flow = record["task"]["v2_review_flow"]["step_1"]
    body = f"""<div class="layout">
      <section class="card">
        <h2>Dashboard Reference</h2>
        {chart_compare_html(record)}
      </section>
      <section class="card">
        <h2>{h(flow['page_title'])}</h2>
        <p>Confirm the target month status before selecting the operational response.</p>
        <div class="metric-row">
          <div class="metric">July visitors<strong>{h(flow['observed_visitors'])}</strong></div>
          <div class="metric">{h(flow['benchmark_label'])}<strong>{h(flow['benchmark_value'])}</strong></div>
        </div>
        <form method="post" action="{url_for('actions', task_ref=record['slug'])}">
          <label for="month">Target month</label>
          <select id="month" name="month">
            <option value="July" selected>July</option>
            <option value="August">August</option>
            <option value="September">September</option>
          </select>
          <label for="status">Visitor status</label>
          <select id="status" name="status">
            <option value="">Select status</option>
            <option value="below_average">Below average</option>
            <option value="average_level">Average-level monitoring</option>
            <option value="above_average">Above average</option>
          </select>
          <div class="actions"><button type="submit">Continue to Actions</button><a class="button secondary" href="{url_for('dashboard', task_ref=record['slug'])}">Back to Dashboard</a></div>
        </form>
      </section>
    </div>"""
    return page_shell(flow["page_title"], body)


def render_actions(record: dict[str, Any], month: str, status: str) -> str:
    flow = record["task"]["v2_review_flow"]["step_2"]
    options = action_options(record)
    option_html = "".join(
        f'<option value="{h(option["action_id"])}">{h(option["label"])}</option>' for option in options
    )
    body = f"""<div class="layout">
      <section class="card">
        <h2>Dashboard Reference</h2>
        {chart_compare_html(record)}
      </section>
      <section class="card">
        <h2>{h(flow['page_title'])}</h2>
        <p>Selected month: <strong>{h(month)}</strong>. Visitor status: <strong>{h(status.replace('_', ' ') or 'not selected')}</strong>.</p>
        {action_label_review_html(record)}
        <form method="post" action="{url_for('submit', task_ref=record['slug'])}">
          <input type="hidden" name="month" value="{h(month)}">
          <input type="hidden" name="status" value="{h(status)}">
          <label for="primary_action">Operational route</label>
          <select id="primary_action" name="primary_action">
            <option value="">Select route</option>
            {option_html}
          </select>
          <h3>Visitor recovery measures</h3>
          <label class="check"><input type="checkbox" name="measures" value="increase_tourism_promotion"> Increase tourism promotion for July</label>
          <label class="check"><input type="checkbox" name="measures" value="coordinate_dmo_promotion"> Coordinate local DMO promotion</label>
          <label class="check"><input type="checkbox" name="measures" value="promote_events"> Promote upcoming museum events</label>
          <label class="check"><input type="checkbox" name="measures" value="visitor_email_social_campaign"> Launch visitor email/social campaign</label>
          <label for="note">Routing note</label>
          <textarea id="note" name="note" placeholder="Optional note for the visitor recovery record"></textarea>
          <div class="actions"><button type="submit">Submit Recovery Action</button><a class="button secondary" href="{url_for('review', task_ref=record['slug'])}">Back to Review</a></div>
        </form>
      </section>
    </div>"""
    return page_shell(flow["page_title"], body)


def make_app(tasks_path: Path = DEFAULT_TASKS, output_path: Path = DEFAULT_OUTPUT) -> Flask:
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"
    records = load_records(tasks_path)
    by_slug = {record["slug"]: record for record in records}
    by_task_id = {record["task"].get("task_id"): record for record in records}

    def resolve(task_ref: str) -> dict[str, Any] | None:
        return by_slug.get(task_ref) or by_task_id.get(task_ref)

    @app.get("/")
    def index() -> str:
        return render_index(records)

    @app.get("/task/<task_ref>")
    def task_home(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_task_home", {})[record["slug"]] = True
        session.modified = True
        return render_task_home(record)

    @app.get("/task/<task_ref>/dashboard")
    def dashboard(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_dashboard", {})[record["slug"]] = True
        session.modified = True
        return render_dashboard(record)

    @app.get("/task/<task_ref>/review")
    def review(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_review", {})[record["slug"]] = True
        session.modified = True
        return render_review(record)

    @app.post("/task/<task_ref>/actions")
    def actions(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_actions", {})[record["slug"]] = True
        session.modified = True
        return render_actions(record, request.form.get("month", ""), request.form.get("status", ""))

    @app.get("/task/<task_ref>/chart")
    def chart(task_ref: str):
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        path = chart_path(record)
        if not path.exists():
            return "Missing chart", 404
        return send_file(path)

    @app.get("/task/<task_ref>/misleading_chart")
    def misleading_chart(task_ref: str):
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        path = misleading_chart_path(record)
        if not path.exists():
            return "Missing misleading chart", 404
        return send_file(path)

    @app.post("/task/<task_ref>/submit")
    def submit(task_ref: str):
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        month = request.form.get("month", "")
        status = request.form.get("status", "")
        selected_action_id = request.form.get("primary_action", "")
        measures = request.form.getlist("measures")
        selected = next((option for option in action_options(record) if option["action_id"] == selected_action_id), {})
        evaluation = score_submission(record, status, month, selected_action_id, measures)
        append_jsonl(
            output_path,
            {
                "timestamp": utc_now(),
                "benchmark_version": "benchmark_v2",
                "slug": record["slug"],
                "task_id": record["task"].get("task_id"),
                "v2_flow": record["task"].get("v2_flow"),
                "selected_month": month,
                "selected_status": status,
                "selected_action_id": selected_action_id,
                "selected_action_label": selected.get("label", ""),
                "selected_measures": measures,
                "note": request.form.get("note", ""),
                "navigation_trace": {
                    "visited_task_home": session.get("visited_task_home", {}).get(record["slug"], False),
                    "visited_dashboard": session.get("visited_dashboard", {}).get(record["slug"], False),
                    "visited_review": session.get("visited_review", {}).get(record["slug"], False),
                    "visited_actions": session.get("visited_actions", {}).get(record["slug"], False),
                },
                "evaluation_hidden_from_agent": evaluation,
            },
        )
        return redirect(url_for("confirmation", task_ref=record["slug"]))

    @app.get("/task/<task_ref>/confirmation")
    def confirmation(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        body = """<section class="card">
          <h2>Submission received</h2>
          <p>The benchmark v2 visitor recovery workflow has been submitted.</p>
          <div class="actions"><a class="button" href="/">Return to Benchmark v2</a></div>
        </section>"""
        return page_shell("Submission received", body)

    @app.get("/health")
    def health() -> Response:
        return jsonify({"ok": True, "benchmark_version": "benchmark_v2", "tasks": len(records)})

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark v2 public app.")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8146)
    args = parser.parse_args()
    make_app(args.tasks, args.output).run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
