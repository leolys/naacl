# health004：原任务与实际防御示例

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
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v1/case03_ordinary/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v1/case03_ordinary/step_00/actor/context.json>) |
| 0 | Actor 实际执行 | 选择：Route to the physician capacity expansion review pathway | 执行成功；当前选择=Route to the physician capacity expansion review pathway |
| 1 | Actor 提案，尚未执行 | 点击提交 | [完整实际请求](<../runs/api_demo_20260923_v1/case03_ordinary/step_01/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v1/case03_ordinary/step_01/actor/context.json>) |
| 1 | Actor 实际执行 | 点击提交 | 服务器接收并观察到确认页 |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v1/case03_ordinary/browser/browser_history.jsonl>)。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v1/case03_ordinary/browser/005_after_submit.png>)

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [],
  "actor_actual_final_submission": "Route to the physician capacity expansion review pathway",
  "actual_submission_receipt": {
    "timestamp": "2026-09-23T12:23:11.081954+00:00",
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

[完整轨迹](<../runs/api_demo_20260923_v1/case03_ordinary/trajectory.json>)

## 原误导条件 / 竞争解释＋持续规则状态

状态：运行错误。主动作评分：`completion_failure`。真实提交：否。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v1/case03_competing_persistent/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v1/case03_competing_persistent/step_00/actor/context.json>) |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v1/case03_competing_persistent/browser/browser_history.jsonl>)。

