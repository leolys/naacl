# env008 phase-1 GUI-Reflection 独立对抗审查

审查日期：2026-08-31  
审查角色：独立红队 sub-agent（未修改 runner、scorer、模型服务或主结果报告）  
审查范围：P0/P1/P2/P3/P4 与新版 D1 的源码、raw steps、events、截图、UI receipts、intervention/validator/scorer records、校准产物及测试。

## 总 verdict

**GO：可作为 env008 单样本、逐轨迹、`reportable=false` 的机制诊断。** 机械证据支持以下核心观察：workflow 能稳定执行 inherited review 到 retry 的局部 Back，但 24 个 inherited cells 中没有一次可观测的 Solar reattempt；native4 全部重选 Wind，current-only 全部在 retry 页循环；natural 与 D1 又暴露出正确 provisional selection 后不 Confirm 的 completion failure。

**NO-GO：不能作为总体成功率、误导图专属效应、视觉 belief/premise 已被测得、GUI-Reflection training 的因果效果或 publication-ready 结果。** 所有正式 summary 仍是 `reportable=false`；只有一个 deterministic case，F2 是近答案的 agent-reviewed upper bound，D1 只是隔离的 L2 renderer sensitivity。

各 block 的边界如下：

| block | 机械/定性诊断 | 不允许升级成的结论 |
|---|---|---|
| P0 natural | **GO**：相同初始决策下的 workflow on/off 逐格对照 | **NO-GO**：recovery 成功率或 reflection-training 因果效果 |
| P1 inherited F0 | **GO**：跨三个 Wind 位置的 external-error recovery capacity | **NO-GO**：模型自然受骗、自我纠错或 misleading-chart 独有失败 |
| P2 F1 | **GO**：L2 answer-neutral checklist uptake probe | **NO-GO**：一般 evidence-level 因果效应 |
| P3 F3_pre | **GO**：L2 binary wrong-signal uptake probe | **NO-GO**：自主发现错误或 oracle-free reflection |
| P4 F2 | **GO**：本 case×L2 的 near-answer、nonreportable upper bound | **NO-GO**：自然 benchmark 条件、外部盲审或“模型读懂后忽略数值” |
| D1 matched-render | **GO**：隔离的 L2 renderer sensitivity | **NO-GO**：canonical replication、视觉 recovery 或 renderer 普遍不影响模型 |

## 纳入与排除的 runs

纳入：

- P0 L2/L0/L1：`20260831T041504Z_c41f44dd`、`20260831T041723Z_e6ba73ef`、`20260831T041925Z_5d62dfdb`
- P1 L2/L0/L1：`20260831T042811Z_38e698be`、`20260831T043017Z_464d2b53`、`20260831T043221Z_01e13dc9`
- P2/P3 interleaved：`20260831T043503Z_d1fe5be9`
- P4 F2：`20260831T045144Z_b22a0540`
- D1：`20260831T051022Z_7cf65f87`

严格排除：

- `runs/phase1_p4_f2_formal/20260831T045017Z_33bc8d66` 是 infrastructure-aborted：只有五个运行前 JSON 与 `fatal_error.json`，无 health、run manifest、cells、model steps、events 或 summary，不能算 cell、更不能算模型失败。
- `runs/phase1_d1_matched_render_formal/20260831T045951Z_40be0f99` 已由 `SUPERSEDED_PROVENANCE.md` 标为 nonpoolable。它行为上完成了四格，但遗漏实际使用的 bold font provenance，且旧 binder 只信任自报 asset SHA，不能进入 40-cell 计数或结论。
- 旧 P0 shakedown 不满足正式 L2→L0→L1 顺序，按其 nonpoolable 标记排除。

## 机械证据计数

下表以 raw artifacts 独立重数，而不是从 narrative 或 reducer 反推：

