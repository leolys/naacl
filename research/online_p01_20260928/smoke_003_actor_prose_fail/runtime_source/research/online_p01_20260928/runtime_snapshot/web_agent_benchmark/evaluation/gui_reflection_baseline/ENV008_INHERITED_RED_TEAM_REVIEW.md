# env008 inherited-Wind F0/F3 独立红队审查

审查日期：2026-08-31  
审查对象：

- F0：`runs/targeted_env008_inherited_f0/20260830T172120Z_9fcc9516`
- F3：`runs/targeted_env008_inherited_f3/20260830T172355Z_8dc091a5`

## 结论

两次 run 的执行与证据链可作为 **env008 的定性 targeted pilot** 使用；未发现 evaluator 注入被冒充为模型动作、F3 只写事件但未进入像素、official/clean 页面不对称、模型 history 未 reset、parser 分歧、receipt 复用或隐藏 scorer 泄漏。

但恢复结论是否定的：**8 个观察 cell 中没有一个满足预先要求的完整恢复链**

`Wind review → 有效 Back/Revise → retry → Solar → final review → Confirm → scorer success`。

实际只完成了第一段结构性 reversal：两轮四格的 step 0 都真实执行了 `PRESS_BACK`。之后：

- native4 在 official 和 clean 上都重新选择 Wind；
- current-only 在 retry 页进入确定性的无状态循环；
- native4 到达 final review 后又把 `TASK_COMPLETE` 当成提交，没有点击醒目的 `Confirm selection`；
- 两轮均无 submission receipt、无 scorer record，也就没有 independent scorer success。

因此，本例支持的细粒度结论是：**GUI-Reflection 的局部轨迹机制能诱发 Action Reversal，却没有把 reversal 转化为视觉前提撤销、Mistake-Informed Reattempt 或已验证的任务完成。** native4 history 改变了失败形态，但没有改善任务结果。

## 正式逐格结果

| Probe | history | official | clean | 提交/评分 |
|---|---|---|---|---|
| F0 | native4 | `Back → Wind(pos0) → TASK_COMPLETE` | `Back → Wind(pos0) → TASK_COMPLETE` | 两格均未 Confirm；无 submission/scorer |
| F0 | current-only | `Back → 7 次相同 SCROLL → timeout` | `Back → 7 次相同 Back → timeout` | 两格均未选新动作；无 submission/scorer |
| F3 | native4 | 明看 conflict 后仍 `Back → Wind(pos0) → TASK_COMPLETE` | 明看 conflict 后仍 `Back → Wind(pos0) → TASK_COMPLETE` | 第二次 validator 仍判 Wind conflict；未 Confirm；无 submission/scorer |
| F3 | current-only | 明看 conflict 后 `Back → 7 次相同 Back → timeout` | 明看 conflict 后 `Back → 7 次相同 Back → timeout` | 两格均未选新动作；无 submission/scorer |

这里的“7 次”是同一 cell 在相同截图、每步 reset 后的确定性重复，不是 7 个独立试验。

两份 summary 各四个、共八个 `full_recovery` 均为 `false`。native4 的轨迹标签均为 `same_misleading_reentry`，current-only 均为 `recovery_incomplete`。

## 证据链审查

### 1. Authority、模型与布局

- 两轮 `agent_health.json` 都记录 official GUI-Reflection agent、审计模型路径 `GUI_Reflection_8b_SFT` 和 `temporal_len=4`；manifest 绑定 checkpoint `craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`。
- case 由 canonical `smoke17/env008` 重建，再应用固定 `cyclic_shift_1`。可见顺序是 `Wind, Hydroelectric, Solar`，Solar 确实为第三张卡、control position 2。
- scorer 与 F3 validator 对派生 pair/task identity 使用同一 layout suffix，并从 canonical token→action 映射判断；未发现 layout/scorer 错位。

布局仍有一个重要限制：`cyclic_shift_1` 虽排除了“正确 Solar 固定在首位”的捷径，却把被注入的 Wind 放在首位。模型 thought 明确点名 Wind，这减弱了“纯粹盲点第一张卡”的解释，但单一布局仍不能排除 first-option bias 对同分支重入的贡献。

### 2. Evaluator intervention 没有伪装成模型错误

八格都通过真实 Selenium coordinate click `(985, 368)` 建立外部 Wind 状态：

- browser execution 是 `/decision → /review`；
- server receipt 是 `selection(choice_1, position=0, from_state=initial_decision)`；
- post-setup state 是 `review`、Wind、`selection_count=1`、`reversal_count=0`、`submitted=false`；
- 八个 intervention transaction ID 均唯一；
- receipt 明确标记 `source=evaluator_intervention` 与 `normalized_as_agent_selection=false`；
- normalized event trace 中不存在 pre-review agent `ui_selection`。

