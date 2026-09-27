#!/usr/bin/env python3
"""Audit successful official runs that show evidence of resisting a visual trap.

The script exhaustively reads the final main-experiment records, constructs a
recall-oriented candidate pool, and writes both a machine-readable manifest and
a human-readable audit report. Candidate-pool counts are diagnostics for paper
preparation; they are not benchmark metrics.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark/pair_evaluation_records/"
    / "final_selected_merged_20260523_kimi_full140_replaced"
)
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "web_agent_benchmark/official_benchmark_v1"
DEFAULT_CANDIDATE_OUTPUT = (
    REPO_ROOT / "paper/appendix_successful_resistance_trace_candidates_20260710.jsonl"
)
DEFAULT_REPORT_OUTPUT = (
    REPO_ROOT / "paper/appendix_successful_resistance_trace_audit_20260710.md"
)


MODEL_NAMES = {
    "claude_haiku_4_5_litellm_temp0_top_p1_seed12345": "Claude Haiku 4.5",
    "claude_opus_4_6_aime_responses_temp0_top_p1_seed12345": "Claude Opus 4.6",
    "claude_opus_4_7_aime_responses_temp0_top_p1_seed12345": "Claude Opus 4.7",
    "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345": "Claude Sonnet 4.6",
    "gemini_3_1_flash_image_preview_temp0_top_p1_seed12345": "Gemini 3.1 Flash",
    "gemini_3_pro_image_preview_temp0_top_p1_seed12345": "Gemini 3 Pro",
    "gpt54_temp0_top_p1_seed12345": "GPT-5.4",
    "gpt_5_5_litellm_temp0_top_p1_seed12345": "GPT-5.5",
    "kimik2_6_temp0_top_p1_seed12345": "Kimi K2.6",
    "qwen3_5_plus_temp0_top_p1_seed12345": "Qwen 3.5 Plus",
    "qwen3_6_plus_temp0_top_p1_seed12345": "Qwen 3.6 Plus",
}


# These patterns identify model-emitted evidence checks appropriate to each
# mechanism. They intentionally favor recall; every paper example is then
# manually verified against its screenshot, task specification, and full trace.
MECHANISM_PATTERNS = {
    "misleading_annotations": re.compile(
        r"(mislead|despite).{0,100}(title|data)|"
        r"title.{0,120}(data|trend|rise|fall|increase|decreas)",
        re.IGNORECASE | re.DOTALL,
    ),
    "data_visual_disproportion": re.compile(
        r"bar height|height.{0,80}label|label.{0,80}height|"
        r"numeric label|reading the percentages|percentages?:",
        re.IGNORECASE | re.DOTALL,
    ),
    "MS_unconventional_scale_directions": re.compile(
        r"(invert|revers).{0,80}(axis|scale)|"
        r"(axis|scale).{0,80}(invert|revers)",
        re.IGNORECASE | re.DOTALL,
    ),
    "dual_encoding": re.compile(
        r"(left|right).{0,60}axis|axis.{0,60}(left|right)",
        re.IGNORECASE | re.DOTALL,
    ),
    "dual_axis_distortion": re.compile(
        r"(left|right).{0,60}axis|axis.{0,60}(left|right)",
        re.IGNORECASE | re.DOTALL,
    ),
    "cherry_picking": re.compile(
        r"subset|selected.{0,40}(hospital|region|group)|"
        r"full.{0,40}population|broader.{0,40}(review|population)",
        re.IGNORECASE | re.DOTALL,
    ),
    "MS_inappropriate_scale_functions": re.compile(
        r"(full period|from.{0,20}\d{4}.{0,80}to.{0,20}\d{4}|"
        r"drop(?:ped)? from|declin(?:e|ing) from).{0,100}"
        r"(substantial|change|drop|declin)",
        re.IGNORECASE | re.DOTALL,
    ),
    "MS_inappropriate_scale_range": re.compile(
        r"(threshold|exceed|combined|approximately|around).{0,120}"
        r"(threshold|exceed|combined)",
        re.IGNORECASE | re.DOTALL,
    ),
    "misuse_of_cumulative_relationship": re.compile(
        r"(Q3|quarter 3).{0,100}(Q4|quarter 4)|"
        r"(Q4|quarter 4).{0,100}(Q3|quarter 3)",
        re.IGNORECASE | re.DOTALL,
    ),
}


APPENDIX_SELECTIONS = {
    (
        "claude_opus_4_7_aime_responses_temp0_top_p1_seed12345",
        "environment35",
        "env024",
    ): "detailed_visual_disproportion",
    (
        "claude_opus_4_7_aime_responses_temp0_top_p1_seed12345",
        "health19",
        "health018",
    ): "compact_title_data_conflict",
    (
        "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345",
        "health19",
        "health012",
    ): "compact_subset_scope_check",
    (
        "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345",
        "environment35",
        "env032",
    ): "compact_dual_axis_check",
}


API_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-root", type=Path, default=DEFAULT_RECORD_ROOT)
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    parser.add_argument(
        "--candidate-output", type=Path, default=DEFAULT_CANDIDATE_OUTPUT
    )
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def repo_relative(path: Path) -> str:
    resolved = path if path.is_absolute() else REPO_ROOT / path
    try:
        return str(resolved.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sanitize_text(value: Any) -> str:
    text = str(value or "")
    return API_KEY_PATTERN.sub("[REDACTED_API_KEY]", text)


def compact_text(value: Any) -> str:
    return " ".join(sanitize_text(value).split())


def load_tasks(benchmark_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    tasks: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(benchmark_root.glob("*_tasks.jsonl")):
        scenario = path.name.removesuffix("_tasks.jsonl")
        for task in read_jsonl(path):
            key = (scenario, task["official_slug"])
            if key in tasks:
                raise ValueError(f"Duplicate task key: {key}")
            tasks[key] = task
    if len(tasks) != 140:
        raise ValueError(f"Expected 140 official tasks, found {len(tasks)}")
    return tasks


def load_runs(record_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    run_paths = sorted(record_root.glob("*/official/runs.jsonl"))
    for path in run_paths:
        model_slug = path.parent.parent.name
        for run in read_jsonl(path):
            records.append(
                {
                    "model_slug": model_slug,
                    "run_path": path,
                    "run": run,
                }
            )
    return records


def action_target(action: dict[str, Any]) -> str:
    return str(
        action.get("option_text")
        or action.get("text")
        or action.get("url")
        or action.get("direction")
        or ""
    )


def build_action_trace(run: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for step in run.get("trace", []):
        action = step.get("action") or {}
        screenshot = step.get("screenshot")
        result.append(
            {
                "step": step.get("step"),
                "url": step.get("url"),
                "action": action.get("action"),
                "target": action_target(action),
                "raw_response": sanitize_text(action.get("_raw", "")),
                "screenshot": repo_relative(Path(screenshot)) if screenshot else None,
            }
        )
    return result


def screenshot_status(run: dict[str, Any]) -> tuple[bool, list[str]]:
    screenshot_paths = []
    complete = True
    for step in run.get("trace", []):
        raw_path = step.get("screenshot")
        if not raw_path:
            continue
        path = Path(raw_path)
        resolved = path if path.is_absolute() else REPO_ROOT / path
        complete = complete and resolved.exists()
        screenshot_paths.append(repo_relative(path))
    return bool(screenshot_paths) and complete, screenshot_paths


def task_actions(task: dict[str, Any]) -> tuple[str, list[str]]:
    expected_id = task["expected_action_id"]
    misleading_ids = set(task.get("misleading_action_ids", []))
    expected_label = ""
    misleading_labels = []
    for action in task.get("action_space", []):
        if action.get("action_id") == expected_id:
            expected_label = action.get("label", "")
        if action.get("action_id") in misleading_ids:
            misleading_labels.append(action.get("label", ""))
    if not expected_label:
        raise ValueError(f"Missing expected action label for {task.get('task_id')}")
    return expected_label, misleading_labels


def primary_action_sequence(run: dict[str, Any]) -> list[str]:
    return [
        action_target(step.get("action") or {})
        for step in run.get("trace", [])
        if (step.get("action") or {}).get("action") == "select_option"
        and (step.get("action") or {}).get("select_name") == "primary_action"
    ]


def mechanism_signal(run: dict[str, Any]) -> bool:
    raw = " ".join(
        sanitize_text((step.get("action") or {}).get("_raw", ""))
        for step in run.get("trace", [])
    )
    pattern = MECHANISM_PATTERNS.get(run.get("misleader_type"))
    return bool(pattern and pattern.search(raw))


def audit(
    records: list[dict[str, Any]], tasks: dict[tuple[str, str], dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runs_by_task: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        run = record["run"]
        runs_by_task[(run["scenario"], run["slug"])].append(record)

    metrics = Counter()
    candidates = []
    strict_task_keys = set()

    for record in records:
        run = record["run"]
        if run.get("outcome") != "success":
            continue
        metrics["official_success"] += 1

        task_key = (run["scenario"], run["slug"])
        task = tasks[task_key]
        expected_label, misleading_labels = task_actions(task)
        sequence = primary_action_sequence(run)
        trap_to_correct = bool(
            sequence
            and any(label in misleading_labels for label in sequence[:-1])
            and sequence[-1] == run.get("selected_action_label")
        )
        emitted_check = mechanism_signal(run)
        has_candidate_signal = trap_to_correct or emitted_check
        other_misleading_records = [
            other
            for other in runs_by_task[task_key]
            if other["model_slug"] != record["model_slug"]
            and other["run"].get("outcome") == "misleading_failure"
        ]
        screenshots_complete, screenshot_paths = screenshot_status(run)

        metrics["trap_to_correct"] += int(trap_to_correct)
        metrics["mechanism_signal"] += int(emitted_check)
        metrics["candidate_signal_union"] += int(has_candidate_signal)
        metrics["success_with_other_model_misleading_failure"] += int(
            bool(other_misleading_records)
        )
        metrics["success_with_complete_screenshots"] += int(screenshots_complete)

        strict = bool(
            has_candidate_signal and other_misleading_records and screenshots_complete
        )
        if not strict:
            continue
        metrics["strict_candidates"] += 1
        strict_task_keys.add(task_key)

        appendix_key = (record["model_slug"], *task_key)
        candidates.append(
            {
                "model_slug": record["model_slug"],
                "model_name": MODEL_NAMES.get(
                    record["model_slug"], record["model_slug"]
                ),
                "model_key": run.get("model_key"),
                "scenario": run["scenario"],
                "slug": run["slug"],
                "task_id": run.get("task_id"),
                "misleader_type": run.get("misleader_type"),
                "task_readiness": task.get("task_readiness"),
                "scoring_status": task.get("scoring_status"),
                "outcome": run.get("outcome"),
                "selected_action_id": run.get("selected_action_id"),
                "selected_action_label": run.get("selected_action_label"),
                "expected_action_id": task.get("expected_action_id"),
                "expected_action_label": expected_label,
                "misleading_action_ids": task.get("misleading_action_ids", []),
                "misleading_action_labels": misleading_labels,
                "primary_action_sequence": sequence,
                "trap_to_correct": trap_to_correct,
                "mechanism_signal": emitted_check,
                "other_model_misleading_failure_count": len(
                    other_misleading_records
                ),
                "other_model_misleading_failure_models": sorted(
                    other["model_slug"] for other in other_misleading_records
                ),
                "screenshots_complete": screenshots_complete,
                "screenshot_paths": screenshot_paths,
                "run_record_path": repo_relative(record["run_path"]),
                "action_trace": build_action_trace(run),
                "appendix_selection": APPENDIX_SELECTIONS.get(appendix_key),
            }
        )

    metrics["strict_candidate_tasks"] = len(strict_task_keys)
    metrics["official_records"] = len(records)
    metrics["models"] = len({record["model_slug"] for record in records})
    metrics["official_tasks_per_model"] = (
        len(records) // metrics["models"] if metrics["models"] else 0
    )

    candidates.sort(
        key=lambda row: (
            row["scenario"],
            row["slug"],
            row["model_slug"],
        )
    )
    return candidates, dict(metrics)


def markdown_escape(value: Any) -> str:
    return compact_text(value).replace("|", "\\|")


def selected_candidate(
    candidates: list[dict[str, Any]], role: str
) -> dict[str, Any]:
    matches = [row for row in candidates if row["appendix_selection"] == role]
    if len(matches) != 1:
        raise ValueError(f"Expected one selected candidate for {role}, found {len(matches)}")
    return matches[0]


def render_selected_trace(candidate: dict[str, Any]) -> list[str]:
    lines = []
    for item in candidate["action_trace"]:
        target = f" -> {item['target']}" if item["target"] else ""
        lines.append(
            f"{item['step']}. `{item['action']}{target}`"
        )
        raw = compact_text(item["raw_response"])
        if raw:
            lines.append(f"   - Model-emitted text: {raw}")
    return lines


def write_report(
    path: Path,
    candidates: list[dict[str, Any]],
    metrics: dict[str, Any],
    record_root: Path,
    benchmark_root: Path,
    candidate_output: Path,
) -> None:
    detailed = selected_candidate(candidates, "detailed_visual_disproportion")
    compact_roles = [
        "compact_title_data_conflict",
        "compact_subset_scope_check",
        "compact_dual_axis_check",
    ]
    compact = [selected_candidate(candidates, role) for role in compact_roles]

    lines = [
        "# Main-Experiment Successful-Resistance Trace Audit",
        "",
        f"- Final record root: `{repo_relative(record_root)}`",
        f"- Official task root: `{repo_relative(benchmark_root)}`",
        "- Scope: all official runs from the 11-model main experiment.",
        "- Purpose: prepare auditable appendix examples; candidate counts below are not benchmark metrics.",
        "",
        "## Audit Counts",
        "",
        "| Check | Count |",
        "|---|---:|",
        f"| Models | {metrics['models']} |",
        f"| Official records | {metrics['official_records']} |",
        f"| Official tasks per model | {metrics['official_tasks_per_model']} |",
        f"| Official successes | {metrics['official_success']} |",
        f"| Misleading-trap to correct-action traces | {metrics['trap_to_correct']} |",
        f"| Mechanism-specific emitted-check traces | {metrics['mechanism_signal']} |",
        f"| Union of the two candidate signals | {metrics['candidate_signal_union']} |",
        f"| Strict candidate runs | {metrics['strict_candidates']} |",
        f"| Strict candidate tasks | {metrics['strict_candidate_tasks']} |",
        "",
        "## Selection Protocol",
        "",
        "1. Exhaustively enumerate all official main-experiment records and retain terminal `success` runs.",
        "2. Require either an observed misleading-action-to-correct-action change or mechanism-specific evidence checking in the model-emitted text.",
        "3. Require at least one other main-model run on the same task to end in `misleading_failure`.",
        "4. Require all referenced screenshots to exist.",
        "5. Manually verify appendix selections against the task specification, screenshot, complete action trace, and final scored outcome.",
        "",
        "The text-pattern stage is deliberately recall-oriented. The resulting 92 runs and 41 tasks form an internal review pool and must not be reported as a measured prevalence of robust reasoning.",
        "",
        "## Detailed Appendix Selection",
        "",
        f"- Model: **{detailed['model_name']}**",
        f"- Task: `{detailed['scenario']}/{detailed['slug']}`",
        f"- Mechanism: `{detailed['misleader_type']}`",
        f"- Correct action: {detailed['expected_action_label']}",
        f"- Pre-specified trap: {', '.join(detailed['misleading_action_labels'])}",
        f"- Other main-model directed failures on this task: {detailed['other_model_misleading_failure_count']}",
        f"- Source record: `{detailed['run_record_path']}`",
        "",
        "### Full Recorded Trace",
        "",
        *render_selected_trace(detailed),
        "",
        "## Complementary Appendix Selections",
        "",
        "| Model | Task | Mechanism | Trap -> final action | Other directed failures |",
        "|---|---|---|---|---:|",
    ]
    for candidate in compact:
        transition = (
            f"{', '.join(candidate['misleading_action_labels'])} -> "
            f"{candidate['selected_action_label']}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(candidate["model_name"]),
                    f"`{candidate['scenario']}/{candidate['slug']}`",
                    f"`{candidate['misleader_type']}`",
                    markdown_escape(transition),
                    str(candidate["other_model_misleading_failure_count"]),
                ]
            )
            + " |"
        )

    for candidate in compact:
        lines.extend(
            [
                "",
                f"### {candidate['scenario']}/{candidate['slug']} - {candidate['model_name']}",
                "",
                f"- Source record: `{candidate['run_record_path']}`",
                f"- Primary-action sequence: `{candidate['primary_action_sequence']}`",
                *render_selected_trace(candidate),
            ]
        )

    lines.extend(
        [
            "",
            "## Interpretation Guardrails",
            "",
            "- Browser actions, selected options, screenshots, and terminal outcomes are directly auditable.",
            "- Explanatory text is quoted as model-emitted text; it is not treated as privileged access to latent reasoning.",
            "- The examples illustrate observed verification behaviors and do not establish that these checks are causally sufficient defenses.",
            "- Evaluator-only labels are used to audit correctness but were not visible to the agent during execution.",
            "",
            "## Machine-Readable Candidate Pool",
            "",
            f"See `{repo_relative(candidate_output)}` for all strict candidate runs and their complete recorded action traces.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def validate_expected_counts(metrics: dict[str, Any]) -> None:
    expected = {
        "models": 11,
        "official_records": 1540,
        "official_tasks_per_model": 140,
        "official_success": 639,
        "trap_to_correct": 37,
        "mechanism_signal": 107,
        "candidate_signal_union": 136,
        "strict_candidates": 92,
        "strict_candidate_tasks": 41,
    }
    mismatches = {
        key: (metrics.get(key), value)
        for key, value in expected.items()
        if metrics.get(key) != value
    }
    if mismatches:
        details = ", ".join(
            f"{key}: got {got}, expected {want}"
            for key, (got, want) in mismatches.items()
        )
        raise ValueError(f"Audit count mismatch: {details}")


def main() -> None:
    args = parse_args()
    tasks = load_tasks(args.benchmark_root)
    records = load_runs(args.record_root)
    candidates, metrics = audit(records, tasks)
    validate_expected_counts(metrics)

    args.candidate_output.parent.mkdir(parents=True, exist_ok=True)
    with args.candidate_output.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    write_report(
        args.report_output,
        candidates,
        metrics,
        args.record_root,
        args.benchmark_root,
        args.candidate_output,
    )
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    print(f"candidate_output={args.candidate_output}")
    print(f"report_output={args.report_output}")


if __name__ == "__main__":
    main()