| block | runs / cells | raw model calls | PNG | normalized events | UI / intervention receipts | scorer / validator |
|---|---:|---:|---:|---:|---:|---:|
| P0 natural | 3 / 12 | 30 | 30 step PNG | 30 | 18 model UI rows，12 unique tx | 6 scorers |
| P1 inherited F0 | 3 / 12 | 66 | 78，含 12 pre-injection | 36 | 18 model UI + 12 evaluator intervention，30 unique tx | 0 / 0 |
| P2 F1 | 1 panel / 4 | 22 | 26，含 4 pre-injection | 12 | 6 model UI + 4 evaluator intervention | 0 / 0 |
| P3 F3_pre | 同一 interleaved panel / 4 | 22 | 26，含 4 pre-injection | 16 | 6 model UI + 4 evaluator intervention | 0 scorer / 4 validators |
| P4 F2 | 1 / 4 | 22 | 26，含 4 pre-injection | 12 | 6 model UI + 4 evaluator intervention | 0 / 0 |
| D1 | 1 / 4 | 10 | 10 step PNG | 10 | 6 model UI rows，4 unique tx | 2 scorers |

完整 suite 在最终源码上独立重跑为 `Ran 150 tests`、`OK (skipped=2)`。本审查没有在受限环境外再次执行两个 loopback tests；主报告所述“随后单独通过”依赖主运行日志，而本地可复现部分是 150 tests 中其余 148 项全部通过。

## P0：natural track 证明了什么

P0 的 12 格结果可从 raw selection/submission/scorer 链重建：

- workflow-off 六格中，3 格 Solar 且 scorer true，3 格 Wind 且 scorer false；
- workflow-on 六格都形成 provisional selection，但 6/6 在 review 页输出 `TASK_COMPLETE`，没有 Confirm、submission 或 scorer；其中恰有 3 格 provisional Solar，对应同臂 workflow-off 的 3 个正确提交；
- L2 两臂 Solar，L1 两臂 Wind；只有 L0 出现 arm 差异，而且方向为 official=Solar、clean=Wind，不能支持“official misleading chart 必然使模型选 Wind”。

同一 arm/layout 的 on/off 不仅 step 0 gate 相同：六个 paired cell 在**真正作出 route 选择的 step 1** 上，PNG 与 raw response 也逐字节相同。差异发生在同一个 Solar/Wind click 被 UI 解释为 atomic submission 或 provisional review 之后。因此，P0 最强的结论是 whole-workflow completion contrast，而不是 reflection training 的效果。

P0 没有一次“先错后改”的自然恢复：选 Solar 的格子从一开始就正确；选 Wind 的 workflow-on 格子在进入 review 后没有有效 Back/Revise（各格此前在 initial page 的 step 0 no-op Back 不构成 reversal）。故 P0 中的 Solar 只能称 prevention/initial correctness，不能称 recovery。

## P1：external Wind handoff 与位置平衡

P1 的 Wind 是 evaluator 通过真实 Firefox click 建立的 provisional state，intervention receipt 标记其为 evaluator-owned，并在交接前 reset agent。它不是模型的自然初选，也不能用来计算 natural susceptibility。

机械结果为：

- 12/12 首个 `PRESS_BACK` 都有 review→retry 的 server receipt；
- 6/6 native4 随后重选 Wind，再在 final review 输出 `TASK_COMPLETE`；
- 6/6 current-only 在首次有效 Back 后又在同一 retry screenshot 上输出 7 次 no-op Back，直至 8-step timeout；
- Wind 在 L2/L0/L1 分别位于 p2/p1/p0，native4 在三处都重选同一 Wind label，因此“固定点第一张卡”或“固定点最下方卡”都不是完整解释；
- 所有 inherited 格均无 Confirm、submission 或 scorer record。

同 arm 的 native4/current-only 在 pre-injection、handoff review 与第一次 retry 三个观察点均像素一致，首步历史为空、memory 为空、task step 为 0。current-only 后续每次调用都重新 reset；其重复 Back 是相同当前像素上的确定性无状态循环。

summary 中 current-only 的残留 `final_selected_action_id=Wind`、`final_role=misleading` 或 `initial_susceptible=true` 来自 evaluator-owned server state，不是模型重新选择或自然受骗。是否重入必须读取 raw UI receipts 与 `post_review_selected_action_ids`。

## P2/P3/P4：反馈增强没有改变可观测 action

三个 L2 block 的逐格行为相同：每个 native4 都是 `effective Back → Wind(p2) → TASK_COMPLETE`，每个 current-only 都是 `effective Back → repeated Back timeout`。这三个 block 自身共有 6 个 native4 与 6 个 current-only；连同 P1 后，phase-1 inherited 汇总才是 12 个 native4 全部重选 Wind、12 个 current-only 全部没有 post-review route selection。

