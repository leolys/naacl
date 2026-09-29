# Stable Choice Timeout Analysis

## qwen3_vl_8b_full140

- Total rows: `140`
- Original outcomes: `{'irrelevant_action_failure': 5, 'success': 23, 'misleading_failure': 35, 'agent_timeout': 77}`
- Timeout subtype counts: `{'oscillating_choice_no_submit': 5, 'stable_choice_no_submit': 72}`
- Stable implied outcomes: `{'misleading_failure': 33, 'success': 33, 'irrelevant_action_failure': 6}`
- Adjusted outcomes from stable only: `{'irrelevant_action_failure': 11, 'success': 56, 'misleading_failure': 68, 'agent_timeout': 5}`

### Oscillating Examples

| Scenario | Slug | Task ID | Select Sequence |
|---|---|---|---|
| public39 | pub021 | pa_task_3a92eb2128_data_visual_disproportion_scatter_plot_20 | Route Support Access to routine feedback monitoring -> Route Service Design to low-feedback coverage follow-up -> Route Support Access to routine feedback monitoring -> Route Service Design to low-feedback coverage follow-up -> Route Support Access to routine feedback monitoring -> Route Service Design to low-feedback coverage follow-up -> Route Support Access to routine feedback monitoring -> Route Service Design to low-feedback coverage follow-up |
| public39 | pub030 | pa_task_3fba889cbe_misleading_annotations_pie_chart_47 | Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up -> Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up -> Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up -> Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up |
| public39 | pub034 | pa_task_d7d4cf4c69_multi_col_20405_dual | Open 2017 IDPs statistics follow-up record -> Open 2017 Refugees statistics follow-up record -> Open 2017 IDPs statistics follow-up record -> Open 2017 Refugees statistics follow-up record -> Open 2017 IDPs statistics follow-up record -> Open 2017 Refugees statistics follow-up record -> Open 2017 IDPs statistics follow-up record -> Open 2017 Refugees statistics follow-up record |
| public39 | pub035 | pa_task_473d8586b7_multi_col_20655_png_dual | Open 2012 United States indicator follow-up record -> Open 2012 Canada indicator follow-up record -> Open 2012 United States indicator follow-up record -> Open 2012 Canada indicator follow-up record -> Open 2012 United States indicator follow-up record -> Open 2012 Canada indicator follow-up record -> Open 2012 United States indicator follow-up record -> Open 2012 Canada indicator follow-up record |
| public39 | pub036 | pa_task_a887293e72_multi_col_524_dual | Open 2013 United States grant intake follow-up record -> Open 2013 Canada grant intake follow-up record -> Open 2013 United States grant intake follow-up record -> Open 2013 Canada grant intake follow-up record -> Open 2013 United States grant intake follow-up record -> Open 2013 Canada grant intake follow-up record -> Open 2013 United States grant intake follow-up record -> Open 2013 Canada grant intake follow-up record |

