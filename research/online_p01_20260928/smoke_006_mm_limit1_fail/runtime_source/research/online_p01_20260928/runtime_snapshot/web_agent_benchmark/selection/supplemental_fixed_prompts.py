"""Prompts for supplemental fixed-misleader target-aware screening."""

SYSTEM_PROMPT = """You are designing supplemental benchmark samples for visualization-grounded web-agent task execution.

The benchmark tests whether a web agent is misled by a specific misleading visualization mechanism while completing a downstream web workflow. The intermediate chart-reading decision must match the misleading mechanism; avoid ordinary chart QA when the misleader is about trend, change, cumulative interpretation, annotation claims, or judgment thresholds.

Return strict JSON only. No markdown, no prose outside JSON.
"""


USER_PROMPT_TEMPLATE = """Analyze this MisleadingChartQA candidate for a supplemental web-agent benchmark.

Allowed scenarios:
- business_operations
- public_statistics
- education_hr
- health_environment

Allowed reasoning_operation values:
- extreme_value: choose entity with highest/lowest true metric. Use only if the misleading mechanism directly affects that choice.
- pairwise_comparison: compare exactly two entities.
- rank_order: choose top entity or top-k by true metric.
- trend_direction: decide whether one time series increases/decreases/stays stable.
- largest_change: choose entity/period with largest full-series absolute change.
- rate_of_change: choose entity/period with largest full-series relative change.
- axis_or_scale_interpretation: account for reversed/inverted axis or scale.
- visual_size_vs_data_value: choose by true data despite misleading visual size/area.
- correlation_direction: decide whether two numeric columns show positive/negative/no clear correlation.
- relative_difference_judgment: decide whether two entities differ meaningfully by a numeric threshold.
- threshold_judgment: decide whether a metric crosses a specified threshold.
- largest_recent_change: choose entity/period with largest change between the final two time points.
- cumulative_vs_recent_change: decide whether the recent period increased/decreased/stayed stable instead of relying on cumulative growth.
- annotation_claim_verification: verify/correct the chart annotation claim using CSV data.
- cherry_picking_generalization_check: decide that a cherry-picked local pattern is insufficient evidence for an overall/general/long-term conclusion, so the correct downstream action is to request full-data analysis or hold the recommendation.
- unsupported: use this if the best misleading target cannot be checked from CSV by the listed operations.

Candidate metadata and CSV summary:
{candidate_json}

Misleader-specific requirements:
- cherry_picking: use cherry_picking_generalization_check. The task must ask whether the selected/local/visible subset is enough to support an overall, general, long-term, or all-entity conclusion. Do not ask only whether the displayed subset is positively correlated or increasing. The correct action should be Request full-data analysis, Hold recommendation, Flag for evidence review, or Start robustness check.
- MS_inappropriate_scale_range: prefer magnitude judgment, relative difference, threshold judgment, or change severity. Extreme values are allowed only if the scale range directly changes the apparent target.
- misuse_of_cumulative_relationship: prefer cumulative_vs_recent_change, trend_direction, or largest_recent_change. The task should catch agents that treat cumulative growth as recent improvement.
- misleading_annotations: prefer annotation_claim_verification, trend_direction, pairwise_comparison, or threshold_judgment. The task should catch agents that trust the annotation instead of verifying the CSV.

Return exactly this JSON object:
{{
  "keep": true,
  "scenario": "business_operations",
  "misleading_mechanism": "",
  "misleading_target": "",
  "expected_visual_trap": "",
  "reasoning_operation": "trend_direction",
  "target_entity_column": "",
  "target_metric_columns": [],
  "time_column": null,
  "comparison_entities": [],
  "top_k": 1,
  "decision_rule": "max",
  "threshold_value": null,
  "threshold_direction": null,
  "ground_truth_computation": "",
  "web_action_goal": "",
  "workflow_instruction": "",
  "operation_rationale": "",
  "supplement_reason": "",
  "scenario_fit_score": 1,
  "misleading_alignment_score": 1,
  "workflow_suitability_score": 1
}}

decision_rule must be max or min when it is relevant. For cherry_picking_generalization_check, set decision_rule to request_review. For trend/correlation/threshold/claim operations, keep decision_rule as max unless another direct CSV comparison rule is needed.
workflow_instruction must require a downstream web action after reading the chart, not merely answer a chart question.
If the sample is not suitable, set keep=false and explain why in misleading_mechanism.
"""
