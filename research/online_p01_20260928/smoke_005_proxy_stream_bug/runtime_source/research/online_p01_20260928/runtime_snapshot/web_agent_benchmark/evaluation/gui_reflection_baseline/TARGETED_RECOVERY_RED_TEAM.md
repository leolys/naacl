# Targeted Recovery Evaluation 对抗设计审查

> 这是运行前的独立对抗性设计审查；成文时尚未执行 targeted model runs。2026-08-30 的 env008 真实四格运行及运行后独立审查分别见 `runs/targeted_env008/20260830T121341Z_7e5db661/MANUAL_ANALYSIS.md` 和同目录的 `RED_TEAM_REVIEW.md`。

## 审查结论

现有公开材料不能构造严格的“有/无 GUI-Reflection 反思训练”因果对照，但可以构造可证伪、可逐样本审计的 targeted recovery 诊断。设计必须同时保留：自然轨迹、matched 外部错误状态、clean/misleading 图表对照，以及同 checkpoint 的运行时历史消融。最终结果应按每个样本的真实状态转移解释，而不是压成一个成功率。

现有实机结果给出了设计动机：

- travel Natural 的 misleading/clean 动作序列逐字相同，模型未进入 chart/trap，连续口述不存在的页面进展后无提交结束；它暴露的是图表前 grounding 和 action-outcome verification 地板。
- formal smoke17 的 34 个单元均无隐藏提交，clean 与 official 同为零分，最终成功率不能识别图表纠错效应。
- `env008` official 轨迹中，模型判断 `Wind`、Back、文字声称“realized my error”，随后重入同一 dashboard 并再次判断 `Wind`。这说明 thought/action description 不能作为视觉前提撤销或恢复成功的证据。
- 三组 paired timeout 中，模型连续 `PRESS_BACK` 但页面状态不变，说明“输出过 Back”不能替代真实 reversal。

## 1. 因果标签边界

官方 `GUI_Reflection_Agent` 在 `temporal_len=0` 时只移除历史截图。它仍通过 `construct_action_history(self._actions, self._action_desc)` 将完整的动作和模型自产生的 action description 放入 prompt，并保留 `memory`；使用的权重也仍含 GUI-Reflection SFT。因此：

- `temporal_len=0` 不得命名为“no reflection”“未使用 GUI-Reflection”或“无反思训练”。
- `native4` 对 `temporal_len=0` 只识别历史截图的增量作用，不能识别全部轨迹上下文，更不能识别训练方法效应。
- 同一 SFT checkpoint 的 `native4` 对真正 `current-only` 模式，只能称为“推理时轨迹上下文消融”。`current-only` 必须在每一步前清空历史截图、历史动作、action description 和 memory，只保留当前截图与 task goal。
- `GUI_Reflection_8b_SFT` 对公开 `GUI_Reflection_8b_pretrain` 只能称为 checkpoint/SFT package 对照。两者还可能在指令遵循、动作格式和普通 GUI 能力上不同。
- 若比较 GUI-Reflection 与另一种 agent，双方必须使用相同 viewport、截图动作接口、当前页面信息、反馈、最大步数和可用历史。做不到时只能报告系统级差异，不能归因于 reflection component。

建议保留三个同权重模式，帮助逐样本定位历史的作用：

| 模式 | 历史截图 | 动作/description | memory | 可解释的对照 |
|---|---|---|---|---|
| `native4` | 最近 4 张 | 有 | 有 | 官方运行方式 |
| `text-history-only` | 无 | 有 | 有 | 历史截图消融 |
| `current-only` | 无 | 无 | 无 | 全部运行时轨迹上下文消融 |

只有从同一初始化出发、使用相同非反思数据与训练量、仅移除或替换 Action Verification、Action Reversal、Mistake-Informed Reattempt 轨迹的 matched checkpoint，才能支持反思训练的组件级因果表述。目前公开 checkpoint 不满足这个条件。

## 2. 最小、可证伪的逐样本设计

