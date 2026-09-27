# Artifact Provenance

This document maps the reviewed working artifacts in the repository to the canonical official benchmark exports.

## Canonical Exports

- `public39_tasks.jsonl`: exported from `public_benchmark_shell_app.load_public39_records()` with frozen public slugs, source-group metadata, and task payloads.
- `business47_tasks.jsonl`: exported from `business_shell_app.build_registry(load_business_tasks(DEFAULT_TASKS))` with frozen `b001-b047` slugs.
- `environment35_tasks.jsonl`: exported from the approved environment shell task set loaded by `environment_shell_app.load_records(DEFAULT_TASKS)`.
- `health19_tasks.jsonl`: exported from the approved health shell task set loaded by `health_shell_app.load_records(DEFAULT_TASKS)`.

## Execution Surfaces

- Public 39 shell: `web_agent_benchmark/public_benchmark/public_benchmark_shell_app.py`
- Business 47 shell: `web_agent_benchmark/business_shell/business_shell_app.py`
- Environment 35 shell: `web_agent_benchmark/environment_energy_shell/environment_shell_app.py`
- Health 19 shell: `web_agent_benchmark/health_shell/health_shell_app.py`

## Official Baseline Results

- Public 39: `web_agent_benchmark/evaluation/public39_gpt54_runs.jsonl`
- Business 47: `web_agent_benchmark/evaluation/business47_llm_full_runs.jsonl`
- Environment 35: `web_agent_benchmark/evaluation/environment35_gpt54_runs.jsonl`
- Health 19: `web_agent_benchmark/evaluation/health19_gpt54_runs.jsonl`
- Full 140 aggregate baseline: `web_agent_benchmark/evaluation/official_benchmark140_gpt54_runs.jsonl`

## Supporting vs Historical Assets

- `supporting`: scenario runners, trace viewers, review annotations, shell build summaries, navigation revisit analysis
- `historical / intermediate`: expansion/gallery directories, OCR classification caches, manual variant workspaces, raw review logs, old shell logs, old port logs

No files are deleted in this release pass. The goal is to make the official benchmark obvious while preserving provenance needed for later paper and ablation work.
