# Environment 35 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-07T20:12:48.428200+00:00
- Total runs: 35
- Success rate: 22/35 (62.86%)
- Outcome distribution: {'success': 22, 'misleading_failure': 13}

## By Source Dataset

| Source Dataset | Outcomes |
|---|---|
| MisleadingChartQA | {'success': 18, 'misleading_failure': 13} |
| visDeception | {'success': 4} |

## By Readiness

| Readiness | Outcomes |
|---|---|
| formal_scored_task | {'success': 18, 'misleading_failure': 13} |
| image_only_draft | {'success': 4} |

## By Misleader Type

| Misleader Type | Outcomes |
|---|---|
| MS_inappropriate_scale_functions | {'success': 12, 'misleading_failure': 2} |
| MS_inappropriate_scale_range | {'misleading_failure': 5} |
| MS_unconventional_scale_directions | {'success': 1} |
| data_visual_disproportion | {'success': 3, 'misleading_failure': 2} |
| dual_encoding | {'success': 3} |
| misleading_annotations | {'success': 3, 'misleading_failure': 4} |

## Task Results

| Task | Source Dataset | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| env001 | MisleadingChartQA | Temperature Change Routing | success | none |
| env002 | MisleadingChartQA | Temperature Trend Follow-Up Routing | success | none |
| env003 | MisleadingChartQA | Energy Portfolio Escalation Review | success | none |
| env004 | MisleadingChartQA | Energy Source Escalation Routing | success | none |
| env005 | MisleadingChartQA | Energy Source Escalation Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env006 | MisleadingChartQA | Energy Source Monitoring Escalation | misleading_failure | chart_induced_intermediate_decision_error |
| env007 | MisleadingChartQA | May Low-output Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env008 | MisleadingChartQA | Renewable Output Escalation Routing | success | none |
| env009 | MisleadingChartQA | Regional Summer Temperature Change Routing | success | none |
| env010 | MisleadingChartQA | Reservoir Storage Change Routing | success | none |
| env011 | MisleadingChartQA | River Temperature Change Routing | success | none |
| env012 | MisleadingChartQA | Cooling Water Temperature Change Routing | success | none |
| env013 | MisleadingChartQA | Coastal Water Temperature Change Routing | success | none |
| env014 | MisleadingChartQA | District Heat Demand Change Routing | success | none |
| env015 | MisleadingChartQA | Mountain Snowpack Temperature Change Routing | success | none |
| env016 | MisleadingChartQA | Reservoir Surface Temperature Change Routing | success | none |
| env017 | MisleadingChartQA | May Low-usage Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env018 | MisleadingChartQA | May Low-release Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env019 | MisleadingChartQA | May Low-output Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env020 | MisleadingChartQA | May Low-pumping Severity Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env021 | MisleadingChartQA | City Emissions Program Escalation Routing | success | none |
| env022 | MisleadingChartQA | Clean Generation Contribution Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env023 | MisleadingChartQA | Renewable Share Escalation Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env024 | MisleadingChartQA | Urban Supply Source Escalation Routing | success | none |
| env025 | MisleadingChartQA | January Air-Quality Alert Escalation Routing | success | none |
| env026 | MisleadingChartQA | Monthly River Discharge Review Routing | success | none |
| env027 | MisleadingChartQA | January Air-Quality Alert Triage Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env028 | MisleadingChartQA | January Reservoir Inflow Routing Review | misleading_failure | chart_induced_intermediate_decision_error |
| env029 | MisleadingChartQA | Clean Grid Output Review Routing | misleading_failure | chart_induced_intermediate_decision_error |
| env030 | MisleadingChartQA | Regional Air-Quality Trend Handling Queue | misleading_failure | chart_induced_intermediate_decision_error |
| env031 | MisleadingChartQA | River Restoration Capacity Review Routing | success | none |
| env032 | visDeception | 2010 Fuel Supply Escalation Review | success | none |
| env033 | visDeception | 2010 Clean Electricity Source Escalation Review | success | none |
| env034 | visDeception | Nuclear Service Cost Escalation Routing | success | none |
| env035 | visDeception | Petroleum Price Escalation Review Routing | success | none |
