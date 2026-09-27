# 对抗实验审查

日期：2026-09-08。审查者：新子Agent `/root/intranet_continuation_audit`，请求模型gpt-5.6-sol、ultra；same-family，provisional。

最终判定：**WARN**。不是跨模型接受，也不是研究假设成立。下文原样保留审查意见；引用行号对应审查当时版本，执行工件不变，展示文档随后有明确文字修订。

落实情况（执行者记录，不覆盖审查者判定）：主报告已补16个spec的4正式/6legacy/6draft资格，以及6个checkpoint mismatch的1正式/2legacy/3draft分层；保留原评分；说明日期顺序、业务动作语义、crop不能归因；区分成功率和相对B0百分比分母；COMMANDS与REPORT_GENERATION.json记录离线reporter命令、实际源码路径与时间。未为追求PASS重新跑实验或重新请求审查。

实现审查另外指出：同一prefix多次跨段中断不受充分支持，mock仅组件级，通用retry比较允许调整，工作区后续变动不能由首次payload相等保证；HTTP非200完整响应体未保存，实际权重未验证。当前单位13此前逻辑调用数为0；实际新旧retry配置相同，8个核心源码副本逐字节一致。这些局限未被本次成功接续自动消除。完整实现审查在原始trace的001-implementation.response.md。

原始trace：`.aris/traces/experiment-audit/2026-09-08_internal_continuation_v1/`。不新增hash或大型门禁。线上结果仅支持本地safe-shell主决策与实际POST/确认链。

## 最终审查原文

总体结论：**WARN（same-family / provisional）**。数值、提交和调用账本可重算；但 16 个 task spec 并非同一等级的 `real_gt`，且若把全部 dataset-score mismatch 都称为“可见证据下的错误”，会超过证据。

### A — WARN：GT 来源与在线隔离

- executed panel 只把公开 task/image 送入在线流程，dataset spec 在在线调度结束后才加载并评分：`live_panel_04/executed_sources/.../panel.py:170-183,298-347`。未见 scorer 驱动在线分支。
- 但 16 个 spec 中只有 4 个标为 `formal_scored_task`，6 个为 `legacy_unspecified`，另 6 个（health001/env035/health005，各两臂）明确为 `image_only_draft_requires_review`：`live_panel_04/TASK_MANIFEST.json:153-160,222-229,291-298`。env035 原 spec 更直写 GT 是 “GPT-5.4 vision” 草稿、须确认：`web_agent_benchmark/benchmark_v2_open/splits/official140/environment35_tasks.jsonl:35`（clean 同文件族 `:35`）。
- scorer 不读取这些资格字段；只要 action id 等于 `expected_action_id` 就记 `success`：`safe_shell.py:233-253`。因此主报告的“6 个错误 checkpoint”应理解为 **dataset expected-action mismatch**，不是 6 个均经独立确认的真实 GT 错误。CASE_NOTES 已部分正确限定：`CASE_NOTES.md:3,46`。

### B — PASS：分母与归一化

- 独立重算 96 行后，checkpoint、score、group counts 均零不一致。恢复率为 `recovered / 同组自然错误 checkpoint`，不是除以模型自身最大值：`executed_sources/.../panel.py:363-380`。
- 表中括号百分比使用 `(方法正确数-B0正确数)/B0正确数`：`report_results.py:85-92`；无可疑自归一化。建议把 `PILOT_REPORT.md:15` 改清楚：原始成功率分母是每组 8 个启动 prefix，而括号百分比是相对 B0 变化，不是同一分母。

### C — PASS：结果、请求、回执与成本

