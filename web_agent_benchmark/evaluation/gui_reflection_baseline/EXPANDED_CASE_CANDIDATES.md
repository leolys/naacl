# GUI-Reflection 下一阶段 matched case 候选盘点

日期：2026-09-01

> **后续状态（同日）：** 本文是运行前候选盘点，不是最终入选表。
> 后续 clean-only 与 matched-render 结果见
> `EXPANDED_CLEAN_SCREEN_DECISIONS.md` 和
> `EXPANDED_TARGETED_RECOVERY_RESULTS.md`。固定的五个非标题 clean screen
> 全部未通过；`b038` 在 canonical release 图上通过，但在同构重画后 clean
> 选择 neutral，因 renderer sensitivity 未进入 inherited F3。当前最强受控
> natural case 是 `pub010`，`b035` 提供 F3 semantic-recovery 的部分正例。

## 结论

在纳入 2026-08-31 的 expanded Stage-1 compact calibration 后，建议保留 **10 个候选**，其中下一步优先筛选 6 个非重复模板：

1. `pub010`：title annotation / Tourism routing；已出现最干净的同-checkpoint matched divergence；
2. `b008`：scatter visual disproportion / business category routing；
3. `env003`：pie inappropriate scale function / energy source routing；
4. `pub012`：reversed choropleth legend / state priority routing；
5. `pub009`：truncated stacked scale / municipal transit routing；
6. `env025`：wrong-average annotation / air-quality routing。

这 6 例的页面模板和主要推理机制均不重复。`env008` 应在同批次作为已充分诊断的 regression anchor，但不再把它的更多 cells 当作新 base case。`b038` 已成为 `pub010` 的同 title-family confirmed replication；`pub011`、`b035` 保留为替补或 control。

最重要的新事实是 `pub010`：同一 GUI-Reflection checkpoint 在 compact `single_attempt` 与 `feedback_retry/F0` 两个条件下，clean 2/2 都选择 growth 并正确提交，official 2/2 都选择 decline trap 并确认错误提交。它同时满足 clean competence、natural official susceptibility、真实 action binding 和真实 submission，因此应成为下一轮 inherited F3/recovery 的第一优先级。

`b038` 随后复现了相同 family 的结果：clean single/F0 2/2 选择 growth-review、提交且 scorer=true；official 2/2 选择 maintain-current-plan trap、提交且 scorer=false；official F0 的 `ordered_recovery=false`。这使它成为已确认的跨 task/scenario title-annotation replication，但它仍与 `pub010` 属于同一个 misleader subtype，不能在机制覆盖数中另算一种类型。

## 证据边界

本报告严格区分三种证据：

- **G1：** 同一 GUI-Reflection checkpoint 在 compact clean arm 有 hidden-scored 正确提交；
- **G2：** 同一 checkpoint 只口述了正确实体/趋势，但没有真实 action/submission；
- **X(n/12)：** 其他 12 个模型在 clean formal run 中有 `n` 次正确提交。X 只说明样本可解，不证明 GUI-Reflection competence。

`C/O/D` 来自两份 formal paired artifacts，共 1,680 rows（12 models × 140 tasks）：`C` 是 clean success，`O` 是 official success，`D` 是同一模型 `clean=success ∧ official=misleading_failure`。这些固定模型不是随机样本，数值只用于 enrichment，不是 GUI-Reflection 的总体成功率。

Expanded Stage-1 是 compact calibration artifact。它比旧 smoke 更直接地测到 card selection 和 scorer，但仍是 exploratory、canonical-layout 的单次运行；不能把 4 cells 当成 4 个独立任务。env008 Phase 3 同样只有 `n_base_case=1`。

## 10 个候选身份

