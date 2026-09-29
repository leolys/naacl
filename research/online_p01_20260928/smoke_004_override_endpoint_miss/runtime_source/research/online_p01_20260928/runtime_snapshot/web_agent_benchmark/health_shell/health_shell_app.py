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
DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark/health_shell/approved_health_shell_tasks.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "web_agent_benchmark/health_shell/submissions.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "web_agent_benchmark/health_shell/shell_build_summary.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_records(tasks_path: Path) -> list[dict[str, Any]]:
    tasks = read_jsonl(tasks_path)
    records = []
    for index, task in enumerate(tasks, start=1):
        records.append(
            {
                "index": index - 1,
                "slug": f"health{index:03d}",
                "label": f"Health Task {index:03d}",
                "task": task,
            }
        )
    if len(records) != 19:
        raise RuntimeError(f"Expected 19 health shell tasks, found {len(records)}")
    return records


def visible_context_fields(record: dict[str, Any]) -> list[dict[str, str]]:
    fields = []
    for field in record["task"].get("companion_actions", []):
        label = str(field.get("field_label") or "")
        value = str(field.get("correct_value") or "")
        field_id = str(field.get("field_id") or label.lower().replace(" ", "_"))
        if label and value:
            fields.append({"field_id": field_id, "field_label": label, "value": value})
    return fields


def action_options(record: dict[str, Any]) -> list[dict[str, str]]:
    options = []
    for index, action in enumerate(record["task"].get("action_space", [])):
        action_id = str(action.get("action_id", ""))
        if action_id == record["task"].get("expected_action_id"):
            review_role = "correct"
        elif action_id in set(record["task"].get("misleading_action_ids", [])):
            review_role = "misleading"
        else:
            review_role = "irrelevant"
        options.append(
            {
                "token": f"option_{index}",
                "action_id": action_id,
                "label": str(action.get("label", "")),
                "review_role": review_role,
            }
        )
    return options


def is_clean_benchmark_record(record: dict[str, Any]) -> bool:
    return record["task"].get("clean_benchmark_version") == "clean_benchmark_v1"


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
        return {"outcome": "misleading_failure", "error_attribution": "chart_induced_intermediate_decision_error"}
    return {"outcome": "irrelevant_action_failure", "error_attribution": "wrong_or_irrelevant_web_action"}


def chart_path(record: dict[str, Any]) -> Path:
    path = Path(record["task"]["chart_asset"]["figure_path"])
    return path if path.is_absolute() else REPO_ROOT / path


def misleading_chart_path(record: dict[str, Any]) -> Path | None:
    if not is_clean_benchmark_record(record):
        return None
    source = record["task"].get("clean_benchmark_source") or {}
    path_value = source.get("misleading_figure_path")
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.is_absolute() else REPO_ROOT / path


