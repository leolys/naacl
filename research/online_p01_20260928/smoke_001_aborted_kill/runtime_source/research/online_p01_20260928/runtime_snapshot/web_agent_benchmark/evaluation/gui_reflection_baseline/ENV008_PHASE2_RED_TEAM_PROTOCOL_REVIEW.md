# env008 phase-2 targeted-recovery 独立红队协议审查

审查日期：2026-08-31  
状态：pre-run protocol freeze；尚未审计 phase-2 模型结果  
审查角色：独立红队 sub-agent；不修改主 runner、scorer 或结果报告

## Protocol verdict

四类 probe 都有可证伪价值，但只有在下述归因边界内才是 **GO**：

1. F3_pre L0/L1 只能检验 binary wrong-signal 下 Wind re-entry 是否跨位置保持；
2. `P=Solar/Wind` 必须是模型输入历史中真实可见、receipt-backed 的**外部 proposition record**，不能是 evaluator-only hidden label，也不能冒充模型 latent belief；
3. inherited Solar 只能检验 completion/action-effect verification，不能算 recovery 或模型初始正确；
4. branch invalidation 是显式“不要重复 previous item”的 answer-neutral action constraint，不能称自主反思，也不能通过隐藏/禁用 previous card 制造成功。

所有 phase-2 cells 继续保持单 case、deterministic、`reportable=false`。`execution_complete` 只表示采集完整。

## 最小 cell 矩阵

| probe | 最小设计 | cells | 为什么不能再减 |
|---|---|---:|---|
| Q1 F3_pre position | L0/L1 × official/clean × native4 | 4 | 这是新位置的最低描述性扩展；正式 F3 effect 还需本轮 F0 controls |
| Q2 matched proposition/action | P∈{Solar,Wind} × official/clean × {native4,current-only} | 8 | current-only 的两个 P setup 是 hidden-state/leakage sanity check，不能只跑一个 |
| Q3 completion-only | inherited Solar final-review × official/clean × {native4,current-only} | 4 | 四格按用户指定保留；主 estimand 是相同空历史输入上的首动作 completion |
| Q4 branch invalidation | previous∈{Wind,Hydroelectric} × official/clean × {F0,invalidation} × native4 | 8 | 必须有本轮 matched F0，才能把 branch exit 归于 cue 而不是 baseline |

严格最小预算为 **24 cells**，但它只回答最低描述性问题。Q1 的可解释 matched panel 应把 L0/L1 各自 F0 补齐为 8 cells；若要正式比较 p0/p1/p2，再加入本轮 L2×official/clean×{F0,F3_pre} 四格，Q1 共 12 cells。Q2 若要区分“Solar 答案 priming”与一般 P/A inconsistency detection，应再加入 `P=Hydroelectric,A=Wind` placebo 四格，Q2 共 12 cells。没有这些扩展时必须降低相应结论。

所有 block 一旦启动必须完整执行；不得根据前几格输出删格、改 feedback 或换顺序。

## Q1：native4 F3_pre 的 L0/L1 位置镜像

### 可证伪问题

phase-1 L2 中 Wind 位于 p2，official/clean native4 都在明确 binary contradiction 后重选 Wind。新 probe 把 Wind 移到 L0 p1 与 L1 p0：

- 三位置仍选择 Wind label：与 semantic/previous-label history anchoring 相容；
- 改为各 layout 的固定位置 label：支持 position heuristic component；
- 选择 Solar：说明 phase-1 L2 的位置或阶段条件可能重要；
- Wind→Hydroelectric：只算 branch exit，不算 correct re-solving。

这仍不能直接观察内部 premise，更不能把跨位置 Wind click 写成 latent Wind belief 已被证明。

### 页面与收据要求

