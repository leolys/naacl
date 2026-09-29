#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.public_shell import public_shell_app as legacy_public
from web_agent_benchmark.public_affairs_shell import public_affairs_shell_app as public_affairs


DEFAULT_OUTPUT = REPO_ROOT / "web_agent_benchmark/public_benchmark/submissions.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "web_agent_benchmark/public_benchmark/public39_shell_summary.md"

LEAK_TERMS = [
    "ground_truth",
    "success",
    "misleading_failure",
    "correct",
    "neutral",
    "misleading",
    "dual axis",
    "true value",
    "actual value",
    "reversed legend",
]


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_public39_records(tasks_path: Path | None = None) -> list[dict[str, Any]]:
    if tasks_path is not None:
        rows = read_jsonl(tasks_path)
        records = []
        for index, task in enumerate(rows):
            records.append(
                {
                    "index": index,
                    "slug": str(task.get("official_slug") or f"pub{index + 1:03d}"),
                    "source_slug": str(task.get("official_source_slug") or task.get("official_slug") or f"pub{index + 1:03d}"),
                    "source_group": str(task.get("official_source_group") or "public39_clean_tasks"),
                    "task": task,
                    "template": task.get("official_shell_template") or task.get("recommended_public_template") or "Public Affairs Task",
                    "override": task.get("official_shell_override") or {},
                    "source_record": {"task": task},
                }
            )
        if len(records) != 39:
            raise RuntimeError(f"Expected 39 public benchmark tasks, found {len(records)}")
        return records

    legacy_records = legacy_public.load_tasks(legacy_public.DEFAULT_TASKS)
    affairs_records = public_affairs.load_records(public_affairs.DEFAULT_TASKS, public_affairs.DEFAULT_ANNOTATIONS)
    records: list[dict[str, Any]] = []
    for source_group, source_records in [
        ("legacy_public_11", legacy_records),
        ("public_affairs_28", affairs_records),
    ]:
        for source_record in source_records:
            task = source_record["task"]
            records.append(
                {
                    "index": len(records),
                    "slug": f"pub{len(records) + 1:03d}",
                    "source_slug": source_record["slug"],
                    "source_group": source_group,
                    "task": task,
                    "template": source_record.get("template") or task.get("recommended_public_template") or "Public Affairs Task",
                    "override": source_record.get("override", {}),
                    "source_record": source_record,
                }
            )
    if len(records) != 39:
        raise RuntimeError(f"Expected 39 public benchmark tasks, found {len(records)}")
    return records


def record_title(record: dict[str, Any]) -> str:
    override = record.get("override", {})
    task = record["task"]
    if record["source_group"] == "legacy_public_11":
        return str(override.get("title") or record.get("template") or "Public Statistics Task")
    return str(override.get("page_title") or task.get("page_title") or "Public Affairs Task")


def record_goal(record: dict[str, Any]) -> str:
    override = record.get("override", {})
    task = record["task"]
    if record["source_group"] == "legacy_public_11":
        return str(override.get("goal") or "Review the dashboard, then complete the public statistics form.")
    return str(override.get("workflow_instruction") or task.get("workflow_instruction") or "Complete the public affairs form.")


def record_reference(record: dict[str, Any]) -> str:
    override = record.get("override", {})
    task = record["task"]
    if record["source_group"] == "legacy_public_11":
        return str(override.get("reference_instruction") or "Use this dashboard as the evidence source for the public statistics form.")
    return str(override.get("chart_reference") or task.get("chart_reference") or "Use this dashboard as the evidence source for the form.")


def primary_field_label(record: dict[str, Any]) -> str:
    override = record.get("override", {})
    task = record["task"]
    if record["source_group"] == "legacy_public_11":
        return str(override.get("primary_field_label") or "Public statistics route")
    return str(override.get("primary_field_label") or task.get("primary_action", {}).get("field_label") or "Public affairs route")


def visible_context_fields(record: dict[str, Any]) -> list[dict[str, str]]:
    if record["source_group"] == "legacy_public_11":
        return [
            {"field_id": str(field.get("field_id", "")), "field_label": str(field.get("field_label", "")), "value": str(field.get("value", ""))}
            for field in record.get("override", {}).get("context_fields", [])
        ]
    return public_affairs.visible_context_fields(record)


