# Expanded clean-only screen decisions

Date completed: 2026-09-01

The decisions below apply the rule fixed in
`EXPANDED_CLEAN_SCREEN_PROTOCOL.md`.  No corresponding official-arm compact
cell was run for these five cases.

| case | clean single-attempt | clean feedback-retry/F0 | decision | reason |
|---|---|---|---|---|
| `b008` | timeout, no selected action | timeout, no selected action | reject | 0/2 expected submissions; repeated `MEMORIZE` behavior is an interaction/grounding floor |
| `env003` | submitted Hydroelectric trap, scorer=false | selected Hydroelectric trap, no submission | reject | clean chart still maps to the canonical misleading action |
| `pub012` | submitted NY trap, scorer=false | selected NY trap, no submission | reject | clean choropleth/legend grounding is not competent |
| `pub009` | submitted Thu-only neutral action, scorer=false | submitted Thu-only neutral action, scorer=false | reject | clean threshold/aggregation decision is wrong in both cells |
| `env025` | complete without selection | complete without selection | reject | 0/2 selected or submitted actions; arithmetic workflow is not observable |

## Run artifacts

- `b008`: `runs/expanded_clean_screen/b008/20260831T182251Z_9f49514c/summary.json`
- `env003`: `runs/expanded_clean_screen/env003/20260831T182504Z_95948e70/summary.json`
- `pub012`: `runs/expanded_clean_screen/pub012/20260831T182633Z_97921909/summary.json`
- `pub009`: `runs/expanded_clean_screen/pub009/20260831T182754Z_cd7b7045/summary.json`
- `env025`: `runs/expanded_clean_screen/env025/20260831T182919Z_fdff14ab/summary.json`

Every summary has `clean_only_screen=true`, `official_arm_not_run=true`,
byte-identical clean candidate/reference first screenshots, identical first
model responses, and `execution_complete=true`.  Here, execution completeness
means the measurement was valid; it does not mean the task was solved.

These failures are retained as a capability boundary.  They are not evidence
that reflection failed to repair a misleading visualization because a clean,
end-to-end premise/action mapping was never established.
