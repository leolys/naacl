# 前瞻性 B0/B2/B3 简单核查准备

授权后实际执行：[停止报告](authorized_pilot_20260907_v1/PILOT_REPORT.md)、[网关路由问题单](authorized_pilot_20260907_v1/GATEWAY_ROUTE_ISSUE.md)。用户已批准本轮资源与 $50 上限。GPU0 的 Qwen 已成功启动并在结束后清理；第一条 API 控制返回 `model=Sol` 但 `usage.model_name=Luna`，因此按协议全停。1 次 API 生成、4 次浏览器 transition、0 次 Qwen 生成、0 个正式任务，未自动做 Qwen-only。

最新增量：[API 与调度准备报告](api_preparation_20260907_v2/PILOT_REPORT.md)、[新模型配置](api_preparation_20260907_v2/MODEL_CONFIG.json)、[执行命令](api_preparation_20260907_v2/COMMANDS.md)。

原准备交付完整保留：[准备阶段报告](preparation_20260907_v1/PILOT_REPORT.md)、[协议](preparation_20260907_v1/PILOT_PROTOCOL.md)、[任务 manifest](preparation_20260907_v1/TASK_MANIFEST.json)、[原模型配置缺项](preparation_20260907_v1/MODEL_CONFIG.json)、[原运行命令](preparation_20260907_v1/COMMANDS.md)。

准备阶段候选为 `gpt-5.6-sol`。旧准备文件保留当时的授权缺项，不代表当前仍缺许可；当前阻塞是上述实际路由不符。原六状态不补跑，新 8 例没有真实被测模型调用。

`panel.py` 已接入双模型串行调度、固定非图表控制、全局/分模型预算、B0/B2/B3 分支、终局离线评分与双成本汇总。默认只检查本地配置，不访问网络。`--execute` 需要本轮明确授权与配置；不自动启动模型、不单模型降级、不换任务。网关模型/费率元数据已读取，但真实请求身份检查失败，尚未完成多图或策略控制。禁止用旧 runner 的核验后确定性提交替代普通 actor 续跑。

工程测试使用 `python -m unittest research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel research.decision_evidence_audit.tests.test_core`。Mock 通过不是视觉能力或研究假设成立的证据。
