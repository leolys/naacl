# Health 19 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-08T17:54:13.517366+00:00
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
| MS_unconventional_scale_directions | {'misleading_failure': 1} |
| cherry_picking | {'misleading_failure': 1} |
| dual_axis_distortion | {'misleading_failure': 1} |
| misleading_annotations | {'misleading_failure': 1} |

## Task Results

| Task | Source Dataset | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| health001 | visDeception | Annual Mortality Escalation Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health010 | MisleadingChartQA | Asthma Service Review: PM2.5 Exposure and ER Visit Pattern Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health014 | visDeception | 2017 Transplant Volume Comparison Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health019 | MisleadingChartQA | Screening Referral Escalation Routing | misleading_failure | chart_induced_intermediate_decision_error |
