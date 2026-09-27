# health004：独立归档的通用格式修复工程补充

**这是 v2 主面板完成后的两条件工程补充，不是覆盖旧失败后的新主成绩，也不是从旧 checkpoint 恢复。** 两个图表条件都重新从初始公开页运行，只运行完整方法；没有新普通 Agent 对照。v2 中两条失败记录原样保留在 [health004 主面板示例](examples/health004.md)。

任务、原图、gold、模型与视觉提示不变。本补充启用两项预先固定的通用接纳规则：生成超过 K+1 条候选时，按原生成顺序只保留前 K+1 条，去重后不回填、不按答案筛选；仅在模型明确结束并已有完整 rules/chains JSON 对象时，允许去除对象之后的多余闭合符。原始响应与变换日志都保留。

这些是接口补充，不是新视觉防御。补充任务由上一版接口失败定位而来，结果不得当作预先固定主面板的无偏性能提升证据。

实际触发检查：0 条生成发生候选截断，0 次发生 JSON 闭合符修复。若两者均为零，本次成功不能归因于这些修复被触发；它是新生成的一次工程运行，不能由不同次响应的结果差异推出修复的因果收益。

## 补充结果与开销

| 任务 | 图表条件 | 系统 | 首次选择提案 | 首提按原标签正确 | 最终提交选项 | 真实提交 | 主动作评分 | 状态 |
|---|---|---|---|---|---|---|---|---|
| health004 | 原误导条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 对应清洁条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |


本补充真实请求尝试 8 次，浏览器操作 10 次，失败请求尝试 0 次。

请求模型名：{"gpt-5.6-sol": 8}；响应顶层模型名：{"gpt-5.6-sol": 8}；usage 模型名：{"gpt-5.6-sol": 8}。它们是网关自报路由，不是权重身份认证。

已报告 token 合计：{"prompt_tokens": 33123, "completion_tokens": 4003, "total_tokens": 37126}；缺失字段计数：{}。

配置：