- 使用 phase-1 的 `F3_pre_reattempt`，不是旧版 per-choice persistent F3；validator 只绑定 evaluator-owned initial Wind。
- L0/L1 Wind intervention 必须由真实 Firefox coordinate click 建立，并分别绑定 canonical token/action 与 p1/p0；handoff 前 agent reset 为空。
- initial review 与 retry 的 F3 文本必须在真实截图中完整可见；feedback region 不含 Solar、GT value、role、token、position 或 `choose` 指令。
- retry selection 后清除 polarity；final review 不允许 validator 对新选择泄漏结果。
- 每格记录 review consumed、有效 Back/Revise、first retry label/position、final review、Confirm、submission、scorer。
- 最低 4 格只能补足位置描述。要估计 F3 相对 F0 的变化，至少运行 L0/L1 × official/clean × {F0,F3_pre} 的 8 格本轮 panel；不得拿更早的 F0 当无混杂 baseline。
- 建议 cell order 跨 layout/arm/evidence 交错；若加 fresh L2，应把四个 L2 F0/F3 cells 分散在序列中，而不是全部放在最后。

### NO-GO

- 用 phase-1 L2 与新 L0/L1 直接声称无混杂位置因果效应，或只跑新 F3、不跑本轮 F0 后声称 F3 effect；
- F3 在 retry 后继续标注新选择对错；
- 把 validator contradiction 当模型自己发现错误；
- 根据 Wind 位置改变 action cards 之外的页面结构。

## Q2：matched action-slip 与 premise-error

### 首要定义修正

这里的 `P` 不能从 thought、最终 click 或 evaluator 私有字段反推。合法定义是：

```text
action-slip condition:
  visible prior proposition record P=Solar
  inherited route action A=Wind

premise-error condition:
  visible prior proposition record P=Wind
  inherited route action A=Wind
```

它操纵的是**外部轨迹中记录的 proposition history**，不是已被证明属于模型的 belief。`P=Solar` 有意携带答案信息，因此该 probe 不是 answer-neutral；它检验“已给正确上游 proposition 时，局部 recovery 是否能把错误 route 重新绑定”。

evaluator-only hidden `premise_type=Solar/Wind` 而模型历史里没有对应可见像素，属于硬性 **NO-GO**：这种设计没有改变模型可用信息，不能检验 premise/action 分解。

### 推荐的 exact-history fixture

固定 L2 与 F0 neutral review。native4 handoff 应包含完全等长的两帧显式历史：

1. `H0 prior proposition record`：同一 chart、同一固定结构；唯一允许的 pair 差异是固定文本区域中的 `Identified source: Solar` / `Identified source: Wind`，不得出现 correct/wrong、百分比、expected route 或 role；H0 对应的 history action 必须是两条件完全相同的中性 Continue/Press-Enter transition；
2. `H1 route decision`：两条件逐字节相同，H1 对应的 action history 均为同一个真实 Wind click；
3. current review：两条件在同 arm 下逐字节相同，只显示 inherited Wind、`Not submitted` 与 neutral F0 prompt，不再显示 P。

两条件必须匹配：history frame count/order、H1 PNG、action/action-description arrays、task goal、task step、memory、generation config、viewport、max-step budget 与当前 screenshot。H0 的实际 pixel diff 必须局限于预声明 proposition-text mask；DOM、URL、aria/data attributes 与 CSS 不得携带额外条件/答案。

最佳实现是服务端显式接收一份审计用 history fixture，并返回 service-owned model-input receipt：每张 history PNG digest、action-history digest、fixture id 与 ownership。fixture 必须标记 `source=evaluator_trajectory_fixture`、`normalized_as_agent_reasoning=false`、`normalized_as_agent_selection=false`，不能伪装成模型先前推理。

官方 GUI-Reflection 在送模前会给 history click 画红点并把 history frame resize 到 448×448。仅哈希原始 full-resolution PNG 不足以证明真实模型输入 matched。receipt 还必须记录 `history_image_annotations_before`（或等价字段）及**加 annotation、resize 后实际送模 history image**的 digest；两 P 条件 annotation 必须相同，448×448 输入的差异仍只能落在经同一变换后的 P 文本区域。

若不提供 exact fixture，而用真实 priming model call 建立 history，则两 P 条件的 priming raw action 与 action description 必须逐字节相同、不得执行不同副作用；否则 P pixel 与模型生成的历史动作同时变化，matched premise contrast 失效。不能筛选“恰好输出理想 premise/action”的轨迹再保留，因为那会产生 outcome-conditioned selection bias。

