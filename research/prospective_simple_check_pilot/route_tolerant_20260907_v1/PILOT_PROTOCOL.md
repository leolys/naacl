# 本段协议索引

研究与任务协议沿用 [准备版 PILOT_PROTOCOL.md](../preparation_20260907_v1/PILOT_PROTOCOL.md) 和根目录 [执行单](../../../Codex_Prospective_Simple_Check_API_Pilot.md)。真实执行配置依次为本目录 MODEL_CONFIG.json、MODEL_CONFIG_scheduler_fix.json；不能用准备版“未授权”配置描述当前已执行请求。

本段明确修订只有两类：

1. [PROTOCOL_AMENDMENT.md](PROTOCOL_AMENDMENT.md)：用户豁免身份不匹配的停止条件；请求仍为 Sol，返回 model / route / usage 保留，权重未验证。预算不变。
2. [SCHEDULER_FIX.md](SCHEDULER_FIX.md)：正式任务前调度字段合并错误的通用修复；显式承接已通过控制和预算。任务、actor/verifier 提示、选择与提交语义、图像尺度和解码不变。GPU0 使用同一 25% 本进程 allocator cap。

原样提交、独立全图核验、通用主动核验三个策略的身份不变。实际来源对照见 [SOURCE_CHANGES.patch](SOURCE_CHANGES.patch)。新运行源快照归属于 live_panel_02；live_panel_01 及更早结果保持原身份和停止状态。

HTTP 429 已使面板停止；本索引不是再次运行授权或重试机制。
