# 审查意见处置（主执行者说明，不替代审查原文）

审查：GPT-5.6-Sol ultra，fresh、同系列、provisional。最终总体 WARN，A/B/F PASS，C/D/E WARN。原文和行号保存在 EXPERIMENT_AUDIT.md，未删减或改写其结论。

已在真实运行前落实：相对执行目录的源文件检查；必要执行代码覆盖；同一 task/condition 的四策略共享 prefix 一致性；mock 不显示纠错判定。修复后 49 项单测中 46 通过、3 个 opt-in 跳过，另有单独浏览器控制通过；最终 mock/live 使用 execution_source_v3。

最终审查后采取的有限处置：

- 用 RUN_STATUS_INDEX.json 标出最初两次工程尝试与旧 mock 视图的历史失败/被替代状态，不修改或删除旧工件。
- 将实际离线 reporter 单独拷贝到 reporting_source/research/decision_evidence_audit/case_report.py，版本标记为 clear-rule-case-view-with-failed-prefixes-1。在线执行源仍是 v3，不把展示代码追认为实验开始时源码。
- 02:37 UTC 用 cmp 对比当前 reporter 读取的 6 份 task spec 与 live run 保存的对应 spec，全部逐字节相同。此检查支持本次展示答案与运行数据相同，但不保证未来任意工作树的 reporter 都自动使用正确版本。未新增 hash 或冻结协议。
- 单文件真实 HTML 共 12 张嵌入图片、1,408,655 字节，无外部依赖；6 个条件、3 个 checkpoint、0 个错误 checkpoint、12 提交/12 未运行分支与 raw 工件一致。它是后生成的可读视图，权威结果仍是 run 内原始请求/响应、prefix、回执和 evaluator。
- 对 env008 采用审查意见中的保守解释：它保留为证据冲突个案，不能自动成为“完全没有可见支持”的错误样本。不修改原公开任务成“相信标签”，避免在本轮改变研究问题。

未在本轮继续实施的通用硬化：短字符串/数字泄漏扫描、snapshot 路径集合完整等价检查、所有 unit_error 分支的统一字段及深度交叉核对、B4 最小提取 schema、generic CLI 与特定协议参数的绑定、真实 revision+POST 的自然机会。这些保留为下一轮工程/设计待办，不把本次已通过的检查夸大成全面安全证明。新增 schema 或强制参数不应悄悄改变已测策略。

关于部分未采纳的强制门禁建议：当前通用 profile 允许子集诊断，valid 是普通工程验证而不是本轮固定矩阵认证；本轮实际命令/工件已逐项核对三题两条件、seed=12345 和解码参数。遵守项目约定，不为未来所有开发运行额外锁死参数，不因 missing checkpoint 丢弃该次真实尝试。

服务关闭由主执行者只读检查确认：本轮自己的 TTY Ctrl-C 退出；02:27 UTC 附近 8045 无监听，原共享 PID 56053 仍在，不声称审查者独立验证了此可变状态。真实推理与全部 CPU 浏览器工作已经结束，不继续扩样或重抽错误。
