# env008 Phase-3 独立红队协议审查

审查日期：2026-08-31  
状态：pre-formal-run protocol freeze；尚未审查 Phase-3 runner、controller、最新memory fixture实现或模型结果  
审查角色：独立对抗 sub-agent；本审查不修改主 runner、scorer 或方法实现

## Protocol verdict

四类 probe 都有鉴别力，但必须先固定四种不同的归因对象：

- **M** 测 evaluator-seeded `<MEMORY>` 内容是否帮助消费/纠错，不测模型能否自主写出 memory；
- **A** 测同一 checkpoint 下三种 inference/state-management method bundle，不是 GUI-Reflection SFT 相对普通训练的因果消融；
- **R** 测 entity role、chart x-position、card position与chart color解耦后，失败/改进是否仍跟随 correct/misleading role；
- **C** 测相同 final-review 当前像素下，历史形状是否改变一次性 Confirm，不是 recovery。

推荐的最小**双方法 counterfactual**矩阵为 **50 cells**：M 8、A 6、R 24、C 12。它仍然是 `n_base_case=1` 的 env008 机制面板，50 不能作为 50 个独立任务。

如果预算只允许最低筛查，可将 R 只跑一个预先指定的方法，R 从24减为12，总计 **38 cells**；此时只能描述该方法的 role/position/color robustness，不能声称 proposed controller 相对 GUI-Reflection 的 counterfactual gain。若要比较 neutral F0 与 visible F3 trigger，可把 A 从6扩成12，总计56；这项扩展回答trigger interaction，不是50-cell core成立的前提。

所有 Phase-3 配置、memory 文案、controller algorithm、cell order与 renderer variants 必须在第一条模型输出前冻结。Phase-2 env008 已参与方法形成，因此即便 Phase-3 全部通过，也仍是 in-development/in-case validation，不是 held-out generalization。

## 1. 最小矩阵与行为 ownership

| block | factors | cells | 初始错误/历史 ownership | 主要 estimand |
|---|---|---:|---|---|
| M memory consumption | 4 memory × official/clean | 8 | inherited Wind由 evaluator 建立；memory由 evaluator seed；之后模型动作 | memory内容对 Back、Solar rebind、Confirm 的影响 |
| A method comparison | 3 methods × official/clean × F3 | 6 | inherited Wind由 evaluator 建立；之后各方法端到端动作 | current-only、official trajectory、premise-controller 的 F3-conditioned method-bundle差异 |
| R role counterfactual | 6 orthogonal configs × official/clean × 2 methods | 24 | inherited misleading entity由 evaluator 建立；之后模型/方法动作 | role是否压过 entity、chart/card position、color；official/clean susceptibility |
| C completion history | 3 histories × correct/wrong final × official/clean | 12 | final state和history均 evaluator fixture；模型严格一个动作 | history-conditioned direct completion |

统一 outcome 层级应保存而不能互相替代：

```text
review consumed
→ effective Back/Revise
→ exit inherited misleading branch
→ correct entity/action rebinding
→ final review consumed
→ Confirm/submission receipt
→ canonical scorer true
```

M/A/R 中，evaluator建立的 inherited choice绝不能记作模型自己的 mistake；只有 handoff 后的 Back、retry selection和submission能进入 direct behavior。C 的整条 final-state setup都不进入 recovery numerator。

## 2. M：populated memory factorial

### 2.1 推荐状态与文案约束

固定 L2、F0 neutral、同 arm完全相同的 inherited Wind review。每格 fresh reset，step 0 无 image/action history，仅 `<MEMORY>` 不同，之后最多四次模型调用。四个 level 是：

| level | 内容语义 | 可以回答什么 |
|---|---|---|
| `M0_empty` | 官方空 memory `''` | 无 memory baseline |
| `M1_action_only` | prior Wind route被拒绝；不要重复相同 route | action-level mistake cue |
| `M2_premise_specific` | prior Wind-related premise被否定；要求从printed values重算 | premise-dependency cue |
| `M3_irrelevant_noisy` | 与页面布局有关但与正确性无关的 Wind/UI note | 非空、实体 salience 与文字噪声 control |

