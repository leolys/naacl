# env008 Phase 3：GUI-Reflection targeted recovery 结果

日期：2026-08-31  
模型：`craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`  
协议：`env008-phase3-50cell-v3`  
校准：`runs/phase3_calibration/20260831T144906Z_6db2f55e`  
正式 run：`runs/phase3_formal/20260831T145905Z_1a0aa4a4`  
范围：一个 env008 开发样本内的 M8+A6+R24+C12 机制面板；`n_base_case=1`，synthetic R cells 与整轮结果均为 `reportable=false`。

## 1. 结论先行

这轮结果没有给出“GUI-Reflection 完全有效”或“完全无效”的二元答案，而是把效果定位到了清楚的轨迹层级：

> GUI-Reflection 的 temporal trajectory 能帮助模型执行局部 Back、恢复部分流程连续性和识别何时点击 Confirm；但它没有稳定地把错误视觉前提的撤销转化为基于打印值的实体重求解、action 重绑定和正确提交。

最重要的四组观察是：

1. **局部撤销真实存在。** A 中 current-only/native 的 4/4 cells、R 中 native 的 12/12 cells 都有真实 `review → retry_decision` Back receipt。
2. **撤销不等于重新求解。** R native 在角色、图表位置、卡片位置和颜色轮换后，12 格中 11 格仍选择 Wind；只有 Wind 恰好被设为正确实体的 r4/r5 四格出现正确 rebind，4/4 随后都未提交。
3. **trajectory-state history bundle 能帮助局部 completion，但不验证语义正确性。** C 的空历史 4/4 都 Back；包含历史图像、动作与 annotation 的两个 populated-history 条件 8/8 都点击 Confirm。Solar final selection 的 4 格提交正确，Wind final selection 的 4 格同样被确认并提交错误。
4. **只加 premise-aware prompt/state machine 仍不够。** 同一 checkpoint 的 controller 在 14/14 evidence calls 中都只列出一个类别，尽管截图中五个类别和值完整可见；只有 1/14 同时输出 evidence stage 所需的 Back。Official A 图上它把 Wind 29.8%称为最大，clean A 图上才选择 Solar 41.2%。

整轮 task-level recovery 为 0。C 中有 4 个 direct completion，但其正确 Solar selection 是 evaluator 在 handoff 前建立的，`recovery_eligible=false`，不能算模型从误导图表完成的 recovery。

## 2. 实验面板回答什么

| Block | Cells | 处理变量 | 问题 |
|---|---:|---|---|
| M | 8 | empty / action-only / premise-specific / irrelevant memory × official/clean | memory 是否把“旧 Wind 不应重复”转成新实体动作 |
| A | 6 | current-only / native4 / premise-aware controller × official/clean | trajectory reflection 与显式 premise pipeline 分别带来什么 |
| R | 24 | 六个 R/X/P/C 正交配置 × native/controller × official/clean | action 跟随正确角色、误导角色、实体名、位置还是颜色 |
| C | 12 | empty / recent selection / revision chain × Solar/Wind × official/clean | 相同 current pixels 下，history 是否触发真实 Confirm，以及是否验证实体正确性 |

M、A 和 R 的 inherited/provisional state 都由 evaluator 通过真实 Firefox transaction 建立，并与模型行为分开记录。C 的整个 history 也是 evaluator-owned fixture，不计作模型自己完成的错误、Back 或选择。

## 3. 运行有效性

正式 run 是一个有效的行为 artifact，而不是基础设施失败：

- 50/50 cells 完成，103 条 raw model calls，239 张 PNG；
- `execution_complete=true`，0 invalid cell，0 paired-check failure，0 intervention-identity failure；
- 50 个发往服务的 task id 均为唯一 `phase3task_<32 hex>`，不包含 method、arm、role config 或 cell key；
- formal 禁止外部 `--agent-url`，使用 runner 启动的受审本机 GUI-Reflection service；
- M/A/R/C 的 first-current、actual model image、memory、history shared-tail 和 method-pair checks 全部通过；
- 10 个真实 submission receipts 与 10 个 scorer records 对应，其中 4 true、6 false；无 submission 的 cells 没有 scorer row；
- current-only 与 native 在 A 的第一张 current PNG、真实模型图像、首个 raw output 和 generation config 相同；
- controller 的 token→entity binding 只在整条 policy trajectory 结束后计算，明确 `used_as_model_input=false`、`used_for_controller_stage_control=false`。
- 当前实现回归套件完整通过：172 tests OK，2 个现有 sandbox-dependent tests skipped。

