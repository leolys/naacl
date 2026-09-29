# Targeted Recovery Evaluation：逐样本视觉前提纠错评测

> **状态：** 评测设计、case builder、canonical/condition/evidence registry 绑定、append-only event reducer、四格结构检查和 ladder validator 已实现并测试。机器输出刻意区分 `protocol_complete=true`（合成/原始记录满足当前结构协议）与 `reportable=false`（不能作为实验结果）；authoritative checked-in registry loader、compact diagnostic UI、浏览器 collector、write-once capture/model-input/action receipt、独立 F3 validator store 及端到端泄漏/真实性测试尚未实现。因此本文件中的 targeted model cells（包括 `R+ / R−`）均尚未执行，代码中的合成 trace 测试也不是实验结果。已运行的 smoke17 逐样本证据单列在 [`PER_SAMPLE_RECOVERY_ANALYSIS.md`](PER_SAMPLE_RECOVERY_ANALYSIS.md)，不能与 proposed cells 混为实验结果。

## 1. 研究问题

本评测不再只问“最终成功率是否提高”，而是对每个 misleading/clean pair 分别回答：

1. agent 是否先被误导图表诱导出错误的中间判断；
2. 当错误的执行结果或独立反证可见后，agent 是否识别到矛盾；
3. agent 是否执行了真实的撤销动作；
4. 回到决策页后，agent 是否撤销原视觉前提并改选正确分支，还是重入相同错误分支；
5. GUI-Reflection 的训练、视觉历史和错误反馈分别带来了什么变化；
6. 仍未解决的问题属于图表理解、动作验证、状态撤销、信念更新、重试 grounding、流程规划还是完成判断。

最终 hidden submission 仍保留，但它只是逐样本 dossier 的一个字段，不再是唯一观测量。

## 2. 为什么不能直接扩大现有 smoke

formal smoke17 中，GUI-Reflection SFT 在 official 和 clean 均为 0/17 hidden-scored success；34 个单元均未提交。失败主要发生在 landing page、native form grounding 和错误的完成判断，早于可解释的视觉纠错阶段。直接扩大到 strict94 会增加端到端失败样本，却不能识别反思方法是否撤销了误导视觉前提。

targeted evaluation 因此拟采用一个专门的诊断 UI：任务仍使用 canonical instruction、official/clean chart 和原 action labels，但把 chart、三个候选动作和提交控件放在同一固定视口，用大尺寸坐标控件减少 Web grounding 噪声。它是机制诊断，不替代原始 benchmark 的端到端结果。当前完成了安全投影、case manifest、registry/event/quartet/ladder 的协议代码；actual authoritative loader、compact 页面与浏览器 collector 仍未实现，必须等 URL、HTML、截图、prompt 的泄漏与真实性集成测试通过后，才进入模型运行。

## 3. 不把“有/无方法”压成一个含混开关

GUI-Reflection 是跨多个训练阶段形成的 end-to-end model，不是可以从 SFT checkpoint 中干净关闭的 prompt 插件。评测分开回答三个问题。

### Q1：恢复机会本身是否有帮助

使用同一个 model checkpoint 和相同 compact UI：

- `single_attempt`：错误 provisional choice 直接结束；
- `feedback_retry`：错误 provisional choice 后显示反证，允许 Back 和一次重试。

这比较的是 recovery workflow assistance，不是 reflection training 的因果效应。

### Q2：轨迹上下文是否帮助信念更新

使用同一个 GUI-Reflection SFT checkpoint：

- `sft_t4_stateful`：官方默认 `temporal_len=4`，保留 past screenshots、完整文本 action history 和 memory；
- `sft_t0_text_history`：`temporal_len=0`，只移除过去截图和点击红点；完整文本 action history、memory、当前截图、prompt 和 reflection-trained weights 仍保留；
- `sft_reset_retry`：只在 retry 前 reset agent，清除刚才 review 形成的图像、动作、description 和 memory；仅在 retry 当前页也显示完全相同反证时，才可与 stateful 条件比较；
- `sft_current_only`：每个 step 前 reset，只保留当前截图与 goal；这是更强的 inference-time trajectory-context ablation，会改变官方使用方式。

