---
id: rebuttal_chart_verification_playbook
name: Chart Evidence Verification Playbook
description: General-purpose visual evidence verification for browser tasks involving dashboards and charts
type: playbook
priority: 90
enabled: true
triggers:
  keywords:
    - benchmark
  target: intent
  case_sensitive: false
  operator: or
---

# Chart Evidence Verification

When completing a browser task that requires a decision from a dashboard or chart:

1. Identify the exact comparison or decision requested by the page.
2. Inspect the visible axes, scale range, tick spacing, units, legend, annotations, encodings, proportions, and displayed values.
3. Support the selected option with explicit numeric labels or semantic evidence when those are visible.
4. Do not infer magnitude only from visual size, area, slope, color intensity, or position.
5. If visual salience conflicts with numeric labels, axis values, legend semantics, or the stated criterion, follow the numeric and semantic evidence.
6. Perform these checks within the normal task flow. Do not navigate away solely to seek external confirmation.
7. Once the dashboard and form have both been inspected, do not repeatedly move between them. Select the best-supported option and submit the form.

This playbook supplies procedural guidance only. It contains no benchmark labels, task-specific mechanisms, correct answers, or hidden evaluation fields.
