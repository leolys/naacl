# GUI-Reflection smoke17 逐样本恢复分析

> **范围声明：** 本报告分析已经运行完成的 smoke17 `official`/`clean` GUI-Reflection 轨迹，并新增一组真实 env008 compact natural targeted quartet。后者比较同一 checkpoint 的 workflow on/off，不是“有/无 reflection training”的 `R+ / R-`。除 env008 F0 natural 四格外，下文其他 targeted 条件仍是未执行设计，不得当作实验结果。

## 比较框架

后续应把每个样本补成以下 2×2：

| 图表 | 完整 GUI-Reflection `R+` | matched no-reflection policy `R−` |
|---|---|---|
| official misleading | `O+` | `O−` |
| clean | `C+` | `C−` |

这里的矩阵是 SFT/full-pipeline stage。`R−` 必须是同一 architecture/base agent、同一执行器，并训练到同一 SFT stage：ordinary GUI data、更新步数和预算匹配，只移除或预算匹配地替换 reflection-specific task/trajectory augmentation。bare regular GUI-Pretrain 只能与 `GUI-Pretrain-Ref` 构成另一个 pretrain-stage 对照，不能充当 SFT `R−`。当前公开资源没有严格的 stage-matched SFT checkpoint，所以四格中的 `O−/C−` 保持 pending。可以另做 context-reset ablation：从同一个 post-error 页面重新开始，但清空最近截图、动作历史、错误总结和 memory；该行记为 `runtime_context=reset`，只隔离在线恢复上下文，不能占用 `R−` 单元，也不能消除 reflection 训练影响。

## 证据约定

- trace 根目录：`/mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/traces`
- `O s2` 表示 `official/<scenario>/<slug>.jsonl` 中 `step=2`；`C` 同理。
- screenshot 是执行相应 step 动作前的真实页面。
- 34/34 个 run summary 均为 `submission_observed=false`。
- 模型 thought 和 `action_description` 只用于分析模型当时口述的判断或意图。是否真实执行，必须由 `action_parsed`、真实坐标、URL 变化、页面/表单状态和 hidden submission 共同确认。本文不会把模型的成功叙事当作真实动作或提交。

## 失败代码

- `CU`：图表理解（Chart Understanding）
- `G`：GUI grounding/执行
- `P`：流程规划
- `V`：动作结果验证
- `R`：错误前提撤销
- `T`：重试策略
- `C`：完成判断

## 逐样本审查

每个样本的 primary natural run 先使用 `[F0]` 中性复核。下表第五列凡展示具体数值、实体—值关系、阈值或独立数据表，均明确属于 `[F2-assisted upper bound; source audit pending]`；`pub001` 的 legend 检查单独属于 `[F1; prompt review pending]`。这些 proposed 证据尚未进入模型，也不能被读作已观察到的 recovery。后面的 evidence registry 给出逐 case 的精确级别与待核验 source；实际运行前还要把泛化 source 名替换为精确 artifact/record、reviewer、status 和 date。

