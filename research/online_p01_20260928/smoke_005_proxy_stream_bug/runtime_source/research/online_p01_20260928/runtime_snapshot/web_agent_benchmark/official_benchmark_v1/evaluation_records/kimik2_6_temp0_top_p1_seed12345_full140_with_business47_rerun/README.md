# Kimi K2.6 Full140 Merged Evaluation Records

This directory keeps the original full140 run intact and applies the business47 b032-b047 rerun as a documented replacement for local runner exceptions.

- Original full run: `web_agent_benchmark/official_benchmark_v1/evaluation_records/kimik2_6_temp0_top_p1_seed12345_full140`
- Rerun source: `web_agent_benchmark/official_benchmark_v1/evaluation_records/kimik2_6_temp0_top_p1_seed12345_business47_b032_b047_rerun`
- Replacement scope: `business47=b032-b047`
- Original replaced rows are preserved in `original_replaced_rows.jsonl`.
- Rerun replacement rows are preserved in `rerun_replacement_rows.jsonl`.

- Total tasks: `140`
- Success count: `65`
- Success rate: `46.43%`
- Outcome distribution: `{'misleading_failure': 73, 'success': 65, 'irrelevant_action_failure': 1, 'agent_timeout': 1}`
- Transient failures after merge: `0`
