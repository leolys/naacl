# b011 generation invalid：离线故障归因

日期：2026-09-24  
审阅者：Codex，同家族／暂定（same-family / provisional）  
性质：开发期故障归因意见，不是数据所有者或人工金标准标签

## 结论

b011 的 `generation: invalid` 是当前表示接口／校验约束触发的真实终止状态，但不能据此断言模型没有理解图表。原始生成包含一条完整的条件式图例绑定、季度实体绑定、印刷数值比较及状态映射；它失败的直接原因是 `rule.text` 中出现了完整公开选项标签 `Select 'Decreased'`，命中了 `engine.py` 的字面子串禁令。

因此应同时保留两层事实：

1. 按当前冻结验证器，输出不符合“规则文本不得包含完整行动标签”的规范，结构拒绝和后续不执行是正确记录；
2. 该拒绝不等价于 O、B、C 的实质内容错误，更不等价于图表读取失败。

## 核对范围

本次只检查：

- b011 原图 `data/task_011/chart.jpeg` 与公开任务；
- generation 的原始 HTTP 200 响应、`parsed.json` 和冻结的 `generation_invalid_raw`；
- 固定 `GENERATOR` 契约；
- `engine.normalized_candidates` 的实际拒绝条件。

未读取或使用 b011 的 hidden gold、offline 机制标签或另一条件；没有修改代码、提示、配置、请求、响应或运行记录，也没有重新运行模型。

## 直接触发原因

`engine.py` 第 234—235 行对每个 `rule.text` 执行以下约束：只要文本为空，或任一完整公开 option label 作为不区分大小写的子串出现在文本中，就抛出 `ValueError("rule contains an action label instead of an interpretation")`。

b011 的公开标签有：

- `Select 'Decreased'`
- `Select 'Increased'`
- `Select 'No significant change'`

原始 `r1.text` 在条件关系末尾逐字包含 `Select 'Decreased'`，因此必然被拒绝；另两个标签没有出现。响应本身是可解析的完整 JSON，`finish_reason` 为 `stop`，所以这不是传输、截断或 JSON 解析故障。

## 固定提示与验证器的边界

固定 `GENERATOR` 要求 B 保存条件式解释桥梁，可包括必要的任务到行动关系；同时又要求不要把获胜实体或选定选项“作为规则本身”，并由独立的 `option_label` 字段承载最终选择。

原始规则确实越过了当前接口要求的严格分栏：它已经在 `option_label` 之外，又把完整行动标签写入 B。就这一表示契约而言，invalid 不是误记。

不过，验证器使用的是纯字面条件，而不是判断规则是否“只有行动标签”或是否仍含有实质解释。错误消息中的 “instead of an interpretation” 对此样本过强：该规则不是用标签替代解释，而是在完整解释末尾附加了标签。字面检查无法区分“行动标签充当整条规则”与“条件式图表解释中顺带引用行动标签”。这说明拒绝点属于严格的字段／归一化约束，不足以单独诊断图表推理能力。

## 原始 O／B／C 的实质内容

- O：原图可见蓝色色块图例 `Store Visits (Count)`；Q3 蓝色段内印有 `7940`，Q4 蓝色段内印有 `5121`。这些是直接文字、颜色、位置和实体绑定，没有把增减结论偷渡进 O。
- B：规则条件式地绑定蓝色图例与各季度蓝色段，把段内白色数字解释为同一 Store Visits 指标，并规定比较 Q3 与 Q4、较低 Q4 映射为 decreased 状态。除末尾嵌入完整 UI 标签这一表示问题外，它包含所需的图例绑定、可比性、数值比较和状态映射，不是一个裸答案。
- C：claim 在上述绑定下比较 `5,121 < 7,940`，得出 Q4 相对 Q3 decreased，并把结果映射到公开的 decreased 选项。该算术方向与原图可见数字一致。
- 单链本身不构成故障：固定提示要求包含提案所需论证，并允许“至多”两个竞争解释，也明确禁止为了形式强行制造相反答案。

## 应如何解释冻结状态

- `generation_invalid_raw` 应继续完整展示，供人区分内容与接口失败。
- `generated`、`normalized` 和 `verification` 均为 `null`，`rule_state` 为空；不存在已接受的生成链、核验 verdict 或规则状态。
- 因此不能把上述离线语义检查改写成正式模型核验通过，也不能声称下游 staffing plan 已完成。公开任务还列有必填 `staffing_adjustment` 字段，但这不是本次 generation 被拒绝的直接原因。
- 本文只解释失败性质，不修复输出、不建议重采样，也不改变 b011 作为终止 invalid 样本的计数。

## 审阅限制

这是同家族、同一批次上下文中的离线复核，不是跨模型盲审，也不能估计全部 140 条材料的错误率。

