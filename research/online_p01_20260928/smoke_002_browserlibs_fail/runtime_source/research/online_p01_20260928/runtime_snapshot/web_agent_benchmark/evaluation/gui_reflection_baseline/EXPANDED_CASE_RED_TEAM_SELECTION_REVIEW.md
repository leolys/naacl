# Env008 扩展样本：独立红队选择审查

日期：2026-09-01  
审查范围：`benchmark_v2`、`benchmark_v2_open`、task sets、历史 GUI-Reflection smoke、当前 expanded-stage1 calibration。本文只审查选样与可归因性，不认可或修改 runner，也不把 calibration 当正式结果。

## 总结 verdict

- **NO-GO：**不能按 `TARGETED_RECOVERY_PANEL_PLAN.md` 中原 9 例直接启动或报告“8 类 misleader 的正式面板”。其中三例已被目标模型 clean 失败否决，三例有答案/可读性/信息充分性问题，`b009` 本轮又是 incomplete。
- **CONDITIONAL GO：**可继续做预先记录的 clean-only target-checkpoint 筛选；所有失败与替换都必须保留。达到 8 例不是放宽准入的理由。
- **当前最强新候选是 `pub010`：**canonical compact 筛选中 clean 两格均真实正确提交，official 两格均真实提交 misleading action；但它只覆盖一个 canonical layout，且 official 为 3420×2784 JPEG、clean 为 1120×928 PNG，因此只能说明“值得做 matched-render formal”，不能支持图题误导的纯因果结论。
- **`b035` 是 competent/prevention anchor：**四格均真实正确提交，证明这个 checkpoint 能完成该工作流，但没有自然错误，不能作为 natural recovery 成功或失败样本。
- `env008` 只能称 development sentinel；它已被反复用于协议和方法开发，不是 held-out case。

## 数据边界与直接泄漏

1. `web_agent_benchmark/benchmark_v2/benchmark_manifest.json` 只有 1 个 task（`pub011`），并不是本次 140-pair 来源。真正的候选库是 `benchmark_v2_open` release `2026-07-07`。
2. `benchmark_v2/benchmark_v2_public_app.py` 不可用于 paired causal evaluation：同一页面同时显示 Clean Chart 与 Original Misleading Chart，shell/reference/review 还直接给出 clean 数值或判断。即使模型只看 screenshot，也已经泄漏；DOM 中另有 reviewer role/action 信息。
3. 合法起点应是 `benchmark_v2_open` 的 paired records，并通过 compact `model_visible_projection` 展示。浏览器只应看到 `choice_0...n` 与自然语言标签；canonical action ID、role、ground truth 只留在 scorer 一侧。
4. task-set 实数为 full140=140、chart_only114=114、readiness95=95、strict_review94=94、smoke17=17。主候选只从 strict_review94 开始：full140 有 26 对 non-chart 字段不一致，另有 19 个 `image_only_draft`，`env032` 为 `gt_uncertain`。

## clean-competent 的强制定義

“模型在 clean 图上说对了”不够。一个 case 只有同时满足以下条件，才可进入 natural-recovery 主面板：

1. 同一目标 checkpoint、同一 system/task template、无 memory、无 F1/F2/F3 提示，执行 compact single-attempt/F0。
2. 有真实 UI selection、真实 Confirm/submit transaction，且独立 scorer 对 expected action 返回 success。没有 submission 只能称 decision-floor observation，不能称 end-to-end competent。
3. official/clean 除 chart intervention 外任务、标签、choice order、预算和初始 history 相同；workflow-on/off 的首帧和首次模型输入在同 arm 内相同。
4. 跑 role-blind L0/L1/L2 并全部保留；建议至少 2/3 clean 成功，且至少一次 correct 不在首位。否则已知的位置/实体先验可伪造 competence。
5. 先完成并冻结 clean-only 结果，再打开该 case 的 official 结果。外部 11-model 统计只能作 enrichment prior，不是目标 GUI-Reflection 的 competence 证据。

自然 recovery 还要求：模型自己在 official 首轮真实选择 canonical misleading action，随后消费 review 截图。evaluator 注入错误不满足这个定义。

## 当前 expanded-stage1 机械复核

