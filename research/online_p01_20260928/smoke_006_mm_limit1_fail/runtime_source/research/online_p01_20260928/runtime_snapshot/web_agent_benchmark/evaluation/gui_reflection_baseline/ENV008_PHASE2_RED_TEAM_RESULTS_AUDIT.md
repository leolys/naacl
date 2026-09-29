# env008 phase-2 正式结果独立红队审计

审计日期：2026-08-31  
正式 run：`runs/phase2_formal/20260831T095625Z_797a0392`  
审计角色：独立对抗审查 sub-agent；未修改 runner、scorer 或主结果报告  
审计方法：从每个 cell 的 `intervention.json`、`steps.jsonl`、PNG、`summary.json` 和 `scorer_records.jsonl` 重新连接与计数，不以顶层 summary 自报值作为唯一依据

## 总 verdict

**VALID，但只作为 `reportable=false` 的单 case、内部机制诊断。**

38/38 cells 均有完整 artifact，未发现会把 GUI-Reflection 恢复成功或失败制造出来的 harness-invalid cell。Q1/Q2/Q3/Q4 四个 block 均可用于协议冻结范围内的定性比较。正式 run 中没有 task-level recovery：唯一六次真实提交全部提交 Wind、canonical scorer 全为 `false`；其余 32 cells 没有提交，不能算成功。

这个 verdict 不把 `execution_complete=true` 等同于任务成功，也不解除两个既有边界：

- 所有 38 cells 都来自同一个 env008 与同一个 deterministic checkpoint，不能当 38 个独立 benchmark 样本或用于总体显著性结论；
- `canonical_case.json` 仍明确写有 `audited_values_status=manual_evidence_pending`。当前 Solar/Wind/Hydroelectric 数值链足以支撑内部 nonreportable scorer，但论文级 artifact 在补 human evidence receipt 前不能称已完成人工 ground-truth 审计。

| block | cells / raw calls | verdict | 实际结果 |
|---|---:|---|---|
| Q1 position-matched F0/F3 | 12 / 36 | VALID | 12/12 `Back → Wind → TASK_COMPLETE`，0 submission |
| Q2 proposition/action | 12 / 30 | VALID | native4 6/6 Confirm Wind 且 scorer false；current-only 6/6 `Back×4` timeout |
| Q3 completion-only | 6 / 6 | VALID | evaluator handoff 后模型严格一动作；6/6 Back，0 Confirm |
| Q4 branch invalidation | 8 / 24 | VALID | previous=Wind 4/4 重入 Wind；previous=Hydro 仅一格 Solar，全部未提交 |

## 1. 从磁盘重算的机械证据

### 1.1 完整性、身份与唯一性

独立遍历 run directory 得到：

- 38 个唯一 cell keys：Q1/Q2/Q3/Q4 分别为 12/12/6/8；与冻结 `cell_order` 一致；
- 96 行 raw model steps：Q1/Q2/Q3/Q4 分别为 36/30/6/24；step 序号在每格内连续；
- 158 个 PNG：38 张 `evaluator_before_setup`、96 张 step screenshot、24 张 Q2 H0/H1 fixture；所有图片恰有 artifact 引用，没有 missing 或未引用的额外 PNG；
- 38 个 intervention IDs 唯一；96 个 request IDs、96 个 response IDs 分别唯一；
- 50 个 evaluator setup transactions 唯一：Q1 12、Q2 12、Q3 18、Q4 8；
- 52 个 model-action UI transactions 唯一：26 `browser_back`、20 `selection`、6 `submission`；它们与 evaluator transaction ID 集合不相交；
- 6 个 scorer record IDs 与 6 个 submission IDs 均唯一。

顶层 `cell_results` 与 38 份 cell `summary.json` 一致，`partial_results.json` 与最终结果一致；没有 `fatal_error.json`。96 steps 中没有 execution error、Back transition error、blocked request、parse error或双 parser disagreement。

### 1.2 截图、动作历史与真实 model-call 输入

对 96 次调用逐次重算后均通过：