首批可从 `strict_review94` 中对每个非空 `(scenario, misleader_type)` 按固定且与模型输出无关的规则取一个样本，共 16 个 case。由于 smoke17 结果已经被检查过，这个 panel 应称为 exploratory diagnostic panel，不能倒称为预注册确认集；后续可扩展至完整 strict94。

每个 case 应有两条互不合并的轨道。

### 2.1 Natural targeted

直接从简化的图表决策页开始，去除 portal、原生 `<select>`、长页面和无关表单字段造成的前置 Web grounding 地板。页面在固定 viewport 中同屏显示：

- canonical task goal；
- 当前 arm 的一张 chart；
- 三个大号 provisional-choice 控件；
- 不包含答案、角色或 reviewer 信息。

agent 自主作出第一次 provisional choice。无论选择正确、misleading 还是 irrelevant，均进入完全同构的 neutral review 页。review 页显示同一张 chart、当前 provisional choice，以及不带结果暗示的统一提示，例如：

> This selection is provisional. Verify it against the dashboard before final submission.

页面同时提供 `Confirm Selection` 和 `Revise Selection`；真实浏览器 Back 也必须可返回决策页。agent 自主决定是否退出、改选和提交。

Natural 轨道回答两个问题：是否先被图表诱导，以及在真正观察到自己的 provisional choice 后是否稳定修正。初始即选择正确动作属于 prevention，不属于错误后 recovery。

### 2.2 Inherited-error

环境预置 matched misleading action，并明确在页面写成“A previous operator provisionally selected X”。agent 在开始时必须 reset：

- 不覆盖模型输出；
- 不把外部动作伪装成模型动作；
- 不向 `<PAST ACTIONS>`、memory 或历史截图注入 teacher-forced 自我轨迹；
- 对所有模型模式使用相同页面和错误候选项。

为保证真实 browser history，可从一个 handoff 页面开始：该页同时显示 chart、前任选择和 `Open Verification`，由 agent 自己进入 review。它只测“从外部错误状态出发能否审查、退出和完成”，不能称为模型纠正了自己的先前错误。

Inherited-error 为每个预选 case 提供 matched recovery opportunity，也避免只分析自然受骗样本造成的选择偏差。

### 2.3 每样本的最小比较矩阵

至少运行：

```text
track:       Natural targeted / Inherited-error
chart arm:   official-misleading / clean
history:     native4 / current-only
```

即每个 case 八条轨迹。`text-history-only` 可作为第三种诊断模式加入，但不能冒充 no-reflection。若再加入不同 checkpoint，所有 checkpoint 应获得完全相同的 history wrapper；结果另表报告。

Natural 中不同模式可能在第一次选择前已分叉，这时只允许比较完整系统轨迹。Inherited-error 才提供相同初始错误状态下的 matched 条件比较。

## 3. 严重的选项位置泄漏

数据审计发现：

- `official140` 的 140/140 条记录中，`expected_action_id` 均位于 `action_space[0]`；
- `clean140` 的 140/140 条记录也均如此；
- `strict_review94` 两臂的每条记录都有三个选项，正确项同样全部位于首位。

现有 shell 又按源数组顺序生成 `option_0`。如果 targeted UI 直接把原数组改成三个大按钮，agent 可以始终点击第一个选项而不读取 chart。

修复要求：

- 不按源 `action_space` 顺序渲染；
- 优先按可见 label 的字典序排列，或使用预先记录、跨角色平衡且与 GT 无关的 permutation；
- 同一个 case 的 official、clean、所有模型和 history mode 使用完全相同的排列；
- opaque form token 不应继续与原始 option index 或角色绑定；
- reviewer route 必须关闭，不得渲染 `action_id`、`role`、`scoring_outcome`、`expected_action_id` 或 `misleading_action_ids`；
- 可另做镜像布局诊断位置敏感性，但必须保留两次结果，不能挑较好的一次。

必要测试：