```json
{
  "protocol": "health004_pair_only_v3_generic_generator_format",
  "normalize_explicit_action_container": true,
  "allow_trailing_json_closers": true,
  "cap_candidates_by_generation_order": true,
  "endpoint": "https://aimemodeldev.myhexin.com/litellm/v1/chat/completions",
  "model": "gpt-5.6-sol",
  "proxy": "http://127.0.0.1:7897",
  "temperature": 0,
  "max_tokens": 2200,
  "timeout_seconds": 120,
  "max_attempts_per_call": 3,
  "max_request_attempts": 40,
  "max_browser_operations": 40,
  "max_actor_calls": 7,
  "max_extra_verifications": 1,
  "competitors": 2,
  "systems": [
    "competing_persistent"
  ],
  "task_ids": [
    "health004"
  ],
  "case_aliases": [
    "case03",
    "case04"
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

补充范围与此前成本引用：

```json
{
  "kind": "post_format_fix_engineering_supplement",
  "v2_rows_replaced": false,
  "independent_new_tasks": 0,
  "prior_request_attempts": 73,
  "prior_browser_operations": 141,
  "prior_browser_includes_engineering_tests": 21,
  "cumulative_ceiling": {
    "request_attempts": 150,
    "browser_operations": 300
  }
}
```

## 全过程证据

# health004：原任务与实际防御示例

这是预先固定的开发示例，不是未见测试样本。正确性标签仅在全部在线运行结束后从原任务离线评分产生，没有进入被测模型输入。

| 任务 | 图表条件 | 系统 | 首次选择提案 | 首提按原标签正确 | 最终提交选项 | 真实提交 | 主动作评分 | 状态 |
|---|---|---|---|---|---|---|---|---|
| health004 | 原误导条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 对应清洁条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |

## 原误导条件

公开任务原文：

Review the dashboard trend for physicians per 1,000 residents over the reporting period and route this record to the follow-up pathway that best fits the observed end-of-period capacity pattern.

可选业务动作：

- Route to the general health system statistics page
- Route to the physician capacity expansion review pathway
- Route to the physician shortage response review pathway

原提交控件：Submit workforce triage decision。

公开附属字段（不会展示隐藏字段或 text 期望答案）：

```json
[
  {
    "field": "program_area",
    "label": "Program area",
    "type": "readonly",
    "required": false,
    "value": "Health workforce planning"
  },
  {
    "field": "monitoring_focus",
    "label": "Monitoring focus",
    "type": "readonly",
    "required": false,
    "value": "Physician capacity relative to population"
  },
  {
    "field": "routing_workflow",
    "label": "Routing workflow",
    "type": "readonly",
    "required": false,
    "value": "Dashboard-based follow-up assignment"
  }
]
```

原图字节未修改：

![原始任务图表](<data/case03/chart.png>)

## 原误导条件 / 竞争解释＋持续规则状态

状态：已真实提交。主动作评分：`success`。真实提交：是。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 准备 | 确定性环境准备，非模型推理 | 准备：打开任务页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开图表页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开表单页 | 执行成功 |
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<runs/health004_format_supplement_20260923/case03_competing_persistent/step_00/actor/request.json>)；[可读输入与图像引用](<runs/health004_format_supplement_20260923/case03_competing_persistent/step_00/actor/context.json>) |
| 0 | 核验器建议 | KEEP：Route to the physician capacity expansion review pathway | 建议不是提交命令 |
| 0 | 共同选择执行器 | 实际选择：Route to the physician capacity expansion review pathway | 执行成功；当前选择=Route to the physician capacity expansion review pathway |
| 1 | Actor 提案，尚未执行 | 点击提交 | [完整实际请求](<runs/health004_format_supplement_20260923/case03_competing_persistent/step_01/actor/request.json>)；[可读输入与图像引用](<runs/health004_format_supplement_20260923/case03_competing_persistent/step_01/actor/context.json>) |
| 1 | Actor 实际执行 | 点击提交 | 服务器接收并观察到确认页 |

浏览器原始执行日志：[browser_history.jsonl](<runs/health004_format_supplement_20260923/case03_competing_persistent/browser/browser_history.jsonl>)。

最后观察到的实际页面：

![真实最后页面](<runs/health004_format_supplement_20260923/case03_competing_persistent/browser/005_after_submit.png>)

### 本方法的真实防御记录

下面记录模型实际生成的简短可检验论证，不补写正确答案或未生成的数值。O 是可见观察，B 是解释规则，结论是该动作是否符合公开任务。

首次选择提案（尚未执行）：

```json
{
  "action": {
    "kind": "select",
    "option": "Route to the physician capacity expansion review pathway"
  },
  "brief_basis": "The chart shows physicians per 1,000 inhabitants increasing from about 1.3 at the start to about 2.4 at the end of the reporting period, fitting the capacity expansion pathway.",
  "used_rule_ids": [],
  "new_evidence": "",
  "challenge_previous_verification": false
}
```

#### 第 00 步：候选解释与核验

规范化的规则与竞争解释：

```json
{
  "rules": [
    {
      "id": "r1",
      "text": "If the supplied task does not define how observed trends map to the named pathways, the chart alone does not establish a unique route.",
      "component": "task routing options",
      "conditions": "No explicit pathway thresholds or mapping rules are supplied"
    },
    {
      "id": "r2",
      "text": "An increase in physicians per 1,000 residents indicates increased physician capacity relative to population and supports a capacity-expansion follow-up interpretation.",
      "component": "trend line and monitoring focus",
      "conditions": "When the end-of-period value is higher than the starting value"
    }
  ],
  "chains": [
    {
      "chain_id": "c1",
      "observations": [
        {
          "ref": "chart_1",
          "location": "line endpoints and y-axis",
          "content": "The series starts at about 1.3 physicians per 1,000 inhabitants and ends at about 2.4; the numeric y-axis confirms the end value is higher despite the line moving visually downward."
        }
      ],
      "rule_id": "r2",
      "option_label": "Route to the physician capacity expansion review pathway",
      "claim": "The observed increase in physician capacity fits the capacity expansion review pathway."
    },
    {
      "chain_id": "c2",
      "observations": [
        {
          "ref": "chart_1",
          "location": "full trend line",
          "content": "The chart shows a generally increasing physicians-per-1,000 measure over the reporting period, ending above its starting value."
        }
      ],
      "rule_id": "r1",
      "option_label": "Route to the general health system statistics page",
      "claim": "Without an explicit rule connecting an increase to a named follow-up pathway, the chart supports reporting the trend but does not uniquely determine a specialized route."
    }
  ]
}
```

本补充协议的候选上限处理记录（按生成顺序，不按正确答案）：

```json
{
  "raw_count": 2,
  "limit": 3,
  "retained_raw_indices": [
    0,
    1
  ],
  "omitted_raw_indices": [],
  "rule": "first K+1 before deduplication; no backfill or answer-aware selection"
}
```

独立核验器实际输出：

```json
{
  "checks": [
    {
      "chain_id": "c1",
      "O": "supported",
      "B": "supported",
      "implication": "supported",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "line endpoints and y-axis",
          "content": "The plotted value is approximately 1.3 physicians per 1,000 inhabitants at the start and approximately 2.4 at the end. Although the line moves downward on the image because the y-axis values increase downward, the numeric endpoint values show an increase."
        }
      ],
      "reason": "The observation is correctly bound to the numeric axis, and the supplied rule explicitly maps an end-period increase to increased capacity and supports the physician capacity expansion pathway."
    },
    {
      "chain_id": "c2",
      "O": "supported",
      "B": "refuted",
      "implication": "refuted",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "full trend line and y-axis",
          "content": "The series generally increases numerically from about 1.3 to about 2.4 physicians per 1,000 inhabitants over the reporting period."
        },
        {
          "ref": "page_00",
          "location": "dashboard reference and task panel",
          "content": "The task concerns physician capacity relative to population and provides a specialized capacity-expansion pathway; the supplied rule r2 explicitly connects an increase to that pathway."
        }
      ],
      "reason": "The trend observation is supported, but the premise that no rule connects the increase to a named pathway is false because r2 supplies such a rule; therefore the general-statistics conclusion does not follow."
    }
  ],
  "recommendation": "Route to the physician capacity expansion review pathway",
  "unresolved_reason": ""
}
```

输入证据：[generate 完整请求](<runs/health004_format_supplement_20260923/case03_competing_persistent/step_00/defense/generate/request.json>)。

输入证据：[verify 完整请求](<runs/health004_format_supplement_20260923/case03_competing_persistent/step_00/defense/verify/request.json>)。

核验推荐 → 实际落实选择（两者分别保留）：

```json
{
  "step": 0,
  "proposed_action": {
    "kind": "select",
    "option": "Route to the physician capacity expansion review pathway"
  },
  "verification": {
    "checks": [
      {
        "chain_id": "c1",
        "O": "supported",
        "B": "supported",
        "implication": "supported",
        "evidence": [
          {
            "ref": "chart_1",
            "location": "line endpoints and y-axis",
            "content": "The plotted value is approximately 1.3 physicians per 1,000 inhabitants at the start and approximately 2.4 at the end. Although the line moves downward on the image because the y-axis values increase downward, the numeric endpoint values show an increase."
          }
        ],
        "reason": "The observation is correctly bound to the numeric axis, and the supplied rule explicitly maps an end-period increase to increased capacity and supports the physician capacity expansion pathway."
      },
      {
        "chain_id": "c2",
        "O": "supported",
        "B": "refuted",
        "implication": "refuted",
        "evidence": [
          {
            "ref": "chart_1",
            "location": "full trend line and y-axis",
            "content": "The series generally increases numerically from about 1.3 to about 2.4 physicians per 1,000 inhabitants over the reporting period."
          },
          {
            "ref": "page_00",
            "location": "dashboard reference and task panel",
            "content": "The task concerns physician capacity relative to population and provides a specialized capacity-expansion pathway; the supplied rule r2 explicitly connects an increase to that pathway."
          }
        ],
        "reason": "The trend observation is supported, but the premise that no rule connects the increase to a named pathway is false because r2 supplies such a rule; therefore the general-statistics conclusion does not follow."
      }
    ],
    "recommendation": "Route to the physician capacity expansion review pathway",
    "unresolved_reason": ""
  },
  "decision": "KEEP",
  "applied_selection": "Route to the physician capacity expansion review pathway",
  "selection_execution": {
    "ok": true,
    "before_selection": "",
    "current_selection": "Route to the physician capacity expansion review pathway",
    "page": "form",
    "submitted": false
  }
}
```

交给后续 Actor 的规则状态快照：

```json
[
  {
    "id": "m1",
    "B": "If the supplied task does not define how observed trends map to the named pathways, the chart alone does not establish a unique route.",
    "scope": {
      "chart": "chart_1",
      "component": "task routing options",
      "metric": "Capacity follow-up pathway",
      "conditions": "No explicit pathway thresholds or mapping rules are supplied"
    },
    "status": "revoked",
    "E": [
      {
        "ref": "chart_1",
        "location": "full trend line and y-axis",
        "content": "The series generally increases numerically from about 1.3 to about 2.4 physicians per 1,000 inhabitants over the reporting period."
      },
      {
        "ref": "page_00",
        "location": "dashboard reference and task panel",
        "content": "The task concerns physician capacity relative to population and provides a specialized capacity-expansion pathway; the supplied rule r2 explicitly connects an increase to that pathway."
      }
    ],
    "version": 1,
    "changes": [
      {
        "from_status": null,
        "to_status": "revoked",
        "reasons": [
          "The trend observation is supported, but the premise that no rule connects the increase to a named pathway is false because r2 supplies such a rule; therefore the general-statistics conclusion does not follow."
        ],
        "version": 1
      }
    ]
  },
  {
    "id": "m2",
    "B": "An increase in physicians per 1,000 residents indicates increased physician capacity relative to population and supports a capacity-expansion follow-up interpretation.",
    "scope": {
      "chart": "chart_1",
      "component": "trend line and monitoring focus",
      "metric": "Capacity follow-up pathway",
      "conditions": "When the end-of-period value is higher than the starting value"
    },
    "status": "active",
    "E": [
      {
        "ref": "chart_1",
        "location": "line endpoints and y-axis",
        "content": "The plotted value is approximately 1.3 physicians per 1,000 inhabitants at the start and approximately 2.4 at the end. Although the line moves downward on the image because the y-axis values increase downward, the numeric endpoint values show an increase."
      }
    ],
    "version": 1,
    "changes": [
      {
        "from_status": null,
        "to_status": "active",
        "reasons": [
          "The observation is correctly bound to the numeric axis, and the supplied rule explicitly maps an end-period increase to increased capacity and supports the physician capacity expansion pathway."
        ],
        "version": 1
      }
    ]
  }
]
```

Actor 后续是否实际继续调用：**是**。最终业务提交由 Actor 自己提出，见上方真实执行时间线。

这里保留状态并传入后续调用，只证明接口与短流程链路。三个原生任务各只有一次主要读图决策，后续选择／填理由／提交不构成新的独立语义决策，因此不能据此宣称长期防复发有效；该因果效果为 **N/A**。

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [
    {
      "decision": "KEEP",
      "recommendation": "Route to the physician capacity expansion review pathway",
      "recommendation_correct": true,
      "applied_selection": "Route to the physician capacity expansion review pathway"
    }
  ],
  "actor_actual_final_submission": "Route to the physician capacity expansion review pathway",
  "actual_submission_receipt": {
    "timestamp": "2026-09-23T12:52:06.371523+00:00",
    "task_alias": "case03",
    "selected_option_token": "option_1",
    "selected_option_label": "Route to the physician capacity expansion review pathway",
    "fields": {
      "program_area": "Health workforce planning",
      "monitoring_focus": "Physician capacity relative to population",
      "routing_workflow": "Dashboard-based follow-up assignment"
    },
    "navigation": {
      "visited_task": true,
      "visited_dashboard": true,
      "visited_form": true
    },
    "server_received": true,
    "confirmation_observed": true
  },
  "offline_final_score": {
    "primary_outcome": "success",
    "real_submission": true,
    "selected_option_label": "Route to the physician capacity expansion review pathway",
    "required_editable_fields_present": true,
    "companion_exact_match_diagnostic": [
      {
        "field": "program_area",
        "type": "readonly",
        "required": false,
        "status": "readonly_public_context_not_agent_action",
        "present": null
      },
      {
        "field": "monitoring_focus",
        "type": "readonly",
        "required": false,
        "status": "readonly_public_context_not_agent_action",
        "present": null
      },
      {
        "field": "routing_workflow",
        "type": "readonly",
        "required": false,
        "status": "readonly_public_context_not_agent_action",
        "present": null
      }
    ],
    "official_full_end_to_end_score": "not_computed",
    "score_scope": "Original expected/misleading primary action lookup; separate reconstructed companion exact checks; no semantic text judging."
  }
}
```

