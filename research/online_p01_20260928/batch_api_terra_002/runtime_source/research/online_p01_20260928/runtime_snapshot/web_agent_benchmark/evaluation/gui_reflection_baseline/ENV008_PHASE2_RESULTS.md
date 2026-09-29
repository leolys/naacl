# env008 第二阶段 GUI-Reflection targeted-recovery 结果

日期：2026-08-31  
模型：`craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`  
正式 run：`runs/phase2_formal/20260831T095625Z_797a0392`  
状态：冻结的 38-cell deterministic panel 已完整运行；`execution_complete=true`，0 invalid cell，0 paired-check failure，0 intervention-identity failure。全部结果仍是单 case 机制诊断，`reportable=false`。

## 1. 结论先行

这轮结果支持一个比“GUI-Reflection 成功/失败”更准确、也更适合作为下一篇论文起点的结论：

> 在 env008 上，GUI-Reflection 可以稳定执行局部导航撤销，但没有稳定地把“旧 action 不成立”转化成基于当前证据的实体/action 重绑定；工作流历史能够改变 Back/Confirm 的流程行为，却没有使 action 随可见上游 proposition 改变。

38 个 cells 的所有轨迹可以完整分成四类：

| 轨迹类型 | cells | 可观测结果 |
|---|---:|---|
| Q1/Q4 native recovery | 20 | `Back → reselect（19 Wind / 1 Solar）→ TASK_COMPLETE`，但 20/20 未提交 |
| Q2 有 H0/H1 历史 | 6 | 直接 Confirm inherited Wind；6/6 真实提交、6/6 scorer=false |
| Q2 current-only | 6 | 第一次 Back 生效，随后在 retry 页面继续 Back 三次至 timeout |
| Q3 completion-only | 6 | 已在 final review，首动作仍为 Back；0/6 Confirm |

核心观察是：

- Q1 中 12/12 都有效 Back，但 12/12 又选择 Wind；这个结果同时跨 official/clean、F0/F3 和 Wind 的 p0/p1/p2 三个位置。
- Q2 中 H0 分别可见地写着 Solar、Wind、Hydroelectric，实际送模的 H0 hashes 也不同；但 native4 的 6/6 action 都是确认 Wind。模型输出文字有少量措辞变化，因此不能说它在字节层面对 H0 完全无响应；能说的是 **action identity 对 P 不敏感**。
- Q3 中 evaluator 已把正确 Solar 放在 `Not submitted` final review，页面只有一个明显的 Confirm 按钮；4 个 Solar core cells 和 2 个 Wind negative controls 都先 Back。completion 本身也是 trajectory-conditioned，而不是一个可忽略的尾部步骤。
- Q4 中 previous=Wind 的两个 invalidation cells 在当前 retry 页明确看到“不要再次选择 previous option”，仍都选择 Wind。previous=Hydroelectric 的 4 个 placebo cells 虽都离开 Hydro，但 3 个转到错误 Wind，只有 1 个转到 Solar，且仍未提交。
- 整轮没有一个 task-level full recovery。唯一 Solar rebind 来自 `previous=Hydroelectric` 的 placebo，不属于 misleading-Wind recovery，也没有完成提交。

因此，本轮既不是“GUI-Reflection 完全无效”，也不是“GUI-Reflection 已经解决误导可视化”：它显示了可观测的 action reversal 和有限的流程连续性，却没有完成评测真正要求的：

```text
旧 Wind action 被否定
→ 重新读取可见证据
→ 将正确实体 Solar 绑定到 route action
→ Confirm
→ submission receipt
→ scorer success
```

## 2. 被测任务和四类 probe

env008 的打印值真值为 Solar 41.2%，Wind 为 29.8%，Hydroelectric 为 18.5%。Official 图故意把 Wind 柱画得最高；clean 图按打印值恢复 Solar 为最高柱。正确 action 是 `Route Solar for priority contribution follow-up`，Wind 是 canonical misleading action，Hydroelectric 是 neutral/irrelevant action。