状态分布为：14 `controller_output_failure`、17 `agent_complete_without_submission`、5 `timeout`、4 `one_action_incomplete`、10 `submitted`。这些是行为结果；controller output failure 没有被改写成 infrastructure invalid。

当前 build 的独立 launch 审查见 [`ENV008_PHASE3_RED_TEAM_IMPLEMENTATION_REVIEW.md`](ENV008_PHASE3_RED_TEAM_IMPLEMENTATION_REVIEW.md)。正式结果的 raw receipt/UI/scorer 独立复算见 [`ENV008_PHASE3_RED_TEAM_RESULTS_AUDIT.md`](ENV008_PHASE3_RED_TEAM_RESULTS_AUDIT.md)。

## 4. 总体 failure-layer 分解

| Block | Cells | effective Back | 离开 inherited branch | correct entity rebind | submission | scorer true | task recovery | C direct completion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| M | 8 | 7 | 0 | 0 | 1 | 0 | 0 | 0 |
| R | 24 | 12 | 7 | 4 | 1 | 0 | 0 | 0 |
| C | 12 | 0 | 0 | 0 | 8 | 4 | 0 | 4 |

这里的 R 统计包含 12 个 native 和 12 个在 evidence stage 停止的 controller cells。C 的 selection 是 evaluator handoff，因此不进入 rebind 或 recovery 列。

```text
错误 review 被消费
  → Back / reversal
  → 是否离开旧实体分支
  → 是否按当前打印值重绑正确实体
  → 是否识别 final review 并点击 Confirm
  → submission receipt
  → scorer true
```

结果表明前两个局部状态转换偶尔或经常发生，完整依赖链没有发生。

## 5. M：memory 改变轨迹，但没有产生正确替代实体

三个非空 memory entries 在 checkpoint tokenizer 下都为 30 tokens，stored form 32 tokens，实际 prompt segment 42 tokens。它们都只提一次旧实体 Wind，不泄露 Solar。

| Memory | official | clean | 解释 |
|---|---|---|---|
| M0 empty | `Back → Wind → TASK_COMPLETE(no-submit)` | 同左 | native 的默认局部撤销后仍回到 Wind |
| M1 action-only | 点击 chart（无状态变化）→ Confirm inherited Wind，scorer=false | `Back → Back → Back → Back` | “不要重复旧 route”没有稳定执行；arm 改变了错误模式 |
| M2 premise-specific | `Back → Back → Back → Back` | 同左 | premise cue 抑制了立即 Wind re-entry，但没有提供/求出替代实体 |
| M3 irrelevant/noisy | `Back → chart click → Wind → TASK_COMPLETE(no-submit)` | `Back → Wind → TASK_COMPLETE(no-submit)` | 一般页面提示没有改变实体绑定 |

M2 是一个有限的正面信号：相对 M0，它没有重新点击 Wind。但它只把错误从“branch re-entry”变成“无进展 Back loop”，不能称为 premise recovery。M1 official 甚至真实提交了 inherited Wind，说明 action-only memory 在误导图上可能与视觉 anchoring 共同产生更危险的错误完成。

因此本轮不能写“memory 完全没有作用”；可写的是：**memory 内容能改变局部控制流，但 action-only 或 premise-specific 文本都没有稳定产生正确实体/action 重绑定。**

## 6. A：history 帮助继续流程，显式 controller 仍没有形成可靠 evidence table