F0 页面写的是 `Inherited selection from previous operator`，只要求 neutral re-check，没有 wrong/correct/conflict 提示。因此不能把 Wind 称为模型的自然初选，也不能把 F0 称为模型纠正自己的错误。

### 3. Handoff reset 与 history contrast 真实

每格 intervention 后的首个模型 receipt 都满足：

- `task_step_index=0`；
- image/action count 均为 0；
- image history 是空列表；
- action-history digest 是空历史 digest；
- `memory_empty_before=true`；
- receipt screenshot hash 与该格 step 0 PNG 精确 join。

每轮的两个 native4 cells（两轮共四格）在三个模型调用中的 step/history/action count 为 `[0,1,2]`；current-only 每个 cell 的 8 次模型调用都保持 `[0,0,0]`，且 `agent_reset_count=8`。这证明当前比较确实是同一 SFT checkpoint 的 native4 trajectory context 与 current-only reset，而不是跨 cell history 污染。

### 4. F3 反馈确实进入模型像素

F3 不是 runner 自报字段：人工查看四格截图确认，以下文本真实可见于 step 0 review 和 step 1 retry：

`This selection conflicts with the independently verified task outcome.`

native4 重选 Wind 后，step 2 final review 仍显示同一 conflict。Solar 同时清晰显示为 Routing option 3。模型却在两臂都输出相同语义的 Wind 点击，pixel `(985, 515)` 真实命中下移后的 Wind position 0，不是 F3 卡片造成的坐标误点。

F3 共 6 条 validator record：四条初始 Wind 和两条 native4 retry Wind。它们的 record ID 均唯一，validator file 与 normalized `outcome_validation` event 精确 join；token 均为 `choice_1`、position 均为 0、canonical action 均为 Wind、`contradiction=true`。review/retry/final-review observation 又分别绑定对应 record ID 与 polarity。

F3 有意泄露的是“当前 Wind 与独立 outcome 冲突”这一二元负反馈；它没有把 Solar/position 2 标为正确答案，也没有泄露 hidden role 或 scorer truth。因此 F3 不是自主发现视觉错误，但即使得到强 binary wrong-signal，本 checkpoint 在此轨迹中仍未据此换分支。

### 5. Matched pixels、arm 对称与顺序

在 F0 和 F3 中：

- candidate/reference 的同 arm step 0 PNG 逐字节相同；
- 同 arm step 0 raw response 逐字节相同，动作都是 `PRESS_BACK`；
- Back 后的同 arm step 1 retry PNG 也逐字节相同；
- official/clean 在 step 0 与 step 1 的 pixel-diff bbox 都是 `(44,293,745,836)`，差异只位于 chart 区域，页面文字、控件和反馈框相同。

因此，step 1 的 native4/current-only 行为分歧发生在相同模型可见像素上，history mode 是本 run 中实际改变的输入。观察到的方向却不是“history 帮助恢复”：native4 把模型推向确定的 Wind 重入，current-only 则停在无效循环。

该对称性仍不能消除所有顺序效应。两轮均使用固定 cell order `candidate_official, reference_official, reference_clean, candidate_clean`；F0 总是在 F3 之前。逐格 reset 排除了 agent state 延续，但没有把 F-level 顺序、运行时漂移或单次固定序列随机化。因此 F0/F3 只能作顺序已知的描述性 probe，不能作无混杂的 evidence-level causal estimate。

### 6. Raw action、POST 与 terminal join

两轮共 44 个 raw model step：

- official parser 与末尾 `<ACTION>` parser 全部一致；
- 没有 browser execution error、UI receipt/action mismatch 或 blocked navigation；
- 44 个 request ID 与 44 个 response ID 均唯一；
- intervention、Back 和 retry selection 的 20 个 transaction ID 均唯一；
- native4 的 Back 与 Wind click 都有对应 server transition/selection receipt。

native4 的最后一步只是模型输出 `TASK_COMPLETE`。浏览器仍停在 `final_review`，页面仍显示 `Confirm selection`，server 没有 submission receipt。故它是 completion/action-effect verification failure，不是一次漏记的成功提交。

## execution/protocol 与 task success 必须分开

两份 summary 都是：

- `execution_complete=true`；
- `intervention_validation_reasons=[]`；
- `quartet.protocol_complete=true`；
- `quartet.reportable=false`。

