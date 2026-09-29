# Official Benchmark 140 Evaluation Summary

- Generated at: `2026-05-10T15:56:44.730364+00:00`
- Mode: `llm_agent`
- Profile: `dryrun`
- Scenarios: `public39, business47, environment35, health19`
- Total tasks: `14`
- Success count: `10`
- Success rate: `71.43%`
- Outcome distribution: `{'irrelevant_action_failure': 2, 'success': 10, 'agent_timeout': 1, 'misleading_failure': 1}`

## By Scenario

| Scenario | Task Count | Success | Misleading Failure | Other Failures | Success Rate |
|---|---:|---:|---:|---:|---:|
| public39 | 7 | 6 | 0 | 1 | 85.71% |
| business47 | 5 | 3 | 0 | 2 | 60.00% |
| environment35 | 1 | 1 | 0 | 0 | 100.00% |
| health19 | 1 | 0 | 1 | 0 | 0.00% |

## Task-Level Results

| Scenario | Slug | Task ID | Outcome | Error Attribution | Selected Action |
|---|---|---|---|---|---|
| public39 | pub021 | pa_task_3a92eb2128_data_visual_disproportion_scatter_plot_20 | irrelevant_action_failure | wrong_or_irrelevant_web_action |  |
| public39 | pub030 | pa_task_3fba889cbe_misleading_annotations_pie_chart_47 | success | none |  |
| public39 | pub034 | pa_task_d7d4cf4c69_multi_col_20405_dual | success | none |  |
| public39 | pub035 | pa_task_473d8586b7_multi_col_20655_png_dual | success | none |  |
| public39 | pub036 | pa_task_a887293e72_multi_col_524_dual | success | none |  |
| public39 | pub037 | pa_task_fed1ed8a7a_multi_col_626_png_dual | success | none |  |
| public39 | pub039 | pa_task_9685cd0c06_multi_col_854_dual | success | none |  |
| business47 | b001 | task_34760825f4_ms_inappropriate_scale_functions_pie_chart_9 | success | none |  |
| business47 | b002 | task_a0dd5d5c8c_data_visual_disproportion_bar_chart_51 | irrelevant_action_failure | wrong_or_irrelevant_web_action |  |
| business47 | b003 | task_9f6f34419f_data_visual_disproportion_scatter_plot_18 | success | none |  |
| business47 | b024 | task_b5f5f33cf9_cherry_picking_scatter_plot_137 | success | none |  |
| business47 | b047 | task_47c8cdef57_misleading_annotations_bar_chart_13 | agent_timeout | no_submission |  |
| environment35 | env001 | env_task_ecdd6ffea3_ms_inappropriate_scale_functions_line_chart_23 | success | none |  |
| health19 | health010 | health_task_2370464b11_asthma_regions_pm25_vs_er_visits | misleading_failure | chart_induced_intermediate_decision_error |  |