实际错误：`ValueError: evidence must reference actual chart observation`。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v1/case03_competing_persistent/browser/002_actor_input_00.png>)

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
  "brief_basis": "The chart shows physicians per 1,000 inhabitants increasing over the reporting period, reaching its highest level at the end.",
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
      "text": "A routing decision requiring a shortage threshold cannot be established unless the chart or task supplies a shortage benchmark or shows a declining/low end-of-period pattern.",
      "component": "chart_1 and task routing options",
      "conditions": "Applies when no explicit threshold or shortage definition is provided."
    },
    {
      "id": "r2",
      "text": "A sustained rise in the measured capacity indicator, ending at its highest observed level, is evidence for a capacity-expansion-oriented follow-up interpretation.",
      "component": "chart_1 time series",
      "conditions": "Applies when the end-of-period value exceeds the beginning value and the series is predominantly rising."
    }
  ],
  "chains": [
    {
      "chain_id": "c1",
      "observations": [
        {
          "ref": "chart_1",
          "location": "line series from start to endpoint",
          "content": "The endpoint is visibly higher by the labeled scale than the starting point, rather than showing a decline."
        }
      ],
      "rule_id": "r1",
      "option_label": "Route to the physician shortage response review pathway",
      "claim": "A shortage response is not directly supported because the observed series rises and the task provides no shortage cutoff."
    },
    {
      "chain_id": "c2",
      "observations": [
        {
          "ref": "chart_1",
          "location": "line series from 2000 through 2018",
          "content": "Using the y-axis labels, the plotted value rises from approximately 1.3 to approximately 2.4 physicians per 1,000 inhabitants, with the final point highest."
        }
      ],
      "rule_id": "r2",
      "option_label": "Route to the physician capacity expansion review pathway",
      "claim": "The observed end-of-period pattern is rising capacity, so the expansion review pathway best fits the proposed interpretation."
    },
    {
      "chain_id": "c3",
      "observations": [
        {
          "ref": "chart_1",
          "location": "line series and y-axis",
          "content": "The series trends toward higher labeled values over time and finishes at its highest visible level; no shortage threshold is shown."
        }
      ],
      "rule_id": "r1",
      "option_label": "Route to the general health system statistics page",
      "claim": "Without a supplied benchmark, the chart alone does not establish a shortage-triggered route; general statistics is a defensible alternative."
    }
  ]
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
      "implication": "refuted",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "line series from 2000 to 2018 and y-axis labels",
          "content": "The plotted value increases numerically from about 1.3 to about 2.4 physicians per 1,000 inhabitants, with the endpoint highest. No explicit shortage benchmark is visible."
        },
        {
          "ref": "page_00",
          "location": "dashboard reference and task text",
          "content": "The task asks for the pathway best fitting the observed end-of-period capacity pattern; it supplies no shortage cutoff or shortage definition."
        }
      ],
      "reason": "The observation and shortage rule are applicable, but they support lack of direct shortage evidence rather than the shortage-response route."
    },
    {
      "chain_id": "c2",
      "O": "supported",
      "B": "supported",
      "implication": "supported",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "line series from 2000 through 2018",
          "content": "Using the numeric y-axis labels, the series rises from approximately 1.3 to approximately 2.4 physicians per 1,000 inhabitants. There is a small mid-period dip, but the overall pattern is predominantly rising and the final point is the highest."
        },
        {
          "ref": "page_00",
          "location": "task instructions and capacity follow-up pathway field",
          "content": "The stated monitoring focus is physician capacity relative to population, and the task requests routing based on the end-of-period capacity pattern."
        }
      ],
      "reason": "The observed predominantly rising series ending at its highest numeric level satisfies the expansion-oriented interpretation and best fits that follow-up pathway."
    },
    {
      "chain_id": "c3",
      "O": "supported",
      "B": "supported",
      "implication": "undetermined",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "line series and y-axis",
          "content": "The numeric series trends upward and ends near 2.4 physicians per 1,000 inhabitants; no shortage threshold is visible."
        },
        {
          "ref": "page_00",
          "location": "task instructions",
          "content": "The task provides a choice among a general statistics page, expansion review, and shortage response, but does not state that absence of a shortage benchmark should be routed to the general statistics page."
        }
      ],
      "reason": "The rule supports rejecting an unsupported shortage trigger, but it does not establish that the general statistics page is the best route when the chart shows a predominantly rising capacity pattern."
    }
  ],
  "recommendation": "Route to the physician capacity expansion review pathway",
  "unresolved_reason": ""
}
```

输入证据：[generate 完整请求](<../runs/api_demo_20260923_v1/case03_competing_persistent/step_00/defense/generate/request.json>)。

输入证据：[verify 完整请求](<../runs/api_demo_20260923_v1/case03_competing_persistent/step_00/defense/verify/request.json>)。

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

[完整轨迹](<../runs/api_demo_20260923_v1/case03_competing_persistent/trajectory.json>)

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
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v1/case04_ordinary/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v1/case04_ordinary/step_00/actor/context.json>) |
| 0 | Actor 实际执行 | 选择：Route to the physician capacity expansion review pathway | 执行成功；当前选择=Route to the physician capacity expansion review pathway |
| 1 | Actor 提案，尚未执行 | 点击提交 | [完整实际请求](<../runs/api_demo_20260923_v1/case04_ordinary/step_01/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v1/case04_ordinary/step_01/actor/context.json>) |
| 1 | Actor 实际执行 | 点击提交 | 服务器接收并观察到确认页 |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v1/case04_ordinary/browser/browser_history.jsonl>)。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v1/case04_ordinary/browser/005_after_submit.png>)

### 三层记录与离线评分

```json
{
  "first_actor_proposal": "Route to the physician capacity expansion review pathway",
  "verification_recommendation_and_applied_selection": [],
  "actor_actual_final_submission": "Route to the physician capacity expansion review pathway",
  "actual_submission_receipt": {
    "timestamp": "2026-09-23T12:26:50.028226+00:00",
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

[完整轨迹](<../runs/api_demo_20260923_v1/case04_ordinary/trajectory.json>)

## 对应清洁条件 / 竞争解释＋持续规则状态

状态：运行错误。主动作评分：`completion_failure`。真实提交：否。

### 真实请求、提案与执行时间线

模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。

| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |
|---|---|---|---|
| 0 | Actor 提案，尚未执行 | 选择：Route to the physician capacity expansion review pathway | [完整实际请求](<../runs/api_demo_20260923_v1/case04_competing_persistent/step_00/actor/request.json>)；[可读输入与图像引用](<../runs/api_demo_20260923_v1/case04_competing_persistent/step_00/actor/context.json>) |

浏览器原始执行日志：[browser_history.jsonl](<../runs/api_demo_20260923_v1/case04_competing_persistent/browser/browser_history.jsonl>)。

实际错误：`ValueError: evidence must reference actual chart observation`。

最后观察到的实际页面：

![真实最后页面](<../runs/api_demo_20260923_v1/case04_competing_persistent/browser/002_actor_input_00.png>)

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
  "brief_basis": "The chart rises from about 1.3 physicians per 1,000 residents in 2000 to about 2.4 at the end of the period, indicating expanding capacity.",
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
      "text": "A sustained upward trend in the physicians-per-1,000-residents measure indicates increasing physician capacity over the reporting period.",
      "component": "chart trend and y-axis measure",
      "conditions": "Compare the beginning and end of the displayed reporting period."
    },
    {
      "id": "r2",
      "text": "A capacity-routing decision cannot distinguish expansion from shortage using trend alone when no benchmark or threshold is supplied.",
      "component": "y-axis level and routing interpretation",
      "conditions": "Apply when the chart provides no stated target, adequacy threshold, or comparison population."
    }
  ],
  "chains": [
    {
      "chain_id": "c1",
      "observations": [
        {
          "ref": "chart_1",
          "location": "plotted line from 2000 to the final year",
          "content": "The physicians-per-1,000-inhabitants measure rises overall from about 1.3 to about 2.4, with only a minor early dip."
        }
      ],
      "rule_id": "r1",
      "option_label": "Route to the physician capacity expansion review pathway",
      "claim": "The observed end-of-period pattern is increasing physician capacity, supporting the expansion review pathway."
    },
    {
      "chain_id": "c2",
      "observations": [
        {
          "ref": "chart_1",
          "location": "y-axis and plotted series",
          "content": "The chart shows the capacity measure and its trend but no adequacy target, shortage threshold, or external benchmark."
        }
      ],
      "rule_id": "r2",
      "option_label": "Route to the general health system statistics page",
      "claim": "The trend supports increasing capacity, but the chart alone does not establish whether the level warrants an expansion or shortage pathway."
    }
  ]
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
          "location": "plotted series from approximately 2000 to 2018",
          "content": "The measure rises from about 1.3 to about 2.4 physicians per 1,000 inhabitants, with a small early dip. Values are approximate readings."
        },
        {
          "ref": "page_00",
          "location": "Submit decision instructions",
          "content": "The task asks for the pathway that best fits the observed end-of-period capacity pattern."
        }
      ],
      "reason": "The observed increase supports the trend rule. Among the listed pathways, expansion review best fits an increasing capacity pattern; this does not establish that capacity is adequate."
    },
    {
      "chain_id": "c2",
      "O": "supported",
      "B": "refuted",
      "implication": "refuted",
      "evidence": [
        {
          "ref": "chart_1",
          "location": "axes and plotted series",
          "content": "The chart shows a rising physicians-per-1,000 measure and no visible adequacy target, shortage threshold, or comparison population."
        },
        {
          "ref": "page_00",
          "location": "Submit decision instructions",
          "content": "Routing is based on the observed end-of-period capacity pattern, not an assessment against an adequacy threshold."
        }
      ],
      "reason": "The missing benchmark prevents an adequacy judgment, but does not prevent the trend-based routing this task requests. It therefore does not justify the general statistics pathway."
    }
  ],
  "recommendation": "Route to the physician capacity expansion review pathway",
  "unresolved_reason": ""
}
```

输入证据：[generate 完整请求](<../runs/api_demo_20260923_v1/case04_competing_persistent/step_00/defense/generate/request.json>)。

输入证据：[verify 完整请求](<../runs/api_demo_20260923_v1/case04_competing_persistent/step_00/defense/verify/request.json>)。

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

[完整轨迹](<../runs/api_demo_20260923_v1/case04_competing_persistent/trajectory.json>)