P2/F1 是 answer-neutral checklist，只提示重新读 label/value、核对 geometry/value 并映射 route；它没有告诉模型 Solar。P3/F3_pre 则明确泄露“已有 inherited selection 与 verified outcome 不一致”，所以它不是自主错误发现，但也没有直接给出 Solar。四个 validator 只验证初始 evaluator Wind，未被伪装成模型结果；retry selection 后 polarity 被清除。

P4/F2 是更强且不同性质的 probe：页面完整显示 `Solar — 41.2%`、`Wind — 29.8%`、`Hydroelectric — 18.5%`。真实 Firefox screenshot 的 review/retry 像素可见性已复核，official-native 的 raw click `[756,885]` 转换为 browser `[967,849]`，server receipt 精确绑定 `choice_1@p2=Wind`。final review 仍为 `Not submitted`，模型却输出 `TASK_COMPLETE`。

F2 source record 有两位 agent 对两臂 task row、CSV 与 figure 路径的六个 refs 做交叉核对，状态是 `agent_cross_checked_nonreportable`。registry 会逐项核对 CSV visible facts；它没有对 figure 做机器 OCR，也不是 blind/external human review。模型 raw thought 从未提到 41.2、29.8 或 18.5。因此允许的措辞仅是：**这些事实像素进入了模型输入，但在本 case×L2 的两格 native4 中没有改变 Wind 输出。** 不能推断模型可靠读到、理解并有意识忽略了数值。

F1/F3 在同一 panel 内交错并逐格 reset，减弱了简单的 block 顺序污染；但 F0、F1/F3、F2 仍按阶段先后运行，F2 又由 F1 失败触发。它们不能被当作无混杂的 evidence-dose causal ladder。

## D1：新版 provenance blocker 已修复，但范围必须隔离

新版 D1 run 内的 `asset_variant_manifest.json` 与当前 source manifest 逐字节相同。独立重算得到：

- official/clean canonical `source.csv` SHA 均为 `af1680…a4f6e`，字段、行序与五项 visible facts 完全一致；
- regular DejaVuSans SHA 为 `690243…0648`，bold DejaVuSans-Bold SHA 为 `d1c3ff…287b`；manifest 的 Python 3.10.12、Pillow 10.4.0 也与当前环境一致；
- 从 exact canonical CSV 在内存重渲染的 official/clean 与磁盘 1000×750 RGB PNG 逐像素一致；asset SHA 分别为 `60def1…163c` 与 `2c3ae5…9e0a`；
- official-clean actual diff bbox 是 `(112,84,921,628)`，不同像素 110,529；allowed mask 有 201,080 像素，mask 外差异为 0；
- 页面 composite 的 corresponding official-clean diff bbox 是 `(124,354,739,769)`，均位于 chart bounds；同 arm on/off 的 step 0 与真正决策 step 1 均 PNG/raw response 相同。

新版 binder 不是再次信任 manifest 自报：它读取固定 canonical CSV 路径并重算 SHA/rows，校验 regular/bold font 文件，再内存重渲染两图并要求与资产逐像素相等；随后重建 allowed mask，并重算 diff bbox/count/outside-mask。新增测试会拒绝“篡改图片并同步修改自报 SHA”的自洽替换，也会拒绝缺失 bold-font provenance 的 manifest。旧 D1 的核心 blocker 因此已实质修复。

D1 的 10 个 raw calls 与证据链均通过：10/10 disk PNG=step SHA=model receipt SHA；history RGB、action-history digest、memory、task step、request/response uniqueness 均可重算。四格 step 0 都是 initial page 上的 no-op Back；step 1 official `[802,527]→[1026,505]`、clean `[812,527]→[1039,505]`，都命中 `choice_0@p1=Solar`。workflow-off 两格 selection+submission 为同一 atomic transaction、scorer true；workflow-on 两格只到 review，step 2 `TASK_COMPLETE` 时未提交。

D1 仍有四个必须保留的限制：