| 级别 | slug / scenario | task id / case id | 机制 | correct → misleading |
|---|---|---|---|---|
| 已确认主样本 | `pub010` / public | `task_6c60db5187_misleading_annotations_line_chart_41`<br>`misleading_annotations/line_chart/misleading_annotations_line_chart_41` | title 说 decreasing，序列 993→2917 | growth planning → decline response |
| regression anchor | `env008` / environment | `env_task_45311697d3_data_visual_disproportion_bar_chart_24`<br>`data_visual_disproportion/bar_chart/data_visual_disproportion_bar_chart_24` | 柱高与打印值不一致 | Solar 41.2% → Wind 29.8% |
| 优先筛选 | `b008` / business | `task_000d3fa08e_data_visual_disproportion_scatter_plot_27`<br>`data_visual_disproportion/scatter_plot/data_visual_disproportion_scatter_plot_27` | 点高与打印百分比不一致 | Price → Support |
| 优先筛选 | `env003` / environment | `env_task_2cd4dfad27_ms_inappropriate_scale_functions_pie_chart_23`<br>`MS_inappropriate_scale_functions/pie_chart/MS_inappropriate_scale_functions_pie_chart_23` | 饼图面积由错误 scale 驱动 | Nuclear → Hydroelectric |
| 优先筛选 | `pub012` / public | `pa_task_9eadd12d9b_ms_unconventional_scale_directions_choropleth_ma`<br>`MS_unconventional_scale_directions/choropleth_map/MS_unconventional_scale_directions_choropleth_map_18` | choropleth legend 方向反常 | NC → NY |
| 优先筛选 | `pub009` / public | `task_e024166274_ms_inappropriate_scale_range_stacked_bar_chart_1`<br>`MS_inappropriate_scale_range/stacked_bar_chart/MS_inappropriate_scale_range_stacked_bar_chart_104` | 截断纵轴影响阈值判断 | Tue+Wed → Tue only |
| 优先筛选 | `env025` / environment | `env_task_bfbd55be02_monthly_air_quality_alert_count`<br>`environment_rewrite/misleading_annotations_bar_chart_19/monthly_air_quality_alert_count` | Average 画在 442，真均值 359 | above-average response → average-range monitoring |
| 替补 | `pub011` / public | `task_d2bc5ae637_misleading_annotations_bar_chart_3`<br>`misleading_annotations/bar_chart/misleading_annotations_bar_chart_3` | Average 画在 200，真均值 300 | low-visitor review → normal monitoring |
| 已确认 title-family replication | `b038` / business | `task_2b513897e5_misleading_annotations_line_chart_46`<br>`misleading_annotations/line_chart/misleading_annotations_line_chart_46` | title 说 stable，Q1→Q4 上升 | growth review → maintain-current-plan |
| 替补 / inherited control | `b035` / business | `task_cb122340db_misleading_annotations_line_chart_32`<br>`misleading_annotations/line_chart/misleading_annotations_line_chart_32` | title 说 increasing，端点实际下降 | efficiency review → capacity expansion |

## 候选证据、混淆与取舍