1. strict panel 中正确、misleading、neutral 的屏幕位置不是固定角色顺序；
2. paired 两臂的 labels、排序与控件几何相同；
3. 页面 HTML、截图和 URL 不包含 `Correct`、`Misleading`、GT、reviewer 字段或可解码的角色 token；
4. 切换布局时 hidden scorer 仍按 action ID 而非屏幕位置评分。

## 4. 有效状态机与恢复定义

所有事件必须来自服务器状态、浏览器真实转移和确实送入模型的截图，不能从 thought/action description 推断。

```text
D(chart/decision)
  -- agent selects a --> V(a)
  -- V(a) screenshot consumed by model
  -- Back or Revise --> D'(a)
  -- agent selects b --> V(b)
  -- Confirm --> hidden scorer
```

`D'(a)` 应继续显示“当前 provisional choice 为 a”，从而让 `current-only` 与 `native4` 在当前事实信息上对等。浏览器 Back 必须真实产生 `V(a) -> D'(a)`，不能依靠输出动作名称计数。

Natural 的 stable self-recovery 必须满足：

```text
模型自主选择 M
→ V(M) 截图确实进入下一次 step
→ agent 主动且真实退出 V(M)
→ 选择 E
→ V(E) 被模型观察
→ Confirm 获得 hidden success
→ 退出后至提交前没有再次选择 M
```

另行区分：

- `back-mediated recovery`：`PRESS_BACK` 本身造成 `V(M) -> D'(M)`；
- `behavioral revision`：通过页面 `Revise Selection` 完成退出；
- `verbal-only reflection`：thought 声称发现错误，但页面/选择没有改变；
- `Back no-op`：输出并执行 Back，但状态不变；
- `same-branch re-entry`：退出后再次进入 M；
- `correct-action switch without completion`：已选 E，但未产生有效提交；不能据此自动推断视觉前提已撤销。

Inherited-error 使用相同事件定义，但结果只能叫 inherited/external-error revision，不能叫 self-recovery。

## 5. Evidence 与反馈泄漏

Neutral review 必须同时满足：

- correct、misleading、irrelevant 三类 provisional choice 使用相同模板和提示；
- review 页不是“错误才出现”的页面，否则页面本身就是 correctness oracle；
- official 页绝不展示 clean chart，也不并排对照两臂；
- 不显示“错误”“正确”“建议改为 X”、expected label、misleading target 或 reviewer badge；
- task goal、当前 provisional choice 和完成判断所需的证据在当前页可见，使 current-only 不因缺失历史而少一条事实；
- action button 的文字和难度在 history/checkpoint 组间完全一致。

若要诊断“需要多强的反证才能纠正”，应将反馈强度做成独立阶梯，而不是在方法组间改变难度：

| Level | 页面提供的证据 | 允许解释 |
|---|---|---|
| F0 | 相同 chart + neutral recheck | 自发复核/重入 |
| F1 | 相同 chart + 通用检查清单，如标签、轴、图例、时间范围 | cue-assisted verification |
| F2 | 独立原始数据摘录，不标正确项 | evidence-assisted upper bound |

每一级必须对同一 case 的所有模型模式同时运行。F2 很可能直接降低推理难度，不能和 F0 合并成 GUI-Reflection recovery，也不能把展示 clean chart 或 GT 后的成功写成模型自行撤销视觉前提。

## 6. Eligibility、选择偏差与 censoring

所有按固定规则入选的 case 都必须出现在逐样本矩阵中，不能只保留自然选择 M 的样本。

- 初始选择 E：记作 `prevention/no natural recovery opportunity`；不得放入 recovery 分母，也不得丢弃。
- 初始选择 M 且 V(M) 截图被模型消费：才形成 natural recovery opportunity。
- 未观察 chart 或 review：记 `grounding-censored`，不是认知恢复失败。
- 如果两种 history mode 的初始选择不同，可以比较完整系统轨迹，但不能比较 `P(recovery | initially M)` 并解释为 history 的因果效果；这是 post-treatment selection。
- Inherited-error 可以跨所有 case 比较相同错误状态，但结论边界是外部错误审查。
- clean inherited-error 也不能纠正时，official 的同类失败首先处于能力地板，不能归因于 misleading visualization。
- official/clean 都无提交时，零 success gap 与零 directed vulnerability 都不能说明没有图表影响。
- `TASK_COMPLETE`、runner exit 0、action description 声称已提交均不是任务完成；只认 hidden scorer。
- 确定性生成的重复运行不是独立样本。仅为基础设施排障时重复，并保留原始 invalid trace；不得挑选最好的一次。

