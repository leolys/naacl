# env008 Phase-3：50-cell 逐格轨迹分析

分析对象：[`20260831T145905Z_1a0aa4a4`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/summary.json)  
冻结协议：[`frozen_protocol.json`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/frozen_protocol.json)  
checkpoint：`craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`

## 结论先行

这次运行支持一个比“能/不能解决”更细的结论：**原生 GUI-Reflection 很稳定地完成局部 Back，却没有稳定地把被否定的视觉前提重算为正确实体、把实体绑定到新 action，并完成真实提交。** 在本开发 case 中：

- 50/50 cell 均有完整 artifact，`invalid_cells=[]`、`paired_check_failures=[]`、`execution_complete=true`。本分析另外逐文件复核了 50 个 handoff、103 个 step screenshot 及其 SHA-256，全部存在且与 receipt 相符。
- M/A/R/C 四个 block 的 `task_level_recovery` 均为 0；其中真正 recovery-eligible 的 M/A/R 共 38 格，0/38 完成 task-level recovery。
- 只看原生 `official_gui_reflection_native4` 的 M+A+R 22 格，21/22 执行过有效的局部 Back，但只有 R 中 4/22 出现正确实体重绑定，且 0/22 正确提交。4 次命中全部发生在 synthetic r4/r5 中，而这些配置恰好把模型几乎固定选择的 Wind 设成了正确实体。
- R 的 12 个原生格中 11/12 在 retry 选择 Wind；Wind 已跨越全部 chart position、card position 与 color level。这不是稳定的 correct-role 跟随，而是明显的 entity identity 锁定。唯一分叉是 r3：clean 选中 neutral Wind，official 改选 misleading Solar，仍然没有正确重绑定。
- 显式 `premise_aware_controller_v1` 的 14/14 evidence call 都只列出 1/5 个可见类别，0/14 列全三个主类别，0/14 列全五类；冻结 parser 因此在第一阶段全部停止。9/14 singleton entity-value pair 本身准确，6/14 恰好是全图真实最大值，但单条记录不能支持 argmax。该失败属于**显式 controller 的证据覆盖/输出协议失败**，不能归因成原生 GUI-Reflection 的行为。
- C 的 populated history 8/8 都会确认当前页面已经选好的实体：Solar 4/4 提交正确，Wind 4/4 提交错误；empty history 4/4 都 Back。C 的状态与历史由 evaluator 建立，`recovery_eligible=false`，所以这是 history-conditioned direct submission probe，**不是 recovery 成功**。

运行文件本身标记 `reportable=false`。这不是 artifact 无效，而是冻结协议明确把它限定为 `n_base_case=1` 的 in-case development panel；50 个 cell 不能当成 50 个 IID 样本，也不能汇总成论文主结果的置信区间。

## 读表约定

每个 cell 名链接到其原始 `steps.jsonl`；同目录下的 `summary.json`、`intervention.json`、screenshots 和 scorer receipt 可继续追踪。缩写如下：

- `B`：真实 `PRESS_BACK`，从 review 回到 retry decision；`B∅`：再次 Back 但没有新的 UI transition。
- `S(entity)`：产生真实 selection receipt；`C(entity)`：产生真实 submission receipt。
- `X∅`：CLICK 但没有 UI receipt；`TC∅`：模型输出 `TASK_COMPLETE`，但没有 submission receipt。
- `CTRL 1/5`：controller 只抽到五个可见类别中的一条；`STOP`：冻结 evidence parser 拒绝，未执行该模型动作。
- “正确/错误”均来自执行后 hidden scorer 的 post-hoc 判断；这些字段未送入模型或 controller。

## M：memory consumption，8 cells

三个非空 memory 均为 30 entry tokens，step-0 current image、空 history、generation config 与 prompt binding 的 paired checks 全部通过。这里的 memory 是 evaluator seed 的辅助条件，不是模型自主生成的反思。