| case | 已有 official/clean 证据 | clean competence | inherited error | 主要混淆与建议 | 原始 artifact |
|---|---|---|---|---|---|
| `pub010` | 旧 GUI smoke 只有 C 口述 increasing，O 未形成 matched exposure。新 compact calibration 修复了这一点：single/F0 的 C 2/2 growth+scorer true，O 2/2 decline trap+scorer false；F0 中模型消费 review 后仍直接确认错误。12-model `C/O/D=12/9/3`。 | **G1 + X(12/12)** | **自然错误已形成；可直接进入 inherited F3。** 注入错误仍需明确标为 evaluator-owned。 | 当前最强样本。下一步先做 matched F3 与 card-layout 轮换，检验反馈后是否 Back、重算首尾、改绑 growth、再 Confirm；不能把 F0 错误确认称为 recovery。 | [compact cells][cal-pub010]；[summary][cal-pub010-summary]；[metadata][m-pub010]；[12-model pairs][x11] + [GPT-5.6 pair][x1] |
| `env008` | GUI smoke O 为 Wind→Back→Wind，C 只点 41.2。Compact single O/C 都 Solar+scorer true；workflow-on 都漏 Confirm。Inherited F0/F3 native4 都 Back→Wind。Phase 3 显示 local reversal、Wind/entity bias 与 correctness-blind Confirm。12-model `12/9/3`。 | **G1 + X(12/12)** | **已构造并运行。** | natural compact 没有 Wind 初选；inherited 不可冒充 natural。作为跨批次锚点，不作为新增样本贡献。 | [GUI O][g-env008-o]；[GUI C][g-env008-c]；[natural][t-env008-natural]；[F0][t-env008-f0]；[F3][t-env008-f3]；[Phase 3][t-env008-p3]；[metadata][m-env008] |
| `b008` | 尚无 direct GUI compact run。12-model `11/3/8`：8 个模型 official 提交 Support、clean 选 Price；GPT-5.4 为完整 Support→Price pair。 | **X(11/12)，GUI 待筛选** | **可构造，未跑。** 单一 Support trap。 | 要保证所有点标签在 1280×960 同屏；轮换 chart point/card position，区分 printed-value reading 与固定最高点/位置 shortcut。 | [GPT-5.4 O][r54-o-b008]；[GPT-5.4 C][r54-c-b008]；[metadata][m-b008]；[pairs][x11] |
| `env003` | 尚无 direct GUI compact run。12-model `12/8/3`；Haiku、GPT-5.4、GPT-5.5 均为 official Hydroelectric trap、clean Nuclear correct。 | **X(12/12)，GUI 待筛选** | **可构造，未跑。** 单一 Hydroelectric trap。 | 用它替代 calibration 中 O invalid/C timeout 的 `b009`。仍需检查饼图标签可读性，并轮换 card order，防 Nuclear/first-card shortcut。 | [GPT-5.4 O][r54-o-env003]；[GPT-5.4 C][r54-c-env003]；[metadata][m-env003]；[pairs][x11] |
| `pub012` | 尚无 direct GUI compact run。12-model `11/2/9`；9 个模型 official NY trap、clean NC correct。 | **X(11/12)，GUI 待筛选** | **可构造，未跑。** 单一 NY trap。 | 用它替代 compact clean 也 2/2 选择 WA 的 `pub002`。地图州形、legend OCR 与 scale direction 仍耦合，必须保证完整 legend 和候选州同屏。 | [GPT-5.4 O][r54-o-pub012]；[GPT-5.4 C][r54-c-pub012]；[metadata][m-pub012]；[pairs][x11] |
| `pub009` | 尚无 direct GUI compact run。12-model `10/10/1`：Opus 4.7 出现 official Tue-only/clean Tue+Wed；另有一个反向 clean failure。 | **X(10/12)，GUI 待筛选** | **可构造，未跑。** “Tue only”是一个可注入 action。 | clean competence 尚可但 natural divergence 弱；同时耦合三站求和、阈值与 scale。只在 clean GUI 真提交且 official 有 susceptibility 时进入 natural recovery 主表。 | [Opus O][ropus-o-pub009]；[Opus C][ropus-c-pub009]；[metadata][m-pub009]；[pairs][x11] |
| `env025` | 旧 GUI smoke O/C 都打开 dashboard 后 complete，无分类。12-model `12/5/7`，7 个模型 official average-range、clean above-average。 | **X(12/12)；GUI 尚无 competence** | **可构造，未跑。** 单一 average-range trap。 | 反证只给 `442,380,255` 并要求重算，不能直接给 359/route；否则测成答案服从。该例提供与 pub010 不同的 annotation+arithmetic 模板。 | [GUI O][g-env025-o]；[GUI C][g-env025-c]；[GPT-5.5 O][r55-o-env025]；[GPT-5.5 C][r55-c-env025]；[metadata][m-env025] |
| `pub011` | 尚无 direct GUI compact run。12-model `12/3/9`；9 个模型 official normal-monitoring、clean low-visitor。 | **X(12/12)，GUI 待筛选** | **可构造，未跑。** 单一 normal-monitoring trap。 | wrong-average 证据强，但 shell template 与 `pub010` 同属 Tourism/Public Program。为满足非重复模板优先，排在 `env025` 后；可用于 arithmetic replication。 | [GPT-5.4 O][r54-o-pub011]；[GPT-5.4 C][r54-c-pub011]；[metadata][m-pub011]；[pairs][x11] |
| `b038` | Compact single/F0：clean 2/2 选择 growth-review、提交且 scorer=true；official 2/2 选择 maintain-current-plan trap、提交且 scorer=false，F0 `ordered_recovery=false`。12-model `12/0/12`，所有 official 都是 stability trap、clean 全成功。 | **G1 + X(12/12)** | **自然错误已形成；可进入 inherited F3。** | 已确认 `pub010` 的跨 task/scenario title-family replication。它提高 family-level 可信度，但不是新的 misleader 类型；机制广度统计只计一次 title-vs-line。优先六例仍先覆盖非重复模板。 | [compact cells][cal-b038]；[summary][cal-b038-summary]；[GPT-5.4 O][r54-o-b038]；[GPT-5.4 C][r54-c-b038]；[metadata][m-b038]；[pairs][x11] |
| `b035` | 旧 GUI smoke O 说 increasing/capacity、C 说 decreasing/efficiency，均无提交。新 compact calibration 的 single/F0 O/C 4/4 都正确选择 decline route 并 scorer=true。12-model `12/5/5`。 | **G1 + X(12/12)** | **可构造，未跑。** | 新 compact 条件下已无 natural official susceptibility，因此不能作为自然恢复主样本；可用 inherited error 检查一个 clean-competent agent 是否能撤销外生 capacity 错误，或用于 layout sensitivity。 | [compact cells][cal-b035]；[GUI O][g-b035-o]；[GUI C][g-b035-c]；[metadata][m-b035] |