| 样本 | GT → 误导目标 | 已运行 O/C 的真实轨迹和差异 | 失败诊断 | Proposed targeted recovery（未运行；`[F1/F2]` 级别见上） |
|---|---|---|---|---|
| `business/b001`<br>`MS_inappropriate_scale_functions` | Apple 45% → Others 10% | O/C 完全相同：20 次真实 `CLICK [152,232]`，URL 始终为 `/task/b001`，从未到 dashboard/form，均 timeout。截图中 Open Dashboard 实际约在 `[150,380]`；模型多次口述“前次失败”，仍重复同一点。证据：O/C s0–19。 | `G,V,T`。未暴露图表，不能诊断 `CU` 或 recovery。 | 只从已稳定加载的 dashboard 开始。让自然选择发生；若选 Others，保留该选择并显示 Apple 45、Others 10 的原始标签，Back 后重选。比较 O+/O−、C+/C− 是否由 Others 切换到 Apple。 |
| `business/b002`<br>`data_visual_disproportion` | Edge 87% → Firefox 23% | 两臂均到 dashboard/form。O s1 口述识别绿色 87%，随后却把它绑定为 Chrome；C s1–2 声称 67% Chrome。O s6、C s5 的截图证明所有 dropdown 仍是默认值；虽然随后真实点击 Submit 按钮，HTML 验证阻止了提交。没有真实 Back；C 的“Back”描述对应一次前进到 form 的 click。 | 数值—实体绑定层面的 `CU`，以及 `G,V,C`。轨迹中没有出现对“87% 对应哪个实体”的可观察复核行为。 | post-error 状态预选 Firefox；最小反证只显示同图的 `Edge 87 > Firefox 23` 及类别标签，不直接写答案句。Back 后必须选 Edge、填必填项并真实提交。另做 entity-binding 消融：只保留数值、不保留类别标签。 |
| `business/b011`<br>`misuse_of_cumulative_relationship` | Q3→Q4 decreased：7940→5121，−2819 → Increased | O/C 都到 dashboard/form，并都口述 Increase。O misleading 为 stacked total，C 为 grouped bars，但两者蓝色柱内部均明确印有 7940 和 5121。O s6、C s5 显示表单仍全部为默认值，未真实选择 Increase，也未提交。 | `CU,G,V,R,C`。clean 同样错误，与最近两点比较的通用能力地板一致；该单例不能把原因单独归为 cumulative trap。 | 令 agent 先自然报 Increase，进入 form 后保留该选择；拒绝卡只呈现 `Q3 Store_Visits=7940; Q4=5121`，要求返回证据页。检查它是否计算符号并切到 Decreased。 |
| `business/b012`<br>`MS_inappropriate_scale_range` | Product E 13201 ≥ 12500，normal path → low-sales queue | O 到 dashboard/form；首个 dashboard 截图的图像尚未加载，O s2 却口述 E<12500。随后发生真实 form→dashboard→form，是少数真实 Back/re-entry，但 s4 表单 route 仍为默认值。它又口述选择 normal，出现“错误前提+正确动作意图”的不一致。C dashboard 图加载后直接 `TASK_COMPLETE`，从未进入 form。 | `CU,G,P,V,R,C`，另有图表加载稳定性混淆。 | 必须等待图渲染稳定。受控地预选 low-sales；反证只显示 `Product E=13201` 和 cutoff `12500`。Back 后选择 normal。单独记录 premise 是否从 `<12500` 更新，不能只看最终动作，因为现有轨迹已出现 lucky correct action intent。 |
| `business/b035`<br>`misleading_annotations` | falling：3480→2055，−1425 → rising/capacity expansion | O 到 dashboard/form。标题写“Increasing”，但折线整体下降；O s1 跟随标题口述 rising/capacity。其后只反思点错 dropdown，未撤销趋势前提；O s4 表单全为默认值。C 明确口述 decreasing/efficiency，但 C s8 表单也全部默认。两臂均无提交。 | official 为 `CU,R`；两臂均有 `G,V,C`。这是清晰的 misleader-conditioned divergence。 | 旗舰样本。先让 O 自然选择 capacity；显示两个端点 `2018=3480, 2023=2055` 或净变化，不重复 clean 标题。Back 后检查是否改为 efficiency。比较 O+−O−，并用 C+−C− 判断恢复机制是否只对误导臂有增益。 |
| `environment/env001`<br>`MS_inappropriate_scale_functions` | substantial decline 13.8：23.9→10.1，targeted follow-up → routine | O/C 均只 Open Dashboard 后 `TASK_COMPLETE`；没有明确 substantial/routine 判断，没有 form，也没有 route。official 非线性轴与 clean 线性轴均已真实显示。证据：O/C s0–1。 | `P,C`。`CU` 未被真正观测，GUI-Reflection 没有进入错误—反转链。 | 增加最小 decision checkpoint。若自然选 routine，拒绝卡只呈现首尾打印值并要求计算差值；Back 后重选 targeted。必须保存 D0 和 D1，不能只保存 terminal。 |
| `environment/env007`<br>`MS_inappropriate_scale_range` | May 8324，standard low-output → critical near-zero | O/C 轨迹和 raw action 完全相同：打开 dashboard 后口述“normal range/standard”，随即 `TASK_COMPLETE`；判断意图恰好正确，但没有 route。图较大，May 标签和数值未必与类别同时出现在 viewport。 | `G,P,C`。没有 recovery 事件，不能声称方法成功。 | natural 模式用于测正确判断能否落实为真实动作；controlled-recovery 模式可以外生预选 critical，但必须标注为“注入错误”。最小反证为 `y-axis starts at 8000` 与 `May=8324`，而不是直接告知 standard。 |
| `environment/env008`<br>`data_visual_disproportion` | Solar 41.2% → Wind 29.8%（视觉最高） | O：初始无效 Back，进入 dashboard 后口述 Wind，真实 Back→task，再进 dashboard，又口述 Wind，再 Back，最后假称已路由。它有真实 dashboard re-entry，并在两次访问中都口述 Wind。O s3 的“realized my error”只针对导航，未明确否定 Wind。C 点击 41.2 bar 并口述最大值 41.2%，但没有绑定为 Solar；Back 后因找不到 route 直接 complete。两臂无 form/提交。 | `CU`/entity binding，以及 `P,V,R,T,C`。该行为与“有效 Back 不足以带来视觉分支改选”的假设一致；它不能证明内部前提未更新，也不能单独归因于 reflection training。 | 最优旗舰。保留 D0=Wind、Back 和两张 dashboard screenshot；反证为同屏 source/value 对照 `Solar 41.2, Wind 29.8`。D1 必须明确 Solar 并真实选择/提交。分别消融 recent screenshots、错误总结和 memory，观察哪一项促成 premise switch。 |
| `environment/env025`<br>`misleading_annotations` | January above true mean：442 vs mean 359 → equal-to-average | O/C 均打开 dashboard 后 complete；均未明确分类或 route。official 平均线错误画在 442，clean 应画在 359；当前没有发生可审查的判断。 | `P,C`。`CU/R` 未被观测。 | 先要求三分类并预留提交页。若选 equal，反证只显示原始值 `442,380,255` 和“请重新计算 mean”，测试是否算出 359 并切到 above。可再做一个直接显示 359 的消融，区分算术失败与前提撤销失败。 |
| `environment/env032`<br>`dual_encoding` | Gas > Coal at 2010 → Coal | O/C 都到 dashboard，且都口述 Coal 更高。official dual-axis 中蓝线视觉更高；C shared-axis 明确 Gas 更高，仍失败。两臂只在图上 click/MEMORIZE，未 route。证据：O/C s1–5。该样本已有 `gt_uncertain`，不属于 strict94。 | `CU,G,P,C`。clean 轨迹提示可能存在通用系列绑定/时间点读取问题，但 GT 未裁定前不作能力结论。 | 只作诊断，不作为主要论文证据；先人工裁定 2010 CSV 和单位。若保留，反证应是同单位的 2010 两行表，不能继续依赖双轴位置；比较是否由 Coal 切换到 Gas。 |
| `health/health016`<br>`misleading_annotations` | overall rising：约1280→3240 → decline | O 进入 dashboard。标题声称 Declining，而曲线强烈上升；O s2 明确口述 declining，scroll 后 Back 到 task，随后 complete，没有 route。C s2–4 明确口述 increasing，但仍 complete。 | official 为 `CU,R`；两臂均有 `P,G,V,C`。这是另一组清晰的 misleader-conditioned divergence。 | 旗舰。自然 D0=decline；反证只显示 2012/2023 两端点或要求比较首尾。Back 后应切换到 rising-growth follow-up 并提交。保留原 misleading 标题，以测试反证能否覆盖 annotation anchor。 |
| `public/pub001`<br>`MS_unconventional_scale_directions` | ME=100 → OK | O/C 都连续 20 次真实 `PRESS_BACK`，URL 不变，从未到 dashboard/form，均 timeout；O/C action 序列完全一致。当前没有暴露 reversed legend。 | `G,V,T`。不能用于现有 chart recovery 结论。 | 从 dashboard seed 后很适合。official 图的 legend 表示浅色=High/100，ME 为浅色；clean 是常规深色=High。若先选 OK，反证应聚焦 legend endpoints 与 ME 色块，Back 后改为 ME。 |
| `public/pub005`<br>`categorical_encoding_for_continuous_data` | California 39.5 → Texas 30.1 | O/C 同样连续 20 次 `PRESS_BACK`，URL 不变，从未 dashboard。更重要的是 official 图把 CA 和 TX 都压入 `30+M` 同色 bin，单靠该图无法区分 39.5 与 30.1；这是证据信息不足，而不只是视觉重读问题。 | 当前为 `G,V,T`；目标任务本质上要求 evidence acquisition，局部重试同一图不足。 | dashboard seed 后，先让 agent 选择 Texas；Back 后必须主动打开 Reference Data，看到 CA39.5/TX30.1，再切换到 California。比较 R+ 是否学会“换证据源”，而不仅是换 click。该样本适合暴露未来方法对前提—证据依赖图的需求。 |
| `public/pub006`<br>`small_size` | Kentucky 1270 → New Mexico | 两臂进入 dashboard，但图有初始加载空窗。O 口述 West Virginia，C 口述 Tennessee；真实 coordinate click 后 URL 均保持 dashboard，没有选中记录或提交。两种口述都既非 GT 也非指定 trap，所以当前差异更像 OCR/grounding 噪声，不是清晰误导效应。 | `CU,G,V,C`，并有 render 时序混淆。 | 中等优先级。等待图稳定后再自然选择；controlled 模式应明确外生预选指定 trap New Mexico。反证使用 legend 与 Kentucky numeric tooltip/value 1270。不能把现有 WV/TN 口述当作真实选择。 |
| `public/pub008`<br>`MS_inappropriate_scale_range` | Station X May06=1526>1300，normal → low-demand | O/C 都在 task 页面点击标题 `[144,130]`，而 Open Dashboard 按钮约在 `[120,253]`；scroll 后仍在 task。O 最后发生 `navigation_blocked`，C 直接 complete。均未到 dashboard/form。 | `G,V,T,C`。没有图表暴露。 | 从 dashboard seed 开始。official y-axis 从1500开始，使 May06 的蓝段看似极小；反证显示 `Station X/May06=1526` 与 cutoff1300，Back 后从 low 切到 normal。 |
| `public/pub010`<br>`misleading_annotations` | increasing：993→2917，+1924 → decreasing | O 始终停在 `/task/pub010`，却口述已看到 chart/increase/growth；所有 click 都落在 task 标题附近，未到 dashboard。C s1 真正到 dashboard 并口述 increasing，但无 form/提交。因此现有 O/C 不能用于评价 annotation 纠错。 | O 为 `G,V,P,C`；C 为 `P,C`。 | 从 dashboard seed 开始后会成为强样本：official 标题为 Decreasing，但折线和端点上升。先选 decline，显示首尾值作为反证，Back 后切换到 growth。 |
| `public/pub020`<br>`data_visual_disproportion` | Service Design 51 → Service Quality 41 | O 到 dashboard。图已显示时，它把图标题或 Portal 文本口述为类别并点击，未选择真实类别；C 打开 dashboard 后在图可能尚未稳定时立即 complete。均无 form。official 中 51% 的 Design 点被画得最低。clean asset 另有“Product Rating/Design”命名；canonical 将 Design 映射为 Service Design，但 targeted 前应确认该别名不会引入额外语义混淆。 | `CU,G,V,C`，并有 render/paired-label caveat。 | 等待稳定加载并统一 label。预选 Service Quality；反证使用 category/value table 或保留 printed 51%，测试是否能从垂直位置改按标签，切到 Service Design 并提交。 |