`execution_complete` 和 `protocol_complete` 只说明预定 cells、artifact 和 trace replay 已完成，**不等于 agent/task complete**。本次没有任何 submission/scorer record。

此外，formal quartet 仍保留一组 `*_pending` publication blockers；F3 还包含 `independent_f3_validator_store_pending`。run-local 文件与本红队手工 join 能支持本次定性审计，但不能擅自覆盖 registry 给出的 `reportable=false`。当前结果不是 publication-ready formal estimate。

“Independent scorer”也需要准确限定：scorer/validator 是同一 runner 进程中、独立重载 canonical truth 的模块，不是外部服务、盲评方或密码学隔离。更重要的是，本次模型从未提交，所以 canonical submission scorer 实际没有被调用；不能写“independent scorer 判定失败”，只能写“没有到达 scorer”。

## 可以声称什么

1. 在这个外部 Wind handoff 上，模型在 F0/F3、official/clean、native4/current-only 的每个观察 cell 都从 review GUI 输出并真实执行了 Back。
2. Back 不足以证明 belief/premise reversal；native4 在 matched retry pixels 上两次都重新进入 Wind 分支。
3. native4 history 对行为有清晰影响，但影响是把 current-only 的无状态犹豫变成确定而错误的 same-branch re-entry，而不是提高恢复成功。
4. F3 的显式 conflict 确实出现在模型输入中；在本样本/布局/顺序下，它没有改变 native4 的 Wind 重入，也没有让 current-only 产生有效 retry。
5. clean arm 也出现相同 native4 Wind 重入，说明本轮无法把该失败专门归因于 misleading chart；更像是跨视觉条件的 history/branch anchoring 与状态理解问题。
6. 到达 final review 后仍输出 `TASK_COMPLETE` 而不点 Confirm，是与选错分支相互独立的 completion-verification 缺陷。

## 禁止或需要降格的表述

- 不得称“GUI-Reflection 解决/恢复了 env008”。
- 不得称“F3 选到了 Solar”或“F3 有效解决任务”。正式模型从未点击 Solar。
- 不得称模型纠正了自己的初始错误；Wind 是 evaluator-owned external state。
- 不得把 `TASK_COMPLETE` 当作提交，或称 scorer 判定失败/成功；本轮没有 submission/scorer record。
- 不得称 native4 比 current-only 更成功，或反过来称 current-only 更安全；二者都没有正确切换或提交，只是失败形态不同。
- 不得把 Wind 重入归因于 misleading chart；clean native4 也重入 Wind。
- 不得称 F3 是自主视觉反思；它提供了显式 oracle-like binary contradiction。
- 不得称 position bias 已排除；当前布局把 Wind 放在第一张卡。
- 不得称这是 reflection-training 的因果效果；两条件使用同一个 SFT checkpoint，仅比较 inference history。
- 不得把 native4/current-only 写成“有 GUI vs 无 GUI”；两者看到同一个 review/retry UI，当前 contrast 只是 trajectory history ablation。
- 不得把 7 次确定性重复当作 7 个独立样本，也不得从一个 case/布局给出总体成功率。
- 不得把 `execution_complete=true` 或 `protocol_complete=true` 写成任务成功或 publication gate 全过；artifact 明确是 `reportable=false`。
- 不得把 F0 与后运行的 F3 直接解释为无混杂的 evidence-level 效应。

## 下一轮最有信息量的 probe

优先运行同一个 env008 inherited-Wind probe 的 `cyclic_shift_2` 镜像：可见顺序固定为 `Hydroelectric, Solar, Wind`，即 Wind position 2、Solar position 1，并在所有 official/clean、native4/current-only cells 中保持完全一致。它能直接区分：

- 若 native4 仍跨位置重选 Wind：更支持语义/历史 branch anchoring；
- 若改点第一张 Hydro：更支持 first-option heuristic；
- 若改选 Solar：说明当前 L1 失败含重要位置成分。

该复现应 counterbalance F3/F0 顺序，或至少把 F3 先运行一次，避免把 layout 与 evidence-order 同时改变。只有发生 `Solar → final review consumed → Confirm → submission → canonical scorer success` 才认恢复。

方法改进的直接切入点不是再添加一段泛化反思文字，而是把 contradiction 变成可执行的前提撤销状态，例如：持久记录 `Wind branch invalidated`、在 retry 时显式约束不得重新选择被否定分支，并在 `TASK_COMPLETE` 前强制验证真实 submission receipt。当前结果表明，像素中的自然语言 conflict 与普通 native history 都不足以稳定实现这两项约束。
