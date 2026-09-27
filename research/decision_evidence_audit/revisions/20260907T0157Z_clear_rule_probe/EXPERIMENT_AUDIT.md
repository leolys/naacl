# 独立对抗审查

审查者：GPT-5.6-Sol ultra，fresh agent /root/clear_rule_audit。review_independence=same-family；acceptance_status=provisional。以下为审查者最终原文；后续处置见 AUDIT_DISPOSITION.md。行号对应审查时版本。

审查结论：**PROVISIONAL WARN / 条件通过**。工程接入基本成立，但本轮不支持任何“纠错有效/无效”结论：真实模型仅形成 3 个提交前 checkpoint，且全部原本正确；另 3 条前缀耗尽预算未提交。因此自然错误 checkpoint 为 0，纠错轨迹为 0。

以下缩写：`REV=research/decision_evidence_audit/revisions/20260907T0157Z_clear_rule_probe`，`V3=$REV/execution_source_v3/research/decision_evidence_audit`，`LIVE=research/decision_evidence_audit/runs/clear_rule_live_20260907T0222Z`。

### A — PASS（本次工件；有防御深度改进项）

- Checkpoint 只由可见提交控件和 Agent 提议触发，不读取 gold：`V3/core.py:261-280,333-370`；前缀请求只含公开目标、当前页面状态和截图，hook 在动作执行前截获，且核对截获前回执数为 0：`V3/runner.py:620-747`。
- 在线投影有严格公开字段 allowlist，选项按公开标签排序去除“正确项在先”的顺序侧信道：`research/decision_evidence_audit/core.py:19-70,167-203`；浏览器状态也单独 allowlist：同文件 `212-251`。安全 shell 没有 scorer，POST 只返回公开回执和确认页；评分在离线函数中完成：`research/decision_evidence_audit/safe_shell.py:136-230,233-254`。
- 实际 live 验证扫描 61 个请求、65 个图像引用，在线 key、隐藏字符串、图像元数据命中均为 0：`LIVE/evaluator/validation.json:71-101`。
- 防御深度限制：隐藏值扫描只遍历字符串，并忽略长度小于 5 的值，不能证明数字或短值绝不会以无害 key 泄漏：`V3/validate_run.py:95-105,159-168`。当前调用图和工件中未见实际泄漏，因此不降为本 run 的 FAIL。

### B — PASS

- 评分按回执标签唯一映射至 action_id，再与数据集 expected/misleading action 比较，不采用模型自报答案或理由：`research/decision_evidence_audit/safe_shell.py:233-254`。
- Validator 重算终局类别，并交叉核对 checkpoint 原选择、policy changed/recommendation、revision 动作、实际提交选择、服务器回执和 B0 保持性：`V3/validate_run.py:338-377,622-650`。
- 实际统计自洽：24 个记录单元中 12 个 `no_before_submit_checkpoint`、12 个 success；3 个 checkpoint、12 组相同状态/截图恢复、12 条回执、12 个确认页、61 对请求/响应：`LIVE/evaluator/validation.json:6-32`。逐策略调用量也正确，B0=0、B2=3、B3=3、B4=6：同文件 `34-69`。
- `valid=true` 只表示结构/一致性验证，不能解释为 24 个提交完成；该次验证明确 `complete_submission_required=false`：同文件 `513-514`。

### C — WARN