- 磁盘 step PNG SHA = raw step SHA = model-service receipt 的 screenshot SHA；
- task id、task step、history/action count、viewport 与 memory state能够从前序状态重建；
- raw RGB history digests 与 annotations 能接到磁盘/fixture；
- action/action-description arrays 的 digest 能从精确历史重算；
- GUI agent 在加 click annotation、将 history resize 到 448×448 后交给 `Model` 的 PIL digests，与 `model_call_input_image_sha256` 一致；
- 96/96 receipts 均为 `memory_empty_before=true`。这证明本 panel 没有 populated memory 条件，不证明 memory bank 无效。

一个非阻塞 provenance 细节：最早的 `q1_cyclic_shift_2_official_f0` step-0 receipt 在调用前记录的 generation config 尚未列出 `eos_token_id`，其余 95 次列出 `[2,92542]`。官方 `infer.py` 会在真正 `model.generate` 前加入该 EOS 列表，且该首步 action 与其他 11 个 Q1 首步逐字节相同，因此没有观察到处理组行为偏差；但不能把 96 份 receipt 的 pre-call config 描述成字节级完全相同。

`agent_health.json` 绑定官方 GUI-Reflection agent、checkpoint、`temporal_len=4`、fixture endpoint 与 model-input receipts。run directory 没有独立 model-server log；因此这些是本机服务/收据闭环，不是外部第三方 attestation。

### 1.3 evaluator offset、UI 与 scorer join

每格 evaluator setup receipt 都位于 model receipt offset 之前。`direct_behavior_summary` 只由 raw model steps 与 offset 之后的 UI receipts重算；50 个 evaluator transactions 没有混入 52 个模型 UI transactions。

逐 transition 检查得到：

- 26 个 `browser_back` 均由模型 `PRESS_BACK` 触发，且是 `review → retry_decision`；
- 20 个 `selection` 均由 retry 页面真实 CLICK 触发，token、control position、entity 与 post snapshot 一致；
- 6 个 `submission` 均由 review 页面真实 Confirm CLICK 触发，随后才产生 scorer record；
- 6 个 scorer record 均提交 canonical `choice_1`/Wind，submission ID 与 model UI receipt 精确相接，success 均为 `false`。

canonical scorer 与 runner 同 codebase/进程，虽然不读取 model thought 或 reducer 结论，但不应称为外部独立 scorer 服务。

## 2. Q1：F3、位置与 Wind 重入

Q1 的 12 格都有同一三步状态链：

| Wind layout position | arms × feedback | step 0 | step 1 | step 2 | submission |
|---|---:|---|---|---|---:|
| p0，`cyclic_shift_1` | 2 × F0/F3 | Back | Wind(p0) | TASK_COMPLETE | 0/4 |
| p1，canonical | 2 × F0/F3 | Back | Wind(p1) | TASK_COMPLETE | 0/4 |
| p2，`cyclic_shift_2` | 2 × F0/F3 | Back | Wind(p2) | TASK_COMPLETE | 0/4 |

机械审计确认：

- 12/12 首步 Back 都有真实 `review → retry_decision` receipt；不是 no-op；
- 12/12 retry CLICK 都跟随 `choice_1=Wind` 移到 p0/p1/p2，而不是固定坐标；
- 六个 F3 intervention 各有唯一 validator outcome ID，均绑定本格 inherited Wind token/action/position 且 `contradiction=true`；六个 F0 没有 validator；
- 六组同 layout/arm F0/F3 的 chart hash、display tokens 与 Wind token/position matched；
- 12 个首步 raw responses逐字节相同；F3 与 F0 的可观察最终 action chain 相同。

因此允许说：在这个 panel 中，visible binary contradiction 没有阻止跨三个位置的 Wind re-entry。它排除了“永远点固定第一/最后 card”作为完整解释。

不能说：模型已经理解了 contradiction 后仍有意选择 Wind；首步 Back 在 F0 也完全相同，artifact只证明 signal进入可见当前像素而没有改变 action。也不能说内部 Wind premise 已被直接测量，或把最后的 `TASK_COMPLETE` 当完成；当时 server 仍 `submitted=false`，没有 scorer。