| Method bundle | official | clean | 结果 |
|---|---|---|---|
| same-checkpoint current-only | `Back × 4` | `Back × 4` | 每步 reset 后只能看到 current page，停在 retry |
| official GUI-Reflection native4 | `Back → Wind → TASK_COMPLETE(no-submit)` | 同左 | history 让模型从 retry 继续选择，但延续错误 Wind 且漏 Confirm |
| premise-aware controller v1 | one-record `Wind=29.8` + `MEMORIZE` | one-record `Solar=41.2` + `MEMORIZE` | evidence 不完整，动作也不是 required Back；0 UI action |

这个 matched comparison 给出两个互补结论：

- Native trajectory history 相对 current-only 确实帮助了局部状态连续性：模型不再无限 Back，而会进入选择页并点击一个 card。
- 该帮助没有转成任务语义纠错。Native 在 official/clean 都选择 Wind，随后把尚未提交的 final review 当成完成。

Controller 不是 GUI-Reflection 原生行为，也不是 same-prompt/same-compute control；它是“同 checkpoint + 明确 printed-value policy + 三阶段 state machine”的 inference bundle。它在 clean/official 的首个实体差异具有诊断意义：即使 prompt 明示“几何与数值冲突时使用打印值”，official 图仍使模型把 Wind 29.8%当作最大，而 clean 图选择 Solar 41.2%。但 controller 没有按要求列全类别，也没有执行 reversal，所以不能把 clean 的单条正确记录当成 recovery。

## 7. R：role rotation 暴露 Wind 实体锚定，而不是 premise-conditioned 选择

R 的六个 synthetic configs 让 correct、misleading、neutral role 在 Solar/Wind/Hydroelectric 间轮换，并与 chart position X、card position P、color C 做 pairwise-balanced 配置。所有 routing labels/action IDs 都是 role-neutral。

### Native4

| Config | correct / inherited | official retry selection | clean retry selection | completion |
|---|---|---|---|---|
| r0 | Solar / Wind | Wind（misleading） | Wind（misleading） | 均 no-submit |
| r1 | Solar / Wind | Wind（misleading） | Wind（misleading） | 均 no-submit |
| r2 | Hydro / Solar | Wind（neutral），并错误提交 | Wind（neutral） | official scorer=false |
| r3 | Hydro / Solar | Solar（misleading） | Wind（neutral） | 均 no-submit |
| r4 | Wind / Hydro | Wind（correct） | Wind（correct） | 均 no-submit |
| r5 | Wind / Hydro | Wind（correct） | Wind（correct） | 均 no-submit |

Native 的可观测规律是：

- 12/12 effective Back；
- 7/12 离开 inherited entity；
- 11/12 首次 retry 选择 Wind，覆盖 Wind 的三个 card positions；
- 4/12 correct rebind 全部来自 r4/r5，即“Wind 被实验者轮成正确角色”；
- 1/12 真实提交来自 r2 official，但提交的是 neutral Wind，scorer=false；
- 0/12 task recovery。

因此 r4/r5 的四次正确 rebind 不能解释成模型读取了 `41.2% → Wind` 的依赖。更节制的解释是固定 Wind 倾向恰好与该配置的 correct role 对齐。R 排除了单一固定坐标解释，也说明仅报告“选择了正确 entity 的次数”会制造假阳性；必须检查选择是否随 role assignment 系统改变。

### Premise-aware controller

14 个 A/R controller cells 全都在第一阶段停止：14/14 evidence JSON 只有一个 record，0/14 覆盖截图中的多个可见类别。Official parser 的 stage action 分布也表明失败不只是 evaluator 的 `records>=2` 要求造成的：只有 r5 official 输出所需的 `PRESS_BACK`；其他输出为 MEMORIZE、TASK_COMPLETE、CLICK 或 INVALID。

R 的单条 evidence 还暴露了多种错误：例如 r0 official 把 `Hydroelectric=41.2` 绑定在一起，r4 official 输出 `Solar=41.2`，r5 official 输出 `Hydroelectric=18.5`；这些都不是对应 source rows 的完整实体—值关系。Clean arm 也并非总能正确绑定值。可见问题不是“JSON 格式太严格”，而是模型没有生成可供 dependency graph 使用的完整、可信 premise set。

