# env008 phase-2 实现独立红队审查

审查日期：2026-08-31  
审查对象：`model_server.py`、`agent_runtime.py`、`phase2_history_fixture.py`、`env008_phase2_protocol.py`、`run_env008_phase2.py`、`targeted_recovery_app.py`、`calibrate_env008_phase2.py` 及 current-build Firefox calibration  
当前权威校准：`runs/phase2_calibration/env008_phase2_calibration_20260831T094211Z/report.json`  
审查边界：pre-run implementation/calibration audit；尚未审计正式模型输出

## 最终 launch verdict

**GO，可启动 38-cell 正式 phase-2 panel。**

此前发现的 Q1 缺少 paired gate、F0 被误标 F3、Q2 action-history 未 exact join、Hydroelectric 被混入 recovery、Q3 setup chain 过弱、Q4 mask 过宽/允许空 diff 等问题，均已在本次审查所见的 live source 中修复。current-build Firefox calibration 为 **26/26 `all_passed=true`**，且下述独立机械复核全部通过。

这里的 GO 只表示 harness 已达到预注册的可证伪条件，不预判 GUI-Reflection 会成功恢复，也不使这些单 case deterministic cells 可用于总体成功率或显著性结论。正式 run 仍须自身产生 `execution_complete=true`；模型服务、浏览器或 receipt gate 的实际失败必须作为 infrastructure/harness invalid 报告，不能算模型失败。

## Block verdict

| block | verdict | 独立审查结果 |
|---|---|---|
| 38-cell matrix | GO | Q1/Q2/Q3/Q4 分别为 12/12/6/8，共 38 个唯一 key |
| Q1 F3 position | GO | p0/p1/p2 均有 official/clean × F0/F3；同 layout 两 arm 的 F0/F3 先后顺序反向；Q1 已进入 `paired_checks` 和 `execution_complete` |
| Q2 proposition/action | GO（限定解释） | P 是可见 H0 外部记录；H1/current/action/annotation 与实际 GUI-agent→Model PIL 输入均可精确绑定；Hydroelectric placebo 已加入 |
| Q3 completion-only | GO（非 recovery） | evaluator 真实建立三段 UI chain 到 final-review，随后 reset；每格严格一个模型动作；Solar core 与 Wind negative control 分开 |
| Q4 branch invalidation | GO（显式 cue） | neutral/invalidation 仅 feedback 文案不同；Wind/Hydro 仅 previous-label 像素不同；previous card 仍可点击；Hydro 不进入 recovery |
| current-build calibration | GO | `094211Z` 26/26；当前 renderer/fixture 重渲染、真实 Back/Revise/Confirm、scorer polarity 与 click receipts 均通过 |

## 1. Matrix、顺序与 Q1 identity

冻结矩阵完整覆盖：

- Q1：3 layouts × 2 arms × F0/F3，共 12 cells；Wind 在 canonical、`cyclic_shift_1`、`cyclic_shift_2` 中分别位于 p1、p0、p2。
- Q2：P∈{Solar, Wind, Hydroelectric} × 2 arms × {native4, current-only}，共 12 cells。
- Q3：Solar final-review 四格，加 official/clean Wind negative controls 两格，共 6 cells。
- Q4：previous∈{Wind, Hydroelectric} × 2 arms × {neutral control, invalidation}，共 8 cells。

Q1 的顺序不再与位置固定共变。每个 layout 中 official 与 clean 的 F0/F3 顺序相反。current calibration 的 12 个 Q1 cells 进一步证实：

- p0/p1/p2 的 evaluator selection receipt 均绑定 Wind token 与正确 control position；
- 六个 F0 均为 `source=evaluator_inherited_wind_fixture`、`intervention_semantics=neutral_recheck_on_inherited_wind`、无 validator record；
- 六个 F3 均为 `source=evaluator_f3_fixture`、`intervention_semantics=binary_outcome_signal_on_inherited_wind`，且 validator `contradiction=true`；
- F0/F3 同 layout/arm 的 display tokens、chart SHA 与 Wind token/position 由正式 `paired_checks` 比对；Q1 不再能在完全未校验的情况下随 panel `execution_complete`。

F3 是 evaluator 提供的 visible binary wrong signal，不能表述为模型自主发现图表矛盾。retry selection 后 validator polarity 被清除，final-review 不对新选择做二次答案验证。

## 2. Q2 external proposition/action exact fixture

### 可见性与 matched 输入

H0 是真实模型历史像素中的 `Prior proposition record`，实体 Solar/Wind/Hydroelectric 在原始 1280×960 与官方 448×448 history transform 后均清楚可读。它没有出现 correct/wrong、ground-truth value、expected route 或角色标签。H1 是同一个 route-decision screenshot，三条件均用同一 Wind click annotation；current review 只显示 inherited Wind，不再显示 P。

