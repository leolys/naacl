#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark/public_affairs_tasks/benchmark_public_affairs_tasks.jsonl"
DEFAULT_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark/public_affairs_tasks/review_annotations.json"
DEFAULT_OUTPUT = REPO_ROOT / "web_agent_benchmark/public_affairs_shell/submissions.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "web_agent_benchmark/public_affairs_shell/public_affairs_shell_summary.md"

LEAK_TERMS = [
    "ground_truth",
    "success",
    "misleading_failure",
    "correct",
    "neutral",
    "misleading",
    "dual axis",
    "true value",
]

PUBLIC_AFFAIRS_OVERRIDES: dict[str, dict[str, Any]] = {
    "pa_task_9eadd12d9b_ms_unconventional_scale_directions_choropleth_ma": {
        "page_title": "State Priority Detail Routing",
        "workflow_instruction": (
            "Review the state prevalence dashboard, then open the state prevalence record "
            "that should be routed into the highest-prevalence priority follow-up workflow."
        ),
        "chart_reference": (
            "Use the state prevalence dashboard as the evidence source for selecting "
            "the highest-prevalence state record."
        ),
        "primary_field_label": "Highest-prevalence state route",
        "context_fields": [
            {"field_id": "program_area", "field_label": "Program area", "value": "Prevalence surveillance"},
            {"field_id": "jurisdiction_level", "field_label": "Jurisdiction level", "value": "State"},
            {"field_id": "record_workflow", "field_label": "Record workflow", "value": "State prevalence priority follow-up"},
            {"field_id": "routing_criterion", "field_label": "Routing criterion", "value": "Highest prevalence state in the dashboard"},
        ],
        "action_labels": {
            "correct_open_nc_prevalence_detail_for_priority_follow_up": "Open North Carolina (NC) prevalence detail for priority follow-up",
            "misleading_open_ny_prevalence_detail_for_priority_follow_up": "Open New York (NY) prevalence detail for priority follow-up",
            "neutral_open_de_prevalence_detail_for_routine_monitoring": "Open Delaware (DE) prevalence detail for routine monitoring",
        },
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_annotations(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"annotations": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("annotations", {})
    return payload


def load_records(tasks_path: Path, annotations_path: Path) -> list[dict[str, Any]]:
    annotations = load_annotations(annotations_path)["annotations"]
    tasks = []
    for task in read_jsonl(tasks_path):
        if annotations.get(task["task_id"], {}).get("status") == "approved_for_shell":
            tasks.append(task)
    records = []
    for index, task in enumerate(tasks):
        records.append({
            "index": index,
            "slug": f"pa{index + 1:03d}",
            "label": f"Public Affairs Task {index + 1:03d}",
            "task": task,
            "override": PUBLIC_AFFAIRS_OVERRIDES.get(task["task_id"], {}),
        })
    return records


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def visible_context_fields(record: dict[str, Any]) -> list[dict[str, str]]:
    override_fields = record.get("override", {}).get("context_fields")
    if override_fields:
        return [
            {
                "field_id": str(field.get("field_id", "")),
                "field_label": str(field.get("field_label", "")),
                "value": str(field.get("value", "")),
            }
            for field in override_fields
            if field.get("field_label") and field.get("value")
        ]
    task = record["task"]
    fields = []
    for field in task.get("companion_actions", []):
        label = str(field.get("field_label") or "")
        value = str(field.get("correct_value") or "")
        field_id = str(field.get("field_id") or label.lower().replace(" ", "_"))
        if not label or not value:
            continue
        fields.append({"field_id": field_id, "field_label": label, "value": value})
    return fields


def action_options(record: dict[str, Any]) -> list[dict[str, str]]:
    options = []
    action_labels = record.get("override", {}).get("action_labels", {})
    for index, action in enumerate(record["task"].get("action_space", [])):
        action_id = str(action.get("action_id", ""))
        options.append({
            "token": f"option_{index}",
            "action_id": action_id,
            "label": str(action_labels.get(action_id) or action.get("label", "")),
        })
    return options


def score_submission(record: dict[str, Any], selected_token: str) -> dict[str, str]:
    if not selected_token:
        return {"outcome": "completion_failure", "error_attribution": "missing_primary_action"}
    options = {option["token"]: option for option in action_options(record)}
    option = options.get(selected_token)
    if not option:
        return {"outcome": "invalid_action_failure", "error_attribution": "invalid_action"}
    action_id = option.get("action_id", "")
    task = record["task"]
    if action_id == task.get("expected_action_id"):
        return {"outcome": "success", "error_attribution": "none"}
    if action_id in set(task.get("misleading_action_ids", [])):
        return {
            "outcome": "misleading_failure",
            "error_attribution": "chart_induced_intermediate_decision_error",
        }
    return {"outcome": "irrelevant_action_failure", "error_attribution": "wrong_or_irrelevant_web_action"}


def chart_path(record: dict[str, Any]) -> Path:
    return Path(record["task"]["chart_asset"]["figure_path"])


def write_summary(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    readiness = Counter(record["task"].get("task_readiness") for record in records)
    misleaders = Counter(record["task"].get("misleader_type") for record in records)
    lines = [
        "# Public Affairs Shell Summary",
        "",
        f"- Loaded public affairs tasks: {len(records)}",
        f"- Readiness distribution: {dict(readiness)}",
        f"- Misleader distribution: {dict(misleaders)}",
        "- Source: approved_for_shell tasks from public_affairs_tasks review annotations.",
        "",
        "| Slug | Task ID | Readiness | Title |",
        "|---|---|---|---|",
    ]
    for record in records:
        task = record["task"]
        lines.append(f"| {record['slug']} | {task['task_id']} | {task.get('task_readiness')} | {task.get('page_title')} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    :root {{ --bg:#f6f7f8; --panel:#fff; --ink:#1f2937; --muted:#667085; --line:#d7dde7; --accent:#2454a6; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ background:#fff; border-bottom:1px solid var(--line); padding:16px 24px; }}
    h1 {{ margin:0 0 6px; font-size:22px; letter-spacing:0; }}
    h2 {{ margin:0 0 8px; font-size:18px; letter-spacing:0; }}
    .sub {{ color:var(--muted); font-size:13px; }}
    main {{ max-width:1320px; margin:0 auto; padding:22px 24px 48px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:14px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .task-card {{ display:grid; gap:10px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); border-radius:999px; padding:4px 8px; font-size:12px; color:var(--muted); background:#fafbfc; }}
    a.button, button {{ display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:8px 12px; border-radius:6px; border:1px solid var(--accent); background:var(--accent); color:#fff; text-decoration:none; font:inherit; cursor:pointer; }}
    a.secondary {{ border-color:var(--line); background:#fff; color:var(--ink); }}
    .layout {{ display:grid; grid-template-columns:minmax(360px, 56%) minmax(320px, 1fr); gap:16px; align-items:start; }}
    .chart {{ width:100%; border:1px solid var(--line); border-radius:8px; background:#fff; }}
    .field {{ margin:12px 0; }}
    label {{ display:block; font-weight:650; margin-bottom:6px; }}
    select, textarea {{ width:100%; border:1px solid var(--line); border-radius:6px; padding:9px; font:inherit; background:#fff; }}
    textarea {{ min-height:80px; resize:vertical; }}
    dl {{ display:grid; grid-template-columns:160px minmax(0,1fr); gap:8px 12px; margin:12px 0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; overflow-wrap:anywhere; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
    @media (max-width:900px) {{ .layout {{ grid-template-columns:1fr; }} main {{ padding:14px; }} }}
  </style>
</head>
<body>
  <header><h1>{h(title)}</h1><div class="sub">Public Affairs Benchmark Portal</div></header>
  <main>{body}</main>
</body>
</html>"""


def render_index(records: list[dict[str, Any]]) -> str:
    cards = []
    for record in records:
        task = record["task"]
        title = record.get("override", {}).get("page_title") or task.get("page_title")
        cards.append(
            f"""<section class="card task-card">
              <h2>{h(record['label'])}</h2>
              <div>{h(title)}</div>
              <div class="chips"><span class="chip">{h(record['label'])}</span></div>
              <a class="button" href="{url_for('task_home', task_ref=record['slug'])}">Open Task</a>
            </section>"""
        )
    return page_shell("Public Affairs Benchmark Portal", f"<div class=\"grid\">{''.join(cards)}</div>")


def render_task_home(record: dict[str, Any]) -> str:
    task = record["task"]
    override = record.get("override", {})
    title = override.get("page_title") or task.get("page_title")
    workflow = override.get("workflow_instruction") or task.get("workflow_instruction")
    body = f"""<section class="card">
      <h2>{h(title)}</h2>
      <p>{h(workflow)}</p>
      <div class="chips"><span class="chip">{h(record['label'])}</span></div>
      <div class="actions">
        <a class="button" href="{url_for('dashboard', task_ref=record['slug'])}">Open Dashboard</a>
        <a class="button secondary" href="{url_for('index')}">Back to Portal</a>
      </div>
    </section>"""
    return page_shell(str(title), body)


def render_dashboard(record: dict[str, Any]) -> str:
    task = record["task"]
    override = record.get("override", {})
    title = override.get("page_title") or task.get("page_title")
    reference = override.get("chart_reference") or task.get("chart_reference") or "Use this dashboard as the evidence source for the public affairs form."
    body = f"""<section class="card">
      <h2>Dashboard</h2>
      <p>{h(reference)}</p>
      <img class="chart" src="{url_for('chart', task_ref=record['slug'])}" alt="public affairs dashboard">
      <div class="actions">
        <a class="button" href="{url_for('form', task_ref=record['slug'])}">Open Form</a>
        <a class="button secondary" href="{url_for('task_home', task_ref=record['slug'])}">Back to Task</a>
      </div>
    </section>"""
    return page_shell(f"{title} Dashboard", body)


def render_form(record: dict[str, Any]) -> str:
    task = record["task"]
    override = record.get("override", {})
    title = override.get("page_title") or task.get("page_title")
    workflow = override.get("workflow_instruction") or task.get("workflow_instruction")
    reference = override.get("chart_reference") or task.get("chart_reference") or "Use this dashboard as the evidence source for the form."
    options = action_options(record)
    option_html = '<option value="">Select a route</option>' + "".join(
        f'<option value="{h(option["token"])}">{h(option["label"])}</option>' for option in options
    )
    context = "".join(
        f"<dt>{h(field['field_label'])}</dt><dd>{h(field['value'])}</dd>" for field in visible_context_fields(record)
    )
    field_label = override.get("primary_field_label") or task.get("primary_action", {}).get("field_label") or "Public affairs route"
    body = f"""<div class="layout">
      <section class="card">
        <h2>Dashboard Reference</h2>
        <p>{h(reference)}</p>
        <img class="chart" src="{url_for('chart', task_ref=record['slug'])}" alt="public affairs dashboard reference">
      </section>
      <section class="card">
        <h2>{h(title)}</h2>
        <p>{h(workflow)}</p>
        <dl>{context}</dl>
        <form method="post" action="{url_for('submit', task_ref=record['slug'])}">
          <div class="field">
            <label for="primary_action">{h(field_label)}</label>
            <select id="primary_action" name="primary_action">{option_html}</select>
          </div>
          <div class="field">
            <label for="note">Routing note</label>
            <textarea id="note" name="note" placeholder="Optional note for the public affairs record"></textarea>
          </div>
          <div class="actions">
            <button type="submit">Submit Form</button>
            <a class="button secondary" href="{url_for('dashboard', task_ref=record['slug'])}">Back to Dashboard</a>
          </div>
        </form>
      </section>
    </div>"""
    return page_shell(str(title), body)


def make_app(
    tasks_path: Path = DEFAULT_TASKS,
    annotations_path: Path = DEFAULT_ANNOTATIONS,
    output_path: Path = DEFAULT_OUTPUT,
) -> Flask:
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"
    records = load_records(tasks_path, annotations_path)
    write_summary(records, DEFAULT_SUMMARY)
    by_slug = {record["slug"]: record for record in records}
    by_task_id = {record["task"]["task_id"]: record for record in records}

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

    @app.get("/task/<task_ref>/form")
    def form(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_form", {})[record["slug"]] = True
        session.modified = True
        return render_form(record)

    @app.get("/task/<task_ref>/chart")
    def chart(task_ref: str):
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        path = chart_path(record)
        if not path.exists():
            return "Missing chart", 404
        return send_file(path)

    @app.post("/task/<task_ref>/submit")
    def submit(task_ref: str):
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        token = request.form.get("primary_action", "")
        options = {option["token"]: option for option in action_options(record)}
        selected = options.get(token, {})
        evaluation = score_submission(record, token)
        row = {
            "timestamp": utc_now(),
            "slug": record["slug"],
            "task_id": record["task"]["task_id"],
            "case_id": record["task"]["case_id"],
            "source_dataset": record["task"].get("source_dataset"),
            "task_readiness": record["task"].get("task_readiness"),
            "selected_action_token": token,
            "selected_action_id": selected.get("action_id", ""),
            "selected_action_label": selected.get("label", ""),
            "visible_context_fields": visible_context_fields(record),
            "note": request.form.get("note", ""),
            "navigation_trace": {
                "visited_task_home": session.get("visited_task_home", {}).get(record["slug"], False),
                "visited_dashboard": session.get("visited_dashboard", {}).get(record["slug"], False),
                "visited_form": session.get("visited_form", {}).get(record["slug"], False),
            },
            "evaluation_hidden_from_agent": evaluation,
        }
        append_jsonl(output_path, row)
        return redirect(url_for("confirmation", task_ref=record["slug"]))

    @app.get("/task/<task_ref>/confirmation")
    def confirmation(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        body = """<section class="card">
          <h2>Submission received</h2>
          <p>The public affairs routing form has been submitted.</p>
          <div class="actions"><a class="button" href="/">Return to Portal</a></div>
        </section>"""
        return page_shell("Submission received", body)

    @app.get("/health")
    def health() -> Response:
        readiness = Counter(record["task"].get("task_readiness") for record in records)
        return jsonify({
            "ok": True,
            "public_affairs_tasks": len(records),
            "readiness_distribution": dict(readiness),
            "source_distribution": dict(Counter(record["task"].get("source_dataset") for record in records)),
        })

    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8025)
    args = parser.parse_args()
    make_app(args.tasks, args.annotations, args.output).run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
