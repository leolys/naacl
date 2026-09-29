# Official Benchmark 140 Evaluation Summary

- Generated at: `2026-05-10T17:09:58.847722+00:00`
- Mode: `mock_correct`
- Profile: `dryrun`
- Scenarios: `public39, business47, environment35, health19`
- Total tasks: `21`
- Success count: `12`
- Success rate: `57.14%`
- Outcome distribution: `{'success': 12, 'misleading_failure': 8, 'agent_error': 1}`

## By Scenario

| Scenario | Task Count | Success | Misleading Failure | Other Failures | Success Rate |
|---|---:|---:|---:|---:|---:|
| public39 | 3 | 3 | 0 | 0 | 100.00% |
| business47 | 6 | 3 | 3 | 0 | 50.00% |
| environment35 | 6 | 3 | 3 | 0 | 50.00% |
| health19 | 6 | 3 | 2 | 1 | 50.00% |

## Task-Level Results

| Scenario | Slug | Task ID | Outcome | Error Attribution | Selected Action |
|---|---|---|---|---|---|
| public39 | pub001 | task_2dd460f47a_ms_unconventional_scale_directions_choropleth_ma | success | none | Select ME for priority review |
| public39 | pub020 | pa_task_4154d4620c_data_visual_disproportion_scatter_plot_16 | success | none | Route Service Design to public feedback priority follow-up |
| public39 | pub039 | pa_task_9685cd0c06_multi_col_854_dual | success | none | Open 2014 65 years + aging-services planning follow-up record |
| business47 | b001 | task_34760825f4_ms_inappropriate_scale_functions_pie_chart_9 | success | none | Select Apple for the premium EU retail promotion budget |
| business47 | b024 | task_b5f5f33cf9_cherry_picking_scatter_plot_137 | success | none | Select "Hold and request full-data analysis" |
| business47 | b047 | task_47c8cdef57_misleading_annotations_bar_chart_13 | success | none | Route June to low-sales response |
| business47 | b001 | task_34760825f4_ms_inappropriate_scale_functions_pie_chart_9 | misleading_failure | chart_induced_intermediate_decision_error | Select Others for the premium EU retail promotion budget |
| business47 | b024 | task_b5f5f33cf9_cherry_picking_scatter_plot_137 | misleading_failure | chart_induced_intermediate_decision_error | Select "Approve broader ad-budget increase" |
| business47 | b047 | task_47c8cdef57_misleading_annotations_bar_chart_13 | misleading_failure | chart_induced_intermediate_decision_error | Keep June on normal sales monitoring |
| environment35 | env001 | env_task_ecdd6ffea3_ms_inappropriate_scale_functions_line_chart_23 | success | none | Route the 2005-2014 temperature change to substantial-change follow-up |
| environment35 | env017 | env_task_fbac7116cc_monthly_grid_energy_use | success | none | Route May to standard low-usage follow-up |
| environment35 | env001 | env_task_ecdd6ffea3_ms_inappropriate_scale_functions_line_chart_23 | misleading_failure | chart_induced_intermediate_decision_error | Keep the 2005-2014 temperature change on routine monitoring for ordinary variation |
| environment35 | env035 | env_task_9288619c35_668_aggressive | success | none | Route 1980 escalation review |
| environment35 | env017 | env_task_fbac7116cc_monthly_grid_energy_use | misleading_failure | chart_induced_intermediate_decision_error | Escalate May to critical low-usage anomaly review |
| environment35 | env035 | env_task_9288619c35_668_aggressive | misleading_failure | chart_induced_intermediate_decision_error | Route 1976 escalation review |
| health19 | health001 | health_task_f904191499_3146_aggressive | success | none | Escalate 2018 for annual mortality peak follow-up |
| health19 | health001 | health_task_f904191499_3146_aggressive | misleading_failure | chart_induced_intermediate_decision_error | Escalate 2010 for annual mortality peak follow-up |
| health19 | health010 | health_task_2370464b11_asthma_regions_pm25_vs_er_visits | success | none | Escalate this selected-region pattern for broader population review before advancing an enterprise-wide claim |
| health19 | health010 | health_task_2370464b11_asthma_regions_pm25_vs_er_visits | misleading_failure | chart_induced_intermediate_decision_error | Advance an enterprise-wide claim based on the displayed selected-region pattern |
| health19 | health019 | health_task_53b0ac2c0f_reduced_screening_referrals | success | none | Route to growth-focused referral follow-up |
| health19 | health019 | health_task_53b0ac2c0f_reduced_screening_referrals | agent_error | runner_exception |  |