对 current-build calibration 的两 arm 重新从各自 `evaluator_before_setup.png` 调用当前 `build_proposition_frame`，保存资产与当前重渲染逐字节相同：

- official：Solar `3b61c14d21…`、Wind `00879ec4c6…`、Hydroelectric `58586205c5…`；
- clean：Solar `847acbb7b8…`、Wind `b0a1e4281a…`、Hydroelectric `d320fb19c2…`。

三组 pair 的原图 diff 与 448×448 diff 均非空且完全落在预声明 entity-text mask；两个 arm 得到相同 bbox：

- Solar/Wind：raw `[895,430,1005,459]`，448 `[312,199,353,216]`；
- Solar/Hydroelectric：raw `[896,430,1180,467]`，448 `[312,199,415,220]`；
- Wind/Hydroelectric：raw `[895,430,1180,467]`，448 `[312,199,415,220]`。

### receipt chain

fixture endpoint 默认关闭，只在 phase-2 managed service 显式启用，并要求 fresh reset、空 actions/images/memory、对齐的两帧/actions/descriptions。formal runner 对 native4 step 0 同时核验：

- `task_step_index=2`、history/action count 均为 2、memory 为空；
- raw history RGB digests 与 prime receipt 相同；
- annotations 与 prime receipt 相同；
- **`action_history_sha256_before == fixture_receipt.action_history_sha256`**；
- 实际 model-call 前两张 PIL image digest 等于预期的 annotation+resize 后 H0/H1 digest；
- H1 与 current 的组内 model-input digest 一致，H0 只按 P 变化。

这关闭了一个曾经可复现的攻击：prime 后篡改 `_action_desc[0]`，保持 frames/counts/annotations 不变。现在 step receipt 的 action digest 无法再与 fixture receipt join，cell 会失败。

current-only 条件在真实 prime 后再次 reset；step 0 receipt 必须为空 history/actions/memory，同 arm 三种 P 的 current screenshot、实际 current model input 与 deterministic raw response相同。故 P 不可能通过未清理 server state 泄漏到 current-only 输出。

边界：`model_call_input_image_sha256` 绑定的是 official GUI agent 传入 `Model` 的 PIL 序列；历史图已经加红点并 resize 到 448×448。它不是 InternVL 内部最终 tensor hash，也没有直接证明模型“相信”H0。P 仍是 evaluator-owned external record。

## 3. Q3 completion-only provenance

每个 completion fixture 都经真实 Firefox transactions 建立：

```text
Solar core: Wind selection → Revise → Solar selection → final_review
Wind negative: Hydroelectric selection → Revise → Wind selection → final_review
```

runner 同时核 kinds、实体、from/to state、selection/reversal count、三段 execution URL 与最终 snapshot；然后在 handoff 前 reset agent。formal Q3 `max_steps=1`，只有该模型 action 可以进入 raw steps/model UI receipts。Solar 的 native4/current-only 在同 arm 必须有相同 step-0 PNG、空 history receipt与相同 raw response；Wind negative 也必须恰好有一个 model call 和空 handoff history。

只有真实 Confirm POST 产生 submission receipt 后才调用 canonical scorer。`TASK_COMPLETE`、当前页面已显示 Solar、evaluator 的三笔 setup transactions都不计 completion。current calibration 中 evaluator Confirm 对 Solar scorer=true、对 Wind scorer=false，证明 scorer/layout binding 按预期工作。

所有 Q3 intervention 均为 `source=evaluator_completion_fixture`、`recovery_eligible=false`，并保存 `completion_target_action_id`。因此成功只能称 **first-action direct completion**；不能称 trajectory recovery、prevention 或 history effect。

## 4. Q4 neutral/invalidation renderer 与 missing-retry 语义

branch invalidation 文案只要求不要重复 previous option，不点名 Solar、百分比、正确性、token、position 或 validator polarity。三张卡在两条件中保持同样式且均可点击。current calibration 在四个 invalidation cells 中都故意重选 previous card，并获得真实 `selection(from_state=retry_decision)` receipt：

- Wind：两 arm 均为 `choice_1`, p2 → 同一 `choice_1`, p2；
- Hydroelectric：两 arm 均为 `choice_2`, p0 → 同一 `choice_2`, p0。

因此 invalidation 不是通过 disabled/removed card 物理强制 branch exit。

current-build 的实际 pixel bboxes 在四组中逐组一致：

| contrast | review bbox | retry bbox | allowlist |
|---|---|---|---|
| neutral vs invalidation | `[864,471,1222,535]` | `[864,374,1222,438]` | review `(850,445,1240,555)`；retry `(850,348,1240,458)` |
| Wind vs Hydro previous label | `[864,375,1186,415]` | `[941,242,1220,281]` | review `(850,350,1235,435)`；retry `(920,225,1235,300)` |

