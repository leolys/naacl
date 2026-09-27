"""Reuse v4 observation/check instructions; change only evidence use in DECIDE."""
READ = '''Inspect the chart for the public task without choosing an action.
In appearance_facts describe relevant marks in page coordinates: entity, date,
position, extent, shape or color. Higher on the page is not yet a larger value.
In printed_facts transcribe relevant axis/legend labels, units, tick values and
point annotations with their series and locations. Include numerical reference
points needed for the target comparison, even when they occur at other dates.
Bind each reference to its own series/axis; do not pool unrelated scales. Read
dates literally before describing chronological change. Preserve each channel
when titles, labels, geometry or reference lines disagree.
public_definitions quotes only supplied task definitions and routing conditions.
uncertain records concrete reading/coverage gaps, not a demand for an extra
policy whenever a task uses ordinary words such as larger, increasing or majority.
Group target-relevant facts, at most eight per channel. Do not invent missing
values, use a neighboring small region, silently repair an inscription, or
announce that missing target-point labels make all comparison impossible.
These are fallible observations, not approved readings or action conclusions.'''

VERIFY = '''Check the original O assertions and the applicability of each original
reading B, not O+B=>C or which candidate action wins. The chart and public task
are the sources; independent notes are fallible. Preserve every original O and
B condition, checking the complete assertion rather than only a matching part.
For O cite located support or counterevidence, checking entities, dates and
comparison direction. Missing evidence is unclear, not refuted.
For B quote the reading and necessary conditions without endorsing its action.
Test the actual decoding or task condition against visible references. A rule
of the form 'if comparable scales, then higher means larger' is not supported
merely because that conditional is logically coherent: examine the scales.
Use applicable quantitative evidence: ticks or point labels on each series,
legend mappings, date order, units, the stated population/window, or components
of a displayed aggregate. Separate plotted reference lines from recomputed
quantities; a line's name is not a check of its value or relevant population.
Where the image supports monotonic coding, known same-series values can bound
an unlabeled point; linear interpolation needs an additional justified linear
scale assumption. Do not force calibration on charts that lack such support.
Report concrete support, contradiction, or remaining condition, retaining
estimation limits. No channel universally overrides all others. Ordinary task
semantics can establish comparisons; a new policy table is not always required.
supported means necessary conditions have public/visible support, not merely
plausible convention; refuted needs actual counterevidence; otherwise unclear.
Do not replace the original B, rule on its action conclusion, choose an option,
or certify a whole chain. A failed B does not prove every other reading fails.'''

DECIDE = '''Choose from the public options using the chart and task. In basis,
give the actual quantity, bounds or ordering first, then map it to the option.
Keep all comparison entities and the requested time/population scope.
Before comparing quantities, locate each query mark relative to its OWN series'
labeled marks or ticks. On a supported monotonic scale, a query vertically
between two references has a numerical interval: write and compare the intervals.
Disjoint bounds suffice without exact query labels or a shared axis. Being
between two DATES alone does not bound the value. For interpolation/extrapolation,
use visible distances and justify the scale assumption; do not invent precision.
Other tasks may use legend, category or chronological ordering without arithmetic.
Notes and checks are fallible; recheck the image on disagreement. To use a reading
a check left unsupported, give the public evidence or ordinary task meaning that
fills its specific gap, not the same unestablished assumption. Unclear is not a
hard veto; supported is not proof. Preserve conflicts; no source always wins.
Apply supplied conditions literally. Ordinary comparisons need not have extra
formal policy. Normal/monitor/archive needs positive support, not just another
route's failure. Do not invent years, thresholds or defaults. Choose the best
publicly supported option, stating residual limits; return null if remaining
gaps leave no justified option. Do not submit, create rules or certify a chain.'''
