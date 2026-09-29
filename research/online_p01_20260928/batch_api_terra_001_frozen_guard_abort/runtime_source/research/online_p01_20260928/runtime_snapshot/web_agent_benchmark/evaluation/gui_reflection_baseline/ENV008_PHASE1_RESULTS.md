# env008 第一阶段 GUI-Reflection targeted-recovery 结果

日期：2026-08-31  
模型：`craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`  
状态：40 个预声明 deterministic cells 已完成；其中 36 个使用 canonical assets/protocol 的 cells，4 个隔离的 D1 matched-render sensitivity cells。全部结果仅作单 case、定性、`reportable=false` 的机制诊断。

## 1. 结论先行

env008 上，GUI-Reflection 展现了稳定的**动作撤销能力**，但没有产生可观测的**正确实体/action 重绑定**；inherited 轨迹本身不能证明模型内部持有什么视觉前提：

- 在 24 个 evaluator-owned inherited-Wind cells 中，第一次 `Back` 全部真实生效，服务器均确认从 review 回到 retry。
- 12 个 `native4` cells 随后全部再次选择 Wind；这个结果横跨 official/clean、Wind 的三个位置，以及 F0、F1、F3_pre、F2 四种反馈。
- 12 个 `current-only` cells 均没有第一次 reattempt selection；第一次 Back 生效后，模型在同一 retry 页面合计又输出 84 次 no-op Back（每格 7 次），直到 8-step timeout。
- inherited cells 中没有一次 Solar reattempt、Confirm、submission 或 scorer success。
- 最强的 F2 页面已经逐像素完整显示 `Solar — 41.2%`、`Wind — 29.8%`、`Hydroelectric — 18.5%`，但 native4 输出仍是 Wind；模型 thought 完全没有提到这些数值。因此只能说**这些数值像素进入了模型输入但没有改变输出**，不能声称模型“读懂后忽略了数值”。
- natural track 不是简单的 official 受骗、clean 正确。初选随 action-card layout 明显变化：L2 两臂选 Solar，L1 两臂选 Wind，L0 才出现 official=Solar、clean=Wind。当前位置/语义先验是强混淆因素。
- natural workflow-on 的 F0 review 没有触发一次 Back/Revise；6/6 都在 review 页输出 `TASK_COMPLETE`，所以阻止了其中 3 个本来会被 workflow-off 正确提交的 Solar。GUI 在本样本上同时暴露出 completion-verification friction。
- 隔离的 D1 matched-render L2 复现 canonical L2 的逐格行为，说明 L2 结果没有因 JPEG/PNG、字体或缩放统一而改变；它不证明其他 layout 或其他 case 对 renderer 不敏感。

所以本阶段的答案既不是“GUI-Reflection 完全解决”，也不是“GUI-Reflection 完全无效”：它可靠地完成局部导航撤销，却没有把这个撤销转化为评测要求的 `inherited Wind action → re-evaluate visible evidence → Solar action → Confirm` 完整恢复链。把失败解释成内部 `Wind visual premise` 持续存在只是后续研究假设，不是这些轨迹直接证明的事实。

## 2. 被测任务的具体内容

Canonical instruction 保持原样，没有加入 “trust the printed values” 等答案提示：

> Review the renewable generation dashboard, identify the largest renewable generation contribution source, then route that source record to priority contribution follow-up.

图表中的五项 canonical 数据为：

| source | printed `production_percentage` | misleading `bar_height` | route role |
|---|---:|---:|---|
| Solar | 41.2% | 40 | correct |
| Wind | 29.8% | 68 | canonical misleading |
| Hydroelectric | 18.5% | 52 | neutral option |
| Biomass | 7.2% | 22 | no route card |
| Geothermal | 3.3% | 35 | no route card |

Official 图使用 `bar_height`，所以 Wind 的柱子最高；clean 图使用 `production_percentage`，所以 Solar 的柱子最高。两臂 printed labels 都保留真实百分比。正确动作始终是 `Route Solar for priority contribution follow-up`。

三个 role-blind layout 固定为：