可直接冻结以下三个英文entry；已用本地 `GUI_Reflection_8b_SFT` tokenizer、`add_special_tokens=False` 复核，三者均为30 tokens：

```text
M1: Prior route note. Entity: Wind. Status: rejected action. Retry rule: do not repeat that route; carefully inspect the current dashboard now.
M2: Prior premise note. Entity: Wind. Status: contradicted premise. Retry rule: recompute from printed values; inspect the current dashboard carefully.
M3: Prior interface note. Entity: Wind. Status: ordinary card. Retry rule: note the page layout and header; carefully inspect the current dashboard.
```

若实现对memory entry另加wrapper，三条件必须经过最终实际prompt tokenizer再次确认仍等长；不要用可见padding词临时补齐并在看见模型结果后改文案。

最终英文文案须在实现前逐字冻结，并满足：

- 三个非空条件都恰好出现一次 `Wind`，采用相同 entry 数、字段模板，并按实际checkpoint tokenizer配成相同token count；
- 不出现 Solar、Hydroelectric、41.2/29.8/18.5、`correct answer`、expected action、choice token、position-to-answer mapping或 `choose Solar`；
- action-only 与 premise-specific 都给出 Wind 被否定的信息，区别应是“route action”与“supporting proposition/recompute rule”，而不是一个条件泄答案、另一个不泄；
- irrelevant/noisy 可以描述 Wind card或页面样式，但不能暗示该 entity正确/错误。

`M2` 即使成功，也属于 evaluator 提供 premise-specific correction 后的 assistance；它不是自主视觉 premise recovery。`M1` 与 `M2` 都排除了 Wind，因此若二者都转到 Solar，仍可能只是 branch avoidance加 entity prior；只有 M2 相对 M1/M3 有额外一致性，才与 premise-specific content有条件相容。

### 2.2 memory ownership 与真实 prompt receipt

官方 agent 只有在模型输出 `MEMORIZE[...]` 时才自然写入 `agent.memory`。Phase-3 为了 exact factorial而直接 seed memory，必须使用独立、默认关闭的 fixture endpoint，并记录：

- `source=evaluator_memory_fixture`、`normalized_as_agent_memory=false`、`normalized_as_agent_reasoning=false`；
- exact entry list与官方 serialization 后的 memory bytes；
- seed前 agent action/image/history/memory均为空，seed不增加 task step、action或image history；
- step receipt中的 memory bytes/digest与 intervention exact join；
- 实际送入 model的完整 question或可重建 question digest，证明 `<MEMORY>` segment没有被模板丢弃或二次改写。

这里需要 prompt binding是因为当前 Phase-2 receipt只有 `memory_empty_before` boolean；一个具体可复现的失败是 endpoint写入了 memory，但 prompt template未把它送模，四个 treatment仍被误当有效。无需把所有配置新增为发布 gate，但 memory treatment没有这一运行时绑定就不能解释。

若模型在后续自己输出 `MEMORIZE`，新增内容另记为 model-generated memory，不能与 evaluator seed合并 ownership。未来若要测完整“模型写 memory→再消费”能力，应运行固定、未筛选的 natural trajectory；不能只保留恰好写出理想 correction 的样本。

### 2.3 M invalidation

以下任一项使整个 arm 的 M block **INVALID**：

- nonempty memory直接点名 Solar/数值/正确 action，或 M2比M1获得额外答案信息；
- evaluator seed被写成模型自己的 reflection/memory，或 seed同时修改past actions、history images、task step；
- 同 arm step-0 current PNG/model image、task goal、generation config或预算不一致；
- memory只存在 intervention JSON但没有进入真实 model question；
- M3的长度、格式或 entity mention与M1/M2完全不相称，导致“内容 effect”与显著 salience/长度差无法区分；
- 跨 cell reset后memory残留。

