# Qwen3-VL Timeout Post-hoc Summary

## Fix Effect Overview

- Runner change tested: expose `select.value`, `select.selected_text`, and option-level `selected` in the browser state, with a prompt instruction to submit instead of reselecting an already selected option.
- Old Qwen3-VL-8B dry run before this fix: `12` rows with `6` timeouts, all stable repeated-selection no-submit cases.
- New Qwen3-VL-8B dry run after this fix: `12` rows with `1` timeout, classified as `single_select_but_not_stable`.
- Targeted subset after this fix: `14` old timeout-prone rows, including the old 5 oscillating public examples, with `1` timeout and no oscillating timeouts.
- Interpretation: selected-state visibility substantially reduces the no-submit timeout mode, while preserving oscillating examples as a separate post-hoc category in the original full-run analysis.

## qwen3_vl_8b_selected_state_dryrun

- Total rows: `12`
- Original outcomes: `{'irrelevant_action_failure': 1, 'success': 7, 'agent_timeout': 1, 'misleading_failure': 3}`
- Timeout subtype counts: `{'single_select_but_not_stable': 1}`
- Stable implied outcomes: `{}`
- Adjusted outcomes from stable only: `{'irrelevant_action_failure': 1, 'success': 7, 'agent_timeout': 1, 'misleading_failure': 3}`

### Oscillating Examples

| Scenario | Slug | Task ID | Select Sequence |
|---|---|---|---|
| - | - | - | - |

## qwen3_vl_8b_selected_state_targeted_subset

- Total rows: `14`
- Original outcomes: `{'irrelevant_action_failure': 2, 'success': 10, 'agent_timeout': 1, 'misleading_failure': 1}`
- Timeout subtype counts: `{'single_select_but_not_stable': 1}`
- Stable implied outcomes: `{}`
- Adjusted outcomes from stable only: `{'irrelevant_action_failure': 2, 'success': 10, 'agent_timeout': 1, 'misleading_failure': 1}`

### Oscillating Examples

| Scenario | Slug | Task ID | Select Sequence |
|---|---|---|---|
| - | - | - | - |