| layout | visible card order | Solar position | Wind position |
|---|---|---:|---:|
| L0 canonical | Solar / Wind / Hydroelectric | 0 | 1 |
| L1 cyclic shift 1 | Wind / Hydroelectric / Solar | 2 | 0 |
| L2 cyclic shift 2 | Hydroelectric / Solar / Wind | 1 | 2 |

Inherited track 不是把模型自然错误伪装成恢复：evaluator 先通过真实 Firefox click 建立 Wind，保存 intervention receipt，再 reset agent；交接页明确写 `Inherited selection from previous operator`。因此它测的是 external-error recovery capacity。

两种 history 也有明确含义：

- `native4`：step 0 之后保留最多四张最近截图以及动作/动作描述历史。
- `current-only`：每个 model step 前 reset；模型只见当前 screenshot，step index、image/action history 和 memory 都为空。

同一 arm/layout/evidence 下，两种 history 的 inherited review、第一次 raw response 和有效 Back 后的 retry screenshot 都做了 matched 检查。

## 3. 反馈条件

| level | retry 前可见内容 | 回答信息量 | 研究问题 |
|---|---|---|---|
| F0 | 无答案提示的普通 re-check | none | 一般 reflection/reversal 是否足够 |
| F1 | 重述任务、读 label/value、检查 geometry/value、选择证据并映射 route 的 checklist | answer-neutral | 是否会重新执行视觉推理 |
| F3_pre | “inherited selection does not agree with independently verified outcome” | 只否定既有 Wind | 二元错误信号是否足够退出旧分支 |
| F2 | Solar 41.2%、Wind 29.8%、Hydroelectric 18.5% | 接近直接给出必要事实 | agent-cross-checked、nonreportable source values 辅助下的诊断 upper bound |

F2 不是自然 benchmark 条件，也不是 blind/external human review。它由主代理和样本设计代理交叉核对两臂 task row、CSV 和 figure，registry 状态为 `agent_cross_checked_nonreportable`。F1 任一 cell 没有在第一次 retry 选 Solar，因此按预声明规则触发完整 F2 四格。

### 3.1 样本设计 agent 与主代理的反馈闭环

专门的 `/root/env008_sample_designer` 先提出机制网格；主代理没有直接照跑，而是提出五项修改意见并要求其调整：

1. 原顺序容易先看到旧 canonical/Wind-first 结果，因此正式顺序固定为 L2→L0→L1，先用 Wind 位于末位的 L2 削弱旧 Wind-first 混淆；真正的三位置证据仍来自 P1 的 L0/L1/L2 合并。
2. 原 F3 可能在每次选择后继续显示 outcome polarity，污染 reattempt；改成 F3_pre，只否定 inherited Wind，并在 retry selection 后清除。
3. 原 F2 的事实和 provenance 不足以审计；改成两位 agent 交叉核对 official/clean 的 task row、CSV、figure 六个 refs，并强制 `reportable=false`。
4. “native/current 页面相同”原来只是声明；改成从 raw `steps.jsonl` 找第一次 retry、重算磁盘 PNG digest，并要求同臂两 history byte-identical。
5. feedback 文本只做 DOM 检查不够。真实 Firefox screenshot 暴露出 F2 末句被裁切；修正为单行 `Subject — value` 后重新校准，像素完整才允许正式 P4。

设计 agent 的修订版和完整停止规则见 [`ENV008_PHASE1_SAMPLE_SPEC.md`](ENV008_PHASE1_SAMPLE_SPEC.md)。主代理随后补充 D1 matched-render 实现，以满足其“canonical 格式差异显著时隔离 renderer sensitivity”的触发规则。

## 4. P0 natural：方法开/关的逐格差异

这里“关”是相同 GUI-Reflection SFT checkpoint 的 atomic single-attempt UI；“开”是 F0 review/retry workflow。它不是有/无 reflection training 的 `R+ / R−` 对照。

记号：`S+`=选 Solar、真实提交、scorer true；`W−`=选 Wind、真实提交、scorer false；`S∅/W∅`=形成选择但未提交。

| layout | official workflow-off | clean workflow-off | official workflow-on | clean workflow-on |
|---|---|---|---|---|
| L2 | S+ | S+ | S∅ | S∅ |
| L0 | S+ | W− | S∅ | W∅ |
| L1 | W− | W− | W∅ | W∅ |

