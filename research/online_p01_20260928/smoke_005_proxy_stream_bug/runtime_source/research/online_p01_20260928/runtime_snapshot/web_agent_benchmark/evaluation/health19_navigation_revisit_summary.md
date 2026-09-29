# Health 19 Navigation Revisit Metrics

- Generated at: 2026-05-08T18:04:32.487518+00:00
- Source runs: web_agent_benchmark/evaluation/health19_gpt54_runs.jsonl, web_agent_benchmark/evaluation/health19_gpt54_runs.jsonl
- Total tasks: 19
- Loop severity distribution: {'none': 19}

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
| none | {'success': 9, 'misleading_failure': 10} |

## Templates By Severity

| Severity | Templates |
|---|---|
| none | {'Annual Mortality Escalation Routing': 1, 'Surveillance Trend Escalation Routing': 1, 'COVID-19 Inpatient Capacity Routing Review': 1, 'Physician Capacity Monitoring Triage': 1, 'Laboratory Testing Capacity Escalation Routing': 1, 'Hospital Screening Referral Monitoring Escalation': 1, 'Sentinel Site Positive Test Routing Review': 1, 'Respiratory Outpatient Volume Escalation Routing': 1, 'Telehealth Follow-Up Enrollment Escalation Review': 1, 'Asthma Service Review: PM2.5 Exposure and ER Visit Pattern Routing': 1, 'Screening Center Outreach Pattern Escalation': 1, 'Sentinel Site Testing and Positivity Review Routing': 1, 'Nursing Staffing and Discharge Throughput Escalation Review': 1, '2017 Transplant Volume Comparison Routing': 1, 'Adolescent Breakfast Cereal Follow-up Routing': 1, 'Emergency Department Utilization Escalation Review': 1, 'Telehealth Follow-up Demand Escalation Routing': 1, 'Respiratory Infection Surveillance Escalation Routing': 1, 'Screening Referral Escalation Routing': 1} |

## Misleader Types By Severity

| Severity | Misleader Types |
|---|---|
| none | {'MS_unconventional_scale_directions': 5, 'cherry_picking': 8, 'dual_axis_distortion': 2, 'misleading_annotations': 4} |
