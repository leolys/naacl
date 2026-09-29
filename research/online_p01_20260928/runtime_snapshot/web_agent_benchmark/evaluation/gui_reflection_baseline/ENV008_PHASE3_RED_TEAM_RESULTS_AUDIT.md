# ENV008 Phase-3 独立红队结果审计

## 审计对象与结论

- 正式运行：`runs/phase3_formal/20260831T145905Z_1a0aa4a4`
- 协议：`env008-phase3-50cell-v3`
- 审计方式：不采信汇总值，逐文件重读 50 个 cell 的 summary、raw step、PNG、模型 request/response receipt、UI transaction、submission、scorer、intervention、controller posthoc audit，并以冻结协议和官方 GUI-Reflection parser 独立重算关联与行为。
- **总 verdict：artifact validity = GO / VALID；机械异常 0。** 该 run 足以报告这 50 个预注册 cell 的实际行为。
- **归因 verdict：部分 NO-GO。** 不允许把 controller 的失败解释为“通用 premise-aware controller 无效”，也不允许把 C 的 4 个正确提交称为 agent recovery。

## 独立机械复算

| 项目 | 复算结果 | 异常 |
|---|---:|---:|
| cell | 50（M=8，A=6，R=24，C=12） | 0 |
| 模型调用 / step screenshot | 103 / 103 | 0 |
| native official receipt / controller receipt | 89 / 14 | 0 |
| 不透明 service task ID | 50 个，均唯一且精确 join | 0 |
| PNG | 239 个，均可解码、1280×960 | 0 |
| UI transaction | 125 个，均唯一；evaluator=74，model=51 | 0 |
| submission / scorer | 10 / 10，逐项一一对应 | 0 |
| 无 submission cell 携带 scorer | 0 | 0 |

- 50 个磁盘 cell summary 与顶层 `partial_results.json` 一致；cell 顺序、spec、memory 条目和冻结 controller prompt manifest 与 v3 协议一致。
- 103 个 raw PNG、实际送模 RGB、SHA、viewport、request/response ID 均与 receipt 对上；50/50 handoff 图像逐字节等于第一张模型截图。
- 89 个 native prompt 由官方模板、动作历史、memory 和历史图像独立重建，question SHA/长度、task goal、92 个历史图像及其 annotation/448-digest、action-history 与 memory 段均精确匹配。
- 14 个 controller question 均等于冻结 evidence prompt，system prompt hash 匹配审计源码；没有动态插入正确实体或答案。
- 74 个 evaluator setup transaction 与 51 个 model transaction 集合不相交；所有 selection 均由可见卡片重新映射实体。
- 10 个 submission 均能沿 model UI transaction → submission ID → scorer 精确连接；独立重跑 canonical/R scorer 得到 4 true、6 false。
- posthoc binding 的 14 份记录均在整条 controller trajectory 后计算，标记 `used_as_model_input=false`、`used_for_controller_stage_control=false`；每格仅一次调用，因此不存在结果反馈到后续策略调用的路径。

## Strict parser 替代解释攻击

- 对 89 个非 controller raw response，独立运行官方 `parse_action_output` 并再运行 strict final parser：**89/89 official payload 与存盘一致，89/89 strict action 与 official action 一致，parser-censored=0**。
- 因此本 run 的 `task_level_recovery=0` 不是 strict parser 把本可执行的 native/current/M/R/C 动作过滤掉造成的。
- 14 个 controller cell 更早就因 evidence record 只有 1 条而不满足方法契约；strict parser 并非首个终止条件。即使假设跳过 evidence gate，也只有 1 个输出为合法 `PRESS_BACK`，且其唯一证据记录仍错误/不完整。
- 这支持“冻结 controller 与该 checkpoint 的输出接口失败”，不支持“任意 premise-aware controller 都无法恢复”。

## M：memory factorial

- 8 格中 7 格发生有效 Back；没有一格正确重绑定，1 格错误提交，0 recovery。
- empty、action-only、premise-specific、irrelevant-noisy memory 确实改变了局部控制流：有的继续重选 Wind，有的反复 Back/timeout，还有一格由 inherited Wind 直接 Confirm。
- premise-specific memory 没有产生正确选择；但其“避开错误”的表象只是停滞，不能计作 premise recovery。
- 允许结论：当前模型读取到不同 memory 后会改变动作序列，但这些 memory 条件没有在本例产生完整恢复。
- 禁止结论：memory 普遍无效，或某类 memory 已改善任务正确率；每条件仅是单个受控 cell/arm realization。

## A：method comparison