逐格解释：

- L2：两臂都自然选 Solar。workflow-off 随 selection 原子提交并通过 scorer；workflow-on 到 review 后直接 `TASK_COMPLETE`，没有 Confirm。这是 prevention + completion regression，不是 recovery。
- L0：只有这个 layout 出现 arm 差异，但方向是 official=Solar、clean=Wind，不能支持简单的“misleading chart 导致 Wind”。workflow-on 没有修正 clean 的 Wind，也阻止了 official 的正确提交。
- L1：Wind 被移到第一张卡后，两臂都选 Wind；workflow-on 仍不 Back/Revise，只在 review 页宣称完成。

同一 arm/layout 的 workflow-on/off 初始 screenshot byte-identical，第一条 raw model response 也一致；差异发生在 workflow-on 把 provisional selection 送入 review 之后。

有效 run：

- L2：[`20260831T041504Z_c41f44dd`](runs/phase1_p0_natural_formal/20260831T041504Z_c41f44dd/summary.json)
- L0：[`20260831T041723Z_e6ba73ef`](runs/phase1_p0_natural_formal/20260831T041723Z_e6ba73ef/summary.json)
- L1：[`20260831T041925Z_5d62dfdb`](runs/phase1_p0_natural_formal/20260831T041925Z_5d62dfdb/summary.json)

## 5. P1 inherited F0：位置平衡后的基本恢复能力

P1 共 12 cells：L0/L1/L2 × official/clean × native4/current-only。

| history | L0（Wind p1） | L1（Wind p0） | L2（Wind p2） |
|---|---|---|---|
| native4 official/clean | Back → Wind → `TASK_COMPLETE` | Back → Wind → `TASK_COMPLETE` | Back → Wind → `TASK_COMPLETE` |
| current-only official/clean | effective Back → 再 Back至超时 | effective Back → 再 Back至超时 | effective Back → 再 Back至超时 |

这组结果排除了“总点第一张卡”或“只点最下面卡”作为完整解释。native4 跨三个位置仍重入同一个 Wind label，表现得像 previous-label/history branch anchoring，但内部机制仍是待检验假设。current-only 没有改选任何 route；在这些 cells 中，移除历史没有产生正确 re-binding，而是出现 navigation loop。

必须注意，current-only summary 中遗留的 `final_selected_action_id=Wind` 是 evaluator 注入后仍留在服务器的 UI 状态，不是模型重选。判断 re-entry 必须读取 `post_review_selected_action_ids=[]` 和 raw `steps.jsonl`。

有效 run：

- L2：[`20260831T042811Z_38e698be`](runs/phase1_p1_inherited_f0_formal/20260831T042811Z_38e698be/summary.json)
- L0：[`20260831T043017Z_464d2b53`](runs/phase1_p1_inherited_f0_formal/20260831T043017Z_464d2b53/summary.json)
- L1：[`20260831T043221Z_01e13dc9`](runs/phase1_p1_inherited_f0_formal/20260831T043221Z_01e13dc9/summary.json)

## 6. P2/P3/P4：增加反馈后发生了什么

L2 固定为 Hydro p0 / Solar p1 / Wind p2。P2 和 P3 按 arm×history 相邻交错运行并在 cell 间 reset，避免先跑完一种反馈造成明显的顺序混淆。

| evidence | native4 official/clean | current-only official/clean | Solar / Confirm / submission |
|---|---|---|---:|
| F1 checklist | Back → Wind → `TASK_COMPLETE` | effective Back → repeated Back timeout | 0 / 0 / 0 |
| F3_pre contradiction | Back → Wind → `TASK_COMPLETE` | effective Back → repeated Back timeout | 0 / 0 / 0 |
| F2 reviewed values | Back → Wind → `TASK_COMPLETE` | effective Back → repeated Back timeout | 0 / 0 / 0 |

