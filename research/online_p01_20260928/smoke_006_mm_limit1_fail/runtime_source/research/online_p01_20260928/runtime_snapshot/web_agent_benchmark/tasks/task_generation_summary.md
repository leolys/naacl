# Task Generation Summary

- Created at: `2026-05-03T06:44:56.864242+00:00`
- Input: `/mnt/data/lys/CognitiveHijacking_CognitiveDenial/web_agent_benchmark/selected_cases_workflow_ready/selected_cases.jsonl`
- Output: `web_agent_benchmark/tasks`
- Generated tasks: `72`
- Validation failures: `0`
- GPT fallback used: `0`
- Neutral actions deterministically rewritten: `1`

## Action Role Distribution

| Role | Count |
|---|---:|
| `correct` | 72 |
| `misleading_trap` | 72 |
| `neutral_or_irrelevant` | 72 |

## Operation Distribution

| Operation | Count |
|---|---:|
| `cherry_picking_generalization_check` | 18 |
| `threshold_judgment` | 16 |
| `visual_size_vs_data_value` | 13 |
| `extreme_value` | 9 |
| `annotation_claim_verification` | 8 |
| `axis_or_scale_interpretation` | 5 |
| `rank_order` | 2 |
| `largest_recent_change` | 1 |

## Misleader Distribution

| Misleader | Count |
|---|---:|
| `cherry_picking` | 18 |
| `misleading_annotations` | 16 |
| `MS_inappropriate_scale_functions` | 10 |
| `data_visual_disproportion` | 8 |
| `MS_inappropriate_scale_range` | 8 |
| `MS_unconventional_scale_directions` | 5 |
| `continous_encoding_for_categorical_data` | 4 |
| `categorical_encoding_for_continuous_data` | 1 |
| `small_size` | 1 |
| `misuse_of_cumulative_relationship` | 1 |

## Validation

- All generated tasks passed structural validation and scorer dry run.