A=Wind 本身仍须由真实 Firefox click 与 server selection receipt 建立，current review 的 Wind state、selection count、submitted=false 与 route identity在两 P 条件一致。

### current-only falsification control

两个 P setup 都要真实建立，然后在 current review 前 reset。四个 current-only 首步 receipt 必须为空历史/空 memory、current screenshot 在同 arm 内 byte-identical、deterministic raw response 一致。若 P=Solar 与 P=Wind 的 current-only 输出不同，则存在未清理状态、页面泄漏或 nondeterminism；该 arm 的 premise contrast **NO-GO**。

### 允许的结果解释

- 只有 P=Solar native4 切到 Solar：正确 prior proposition 可帮助 action rebinding；也可能只是 Solar answer priming，不证明模型检测到 P/A mismatch，更不证明从图中自主修正 premise。
- 两 P 都重选 Wind：可见 proposition record 没有压过 inherited action/history，或模型未 uptake 该记录。
- 两 P 都选 Solar：不能归因于 P；需看 current-only/F0 baseline 与 position。
- P=Wind 退出 Wind 但选 Hydro：branch avoidance，不是 premise revision。

若研究者要进一步声称“模型识别 proposition/action inconsistency”，必须加入 `P=Hydroelectric,A=Wind` 的 wrong-but-inconsistent placebo（同样 official/clean×history 四格）。Solar 与 Hydro 两种 `P≠A` 都比 `P=A=Wind` 更容易退出 Wind，才与一般 mismatch uptake 相容；只有 P=Solar 有效更像正确实体 priming。即使加入 placebo，P 仍是 evaluator-seeded record，不是模型 latent belief。

### 硬性 NO-GO

- P 只存在 runner label、hidden DOM、文件名或分析代码；
- P=Solar 页面写 `correct`、`largest verified`、41.2% 或 route answer；
- current review、H1、action history、memory 或预算在两 P 条件不同；
- evaluator fixture 被记录成模型自身 thought/belief/action；
- priming raw action 不同却仍称唯一处理变量是 P；
- P=Solar 成功被写成自主视觉 recovery。

## Q3：inherited Solar completion-only

### 可证伪问题

evaluator 应通过真实 UI 链建立 canonical Solar **final-review**：例如 evaluator-owned `Wind review → Back/Revise → retry Solar → final review`，随后 reset agent，把无 evidence panel 的 neutral final review 交给模型。这样直接复现 full-recovery 链最后缺失的 completion component。页面不得标记 Solar 正确。核心 outcome 是：模型是否读取 `Not submitted` 并在**一个模型动作预算**内产生真实 Confirm/submission/scorer success。

成功层级必须拆开：

1. **direct completion**：唯一 final-review action 即 Confirm，产生 submission receipt 与 canonical scorer true；
2. **correct provisional but incomplete**：`TASK_COMPLETE`、no-op 或其他非 Confirm action，未 submission；
3. **correct-state corruption attempt**：输出 Back/其他动作试图离开正确 final state；主 one-step probe 到此即止。

只有第 1 类是 completion-only success。若另行研究多步 eventual completion，必须使用不同 probe identity，不能把后续循环并入这个 first-decision component test。任何结果都不是 recovery，因为整条到达 Solar final-review 的链是 evaluator-owned。

### 身份与收据要求

- 新 recovery branch/condition 必须叫 `completion_only` 或等价名称；不得复用 `STANDARDIZED_MISTAKE`、`injected_mistake_action_id` 或 `initial_susceptible=true`。
- intervention 保存完整 setup UI transactions，`source=evaluator_completion_fixture`、`injected_action_id=Solar`、`normalized_as_agent_selection=false`；analysis 中 initial role 标为 evaluator-owned correct/NA。
- official/clean × native4/current-only 四格的 step-0 history 都为空，review 结构一致；同 arm 两 history 的 step-0 PNG/raw response应相同。
- Confirm 必须是真实 POST/transaction；submission 后才调用 canonical scorer。`TASK_COMPLETE`、current Solar UI state或 thought 不计完成。
- native4/current-only 在这个 one-step handoff 前都为空，因此四格是按用户要求保留的 arm/history 重复，不得从首步相同行为推断 history effect。
- 建议另加同构 wrong-final Wind negative control：若 Solar/Wind 都 Confirm，说明主要是按钮/状态遵循能力；只有 Solar Confirm 才与内容敏感 verification 相容。负控必须独立报告，不进入 completion-success numerator。