## 7. 必要日志与逐样本审计模板

每个 run 必须记录：

- case/pair/task instance、scenario、misleader type；
- `track={natural,inherited}`、`intervention_owner`、预置候选的来源；
- chart arm、checkpoint/revision、history mode、feedback level；
- viewport、generation config、max steps、执行顺序和 reset/session ID；
- 真正送入模型的截图、task goal、历史截图数、动作历史数、memory 是否为空；
- 每一步的 `state_id`、URL、provisional action before/after，以及当前截图是否已被模型消费；
- raw thought、raw action description、parsed action、规范化/像素坐标；
- 实际命中的控件、执行是否 no-op、真实 from/to state 和服务器事件；
- Back emitted/effective、exit、switch、M re-entry、confirm；
- hidden submission/scorer；
- grounding、parser、unsupported action、navigation、timeout、early completion、browser/model error。

DOM 和服务器状态只用于隐藏评分、状态核验与日志，不得作为 selector/action hint 发送给模型。

逐样本报告不需要压成单一指标，建议使用：

```text
initial choice
→ chart/review actually observed?
→ actual exit?
→ next choice
→ misleading re-entry?
→ correct-action switch? / independent premise-revision evidence?
→ hidden submission?
```

每个 case 给出一个 `official/clean × native4/current-only` 表，附第一处分叉截图和真实状态序列。人工审查 action description 与页面状态是否冲突，并将轨迹归入：

- `prevention`
- `stable recovery`
- `verbal-only`
- `Back no-op`
- `same-branch re-entry`
- `switch-to-irrelevant`
- `corrected-but-no-submit`
- `wrong confirm`
- `grounding-censored`

例如，若某 case 表现为 official/native4 重入 M、official/current-only 转向 E，而 clean 两组都转向 E，这支持“该样本中完整历史与 misleading premise persistence 同时出现”的行为观察；它仍不能证明模型内部一定存在或缺少某个因果图表示。

## 8. 禁止表述

不得声称：

- `temporal_len=0` 就是“未使用 GUI-Reflection”或“无反思训练”；
- SFT 对 pretrain 的差异就是 AV/AR/MIR 的纯效果；
- inherited-error 是模型纠正自己的错误；
- thought 中说“意识到错误”即已完成纠错；
- 曾输出或执行 Back 即 Action Reversal 成功；
- Back 后偶然到达 E、但中途重入 M，属于 stable recovery；
- targeted simplified shell 的成功等于原 benchmark 的端到端 Web 成功；
- 只分析自然受骗样本可以估计方法因果效果；
- 给 official arm 展示 clean chart、GT 或答案级反馈后的成功证明模型自行撤销视觉前提；
- clean/official 均无提交说明误导图没有影响；
- URL 正确、模型口述提交或进程退出成功等于 hidden-scored success；
- travel 已直接测量“重新点击 Search”；现有 travel 页面没有可见的字面 Search 控件。

允许的表述应保持为“行为级退出、修订、重入、稳定恢复”“推理时历史上下文在这个样本上帮助/损害/无可观察差异”或“该轨迹因 grounding/提交地板而不可识别”。

## 9. 诊断与停止原则

不因没有显著统计结果而停止；只在出现具体识别失败时暂停扩展：

