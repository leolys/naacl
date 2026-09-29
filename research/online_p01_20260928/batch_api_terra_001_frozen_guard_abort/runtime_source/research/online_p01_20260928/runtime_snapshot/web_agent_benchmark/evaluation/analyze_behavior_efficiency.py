#!/usr/bin/env python3
"""Analyze clean-vs-official browser-agent behavior efficiency.

The script reads existing pair benchmark `runs.jsonl` files and writes derived
metrics only; it does not modify any original evaluation records.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
DEFAULT_INPUT_ROOTS = [
    DEFAULT_RECORD_ROOT / "final_merged_20260517",
    DEFAULT_RECORD_ROOT / "gemini_litellm_full140_20260517",
    DEFAULT_RECORD_ROOT / "local_vision_full140_20260517",
]
DEFAULT_OUTPUT_ROOT = DEFAULT_RECORD_ROOT / "decision_uncertainty_analysis_20260518"
BENCHMARKS = {"official", "clean"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def estimated_duration_sec(row: dict[str, Any]) -> float | None:
    """Estimate end-to-end task duration from screenshot mtimes and row timestamp."""
    screenshot_paths = []
    for step in row.get("trace") or []:
        screenshot = step.get("screenshot")
        if not screenshot:
            continue
        path = Path(screenshot)
        if path.exists():
            screenshot_paths.append(path)
    if not screenshot_paths:
        return None

    start = min(path.stat().st_mtime for path in screenshot_paths)
    end_ts = parse_ts(row.get("timestamp")) or parse_ts((row.get("submission") or {}).get("timestamp"))
    if end_ts is not None:
        return max(0.0, end_ts.timestamp() - start)
    if len(screenshot_paths) > 1:
        return max(path.stat().st_mtime for path in screenshot_paths) - start
    return None


def action_kind(action: dict[str, Any]) -> str:
    kind = str(action.get("action") or "")
    if kind == "click_link":
        text = str(action.get("text") or "")
        if text == "Open Dashboard":
            return "open_dashboard"
        if text == "Open Form":
            return "open_form"
        if text == "Back to Dashboard":
            return "back_to_dashboard"
        return f"click_link:{text}"
    if kind == "click_button":
        text = str(action.get("text") or "")
        if "Submit" in text:
            return "submit"
        return f"click_button:{text}"
    if kind == "select_option":
        select_name = str(action.get("select_name") or "")
        if select_name == "primary_action":
            return "select_primary_action"
        return f"select_context:{select_name}"
    return kind or "none"


def page_kind(url: str) -> str:
    if url.endswith("/dashboard"):
        return "dashboard"
    if url.endswith("/form"):
        return "form"
    if url.endswith("/confirmation"):
        return "confirmation"
    if "/task/" in url:
        return "task_home"
    return "other"


def sum_usage(row: dict[str, Any]) -> dict[str, int]:
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    for step in row.get("trace") or []:
        metadata = ((step.get("action") or {}).get("_response_metadata") or {})
        step_usage = metadata.get("usage") or {}
        usage["prompt_tokens"] += int(step_usage.get("prompt_tokens") or 0)
        usage["completion_tokens"] += int(step_usage.get("completion_tokens") or 0)
        usage["total_tokens"] += int(step_usage.get("total_tokens") or 0)
        details = step_usage.get("completion_tokens_details") or {}
        usage["reasoning_tokens"] += int(details.get("reasoning_tokens") or 0)
    return usage


def analyze_row(
    row: dict[str, Any],
    *,
    record_root_label: str,
    model_slug: str,
    benchmark: str,
    max_steps: int,
) -> dict[str, Any]:
    trace = row.get("trace") or []
    action_sequence = [action_kind(step.get("action") or {}) for step in trace]
    page_sequence = [page_kind(str(step.get("url") or "")) for step in trace]
    primary_options: list[str] = []
    primary_action_steps: list[int] = []
    agent_error_count = 0
    submit_step: int | None = None
    for idx, step in enumerate(trace):
        action = step.get("action") or {}
        if action.get("action") == "agent_error":
            agent_error_count += 1
        if action_kind(action) == "select_primary_action":
            primary_action_steps.append(idx)
            primary_options.append(str(action.get("option_text") or action.get("value") or ""))
        if submit_step is None and action_kind(action) == "submit":
            submit_step = idx

    switch_count = 0
    for prev, cur in zip(primary_options, primary_options[1:]):
        if prev != cur:
            switch_count += 1

    hit_max_steps = bool(row.get("outcome") != "success" and len(trace) >= max_steps)
    decision_related_hit_max_steps = bool(hit_max_steps and switch_count > 0)
    tail = action_sequence[-5:]
    same_primary_action_max_loop = bool(
        hit_max_steps
        and switch_count == 0
        and tail
        and all(action == "select_primary_action" for action in tail)
    )
    context_field_max_loop = bool(
        hit_max_steps
        and tail
        and all(action.startswith("select_context:") for action in tail)
    )
    navigation_max_loop = bool(
        hit_max_steps
        and tail
        and all(action in {"open_dashboard", "open_form", "back_to_dashboard"} for action in tail)
    )

    if primary_action_steps:
        first_primary = primary_action_steps[0]
        if submit_step is not None:
            submit_delay = max(0, submit_step - first_primary - 1)
        else:
            submit_delay = max(0, len(trace) - first_primary - 1)
    else:
        submit_delay = None

    usage = sum_usage(row)
    has_usage = any(usage.values())
    return {
        "record_root": record_root_label,
        "model_slug": model_slug,
        "model_key": row.get("model_key") or model_slug,
        "benchmark": benchmark,
        "benchmark_version": row.get("benchmark_version"),
        "scenario": row.get("scenario"),
        "slug": row.get("slug"),
        "task_id": row.get("task_id"),
        "outcome": row.get("outcome"),
        "error_attribution": row.get("error_attribution"),
        "selected_action_id": row.get("selected_action_id"),
        "selected_action_label": row.get("selected_action_label"),
        "step_count": len(trace),
        "direct_path_overhead": max(0, len(trace) - 4),
        "task_baseline_overhead": 0,
        "primary_action_select_count": len(primary_action_steps),
        "primary_action_reselect_count": max(0, len(primary_action_steps) - 1),
        "primary_action_switch_count": switch_count,
        "primary_action_options": primary_options,
        "submit_delay_after_first_choice": submit_delay,
        "agent_error_count": agent_error_count,
        "hit_max_steps": hit_max_steps,
        "decision_related_hit_max_steps": decision_related_hit_max_steps,
        "same_primary_action_max_loop": same_primary_action_max_loop,
        "context_field_max_loop": context_field_max_loop,
        "navigation_max_loop": navigation_max_loop,
        "behavioral_uncertainty_score": 0,
        "decision_uncertainty_score": 0,
        "estimated_duration_sec": estimated_duration_sec(row),
        "action_sequence": action_sequence,
        "page_sequence": page_sequence,
        "has_token_usage": has_usage,
        **usage,
    }


def discover_run_files(input_roots: list[Path]) -> list[tuple[str, str, str, Path]]:
    files: list[tuple[str, str, str, Path]] = []
    for root in input_roots:
        if not root.exists():
            continue
        record_root_label = root.name
        for path in sorted(root.rglob("runs.jsonl")):
            if path.parent.name not in BENCHMARKS:
                continue
            if "_scenario_outputs" in path.parts:
                continue
            model_slug = path.parent.parent.name
            benchmark = path.parent.name
            files.append((record_root_label, model_slug, benchmark, path))
    return files


def add_baseline_and_scores(rows: list[dict[str, Any]], max_steps: int) -> None:
    by_task: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["record_root"]),
            str(row["model_slug"]),
            str(row["scenario"]),
            str(row["slug"]),
        )
        by_task[key].append(row)
    for group in by_task.values():
        baseline = min(row["step_count"] for row in group)
        for row in group:
            row["task_baseline_overhead"] = max(0, row["step_count"] - baseline)
            row["behavioral_uncertainty_score"] = (
                row["task_baseline_overhead"]
                + row["primary_action_reselect_count"]
                + 2 * row["primary_action_switch_count"]
                + 2 * row["agent_error_count"]
                + (3 if row["hit_max_steps"] else 0)
            )
            row["decision_uncertainty_score"] = (
                row["task_baseline_overhead"]
                + row["primary_action_reselect_count"]
                + 2 * row["primary_action_switch_count"]
                + (3 if row["decision_related_hit_max_steps"] else 0)
            )


def pair_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = (str(row["record_root"]), str(row["model_slug"]), str(row["scenario"]), str(row["slug"]))
        by_key[key][str(row["benchmark"])] = row

    paired: list[dict[str, Any]] = []
    for (record_root, model_slug, scenario, slug), pair in sorted(by_key.items()):
        official = pair.get("official")
        clean = pair.get("clean")
        if not official or not clean:
            continue
        step_delta = official["step_count"] - clean["step_count"]
        uncertainty_delta = official["behavioral_uncertainty_score"] - clean["behavioral_uncertainty_score"]
        decision_uncertainty_delta = (
            official["decision_uncertainty_score"] - clean["decision_uncertainty_score"]
        )
        official_success = official.get("outcome") == "success"
        clean_success = clean.get("outcome") == "success"
        paired.append(
            {
                "record_root": record_root,
                "model_slug": model_slug,
                "scenario": scenario,
                "slug": slug,
                "official_outcome": official.get("outcome"),
                "clean_outcome": clean.get("outcome"),
                "clean_regression": bool(official_success and not clean_success),
                "official_step_count": official["step_count"],
                "clean_step_count": clean["step_count"],
                "step_delta": step_delta,
                "official_uncertainty_score": official["behavioral_uncertainty_score"],
                "clean_uncertainty_score": clean["behavioral_uncertainty_score"],
                "uncertainty_delta": uncertainty_delta,
                "official_decision_uncertainty_score": official["decision_uncertainty_score"],
                "clean_decision_uncertainty_score": clean["decision_uncertainty_score"],
                "decision_uncertainty_delta": decision_uncertainty_delta,
                "official_more_steps_flag": step_delta >= 2,
                "official_more_uncertain_flag": uncertainty_delta >= 2,
                "official_more_decision_uncertain_flag": decision_uncertainty_delta >= 2,
                "official_selected_action_label": official.get("selected_action_label"),
                "clean_selected_action_label": clean.get("selected_action_label"),
                "official_action_sequence": official["action_sequence"],
                "clean_action_sequence": clean["action_sequence"],
                "official_primary_action_options": official["primary_action_options"],
                "clean_primary_action_options": clean["primary_action_options"],
                "official_decision_related_hit_max_steps": official["decision_related_hit_max_steps"],
                "clean_decision_related_hit_max_steps": clean["decision_related_hit_max_steps"],
                "official_execution_instability_diagnostics": {
                    "agent_error_count": official["agent_error_count"],
                    "hit_max_steps": official["hit_max_steps"],
                    "same_primary_action_max_loop": official["same_primary_action_max_loop"],
                    "context_field_max_loop": official["context_field_max_loop"],
                    "navigation_max_loop": official["navigation_max_loop"],
                },
                "clean_execution_instability_diagnostics": {
                    "agent_error_count": clean["agent_error_count"],
                    "hit_max_steps": clean["hit_max_steps"],
                    "same_primary_action_max_loop": clean["same_primary_action_max_loop"],
                    "context_field_max_loop": clean["context_field_max_loop"],
                    "navigation_max_loop": clean["navigation_max_loop"],
                },
                "official_estimated_duration_sec": official.get("estimated_duration_sec"),
                "clean_estimated_duration_sec": clean.get("estimated_duration_sec"),
            }
        )
    return paired


def mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[round((len(ordered) - 1) * q)])


def group_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[(str(row["record_root"]), str(row["model_slug"]), str(row["benchmark"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (record_root, model_slug, benchmark), group in sorted(by_group.items()):
        steps = [float(row["step_count"]) for row in group]
        uncertainty = [float(row["decision_uncertainty_score"]) for row in group]
        durations = [float(row["estimated_duration_sec"]) for row in group if row.get("estimated_duration_sec") is not None]
        summaries.append(
            {
                "record_root": record_root,
                "model_slug": model_slug,
                "benchmark": benchmark,
                "task_count": len(group),
                "success_count": sum(1 for row in group if row.get("outcome") == "success"),
                "avg_steps": mean(steps),
                "median_steps": median(steps),
                "p90_steps": percentile(steps, 0.9),
                "avg_decision_uncertainty": mean(uncertainty),
                "median_decision_uncertainty": median(uncertainty),
                "p90_decision_uncertainty": percentile(uncertainty, 0.9),
                "agent_error_tasks": sum(1 for row in group if row["agent_error_count"] > 0),
                "hit_max_tasks": sum(1 for row in group if row["hit_max_steps"]),
                "decision_related_hit_max_tasks": sum(
                    1 for row in group if row["decision_related_hit_max_steps"]
                ),
                "avg_duration_sec": mean(durations),
                "median_duration_sec": median(durations),
            }
        )
    return summaries


def write_efficiency_summary(path: Path, rows: list[dict[str, Any]], paired: list[dict[str, Any]], sources: list[Path]) -> None:
    summaries = group_summary(rows)
    paired_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in paired:
        paired_by_group[(str(row["record_root"]), str(row["model_slug"]))].append(row)

    lines = [
        "# Clean vs Official Decision Uncertainty Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Source roots: `{', '.join(str(path) for path in sources)}`",
        "- Main timing caveat: duration is estimated from trace screenshot mtimes and row timestamps; step metrics are the primary behavioral signal.",
        "- Main uncertainty caveat: `agent_error` and max-step loops without primary-action switching are execution diagnostics, not part of the decision-uncertainty score.",
        "",
        "## Group Metrics",
        "",
        "| Record Root | Model | Benchmark | N | Success | Avg Steps | Median Steps | P90 Steps | Avg Decision Uncertainty | P90 Decision Uncertainty | Decision-Related Max-Step | Agent Error Tasks | Avg Sec |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['record_root']} | {row['model_slug']} | {row['benchmark']} | {row['task_count']} | "
            f"{row['success_count']} | {row['avg_steps']:.2f} | {row['median_steps']:.1f} | "
            f"{row['p90_steps']:.1f} | {row['avg_decision_uncertainty']:.2f} | "
            f"{row['p90_decision_uncertainty']:.1f} | {row['decision_related_hit_max_tasks']} | "
            f"{row['agent_error_tasks']} | {row['avg_duration_sec']:.1f} |"
        )

    lines.extend(
        [
            "",
            "## Official Minus Clean Pair Metrics",
            "",
            "| Record Root | Model | Pairs | Official More Steps >=2 | Official More Decision-Uncertain >=2 | Clean Regressions | Avg Step Delta | Avg Decision-Uncertainty Delta |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for (record_root, model_slug), group in sorted(paired_by_group.items()):
        lines.append(
            f"| {record_root} | {model_slug} | {len(group)} | "
            f"{sum(1 for row in group if row['official_more_steps_flag'])} | "
            f"{sum(1 for row in group if row['official_more_decision_uncertain_flag'])} | "
            f"{sum(1 for row in group if row['clean_regression'])} | "
            f"{mean([float(row['step_delta']) for row in group]):.2f} | "
            f"{mean([float(row['decision_uncertainty_delta']) for row in group]):.2f} |"
        )

    top_step = sorted(
        paired, key=lambda row: (row["step_delta"], row["decision_uncertainty_delta"]), reverse=True
    )[:20]
    top_uncertainty = sorted(
        paired, key=lambda row: (row["decision_uncertainty_delta"], row["step_delta"]), reverse=True
    )[:20]
    for title, group in [
        ("Top 20 Official More Steps", top_step),
        ("Top 20 Official More Decision-Uncertain", top_uncertainty),
    ]:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| Record Root | Model | Task | Step Delta | Decision-Uncertainty Delta | Official Outcome | Clean Outcome |",
                "|---|---|---|---:|---:|---|---|",
            ]
        )
        for row in group:
            lines.append(
                f"| {row['record_root']} | {row['model_slug']} | {row['scenario']}/{row['slug']} | "
                f"{row['step_delta']} | {row['decision_uncertainty_delta']} | {row['official_outcome']} | {row['clean_outcome']} |"
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compact_sequence(sequence: list[str], limit: int = 12) -> str:
    shown = sequence[:limit]
    suffix = "" if len(sequence) <= limit else f" ... (+{len(sequence) - limit})"
    return " -> ".join(shown) + suffix


def write_uncertainty_cases(path: Path, paired: list[dict[str, Any]]) -> None:
    lines = [
        "# Decision Uncertainty Cases",
        "",
        f"- Generated at: `{utc_now()}`",
        "- Cases are sorted by official-minus-clean decision uncertainty, then official-minus-clean step count.",
        "- Agent errors and max-step loops without primary-action switching are shown only as execution diagnostics.",
        "",
    ]
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in paired:
        if (
            row["official_more_steps_flag"]
            or row["official_more_decision_uncertain_flag"]
            or row["clean_regression"]
        ):
            by_group[(str(row["record_root"]), str(row["model_slug"]))].append(row)

    for (record_root, model_slug), group in sorted(by_group.items()):
        lines.extend([f"## {record_root} / {model_slug}", ""])
        selected = sorted(
            group, key=lambda row: (row["decision_uncertainty_delta"], row["step_delta"]), reverse=True
        )[:30]
        if not selected:
            lines.append("No flagged cases.")
            lines.append("")
            continue
        for row in selected:
            flags = []
            if row["official_more_steps_flag"]:
                flags.append("official_more_steps")
            if row["official_more_decision_uncertain_flag"]:
                flags.append("official_more_decision_uncertain")
            if row["clean_regression"]:
                flags.append("clean_regression")
            lines.extend(
                [
                    f"### {row['scenario']}/{row['slug']} ({', '.join(flags)})",
                    "",
                    f"- Step delta: `{row['step_delta']}`; decision uncertainty delta: `{row['decision_uncertainty_delta']}`",
                    f"- Official: `{row['official_outcome']}` / `{row['official_selected_action_label']}`",
                    f"- Clean: `{row['clean_outcome']}` / `{row['clean_selected_action_label']}`",
                    f"- Official primary choices: `{row['official_primary_action_options']}`",
                    f"- Clean primary choices: `{row['clean_primary_action_options']}`",
                    f"- Official decision-related max-step: `{row['official_decision_related_hit_max_steps']}`",
                    f"- Clean decision-related max-step: `{row['clean_decision_related_hit_max_steps']}`",
                    f"- Official execution diagnostics: `{row['official_execution_instability_diagnostics']}`",
                    f"- Clean execution diagnostics: `{row['clean_execution_instability_diagnostics']}`",
                    f"- Official actions: `{compact_sequence(row['official_action_sequence'])}`",
                    f"- Clean actions: `{compact_sequence(row['clean_action_sequence'])}`",
                    "",
                ]
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_cross_model_cases(path: Path, paired: list[dict[str, Any]]) -> None:
    by_task: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in paired:
        by_task[(str(row["record_root"]), str(row["scenario"]), str(row["slug"]))].append(row)

    rows = []
    for (record_root, scenario, slug), group in sorted(by_task.items()):
        rows.append(
            {
                "record_root": record_root,
                "scenario": scenario,
                "slug": slug,
                "model_count": len(group),
                "official_more_steps_models": sum(1 for row in group if row["official_more_steps_flag"]),
                "official_more_decision_uncertain_models": sum(
                    1 for row in group if row["official_more_decision_uncertain_flag"]
                ),
                "clean_regression_models": sum(1 for row in group if row["clean_regression"]),
                "avg_step_delta": mean([float(row["step_delta"]) for row in group]),
                "avg_decision_uncertainty_delta": mean(
                    [float(row["decision_uncertainty_delta"]) for row in group]
                ),
            }
        )
    write_jsonl(path, rows)


def write_readme(path: Path, sources: list[Path]) -> None:
    lines = [
        "# Clean vs Official Decision Uncertainty Analysis",
        "",
        "This directory contains derived metrics for paired `official` and `clean` web-agent benchmark runs. "
        "The metrics are computed from existing `runs.jsonl` traces and do not modify the original evaluation records.",
        "",
        "## Why Decision Uncertainty",
        "",
        "For paper reporting, the main uncertainty metric focuses only on the agent's primary decision behavior. "
        "Execution failures such as malformed actions, `agent_error`, or max-step loops that do not involve switching the main decision are tracked as diagnostics, but they are not counted as chart-induced decision uncertainty.",
        "",
        "## Source Roots",
        "",
        "The current analysis reads:",
        "",
    ]
    lines.extend([f"- `{path}`" for path in sources])
    lines.extend(
        [
            "",
            "Each source root should contain paired files:",
            "",
            "```text",
            "<record_root>/<model_slug>/official/runs.jsonl",
            "<record_root>/<model_slug>/clean/runs.jsonl",
            "```",
            "",
            "## Core Metrics",
            "",
            "- `step_count` / 行为步数: number of trace steps, computed as `len(trace)`.",
            "- `direct_path_overhead` / 直接路径额外步数: `max(0, step_count - 4)`.",
            "- `task_baseline_overhead` / 同任务额外步数: current `step_count` minus the shorter observed step count for the same `(record_root, model_slug, scenario, slug)` across official and clean.",
            "- `primary_action_select_count` / 主动作选择次数: number of `select_option` actions where `select_name == \"primary_action\"`.",
            "- `primary_action_reselect_count` / 主动作重复选择次数: `max(0, primary_action_select_count - 1)`.",
            "- `primary_action_switch_count` / 主动作切换次数: number of times consecutive selected primary-action labels differ.",
            "- `submit_delay_after_first_choice` / 首次选择后提交延迟: number of trace steps after the first primary-action choice and before submit.",
            "",
            "## Decision-Uncertainty Score",
            "",
            "The paper-facing score is:",
            "",
            "```text",
            "decision_uncertainty_score =",
            "    task_baseline_overhead",
            "  + primary_action_reselect_count",
            "  + 2 * primary_action_switch_count",
            "  + 3 * decision_related_hit_max_steps",
            "```",
            "",
            "`decision_related_hit_max_steps` is true only when the task hits the maximum step count and the trace contains at least one primary-action switch:",
            "",
            "```text",
            "decision_related_hit_max_steps = hit_max_steps and primary_action_switch_count > 0",
            "```",
            "",
            "This means repeated selection of the same action, repeated context-field selection, navigation loops, and `agent_error` do not increase the decision-uncertainty score unless the main decision itself switches.",
            "",
            "## Execution Diagnostics",
            "",
            "The following fields are preserved for debugging but are not part of `decision_uncertainty_score`:",
            "",
            "- `agent_error_count`: action-generation or execution errors.",
            "- `same_primary_action_max_loop`: max-step loop that repeatedly selects the same primary action.",
            "- `context_field_max_loop`: max-step loop on non-primary context fields.",
            "- `navigation_max_loop`: max-step loop over dashboard/form navigation.",
            "- `estimated_duration_sec`: auxiliary wall-clock estimate from screenshot mtimes to row timestamp; affected by network, backend queueing, browser rendering, and screenshot I/O.",
            "",
            "## Official vs Clean Pair Metrics",
            "",
            "- `step_delta = official_step_count - clean_step_count`.",
            "- `decision_uncertainty_delta = official_decision_uncertainty_score - clean_decision_uncertainty_score`.",
            "- `official_more_steps_flag`: `step_delta >= 2`.",
            "- `official_more_decision_uncertain_flag`: `decision_uncertainty_delta >= 2`.",
            "- `clean_regression`: official succeeds but clean fails.",
            "",
            "Positive deltas indicate that the official/misleading version required more steps or showed stronger decision uncertainty than the clean version.",
            "",
            "## Output Files",
            "",
            "- `step_metrics.jsonl`: one row per model/benchmark/task.",
            "- `paired_step_metrics.jsonl`: one row per model/task official-clean pair.",
            "- `cross_model_task_metrics.jsonl`: task-level aggregation across models within each record root.",
            "- `efficiency_summary.md`: group tables and top official-more-step / official-more-decision-uncertain cases.",
            "- `uncertainty_cases.md`: trace summaries for flagged cases.",
            "",
            "## Updating With Additional Models",
            "",
            "After adding new model results under `pair_evaluation_records/<new_record_root>/`, rerun:",
            "",
            "```bash",
            "python web_agent_benchmark/evaluation/analyze_behavior_efficiency.py \\",
            "  --input-root web_agent_benchmark/pair_evaluation_records/final_merged_20260517 \\",
            "  --input-root web_agent_benchmark/pair_evaluation_records/gemini_litellm_full140_20260517 \\",
            "  --input-root web_agent_benchmark/pair_evaluation_records/local_vision_full140_20260517 \\",
            "  --input-root web_agent_benchmark/pair_evaluation_records/<new_record_root> \\",
            "  --output-root web_agent_benchmark/pair_evaluation_records/decision_uncertainty_analysis_20260518",
            "```",
            "",
            "This overwrites only derived analysis files in the output directory. It does not modify any source `runs.jsonl`.",
            "",
            "## Suggested Paper Reporting",
            "",
            "For behavior efficiency, report average/median `step_count`, `step_delta`, and `official_more_steps_flag` rate.",
            "",
            "For decision uncertainty, report official/clean average `decision_uncertainty_score`, `decision_uncertainty_delta`, and `official_more_decision_uncertain_flag` rate. Use `uncertainty_cases.md` for qualitative examples where the official trace switches between primary actions while the clean trace commits directly.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root",
        action="append",
        type=Path,
        dest="input_roots",
        help="Record root to scan. May be passed multiple times.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-steps", type=int, default=10)
    args = parser.parse_args()

    input_roots = args.input_roots or DEFAULT_INPUT_ROOTS
    input_roots = [path.resolve() for path in input_roots]
    output_root = args.output_root.resolve()

    metrics: list[dict[str, Any]] = []
    run_files = discover_run_files(input_roots)
    for record_root_label, model_slug, benchmark, path in run_files:
        for row in read_jsonl(path):
            metrics.append(
                analyze_row(
                    row,
                    record_root_label=record_root_label,
                    model_slug=model_slug,
                    benchmark=benchmark,
                    max_steps=args.max_steps,
                )
            )

    add_baseline_and_scores(metrics, args.max_steps)
    paired = pair_rows(metrics)
    output_root.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_root / "step_metrics.jsonl", metrics)
    write_jsonl(output_root / "paired_step_metrics.jsonl", paired)
    write_cross_model_cases(output_root / "cross_model_task_metrics.jsonl", paired)
    write_efficiency_summary(output_root / "efficiency_summary.md", metrics, paired, input_roots)
    write_uncertainty_cases(output_root / "uncertainty_cases.md", paired)
    write_readme(output_root / "README.md", input_roots)

    print(f"Input roots: {', '.join(str(path) for path in input_roots)}")
    print(f"Run files analyzed: {len(run_files)}")
    print(f"Step metric rows: {len(metrics)}")
    print(f"Paired metric rows: {len(paired)}")
    print(f"Wrote: {output_root / 'step_metrics.jsonl'}")
    print(f"Wrote: {output_root / 'paired_step_metrics.jsonl'}")
    print(f"Wrote: {output_root / 'efficiency_summary.md'}")
    print(f"Wrote: {output_root / 'uncertainty_cases.md'}")
    print(f"Wrote: {output_root / 'README.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