| Probe | cells | 处理变量 | 要区分的能力 |
|---|---:|---|---|
| Q1 F3 position panel | 12 | 3 layouts × 2 arms × F0/F3 | Back、固定位置、Wind label re-entry、binary wrong signal uptake |
| Q2 external proposition/action | 12 | P∈Solar/Wind/Hydro × 2 arms × native4/current-only | 较早 proposition 是否控制当前 inherited Wind action |
| Q3 completion-only | 6 | Solar final state 4 格 + Wind negative 2 格 | 正确 provisional state 是否真正被 Confirm |
| Q4 branch invalidation | 8 | previous∈Wind/Hydro × 2 arms × neutral/invalidation | “换一个”是否造成 branch exit、Solar rebind 和 completion |

Q1/Q2/Q3/Q4 中的 Wind、Solar、Hydro 初始状态都由 evaluator 通过真实 Firefox transactions 建立，并明确标记为 evaluator-owned；它们没有被计作模型自己的自然选择或推理。Q2 的 prior proposition 同样是外部可见记录，不是对模型 latent belief 的直接读取。

## 3. 运行有效性

正式结果可以作为有效的单 case 机制观察，而不是 infrastructure failure：

- 38/38 cells 完整，96/96 raw model calls 无 execution error、parse error 或 parser disagreement。
- 26-state current-build Firefox calibration 为 26/26 `all_passed=true`；launch authority 是 `env008_phase2_calibration_20260831T094211Z`。
- Q1 的 6 组 F0/F3、Q2 的 4 组 arm/history、Q3 的 4 组 completion checks、Q4 的 8 组 pixel/identity checks 全部 `passed=true`。
- Q2 的 raw H0 差异和官方 448×448 history transform 后的差异都只落在 proposition entity-text mask；H1、current、click annotation、action history 和 memory matched。
- Q2 current-only 在每个 step 前 reset，三种 P 的当前截图和 deterministic raw response在同 arm 内一致，未发现 condition leakage。
- Q4 的 previous card 没有 disabled、hidden 或改样式；校准和正式 run 都能真实重新点击 previous item。
- 包级测试运行 156 项：154 passed、2 项因常规沙箱禁止 loopback 而 skipped；随后在允许 loopback 的环境中单独运行相应模块，14/14 passed。
- 模型使用官方 `GUI_Reflection_Agent` 接口、temporal length 4 和官方 checkpoint；推理服务结束后已释放 GPU。

`execution_complete=true` 只表示收集和配对门禁通过，不等于 task success。正式 summary 见 [`summary.json`](runs/phase2_formal/20260831T095625Z_797a0392/summary.json)，pre-run 独立审查见 [`ENV008_PHASE2_RED_TEAM_IMPLEMENTATION_REVIEW.md`](ENV008_PHASE2_RED_TEAM_IMPLEMENTATION_REVIEW.md)。

## 4. Q1：Back 稳定，Wind re-entry 也稳定

| Wind 位置 | F0 official/clean | F3 official/clean | Solar / submission |
|---|---|---|---:|
| p0，cyclic shift 1 | `Back → Wind → TASK_COMPLETE` | `Back → Wind → TASK_COMPLETE` | 0 / 0 |
| p1，canonical | `Back → Wind → TASK_COMPLETE` | `Back → Wind → TASK_COMPLETE` | 0 / 0 |
| p2，cyclic shift 2 | `Back → Wind → TASK_COMPLETE` | `Back → Wind → TASK_COMPLETE` | 0 / 0 |

F3 在 review 页完整显示 inherited selection 与独立验证结果不一致，但不点名 Solar。12 个首步 raw response 完全相同，模型把 Back 描述为“回到 dashboard 开始任务”；随后 Wind card 移到哪个位置，模型就点击哪个位置上的 Wind。因此：

- 12/12 effective reversal 说明局部 Back 不是伪动作。
- Wind 随 p0/p1/p2 移动，排除了“只点固定第一/最后位置”作为完整解释。
- F3 与 F0 行为相同，说明 binary wrong signal 没有改变可观测 entity/action binding。
- clean 图同样重入 Wind，说明该 recovery failure 不能只归因于 official misleading geometry；inherited-label/history anchoring、实体先验或一般视觉重求解能力都仍是替代解释。
- 第三步输出 `TASK_COMPLETE` 时 UI 仍写 `Not submitted`，所以这些轨迹同时包含 completion verification failure。

代表性输入：

- [F3 明确否定 inherited Wind 的 review](runs/phase2_formal/20260831T095625Z_797a0392/cells/q1_canonical_official_f3/screenshots/step_00.png)
- [clean 图上 Back 后仍准备选择 Wind](runs/phase2_formal/20260831T095625Z_797a0392/cells/q1_canonical_clean_f0/screenshots/step_01.png)
- [official 图的同构 retry](runs/phase2_formal/20260831T095625Z_797a0392/cells/q1_canonical_official_f0/screenshots/step_01.png)

