# 本批工件索引

生成范围：固定140个原任务，静态O/B/C解释和竞争解释；本轮API额度阻塞，0条新生成。主记录为 `runs/obc140_v4_20260923/summary.json`，不以目录数量计算完成数。

| 类别 | 路径 | 用途 |
|---|---|---|
| 阅览 | OBC140_REVIEW.html | 全140原图、公开任务、阶段状态、解释/核验/中文/笔记展示；当前待生成 |
| 分享 | OBC140_VIEWER.zip、PACKAGE_READ_ME.md、PACKAGE_INVENTORY.json | 仅离线展示和状态文档，无账户错误响应或原始gold文件 |
| 状态 | STATUS_20260923.md、STATUS_20260923.html | 1次真实请求被额度拒绝；未完成部分和结论边界 |
| 使用 | READ_ME.md、COMMANDS_20260923.md | 操作与执行命令，恢复服务后续跑方法 |
| 固定协议 | PROTOCOL_20260923.md、config.json | 静态四阶段、模型和尝试上限、信息隔离 |
| 数据 | catalog.json、preparation_audit.json、data/task_001…task_140 | 140原图、公开输入与独立离线元数据，原图哈希核验 |
| 数据代码 | prepare_catalog.py、tests_catalog.py | 复用公开投影，缺失select选项不推造，原数据不覆盖 |
| 执行代码 | panel_core.py、run_panel.py、tests_panel.py | 串行API、完整请求/响应、预算、断点、未知结果不重发 |
| 展示代码 | render_viewer.py、viewer_template.html、tests_viewer.py | 中英稳定键对照、规则按编号关联、转义、无CDN |
| 打包与QA | package_viewer.py、browser_check.py、browser_qa/ | 离线分享包、真实Edge展示验收；不是被测轨迹 |
| 实际运行 | runs/obc140_v4_20260923/ | 唯一真实调用、140阶段槽位、全局停止和规范JSON |
| 冻结身份 | runs/obc140_v4_20260923/runtime_source/、runtime.json、config_snapshot.json | 真实请求时的代码与配置快照，后续修改不得追写旧身份 |
| 测试 | tests_final.xml | 28项离线检查通过，不是模型质量证据 |
| 代码审查 | PREDEPLOY_REVIEW.md | 对抗审查与超时修复；同家族暂定审查 |
| 展示审查 | OBC140_REVIEW.html.review.json | 与规范JSON的保真/安全审查，不判断研究结论 |
| 完整审查追踪 | ../../.aris/traces/experiment-bridge/2026-09-23_obc140/、../../.aris/traces/render-html/2026-09-23_obc140/ | 原始请求、审查响应与来源信息 |

代码复用的已有文件：相邻 `../competing_rules_20260923/{engine.py,format_replay.py,adapter.py,prompts_observation_v4.py}`。原数据来源：`../../.aris/dataset_inventory_20260918`。这些源文件没有修改。

## 2026-09-24：另存 APIYI 两任务选型，不覆盖以上历史

新增 `apiyi_selection_20260924/`，固定 b001/pub013 × Sol/Terra/Mini；实际 17 次尝试、3 个四阶段完整组合，140 批量没有开始。报告、费用估算、原始失败及每模型两任务中英离线视图见其 `SELECTION_REPORT_20260924.md` 和 `MANIFEST.md`。本段为新活动索引，不改写旧 run、旧 score 或旧冻结版本身份。

## 2026-09-24：另存 Terra 引用兼容验证

新增 `terra_citation_check_20260924/`：先离线重放四份旧核验，再对 b001/pub013 各做新鲜四阶段，共 8 次请求、两例完整。公开任务引用与图像证据分离已生效；b001 几何副链的观察否定依据不足，作为语义问题保留。报告为 `VALIDATION_REPORT_20260924.md`，中英原图阅览为 `TERRA_CITATION_REVIEW.html`。旧失败不改写，140 全量仍未开始。

## 2026-09-24：固定 140 条 Terra 解释材料与原生中文交付

另存 `terra140_native_zh_20260924/`，不覆盖上述历史。固定 140 条均已处理，b001/pub013 两条英文三阶段按来源复用，其余 138 条产生 409 次新请求；没有 APIYI 翻译请求、GPU 或网页业务操作。

- 最终离线单文件：`terra140_native_zh_20260924/OBC140_TERRA_ZH_REVIEW.html`。
- 报告与使用：同目录 `REPORT.md`、`READ_ME.md`、`RUN_COMMANDS.md`。
- 完整工件包：`OBC140_TERRA_NATIVE_ZH_20260924.zip`（原图、公开输入、配置、源快照、请求／响应、失败和原生中文）。
- 140 条均有可阅览原始解释；135 条生成通过结构校验，99 条核验通过接口；41 条失败终态保留，不按视觉理解错误统一计分。规范化后 82 条具有不同选项候选。
- 140 条现有文本的中文映射齐全，共 4,750 个去重字符串；无缺失键、无数字警告。翻译未改写规范英文记录。
- 新请求估算账本为 11.569135 美元，不是实际账单；0 次重试。用量别名的零值／非零值差异及解析口径保留在 `cost_summary.json`。
- 最新离线回归 56 项通过；140 条离线浏览器与工件新鲜度检查通过；语义审查仅覆盖固定八例（另继承 b001 疑点、记录 b011 接口归因），不认证全部 140 条正确。

这是一批静态 O／B／C 解释与核验材料，不是 GUI 多步任务成功率或防御有效率实验。规范结果、原始草稿、核验失败、规则状态和独立审阅意见分开展示。
