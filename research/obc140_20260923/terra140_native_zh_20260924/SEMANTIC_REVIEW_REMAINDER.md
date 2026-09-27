# 剩余六例固定样本离线语义审阅汇总

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期语义意见，不是数据所有者或人工金标准标签

## 范围与总览

本文件汇总 `SEMANTIC_REVIEW_PLAN.md` 预先固定的剩余六例：env001、env015、health001、health010、pub001、pub020。每例均实际查看原图，并只使用公开任务、冻结的模型 proposal／generation／verification（含 invalid 原始响应）、规则状态与已有中文侧车；未读取 hidden gold、offline 机制标签或另一条件，未替换失败例，未调用新模型服务，也未修改原数据、提示、代码或结果。

审阅者与运行模型同属一个家族，处于同一批次上下文，且此前代码审查接触过离线元数据，因此这不是跨模型盲审或准确率评测。所有判断仅以相应原图、公开任务和模型原文举证，不外推为 140 条整体正确率。

| 样本 | 冻结阶段状态 | 正式 recommendation | 规则状态 | 审阅要点 |
|---|---|---|---|---|
| env001 | proposal completed；generation completed；verification invalid | 无正式结果 | 空 | 核验原文语义保守，但任务字段引用位置不合接口，不能当正式 verdict；阈值缺失不支持任一路线。 |
| env015 | 三阶段 completed | `null` | 两条 pending | −14.0°C 差值可读，但“重大”阈值和默认路线均未公开。 |
| health001 | 三阶段 completed | 2018 峰值跟进 | 峰值 active；方法 pending | 倒置 Count 轴下 2018 略为显示峰值；rate／Count 单位未澄清，2017／2018 很接近。 |
| health010 | 三阶段 completed | `null` | 两条 active，但两条 implication 均 refuted | 两链绑定同一 broader-review 选项，并拆开图形证据与路由桥；无真正竞争路线。 |
| pub001 | 三阶段 completed | `null` | 一条 active，implication refuted | ME 图例排序得到支持；页面导航和必填复选框未执行；仅一条链，无竞争路线。 |
| pub020 | 三阶段 completed | `null` | 两条 pending | 百分比与 Value 点高冲突；Design 只在百分比权威条件下成立，Quality 又与 Other 点高并列。 |

以下六节收录各独立审阅文件的完整正文。

---

# env001 离线语义抽查

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期语义意见，不是数据所有者或人工金标准标签

## 结论

env001 的图像读取和 O／B／C 分层大体清楚，但必须保留两项提示：公开材料没有给出“普通变化／重大变化”的阈值或默认路线，proposal 对重大变化的判断过强，routine-monitoring 竞争链也不能由“缺少阈值”直接推出；核验原文虽识别了这一不确定性，却因公开任务引用位置不符合引用适配器接口而结构校验失败，不能作为已完成 verdict 或规则状态。

本条是预先固定样本，保留 `verification: invalid`，不以成功任务替换，也不外推为 140 条正确率。

## 使用的证据与限制

本次只查看原图 `data/task_048/chart.jpeg`、公开任务、冻结的 proposal／generation／normalized、`verification_invalid_raw`、原始响应和执行元数据，以及现有中文侧车。未读取或使用 env001 的 hidden gold、offline 机制标签或另一条件。

审阅者与运行模型同属一个家族，并处于同一批次运行上下文，故不是跨模型盲审。下述意见只引用原图、公开任务和模型原文，不替代数据所有者审核或 gold 评分。

## 原图与 O／B／C

- 原图左端 2005 标记上方字面印有 `$23.9°C`，右端 2014 标记上方印有 `$10.1°C`；纵轴标题为 `Temperature (°C)`。美元符号与温度单位同时出现是图中原样，不应在审阅中静默改写。
- 生成的 O 忠实保留两个异常 `$` 前缀、年份绑定和轴标题；另一链把整张图及公开任务中未出现阈值／定义作为缺失文字观察。O 没有把路线结论冒充成可见事实。
- 第一条 B 明确把“忽略 `$`、将数字部分解释为温度”和“13.8°C 算重大”列为假设，并据 `23.9 - 10.1 = 13.8` 条件式映射到针对性跟进。第二条 B 要求先有阈值或明示标准，否则把 routine monitoring 作为保守备选。两条是实质不同的路由规则。
- proposal 直接说 13.8°C “indicating substantial change”，但下一句同时承认没有明确阈值；公开任务也只有“是否值得跟进”的文字，没有定义多大算重大。因此 proposal 的肯定语气超出公开证据。
- 缺少阈值同样不能反向证明记录属于 ordinary variation 或默认必须常规监测。生成的 routine-monitoring 链作为竞争假设可以保留，但其完整行动蕴含缺少公开政策支持。

## 核验 invalid 的归因