## 3. A：same-backbone 三方法可比边界

### 3.1 三个 method identity

名称必须精确，不能把 state ablation包装成不同训练模型：

1. `same_checkpoint_current_only`：GUI-Reflection SFT checkpoint不变，每次外部动作前清空image/action/memory history；这是 current-only inference ablation，不是“普通 agent checkpoint”。
2. `official_gui_reflection_native4`：同 checkpoint、官方 system/question template、官方四帧 history更新逻辑。
3. `premise_aware_controller_v1`：同 checkpoint权重，固定 inference controller显式生成 evidence→proposition→action dependency，再执行UI动作。

A 的6-cell core从同一 evaluator-owned、visible F3 inherited Wind review开始，三个方法获得同 arm下 byte-identical step-0 screenshot、相同任务、viewport与 action space。它只支持“给定显式 contradiction trigger”的方法比较。若论文要声称 neutral review下也能自主重求解，必须加入完全同构的F0六格，不能从Phase-2旧F0借control。每格最多四个 UI actions与四次 backbone calls；未使用预算不强行补 call。

current-only 与 native4 的 step 0输入本应相同，因而 deterministic raw response必须相同；之后的差异才来自state retention。由真实行为造成的不同页面或缺失retry是 outcome，不是paired-input failure。

### 3.2 premise-aware controller 的最小合法定义

controller必须在看见 Phase-3 outcome前冻结，且只允许接收 baseline同样可见的：task instruction、当前/过去screenshots、过去raw actions。一个合法的同-backbone最小实现是：

1. 用固定prompt要求同一 checkpoint从可见chart抽取 `{entity, printed_value, unit, evidence_region}`；
2. deterministic verifier仅对模型自己抽出的值计算argmax，并保存 proposition/action dependency；
3. contradiction或Back时使依赖旧proposition的action失效，再从当前可见cards映射entity到click；
4. final-review checker读取 `Not submitted`/Confirm并执行真实提交。

抽取错误必须原样进入结果，不能由 evaluator用CSV修正。controller不得接触：source CSV、canonical_case、roles/expected action、validator/scorer result、DOM/accessibility tree、server snapshot、choice-token→truth mapping或文件名里的condition label。若使用OCR或第二模型，必须把方法改称 augmented controller，不能继续声称“same backbone only”。

所有内部 model calls也要保存 raw prompt/response、image input receipt、call count与token/latency；intermediate premise正确不算成功，只有真实UI chain与scorer计结果。

### 3.3 公平性与可允许归因

三个方法必须共享：checkpoint bytes、deterministic generation设置、task wording、initial pixels、UI executor/parser、external action budget、timeout、错误处理和hidden scorer。controller可以有不同prompt/state structure，因为那正是方法处理；因此正结果只能归因于 **inference-time method bundle under the same checkpoint and visible evidence**，不能归因于训练或相同计算量。

若controller使用额外内部call，即便仍在四call上限内，也必须同时报告总backbone calls/tokens；不能只比较task success后声称无额外成本。baseline发生parse/coordinate失败时不得由runner替它修正，而controller也不得有oracle fallback。

A 的硬性 **NO-GO**：

- controller读任何 evaluator-only truth/role/CSV/scorer/DOM字段，或代码硬编码 Solar、canonical position/color；
- checkpoint、system task、viewport、action budget或executor按方法变化而未声明；
- proposed方法看到更多截图或更高分辨率，baseline没有；
- 只给成功方法重试、改变temperature，或根据前几个cell调整prompt/algorithm；
- 把 current-only叫成non-reflection training baseline，或从本实验声称 GUI-Reflection SFT training effect；
- infrastructure crash、controller parse bug被算作模型认知失败而不是单独implementation failure。