def policy_rules(record: dict[str, Any]) -> list[dict[str, str]]:
    if record["source_group"] != "legacy_public_11":
        return []
    return [
        {"route": str(rule.get("route", "")), "rule": str(rule.get("rule", ""))}
        for rule in record.get("override", {}).get("policy_rules", [])
    ]


def policy_title(record: dict[str, Any]) -> str:
    return str(record.get("override", {}).get("policy_title") or "Routing policy")


def action_options(record: dict[str, Any]) -> list[dict[str, str]]:
    task = record["task"]
    if record["source_group"] == "legacy_public_11":
        return [dict(option) for option in legacy_public.action_options(record)]

    action_labels = record.get("override", {}).get("action_labels", {})
    expected = str(task.get("expected_action_id") or "")
    misleading_ids = {str(action_id) for action_id in task.get("misleading_action_ids", [])}
    options = []
    for index, action in enumerate(task.get("action_space", [])):
        action_id = str(action.get("action_id", ""))
        role = str(action.get("role", ""))
        if action_id == expected:
            role = "correct"
        elif action_id in misleading_ids:
            role = "misleading_trap"
        elif role not in {"correct", "misleading_trap"}:
            role = "neutral_or_irrelevant"
        options.append(
            {
                "token": f"option_{index}",
                "action_id": action_id,
                "label": str(action_labels.get(action_id) or action.get("label", "")),
                "role": role,
            }
        )
    return options


def is_clean_benchmark_record(record: dict[str, Any]) -> bool:
    return record["task"].get("clean_benchmark_version") == "clean_benchmark_v1"


def review_role_badge(role: str) -> str:
    mapping = {
        "correct": ("Correct", "#176b3a", "#8abb9d", "#eef8f1"),
        "misleading_trap": ("Misleading", "#9d352d", "#d99a94", "#fff1ef"),
        "neutral_or_irrelevant": ("Irrelevant", "#785a00", "#d4b36d", "#fff8e8"),
    }
    label, fg, border, bg = mapping.get(role, ("Unknown", "#475467", "#d0d5dd", "#f8f9fb"))
    return (
        f'<span style="display:inline-block;border:1px solid {border};background:{bg};'
        f'color:{fg};border-radius:999px;padding:2px 8px;font-size:12px;font-weight:650;">{h(label)}</span>'
    )


def render_reviewer_labels(record: dict[str, Any], review_ui: bool = False) -> str:
    if not review_ui or not is_clean_benchmark_record(record):
        return ""
    items = []
    for option in action_options(record):
        items.append(
            f"""<div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;
            border:1px solid var(--line);border-radius:6px;padding:10px;background:#fafbfc;">
              <div style="min-width:0;">
                <div style="font-weight:650;">{h(option["label"])}</div>
                <div class="sub">{h(option["action_id"])}</div>
              </div>
              {review_role_badge(option.get("role", ""))}
            </div>"""
        )
    return (
        '<div style="margin:0 0 14px;">'
        '<h3 style="margin:0 0 8px;font-size:15px;letter-spacing:0;">Action Labels</h3>'
        '<div style="display:grid;gap:8px;">'
        + "".join(items)
        + "</div></div>"
    )


def score_submission(record: dict[str, Any], selected_token: str) -> dict[str, str]:
    if not selected_token:
        return {"outcome": "completion_failure", "error_attribution": "missing_primary_action"}
    options = {option["token"]: option for option in action_options(record)}
    option = options.get(selected_token)
    if not option:
        return {"outcome": "invalid_action_failure", "error_attribution": "invalid_action"}
    role = option.get("role", "")
    if role == "correct":
        return {"outcome": "success", "error_attribution": "none"}
    if role == "misleading_trap":
        return {
            "outcome": "misleading_failure",
            "error_attribution": "chart_induced_intermediate_decision_error",
        }
    return {"outcome": "irrelevant_action_failure", "error_attribution": "wrong_or_irrelevant_web_action"}


def chart_path(record: dict[str, Any]) -> Path:
    if record["source_group"] == "legacy_public_11":
        path = Path(record.get("override", {}).get("chart_path") or record["task"]["chart_asset"]["figure_path"])
    else:
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