| case | 当前磁盘证据 | 红队处理 |
|---|---|---|
| `pub010` | `20260831T174559Z_6f56a144` execution complete；clean 2/2 正确提交，official 2/2 misleading 提交；workflow-on 未改正 | **优先 conditional admit**：先 matched rerender，再补 L0/L1/L2；这是自然错误候选，不是现成因果结果 |
| `b035` | `20260831T173044Z_7b721ac1` 四格均 expected submit + scorer true | **conditional admit as prevention/competence anchor**；无 natural recovery opportunity；matched rerender 未完成 |
| `b009` | `20260831T173747Z_932696c1` execution_complete=false；两 clean timeout，两 official 因 unsupported `PRESS_HOME` invalid | **quarantine**；只能在统一 action-subset 修复后的新版本做 clean-only 重筛，现 run 不支持任何能力结论 |
| `b011` | 四格均提交 misleading | **淘汰主面板**：clean 不 competent |
| `b012` | 三格 misleading submit、一格无提交 | **淘汰主面板**：clean 不 competent，且 completion floor |
| `health016` | 四格均 misleading submit | **淘汰主面板**：clean 不 competent |
| `pub002` | 四格均 misleading submit；clean 像素写出 clean-map 解码规则 | **淘汰主面板**；只保留为无效筛查记录 |
| `pub005` | run 无 summary/health/完整结果；官方分箱不足以区分 CA 39.5 与 TX 30.1 | **硬淘汰**；已中止，不能归因 recovery |
| `pub006` | 历史轨迹出现 WV/TN 等非 canonical grounding；clean 像素写出解码规则 | **硬淘汰 canonical 主面板**；它测 OCR/grounding 与 arm cue，不是局部前提撤销 |

历史 `formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0` 的 34 格没有任何 submission（27 `agent_complete_without_submission`、6 timeout、1 navigation_blocked）。这些轨迹可生成假设，但不能替代上述 clean target-checkpoint gate。

## Paired arm 身份：P0 matched-render 要求

原候选 official/clean 的 CSV 均相同，但图像大多来自不同 renderer、尺寸与压缩：例如 `b035` 3420×2784 JPEG 对 1120×928 PNG，`pub010` 同样如此；`env008` 为 3420×2700 对 1120×888。object-fit 到同一网页框并不能消除此混淆。clean 图中出现 “Clean ...” 或直接说明正确视觉规则时，更是像素级答案/arm 泄漏。

若论文要声称“misleader manipulation 导致行为差异”，以下是 **P0 blocker**：

- 从两臂共同的 canonical CSV，用同一 renderer、canvas、font、颜色和数据层重画；只改变预声明的 misleader 区域。`pub010` 应只改标题文本，折线、坐标、字号和布局不变。
- 逐像素确认差异只落在预声明 mask 内；这不是形式化装饰，而是为排除已经实际存在的 JPEG/PNG、分辨率、caption 和可读性混淆。
- rendered 图不得出现 `clean`/`official`、正确 action、role、ground-truth rationale 或“darker means higher true value”等 arm/答案提示。
- matched rerender 后重跑 target checkpoint；canonical release 结果只保留作筛选，不能与新 formal 混池。

若研究问题明确改成“原 release paired variants 的总体效果”，可不 matched render，但必须把结论限定为 release-variant effect，不能归因具体 misleader。

## Inherited F3：P0/P1 归因边界

**P0：**

- externally forced misleading selection 必须记为 evaluator-owned intervention，不能计作模型初始错误、natural susceptibility 或 natural recovery opportunity。
- 模型接手点必须真实看到“当前选中项 + review/F3 feedback”，该帧、输入 history、模型 request receipt 与后续 UI actions 可 join；evaluator 预置动作不得混入 agent action count。
- F3 不能直接写出 correct action/实体。反馈只可否定当前前提或给可审计证据；否则测的是遵循答案提示。
- official/clean 使用同一错误角色、同一位置、同一反馈模板与预算。submission 必须由模型自己的 post-handoff transaction 触发，并由隐藏 scorer 独立判定。
- 结果标签固定为 `external-error/outcome-feedback capacity probe`；不得合并进 natural recovery 分子或声称 GUI-Reflection 自己发现/犯下并修复了错误。

**P1：**保留 F0 与 F3、natural 与 inherited 的运行顺序或反向顺序；用 answer-neutral F0 先建立基线；所有位置轮换均保留；把“Back 有效”“选择改变”“最终正确提交”拆成三层报告。

## Case independence 与 taxonomy 攻击

