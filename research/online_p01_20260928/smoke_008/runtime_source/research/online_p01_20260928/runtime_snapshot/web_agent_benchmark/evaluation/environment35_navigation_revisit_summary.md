# Environment 35 Navigation Revisit Metrics

- Generated at: 2026-05-07T20:13:09.630935+00:00
- Source runs: web_agent_benchmark/evaluation/environment35_gpt54_runs.jsonl
- Total tasks: 35
- Loop severity distribution: {'none': 35}

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
| none | {'success': 22, 'misleading_failure': 13} |

## Templates By Severity

| Severity | Templates |
|---|---|
| none | {'Temperature Change Routing': 1, 'Environmental Trend Escalation Routing': 9, 'Energy Source Priority Routing': 4, 'May Low-output Severity Routing': 1, 'Source Contribution Priority Routing': 5, 'Monthly Low-output Review Routing': 4, 'January Air Quality Alert Count Classification Routing': 1, 'January River Discharge Classification Routing': 1, 'January Air Quality Alert Classification Routing': 1, 'January Inflow Classification Routing': 1, 'Clean Grid Output Trend Routing': 1, 'Regional Air Quality Recovery Trend Routing': 1, 'River Restoration Capacity Trend Routing': 1, '2010 Fuel Supply Routing': 1, '2010 Clean Grid Share Routing': 1, 'Service Support Cost Routing': 1, 'Energy Cost Review Routing': 1} |

## Misleader Types By Severity

| Severity | Misleader Types |
|---|---|
| none | {'MS_inappropriate_scale_functions': 14, 'MS_inappropriate_scale_range': 5, 'data_visual_disproportion': 5, 'misleading_annotations': 7, 'dual_encoding': 3, 'MS_unconventional_scale_directions': 1} |