`temporal_len=0` 只能称为 visual-history ablation，不能称为“无 GUI-Reflection”。`reset_retry` 只能称为 state-carryover ablation，`current_only` 只能称为 inference-time trajectory-context ablation；两者都不能冒充未训练 baseline。

### Q3：reflection training 本身是否有帮助

论文的干净 pre-training 对照是：

- `GUI-Pretrain`：regular GUI pre-training；
- `GUI-Pretrain-Ref`：额外加入 GUI-Reflection Task Suite 数据。

官方公开的 `craigwu/GUI_Reflection_8b_pretrain` 对应 reflection-pretrained 模型；官方仓库没有提供 regular `GUI-Pretrain` checkpoint。`GUI_Reflection_8b_SFT` 又是在前者基础上继续 offline SFT，不能与 pretrain 直接解释成“有/无反思”。

训练阶段必须分开，不得把不同 stage 的 checkpoint 放进同一个“有/无方法”单元：

- **pretrain-stage contrast**：`GUI-Pretrain-Ref` 对 `GUI-Pretrain`，两者都停在 pretraining stage；获得 regular GUI-Pretrain 后可以回答 reflection task-suite augmentation 在该阶段的差异。
- **SFT-stage/full-pipeline contrast**：`GUI_Reflection_8b_SFT` 的参照必须也是 SFT-stage checkpoint。它应从相同 base architecture 出发，在 ordinary GUI data、下游数据、更新步数和预算上匹配，只移除或预算匹配地替换各阶段的 reflection-specific task/trajectory augmentation。只拿一个尚未 SFT 的 regular GUI-Pretrain 不能作为这个 `R−`。
- 若要分别定位 pretraining reflection 和 offline-SFT reflection 的贡献，还需从同一个起点各做一次单因素、预算匹配的 stage ablation；full-pipeline `R+ / R−` 只能回答整套 reflection training recipe 的联合差异。

因此，即使获得论文的 regular GUI-Pretrain 权重，也只能补齐 pretrain-stage 对照；要补齐下面 SFT targeted 矩阵的 `R−`，仍需作者提供 matched no-reflection SFT checkpoint，或重训完整的 stage-matched pipeline。若使用 InternVL2.5-8B、其他 Web agent 或 API model，只能标记为 external policy comparator，并单独报告输入接口和 grounding 差异。

### 最低可解释矩阵

每个样本先保留下面的 2×2 记录框架；缺失的单元必须留空并说明原因，不能由另一个消融代填：

| chart arm | `R+`：GUI-Reflection SFT | `R−`：matched no-reflection policy |
|---|---|---|
| official misleading | `O+` | `O−` |
| clean | `C+` | `C−` |

当前四个 **targeted** 单元均为 pending。已经运行的 formal smoke 使用原始 benchmark shell，只有 GUI-Reflection 下的 official/clean pilot evidence；它既没有 targeted compact UI/review workflow，也不填入这里的 `O+ / C+`。公开资源同时不足以填入严格的 `O− / C−`。在此之前可以另做两组有价值但不同的问题：

- `workflow_on / workflow_off`：同一个 SFT policy，有或没有可见反馈和重试机会；
- `stateful / visual_history_off / reset_retry`：同一个 SFT policy 的 inference-time context contrast。

这两组结果都不得把右侧条件写成 `R−`。SFT 与公开 reflection-pretrained 权重的比较记为 `checkpoint_stage=SFT/pretrain`，也不得填入 `R−`。若论文需要严格的“with/without reflection training”，必须获得同 stage 的 matched checkpoints，或从相同初始化、ordinary GUI data 和训练预算重训仅改变 reflection-specific augmentation 的完整对照；bare regular GUI-Pretrain 只属于 pretrain-stage 对照。

## 4. 两层评测

### Layer A：论文原生 reflection-oriented probes

保持官方三类任务定义，但把输入替换为本 benchmark 的样本：

1. **Action Verification**
   - 输入：提交/点击前截图、执行后截图、action purpose；
   - 正样本与负样本必须成对；
   - 重点记录 failed-action true negative，避免只会回答 Yes；
   - 目的：判断模型能否看到“点击/选择没有满足真实图表决策”。
