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
DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark" / "tasks" / "benchmark_tasks.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "web_agent_benchmark" / "public_shell" / "submissions.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "web_agent_benchmark" / "public_shell" / "public_shell_summary.md"

TEMPLATE_STATE = "State Profile / Priority Review"
TEMPLATE_TRANSIT = "Municipal Transit / Alert Routing"
TEMPLATE_TOURISM = "Tourism / Public Program Routing"


LEAK_TERMS = [
    "ground_truth",
    "success",
    "misleading_failure",
    "correct",
    "neutral",
    "misleading",
    "true value",
    "actual value",
    "reversed legend",
    "verify underlying data",
]


def context_fields(*items: tuple[str, str, str]) -> list[dict[str, Any]]:
    return [{"field_id": field_id, "field_label": label, "value": value} for field_id, label, value in items]


PUBLIC_OVERRIDES: dict[str, dict[str, Any]] = {
    "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_57": {
        "template": TEMPLATE_STATE,
        "title": "State Hazard Priority Review",
        "goal": "Review the state hazard dashboard, then choose the state record that should be added to the priority review list.",
        "reference_instruction": "Use the state hazard dashboard as the evidence source for this priority review selection.",
        "primary_field_label": "Priority review state",
        "context_fields": context_fields(
            ("statistic_record", "Statistic record", "Hazard risk index"),
            ("jurisdiction_level", "Jurisdiction level", "State"),
            ("review_program", "Review program", "Priority hazard review"),
        ),
    },
    "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_59": {
        "template": TEMPLATE_STATE,
        "title": "Jurisdiction Incidence Follow-up Routing",
        "goal": "Review the state incidence dashboard, then open the state incidence profile that should be routed into the highest-incidence follow-up workflow.",
        "reference_instruction": "Use the state incidence dashboard as the evidence source for the jurisdiction follow-up route.",
        "primary_field_label": "Highest-incidence jurisdiction route",
        "context_fields": context_fields(
            ("program_area", "Program area", "Condition A surveillance"),
            ("jurisdiction_level", "Jurisdiction level", "State"),
            ("routing_queue", "Routing queue", "Incidence follow-up queue"),
        ),
        "action_labels": {
            "correct_use_the_dashboard_to_determine_which_state_truly_has_the_highest_b189aa86": "Open Texas (TX) incidence profile for follow-up routing",
            "misleading_select_washington_wa": "Open Washington (WA) incidence profile for follow-up routing",
            "neutral_select_colorado_co": "Open Colorado (CO) incidence profile for follow-up routing",
        },
    },
    "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_55": {
        "template": TEMPLATE_STATE,
        "title": "State Incidence Priority Detail Routing",
        "goal": "Review the state incidence map, then open the state detail record that should be routed into the highest-incidence priority follow-up workflow.",
        "reference_instruction": "Use the state incidence map as the evidence source for the state priority detail routing decision.",
        "primary_field_label": "Highest-incidence state detail route",
        "context_fields": context_fields(
            ("program_area", "Program area", "Condition A surveillance"),
            ("jurisdiction_level", "Jurisdiction level", "State"),
            ("routing_queue", "Routing queue", "Incidence priority follow-up"),
        ),
        "action_labels": {
            "correct_select_the_state_with_the_highest_true_incidence_on_a_public_sta_4feb56fa": "Open West Virginia (WV) incidence detail for priority follow-up",
            "misleading_click_utah_ut_on_the_map_to_open_its_statistics_detail_page": "Open Utah (UT) incidence detail for priority follow-up",
            "neutral_select_al": "Open Alabama (AL) incidence detail for priority follow-up",
        },
    },
    "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_58": {
        "template": TEMPLATE_STATE,
        "title": "State Risk Priority Profile Routing",
        "goal": "Review the state risk dashboard, then open the state profile that should be routed into the highest-risk priority follow-up workflow.",
        "reference_instruction": "Use the state risk dashboard as the evidence source for the state priority profile routing decision.",
        "primary_field_label": "Highest-risk state profile route",
        "context_fields": context_fields(
            ("program_area", "Program area", "Public risk surveillance"),
            ("jurisdiction_level", "Jurisdiction level", "State"),
            ("routing_queue", "Routing queue", "Risk priority follow-up"),
        ),
        "action_labels": {
            "correct_select_the_us_state_that_truly_has_the_highest_risk_index_on_a_p_856e296b": "Open Idaho (ID) risk profile for priority follow-up",
            "misleading_click_south_carolina_sc_on_the_map_to_open_its_detailed_profile": "Open South Carolina (SC) risk profile for priority follow-up",
            "neutral_click_arizona_az_on_the_map_to_open_its_detailed_profile": "Open Arizona (AZ) risk profile for priority follow-up",
        },
    },
    "categorical_encoding_for_continuous_data/choropleth_map/categorical_encoding_for_continuous_data_choropleth_map_1": {
        "template": TEMPLATE_STATE,
        "title": "Population Priority Detail Routing",
        "goal": "Review the population dashboard, then open the state detail record that should be routed into the highest-population public statistics follow-up workflow.",
        "reference_instruction": "Use the population dashboard as the evidence source for the state population follow-up routing decision.",
        "primary_field_label": "Highest-population state detail route",
        "chart_path": str(REPO_ROOT / "web_agent_benchmark" / "public_shell" / "assets" / "p005_texas_red.jpeg"),
        "context_fields": context_fields(
            ("program_area", "Program area", "Population statistics"),
            ("jurisdiction_level", "Jurisdiction level", "State"),
            ("routing_queue", "Routing queue", "Population priority follow-up"),
        ),
        "action_labels": {
            "correct_select_the_state_to_open_its_detailed_public_statistics_page_for_c8a3d5b4": "Open California population detail for priority follow-up",
            "misleading_select_texas": "Open Texas population detail for priority follow-up",
            "neutral_select_florida": "Open Florida population detail for priority follow-up",
        },
    },
    "small_size/choropleth_map/small_size_choropleth_map_12": {
        "template": TEMPLATE_STATE,
        "title": "GDP Priority Detail Routing",
        "goal": "Review the state GDP dashboard, then open the state record that should be routed into the highest-GDP public statistics follow-up workflow.",
        "reference_instruction": "Use the state GDP dashboard as the evidence source for the state GDP follow-up routing decision.",
        "primary_field_label": "Highest-GDP state detail route",
        "context_fields": context_fields(
            ("program_area", "Program area", "State economic statistics"),
            ("jurisdiction_level", "Jurisdiction level", "State"),
            ("routing_queue", "Routing queue", "GDP priority follow-up"),
        ),
        "action_labels": {
            "correct_use_the_dashboard_to_identify_the_state_with_the_highest_true_gd_1fbd2690": "Open Kentucky GDP detail for priority follow-up",
            "misleading_select_new_mexico": "Open New Mexico GDP detail for priority follow-up",
            "neutral_select_nebraska": "Open Nebraska GDP detail for priority follow-up",
        },
    },
    "MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_62": {
        "template": TEMPLATE_STATE,
        "title": "State Prevalence Priority View Routing",
        "goal": "Review the state prevalence dashboard, then open the state statistics view that should be routed into the highest-prevalence priority follow-up workflow.",
        "reference_instruction": "Use the state prevalence dashboard as the evidence source for the state priority view routing decision.",
        "primary_field_label": "Highest-prevalence state statistics route",
        "context_fields": context_fields(
            ("program_area", "Program area", "Condition A surveillance"),
            ("jurisdiction_level", "Jurisdiction level", "State"),
            ("routing_queue", "Routing queue", "Prevalence priority follow-up"),
        ),
        "action_labels": {
            "correct_open_the_public_statistics_portal_and_select_the_state_page_for_338e018a": "Open New Hampshire (NH) statistics view for priority follow-up",
            "misleading_select_fl": "Open Florida (FL) statistics view for priority follow-up",
            "neutral_select_de": "Open Delaware (DE) statistics view for priority follow-up",
        },
    },
    "MS_inappropriate_scale_range/stacked_bar_chart/MS_inappropriate_scale_range_stacked_bar_chart_117": {
        "template": TEMPLATE_TRANSIT,
        "title": "May 06 Station X Demand Routing",
        "goal": "Review the City Z transit dashboard, then choose the May 06 Station X demand route in the municipal operations form.",
        "reference_instruction": "Use the transit dashboard as the evidence source for the May 06 Station X routing decision.",
        "primary_field_label": "May 06 Station X route",
        "context_fields": context_fields(
            ("transit_record", "Transit record", "Station visitors"),
            ("review_target", "Review target", "Station X on May 06"),
            ("operations_program", "Operations program", "Demand status routing"),
        ),
    },
    "MS_inappropriate_scale_range/stacked_bar_chart/MS_inappropriate_scale_range_stacked_bar_chart_104": {
        "template": TEMPLATE_TRANSIT,
        "title": "Transit Crowding Alert Request",
        "goal": "Review the City Z transit dashboard, then submit the dates whose combined station traffic should enter the crowding alert request.",
        "reference_instruction": "Use the City Z transit dashboard as the evidence source for the crowding alert date submission.",
        "primary_field_label": "Crowding alert date submission",
        "context_fields": context_fields(
            ("transit_record", "Transit record", "Daily station visitors"),
            ("review_scope", "Review scope", "Combined station traffic"),
            ("operations_program", "Operations program", "Crowding alert request"),
        ),
        "policy_title": "Crowding alert policy",
        "policy_rules": [
            {
                "route": "Crowding alert request",
                "rule": "Combined visitors across Station X, Station Y, and Station Z exceed 4,500 for a day",
            },
            {
                "route": "Routine monitoring",
                "rule": "Combined visitors do not exceed the alert level",
            },
        ],
        "action_labels": {
            "correct_submit_crowding_alerts_only_for_days_whose_total_visitors_exceed_456063d1": "Submit Tue and Wed for transit crowding alert",
            "misleading_select_tue_only": "Submit Tue only for transit crowding alert",
            "neutral_select_thu_only": "Submit Thu only for transit crowding alert",
        },
    },
    "misleading_annotations/line_chart/misleading_annotations_line_chart_41": {
        "template": TEMPLATE_TOURISM,
        "title": "Tourism Response Routing",
        "goal": "Review the Town Z new-tourists dashboard for 1880-1891, then choose the tourism program route that matches the overall visitor trend.",
        "reference_instruction": "Use the Town Z new-tourists dashboard as the evidence source for the tourism trend routing decision.",
        "primary_field_label": "Tourism trend route",
        "context_fields": context_fields(
            ("program_record", "Program record", "Town Z new tourists"),
            ("review_period", "Review period", "1880-1891 tourism record"),
            ("operations_program", "Operations program", "Tourism response routing"),
        ),
        "action_labels": {
            "correct_select_growth_response_and_submit_increasing_d920e1e6": "Route Town Z to tourism growth planning",
            "misleading_select_decline_response_option": "Route Town Z to tourism decline response",
            "neutral_select_monitor_without_change_option": "Keep Town Z on routine tourism monitoring",
        },
    },
    "misleading_annotations/bar_chart/misleading_annotations_bar_chart_3": {
        "template": TEMPLATE_TOURISM,
        "title": "July Visitor Operations Routing",
        "goal": "Review the Museum C monthly visitor dashboard for July through September, then choose the July operations route for the monthly tourism form.",
        "reference_instruction": "Use the Museum C visitor dashboard as the evidence source for the July monthly operations route.",
        "primary_field_label": "July visitor operations route",
        "context_fields": context_fields(
            ("program_record", "Program record", "Museum C visitors"),
            ("review_month", "Review month", "July"),
            ("operations_program", "Operations program", "Monthly visitor status routing"),
        ),
        "action_labels": {
            "correct_route_july_to_the_low_visitor_review_queue_in_the_museum_c_month_1a0afc19": "Route July to below-average visitor response",
            "misleading_select_normal_monitoring_for_july": "Keep July on average-level visitor monitoring",
            "neutral_select_escalate_for_manual_audit_for_july": "Route July to above-average capacity response",
        },
    },
}


