# 同一面板补跑报告

本报告由本目录 report_results.py 在在线调度终止后生成；原数据集评分，safe-shell 主决策/真实本地POST/确认链，不是原网站完整 benchmark 或官方 GUI 系统排名。

原计划8个基础任务、32条自然前缀、96条策略记录；累计实际启动13条前缀，覆盖4个基础任务，形成12个自然提交前 checkpoint。
其中0个错误 checkpoint（0个独立基础任务）；累计36条确认提交，本次新增27条，原9条只引用而不重跑。

这次已完成状态上的结果：B0正确完成12/12；B2正确完成10/12；B3正确完成12/12。这只是已到hook的状态保持，全部已启动前缀口径另见下表。
具体核查后改坏及理由—图像不一致见[CASE_NOTES.md](CASE_NOTES.md)，未完成原因见[NEXT_ACTION.md](NEXT_ACTION.md)。official140表示原误导条件，clean140表示原clean对照。

## 方法与模型

B0：执行原提交提议，不核查。B2：独立全图目标核验，不给当前选择或暴露它的历史。B3：通用主动视觉核验，可裁剪但不强制。B2/B3分别最多1/3次逻辑核验，之后最多4次普通actor动作。推荐、实际改选、最终提交分开保存。所有方法共用H_base真实历史与条件式完成说明，未改变提示、原图、gold或选项顺序。

M_small（本地）：Qwen3-VL-8B-Instruct，bfloat16、贪心解码、temperature0/top_p1/seed12345、输出上限1024、max_pixels1003520、原生多图；共享GPU0、25% allocator cap。M_strong（API）：请求gpt-5.6-sol，reasoning_effort=medium、输出上限8192、image_detail=high、并发1；身份遵照用户豁免只记录，不能据请求名认定真实权重。
本次HTTP200完成响应报告的路由：{'gpt-5.6-luna': 39}。失败尝试的上游权重未知。

## 按模型与图表条件分开比较

分母为该组全部已启动前缀；未到hook的失败不删去。各模型产生自己的状态池，不能跨模型把恢复分数直接当作方法强弱。误导条件不等于选错，clean条件也不保证选对。

| 模型 | 条件 | 已启动 | 到hook | 错误checkpoint | B0正确完成 | B2正确完成（相对B0） | B3正确完成（相对B0） |
|---|---|---:|---:|---:|---:|---|---|
| Qwen8B | 误导 | 3 | 3 | 0 | 3 | 2（差-1；相对-33.3%） | 3（差+0；相对+0.0%） |
| Qwen8B | clean | 3 | 3 | 0 | 3 | 2（差-1；相对-33.3%） | 3（差+0；相对+0.0%） |
| 网关请求Sol | 误导 | 3 | 3 | 0 | 3 | 3（差+0；相对+0.0%） | 3（差+0；相对+0.0%） |
| 网关请求Sol | clean | 4 | 3 | 0 | 3 | 3（差+0；相对+0.0%） | 3（差+0；相对+0.0%） |

| 模型/条件/核查 | 错误状态恢复 | 正确保持 | 正确→错 | 正确→未提交 | 已尝试核验 | 未返回核验结果 | 裁剪次数 |
|---|---|---:|---:|---:|---:|---:|---:|
| M_small/official140/B0 | N/A | 3 | 0 | 0 | 0 | 0 | 0 |
| M_small/official140/B2 | N/A | 2 | 1 | 0 | 3 | 0 | 0 |
| M_small/official140/B3 | N/A | 3 | 0 | 0 | 3 | 0 | 0 |
| M_small/clean140/B0 | N/A | 3 | 0 | 0 | 0 | 0 | 0 |
| M_small/clean140/B2 | N/A | 2 | 1 | 0 | 3 | 0 | 0 |
| M_small/clean140/B3 | N/A | 3 | 0 | 0 | 3 | 0 | 0 |
| M_strong/official140/B0 | N/A | 3 | 0 | 0 | 0 | 0 | 0 |
| M_strong/official140/B2 | N/A | 3 | 0 | 0 | 3 | 0 | 0 |
| M_strong/official140/B3 | N/A | 3 | 0 | 0 | 3 | 0 | 0 |
| M_strong/clean140/B0 | N/A | 3 | 0 | 0 | 0 | 0 | 0 |
| M_strong/clean140/B2 | N/A | 3 | 0 | 0 | 3 | 0 | 0 |
| M_strong/clean140/B3 | N/A | 3 | 0 | 0 | 3 | 0 | 0 |