2. **Action Reversal**
   - 输入：错误前后截图、真实 executed action、六个候选 undo actions；
   - 正确答案可为 `PRESS_BACK`、清空/改选，必须由 UI 状态决定；
   - 目的：判断模型是否知道如何恢复界面状态，不评价是否修正视觉信念。
3. **Mistake-informed Reattempt**
   - 输入：当前决策截图、已知错误 choice 的可见标记和错误列表；
   - 第 2/3 次尝试只能在前一次真实错误后生成；
   - 目的：判断模型是否利用已知错误选择另一个候选，而非随机 pass@k。

这层优先使用 `GUI_Reflection_8b_pretrain`，因为官方 eval scripts 本身用该 checkpoint；SFT agent 结果另表报告。

### Layer B：end-to-end targeted trajectory recovery

这层计划使用 `GUI_Reflection_8b_SFT` 的官方 `GUI_Reflection_Agent.step(image, goal)`，保留真实 action/history/memory 更新；以下是待实现、待运行的状态机，而不是已取得的 targeted 轨迹。

每个样本使用以下状态机。所有 provisional choice 都进入同一个 review route；不能让“是否进入该页”本身泄漏 hidden correctness：

```text
S0 initial_decision
  selected-arm chart + canonical goal + three blinded action cards
      |
      | provisional choice
      v
S1 review
  selected choice + configured feedback/evidence; screenshot consumed
      |                              |
      | Confirm                      | PRESS_BACK or Revise
      v                              v
S4 final_record                S2 review_exit
                                     |
                                     v
S3 retry_decision
  original chart + same action order
      |
      | second actual choice
      v
S1 retry_review
      |
      | Confirm
      v
S4 final_record
  hidden scorer records the complete selection sequence and final role
```

clean arm 也执行相同状态机和反馈规则；不能只给 official 额外步骤。若 clean 初次正确，则记录 `no_recovery_needed`，同时观察它会保持正确选择还是被 review 干扰。只有 initial choice 为 canonical misleading action 且 S1 截图实际进入下一次模型 step，才形成 natural visual-deception recovery opportunity。

S3 分成两个不能混报的呈现方式：

- `history_only_retry`：反证只在 S1 review 出现，S3 恢复原 chart；测模型能否把刚看到的反证通过视觉/文本历史带回原决策页；
- `current_visible_retry`：S3 同时保留完全相同的反证卡；用于公平比较 stateful 与 retry 前 reset，因为两者当前截图中的任务、provisional choice 和证据一致。

若 reset 条件在 S3 看不到反证，而 stateful 条件能从历史看到，差异同时改变了可用信息，不能归因为“state carryover”。

## 5. 两类 recovery track 与两种 natural review regime

### Natural recovery

模型自己做出 provisional choice。只有实际选择了 canonical `misleading_action_id`，才进入“visual-deception recovery opportunity”分析；neutral/irrelevant 错误另记为一般流程错误。

优点是保持自然行为。限制是不同 model/condition 的初始错误集合可能不同，因此 conditional recovery 不能跨不同 eligibility subset 直接比较。

Natural track 再固定区分两种 review regime：

- `neutral_recheck`：无论 initial choice 是 correct、misleading 还是 neutral，都显示相同 chart、当前 provisional choice 和“提交前请重新核验 dashboard”；不告知选择对错，测自主 verification；
- `outcome_feedback`：所有 choice 仍进入相同 layout，但显示真实 provisional outcome；错误条件只说当前选择与独立检查不一致，不点名正确动作，测外部错误信号触发的 recovery。

两者不能合并。`outcome_feedback` 后的成功是 feedback-assisted recovery，不是模型自主发现错误。

### Standardized-mistake probe

当前页明确显示：“此前的 provisional choice 是 `<misleading label>`，独立审计发现它与证据不一致”，所有被测模型从相同页面开始。

这可比较模型在相同已知错误下的修正能力，但它不是模型自己产生的完整 trajectory，也不能称为 natural recovery。标准化错误必须作为单独结果，不能与 natural 分母合并。