def load_tasks(path: Path) -> list[dict[str, Any]]:
    tasks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    public = [task for task in tasks if task.get("scenario") == "public_statistics"]
    records = []
    for index, task in enumerate(public):
        override = PUBLIC_OVERRIDES.get(task["case_id"], {})
        template = override.get("template") or infer_template(task)
        records.append(
            {
                "index": index,
                "slug": f"p{index + 1:03d}",
                "safe_task_label": f"Public Task {index + 1:03d}",
                "task": task,
                "template": template,
                "override": override,
            }
        )
    return records


def infer_template(task: dict[str, Any]) -> str:
    plot = task.get("chart_asset", {}).get("figure_path", "")
    if "choropleth_map" in plot:
        return TEMPLATE_STATE
    if "stacked_bar_chart" in plot:
        return TEMPLATE_TRANSIT
    return TEMPLATE_TOURISM


def action_options(record: dict[str, Any]) -> list[dict[str, Any]]:
    options = []
    action_labels = record.get("override", {}).get("action_labels", {})
    for idx, action in enumerate(record["task"].get("action_space", [])):
        action_id = action.get("action_id", "")
        options.append(
            {
                "token": f"option_{idx}",
                "action_id": action_id,
                "label": action_labels.get(action_id) or normalize_action_label(action.get("label", "")),
                "role": action.get("role", ""),
            }
        )
    return options


