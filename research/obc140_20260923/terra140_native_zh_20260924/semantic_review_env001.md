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

