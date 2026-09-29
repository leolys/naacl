#!/usr/bin/env python3
"""Build the canonical official_benchmark_v1 package."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.business_shell import business_shell_app as business_shell  # noqa: E402
from web_agent_benchmark.environment_energy_shell import environment_shell_app as environment_shell  # noqa: E402
from web_agent_benchmark.evaluation import run_official_benchmark140 as official_eval  # noqa: E402
from web_agent_benchmark.health_shell import health_shell_app as health_shell  # noqa: E402
from web_agent_benchmark.public_benchmark import public_benchmark_shell_app as public_shell  # noqa: E402


OFFICIAL_DIR = REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1"
EVAL_DIR = REPO_ROOT / "web_agent_benchmark" / "evaluation"
VERSION = "official_benchmark_v1"
DETERMINISTIC_EVAL_DIR = (
    OFFICIAL_DIR / "evaluation_records" / "gpt54_temp0_top_p1_seed12345_full140"
)
QWEN3_VL_8B_EVAL_DIR = OFFICIAL_DIR / "evaluation_records" / "qwen3_vl_8b_full140"
QWEN3_VL_32B_EVAL_DIR = OFFICIAL_DIR / "evaluation_records" / "qwen3_vl_32b_full140"
LLAMA32_11B_EVAL_DIR = OFFICIAL_DIR / "evaluation_records" / "llama3_2_vision_11b_full140"
LLAMA32_90B_EVAL_DIR = OFFICIAL_DIR / "evaluation_records" / "llama3_2_vision_90b_full140"
LLAMA32_90B_4GPU_RERUN_EVAL_DIR = (
    OFFICIAL_DIR / "evaluation_records" / "llama3_2_vision_90b_full140_4gpu_rerun"
)
LLAMA32_90B_PROMPT_ONLY_RERUN_EVAL_DIR = (
    OFFICIAL_DIR / "evaluation_records" / "llama3_2_vision_90b_full140_prompt_only_rerun"
)
QWEN3_VL_TIMEOUT_POSTHOC_SUMMARY = (
    OFFICIAL_DIR / "evaluation_records" / "qwen3_vl_timeout_posthoc_summary.md"
)
QWEN3_VL_SELECTED_STATE_FIX_SUMMARY = (
    OFFICIAL_DIR / "evaluation_records" / "qwen3_vl_selected_state_fix_test_summary.md"
)
PAPER_EXPERIMENT_RESULTS = OFFICIAL_DIR / "paper_experiment_results.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def link_from_official(path: Path) -> str:
    return os.path.relpath(path, OFFICIAL_DIR)


def export_public39() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in public_shell.load_public39_records():
        task = deepcopy(record["task"])
        task["official_benchmark_version"] = VERSION
        task["official_scenario"] = "public39"
        task["official_slug"] = record["slug"]
        task["official_task_index"] = record["index"] + 1
        task["official_source_group"] = record["source_group"]
        task["official_source_slug"] = record["source_slug"]
        task["official_shell_template"] = record.get("template")
        task["official_shell_override"] = record.get("override", {})
        rows.append(task)
    return rows


def export_business47() -> list[dict[str, Any]]:
    records, _ = business_shell.build_registry(business_shell.load_business_tasks(business_shell.DEFAULT_TASKS))
    rows: list[dict[str, Any]] = []
    for record in records:
        task = deepcopy(record["task"])
        task["official_benchmark_version"] = VERSION
        task["official_scenario"] = "business47"
        task["official_slug"] = record["slug"]
        task["official_task_index"] = record["index"] + 1
        rows.append(task)
    return rows


def export_environment35() -> list[dict[str, Any]]:
    records = environment_shell.load_records(environment_shell.DEFAULT_TASKS)
    rows: list[dict[str, Any]] = []
    for record in records:
        task = deepcopy(record["task"])
        task["official_benchmark_version"] = VERSION
        task["official_scenario"] = "environment35"
        task["official_slug"] = record["slug"]
        task["official_task_index"] = record["index"] + 1
        rows.append(task)
    return rows


def export_health19() -> list[dict[str, Any]]:
    records = health_shell.load_records(health_shell.DEFAULT_TASKS)
    rows: list[dict[str, Any]] = []
    for record in records:
        task = deepcopy(record["task"])
        task["official_benchmark_version"] = VERSION
        task["official_scenario"] = "health19"
        task["official_slug"] = record["slug"]
        task["official_task_index"] = record["index"] + 1
        rows.append(task)
    return rows


def scenario_rows() -> dict[str, list[dict[str, Any]]]:
    return {
        "public39": export_public39(),
        "business47": export_business47(),
        "environment35": export_environment35(),
        "health19": export_health19(),
    }


def build_trace_registry() -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    for scenario_name in official_eval.DEFAULT_ORDER:
        meta = official_eval.SCENARIOS[scenario_name]
        registry.append(
            {
                "scenario": scenario_name,
                "runs_file": rel(meta["official_runs"]),
                "failures_file": rel(meta["official_failures"]),
                "summary_file": rel(meta["official_summary"]),
                "trace_viewer_app": rel(meta["viewer_app"]),
                "trace_viewer_port": meta["viewer_port"],
                "shell_app": rel(meta["shell_app"]),
                "shell_port": meta["shell_port"],
            }
        )
    return registry


def build_manifest(exported: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    total = 0
    for scenario_name in official_eval.DEFAULT_ORDER:
        rows = exported[scenario_name]
        meta = official_eval.SCENARIOS[scenario_name]
        readiness_counts = Counter(row.get("task_readiness", "legacy_or_unspecified") for row in rows)
        scenario_entry = {
            "scenario": scenario_name,
            "task_count": len(rows),
            "canonical_tasks_file": rel(OFFICIAL_DIR / f"{scenario_name}_tasks.jsonl"),
            "shell_app": rel(meta["shell_app"]),
            "shell_port": meta["shell_port"],
            "runner": rel(meta["runner"]),
            "official_runs": rel(meta["official_runs"]),
            "official_summary": rel(meta["official_summary"]),
            "official_failures": rel(meta["official_failures"]),
            "trace_viewer_app": rel(meta["viewer_app"]),
            "trace_viewer_port": meta["viewer_port"],
            "official_submissions": rel(meta["submissions"]),
            "readiness_distribution": dict(readiness_counts),
        }
        scenarios.append(scenario_entry)
        total += len(rows)
    return {
        "benchmark_version": VERSION,
        "generated_at": utc_now(),
        "benchmark_total": total,
        "aggregate_runner": rel(EVAL_DIR / "run_official_benchmark140.py"),
        "official_aggregate_runs": rel(EVAL_DIR / "official_benchmark140_gpt54_runs.jsonl"),
        "official_aggregate_summary": rel(EVAL_DIR / "official_benchmark140_gpt54_summary.md"),
        "official_aggregate_failures": rel(EVAL_DIR / "official_benchmark140_gpt54_failures.jsonl"),
        "deterministic_gpt54_eval_record": {
            "label": "gpt54_temp0_top_p1_seed12345_full140",
            "directory": rel(DETERMINISTIC_EVAL_DIR),
            "runs": rel(DETERMINISTIC_EVAL_DIR / "runs.jsonl"),
            "summary": rel(DETERMINISTIC_EVAL_DIR / "summary.md"),
            "failures": rel(DETERMINISTIC_EVAL_DIR / "failures.jsonl"),
            "run_config": rel(DETERMINISTIC_EVAL_DIR / "run_config.json"),
            "decoding_config": {"temperature": 0, "top_p": 1, "seed": 12345},
        },
        "qwen3_vl_eval_records": [
            {
                "label": "qwen3_vl_8b_full140",
                "model_size": "8b",
                "model_path": "/mnt/data/datasets/open_source_models/Qwen3-VL-8B-Instruct",
                "directory": rel(QWEN3_VL_8B_EVAL_DIR),
                "runs": rel(QWEN3_VL_8B_EVAL_DIR / "runs.jsonl"),
                "summary": rel(QWEN3_VL_8B_EVAL_DIR / "summary.md"),
                "failures": rel(QWEN3_VL_8B_EVAL_DIR / "failures.jsonl"),
                "run_config": rel(QWEN3_VL_8B_EVAL_DIR / "run_config.json"),
                "timeout_posthoc_analysis": rel(QWEN3_VL_8B_EVAL_DIR / "stable_choice_timeout_analysis.jsonl"),
                "timeout_posthoc_summary": rel(QWEN3_VL_8B_EVAL_DIR / "stable_choice_timeout_summary.md"),
                "oscillating_timeout_examples": rel(QWEN3_VL_8B_EVAL_DIR / "oscillating_choice_timeout_examples.jsonl"),
            },
            {
                "label": "qwen3_vl_32b_full140",
                "model_size": "32b",
                "model_path": "/mnt/data/datasets/open_source_models/Qwen3-vl-32-instruct",
                "directory": rel(QWEN3_VL_32B_EVAL_DIR),
                "runs": rel(QWEN3_VL_32B_EVAL_DIR / "runs.jsonl"),
                "summary": rel(QWEN3_VL_32B_EVAL_DIR / "summary.md"),
                "failures": rel(QWEN3_VL_32B_EVAL_DIR / "failures.jsonl"),
                "run_config": rel(QWEN3_VL_32B_EVAL_DIR / "run_config.json"),
                "timeout_posthoc_analysis": rel(QWEN3_VL_32B_EVAL_DIR / "stable_choice_timeout_analysis.jsonl"),
                "timeout_posthoc_summary": rel(QWEN3_VL_32B_EVAL_DIR / "stable_choice_timeout_summary.md"),
                "oscillating_timeout_examples": rel(QWEN3_VL_32B_EVAL_DIR / "oscillating_choice_timeout_examples.jsonl"),
            },
        ],
        "qwen3_vl_timeout_posthoc_summary": rel(QWEN3_VL_TIMEOUT_POSTHOC_SUMMARY),
        "qwen3_vl_selected_state_fix_test_summary": rel(QWEN3_VL_SELECTED_STATE_FIX_SUMMARY),
        "llama3_2_vision_eval_records": [
            {
                "label": "llama3_2_vision_11b_full140",
                "model_size": "11b",
                "model_path": "/mnt/data/datasets/open_source_models/llama3.2_vision_11B",
                "directory": rel(LLAMA32_11B_EVAL_DIR),
                "runs": rel(LLAMA32_11B_EVAL_DIR / "runs.jsonl"),
                "summary": rel(LLAMA32_11B_EVAL_DIR / "summary.md"),
                "failures": rel(LLAMA32_11B_EVAL_DIR / "failures.jsonl"),
                "run_config": rel(LLAMA32_11B_EVAL_DIR / "run_config.json"),
            },
            {
                "label": "llama3_2_vision_90b_full140",
                "model_size": "90b",
                "model_path": "/mnt/data/datasets/open_source_models/Llama-3.2-90B-Vision",
                "note": "Historical 3-GPU run; generation failed due to CUDA OOM.",
                "directory": rel(LLAMA32_90B_EVAL_DIR),
                "runs": rel(LLAMA32_90B_EVAL_DIR / "runs.jsonl"),
                "summary": rel(LLAMA32_90B_EVAL_DIR / "summary.md"),
                "failures": rel(LLAMA32_90B_EVAL_DIR / "failures.jsonl"),
                "run_config": rel(LLAMA32_90B_EVAL_DIR / "run_config.json"),
            },
            {
                "label": "llama3_2_vision_90b_full140_4gpu_rerun",
                "model_size": "90b",
                "model_path": "/mnt/data/datasets/open_source_models/Llama-3.2-90B-Vision",
                "cuda_visible_devices": "4,5,6,7",
                "note": "Official clean 4-GPU rerun after removing the previous CUDA OOM blocker.",
                "directory": rel(LLAMA32_90B_4GPU_RERUN_EVAL_DIR),
                "runs": rel(LLAMA32_90B_4GPU_RERUN_EVAL_DIR / "runs.jsonl"),
                "summary": rel(LLAMA32_90B_4GPU_RERUN_EVAL_DIR / "summary.md"),
                "failures": rel(LLAMA32_90B_4GPU_RERUN_EVAL_DIR / "failures.jsonl"),
                "run_config": rel(LLAMA32_90B_4GPU_RERUN_EVAL_DIR / "run_config.json"),
            },
            {
                "label": "llama3_2_vision_90b_full140_prompt_only_rerun",
                "model_size": "90b",
                "model_path": "/mnt/data/datasets/open_source_models/Llama-3.2-90B-Vision",
                "cuda_visible_devices": "4,5,6,7",
                "note": "Execution-prompt ablation only; no runner guardrail, shell, task, or scoring changes. This negative ablation increased timeouts and is not the main 90B score.",
                "directory": rel(LLAMA32_90B_PROMPT_ONLY_RERUN_EVAL_DIR),
                "runs": rel(LLAMA32_90B_PROMPT_ONLY_RERUN_EVAL_DIR / "runs.jsonl"),
                "summary": rel(LLAMA32_90B_PROMPT_ONLY_RERUN_EVAL_DIR / "summary.md"),
                "failures": rel(LLAMA32_90B_PROMPT_ONLY_RERUN_EVAL_DIR / "failures.jsonl"),
                "run_config": rel(LLAMA32_90B_PROMPT_ONLY_RERUN_EVAL_DIR / "run_config.json"),
            },
        ],
        "paper_experiment_results": rel(PAPER_EXPERIMENT_RESULTS),
        "trace_registry": rel(OFFICIAL_DIR / "official_benchmark140_trace_registry.json"),
        "scenarios": scenarios,
    }


def build_aggregate_full_outputs() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = official_eval.aggregate_existing_full_runs()
    runs_out, summary_out, failures_out = official_eval.output_paths("llm_agent", "full")
    official_eval.write_jsonl(runs_out, rows)
    failures = [row for row in rows if row.get("outcome") != "success"]
    official_eval.write_jsonl(failures_out, failures)
    official_eval.write_summary(summary_out, rows, mode="llm_agent", profile="full", scenarios=official_eval.DEFAULT_ORDER)
    return rows, official_eval.summarize_rows(rows)


def write_readme(manifest: dict[str, Any]) -> None:
    lines = [
        "# official_benchmark_v1",
        "",
        "This directory is the canonical release surface for the current reviewed misleading-visualization agent benchmark.",
        "",
        f"- Benchmark version: `{manifest['benchmark_version']}`",
        f"- Total official tasks: `{manifest['benchmark_total']}`",
        "- Official scenarios: `public39`, `business47`, `environment35`, `health19`",
        "",
        "## Canonical Task Files",
        "",
    ]
    for scenario in manifest["scenarios"]:
        lines.append(
            f"- `{scenario['scenario']}`: [{Path(scenario['canonical_tasks_file']).name}]({Path(scenario['canonical_tasks_file']).name}) "
            f"({scenario['task_count']} tasks)"
        )
    lines.extend(
        [
            "",
            "## Official Evaluation Baselines",
            "",
            f"- Full 140-task GPT-5.4 aggregate runs: [{Path(manifest['official_aggregate_runs']).name}]({link_from_official(REPO_ROOT / manifest['official_aggregate_runs'])})",
            f"- Full 140-task GPT-5.4 aggregate summary: [{Path(manifest['official_aggregate_summary']).name}]({link_from_official(REPO_ROOT / manifest['official_aggregate_summary'])})",
            f"- Deterministic GPT-5.4 full-140 record: [{manifest['deterministic_gpt54_eval_record']['label']}]({link_from_official(REPO_ROOT / manifest['deterministic_gpt54_eval_record']['directory'])})",
            "- Qwen3-VL 8B full-140 record: [qwen3_vl_8b_full140](evaluation_records/qwen3_vl_8b_full140)",
            "- Qwen3-VL 32B full-140 record: [qwen3_vl_32b_full140](evaluation_records/qwen3_vl_32b_full140)",
            "- Llama-3.2 Vision 11B full-140 record: [llama3_2_vision_11b_full140](evaluation_records/llama3_2_vision_11b_full140)",
            "- Llama-3.2 Vision 90B clean 4-GPU full-140 rerun: [llama3_2_vision_90b_full140_4gpu_rerun](evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun)",
            "- Llama-3.2 Vision 90B prompt-only timeout ablation: [llama3_2_vision_90b_full140_prompt_only_rerun](evaluation_records/llama3_2_vision_90b_full140_prompt_only_rerun)",
            "- Llama-3.2 Vision 90B historical 3-GPU OOM record: [llama3_2_vision_90b_full140](evaluation_records/llama3_2_vision_90b_full140)",
            "- Qwen3-VL timeout post-hoc summary: [qwen3_vl_timeout_posthoc_summary.md](evaluation_records/qwen3_vl_timeout_posthoc_summary.md)",
            "- Qwen3-VL selected-state fix test summary: [qwen3_vl_selected_state_fix_test_summary.md](evaluation_records/qwen3_vl_selected_state_fix_test_summary.md)",
            "- Paper-facing experiment results draft: [paper_experiment_results.md](paper_experiment_results.md)",
            "",
            "Per-scenario official baseline result files are recorded in `benchmark_manifest.json` and `scenario_inventory.jsonl`.",
            "",
            "## Asset Classes",
            "",
            "- `official`: canonical task files, this manifest layer, shell entrypoints, official baseline evaluation outputs",
            "- `supporting`: scenario runners, trace viewers, navigation-revisit analysis, review annotations needed to explain provenance",
            "- `historical / intermediate`: gallery pools, OCR caches, manual rewrite workspaces, scratch summaries, review logs, old port logs",
            "",
            "## What To Use In A Fresh Conversation",
            "",
            "Start from this directory when you need a stable handoff for experiments, paper writing, or rerunning GPT-5.4 baselines. The shell apps remain the formal execution surfaces; the task JSONL files here are the frozen canonical exports for analysis, citation, and future automation.",
            "",
        ]
    )
    (OFFICIAL_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_reproduction_guide(manifest: dict[str, Any]) -> None:
    lines = [
        "# Reproduction Guide",
        "",
        "## Launch Shells",
        "",
        "```bash",
        "python web_agent_benchmark/public_benchmark/public_benchmark_shell_app.py --host 127.0.0.1 --port 8026",
        "python web_agent_benchmark/business_shell/business_shell_app.py --port 8016",
        "python web_agent_benchmark/environment_energy_shell/environment_shell_app.py --host 127.0.0.1 --port 8033",
        "python web_agent_benchmark/health_shell/health_shell_app.py --host 127.0.0.1 --port 8037",
        "```",
        "",
        "Reviewer routes stay under `/review/...` where supported; formal agent evaluation uses only `/task/...` routes.",
        "",
        "## Scenario Runners",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/run_public39.py --mode llm_agent --tasks pub001-pub039",
        "python web_agent_benchmark/evaluation/run_business47.py --mode llm_agent --tasks b001-b047",
        "python web_agent_benchmark/evaluation/run_environment35.py --mode llm_agent --tasks env001-env035",
        "python web_agent_benchmark/evaluation/run_health19.py --mode llm_agent --tasks health001-health019",
        "```",
        "",
        "## Full Benchmark Runner",
        "",
        "Dry run:",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode llm_agent --profile dryrun",
        "```",
        "",
        "Full 140-task run:",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode llm_agent --profile full",
        "```",
        "",
        "Mock smoke checks:",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode mock_correct --profile dryrun",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode mock_misleading --profile dryrun",
        "```",
        "",
        "The full-benchmark runner writes mode-specific outputs into `web_agent_benchmark/evaluation/`. For GPT-5.4 runs the canonical outputs are:",
        "",
        "- `official_benchmark140_gpt54_runs.jsonl`",
        "- `official_benchmark140_gpt54_summary.md`",
        "- `official_benchmark140_gpt54_failures.jsonl`",
        "",
        "Qwen3-VL 8B / 32B full benchmark runs use a local Qwen server in the dedicated conda environment:",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py \\",
        "  --mode llm_agent --profile full \\",
        "  --agent-backend qwen3_vl_http --qwen-model-size 8b \\",
        "  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/qwen3_vl_8b_full140",
        "",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py \\",
        "  --mode llm_agent --profile full \\",
        "  --agent-backend qwen3_vl_http --qwen-model-size 32b \\",
        "  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/qwen3_vl_32b_full140",
        "```",
        "",
        "These commands auto-start `web_agent_benchmark/evaluation/qwen3_vl_server.py` with `/mnt/data/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python` and `CUDA_VISIBLE_DEVICES=4,5,6`.",
        "",
        "Llama-3.2 Vision 11B / 90B full benchmark runs use the same local HTTP serving pattern in the InternVL conda environment:",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py \\",
        "  --mode llm_agent --profile full \\",
        "  --agent-backend llama32_vision_http --llama32-model-size 11b \\",
        "  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_11b_full140",
        "",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py \\",
        "  --mode llm_agent --profile full \\",
        "  --agent-backend llama32_vision_http --llama32-model-size 90b \\",
        "  --llama32-cuda-visible-devices 4,5,6,7 \\",
        "  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun",
        "```",
        "",
        "The prompt-only timeout ablation keeps the same Llama-90B serving setup and changes only the LLM action prompt. It is recorded separately because it is not the main 90B score:",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/run_official_benchmark140.py \\",
        "  --mode llm_agent --profile full \\",
        "  --agent-backend llama32_vision_http --llama32-model-size 90b \\",
        "  --llama32-cuda-visible-devices 4,5,6,7 \\",
        "  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_90b_full140_prompt_only_rerun",
        "```",
        "",
        "These commands auto-start `web_agent_benchmark/evaluation/llama32_vision_server.py` with `/mnt/data/code_generation/liyisheng/8H100conda/envs/internvl/bin/python`; the 90B commands above explicitly use `CUDA_VISIBLE_DEVICES=4,5,6,7`.",
        "",
        "## Trace Viewers",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/public39_trace_viewer_app.py --runs web_agent_benchmark/evaluation/public39_gpt54_runs.jsonl --port 8027",
        "python web_agent_benchmark/evaluation/trace_viewer_app.py --runs web_agent_benchmark/evaluation/business47_llm_full_runs.jsonl --port 8017",
        "python web_agent_benchmark/evaluation/environment35_trace_viewer_app.py --runs web_agent_benchmark/evaluation/environment35_gpt54_runs.jsonl --port 8034",
        "python web_agent_benchmark/evaluation/health19_trace_viewer_app.py --runs web_agent_benchmark/evaluation/health19_gpt54_runs.jsonl --port 8038",
        "```",
        "",
        "## Navigation Revisit Analysis",
        "",
        "```bash",
        "python web_agent_benchmark/evaluation/analyze_navigation_revisits.py \\",
        "  --runs web_agent_benchmark/evaluation/public39_gpt54_runs.jsonl \\",
        "  --out web_agent_benchmark/evaluation/public39_navigation_revisit_metrics.jsonl \\",
        "  --summary-out web_agent_benchmark/evaluation/public39_navigation_revisit_summary.md \\",
        "  --report-title 'Public 39 Navigation Revisit Metrics'",
        "```",
        "",
        "Use the same pattern for the other three scenarios by swapping in the corresponding runs, rerun, metrics, and summary paths recorded in `benchmark_manifest.json`.",
        "",
    ]
    (OFFICIAL_DIR / "reproduction_guide.md").write_text("\n".join(lines), encoding="utf-8")


def write_artifact_provenance(exported: dict[str, list[dict[str, Any]]]) -> None:
    lines = [
        "# Artifact Provenance",
        "",
        "This document maps the reviewed working artifacts in the repository to the canonical official benchmark exports.",
        "",
        "## Canonical Exports",
        "",
        "- `public39_tasks.jsonl`: exported from `public_benchmark_shell_app.load_public39_records()` with frozen public slugs, source-group metadata, and task payloads.",
        "- `business47_tasks.jsonl`: exported from `business_shell_app.build_registry(load_business_tasks(DEFAULT_TASKS))` with frozen `b001-b047` slugs.",
        "- `environment35_tasks.jsonl`: exported from the approved environment shell task set loaded by `environment_shell_app.load_records(DEFAULT_TASKS)`.",
        "- `health19_tasks.jsonl`: exported from the approved health shell task set loaded by `health_shell_app.load_records(DEFAULT_TASKS)`.",
        "",
        "## Execution Surfaces",
        "",
        "- Public 39 shell: `web_agent_benchmark/public_benchmark/public_benchmark_shell_app.py`",
        "- Business 47 shell: `web_agent_benchmark/business_shell/business_shell_app.py`",
        "- Environment 35 shell: `web_agent_benchmark/environment_energy_shell/environment_shell_app.py`",
        "- Health 19 shell: `web_agent_benchmark/health_shell/health_shell_app.py`",
        "",
        "## Official Baseline Results",
        "",
        "- Public 39: `web_agent_benchmark/evaluation/public39_gpt54_runs.jsonl`",
        "- Business 47: `web_agent_benchmark/evaluation/business47_llm_full_runs.jsonl`",
        "- Environment 35: `web_agent_benchmark/evaluation/environment35_gpt54_runs.jsonl`",
        "- Health 19: `web_agent_benchmark/evaluation/health19_gpt54_runs.jsonl`",
        "- Full 140 aggregate baseline: `web_agent_benchmark/evaluation/official_benchmark140_gpt54_runs.jsonl`",
        "",
        "## Supporting vs Historical Assets",
        "",
        "- `supporting`: scenario runners, trace viewers, review annotations, shell build summaries, navigation revisit analysis",
        "- `historical / intermediate`: expansion/gallery directories, OCR classification caches, manual variant workspaces, raw review logs, old shell logs, old port logs",
        "",
        "No files are deleted in this release pass. The goal is to make the official benchmark obvious while preserving provenance needed for later paper and ablation work.",
        "",
    ]
    (OFFICIAL_DIR / "artifact_provenance.md").write_text("\n".join(lines), encoding="utf-8")


def write_aggregate_eval_summary(summary: dict[str, Any]) -> None:
    lines = [
        "# Aggregate Evaluation Summary",
        "",
        "This file freezes the current official GPT-5.4 baseline across the four reviewed scenarios.",
        "",
        f"- Total tasks: `{summary['task_count']}`",
        f"- Total success count: `{summary['success_count']}`",
        f"- Total success rate: `{summary['success_rate']:.2%}`",
        f"- Outcome distribution: `{summary['outcome_counts']}`",
        "",
        "| Scenario | Task Count | Success | Misleading Failure | Other Failures | Success Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario_name in official_eval.DEFAULT_ORDER:
        row = summary["by_scenario"][scenario_name]
        lines.append(
            f"| {scenario_name} | {row['task_count']} | {row['success_count']} | "
            f"{row['misleading_failure_count']} | {row['other_failure_count']} | {row['success_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Official Baseline Files",
            "",
            f"- Aggregate runs: [{(EVAL_DIR / 'official_benchmark140_gpt54_runs.jsonl').name}]({link_from_official(EVAL_DIR / 'official_benchmark140_gpt54_runs.jsonl')})",
            f"- Aggregate summary: [{(EVAL_DIR / 'official_benchmark140_gpt54_summary.md').name}]({link_from_official(EVAL_DIR / 'official_benchmark140_gpt54_summary.md')})",
            f"- Aggregate failures: [{(EVAL_DIR / 'official_benchmark140_gpt54_failures.jsonl').name}]({link_from_official(EVAL_DIR / 'official_benchmark140_gpt54_failures.jsonl')})",
            "",
        ]
    )
    (OFFICIAL_DIR / "aggregate_eval_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OFFICIAL_DIR.mkdir(parents=True, exist_ok=True)
    exported = scenario_rows()
    for scenario_name, rows in exported.items():
        write_jsonl(OFFICIAL_DIR / f"{scenario_name}_tasks.jsonl", rows)
    aggregate_rows, aggregate_summary = build_aggregate_full_outputs()
    manifest = build_manifest(exported)
    (OFFICIAL_DIR / "benchmark_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inventory_rows = []
    for scenario in manifest["scenarios"]:
        inventory_rows.append(scenario)
    write_jsonl(OFFICIAL_DIR / "scenario_inventory.jsonl", inventory_rows)
    (OFFICIAL_DIR / "official_benchmark140_trace_registry.json").write_text(
        json.dumps(build_trace_registry(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_readme(manifest)
    write_reproduction_guide(manifest)
    write_artifact_provenance(exported)
    write_aggregate_eval_summary(aggregate_summary)
    print(f"Built {VERSION} at {OFFICIAL_DIR}")
    print(f"Aggregate official baseline rows: {len(aggregate_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
