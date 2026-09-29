# 仓库现状审计：GUI-Reflection baseline 所处位置

审计截止时间：2026-08-30。结论先行：这个仓库已经完成了规模化的误导图表 Web Agent 成对评测，也做过跨步历史/反思提示实验；但在本轮工作以前，没有运行过官方 GUI-Reflection 模型。`benchmark_v2/` 只是一个带答案泄漏的单样本展示壳，正式实验应以 `benchmark_v2_open/` 及原有四类场景壳为基础。

## 1. `benchmark_v2/` 是单样本展示，不是可计分 baseline 集

- [`benchmark_v2/benchmark_manifest.json`](../../benchmark_v2/benchmark_manifest.json) 明确写有 `task_count: 1`、`first_task: pub011`。
- [`benchmark_v2/benchmark_v2_public_app.py`](../../benchmark_v2/benchmark_v2_public_app.py) 的 dashboard 和 review 页面始终并排显示 “Clean Chart” 与 “Original Misleading Chart”。
- 同一应用在 review 页面直接显示 July visitors 和 “True July-September average”，在 actions 页面还可展开 “Reviewer action labels”，其中把选项标成 Correct、Misleading 或 Irrelevant。
- [`benchmark_v2/public_tasks.jsonl`](../../benchmark_v2/public_tasks.jsonl) 的可见 business rationale 与 reference instruction 也直接说明 July 低于平均值及应采取的动作。

因此，在这个壳上得到正确提交，无法归因于模型撤销了误导图表前提。它最多用于检查浏览器、坐标动作和提交记录能否连通，不能作为 GUI-Reflection 的性能数字。

## 2. 可用的数据发布候选是 `benchmark_v2_open/`

[`benchmark_v2_open/benchmark_manifest.json`](../../benchmark_v2_open/benchmark_manifest.json) 与 [`benchmark_v2_open/DATASET_CARD.md`](../../benchmark_v2_open/DATASET_CARD.md) 给出的构成为：

- `official140`：140 个误导图表任务；
- `clean140`：与上述任务通过 `pair_group_id` 配对的 140 个 clean 任务；
- `real_world40`：40 个无 clean 对照的真实世界扩展任务；
- 共 180 个 case、320 个 task instance、797 个发布资产。

发布校验脚本是 [`benchmark_v2_open/scripts/validate_release.py`](../../benchmark_v2_open/scripts/validate_release.py)。`real_world40` 只能单独报告，不能与 synthetic paired 指标混成一个 clean-minus-misleading 效应。

### 配对并非全部只差图表

逐字段比较 `official140` 与 `clean140` 后，140 对中有 26 对同时改变了任务/工作流、动作空间或 ground truth：`b017`–`b034` 共 18 对，`health006`–`health013` 共 8 对。由此得到真正的 chart-only 集合 114 对。规则、逐对来源行和差异字段记录在：

- [`build_task_sets.py`](build_task_sets.py)
- [`task_sets/manifest.json`](task_sets/manifest.json)
- [`task_sets/chart_only114.jsonl`](task_sets/chart_only114.jsonl)

这 26 对仍可作为 exploratory full-140 结果，但不能支持“两个条件只差图表”的因果表述。

### 壳层元数据泄漏需要对称清理

环境和健康场景的任务首页会把 `misleader_type`、`task_readiness` 渲染进 `.chips`，见 [`environment_shell_app.py`](../../environment_energy_shell/environment_shell_app.py) 与 [`health_shell_app.py`](../../health_shell/health_shell_app.py)。已有反思实验在 [`reflection_history.py`](../reflection_history.py) 中会移除 `.chips`。GUI-Reflection 正式跑也应在 official/clean 两臂使用同一视觉清理规则；清理只影响元数据 badge，不能读取 DOM 后把文本、selector 或 element box 交给模型。

## 3. 主论文与后续实验已经做到的程度

### 主成对结果

仓库中最完整的主论文汇总候选是 [`final_selected_merged_20260523_kimi_full140_replaced/overall_experiment_summary_table.md`](../../pair_evaluation_records/final_selected_merged_20260523_kimi_full140_replaced/overall_experiment_summary_table.md)：

- 11 个模型；
- 每个模型 140 对 official/clean 任务；
- 共 1540 个 paired row；
- micro-average 为 official `639/1540`、clean `1173/1540`；
- clean-minus-official 差距为 `+34.68 pp`；
- clean 成功而 official 非成功的翻转 pair 共 `593/1540`；其中仓库的 directed-choice 审计进一步识别出 `531/593` 个指定误导动作。

这说明仓库已经具备大规模 paired susceptibility 证据，不是停留在任务生成阶段。不过这些 agent 的既有接口并不等于 GUI-Reflection 的截图—坐标策略。

### GPT-5.6 与 CUGA 后续实验

- [`gpt56_sol_litellm_full140_merged_20260711/pair_summary.md`](../../pair_evaluation_records/gpt56_sol_litellm_full140_merged_20260711/pair_summary.md) 另有 GPT-5.6 的 140 对结果：official `72/140`、clean `117/140`。它不在上面的 11 模型主汇总表中，应作为后续追加结果单列。
- [`cuga_policy_system_v2_guarded_full140_gpt54_20260711/summary.md`](../../pair_evaluation_records/cuga_policy_system_v2_guarded_full140_gpt54_20260711/summary.md) 有 CUGA playbook/guard 的 560 行实验，即 140 task × official/clean × control/guarded。它测的是提交前策略与 guard，不是 GUI-Reflection 的局部视觉纠错模型。

### 512-cell `reflection_history` pilot

[`reflection_history_pilot_20260727_restart1/final_conclusion.md`](../../pair_evaluation_records/reflection_history_pilot_20260727_restart1/final_conclusion.md) 汇总了 512 个正式 cell：GPT-5.4 与 Claude Sonnet 4.6、official/clean、`no_history`、`previous_step`、`full_history`、`structured_falsification`，每个设计单元含重复运行。

这个 pilot 的真实结论是 `harness_fix`，不是“反思方法已经有效”：

- `previous_step` 消除了观测到的 3 个 no-history cycle block；
- structured 相对 previous-step 的 success 改善约 2.2 个百分点，bootstrap 区间跨 0；
- full-history 有明显 schema warning 与截断不平衡；
- strict fail-closed parser sensitivity 的结论是 `no_go`。

更关键的是，三个观测 cycle 都发生在同一表单内的 A/B 选项切换，没有出现“进入错误分支 → `PRESS_BACK` → 换分支”的导航轨迹。该实验使用的模型、历史提示与动作接口也不是官方 GUI-Reflection。因此它只能为任务选择和失败模式提供先验，不能充当本次 baseline 的结果。

## 4. 当前缺口

在现有结果树和新适配器目录中，没有官方 `craigwu/GUI_Reflection_8b_SFT` 生成的正式 trajectory。当前明确缺少的是：

1. 官方仓库 checkout；
2. 完整的官方 8B SFT 权重；
3. 在误导/clean 成对条件下由官方 `GUI_Reflection_Agent` 自己生成的动作；
4. 自然误入后真实发生的 Back、退出、重入或恢复统计。

所以，仓库已经具备数据、壳、评分、既有模型对照和反思 pilot，但“GUI-Reflection 是否能抵抗这些误导可视化”仍是尚未获得模型观测值的问题。