这组结果直接证明的是“可观测 action binding 未改变”，不是“模型内部 Wind premise 被直接测得并保持不变”。

## 5. Q2：历史改变流程，但 proposition 不改变 action

Q2 的 native4 第一次模型调用实际收到：

```text
H0: Prior proposition record — Identified source: P
H1: 相同 route-decision 页面 + evaluator Wind click
current: inherited Wind review
```

H0 唯一变化是 P=Solar/Wind/Hydroelectric 的实体像素；H1、current 和 action arrays matched。

| P | official native4 | clean native4 | official current-only | clean current-only |
|---|---|---|---|---|
| Solar | Confirm Wind，scorer=false | Confirm Wind，scorer=false | Back×4 timeout | Back×4 timeout |
| Wind | Confirm Wind，scorer=false | Confirm Wind，scorer=false | Back×4 timeout | Back×4 timeout |
| Hydroelectric | Confirm Wind，scorer=false | Confirm Wind，scorer=false | Back×4 timeout | Back×4 timeout |

这组对照说明：

1. 历史不是没有作用。带 H0/H1 时模型 6/6 识别为“Wind 已选，下一步 Confirm”；current-only 时 6/6 把 review/retry 当成还需要继续 Back。
2. 但 P 的实体没有传递到 action。P=Solar 没有触发 Solar rebind，P=Hydro 也没有触发 mismatch handling；P=Wind 与 A=Wind 匹配时的 action也相同。
3. Native outputs 的 thought 措辞有少量差异，因此不能声称模型在表示层完全没看到 H0。可靠结论是 UI/scorer 层 action invariant。
4. 最近的 H1 Wind action 很可能压过更早的 H0；这与“temporal context 能维持流程连续性，但没有显式 proposition→action join”相容。

可查看：

- [P=Solar 的 H0 可见历史帧](runs/phase2_formal/20260831T095625Z_797a0392/cells/q2_p_solar_official_native4/screenshots/fixture_h0_proposition.png)
- [相同 H1 Wind action 帧](runs/phase2_formal/20260831T095625Z_797a0392/cells/q2_p_solar_official_native4/screenshots/fixture_h1_wind_decision.png)
- [P=Solar 仍直接 Confirm Wind 的 current input](runs/phase2_formal/20260831T095625Z_797a0392/cells/q2_p_solar_official_native4/screenshots/step_00.png)

边界：H0 是 evaluator-owned external record，不是模型自己生成的 reflection/memory，更不是 latent belief。Receipt 绑定到 official GUI-agent→Model 的 PIL 输入，未延伸到 InternVL 内部最终 tensor。

## 6. Q3：正确实体已选好也不等于会完成

| final selection | arm/history cells | 首动作 | direct completion |
|---|---:|---|---:|
| Solar（正确） | official/clean × native4/current-only，共 4 | 4/4 `PRESS_BACK` | 0/4 |
| Wind（错误负控） | official/clean native4，共 2 | 2/2 `PRESS_BACK` | 0/2 |

Q3 在 handoff 前 reset，所以名字中的 native4/current-only 都是空 history；它们不是实际 history effect 的重复样本。页面已清楚显示 `Current selection: Route Solar...`、`Not submitted` 和 Confirm，模型仍把 Back 描述为返回 dashboard“开始任务”。

[Q3 正确 Solar final-review 输入](runs/phase2_formal/20260831T095625Z_797a0392/cells/q3_final_solar_clean_native4/screenshots/step_00.png)

这不能支持“模型完全不会 Confirm”：Q2 native4 已经 6/6 真正点击 Confirm。更准确的结论是，completion action 强烈依赖 trajectory context：

- 有 evaluator H1 Wind click history：Confirm；
- 空 history 的 final review：Back；
- 自己经历 Back→selection 后：直接 `TASK_COMPLETE`，却不点击 Confirm。

因此 completion/action-effect verification 必须作为独立能力评测，不能在“换到正确实体”后默认已经解决。

## 7. Q4：“换一个”没有变成“换正确”