| cell | arm / memory | 实际轨迹 | 与配对格的差异及含义 |
|---|---|---|---|
| [`m_m0_empty_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m0_empty_clean/steps.jsonl) | clean / M0 empty | `B → S(Wind) → TC∅`；无提交 | 与 official 完全同型；clean 几何也没有触发 printed-value 重算。 |
| [`m_m0_empty_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m0_empty_official/steps.jsonl) | official / M0 empty | `B → S(Wind) → TC∅`；无提交 | 与 clean 同型；误导几何不是这里失败的唯一来源，错误实体在 Back 后继续存活。 |
| [`m_m1_action_only_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m1_action_only_clean/steps.jsonl) | clean / “不要重复 Wind route” | `B → B∅ → B∅ → B∅`；timeout | memory 阻止了立即重选 Wind，但没有给出可执行的新实体绑定；不同于 official 的错误直接提交。 |
| [`m_m1_action_only_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m1_action_only_official/steps.jsonl) | official / action-only | `X∅(Wind chart bar) → C(Wind)`；scorer=false | 未离开 inherited Wind review，反而确认原错误；是 direct wrong submission，不是 reversal/recovery。与 clean 的分叉说明同一 memory 会与视觉 arm 发生强交互。 |
| [`m_m2_premise_specific_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m2_premise_specific_clean/steps.jsonl) | clean / “前提矛盾，按 printed values 重算” | `B → B∅ → B∅ → B∅`；timeout | 不再选 Wind，但也没有抽取 Solar、绑定 action 或提交；premise cue 只形成回避/循环。 |
| [`m_m2_premise_specific_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m2_premise_specific_official/steps.jsonl) | official / premise-specific | `B → B∅ → B∅ → B∅`；timeout | 与 clean 完全同型；显式“重算”文字仍不足以把 premise invalidation 变成新 action。 |
| [`m_m3_irrelevant_noisy_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m3_irrelevant_noisy_clean/steps.jsonl) | clean / interface-noise control | `B → S(Wind) → TC∅`；无提交 | 与 empty baseline 同型；非空 memory 本身不带来纠正。 |
| [`m_m3_irrelevant_noisy_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/m_m3_irrelevant_noisy_official/steps.jsonl) | official / interface-noise control | `B → X∅ → S(Wind) → TC∅`；无提交 | 比 clean 多一次落空 click，最终仍回到 Wind；噪声没有纠正能力。 |

M 的主要研究含义不是“memory 无效”，而是：action-level 与 premise-level 负向提示都可能让模型停止重复原动作，但**停止旧动作不等于形成正确的新 premise/action dependency**。M2 在两臂都把重入 Wind 变成 Back loop，正好暴露缺失的中间能力。

## A：same-checkpoint method bundle，6 cells

同一 arm 下三个方法看到相同 step-0 current pixels；current-only 与 native4 的确定性首个 raw output 也完全相同。后续差异来自 history/state/prompt bundle，不是不同 checkpoint。`same_checkpoint_current_only` 不是“未训练 reflection 的模型”；controller 也不是原生 GUI-Reflection。

| cell | arm / method | 实际轨迹或 raw evidence | 比较结论 |
|---|---|---|---|
| [`a_same_checkpoint_current_only_clean_f3`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_same_checkpoint_current_only_clean_f3/steps.jsonl) | clean / current-only | `B → B∅ → B∅ → B∅`；timeout | 清空历史使模型每次都把 retry page 当成应 Back 的当前页；避免了 Wind 重入，但失去推进能力。 |
| [`a_same_checkpoint_current_only_official_f3`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_same_checkpoint_current_only_official_f3/steps.jsonl) | official / current-only | `B → B∅ → B∅ → B∅`；timeout | 与 clean 同型；单帧局部策略不能完成纠错链。 |
| [`a_official_gui_reflection_native4_clean_f3`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_official_gui_reflection_native4_clean_f3/steps.jsonl) | clean / native4 | `B → S(Wind) → TC∅` | 历史使模型从循环变成“换一个界面动作”，但没有更新实体，且把 final review 误当已完成。 |
| [`a_official_gui_reflection_native4_official_f3`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_official_gui_reflection_native4_official_f3/steps.jsonl) | official / native4 | `B → S(Wind) → TC∅` | 与 clean 完全同型；这是最直接的“局部导航撤销成功、实体/action 重绑定失败”。 |
| [`a_premise_aware_controller_v1_clean_f3`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_premise_aware_controller_v1_clean_f3/steps.jsonl) | clean / controller | `CTRL 1/5: Solar=41.2`（准确且为真最大）+ `MEMORIZE`；`STOP` | 视觉 singleton 方向正确，但未列全类别、未输出要求的 Back，故不能算 argmax 或 recovery。 |
| [`a_premise_aware_controller_v1_official_f3`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/a_premise_aware_controller_v1_official_f3/steps.jsonl) | official / controller | `CTRL 1/5: Wind=29.8`（pair 准确但非最大）+ `MEMORIZE`；`STOP` | 与 clean 的 Solar→Wind singleton 分叉与 misleading geometry 相容，但 controller 在执行前即失败，不能声称产生行为改进。 |

