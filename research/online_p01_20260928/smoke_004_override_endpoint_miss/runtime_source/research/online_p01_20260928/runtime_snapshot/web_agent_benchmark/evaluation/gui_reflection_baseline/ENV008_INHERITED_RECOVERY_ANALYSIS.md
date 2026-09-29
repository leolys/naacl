# env008 inherited-Wind targeted recovery：逐轨迹分析

## 结论

这组实验给出了比 natural quartet 更直接的负面诊断：GUI-Reflection SFT 能稳定执行真实 Back，但不能把 Back 转化为视觉前提撤销、正确重选和最终提交。

在 evaluator 通过真实浏览器 POST 预置 Wind、随后完全 reset 模型的 8 个 cell 中：

- 8/8 首步都是真实 `PRESS_BACK`，且服务器确认从 review 返回 current-visible retry；
- native4 的 4/4 轨迹都在 retry 重新选择 Wind，随后面对 final review 直接 `TASK_COMPLETE`，没有 Confirm；
- current-only 的 4/4 轨迹都没有选择任何 route，在同一 retry 截图上重复无效 Back 或 Scroll 直到 8-step timeout；
- 0/8 改选 Solar，0/8 Confirm，0/8 submission，0/8 hidden scorer result；
- F3 明确告诉模型 Wind 与独立验证结果冲突，仍未产生任何正确重选。

因此，这个样本支持的不是“模型不会按 Back”，而是更细的三层缺口：

1. action reversal 成功，但 premise revision 失败；
2. native4 history 使模型重新执行旧的 Wind 分支，而非帮助它撤销前提；
3. 即便重新选择后，模型仍把 provisional selection 当成 terminal completion。

## 协议与干预身份

- canonical case：`synthetic140:environment35:env008`
- evaluator-owned error：Wind；不计入模型 initial selection
- 固定布局：role-blind `cyclic_shift_1`，卡片顺序为 `Wind / Hydro / Solar`
- correct Solar 位于 position 2，不再是第一项
- candidate：官方 native4 screenshot/action history
- reference：同一 checkpoint，每一步前 reset 的 true current-only
- F0：只显示 `Inherited selection from previous operator: Wind` 与 neutral recheck
- F3：在 F0 基础上显示 sanitized independent outcome contradiction，不点名 Solar
- chart arms：official misleading / clean
- checkpoint：`craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`

每个 cell 的 Wind 状态都由真实 Firefox 从 decision 页坐标点击卡片并完成 `/choose → 303 → /review` 建立。独立 intervention receipt 保存原始 token、position、transaction、浏览器 from/to URL 和 server snapshot；这条 evaluator selection 没有进入 agent `ui_selection` 事件。模型在 handoff 后 reset，首个 service receipt 均证明 image history、action history 和 memory 为空。

## 八格结果

| evidence | arm | history | 真实状态/动作序列 | 分类 |
|---|---|---|---|---|
| F0 | official | native4 | inherited Wind review → Back → retry → Wind → final review → `TASK_COMPLETE` | same misleading re-entry；无提交 |
| F0 | clean | native4 | inherited Wind review → Back → retry → Wind → final review → `TASK_COMPLETE` | same misleading re-entry；无提交 |
| F0 | official | current-only | inherited Wind review → Back → retry → 7 次无效 Scroll | timeout；无 retry choice |
| F0 | clean | current-only | inherited Wind review → Back → retry → 7 次无效 Back | timeout；无 retry choice |
| F3 | official | native4 | conflict-visible Wind review → Back → conflict-visible retry → Wind → conflict-visible final review → `TASK_COMPLETE` | same misleading re-entry；无提交 |
| F3 | clean | native4 | conflict-visible Wind review → Back → conflict-visible retry → Wind → conflict-visible final review → `TASK_COMPLETE` | same misleading re-entry；无提交 |
| F3 | official | current-only | conflict-visible Wind review → Back → conflict-visible retry → 7 次无效 Back | timeout；无 retry choice |
| F3 | clean | current-only | conflict-visible Wind review → Back → conflict-visible retry → 7 次无效 Back | timeout；无 retry choice |