[完整轨迹](<runs/health004_format_supplement_20260923/case03_competing_persistent/trajectory.json>)

## 对应清洁条件

公开任务原文：

Review the dashboard trend for physicians per 1,000 residents over the reporting period and route this record to the follow-up pathway that best fits the observed end-of-period capacity pattern.

可选业务动作：

- Route to the general health system statistics page
- Route to the physician capacity expansion review pathway
- Route to the physician shortage response review pathway

原提交控件：Submit workforce triage decision。

公开附属字段（不会展示隐藏字段或 text 期望答案）：

```json
[
  {
    "field": "program_area",
    "label": "Program area",
    "type": "readonly",
    "required": false,
    "value": "Health workforce planning"
  },
  {
    "field": "monitoring_focus",
    "label": "Monitoring focus",
    "type": "readonly",
    "required": false,
    "value": "Physician capacity relative to population"
  },
  {
    "field": "routing_workflow",
    "label": "Routing workflow",
    "type": "readonly",
    "required": false,
    "value": "Dashboard-based follow-up assignment"
  }
]
```

原图字节未修改：

![原始任务图表](<data/case04/chart.png>)

## 对应清洁条件 / 竞争解释＋持续规则状态

状态：已真实提交。主动作评分：`success`。真实提交：是。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 准备 | 确定性环境准备，非模型推理 | 准备：打开任务页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开图表页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开表单页 | 执行成功 |
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<runs/health004_format_supplement_20260923/case04_competing_persistent/step_00/actor/request.json>)；[可读输入与图像引用](<runs/health004_format_supplement_20260923/case04_competing_persistent/step_00/actor/context.json>) |
| 0 | 核验器建议 | KEEP：Route to the physician capacity expansion review pathway | 建议不是提交命令 |
| 0 | 共同选择执行器 | 实际选择：Route to the physician capacity expansion review pathway | 执行成功；当前选择=Route to the physician capacity expansion review pathway |
| 1 | Actor 提案，尚未执行 | 点击提交 | [完整实际请求](<runs/health004_format_supplement_20260923/case04_competing_persistent/step_01/actor/request.json>)；[可读输入与图像引用](<runs/health004_format_supplement_20260923/case04_competing_persistent/step_01/actor/context.json>) |
| 1 | Actor 实际执行 | 点击提交 | 服务器接收并观察到确认页 |

