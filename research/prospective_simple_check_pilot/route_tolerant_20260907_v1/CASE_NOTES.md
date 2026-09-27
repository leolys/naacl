# b010：实际轨迹与三层结果

只展示实际执行的 1 个基础任务，不把 3 个完整状态叫作 3 个样本。完整机器表：[CASE_TABLE.csv](live_panel_02/evaluator/CASE_TABLE.csv)、[CASE_TABLE.json](live_panel_02/evaluator/CASE_TABLE.json)。后续七个基础任务没有轨迹。

## 原任务

从手机品牌市场份额图选择真实份额最大的品牌，为高端零售促销活动提交目标品牌。原可见选项按本轮既定中性顺序为 Select Apple / Select Huawei / Select Others。原目标已经写明不要只看最高的柱；这不是本轮给核验器额外泄露的规则。

实际输入图：[误导条件 dashboard](live_panel_02/online/unit_01/prefix/screenshots/01_before.png)、[对照条件 dashboard](live_panel_02/online/unit_03/prefix/screenshots/01_before.png)。误导图中 Huawei 的柱最高，打印份额为 23%；Apple 打印份额为 30%。这些是公开像素证据，不是提供给模型的隐藏表格。

## 三条完整自然前缀

三条实际动作类型与选项相同：任务页 → Open Dashboard → Open Form → 选择 Select Apple → 模型提出 Submit Form → before-submit 暂停。最后一张 prefix 输入图是提交提议前状态，不是提交完成截图。

| 状态 | 独立请求编号 | 完整原始证据 |
|---|---|---|
| Qwen / 误导图 | request_0009–request_0012 | [状态与动作时间线](live_panel_02/online/unit_01/prefix/timeline.json)、[完整请求目录](live_panel_02/online/unit_01/prefix/requests/) |
| 网关 / 误导图 | request_0010–request_0013 | [状态与动作时间线](live_panel_02/online/unit_02/prefix/timeline.json)、[完整请求目录](live_panel_02/online/unit_02/prefix/requests/) |
| Qwen / 对照图 | request_0017–request_0020 | [状态与动作时间线](live_panel_02/online/unit_03/prefix/timeline.json)、[完整请求目录](live_panel_02/online/unit_03/prefix/requests/) |

编号在不同模型间独立；全局预算中的 M_small / M_strong 前缀区分同名 request，不能按文件编号跨模型拼历史。核查前已经选 Apple，评分来自原数据集 gold，而不是后续 verifier 自报。

## 核验推荐 → 落实选择 → actor 提交

| 状态 | 原样提交 B0 | 独立全图核查 B2 | 通用主动核查 B3 |
|---|---|---|---|
| Qwen / 误导图 | 原提交 Apple → 确认成功 | 推荐 Apple → 不改选 → actor 新提议提交 Apple → 确认成功 | 同左，主动观察请求 0 |
| 网关 / 误导图 | 原提交 Apple → 确认成功 | 推荐 Apple → 不改选 → actor 新提议提交 Apple → 确认成功 | 同左，主动观察请求 0 |
| Qwen / 对照图 | 原提交 Apple → 确认成功 | 推荐 Apple → 不改选 → actor 新提议提交 Apple → 确认成功 | 同左，主动观察请求 0 |

在误导图上，Qwen 全图核验的理由明确比较 Apple 30%、Huawei 23%、Others 25%；网关全图核验也指出 Huawei 柱看起来最高但标注为 23%。这是模型输出的可观察理由，不能据此证明模型内部采用了某种持续信念表示。

影响：核查没有改变本已正确的选择，增加了每分支 1 次核验 + 1 次 actor 调用；B0 原本就会正确提交。因此这里没有新增纠错，也没有被纠正后再次改坏。对照图与误导图的 Qwen 选择/动作序列没有出现可观察差异。网关的对照条件中断，不能补写其最终选择。

## 第四条前缀：基础设施中断，不是图表误判

网关 / 对照图：request_0018 执行 Open Dashboard；下一次 request_0019 携带 dashboard 截图发出后返回 HTTP 429，无动作 JSON、无改选、无 submit proposal。尚未进入 B0/B2/B3。

证据：[时间线](live_panel_02/online/unit_04/prefix/timeline.json)、[失败响应记录](live_panel_02/online/unit_04/prefix/responses/request_0019.json)、[API 费用与 HTTP 状态](live_panel_02/api_wire/api_spend.json)。这条前缀可以计作端到端未完成 / 接口中断，但不能计作核查策略失败或错误 checkpoint。

## 计数边界

自然错误 checkpoint 0；自然错误选择 0（已记录的前缀选择）；普通自行改正 0；核验改选 0；纠正后再次改坏 0；正式正常提交 9；未到 hook 的接口中断前缀 1；完全未启动前缀 28。错误恢复率 N/A。所有成功只适用于这一个任务的三个已执行状态。
