# Qwen3-VL Timeout Post-hoc Summary

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

## qwen3_vl_32b_full140

- Total rows: `140`
- Original outcomes: `{'agent_timeout': 83, 'misleading_failure': 27, 'irrelevant_action_failure': 2, 'success': 27, 'agent_error': 1}`
- Timeout subtype counts: `{'stable_choice_no_submit': 75, 'oscillating_choice_no_submit': 8}`
- Stable implied outcomes: `{'irrelevant_action_failure': 3, 'misleading_failure': 37, 'success': 35}`
- Adjusted outcomes from stable only: `{'irrelevant_action_failure': 5, 'misleading_failure': 64, 'success': 62, 'agent_timeout': 8, 'agent_error': 1}`

### Oscillating Examples

| Scenario | Slug | Task ID | Select Sequence |
|---|---|---|---|
| public39 | pub014 | pa_task_0eded76b98_ms_unconventional_scale_directions_choropleth_ma | Open New Mexico (NM) risk detail for priority follow-up -> Open Rhode Island (RI) risk detail for priority follow-up -> Open New Mexico (NM) risk detail for priority follow-up -> Open Rhode Island (RI) risk detail for priority follow-up -> Open New Mexico (NM) risk detail for priority follow-up -> Open Rhode Island (RI) risk detail for priority follow-up -> Open New Mexico (NM) risk detail for priority follow-up -> Open Rhode Island (RI) risk detail for priority follow-up |
| public39 | pub019 | pa_task_e482dfdd97_ms_unconventional_scale_directions_choropleth_ma | Open Tennessee (TN) incidence detail for priority follow-up -> Open California (CA) incidence detail for priority follow-up -> Open Tennessee (TN) incidence detail for priority follow-up -> Open California (CA) incidence detail for priority follow-up -> Open Tennessee (TN) incidence detail for priority follow-up -> Open California (CA) incidence detail for priority follow-up -> Open Tennessee (TN) incidence detail for priority follow-up -> Open California (CA) incidence detail for priority follow-up |
| public39 | pub021 | pa_task_3a92eb2128_data_visual_disproportion_scatter_plot_20 | Route Support Access to routine feedback monitoring -> Route Other to low-feedback coverage follow-up -> Route Support Access to routine feedback monitoring -> Route Other to low-feedback coverage follow-up -> Route Support Access to routine feedback monitoring -> Route Other to low-feedback coverage follow-up -> Route Support Access to routine feedback monitoring -> Route Other to low-feedback coverage follow-up |
| public39 | pub030 | pa_task_3fba889cbe_misleading_annotations_pie_chart_47 | Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up -> Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up -> Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up -> Route Public Transit to majority-preference policy follow-up -> Route Car to majority-preference policy follow-up |
| public39 | pub032 | pa_task_dd17dc7f7d_multi_col_1282_dual | Open 1990 Urban statistics follow-up record -> Open 1990 Rural statistics follow-up record -> Open 1990 Urban statistics follow-up record -> Open 1990 Rural statistics follow-up record -> Open 1990 Urban statistics follow-up record -> Open 1990 Rural statistics follow-up record -> Open 1990 Urban statistics follow-up record -> Open 1990 Rural statistics follow-up record |
| public39 | pub034 | pa_task_d7d4cf4c69_multi_col_20405_dual | Open 2017 IDPs statistics follow-up record -> Open 2017 IDPs statistics follow-up record -> Open 2017 Refugees statistics follow-up record -> Open 2017 IDPs statistics follow-up record -> Open 2017 Refugees statistics follow-up record -> Open 2017 IDPs statistics follow-up record -> Open 2017 Refugees statistics follow-up record -> Open 2017 IDPs statistics follow-up record |
| public39 | pub035 | pa_task_473d8586b7_multi_col_20655_png_dual | Open 2012 Canada indicator follow-up record -> Open 2012 United States indicator follow-up record -> Open 2012 Canada indicator follow-up record -> Open 2012 United States indicator follow-up record -> Open 2012 Canada indicator follow-up record -> Open 2012 United States indicator follow-up record -> Open 2012 Canada indicator follow-up record -> Open 2012 United States indicator follow-up record |
| public39 | pub038 | pa_task_e4f59e1715_multi_col_73_dual | Open 2014 Industry sector-share follow-up record -> Open 2014 Agriculture sector-share follow-up record -> Open 2014 Industry sector-share follow-up record -> Open 2014 Agriculture sector-share follow-up record -> Open 2014 Industry sector-share follow-up record -> Open 2014 Agriculture sector-share follow-up record -> Open 2014 Industry sector-share follow-up record -> Open 2014 Agriculture sector-share follow-up record |