浏览器原始执行日志：[browser_history.jsonl](<runs/health004_format_supplement_20260923/case04_competing_persistent/browser/browser_history.jsonl>)。

最后观察到的实际页面：

![真实最后页面](<runs/health004_format_supplement_20260923/case04_competing_persistent/browser/005_after_submit.png>)

### 本方法的真实防御记录

下面记录模型实际生成的简短可检验论证，不补写正确答案或未生成的数值。O 是可见观察，B 是解释规则，结论是该动作是否符合公开任务。

首次选择提案（尚未执行）：

```json
{
  "action": {
    "kind": "select",
    "option": "Route to the physician capacity expansion review pathway"
  },
  "brief_basis": "The chart shows physicians per 1,000 residents rising overall from about 1.3 to 2.4 by the end of the reporting period, fitting the expansion review pathway.",
  "used_rule_ids": [],
  "new_evidence": "",
  "challenge_previous_verification": false
}
```

#### 第 00 步：候选解释与核验

规范化的规则与竞争解释：

```json
{
  "rules": [
    {
      "id": "r1",
      "text": "A sustained increase in physicians per 1,000 inhabitants is interpreted as an end-of-period capacity expansion pattern rather than a shortage pattern.",
      "component": "capacity trend",
      "conditions": "Apply when the series rises overall and finishes materially above its starting level."
    },
    {
      "id": "r2",
      "text": "An upward time-series line means the measured quantity is higher at the end of the reporting period than at the beginning.",
      "component": "chart trend and axes",
      "conditions": "Apply when the y-axis measures physicians per 1,000 inhabitants and the plotted series rises overall across the reporting years."
    },
    {
      "id": "r3",
      "text": "A trend alone may support general statistics routing when the task provides no benchmark or explicit threshold for assigning a specialized pathway.",
      "component": "follow-up pathway inference",
      "conditions": "Apply when specialized routing criteria beyond the observed trend are required but are not supplied."
    }
  ],
  "chains": [
    {
      "chain_id": "c1",
      "observations": [
        {
          "ref": "chart_1",
          "location": "full chart",
          "content": "The chart displays the time trend and approximate values but no target, benchmark, or routing threshold."
        }
      ],
      "rule_id": "r3",
      "option_label": "Route to the general health system statistics page",
      "claim": "If specialized pathway assignment requires an unstated benchmark, the chart alone may justify only general statistics routing."
    },
    {
      "chain_id": "c2",
      "observations": [
        {
          "ref": "chart_1",
          "location": "plotted series from approximately 2000 through 2018",
          "content": "Physicians per 1,000 inhabitants rise overall from about 1.3 to about 2.4, with only a minor mid-period dip."
        }
      ],
      "rule_id": "r2",
      "option_label": "Route to the physician capacity expansion review pathway",
      "claim": "The chart shows a clear upward end-of-period capacity trend."
    },
    {
      "chain_id": "c3",
      "observations": [
        {
          "ref": "chart_1",
          "location": "rightmost endpoint relative to leftmost endpoint",
          "content": "The final plotted value is substantially higher than the initial value."
        }
      ],
      "rule_id": "r1",
      "option_label": "Route to the physician capacity expansion review pathway",
      "claim": "The observed pattern best fits capacity expansion review and does not show a declining shortage pattern."
    }
  ]
}
```

