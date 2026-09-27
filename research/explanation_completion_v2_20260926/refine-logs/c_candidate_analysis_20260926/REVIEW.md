结论：方向正确，但仅改 C 文案还不够；现有提示词和方法正文仍有 4 处真实边界冲突。审查属性：`same-family / provisional`；本次无实现、无 API、无实验，不声称效果提升。

1. 生成阶段仍在提前核验。
[prompts.py:25](D:/ths_Viswork/research/explanation_completion_v2_20260926/prompts.py:25)–[28](D:/ths_Viswork/research/explanation_completion_v2_20260926/prompts.py:28) 要生成器判断缺口、提醒“不证明 P 不等于证明非 P”及全局最大值完整性；[prompts.py:64](D:/ths_Viswork/research/explanation_completion_v2_20260926/prompts.py:64)、[69](D:/ths_Viswork/research/explanation_completion_v2_20260926/prompts.py:69)、[101](D:/ths_Viswork/research/explanation_completion_v2_20260926/prompts.py:101)–[104](D:/ths_Viswork/research/explanation_completion_v2_20260926/prompts.py:104) 又允许 `underdetermined`、`claim or gap`、`support_gap` 成为链内容。这会让 C 继续承担 verdict，而不是候选结论。应把这些提醒全部移到 VERIFY；COMMON 仅保留共享词汇、O/B/C 边界和数据完整性。

2. 方法正文也需同步一小处，否则提示词与论文定义不一致。
[METHOD_SOURCE.md:92](D:/ths_Viswork/research/competing_rules_20260923/METHOD_SOURCE.md:92) 允许把“解释缺口”当当前链，[100–102](D:/ths_Viswork/research/competing_rules_20260923/METHOD_SOURCE.md:100) 把“是否足以支持”放入反问生成，[123](D:/ths_Viswork/research/competing_rules_20260923/METHOD_SOURCE.md:123) 又说竞争模块可返回支持不足。这些应改为：反问只检查“是否遗漏另一种具体、可测试的 O-B-C 阅读”；证据是否支持 B、推导是否充分由 3.3 核验。若确实无链可构造，记录链外 unresolved question。

3. 放宽 B 的预先证实时，必须补上防止任意构造的约束。
允许错误但可测试的 B 是对的，但 B 必须针对实际出现的编码组件、绑定关系或任务桥接，且与 O 独立可陈述；禁止“假设目标答案正确”“假设 X 最大，所以选 X”及 C 的同义改写。O 仍只能是实际可见内容；不确定的轴向、颜色含义、标签绑定等放进 B。这里的“有可见/公开动机”只约束为何值得提出该阅读，不等于 B 已被图表证实。

4. 最小结构联动不可省略。
当前旧验证器明确要求初始 `rules/chains` 非空，并把 `claim_kind`、`support_gap` 写入语义约束。因此后续实现至少需要：

- 新输出不再使用 `claim_kind=underdetermined`；最好完全删除 `claim_kind`，由自然语言 C、`option_label` 和可选候选关系表达内容。
- `relationship` 删除 `support_gap`，仅描述候选间 `compatible|competing`。
- 若保留 `proposal_relation`，把 `supports|refutes` 改成非核验式名称，如 `same_action|rejects_action|alternative_action|not_addressed`。
- 初始生成允许 `chains=[]`，但此时必须有有界的链外 `unresolved_questions`；补充阶段已有 `question_responses.outcome=unresolved`，无需伪造新链。
- 保留真正的 `refinements`；不能把每个问题都映射成额外链。
- 旧工件中的 `claim_kind` 可作为惰性兼容元数据读取，但新生成不再要求或默认补写。相应更新导入验证器、补充验证器和针对零链/未解决问题的测试即可，无需扩大状态模式。

关于“是否总要更多链”：当前“至多、可为零”的文字基本正确；真正的冲突是 GENERATOR 仍要求包含当前提议的条件论证，而底层又禁止空初始集。修掉这两点即可，不需新增链数目标。

建议的中文 C 约束如下：

:::writing{variant="standard" id="38417"}
对每条候选解释，C 必须是在采用该链明示的 B 假设后，由 O 与 B 推出的具体任务结论。C 应明确写出实体、比较对象、方向或行动以及适用范围，可以是肯定、否定或比较结论；即使该候选随后会因 B 不适用于当前图表而被拒绝，也仍须陈述它自身的具体结论。

生成阶段不判断 B 是否已被当前图表证实，不把“证据不足”“未确定”“缺少支持”写成 C，也不把未证实 P 解释为非 P。B 可以是尚待核验、甚至最终错误的解释假设，但必须对应实际可见的编码组件、实体绑定或公开任务桥接，并能被后续核验；不得写成“假设期望答案正确”、直接重述 C，或加入图中不存在的事实。O 只记录实际可见内容；不确定的编码含义写入 B。

若根据可访问的观察无法形成任何连贯、具体且可测试的 O-B-C 候选，不生成伪造的缺口链；在 chains 之外记录一条有界的 unresolved question。
:::