- strict94 中 `pub011` 与 `pub023` 的 official/clean figure 都是逐字节重复，且共享 case ID；最多保留一个。若选 public wrong-average family，保留 `pub011`，淘汰 `pub023`。
- `env008` 与 `env023` 使用同一 Solar/Wind/Hydro/Biomass/Geothermal 数值与同一不一致尺度机制，不能计作两个独立 case。
- `b009`/`env003` 是同一 pie scale-function 机制的跨场景复现；`b035`/`health016`/`b038`/`health018` 是 title-claim vs line-trend family。可报告 case-level replication，但不能把模板复本当独立 misleader type。
- 一个 case 的三种 layout、两个 arms、F0/F3 只是 repeated cells，不增加 case N。
- 当前类型几乎与 scenario/plot/template 共线；即使凑齐 8 个 taxonomy 标签，也不能比较“哪个 misleader type 更容易恢复”。
- enriched/adaptive shortlist 可支持逐例诊断，不支持 benchmark prevalence、总体 recovery rate 或显著性外推。

## 独立 shortlist 与强制淘汰清单

### 当前可继续

1. `pub010`：matched-title rerender 后的首要 natural candidate；补三布局。
2. `b035`：matched-title rerender 后的 clean/workflow competence 与 prevention anchor，不冒充 recovery。
3. `env008`：只作 development sentinel/协议回归，不计 held-out。

### clean-only blind screen queue

按当前证据，建议预先固定以下队列再看 official：`b008`、`b016`、`env003`、`env028`、`health018`、`pub011`。`b038` 只作同 family backup，不与 `b035/health018` 都当独立机制。若其中未达到 clean-competent，保留失败并停止该例；不要为了凑 8 例反复替换。

证据源为 `task_sets/strict_review94.jsonl`、对应 `benchmark_v2_open/splits/{official140,clean140}` 与 paired assets。`pub011` 必须走 compact open task，不能走泄漏的 `benchmark_v2_public_app.py`。

### 当前硬淘汰或隔离

- 主面板淘汰：`b011`、`b012`、`health016`、`pub002`、`pub005`、canonical `pub006`。
- infrastructure quarantine：`b009` 当前 incomplete run；修复 action-subset 后只能从 clean-only 重新筛。
- independence 淘汰：`pub023`（与 `pub011` exact duplicate）、`env023`（若已纳入 `env008`）。
- 数据质量淘汰：所有 `image_only_draft`、`env032 gt_uncertain`、full140 中 non-chart pair 不一致的 26 对。

因此现在没有诚实的“已冻结 8–12 个正式 case”。有 1 个新 natural 候选、1 个 competent anchor、1 个 development sentinel，以及 6 个尚待 blind clean screen 的候选。最终 N 应由预声明 gate 决定，而不是目标数字决定。

## 允许与禁止的论文表述

允许：

- “在一个 canonical-layout screening 中，`pub010` clean 两条件正确提交而 official 两条件提交 misleading action；这促使我们进行 matched-render、position-rotated formal probe。”
- “`b035` 显示目标 checkpoint 在该工作流具有 end-to-end completion competence，但该布局未产生 natural recovery opportunity。”
- “筛选是 enriched/adaptive，结果按 case 与 failure layer 描述。”

禁止：

- “原 9 例覆盖 8 类且模型在这些类上的 recovery rate 为……”
- 把 clean thought、未提交的正确选择、外部模型成功或 inherited evaluator injection 计为本 checkpoint 的 recovery。
- 把 JPEG/PNG canonical-arm 差异称为纯 misleader 因果效应。
- 把 `pub010` 的两个 workflow 条件或三个布局当作独立 case；把 `env008` 称 held-out。
- 隐去 clean 失败、incomplete run 或 backup 替换，只报告最终通过筛选的样本。

## 关键证据路径

- `web_agent_benchmark/benchmark_v2/benchmark_manifest.json`
- `web_agent_benchmark/benchmark_v2/benchmark_v2_public_app.py`
- `web_agent_benchmark/evaluation/gui_reflection_baseline/task_sets/{manifest,strict_review94,full140}.jsonl`
- `web_agent_benchmark/evaluation/gui_reflection_baseline/build_targeted_recovery_cases.py`
- `web_agent_benchmark/evaluation/gui_reflection_baseline/PER_SAMPLE_RECOVERY_ANALYSIS.md`
- `/mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/summary.json`
- `web_agent_benchmark/evaluation/gui_reflection_baseline/runs/expanded_stage1_calibration/`
- `web_agent_benchmark/pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/paired_results.jsonl`