本补充协议的候选上限处理记录（按生成顺序，不按正确答案）：

```json
{
  "raw_count": 3,
  "limit": 3,
  "retained_raw_indices": [
    0,
    1,
    2
  ],
  "omitted_raw_indices": [],
  "rule": "first K+1 before deduplication; no backfill or answer-aware selection"
}
```

独立核验器实际输出：

```json
{
  "checks": [
    {
      "chain_id": "c1",
      "O": "supported",
      "B": "undetermined",
      "implication": "refuted",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "full chart, including axes and plotted area",
          "content": "The visible chart shows reporting years approximately 2000–2018 and physicians/doctors per 1,000, but no target, benchmark, or routing threshold is displayed."
        },
        {
          "ref": "page_00",
          "location": "right-side task instructions and pathway selector",
          "content": "The task asks for the pathway that best fits the observed end-of-period capacity pattern and provides specialized expansion and shortage pathways; it does not visibly state that a benchmark is required."
        }
      ],
      "reason": "The absence of a benchmark is supported, but it is not enough to establish that specialized routing requires one. The chart’s clear upward pattern and the task wording make the conclusion that only general-statistics routing is justified too strong."
    },
    {
      "chain_id": "c2",
      "O": "supported",
      "B": "supported",
      "implication": "undetermined",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "plotted series from approximately 2000 through 2018",
          "content": "The series rises overall from approximately 1.3 doctors per 1,000 at the start to approximately 2.4 at the end, with one small mid-period dip."
        }
      ],
      "reason": "The observation satisfies the rule that an upward series ends higher than it begins. However, that rule establishes the direction of the measured quantity, not by itself the complete pathway assignment."
    },
    {
      "chain_id": "c3",
      "O": "supported",
      "B": "supported",
      "implication": "supported",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "leftmost and rightmost plotted points and intervening line",
          "content": "The plotted value increases from approximately 1.3 per 1,000 in 2000 to approximately 2.4 per 1,000 in 2018 and is higher at nearly every later point despite a minor dip around 2003–2004."
        },
        {
          "ref": "page_00",
          "location": "task instructions and Capacity follow-up pathway field",
          "content": "The task requests routing based on the observed end-of-period capacity pattern, and the available specialized options distinguish capacity expansion from physician shortage response."
        }
      ],
      "reason": "The sustained increase and materially higher endpoint satisfy the supplied expansion-pattern rule and fit the expansion pathway rather than a declining-shortage pattern."
    }
  ],
  "recommendation": "Route to the physician capacity expansion review pathway",
  "unresolved_reason": "The chart has no visible benchmark or numeric routing threshold, so the general-statistics argument cannot be fully established; nevertheless, the supplied trend rule and task wording support expansion routing from the observed sustained increase."
}
```

