# Stage 2.5 下一步决策

## 当前判断

**当前源码已有完整真实模型链路证据，但还不应直接启动 12-task pilot，也没有证据支持立即开发决策相关视觉观察选择机制。**

fresh run `stage25_live_smoke_20260906T1515Z` 使用 GPU 0 上本地 Qwen3-VL-8B-Instruct，完成 4/4 checkpoint、16/16 replay/POST/confirmation；严格 validator 为 `valid=true, errors=[], warnings=[]`。主 grid 为 33 次真实模型调用、96 次浏览器 transition；加单列控制后共 38/160 个计费调用事件、36 次真实模型 HTTP completion、96/800 transitions。运行后服务关闭、GPU 释放。

四个自然 checkpoint 中，按数据集 scorer 有 1 个错、3 个对：

- 错：`env001/official140`；完整图表重读＋目标语义核查、通用主动视觉核验、模型自行提取＋普通 Agent 都没有改选，数据集口径是 0/3 recovery attempts；
- 对：`env001/clean140`、`env025/official140`、`env025/clean140`；三种核查共 9/9 保持正确；
- 通用主动视觉核验 4/4 返回合法决定，但 0 次请求 crop、0 次自然改选；
- 四种配置都为 3/4 终局成功，相对原样继续的差值为 0 个百分点。

这些数字不能解释为方法 recovery rate。`env001` 的公开规则没有定义“large enough”的阈值，已在运行前归为 `engineering_only`；规则合格的 `env025` 两个 arm 又都没有原始错误。因此研究资格口径仍是 **0 个无歧义错误 checkpoint**。

## 现有观察能定位到哪里

当前能定位两项残余，但都还不是“看哪里”的证据：

1. `env001/official140` 中，完整重读准确说出 23.9°C 到 10.1°C；模型自行提取也得到完整数值序列，但仍把它映射为 ordinary variation。clean arm 的近似同值序列则被映射为 substantial change。这里混有视觉 framing、未定义阈值和当前选择锚定，不能单独归因给视觉区域选择。
2. `env025/official140` 中，模型最终动作正确，但完整重读和通用主动核验都错误声称 January 柱高于误导 Average 线。终局 action score 会掩盖理由所依据的视觉事实错误。
3. 单列控制中，注入两次 crop 后的 2→3→4 累计多图传输成功，排除了工具通道完全不可用；但另一个自然改选控制出现 reason 明确要求 Route B、顶层 `option_label` 仍为 Route A，表明结构化 action binding 可以独立失败。注入 crop 不代表模型会自主选择观察区域。

因此，“普通重读已经足够”没有得到支持；“普通重读一定不够、必须开发新观察选择器”也没有得到支持。通用主动核验从未实际使用 crop，无法判断它是无需观察、不会选择区域、受原选择锚定，还是其他规则遵循问题。

## 是否具备进入约 12-task pilot 的条件

工程链条件已经满足：当前源码、配置、预算持久化、请求响应、状态/截图复算、真实 POST 和信息隔离均有本次真实 run 证据；早期 env025 label/name 阻断也未再出现。

正式 pilot 设计条件尚未全部满足：

1. 需要从 `TASK_ELIGIBILITY.csv` 的 13 个合格候选中按近重复家族 materialize development/diagnostic/formal holdout；不能把近重复任务当独立现象。
2. 需要用与 gold 无关的外部固定 seed 实现共享 option permutation，并加入 position-only/no-image diagnostic。
3. 若论文主张覆盖 GUI Agent 回溯/纠错方法，需要先实现普通反思 B1 和来源明确的 GUI target-level recovery B5；没有 B5 时只能声称比较简单核查基线。
4. 需要先在明确规则任务上产生多个自然错误 checkpoint。优先开发任务仍是 `pub010`、`env008`、`b035`，因为其趋势方向或最大类别到动作的映射公开、无需隐藏阈值。
5. pilot 的运行单元与调用预算必须单独申请；本次 16-unit 授权已用完，不能以 160/800 尚有余量追加运行。

所以当前判断是：**可以停止工程 smoke，进入“冻结 pilot 设计与最小适配”的下一执行单；尚不能直接开跑 12-task × 多配置矩阵。**

## 下一执行单的最小范围

下一单应只完成：

- 固定按近重复家族分组的任务表和开发/留出身份；
- 实现 gold-independent shared option permutation 及 position-only/no-image 诊断；
- 在不加入误导 taxonomy、gold、另一 arm 或 evaluator 框的前提下，适配普通反思 B1；
- 核实 B5 的开源来源和可执行接口；若只能按论文思想实现，明确命名为 `inspired adapter`；
- 先用 `pub010`、`env008`、`b035` 做一个单独获批的小型自然-prefix qualification，确认存在无歧义错误 checkpoint，再决定约 12-task pilot 的完整预算。

只有在多个无歧义任务中，普通重读、通用主动视觉核验和自行提取仍留下非接口造成的残余失败，并且给定正确视觉事实/正确 action 的诊断把瓶颈定位到观察选择时，才开发决策相关视觉观察选择机制。

## 停止点

Stage 2.5 已完成并停止。没有启动完整 pilot、140 对评测、B1/B5 适配、超出执行单的其他控制或新机制。详细结果见 `revisions/20260906T1515Z/STAGE_REPORT.md`。
