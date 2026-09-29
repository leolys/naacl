# GUI-Reflection expanded targeted-recovery results

Date: 2026-09-01

## Bottom line

The expanded experiment does **not** support either extreme claim that
GUI-Reflection solves misleading-chart tasks or that it never helps.  It
separates three boundaries:

1. On five more complex, non-title templates, this checkpoint did not first
   establish clean end-to-end competence.  Those cases cannot identify a
   recovery failure.
2. On the controlled `pub010` title intervention, the model is clean-competent
   and naturally susceptible, but neutral F0 review and an evaluator-owned F3
   outcome contradiction did not make it retract the misleading visual premise
   in the tested deterministic cells.
3. On controlled `b035`, evaluator-owned F3 causes `Back` and correct action
   rebinding in both arms, but the misleading arm still fails to Confirm.  This
   is semantic recovery without end-to-end recovery under explicit external
   contradiction feedback.

The evidence therefore supports a narrower research claim: with explicit
external contradiction feedback, this trajectory-correction checkpoint can
supply navigation reversal and sometimes semantic correction, but it does not
reliably invalidate the visual premise that selected the old action, and it
does not reliably carry a corrected decision through Confirm.

## Controlled rendering

`matched_annotation_v1` redraws each official/clean pair from the shared
canonical CSV with the same 1000×750 canvas, renderer, fonts, axes, data line,
colors and margins.  Only the title string is arm-dependent.  Pixel checks
found zero differences outside the union of the two title glyph masks:

| case | differing pixels | diff bbox | outside title mask |
|---|---:|---|---:|
| `pub010` | 8,494 | `[98, 24, 901, 46]` | 0 |
| `b035` | 7,527 | `[164, 24, 836, 46]` | 0 |
| `b038` | 6,239 | `[199, 24, 803, 46]` | 0 |

The manifests bind separate pair/task/scorer/validator identities and retain
canonical CSV and HTML hashes.  These are controlled diagnostic interventions,
not canonical release renders or benchmark accuracy measurements.

## Case-by-case results

### `pub010`: strongest controlled failure

The data rise overall from 993 in 1880 to 2,917 in 1891.  The clean title says
increasing; the misleading title says decreasing.  Correct action is growth
planning and the canonical trap is decline response.

#### Natural track, L0/L1/L2

Across all three role-blind card layouts:

| arm / condition | cells | initial/final role | Back | correct submit |
|---|---:|---|---:|---:|
| clean single-attempt | 3 | correct → correct | n/a | 3/3 |
| clean F0 workflow | 3 | correct → correct | 0/3 | 3/3 |
| misleading single-attempt | 3 | misleading → misleading | n/a | 0/3 |
| misleading F0 workflow | 3 | misleading → misleading | 0/3 | 0/3 |

Every misleading cell made a real decline selection and submission.  The
workflow cells consumed the review frame but simply confirmed the wrong
choice.  Clean and misleading results persist as correct/trap occupy all three
card positions.  Within each arm and layout, workflow-on/off first screenshots
and first raw model responses are identical.

#### Inherited external error, F0 versus F3

The evaluator first creates a real decline selection, records it as
evaluator-owned, resets the model to empty history/memory, and hands over the
review screenshot.  This is a capacity probe, not natural susceptibility.

At L0 under F0, all four cells remain on decline and none executes Back.
Native4 confirms the wrong choice; current-only repeats/holds it to timeout.

Under F3, the feedback says only that the inherited selection conflicts with
an independently verified outcome; it does not reveal growth or the correct
button.  The pattern is identical at L0/L1/L2:

| arm / history | cells | effective Back | correct rebind | correct submit |
|---|---:|---:|---:|---:|
| clean native4 | 3 | 3/3 | 3/3 | 3/3 |
| clean current-only | 3 | 3/3 | 3/3 | 0/3 |
| misleading native4 | 3 | 0/3 | 0/3 | 0/3 |
| misleading current-only | 3 | 0/3 | 0/3 | 0/3 |

The clean cells prove that the F3 signal and the Back/retry UI are actionable.
In the tested misleading cells, the same signal did not override the visible
false title: native4 confirms decline, while current-only remains on decline
until timeout.  Native4 history coincides with different completion behavior
here, not with improved semantic correctness.

This is a direct instance of “local action correction is not premise
invalidation.”  The checkpoint used contradiction feedback when the current
visual premise supported the correction, but did not do so in these tested
cells when the same chart continued to support the old premise through a
misleading title.

### `b035`: partial positive result

The production line falls overall.  The clean title says decreasing and the
misleading title says increasing.  Correct action is production-efficiency
review; the trap is capacity-expansion planning.

On the natural matched track, clean is correct in 2/2 cells.  Misleading is
wrong in 2/2 cells, but selects the neutral routine-monitoring action rather
than the capacity trap.  Thus the title conflict disrupts correct action
binding without producing exact trap-following.

Under inherited F0, all four cells remain on the injected capacity trap and
none executes Back.  Under F3:

| arm / history | Back | correct rebind | correct submit | terminal behavior |
|---|---:|---:|---:|---:|
| clean native4 | yes | yes | yes | full recovery |
| clean current-only | yes | yes | no | repeats correct selection to timeout |
| misleading native4 | yes | yes | no | emits `TASK_COMPLETE` without Confirm |
| misleading current-only | yes | yes | no | repeats correct selection to timeout |