1. 它只覆盖 L2 与一个 case；两臂都自然选 Solar，`visual_recovery_eligible=false`，所以它没有提供 recovery opportunity。
2. allowed mask 是 bar/value-label 几何的语义 superset，不是 exact diff mask；约 45% 的 allowed pixels 实际未改变。两个单臂 mask 文件是 provenance 展示，binder 直接使用内存重渲染的单臂 mask 验证 allowed mask；本审查另行核对了两个磁盘单臂 mask。
3. pair_group、task_instance、trial/run 与 scorer binding 含 `asset_variant:matched_render_v1`，但 `task_id` 与 slug 仍沿用 canonical。聚合时必须按 asset variant/pair suffix 过滤，不能只按 task_id/slug。
4. scorer 是同一 Python 进程、同一 codebase 中独立于 run registry 重载 canonical truth 的模块，不是外部评分系统或独立代码库。

因此 D1 只支持：“在这个 matched-render L2 四格中，两臂仍自然选 Solar；off 2/2 提交成功，on 2/2 正确 provisional selection 后未提交。”模型 thought 只说 Solar “seems most relevant”，不能称其显式比较 41.2>29.8、抵抗柱高或完成视觉纠错。

## action、receipt、scorer 与 reducer 边界

正式 raw steps 未发现 parser disagreement、browser execution error、UI receipt/action mismatch、blocked request、request/response ID 复用或跨 cell history 污染。single-attempt 的 selection 与 submission 确实是同一 transaction，`atomic_with_selection=true`；因此它不要求额外 Confirm。feedback-retry 则必须有单独 Confirm/submission receipt，`TASK_COMPLETE`、thought 或 provisional click 都不算完成。

canonical scorer 只在真实 submission 后调用。P0 的 3 个 Solar submission 为 true、3 个 Wind submission 为 false；D1 的 2 个 Solar submission 为 true。24 个 inherited cells 和所有 workflow-on completion failures 均没有 scorer record，不能写成“scorer 判失败”。F3 validator 也只证明 evaluator Wind 与 canonical truth 冲突，不证明 agent recovery。

normalized events 是状态变化/观察的语义 trace，不是逐调用账本：

- current-only 的 84 次 retry no-op Back 不进入 reducer event trace；
- P4 raw 有 22 calls，而 quartet 只列 8 个 model-step IDs；
- D1 raw 有 10 calls，而 quartet 只列 6 个 model-step IDs、4 个 response IDs，漏掉四格 step-0 no-op Back，并未完整表示两个 workflow-on terminal response。

所以动作重复次数、模型调用数、history 与 terminal semantics 必须以 `steps.jsonl` 为准；events 用于 join 真实 UI state transition、submission、scorer/validator 与 screenshot observation。`execution_complete=true` 只表示采集协议完成，不表示 task success 或 publication gate 通过。

## 可以写入结果的结论

1. 本 case 的 24 个 evaluator-owned inherited cells 中，24/24 首个 Back 有效；12/12 native4 首次 reattempt 为 Wind，12/12 current-only 没有 post-review route selection；0 Solar、0 Confirm、0 submission、0 scorer record。
2. Wind 横跨 p0/p1/p2 仍被 native4 重选，固定首卡/末卡不足以完整解释结果；previous-label/history anchoring 是与结果相容、尚待验证的机制假设。
3. natural P0 明显受 layout/action-card ordering 影响，没有一致的 official-harm pattern；workflow-on 在 3 个 paired correct-Solar cell 中把可提交成功变成未 Confirm。
4. F2 值在像素层进入输入但未改变本 case×L2 的 native4 输出；它定位了 evidence uptake/action rebinding 问题的上界，不能证明内部视觉 premise 未被撤销。
5. D1 在隔离 matched renderer 下复现 canonical L2 的逐格行为；这降低了“L2 结果完全由原文件格式/renderer 差异造成”的担忧，但不排除其他 layout/case 的 renderer sensitivity。
6. 当前最直接的 observable failure layers 是 action/label rebinding、history-conditioned navigation 与 completion/action-effect verification；内部 `bar geometry→Wind proposition→Wind route` 只能作为待检验依赖假设。

## 禁止或必须降格的表述