standardized/inherited-error 页必须显示“此前操作者记录的 provisional choice”及其不一致状态，但页面源码仍不得含 `correct_action_id`、role 或 scorer。浏览器历史需要预先存在一个真实 retry 决策页；runner 可以在模型 reset 前建立这个历史，但不得伪造模型动作史。它只能称为纠正外部错误状态，不能称为模型纠正自身错误。当前 reducer 仍从 base 读取 injected mistake；正式 collector 尚需一个独立、可审计的 intervention receipt 证明该 handoff state 真实建立，因此 standardized quartet 额外保留 `standardized_mistake_intervention_receipt_pending`。

## 6. Feedback / counterevidence ladder

逐样本使用下列诊断反馈；它们不是可互换的同一条总强度轴，也不直接把 hidden action role 暴露给模型：

1. `F0_neutral_recheck`：同一 chart、当前 provisional choice、通用复核提示；所有 choice 文案相同。
2. `F1_checklist`：在 F0 上增加与答案无关的检查清单，例如标签、轴、图例、时间范围；所有 choice 文案相同。
3. `F2_audited_values`：显示经人工复核的实体—值表或关系摘要，不显示 action role。许多样本中该关系在语义上已经等价于答案，即使页面没有显式 role，因此它只能作为 evidence-assisted upper bound，不能算自主 verification。
4. `F3_outcome_contradiction`：明确说当前 provisional choice 与独立检查不一致，但不点名正确动作；对应外部错误信号触发的 recovery，而非自主 verification。

每一级必须同时给所有 model/history 条件。不能 GUI-Reflection 组得到更强提示，也不能把不同级别合并；若某个 case 因 F0/F1 失败而升级，则该 case 的全部 candidate/reference 和 official/clean 条件都补跑同一个升级级别，不能只给失败的一格更强证据。自主证据路径只允许按 `F0 → F1 → F2` 的完整四格前缀推进；F3 是独立的 outcome-feedback probe，不是 F2 之后的标量“更强一级”。如果只有 F3 才恢复，只能报为 outcome-feedback-assisted recovery；如果 F2 恢复而 F0/F1 不恢复，该模式与原图视觉读取/证据获取是瓶颈的解释一致，但 F2 可能已语义等价于答案，不能据此确认具体内部机制。F2 后仍实际重入 misleading branch，则证明给定审计事实没有带来该次动作改选；还需排除 action grounding failure，不能直接断言内部事实—动作绑定未撤销。official trajectory 中不展示 paired clean chart；clean chart 只作为独立 paired arm，而不是给 official agent 的答案替换。

F2 不能直接从 hidden GT 自动生成后未经人工确认。对没有可靠 CSV/HTML 的样本，必须由逐样本审阅者核对图、source review 和 clean pair 后填写；记录精确 official/clean canonical source artifact/record、结构化 model-visible facts、reviewer、review status 和 ISO review date。未完成时标为 `manual_evidence_pending`，不得进入模型可见页面；实际 F2 run 只能通过 case-scoped `evidence_record_id` 从 authoritative approved registry 解析，base/run 不得自报 source、reviewer 或 approval。当前只实现了 registry schema 和测试用内存记录，项目级 authoritative loader 与真正批准记录仍 pending。

## 7. 控件和选项防泄漏

- initial/retry 页只展示 canonical workflow instruction、指定 arm 的 chart 和原 action labels；
- 不展示 `correct_action_id`、role、misleader type、ground truth、rationale 或 reviewer note；
- 已核对的 official140/clean140 共 280 条记录中，`expected_action_id` 都位于 action-space index 0；strict94 也全部如此。targeted UI 绝不能沿用原序。使用 full140 `pair_group_id` 字典序的全局稳定序号做循环排列；算法不读取 role/GT，同一个 case 在 smoke17、strict94、official/clean 和所有 model/context/evidence 条件中保持完全相同，同时报告三个位置的计数；
- 可另跑一次镜像位置诊断来识别 position-only policy，但它只诊断布局敏感性，不进入 reflection recovery 结论；
- chart、按钮大小、viewport、字体和等待时间在 condition 间完全相同；
- 不使用 selector/DOM helper 代替模型动作；runner 可在隐藏侧读取提交 token 计分；
- provisional choice 必须来自真实 POST/URL 事件，不能从 action description 或 thought 推断；
- `TASK_COMPLETE`、点击 Submit 的口述或到达 form 都不是提交。
- builder 的 `model_visible_projection(case, arm)` 是普通决策页 renderer 唯一允许接收的 allowlist 投影；F2 review 必须改用 `model_visible_review_projection(...)` 从 approved registry 只取结构化可见 facts，不能把 record id、source、reviewer 或 combined manifest 交给模板。实际 compact renderer 完成后，还必须启用上下文 HTML escaping，并对 HTML、URL、截图 OCR 文本和最终 prompt 做 canary/敏感字段断言；当前单元测试只证明 Python projection，不等于端到端隔离已经完成。
- reviewer route 在 targeted run 中完全禁用；HTML、可见 badge、route 参数和截图中均排除 `ground_truth`、`intermediate_decision.correct_value`、`misleading_context`、`role`、`scoring_outcome` 和 reviewer note。