## 3. Q2：P 是否真实进入模型、current-only reset 与结果

### 3.1 P 不是 hidden evaluator label

Q2 的 12 个 fixture IDs 均唯一。每个 H0 PNG 在像素中明确显示 `Prior proposition record — Identified source: {Solar|Wind|Hydroelectric}`；H1 和 current review不显示 P。独立检查确认：

- H0/H1 磁盘 PNG、raw RGB hashes、history annotations、action-history digest 均与 prime receipt精确相接；
- 从本格 H1/chart 重新调用当前 proposition renderer 可 byte-exact 重建 H0；
- H0 的 raw diff 与 448×448 model-history diff均非空，且只落在预声明 entity-text mask；
- native4 首次调用的前两张实际 model-call PIL hashes正是对应 P 的 annotated/resized H0/H1；第三张 current image在同 arm 三个 P 间相同；
- H1、Wind action及 click annotation `[985,626]` 在同 arm/history group内一致。

所以可以确认 **P 的可见像素真实进入 GUI-agent→Model 的 PIL 输入**，不是仅存在于文件名、runner label或 evaluator hidden state。这个 receipt 边界仍停在送入 `Model` 的 PIL，不是 InternVL 内部最终 tensor。

### 3.2 current-only 真的清除了 P history

六个 current-only cells 先真实 prime fixture，再 reset；每格 `agent_reset_count=5`，即 handoff 前一次并在四次调用之间继续保持 current-only。24 次 current-only model receipts全部为：

```text
task_step_index=0
history_image_count_before=0
action_count_before=0
memory_empty_before=true
model input image count=1
```

同一 arm 下 Solar/Wind/Hydro 的 current pixels一致；更强地说，三种 P 的完整四步 raw action、截图/model-input hash序列也一致：`review Back → retry Back → retry Back → retry Back`。因此没有发现 P 从 fixture、memory或 task step 泄漏到 current-only。

### 3.3 行为矩阵与严格解释

| visible P | official native4 | clean native4 | official current-only | clean current-only |
|---|---|---|---|---|
| Solar | Confirm Wind；scorer false | Confirm Wind；scorer false | Back×4 timeout | Back×4 timeout |
| Wind | Confirm Wind；scorer false | Confirm Wind；scorer false | Back×4 timeout | Back×4 timeout |
| Hydroelectric | Confirm Wind；scorer false | Confirm Wind；scorer false | Back×4 timeout | Back×4 timeout |

native4 六格 action identity 与坐标完全相同：第一步直接 Confirm inherited Wind，没有 Back、retry 或 action rebinding。六个 thought 都显式描述“Wind 已选、现在确认”，但 raw wording不是六格逐字节一致：official 的 Solar cell与另两种 P不同，clean 的 Wind cell与另两种 P不同。故正确结论是 **action-level invariant**，不是“整个生成对 P 完全无响应”。

同样不能写成“模型读懂 P 后忽略它”。artifact证明 P 在实际可见输入中，却不能证明认知读取；raw thought没有提及任何 P，只复述最近 Wind action。可写成：没有观察到 P 的语义/action uptake。

native4 与 current-only 的 Confirm/Back 分裂证明整个 temporal-context bundle 会改变流程动作；该 bundle同时包含 H0、H1、两条 action history和 task step，不能进一步单独归因于 H0、H1或 task-step index。P=Solar 与 P=Hydro 均未相对 P=Wind 触发 branch change，所以本次也没有一般 P/A mismatch uptake 的行为证据。

## 4. Q3：evaluator completion chain 没有被误计

六格各有三笔、共 18 笔 evaluator transactions，均在 agent reset 与 model offset 之前：

```text
Solar core: Wind selection → Revise → Solar selection → final review
Wind negative: Hydroelectric selection → Revise → Wind selection → final review
```

