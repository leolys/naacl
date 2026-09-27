"""Concrete condition tests and sufficient comparisons; new standalone prompt."""
READ = '''Read the image for the public task, without selecting an action.
appearance_facts: record visible marks, entity bindings, page positions, colors
and relative extents. For a queried point, also locate relevant labeled reference
points on its OWN series and describe whether it lies above, below or between
them. These are page relations, not cross-series numerical comparisons.
printed_facts: transcribe actual axis/legend inscriptions, units, dates, and
numerical annotations, each bound to its mark/series/location. Include references
needed for the query even at other dates. Do not put visual estimates among
printed numbers. Group facts within the eight-item limits.
public_definitions: quote the actual task scope and applicable option conditions.
uncertain: identify specific unresolved bindings or readings. Do not invent a
legend from a line style, a threshold, an unshown time segment, or a source
priority. Read date order and tick directions literally. Keep conflicting
channels distinct. Notes are fallible observations, not approved interpretations.'''

VERIFY = '''Evaluate the original O assertions and whether each reading B applies
to this chart/task. Do not judge an O+B=>C inference or select an action.
O: check exactly what is asserted. Do not insert 'only', 'all', or a causal
claim that was not there. An additional unmentioned mark does not refute an
existential observation. Cite located support or a genuine contradiction.
B: retain its full text AND conditions in reading_checked. In evidence,
identify its necessary conditions and perform concrete tests with public facts.
Do not answer 'if we assume this, it works': that is not an applicability test.
For a proposed decoding, ask whether the known labeled references would have
the relations it predicts. Use each series' own labels/ticks/legend binding;
explicitly compare reference order with page order before endorsing a common
scale. Where same-series monotonic coding is supported, surrounding labeled
marks can bound an unlabeled target without knowing its exact value. State
the bounds. Non-overlapping bounds can settle a comparison without common axes.
Interpolation or extrapolation requires a justified scale form; disclose it.
For a task condition, check the stated population, date window, units and each
inequality boundary. A visible subset does not establish the whole population
or window. Distinguish the name/position of a reference line from a checked
aggregate over the relevant members. Do not expand a policy interval to fit
an estimate or infer a policy solely because another policy is absent.
supported: necessary conditions actually have public/visible support. refuted:
at least one necessary condition has contrary evidence. Otherwise unclear,
stating which part remains open. Ordinary word meanings need not be separately
legislated. Do not replace the original B or claim a whole chain is valid.'''

DECIDE = '''Make the requested public choice using the image, task, and fallible
O/B checks. Briefly give the evidence-derived comparison and its route mapping.
Check the strongest relevant evidence before declaring the choice unresolved:
use same-series references, numerical bounds, actual date order, legend mappings
and task scope. Exact values are unnecessary when justified bounds or ordinal
relations already distinguish the options. Separate axes alone do not prevent
comparison; cross-axis page height alone does not establish it.
Do not inherit an unsupported assumption just because a check calls it supported;
read its cited evidence. Apply all explicit task constraints as written. A range
that excludes your own estimate cannot be chosen as the 'closest' range. Missing
years do not become observed years, and a clipped visible extent is not the full
quantity. Missing evidence for one reading does not establish another reading.
If an option explicitly accommodates the limited evidence, assess that option
on its own conditions, without inventing earlier history or a default policy.
Another publicly supported reading may justify a choice even if every original
B failed; name that actual evidence. Preserve unresolved source conflicts and
state any justified interpretation used. No universal source priority, external
facts, guessed tie-break, or arbitrary threshold. Return null only when no
available option is justified. Do not submit or produce an inference verdict.'''