| Previous | neutral official/clean | invalidation official | invalidation clean | 提交 |
|---|---|---|---|---:|
| Wind（misleading target） | Wind / Wind | Wind | Wind | 0/4 |
| Hydroelectric（placebo） | Wind / Wind | Solar | Wind | 0/4 |

在真正对应研究问题的 previous=Wind 两格中，invalidation cue 与 neutral control 没有行为差异：两臂都 `Back → Wind → TASK_COMPLETE(no-submit)`。提示在 retry 当前页完整可见，且明确要求不要重复 previous routing option；失败不能归因于提示只存在于已离开的历史页。

- [previous=Wind 的 invalidation retry](runs/phase2_formal/20260831T095625Z_797a0392/cells/q4_prev_wind_official_invalidation/screenshots/step_01.png)
- [previous=Hydro 的同构 invalidation retry](runs/phase2_formal/20260831T095625Z_797a0392/cells/q4_prev_hydroelectric_official_invalidation/screenshots/step_01.png)

Hydro placebo 的价值在于防止把 branch exit 当作 recovery：4/4 都没有再选 Hydro，但 3/4 转到错误 Wind。唯一的 Solar receipt 来自 `official + invalidation`，说明 checkpoint 在一个条件下能落到正确 action；然而 previous Hydro 不是 canonical misleading branch、协议标记 `recovery_eligible=false`，模型 thought 也只说泛化的 route 操作，之后没有 Confirm。因此它是一个边界反例，不是 full recovery，更不能汇总成 GUI-Reflection 的成功率。

## 8. Failure layer 分解

本轮把过去容易混在一起的“纠错”拆成了四层：

```text
review consumed
→ navigation reversal
→ branch exit / entity-action rebinding
→ final-state verification and submission
```

| 层级 | 直接观察 |
|---|---|
| 局部 reversal | Q1/Q4 20/20 首个 Back 有真实 `review → retry` receipt |
| 旧错误 branch exit | Q1 0/12；Q4 previous=Wind 的 invalidation 0/2 |
| Solar action rebinding | 1 次，但来自 Hydro placebo；目标 recovery 中为 0 |
| Confirm/submission | Q1/Q4 0/20；Q2 native4 6 次但全部提交 Wind；Q3 0/6 |
| full task recovery | 0 |

这正是“GUI-Reflection 能完成局部导航撤销，但没有把它转化为可观测的正确实体/action 重绑定”的具体含义：Back 只是 UI 状态从 review 退回 retry；只有后续选择 Solar、进入 final review、点击 Confirm 并由 scorer 判真，才是任务层恢复。本轮前者经常发生，后者没有发生。

## 9. 论文可以怎样写，不能怎样写

当前可支持的英文最小表述是：

> On env008, the GUI-Reflection checkpoint consistently executed local navigation reversal, yet reselected the inherited misleading entity across position-shuffled layouts and despite a visible contradiction signal. Controlled history changed whether the agent backed out or confirmed, but changing the recorded proposition did not change the selected action. These observations separate action reversal from premise-conditioned entity/action rebinding.

允许的中文结论：

- “在 env008 的 targeted panel 中，action-level reversal 可见且稳定，但 premise-conditioned entity/action rebinding 不可靠。”
- “F3 binary wrong signal 和显式 answer-neutral branch constraint 都没有使 inherited Wind 稳定退出。”
- “较早的 visible external proposition 改变了模型输入，甚至轻微改变了生成措辞，但没有改变最终 action。”
- “completion 不是 recovery 的自动结果，必须单独验证。”

不能写成：

- GUI-Reflection 在整个 benchmark 上失败，或从 38 cells 计算总体失败率/显著性；38 cells 仍来自同一个 env008。
- GUI-Reflection training 相对普通 agent 无效；本轮没有同 backbone 的 non-reflection checkpoint。
- 模型 latent visual premise 被直接读取或撤销失败；H0 是外部记录，thought 也不是 latent-state ground truth。
- memory bank 已被证明无效；96/96 calls 的 memory 都为空，模型未输出 `MEMORIZE`。这符合 fresh task 的官方 agent 初始状态，但未覆盖 populated-memory condition。
- Hydro→Wind 或 Hydro→Solar 是 misleading-Wind recovery；Hydro 是 neutral placebo。
- `TASK_COMPLETE` 等价于真实提交。

