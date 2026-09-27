# 固定小面板的离线费用统计方法

`analyze_usage.py` 只读本地证据，不导入执行器、不读取凭据、不发送 API 或其他网络请求。固定模型为 Sol／Terra／5.4-mini，固定任务为 b001／pub013，每例 proposal／generation／verification／translation 四阶段，计划最多 24 个请求记录。它不会启动或补跑任何任务。

## 运行与输出

完成后在此目录运行：

```powershell
& 'D:\anaconda\python.exe' '.\analyze_usage.py'
```

输出为本目录 `cost_summary.json`，以后可重复离线生成。`--root` 可指定同构的面板目录，测试使用临时目录；生产执行不改 `PLAN.md`、执行器、核心逻辑、任一 run 或历史 attempt。

按模型、任务、阶段统计 attempt 记录数、HTTP 成功／失败／未知、缺失 usage、字段冲突、耗时、已知 token 数及两种参考金额；每条 attempt 保留响应模型、HTTP 状态、结束原因、错误分类与耗时。流水线 `completed`／`invalid`／`failed`／`blocked` 与 HTTP 成败分别记录，不能将 HTTP 200 当作四阶段语义成功。

读取路径为 `runs/<固定模型>/tasks/<固定任务>/<固定阶段>/round_*/attempt_*.json`。真实保存的请求记录数与各模型 `budget.json.request_attempts` 对齐，并核对 budget events 的任务、阶段、轮次、attempt 身份。发现固定面板以外的 attempt 文件、超过每模型 8 次或总计 24 次、预算预留但记录尚未落盘，都必须在报告中呈现。实时运行过程中可能短暂不对齐，不能将缺失记录当免费请求。

## 用量归一化

只将 OpenAI 同义字段视为同一计费量：`input_tokens`／`prompt_tokens`、`output_tokens`／`completion_tokens`、对应 details 中缓存读写，以及 `billing_usage.openai_usage` 内的别名。相同数值只记一次。

出现 0 与唯一非 0 值时，选唯一非 0 值，同时保留冲突字段的完整路径、原值和决策；存在多个不同非 0 值时不臆断，相关请求金额设为未知。输入／输出总量缺失、非法 token 值、总数不符或缓存读写合计超过输入，也不给完整金额。推理 token 只做诊断，不再加到已包含推理的输出总量上。

缺少缓存 details 时，仅在费用情景内明确假设缺失缓存量为 0，并保留该假设。缺少输入／输出 usage 时费用是未知，绝非 0。`known_usage_scenario_subtotals_usd` 只覆盖已知部分；有未知请求时，`all_recorded_attempts_scenario_totals_usd` 为 null。二者均不表示账户实扣或经证明的费用下界。

## 两种费用情景

单价直接读取已有 `provider_rates.json`。单位为美元／1M tokens；短上下文共同范围限制为不超过 272,000 输入 tokens。令 P 为输入总数、O 为输出总数、C 为返回的缓存读取量、W 为返回的缓存写入量；读写作为输入总数中互不重叠的子集，是明确的估算假设。

- 情景 1：`((P-C) × 普通输入价 + C × 缓存读价 + O × 输出价) / 1M`。没有额外写入溢价。
- 情景 2：情景 1 加 `W × 普通输入价 × 0.25 / 1M`。只对返回的写入量加 25%，不重复加完整写入费。

情景 2 的倍率不是已确认的 APIYI 写入价格，两种金额也不是上下界。实际账户分组、充值赠送及实扣未知，输出始终保留 `actual_charge_usd=null`。公开资料版本边界见 `CACHE_BILLING_NOTE.md`。

## 140 条纯算术外推的门槛

只有该模型两个固定开发例均完成四阶段、每任务阶段恰好一个 attempt、全部用量可估、预算与记录身份完全对齐、没有模型／阶段元数据问题，才给出每例完整费用的均值乘 140，并另列两例最小值／最大值乘 140 的敏感性。其他模型是否完成不影响某个已完成模型自己的门槛。

这两个已知开发例不代表 140 条的分布，min／max 不是置信界限，外推不含未知重试和账户实扣。批量预算未确认，外推结果不能授权执行 140 条；脚本没有执行实验的能力。

`completed_task_scenario_costs_usd` 单独列出已经完成四阶段的单例费用，即使同模型另一例失败，也可以如实展示这个已完成单例；这不会解除两例完整后才能外推的门槛。

## 验证

`test_usage.py` 使用合成用量与临时面板，检查重复别名不重计、0／非 0 冲突、不同非 0 冲突、缓存读写价、推理不重复计费、缺失 usage 保持未知、预算数量与身份对齐、完整两例外推门槛，以及证据读取不改 run 文件。测试不使用真实凭据，不运行推理，也不生成真实面板最终汇总。

实际验证时设置进程环境变量 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，使用 `D:\anaconda\python.exe -m pytest test_usage.py -q -p no:cacheprovider`，避免无关第三方测试插件参与。
