# ENV008 Phase 2：逐 cell 独立分析

## 结论先行

这组实验支持一个比“GUI-Reflection 成功/失败”更精确的结论：在 env008 这个单一、确定性解码的样本上，GUI-Reflection checkpoint 很稳定地执行了局部导航撤销，但没有稳定地把“旧分支不成立”转化成新的证据判断与实体/action 重绑定。

最直接的证据有三组：

1. Q1 的 12 个 cell 全部执行 `Back → 再选 Wind → TASK_COMPLETE（未提交）`。F3 已明确告知 inherited Wind 与独立验证结果不一致，但相对 F0，在 3 个按钮排列和 official/clean 两个图表 arm 下均没有改变实体动作。
2. Q2 把历史命题唯一地改为 Solar、Wind 或 Hydroelectric。有历史时 6/6 都直接确认 inherited Wind，并由 scorer 判错；无历史时 6/6 都先 Back、随后在 retry 页面继续 Back 直至 timeout。历史改变了“继续/撤销”的局部流程模式，却没有让动作随命题实体改变。
3. Q4 对真正的错误旧分支 Wind 明示“不要再次选择 previous routing option”，official 和 clean 两个 matched cell 仍都重新选择 Wind。Hydroelectric placebo 则说明“离开旧分支”也不等于“找到正确分支”：4 个 Hydro cell 都离开 Hydro，但 3 个转入错误 Wind，只有 `official + invalidation` 转入 Solar，且仍未提交。

因此，当前最稳妥的论文表述是：**action-level reversal is observable, but premise-conditioned entity/action rebinding is not reliable**。不能写成“GUI-Reflection 完全不能纠错”，因为 Q4 有一个 evaluator-owned Hydro placebo cell 选到了 Solar；也不能写成“完整 GUI-Reflection 方法普遍失败”，因为本轮只有一个任务、没有普通 agent checkpoint 对照，而且所有模型调用的 memory 均为空。

## 审阅范围与记号

独立审阅对象为：

`runs/phase2_formal/20260831T095625Z_797a0392`

我没有只读顶层 summary，而是逐 cell 检查了：

- 38 份 `intervention.json`；
- 38 份 `summary.json`；
- 96 条 `steps.jsonl` 原始模型输出、官方 parser 结果、执行前后 UI snapshot 和 model receipt；
- Q2 六份 `scorer_records.jsonl`；
- Q1/Q2/Q3/Q4 的 matched-pair pixel/hash checks；
- 代表性 H0/H1/current 截图及 official/clean 图表。

运行完整性方面，38/38 cell 完成记录，96/96 step 无 execution error、parse error 或 parser disagreement；`invalid_cells`、`paired_check_failures`、`intervention_identity_failures` 均为空。这里的“完整”只表示 artifact 可审计，不表示任务成功。冻结协议本身将本轮标为 `reportable=false`，因此下面的次数只作同一样本内的描述，不能当作独立样本成功率或显著性结果。

env008 的任务真值是 Solar：打印值 Solar 41.2% 最大；official 图故意把 Wind 29.8% 的柱子画得最高，clean 图恢复与数值一致的柱高。动作真值为 `Route Solar for priority contribution follow-up`，Wind 是 misleading action，Hydroelectric 是 neutral/irrelevant action。

下表采用以下记号：

- `B`：模型输出 `PRESS_BACK`；
- `Sel(X@k)`：UI receipt 确认模型选择实体 X，位于第 k 个 action card；
- `Confirm(X, false)`：模型点击 Confirm，submission receipt/scorer 确认提交 X 且失败；
- `TC(no-submit)`：模型输出 `TASK_COMPLETE`，但 UI 没有 submission receipt；
- `B×3(no transition)`：已在 retry 页面后又连续三次 Back，页面没有进一步状态迁移。

## Q1：可见 F3 contradiction 是否改变 reattempt

