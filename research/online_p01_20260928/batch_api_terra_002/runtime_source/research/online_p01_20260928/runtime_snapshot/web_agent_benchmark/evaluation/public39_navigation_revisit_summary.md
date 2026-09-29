# Public 39 Navigation Revisit Metrics

- Generated at: 2026-05-06T15:15:45.271519+00:00
- Source runs: web_agent_benchmark/evaluation/public39_gpt54_runs.jsonl
- Total tasks: 39
- Loop severity distribution: {'none': 39}

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
| none | {'success': 17, 'misleading_failure': 22} |

## Templates By Severity

| Severity | Templates |
|---|---|
| none | {'State Profile / Priority Review': 7, 'Municipal Transit / Alert Routing': 2, 'Tourism / Public Program Routing': 10, 'State / Regional Priority Review': 8, 'Public Feedback Priority Routing': 3, 'Public Demographic Record Routing': 1, 'Public Urbanization Record Routing': 1, 'Public International Statistics Record Routing': 1, 'Public Humanitarian Statistics Record Routing': 1, 'Public Cross-border Indicator Record Routing': 1, 'Public Grant Intake Record Routing': 1, 'Public Demographic Planning Record Routing': 1, 'Public Economic Sector Record Routing': 1, 'Public Age-share Planning Record Routing': 1} |

## Misleader Types By Severity

| Severity | Misleader Types |
|---|---|
| none | {'MS_unconventional_scale_directions': 13, 'categorical_encoding_for_continuous_data': 1, 'small_size': 1, 'MS_inappropriate_scale_range': 2, 'misleading_annotations': 10, 'data_visual_disproportion': 3, 'dual_encoding': 9} |