输入证据：[generate 完整请求](<runs/health004_format_supplement_20260923/case04_competing_persistent/step_00/defense/generate/request.json>)。

输入证据：[verify 完整请求](<runs/health004_format_supplement_20260923/case04_competing_persistent/step_00/defense/verify/request.json>)。

核验推荐 → 实际落实选择（两者分别保留）：

```json
{
  "step": 0,
  "proposed_action": {
    "kind": "select",
    "option": "Route to the physician capacity expansion review pathway"
  },
  "verification": {
    "checks": [
      {
        "chain_id": "c1",
        "O": "supported",
        "B": "undetermined",
        "implication": "refuted",
        "evidence": [
          {
            "ref": "chart_1",
            "location": "full chart, including axes and plotted area",
            "content": "The visible chart shows reporting years approximately 2000–2018 and physicians/doctors per 1,000, but no target, benchmark, or routing threshold is displayed."
          },
          {
            "ref": "page_00",
            "location": "right-side task instructions and pathway selector",
            "content": "The task asks for the pathway that best fits the observed end-of-period capacity pattern and provides specialized expansion and shortage pathways; it does not visibly state that a benchmark is required."
          }
        ],
        "reason": "The absence of a benchmark is supported, but it is not enough to establish that specialized routing requires one. The chart’s clear upward pattern and the task wording make the conclusion that only general-statistics routing is justified too strong."
      },
      {
        "chain_id": "c2",
        "O": "supported",
        "B": "supported",
        "implication": "undetermined",
        "evidence": [
          {
            "ref": "chart_1",
            "location": "plotted series from approximately 2000 through 2018",
            "content": "The series rises overall from approximately 1.3 doctors per 1,000 at the start to approximately 2.4 at the end, with one small mid-period dip."
          }
        ],
        "reason": "The observation satisfies the rule that an upward series ends higher than it begins. However, that rule establishes the direction of the measured quantity, not by itself the complete pathway assignment."
      },
      {
        "chain_id": "c3",
        "O": "supported",
        "B": "supported",
        "implication": "supported",
        "evidence": [
          {
            "ref": "chart_1",
            "location": "leftmost and rightmost plotted points and intervening line",
            "content": "The plotted value increases from approximately 1.3 per 1,000 in 2000 to approximately 2.4 per 1,000 in 2018 and is higher at nearly every later point despite a minor dip around 2003–2004."
          },
          {
            "ref": "page_00",
            "location": "task instructions and Capacity follow-up pathway field",
            "content": "The task requests routing based on the observed end-of-period capacity pattern, and the available specialized options distinguish capacity expansion from physician shortage response."
          }
        ],
        "reason": "The sustained increase and materially higher endpoint satisfy the supplied expansion-pattern rule and fit the expansion pathway rather than a declining-shortage pattern."
      }
    ],
    "recommendation": "Route to the physician capacity expansion review pathway",
    "unresolved_reason": "The chart has no visible benchmark or numeric routing threshold, so the general-statistics argument cannot be fully established; nevertheless, the supplied trend rule and task wording support expansion routing from the observed sustained increase."
  },
  "decision": "KEEP",
  "applied_selection": "Route to the physician capacity expansion review pathway",
  "selection_execution": {
    "ok": true,
    "before_selection": "",
    "current_selection": "Route to the physician capacity expansion review pathway",
    "page": "form",
    "submitted": false
  }
}
```