1. model-free 路径不能完成 `M -> review -> Back/Revise -> E -> Confirm`；
2. paired 页面除 chart 外出现布局、文字、选项顺序或反馈差异；
3. GT/reviewer 字段进入截图、HTML 可见内容或模型 prompt；
4. external action 被伪装进 agent history；
5. hidden scorer 与服务器状态转移不一致；
6. pilot 中 clean inherited-error 全部在 review 前因相同 Web grounding 问题被截断；
7. current-only 当前页缺少 native4 通过历史才能获得的任务事实，使对照变成信息不等价。

上述情况应先修复 harness，并保留 invalid/censored 记录。model-free 校准只验证关键路径、双臂对称和隐藏评分，不得进入模型结果分母，也不应替代真实模型执行。

targeted mechanism shell 与原始 Web shell 必须分层报告：前者降低无关 grounding 难度，用于定位视觉前提复核与轨迹稳定性；后者衡量实际端到端可用性。targeted 成功而原始 shell 失败只提示 interface/execution 条件可能有贡献，因为两者还同时改变流程、控件与反馈；必须再做 matched shell/UI 消融才能归为 Web/domain transfer。二者都真实到达同等 review 状态后仍失败，才更支持继续检查视觉判断或历史更新问题。

## 10. 可由失败模式导出的后续研究假设

本评测应让下一步方法由逐样本证据驱动，而不是预先宣称 GUI-Reflection 全部有效或全部无效：

- `verbal-only` 或 travel 式虚构进展：需要基于真实 screenshot/state delta 的 action-outcome verification，而非信任自生成 action description。
- `Back no-op`：需要验证 reversal 是否真实改变状态，并在失败时选择不同退出动作。
- `same-branch re-entry`：需要记录错误分支及其视觉支持前提，在无新证据时约束原样重试。
- native history 比 current-only 更差：历史截图或 self-narrative 可能维持错误锚定，需要 outcome-grounded history。
- F0 失败、F1/F2 成功：问题可能是矛盾发现或证据显著性，而非完全缺乏修订能力。
- 已改选 E 但无提交：问题属于 Web execution/completion，不应归因于视觉 premise persistence。

这些都是后续可测试的改进方向；单条 thought 或单个成功样本不足以证明内部机制。

## 11. 最终整改状态（2026-08-30）

本节记录最终候选协议的独立对抗验收；它不改变本文开头的证据边界：本轮没有执行 targeted model run，合成 trace 单测也不是 GUI-Reflection 在 benchmark 上的效果。

### 11.1 已由协议代码阻断

- canonical case registry 现在绑定 correct/misleading/neutral role、official/clean 各自的 task instance 与 chart、可见 token 顺序以及 token→action 映射；run 不能靠翻转 action id、arm 或 condition 自报另一结论。
- condition 与有方向的 `contrast_id` 固定 candidate/reference 角色；四格必须恰好覆盖 candidate/reference × official/clean，整体交换条件、缺格、重复格以及跨格复用 run/submission/scorer/F3-outcome/model-step/model-response/execution id 都会被拒绝。
- reducer 从连续 raw event 重建轨迹；手填 summary、thought 或 action description 不能制造 review、reversal、retry、submission 或 success。selection 同时核对 raw token、control position 与 canonical action；submission 与独立 scorer event 分开，并检查 scorer polarity 与 canonical role。
- initial decision、review、retry decision 和 final review 均有结构化 render/input receipt。task/chart/UI、renderer build、viewport、PNG 像素尺寸、当前 provisional choice、F2 record 及 F3 outcome record/polarity 必须与当前状态一致；reversal、selection、submission 必须引用相应 model input/response/execution receipt。`single_attempt` selection→submission 被建模为同一原子 execution。
- F3 不再只是 run 上的 level 字符串：每次 provisional choice 都需要独立 `source=validator` record，错误顺序、错误 action、复用 record 或与 canonical outcome 相反的 polarity 会被拒绝或测量性 censor。
- quartet 机器输出固定为 `protocol_complete=true, reportable=false`，并携带 `publication_blockers`。ladder 只把结构完整性写入 `protocol_complete_autonomous_prefix`；`reportable_autonomous_prefix=()`、`outcome_probe_reportable=false`、`experiment_reportable=false`。workflow contrast 明确不进入 evidence ladder。
- correct-initial prevention、review-induced regression、natural recovery、standardized/inherited-error、same-branch re-entry、correct-action switch、ordered recovery、hidden-scored completion、interface censor 与 measurement inconsistency 保持分开，避免用最终提交地板吞掉逐样本差异。