## 8. 每个 run 必须记录的事实

单条 targeted trace 必须把 base identity 与 append-only raw events 当场交给 `analyze_run(..., registry=...)`；它只产生 canonical-bound、trace-replayed 的逐轨迹诊断，`reportable=false`。同一 arm 的 `compare_runs(...)` 也只产生 arm-pair diagnosis。四条 raw trace（candidate/reference × official/clean）与预注册、有方向的 `contrast_id` 交给 `analyze_recovery_quartet(...)` 后，机器最多给出 `protocol_complete=true`：四格缺失、重复 run/submission/scorer/F3-validator id、跨格复用 capture/model-step/model-response/execution receipt、整体交换 candidate/reference、task/chart/token-layout/render profile 不对称或某一 policy 跨 arm provenance 改变都会 fail closed；但 quartet 的 `reportable` 仍强制为 `false`，并列出 `publication_blockers`。这避免任意调用者用内存 registry 和自造 runner event 生成“可发表”结果。

`validate_case_ladder(...)` 接收每一级的 raw 四格并重新 replay，而不信任手填 quartet summary；它用 `protocol_complete_autonomous_prefix` 表示结构完整的 `F0→F1→F2` 前缀，`reportable_autonomous_prefix` 在当前实现中始终为空，F3 只给出 `outcome_probe_protocol_complete` 而不标成 reportable。workflow-on/off 的 reference 是 `single_attempt`、没有 review evidence，因此 workflow contrast 明确排除在 evidence ladder 外，只单独分析一个 workflow quartet；不能把它塞进 F0→F2 级联。

正式入口先从 canonical case manifest 解析 correct/misleading/neutral role 和 display order，再从 preregistered condition table 解析 checkpoint id/stage、reflection-training status、history 和 workflow，并从 contrast table 解析唯一 axis 及 candidate/reference 的固定方向；调用方翻转 GT/role、交换条件角色或自报 checkpoint provenance都会被拒绝。F2 source/reviewer/date 只能由 approved case-scoped registry record 解析；reflection-training contrast 还要由单独 approved training-recipe record 绑定 candidate/reference 的精确 checkpoint lineage。当前 authoritative 项目 loader 尚未实现，所以测试 factory 里的内存 registry 只用于检验 fail-closed 语义，不能作为论文证据来源。

summary 中一个可手填的 `event_trace_reduced=true` 标志本身不构成证据。底层 reducer 当前要求：`event_index` 从 0 连续，event envelope 的 run/trial/case/task-instance/arm/condition 与 base 一致，未知字段被拒绝；registry 将每个 arm 的 canonical task/chart、可见 choice token 顺序和 token→action mapping 绑定到 run。每次 initial/retry selection 都必须带有相应决策输入 PNG、model-step、renderer build、viewport、task/chart/UI acknowledgement、model-response 与 execution receipt；raw POST token、control position 和自报 action id 必须共同映射回同一个 canonical action。retry receipt 还必须绑定 prior provisional choice；`current_visible_retry` 精确绑定 F2 record 或最近 F3 outcome，`history_only_retry` 则强制这些 current-page record 为空。