A 给出的机制图景是：current-only 保守但循环；native history 能推进，却沿用错误实体并漏掉 Confirm；显式 controller 有希望把问题改写成 evidence computation，但当前 checkpoint 无法遵守“列全类别 + Back”的复合输出 contract。

## R：role / position / color counterfactual，24 cells

五个可见类别为 Solar、Wind、Hydroelectric、Biomass、Geothermal；前三者参与正交角色轮换，后两者固定为 7.2 与 3.3。下表中的 target/misleading 均是执行后诊断，不是模型输入。

| config | target / misleading / neutral | X / P / C（按 Solar, Wind, Hydro） |
|---|---|---|
| r0 | Solar / Wind / Hydro | `120 / 201 / 210` |
| r1 | Solar / Wind / Hydro | `201 / 120 / 021` |
| r2 | Hydro / Solar / Wind | `012 / 120 / 102` |
| r3 | Hydro / Solar / Wind | `120 / 012 / 021` |
| r4 | Wind / Hydro / Solar | `012 / 012 / 210` |
| r5 | Wind / Hydro / Solar | `201 / 201 / 102` |

### R 的 24 格逐格结果

| cell | method / arm | 实际轨迹或 evidence | post-hoc 诊断 |
|---|---|---|---|
| [`r_r0_official_gui_reflection_native4_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r0_official_gui_reflection_native4_clean/steps.jsonl) | native4 / clean | `B → S(Wind) → TC∅` | 选择 misleading entity；无提交。 |
| [`r_r0_official_gui_reflection_native4_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r0_official_gui_reflection_native4_official/steps.jsonl) | native4 / official | `B → S(Wind) → TC∅` | 与 clean 相同，选择 misleading entity；无提交。 |
| [`r_r0_premise_aware_controller_v1_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r0_premise_aware_controller_v1_clean/steps.jsonl) | controller / clean | `CTRL 1/5: Solar=29.8` + `TASK_COMPLETE`；`STOP` | entity 是 target，但值错绑；真实 Solar=41.2，不能计算 argmax。 |
| [`r_r0_premise_aware_controller_v1_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r0_premise_aware_controller_v1_official/steps.jsonl) | controller / official | `CTRL 1/5: Hydro=41.2` + `MEMORIZE`；`STOP` | entity/value 均错绑；真实 Hydro=18.5。 |
| [`r_r1_official_gui_reflection_native4_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r1_official_gui_reflection_native4_clean/steps.jsonl) | native4 / clean | `B → S(Wind) → TC∅` | 选择 misleading Wind；说明不是固定 card position，因为本格 Wind 在 P2。 |
| [`r_r1_official_gui_reflection_native4_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r1_official_gui_reflection_native4_official/steps.jsonl) | native4 / official | `B → S(Wind) → TC∅` | 与 clean 相同；无提交。 |
| [`r_r1_premise_aware_controller_v1_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r1_premise_aware_controller_v1_clean/steps.jsonl) | controller / clean | `CTRL 1/5: Wind=29.8`（pair 准确）+ 重复 evidence/invalid action；`STOP` | 漏掉 target Solar=41.2。 |
| [`r_r1_premise_aware_controller_v1_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r1_premise_aware_controller_v1_official/steps.jsonl) | controller / official | `CTRL 1/5: Wind=29.8`（pair 准确）+ invalid action；`STOP` | 与 clean 相同，singleton 非最大。 |
| [`r_r2_official_gui_reflection_native4_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r2_official_gui_reflection_native4_clean/steps.jsonl) | native4 / clean | `B → S(Wind) → TC∅` | Wind 在本格是 neutral；target Hydro 未绑定。 |
| [`r_r2_official_gui_reflection_native4_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r2_official_gui_reflection_native4_official/steps.jsonl) | native4 / official | `B → S(Wind) → C(Wind)`；scorer=false | 唯一 R 原生提交，但提交 neutral Wind；official 比 clean 更危险地把错误选择真正提交。 |
| [`r_r2_premise_aware_controller_v1_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r2_premise_aware_controller_v1_clean/steps.jsonl) | controller / clean | `CTRL 1/5: Hydro=41.2`（准确 target）+ invalid action；`STOP` | singleton 恰好是真最大，但没有完整 evidence set 或 UI action。 |
| [`r_r2_premise_aware_controller_v1_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r2_premise_aware_controller_v1_official/steps.jsonl) | controller / official | `CTRL 1/5: Hydro=41.2`（准确 target）+ invalid action；`STOP` | 与 clean 相同；不能把正确 singleton 记作 recovery。 |
| [`r_r3_official_gui_reflection_native4_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r3_official_gui_reflection_native4_clean/steps.jsonl) | native4 / clean | `B → S(Wind) → TC∅` | 选择 neutral Wind；无提交。 |
| [`r_r3_official_gui_reflection_native4_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r3_official_gui_reflection_native4_official/steps.jsonl) | native4 / official | `B → S(Solar) → TC∅` | 唯一 native arm 分叉；从 clean 的 neutral Wind 转为 official 的 misleading/tall Solar，仍非 target Hydro。 |
| [`r_r3_premise_aware_controller_v1_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r3_premise_aware_controller_v1_clean/steps.jsonl) | controller / clean | `CTRL 1/5: Hydro=41.2`（准确 target）+ `TASK_COMPLETE`；`STOP` | evidence singleton 正确，但 action 过早宣称完成。 |
| [`r_r3_premise_aware_controller_v1_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r3_premise_aware_controller_v1_official/steps.jsonl) | controller / official | `CTRL 1/5: Hydro=41.2`（准确 target）+ `MEMORIZE`；`STOP` | 与 clean 同一 singleton，仍未遵守 Back contract。 |
| [`r_r4_official_gui_reflection_native4_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r4_official_gui_reflection_native4_clean/steps.jsonl) | native4 / clean | `B → S(Wind) → TC∅` | `correct_entity_rebinding=true`，但无提交；Wind 恰好是本格 target。 |
| [`r_r4_official_gui_reflection_native4_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r4_official_gui_reflection_native4_official/steps.jsonl) | native4 / official | `B → S(Wind) → TC∅` | 与 clean 相同；correct rebind 仍未转成 task recovery。 |
| [`r_r4_premise_aware_controller_v1_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r4_premise_aware_controller_v1_clean/steps.jsonl) | controller / clean | `CTRL 1/5: Wind=29.8` + `CLICK[[500,500]]`；`STOP` | entity 是 target，值错绑；真实 Wind=41.2，click 也不满足 Back stage。 |
| [`r_r4_premise_aware_controller_v1_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r4_premise_aware_controller_v1_official/steps.jsonl) | controller / official | `CTRL 1/5: Solar=41.2` + invalid action；`STOP` | entity/value 错绑；真实 Solar=18.5，target 是 Wind。 |
| [`r_r5_official_gui_reflection_native4_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r5_official_gui_reflection_native4_clean/steps.jsonl) | native4 / clean | `B → S(Wind) → TC∅` | correct rebind，但无提交；Wind 在本格 P0，排除只跟随 r4 的中间 card slot。 |
| [`r_r5_official_gui_reflection_native4_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r5_official_gui_reflection_native4_official/steps.jsonl) | native4 / official | `B → S(Wind) → TC∅` | 与 clean 相同；correct rebind 仍是 incomplete recovery。 |
| [`r_r5_premise_aware_controller_v1_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r5_premise_aware_controller_v1_clean/steps.jsonl) | controller / clean | `CTRL 1/5: Wind=41.2`（准确 target）+ invalid action；`STOP` | singleton 恰好是真最大，但没有可执行 chain。 |
| [`r_r5_premise_aware_controller_v1_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/r_r5_premise_aware_controller_v1_official/steps.jsonl) | controller / official | `CTRL 1/5: Hydro=18.5` + `PRESS_BACK`；`STOP` | 14 格中唯一输出所要求 Back 的 controller call，但值错绑（真实 Hydro=29.8）且 evidence 不完整，所以动作没有执行。 |