## Expanded Stage-1 对原 panel 的反证

新 compact calibration 已经直接否定了若干旧 enrichment prior，下一步不应继续优先它们：

| 暂不纳入 | 新 GUI-Reflection 证据 | 原因 |
|---|---|---|
| `health016` | single/F0 的 O/C 4/4 都实际提交 decline trap，clean 也错。 | 没有 clean competence；旧 smoke 的 clean “increasing”口述没有转化为 action。 |
| `pub002` | single/F0 的 O/C 4/4 都提交 WA trap。 | reversed-scale clean reading floor；用 X evidence 更强的 `pub012` 先筛。 |
| `b009` | official 两格因 `PRESS_HOME` unsupported 而 invalid；clean 两格 timeout。 | 当前 compact interface/grounding floor，不能解释视觉 recovery；用 `env003` 替代同机制。 |
| `b011` | O/C single/F0 4/4 都提交 Increase trap。 | clean 错且无 directed divergence；只可作一般 arithmetic control。 |
| `b012` | O/C 都先选 Product E trap；三格错误提交，一格无提交。 | clean task floor，不能进入 recovery 主论证。 |
| `pub005` | calibration 只留下一个未提交 cell，没有完整 quartet；旧 formal 12-model 为 `12/12/0`。 | 无完整 matched artifact，也没有 official-specific divergence。 |
| `b002` | 旧 GUI clean 也给错误 Chrome；12-model `10/7/0`。 | direct clean reading failure且无严格 directed trap。 |
| `pub008` | 12-model `4/0/4`，但 GUI official invalid；workflow/GT 指 May 06，misleading target/completion rationale 写 May 08。 | clean competence 低且 metadata target 不一致，修复前不用于论文。 |
| `env032` | 不在 strict_review94，source review 仍为 `gt_uncertain`。 | 仅工程样本。 |

这意味着候选选择不能只看其他模型的 `D`：`health016/pub002` 的 X evidence 看似可用，但 GUI-Reflection clean arm 在 compact UI 上仍绑定到 trap。Stage-1 clean 实际行为必须覆盖 enrichment prior。

## 下一步运行顺序

1. **先正式化 `pub010`**：同一 canonical layout 重跑一次 interleaved receipt audit，再做 inherited F3；随后加至少一个 card-position 轮换。目标是观察 `decline review → Back → growth → Confirm` 是否真实发生。
2. **并行筛选五个非重复新模板**：`b008/env003/pub012/pub009/env025` 各跑 official/clean × single/F0。先看 clean actual action/submission，再看 official natural susceptibility。
3. 新样本只有在 clean 正确提交，或至少真实选择 correct 且剩余仅为 Confirm failure时，才进入 inherited F3。若 clean 选择 trap，记 competence floor，不用外生错误制造“恢复机会”。
4. `env008` 每批保留最小 anchor cells；`b038` 作为预先标明的 title-family replication 单列，不计作额外 mechanism；`pub011/b035` 仅按缺口替补，不与优先六例一起堆同模板。
5. 每例仍输出 `exposure → D0/A0 → review consumed → effective Back → D1/A1 → re-entry → Confirm → scorer`；F0 direct correct/error completion 都不算 recovery，只有 recovery-eligible 的错误后改选才算。

## Artifact 路径索引

- GUI smoke17：[runs][g-smoke-runs]、[summary][g-smoke-summary]、[逐样本分析](PER_SAMPLE_RECOVERY_ANALYSIS.md)。
- Expanded Stage-1 roots：[pub010 cells][cal-pub010]、[b038 cells][cal-b038]、[b035 cells][cal-b035]、[all calibration runs](runs/expanded_stage1_calibration/)。
- env008：[natural][t-env008-natural]、[inherited F0][t-env008-f0]、[inherited F3][t-env008-f3]、[Phase 3][t-env008-p3]。
- 12-model formal：[11-model pairs][x11]、[GPT-5.6 pairs][x1]。
- Candidate metadata：[business][meta-business]、[environment][meta-environment]、[public][meta-public]、[strict94](task_sets/strict_review94.jsonl)。