## 8. C：history presence 能触发 Confirm，revision semantics 不能触发 correctness gate

C 在同一 arm、同一 final entity 内保证三种条件的 current PNG 和 app state 相同。两个 populated histories 都恰好有 2 frames/2 actions，共享最后 raw frame、最后 click action、annotation 和实际 model-input digest；区别只在较早语义：neutral WAIT 对 wrong-review→Back。

| Final entity | H0 empty | H2 recent selection | H2 revision chain |
|---|---|---|---|
| Solar（正确） | official/clean 均 Back | 两臂均 Confirm，scorer=true | 两臂均 Confirm，scorer=true |
| Wind（错误） | official/clean 均 Back | 两臂均 Confirm，scorer=false | 两臂均 Confirm，scorer=false |

这组结果同时给出正面和负面证据：

- **正面：** temporal history 使模型正确识别“已经选择、现在应 Confirm”的局部阶段。H0 的相同 current pixels 不足以触发该动作。
- **负面：** 模型同样确认 Solar 和 Wind；更早 history 是 WAIT 还是明确 revision chain，也不改变 action。因此 history 支持的是流程连续性，不是 correctness verification。

四个 Solar direct completions 是真实 submission/scorer success，但 Solar selection 与 history 都由 evaluator 建立；它们只能证明 completion capacity，不能证明模型已从误导图表恢复。

## 9. 对“0 recovery 是不是 runner 造出来的”这一替代解释

当前证据不支持把 0 recovery 归因于 strict parser 或 scorer 过严：

- 红队对 89 个非-controller raw responses 独立复算，89/89 的 strict action 与官方 parser action 一致，`parser-censored=0`。其中 16 个非-controller A/R cells（current-only/native）都执行真实 Back，R native 还全部执行了真实选择。失败发生在实体身份和 Confirm，而不是 parsing。
- Controller 的 14/14 calls 不仅 evidence 不完整；13/14 的官方动作也不是该阶段需要的 Back。放松 record 数量不会自动产生合法三阶段轨迹。
- 10 个真实 submission 全有 scorer：Solar C 的 4 个被判 true，Wind C、M1 official 和 r2 official 的 6 个被判 false，证明 scorer 能接受正确提交而不是恒 false。
- C 的 8 个 populated-history cells 都能点击同一个 Confirm，说明按钮可见、坐标执行和 submission path 可用。

因此 0 task recovery 是可观测行为链缺失，不是页面无法操作或 hidden scorer 永远拒绝。

## 10. 论文可以怎样表述

当前最稳妥的英文表述是：

> On the env008 development case, GUI-Reflection's temporal trajectory supported local reversal and workflow continuation, but did not reliably convert contradiction into printed-value-based entity/action rebinding and verified submission. Role counterfactuals revealed a strong Wind selection bias, while populated history triggered confirmation regardless of whether the selected entity was correct. A same-checkpoint premise-aware prompt pipeline also failed to produce complete visual evidence records.

允许的中文结论：

- “GUI-Reflection 在该样本上能执行局部 navigation reversal，但 premise-conditioned entity/action rebinding 不稳定。”
- “Temporal history 帮助状态连续性与 Confirm，却不构成实体正确性验证。”
- “显式要求 printed-value-first 的 prompt 仍可能在 misleading 图上跟随几何，并且不能稳定列全证据。”
- “R 中的正确 rebind 是 Wind role 对齐后的反事实诊断，不是完整恢复。”

不能写成：

- 50 cells 是 50 个独立任务或成功率样本；
- GUI-Reflection training 相对普通 agent 的因果效果；current-only 仍是同一个已训练 checkpoint 的运行时 ablation；
- controller 成功/失败等价于原始 GUI-Reflection 成功/失败；它使用不同 prompt 与 state machine；
- C 的 evaluator-built Solar history 是模型 recovery；
- clean arm 也经常失败时，所有 end-to-end failure 都由 misleading visualization 单独造成；
- 单条 evidence JSON 与 action 一致就证明模型完整读取了像素。

