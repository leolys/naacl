# pub020 离线语义抽查

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期语义意见，不是数据所有者或人工金标准标签

## 结论

pub020 的原图确实同时提供两套冲突的候选编码：直接印出的百分比以 Service Design 的 `51%` 为最大；点在 `Value` 纵轴上的高度则把 Service Quality 与 Other 并列在约 60 的最高位置，而 Service Design 仅约 22。generation 对两套解释分别建链，属于真正竞争映射；verifier 没有擅自决定哪套表示权威，最终 `recommendation: null`、两条规则均 pending，是与公开材料一致的保守结果。

proposal 只按百分比选择 Service Design，未在 brief_basis 中披露点高冲突。该选择可作为“百分比文字代表 feedback share”条件下的结论，但不是冻结核验已经接受的无条件路线。反向的 Service Quality 路线同样不能直接接受：除权威性未定外，Other 与 Quality 在最高点位并列，点高无法确立 Quality 是完整任务的唯一最高类别。

本条只覆盖预先固定的 pub020，不替代数据所有者判断，也不外推为 140 条正确率。

## 使用的证据与限制

本次只查看原图 `data/task_121/chart.jpeg`、公开任务、冻结的 proposal／generation／normalized／verification、规则状态和现有中文侧车。未读取或使用 pub020 的 hidden gold、offline 机制标签或另一条件。

审阅者与运行模型同属一个家族，并处于同一批次上下文，不是跨模型盲审；此前代码审查也接触过离线元数据。因此下述结论不是盲审准确率评分，只以本条原图、公开任务和模型原文为证据。

## O／B／C 与竞争映射

- 原图标题为 `Public Service Feedback Share by Category`，纵轴只标 `Value`。六个百分比文字分别为 Service Quality 41%、Service Cost 46%、Service Design 51%、Support Access 42%、Service Delivery 36%、Other 10%；这些文字与点高明显不一致。
- 百分比链的 O 完整引用标题、类别绑定及六个字面百分比；B 条件式规定百分比文字而非点高是 feedback share；C 因 51% 最大而路由 Service Design。O 未把权威性假设偷渡成可见事实。
- 点高链的 O 引用 `Value` 轴、Quality 相对 Design／Delivery 的高度及 41%／51% 冲突；B 条件式规定纵向位置才编码 share；C 指向 Service Quality。它与百分比链在证据来源、规则条件和选项上均不同，是真正竞争路线。
- proposal 的数字抄录本身准确，但仅陈述百分比次序，没有说明原图还存在相反的几何编码，因此其肯定选择比正式核验更强。

## 核验充分性

- verifier 对两条链的 O 均判 supported，重新核对了六个百分比、纵轴、点位和 Quality／Other 并列事实。
- 点高链的 B 为 undetermined，因为图中没有说明 `Value` 点高而非百分比才是 feedback share；implication 为 refuted，因为 Quality 与 Other 在最高点位并列，不能推出唯一 Quality 路线。
- 百分比链的 B 同样为 undetermined：标题中的 `Feedback Share` 与百分号支持这一解释，但同一图中存在冲突的 `Value` 轴点位且没有权威性说明。verifier 将 implication 保留为条件式 supported，即若百分比是 share，则 Design 51% 可完成该选择；这不等于无条件接受 B。
- recommendation 为 `null`，unresolved_reason 准确陈述两套编码冲突；两条 rule_state 均为 pending。展示时不能只引用 proposal 或其中一条 conditional implication 而省略这一正式未决状态。

## 中文侧车

首次检查时 pub020 的 135 个待译字符串中有 110 个尚未落盘；等待两轮后 135／135 均已有映射，自动数字检查无警告。抽查 proposal、两条规则与 conditions、两条 claim、核验理由和 unresolved_reason，51%、46%、42%、41%、36%、10%、Quality／Other 并列、两项 B undetermined、Quality implication refuted 及 recommendation 未决均被保留。

## 范围声明

本次没有修改原图、公开任务、运行记录、请求、响应、提示、配置或结果，没有重跑或发出新 API 请求。
