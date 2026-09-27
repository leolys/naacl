# Llama-3.2-Vision-90B Full-140 Evaluation Record

This directory contains one official benchmark_v1 evaluation run.

This is a **prompt-only timeout ablation** for Llama-3.2 Vision 90B. It changes only the LLM action prompt used by the four scenario runners. It does not add runner guardrails, auto-submit behavior, shell changes, task changes, hidden scoring changes, or action-schema changes. The clean 4-GPU Llama-90B benchmark score remains `evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun/`.

Result summary: this ablation did not improve the timeout problem. The full run produced `0` successes, `130` timeouts, and `10` agent errors, so it is retained as a negative execution-prompt ablation rather than the main model score.

- Mode: `llm_agent`
- Profile: `full`
- Scenarios: `public39, business47, environment35, health19`
- Task overrides: `{}`
- Agent backend: `llama32_vision_http`
- Model metadata: `{'agent_backend': 'llama32_vision_http', 'agent_model_family': 'llama3_2_vision', 'agent_model_size': '90b', 'agent_model_name': 'Llama-3.2-Vision-90B', 'model_path': '/hipilot/sharestorage/datasets/open_source_models/Llama-3.2-90B-Vision', 'llama32_server_url': 'http://127.0.0.1:8048', 'generation_config': {'do_sample': False}}`
- Decoding config: `{}`
- Runs: `runs.jsonl`
- Summary: `summary.md`
- Failures: `failures.jsonl`