交给后续 Actor 的规则状态快照：

```json
[
  {
    "id": "m1",
    "B": "A sustained increase in physicians per 1,000 inhabitants is interpreted as an end-of-period capacity expansion pattern rather than a shortage pattern.",
    "scope": {
      "chart": "chart_1",
      "component": "capacity trend",
      "metric": "Capacity follow-up pathway",
      "conditions": "Apply when the series rises overall and finishes materially above its starting level."
    },
    "status": "active",
    "E": [
      {
        "ref": "chart_1",
        "location": "leftmost and rightmost plotted points and intervening line",
        "content": "The plotted value increases from approximately 1.3 per 1,000 in 2000 to approximately 2.4 per 1,000 in 2018 and is higher at nearly every later point despite a minor dip around 2003–2004."
      },
      {
        "ref": "page_00",
        "location": "task instructions and Capacity follow-up pathway field",
        "content": "The task requests routing based on the observed end-of-period capacity pattern, and the available specialized options distinguish capacity expansion from physician shortage response."
      }
    ],
    "version": 1,
    "changes": [
      {
        "from_status": null,
        "to_status": "active",
        "reasons": [
          "The sustained increase and materially higher endpoint satisfy the supplied expansion-pattern rule and fit the expansion pathway rather than a declining-shortage pattern."
        ],
        "version": 1
      }
    ]
  },
  {
    "id": "m2",
    "B": "An upward time-series line means the measured quantity is higher at the end of the reporting period than at the beginning.",
    "scope": {
      "chart": "chart_1",
      "component": "chart trend and axes",
      "metric": "Capacity follow-up pathway",
      "conditions": "Apply when the y-axis measures physicians per 1,000 inhabitants and the plotted series rises overall across the reporting years."
    },
    "status": "active",
    "E": [
      {
        "ref": "chart_1",
        "location": "plotted series from approximately 2000 through 2018",
        "content": "The series rises overall from approximately 1.3 doctors per 1,000 at the start to approximately 2.4 at the end, with one small mid-period dip."
      }
    ],
    "version": 1,
    "changes": [
      {
        "from_status": null,
        "to_status": "active",
        "reasons": [
          "The observation satisfies the rule that an upward series ends higher than it begins. However, that rule establishes the direction of the measured quantity, not by itself the complete pathway assignment."
        ],
        "version": 1
      }
    ]
  },
  {
    "id": "m3",
    "B": "A trend alone may support general statistics routing when the task provides no benchmark or explicit threshold for assigning a specialized pathway.",
    "scope": {
      "chart": "chart_1",
      "component": "follow-up pathway inference",
      "metric": "Capacity follow-up pathway",
      "conditions": "Apply when specialized routing criteria beyond the observed trend are required but are not supplied."
    },
    "status": "pending",
    "E": [
      {
        "ref": "chart_1",
        "location": "full chart, including axes and plotted area",
        "content": "The visible chart shows reporting years approximately 2000–2018 and physicians/doctors per 1,000, but no target, benchmark, or routing threshold is displayed."
      },
      {
        "ref": "page_00",
        "location": "right-side task instructions and pathway selector",
        "content": "The task asks for the pathway that best fits the observed end-of-period capacity pattern and provides specialized expansion and shortage pathways; it does not visibly state that a benchmark is required."
      }
    ],
    "version": 1,
    "changes": [
      {
        "from_status": null,
        "to_status": "pending",
        "reasons": [
          "The absence of a benchmark is supported, but it is not enough to establish that specialized routing requires one. The chart’s clear upward pattern and the task wording make the conclusion that only general-statistics routing is justified too strong."
        ],
        "version": 1
      }
    ]
  }
]
```

