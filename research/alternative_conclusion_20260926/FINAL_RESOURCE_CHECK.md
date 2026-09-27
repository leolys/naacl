# 结束时资源只读检查

2026-09-26，本轮真实实验结束后，通过原 SSH 别名执行 `ps`、`nvidia-smi`、`GET /health` 和 `GET /v1/models`。没有新增模型推理。

- 健康接口：HTTP 200。
- 模型列表：`Qwen3.8-27B`，root `/mnt/data/datasets/open_source_models/Qwen3.8-27B`，max_model_len 16384，owned_by vllm。
- API 进程 316818，启动时间 Sep 26 10:59:49，与启动前核对身份相同。
- EngineCore 319282，启动时间 Sep 26 11:00:46，与启动前核对身份相同。
- GPU 0–6 guard 282313，启动时间 Sep 26 10:48:06，与启动前核对身份相同。
- GPU7 UUID `GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7`，显存已用 72,211 MiB，空闲 8,784 MiB，检查时利用率 0%。这些只是即时读数，不代表预约或释放资源。
- GPU0–6 各已用 41,643 MiB，空闲 39,352 MiB；没有停止、重启或修改占卡进程。

API 原进程参数仍为用户提供的 BF16、单卡、16,384 上下文、max_num_seqs=1、image=1、max_pixels=1,605,632、eager、gdn_prefill_backend=triton。

原始启动前回执保存在 `preflight_001/receipt.json`；本文件记录结束时工具回执的人工整理，不是持续监控证明。