F0 没有 outcome feedback；F3 显示：“The inherited selection does not agree with the independently verified task outcome. Re-examine the chart before submitting.” 该提示只否定 Wind，不泄露 Solar。三种 layout 把 Wind 分别放在第 2、第 1、第 3 个 card，因而可排除固定点击位置这一种解释。

| Cell | 图表 / feedback | 原始可观测轨迹 | 结果 |
|---|---|---|---|
| `q1_canonical_official_f0` | misleading / F0 | `B → Sel(Wind@2) → TC(no-submit)` | 有效撤销；重入 Wind |
| `q1_canonical_official_f3` | misleading / F3 | `B → Sel(Wind@2) → TC(no-submit)` | F3 未改变实体动作 |
| `q1_canonical_clean_f0` | clean / F0 | `B → Sel(Wind@2) → TC(no-submit)` | 有效撤销；重入 Wind |
| `q1_canonical_clean_f3` | clean / F3 | `B → Sel(Wind@2) → TC(no-submit)` | F3 未改变实体动作 |
| `q1_cyclic_shift_1_official_f0` | misleading / F0 | `B → Sel(Wind@1) → TC(no-submit)` | 跟随 Wind，而非固定位置 |
| `q1_cyclic_shift_1_official_f3` | misleading / F3 | `B → Sel(Wind@1) → TC(no-submit)` | F3 未改变实体动作 |
| `q1_cyclic_shift_1_clean_f0` | clean / F0 | `B → Sel(Wind@1) → TC(no-submit)` | 跟随 Wind，而非固定位置 |
| `q1_cyclic_shift_1_clean_f3` | clean / F3 | `B → Sel(Wind@1) → TC(no-submit)` | F3 未改变实体动作 |
| `q1_cyclic_shift_2_official_f0` | misleading / F0 | `B → Sel(Wind@3) → TC(no-submit)` | 跟随 Wind，而非固定位置 |
| `q1_cyclic_shift_2_official_f3` | misleading / F3 | `B → Sel(Wind@3) → TC(no-submit)` | F3 未改变实体动作 |
| `q1_cyclic_shift_2_clean_f0` | clean / F0 | `B → Sel(Wind@3) → TC(no-submit)` | 跟随 Wind，而非固定位置 |
| `q1_cyclic_shift_2_clean_f3` | clean / F3 | `B → Sel(Wind@3) → TC(no-submit)` | F3 未改变实体动作 |

六个 F3/F0 matched pair 的 action type、实体和提交状态完全相同。所有首步 raw response 也完全相同：模型把 Back 描述成“回到 dashboard 开始任务”，没有在可观测文本中提到 F3 contradiction。第二步措辞会因 layout/arm 略有变化，但都明确声称要选择 Wind；第三步都声称任务已完成，实际 UI 仍在 final review。

### Q1 能说明什么

Q1 是目前最干净的“导航撤销 vs 实体重绑定”区分：Back 的 transition receipt 在 12/12 cell 中都存在，但 Solar selection 和 submission 在 12/12 中都不存在。按钮换位后仍精确追踪 Wind，也说明结果不是固定坐标复现。

Q1 不能单独证明模型“保留了某个 latent premise”。同样的行为也可能来自 inherited-selection 文案锚定、对 Wind 的词汇/任务先验，或对 F3 区域注意不足。它证明的是可观测 action binding 没有改变，而不是内部信念的唯一机制。

## Q2：历史命题是否控制后续实体动作

Q2 的 native4 输入是 evaluator-owned 的可见两帧历史加当前页：

1. H0：`Prior proposition record — Identified source: {Solar | Wind | Hydroelectric}`；
2. H1：相同 cyclic-shift-2 decision UI，并有一次真实 Wind click/action；
3. current：Wind 已 inherited 的 review UI。

三个 H0 只有实体词像素不同；raw 和 448 resize 的 pair diff 都落在预注册 mask 内。H1、current、action history 以及 click annotation 在同一 arm 内一致，step-0 model receipt 也确实接收到 `[H0, H1, current]`。current-only 则在相同 current 页面上清空历史。