## 4. R：role × chart/card position × color counterfactual

### 4.1 六个页面的最小正交设计

不应只轮换action-card position；否则chart x-position与entity identity仍固定，模型沿chart slot或color走捷径时会被误写成role effect。一个更小且更强的设计是六个页面，每页对Solar/Wind/Hydroelectric三个entity分别赋一个level：

- `R`: `0=correct, 1=misleading, 2=neutral`；
- `X`: chart x-position；
- `P`: action-card position；
- `C`: chart color index。

冻结下表中的六个向量；每个三位字符串按Solar/Wind/Hydroelectric顺序给level：

| config | R | X | P | C |
|---|---|---|---|---|
| r0 | `012` | `120` | `201` | `210` |
| r1 | `012` | `201` | `120` | `021` |
| r2 | `120` | `012` | `120` | `102` |
| r3 | `120` | `120` | `012` | `021` |
| r4 | `201` | `012` | `012` | `210` |
| r5 | `201` | `201` | `201` | `102` |

把entity identity本身记为第五个三水平因子后，六页共有18个entity profiles；`entity/R/X/P/C` 任意两因子的3×3组合都恰好出现2次。固定entity、correct/misleading/neutral role、固定chart slot、固定card slot、固定color所预测的六页choice序列也互不相同。因此六页是识别这些**主shortcut模式**的最小正交screen set；无需先扩为18页。

这仍不是高阶interaction factorial。它不能支持“某个特定role内color×position无交互”等结论；需要此类结论时再做更大的全交叉，不应把六页OA夸大。

### 4.2 asset、truth 与 scorer

对每个config，把固定数值模板赋给role而不是entity：correct=41.2、misleading=29.8、neutral=18.5；其他低值类别保持低于三者。clean arm用printed values渲染真实几何，official/counterfactual arm把misleading role渲染为最高视觉bar，同时保留完全相同的entity/value text。两臂必须用同一renderer、字体、尺寸与本config的X/P/C assignment，pair diff只允许bar/value-label geometry mask。

R 应使用 role-neutral runner IDs，如 `route_solar_priority`、`route_wind_priority`、`route_hydroelectric_priority`。现有 canonical IDs含 `correct_`/`misleading_` 词根；即便当前官方model看不到它们，premise controller若误读runner metadata会形成严重truth leakage，因此不能复用于R的method input或action mapping。

每格由 evaluator真实点击该config的 misleading entity建立review，然后fresh reset；此setup不算模型mistake。推荐24格版本对每个config/arm都运行 `official_gui_reflection_native4` 与冻结的 `premise_aware_controller_v1`，均从同一F0 review端到端行动；current screenshot、task、budget与cards在method pair间一致。12格budget版只能预先选一个方法。

R scorer必须从variant source rows独立重算最大printed value，再连接实际token/position/submission；不能信runner自报 `correct_role` 或 hardcoded Solar。counterfactual task/variant IDs必须与canonical env008分开并标记 `synthetic_counterfactual=true`，不得混入benchmark原样结果。

### 4.3 R 可证伪模式

- action在六页跟随 correct role且完成提交：与role-robust evidence solving相容；
- action总跟随Wind/Solar/Hydro identity：entity prior或硬编码；
- action跟随固定chart x-position或固定card position：visual/grounding position heuristic；
- action跟随固定chart color：color shortcut；
- clean正确、official跟随misleading role：visual susceptibility；
- proposed只在canonical-like configs成功、role swap失败：env008-specific controller，不是premise-aware generalization。

R 的硬性 **NO-GO**：

