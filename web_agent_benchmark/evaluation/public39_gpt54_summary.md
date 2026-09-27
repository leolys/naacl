# Public 39 GPT-5.4 Evaluation Summary

- Generated at: 2026-05-06T15:15:29.524749+00:00
- Total runs: 39
- Success rate: 17/39 (43.59%)
- Outcome distribution: {'success': 17, 'misleading_failure': 22}

## By Source

| Source | Outcomes |
|---|---|
| legacy_public_11 | {'success': 6, 'misleading_failure': 5} |
| public_affairs_28 | {'misleading_failure': 17, 'success': 11} |

## By Readiness

| Readiness | Outcomes |
|---|---|
| formal_scored_task | {'misleading_failure': 11, 'success': 8} |
| image_only_draft | {'success': 3, 'misleading_failure': 6} |
| legacy_public | {'success': 6, 'misleading_failure': 5} |

## By Misleader Type

| Misleader Type | Outcomes |
|---|---|
| MS_inappropriate_scale_range | {'misleading_failure': 1, 'success': 1} |
| MS_unconventional_scale_directions | {'success': 3, 'misleading_failure': 10} |
| categorical_encoding_for_continuous_data | {'success': 1} |
| data_visual_disproportion | {'misleading_failure': 3} |
| dual_encoding | {'success': 3, 'misleading_failure': 6} |
| misleading_annotations | {'success': 8, 'misleading_failure': 2} |
| small_size | {'success': 1} |

## Task Results

| Task | Source | Title | Outcome | Error Attribution |
|---|---|---|---|---|
| pub001 | legacy_public_11 | State Hazard Priority Review | success | none |
| pub002 | legacy_public_11 | Jurisdiction Incidence Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub003 | legacy_public_11 | State Incidence Priority Detail Routing | success | none |
| pub004 | legacy_public_11 | State Risk Priority Profile Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub005 | legacy_public_11 | Population Priority Detail Routing | success | none |
| pub006 | legacy_public_11 | GDP Priority Detail Routing | success | none |
| pub007 | legacy_public_11 | State Prevalence Priority View Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub008 | legacy_public_11 | May 06 Station X Demand Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub009 | legacy_public_11 | Transit Crowding Alert Request | success | none |
| pub010 | legacy_public_11 | Tourism Response Routing | success | none |
| pub011 | legacy_public_11 | July Visitor Operations Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub012 | public_affairs_28 | State Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub013 | public_affairs_28 | State Risk Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub014 | public_affairs_28 | State Risk Priority Detail Routing | success | none |
| pub015 | public_affairs_28 | State Incidence Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub016 | public_affairs_28 | State Prevalence Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub017 | public_affairs_28 | State Prevalence Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub018 | public_affairs_28 | State Risk Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub019 | public_affairs_28 | State Incidence Priority Detail Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub020 | public_affairs_28 | Public Service Feedback Priority Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub021 | public_affairs_28 | Public Service Low-Feedback Coverage Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub022 | public_affairs_28 | Public Service Low-Feedback Coverage Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub023 | public_affairs_28 | July Visitor Operations Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub024 | public_affairs_28 | Town Z Tourism Trend Response Routing | success | none |
| pub025 | public_affairs_28 | Town Z Tourism Trend Response Routing | success | none |
| pub026 | public_affairs_28 | Town Z Tourism Trend Response Routing | success | none |
| pub027 | public_affairs_28 | Town Z Tourism Trend Response Routing | success | none |
| pub028 | public_affairs_28 | City A Population Trend Response Routing | success | none |
| pub029 | public_affairs_28 | Town Z Tourism Trend Response Routing | success | none |
| pub030 | public_affairs_28 | Regional Transport Preference Follow-up Routing | success | none |
| pub031 | public_affairs_28 | 2020 Demographic Count Follow-up Routing | success | none |
| pub032 | public_affairs_28 | 1990 Urbanization Statistics Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub033 | public_affairs_28 | 2020 International Statistics Follow-up Routing | success | none |
| pub034 | public_affairs_28 | 2017 Displacement Statistics Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub035 | public_affairs_28 | 2012 Cross-border Indicator Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub036 | public_affairs_28 | 2013 Public Grant Intake Follow-up Routing | success | none |
| pub037 | public_affairs_28 | 2012 Age-cohort Planning Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub038 | public_affairs_28 | 2014 Economic Sector Share Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
| pub039 | public_affairs_28 | 2014 Age-share Planning Follow-up Routing | misleading_failure | chart_induced_intermediate_decision_error |