| Cell | 传给模型的 H0 | 原始可观测轨迹 | Scorer / 状态 |
|---|---|---|---|
| `q2_p_solar_official_native4` | Solar | `Confirm(Wind, false)` | 提交 Wind，失败 |
| `q2_p_wind_official_native4` | Wind | `Confirm(Wind, false)` | 提交 Wind，失败 |
| `q2_p_hydroelectric_official_native4` | Hydroelectric | `Confirm(Wind, false)` | 提交 Wind，失败 |
| `q2_p_solar_clean_native4` | Solar | `Confirm(Wind, false)` | 提交 Wind，失败 |
| `q2_p_wind_clean_native4` | Wind | `Confirm(Wind, false)` | 提交 Wind，失败 |
| `q2_p_hydroelectric_clean_native4` | Hydroelectric | `Confirm(Wind, false)` | 提交 Wind，失败 |
| `q2_p_solar_official_current_only` | 不传 H0/H1 | `B → B×3(no transition)` | timeout，无提交 |
| `q2_p_wind_official_current_only` | 不传 H0/H1 | `B → B×3(no transition)` | timeout，无提交 |
| `q2_p_hydroelectric_official_current_only` | 不传 H0/H1 | `B → B×3(no transition)` | timeout，无提交 |
| `q2_p_solar_clean_current_only` | 不传 H0/H1 | `B → B×3(no transition)` | timeout，无提交 |
| `q2_p_wind_clean_current_only` | 不传 H0/H1 | `B → B×3(no transition)` | timeout，无提交 |
| `q2_p_hydroelectric_clean_current_only` | 不传 H0/H1 | `B → B×3(no transition)` | timeout，无提交 |

native4 六个首步 thought 都以“我已经选择了 Wind”为前提并点击 Confirm。Solar 命题没有触发 revise/Solar；Hydroelectric 命题也没有触发 revise/Hydroelectric；Wind 命题与 inherited action 一致，但提交仍因任务真值为 Solar 而失败。因此，H0 命题对 action identity 的 matched effect 为零，而 temporal context 对局部流程模式的 effect 很大：从 Back/loop 变为 confirm/submit。

这个结果不能简化为“history 有害”。H1 自身包含最近的 Wind selection/action，因而 native4 可能优先延续最近动作，而不是读取更早的 H0。更准确的解释是：**当前历史编码能够恢复工作流连续性，却没有表现出对较早 proposition 的条件化重绑定**。这正是后续方法需要显式维护 `evidence → proposition → action` 依赖关系的地方。

Q2 仍有一个重要外推限制：H0 是 evaluator 制作的 GUI proposition record，不是模型自己生成的 `MEMORIZE` 内容，也不是论文训练分布中已证实的 reflection 格式；GUI-agent-to-Model 的 PIL hash 已绑定，但 artifact 明确没有记录到最终 InternVL tensor 边界。因此它是一个强的 action-sensitivity probe，而不是“模型内部信念”的直接读取。

## Q3：给定 final review，模型能否单独完成提交

Q3 由 evaluator 先构造 final-review 状态，只允许一个模型动作。Solar 是正确 completion target；Wind 是负对照。特别要注意：虽然 cell 名中保留 `native4/current_only`，Q3 的模型 handoff 在两者中都被 reset，step receipt 均为 `history_image_count_before=0`、`action_count_before=0`。因此这里不能把 native4/current-only 当成真正的 history ablation。

| Cell | Final selection | 原始可观测轨迹 | 结果 |
|---|---|---|---|
| `q3_final_solar_official_native4` | Solar（正确） | `B(final-review → retry)` | 未 Confirm |
| `q3_final_solar_official_current_only` | Solar（正确） | `B(final-review → retry)` | 未 Confirm |
| `q3_final_solar_clean_native4` | Solar（正确） | `B(final-review → retry)` | 未 Confirm |
| `q3_final_solar_clean_current_only` | Solar（正确） | `B(final-review → retry)` | 未 Confirm |
| `q3_final_wind_official_native4` | Wind（错误负对照） | `B(final-review → retry)` | 未 Confirm |
| `q3_final_wind_clean_native4` | Wind（错误负对照） | `B(final-review → retry)` | 未 Confirm |

