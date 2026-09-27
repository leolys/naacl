# 请求级有界重试：实现与工程验证

用户本次允许处理网关并发不稳定时的重试。此改动只属于请求可靠性层，不是视觉核查策略、新的 Agent 框架或任务重抽机制。旧配置默认仍为零重试；新执行可显式加 `--retry-policy research/prospective_simple_check_pilot/retry_reliability_20260907_v1/RETRY_POLICY.json`，该文件只能覆盖四个重试参数，不能变更模型、端点或预算。

## 固定规则

- 同一逻辑模型请求最多首次 + 3 次重试，总计 4 次 HTTP 尝试。等待约 10 / 20 / 40 秒，各加 0–3 秒随机延迟；并发仍为 1。
- 仅 HTTP 408 / 429 / 500 / 502 / 503 / 504，以及 ConnectionError / Timeout 可重试。SSL 验证错误不重试；明确 insufficient_quota 等额度/鉴权错误也不重试。
- Retry-After 支持秒数和 HTTP 日期；等待不会早于有效提示。若服务器要求等待超过 60 秒，本次有界处理停止并记录，不擅自将它缩短到 60 秒重发。
- HTTP 200 的有效、错误判断、格式错误、拒绝、截断或空输出都不是运输层重试依据；不通过多次采样挑更好的动作。下游原有解析行为不在本次改动范围。
- 一个请求的消息、模型参数和所有图像字节先序列化一次；重试只重发同一内容，不重新截图、不添加错误反馈、不换模型或另一个 arm。

Retry-After 的格式来自 [RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)；429 可携带 Retry-After，但不保证它一定出现，见 [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)。本项目的次数、延迟和失败白名单是本轮工程选择，不是 RFC 要求。

## 预算与结果口径

每次物理 HTTP 尝试分别预留费用、保存请求/结果；第一次由 RecordedModel 计入共享模型调用账本，额外尝试经同一 ModelBudget callback 计数。全局每模型 400 次、控制 16 / 主面板 384 次和原金额上限仍包含重试，不给额外免费预算。未知计费（尤其读超时可能已生成）保留整笔预留；不能保证生成只计费一次。

原前缀 12、核验 1 / 3、actor 续跑 4 等循环上限仍限制**逻辑请求**；本次用户允许的运输层重试是同一逻辑请求的额外物理尝试，全部进入共享次数与费用限额。这是明确的可靠性协议修订，不能与旧“每次仅一个 HTTP 尝试”版本混称相同协议。各模型/策略的请求、原始推荐、落实选择和真正提交三层不变。

模型回复只有最终收到的一份交给 actor/策略。成功回复的 metadata 包含 transport_attempt_count 和 transport_attempts；api_wire 中每次尝试都有独立 call 目录及费用条目。汇总发现未知的中间尝试用量时，usage_complete 不再写 true。统计物理成本用 budget / api_spend，不把逻辑 response 文件数当总调用数。

## 连续失败的兜底与旧面板边界

重试用尽、服务器要求长等待或预算不足时保存 transport_stop.json，保留完整原请求、每次尝试、有限的脱敏 HTTP 状态 / Retry-After / request ID / error code，然后停止。默认不保存原始错误体、鉴权头或异常消息；不能从未保存的字段猜测上游原因。

本模块没有浏览器执行权限，不能重复业务 POST。只有最终成功返回的模型提议能进入原 before-submit hook 与公共执行器；实际提交仍 max_attempts=1。

**本次不从头重跑已中断的 8 任务面板。** 旧 live_panel_02 已有 9 条完成轨迹和第 4 条中断前缀，不能通过仅支持控制阶段承接的旧路径重新执行。当前保存的是可供恢复的请求与公开状态证据，不宣称已经实现进程重启后的完整面板自动恢复。下一次续跑应重建同一中断公开状态、复用真实历史、承接旧消耗后才重试该请求；已完成前缀/提交不得重跑。

## 本次验证

最终版本通过 **92 项单元/回归测试**（19 项新增 retry 测试 + 73 项既有测试），见 [unit_tests_after_review.log](unit_tests_after_review.log)。审查前 91 项测试日志也保留，不覆盖。

非图表浏览器正控制两次各通过：模拟第一次生成请求返回 429，第二次返回 Submit Form 提议；同一逻辑请求计入 2 次 mock 尝试，随后只产生 **1 次真实 localhost 业务 POST** 和确认页。最终版本见 [browser_probe_02/result.json](browser_probe_02/result.json)，该目录保留实际请求、图像、执行回执和运行时源拷贝。等待用可注入函数记录为 10 秒，不进行真实网络等待；这不是对实际网关负载、计费或重试成功率的测量。

只读 CLI 准备检查能够载入 retry policy，未设置 MODEL_API_KEY，结果为 local_readiness_only / credential missing / 0 网络请求。没有用真实密钥启动推理。

命令见 [COMMANDS.md](COMMANDS.md)，一次有界的已有 sub-agent 审查及处理见 [CODE_REVIEW.md](CODE_REVIEW.md)。未新增大型门禁或重复审查到 PASS。原已执行源保留；首批差异为 SOURCE_CHANGES.patch，审查后小修为 REVIEW_FIX.patch，最终源码以 browser_probe_02/executed_sources 为本次执行证据。

本次两个浏览器控制合计新增 10 次实际 transition、4 次模拟生成尝试、2 次本地提交；真实模型/API 调用 0、GPU 使用 0、API 费用增量 0。沿原预算口径，旧 231 + 本次 10 = 241 次实际浏览器 transition；未来接续不得漏计，见 [COSTS_ADDENDUM.json](COSTS_ADDENDUM.json)。mock / 本地浏览器正控制不是图表能力或真实网关可靠性结果。不改变原图、原任务、gold 或旧实验结果。

## 已知边界

- 非标准错误体或尚未识别的供应商额度码可能仍按 429/5xx 重试，但不超过次数/金额限制；只声称识别列明的 error.type/code，不声称识别全部供应商永久错误。
- 金额/接口次数不足在等待前停止；共享模型次数 callback 仍在下次派发前检查，因此该额度不足时可能多等待一个退避周期，但不会额外派发。
- 原 actor 对无效动作继续发下一次逻辑请求的行为未改变；“不重采样”特指 transport 层，不意味着普通 actor 只有一次逻辑调用。
- 同一消息、图像内容、请求 model 字段和参数保持不变；没有真实线上 HTTP 字节抓包，也不能保证网关内部路由或权重不变，失败尝试的上游模型身份仍未知。
- 完整面板进程重启后的断点接续尚未实现，旧面板未补跑；本次只交付请求内自动重试及失败保留，不把保存状态等同于自动恢复。