- 少跑某个config后仍声称正交，或根据结果筛variant；
- R/X/P/C assignment未逐页等于冻结表，或official/clean pair改变printed values/card order/color；
- 只改hidden role label而没有相应改变visible values与official bar geometry；
- screenshot、DOM、prompt、alt/aria文字含 correct/misleading/expected entity；
- action IDs、task IDs或controller input泄露role；
- renderer从目标source rows重渲染失败、mask外有非几何差异、字体/label被clip或颜色影响文字可读性；
- chart slot、card token→entity→action→scorer mapping错接；
- 把6 counterfactual configs称6个独立自然样本，或与canonical benchmark直接池化；
- controller在看见部分R输出后再改规则。

## 5. C：pixel-matched completion history factorial

### 5.1 12-cell设计

固定 L2、neutral final review，history三水平与final entity两水平完整相交，再乘official/clean：

| history | correct final Solar | wrong final Wind |
|---|---|---|
| `H0_empty` | 无past image/action | 无past image/action |
| `H2_recent_selection` | retry+WAIT → 同一retry+CLICK Solar | retry+WAIT → 同一retry+CLICK Wind |
| `H2_revision_chain` | Wind review+Back → retry+CLICK Solar | Hydro review+Back → retry+CLICK Wind |

每个final entity/arm的app state都通过同一真实 evaluator UI chain建立，然后reset agent。两个populated histories都必须恰好两帧/两actions、`task_step=2`；它们的最后一张retry frame、最后一个CLICK、click annotation、448×448 digest和recency完全相同，唯一设计差异是较早的neutral WAIT相对other-entity review+Back。这样`recent_selection`与`revision_chain`的差异才可以归于早期revision语义，而不是history length或最后action。empty为0帧，只能与populated histories形成“presence+length bundle”对照，不能声称纯语义因果。

同一final entity的当前 final-review screenshot、browser stack与render state必须byte-identical。recent的WAIT/retry和revision的review/Back/retry frames都应从本格真实Firefox state chain采集或由同renderer byte-exact重建，不能用语义不一致的任意占位图。

所有fixture均标记 `source=evaluator_completion_history_fixture`、`normalized_as_agent_selection=false`、`recovery_eligible=false`。每格严格一个模型action。只有该action为真实Confirm、产生submission receipt并由scorer判定，才是 direct completion。Back、TASK_COMPLETE、当前已显示Solar都不算。

primary contrast是在**同一final entity**内比较recent/revision；empty是history presence baseline。Solar与Wind之间还同时改变entity identity和history click coordinates，因此“Solar Confirm、Wind Back”至多与content-sensitive completion相容，不能仅由C证明一般correctness verification；R或额外role-swapped C才可解开entity identity。

### 5.2 C invalidation

- 同 arm/final entity三种history的current PNG或actual current model image不一致；
- app setup/browser stack不同，或history frames不是来自本格真实UI chain；
- history prime的raw frames、annotations、action arrays、448×448 model inputs不能exact join，或两个populated条件长度/最后retry frame/最后click annotation不相同；
- evaluator setup actions进入model behavior/recovery计数；
- memory非空、action budget不等于1，或模型动作后继续追到成功再称first-action completion；
- final页面提示correct/wrong、反馈答案，或submission前调用/展示scorer；
- wrong final未使用真实wrong submission scorer negative control。

## 6. 共同 artifact、paired checks 与失败分类

每个cell至少保存：phase/probe/method/arm/variant/history/memory identity，模型与UI版本，intervention ownership，raw model calls，current/history image receipts，action-history与memory prompt binding，parser/execution，server pre/post snapshots，UI transactions，真实submission与hidden scorer记录。

必要的 paired/model-free checks 是为了阻止具体归因错误，不应替代真实运行：

- M：同arm当前像素与空history一致，只有memory prompt segment不同；
- A：三方法step-0当前像素一致；current-only/native4的实际初始model input与raw output一致；
- R：6-config R/X/P/C正交表完整；每个official/clean资产从同source重渲染；method pair当前像素一致；
- C：同arm/final三history当前像素byte-identical；两个populated histories等长且共享最后retry frame/click receipt；
- 所有block：evaluator receipt offset与model UI receipt ID空间分离，scorer只在真实submission后运行且不回显浏览器/方法。