六个 raw response 完全相同，均称需要返回 dashboard“开始任务”。这说明 final-review 当前截图本身不足以让该 checkpoint 可靠识别“正确实体已选好，现在应 Confirm”的阶段；它也没有根据 Solar/Wind 正误区分首动作。

但 Q3 不能支持“模型不会提交”的绝对结论：Q2 的 native4 六个 cell 都成功执行了 Confirm/submission，只是提交了错误 Wind。真正的差异是上下文：有最近 Wind click/action 的 Q2 会 Confirm；空 handoff 的 Q3 会 Back；经历 Back→selection 的 Q1/Q4 则在 final review 直接输出 TASK_COMPLETE 而没有点击 Confirm。由此可见，completion 行为本身也是 trajectory-conditioned，必须与实体纠错分开评测。

## Q4：显式禁止旧分支，是否足以实现 branch exit 和正确重绑定

Q4 在同一 cyclic-shift-2 layout 中，对 review 和 retry 两个状态加入位置匹配的 action-neutral 文案。Invalidation 明示：“Do not select the previous routing option again. Re-examine the dashboard and choose a different option.” F0 只要求重新检查。Wind 是真实 misleading previous branch；Hydroelectric 是 neutral placebo，用来区分“换一个”与“换到正确 Solar”。

| Cell | Previous / cue | 原始可观测轨迹 | 实体层结果 |
|---|---|---|---|
| `q4_prev_wind_official_f0` | Wind / neutral | `B → Sel(Wind@3) → TC(no-submit)` | 重入错误旧分支 |
| `q4_prev_wind_official_invalidation` | Wind / 禁止旧分支 | `B → Sel(Wind@3) → TC(no-submit)` | 明示约束仍被违反 |
| `q4_prev_wind_clean_f0` | Wind / neutral | `B → Sel(Wind@3) → TC(no-submit)` | 重入错误旧分支 |
| `q4_prev_wind_clean_invalidation` | Wind / 禁止旧分支 | `B → Sel(Wind@3) → TC(no-submit)` | 明示约束仍被违反 |
| `q4_prev_hydroelectric_official_f0` | Hydro / neutral | `B → Sel(Wind@3) → TC(no-submit)` | 离开 Hydro，但转入错误 Wind |
| `q4_prev_hydroelectric_official_invalidation` | Hydro / 禁止旧分支 | `B → Sel(Solar@2) → TC(no-submit)` | 唯一 Solar rebind；未提交 |
| `q4_prev_hydroelectric_clean_f0` | Hydro / neutral | `B → Sel(Wind@3) → TC(no-submit)` | 离开 Hydro，但转入错误 Wind |
| `q4_prev_hydroelectric_clean_invalidation` | Hydro / 禁止旧分支 | `B → Sel(Wind@3) → TC(no-submit)` | 离开 Hydro，但转入错误 Wind |

真正对应研究问题的 Wind matched pair 中，invalidation 相对 F0 在 official 和 clean 下都没有 action difference；模型甚至在 thought 和 action description 中明确说要再次选择 Wind。这个结果比 Q1 更直接：即使把局部 action constraint 写到当前页和 retry 页，Back 之后仍不能稳定退出原 misleading branch。

Hydroelectric placebo 则避免了另一个错误结论：“只要不是 previous 就算 recovery”。四个 Hydro cell 都产生 branch exit，但其中三个落到 misleading Wind。`official + invalidation` 的 Solar receipt 是真实的可观测正确重绑定，说明该 checkpoint 在某个条件下可以选到 Solar；不过它不应计作目标 recovery，因为 previous Hydro 不是本任务的 misleading branch，协议也标记 `recovery_eligible=false`，而且随后仍是 `TASK_COMPLETE`、没有 submission。该 cell 的 thought 只说泛化的“route to priority contribution follow-up”，没有明确说 Solar；再加上相同 cue 在 clean Hydro 上选择 Wind，所以更稳妥的解释是“单个条件下出现了正确 action”，不能据此声称形成了稳定的视觉前提修正。