[g-smoke-runs]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/runs.jsonl
[g-smoke-summary]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/summary.json
[g-env008-o]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/traces/official/environment35/env008.jsonl
[g-env008-c]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/traces/clean/environment35/env008.jsonl
[g-env025-o]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/traces/official/environment35/env025.jsonl
[g-env025-c]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/traces/clean/environment35/env025.jsonl
[g-b035-o]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/traces/official/business47/b035.jsonl
[g-b035-c]: /mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0/traces/clean/business47/b035.jsonl

[cal-pub010]: runs/expanded_stage1_calibration/pub010/20260831T174559Z_6f56a144/cells.jsonl
[cal-pub010-summary]: runs/expanded_stage1_calibration/pub010/20260831T174559Z_6f56a144/summary.json
[cal-b038]: runs/expanded_stage1_calibration/b038/20260831T175302Z_d122e675/cells.jsonl
[cal-b038-summary]: runs/expanded_stage1_calibration/b038/20260831T175302Z_d122e675/summary.json
[cal-b035]: runs/expanded_stage1_calibration/b035/20260831T173044Z_7b721ac1/cells.jsonl
[t-env008-natural]: runs/targeted_env008/20260830T121341Z_7e5db661/cells.jsonl
[t-env008-f0]: runs/targeted_env008_inherited_f0/20260830T172120Z_9fcc9516/summary.json
[t-env008-f3]: runs/targeted_env008_inherited_f3/20260830T172355Z_8dc091a5/summary.json
[t-env008-p3]: runs/phase3_formal/20260831T145905Z_1a0aa4a4/summary.json

[x11]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/paired_results.jsonl
[x1]: ../../pair_evaluation_records/gpt56_sol_litellm_full140_merged_20260711/paired_results.jsonl
[r54-o-b008]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/official/runs.jsonl#L47
[r54-c-b008]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/clean/runs.jsonl#L47
[r54-o-env003]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/official/runs.jsonl#L89
[r54-c-env003]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/clean/runs.jsonl#L89
[r54-o-pub012]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/official/runs.jsonl#L12
[r54-c-pub012]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/clean/runs.jsonl#L12
[ropus-o-pub009]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/claude_opus_4_7_aime_responses_temp0_top_p1_seed12345/official/runs.jsonl#L9
[ropus-c-pub009]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/claude_opus_4_7_aime_responses_temp0_top_p1_seed12345/clean/runs.jsonl#L9
[r55-o-env025]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt_5_5_litellm_temp0_top_p1_seed12345/official/runs.jsonl#L111
[r55-c-env025]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt_5_5_litellm_temp0_top_p1_seed12345/clean/runs.jsonl#L111
[r54-o-pub011]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/official/runs.jsonl#L11
[r54-c-pub011]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/clean/runs.jsonl#L11
[r54-o-b038]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/official/runs.jsonl#L77
[r54-c-b038]: ../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/gpt54_temp0_top_p1_seed12345/clean/runs.jsonl#L77

[meta-business]: ../../benchmark_v2_open/splits/official140/business47_tasks.jsonl
[meta-environment]: ../../benchmark_v2_open/splits/official140/environment35_tasks.jsonl
[meta-public]: ../../benchmark_v2_open/splits/official140/public39_tasks.jsonl
[m-b008]: ../../benchmark_v2_open/splits/official140/business47_tasks.jsonl#L8
[m-b035]: ../../benchmark_v2_open/splits/official140/business47_tasks.jsonl#L35
[m-b038]: ../../benchmark_v2_open/splits/official140/business47_tasks.jsonl#L38
[m-env003]: ../../benchmark_v2_open/splits/official140/environment35_tasks.jsonl#L3
[m-env008]: ../../benchmark_v2_open/splits/official140/environment35_tasks.jsonl#L8
[m-env025]: ../../benchmark_v2_open/splits/official140/environment35_tasks.jsonl#L25
[m-pub009]: ../../benchmark_v2_open/splits/official140/public39_tasks.jsonl#L9
[m-pub010]: ../../benchmark_v2_open/splits/official140/public39_tasks.jsonl#L10
[m-pub011]: ../../benchmark_v2_open/splits/official140/public39_tasks.jsonl#L11
[m-pub012]: ../../benchmark_v2_open/splits/official140/public39_tasks.jsonl#L12
