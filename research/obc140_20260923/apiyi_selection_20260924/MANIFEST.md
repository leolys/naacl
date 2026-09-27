# 两任务 × 三模型选型工件索引

截至本轮结束：17 次 API 请求尝试、3 个四阶段完整组合；原始基础任务仅 b001 与 pub013 两个。140 批量未授权、未运行。

| 类别 | 位置 | 内容 |
| --- | --- | --- |
| 阅读入口 | SELECTION_REPORT_20260924.md / .html | 结果、具体差异、费用和停止边界 |
| 可携带阅读包 | APIYI_SMALL_SAMPLE_REVIEW.zip、PACKAGE_READ_ME.md、PACKAGE_INVENTORY.json | 报告、三份内嵌原图阅览页、中英JSON和费用依据；非独立推理环境 |
| 固定设计 | PLAN.md | 两任务三模型、24 次上限、原提示、无重试 |
| 配置和执行 | run_selection.py、runs/每模型/config_snapshot.json | 新 APIYI 入口，旧代码不变 |
| 英文及中文结果 | runs/每模型/tasks/b001 或 pub013/record.json | 全部成功、invalid、failed、not_run 状态 |
| 完整线上证据 | 上述任务目录内 proposal、generation、verification、translation | 每次 request、response、attempt、context 和解析内容；未执行阶段无伪造文件 |
| 冻结代码身份 | runs/每模型/runtime_source/、runtime.json | 实际请求时的源快照，旧结果没有追写身份 |
| 预算 | runs/每模型/budget.json | 8 / 7 / 2 次实际尝试，业务浏览器操作为 0 |
| 每模型阅览 | views/每模型.json、.html | 仅两任务，JSON 来源哈希，HTML 原图内嵌；失败也保留 |
| 导出工具 | export_pilot_views.py | 不修改原 run 导出，筛选两条形成派生阅览数据 |
| 语义复核 | SEMANTIC_REVIEW.md | 子 Agent 逐图检查 O/B/C、竞争解释、核验及中文，不是用户人工标签 |
| 费用 | cost_summary.json、analyze_usage.py、COST_METHOD.md | 请求／任务／阶段用量、两估算情景和未知费用 |
| 价格证据 | PRICE_SOURCES.md、provider_rates.json、CACHE_BILLING_NOTE.md | 网关标价及缓存写入信息缺口 |
| 测试 | test_selection.py、test_usage.py、tests_pipeline.xml、tests_usage.xml | 32 项管线及固定入口回归、18 项用量测试 |
| 界面验证 | browser_check_pilot.py、browser_qa/ | 三页实际 Edge 检查与截图，不是 Agent 任务执行 |
| 代码审查 | PREDEPLOY_REVIEW.md | 首例门禁及小面板预算审查，同家族暂定审查 |
| 审查追踪 | ../../../.aris/traces/experiment-bridge/2026-09-24_apiyi_selection/ | 独立运行前审查请求、完整答复和身份 |
| 命令 | REPRO_COMMANDS.md | 无凭据的执行与复核说明 |

各模型 run 的原导出含 140 个预备任务槽位，仅用于来源一致性。人类阅读页已另行筛成两任务，不能把槽位数量计入模型评测。

历史 `../runs/obc140_v4_20260923` 与 `../OBC140_REVIEW.html` 保持原状；它们是旧网关额度阻塞记录，不是本轮 APIYI 成功结果。