### R 的 shortcut 读法

原生模型在 r0/r1 选择 misleading Wind，在 r2 与 r3-clean 选择 neutral Wind，在 r4/r5 选择 correct Wind。它跟随的是同一个 **Wind identity**，不是随页面轮换的 correct/misleading role；同一实体在这些页上已经覆盖不同 X/P/C level，因此也不是单一固定位置或颜色能解释。r3-official 的 Solar 是唯一反例，且恰好转向该 official 页的视觉 tallest/misleading entity，说明视觉几何可能在特定布局上覆盖实体 prior，但 `n_base_case=1`，不能据此估计一般效应。

## Controller raw evidence 专项核查

controller 共 14 个首阶段调用（A 2 + R 12）：

| 项目 | 观察值 | 能否支持下一阶段 |
|---|---:|---|
| 列全 5 个可见类别 | 0/14 | 否 |
| 至少列全 3 个参与 role 的主类别 | 0/14 | 否 |
| 只输出 1 条 record | 14/14 | 否；冻结 parser 要求 2--20 条，prompt 实际要求 every visible category |
| singleton entity-value pair 与 source row 一致 | 9/14 | 只说明局部 OCR/配对有时正确，不足以做 argmax |
| singleton 恰好等于真实最大 entity-value | 6/14 | 仍不是完整集合上的 argmax，也未进入 action-binding |
| singleton entity 名恰好为 target（不论值） | 8/14 | 其中 2 次值错绑，且 8 次全部缺少完整比较，不能提升为 premise success |
| 输出所要求的 `PRESS_BACK` | 1/14 | 该格仍因 singleton 被拒绝；其余输出 MEMORIZE/TASK_COMPLETE/CLICK/INVALID |
| 真正执行 controller UI action | 0/14 | 否 |