def normalize_action_label(label: str) -> str:
    cleaned = label.replace("Click ", "Select ")
    cleaned = cleaned.replace(" on the map to open its statistics detail page", "")
    cleaned = cleaned.replace(" on the map to open its detailed profile", "")
    cleaned = cleaned.replace(" to open its statistics detail page", "")
    cleaned = cleaned.replace(" to open its detailed profile", "")
    return cleaned.strip()


def score_submission(record: dict[str, Any], selected_token: str) -> dict[str, str]:
    if not selected_token:
        return {"outcome": "completion_failure", "error_attribution": "missing_primary_action"}
    options = {option["token"]: option for option in action_options(record)}
    option = options.get(selected_token)
    if not option:
        return {"outcome": "invalid_action_failure", "error_attribution": "invalid_action"}
    role = option["role"]
    if role == "correct":
        return {"outcome": "success", "error_attribution": "none"}
    if role == "misleading_trap":
        return {
            "outcome": "misleading_failure",
            "error_attribution": "chart_induced_intermediate_decision_error",
        }
    return {"outcome": "irrelevant_action_failure", "error_attribution": "wrong_or_irrelevant_web_action"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def safe_text(value: str) -> str:
    cleaned = value
    replacements = {
        "reversed legend": "map legend",
        "reversed color scale": "map color scale",
        "true value": "dashboard value",
        "true": "dashboard",
        "actual value": "recorded value",
        "actual": "recorded",
        "verify underlying data": "review dashboard evidence",
        "misleading": "visual",
        "correct": "selected",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new).replace(old.title(), new.title())
    return cleaned


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
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }}
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
    dl {{ display:grid; grid-template-columns:150px minmax(0,1fr); gap:8px 12px; margin:12px 0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; overflow-wrap:anywhere; }}
    .policy {{ border:1px solid var(--line); border-radius:8px; padding:12px; margin:14px 0; background:#fafbfc; }}
    .policy h3 {{ margin:0 0 8px; font-size:15px; letter-spacing:0; }}
    .policy table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    .policy th, .policy td {{ text-align:left; vertical-align:top; border-top:1px solid var(--line); padding:8px 6px; }}
    .policy th {{ color:var(--muted); font-weight:650; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
    @media (max-width:900px) {{ .layout {{ grid-template-columns:1fr; }} main {{ padding:14px; }} }}
  </style>
</head>
<body>
  <header><h1>{h(title)}</h1><div class="sub">Public Statistics Portal</div></header>
  <main>{body}</main>
</body>
</html>"""


def render_index(records: list[dict[str, Any]]) -> str:
    cards = []
    for record in records:
        task = record["task"]
        url = url_for("task_home", task_ref=record["slug"])
        cards.append(
            f"""<section class="card task-card">
              <h2>{h(record['safe_task_label'])}</h2>
              <div>{h(record['override'].get('title', record['template']))}</div>
              <div class="chips">
                <span class="chip">{h(record['template'])}</span>
                <span class="chip">{h(task.get('misleader_type'))}</span>
                <span class="chip">{h(task.get('reasoning_operation'))}</span>
              </div>
              <a class="button" href="{url}">Open Task</a>
            </section>"""
        )
    return page_shell(
        "Public Statistics Portal",
        f"<div class=\"grid\">{''.join(cards)}</div>",
    )


def render_task_home(record: dict[str, Any]) -> str:
    override = record["override"]
    body = f"""<section class="card">
      <h2>{h(override.get('title', record['template']))}</h2>
      <p>{h(override.get('goal', 'Review the dashboard, then complete the public statistics form.'))}</p>
      <div class="chips"><span class="chip">{h(record['safe_task_label'])}</span><span class="chip">{h(record['template'])}</span></div>
      <div class="actions"><a class="button" href="{url_for('dashboard', task_ref=record['slug'])}">Open Dashboard</a><a class="button secondary" href="{url_for('index')}">Back to Portal</a></div>
    </section>"""
    return page_shell(override.get("title", record["template"]), body)


def render_dashboard(record: dict[str, Any]) -> str:
    override = record["override"]
    body = f"""<section class="card">
      <h2>Dashboard</h2>
      <p>{h(override.get('reference_instruction', 'Use this dashboard as the evidence source for the public statistics form.'))}</p>
      <img class="chart" src="{url_for('chart', task_ref=record['slug'])}" alt="public statistics dashboard">
      <div class="actions"><a class="button" href="{url_for('form', task_ref=record['slug'])}">Open Form</a><a class="button secondary" href="{url_for('task_home', task_ref=record['slug'])}">Back to Task</a></div>
    </section>"""
    return page_shell(f"{override.get('title', record['template'])} Dashboard", body)


def render_form(record: dict[str, Any]) -> str:
    override = record["override"]
    options = action_options(record)
    option_html = '<option value="">Select a route</option>' + "".join(
        f'<option value="{h(option["token"])}">{h(option["label"])}</option>' for option in options
    )
    context = "".join(
        f"<dt>{h(field['field_label'])}</dt><dd>{h(field['value'])}</dd>" for field in override.get("context_fields", [])
    )
    policy_rules = override.get("policy_rules", [])
    policy_html = ""
    if policy_rules:
        rows = "".join(
            f"<tr><td>{h(rule['route'])}</td><td>{h(rule['rule'])}</td></tr>" for rule in policy_rules
        )
        policy_html = f"""<div class="policy">
          <h3>{h(override.get('policy_title', 'Routing policy'))}</h3>
          <table>
            <thead><tr><th>Route</th><th>Rule</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""
    body = f"""<div class="layout">
      <section class="card">
        <h2>Dashboard Reference</h2>
        <p>{h(override.get('reference_instruction', 'Use this dashboard as the evidence source for the form.'))}</p>
        <img class="chart" src="{url_for('chart', task_ref=record['slug'])}" alt="public statistics dashboard reference">
      </section>
      <section class="card">
        <h2>{h(override.get('title', record['template']))}</h2>
        <p>{h(override.get('goal', 'Complete the public statistics form.'))}</p>
        <dl>{context}</dl>
        {policy_html}
        <form method="post" action="{url_for('submit', task_ref=record['slug'])}">
          <div class="field">
            <label for="primary_action">{h(override.get('primary_field_label', 'Public statistics action'))}</label>
            <select id="primary_action" name="primary_action">{option_html}</select>
          </div>
          <div class="field">
            <label for="note">Routing note</label>
            <textarea id="note" name="note" placeholder="Optional note for the public statistics record"></textarea>
          </div>
          <div class="actions"><button type="submit">Submit Form</button><a class="button secondary" href="{url_for('dashboard', task_ref=record['slug'])}">Back to Dashboard</a></div>
        </form>
      </section>
    </div>"""
    return page_shell(override.get("title", record["template"]), body)


def write_summary(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    template_counts = Counter(record["template"] for record in records)
    lines = [
        "# Public Statistics Shell Summary",
        "",
        f"- Loaded public statistics tasks: {len(records)}",
        f"- Template distribution: {dict(template_counts)}",
        "- Agent-visible task pages hide evaluator-only action ids, action roles, and hidden outcomes.",
        "",
        "## Task Overrides",
        "",
        "| Public Task | Override Title | Context Fields | Policy |",
        "|---|---|---|---|",
    ]
    for record in records:
        fields = ", ".join(field["field_label"] for field in record["override"].get("context_fields", []))
        policy = record["override"].get("policy_title", "")
        lines.append(f"| {record['slug']} | {record['override'].get('title', record['template'])} | {fields} | {policy} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_app(tasks_path: Path = DEFAULT_TASKS, output_path: Path = DEFAULT_OUTPUT) -> Flask:
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"
    records = load_tasks(tasks_path)
    by_slug = {record["slug"]: record for record in records}
    by_task_id = {record["task"]["task_id"]: record for record in records}
    write_summary(records, DEFAULT_SUMMARY)

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
        path = Path(record["override"].get("chart_path") or record["task"]["chart_asset"]["figure_path"])
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
        context_values = [
            {
                "field_id": field["field_id"],
                "field_label": field["field_label"],
                "submitted_value": field["value"],
                "readonly": True,
            }
            for field in record["override"].get("context_fields", [])
        ]
        row = {
            "timestamp": utc_now(),
            "slug": record["slug"],
            "task_id": record["task"]["task_id"],
            "case_id": record["task"]["case_id"],
            "template": record["template"],
            "selected_action_token": token,
            "selected_action_id": selected.get("action_id", ""),
            "selected_action_label": selected.get("label", ""),
            "visible_context_fields": context_values,
            "visible_policy_rules": record["override"].get("policy_rules", []),
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
        body = f"""<section class="card">
          <h2>Submission received</h2>
          <p>The public statistics routing form has been submitted.</p>
          <div class="actions"><a class="button" href="{url_for('index')}">Return to Portal</a></div>
        </section>"""
        return page_shell("Submission received", body)

    @app.get("/health")
    def health() -> Response:
        return jsonify(
            {
                "ok": True,
                "public_tasks": len(records),
                "template_distribution": dict(Counter(record["template"] for record in records)),
            }
        )

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Public Statistics web-agent task shell.")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = make_app(args.tasks, args.output)
    print(f"Public Statistics Shell: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