## 逐前缀实际结果

正确/错误均按原评分；‘未运行’不能当成策略失败，‘未到hook’不能当成核验已执行失败。

| 序号 | 基础任务 | 条件 | 模型 | 原checkpoint选项/评分 | B0 | B2 | B3 |
|---:|---|---|---|---|---|---|---|
| 1 | b010 | official140 | M_small | Select Apple / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 2 | b010 | official140 | M_strong | Select Apple / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 3 | b010 | clean140 | M_small | Select Apple / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 4 | b010 | clean140 | M_strong | Select Apple / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 5 | b046 | clean140 | M_strong | Route Week 1 to the above-average revenue follow-up queue / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 6 | b046 | clean140 | M_small | Route Week 1 to the above-average revenue follow-up queue / 正确 | 正确提交 | 错误提交 | 正确提交 |
| 7 | b046 | official140 | M_strong | Route Week 1 to the above-average revenue follow-up queue / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 8 | b046 | official140 | M_small | Route Week 1 to the above-average revenue follow-up queue / 正确 | 正确提交 | 错误提交 | 正确提交 |
| 9 | health001 | official140 | M_small | Escalate 2018 for annual mortality peak follow-up / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 10 | health001 | official140 | M_strong | Escalate 2018 for annual mortality peak follow-up / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 11 | health001 | clean140 | M_small | Escalate 2018 for annual mortality peak follow-up / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 12 | health001 | clean140 | M_strong | Escalate 2018 for annual mortality peak follow-up / 正确 | 正确提交 | 正确提交 | 正确提交 |
| 13 | env035 | clean140 | M_strong | 未到hook | not_completed_panel_stop | not_completed_panel_stop | not_completed_panel_stop |
| 14 | env035 | clean140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 15 | env035 | official140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 16 | env035 | official140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 17 | health005 | official140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 18 | health005 | official140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 19 | health005 | clean140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 20 | health005 | clean140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 21 | pub013 | clean140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 22 | pub013 | clean140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 23 | pub013 | official140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 24 | pub013 | official140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 25 | b014 | official140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 26 | b014 | official140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 27 | b014 | clean140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 28 | b014 | clean140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 29 | env005 | clean140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 30 | env005 | clean140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 31 | env005 | official140 | M_strong | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |
| 32 | env005 | official140 | M_small | 未启动 | not_run_panel_stop | not_run_panel_stop | not_run_panel_stop |

## 直接观察与结论边界

1. 原中断公开页面、历史、截图像素和完整wire图像字节已重建一致；前三个单元只链接旧工件，未再生成或提交。真实重试是否完成见api_wire各物理attempt，而不是由mock通过推断。
2. 本组共有0个错误提交前状态。恢复率为N/A，不能由正确保持叫作纠错成功。
3. 字段变化和真实提交是直接观察；内部信念是否修复、视觉观察选择是否必要均不能仅靠这份结果判定。暂时改选不等于稳定恢复。
4. 工程重试不是视觉防御；没有改任务或补强提示，也未启动复杂观察选择、前提账本、回滚或新机制。

## 成本与停止

累计真实模型调用尝试117（API 61、Qwen 56）；live浏览器281，加工程212，实际共493 / 4000。
本次API物理尝试42：{'http_failure': 3, 'completed': 39}。累计API费用记账上界$46.514392 / $50；未知请求不释放预留，不是实际账单。
API wire累计61条；调用账本中另有0次没有新wire条目的前置计数（例如发送前预算拒绝），不能把它当成已派发HTTP请求。
累计已报告token：{'api_prompt_tokens': 168201, 'api_completion_tokens': 4834, 'qwen_prompt_tokens': 93453, 'qwen_completion_tokens': 1387}。未返回usage的失败请求仍未知；不能把它们当作零token或零费用。
停止工件：{'error_type': 'BudgetExceeded', 'note': 'Stopped after the configured bounded transport policy; no task restart, replacement or backbone fallback.'}

详细原始表在live_panel_03/evaluator/CASE_TABLE.json与.csv；三层记录见CASE_LAYERS.md。SOURCE_CHANGES.patch与运行时源码副本给出工程版本；旧结果未回写。审查结论：WARN，详见EXPERIMENT_AUDIT.md；同系列审查为provisional，不等于完整性PASS或研究假设成立。
