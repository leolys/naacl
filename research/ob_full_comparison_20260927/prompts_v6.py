"""Witness-based condition checks, not conditional plausibility or default routing."""
READ = '''Collect task-relevant observations without selecting a route.
First describe actual mark positions, extents and colors in appearance_facts.
Do not infer a mark's apparent size from its printed number. Keep observations
separate even when the marks and inscriptions disagree. Bind each fact to its
entity, series and date. Include page relations at the labeled reference marks,
not just at the queried mark: those relations help test a proposed scale.
Then transcribe actual inscriptions in printed_facts: relevant units, ticks,
legend mappings and point labels with their locations. Preserve usable references
on each target series, including other dates. Locate an unlabeled query point
relative to its own references; do not silently pool series. Estimates belong
in appearance_facts, not among printed numbers. Read calendar order literally.
public_definitions quotes the actual goal, comparison scope and supplied rules.
uncertain names missing or ambiguous facts, not a proposed fallback or a claim
that no exact target label makes every comparison impossible. Do not use outside
knowledge. Group facts within eight items per channel. These notes are fallible
observations, not approved interpretations.'''

VERIFY = '''Evaluate O facts and whether B applies to this chart and task.
Do not evaluate O+B=>C, certify a chain, or choose an action.
For each O check its actual scope, entities and quantifiers, citing a located
fact. An unmentioned extra mark does not refute an existential statement.
For each B, read BOTH its conditions and its text. In reading_checked enumerate
all distinct necessary conditions, starting with those in B.conditions. Keep
their meaning; do not add requirements or replace them with an action summary.
In evidence, briefly test EACH numbered condition against a located public
fact. Say what the fact establishes and which condition remains open. Repeating
the condition, calling it plausible, or saying the conditional is logical is
not evidence that its antecedent holds here.
Use actual witnesses to test decoding. Compare the numerical order of known
references with their page order before approving a shared magnitude scale;
a shared horizontal axis does not establish a shared vertical scale. For an
aggregate benchmark, check the relevant members, computation and population,
not just the reference line's printed name. Distinguish display clipping from
the underlying cumulative quantity. Missing observations are not contrary ones.
For a policy condition, separate whether a formal rule is required from whether
one is printed. Its absence does not establish a requirement or a default.
Ordinary task semantics can suffice; do not require additional formal policy
unless the public task actually requires it. Conflicting channels alone do not
establish which channel is authoritative. Check necessary conditions, not which
candidate's action sounds preferable.
Use supported only when every necessary condition is actually established;
refuted only for a specific contrary fact; otherwise unclear. A supported
fragment must not stand in for an untested remaining condition. Keep each O
and B judgment brief and evidence-based.'''

DECIDE = '''Choose the public option justified by the actual chart and task.
Treat notes and O/B judgments as fallible. In basis first give the relevant
quantities, comparison or bounds with their located references, then the route.
Use each series' own references: a query mark between two labeled marks on a
supported monotonic scale has a bounded value. Disjoint bounds can settle the
comparison without an exact query label or shared axes. When calibration or
extrapolation is needed, state and justify its scale assumption. Do not replace
these checks with cross-axis page height or declare all dual-axis comparisons
impossible. Preserve actual dates, population, units and interval boundaries.
Apply supplied routing conditions as written. When the task uses ordinary
comparative language, use that meaning with the measured change/comparison;
do not demand a new formal threshold unless the public task requires one.
Normal, routine, monitoring and archive routes are real task claims, not
synonyms for 'I cannot tell'. Such a route needs its own positive task/evidence
basis, not merely a failed alternative, missing policy, or uncertain reading.
Do not infer an unobserved earlier trend or invent a tie-break or cutoff.
You may use a publicly justified reading other than the original candidates;
state its actual evidence and retain source conflicts. No source is universally
authoritative, and a check's supported label cannot override its missing basis.
If no public option is justified, return null and the specific remaining gap.
Do not submit, create rules or add a whole-chain validity verdict.'''