## env008 compact natural targeted quartet（已运行）

真实输出位于 `runs/targeted_env008/20260830T121341Z_7e5db661`。同一 arm 的 workflow on/off 首屏 PNG 和第一条 raw response 均逐字相同；official/clean 像素差异只位于 chart box，四格 parser、containment、模型当前/历史输入 receipt 和独立 scorer 检查均通过。

四格第一次真实选择都是 Solar/correct，所以都不具备错误后 recovery 资格。`single_attempt` 的 official/clean 均原子提交并 success；`feedback_retry/F0` 的两臂均真实看到 review 页，却直接 `TASK_COMPLETE`，没有点击 Confirm，也没有 submission。该样本说明新增 review workflow 会暴露 GUI-Reflection 的 completion/action-effect verification 缺陷，但不能回答“从 Wind 能否恢复”。完整逐步解释见同一 run 目录的 `MANUAL_ANALYSIS.md`。

下一步应先运行明确标注为 evaluator 注入的 env008 inherited-error probe（Wind provisional state），再跑三个预先固定的循环布局；不能把注入 Wind 冒充 natural 初选。随后扩展 `b035`、`health016` natural 四格。

## env008 inherited-Wind targeted recovery（已运行）

上述受控 probe 已按 F0/F3 各四格完成。evaluator 用真实浏览器点击外生预置 Wind，随后 reset 模型；8/8 轨迹都把 review→retry 的 Back 做对。native4 的 official/clean 在 F0/F3 均重新选择 Wind，然后在 final review 输出 `TASK_COMPLETE` 而不 Confirm；current-only 的四格均在相同 retry 页面重复无效 Back/Scroll，未作任何新选择。即使 F3 明示 Wind 与 independently verified outcome 冲突，也没有一次选择 Solar。总计 44 个 model step、36 次 reset、0/8 Solar、0/8 submission。