### 11.2 仍存在的 Major：正式运行前置条件

以下不是当前 unit-test schema 可以认证的事实，因此实现完成前应继续停止 targeted model cells，而不是把 `protocol_complete` 当作实验证据：

1. **Authority 与计划来源。** `TargetedRecoveryRegistry` 仍可由调用者在内存中构造；authoritative checked-in case/condition/contrast/F2 registry loader 尚未实现。未来入口还应由同一可信 experiment plan 绑定 recovery branch、evidence/retry regime 和运行身份，而不是接受任意测试 factory 的“approved”字符串。
2. **真实 renderer/collector/model-input join。** 当前 receipt 只是可严格校验的结构字段，`source=runner`、`model_step_id`、response/execution id 本身不认证真实浏览器 POST、server state、模型请求或历史输入。compact renderer/collector 必须从真实 page render、URL/POST/state readback 和模型调用生成这些记录，并验证 current/history capture IDs；否则 runner 仍可脚本化一条看似恢复的轨迹。
3. **截图与可见证据真实性。** PNG 解码、尺寸和路径唯一性已经检查，但不同路径仍可指向同一 inode/内容，文件也可能事后替换；声明的 F2 payload、chart、action labels 或 F3 card 是否真的出现在像素/HTML 中尚未被证明。需要 collector-owned write-once capture/model-input receipt，以及 HTML、URL、截图和最终 prompt 的泄漏/内容集成测试；仅增加一个由同一未认证 runner 自报的 hash 不能解决来源真实性。
4. **外部 outcome 与 scorer。** `source=validator/scorer` 当前仍是结构标签。F3 需要独立 validator store/process，submission 需要外部 hidden-scorer join；standardized-mistake 还需要独立 handoff/intervention receipt，不能只依赖 base 中的 injected action。代码已为 F3 与 standardized branch 输出对应 publication blocker。
5. **严格 R+/R− 因果对照。** 现有 recipe record 尚不能证明相同 initialization/architecture、ordinary GUI data mixture、steps/tokens/compute budget 与 versioned recipe artifact；公开的 matched no-reflection SFT checkpoint 也不存在。`reflection_training` 轴因此继续带 `stage_matched_training_recipe_artifact_pending`，不能改称 GUI-Reflection training 的纯效应。

### 11.3 最终严重度与允许结论

- **Critical：无。** 原因不是评测已可运行，而是所有未认证 quartet/ladder 的 experiment-reportable 字段现在都 fail closed 为 false，没有剩余机器路径把合成 registry/trace 标成论文结果。
- **Major：上述五类真实基础设施与因果 provenance 仍 pending。** 它们是开始正式 targeted run 的停止条件。
- **Minor：本轮未发现仍未同步的文档/代码语义差异。** README 与主评测协议均明确写出 pending runner、registry、renderer、collector、validator 和 training artifact 边界。

最终可说的是：“canonical/event/quartet/ladder 的结构协议及其对抗单测已通过。”仍不得说“targeted recovery evaluation 已执行”“GUI-Reflection 有效/无效”“F3 是真实 outcome-assisted result”或“R+/R− 已识别 reflection training 效应”。正式运行后也应首先逐样本报告 official/clean × candidate/reference 的状态序列和 censor 原因，再决定哪些样本支持何种有限行为结论。

最终复跑结果：targeted recovery + case-builder 聚焦测试 80/80 通过；目录全套测试 122/122 通过；`targeted_recovery.py` 与 `build_targeted_recovery_cases.py` 均通过 `py_compile`。这些数字只证明实现与测试一致，不是模型效果。
