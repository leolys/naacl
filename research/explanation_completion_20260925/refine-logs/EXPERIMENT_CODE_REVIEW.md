## CODE_REVIEW

结论：**PASS，0 个 BLOCKING。** 当前实现满足固定三例真实运行的代码门槛。本审查为同族 Codex 对抗审查，属于暂定工程判断，不是人工语义真值审核。

已确认：

- [runner.py](D:/ths_Viswork/research/explanation_completion_20260925/runner.py:47) 直接读取完整原始 generation 集合，不读取 proposal、gold 或旧 verifier；b002 两条初始链均保留。
- [core.py](D:/ths_Viswork/research/explanation_completion_20260925/core.py:115) 保持原始规则、链及顺序，不再排序重编号；新增、细化、已有覆盖和未解决均有原生接口。
- 图像观察与公共任务引用分离；非行动链必须使用 `option_label: null`。
- [core.py](D:/ths_Viswork/research/explanation_completion_20260925/core.py:264) 分别核验 O、B、implication；规则状态只聚合 B，因此观察错误不会自动撤销规则，B 有效也不会自动证明 C 或行动成立。
- 规则状态带任务、具体图像、组件、条件和版本范围；细化记录不会静默改写原规则，保存后执行重载一致性检查。
- [runner.py](D:/ths_Viswork/research/explanation_completion_20260925/runner.py:94) 冻结三例、最多 12 次请求尝试和 2 美元估算账本；每次网络尝试在发送前记账，失败与重试均计入。
- 无问题时跳过 supplement 调用，并明确标记为确定性空结果，因此正常调用数是最多 9 次而非强制 9 次。
- 已修复模拟运行冒充真实运行的问题：[runner.py](D:/ths_Viswork/research/explanation_completion_20260925/runner.py:140) 将非默认 API 工厂标记为 `mock`、`offline_fixture`、`mock_completed`；对应反向测试覆盖。
- 最终离线回归：**33 passed，3 条继承依赖的 DeprecationWarning**。
- `prepared_final` 门槛核验：0 次调用、b002 两条初始链、冻结运行源全部未变。

剩余 NON-BLOCKING：

1. `relationship="competing"` 没有结构化强制 discriminator；当前逐链 O/B/implication 核验仍足够支撑本轮流程。若论文强调显式区分检查，应作为输出限制说明，不建议为此中断当前固定运行。
2. `unresolved` 可以同时引用部分已有覆盖链。报告必须仍按“整体未解决”处理，不能计为新增、完全覆盖或穷尽证明。
3. 2 美元是本地估算账本边界，不是提供商发票保证；配置和工件已正确披露。
4. mock、结构验证及本次同族审查都不证明模型视觉判断正确；真实输出仍需后续人工语义审阅。