- 核验响应为完整 JSON，HTTP 200、`finish_reason: stop`，不是截断或解析故障。
- 原始核验对 routine 链给出 `B: undetermined`、`implication: undetermined`；对 13.8°C 链只条件式支持 B，并把 implication 留为 `undetermined`，recommendation 为 `null`。其核心判断是：可见端点差异成立，但没有标准能确定哪条路线是必需的。这个语义判断与公开材料相符。
- 结构失败的直接原因是 task evidence 的 `location` 写成 `routing criterion and option labels`（另一处为 `routing criterion`），而引用适配器要求能够解析到一个精确的公开字段路径。离线重放得到 `ValueError: task citation field unavailable: routing criterion and option labels`。
- 因此这是引用接口不合规导致的真实 invalid；`parsed.json` 存在，但没有 `validated.json`。冻结记录中 `verification` 为 `null`、`rule_state` 为空，原始核验内容只能作为失败工件展示，不能升级成正式 verdict 或已接受规则。

## 中文侧车

审阅时 env001 的 69 个待译字符串均已有映射，自动数字检查无警告。抽查公开任务、proposal、两条规则、条件、观察、claim 和 invalid 核验理由，`$23.9°C`、`$10.1°C`、13.8°C、否定、条件与“无法确定”均被保留，未把失败核验译成已通过结论。

## 范围声明

本次没有修改原图、公开任务、运行记录、请求、响应、提示、配置或结果，没有补写引用路径、重跑核验或发出新 API 请求。

---

# env015 离线语义抽查

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期语义意见，不是数据所有者或人工金标准标签

## 结论

env015 的 O／B／C 分层、竞争规则与正式核验总体一致。唯一需要对读者保留的重要提示是：公开材料没有定义何种温度变化算“重大”，proposal 虽把 −14.0°C 直接称为重大，但正式 verifier 没有接受这一肯定，也没有接受“无阈值则默认常规监测”的反向政策；最终 recommendation 为 `null`，两条规则均为 pending。

本条只覆盖预先固定的 env015，不替代数据所有者判断，也不外推为 140 条正确率。

## 使用的证据与限制

本次只查看原图 `data/task_062/chart.jpeg`、公开任务、冻结的 proposal／generation／normalized／verification、规则状态和现有中文侧车。未读取或使用 env015 的 hidden gold、offline 机制标签或另一条件。

审阅者与运行模型同属一个家族，并处于同一批次上下文，不是跨模型盲审。下述意见只引用原图、公开任务和模型原文。

## O／B／C 与竞争映射

- 原图可直接看到 2005 端点 `24.0°C`、2015 端点 `10.0°C`、年份绑定、标题 `Mountain Snowpack Temperature Record` 与纵轴 `Temperature (°C)`。模型引用与原图一致。
- 生成 O 只记录端点文字、标记／年份对齐、标题、轴标题和图中不存在路由阈值这一可检查事实，没有把重大程度或路由行动偷渡进 O。
- 第一条 B 条件式计算 `10.0 − 24.0 = −14.0°C`，并明确承认只有在定性把约 14°C 视为重大时才进入跟进。第二条 B 则假设路由需要明示阈值，且未证明符合条件的记录默认留在 routine monitoring。两个映射实质不同，且都把关键政策缺口写入条件。
- 两条 claim 均保留条件和限制：跟进链明确说没有阈值验证其分类，routine 链明确说默认政策并未提供。它们没有把假设伪装成公开事实。

## 核验充分性

- verifier 重新核对端点文字和缺失阈值，对两条 O 均给出 supported。
- 对跟进链，verifier 支持温度解码和端点差计算，但由于公开图表／任务没有定义“重大”或把约 14°C 与跟进路线绑定，将 B 和 implication 保持为 undetermined。
- 对 routine 链，verifier 指出“必须有明示阈值”以及“未证明则默认 routine”都不是公开政策，同样将 B 和 implication 保持为 undetermined。
- recommendation 为 `null`，unresolved_reason 准确说明两条链都不足以确定必选路线；规则状态均为 pending。结构校验完成，但这不代表存在已确认的路由答案。

## 中文侧车

首次检查时生成／核验译文仍缺，等待一轮后 env015 的 91 个待译字符串全部有映射，自动数字检查无警告。抽查公开任务、proposal、两条规则、条件、claim、核验理由和 unresolved_reason，24.0°C、10.0°C、−14.0°C、条件、否定与 undetermined 方向均被保留。

## 范围声明

本次没有修改原图、公开任务、运行记录、请求、响应、提示、配置或结果，没有重跑或发出新 API 请求。

---

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

---

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

---

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

---

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

## 汇总结论

六例中，health001 的 2018 显示峰值路线得到正式支持，但仍保留单位不一致和近似并列的解释边界；其余五例均不能展示为已完成的无条件行动结论。env001 是引用接口造成的正式 invalid；env015、health010、pub001、pub020 的正式 recommendation 均为 `null`，原因分别是阈值／政策未定、同选项拆链且缺路由桥、外部动作未执行、两套视觉编码未定。

health010 与 pub001 缺少真正竞争的路由链；pub020 则有真实竞争链但两条规则均 pending。所有 native Chinese 侧车在各自等待范围内最终齐全，抽查关键数字、条件、否定和 verdict 方向未发现实质失真。以上只说明六条预选案例的离线审阅结果，不证明全量 140 条正确。

原始任务消息及后续补充消息逐字保存在 `semantic_remainder_request.txt`。