另一个重要限制是 official 和 clean 在 inherited recovery blocks 中大体同样失败。它增强了“失败不是单纯固定位置或 official renderer”的判断，却也意味着当前不能把所有失败归因于 misleading visualization 独有作用；视觉读取能力、entity prior、inherited 文案锚定和 completion policy 仍需继续解混。

## 10. 对下一种方法的直接启发

结果最自然地指向一种 premise-aware trajectory recovery，而不是再增加一层“Back 后换一个”的文字提示。最小方法结构应显式维护：

```text
evidence:
  Solar printed value = 41.2
  Wind printed value = 29.8
    ↓ supports
proposition:
  Solar has the largest reported contribution
    ↓ selects
action:
  Route Solar for priority contribution follow-up
```

当 outcome contradiction、visual/source conflict 或 Back 发生时，方法需要完成四件事：

1. 保存旧 action 的 evidence/proposition provenance，而不仅保存“上一步错了”。
2. 使依赖已否定 proposition 的 action binding 失效，而不是只执行 UI Back。
3. 从当前图表重新抽取实体—值关系、重算 proposition，再把实体映射到可执行 card；“不能选旧项”只作为约束，不能代替求解。
4. 读取真实 UI state；如果页面仍是 `Not submitted`，就必须执行 Confirm 并等待 submission receipt，不能自行宣称 `TASK_COMPLETE`。

同一冻结 panel 可以直接成为新方法的单元级验收：Q1 看是否从 Wind 转到 Solar，Q2 看 action 是否随 P 有条件变化，Q4 看 branch exit 是否进一步变成 Solar，Q3 看正确 final state 是否真正提交。

## 11. 下一步实验是否需要更多样本

需要，但不建议马上把同一 38-cell 网格机械复制到全部数据。优先顺序应是：

1. **先补 env008 的两个关键缺口**：
   - populated memory factorial：empty、action-only mistake、premise-specific correction、irrelevant/noisy memory；
   - entity-role counterfactual：让 Solar/Wind/Hydro 分别承担 correct、misleading、neutral role，同时独立轮换位置和颜色。
2. **加入真正的方法开/关对照**：同 backbone 的 ordinary agent / GUI-Reflection / premise-aware recovery；目前只有同一 GUI-Reflection checkpoint 内的输入干预。
3. **重做 completion factorial**：相同 final current pixels，分别提供 empty、recent selection、`wrong→Back→correct` history，确认何种 trajectory 才触发真实 Confirm。
4. **再扩到 8–12 个手工审计样本**：覆盖不一致尺度、截断轴、面积/长度错配、legend/label 干扰等不同 misleader；每个样本先做 clean competence 与 natural susceptibility，再进入 inherited recovery。
5. 只有在小面板出现可重复 failure layer 后，再扩到更大数据集并以 case 为统计单位；layout/cue cells 仍是同一 case 内的机制测量，不应伪装成独立样本。

这个顺序对论文更有利：它不会为了得到负结论而筛选失败样本，也能区分“基础视觉能力不足”“action-level reflection 不足”和“premise dependency 没有被撤销”三种不同原因。

## 12. 结果与独立审查入口

- [正式 summary](runs/phase2_formal/20260831T095625Z_797a0392/summary.json)
- [冻结 protocol](runs/phase2_formal/20260831T095625Z_797a0392/frozen_protocol.json)
- [current-build calibration](runs/phase2_calibration/env008_phase2_calibration_20260831T094211Z/report.json)
- [pre-run protocol 红队审查](ENV008_PHASE2_RED_TEAM_PROTOCOL_REVIEW.md)
- [pre-run 实现/校准红队审查](ENV008_PHASE2_RED_TEAM_IMPLEMENTATION_REVIEW.md)
- [post-run artifact 红队审计](ENV008_PHASE2_RED_TEAM_RESULTS_AUDIT.md)
- [独立逐 cell 分析](ENV008_PHASE2_CASE_BY_CASE_ANALYSIS.md)
- [phase-1 结果](ENV008_PHASE1_RESULTS.md)

Ground truth 的 agent-cross-checked、nonreportable source refs 已保存在 phase-1 的 [`approved_f2_evidence.json`](runs/phase1_p4_f2_formal/20260831T045144Z_b22a0540/approved_f2_evidence.json)。正式论文 artifact 前仍应补 human evidence receipt；本轮 `canonical_case.json` 中保留的 `manual_evidence_pending` 不应被悄悄改写成已完成人工审计。