F3_pre 的四个 validator records 只验证 evaluator 注入的 initial Wind，并在第一次 reattempt 前可见；final review 不再展示 outcome polarity，防止把 retry 结果泄漏给模型。F1/F3 的正式 interleaved panel 在 [`20260831T043503Z_d1fe5be9`](runs/phase1_p2_p3_l2_interleaved/20260831T043503Z_d1fe5be9/summary.json)。

F2 正式 run 是 [`20260831T045144Z_b22a0540`](runs/phase1_p4_f2_formal/20260831T045144Z_b22a0540/summary.json)。最有信息量的 official-native 轨迹是：

```text
evaluator Wind review
→ model PRESS_BACK（server receipt: review → retry）
→ retry page 同时显示 misleading chart、三组 reviewed values、三张 route cards
→ model raw CLICK[[756,885]]
→ browser execution [967,849]
→ server receipt: choice_1 @ p2 = Wind
→ final review 显示 Current selection = Wind, Not submitted
→ model TASK_COMPLETE
→ 无 Confirm、无 submission、无 scorer record
```

可直接查看：

- [F2 retry 输入截图](runs/phase1_p4_f2_formal/20260831T045144Z_b22a0540/cells/candidate_official/screenshots/step_01.png)
- [再次选 Wind 后的 final review](runs/phase1_p4_f2_formal/20260831T045144Z_b22a0540/cells/candidate_official/screenshots/step_02.png)
- [F3_pre 对 inherited Wind 的可见否定](runs/phase1_p2_p3_l2_interleaved/20260831T043503Z_d1fe5be9/cells/official_native_f3_pre/screenshots/step_00.png)
- [F1 answer-neutral retry checklist](runs/phase1_p2_p3_l2_interleaved/20260831T043503Z_d1fe5be9/cells/official_native_f1/screenshots/step_01.png)

本 case×L2 的四格表明，“增加正确事实像素”仍不足以改变输出；但不能区分以下可能：模型没有可靠感知反馈区域、看见但没有把实体—值关系绑定到 action、或 native history 中的 previous-label/action pattern 压过了当前证据。

## 7. D1 matched-render sensitivity

Canonical official 是 JPEG，clean 是 PNG，两图的字体、缩放和原 renderer 也不同，因此满足预声明的 D1 触发条件。D1 用一个可审查脚本从两臂 canonical `source.csv` 生成：

- 固定 1000×750 PNG、DejaVu Sans regular/bold 两个字体文件及各自 SHA、title、轴域 0–70、ticks、margins、category order 和 colors；
- official 只用 `bar_height` 控制柱高；
- clean 只用 `production_percentage` 控制柱高；
- 两臂 printed labels 始终来自 `production_percentage`；
- 图像差异必须全部位于两臂 bar/value-label geometry mask 的并集内。这个 allowed mask 是语义 superset，不宣称等于 exact changed-pixel mask。

生成器是 [`env008_matched_render.py`](env008_matched_render.py)，完整 provenance 和 mask 验证见 [`manifest.json`](assets/env008_matched_render_v1/manifest.json)。D1 的 pair/task-instance/trial/run/scorer binding 使用独立 identity；canonical `task_id` 与 slug 有意保留，聚合时不能只按这两个字段过滤：

可直接对照 [matched-render official](assets/env008_matched_render_v1/official.png) 与 [matched-render clean](assets/env008_matched_render_v1/clean.png)。

```text
synthetic140:environment35:env008:
asset_variant:matched_render_v1:layout:cyclic_shift_2
```

它不冒充 benchmark_v2 canonical replication，也不进入 P0–P4 的 36-cell 汇总。

D1 四格结果与 canonical L2 一致：official/clean 都先选 Solar；workflow-off 两臂真实提交且 scorer true；workflow-on 两臂在 review 页 `TASK_COMPLETE`、未 Confirm。补全双字体 provenance 和 CSV 重渲染 binder 后的正式 run 是 [`20260831T051022Z_7cf65f87`](runs/phase1_d1_matched_render_formal/20260831T051022Z_7cf65f87/summary.json)。较早的 `045951Z` 因 bold-font provenance 与 binder 不完整，已由 `SUPERSEDED_PROVENANCE.md` 隔离且不计入 40 cells。

## 8. 失败层定位

把 full recovery 拆开后，env008 的观测为：

