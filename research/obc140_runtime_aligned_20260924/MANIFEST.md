# 本轮产物索引

本目录是原网页业务输入对齐后的独立新版本，不覆盖旧版解释。所有 140 条均已处理；无效、失败、未运行阶段按实际状态保留。逐文件字节数与 SHA256 见打包时生成的 `PACKAGE_INDEX.json`，ZIP 完整性见 `PACKAGE_CHECK.json`。

| 产物 | 用途 |
|---|---|
| OBC140_TERRA_ZH_REVIEW.html | 最终离线单文件：任务、图表、OBC／竞争解释、核验、中文、人工备注 |
| RUNTIME_INPUTS_140_ZH.html | 独立输入展示：实际任务公开字段与旧版差异，不含模型结论 |
| README_ZH.md | 阅读方式、信息边界、不能据此主张的结论 |
| REPORT.md / RESULTS.json | 140 条真实状态、416 次尝试、估算费用、阶段失败及工程检查 |
| PLAN.md / PROTOCOL.md / config.json | 固定范围、授权预算、输入规则与运行配置 |
| COMMANDS.md | 不含密钥的实际执行和归档入口 |
| INPUT_CORRECTION_EXAMPLES.md | b001、b002、pub003 的公开输入修复实例 |
| prepared/ | 140 条任务输入、原图、原网页来源、差异及不可变记录 |
| run/tasks/ | 每条任务各阶段完整请求、响应、尝试回执、解析／规范记录 |
| run/runtime.json / run/runtime_source/ | 实际运行源版本与源码快照 |
| run/budget.json / run/summary.json | 实际动态预算及进度记录，不使用初始化占位字段计数 |
| translations/ | 仅用于人工阅读的本地中文映射及原英文，0 次翻译 API |
| review_data_zh.json / view_provenance.json | 最终展示数据和来源哈希 |
| all_request_checks.json | 全量 416 请求输入、图像、冻结源码与配置一致性 |
| offline_tests_final_delivery.xml | 172 项本地测试，0 失败／错误 |
| browser_check.json / note_isolation_check.json | 140 条显示、无外部请求、新旧人工笔记隔离检查 |
| reviews/ / *.review.json | 独立上下文的同家族工程审查，暂定结论，不是人工语义确认 |
| PREVIEW_IN_PROGRESS.html / preview_* / review_data_preview.json | 保留的运行中展示快照及对应审查，不是最终结果 |
| *.py / tests/ | 本轮输入、运行、翻译、展示、检查及归档代码；推理版本以冻结快照为准 |

原图、gold 和旧模型输出未被改写。完整包适用于离线阅读与溯源；在另一台电脑发起在线重跑仍需配置依赖与新预算授权。
