# Official Benchmark 140 Evaluation Summary

- Generated at: `2026-05-10T13:14:30.763211+00:00`
- Mode: `llm_agent`
- Profile: `full`
- Scenarios: `public39, business47, environment35, health19`
- Total tasks: `140`
- Success count: `23`
- Success rate: `16.43%`
- Outcome distribution: `{'irrelevant_action_failure': 5, 'success': 23, 'misleading_failure': 35, 'agent_timeout': 77}`

## By Scenario

| Scenario | Task Count | Success | Misleading Failure | Other Failures | Success Rate |
|---|---:|---:|---:|---:|---:|
| public39 | 39 | 10 | 13 | 16 | 25.64% |
| business47 | 47 | 0 | 5 | 42 | 0.00% |
| environment35 | 35 | 12 | 11 | 12 | 34.29% |
| health19 | 19 | 1 | 6 | 12 | 5.26% |

## Task-Level Results

| Scenario | Slug | Task ID | Outcome | Error Attribution | Selected Action |
|---|---|---|---|---|---|
| public39 | pub001 | task_2dd460f47a_ms_unconventional_scale_directions_choropleth_ma | irrelevant_action_failure | wrong_or_irrelevant_web_action |  |
| public39 | pub002 | task_48b401885c_ms_unconventional_scale_directions_choropleth_ma | success | none |  |
| public39 | pub003 | task_40de98dd9b_ms_unconventional_scale_directions_choropleth_ma | success | none |  |
| public39 | pub004 | task_5a36c16f58_ms_unconventional_scale_directions_choropleth_ma | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub005 | task_c6ae36b8ea_categorical_encoding_for_continuous_data_choropl | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub006 | task_f366c5c885_small_size_choropleth_map_12 | success | none |  |
| public39 | pub007 | task_b2b270b34f_ms_unconventional_scale_directions_choropleth_ma | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub008 | task_a0ff55adf8_ms_inappropriate_scale_range_stacked_bar_chart_1 | irrelevant_action_failure | wrong_or_irrelevant_web_action |  |
| public39 | pub009 | task_e024166274_ms_inappropriate_scale_range_stacked_bar_chart_1 | success | none |  |
| public39 | pub010 | task_6c60db5187_misleading_annotations_line_chart_41 | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub011 | task_d2bc5ae637_misleading_annotations_bar_chart_3 | irrelevant_action_failure | wrong_or_irrelevant_web_action |  |
| public39 | pub012 | pa_task_9eadd12d9b_ms_unconventional_scale_directions_choropleth_ma | success | none |  |
| public39 | pub013 | pa_task_0eeef49efa_ms_unconventional_scale_directions_choropleth_ma | success | none |  |
| public39 | pub014 | pa_task_0eded76b98_ms_unconventional_scale_directions_choropleth_ma | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub015 | pa_task_d8c3875ff0_ms_unconventional_scale_directions_choropleth_ma | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub016 | pa_task_a8416cce0c_ms_unconventional_scale_directions_choropleth_ma | success | none |  |
| public39 | pub017 | pa_task_414ffbd7df_ms_unconventional_scale_directions_choropleth_ma | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub018 | pa_task_5f99ed0562_ms_unconventional_scale_directions_choropleth_ma | success | none |  |
| public39 | pub019 | pa_task_e482dfdd97_ms_unconventional_scale_directions_choropleth_ma | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub020 | pa_task_4154d4620c_data_visual_disproportion_scatter_plot_16 | success | none |  |
| public39 | pub021 | pa_task_3a92eb2128_data_visual_disproportion_scatter_plot_20 | agent_timeout | no_submission |  |
| public39 | pub022 | pa_task_adca69d05f_data_visual_disproportion_scatter_plot_21 | agent_timeout | no_submission |  |
| public39 | pub023 | pa_task_d2bc5ae637_misleading_annotations_bar_chart_3 | irrelevant_action_failure | wrong_or_irrelevant_web_action |  |
| public39 | pub024 | pa_task_bf3f12daa9_misleading_annotations_line_chart_1 | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub025 | pa_task_7aa35920bc_misleading_annotations_line_chart_19 | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub026 | pa_task_01528cc6da_misleading_annotations_line_chart_22 | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub027 | pa_task_3f8815bf83_misleading_annotations_line_chart_27 | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub028 | pa_task_37c083d461_misleading_annotations_line_chart_4 | agent_timeout | no_submission |  |
| public39 | pub029 | pa_task_5b47970610_misleading_annotations_line_chart_8 | misleading_failure | chart_induced_intermediate_decision_error |  |
| public39 | pub030 | pa_task_3fba889cbe_misleading_annotations_pie_chart_47 | agent_timeout | no_submission |  |
| public39 | pub031 | pa_task_c334dc9862_multi_col_1047_dual | agent_timeout | no_submission |  |
| public39 | pub032 | pa_task_dd17dc7f7d_multi_col_1282_dual | agent_timeout | no_submission |  |
| public39 | pub033 | pa_task_256cf4f7c0_multi_col_20385_dual | agent_timeout | no_submission |  |
| public39 | pub034 | pa_task_d7d4cf4c69_multi_col_20405_dual | agent_timeout | no_submission |  |
| public39 | pub035 | pa_task_473d8586b7_multi_col_20655_png_dual | agent_timeout | no_submission |  |
| public39 | pub036 | pa_task_a887293e72_multi_col_524_dual | agent_timeout | no_submission |  |
| public39 | pub037 | pa_task_fed1ed8a7a_multi_col_626_png_dual | agent_timeout | no_submission |  |
| public39 | pub038 | pa_task_e4f59e1715_multi_col_73_dual | success | none |  |
| public39 | pub039 | pa_task_9685cd0c06_multi_col_854_dual | agent_timeout | no_submission |  |
| business47 | b001 | task_34760825f4_ms_inappropriate_scale_functions_pie_chart_9 | agent_timeout | no_submission |  |
| business47 | b002 | task_a0dd5d5c8c_data_visual_disproportion_bar_chart_51 | agent_timeout | no_submission |  |
| business47 | b003 | task_9f6f34419f_data_visual_disproportion_scatter_plot_18 | agent_timeout | no_submission |  |
| business47 | b004 | task_a4f37d97be_ms_inappropriate_scale_functions_pie_chart_28 | agent_timeout | no_submission |  |
| business47 | b005 | task_3ac1c1e020_data_visual_disproportion_bar_chart_52 | agent_timeout | no_submission |  |
| business47 | b006 | task_7b0f889a77_data_visual_disproportion_scatter_plot_19 | agent_timeout | no_submission |  |
| business47 | b007 | task_ef1a77c8a2_data_visual_disproportion_bar_chart_54 | agent_timeout | no_submission |  |
| business47 | b008 | task_000d3fa08e_data_visual_disproportion_scatter_plot_27 | agent_timeout | no_submission |  |
| business47 | b009 | task_b06b171087_ms_inappropriate_scale_functions_pie_chart_15 | agent_timeout | no_submission |  |
| business47 | b010 | task_d01342ef81_data_visual_disproportion_bar_chart_55 | agent_timeout | no_submission |  |
| business47 | b011 | task_3e65d6c348_misuse_of_cumulative_relationship_stacked_bar_ch | agent_timeout | no_submission |  |
| business47 | b012 | task_5c6960f403_ms_inappropriate_scale_range_bar_chart_53 | misleading_failure | chart_induced_intermediate_decision_error |  |
| business47 | b013 | task_c53eae1ce8_ms_inappropriate_scale_range_bar_chart_38 | irrelevant_action_failure | wrong_or_irrelevant_web_action |  |
| business47 | b014 | task_f1a3db2e19_ms_inappropriate_scale_range_bar_chart_26 | misleading_failure | chart_induced_intermediate_decision_error |  |
| business47 | b015 | task_39785b3779_ms_inappropriate_scale_range_bar_chart_39 | misleading_failure | chart_induced_intermediate_decision_error |  |
| business47 | b016 | task_c899168c00_ms_inappropriate_scale_range_bar_chart_60 | misleading_failure | chart_induced_intermediate_decision_error |  |
| business47 | b017 | task_9ec85dcc08_cherry_picking_scatter_plot_95 | agent_timeout | no_submission |  |
| business47 | b018 | task_87eee96e59_cherry_picking_scatter_plot_134 | agent_timeout | no_submission |  |
| business47 | b019 | task_b1f2d81fc2_cherry_picking_scatter_plot_126 | agent_timeout | no_submission |  |
| business47 | b020 | task_888fde5f0a_cherry_picking_scatter_plot_125 | misleading_failure | chart_induced_intermediate_decision_error |  |
| business47 | b021 | task_0f4434cf82_cherry_picking_scatter_plot_127 | agent_timeout | no_submission |  |
| business47 | b022 | task_63e1b44e4d_cherry_picking_scatter_plot_131 | agent_timeout | no_submission |  |
| business47 | b023 | task_88b99fffbb_cherry_picking_scatter_plot_138 | agent_timeout | no_submission |  |
| business47 | b024 | task_b5f5f33cf9_cherry_picking_scatter_plot_137 | agent_timeout | no_submission |  |
| business47 | b025 | task_b94c61eab6_cherry_picking_scatter_plot_94 | agent_timeout | no_submission |  |
| business47 | b026 | task_c8b9835eda_cherry_picking_scatter_plot_97 | agent_timeout | no_submission |  |
| business47 | b027 | task_0d1d724231_cherry_picking_scatter_plot_99 | agent_timeout | no_submission |  |
| business47 | b028 | task_71f1505dcb_cherry_picking_scatter_plot_3 | agent_timeout | no_submission |  |
| business47 | b029 | task_f37014fe36_cherry_picking_scatter_plot_139 | agent_timeout | no_submission |  |
| business47 | b030 | task_f5c75f1c96_cherry_picking_scatter_plot_102 | agent_timeout | no_submission |  |
| business47 | b031 | task_99f8eeed90_cherry_picking_scatter_plot_103 | agent_timeout | no_submission |  |
| business47 | b032 | task_b25fcdf85a_cherry_picking_scatter_plot_104 | agent_timeout | no_submission |  |
| business47 | b033 | task_947df19bfb_cherry_picking_scatter_plot_113 | agent_timeout | no_submission |  |
| business47 | b034 | task_abeb87c99e_cherry_picking_scatter_plot_123 | agent_timeout | no_submission |  |
| business47 | b035 | task_cb122340db_misleading_annotations_line_chart_32 | agent_timeout | no_submission |  |
| business47 | b036 | task_c36362b5ca_misleading_annotations_line_chart_31 | agent_timeout | no_submission |  |
| business47 | b037 | task_ab14f8c27e_misleading_annotations_line_chart_37 | agent_timeout | no_submission |  |
| business47 | b038 | task_2b513897e5_misleading_annotations_line_chart_46 | agent_timeout | no_submission |  |
| business47 | b039 | task_de87e31aaa_misleading_annotations_line_chart_47 | agent_timeout | no_submission |  |
| business47 | b040 | task_898e807600_misleading_annotations_line_chart_29 | agent_timeout | no_submission |  |
| business47 | b041 | task_7b07151b3f_misleading_annotations_bar_chart_35 | agent_timeout | no_submission |  |
| business47 | b042 | task_78f9668995_misleading_annotations_bar_chart_47 | agent_timeout | no_submission |  |
| business47 | b043 | task_74a63303da_misleading_annotations_bar_chart_46 | agent_timeout | no_submission |  |
| business47 | b044 | task_b300f2336c_misleading_annotations_bar_chart_33 | agent_timeout | no_submission |  |
| business47 | b045 | task_d8e9244689_misleading_annotations_bar_chart_2 | agent_timeout | no_submission |  |
| business47 | b046 | task_c2306b1cad_misleading_annotations_bar_chart_16 | agent_timeout | no_submission |  |
| business47 | b047 | task_47c8cdef57_misleading_annotations_bar_chart_13 | agent_timeout | no_submission |  |
| environment35 | env001 | env_task_ecdd6ffea3_ms_inappropriate_scale_functions_line_chart_23 | agent_timeout | no_submission |  |
| environment35 | env002 | env_task_9615fe8d3b_ms_inappropriate_scale_functions_line_chart_41 | success | none |  |
| environment35 | env003 | env_task_2cd4dfad27_ms_inappropriate_scale_functions_pie_chart_23 | success | none |  |
| environment35 | env004 | env_task_2ca7079c63_ms_inappropriate_scale_functions_pie_chart_46 | success | none |  |
| environment35 | env005 | env_task_cdf97c4622_ms_inappropriate_scale_functions_pie_chart_48 | success | none |  |
| environment35 | env006 | env_task_b62164db3a_ms_inappropriate_scale_functions_pie_chart_7 | success | none |  |
| environment35 | env007 | env_task_c7b4764741_ms_inappropriate_scale_range_bar_chart_27 | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env008 | env_task_45311697d3_data_visual_disproportion_bar_chart_24 | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env009 | env_task_8e71d02be4_regional_summer_temperature | agent_timeout | no_submission |  |
| environment35 | env010 | env_task_a96cdb5daf_reservoir_storage_level | agent_timeout | no_submission |  |
| environment35 | env011 | env_task_9473005050_river_temperature_monitoring | agent_timeout | no_submission |  |
| environment35 | env012 | env_task_51055b69ee_thermal_power_cooling_water | agent_timeout | no_submission |  |
| environment35 | env013 | env_task_179f99fb9f_coastal_water_temperature | agent_timeout | no_submission |  |
| environment35 | env014 | env_task_f3cfca7323_district_heat_demand_index | agent_timeout | no_submission |  |
| environment35 | env015 | env_task_0fa0d33b33_mountain_snowpack_temperature | agent_timeout | no_submission |  |
| environment35 | env016 | env_task_76053112dc_reservoir_surface_temperature | agent_timeout | no_submission |  |
| environment35 | env017 | env_task_fbac7116cc_monthly_grid_energy_use | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env018 | env_task_e0a5e6768f_monthly_reservoir_release_volume | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env019 | env_task_0e18fa9ed7_monthly_solar_generation_output | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env020 | env_task_415a2c6894_monthly_water_pumping_volume | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env021 | env_task_bef1581dd5_city_emissions_reduction_programs | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env022 | env_task_9aef0281b5_clean_grid_contribution | success | none |  |
| environment35 | env023 | env_task_d194599898_renewable_energy_mix | success | none |  |
| environment35 | env024 | env_task_b45719eb83_urban_water_supply_mix | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env025 | env_task_bfbd55be02_monthly_air_quality_alert_count | success | none |  |
| environment35 | env026 | env_task_ddb392608c_monthly_river_discharge_monitoring | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env027 | env_task_537c70e795_monthly_air_quality_alert_days | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env028 | env_task_2aafcb90a3_monthly_reservoir_inflow_volume | misleading_failure | chart_induced_intermediate_decision_error |  |
| environment35 | env029 | env_task_2e23e769d9_clean_grid_output | agent_timeout | no_submission |  |
| environment35 | env030 | env_task_ad37066925_regional_air_quality_recovery | success | none |  |
| environment35 | env031 | env_task_45a9d90d56_river_restoration_capacity | agent_timeout | no_submission |  |
| environment35 | env032 | env_task_39fbf24191_multi_col_1291_dual | agent_timeout | no_submission |  |
| environment35 | env033 | env_task_f4546c112b_multi_col_398_dual | success | none |  |
| environment35 | env034 | env_task_69b7319723_multi_col_806_png_dual | success | none |  |
| environment35 | env035 | env_task_9288619c35_668_aggressive | success | none |  |
| health19 | health001 | health_task_f904191499_3146_aggressive | success | none |  |
| health19 | health002 | health_task_c229574acc_4127_aggressive | misleading_failure | chart_induced_intermediate_decision_error |  |
| health19 | health003 | health_task_01c703e3fa_4243_aggressive | agent_timeout | no_submission |  |
| health19 | health004 | health_task_d978be0e75_5014_aggressive | misleading_failure | chart_induced_intermediate_decision_error |  |
| health19 | health005 | health_task_cef467a631_6612_aggressive | agent_timeout | no_submission |  |
| health19 | health006 | health_task_50ce3ac36b_hospital_screening_referral_volume | agent_timeout | no_submission |  |
| health19 | health007 | health_task_ab93fad137_positive_test_rate_sentinel_sites | agent_timeout | no_submission |  |
| health19 | health008 | health_task_15be3a25e9_respiratory_clinic_visits | misleading_failure | chart_induced_intermediate_decision_error |  |
| health19 | health009 | health_task_2edbc9836c_telehealth_followup_enrollment | agent_timeout | no_submission |  |
| health19 | health010 | health_task_2370464b11_asthma_regions_pm25_vs_er_visits | agent_timeout | no_submission |  |
| health19 | health011 | health_task_676be2bdac_screening_centers_outreach_vs_referrals | agent_timeout | no_submission |  |
| health19 | health012 | health_task_81abc77036_sentinel_sites_testing_vs_positive_cases | agent_timeout | no_submission |  |
| health19 | health013 | health_task_ecc370154e_top_hospitals_nurse_hours_vs_discharge | agent_timeout | no_submission |  |
| health19 | health014 | health_task_f2164478dc_multi_col_20263_dual | agent_timeout | no_submission |  |
| health19 | health015 | health_task_51f8d806df_multi_col_20517_png_dual | agent_timeout | no_submission |  |
| health19 | health016 | health_task_37e50d7e34_declining_emergency_department_visits | agent_timeout | no_submission |  |
| health19 | health017 | health_task_1edc9622c9_declining_telehealth_followup_requests | misleading_failure | chart_induced_intermediate_decision_error |  |
| health19 | health018 | health_task_5e43a4f672_falling_respiratory_infection_cases | misleading_failure | chart_induced_intermediate_decision_error |  |
| health19 | health019 | health_task_53b0ac2c0f_reduced_screening_referrals | misleading_failure | chart_induced_intermediate_decision_error |  |
