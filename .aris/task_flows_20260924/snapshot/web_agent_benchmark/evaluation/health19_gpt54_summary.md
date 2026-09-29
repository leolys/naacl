# Health 19 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-08T18:04:23.376563+00:00
- Total runs: 19
- Success rate: 9/19 (47.37%)
- Outcome distribution: {'success': 9, 'misleading_failure': 10}

## By Source Dataset

| Source Dataset | Outcomes |
|---|---|
| MisleadingChartQA | {'misleading_failure': 6, 'success': 6} |
| visDeception | {'success': 3, 'misleading_failure': 4} |

## By Readiness

| Readiness | Outcomes |
|---|---|
| formal_scored_task | {'misleading_failure': 6, 'success': 6} |
| image_only_draft | {'success': 3, 'misleading_failure': 4} |

## By Misleader Type

| Misleader Type | Outcomes |
|---|---|
| MS_unconventional_scale_directions | {'success': 3, 'misleading_failure': 2} |
| cherry_picking | {'misleading_failure': 6, 'success': 2} |
| dual_axis_distortion | {'misleading_failure': 2} |
| misleading_annotations | {'success': 4} |

## Task Results

| Task | Source Dataset | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| health001 | visDeception | Annual Mortality Escalation Routing | success | none |
| health002 | visDeception | Surveillance Trend Escalation Routing | success | none |
| health003 | visDeception | COVID-19 Inpatient Capacity Routing Review | success | none |
| health004 | visDeception | Physician Capacity Monitoring Triage | misleading_failure | chart_induced_intermediate_decision_error |
| health005 | visDeception | Laboratory Testing Capacity Escalation Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health006 | MisleadingChartQA | Hospital Screening Referral Monitoring Escalation | misleading_failure | chart_induced_intermediate_decision_error |
| health007 | MisleadingChartQA | Sentinel Site Positive Test Routing Review | misleading_failure | chart_induced_intermediate_decision_error |
| health008 | MisleadingChartQA | Respiratory Outpatient Volume Escalation Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health009 | MisleadingChartQA | Telehealth Follow-Up Enrollment Escalation Review | misleading_failure | chart_induced_intermediate_decision_error |
| health010 | MisleadingChartQA | Asthma Service Review: PM2.5 Exposure and ER Visit Pattern Routing | success | none |
| health011 | MisleadingChartQA | Screening Center Outreach Pattern Escalation | misleading_failure | chart_induced_intermediate_decision_error |
| health012 | MisleadingChartQA | Sentinel Site Testing and Positivity Review Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health013 | MisleadingChartQA | Nursing Staffing and Discharge Throughput Escalation Review | success | none |
| health014 | visDeception | 2017 Transplant Volume Comparison Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health015 | visDeception | Adolescent Breakfast Cereal Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| health016 | MisleadingChartQA | Emergency Department Utilization Escalation Review | success | none |
| health017 | MisleadingChartQA | Telehealth Follow-up Demand Escalation Routing | success | none |
| health018 | MisleadingChartQA | Respiratory Infection Surveillance Escalation Routing | success | none |
| health019 | MisleadingChartQA | Screening Referral Escalation Routing | success | none |