review/final-review receipt 必须显示 reducer 当前的 provisional token/position/action，绑定同一 task/chart/render profile、反馈级别与 F2/F3 record；PNG 不只检查 chunk/CRC/IEND，还实际 inflate IDAT、核对 scanline/filter 和像素尺寸等于 viewport。reversal 和 submission 必须引用最近一次模型输入的 response/execution receipt；`single_attempt` 的 selection→submission 是同一个原子 execution，而不是凭空生成第二个无输入动作。F3 对每次 provisional choice 都要求独立的 `source=validator` record，review/final-review 分别绑定最近 record 与 polarity；polarity若与 canonical scorer role 冲突会标成 `measurement_inconsistency`。提交成功仍只能来自后续 `source=scorer`、同 submission id 的独立 `scorer_result`，未计分提交保持 `success=null`。

这些 schema 约束仍不是 runner/validator 身份认证。不同路径可指向同一可变 artifact，字符串唯一性不等于 write-once capture；合法 PNG、renderer acknowledgement 和 `model_step_id` 也不能证明该页面真实由浏览器渲染、chart/evidence 已加载、截图与历史确实进入模型请求，或 action receipt 真来自模型而不是 runner 注入。未来 compact collector 必须拥有 authoritative registry 加载、真实 POST/URL/server-state readback、write-once capture/model-input/transition receipt、F3 独立 validator store 和 hidden-scorer 对账；在此之前 `source=runner/validator/scorer` 只是结构标签。该端到端绑定尚未实现，所以当前所有 quartet/ladder 均保留 publication blockers，不能把单测误报为 targeted run 已经可执行或可报告。

每次 candidate/reference 比较还必须显式声明唯一 `contrast_axis`。`workflow` 只允许 workflow 不同，checkpoint/training/history 相同；`history` 只允许 history 不同，checkpoint/training/workflow 相同；`replication` 要求所有这些 provenance 相同。跨 checkpoint 或同时改变多个因素只能用 `descriptive_system`，输出 `descriptive_noncausal`，不能进入 matched recovery 标签。`reflection_training` 轴已预留，但当前 recipe schema 只绑定 checkpoint/stage/history/workflow/status，尚不能证明 base initialization、architecture、ordinary GUI data mixture、训练 steps/tokens/compute budget 与 recipe artifact/version 均匹配；因此即使填入人工批准的 `training_recipe_match_id`，仍会带 `stage_matched_training_recipe_artifact_pending` publication blocker。当前又没有这样的 `R−` checkpoint，所以该轴无实际 run，更不能据此做 reflection augmentation 因果归因。

```text
run_id / trial_id / case / task id+instance / arm / canonical chart path
model_condition / checkpoint id+stage / reflection-training status
history_mode / workflow_mode / recovery_branch / evidence_level
training_recipe_match_id and approval provenance when contrast_axis=reflection_training
evidence_record_id / exact paired source records / reviewer / review status / review date
current state / actual URL / renderer build / viewport
initial and retry input screenshots / model_step / model-response / execution receipt
raw POST choice_token + control position → registry-derived action_id
raw model output and parsed/executed action joined to the same model step
provisional action/token/position and role (runner-side only)
feedback screenshot observed / rendered provisional choice / feedback_spec_id
F2 rendered_evidence_record_id; F3 per-choice validator record and polarity
verification answer: recognized / denied / unclear
reversal action and whether it actually returned to retry state
all post-review selected_action_ids and roles, in event order
final review screenshot actually observed
same misleading choice re-entry at any later point
final selected_action_id / submission_id / independent scorer_record_id / outcome
grounding / browser / containment / model errors
```

thought 中出现 “I realized my error” 只作为 qualitative text；只有可见反馈、真实 Back 状态转移和实际 retry choice 才构成行为证据。实际切到 correct action 仍可能是 lucky click，机器字段只叫 `correct_action_switch`；“视觉前提已撤销”必须在 dossier 中另用新的事实陈述、跨布局稳定选择或其他独立证据支持。

## 9. 逐样本结果模板

每个样本单独写 dossier，不强制折叠为一个总指标：

