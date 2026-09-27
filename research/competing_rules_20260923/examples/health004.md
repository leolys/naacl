# health004：原任务与实际防御示例

**本页保留 v2 主面板原始失败，不用补充运行覆盖。** 后续独立的两条件工程补充已完成真实提交，见 [health004 补充全过程](../HEALTH004_SUPPLEMENT_20260923.md)；但该补充存在用生成规则证明自身的核验依据问题，见 [证据审查与限定](../HEALTH004_QUALITATIVE_CAVEAT_20260923.md)。正确提交不等于独立规则核验已被证实。

这是预先固定的开发示例，不是未见测试样本。正确性标签仅在全部在线运行结束后从原任务离线评分产生，没有进入被测模型输入。

| 任务 | 图表条件 | 系统 | 首次选择提案 | 首提按原标签正确 | 最终提交选项 | 真实提交 | 主动作评分 | 状态 |
|---|---|---|---|---|---|---|---|---|
| health004 | 原误导条件 | 普通 Agent | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 原误导条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | 未提交 | 否 | completion_failure | 运行错误 |
| health004 | 对应清洁条件 | 普通 Agent | Route to the physician capacity expansion review pathway | 是 | Route to the physician capacity expansion review pathway | 是 | success | 已真实提交 |
| health004 | 对应清洁条件 | 竞争解释＋持续规则状态 | Route to the physician capacity expansion review pathway | 是 | 未提交 | 否 | completion_failure | 运行错误 |

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

![原始任务图表](<../data/case03/chart.png>)

## 原误导条件 / 普通 Agent

状态：已真实提交。主动作评分：`success`。真实提交：是。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 准备 | 确定性环境准备，非模型推理 | 准备：打开任务页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开图表页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开表单页 | 执行成功 |
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v2/case03_ordinary/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v2/case03_ordinary/step_00/actor/context.json>) |
| 0 | Actor 实际执行 | 选择：Route to the physician capacity expansion review pathway | 执行成功；当前选择=Route to the physician capacity expansion review pathway |
| 1 | Actor 提案，尚未执行 | 模型原始扁平动作名：submit（是否执行见实际回执） | [完整实际请求](<../runs/api_demo_20260923_v2/case03_ordinary/step_01/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v2/case03_ordinary/step_01/actor/context.json>) |
| 1 | 仅动作容器规范化 | 点击提交 | [原文与规范化字段](<../runs/api_demo_20260923_v2/case03_ordinary/step_01/action_representation_normalization.json>) |
| 1 | Actor 实际执行 | 点击提交 | 服务器接收并观察到确认页 |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v2/case03_ordinary/browser/browser_history.jsonl>)。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v2/case03_ordinary/browser/005_after_submit.png>)

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [],
  "actor_actual_final_submission": "Route to the physician capacity expansion review pathway",
  "actual_submission_receipt": {
    "timestamp": "2026-09-23T12:39:47.450327+00:00",
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

[完整轨迹](<../runs/api_demo_20260923_v2/case03_ordinary/trajectory.json>)

## 原误导条件 / 竞争解释＋持续规则状态

状态：运行错误。主动作评分：`completion_failure`。真实提交：否。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v2/case03_competing_persistent/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v2/case03_competing_persistent/step_00/actor/context.json>) |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v2/case03_competing_persistent/browser/browser_history.jsonl>)。

实际错误：`ValueError: invalid candidate count`。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v2/case03_competing_persistent/browser/002_actor_input_00.png>)

### 本方法的真实防御记录

下面记录模型实际生成的简短可检验论证，不补写正确答案或未生成的数值。O 是可见观察，B 是解释规则，结论是该动作是否符合公开任务。

此轨迹没有已完成的核验事件。不能将未进入核验／核验执行失败记成核验成功或已执行核验后的失败。

首次选择提案（尚未执行）：

```json
{
  "action": {
    "kind": "select",
    "option": "Route to the physician capacity expansion review pathway"
  },
  "brief_basis": "The chart’s numeric values rise from about 1.3 to 2.4 physicians per 1,000 residents by the end of the period; the y-axis is inverted.",
  "used_rule_ids": [],
  "new_evidence": "",
  "challenge_previous_verification": false
}
```

#### 第 00 步：候选解释与核验

候选生成器已有实际输出，但未通过当前接口规范化；以下不是已完成的核验：

