# 三任务 API 开发示例：实际结果与可复现证据

此报告直接读取本轮实际请求、响应、浏览器执行回执和离线评分；未补写模型结论，也未根据效果换样本。

## 运行范围

本报告仅汇报运行 `api_demo_20260923_v2`（协议 `competing_rules_development_v2_interface_fix`）。其他接口版本和补充诊断分别归档，不与本表合并成独立样本。

预先固定 pub013、health004、b046，各使用原误导图和对应清洁图；普通 Agent 与竞争解释＋持续规则状态使用相同 API 配置、图像和公开任务权限。计划 12 条轨迹，实际归档 12 条。

这是 API 工程验证和开发观察，不是完整 140 对实验、独立泛化证明、官方 GUI 系统排名，或方法优越性的定论。此前丢失数据上的结果不计入本报告证据。

## 12 条结果逐项展示

| 任务 | 图表条件 | 系统 | 首次选择提案 | 首提按原标签正确 | 最终提交选项 | 真实提交 | 主动作评分 | 状态 |
|---|---|---|---|---|---|---|---|---|
| pub013 | 原误导条件 | 普通 Agent | Open Illinois (IL) risk detail for priority follow-up | 是 | Open Illinois (IL) risk detail for priority follow-up | 是 | success | 已真实提交 |
| pub013 | 原误导条件 | 竞争解释＋持续规则状态 | Open Illinois (IL) risk detail for priority follow-up | 是 | Open Illinois (IL) risk detail for priority follow-up | 是 | success | 已真实提交 |
| pub013 | 对应清洁条件 | 普通 Agent | Open Illinois (IL) risk detail for priority follow-up | 是 | Open Illinois (IL) risk detail for priority follow-up | 是 | success | 已真实提交 |
| pub013 | 对应清洁条件 | 竞争解释＋持续规则状态 | Open Illinois (IL) risk detail for priority follow-up | 是 | Open Illinois (IL) risk detail for priority follow-up | 是 | success | 已真实提交 |
| health004 | 原误导条件 | 普通 Agent | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 原误导条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| health004 | 对应清洁条件 | 普通 Agent | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 对应清洁条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| b046 | 原误导条件 | 普通 Agent | Route Week 1 to the above-average revenue follow-up queue | 是 | Route Week 1 to the above-average revenue follow-up queue | 是 | success | 已真实提交 |
| b046 | 原误导条件 | 竞争解释＋持续规则状态 | Route Week 1 to the above-average revenue follow-up queue | 是 | Route Week 1 to the above-average revenue follow-up queue | 是 | success | 已真实提交 |
| b046 | 对应清洁条件 | 普通 Agent | Route Week 1 to the above-average revenue follow-up queue | 是 | Route Week 1 to the above-average revenue follow-up queue | 是 | success | 已真实提交 |
| b046 | 对应清洁条件 | 竞争解释＋持续规则状态 | Route Week 1 to the above-average revenue follow-up queue | 是 | Route Week 1 to the above-average revenue follow-up queue | 是 | success | 已真实提交 |


“首次选择”是 Actor 首次提出的选择。方法组会在执行该提案之前核验，因此改掉错误提案属于阻止错误选择，不能伪称在已执行错误状态上恢复。普通组则按正常执行继续。

## 数量汇总

```json
{
  "ordinary": {
    "trajectories": 6,
    "first_wrong_proposals": 0,
    "real_submissions": 6,
    "primary_success_with_real_submission": 6,
    "wrong_first_to_primary_success": 0,
    "correct_first_to_non_success": 0,
    "no_real_submission": 0,
    "runtime_errors": 0,
    "recommendation_correct_but_final_not_success": 0,
    "verification_decisions": {}
  },
  "competing_persistent": {
    "trajectories": 6,
    "first_wrong_proposals": 0,
    "real_submissions": 4,
    "primary_success_with_real_submission": 4,
    "wrong_first_to_primary_success": 0,
    "correct_first_to_non_success": 2,
    "no_real_submission": 2,
    "runtime_errors": 2,
    "recommendation_correct_but_final_not_success": 0,
    "verification_decisions": {
      "KEEP": 4
    }
  }
}
```

`wrong_first_to_primary_success` 只是首提与最终提交间的实际转移：普通组可称正常自行改正；方法组须结合其核验推荐与执行层判断，不能仅凭转移归因。KEEP 是保留判断，不是新增纠错。无提交、API 错误、证据未决分别保留。