F0 与 F3 各有 22 个真实 model step、18 次 reset；两个 model service log 合计正好为 44 step、36 reset，没有 HTTP 400/500。所有 action parser 与独立 final-`<ACTION>` parser 一致。

## matched history 对照

同一 arm 内，native4 与 current-only 的 handoff review PNG 逐字节相同，首个 raw model response 也相同，四组都选择 Back。Back 后的 retry PNG 在同一 arm 内仍逐字节相同；F3 两种 history 看到的 retry 页都真实包含同一 Wind、同一 contradiction 和同一 `Wind / Hydro / Solar` 布局。

分化发生在相同 retry input 上：

- native4 保留先前 review screenshot 与 `PRESS_BACK` action history，下一步点击 Wind；
- current-only 在该步前 reset，重复输出与页面状态不相容的 Back/Scroll。

这可称为本次 deterministic run 中的 inference-time history contrast。它不能称为 reflection-training `R+ / R-`，也不能排除固定运行顺序的 carryover；服务 reset receipts 只能排除显式模型 history/memory 污染。

## F3 的额外发现

F3 retry screenshot 明确显示：

> This selection conflicts with the independently verified task outcome.

Solar 同时作为第三个可见选项出现。native4 两臂仍点击第一个 Wind。独立 validator 随即再次产生 `contradiction=true`；final review 同时显示 Current selection = Wind 和同一冲突提示，模型仍输出 `TASK_COMPLETE`，没有点击醒目的 Confirm。

这表明失败不只是“没有反证”。在本例中，即便矛盾已经显式化，模型也没有把它转化为 route switch；并且它继续把内部叙述的“已经 routed”当成真实服务器完成状态。

## 可以与不能声称的结论

可以说：

- GUI-Reflection 的 Back primitive 在 inherited error 状态下 8/8 生效；
- native4 在 F0/F3、official/clean 中均稳定重入 Wind；
- current-only 没有重入 Wind，但这是因为它陷入 interface/grounding no-op，不是因为恢复更好；
- F3 outcome contradiction 在模型截图中真实可见，但未产生 Solar switch；
- compact path 本身可恢复：独立 scripted Selenium 能完成 Wind → Back → Solar → Confirm → scorer success。

不能说：

- 模型自然犯了 Wind 错误；Wind 是 evaluator-owned inherited state；
- F3 对 F0 没有“因果效果”；两级按预定阈值顺序独立运行，存在 order confound；
- native4 history 在总体上有害；这里只观察到一个 case、一个 rotated layout 的重入；
- current-only 更鲁棒；它没有正确选择或提交；
- GUI-Reflection 已被总体证明无法恢复；本实验是单样本、单 checkpoint 的 targeted qualitative diagnosis；
- `protocol_complete=true` 等于 publication-reportable。通用 reducer 仍强制 `reportable=false`，其静态 blockers 不是本 run 的逐项实现清单。

## 剩余混淆与下一步

`cyclic_shift_1` 消除了 Solar-first，但把 Wind 放在第一项。native4 的 Wind re-entry 仍可能同时包含 inherited-choice anchoring 与 first-option bias。下一轮不应重复同一布局，而应使用完整的 L0/L1/L2 循环位置筛查，尤其让 Wind 不在第一项。

更重要的是扩展到机制不同的样本。建议先运行 `b035 / health016 / b012`，再按预声明 panel 扩展至 9 个 case；不要直接把 strict94 全跑一遍，也不要把 adaptive enriched panel 的比例当总体准确率。

## 原始运行

- F0：`runs/targeted_env008_inherited_f0/20260830T172120Z_9fcc9516`
- F3：`runs/targeted_env008_inherited_f3/20260830T172355Z_8dc091a5`
- 独立对抗审查：`ENV008_INHERITED_RED_TEAM_REVIEW.md`