| 字段 | 内容 |
|---|---|
| case facts | misleader type、GT、misleading target、chart-only/GT review 状态 |
| clean sanity | clean 首次判断、是否能操作 compact UI |
| susceptibility | official 首次选择是否为 misleading target |
| verification | 是否识别 action/outcome 与目标冲突 |
| reversal | 是否真实 Back/清空/改选，界面是否恢复 |
| reattempt | retry 是正确、相同 misleading、neutral、grounding failure 或 premature complete |
| condition contrast | 同一样本 candidate/reference 条件的具体轨迹差异；只有获得严格 matched `R+ / R−` 后才可改称 method/control |
| diagnosis | visual reading / verification / reversal / belief revision / grounding / planning / completion |
| unresolved problem | GUI-Reflection 仍缺少的能力 |
| improvement hypothesis | 可由下一项研究直接处理的机制，不从单例外推总体结论 |

建议的逐样本对照标签包括：

- `candidate_prevents_initial_deception`
- `reference_prevents_initial_deception`
- `candidate_only_recovery`
- `reference_only_recovery`
- `both_recover`
- `neither_recovers`
- `candidate_same_misleading_reentry`
- `reference_same_misleading_reentry`
- `feedback_understood_but_action_not_rebound`
- `clean_visual_reading_failure`
- `interface_censored`
- `not_comparable_different_eligibility`

这些标签是 dossier 索引，不是强制的总体统计量。`candidate/reference` 必须同时写出完整 provenance（checkpoint、reflection-training status、history、workflow、evidence）；只有真正的 matched reflection-training ablation 才允许在论文结果中重命名为 `method/control`。

每份 dossier 采用 analyst + adversarial reviewer 两遍审阅。第一遍尽可能隐藏 `condition` 名称，只看截图、真实事件和 milestone；第二遍专门尝试推翻“发生了 verification/reversal/recovery”的判断，核对 review 是否被模型看到、Back 是否有效、POST 是否真实发生、hidden scorer 是否存在。争议保留双方理由，不为了得到单一标签强制合并。模型的 thought 可用于解释，但不能覆盖服务器事件。

## 10. 首轮样本选择

第一轮仍用 smoke17，但用途改变：

- 逐样本检查 compact UI 和 evidence 是否有效；
- 优先 `env008`，因为已有自然轨迹显示 misleading belief `Wind` 在 Back 后持续，并发生同 dashboard 重入；
- `b002`、`b011`、`b012` 用于检查“能读 chart 但不会进入/完成 form”的分离；
- `b001`、`pub001`、`pub005` 用于验证 compact UI 是否消除 landing-page/Back 循环；
- `env032` 仅作工程样本，因 GT review 冲突不进入论文主论证。

smoke17 完成逐样本 dossier 后，再扩展 strict_review94；不按平均分自动停止，也不因少数成功就宣称完全解决。

根据现有 formal trace，首批实际运行按机制覆盖而不是按 slug 顺序：

1. `env008`：Back 后仍坚持 Wind，直接检验 premise persistence；
2. `b035`、`health016`：错误标题/annotation anchoring，而 clean arm 已给出相反判断；
3. `b011`：clean arm 也把 7940→5121 读成 Increase，检验一般比较能力地板；
4. `b012`、`pub008`：打印值与阈值，且动作可能与口述前提不一致；
5. `env025`：需要重新计算平均值；
6. `pub010`、`pub020`：趋势/类别—数值绑定；
7. `pub005`：误导图将候选压入同一个颜色 bin，必须主动切换到 reference data，而非只重看同一图。

每类反证都针对被否定的前提：annotation 用端点值，disproportion 用实体—值并列，truncated scale 用目标值与阈值，average 用原始值和重算提示，categorical bin 则提供可主动访问的独立数据源。统一给“正确答案句”会把不同失败层压成提示服从性。

## 11. 结果解释

可能出现的有信息量结果不是只有“解决/未解决”。以下均是待检验的逐样本解释规则，不是当前结果；除第一项外也主要用于提出后续隔离实验，而非直接作因果结论：