- Live 执行本身绑定良好：固定配置为三题、两 arm、四策略、seed 12345、零重试，见 `LIVE/evaluator/run_start.json:2-60`；manifest 记录 33 个执行依赖和运行期来源未改变：`LIVE/run_manifest.json:133-138,412-416`；validator 也报告 33/33 快照无差异：`LIVE/evaluator/validation.json:93-101`。
- 但离线报告不是由执行快照中的 reporter 生成。运行快照记录的 `case_report.py` hash 在 `LIVE/evaluator/run_start.json:82-83`；最终 `CASE_SUMMARY` 只写当前工作树 reporter 路径而无 hash/version：`REV/live_case_view/CASE_SUMMARY.json:2-6`。当前 reporter 后来增加了失败前缀展示逻辑：`research/decision_evidence_audit/case_report.py:111-120`。这不改变 raw run 数值，但“执行来源完整”不能自动覆盖这个后生成视图。
- Reporter 的 `qualified` 仅检查 mode、保存的 validation、来源路径是否齐全、source unchanged、无 run error 和 witness；不检查固定 profile/三题/参数，也不检查 `complete_submission_required`：`research/decision_evidence_audit/case_report.py:65-72`。它还从当前任务文件而非运行快照重算 gold：同文件 `88-92`。
- Validator 逐条检查快照记录，却未要求快照路径集合与 fingerprint 路径集合完全相等：`V3/validate_run.py:824-854`。本次两边都恰为 33，不构成当前失败。
- `STAGE_REPORT.md` 的研究结论没有超出 raw artifact；其 24 条记录≠24 条执行、validator 非完整矩阵、无纠错机会等限定准确：`REV/STAGE_REPORT.md:7-21,78-86`。但服务已关闭/PID 状态属于可变外部状态：同文件 `86`，不在 immutable run manifest 中，本次只读审查未独立验证。

### D — WARN

- B0 回归通过：真实 live 的 B0 从原 checkpoint 保持选择、0 次额外模型调用、无 revision，执行原待提交动作并得到单条回执和确认页，例如 `LIVE/online/units/unit_0009/result.json:4-54`、`unit_0021/result.json:4-54`。合成浏览器正控制还比较了无 hook 直接继续与 B0 的动作/回执一致性：`V3/tests/test_browser_integration.py:181-228`。
- 同一 checkpoint 四分支映射由 validator 强制为每个 task-condition 恰好一个 prefix：`V3/validate_run.py:36-49,484-488`。真实工件中 12 个已执行分支均恢复状态和截图相同并实际 POST：`LIVE/evaluator/validation.json:9-19`。
- 真实模型没有一次 `changed=true` 或非空 `revision_action`；因此“修改选择后真实提交”的 live 路径未被本轮触发。B2/B3 改选和提交只在 synthetic mock 正控制中出现：`V3/tests/test_browser_integration.py:229-258`。而最终普通单测命令跳过了 3 个 browser tests：`REV/review_fix_unit_tests.log:1-3,53-56`；单独 browser 日志虽通过，但 traceback 路径指向旧 `execution_source` 而非 v3：`REV/browser_control.log:26,65-70`。
- 失效路径仍偏松：`unit_error` 结果缺少正常路径中的 revision、executed submission、selected-before-submit、confirmation 字段：`V3/runner.py:950-964`；validator 对非提交单元只检查无回执及有 exclusion，没有交叉验证其 policy/request/replay 一致性：`V3/validate_run.py:663-669`。
- B4 将第一次模型输出原样作为文本传入第二次决策，只验证最终选项，不验证提取 JSON 的结构或与实际可见内容一致：`V3/policies.py:350-407`。本次 live 的 B4 输出本身结构完整，例如 `LIVE/online/units/unit_0012/result.json:13-20`，但通用路径仍需硬化。

### E — WARN

- 范围和结论边界写得正确：仅三个已使用开发题、单 seed、非总体效果、非原网站完整流程：`REV/PROTOCOL.md:7-15`；不重抽错误、同 checkpoint 分支、无因果/总体推断：同文件 `24-30,40,48-50`。Live manifest 同样禁止 research-level interpretation，只允许个案检查：`LIVE/run_manifest.json:412-416`。
- 公平性存在一处实质歧义：env008 的 Wind 柱高最高，但打印标签为 Solar 41.2%、Wind 29.8%；公开规则只说“最大贡献”，未告诉模型冲突时应信柱高还是标签：`REV/SAMPLE_GUIDE.md:13-19`，原任务见 `web_agent_benchmark/benchmark_v2_open/splits/official140/environment35_tasks.jsonl:8`。因此未来若自然选择 Wind，不应自动当作无歧义认知错误；应改为公开说明“最大打印百分比”，或把该样本从明确错误分母排除。本轮模型选 Solar，故不影响现有 0-error 结论。
- 最终文字没有声称纠错失败。它准确说“出现过瞬时错误选项与反复切换”，但没有错误待提交 checkpoint，因此既不能说核查成功，也不能说失败：`REV/STAGE_REPORT.md:7-9,36-40,82-86`。`NEXT_ACTION.md:3-11` 也明确禁止按 gold 暂停、强制出错或换 seed，未超出工件证据。