因此 controller 的失败至少有两个可分离来源：

1. **证据集合覆盖失败**：模型倾向只报告一个显著类别；official canonical 从 clean 的 Solar=41.2 变为 Wind=29.8，直接表明“要求用 printed labels”并未消除几何显著性。
2. **输出/action contract 失败**：即使 singleton 恰好正确，checkpoint 仍常输出其原生习惯的 MEMORIZE、TASK_COMPLETE 或重复 JSON，而不是要求的 Back。冻结 parser 正确地阻止了 runner 用 evaluator truth 补齐这些失败。

这说明“给 GUI-Reflection 加一句按 printed values 重算”还不够。下一版方法需要一个可验证的 evidence coverage loop，而不是在 parser 失败后偷偷使用 source CSV 或只保留碰巧正确的 singleton。

## C：completion history，12 cells

每个 arm/final-entity 内，H0、recent、revision 的 handoff current PNG 与 app state 相同；两个 populated history 都恰好两帧、共享最后 retry frame、最后 CLICK 与 annotation。早期语义分别是 WAIT 与 other-entity review + Back。所有 setup 和 history 都由 evaluator 建立，明确 `recovery_eligible=false`。

| cell | arm / history / final entity | 严格一个模型动作 | 解释边界 |
|---|---|---|---|
| [`c_H0_empty_solar_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H0_empty_solar_clean/steps.jsonl) | clean / empty / Solar | `PRESS_BACK`；无提交 | 当前页已是正确 Solar final review，但空 history 下模型没有直接确认。不是 failed recovery，只是 completion probe incomplete。 |
| [`c_H0_empty_solar_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H0_empty_solar_official/steps.jsonl) | official / empty / Solar | `PRESS_BACK`；无提交 | 与 clean 相同。 |
| [`c_H0_empty_wind_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H0_empty_wind_clean/steps.jsonl) | clean / empty / Wind | `PRESS_BACK`；无提交 | 没有确认错误 Wind，但单步 probe 不能证明后续会纠正。 |
| [`c_H0_empty_wind_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H0_empty_wind_official/steps.jsonl) | official / empty / Wind | `PRESS_BACK`；无提交 | 与 clean 相同；只能说没有 direct submission。 |
| [`c_H2_recent_selection_solar_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_recent_selection_solar_clean/steps.jsonl) | clean / WAIT→click / Solar | `C(Solar)`；scorer=true | evaluator 已完成正确选择；模型只完成最后确认，不能计 recovery。 |
| [`c_H2_recent_selection_solar_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_recent_selection_solar_official/steps.jsonl) | official / WAIT→click / Solar | `C(Solar)`；scorer=true | 与 clean 相同；history 支持 procedural continuation。 |
| [`c_H2_recent_selection_wind_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_recent_selection_wind_clean/steps.jsonl) | clean / WAIT→click / Wind | `C(Wind)`；scorer=false | 同样确认错误实体，说明 populated history 不是 correctness verifier。 |
| [`c_H2_recent_selection_wind_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_recent_selection_wind_official/steps.jsonl) | official / WAIT→click / Wind | `C(Wind)`；scorer=false | 与 clean 相同；直接提交错误。 |
| [`c_H2_revision_chain_solar_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_revision_chain_solar_clean/steps.jsonl) | clean / other review→Back→click Solar / Solar | `C(Solar)`；scorer=true | 早期 revision 语义没有比 recent history 带来额外可见差异；仍是 evaluator-owned completion。 |
| [`c_H2_revision_chain_solar_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_revision_chain_solar_official/steps.jsonl) | official / revision→click Solar / Solar | `C(Solar)`；scorer=true | 与 clean 和 recent-Solar 同型；不能叫轨迹纠正成功。 |
| [`c_H2_revision_chain_wind_clean`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_revision_chain_wind_clean/steps.jsonl) | clean / revision→click Wind / Wind | `C(Wind)`；scorer=false | 即使历史含 Back/revision，也确认当前错误实体；语义 reversal 没有形成持续 premise guard。 |
| [`c_H2_revision_chain_wind_official`](runs/phase3_formal/20260831T145905Z_1a0aa4a4/cells/c_H2_revision_chain_wind_official/steps.jsonl) | official / revision→click Wind / Wind | `C(Wind)`；scorer=false | 与 clean 和 recent-Wind 同型；不是 recovery。 |