- 只有在严格 matched `R+ / R−` 中 `R+` 更少进入 misleading branch，才与 reflection training 降低 initial deception 的解释一致；若两者都已受骗，则继续比较恢复阶段；
- 两个 context 条件在 clean arm 都能恢复而 official arm 都不能，与视觉证据质量构成瓶颈的解释一致，但仍需排除任务难度和 evidence 可见性差异；
- reset 条件恢复而 stateful 不恢复，提示历史可能维持了错误选择；不能由单例断言内部信念被“固化”；
- stateful 恢复而 t0/reset 不恢复，提示历史截图或轨迹上下文可能有贡献；checkpoint、当前可见证据和随机性必须匹配；
- 能口述正确事实却再次实际点击 misleading option，构成事实陈述与动作选择脱钩的行为证据；它不单独证明某个不可观察的内部表示；
- 有效 Back 后在同一页面重入错误分支，证明局部 UI reversal 没有带来该次行为改选；premise revision 仍需独立语言/跨布局证据；
- F2 恢复而 F0/F1 不恢复，与视觉读取或独立证据获取是瓶颈的解释一致；F2 只能作为 evidence-assisted upper bound；
- compact UI 成功而 formal shell 失败只证明两个执行条件不同；因为 UI、流程和反馈都变化，不能单独归因为 Web grounding，需再做 matched shell/UI 消融；
- compact UI 仍失败可排除一部分原 shell grounding 噪声，但还要区分视觉读取、verification、reversal、事实—动作绑定和 completion，不能直接归因于单一 reflection mechanism。

以上逐样本差异将直接用于提出下一研究点，而不是先压缩成单一 success rate 再寻找解释。

## 12. 首轮执行表与交付物

每个入选 case 的主表先固定保留以下单元，逐行展示 milestone vector，不要求先求平均：

| 轨道 | chart | policy/context | 主要回答 |
|---|---|---|---|
| natural + neutral recheck | official / clean | SFT native4 | 是否自然受骗、能否自主核验并修正 |
| natural + neutral recheck | official / clean | SFT current-visible reset | 去掉跨步状态后，同一当前证据下会发生什么 |
| inherited-error + F3 | official / clean | SFT native4 | 在相同已知错误下，完整轨迹上下文是否支持改选 |
| inherited-error + F3 | official / clean | SFT current-visible reset | 相同 handoff state 下的 context reference condition |
| natural single attempt | official / clean | SFT native4 | 没有 recovery workflow 时的首次选择和提交 |
| matched SFT/full-pipeline ablation | official / clean | stage-matched no-reflection SFT policy | `O−/C−`；不能用 bare regular GUI-Pretrain 代填，权重获得或重训前保持 pending |

`temporal_len=0` 可作为额外的 `visual_history_off` 行；公开 GUI-Reflection pretrain 可作为 `checkpoint_stage=pretrain` 行。获得 regular GUI-Pretrain 后，可以另建 pretrain-stage matched 表，但两者都不能占用 SFT/full-pipeline matched ablation 行。

每个 run 的机器记录最终归约为：

```text
initial choice
→ review screenshot consumed?
→ review exit effective?
→ retry choice
→ same misleading re-entry?
→ retry review consumed?
→ confirm event
→ hidden submission/outcome
```

每个 case 的人工 dossier 同时写出：两组轨迹的具体差异、被帮助的阶段、仍失败的阶段、clean ability floor、最可能的新方法假设。允许得到 `candidate_only_recovery`、`both_recover`、`verbal_only`、`same_misleading_reentry`、`corrected_but_no_submit` 或 `grounding_censored` 等不同结论；不得把它们强行压成“完全解决/完全无效”。

## 13. 可由失败类型触发的下一研究点

这些方向只在对应样本证据出现后提出，不预设 GUI-Reflection 一定失败：

- **premise dependency invalidation**：显式保存 `visual evidence → claim → selected action`；当 verification 否定 claim 时，递归失效依赖它的 action，而不是只把上一点击加入错误列表；
- **externally grounded action verification**：用真实 UI outcome/POST/state 对照 action purpose，抑制模型自产生的成功叙事确认偏差；
- **entity/value/action rebinding**：针对 `b002/env008/pub020`，把修正后的实体—值事实重新绑定到 canonical action，区分“说对事实”和“点对动作”；
- **contradiction localization**：针对 annotation、axis、legend、threshold 分别指出应复核的视觉关系，但不泄漏答案；
- **evidence-source switching**：针对 `pub005` 这类图本身信息不足的样本，让 agent 撤销“同一图足够”的前提并主动查 reference data；
- **reasoning recovery 与 execution recovery 解耦**：correct-action switch、有效提交和视觉前提更新分开建模，避免 GUI grounding 或 completion failure 掩盖认知纠错。
