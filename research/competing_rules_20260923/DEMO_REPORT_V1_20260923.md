# 三任务 API 开发示例：实际结果与可复现证据

此报告直接读取本轮实际请求、响应、浏览器执行回执和离线评分；未补写模型结论，也未根据效果换样本。

## 运行范围

预先固定 pub013、health004、b046，各使用原误导图和对应清洁图；普通 Agent 与竞争解释＋持续规则状态使用相同 API 配置、图像和公开任务权限。计划 12 条轨迹，实际归档 12 条。

这是 API 工程验证和开发观察，不是完整 140 对实验、独立泛化证明、官方 GUI 系统排名，或方法优越性的定论。此前丢失数据上的结果不计入本报告证据。

## 12 条结果逐项展示

| 任务 | 图表条件 | 系统 | 首次选择提案 | 首提按原标签正确 | 最终提交选项 | 真实提交 | 主动作评分 | 状态 |
|---|---|---|---|---|---|---|---|---|
| pub013 | 原误导条件 | 普通 Agent | Open Illinois (IL) risk detail for priority follow-up | 是 | Open Illinois (IL) risk detail for priority follow-up | 是 | success | 已真实提交 |
| pub013 | 原误导条件 | 竞争解释＋持续规则状态 | Open Illinois (IL) risk detail for priority follow-up | 是 | Open Illinois (IL) risk detail for priority follow-up | 是 | success | 已真实提交 |
| pub013 | 对应清洁条件 | 普通 Agent | Open Illinois (IL) risk detail for priority follow-up | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| pub013 | 对应清洁条件 | 竞争解释＋持续规则状态 | Open Illinois (IL) risk detail for priority follow-up | 是 | Open Illinois (IL) risk detail for priority follow-up | 是 | success | 已真实提交 |
| health004 | 原误导条件 | 普通 Agent | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 原误导条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| health004 | 对应清洁条件 | 普通 Agent | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 对应清洁条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| b046 | 原误导条件 | 普通 Agent | Route Week 1 to the above-average revenue follow-up queue | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| b046 | 原误导条件 | 竞争解释＋持续规则状态 | Route Week 1 to the above-average revenue follow-up queue | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| b046 | 对应清洁条件 | 普通 Agent | Route Week 1 to the above-average revenue follow-up queue | 是 | Route Week 1 to the above-average revenue follow-up queue | 是 | success | 已真实提交 |
| b046 | 对应清洁条件 | 竞争解释＋持续规则状态 | Route Week 1 to the above-average revenue follow-up queue | 是 | Route Week 1 to the above-average revenue follow-up queue | 是 | success | 已真实提交 |


“首次选择”是 Actor 首次提出的选择。方法组会在执行该提案之前核验，因此改掉错误提案属于阻止错误选择，不能伪称在已执行错误状态上恢复。普通组则按正常执行继续。

## 数量汇总

```json
{
  "ordinary": {
    "trajectories": 6,
    "first_wrong_proposals": 0,
    "real_submissions": 4,
    "primary_success_with_real_submission": 4,
    "wrong_first_to_primary_success": 0,
    "correct_first_to_non_success": 2,
    "no_real_submission": 2,
    "runtime_errors": 2,
    "recommendation_correct_but_final_not_success": 0,
    "verification_decisions": {}
  },
  "competing_persistent": {
    "trajectories": 6,
    "first_wrong_proposals": 0,
    "real_submissions": 3,
    "primary_success_with_real_submission": 3,
    "wrong_first_to_primary_success": 0,
    "correct_first_to_non_success": 3,
    "no_real_submission": 3,
    "runtime_errors": 3,
    "recommendation_correct_but_final_not_success": 0,
    "verification_decisions": {
      "KEEP": 3
    }
  }
}
```

`wrong_first_to_primary_success` 只是首提与最终提交间的实际转移：普通组可称正常自行改正；方法组须结合其核验推荐与执行层判断，不能仅凭转移归因。KEEP 是保留判断，不是新增纠错。无提交、API 错误、证据未决分别保留。

## 请求路由、重试与开销

- 运行预算记录的真实请求尝试：35；归档尝试元数据：35；失败尝试：0。
- 本轮浏览器操作：54。另有三次无模型浏览器回归共 21 次操作（实现、保存工件复核、审查各7次），单列，不伪装成研究轨迹。
- 缺少 usage 的尝试：0。已报告 token 合计：{"prompt_tokens": 250614, "completion_tokens": 9913, "total_tokens": 260527}；未知部分不是零。
- 各 token 字段未报告的尝试数：{}。
- 请求模型名：{"gpt-5.6-sol": 35}。
- 响应顶层模型名：{"gpt-5.6-sol": 35}。
- usage 内模型名：{"gpt-5.6-sol": 35}。

