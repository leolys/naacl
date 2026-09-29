#!/usr/bin/env python3
"""Analyze dashboard/form revisits in Business web-agent run traces."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "business47_llm_full_runs.jsonl"
DEFAULT_RERUN = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "business47_timeout_rerun_runs.jsonl"
DEFAULT_OUT = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "business47_navigation_revisit_metrics.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "business47_navigation_revisit_summary.md"


def load_latest_rows(paths: list[Path]) -> list[dict[str, Any]]:
    by_slug: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            by_slug[row["slug"]] = row
    return [by_slug[slug] for slug in sorted(by_slug)]


def page_kind(url: str) -> str:
    if url.endswith("/dashboard"):
        return "dashboard"
    if url.endswith("/form"):
        return "form"
    if url.endswith("/confirmation"):
        return "confirmation"
    if "/task/" in url:
        return "task_home"
    if re_match_local_portal(url):
        return "portal"
    if url.startswith("chrome-error://"):
        return "browser_error"
    return "other"


def re_match_local_portal(url: str) -> bool:
    return any(url.endswith(f":{port}/") or url.endswith(f":{port}") for port in ("8016", "8026", "8033", "8037", "8038"))


def action_kind(step: dict[str, Any]) -> str:
    action = step.get("action") or {}
    kind = action.get("action") or ""
    text = action.get("text") or ""
    option = action.get("option_text") or ""
    select_name = action.get("select_name") or ""
    if kind == "click_link" and text == "Back to Dashboard":
        return "back_to_dashboard"
    if kind == "click_link" and text == "Open Form":
        return "open_form"
    if kind == "click_link" and text == "Open Dashboard":
        return "open_dashboard"
    if kind == "click_button" and "Submit" in text:
        return "submit"
    if kind == "select_option" and select_name == "primary_action":
        return "select_primary_action"
    if kind == "select_option":
        return "select_context_field"
    if kind == "finish":
        return "finish"
    return kind or "none"


def analyze_row(row: dict[str, Any]) -> dict[str, Any]:
    trace = row.get("trace", [])
    kinds = [page_kind(step.get("url", "")) for step in trace]
    actions = [action_kind(step) for step in trace]

    dashboard_visits = sum(1 for kind in kinds if kind == "dashboard")
    form_visits = sum(1 for kind in kinds if kind == "form")
    back_to_dashboard_actions = sum(1 for action in actions if action == "back_to_dashboard")
    open_form_actions = sum(1 for action in actions if action == "open_form")
    open_dashboard_actions = sum(1 for action in actions if action == "open_dashboard")
    submit_actions = sum(1 for action in actions if action == "submit")
    primary_action_step = next((idx for idx, action in enumerate(actions) if action == "select_primary_action"), None)
    submit_step = next((idx for idx, action in enumerate(actions) if action == "submit"), None)

    form_to_dashboard_revisits = 0
    dashboard_to_form_returns = 0
    alternating_segments: list[dict[str, Any]] = []
    for idx in range(len(kinds) - 1):
        if kinds[idx] == "form" and kinds[idx + 1] == "dashboard":
            form_to_dashboard_revisits += 1
        if kinds[idx] == "dashboard" and kinds[idx + 1] == "form":
            dashboard_to_form_returns += 1
    for idx in range(len(kinds) - 3):
        if kinds[idx] == kinds[idx + 2] and kinds[idx + 1] == kinds[idx + 3] and kinds[idx] != kinds[idx + 1]:
            alternating_segments.append(
                {
                    "start_step": idx,
                    "pattern": [kinds[idx], kinds[idx + 1], kinds[idx + 2], kinds[idx + 3]],
                }
            )

    dashboard_revisits_after_form = max(0, dashboard_visits - 1)
    pre_submit_dashboard_revisits = 0
    if submit_step is not None:
        seen_form = False
        for idx, kind in enumerate(kinds[:submit_step]):
            if kind == "form":
                seen_form = True
            elif kind == "dashboard" and seen_form:
                pre_submit_dashboard_revisits += 1

    selected_primary_then_revisited_dashboard = False
    if primary_action_step is not None:
        selected_primary_then_revisited_dashboard = any(kind == "dashboard" for kind in kinds[primary_action_step + 1 :])

    loop_severity = "none"
    if form_to_dashboard_revisits >= 2 or len(alternating_segments) >= 1:
        loop_severity = "repeated_loop"
    elif form_to_dashboard_revisits == 1 or selected_primary_then_revisited_dashboard:
        loop_severity = "single_revisit"

    return {
        "slug": row.get("slug"),
        "task_id": row.get("task_id"),
        "case_id": row.get("case_id"),
        "template": row.get("template"),
        "misleader_type": row.get("misleader_type"),
        "reasoning_operation": row.get("reasoning_operation"),
        "outcome": row.get("outcome"),
        "error_attribution": row.get("error_attribution"),
        "trace_steps": len(trace),
        "dashboard_visits": dashboard_visits,
        "form_visits": form_visits,
        "dashboard_revisits_after_form": dashboard_revisits_after_form,
        "form_to_dashboard_revisits": form_to_dashboard_revisits,
        "dashboard_to_form_returns": dashboard_to_form_returns,
        "pre_submit_dashboard_revisits": pre_submit_dashboard_revisits,
        "back_to_dashboard_actions": back_to_dashboard_actions,
        "open_dashboard_actions": open_dashboard_actions,
        "open_form_actions": open_form_actions,
        "submit_actions": submit_actions,
        "primary_action_step": primary_action_step,
        "submit_step": submit_step,
        "selected_primary_then_revisited_dashboard": selected_primary_then_revisited_dashboard,
        "alternating_segments": alternating_segments,
        "loop_severity": loop_severity,
        "page_sequence": kinds,
        "action_sequence": actions,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(path: Path, rows: list[dict[str, Any]], source_paths: list[Path], report_title: str) -> None:
    severity = Counter(row["loop_severity"] for row in rows)
    outcome_by_severity: dict[str, Counter[str]] = defaultdict(Counter)
    template_by_severity: dict[str, Counter[str]] = defaultdict(Counter)
    misleader_by_severity: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        outcome_by_severity[row["loop_severity"]][row["outcome"]] += 1
        template_by_severity[row["loop_severity"]][row["template"]] += 1
        misleader_by_severity[row["loop_severity"]][row["misleader_type"]] += 1

    revisit_rows = [row for row in rows if row["loop_severity"] != "none"]
    lines = [
        f"# {report_title}",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Source runs: {', '.join(str(path) for path in source_paths if path.exists())}",
        f"- Total tasks: {len(rows)}",
        f"- Loop severity distribution: {dict(severity)}",
        "",
        "## Interpretation",
        "",
        "- `form_to_dashboard_revisits`: number of times the agent returned from the action form to the dashboard.",
        "- `pre_submit_dashboard_revisits`: dashboard revisits after first seeing the form and before submit.",
        "- `single_revisit`: one form-to-dashboard revisit or revisiting the dashboard after selecting a primary action.",
        "- `repeated_loop`: repeated form/dashboard alternation.",
        "",
        "## Revisit Tasks",
        "",
        "| Task | Severity | Outcome | Form→Dashboard | Pre-Submit Revisit | Steps | Error |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in revisit_rows:
        lines.append(
            "| {slug} | {loop_severity} | {outcome} | {form_to_dashboard_revisits} | "
            "{pre_submit_dashboard_revisits} | {trace_steps} | {error_attribution} |".format(**row)
        )

    lines.extend(["", "## Outcomes By Severity", "", "| Severity | Outcomes |", "|---|---|"])
    for key, counter in sorted(outcome_by_severity.items()):
        lines.append(f"| {key} | {dict(counter)} |")

    lines.extend(["", "## Templates By Severity", "", "| Severity | Templates |", "|---|---|"])
    for key, counter in sorted(template_by_severity.items()):
        lines.append(f"| {key} | {dict(counter)} |")

    lines.extend(["", "## Misleader Types By Severity", "", "| Severity | Misleader Types |", "|---|---|"])
    for key, counter in sorted(misleader_by_severity.items()):
        lines.append(f"| {key} | {dict(counter)} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument(
        "--rerun",
        type=Path,
        default=DEFAULT_RERUN,
        help="Optional rerun file whose rows override same-slug rows from --runs.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report-title", default="Business 47 Navigation Revisit Metrics")
    args = parser.parse_args()

    source_paths = [args.runs]
    if args.rerun:
        source_paths.append(args.rerun)
    rows = [analyze_row(row) for row in load_latest_rows(source_paths)]
    write_jsonl(args.out, rows)
    write_summary(args.summary_out, rows, source_paths, args.report_title)
    print(f"Wrote metrics: {args.out}")
    print(f"Wrote summary: {args.summary_out}")
    print(f"Tasks analyzed: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
