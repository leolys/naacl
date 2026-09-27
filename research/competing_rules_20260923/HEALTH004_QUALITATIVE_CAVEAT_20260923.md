# health004 补充运行：核验依据的限定

这是对已保存的 `runs/health004_format_supplement_20260923/case03_competing_persistent` 的只读事后分析。未调用模型或浏览器，未修改候选、核验、状态、评分或执行记录。结论是：**数值趋势读取有独立图内依据，但本次“排除另一规则”的理由存在用生成规则证明自身的循环，以及证据来源混写，不能作为可靠独立规则核验的成功例。**

实际图中纵轴数字向下增大，起止点约为每千人 1.3 与 2.4 名医生，支持“数值增长”。公开任务要求选择最符合期末容量模式的后续路径；页面给出人口相对医生容量的监测目标，公开选项包括扩容、短缺响应和一般统计页。**页面没有显式的“增长即进入扩容路径”规则，也没有 `r2` 文字。** 这些可由[实际页面截图](runs/health004_format_supplement_20260923/case03_competing_persistent/browser/002_actor_input_00.png)、[公开任务](data/case03/public.json)和[核验实际输入](runs/health004_format_supplement_20260923/case03_competing_persistent/step_00/defense/verify/context.json)复核。

| 对象 | 实际来源与可以支持的结论 |
|---|---|
| 反向轴、约 1.3→2.4 | 图像可直接检查；支持数值增长，不是精确原始序列的恢复。 |
| `r2`：增长表示人口相对医生容量增加，并支持扩容后续解释 | 来自模型生成的候选规则。前半与指标定义一致；后半可结合公开任务及选项语义作“最匹配”的推断，但不是页面明文给出的政策或阈值。 |
| `r1`：缺少任务定义的趋势—路径映射时，图表不能确定唯一路径 | 也是待评估候选。即使不接受它推出一般统计页，也须依据任务语义检查推导，不能用另一候选存在来否定“任务未显式定义映射”。 |

具体问题出现在[实际核验](runs/health004_format_supplement_20260923/case03_competing_persistent/step_00/defense/validated_verification.json)：c1 将 `r2` 判为 supported，理由依赖 “the supplied rule explicitly maps”；c2 将 `r1` 判为 refuted，理由是 “because r2 supplies such a rule”。同时 c2 的 `page_00` 证据条目把页面确有的任务背景，与“生成的 r2 明确连接该路径”合写。**候选规则被提供给核验器，不等于公开任务已定义或证实该规则；观察标识真实，也不保证该条证据的每个断言来自该观察。** `validated_verification` 在这里表明通过接口校验，不能替代语义独立性审查。

这不说明最终扩容选择错误，也不证明一般统计页应当正确。扩容是对增长模式与选项含义的合理解释；问题是本次记录没有用独立的任务语义论证完成那一步，而借用了候选自身。应把“图内读取正确”“路由解释合理”“该次核验的反驳理由不充分”分别报告，保持原 gold 和实际结果。

[状态记录](runs/health004_format_supplement_20260923/case03_competing_persistent/step_00/defense/rule_state.json)确实将 `m1` 首次写为 revoked、`m2` 写为 active，后续 actor [引用了 m2](runs/health004_format_supplement_20260923/case03_competing_persistent/step_01/actor/parsed.json)。这证明状态写入和读取发生，但也把上述薄弱依据带入状态。`m1` 是从未入库直接变为 revoked 的候选，不是此前已确认规则被新证据推翻。另一个反向轴映射规则虽在生成输出中出现，却未被任何链引用，规范化后未保存；因此本例实际持久化的是路由解释，不是独立的轴映射规则。

建议在演示说明中保留这一局限，并在后续全量分析中单列“候选内容被当成外部证据”的核验可靠性问题。本记录不要求重跑、改提示、补写有利论证或新增实验门槛，也不改变已有固定任务选择。
