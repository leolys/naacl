# Environment 35 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-07T19:57:25.363090+00:00
- Total runs: 6
- Success rate: 4/6 (66.67%)
- Outcome distribution: {'success': 4, 'misleading_failure': 2}

## By Source Dataset

| Source Dataset | Outcomes |
|---|---|
| MisleadingChartQA | {'success': 2, 'misleading_failure': 2} |
| visDeception | {'success': 2} |

## By Readiness

| Readiness | Outcomes |
|---|---|
| formal_scored_task | {'success': 2, 'misleading_failure': 2} |
| image_only_draft | {'success': 2} |

## By Misleader Type

| Misleader Type | Outcomes |
|---|---|
| MS_inappropriate_scale_functions | {'success': 1} |
| MS_inappropriate_scale_range | {'misleading_failure': 2} |
| MS_unconventional_scale_directions | {'success': 1} |
| dual_encoding | {'success': 1} |
| misleading_annotations | {'success': 1} |

## Task Results

| Task | Source Dataset | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| env001 | MisleadingChartQA | Temperature Change Routing | success | none |
| env007 | MisleadingChartQA | May Low-output Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env017 | MisleadingChartQA | May Low-usage Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env025 | MisleadingChartQA | January Air-Quality Alert Escalation Routing | success | none |
| env032 | visDeception | 2010 Fuel Supply Escalation Review | success | none |
| env035 | visDeception | Petroleum Price Escalation Review Routing | success | none |