```json
{
  "rules": [
    {
      "id": "r1",
      "text": "Read the plotted values from the numeric y-axis labels; because the axis increases downward, a lower visual position represents a higher physicians-per-1,000 value.",
      "component": "y-axis and line position",
      "conditions": "Applies when interpreting the chart’s vertical encoding."
    },
    {
      "id": "r2",
      "text": "When the measured physicians-per-1,000 value rises over the reporting period and ends at a higher level, treat the end-period pattern as increased capacity for routing purposes.",
      "component": "trend and capacity follow-up mapping",
      "conditions": "Conditional inference; the supplied task does not explicitly define how capacity levels map to pathways."
    },
    {
      "id": "r3",
      "text": "If visual movement is interpreted without accounting for the inverted numeric axis, a downward-sloping line may be treated as declining capacity.",
      "component": "y-axis and line direction",
      "conditions": "Competing interpretation that ignores the numeric direction of the displayed scale."
    },
    {
      "id": "r4",
      "text": "If no explicit rule links an observed capacity level or trend to a specialized pathway, the chart may support only a general statistics route.",
      "component": "task routing decision",
      "conditions": "Applies because the supplied task provides pathway labels but no formal threshold or routing policy."
    }
  ],
  "chains": [
    {
      "observations": [
        {
          "ref": "chart_1",
          "location": "line from 2000 to the final plotted year",
          "content": "The plotted physicians-per-1,000 values rise approximately from 1.3 to 2.4; the line moves downward visually because the y-axis values increase downward."
        }
      ],
      "rule_id": "r1",
      "option_label": "Route to the physician capacity expansion review pathway",
      "claim": "The end-of-period numeric capacity is higher than at the start."
    },
    {
      "observations": [
        {
          "ref": "chart_1",
          "location": "final plotted point",
          "content": "The final point is approximately 2.4 physicians per 1,000 inhabitants, above the initial point near 1.3."
        }
      ],
      "rule_id": "r2",
      "option_label": "Route to the physician capacity expansion review pathway",
      "claim": "Under the proposed capacity interpretation, the rising end-period pattern supports the expansion review route, although the chart supplies no explicit policy mapping."
    },
    {
      "observations": [
        {
          "ref": "chart_1",
          "location": "overall visual line direction",
          "content": "The line slopes downward from left to right on the displayed chart."
        }
      ],
      "rule_id": "r3",
      "option_label": "Route to the physician shortage response review pathway",
      "claim": "A reader who mistakes visual descent for numeric decline could infer worsening physician capacity."
    },
    {
      "observations": [
        {
          "ref": "chart_1",
          "location": "chart title, axes, and plotted series",
          "content": "The chart shows a physician-per-1,000 trend but no stated thresholds or routing criteria."
        }
      ],
      "rule_id": "r4",
      "option_label": "Route to the general health system statistics page",
      "claim": "Without an explicit mapping from the observed level to a specialized pathway, a general statistics route remains a possible explanation."
    }
  ]
}
```

输入证据：[generate 完整请求](<../runs/api_demo_20260923_v2/case03_competing_persistent/step_00/defense/generate/request.json>)。

Actor 后续是否实际继续调用：**否**。最终业务提交由 Actor 自己提出，见上方真实执行时间线。

这里保留状态并传入后续调用，只证明接口与短流程链路。三个原生任务各只有一次主要读图决策，后续选择／填理由／提交不构成新的独立语义决策，因此不能据此宣称长期防复发有效；该因果效果为 **N/A**。

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [],
  "actor_actual_final_submission": null,
  "actual_submission_receipt": null,
  "offline_final_score": {
    "primary_outcome": "completion_failure",
    "real_submission": false,
    "selected_option_label": "",
    "required_editable_fields_present": false,
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

[完整轨迹](<../runs/api_demo_20260923_v2/case03_competing_persistent/trajectory.json>)

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

![原始任务图表](<../data/case04/chart.png>)

## 对应清洁条件 / 普通 Agent

状态：已真实提交。主动作评分：`success`。真实提交：是。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 准备 | 确定性环境准备，非模型推理 | 准备：打开任务页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开图表页 | 执行成功 |
| 准备 | 确定性环境准备，非模型推理 | 准备：打开表单页 | 执行成功 |
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v2/case04_ordinary/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v2/case04_ordinary/step_00/actor/context.json>) |
| 0 | Actor 实际执行 | 选择：Route to the physician capacity expansion review pathway | 执行成功；当前选择=Route to the physician capacity expansion review pathway |
| 1 | Actor 提案，尚未执行 | 点击提交 | [完整实际请求](<../runs/api_demo_20260923_v2/case04_ordinary/step_01/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v2/case04_ordinary/step_01/actor/context.json>) |
| 1 | Actor 实际执行 | 点击提交 | 服务器接收并观察到确认页 |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v2/case04_ordinary/browser/browser_history.jsonl>)。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v2/case04_ordinary/browser/005_after_submit.png>)

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [],
  "actor_actual_final_submission": "Route to the physician capacity expansion review pathway",
  "actual_submission_receipt": {
    "timestamp": "2026-09-23T12:41:09.331708+00:00",
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

[完整轨迹](<../runs/api_demo_20260923_v2/case04_ordinary/trajectory.json>)

## 对应清洁条件 / 竞争解释＋持续规则状态

状态：运行错误。主动作评分：`completion_failure`。真实提交：否。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v2/case04_competing_persistent/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v2/case04_competing_persistent/step_00/actor/context.json>) |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v2/case04_competing_persistent/browser/browser_history.jsonl>)。