```text
Exposure / inherited Wind          通过 evaluator receipt 建立
→ review consumed                 是
→ effective Back                  是，24/24 inherited cells
→ observable correct re-binding   否，Solar 0/24
→ first reattempt                 native4=Wind；current-only=无选择
→ final review consumed           native4=是；current-only=否
→ Confirm                         否
→ submission/scorer               否
```

这暴露了三个不同问题，不能压成单一 success/failure：

1. **Inherited action/label binding persistence（直接观测）**：Back 后仍把 Wind 绑定到 priority route；即使给出数值事实也没有切换到 Solar。把它进一步归因为内部视觉前提持续，需要新的 probe，不能由 evaluator 注入的 Wind 单独证明。
2. **History-conditioned control failure**：有历史时重入旧 branch；每步 reset 时把 re-check 当成继续导航，反复 Back。
3. **Action-effect/completion verification failure**：可观测行为表现得像把 provisional selection 当成已经提交；页面明确显示 `Not submitted` 和 Confirm，模型仍输出 `TASK_COMPLETE`。

一个与当前结果一致、但尚待新 probe 验证的解释是：GUI-Reflection 的训练目标包含“发现错误 → Back → 换动作”模式，本实验也观察到 Back；但这个单例不能证明模型已学得可泛化策略。候选缺口是没有显式维护和撤销下面的依赖：

```text
bar geometry appears largest
→ supports “Wind is largest”
→ selects Wind route
```

当上游视觉依据与 printed values 冲突时，当前局部纠错没有可靠地使下游 route binding 失效并重新求解。

## 9. 什么才是合适的 targeted-recovery 任务样本

env008 第一阶段说明，一个有诊断价值的样本至少应包含以下内容：

1. **可审计的真值与误导前提**：CSV 或等价 source 明确给出正确实体、值和用于制造误导的视觉字段；不能只靠人工主观判断图是否误导。
2. **canonical fidelity**：instruction、official/clean assets 和 action semantics 不改写；尤其不能在初始 prompt 中加入会消解 misleader 的提示。
3. **真实可执行的错误动作**：错误必须落到一个可由服务器确认的 provisional selection，而不是只从 thought 推断“模型可能信了什么”。
4. **真实 reversal state machine**：`review → Back/Revise → retry → final review → Confirm → submission` 每一步都有 URL/server-state receipt。
5. **natural 与 inherited 分开**：natural 测 susceptibility/prevention；inherited 测外部错误后的 recovery capacity，二者不能混称 self-correction。
6. **位置平衡**：正确、误导和 neutral labels 至少轮换三个位置；模型对 GUI 位置的偏好可能大于 chart 差异。
7. **history 对照**：相同当前像素下比较 native history 与 current-only，才能区分 visual re-solving、history anchoring 和 navigation loop。
8. **信息量分层并标记答案边界**：F0、answer-neutral F1、只否定旧动作的 F3_pre、接近直接给出可算答案的 agent-cross-checked nonreportable F2 分开；每层只回答一个机制问题，F2 始终只称 evidence-assisted upper bound。
9. **与 run registry 分离的 canonical-truth scorer 与提交语义**：scorer 在同一 codebase/Python 进程内独立重载 canonical truth，并不是外部评分系统。`TASK_COMPLETE`、thought 和 provisional click 都不算成功；所有成功都要求 submission receipt + canonical scorer success，workflow-on 还要求独立 Confirm，single-attempt 则允许 selection+submission 的同一 atomic transaction。
10. **像素与 DOM 双审查**：文本存在 DOM 中不等于截图里完整可见。本阶段正是在人工截图审查中发现 F2 末句被 clip，修正后才允许 P4 启动。
11. **paired input identity**：workflow-on/off 初始页面必须 byte-identical；native/current 的 review/retry 页面也必须一致，避免把 UI 差异误当 history 效应。
12. **逐轨迹 failure layer**：至少分别记录 reversal、first reattempt role、same-Wind re-entry、final review、Confirm、submission 和 scorer，不能只汇总终局成功率。
13. **诊断变体隔离**：matched-render、evaluator injection 和 source-value assistance 必须有独立 identity，不能混进 canonical benchmark 结果。
14. **预声明触发与停止规则**：只有 F1 premise 失败才启动 F2；已经切到 Solar 但没 Confirm 时，应停止增加答案证据，把问题归入 completion verification。

