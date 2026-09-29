# Reproduction Guide

## Launch Shells

```bash
python web_agent_benchmark/public_benchmark/public_benchmark_shell_app.py --host 127.0.0.1 --port 8026
python web_agent_benchmark/business_shell/business_shell_app.py --port 8016
python web_agent_benchmark/environment_energy_shell/environment_shell_app.py --host 127.0.0.1 --port 8033
python web_agent_benchmark/health_shell/health_shell_app.py --host 127.0.0.1 --port 8037
```

Reviewer routes stay under `/review/...` where supported; formal agent evaluation uses only `/task/...` routes.

## Scenario Runners

```bash
python web_agent_benchmark/evaluation/run_public39.py --mode llm_agent --tasks pub001-pub039
python web_agent_benchmark/evaluation/run_business47.py --mode llm_agent --tasks b001-b047
python web_agent_benchmark/evaluation/run_environment35.py --mode llm_agent --tasks env001-env035
python web_agent_benchmark/evaluation/run_health19.py --mode llm_agent --tasks health001-health019
```

## Full Benchmark Runner

Dry run:

```bash
python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode llm_agent --profile dryrun
```

Full 140-task run:

```bash
python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode llm_agent --profile full
```

Mock smoke checks:

```bash
python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode mock_correct --profile dryrun
python web_agent_benchmark/evaluation/run_official_benchmark140.py --mode mock_misleading --profile dryrun
```

The full-benchmark runner writes mode-specific outputs into `web_agent_benchmark/evaluation/`. For GPT-5.4 runs the canonical outputs are:

- `official_benchmark140_gpt54_runs.jsonl`
- `official_benchmark140_gpt54_summary.md`
- `official_benchmark140_gpt54_failures.jsonl`

Qwen3-VL 8B / 32B full benchmark runs use a local Qwen server in the dedicated conda environment:

```bash
python web_agent_benchmark/evaluation/run_official_benchmark140.py \
  --mode llm_agent --profile full \
  --agent-backend qwen3_vl_http --qwen-model-size 8b \
  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/qwen3_vl_8b_full140

python web_agent_benchmark/evaluation/run_official_benchmark140.py \
  --mode llm_agent --profile full \
  --agent-backend qwen3_vl_http --qwen-model-size 32b \
  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/qwen3_vl_32b_full140
```

These commands auto-start `web_agent_benchmark/evaluation/qwen3_vl_server.py` with `/mnt/data/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python` and `CUDA_VISIBLE_DEVICES=4,5,6`.

Llama-3.2 Vision 11B / 90B full benchmark runs use the same local HTTP serving pattern in the InternVL conda environment:

```bash
python web_agent_benchmark/evaluation/run_official_benchmark140.py \
  --mode llm_agent --profile full \
  --agent-backend llama32_vision_http --llama32-model-size 11b \
  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_11b_full140

python web_agent_benchmark/evaluation/run_official_benchmark140.py \
  --mode llm_agent --profile full \
  --agent-backend llama32_vision_http --llama32-model-size 90b \
  --llama32-cuda-visible-devices 4,5,6,7 \
  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun
```

The prompt-only timeout ablation keeps the same Llama-90B serving setup and changes only the LLM action prompt. It is recorded separately because it is not the main 90B score:

```bash
python web_agent_benchmark/evaluation/run_official_benchmark140.py \
  --mode llm_agent --profile full \
  --agent-backend llama32_vision_http --llama32-model-size 90b \
  --llama32-cuda-visible-devices 4,5,6,7 \
  --record-dir web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_90b_full140_prompt_only_rerun
```

These commands auto-start `web_agent_benchmark/evaluation/llama32_vision_server.py` with `/mnt/data/code_generation/liyisheng/8H100conda/envs/internvl/bin/python`; the 90B commands above explicitly use `CUDA_VISIBLE_DEVICES=4,5,6,7`.

## Trace Viewers

```bash
python web_agent_benchmark/evaluation/public39_trace_viewer_app.py --runs web_agent_benchmark/evaluation/public39_gpt54_runs.jsonl --port 8027
python web_agent_benchmark/evaluation/trace_viewer_app.py --runs web_agent_benchmark/evaluation/business47_llm_full_runs.jsonl --port 8017
python web_agent_benchmark/evaluation/environment35_trace_viewer_app.py --runs web_agent_benchmark/evaluation/environment35_gpt54_runs.jsonl --port 8034
python web_agent_benchmark/evaluation/health19_trace_viewer_app.py --runs web_agent_benchmark/evaluation/health19_gpt54_runs.jsonl --port 8038
```

## Navigation Revisit Analysis

```bash
python web_agent_benchmark/evaluation/analyze_navigation_revisits.py \
  --runs web_agent_benchmark/evaluation/public39_gpt54_runs.jsonl \
  --out web_agent_benchmark/evaluation/public39_navigation_revisit_metrics.jsonl \
  --summary-out web_agent_benchmark/evaluation/public39_navigation_revisit_summary.md \
  --report-title 'Public 39 Navigation Revisit Metrics'
```

Use the same pattern for the other three scenarios by swapping in the corresponding runs, rerun, metrics, and summary paths recorded in `benchmark_manifest.json`.