因此本例的失败层可以定位为 `R` 成功后仍有 `P/V/T/C`：局部动作撤销没有带来前提撤销，历史轨迹会把旧分支重新带入，重新选错后又把 provisional state 当成完成。current-only 的 no-op 不是恢复成功。该 probe 仍不是 natural susceptibility，也不是 reflection-training 因果对照；固定布局将 Wind 放在第一项，必须补 L0/L2 才能拆开历史锚定与 first-option bias。完整证据见 `ENV008_INHERITED_RECOVERY_ANALYSIS.md`。

下一批不应直接跑 strict94。先运行 `b035 / health016 / b012` 的 natural quartet，并对旗舰样本做 L0/L1/L2 位置筛查；随后按 `TARGETED_RECOVERY_PANEL_PLAN.md` 的预声明 9-case enriched panel 扩展。

## Proposed evidence registry（除上述 env008 F0 natural 外尚未运行）

所有样本的 primary natural condition 都先用 `F0_neutral_recheck`。下表只标注在 F0 失败后用于定位瓶颈的升级条件；`F2` 是 evidence-assisted upper bound，不能并入自主纠错结果。当前 source 列只是待定位的来源类别，不是可复核的 artifact locator；`manual_evidence_pending` 表示值或关系仍须由人工核对 canonical source、图像和 paired arm，并补齐精确 artifact/record、reviewer、status/date 后才能渲染。

