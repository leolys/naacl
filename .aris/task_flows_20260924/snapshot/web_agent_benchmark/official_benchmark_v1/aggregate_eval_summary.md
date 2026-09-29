# Aggregate Evaluation Summary

This file freezes the current official GPT-5.4 baseline across the four reviewed scenarios.

- Total tasks: `140`
- Total success count: `57`
- Total success rate: `40.71%`
- Outcome distribution: `{'success': 57, 'misleading_failure': 74, 'agent_timeout': 4, 'irrelevant_action_failure': 5}`

| Scenario | Task Count | Success | Misleading Failure | Other Failures | Success Rate |
|---|---:|---:|---:|---:|---:|
| public39 | 39 | 17 | 22 | 0 | 43.59% |
| business47 | 47 | 9 | 29 | 9 | 19.15% |
| environment35 | 35 | 22 | 13 | 0 | 62.86% |
| health19 | 19 | 9 | 10 | 0 | 47.37% |

## Official Baseline Files

- Aggregate runs: [official_benchmark140_gpt54_runs.jsonl](../evaluation/official_benchmark140_gpt54_runs.jsonl)
- Aggregate summary: [official_benchmark140_gpt54_summary.md](../evaluation/official_benchmark140_gpt54_summary.md)
- Aggregate failures: [official_benchmark140_gpt54_failures.jsonl](../evaluation/official_benchmark140_gpt54_failures.jsonl)