Actor 后续是否实际继续调用：**是**。最终业务提交由 Actor 自己提出，见上方真实执行时间线。

这里保留状态并传入后续调用，只证明接口与短流程链路。三个原生任务各只有一次主要读图决策，后续选择／填理由／提交不构成新的独立语义决策，因此不能据此宣称长期防复发有效；该因果效果为 **N/A**。

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [
    {
      "decision": "KEEP",
      "recommendation": "Route to the physician capacity expansion review pathway",
      "recommendation_correct": true,
      "applied_selection": "Route to the physician capacity expansion review pathway"
    }
  ],
  "actor_actual_final_submission": "Route to the physician capacity expansion review pathway",
  "actual_submission_receipt": {
    "timestamp": "2026-09-23T12:53:49.260180+00:00",
    "task_alias": "case04",
    "selected_option_token": "option_1",
    "selected_option_label": "Route to the physician capacity expansion review pathway",
    "fields": {
      "program_area": "Health workforce planning",
      "monitoring_focus": "Physician capacity relative to population",
      "routing_workflow": "Dashboard-based follow-up assignment"
    },
    "navigation": {
      "visited_task": true,
      "visited_dashboard": true,
      "visited_form": true
    },
    "server_received": true,
    "confirmation_observed": true
  },
  "offline_final_score": {
    "primary_outcome": "success",
    "real_submission": true,
    "selected_option_label": "Route to the physician capacity expansion review pathway",
    "required_editable_fields_present": true,
    "companion_exact_match_diagnostic": [
      {
        "field": "program_area",
        "type": "readonly",
        "required": false,
        "status": "readonly_public_context_not_agent_action",
        "present": null
      },
      {
        "field": "monitoring_focus",
        "type": "readonly",
        "required": false,
        "status": "readonly_public_context_not_agent_action",
        "present": null
      },
      {
        "field": "routing_workflow",
        "type": "readonly",
        "required": false,
        "status": "readonly_public_context_not_agent_action",
        "present": null
      }
    ],
    "official_full_end_to_end_score": "not_computed",
    "score_scope": "Original expected/misleading primary action lookup; separate reconstructed companion exact checks; no semantic text judging."
  }
}
```

[完整轨迹](<runs/health004_format_supplement_20260923/case04_competing_persistent/trajectory.json>)


## 结论边界

仅按上面实际轨迹判断本补充是否完成。核验推荐与落实选择、Actor 最终提交分别计数；KEEP 不是纠错，暂时选对但未提交不是完成。未执行的核验、模型输出格式错误、已执行核验后的失败不可混为一谈。

这些原生任务仍没有新的独立后续语义判断，持续规则状态防复发的因果效果为 N/A；没有去状态或等预算普通核验对照，不据此归因。

机器记录：[补充离线结果](<runs/health004_format_supplement_20260923/offline_results.json>)；[补充汇总](<HEALTH004_SUPPLEMENT_SUMMARY.json>)。

## 已发现的核验依据问题

事后只读审查发现：误导条件的数值增长读取有图内依据，但核验器用模型自己生成的 r2 去证明存在明确业务映射，又在 page_00 证据中混入该生成规则。页面本身并未明文提供 r2。因此正确提交不等于这次规则核验具有独立充分依据；接口通过也不证明语义证据合格。持久状态还继承了这一薄弱依据。

这不改变原 gold，也不表示最终扩容选择错误。它把“数值趋势读取”“合理业务解释”“独立核验证成”三个层次分开：当前记录完成了执行链路，但不能作为可靠独立规则核验已经成功的证明。

完整证据及状态覆盖限定见 [health004 核验依据审查](<HEALTH004_QUALITATIVE_CAVEAT_20260923.md>)。