## 11. 下一种方法应解决的具体缺口

本轮不支持“再多写一句反思提示”作为充分方案。下一种方法至少需要：

1. **完整 evidence acquisition。** 对每个可见类别建立 entity/value/region，并验证覆盖率与实体—值绑定；单个最显眼类别不能直接成为 premise。
2. **显式依赖图。** 保存 `visual evidence → proposition → executable entity/action`，当 contradiction 到来时使依赖旧 premise 的 action 失效。
3. **重新求解而非 different-action heuristic。** 从当前证据重算 argmax，再将实体名绑定到可见 card；“不要再点旧项”只是约束，不是答案。
4. **role/shortcut robustness。** 方法输出必须随 R 的 correct role 改变，而不能持续偏好 Wind、固定位置或颜色。
5. **semantic completion gate。** Confirm 前检查 current selection 与当前有效 proposition 一致；提交后等真实 UI receipt，不能用 `TASK_COMPLETE` 代替。
6. **failure-preserving verifier。** evidence 不完整时应保留为感知失败或触发新的视觉读取，而不是让 evaluator 填入 CSV/DOM 真值。

这也说明一个重要设计风险：仅在 LLM prompt 中要求“抽取所有值”并不保证得到可执行 premise graph。下一方法需要更可靠的结构化视觉读取、逐实体查询或可验证 grounding，而不是只在原 checkpoint 外包一层 JSON 格式。

## 12. 是否需要更多样本

需要，但不建议继续无限扩充 env008 cells。Phase 3 已经把 env008 的主要 failure layers 暴露出来。下一步更有价值的是：

1. 把 env008 保留为 development/unit case，用来迭代 premise-aware 方法；
2. 先确保新方法在 env008 同时通过 evidence completeness、role covariance、correct rebind 和真实 submission；
3. 再扩到 8–12 个手工审计 case，覆盖不一致尺度、截断轴、面积/长度错配、legend/label 干扰、双轴或 stacked-bar 等不同 misleader；
4. 优先选择或构造 clean arm 上 agent 具备基本 end-to-end competence 的 case，避免把一般 GUI/视觉能力不足误写成 misleading-specific failure；
5. 每个 case 以 case 为统计单位，cell 只作 case 内机制条件；冻结 development/validation/held-out 划分后再报告总体结果。

一个适合后续论文的任务样本至少应包含：明确可人工核验的打印值真值、只改变可视化误导机制的 matched clean arm、可观测 inherited error、真实 Back/reattempt/final-submit 状态、answer-neutral contradiction、实体角色与 UI shortcut counterfactual，以及 submission/scorer 的独立 receipt。

## 13. Artifact 入口

- [正式 summary](runs/phase3_formal/20260831T145905Z_1a0aa4a4/summary.json)
- [冻结 protocol](runs/phase3_formal/20260831T145905Z_1a0aa4a4/frozen_protocol.json)
- [v3 calibration](runs/phase3_calibration/20260831T144906Z_6db2f55e/summary.json)
- [pre-run protocol 审查](ENV008_PHASE3_RED_TEAM_PROTOCOL_REVIEW.md)
- [pre-run 实现/校准审查](ENV008_PHASE3_RED_TEAM_IMPLEMENTATION_REVIEW.md)
- [post-run 结果红队审计](ENV008_PHASE3_RED_TEAM_RESULTS_AUDIT.md)
- [逐 cell 分析](ENV008_PHASE3_CASE_BY_CASE_ANALYSIS.md)
- [Phase 2 结果](ENV008_PHASE2_RESULTS.md)

代表性截图：

- [A official misleading controller input](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_premise_aware_controller_v1_official_f3/screenshots/controller_00_evidence_and_reversal.png)
- [A clean controller input](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_premise_aware_controller_v1_clean_f3/screenshots/controller_00_evidence_and_reversal.png)
- [Native Back 后的 official retry](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_official_gui_reflection_native4_official_f3/screenshots/step_01.png)
- [C revision-chain Solar final review](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_revision_chain_solar_official/screenshots/step_00.png)
