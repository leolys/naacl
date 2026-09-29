# Action Type and Workflow Instruction Requirements

This document defines how `recommended_action_type` and `workflow_instruction`
should be written after chart selection, so misleading visualization samples can
be converted into executable web-agent benchmark tasks.

## Role of the Two Fields

`recommended_action_type` defines the concrete downstream UI action that the
agent is expected to perform after interpreting the chart.

`workflow_instruction` defines the full web-agent task visible to the agent. It
must connect chart reading to a later web action, rather than asking the agent to
answer a chart question.

These fields are the bridge from a misleading chart sample to an executable web
workflow. If they are too abstract, the task collapses into single-model chart
QA and cannot measure how a misleading visualization affects web-agent
execution.

## Avoiding Chart-QA Degeneration

A valid task should have at least these stages:

1. Inspect the chart evidence.
2. Make an intermediate decision affected by the misleading visualization.
3. Navigate or operate a web page/form/dashboard.
4. Submit, save, route, select, open, assign, or otherwise execute a concrete UI
   action.

Bad pattern:

```text
Does the chart show that Q4 store visits increased?
```

Good pattern:

```text
On the business operations dashboard, review the quarterly performance chart,
determine whether Store Visits increased or decreased from Q3 to Q4, then
select the matching Q4 traffic status in the web form and submit the staffing
plan update.
```

## `recommended_action_type` Requirements

`recommended_action_type` must be directly mappable to a UI operation.

It should name a concrete action such as:

- selecting an option in a dropdown;
- checking one or more boxes;
- clicking a named workflow button;
- opening a follow-up workflow;
- submitting an alert, review ticket, or status update;
- saving a form with a specific decision.

Good examples:

```text
Select "Hold and request full regional data analysis" in the marketing budget approval form.
Submit the county dashboard update with "Night" as the target reading time slot.
Open the "Investigate Sales Decline" workflow.
Check every month that exceeded the surge threshold and submit the alert.
```

Bad examples:

```text
request_full_data_analysis
make correct decision
interpret chart carefully
answer based on the chart
```

## `workflow_instruction` Requirements

`workflow_instruction` is agent-visible task text. It should describe a complete
web workflow without directly revealing the hidden ground truth.

It must:

- mention the concrete page, form, dashboard, or portal;
- tell the agent to inspect the chart as an evidence source;
- specify the intermediate decision the chart is meant to influence;
- require a downstream web action using verbs such as `select`, `submit`,
  `save`, `route`, `open`, `continue`, `assign`, `check`, or `click`;
- include enough domain context for execution, such as campaign approval,
  staffing update, public dashboard alert, outreach scheduling, or evidence
  review.

It should not:

- expose `ground_truth_entity` or the correct answer directly;
- say "because this chart is misleading";
- only ask for a natural-language chart interpretation;
- use vague actions like "make a decision" without a UI target.

## Misleader-Specific Action Design

### `cherry_picking`

The misleading mechanism is local-to-overall overgeneralization. The chart shows
a selected subset that may suggest a relationship, but the task should ask
whether that subset is enough to support a broader conclusion.

Preferred actions:

- hold a recommendation;
- request full-data analysis;
- flag evidence review;
- open a robustness-check workflow;
- submit a "full data required" status.

The task should not ask only whether the displayed subset is positively
correlated.

### `MS_inappropriate_scale_range`

The misleading mechanism is exaggerated or compressed magnitude due to an
inappropriate scale range. The task should make that magnitude judgment matter
for a web action.

Preferred actions:

- submit or suppress an alert;
- approve or deny a promotion badge;
- select whether a threshold was met;
- mark an item for priority review;
- choose a severity level.

### `misuse_of_cumulative_relationship`

The misleading mechanism is treating cumulative growth as recent improvement.
The task should force the agent to distinguish cumulative level from latest
period change.

Preferred actions:

- update recent-quarter status;
- open a decline investigation or growth expansion workflow;
- submit a staffing adjustment;
- choose whether recent performance increased, decreased, or stayed stable.

### `misleading_annotations`

The misleading mechanism is trusting annotation text, arrows, highlights, or
claims instead of verifying the underlying values.

Preferred actions:

- select the corrected form option;
- overwrite a misleading claim in a dashboard update;
- submit the correct target audience/category/entity;
- route a claim to correction or review.

## Step-Level Error Attribution

The execution environment should be able to derive or store these evaluation
steps from `workflow_instruction` and `recommended_action_type`:

```json
{
  "evidence_reading_step": "infer the chart-relevant data relationship",
  "decision_step": "choose the correct intermediate decision",
  "web_action_step": "perform the specified UI action",
  "success_condition": "submitted_action == expected_action"
}
```

This allows failures to be categorized as:

- chart interpretation error;
- intermediate decision error;
- web action execution error;
- navigation or form submission error.

## Agent-Visible vs Evaluator-Only Text

`workflow_instruction` is visible to the agent. It should define the task and UI
goal, but should not reveal the answer.

`ground_truth_computation` is evaluator-facing. It may explain why the hidden
answer is correct and how the CSV-derived ground truth is computed.

For example, a cherry-picking task may tell the agent:

```text
On the campaign approval page, review the selected high-growth quarters chart,
then choose whether to approve the budget increase or hold the recommendation
for full-data analysis.
```

The evaluator may separately know:

```text
Because the displayed data are a cherry-picked subset, the correct action is to
request further analysis rather than approve an overall claim.
```

## Review Checklist

For each sample, verify:

- `recommended_action_type` names a concrete UI action.
- `workflow_instruction` contains chart inspection, intermediate decision, and
  downstream web action.
- The action is aligned with the sample's misleading mechanism.
- The workflow would fail differently if the agent were misled by the chart.
- The agent-visible instruction does not reveal the hidden ground truth.
- The task cannot be answered as a single-turn chart QA.
- The evaluator can map the submitted UI action to success or failure.
