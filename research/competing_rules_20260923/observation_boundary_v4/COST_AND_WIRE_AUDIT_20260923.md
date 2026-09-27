# 五任务旧／新观察边界提示：工程成本与实际请求审计

本文件只读真实运行工件，不发起 API 请求、不启动浏览器、不修改旧结果。检查通过只能证明成本与输入工程关系，不能证明观察内容真实、规则合理或核验具有独立依据。

## 实际调用与成本

| 项目 | 实际记录 |
|---|---:|
| 计划逻辑调用 | 22 |
| 实际请求体数量 | 14 |
| 真实请求尝试 | 15 |
| 失败尝试（含解析失败） | 4 |
| 额外重试尝试 | 1 |
| 浏览器操作 | 6 |
| 以 length 结束的响应 | 0 |
| 发生候选截断的生成 | 0 |
| 实际 JSON 表示修复 | 0 |
| 新任务 Actor 动作容器实际变化 | 0 |

总账／尝试文件计数一致：True；未超过冻结上限：True。

已报告 token 合计：`{"prompt_tokens": 116347, "completion_tokens": 8468, "total_tokens": 124815}`。缺少 usage 的尝试为 4；各 token 字段缺失计数为 `{"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 4}`。未知开销不作零处理。

内网费用按用户既定豁免口径，本审计不估算真实付费金额。

## 网关路由与完成状态

- 请求模型名：`{"gpt-5.6-sol": 15}`。
- 响应顶层模型名：`{"not_reported": 4, "gpt-5.6-sol": 11}`。
- usage 内模型名：`{"not_reported": 4, "gpt-5.6-sol": 11}`。
- HTTP 状态：`{"400": 3, "200": 11, "503": 1}`；finish_reason：`{"stop": 11}`。
- 模块状态：`{"completed": 5, "verifier_call_or_parse_failure": 1, "unsupported_source_or_ordinary_proposal": 4}`；固定模块槽位 10，已开始模块 6。
- 发起过核验请求的模块数 6；核验 HTTP200 响应 5；有已解析核验结果的逻辑调用 5。`verifier_executed` 只代表请求尝试，不代表服务已完成模型推理。
- 服务端错误类型：`{"budget_exceeded": 3}`。仅保留错误类别，不抄录响应里的个人邮箱、团队或账户细节。

本轮 budget_exceeded 为 3 次；本地请求 15/60、浏览器操作 6/30，仍在冻结上限内。该类阻塞来自服务端账户累计阈值，而不是本地实验预算用尽；这不是得到继续换账户、换服务或绕过限制的授权。

这些模型名都是网关自报字段，不是对底层权重的独立认证。length 计数仅反映协议报告的输出上限终止，不判断图像裁剪；本实验发送的图像尺寸和哈希逐次记录在 JSON 附录中。

## 配对实际输入核对

| 任务 | 生成器完整 user 消息相同 | 图像字节／标识相同 | system 提示不同 | 与原配对证明一致 | 核验候选集合相同 |
|---|---|---|---|---|---|
| pub013 | True | True | True | True | False |
| health004 | True | True | True | True | False |
| b046 | True | True | True | True | False |
| pub031 | 未发生／未知 | 未发生／未知 | 未发生／未知 | 未发生／未知 | 未发生／未知 |
| b001 | 未发生／未知 | 未发生／未知 | 未发生／未知 | 未发生／未知 | 未发生／未知 |

生成器收到相同公开内容、初始提案和图像，只改变提示配置。核验器候选集允许因上游生成不同而不同；不能将它描述为对完全相同候选进行的单一核验器消融。两个阶段的提示都发生变化。

## 浏览器与复现边界

实际浏览器动作种类：`{"setup_open_task": 2, "setup_open_dashboard": 2, "setup_open_form": 2}`。提交事件 0；非空提交回执文件 0。

旧三例复用已有真实输入，不进行页面恢复；新两例各尝试获取一次普通 Actor 提案，但均被网关拒绝，不落实选择、不提交。该结果是观察／规则／推论模块诊断，不是新的自然轨迹结果、恢复率或业务完成率。

新两例取得已解析普通 Actor 提案的逻辑调用为 0。完成记录中的 `source_tasks_added: 2` 表示固定的两个新增任务已纳入数据准备，不表示两例都成功接受了被测模块评测。未取得前置选择时，其两个提示配置均未运行。

运行时源快照哈希检查：`{"engine.py": true, "run_demo.py": true, "prompts_observation_v4.py": true, "adapter.py": true, "format_replay.py": true, "run_check.py": true}`。本审计读取运行快照，不用当前可编辑源码冒充执行版本。

完整逐次请求、响应、模型路由、图像尺寸／哈希、候选裁剪索引和 JSON 修复日志见 [COST_AND_WIRE_AUDIT_20260923.json](COST_AND_WIRE_AUDIT_20260923.json)。

来源：[冻结协议](runs/paired_v4_20260923/frozen_protocol.json)、[实际总账](runs/paired_v4_20260923/budget.json)、[完成记录](runs/paired_v4_20260923/completion.json)。
