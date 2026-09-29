# Environment 35 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-07T19:53:48.468331+00:00
- Total runs: 4
- Success rate: 0/4 (0.00%)
- Outcome distribution: {'misleading_failure': 4}

## By Source Dataset

| Source Dataset | Outcomes |
|---|---|
| MisleadingChartQA | {'misleading_failure': 2} |
| visDeception | {'misleading_failure': 2} |

## By Readiness

| Readiness | Outcomes |
|---|---|
| formal_scored_task | {'misleading_failure': 2} |
| image_only_draft | {'misleading_failure': 2} |

## By Misleader Type

| Misleader Type | Outcomes |
|---|---|
| MS_inappropriate_scale_functions | {'misleading_failure': 1} |
| MS_inappropriate_scale_range | {'misleading_failure': 1} |
| MS_unconventional_scale_directions | {'misleading_failure': 1} |
| dual_encoding | {'misleading_failure': 1} |

## Task Results

| Task | Source Dataset | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| env001 | MisleadingChartQA | Temperature Change Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env017 | MisleadingChartQA | May Low-usage Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env032 | visDeception | 2010 Fuel Supply Escalation Review | misleading_failure | chart_induced_intermediate_decision_error |
| env035 | visDeception | Petroleum Price Escalation Review Routing | misleading_failure | chart_induced_intermediate_decision_error |