| case | 升级条件 | 拟展示证据 | proposed source class（非精确 locator） | review status |
|---|---|---|---|---|
| `b001` | `F2_audited_values` | Apple 45、Others 10 | canonical chart/source values | `manual_evidence_pending` |
| `b002` | `F2_audited_values` | Edge 87、Firefox 23 及实体标签 | canonical chart/source values | `manual_evidence_pending` |
| `b011` | `F2_audited_values` | Q3=7940、Q4=5121 | canonical printed values/source | `manual_evidence_pending` |
| `b012` | `F2_audited_values` | Product E=13201、cutoff=12500 | canonical source + workflow threshold | `manual_evidence_pending` |
| `b035` | `F2_audited_values` | 2018=3480、2023=2055 | canonical endpoints/source | `manual_evidence_pending` |
| `env001` | `F2_audited_values` | 23.9→10.1 | canonical endpoints/source | `manual_evidence_pending` |
| `env007` | `F2_audited_values` | axis start=8000、May=8324 | canonical axis/value source | `manual_evidence_pending` |
| `env008` | `F2_audited_values` | Solar 41.2、Wind 29.8 | canonical entity/value source | `manual_evidence_pending` |
| `env025` | `F2_audited_values` | 442、380、255，要求重算均值 | canonical raw values | `manual_evidence_pending` |
| `env032` | `F2_audited_values` | 2010 同单位两行表 | canonical source after GT adjudication | `blocked_gt_uncertain` |
| `health016` | `F2_audited_values` | 2012/2023 两端点 | canonical endpoints/source | `manual_evidence_pending` |
| `pub001` | `F1_checklist` | 复核 legend endpoints 与 ME 色块，不给数值答案 | current chart only | `prompt_review_pending` |
| `pub005` | `F2_audited_values` | Reference Data 中 CA39.5、TX30.1 | independent reference-data route | `manual_evidence_pending` |
| `pub006` | `F2_audited_values` | legend + Kentucky tooltip/value 1270 | canonical tooltip/source | `manual_evidence_pending` |
| `pub008` | `F2_audited_values` | Station X/May06=1526、cutoff=1300 | canonical source + workflow threshold | `manual_evidence_pending` |
| `pub010` | `F2_audited_values` | 993→2917 | canonical endpoints/source | `manual_evidence_pending` |
| `pub020` | `F2_audited_values` | category/value table，含 Design=51 | canonical source after label reconciliation | `manual_evidence_pending` |