intervention 均标记 `source=evaluator_completion_fixture`、`normalized_as_agent_selection=false`、`recovery_eligible=false`。因此 evaluator 建立的 Solar/Wind、一次 revision和两次 selection都没有进入 model selection/reversal计数。

handoff 后六格的 history/action/memory均为空，且每格严格只有一个 raw model call。模型 6/6 输出 `PRESS_BACK`；真实 browser history从 review URL返回 decision URL，但没有生成 server-side revision transaction，所以 reducer正确记录 model selection/reversal均为 0。这个 Back 是模型离开 final review 的动作，不应与 evaluator Revise或 Q1/Q4 的 server `browser_back` receipt混在一起。

| final state | cells | model first action | Confirm/submission |
|---|---:|---|---:|
| Solar core | official/clean × native4/current-only，4 | 4/4 Back | 0/4 |
| Wind negative | official/clean native4，2 | 2/2 Back | 0/2 |

同 arm Solar native4/current-only 的 step-0 screenshot和raw response byte-identical，符合二者实际都为空历史的设计。Q3 可支持“在这六个空历史 one-step final-review handoff 中没有 direct completion”，不支持“模型绝对不会 Confirm”；Q2 已提供 6/6 真 Confirm 的直接反例。Q3 没有 scorer不是 scorer failure，而是因为模型从未提交；对于 completion-only outcome，这仍是 completion failure。

## 5. Q4：Hydroelectric 不能进入 recovery numerator

正式 run 的 neutral/invalidation pairs全部到达 retry，故不存在把行为导致的 missing retry误报为 harness failure的问题。独立像素重算得到：

- neutral vs invalidation：review diff bbox `[864,471,1222,535]`，retry `[864,374,1222,438]`，mask外像素差为 0；
- Wind vs Hydro previous-label：review diff bbox `[864,375,1186,415]`，retry `[941,242,1220,281]`，mask外像素差为 0。

cards、chart、tokens、layout与预算保持一致；previous card可点。事实上四个 previous=Wind cells都在 retry真实重新点击 Wind，直接排除了 UI disable/hidden 强制 branch exit。

逐 condition 的真实结果为：

| previous | arm | neutral control | invalidation | 可计 recovery？ |
|---|---|---|---|---|
| Wind | official | Wind，no-submit | Wind，no-submit | 两格均否 |
| Wind | clean | Wind，no-submit | Wind，no-submit | 两格均否 |
| Hydroelectric | official | Wind，no-submit | **Solar，no-submit** | 否；previous不是视觉 trap |
| Hydroelectric | clean | Wind，no-submit | Wind，no-submit | 否；previous不是视觉 trap |

previous=Wind 是目标 recovery condition：4/4 branch exit=false，invalidation 与 neutral没有 action差异。previous=Hydro 的 4/4 都离开 Hydro，但 Hydro 的 role是 `neutral_or_irrelevant`、`recovery_eligible=false`；其中三个换到错误 Wind，不能叫纠错。

唯一局部正例 `q4_prev_hydroelectric_official_invalidation` 确实有真实 Solar selection receipt，说明该 cue/arm/previous组合能在本格改变 alternative；但它没有 Confirm/submission，而且 previous不是 misleading Wind。因此它只能作为 localized counterexample，既不能进入 misleading-Wind recovery numerator，也不能推广为 invalidation有效。反过来也不应说 cue在所有条件完全没有任何 action effect；它在这一格相对 matched neutral从 Wind变成了 Solar。

## 6. 没有 submission 到底意味着什么

正式 run 只有 Q2 native4 六格提交，且全部是错误 Wind、scorer=false。其余 32 格没有 `submission` UI receipt，因此按协议根本没有 scorer invocation：

- Q1/Q4 的 `TASK_COMPLETE` 只是模型输出，server仍为 `submitted=false`；
- Q2 current-only 是未选新 action 的 timeout；
- Q3 是 one-step direct-completion 未完成。

所以“no submission”不能伪装成成功，也不能写成“scorer=false”——其 scorer值是未定义/null。任务级成功要求 submission receipt加 canonical scorer true；按这个定义本 run 为 0 个 task-level success。