以上名称是网关自报字段，不是对实际底层权重身份的独立认证。完整每次尝试见机器汇总与各请求目录。内网费用按用户豁免口径，不推算真实消费。

固定配置：

```json
{
  "protocol": "competing_rules_development_v1",
  "endpoint": "https://aimemodeldev.myhexin.com/litellm/v1/chat/completions",
  "model": "gpt-5.6-sol",
  "proxy": "http://127.0.0.1:7897",
  "temperature": 0,
  "max_tokens": 2200,
  "timeout_seconds": 120,
  "max_attempts_per_call": 3,
  "max_request_attempts": 150,
  "max_browser_operations": 300,
  "max_actor_calls": 7,
  "max_extra_verifications": 1,
  "competitors": 2,
  "systems": [
    "ordinary",
    "competing_persistent"
  ],
  "task_ids": [
    "pub013",
    "health004",
    "b046"
  ],
  "conditions": [
    "official140",
    "clean140"
  ],
  "browser_executable": "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "full_panel_authorized": false,
  "wandb": false
}
```

运行时版本与代码哈希：

```json
{
  "python": "3.9.13 (main, Aug 25 2022, 23:51:50) [MSC v.1916 64 bit (AMD64)]",
  "platform": "Windows-10-10.0.26200-SP0",
  "packages": {
    "requests": "2.28.1",
    "Pillow": "9.2.0",
    "Flask": "1.1.2",
    "playwright": "1.60.0"
  },
  "source_sha256": {
    "adapter.py": "2a0062ba9bbdd3cb36ecdb9496383ffaa2b76e7b4a7f7823803843a377007e65",
    "engine.py": "88cbd50e41a0d1cf6b9b261671d54331bc146b2e1fe12381c20b18a568c8864b",
    "prepare_panel.py": "fab3c56c9d4272095f689f6ade74e4657dc28c32922a57c3112817c186d09e2f",
    "run_demo.py": "d52d811040728499299ae1f5c19bbbf198b5d0d20e26f0aa835aa1e5278f32b0",
    "tests_adapter.py": "e71777c4ece0f2bf1e33e977bfad7bf8ef9dbf68b793cc18a0da05c5cae6c768",
    "tests_engine.py": "271882bbe52050d320f9d2ae97b1b13f8c2e2fd7616098cf00bbf2a56cbdd591"
  }
}
```

## 三份完整任务与防御示例

- [pub013：原图、原任务、竞争解释、核验、执行与真实提交](<examples_v1/pub013.md>)
- [health004：原图、原任务、竞争解释、核验、执行与真实提交](<examples_v1/health004.md>)
- [b046：原图、原任务、竞争解释、核验、执行与真实提交](<examples_v1/b046.md>)

## 评分与证据边界

- 正确性只在在线运行结束后依据原数据集标签离线计算；标签、另一条件、CSV、误导类型和原始 action_id 不向被测模型提供。
- 使用 `field-complete-public-shell-v1`：保留原公开任务、原图、原选项、真实可见附属字段与提交标签，并真正执行浏览器表单 POST；它不是原门户网站逐像素复现。
- 主动作按原 expected/misleading action 对应关系评分；附属文字的 exact-match 只是独立诊断，不当作语义正确性。原官方完整端到端分数未计算。
- 隐藏上下文字段由服务器带入，只是原流程静态上下文，不计作 Agent 完成的操作。只读公开字段同样不计作 Agent 推理。
- 核验推荐、选择执行器落实的选择、Actor 最终提交三层不合并。暂时推荐正确但没有正确提交，不算稳定完成。
- 原生三任务只有一次主要读图判断。后续选择／理由／提交可见规则状态传入接口，但没有新的独立语义判断，持续规则状态的防复发因果效果为 N/A。
- 本次没有普通全图核查、竞争解释不持久化的实际对照，不能把与普通 Agent 的差异独立归因到竞争解释或持续规则状态；对应公平对照留在后续预注册实验配置。
- 工程测试通过只证明接口与执行链路，不等于研究假设成立。本轮结束即停止，不自动运行完整 140 对。

## 原始证据入口

- [离线结果](<runs/api_demo_20260923_v1/offline_results.json>)
- [请求／操作总账](<runs/api_demo_20260923_v1/budget.json>)
- [运行时代码快照](<runs/api_demo_20260923_v1/runtime_source>)
- [机器可读报告与逐次路由记录](<report_summary_v1.json>)