- 不得称 GUI-Reflection “恢复/解决了 env008”；本阶段 0 个完整 recovery。
- 不得把 evaluator Wind 写成模型自然错误、初始视觉 susceptibility 或 self-correction 起点。
- 不得把 clean/official 均出现的 inherited failure 专门归因于 misleading chart。
- 不得从没有 Solar click 推断模型内部 belief/premise 必然未改变；只能说没有可观测 action rebinding。
- 不得把 F3_pre 称为自主反思；它给了 binary wrong-signal。
- 不得把 F2 称为自然 evidence、可信外部源或 blind human review，也不得称模型“读懂后忽略”。
- 不得把 provisional selection 或 `TASK_COMPLETE` 当 submission；没有 submission 的格子没有 scorer result。
- 不得称 native4/current-only 是“有 GUI/无 GUI”或“有/无 reflection training”；两者是同 checkpoint、同当前 GUI 的 history ablation。
- 不得称 P0/D1 的初始 Solar 为 recovery，也不得据 D1 宣称模型显式使用 printed values。
- 不得把 L2、一个 case 或固定阶段顺序推广成总体成功率、显著性、普遍 renderer invariance 或训练因果效应。
- 不得把 allowed geometry mask 描述为 exact pixel-difference mask。
- 不得把 `execution_complete=true`、`quartet.protocol_complete=true` 或静态 publication blockers 的存在/消失写成 task success。

## 对主结果报告的逐条攻击

最终版本中的核心计数获得 raw artifacts 支持：40 completed cells、36 canonical-asset/protocol cells、24 inherited、24/24 effective Back、12 native Wind reattempt、12 current-only no selection、84 later no-op Back、P0 的 3 个 paired correct submissions 被 workflow-on 留在未提交状态，以及新版 D1 的 2 off success/2 on no-submit 均正确。失败 P4 与旧 D1 也已正确隔离，测试数已更新为 150。

仍建议保留以下措辞警戒；它们不改变本次 GO verdict：

1. “L2 排除位置混淆”过强。L2 只削弱旧 Wind-first/固定位置解释；真正的三位置证据来自 P1 的 L0/L1/L2 合并，而且布局顺序仍不是随机化因果实验。
2. “GUI-Reflection 学习了发现错误→Back→换动作”是训练后内部能力归因。现有证据只证明论文/训练轨迹目标包含这一模式，并观察到 Back；是否已经学得可泛化策略不能由 env008 单例断言。
3. D1 的字体描述应理解为 regular 与 bold 两个 DejaVu Sans 文件；“独立 identity”应限定到 pair/task-instance/trial/run/scorer binding，不能暗示 canonical task_id/slug 也改变。
4. “信息量分层但不偷答案”只适合 F0/F1/F3_pre；F2 已接近直接给出可算答案，应始终连写为 nonreportable evidence-assisted upper bound。
5. reducer 限制不只影响 P4/current loops；D1 也有 6/10 model-step、4/10 response 的缩减。所有完整调用计数都应指向 raw steps。

## 下一轮最有信息量的 probes

1. **F3_pre 的位置镜像**：在 L0/L1 复跑 native4 official/clean，并 counterbalance F3/F0 顺序。若仍跨 p0/p1/p2 追随 Wind，更支持 label/history branch anchoring；若随位置改变，则量化 position component。
2. **answer-neutral branch invalidation positive control**：只要求“不要再次选择 inherited item”，同时把 inherited item 在 Wind/Hydroelectric 间切换，不告知 Solar。它可区分模型完全不 uptake correction cue，还是能退出旧分支但不能重算正确实体。
3. **completion-only control**：由 evaluator 建立正确 Solar review，再交给同模型，仅测试是否读取 `Not submitted` 并点击 Confirm。这样可把 action rebinding failure 与 submission verification failure拆开。
4. **显式两阶段依赖 probe**：先让模型在 GUI 中提交“largest source” proposition，再显示 route cards；contradiction 后必须先撤销 proposition 才能 route。这样才能直接观察 `visual evidence→proposition→action` 的失效传播，而不是从最终 click 反推不可观察的 premise。

只有出现并被 receipts/scorer 连接的 `effective Back/Revise → Solar reattempt → final review consumed → Confirm/submission → canonical scorer true`，才应记为完整 targeted recovery。