formal gate 要求 review diff 非空且完全位于 tight mask；若双方都到达 retry，则 retry diff 也必须非空且位于对应 mask。same-chart、same-card-order、previous action/role 与 `recovery_eligible` 也进入 `passed`，不再只是展示字段。

特别复核了行为导致的 missing retry：

- 若任一 cell 因模型直接 Confirm、`TASK_COMPLETE`、no-op/timeout 或其他真实行为没有进入 retry，`retry_diff=None` 并记录 `retry_pair_missing_is_behavioral=true`；这**不会**把有效的行为差异误判为 harness invalid。
- 若缺帧来自 runner/parser/navigation 错误，对应 cell 会先进入 `invalid_cells` 或 fatal path，不能借上述分支变成有效结果。
- 只有双方实际都有 retry frame 时，才要求 retry pixel parity。

Hydroelectric 的 `inherited_previous_role=neutral_or_irrelevant`、`recovery_eligible=false`，且 reducer 的 `full_recovery` 只允许 Q4 previous=Wind。Hydro→Wind 只能是 branch exit；Hydro→Solar 可记 correct rebinding/full completion component，但不得汇总进 misleading-Wind recovery。

注意 Q4 key 的 neutral control 仍使用 `_f0` 后缀，但实际 feedback spec 是 `phase2_branch_neutral_control`，页面含 geometry-matched neutral guidance。最终报告应称 **neutral control**，不要把它误写成 phase-1 的空 feedback F0。

## 5. Ownership、行为 authority 与 scorer 边界

current calibration 的 26 个 intervention IDs 全部非空且唯一；每条 intervention 自包含 `phase/probe/cell/condition/run/pair/task/layout/arm/history/feedback` identity，并针对 Q2/Q3/Q4分别保存 route ownership、completion target、previous action/role。formal summary 还会 exact join intervention 与 cell summary 的 run/cell/pair/task，并拒绝 duplicate intervention ID。

evaluator setup receipts 在 model receipt offset 之前；`direct_behavior_summary` 只读取 setup 之后、由模型 action 产生的 UI receipts和 raw model steps。Q2 fixture actions、Q3 Solar chain、Q4 previous item均明确 `normalized_as_agent_reasoning=false`、`normalized_as_agent_selection=false`。因此当前 reducer 不会把 evaluator state当成模型初选或恢复动作。

canonical scorer 仍在 runner 同进程/同 codebase，但不读取模型 thought、intervention role或结果 reducer；它只在真实 submission receipt 后由 canonical task/layout pointers重建 truth。这个边界必须在结果报告中继续明示，不能称外部独立服务 scorer。

## 6. 验证与校准排除项

- 正确 package discovery 下，baseline test suite 共运行 **156 tests：154 passed，2 skipped**；两个 skip 是 sandbox 中 loopback browser-server测试，不是 assertion failure。
- current-build Firefox calibration：`env008_phase2_calibration_20260831T094211Z`，26/26 `all_passed=true`。
- `091827Z` 是 aborted calibration；不得引用。
- `091915Z` 已因 H0 heading clipping/fixture变更 superseded；不得引用。
- `092530Z` 早于最后的 intervention/paired-gate schema修改，可作视觉历史参考，但不应再作为 current-build 全链 authority；正式材料只引用 `094211Z`。

## 7. 正式结果审查时的硬边界

正式 run 完成后仍需逐 artifact 复核，而不能仅接受顶层 `execution_complete`：

1. 38/38 cells、无 invalid/fatal/parser disagreement、所有 q1/q2/q3/q4 paired checks true；
2. Q2 native4 首次真实 model-call receipts 与磁盘 H0/H1/action fixture exact join；current-only 三 P raw response相同；
3. Q3 每格只有一个 raw model call，evaluator chain不进入 model behavior；
4. Q4 missing retry 按具体 raw action解释，不能把缺失本身说成 cue success/failure；
5. 每次 task-level success 必须有真实 selection/reversal（该 probe需要时）/final review/Confirm/submission/scorer chain。

允许的最终表述仍限于：跨位置 Wind re-entry；外部 visible proposition record 对同一 Wind route 的影响；evaluator-owned final state的首动作 completion；显式 answer-neutral branch constraint 对 branch exit、Solar rebinding与最终提交的分层影响。

禁止把这些结果写成：模型内部 premise 被直接测量或撤销、action-slip 是模型自身 slip、completion-only 是 recovery、branch invalidation 是自主反思、避开 Wind 就等于正确，或 GUI-Reflection 已在总体上解决/无法解决 misleading visualization。
