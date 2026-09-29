---
id: rebuttal_chart_verification_playbook_v2
name: Evidence-First Chart Decision Playbook
description: Structured visible-evidence verification for chart-grounded browser decisions
type: playbook
priority: 90
enabled: true
triggers:
  always: true
---

# Evidence-First Chart Decision

Before selecting or submitting a form option derived from a chart:

1. Define the decision.
   Identify the target metric, required operation (max, min, comparison,
   trend, or ratio), unit, time range, relevant candidates, and downstream action.
   Treat the visible form options as the operative decision candidate set; a
   chart entity without a visible option cannot be the submitted choice.

2. Build a compact evidence ledger.
   For each visible selectable candidate, record the visible value or relation,
   evidence source (data label, axis, legend, mark, or annotation), axis/legend
   mapping, and readability (clear, ambiguous, or unreadable).
   Never invent a value that is not visibly readable.

3. Run only applicable checks.
   Verify axis direction, baseline, tick spacing, scale and units when present.
   Bind each series to its own axis and never compare heights across incompatible
   axes. Treat annotations as claims that must be checked against marks or labels.
   For temporal or cumulative claims, inspect the full task-relevant range.
   Validate size, area and color encodings against the legend and readable labels.

4. Compute and lock the decision.
   Apply the requested operation to the ledger. Confirm that the chosen form
   option maps exactly to the resulting entity; do not change it based only on
   visual salience. If a global chart extreme has no visible form option, do not
   stop; recompute the decision within the visible selectable candidate set.

5. Handle uncertainty once.
   If evidence is unreadable or contradictory, perform at most one additional
   chart inspection or QA pass. After that, choose the option best supported by
   visible evidence and continue the workflow. Do not invent values, loop, or
   refuse solely because exact values are unreadable or because an unlisted
   chart entity appears stronger than the available options.

6. Complete the workflow.
   Once the evidence and form mapping are consistent, submit the form once.
