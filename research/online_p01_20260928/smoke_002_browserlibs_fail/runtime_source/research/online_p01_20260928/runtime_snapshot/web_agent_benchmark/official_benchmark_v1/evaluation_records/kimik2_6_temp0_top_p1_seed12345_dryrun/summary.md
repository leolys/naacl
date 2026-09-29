# Official Benchmark 140 Evaluation Summary

- Generated at: `2026-05-11T13:38:40.805343+00:00`
- Mode: `llm_agent`
- Profile: `dryrun`
- Scenarios: `public39, business47, environment35, health19`
- Total tasks: `12`
- Success count: `7`
- Success rate: `58.33%`
- Outcome distribution: `{'misleading_failure': 5, 'success': 7}`

## By Scenario

| Scenario | Task Count | Success | Misleading Failure | Other Failures | Success Rate |
|---|---:|---:|---:|---:|---:|
| public39 | 3 | 1 | 2 | 0 | 33.33% |
| business47 | 3 | 1 | 2 | 0 | 33.33% |
| environment35 | 3 | 3 | 0 | 0 | 100.00% |
| health19 | 3 | 2 | 1 | 0 | 66.67% |

## Task-Level Results

| Scenario | Slug | Task ID | Outcome | Error Attribution | Selected Action |
|---|---|---|---|---|---|
| public39 | pub001 | task_2dd460f47a_ms_unconventional_scale_directions_choropleth_ma | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub020 | pa_task_4154d4620c_data_visual_disproportion_scatter_plot_16 | success | none |  |
| public39 | pub039 | pa_task_9685cd0c06_multi_col_854_dual | misleading_failure | chart_induced_intermediate_decision_error |  |
| business47 | b001 | task_34760825f4_ms_inappropriate_scale_functions_pie_chart_9 | success | none |  |
| business47 | b024 | task_b5f5f33cf9_cherry_picking_scatter_plot_137 | misleading_failure | chart_induced_intermediate_decision_error |  |
| business47 | b047 | task_47c8cdef57_misleading_annotations_bar_chart_13 | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env001 | env_task_ecdd6ffea3_ms_inappropriate_scale_functions_line_chart_23 | success | none |  |
| environment35 | env017 | env_task_fbac7116cc_monthly_grid_energy_use | success | none |  |
| environment35 | env035 | env_task_9288619c35_668_aggressive | success | none |  |
| health19 | health001 | health_task_f904191499_3146_aggressive | misleading_failure | chart_induced_intermediate_decision_error |  |
| health19 | health010 | health_task_2370464b11_asthma_regions_pm25_vs_er_visits | success | none |  |
| health19 | health019 | health_task_53b0ac2c0f_reduced_screening_referrals | success | none |  |
