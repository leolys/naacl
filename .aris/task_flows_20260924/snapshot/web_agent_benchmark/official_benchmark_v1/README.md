# official_benchmark_v1

This directory is the canonical release surface for the current reviewed misleading-visualization agent benchmark.

- Benchmark version: `official_benchmark_v1`
- Total official tasks: `140`
- Official scenarios: `public39`, `business47`, `environment35`, `health19`

## Canonical Task Files

- `public39`: [public39_tasks.jsonl](public39_tasks.jsonl) (39 tasks)
- `business47`: [business47_tasks.jsonl](business47_tasks.jsonl) (47 tasks)
- `environment35`: [environment35_tasks.jsonl](environment35_tasks.jsonl) (35 tasks)
- `health19`: [health19_tasks.jsonl](health19_tasks.jsonl) (19 tasks)

## Official Evaluation Baselines

- Full 140-task GPT-5.4 aggregate runs: [official_benchmark140_gpt54_runs.jsonl](../evaluation/official_benchmark140_gpt54_runs.jsonl)
- Full 140-task GPT-5.4 aggregate summary: [official_benchmark140_gpt54_summary.md](../evaluation/official_benchmark140_gpt54_summary.md)
- Deterministic GPT-5.4 full-140 record: [gpt54_temp0_top_p1_seed12345_full140](evaluation_records/gpt54_temp0_top_p1_seed12345_full140)
- Qwen3-VL 8B full-140 record: [qwen3_vl_8b_full140](evaluation_records/qwen3_vl_8b_full140)
- Qwen3-VL 32B full-140 record: [qwen3_vl_32b_full140](evaluation_records/qwen3_vl_32b_full140)
- Llama-3.2 Vision 11B full-140 record: [llama3_2_vision_11b_full140](evaluation_records/llama3_2_vision_11b_full140)
- Llama-3.2 Vision 90B clean 4-GPU full-140 rerun: [llama3_2_vision_90b_full140_4gpu_rerun](evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun)
- Llama-3.2 Vision 90B prompt-only timeout ablation: [llama3_2_vision_90b_full140_prompt_only_rerun](evaluation_records/llama3_2_vision_90b_full140_prompt_only_rerun)
- Llama-3.2 Vision 90B historical 3-GPU OOM record: [llama3_2_vision_90b_full140](evaluation_records/llama3_2_vision_90b_full140)
- Qwen3-VL timeout post-hoc summary: [qwen3_vl_timeout_posthoc_summary.md](evaluation_records/qwen3_vl_timeout_posthoc_summary.md)
- Qwen3-VL selected-state fix test summary: [qwen3_vl_selected_state_fix_test_summary.md](evaluation_records/qwen3_vl_selected_state_fix_test_summary.md)
- Paper-facing experiment results draft: [paper_experiment_results.md](paper_experiment_results.md)

Per-scenario official baseline result files are recorded in `benchmark_manifest.json` and `scenario_inventory.jsonl`.

## Asset Classes

- `official`: canonical task files, this manifest layer, shell entrypoints, official baseline evaluation outputs
- `supporting`: scenario runners, trace viewers, navigation-revisit analysis, review annotations needed to explain provenance
- `historical / intermediate`: gallery pools, OCR caches, manual rewrite workspaces, scratch summaries, review logs, old port logs

## What To Use In A Fresh Conversation

Start from this directory when you need a stable handoff for experiments, paper writing, or rerunning GPT-5.4 baselines. The shell apps remain the formal execution surfaces; the task JSONL files here are the frozen canonical exports for analysis, citation, and future automation.