## 7. 对主结果报告关键计数/措辞的核对

对 `ENV008_PHASE2_RESULTS.md` 的核心表述逐项攻击结果如下：

| 主报告表述 | 审计 verdict | 必要边界 |
|---|---|---|
| Q1/Q4 20/20 effective Back | **支持** | 20 个首个 Back均有真实 `review→retry` model UI receipt；不要把 Q3 browser-history Back计入该 20 |
| 96/96 calls memory empty | **支持** | 只说明本 panel未测试 populated memory，不能推断 memory bank无效 |
| Q2 native action invariant，但 raw wording略变 | **支持** | 六格均 Confirm Wind；两处 arm内 raw wording变化不提及 P，不能叫 semantic read/ignore |
| Q3 0/6 Confirm | **支持** | 仅限空历史 one-step handoff；Q2 的 6/6 Confirm是“绝不会 Confirm”的反例 |
| 唯一 Hydro→Solar 不算 recovery | **支持** | previous=Hydro、`recovery_eligible=false`，且 no-submit |
| 0 full task recovery | **支持** | 六次提交全为 Wind/scorer false；32 格无提交 |
| exact printed-value truth 可用于正式报告 | **尚不支持** | `manual_evidence_pending`；当前只适用于内部 nonreportable evaluation |

主报告整体的行为计数与 raw artifacts一致。两项运行外围陈述——“允许 loopback 后 14/14 tests passed”和“推理服务结束后 GPU 已释放”——不在此 formal run directory 的可重算证据内；本审计不以它们为结果有效性的依据，也不对其作独立背书。

## 8. 允许与禁止的结论

允许：

- “在 env008 的冻结 deterministic panel 中，GUI-Reflection 稳定执行了局部 Back，但 Q1 在 F0/F3 与 p0/p1/p2 上都重入 inherited Wind。”
- “Q2 的外部 proposition P 确实进入实际模型可见历史输入；P 改变未改变 action identity，temporal-context bundle却改变 Confirm/Back 流程动作。”
- “Q3 的 evaluator-owned正确 final state在四个 Solar空历史 one-step handoff 中均未直接 Confirm。”
- “answer-neutral invalidation 未使 previous=Wind 的目标格退出 Wind；Hydro/official/invalidation 有一个未提交 Solar边界反例。”
- “本 run 将 navigation reversal、entity/action rebinding与真实 completion区分开；task-level success为 0。”

禁止：

- GUI-Reflection 在整个 benchmark 上成功或失败，或 GUI-Reflection training相对普通 agent有效/无效；没有多 case与同 backbone non-reflection对照；
- 模型内部 premise 被直接读取、理解、保持或撤销；P是 evaluator-owned可见 record，thought不是 latent-state ground truth；
- “模型读了 Solar但选择忽略”，或用 wording变化证明语义理解；
- F3 Back证明模型理解 contradiction，或 branch exit本身等于视觉重求解；
- 把 evaluator Q3 chain、Hydro→Solar/Hydro→Wind、`TASK_COMPLETE` 或 no-submit计作 recovery；
- 从 Q3 断言模型不会 Confirm，从 96 个 empty-memory calls断言 memory无效；
- 称 canonical scorer是外部独立服务，或称当前 ground truth已完成人工 evidence audit；
- 将 38 layout/cue cells当 38 个独立任务汇报成功率、置信区间或显著性。

## 最终审查结论

本 formal run 的机械链与 paired design **有效**，没有需整轮作废重跑的 artifact blocker。它支持一个窄而清楚的负结果：在 env008 上，GUI-Reflection 的局部导航 reversal没有转化为目标 Wind→Solar action rebinding和真实提交；显式 P、binary contradiction与“不重复 previous”cue也没有在目标格完成该链。与此同时，Q2 的真实 Confirm和 Q4 的单个 Hydro→Solar表明不能把结果夸大为模型没有任何流程能力或任何条件响应。