### NO-GO

- 页面写 inherited selection is correct、verified 或建议 Confirm；
- evaluator Solar 被计作模型初选、prevention 或 recovery；
- server 残留 Solar 被计作 post-review model selection；
- 将 native4/current-only 首步完全相同的 deterministic duplicate 当独立统计样本；
- scorer 在 submission 前运行或结果返回 browser。
- 多步循环后才把结果称 first-decision completion，或把 evaluator-owned Solar/setup 写成 trajectory correction。

## Q4：answer-neutral branch invalidation

### 可证伪问题

分别由 evaluator 建立 previous Wind 与 previous Hydroelectric。review/retry 只增加一条可执行但不指向答案的约束，例如：

> Do not select the previous routing option again. Re-examine the dashboard and choose a different option.

页面可正常显示 `Previous selection: [label]`，但不得出现 Solar、correct/wrong、GT value、role、token、position 或 outcome polarity。三张 route card必须保持可点击、同样式；不得隐藏、禁用或淡化 previous card，否则“没有重入”只是 UI enforcement，不是模型 uptake。

最少运行 previous∈{Wind,Hydroelectric} × official/clean × {F0,invalidation} × native4 八格。F0 必须在 phase-2 同一 panel 重跑，不能拿旧 Wind F0 或不存在的 Hydro baseline 代替。固定同一 layout、chart 与 card order；同一 previous/arm 的 F0/invalidation pair 只允许 feedback bbox 不同，Wind/Hydro pair 的 review/retry 只允许 previous-label 文本区域和由该文本产生的必要像素不同。handoff 前均 reset，intervention 不进入模型历史。

current-only 可以作为后续 history interaction 扩展，但若加入就必须完整补成 previous×arm×feedback×history 的 16 格 factorial，不能只追补看起来会成功的条件。

### 三个互不替代的 outcome

- `branch_invalidation_compliance`：第一次 retry action != previous action；
- `correct_action_rebinding`：第一次 retry action = Solar；
- `full_completion`：Solar final review→Confirm→submission→scorer true。

Wind→Hydro、Hydro→Wind 都只满足 branch avoidance；只有 Solar 才满足 task reasoning。用两种 previous item 是为了检验模型是否执行一般“不重复”约束，而不是把“换一个”误报为正确恢复。

Hydroelectric 不是 canonical visual trap，故该组不得使用 `injected_mistake_action_id=Wind` 的分析逻辑，也不得汇总进 misleading-Wind recovery rate。统一使用 `inherited_previous_action_id`，同时 runner-side 记录其 canonical role。

### NO-GO

- feedback 点名 Solar，或用排版/颜色突出某个 alternative；
- previous card 被 disabled/removed，造成物理不可重入；
- 只跑 previous=Wind，然后把“选了别项”称 premise revision；
- 不跑同 phase-2 F0 baseline，却把 branch exit 变化归因于 invalidation cue；
- previous=Hydro 的 Wind switch 被算恢复或正确；
- Wind/Hydro 条件改变 card order、chart、预算或其他非 previous-label UI；
- 若扩展 current-only，其 reset 不为空，却把结果归因于当前 branch cue。

## 共同 identity、authority 与 artifact 要求

这些字段不是为了增加形式化负担，而是防止一个具体错误：Solar completion fixture、Hydro previous fixture或 P history 被旧 reducer 误接成模型的 inherited-Wind recovery。

每个 run/cell 至少绑定：

- `phase_id=env008_phase2`、唯一 `probe_id` 与 condition id；
- canonical pair/task pointer、layout id、arm、checkpoint、UI build、history mode；
- `intervention_semantics`：F3 Wind / external proposition-action / completion Solar / previous-item invalidation；
- 对 Q2：`recorded_proposition_entity`、`inherited_route_action_id`、history-fixture id/ownership；
- 对 Q3：`completion_target_action_id=Solar` 与 `recovery_eligible=false`；
- 对 Q4：`inherited_previous_action_id` 与 runner-side role；
- trial/run/event/intervention/submission/scorer IDs，不得跨 probe复用。

