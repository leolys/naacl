# health010 离线语义抽查

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期语义意见，不是数据所有者或人工金标准标签

## 结论

health010 对图形内容的读取基本可靠，但 generation 没有形成真正竞争的路由规则，也没有让任一单条链同时具备“正向图形证据”和“为何应转交更广泛人群审查”的完整桥接。两条链都绑定同一个 broader-population-review 选项：一条只证明选定地区呈正向图形，另一条只以副标题证明样本范围受限。verifier 因而把两条 implication 均判为 refuted，并保持 recommendation 为 `null`；这比直接接受 proposal 更符合当前链级证据。

原图明确写着 `Selected high-burden regions`。可见的 A–E 点支持“这些选定地区中 PM2.5 exposure index 与 Asthma ER visits 同向增加”的描述，但不支持因果解释、总体代表性或 enterprise-wide 外推。proposal 的“先做更广泛人群审查”在语义上合理，但本次正式记录没有接受任何路线。

本条只覆盖预先固定的 health010，不替代数据所有者判断，也不外推为 140 条正确率。

## 使用的证据与限制

本次只查看原图 `data/task_092/chart.jpeg`、公开任务、冻结的 proposal／generation／normalized／verification、规则状态和现有中文侧车。未读取或使用 health010 的 hidden gold、offline 机制标签或另一条件。

审阅者与运行模型同属一个家族，并处于同一批次上下文，不是跨模型盲审；此前代码审查也接触过离线元数据。因此下述结论不是盲审准确率评分，只以本条原图、公开任务和模型原文为证据。

## O／B／C 与竞争映射

- 原图可直接看到标题 `Selected Asthma Regions: PM2.5 Exposure vs ER Visits`、副标题 `Selected high-burden regions shown in dashboard summary`、两轴标题／递增刻度，以及 Region A 至 E 向右上方递进的五个红点。模型引用与原图一致。
- 图形规则的 O 包含完整的标题、轴、刻度和五点顺序，B 仅把屏幕方向解释为选定地区中的正向 plotted pattern；它没有声称因果关系，这一边界正确。
- 范围规则以“selected high-burden regions”为 O，并将缺少人群覆盖／代表性映射到“不能直接推进 enterprise-wide claim、可以做 broader population review”。这一规则处理的是外推边界，和图形解码互补。
- 但两条 normalized chain 的 `option_label` 完全相同，均为 broader-population-review。没有一条链为 enterprise-wide claim 或 background retention 提出可证伪的竞争条件。因此它们不是两条相互竞争的路由映射，而是同一路线的两个不完整组成部分。
- 范围链只引用副标题，却在 claim 中预设“positive pattern”；图形链证明 positive pattern，却没有提供 escalation 而非 retention 的路由桥。O／B 本身可读，C 在单链内均不充分。

## 核验充分性

- verifier 对范围链支持 O 和 B，但指出副标题本身没有证明该链 claim 中的正向图形，故 implication 为 refuted。
- verifier 对图形链支持 O 和 B，但指出该规则只能证明选定地区中的图形，不能说明为何应 escalation 而非 retention，也不能证明总体覆盖，故 implication 为 refuted。
- recommendation 为 `null`，unresolved_reason 准确指出没有任一单链同时提供图形证据与任务适用的路由桥；这不是已确认的 broader-review 结论。
- 两条 rule_state 虽均为 active，只代表其 B 在各自范围内得到支持；由于对应 implication 均为 refuted，不能把 active 规则数量展示成路线已经通过。
- generation 缺少真正竞争规则是生成质量限制，不等于原图没有正向模式，也不等于 proposal 的保守路线已被反证。正式可复述结果应停在 `null`／未决。

## 中文侧车

首次检查时 health010 的 81 个待译字符串中有 21 个尚未落盘；等待一轮后 81／81 均已有映射，自动数字检查无警告。抽查 proposal、两条规则、两条 claim、核验理由与 unresolved_reason，选定地区范围、正向图形、代表性限制、两条 implication 被反驳及 recommendation 未决的语义均被保留。

## 范围声明

本次没有修改原图、公开任务、运行记录、请求、响应、提示、配置或结果，没有重跑或发出新 API 请求。
