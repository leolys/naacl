#!/usr/bin/env python3
"""Visual review page for Business 47 LLM dry-run traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from flask import Flask, abort, render_template_string, request, send_file


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "business47_llm_dryrun_runs.jsonl"
SCREENSHOT_ROOT = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "screenshots"


def load_runs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def pretty_action(action: dict[str, Any]) -> str:
    kind = action.get("action", "")
    if kind == "click_link":
        return f"Click link: {action.get('text', '')}"
    if kind == "click_button":
        return f"Click button: {action.get('text', '')}"
    if kind == "select_option":
        return f"Select {action.get('select_name', '')}: {action.get('option_text', '')}"
    if kind == "finish":
        return "Finish"
    if not action:
        return "No action recorded"
    return json.dumps(action, ensure_ascii=False)


def create_app(runs_path: Path = DEFAULT_RUNS) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        rows = load_runs(runs_path)
        outcome_counts: dict[str, int] = {}
        for row in rows:
            outcome_counts[row.get("outcome", "unknown")] = outcome_counts.get(row.get("outcome", "unknown"), 0) + 1

        return render_template_string(
            TEMPLATE,
            rows=rows,
            runs_path=str(runs_path),
            outcome_counts=outcome_counts,
            pretty_action=pretty_action,
        )

    @app.get("/shot")
    def shot():
        raw_path = request.args.get("path", "")
        if not raw_path:
            abort(404)
        path = Path(raw_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        resolved = path.resolve()
        try:
            resolved.relative_to(SCREENSHOT_ROOT.resolve())
        except ValueError:
            abort(403)
        if not resolved.exists():
            abort(404)
        return send_file(resolved)

    @app.get("/health")
    def health() -> dict[str, Any]:
        rows = load_runs(runs_path)
        return {"ok": True, "runs": len(rows), "runs_path": str(runs_path)}

    return app


TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Business 47 LLM Dry Run Trace Review</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1d2430;
      --muted: #5f6875;
      --line: #d9dee7;
      --accent: #1f6feb;
      --ok: #167a3a;
      --bad: #b42318;
      --warn: #9a6700;
      --soft: #eef2f7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      background: rgba(255, 255, 255, 0.95);
      border-bottom: 1px solid var(--line);
      padding: 16px 24px;
      backdrop-filter: blur(10px);
    }
    h1 { margin: 0 0 8px; font-size: 22px; letter-spacing: 0; }
    .sub { color: var(--muted); font-size: 13px; }
    .wrap { padding: 22px 24px 60px; max-width: 1480px; margin: 0 auto; }
    .summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .metric strong { display: block; font-size: 24px; margin-top: 4px; }
    .task {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 18px 0;
      overflow: hidden;
    }
    .task-head {
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: start;
    }
    h2 { margin: 0 0 6px; font-size: 18px; letter-spacing: 0; }
    .ids, .meta {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 5px 10px;
      font-weight: 650;
      font-size: 12px;
      white-space: nowrap;
      border: 1px solid var(--line);
      background: var(--soft);
    }
    .success { color: var(--ok); background: #e9f7ef; border-color: #bfe7cd; }
    .misleading_failure { color: var(--bad); background: #fff0ed; border-color: #ffd0c9; }
    .completion_failure, .irrelevant_action_failure, .invalid_action_failure { color: var(--warn); background: #fff8df; border-color: #f2d888; }
    .task-body { padding: 16px 18px; }
    .submission {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .kv {
      background: #fafbfc;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      min-width: 0;
    }
    .kv label {
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 4px;
    }
    .kv div { overflow-wrap: anywhere; font-size: 13px; }
    .steps {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }
    .step {
      display: grid;
      grid-template-columns: minmax(320px, 52%) minmax(260px, 1fr);
      gap: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 12px;
    }
    .shot {
      display: block;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f1f3f6;
    }
    .step-info h3 { margin: 2px 0 8px; font-size: 15px; }
    pre {
      background: #f6f8fa;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 12px;
      margin: 8px 0 0;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    @media (max-width: 900px) {
      .task-head { grid-template-columns: 1fr; }
      .step { grid-template-columns: 1fr; }
      header, .wrap { padding-left: 14px; padding-right: 14px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Business 47 LLM Dry Run Trace Review</h1>
    <div class="sub">Source: {{ runs_path }} · This page is for human audit and includes evaluator-hidden outcomes.</div>
  </header>

  <main class="wrap">
    <section class="summary">
      <div class="metric"><span>Total runs</span><strong>{{ rows|length }}</strong></div>
      {% for outcome, count in outcome_counts.items() %}
      <div class="metric"><span>{{ outcome }}</span><strong>{{ count }}</strong></div>
      {% endfor %}
    </section>

    {% for row in rows %}
    <article class="task" id="{{ row.slug }}">
      <div class="task-head">
        <div>
          <h2>{{ row.slug }} · {{ row.template }}</h2>
          <div class="ids">{{ row.task_id }}</div>
          <div class="ids">{{ row.case_id }}</div>
          <div class="meta">{{ row.misleader_type }} · {{ row.reasoning_operation }}</div>
        </div>
        <div>
          <span class="badge {{ row.outcome }}">{{ row.outcome }}</span>
        </div>
      </div>
      <div class="task-body">
        <section class="submission">
          <div class="kv"><label>Error Attribution</label><div>{{ row.error_attribution }}</div></div>
          <div class="kv"><label>Submitted Action</label><div>{{ row.submission.selected_action_label if row.submission else "N/A" }}</div></div>
          <div class="kv"><label>Selected Action ID</label><div>{{ row.submission.selected_action_id if row.submission else "N/A" }}</div></div>
          <div class="kv"><label>Navigation Trace</label><div>{{ row.submission.navigation_trace if row.submission else "N/A" }}</div></div>
        </section>

        <section class="steps">
          {% for step in row.trace %}
          <div class="step">
            <a href="/shot?path={{ step.screenshot }}" target="_blank" title="Open full-size screenshot">
              <img class="shot" src="/shot?path={{ step.screenshot }}" alt="{{ row.slug }} step {{ step.step }} screenshot">
            </a>
            <div class="step-info">
              <h3>Step {{ step.step }}</h3>
              <div class="kv"><label>URL</label><div>{{ step.url }}</div></div>
              <div class="kv"><label>Agent Action</label><div>{{ pretty_action(step.action or {}) }}</div></div>
              <div class="kv"><label>Leak Terms Seen</label><div>{{ step.leak_terms_seen or [] }}</div></div>
              <pre>{{ step.action | tojson(indent=2) }}</pre>
            </div>
          </div>
          {% endfor %}
        </section>
      </div>
    </article>
    {% endfor %}
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8017)
    args = parser.parse_args()
    app = create_app(args.runs)
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
