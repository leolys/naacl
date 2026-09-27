"""Visible references, actual reading applicability, and explicit decision basis."""
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

DECIDE = '''Choose the next public option from the image and public task, using
the observations and O/B checks as fallible evidence, not votes or instructions.
Keep the original entities, dates, units, comparison scope and all applicable
routing conditions. Derive the relevant comparison using the visible references;
do not equate cross-axis page height with magnitude or a truncated visible
segment with the full quantity. State the actual relation/range and task mapping.
If a check left a necessary condition unresolved, do not silently treat it as
established. You may choose through another publicly supported reading: state
that replacement evidence and its assumptions, rather than copying a candidate's
action. Review remaining contradictions before selecting. Use ordinary task
meaning when sufficient; do not require an extra policy just for 'larger',
'increasing' or 'majority'. Do not invent a numerical threshold or tie-break.
Return null only if no supported route justifies a public option after considering
the available evidence; specify the concrete remaining limitation. Do not submit
or add an O+B=>C/whole-chain validity verdict. Keep the basis concise.'''
