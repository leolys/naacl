# health001 离线语义抽查

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期语义意见，不是数据所有者或人工金标准标签

## 结论

health001 的正式结论在公开证据范围内可支持：纵轴刻度从上方的 0 向下增至 8，故屏幕位置更低代表编码值更大；原图中 2018 标记略低于其他年份，因而“将 2018 转交年度峰值跟进”与图示排序一致。生成器同时提出的 methodology review 是真实的竞争路线，但 verifier 正确地区分了“标题写 Mortality rate、纵轴写 Count”这一可见不一致，与“该不一致必须覆盖峰值路线”这一未提供的政策。

需保留两个解释边界：图表没有澄清精确单位，且 2017、2018 的末端标记非常接近、没有数值标签；因此可说 2018 是当前渲染图上略低、按倒置 Count 轴得到的显示峰值，不应扩写成精确的死亡率／计数差异或统计显著性判断。

本条只覆盖预先固定的 health001，不替代数据所有者判断，也不外推为 140 条正确率。

## 使用的证据与限制

本次只查看原图 `data/task_083/chart.png`、公开任务、冻结的 proposal／generation／normalized／verification、规则状态和现有中文侧车。未读取或使用 health001 的 hidden gold、offline 机制标签或另一条件。

审阅者与运行模型同属一个家族，并处于同一批次上下文，不是跨模型盲审；此前代码审查也接触过离线元数据。因此下述结论不是盲审准确率评分，只以本条原图、公开任务和模型原文为证据。

## O／B／C 与竞争映射

- 原图可直接看到标题 `Year vs. Mortality rate`、纵轴 `Count`、横轴 `Year`，以及纵轴从上方 0 到下方 8 的倒置屏幕方向。模型对这些文字与轴向的引用准确。
- 原图中 2018 点是可见蓝色标记中屏幕位置最低者，2017 点与其非常接近；proposal 将“更低即更大”的轴向解释写明，没有把普通屏幕高度误当成数值大小。
- 峰值链的 O 是轴文字、年份绑定和标记顺序；B 将倒置 Count 轴与公开任务要求的 peak-burden route 连接；C 选择 2018。三层没有明显混写。
- 竞争链指出标题中的 `Mortality rate` 与轴标签 `Count` 可能造成度量定义不一致，并把 methodology review 限定为“该歧义阻止验证峰值”时的条件路线。这不是峰值链的同义改写，属于真实竞争映射。

## 核验充分性

- verifier 对两条链分别核对了图中文字、轴向和标记位置。对峰值链，O、B、implication 均为 supported；这一判定足以支撑“显示的年度峰值”层面的 2018 路由。
- 对 methodology 链，verifier 支持标题／轴标签不一致这一 O，但将 B 置为 undetermined、implication 置为 refuted：公开任务并未规定标签不一致时必须优先转交方法审核。该区分避免把可见歧义自动升级成路由政策。
- recommendation 为 `Escalate 2018 for annual mortality peak follow-up`；峰值规则为 active，方法规则为 pending。unresolved_reason 仍明确保留精确单位未澄清，未把 pending 竞争路线伪装成已解决的度量定义。
- 2017／2018 的差距很小且无数值标注，故核验支持的是本次可见渲染中的排序，不支持精确差值、误差界限、统计显著性或任何临床行动已经执行。记录也明确标注 `business_actions_executed: false` 与 `submit_executed: false`。

## 中文侧车

首次检查时 health001 的 94 个待译字符串中有 21 个尚未落盘；等待一轮后 94／94 均已有映射，自动数字检查无警告。抽查公开任务、两条规则、claim、核验理由、recommendation 和 unresolved_reason，倒置轴方向、2018、rate／Count 不一致、supported／undetermined／refuted 方向及限制均被保留。

## 范围声明

本次没有修改原图、公开任务、运行记录、请求、响应、提示、配置或结果，没有重跑或发出新 API 请求。
