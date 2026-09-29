# Public 39 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-06T14:46:56.747516+00:00
- Total runs: 7
- Success rate: 1/7 (14.29%)
- Outcome distribution: {'irrelevant_action_failure': 1, 'misleading_failure': 5, 'success': 1}

## By Source

| Source | Outcomes |
|---|---|
| legacy_public_11 | {'irrelevant_action_failure': 1, 'misleading_failure': 1} |
| public_affairs_28 | {'misleading_failure': 4, 'success': 1} |

## By Readiness

| Readiness | Outcomes |
|---|---|
| formal_scored_task | {'misleading_failure': 3, 'success': 1} |
| image_only_draft | {'misleading_failure': 1} |
| legacy_public | {'irrelevant_action_failure': 1, 'misleading_failure': 1} |

## By Misleader Type

| Misleader Type | Outcomes |
|---|---|
| MS_inappropriate_scale_range | {'misleading_failure': 1} |
| MS_unconventional_scale_directions | {'irrelevant_action_failure': 1, 'misleading_failure': 2} |
| data_visual_disproportion | {'misleading_failure': 1} |
| dual_encoding | {'misleading_failure': 1} |
| misleading_annotations | {'success': 1} |

## Task Results

| Task | Source | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| pub001 | legacy_public_11 | State Hazard Priority Review | irrelevant_action_failure | wrong_or_irrelevant_web_action |
| pub008 | legacy_public_11 | May 06 Station X Demand Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub012 | public_affairs_28 | State Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub019 | public_affairs_28 | State Incidence Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub020 | public_affairs_28 | Public Service Feedback Priority Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub028 | public_affairs_28 | City A Population Trend Response Routing | success | none |
| pub039 | public_affairs_28 | 2014 Age-share Planning Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
