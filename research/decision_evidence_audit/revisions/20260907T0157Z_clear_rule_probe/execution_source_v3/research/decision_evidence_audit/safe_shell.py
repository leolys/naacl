"""Agent-safe, single-task shell over the existing benchmark task rows.

The original task files stay untouched.  Rendering receives only a public
projection plus one chart path.  Hidden scoring is performed later by
``score_receipt`` and never appears in an HTTP response.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for

from .core import append_jsonl, public_task_projection


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ShellBundle:
    public_task: dict[str, Any]
    chart_path: Path
    token_to_label: dict[str, str]


def build_shell_bundle(
    raw_task: dict[str, Any], *, task_alias: str, repository_root: Path
) -> ShellBundle:
    public_task = public_task_projection(raw_task, task_alias=task_alias)
    raw_path = Path(str((raw_task.get("chart_asset") or {}).get("figure_path") or ""))
    chart_path = raw_path if raw_path.is_absolute() else repository_root / raw_path
    if not chart_path.is_file():
        raise FileNotFoundError(f"chart asset is missing for task alias {task_alias}")
    token_to_label = {
        f"option_{index}": label for index, label in enumerate(public_task["option_labels"])
    }
    return ShellBundle(
        public_task=public_task,
        chart_path=chart_path,
        token_to_label=token_to_label,
    )


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f5f7fa; color: #172033; font-family: Arial, sans-serif; }}
    header {{ background: #fff; border-bottom: 1px solid #d7deea; padding: 16px 24px; }}
    main {{ max-width: 1280px; margin: auto; padding: 22px 24px 42px; }}
    .card {{ background: #fff; border: 1px solid #d7deea; border-radius: 8px; padding: 18px; }}
    .layout {{ display: grid; grid-template-columns: minmax(420px, 58%) minmax(310px, 1fr); gap: 16px; align-items: start; }}
    .chart {{ display: block; width: 100%; max-height: 720px; object-fit: contain; background: #fff; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; }}
    a, button {{ border: 1px solid #2356a8; border-radius: 6px; background: #2356a8; color: #fff; padding: 9px 13px; text-decoration: none; font: inherit; cursor: pointer; }}
    a.secondary {{ background: #fff; color: #172033; border-color: #aab5c5; }}
    label {{ display: block; font-weight: 700; margin: 12px 0 6px; }}
    select, textarea {{ width: 100%; padding: 9px; border: 1px solid #aab5c5; border-radius: 0; font: inherit; }}
    textarea {{ min-height: 80px; }}
    @media (max-width: 850px) {{ .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body><header><h1>{_h(title)}</h1></header><main>{body}</main></body>
</html>"""


def _task_page(task: dict[str, Any]) -> str:
    alias = task["task_alias"]
    body = f"""<section class="card">
      <h2>Task</h2>
      <p>{_h(task['user_goal'])}</p>
      <div class="actions"><a href="{url_for('dashboard', task_alias=alias)}">Open Dashboard</a></div>
    </section>"""
    return _page(task["page_title"], body)


def _dashboard_page(task: dict[str, Any]) -> str:
    alias = task["task_alias"]
    body = f"""<section class="card">
      <h2>Dashboard</h2>
      <p>{_h(task['chart_reference'])}</p>
      <img class="chart" src="{url_for('chart', task_alias=alias)}" alt="Decision dashboard chart">
      <div class="actions">
        <a href="{url_for('form', task_alias=alias)}">Open Form</a>
        <a class="secondary" href="{url_for('task_home', task_alias=alias)}">Back to Task</a>
      </div>
    </section>"""
    return _page(f"{task['page_title']} Dashboard", body)


def _form_page(task: dict[str, Any], token_to_label: dict[str, str]) -> str:
    alias = task["task_alias"]
    option_html = '<option value="">Select a route</option>' + "".join(
        f'<option value="{_h(token)}">{_h(label)}</option>'
        for token, label in token_to_label.items()
    )
    body = f"""<div class="layout">
      <section class="card">
        <h2>Dashboard Reference</h2>
        <p>{_h(task['chart_reference'])}</p>
        <img class="chart" src="{url_for('chart', task_alias=alias)}" alt="Decision dashboard chart">
      </section>
      <section class="card">
        <h2>Submit Decision</h2>
        <p>{_h(task['user_goal'])}</p>
        <form method="post" action="{url_for('submit', task_alias=alias)}">
          <label for="primary_action">{_h(task['primary_field_label'])}</label>
          <select id="primary_action" name="primary_action">{option_html}</select>
          <label for="note">Decision note</label>
          <textarea id="note" name="note" placeholder="Optional visible note"></textarea>
          <div class="actions">
            <button type="submit">Submit Form</button>
            <a class="secondary" href="{url_for('dashboard', task_alias=alias)}">Back to Dashboard</a>
          </div>
        </form>
      </section>
    </div>"""
    return _page(task["page_title"], body)


