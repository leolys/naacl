#!/usr/bin/env python3
"""Post-hoc analysis for Qwen3-VL no-submit timeouts.

This does not rewrite the original runs.  It separates stable repeated
selections from oscillating choices so timeout examples that keep changing
options remain visible for review and paper analysis.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.business_shell import business_shell_app as business_shell  # noqa: E402
from web_agent_benchmark.environment_energy_shell import environment_shell_app as environment_shell  # noqa: E402
from web_agent_benchmark.health_shell import health_shell_app as health_shell  # noqa: E402
from web_agent_benchmark.public_benchmark import public_benchmark_shell_app as public_shell  # noqa: E402


DEFAULT_RECORDS = [
    REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1" / "evaluation_records" / "qwen3_vl_8b_full140",
    REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1" / "evaluation_records" / "qwen3_vl_32b_full140",
]
DEFAULT_COMBINED_SUMMARY = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "official_benchmark_v1"
    / "evaluation_records"
    / "qwen3_vl_timeout_posthoc_summary.md"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_registry() -> dict[str, dict[str, tuple[dict[str, Any], Any, str]]]:
    public_records = public_shell.load_public39_records()
    business_records, _ = business_shell.build_registry(
        business_shell.load_business_tasks(business_shell.DEFAULT_TASKS)
    )
    environment_records = environment_shell.load_records(environment_shell.DEFAULT_TASKS)
    health_records = health_shell.load_records(health_shell.DEFAULT_TASKS)
    return {
        "public39": {record["slug"]: (record, public_shell, "record") for record in public_records},
        "business47": {record["slug"]: (record, business_shell, "task") for record in business_records},
        "environment35": {
            record["slug"]: (record, environment_shell, "record") for record in environment_records
        },
        "health19": {record["slug"]: (record, health_shell, "record") for record in health_records},
    }


def action_from_trace_step(step: Any) -> dict[str, Any]:
    if not isinstance(step, dict):
        return {}
    action = step.get("action")
    return action if isinstance(action, dict) else {}


def select_sequence(row: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for step in row.get("trace") or []:
        action = action_from_trace_step(step)
        if action.get("action") == "select_option":
            labels.append(str(action.get("option_text", "")))
    return labels


def last_n_actions(row: dict[str, Any], stable_window: int) -> list[dict[str, Any]]:
    actions = [action_from_trace_step(step) for step in row.get("trace") or []]
    return actions[-stable_window:]


def classify_timeout(row: dict[str, Any], stable_window: int) -> tuple[str, str | None]:
    sequence = select_sequence(row)
    if not sequence:
        return "no_select_timeout", None
    tail = last_n_actions(row, stable_window)
    if (
        len(tail) == stable_window
        and all(action.get("action") == "select_option" for action in tail)
        and len({str(action.get("option_text", "")) for action in tail}) == 1
    ):
        label = str(tail[-1].get("option_text", ""))
        if label:
            return "stable_choice_no_submit", label
    if len(set(sequence)) > 1:
        return "oscillating_choice_no_submit", None
    return "single_select_but_not_stable", None


def normalize_role(option: dict[str, Any]) -> str | None:
    role = str(option.get("review_role") or option.get("role") or "").strip()
    outcome = str(option.get("outcome") or "").strip()
    if role == "correct" or outcome == "success":
        return "correct"
    if role in {"misleading", "misleading_trap"} or outcome == "misleading_failure":
        return "misleading"
    if role in {"irrelevant", "neutral", "neutral_or_irrelevant"} or outcome == "irrelevant_action_failure":
        return "irrelevant"
    return role or None


def implied_outcome(role: str | None) -> str | None:
    return {
        "correct": "success",
        "misleading": "misleading_failure",
        "irrelevant": "irrelevant_action_failure",
    }.get(role or "")


def option_for_label(
    registry: dict[str, dict[str, tuple[dict[str, Any], Any, str]]],
    row: dict[str, Any],
    label: str,
) -> dict[str, Any] | None:
    record, module, shape = registry[str(row["scenario"])][str(row["slug"])]
    options_arg = record["task"] if shape == "task" else record
    for option in module.action_options(options_arg):
        if str(option.get("label", "")) == label or str(option.get("label", "")).strip() == label.strip():
            return option
    return None


def annotated_timeout_rows(
    rows: list[dict[str, Any]],
    *,
    registry: dict[str, dict[str, tuple[dict[str, Any], Any, str]]],
    stable_window: int,
) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for row in rows:
        if row.get("outcome") != "agent_timeout":
            continue
        subtype, stable_label = classify_timeout(row, stable_window)
        sequence = select_sequence(row)
        option = option_for_label(registry, row, stable_label) if stable_label else None
        role = normalize_role(option) if option else None
        implied = implied_outcome(role) if subtype == "stable_choice_no_submit" else None
        annotations.append(
            {
                "scenario": row.get("scenario"),
                "slug": row.get("slug"),
                "task_id": row.get("task_id"),
                "case_id": row.get("case_id"),
                "title": row.get("title"),
                "misleader_type": row.get("misleader_type"),
                "task_readiness": row.get("task_readiness"),
                "timeout_subtype": subtype,
                "stable_window": stable_window,
                "select_sequence": sequence,
                "unique_selected_options": list(dict.fromkeys(sequence)),
                "last_n_actions": last_n_actions(row, stable_window),
                "stable_choice_label": stable_label,
                "stable_choice_action_id": option.get("action_id") if option else None,
                "stable_choice_token": option.get("token") if option else None,
                "stable_choice_role": role,
                "implied_outcome": implied,
                "would_change_outcome": bool(implied and implied != row.get("outcome")),
                "original_outcome": row.get("outcome"),
                "original_error_attribution": row.get("error_attribution"),
                "trace_length": len(row.get("trace") or []),
            }
        )
    return annotations


def adjusted_outcomes(rows: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> Counter[str]:
    stable_by_key = {
        (row.get("scenario"), row.get("slug")): row
        for row in annotations
        if row.get("timeout_subtype") == "stable_choice_no_submit" and row.get("implied_outcome")
    }
    outcomes: Counter[str] = Counter()
    for row in rows:
        annotation = stable_by_key.get((row.get("scenario"), row.get("slug")))
        outcomes[str(annotation["implied_outcome"] if annotation else row.get("outcome"))] += 1
    return outcomes


def summarize_one(label: str, rows: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> list[str]:
    original = Counter(str(row.get("outcome")) for row in rows)
    subtype_counts = Counter(str(row.get("timeout_subtype")) for row in annotations)
    stable = [row for row in annotations if row.get("timeout_subtype") == "stable_choice_no_submit"]
    oscillating = [row for row in annotations if row.get("timeout_subtype") == "oscillating_choice_no_submit"]
    implied = Counter(str(row.get("implied_outcome")) for row in stable)
    adjusted = adjusted_outcomes(rows, annotations)
    lines = [
        f"## {label}",
        "",
        f"- Total rows: `{len(rows)}`",
        f"- Original outcomes: `{dict(original)}`",
        f"- Timeout subtype counts: `{dict(subtype_counts)}`",
        f"- Stable implied outcomes: `{dict(implied)}`",
        f"- Adjusted outcomes from stable only: `{dict(adjusted)}`",
        "",
        "### Oscillating Examples",
        "",
        "| Scenario | Slug | Task ID | Select Sequence |",
        "|---|---|---|---|",
    ]
    for row in oscillating[:20]:
        seq = " -> ".join(row.get("select_sequence") or [])
        lines.append(f"| {row.get('scenario')} | {row.get('slug')} | {row.get('task_id')} | {seq} |")
    if not oscillating:
        lines.append("| - | - | - | - |")
    lines.append("")
    return lines


def analyze_record_dir(record_dir: Path, *, stable_window: int, registry: dict[str, Any]) -> dict[str, Any]:
    runs_path = record_dir / "runs.jsonl"
    rows = read_jsonl(runs_path)
    if not rows:
        raise RuntimeError(f"No rows found in {runs_path}")
    annotations = annotated_timeout_rows(rows, registry=registry, stable_window=stable_window)
    oscillating = [
        row for row in annotations if row.get("timeout_subtype") == "oscillating_choice_no_submit"
    ]
    write_jsonl(record_dir / "stable_choice_timeout_analysis.jsonl", annotations)
    write_jsonl(record_dir / "oscillating_choice_timeout_examples.jsonl", oscillating)
    summary_lines = ["# Stable Choice Timeout Analysis", "", *summarize_one(record_dir.name, rows, annotations)]
    (record_dir / "stable_choice_timeout_summary.md").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )
    return {"label": record_dir.name, "rows": rows, "annotations": annotations}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-dir", type=Path, action="append", help="Evaluation record directory.")
    parser.add_argument("--stable-window", type=int, default=3)
    parser.add_argument("--combined-summary", type=Path, default=DEFAULT_COMBINED_SUMMARY)
    args = parser.parse_args()

    record_dirs = args.record_dir or DEFAULT_RECORDS
    registry = load_registry()
    combined_lines = ["# Qwen3-VL Timeout Post-hoc Summary", ""]
    for record_dir in record_dirs:
        result = analyze_record_dir(record_dir, stable_window=args.stable_window, registry=registry)
        combined_lines.extend(summarize_one(result["label"], result["rows"], result["annotations"]))
    args.combined_summary.parent.mkdir(parents=True, exist_ok=True)
    args.combined_summary.write_text("\n".join(combined_lines) + "\n", encoding="utf-8")
    print(f"Wrote combined summary: {args.combined_summary}")
    for record_dir in record_dirs:
        print(f"Wrote analysis files in: {record_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