This is evidence that the GUI-Reflection checkpoint, after evaluator-owned F3
contradiction, executed semantic recovery on this misleading chart.  It also
exposes a second gap: correct premise/action rebinding is not automatically
converted into a scored submission.  Native4 history coincides with Confirm in
the one clean cell, but not in the misleading cell; this is an observed paired
difference, not a cross-case causal estimate.

### `b038`: renderer-sensitive, excluded from controlled recovery

With canonical release assets, clean was correct in 2/2 cells and misleading
selected the stable-pattern trap in 2/2.  After same-render title-only
intervention, both clean cells instead selected neutral manual review, while
both misleading cells selected the stable trap.  Because clean competence did
not survive the renderer intervention, `b038` is not used for an inherited
recovery claim.  It is retained as evidence that apparent paired competence
can be renderer-sensitive.

### Five non-title clean screens: capability floor

The fixed clean-only queue was completed before opening any corresponding
official arm:

| case | mechanism | clean result | decision |
|---|---|---|---|
| `b008` | scatter visual disproportion | 2/2 timeout, no selection | reject |
| `env003` | pie scale function | Hydroelectric trap in both cells | reject |
| `pub012` | reversed choropleth legend | NY trap in both cells | reject |
| `pub009` | truncated scale + aggregation | neutral Thu-only in both cells | reject |
| `env025` | wrong average + arithmetic | 2/2 complete without selection | reject |

These cases show where the current checkpoint lacks clean task competence.
They must not be described as reflection failures: no trustworthy clean
premise-to-action mapping exists to recover.  They are still useful design
evidence that a future method needs stronger visual evidence acquisition and
grounding before premise revision can be evaluated broadly.

## What this means for the proposed paper

The most defensible central claim is now:

> GUI-Reflection's trajectory-level correction is useful but insufficient for
> misleading visualizations.  With explicit evaluator-owned contradiction
> feedback, the tested checkpoint may reverse navigation and sometimes repair
> the decision; however it does not reliably invalidate the visual premise
> that selected the old branch, nor guarantee that a corrected branch is
> rebound and submitted.

The next method should make the missing dependency explicit:

```text
visual evidence
    -> intermediate claim (increase/decrease, largest entity, threshold)
    -> selected workflow action
```

After contradiction, the method should invalidate the claim and every action
derived from it, reacquire the relevant chart evidence, construct a competing
claim, rebind the action, and validate that the final Confirm agrees with the
new claim.  Useful components are:

1. a small premise/action ledger with provenance to chart regions or values;
2. contradiction-triggered re-observation of the decisive visual evidence;
3. explicit retirement of the old hypothesis/action, preventing immediate
   re-entry;
4. a pre-Confirm consistency check between revised claim and selected action;
5. separate handling of semantic recovery and workflow completion.

Evaluation should continue reporting the ordered layers rather than one rate:
`exposure → initial decision/action → review consumed → Back → revised
decision/action → old-branch re-entry → Confirm → hidden scorer`.

## Limits and allowed interpretation

- `pub010`, `b035` and `b038` are three tasks from one title-vs-line family,
  not three independent misleader types.
- Layout cells and history conditions are repeated measurements, not an
  increase in base-case N.
- The shortlist was enriched/adaptive; no prevalence, population recovery rate
  or significance claim is supported.
- F3 uses an evaluator-owned error and outcome contradiction.  It measures
  recovery capacity, not whether GUI-Reflection naturally detected or made the
  initial error.
- The scorer and validator are hidden from the model and model-independent,
  but are generated from canonical stores in the same experiment process; they
  are not an external service or independent human adjudication.
- Matched renders are controlled diagnostics, not canonical
  `benchmark_v2_open` scores.
- Nested `RecoveryQuartet.reportable=false` and its static publication blockers
  are conservative schema flags.  Claims here rely on raw UI/model receipts,
  model-independent scorer/validator records, and runner-level execution
  checks; they should not be presented as a released benchmark aggregate.

## Primary artifacts

- Controlled assets: `assets/matched_annotation_v1/{pub010,b035,b038}/`
- `pub010` natural L0/L1/L2:
  `runs/expanded_matched_title/pub010/`
- `pub010` inherited F0:
  `runs/expanded_inherited_f0/pub010/L0/20260831T183846Z_ab6dd2c5/`
- `pub010` inherited F3 L0/L1/L2:
  `runs/expanded_inherited_f3/pub010/`
- `b035` natural:
  `runs/expanded_matched_title/b035/L0/20260831T183321Z_0524ce46/`
- `b035` inherited F0/F3:
  `runs/expanded_inherited_f0/b035/` and
  `runs/expanded_inherited_f3/b035/`
- `b038` matched natural:
  `runs/expanded_matched_title/b038/L0/20260831T183125Z_f13b1f85/`
- Clean-only protocol and decisions:
  `EXPANDED_CLEAN_SCREEN_PROTOCOL.md` and
  `EXPANDED_CLEAN_SCREEN_DECISIONS.md`
- Independent selection review:
  `EXPANDED_CASE_RED_TEAM_SELECTION_REVIEW.md`

The pre-execution `pub010` F3 attempt rejected the accidental registration of
env008-specific F2 evidence and contains no model call.  A later L0 run was
superseded because the old runner mislabeled paired no-reversal as missing
retry instrumentation; its replacement reproduced the same behavior and is
the only L0 run used above.  Both directories retain explicit audit markers.