def make_app(
    public_task: dict[str, Any],
    *,
    chart_path: Path,
    output_path: Path,
) -> Flask:
    """Create a shell that has no scorer object and emits no score fields."""

    expected_keys = {
        "task_alias",
        "page_title",
        "user_goal",
        "chart_reference",
        "primary_field_label",
        "option_labels",
    }
    if set(public_task) != expected_keys:
        raise ValueError("safe shell requires the exact public task projection")
    token_to_label = {
        f"option_{index}": label for index, label in enumerate(public_task["option_labels"])
    }
    alias = str(public_task["task_alias"])
    # Flask resolves relative send_file paths against the package directory,
    # whereas caller-supplied paths are relative to the current working directory.
    chart_path = chart_path.resolve()
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"

    def _matches(candidate: str) -> bool:
        return candidate == alias

    @app.get("/task/<task_alias>")
    def task_home(task_alias: str):
        if not _matches(task_alias):
            return "Unknown task", 404
        session["visited_task"] = True
        return _task_page(public_task)

    @app.get("/task/<task_alias>/dashboard")
    def dashboard(task_alias: str):
        if not _matches(task_alias):
            return "Unknown task", 404
        session["visited_dashboard"] = True
        return _dashboard_page(public_task)

    @app.get("/task/<task_alias>/form")
    def form(task_alias: str):
        if not _matches(task_alias):
            return "Unknown task", 404
        session["visited_form"] = True
        return _form_page(public_task, token_to_label)

    @app.get("/task/<task_alias>/chart")
    def chart(task_alias: str):
        if not _matches(task_alias):
            return "Unknown task", 404
        if not chart_path.is_file():
            return "Chart unavailable", 404
        return send_file(chart_path)

    @app.post("/task/<task_alias>/submit")
    def submit(task_alias: str):
        if not _matches(task_alias):
            return "Unknown task", 404
        token = str(request.form.get("primary_action") or "")
        receipt = {
            "timestamp": _utc_now(),
            "task_alias": alias,
            "selected_option_token": token,
            "selected_option_label": token_to_label.get(token, ""),
            "note": str(request.form.get("note") or ""),
            "navigation": {
                "visited_task": bool(session.get("visited_task")),
                "visited_dashboard": bool(session.get("visited_dashboard")),
                "visited_form": bool(session.get("visited_form")),
            },
        }
        append_jsonl(output_path, receipt)
        return redirect(url_for("confirmation", task_alias=alias))

    @app.get("/task/<task_alias>/confirmation")
    def confirmation(task_alias: str):
        if not _matches(task_alias):
            return "Unknown task", 404
        return _page(
            "Submission received",
            '<section class="card"><h2>Submission received</h2>'
            "<p>The decision form has been submitted.</p></section>",
        )

    @app.get("/health")
    def health() -> Response:
        return jsonify({"ok": True, "task_count": 1})

    return app


def score_receipt(raw_task: dict[str, Any], receipt: dict[str, Any]) -> dict[str, str]:
    """Offline-only terminal scoring; no caller result is used for branching."""

    selected_label = str(receipt.get("selected_option_label") or "")
    if not selected_label:
        return {"outcome": "completion_failure", "error_attribution": "missing_primary_action"}
    actions = raw_task.get("action_space") or []
    matches = [action for action in actions if str(action.get("label") or "") == selected_label]
    if len(matches) != 1:
        return {"outcome": "invalid_action_failure", "error_attribution": "invalid_action"}
    action_id = str(matches[0].get("action_id") or "")
    if action_id == str(raw_task.get("expected_action_id") or ""):
        return {"outcome": "success", "error_attribution": "none"}
    if action_id in {str(value) for value in raw_task.get("misleading_action_ids") or []}:
        return {
            "outcome": "misleading_failure",
            "error_attribution": "selected_dataset_misleading_option",
        }
    return {
        "outcome": "irrelevant_action_failure",
        "error_attribution": "wrong_or_irrelevant_web_action",
    }