## 中间实际选择的变化（不只看首尾）

```json
{
  "ordinary": {
    "first_executed_correct": 6,
    "correct_to_wrong": 1,
    "wrong_to_correct": 1,
    "trajectories_with_any_executed_wrong": 1
  },
  "competing_persistent": {
    "first_executed_correct": 4,
    "trajectories_with_any_executed_wrong": 0
  }
}
```

`correct_to_wrong` 表示已正确选择后实际改坏；`wrong_to_correct` 表示实际改回。重复选择和首次执行另列。事件不能当作独立样本，普通Agent的自行改正不能归功于核验。未提交不等于选错。逐条变化见 report_summary.json 的 executed_selection_audit。

## 请求路由、重试与开销

- 运行预算记录的真实请求尝试：38；归档尝试元数据：38；失败尝试：1。
- 本轮浏览器操作：62。另有三次无模型浏览器回归共 21 次操作（实现、保存工件复核、审查各7次），单列，不伪装成研究轨迹。
- 缺少 usage 的尝试：0。已报告 token 合计：{"prompt_tokens": 315557, "completion_tokens": 9897, "total_tokens": 325454}；未知部分不是零。
- 各 token 字段未报告的尝试数：{}。
- 请求模型名：{"gpt-5.6-sol": 38}。
- 响应顶层模型名：{"gpt-5.6-sol": 38}。
- usage 内模型名：{"gpt-5.6-sol": 38}。

以上名称是网关自报字段，不是对实际底层权重身份的独立认证。完整每次尝试见机器汇总与各请求目录。内网费用按用户豁免口径，不推算真实消费。

固定配置：

```json
{
  "protocol": "competing_rules_development_v2_interface_fix",
  "normalize_explicit_action_container": true,
  "endpoint": "https://aimemodeldev.myhexin.com/litellm/v1/chat/completions",
  "model": "gpt-5.6-sol",
  "proxy": "http://127.0.0.1:7897",
  "temperature": 0,
  "max_tokens": 2200,
  "timeout_seconds": 120,
  "max_attempts_per_call": 3,
  "max_request_attempts": 115,
  "max_browser_operations": 221,
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
    "build_report.py": "091f2ccae40ed1f64e4925cf90e7fd5c90384d6e788b3c9b3c6165f1f46fe997",
    "engine.py": "57fe690764bc82fa8c1031626ee1719e2cae9b877e01173922419ab1392bd8fb",
    "format_replay.py": "337659f4b6f0d7ed031c01a73eea4b88fe6fee1b3c716f592d85556c186418cd",
    "package_artifacts.py": "938bd640bbaf7e64d3c3df5833d336b692760c16e93f1bb8b6c232af027591d2",
    "prepare_panel.py": "a703326be51e6b71375923e465cd271f477322489a04898d995c789264b13e8c",
    "resume_interfaces.py": "ab3f16b6a187ef77d2a108d5cb48349483bbf2d5c007fdd0179400378be8a67d",
    "run_demo.py": "5c4dcabd8706708a2ff64e0a58f6c7e382faec02cf52fe44e71f1e41b7c1a636",
    "tests_adapter.py": "e71777c4ece0f2bf1e33e977bfad7bf8ef9dbf68b793cc18a0da05c5cae6c768",
    "tests_engine.py": "d132d5ff5998f0cef6ae9334864d8b2635a8d22ab89e569f047986eadd7df0d3",
    "tests_format.py": "8ecfbf433643e160d573e84bd99fbf0be5964cd9c8f3c6133982aaecd64238a0",
    "tests_resume.py": "319eafeb1d60e697d5544205b521e1c9e1c8f38da46aed7bb0cf684881be4581"
  }
}
```

## 三份完整任务与防御示例

- [pub013：原图、原任务、竞争解释、核验、执行与真实提交](<examples/pub013.md>)
- [health004：原图、原任务、竞争解释、核验、执行与真实提交](<examples/health004.md>)
- [b046：原图、原任务、竞争解释、核验、执行与真实提交](<examples/b046.md>)

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

- [离线结果](<runs/api_demo_20260923_v2/offline_results.json>)
- [请求／操作总账](<runs/api_demo_20260923_v2/budget.json>)
- [运行时代码快照](<runs/api_demo_20260923_v2/runtime_source>)
- [机器可读报告与逐次路由记录](<report_summary.json>)