def chart_compare_html(record: dict[str, Any], alt_context: str, review_mode: bool = False) -> str:
    if not review_mode:
        return f'<img class="chart" src="{url_for("chart", task_ref=record["slug"])}" alt="{h(alt_context)}">'
    misleading_path = misleading_chart_path(record)
    if misleading_path and misleading_path.exists():
        return f"""<div class="chart-compare">
          <figure><figcaption>Clean Chart</figcaption><img class="chart" src="{url_for('chart', task_ref=record['slug'])}" alt="{h(alt_context)} clean chart"></figure>
          <figure><figcaption>Original Misleading Chart</figcaption><img class="chart" src="{url_for('misleading_chart', task_ref=record['slug'])}" alt="{h(alt_context)} original misleading chart"></figure>
        </div>"""
    return f'<img class="chart" src="{url_for("chart", task_ref=record["slug"])}" alt="{h(alt_context)}">'


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
    .chart-compare {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .chart-compare figure {{ margin:0; }}
    .chart-compare figcaption {{ color:var(--muted); font-size:13px; font-weight:650; margin:0 0 6px; }}
    .field {{ margin:12px 0; }}
    label {{ display:block; font-weight:650; margin-bottom:6px; }}
    select, textarea {{ width:100%; border:1px solid var(--line); border-radius:6px; padding:9px; font:inherit; background:#fff; }}
    textarea {{ min-height:80px; resize:vertical; }}
    dl {{ display:grid; grid-template-columns:180px minmax(0,1fr); gap:8px 12px; margin:12px 0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; overflow-wrap:anywhere; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
    @media (max-width:900px) {{ .layout, .chart-compare {{ grid-template-columns:1fr; }} main {{ padding:14px; }} }}
  </style>
</head>
<body>
  <header><h1>{h(title)}</h1><div class="sub">Health Benchmark Portal</div></header>
  <main>{body}</main>
</body>
</html>"""


def review_role_badge(role: str) -> str:
    mapping = {
        "correct": ("Correct", "#176b3a", "#8abb9d", "#eef8f1"),
        "misleading": ("Misleading", "#9d352d", "#d99a94", "#fff1ef"),
        "irrelevant": ("Irrelevant", "#785a00", "#d4b36d", "#fff8e8"),
    }
    label, fg, border, bg = mapping.get(role, ("Unknown", "#475467", "#d0d5dd", "#f8f9fb"))
    return (
        f'<span style="display:inline-block;border:1px solid {border};background:{bg};'
        f'color:{fg};border-radius:999px;padding:2px 8px;font-size:12px;font-weight:600;">{h(label)}</span>'
    )


def render_index(records: list[dict[str, Any]], review_mode: bool = False) -> str:
    cards = []
    for record in records:
        task = record["task"]
        chip_values = [record["label"]] if is_clean_benchmark_record(record) and not review_mode else [
            record["label"],
            task.get("misleader_type"),
            task.get("task_readiness"),
        ]
        chips = "".join(
            f'<span class="chip">{h(value)}</span>'
            for value in chip_values
            if value
        )
        open_endpoint = "review_task_home" if review_mode else "task_home"
        cards.append(
            f"""<section class="card task-card">
              <h2>{h(record['label'])}</h2>
              <div>{h(task.get('page_title'))}</div>
              <div class="chips">{chips}</div>
              <a class="button" href="{url_for(open_endpoint, task_ref=record['slug'])}">Open Task</a>
            </section>"""
        )
    title = "Health Benchmark Portal (Reviewer View)" if review_mode else "Health Benchmark Portal"
    return page_shell(title, f"<div class=\"grid\">{''.join(cards)}</div>")


def render_task_home(record: dict[str, Any], review_mode: bool = False) -> str:
    task = record["task"]
    dashboard_endpoint = "review_dashboard" if review_mode else "dashboard"
    index_endpoint = "review_index" if review_mode else "index"
    review_chip = '<span class="chip">Reviewer View</span>' if review_mode else ""
    if is_clean_benchmark_record(record) and not review_mode:
        task_chips = f'<span class="chip">{h(record["label"])}</span>{review_chip}'
    else:
        task_chips = f"""<span class="chip">{h(record['label'])}</span>
        <span class="chip">{h(task.get('misleader_type'))}</span>
        <span class="chip">{h(task.get('task_readiness'))}</span>
        {review_chip}"""
    body = f"""<section class="card">
      <h2>{h(task.get('page_title'))}</h2>
      <p>{h(task.get('workflow_instruction'))}</p>
      <div class="chips">
        {task_chips}
      </div>
      <div class="actions">
        <a class="button" href="{url_for(dashboard_endpoint, task_ref=record['slug'])}">Open Dashboard</a>
        <a class="button secondary" href="{url_for(index_endpoint)}">Back to Portal</a>
      </div>
    </section>"""
    return page_shell(str(task.get("page_title")), body)


def render_dashboard(record: dict[str, Any], review_mode: bool = False) -> str:
    task = record["task"]
    form_endpoint = "review_form" if review_mode else "form"
    task_endpoint = "review_task_home" if review_mode else "task_home"
    review_note = "<p><strong>Reviewer note:</strong> labels for option roles appear on the form page only.</p>" if review_mode else ""
    body = f"""<section class="card">
      <h2>Dashboard</h2>
      <p>{h(task.get('chart_reference'))}</p>
      {review_note}
      {chart_compare_html(record, "health dashboard", review_mode)}
      <div class="actions">
        <a class="button" href="{url_for(form_endpoint, task_ref=record['slug'])}">Open Form</a>
        <a class="button secondary" href="{url_for(task_endpoint, task_ref=record['slug'])}">Back to Task</a>
      </div>
    </section>"""
    return page_shell(f"{task.get('page_title')} Dashboard", body)


def render_form(record: dict[str, Any], review_mode: bool = False) -> str:
    task = record["task"]
    options = action_options(record)
    option_html = '<option value="">Select a route</option>' + "".join(
        f'<option value="{h(option["token"])}">{h(option["label"])}</option>' for option in options
    )
    review_options_html = ""
    show_reviewer_labels = review_mode
    if show_reviewer_labels:
        items = []
        for option in options:
            items.append(
                f"""<div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;
                border:1px solid var(--line);border-radius:6px;padding:10px;background:#fafbfc;">
                  <div style="min-width:0;">
                    <div style="font-weight:600;">{h(option["label"])}</div>
                    <div class="sub">{h(option["action_id"])}</div>
                  </div>
                  {review_role_badge(option["review_role"])}
                </div>"""
            )
        review_options_html = (
            '<div class="panel" style="padding:0;border:none;margin:0 0 14px;background:transparent;">'
            '<h2>Action Labels</h2>'
            '<div style="display:grid;gap:8px;">'
            + "".join(items)
            + "</div></div>"
        )
    context = "".join(
        f"<dt>{h(field['field_label'])}</dt><dd>{h(field['value'])}</dd>" for field in visible_context_fields(record)
    )
    field_label = task.get("primary_action", {}).get("field_label") or "Health route"
    submit_endpoint = "submit" if not review_mode else "submit"
    dashboard_endpoint = "review_dashboard" if review_mode else "dashboard"
    review_hint = ""
    if show_reviewer_labels:
        review_hint = (
            "<p><strong>Reviewer labels:</strong> the tags below show which action is correct, misleading, or irrelevant for auditing.</p>"
        )
    body = f"""<div class="layout">
      <section class="card">
        <h2>Dashboard Reference</h2>
        <p>{h(task.get('chart_reference'))}</p>
        {chart_compare_html(record, "health dashboard reference", review_mode)}
      </section>
      <section class="card">
        <h2>{h(task.get('page_title'))}</h2>
        <p>{h(task.get('workflow_instruction'))}</p>
        {review_hint}
        <dl>{context}</dl>
        {review_options_html}
        <form method="post" action="{url_for('submit', task_ref=record['slug'])}">
          <div class="field">
            <label for="primary_action">{h(field_label)}</label>
            <select id="primary_action" name="primary_action">{option_html}</select>
          </div>
          <div class="field">
            <label for="note">Routing note</label>
            <textarea id="note" name="note" placeholder="Optional note for the health record"></textarea>
          </div>
          <div class="actions">
            <button type="submit">Submit Form</button>
            <a class="button secondary" href="{url_for(dashboard_endpoint, task_ref=record['slug'])}">Back to Dashboard</a>
          </div>
        </form>
      </section>
    </div>"""
    return page_shell(str(task.get("page_title")), body)


def make_app(tasks_path: Path = DEFAULT_TASKS, output_path: Path = DEFAULT_OUTPUT, review_ui: bool = False) -> Flask:
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"
    records = load_records(tasks_path)
    by_slug = {record["slug"]: record for record in records}
    by_task_id = {record["task"]["task_id"]: record for record in records}

    def resolve(task_ref: str) -> dict[str, Any] | None:
        return by_slug.get(task_ref) or by_task_id.get(task_ref)

    @app.get("/")
    def index() -> str:
        return render_index(records)

    @app.get("/review")
    def review_index() -> str:
        if not review_ui:
            return "Review UI is disabled", 404
        return render_index(records, review_mode=True)

    @app.get("/task/<task_ref>")
    def task_home(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_task_home", {})[record["slug"]] = True
        session.modified = True
        return render_task_home(record)

    @app.get("/review/task/<task_ref>")
    def review_task_home(task_ref: str) -> str:
        if not review_ui:
            return "Review UI is disabled", 404
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        return render_task_home(record, review_mode=True)

    @app.get("/task/<task_ref>/dashboard")
    def dashboard(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_dashboard", {})[record["slug"]] = True
        session.modified = True
        return render_dashboard(record, review_mode=review_ui)

    @app.get("/review/task/<task_ref>/dashboard")
    def review_dashboard(task_ref: str) -> str:
        if not review_ui:
            return "Review UI is disabled", 404
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        return render_dashboard(record, review_mode=True)

    @app.get("/task/<task_ref>/form")
    def form(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_form", {})[record["slug"]] = True
        session.modified = True
        return render_form(record, review_mode=review_ui)

    @app.get("/review/task/<task_ref>/form")
    def review_form(task_ref: str) -> str:
        if not review_ui:
            return "Review UI is disabled", 404
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        return render_form(record, review_mode=True)

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
        if not review_ui:
            return "Misleading chart is available only in review mode", 404
        path = misleading_chart_path(record)
        if not path or not path.exists():
            return "Missing misleading chart", 404
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
            "misleader_type": record["task"].get("misleader_type"),
            "selected_action_token": token,
            "selected_action_id": selected.get("action_id", ""),
            "selected_action_label": selected.get("label", ""),
            "visible_context_snapshot": visible_context_fields(record),
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
          <p>The health routing form has been submitted.</p>
          <div class="actions"><a class="button" href="/">Return to Portal</a></div>
        </section>"""
        return page_shell("Submission received", body)

    @app.get("/health")
    def health() -> Response:
        readiness = Counter(record["task"].get("task_readiness") for record in records)
        return jsonify(
            {
                "ok": True,
                "health_tasks": len(records),
                "readiness_distribution": dict(readiness),
                "source_distribution": dict(Counter(record["task"].get("source_dataset") for record in records)),
            }
        )

    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8037)
    parser.add_argument("--review-ui", action="store_true", help="Show clean/misleading comparison and action labels for human review.")
    args = parser.parse_args()
    make_app(args.tasks, args.output, review_ui=args.review_ui).run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