C 表明最近两步历史能把当前页从“需要 Back”解释成“可以 Confirm”，但它会同样确认 Solar 与 Wind；而 recent 与 revision 的结果完全一致。换言之，模型利用的是**程序性 recency/continuation signal**，没有证据表明它保留了“哪个前提为何被撤销”的语义依赖。

## 对论文主张的严格归因

本 case 可以支持：

1. GUI-Reflection 的原生 trajectory history 能帮助完成局部 navigation reversal，并使 current-only 的 Back loop 变成 retry selection。
2. 这种推进不等于视觉前提撤销：native4 在 canonical A 的 clean/official 都重新选择 Wind，R 中 11/12 也选择 Wind，且通常在 final review 过早 `TASK_COMPLETE`。
3. premise-specific memory 能抑制立即重入，但只把错误变成停滞；需要显式的 evidence→proposition→entity→action dependency 才可能形成真正 recovery。
4. misleading geometry 的影响不是简单的“official 全坏、clean 全好”：native 的多数 pair 同型；但 A-controller 的 singleton Solar→Wind 以及 r3 native 的 Wind→Solar 都显示特定布局上存在 arm-sensitive visual capture。

本 case **不能**支持：

- “GUI-Reflection 训练相对无 reflection 训练无效”，因为 current-only 使用的是同一 GUI-Reflection checkpoint；
- “显式 printed-value controller 已优于 GUI-Reflection”，因为 controller 14/14 在 evidence stage 停止，0 次执行 UI action；
- “C 的 4 次 Solar 正确提交是 recovery”，因为正确 entity、final state 与 history 均由 evaluator setup；
- “50 格上的比例可泛化”，因为 `n_base_case=1`，六个 R 配置还是同一 case 的 synthetic diagnostics。

## 下一版方法应针对的具体缺口

按这 50 格暴露出的失败链，下一研究点不应只加强“再 Back 一次”，而应依次补齐：

1. **coverage-aware visual extraction**：必须确认五个可见类别均被枚举；不完整时在固定预算内做可见区域重读/分区重读，而不是用 hidden CSV 补全。
2. **premise invalidation 与 provenance**：Back/contradiction 要显式使旧的“Wind largest”及其 downstream action 失效，不能只在 memory 中留下“不要重复”。
3. **deterministic recomputation**：只对模型完整抽出的 printed-value records 求 argmax；同时保存 geometry observation，允许研究两者冲突，而不是让 tallest bar 覆盖数值。
4. **entity-to-action rebinding**：把 argmax entity 持续绑定到可见同名 card；R 的角色轮换正好可以检查它是否继续锁死 Wind identity。
5. **submission-state guard**：看到 `Not submitted` 时，selection 不能被 `TASK_COMPLETE` 终止；只有真实 Confirm receipt 和 scorer 才结束。
6. **semantic history 而非纯 recency**：C 表明两帧历史会强烈促成 Confirm，但对错误 Wind 也一样。新的 memory/history representation 应携带被撤销 premise 及其依赖，而不只是最近 click。

在这些组件冻结并通过当前 50-cell development panel 后，再扩大到未参与设计的多 sample official/clean pairs，才适合检验跨图表、跨布局与跨任务的泛化；当前结果最有价值的用途是定位上述可证伪的机制缺口，而不是形成一个看似精确的总体成功率。
