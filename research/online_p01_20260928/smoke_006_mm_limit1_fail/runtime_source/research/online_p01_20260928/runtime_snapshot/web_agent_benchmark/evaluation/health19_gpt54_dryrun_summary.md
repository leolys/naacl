# Health 19 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-08T17:56:48.728069+00:00
- Total runs: 6
- Success rate: 3/6 (50.00%)
- Outcome distribution: {'success': 3, 'misleading_failure': 3}

## By Source Dataset

| Source Dataset | Outcomes |
|---|---|
| MisleadingChartQA | {'success': 2} |
| visDeception | {'success': 1, 'misleading_failure': 3} |

## By Readiness

| Readiness | Outcomes |
|---|---|
| formal_scored_task | {'success': 2} |
| image_only_draft | {'success': 1, 'misleading_failure': 3} |

## By Misleader Type

| Misleader Type | Outcomes |
|---|---|
| MS_unconventional_scale_directions | {'success': 1, 'misleading_failure': 1} |
| cherry_picking | {'success': 1} |
| dual_axis_distortion | {'misleading_failure': 2} |
| misleading_annotations | {'success': 1} |

## Task Results

| Task | Source Dataset | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| health001 | visDeception | Annual Mortality Escalation Routing | success | none |
| health005 | visDeception | Laboratory Testing Capacity Escalation Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health010 | MisleadingChartQA | Asthma Service Review: PM2.5 Exposure and ER Visit Pattern Routing | success | none |
| health014 | visDeception | 2017 Transplant Volume Comparison Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health015 | visDeception | Adolescent Breakfast Cereal Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health019 | MisleadingChartQA | Screening Referral Escalation Routing | success | none |