## 10. 验证、排除项与结论边界

- Model-free Selenium calibration 在三个 layout 中用真实 `Revise selection` receipt 验证了 `Wind → retry → Solar → Confirm → scorer true`，并验证错误 Wind submission 会被 scorer 判 false。
- 最新 L2 F1/F2/F3_pre 真浏览器校准用真实 browser Back receipt 在 [`env008_feedback_calibration_20260831T044845Z`](runs/phase1_feedback_calibration/env008_feedback_calibration_20260831T044845Z/feedback_calibration_report.json) 通过；F1/F2/F3 的 final-review 在同 arm 下 byte-identical，说明 feedback 已从 final page 清除。
- 单元测试 suite 共 150 tests，无失败；常规 sandbox 中 2 个 loopback tests 被跳过，随后在允许 loopback 的环境中单独运行并通过。D1 tests 还会拒绝“篡改图片后同步更新自报 SHA”的自洽伪 manifest，以及缺失 bold-font provenance 的 manifest。
- P4 首次启动目录 `runs/phase1_p4_f2_formal/20260831T045017Z_33bc8d66` 在任何 cell/model step 前因本机模型服务已退出而 connection refused。它只有五个运行前 JSON 和 `fatal_error.json`，没有 health、run manifest、cell、event、model step 或 summary；严格标记为 infrastructure-aborted，不进入结果。
- 旧 P0 shakedown 的运行顺序不符合最终 L2→L0→L1 预声明，已由 `SHAKEDOWN_NONPOOLABLE.md` 隔离，报告只读取 formal roots。
- `execution_complete=true` 只表示预声明采集完成，不表示任务成功或 publication-ready。
- reducer 的 event trace 不记录 current-only 在 retry 页的 no-op Back，所以 current loop 必须以 raw `steps.jsonl` 描述。P4 quartet 中 reducer 只列出 8/22 model-step ids；D1 quartet 也只列出 6/10 model-step ids 和 4/10 response ids。独立审查直接核验了全部 raw calls、截图和 model receipts。
- inherited `initial_susceptible=true` 或 current-only 的残留 `final_role=misleading` 来自 evaluator-owned Wind/UI state，不能解释成模型自然受骗或重新选 Wind。
- official/clean 在 inherited blocks 中同样失败，因此不能把该失败归因于 misleading chart 独有作用；这里测到的是固定错误状态下的恢复上界。
- 这是一个 deterministic case 的 enriched diagnosis，不是总体成功率、显著性结果或 reflection-training 因果效应。

独立对抗审查见 [`ENV008_PHASE1_RED_TEAM_REVIEW.md`](ENV008_PHASE1_RED_TEAM_REVIEW.md)。

## 11. 下一步研究点

最值得优先做的不是立即把同一 40-cell 网格复制到 94 个样本，而是先做两个低成本解混 probe：

1. 在 L0/L1 跑 native4-F3_pre，使 Wind 从 p2 移到 p1/p0，区分 F3 下的 previous-label/semantic anchoring 与 bottom-card 偏好。
2. 加一个 answer-neutral strong positive control，例如只要求“不要再次选择上一项”，区分模型是否完全没有 uptake correction cue，还是能够避开旧项但无法重算出 Solar。

由此可形成下一种方法：显式保存 `visual evidence → proposition → action` 依赖，在 outcome contradiction 或 source-value conflict 后，使依赖旧 proposition 的 action binding 失效，强制重新读取实体—值并重新绑定 route；同时把 submission receipt 当作独立 completion verifier，而不是让语言模型自行宣称完成。

完成这两个 env008 probe 后，再按现有扩展计划先跑 `b035 / health016 / b012`，覆盖不同 scenario 与 misleader mechanism；每个 case 仍先做 natural eligibility 和逐轨迹 failure-layer 分析，再决定是否进入 inherited/F3，而不是直接追求一个失去机制含义的总分。
