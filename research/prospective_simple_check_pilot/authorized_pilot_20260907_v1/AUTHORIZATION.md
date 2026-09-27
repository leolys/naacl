# 本轮授权，2026-09-07

用户在收到“API 最多 50 美元、共享 GPU0、两模型各最多 400 次调用、共 4000 次浏览器 transition、并发 1”的确认请求后回答“好的授权”，随后再次要求“继续”。本记录仅适用于当前预选 8 个任务 × 两条件 × 两模型 × B0/B2/B3 面板，包含固定接口控制、失败与重试，不是后续轮次的长期许可。

沿用 gpt-5.6-sol 候选、medium reasoning、8192 max_completion_tokens、high image detail，以及已有 BF16 Qwen3-VL-8B-Instruct / max_pixels 1003520 / greedy 1024 输出。两模型独立自然前缀；并发 1，不自动强制提交、换任务、模型降级、增添付费提供方或下载模型。

旧准备文件保留其当时“未授权”身份，不覆盖。该目录从授权后的资源和接口核对开始记录，真实正式面板状态以另存进度文件为准。金额已批准，但网关实际费用依据及模型路由仍须核对，不把本文件误读为已经执行推理或已经证实模型身份。

首次资源检查：沙箱内 NVIDIA/网络查询失败；经明确只读权限审核，在真实主机查询成功，GPU0 为 NVIDIA H100 80GB HBM3，总 81559 MiB，使用 3 MiB，利用率 0%，无 compute-app PID。8045 未监听，18891 在本机监听。未启动 GPU 模型，未停止其他作业。

run-experiment 技能的小型 fresh-agent CUDA witness 已通过：8×8、finite=True、GPU0 H100、torch 2.8.0+cu128，transformers 4.57.1、qwen-vl-utils 0.0.14。仅 CUDA 算子、0 模型调用；不能称模型推理控制已通过。沿用既有环境，不新增环境 contract/hash 或 rebuild。