## 四个 probe 真正区分了什么

| Probe | 区分能力 | 本轮证据强度 | 仍然混入的因素 |
|---|---|---|---|
| Q1 F3 × F0 × layout | 局部 Back 与实体 rebind；语义实体与固定按钮位置 | 强：12 个 cell 都 Back，Wind 随位置移动，6 个 F3/F0 pair 无实体差异 | correct/misleading 的实体名字没有互换，不能排除 Wind 词汇先验或 inherited 文案锚定 |
| Q2 proposition × history | temporal workflow continuation 与 proposition-conditioned action | 强：输入 hash/annotation/action join 完整；H0 三实体不改变动作，history presence 改变 Back/Confirm | H0 是外部 fixture、位于较早帧；没有 authentic `MEMORIZE` bank 条件 |
| Q3 final-review isolation | 当前 final screenshot 是否足以触发 Confirm；completion 与 recovery 分离 | 中等：正确/错误 selection 都 Back；证明 current-screen-only handoff 不可靠 | 所有 Q3 handoff 都是空历史；只有一步；Q2 已证明有 history 时模型能 Confirm |
| Q4 invalidation × previous placebo | branch exit 与 correct rebind；显式“换一个”约束是否被执行 | 强：Wind target 中 cue 仍被违反；Hydro→Wind 显示 different 不等于 correct | 只有一个任务/一种文案；唯一 Hydro→Solar cell 无重复且不提交 |

总体上，Q1、Q2、Q4 已经能够支撑“撤销、分支退出、证据重绑定、提交是四个不同事件”，而不是用一个 trajectory success 把它们混在一起。Q3 的价值主要是暴露 completion/handoff confound，不应被当作 GUI-Reflection 提交能力的最终判决。

## 对抗性替代解释与论文边界

### 1. 这不是 GUI-Reflection vs 普通 agent 的处理效应

38 个 cell 都使用同一个 GUI-Reflection checkpoint。F3/F0、native4/current-only、invalidation/neutral 是该 checkpoint 内部的输入干预，不是另一个 base-agent checkpoint。因此本轮可以说“GUI-Reflection checkpoint 在这些 recovery probes 下表现出局部撤销但缺乏稳定重绑定”，不能说“GUI-Reflection 比不用 GUI-Reflection 更差/更好”。下一轮若要满足“使用该方法和不使用该方法逐样本比较”，必须加入同 backbone/base SFT 或关闭 reflection training 的 matched agent。

### 2. 本轮没有测试 populated memory bank

96/96 model receipt 的 `memory_empty_before=true`，模型也没有输出 `MEMORIZE`。所以本轮测试了官方 GUI-Reflection Agent、temporal screenshot/action history 和该 checkpoint 的训练行为，但没有测试一个已填入相关错误总结的 memory bank。不能从这里写“memory bank 无效”。应补一个预注册的 memory factorial：empty、action-only mistake、premise-specific correction、irrelevant/noisy memory，并记录真正传入 prompt 的 memory hash/content。

### 3. 38 个 cell 不是 38 个独立任务

所有 cell 都源于 env008，同一实体语义和同一任务目标；确定性解码也没有随机重复。它适合机制定位，不适合成功率、置信区间或显著性结论。尤其 `Hydro official invalidation → Solar` 只能作为反例/边界，不能当成稳定改善率。

### 4. 位置已经 counterbalance，实体角色还没有

Q1 排除了固定 control position，但 Wind 始终是 misleading entity，Solar 始终是 correct entity。模型持续选 Wind 可能包含词汇、颜色、类别常识或 inherited 文案先验。需要把 correct/misleading/neutral 角色在 Solar/Wind/Hydro 之间轮换，同时独立轮换按钮位置和柱颜色。

### 5. 行为证据不能唯一识别内部信念