实际错误：`RuntimeError: API call failed: JSONDecodeError: Extra data: line 1 column 2438 (char 2437)`。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v2/case04_competing_persistent/browser/002_actor_input_00.png>)

### 本方法的真实防御记录

下面记录模型实际生成的简短可检验论证，不补写正确答案或未生成的数值。O 是可见观察，B 是解释规则，结论是该动作是否符合公开任务。

此轨迹没有已完成的核验事件。不能将未进入核验／核验执行失败记成核验成功或已执行核验后的失败。

首次选择提案（尚未执行）：

```json
{
  "action": {
    "kind": "select",
    "option": "Route to the physician capacity expansion review pathway"
  },
  "brief_basis": "The dashboard shows physicians per 1,000 inhabitants rising from about 1.3 in 2000 to 2.4 at the end of the reporting period.",
  "used_rule_ids": [],
  "new_evidence": "",
  "challenge_previous_verification": false
}
```

#### 第 00 步：候选解释与核验

候选生成调用未得到可接受的解析结果；以下是原始响应文本，不作已执行论证或核验建议：

```json
{
  "raw_model_content": "{\"rules\":[{\"id\":\"r1\",\"text\":\"A sustained upward trajectory in the measured capacity indicator represents increasing capacity over the reporting period.\",\"component\":\"chart_1 line series and vertical measure axis\",\"conditions\":\"Use when successive plotted values generally rise from the beginning to the end of the period.\"},{\"id\":\"r2\",\"text\":\"When the observed end-of-period pattern indicates increasing capacity, the follow-up interpretation should favor capacity-growth review rather than shortage-response review.\",\"component\":\"capacity follow-up pathway\",\"conditions\":\"Use when the chart shows an upward capacity pattern and no supplied rule reverses that interpretation.\"},{\"id\":\"r3\",\"text\":\"The highest observed endpoint can independently support treating the record as an expansion-oriented capacity case, even without an explicit numeric threshold.\",\"component\":\"chart_1 endpoint and capacity follow-up pathway\",\"conditions\":\"Use when the endpoint is visibly above the starting level and the task requires routing based on the observed end pattern.\"}],\"chains\":[{\"observations\":[{\"ref\":\"chart_1\",\"location\":\"line series from the first plotted year to the final plotted year\",\"content\":\"Physicians per 1,000 inhabitants rise overall from about 1.3 to about 2.4, with only a small mid-period dip.\"}],\"rule_id\":\"r1\",\"option_label\":\"Route to the physician capacity expansion review pathway\",\"claim\":\"The sustained increase indicates an expanding physician-capacity pattern, supporting the proposed expansion review route.\"},{\"observations\":[{\"ref\":\"chart_1\",\"location\":\"final plotted point relative to the first plotted point\",\"content\":\"The final value is visibly the highest point in the series and is well above the starting value.\"}],\"rule_id\":\"r3\",\"option_label\":\"Route to the physician capacity expansion review pathway\",\"claim\":\"The elevated end-of-period capacity independently fits an expansion-oriented review; the chart supplies no explicit threshold, so this remains an interpretive mapping.\"},{\"observations\":[{\"ref\":\"chart_1\",\"location\":\"full visible series\",\"content\":\"The series trends upward across the reporting period rather than downward.\"}],\"rule_id\":\"r2\",\"option_label\":\"Route to the physician capacity expansion review pathway\",\"claim\":\"Given the upward capacity pattern, expansion review is a better fit than a shortage-response route, although the supplied task does not state a formal routing threshold.\"}]}]}"
}
```

[未解析的完整实际响应](<../runs/api_demo_20260923_v2/case04_competing_persistent/step_00/defense/generate/response_01.json>)

输入证据：[generate 完整请求](<../runs/api_demo_20260923_v2/case04_competing_persistent/step_00/defense/generate/request.json>)。

Actor 后续是否实际继续调用：**否**。最终业务提交由 Actor 自己提出，见上方真实执行时间线。

这里保留状态并传入后续调用，只证明接口与短流程链路。三个原生任务各只有一次主要读图决策，后续选择／填理由／提交不构成新的独立语义决策，因此不能据此宣称长期防复发有效；该因果效果为 **N/A**。

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [],
  "actor_actual_final_submission": null,
  "actual_submission_receipt": null,
  "offline_final_score": {
    "primary_outcome": "completion_failure",
    "real_submission": false,
    "selected_option_label": "",
    "required_editable_fields_present": false,
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

[完整轨迹](<../runs/api_demo_20260923_v2/case04_competing_persistent/trajectory.json>)
