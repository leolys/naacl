# Expanded clean-only competence screen

Date fixed: 2026-09-01

This screen is a development-stage inclusion check for the GUI-Reflection
checkpoint, not a benchmark score.  It prevents official-arm behavior from
being used to excuse a clean-task floor.

## Fixed queue

The five non-title templates are run in this order:

1. `b008` — scatter visual disproportion;
2. `env003` — pie inappropriate scale function;
3. `pub012` — reversed choropleth legend;
4. `pub009` — truncated stacked scale plus threshold aggregation;
5. `env025` — wrong-average annotation plus arithmetic.

The queue was enriched from existing 12-model artifacts and is therefore not
a random or held-out sample.  `pub010` and `b038` were already opened during
earlier adaptive calibration and are analyzed separately as title-vs-line
cases.  `env008` remains a development regression anchor.

## Execution and decision rule

- Source set: `strict_review94` from `benchmark_v2_open`.
- Target: official `GUI_Reflection_8b_SFT`, deterministic decoding.
- UI: compact screenshot-only renderer, canonical role-blind card layout.
- Cells: clean `single_attempt` and clean `feedback_retry/F0` only.  The runner
  records `clean_only_screen=true` and verifies that no official cell ran.
- **Natural-panel admit:** both clean cells make a real expected-action
  submission and the independent scorer returns `true` (2/2).
- **Diagnostic only:** the expected action is selected but submission is
  missing in at least one cell.
- **Reject:** either clean cell selects a misleading/irrelevant action, or a
  cell is invalid/censored.

All five clean runs and their decisions are retained before any corresponding
official compact run.  Passing this screen does not make the canonical
official/clean JPEG/PNG pair a controlled causal comparison.  A passing case
still needs a same-render intervention, with pixel differences restricted to
the declared misleader region, before a misleader-specific claim is allowed.
