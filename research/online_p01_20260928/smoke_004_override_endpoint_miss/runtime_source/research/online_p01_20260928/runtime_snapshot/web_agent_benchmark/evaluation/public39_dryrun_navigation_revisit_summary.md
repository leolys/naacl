# Public 39 Dry Run Navigation Revisit Metrics

- Generated at: 2026-05-06T14:47:08.555453+00:00
- Source runs: web_agent_benchmark/evaluation/public39_gpt54_dryrun_runs.jsonl
- Total tasks: 7
- Loop severity distribution: {'none': 7}

## Interpretation

- `form_to_dashboard_revisits`: number of times the agent returned from the action form to the dashboard.
- `pre_submit_dashboard_revisits`: dashboard revisits after first seeing the form and before submit.
- `single_revisit`: one form-to-dashboard revisit or revisiting the dashboard after selecting a primary action.
- `repeated_loop`: repeated form/dashboard alternation.

## Revisit Tasks

| Task | Severity | Outcome | Form→Dashboard | Pre-Submit Revisit | Steps | Error |
|---|---|---|---:|---:|---:|---|

## Outcomes By Severity

| Severity | Outcomes |
|---|---|
| none | {'irrelevant_action_failure': 1, 'misleading_failure': 5, 'success': 1} |

## Templates By Severity

| Severity | Templates |
|---|---|
| none | {'State Profile / Priority Review': 1, 'Municipal Transit / Alert Routing': 1, 'State / Regional Priority Review': 2, 'Public Feedback Priority Routing': 1, 'Tourism / Public Program Routing': 1, 'Public Age-share Planning Record Routing': 1} |

## Misleader Types By Severity

| Severity | Misleader Types |
|---|---|
| none | {'MS_unconventional_scale_directions': 3, 'MS_inappropriate_scale_range': 1, 'data_visual_disproportion': 1, 'misleading_annotations': 1, 'dual_encoding': 1} |