## 跨样本发现

### 1. 本次 smoke 中最明显的能力地板之一不是 chart reasoning，而是到达页面和完成流程

`b001`、`pub001`、`pub005`、`pub008` 两臂都没有看到图；`pub010` official 也没有看到图。若 targeted evaluator 不从稳定 dashboard 或 post-error checkpoint 开始，grounding 噪声仍会掩盖 recovery 能力。

### 2. 口述“动作错了”不等于撤销导致动作的视觉前提

最清晰的行为证据是 `env008`：真实 Back→dashboard re-entry 后仍两次口述 Wind。`b035` 的可见自我纠错只涉及“点错 dropdown”，没有出现对 “Increasing” 标题的明确否定。这些轨迹与“局部动作纠错未必带来视觉分支改选”的研究假设一致，但尚未证明内部前提是否更新，也不是 reflection training 的因果效应。

### 3. action description 和成功叙事不能作为真实动作证据

`b002`、`b011`、`b012`、`b035` 都口述已选择或提交，但提交前截图证明 primary dropdown 仍是默认值，hidden scorer 也没有 submission。targeted evaluator 必须以 DOM/form state、URL、POST/submission 为准。

### 4. clean 失败是通用视觉能力地板的警报

- `b011` clean 仍把 7940→5121 判断为 Increase。
- `env032` clean shared-axis 仍认为 Coal>Gas。
- `b002` clean 仍错误绑定 Chrome。

因此不能把所有 official 失败归因于 misleader。

### 5. 已有三组清晰的 misleading-conditioned 差异

- `b035`：official 口述 rising/trap，clean 口述 falling/correct。
- `env008`：official 口述 Wind，clean 至少识别到最大值 41.2。
- `health016`：official 口述 decline，clean 口述 increase。

这些是第一批 targeted continuation 的优先对象，但仍不是 `R+` 对 `R−` 的方法效果。

### 6. 不同 misleader 需要不同的最小反证

- title/annotation：首尾打印值，例如 `b035`、`health016`、`pub010`
- disproportion/value binding：类别—数值并列，例如 `b002`、`env008`、`pub020`
- truncated scale/threshold：目标值+阈值，例如 `b012`、`pub008`
- wrong average：原始值+重新计算提示，例如 `env025`
- categorical bin：必须切换到 reference table，例如 `pub005`
- dual axis：同单位数值表，例如 `env032`

### 7. 有些页面存在评测层面的可见性混淆

`b012`、`pub006`、`pub020` 存在首屏 chart render 空窗；`env007`、`env008`、`pub020` 的类别标签可能在 viewport 下缘之外。targeted evaluator 应等待图像稳定、固定可见区域，并保证最小反证与被否定前提同时可见。该等待是实际测量条件，不是额外 release gate。

## 建议的逐样本人工轨迹卡

不必先压缩成单一统计指标。每个四条件运行至少保留：

```text
Exposure: 是否真实到达 dashboard/form
D0: 第一次明确判断（entity/value/route）
A0: 第一次真实选择的 action_id
Counterevidence seen: 实际看到的反证
Back: 是否真实回到证据页
Premise update: 是否明确否定原视觉前提
D1/A1: 重试判断与真实 action_id
Re-entry: 是否重入原错误 branch
Submission: 是否真实提交
Failure layer: CU/G/P/V/R/T/C
```

建议同时保留两种进入 recovery 的方式：

1. **Natural-error continuation**：让 agent 自然产生 D0/A0；只有真实错误的样本进入恢复阶段。它可以用于分析自然 susceptibility 与 recovery 的联合表现。
2. **Controlled-error continuation**：由 evaluator 外生预选 misleading trap，再给相同最小反证。它只测 recovery capacity，不得把注入的错误归因于 agent。

## 第一批优先样本

1. `env008`
2. `b035`
3. `health016`
4. `b011`
5. `b012`
6. `env025`
7. `pub008`
8. `pub010`
9. `pub020`
10. `pub005`

这十个样本覆盖：局部反思不撤销视觉前提、数值—实体绑定、阈值反转、标题锚定、错误完成判断，以及必须更换证据源等不同的下一步研究入口。