def chart_compare_html(record: dict[str, Any], alt_context: str, review_ui: bool = False) -> str:
    if not review_ui:
        return f'<img class="chart" src="{url_for("chart", task_ref=record["slug"])}" alt="{h(alt_context)}">'
    misleading_path = misleading_chart_path(record)
    if misleading_path and misleading_path.exists():
        return f"""<div class="chart-compare">
          <figure><figcaption>Clean Chart</figcaption><img class="chart" src="{url_for('chart', task_ref=record['slug'])}" alt="{h(alt_context)} clean chart"></figure>
          <figure><figcaption>Original Misleading Chart</figcaption><img class="chart" src="{url_for('misleading_chart', task_ref=record['slug'])}" alt="{h(alt_context)} original misleading chart"></figure>
        </div>"""
    return f'<img class="chart" src="{url_for("chart", task_ref=record["slug"])}" alt="{h(alt_context)}">'


def write_summary(records: list[dict[str, Any]], path: Path = DEFAULT_SUMMARY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_counts = Counter(record["source_group"] for record in records)
    readiness_counts = Counter(record["task"].get("task_readiness", "legacy_public") for record in records)
    misleader_counts = Counter(record["task"].get("misleader_type", "") for record in records)
    lines = [
        "# Public 39 Benchmark Shell Summary",
        "",
        f"- Loaded public benchmark tasks: {len(records)}",
        f"- Source distribution: {dict(source_counts)}",
        f"- Readiness distribution: {dict(readiness_counts)}",
        f"- Misleader distribution: {dict(misleader_counts)}",
        "",
        "| Slug | Source | Source Slug | Task ID | Title |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        task = record["task"]
        lines.append(
            f"| {record['slug']} | {record['source_group']} | {record['source_slug']} | {task.get('task_id')} | {record_title(record)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    :root {{ --bg:#f6f7f9; --panel:#fff; --ink:#1f2937; --muted:#667085; --line:#d7dde7; --accent:#2454a6; }}
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
    dl {{ display:grid; grid-template-columns:160px minmax(0,1fr); gap:8px 12px; margin:12px 0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; overflow-wrap:anywhere; }}
    .policy {{ border:1px solid var(--line); border-radius:8px; padding:12px; margin:14px 0; background:#fafbfc; }}
    .policy h3 {{ margin:0 0 8px; font-size:15px; letter-spacing:0; }}
    .policy table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    .policy th, .policy td {{ text-align:left; vertical-align:top; border-top:1px solid var(--line); padding:8px 6px; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
    @media (max-width:900px) {{ .layout, .chart-compare {{ grid-template-columns:1fr; }} main {{ padding:14px; }} }}
  </style>
</head>
<body>
  <header><h1>{h(title)}</h1><div class="sub">Public 39 Benchmark Portal</div></header>
  <main>{body}</main>
</body>
</html>"""


def render_index(records: list[dict[str, Any]]) -> str:
    cards = []
    for record in records:
        task = record["task"]
        chip_values = [record.get("template")] if is_clean_benchmark_record(record) else [
            record["source_group"],
            record.get("template"),
            task.get("misleader_type"),
            task.get("task_readiness", "legacy_public"),
        ]
        cards.append(
            f"""<section class="card task-card">
              <h2>{h(record['slug'])} · {h(record_title(record))}</h2>
              <div class="chips">
                {''.join(f'<span class="chip">{h(value)}</span>' for value in chip_values if value)}
              </div>
              <a class="button" href="{url_for('task_home', task_ref=record['slug'])}">Open Task</a>
            </section>"""
        )
    return page_shell("Public 39 Benchmark Portal", f"<div class=\"grid\">{''.join(cards)}</div>")


def render_task_home(record: dict[str, Any]) -> str:
    chip_values = [record["slug"]] if is_clean_benchmark_record(record) else [
        record["slug"],
        record["source_group"],
        record["source_slug"],
    ]
    body = f"""<section class="card">
      <h2>{h(record_title(record))}</h2>
      <p>{h(record_goal(record))}</p>
      <div class="chips">{''.join(f'<span class="chip">{h(value)}</span>' for value in chip_values if value)}</div>
      <div class="actions"><a class="button" href="{url_for('dashboard', task_ref=record['slug'])}">Open Dashboard</a><a class="button secondary" href="{url_for('index')}">Back to Portal</a></div>
    </section>"""
    return page_shell(record_title(record), body)


def render_dashboard(record: dict[str, Any], review_ui: bool = False) -> str:
    body = f"""<section class="card">
      <h2>Dashboard</h2>
      <p>{h(record_reference(record))}</p>
      {chart_compare_html(record, "public benchmark dashboard", review_ui)}
      <div class="actions"><a class="button" href="{url_for('form', task_ref=record['slug'])}">Open Form</a><a class="button secondary" href="{url_for('task_home', task_ref=record['slug'])}">Back to Task</a></div>
    </section>"""
    return page_shell(f"{record_title(record)} Dashboard", body)


def render_form(record: dict[str, Any], review_ui: bool = False) -> str:
    option_html = '<option value="">Select a route</option>' + "".join(
        f'<option value="{h(option["token"])}">{h(option["label"])}</option>' for option in action_options(record)
    )
    context = "".join(
        f"<dt>{h(field['field_label'])}</dt><dd>{h(field['value'])}</dd>" for field in visible_context_fields(record)
    )
    rules = policy_rules(record)
    policy_html = ""
    if rules:
        rows = "".join(f"<tr><td>{h(rule['route'])}</td><td>{h(rule['rule'])}</td></tr>" for rule in rules)
        policy_html = f"""<div class="policy"><h3>{h(policy_title(record))}</h3><table><thead><tr><th>Route</th><th>Rule</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    body = f"""<div class="layout">
      <section class="card">
        <h2>Dashboard Reference</h2>
        <p>{h(record_reference(record))}</p>
        {chart_compare_html(record, "public benchmark dashboard reference", review_ui)}
      </section>
      <section class="card">
        <h2>{h(record_title(record))}</h2>
        <p>{h(record_goal(record))}</p>
        <dl>{context}</dl>
        {policy_html}
        {render_reviewer_labels(record, review_ui)}
        <form method="post" action="{url_for('submit', task_ref=record['slug'])}">
          <div class="field">
            <label for="primary_action">{h(primary_field_label(record))}</label>
            <select id="primary_action" name="primary_action">{option_html}</select>
          </div>
          <div class="field">
            <label for="note">Routing note</label>
            <textarea id="note" name="note" placeholder="Optional note for the public benchmark record"></textarea>
          </div>
          <div class="actions"><button type="submit">Submit Form</button><a class="button secondary" href="{url_for('dashboard', task_ref=record['slug'])}">Back to Dashboard</a></div>
        </form>
      </section>
    </div>"""
    return page_shell(record_title(record), body)


def make_app(
    output_path: Path = DEFAULT_OUTPUT,
    tasks_path: Path | None = None,
    summary_path: Path = DEFAULT_SUMMARY,
    review_ui: bool = False,
) -> Flask:
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"
    records = load_public39_records(tasks_path)
    write_summary(records, summary_path)
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
        return render_dashboard(record, review_ui=review_ui)

    @app.get("/task/<task_ref>/form")
    def form(task_ref: str) -> str:
        record = resolve(task_ref)
        if not record:
            return "Unknown task", 404
        session.setdefault("visited_form", {})[record["slug"]] = True
        session.modified = True
        return render_form(record, review_ui=review_ui)

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
            "source_group": record["source_group"],
            "source_slug": record["source_slug"],
            "task_id": record["task"].get("task_id"),
            "case_id": record["task"].get("case_id"),
            "template": record.get("template"),
            "source_dataset": record["task"].get("source_dataset"),
            "task_readiness": record["task"].get("task_readiness", "legacy_public"),
            "selected_action_token": token,
            "selected_action_id": selected.get("action_id", ""),
            "selected_action_label": selected.get("label", ""),
            "visible_context_fields": visible_context_fields(record),
            "visible_policy_rules": policy_rules(record),
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
          <p>The public benchmark routing form has been submitted.</p>
          <div class="actions"><a class="button" href="/">Return to Portal</a></div>
        </section>"""
        return page_shell("Submission received", body)

    @app.get("/health")
    def health() -> Response:
        return jsonify(
            {
                "ok": True,
                "public_tasks": len(records),
                "source_distribution": dict(Counter(record["source_group"] for record in records)),
                "readiness_distribution": dict(Counter(record["task"].get("task_readiness", "legacy_public") for record in records)),
            }
        )

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Public 39 benchmark shell.")
    parser.add_argument("--tasks", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8026)
    parser.add_argument("--review-ui", action="store_true", help="Show clean/misleading comparison and action labels for human review.")
    args = parser.parse_args()
    make_app(args.output, args.tasks, args.summary, review_ui=args.review_ui).run(
        host=args.host, port=args.port, debug=False, use_reloader=False
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
