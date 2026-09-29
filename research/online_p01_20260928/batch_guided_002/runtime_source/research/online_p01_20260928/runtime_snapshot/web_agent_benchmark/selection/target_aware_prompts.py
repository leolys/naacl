"""Prompts for target-aware GPT-5.4 visual screening."""

SYSTEM_PROMPT = """You are designing a benchmark for visualization-grounded web-agent task execution.

For each candidate chart, identify the intermediate chart-reading decision that
would actually be vulnerable to the chart's misleading visualization technique.
Do not default to max/min unless that is truly the target of the misleading design.

The final benchmark will convert your intermediate decision spec into a web task:
the agent reads the dashboard, then performs a downstream web action on the
selected entity/period/series/status. Your job is to create a decision spec that
matches the misleading mechanism and can be checked from the CSV.

Return strict JSON only. No markdown, no prose outside JSON.
"""


USER_PROMPT_TEMPLATE = """Analyze this candidate for scenario "{scenario}".

Allowed reasoning_operation values:
- extreme_value: choose entity with highest/lowest true metric.
- pairwise_comparison: compare exactly two entities.
- rank_order: choose top entity or top-k by true metric.
- trend_direction: decide whether one time series increases/decreases/stays stable.
- largest_change: choose entity/period with largest absolute change.
- rate_of_change: choose entity/period with largest relative change.
- axis_or_scale_interpretation: account for reversed/inverted axis or scale.
- visual_size_vs_data_value: choose by true data despite misleading visual size/area.
- unsupported: use this if the best misleading target cannot be checked from CSV by the listed operations.

Candidate metadata and CSV summary:
{candidate_json}

Important guidance by misleader type:
- cherry_picking: prefer full-period trend/change, not a visible local max.
- inappropriate order: prefer temporal/order reasoning if applicable.
- inappropriate scale range/functions: prefer true magnitude, difference, rank, or change hidden by scale.
- unconventional scale directions: prefer axis_or_scale_interpretation, but decision_rule must still be max/min directly over the CSV metric column.
- data visual disproportion: prefer visual_size_vs_data_value.
- missing normalization: use unsupported unless a normalized field is present in CSV.
- concealed uncertainty: use unsupported unless uncertainty can be programmatically compared.
- overplotting: use unsupported unless group trend/density is represented in columns.
- misuse of cumulative relationship: use unsupported unless a component-vs-total target can be expressed using listed operations.
- lack of legend: use unsupported unless series identity can be checked from CSV.
- misleading annotations: use unsupported unless the data-conflict target can be reduced to a listed operation.

Return exactly this JSON object:
{{
  "keep": true,
  "scenario": "{scenario}",
  "misleading_mechanism": "",
  "misleading_target": "",
  "expected_visual_trap": "",
  "reasoning_operation": "extreme_value",
  "target_entity_column": "",
  "target_metric_columns": [],
  "time_column": null,
  "comparison_entities": [],
  "top_k": 1,
  "decision_rule": "max",
  "ground_truth_computation": "",
  "web_action_goal": "",
  "workflow_instruction": "",
  "scenario_fit_score": 1,
  "misleading_alignment_score": 1,
  "workflow_suitability_score": 1
}}

decision_rule must be one of:
- max
- min

Do not use invert_then_max or invert_then_min in final task specs. If a chart has an inverted visual scale,
describe the visual trap in misleading_mechanism/expected_visual_trap, but set decision_rule to the direct
CSV computation rule over target_metric_columns[0].

workflow_instruction must require a downstream web action, not merely answer a chart question.
If the sample is not suitable, set keep=false and explain why in misleading_mechanism.
"""