- current-only 两臂均为 4 次 Back、无 selection；native 两臂均为 Back → Wind → `TASK_COMPLETE`、无提交；controller 两臂均在第一证据阶段失败、无 UI 动作。
- current-only 四次调用均满足 task step/history/action/memory 清空和 reset receipt；current 与 native 的第一张图、第一问题、第一 raw generation 在对应 arm 内精确匹配。
- 这排除了首步像素或初始模型响应不对称，却不能把三种方法作为完整能力排名：controller 使用不同的结构化 prompt，并且从未进入其策略执行阶段。
- controller 失败不得归因于原生 GUI-Reflection 模型；反过来，native/current 的失败也不能证明 premise-aware 设计无潜力。

## R：role counterfactual

- 12 个 native cell 全部有效 Back；其第一重试选择为 Wind 11/12、Solar 1/12。
- 按 counterfactual role 计：correct=4、misleading=5、neutral=3；6 个配置中 5 个 official/clean 动作相同，只有 r3 发生 arm 差异；另有 1 个 neutral Wind 错误提交。
- 4 个“correct”重绑定均出现在 Wind 被指定为正确实体的布局，因此更符合 Wind 实体先验，而不是角色/视觉前提追踪。
- 允许结论：在本组位置/颜色轮换内观察到强 Wind 选择偏好，且对 correct/misleading/neutral 角色不敏感。
- 禁止结论：模型学会了 role counterfactual，或该 12 格足以给出跨样本的普遍捷径率。

## C：completion history 的真实性边界

- H0 的 Solar/Wind × 两臂共 4 格均 `PRESS_BACK`，无 submission。
- H2 recent-selection 与 other-entity review→Back→final-selection 两种历史下，Solar/Wind × 两臂共 8 格均真实执行 `CLICK Confirm`，并形成 submission/scorer：Solar 4/4 true，Wind 4/4 false。
- 所以 4 个 true 是**真实 UI 提交和真实 scorer success**，不是 receipt 伪造；但其 Solar 选择、两帧历史和动作描述均由 evaluator 构造，且这些 cell 明确 `recovery_eligible=false`。
- 两个 H2 条件的当前末帧逐像素匹配，同时历史 bundle 包含图像、动作及显式实体 action-description；因此只能归因于“填充的官方 trajectory-state bundle 提高 Confirm 倾向”，不能只归因于视觉历史。
- 正确和错误最终实体都同样触发 Confirm，说明该效应不是 correctness verification。4 个 true 必须报告为 evaluator-owned direct completion，不能并入 recovery。

## Controller 人工语义核读

- 14/14 controller 截图中五个类别和值均像素可见；question/template/system prompt 与冻结版本一致，无答案字段泄漏。
- 14/14 输出都只有 1 条 evidence record，而协议要求覆盖所有可见类别；满足完整表格者为 0。
- 唯一记录中，entity-value 事实正确 9/14、错误 5/14；首实体等于可见最大值实体 8/14；正确阶段动作 `PRESS_BACK` 仅 1/14。
- action 类型为 INVALID 6、MEMORIZE 4、TASK_COMPLETE 2、CLICK 1、PRESS_BACK 1；6/14 撞到 1024-token cap，并重复畸形 `EVIDENCE_JSON`。
- 因此 `controller_output_failure=14` 是可复现的 checkpoint/prompt-interface 失配；这些轨迹没有真正构造 premise dependency，也没有测试后续 recovery policy。

## 允许与禁止的论文主张

允许：

- 在该冻结协议和 env008 的 50 格中，`task_level_recovery=0`、`method_attributable_full_recovery=0`；该计数不是 strict parser 或 scorer join 人为制造。
- 原生 GUI-Reflection 能完成局部 Back/继续动作，但没有在这些格中稳定撤销视觉前提并完成正确提交。
- R 组呈现 Wind 实体偏好；M 组 memory 会改变控制流但未带来完整恢复。
- C 组的完整 trajectory-state history 提高 Confirm 倾向，且不区分正确/错误实体。
- 冻结 controller 在 evidence stage 出现 14/14 结构化输出失败。

禁止：

- “GUI-Reflection/轨迹纠错方法完全无效”或“误导图表一定不可恢复”。
- “提出的 premise-aware controller 已被端到端否证”；它没有越过 stage 0。
- 将 C 的 4 个正确提交称作 recovery、模型自主纠错或语义验证。
- 把无 submission 等同于 scorer failure，或把 `TASK_COMPLETE` 无提交当作任务成功。
- 将 50 格当作 50 个独立 benchmark 样本、报告泛化成功率，或把 clean arm 的失败归因于 misleading chart。
- 将 controller 的畸形输出归因于原生 GUI-Reflection 行为。

## 最终判定

**GO：** 作为 env008 Phase-3 冻结、可复核的逐条件行为证据，正式 run 有效，机械异常数为 **0**。

**NO-GO：** 不得据此宣称 controller 已被公平地端到端比较、C 实现了 recovery，或结论已推广到 benchmark/模型族。主报告的关键机械计数与主要限定结论均获 raw artifact 支持；需要保持的两项精度边界是：C 的处理是图像+动作/动作描述的 bundle，controller 失败是本 checkpoint/接口失败而非通用方法失败。