### F — PASS

- 真实 run 明确为 `live-local`，模型路径、8B、temperature/top_p/seed、零重试和多图 witness 均有记录：`LIVE/run_manifest.json:8-85`；服务日志显示实际加载 Qwen3-VL-8B 至 CUDA device 0 并收到本地 HTTP 请求：`REV/qwen3_vl_server.log:1-10`。
- Mock 明确标记为 scripted backend、`research_result=false`、无真实模型链：`research/decision_evidence_audit/runs/clear_rule_mock_reviewed_20260907T0220Z/run_manifest.json:8-21`；修复后的 case view 不再给 mock 自然错误或纠错判定：`REV/reviewed_case_view/CASE_SUMMARY.json:5-17`。
- safe shell 是 `simulation_only` 的本地主决策/POST/确认链，不是原始完整网站；gold 是 benchmark-provided offline `real_gt`，不是在线可见信息或现实环境原生真值：`REV/PROTOCOL.md:15,30,34`。
- Live 也正确标为 `attempted_incomplete_chain_smoke`：`LIVE/run_manifest.json:87-108`。虽然代码中的 `real_model_chain_exercised` 仅按 mode 置位：`V3/runner.py:1387-1405`，本次有 61 个真实调用和 12 条真实链支撑，不导致当前误分类。

### 历史失败必须保留

- 首次 mock 只完成 8 条提交，随后因 `RuntimeSourceChanged` 保留其余 16 条失败，不能称完整通过：`research/decision_evidence_audit/runs/clear_rule_mock_20260907T0200Z/run_manifest.json:33-47`。
- 第二次 isolated mock 虽旧 validator 报 `valid=true`，但来源只有 12 个数据/图表文件、没有执行代码：`research/decision_evidence_audit/runs/clear_rule_mock_isolated_20260907T0206Z/evaluator/validation.json:80-88`。旧 `mock_case_view` 还显示“原本错误且未纠正 24”，虽同时标记非真实结果，仍易误用：`REV/mock_case_view/CASE_SUMMARY.json:8-13`。
- reviewed mock 已修复为 31 个来源文件和 engineering-only 解释：`research/decision_evidence_audit/runs/clear_rule_mock_reviewed_20260907T0220Z/evaluator/validation.json:80-88,524-525`。旧两次应显式标记 superseded/legacy-invalid，不能从目录存在推断通过。

### 可修复项

1. 给旧 mock run/view 增加非破坏性的状态索引，明确 `superseded`、历史失败原因及禁止用于研究结论。
2. 用 run snapshot 中的 reporter/validator 生成派生视图，或在 summary 记录实际 reporter/validator 来源、版本与生成时间；任务 gold 也从 snapshot 读取。
3. Reporter 的逐单元分类应以完整 `qualified` 而非仅 `model_mode=="live-local"` 为条件，并核验 profile、任务矩阵和固定参数。
4. Validator 要求 fingerprint 与 snapshot 路径集合完全一致，并为非提交/`unit_error` 路径核对请求数、policy、replay 和统一终局字段。
5. 为 B4 提取增加最小 JSON schema/解析状态；不能仅因第二步选项合法就称提取有效。
6. 修补隐藏值扫描对数字和短值的盲区。
7. 将 `real_model_chain_exercised` 改为由实际配对调用/完成链派生；保留 `attempted_incomplete_chain_smoke` 的精确状态。
8. 下一轮若自然出现错误 checkpoint，再验证真实模型 revision+POST；不得为覆盖路径人为注入错误。env008 先解决公开规则歧义。

最终可接受表述只能是：**工程层面，12 个由 3 个正确 checkpoint 派生的分支实现了相同状态恢复、B0 原样继续及真实本地提交；研究层面，本轮没有产生任何自然错误的提交前核查机会，故纠错成功率与纠错失败率均不可估计。** 同系列 Codex 审查仍为 provisional。