行为造成的missing retry、TASK_COMPLETE、timeout或no-submission是有效 outcome；navigation错误、coordinate miss、parser disagreement、模型服务失败、receipt join失败才是 harness/implementation invalid。不能用 `execution_complete` 表示task success，也不能把infrastructure invalid填成failure numerator。

## 7. sample/cell、顺序与统计边界

建议冻结后交错执行block/arm/method，避免把method、arm、memory或role固定在时间顺序；每格都fresh reset GUI agent、controller state与app instance。不得因早期成功/失败停止某个factorial，或把旧Phase-2 cell混作本轮matched control。

报告必须同时给出：

```text
n_base_case = 1
n_counterfactual_configs = 6
n_cells = 50  # 双方法R core；单方法R screening为38
deterministic calls/cells are within-case conditions, not IID samples
```

可以报告逐condition表、paired action变化和“6个预注册config中多少个一致”的描述性计数；不能以38/50为样本量计算benchmark success rate、置信区间或显著性。Phase-3方法源于Phase-2 env008 failure analysis，不能叫held-out。真正的方法结论需要controller冻结后，在未用于设计的多种misleader cases上按case为单位复验。

## 8. 允许与禁止的最终结论

允许：

- “evaluator-seeded action-only/premise-specific/noisy memory对同一 inherited review 的可观察行为差异”；
- “同一 GUI-Reflection checkpoint 下，current-only、official native4与premise-aware inference controller method bundle的差异”；
- “在预注册role counterfactual panel中，action是否跟随correct/misleading role，是否受entity/position/color shortcut影响”；
- “在相同final current pixels下，empty/recent/revision history是否改变一次性Confirm”；
- 只有A/R中模型自己完成 `Back→correct rebind→Confirm→scorer true` 时，称 standardized handoff后的task-level recovery。

禁止：

- “GUI-Reflection自主生成了有效memory”，因为M memory是evaluator seed；
- “premise-specific memory无answer cue”后再把它当自主视觉发现；它显式否定Wind premise，只是不直接点名Solar；
- “ordinary agent vs reflection training effect”，因为A0仍是GUI-Reflection SFT checkpoint；
- “same compute”而不报告controller额外calls/tokens，或“same backbone”同时使用未声明OCR/第二模型；
- proposed成功即证明内部premise被读取/撤销；controller的structured state是外部可观察算法产物，不是latent-state探针；
- role/chart-position/card-position/color完全无交互；6-config OA只支持pairwise-balanced main-shortcut诊断；
- evaluator建立的inherited mistake、memory、completion history或correct final state被记成模型行为；
- Hydro/Wind branch avoidance、TASK_COMPLETE、no-submission或正确provisional state等同full recovery；
- 从env008的38/50 cells推断整个benchmark、训练方法或总体显著性。

## Launch前总 NO-GO

在正式模型运行前，如有以下任一项，Phase-3应暂停：

1. memory endpoint不能证明exact `<MEMORY>` 真正进入model question，或ownership仍写成agent-generated；
2. premise controller仍能访问CSV/DOM/roles/scorer/expected action，或算法尚可按cell人工调整；
3. A 三方法初始可见输入、checkpoint或预算不匹配，且差异不是预声明method treatment；
4. R没有冻结完整role/rotation表、使用含role词根的action IDs、official/clean renderer不matched，或scorer仍hardcode Solar；
5. C同final/history pair的当前像素或browser state不一致，或evaluator chain进入model behavior；
6. 把cell数当样本数、把Phase-3称held-out，或预先计划只保留成功conditions；
7. 任一 scorer/validator/role truth进入browser、prompt或controller input。

满足这些条件后，Phase-3可以启动；结果无论成功、失败或mixed都应保留逐cell轨迹，而不是只汇总一个“GUI-Reflection有效/无效”的数字。