如果自定义 proposition/branch页面改变了任务语义，必须使用新的 condition/UI-variant identity；不能只靠 canonical `task_id` 或 slug 聚合。scorer仍从 canonical task pointers与 layout algorithm重建 truth；它可以与 runner 同 codebase/进程，但必须独立于 run registry，并且只在真实 submission 后调用。

每个 model step保存 raw response、两套 parser、current PNG、model-input current/history/action/memory receipts、坐标、URL、server pre/post snapshot与 UI transaction。raw `steps.jsonl` 是调用次数与 no-op 的 authority；reducer events只用于 state-transition join。

## 页面泄漏与 paired-pixel 检查

1. 对 Q1/Q3，feedback/状态区域做 DOM allowlist、hidden metadata检查与人工像素审查。
2. 对 Q2，current review同 arm/P pair必须 byte-identical；H0原图及 annotated/resized 实际模型输入的diff必须完全落在对应 proposition-text mask；H1、annotations与action arrays相同。
3. 对 Q2 current-only，同 arm两个 P setup在 reset 后的完整模型输入必须相同，而不仅是页面截图相同。
4. 对 Q3，同 arm native/current step 0截图、空 history receipt与raw response相同。
5. 对 Q4，同 previous/arm 的 F0/invalidation pair只允许 feedback bbox不同；Wind/Hydro pair的非 previous-label区域相同。
6. official/clean差异只能位于 canonical chart区域；action cards、feedback与状态文字保持相同。
7. model-free Firefox calibration必须分别走通每个新 state：合法 Back/Revise、previous card仍可点击、Solar Confirm成功、错误提交scorer false。

## Block-level 硬性失效条件

出现以下任一项，整个 matched block 都应标为 harness-invalid 并重跑，不能算模型失败或成功：

- Q2 proposition不在实际模型历史像素中，或 current页面泄露 P；
- paired输入的非处理变量不同，包括 action history、memory、step/budget或 generation config；
- evaluator action/proposition/Solar/Hydro被 normalized成模型行为；
- handoff/reset/history receipt与磁盘 PNG/action digest无法精确 join，或Q2缺少annotation及实际448×448 history-input收据；
- feedback不可见、被 clip、包含未批准答案，或 hidden DOM/URL携带 role/token；
- branch invalidation通过禁用/隐藏 previous card实现；
- layout token/position/action/scorer映射不一致；
- parser disagreement、coordinate miss、navigation containment failure、transaction/record ID复用；
- `TASK_COMPLETE` 被当 submission，或 scorer/validator结果泄漏到 browser；
- 同一 deterministic model input给出不一致结果但未原样报告；
- block未完整执行、结果后改顺序/提示，或旧 run与 phase-2 identity混池。

## 允许与禁止的最终表述

允许：

- “在 F3_pre 下，Wind label 是否跨 p0/p1/p2 重入”；
- “外部可见的 prior Solar/Wind proposition record 是否改变同一 inherited Wind action 的 reattempt”；
- “evaluator-owned correct Solar final-review 是否在首个动作被真正 Confirm”；
- “显式不重复约束能否诱发 branch exit，以及 branch exit 是否进一步成为 Solar/full completion”。

禁止：

- “模型内部 premise 被直接测量/撤销”；
- “action-slip 是模型自己的 slip”，除非未来另有真实、非筛选的模型生成链；
- “completion-only 证明视觉 recovery”；
- “branch invalidation 是自主视觉反思”；
- “避开 Wind 就等于正确”，或把 Hydro/Wind 互换算 recovery；
- “历史 L2 + 新 L0/L1 已证明位置因果效应”；
- 从这些 deterministic phase-2 cells 报总体成功率、显著性或 GUI-Reflection training effect。

只有可观察的 `review consumed → effective reversal（若该 probe需要）→ Solar action → final review consumed → Confirm/submission receipt → canonical scorer true` 才能记 task-level recovery；completion-only 的 direct Confirm应单独记为 completion success，而不是 recovery。