- 只读交叉核对得到：32 prefixes、96 rows、每策略 32；progress 的所有执行字段与 CASE_TABLE 对应行一致；32 个实际 unit 目录每个恰有 3 条 receipt，共 96 条，且 96 个 timestamp 唯一，CASE_TABLE 内 receipt 与原 JSONL 完全一致。旧 36 行来自 12 个 `source_directory`，当前 60 行来自 20 个新 unit，没有旧 unit 重提。
- 所有关联 unit/prior-prefix 中有 265 对逻辑 request/response 文件，零缺对；263 成功、2 个旧中断失败记录。物理账本为 285 次（API149/Qwen136）、691 live transitions：`live_panel_04/budget.json:2-5`。当前 API ledger 88 次：`api_spend.json:2-10`；与先前累计 61 次相加正好 149，且 reporter 只链接 prior cumulative 一次：`resumed_pilot_20260907_v1/CUMULATIVE_COSTS.json:11-15,40-41`、`report_results.py:29-30,62-70`。
- 报告的 87 completed + 1 transport failure、60 新提交、96 确认提交、总 transition 982 均匹配：`CUMULATIVE_COSTS.json:9-28`。未发现 phantom result 或重复累计。

### D — WARN：执行代码与 reporter 证据

- 实际命令被记录：`COMMANDS.md:38-45`；运行时保存 Python/protocol/concurrency 和源码副本，但 `git_head=null`：`live_panel_04/runtime.json:2-7`。
- executed `offline_report` 确实调用 `safe_shell.score_receipt` 并写 CASE_TABLE/SUMMARY：`executed_sources/.../panel.py:334-400`。我用 16 个原 spec、progress receipts 和同一 scoring rule独立重算，96/96 行零差异。
- `report_results.py` 只读 evaluator/ledger 后生成展示：`:23-73,101-122`，不重新调用 scorer。其执行命令、生成时间和 reporter source identity 未记录；因此展示层来源为可重算但非完整执行证明。建议在 `COMMANDS.md` 补记实际离线 reporter 命令/时间，无需新增大门禁。

### E — WARN：范围、伤害、恢复、身份与观察

- 范围限定正确：仅 8 个开发任务、单面板、无多 seed、非官方 GUI benchmark：`PILOT_REPORT.md:3,85-86`。
- B2 恢复 1 个错误状态但改坏 4 个原本正确状态；B3 恢复同一个 pub013 状态且改坏 0 个。因此“两种方法各恢复一次”其实是同一自然 checkpoint，不能算两个独立恢复样本：`CASE_NOTES.md:62-69`。
- 并非所有 20 个 dataset-score failures 都是“无可见依据”的决定。health005 图面左到右确实从约 1.24M 降到 0.41M，但日期由 Nov 倒排到 Jun；错误理由有可见支持，只是没有按日历正序解释：`CASE_NOTES.md:25-38`。b014 的模型正确读出 `<25,000`，但“普通 review / critical escalation”没有额外公开量化阈值，属于动作语义映射，不是纯视觉错误：`:48-54`。
- 唯一 B3 crop 只覆盖东北部，不含 Illinois、Kansas 或完整图例；它不能被归因为恢复原因，全图 B2 已成功：`:19-23`。
- API 请求名为 Sol，但当前成功响应路由是 mirror-Luna/Luna，身份不匹配且仅 record-only：`PILOT_REPORT.md:10-11`、`api_spend.json:21-23,3154-3163`。报告对此限定正确。

### F — WARN：评估类型

- 交互环境是 **simulation_only safe-shell**（本地 task/form/POST/confirmation），不是原网站。
- 离线评分应分层表述：4 个 formal specs 可称 `real_gt`；6 个 legacy specs 是 dataset-label evaluation；6 个 image-only drafts 是显式 provisional/draft GT，而非已确认 `real_gt`。mock/control 仅为工程验证，不属于研究结果；`COMMANDS.md:14-20` 已正确说明。

建议的报告修正：

1. 将 `PILOT_REPORT` 中泛称“正确/错误”改为“按 dataset expected action 匹配/不匹配”，并列出 formal 4、legacy 6、image-only draft 6。
2. 将 env035 的“原数据集正确为1980”改为“原 draft expected action 为1980”。
3. 在主报告直接加入 `CASE_NOTES.md:38,54` 的关键限定：并非全部 score errors 都是可见证据完全不支持的决定。
4. 澄清成功率与相对 B0 百分比的不同分母，并补记离线 reporter 命令/时间。