模型 thought 是生成文本，不是 latent-state ground truth；H0 proposition 也是 evaluator-owned record。当前最坚实的量是 UI receipt、scorer 和 matched action difference。论文应把“没有显式撤销视觉前提”写成对可观测依赖敏感性的推断，而不是声称已直接读取模型信念。

### 6. Ground-truth artifact 仍有一个文档缺口

`canonical_case.json` 中 `audited_values_status` 仍为 `manual_evidence_pending`，尽管可见图上 Solar 41.2% 明确高于 Wind 29.8%，且 runner ground-truth computation 指向 CSV 最大值。正式论文 artifact 前应补人工 evidence receipt/CSV 行引用，避免审稿人把任务真值审计状态当作漏洞。

## 下一轮最值得做的实验

### A. 先补 env008 的实体角色 counterfactual

保持数值关系、视觉误导强度和页面结构不变，系统地轮换：

- printed-value 最大实体；
- tallest-bar misleading 实体；
- previous/inherited 实体；
- action card 位置与颜色。

最低要求是让 Solar、Wind、Hydroelectric 都各自承担一次 correct、misleading 和 neutral 角色。这样才能判断当前 Wind persistence 是错误分支依赖，还是特定实体偏置。

### B. 把反馈做成“依赖撤销阶梯”

在严格 matched UI 下比较：

1. F0：只要求 re-check；
2. action-only：不要再次选择旧 action；
3. premise-specific：柱高比例不可信，应按打印数值比较；
4. proposition-specific：旧命题“Wind 最大”无效，重新计算最大打印值；
5. answer-revealing upper bound：正确实体是 Solar。

若 2 只能 branch exit、3/4 才能稳定 rebind，就能直接论证你们方法需要追踪并撤销上游视觉前提；若连 5 都失败，则主要瓶颈可能是 GUI grounding/action execution，而不是认知依赖。

### C. 补齐 GUI-Reflection 的 memory 条件

将官方 `MEMORY` prompt 真正填入并做四臂 matched test：empty、仅“previous action wrong”、包含 `evidence→proposition→action` 的结构化纠错、无关 memory。必须同时保留 native screenshots/action history，避免把 memory effect 与 history presence 混在一起。

### D. 重做 completion factorial

用像素完全相同的 final-review current screenshot，独立控制：

- 空历史；
- 最近一次选择动作历史；
- `wrong → Back → correct selection` 完整历史；
- correct vs wrong final entity。

每个 cell 至少允许 Confirm 或 Back 后再执行一步，并以 scorer receipt 为唯一 completion 成功。这样可以判断 Q1/Q4 的 `TASK_COMPLETE(no-submit)` 是终止动作习惯、历史链问题还是按钮 grounding 问题。

### E. 再扩到小型手工 case panel

在 env008 机制稳定后，再选 8–12 个经过人工真值审计的样本，覆盖不一致尺度、截断轴、面积/长度错配、legend/label 干扰等误导类型。仍按逐样本 matched trajectory 报告，不必一开始追求单一平均分；先寻找“能 Back 但不能撤销哪一种 premise”的可重复模式，再决定新方法模块。

## 可用于论文的最小结论

> On env008, the GUI-Reflection checkpoint consistently executed local navigation reversal, yet reselected the inherited misleading entity across position-shuffled layouts and despite a visible contradiction signal. Controlled history changed whether the agent backed out or confirmed, but changing the recorded proposition did not change the selected action. These observations separate action reversal from premise-conditioned entity/action rebinding; they do not establish a dataset-level failure rate or rule out gains from a populated memory bank.

对应中文：

> 在 env008 上，GUI-Reflection checkpoint 能稳定完成局部导航撤销，但在按钮换位及可见 contradiction 条件下仍重选 inherited misleading entity。受控历史会改变 agent 是 Back 还是 Confirm，却不会使动作随历史命题实体改变。这说明 action reversal 与基于视觉前提的实体/action 重绑定是可分离的能力；当前单样本结果既不是全数据集失败率，也不能排除 populated memory bank 带来的改善。
