# Qwen3-VL-8B-Instruct Full-140 Evaluation Record

This directory contains one official benchmark_v1 evaluation run.

- Mode: `llm_agent`
- Profile: `dryrun`
- Scenarios: `public39, business47, environment35, health19`
- Task overrides: `{'public39': 'pub021,pub030,pub034,pub035,pub036,pub037,pub039', 'business47': 'b001,b002,b003,b024,b047', 'environment35': 'env001', 'health19': 'health010'}`
- Agent backend: `qwen3_vl_http`
- Model metadata: `{'agent_backend': 'qwen3_vl_http', 'agent_model_family': 'qwen3_vl', 'agent_model_size': '8b', 'agent_model_name': 'Qwen3-VL-8B-Instruct', 'model_path': '/hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct', 'qwen_server_url': 'http://127.0.0.1:8045', 'generation_config': {'do_sample': False}}`
- Decoding config: `{}`
- Runs: `runs.jsonl`
- Summary: `summary.md`
- Failures: `failures.jsonl`
