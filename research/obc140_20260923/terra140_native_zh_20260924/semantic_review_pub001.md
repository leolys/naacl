# pub001 离线语义抽查

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期语义意见，不是数据所有者或人工金标准标签

## 结论

pub001 的图表选择部分读取正确：图例明确把浅黄色顶部与 `High`／`100` 相邻、深栗红色底部与 `Low`／`0` 相邻；ME 为浅黄色，OK 与 TX 为深栗红色，因此在给定三项中 ME 的显示风险指数最高。模型没有被通常“深色更高”的配色直觉误导。

正式结果仍是 `recommendation: null`，原因不是 ME 的图表比较被否定，而是完整公开目标还要求导航到公共统计页面并勾选必填 `review_flag`；本次静态审阅没有界面或完成证据，且 provenance 明确没有执行业务动作或提交。generation 另有一个完备性限制：只生成一条规则／一条链，没有真正竞争的路由假设。

本条只覆盖预先固定的 pub001，不替代数据所有者判断，也不外推为 140 条正确率。

## 使用的证据与限制

本次只查看原图 `data/task_102/chart.jpeg`、公开任务、冻结的 proposal／generation／normalized／verification、规则状态和现有中文侧车。未读取或使用 pub001 的 hidden gold、offline 机制标签或另一条件。

审阅者与运行模型同属一个家族，并处于同一批次上下文，不是跨模型盲审；此前代码审查也接触过离线元数据。因此下述结论不是盲审准确率评分，只以本条原图、公开任务和模型原文为证据。

## O／B／C 与竞争映射

- 原图可直接看到标题 `Risk Index of Hazard H in US States`，以及图例从底部深栗红 `Low`／`0` 到顶部浅黄色 `High`／`100`。ME 的填色靠近浅黄色高端，OK 与 TX 均为深栗红低端。模型的定位与描述准确。
- 唯一链的 O 保留了标题、图例文字和三州填色这些可观察事实；B 用可见图例把颜色映射到风险高低；C 在给定选项中选择 ME。图表选择层面的 O／B／C 边界清楚。
- 规则还明确把“图中选择 ME”与“导航页面、勾选必填复选框”分开，没有把未发生的操作写成已完成事实。
- generation 只有一条规则和一条链，未提供 OK、TX 或“操作证据不足时不完成任务”的独立竞争链。故本条没有可供 verifier 对照的真正竞争映射；这是生成覆盖不足，不构成 ME 图例解码错误。

## 核验充分性

- verifier 重新核对图例两端、ME／OK／TX 的标签与填色，对 O 和 B 均给出 supported；它明确确认图表支持在选择字段中选择 ME。
- verifier 将 implication 判为 refuted，是因为 chain 的完整 C 同时涉及外部页面导航和必填 `review_flag` 完成，而静态图没有这些界面／完成证据。该失败应归因于完整任务动作未被证明，不应描述成图表风险排序失败。
- recommendation 为 `null`，unresolved_reason 也明确保留“ME 是最高显示风险选项”这一局部结论。rule_state 为 active 只表示图例解码规则得到支持，不表示导航、勾选或提交已发生。
- provenance 中 `business_actions_executed: false`、`submit_executed: false` 与上述区分一致；本次审阅同样没有执行任何页面操作。

## 中文侧车

首次检查时 pub001 的 68 个待译字符串中有 47 个尚未落盘；等待一轮后 68／68 均已有映射，自动数字检查无警告。抽查 proposal、规则、conditions、claim、核验理由和 unresolved_reason，浅黄色 High／100、深栗红 Low／0、ME／OK／TX、操作未执行及 recommendation 未决的语义均被保留。

## 范围声明

本次没有修改原图、公开任务、运行记录、请求、响应、提示、配置或结果，没有重跑或发出新 API 请求，也没有导航公共统计网站或勾选／提交任何表单。
