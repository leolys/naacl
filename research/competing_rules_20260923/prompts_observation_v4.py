"""Generic observation/interpretation boundary; no task IDs or preferred answers."""

OBSERVATION_CONTRACT = """Keep O, B, and C separate; an already interpreted result is not an observation.
O (observations) contains only directly visible marks and literal inscriptions:
- entity labels and their visible attachment to marks; colors, shapes, lengths,
  positions, alignment and screen-space comparisons;
- exact text/numerals visibly printed on the image, explicitly described as
  inscriptions and located next to the relevant mark, tick or legend swatch;
- visible relationships between marks and printed ticks, with uncertainty if needed.
For example, 'the final point is lower on the page than the initial point' is
geometry, whereas 'the measured quantity decreased' already applies a mapping.
A mark between two labeled ticks is visible; its interpolated numeric value is
derived. A printed number may be transcribed, but is not thereby validated as true.
Do not put decoded metric ranks, metric trends, unprinted numeric estimates,
computed means/differences, causal or business implications, or recommended
actions in O. These remain interpretations even when they happen to be correct.
Do not copy an actor's brief_basis, an earlier verdict, or a candidate rule into
O as if it were a fresh visual fact. Identify literal quotation as quotation.
Each observation should be a short, localized fact, not a fact followed by 'so'.

B (rules) states the conditional bridge from these facts to task meaning:
encoding direction, series/axis/entity binding, scale comparability, numeric
decoding or calculation, and any needed task-to-action relation. Put assumptions
and their scope here, not inside O. Several necessary clauses may form one rule.
Do not omit the encoding bridge by placing the decoded ordering in O and using
a tautology such as 'choose the largest' as the whole B. Do not store a winning
entity or chosen option as the rule itself.

C (claim) states the derived interpretation and its task implication, marking
estimated numeric results as estimates. The option_label carries the final choice.
Raw marks and literal text may support or conflict with an interpretation;
neither customary geometry nor printed labels are automatically authoritative.
If the public evidence is insufficient, preserve uncertainty instead of inventing
a value, mapping, policy threshold, or opposite answer."""

GENERATOR = """Create concise checkable argument records for this proposed chart decision.
Use only the full observed chart, public task, actual history and supplied rule state.
Return JSON {"rules":[{"id":"r1","text":"conditional interpretation relation, not an answer",
"component":"actually involved encoding or task relation","conditions":"scope and assumptions"}],
"chains":[{"observations":[{"ref":"chart_1","location":"visible area","content":"direct visible fact"}],
"rule_id":"r1","option_label":"exact public option","claim":"derived interpretation and task implication"}]}.
Include the argument needed for the proposed choice, even if it has an evidence gap,
then at most two substantively different competing explanations. Alternatives may
support the SAME action on different grounds. Never force an opposite answer.
""" + OBSERVATION_CONTRACT + """
Competing interpretations may share the same raw observations; vary the disputed
bridge or its scope rather than rewriting an interpretation into a different O.
Normalize semantically identical rules to a shared ID; preserve distinct entity
comparisons. Duplication is not corroboration. Include every necessary bridge
clause in the chain's single referenced rule record; do not list an unused
encoding rule while assuming it silently in O.
Use short argument records, not a long step-by-step reasoning transcript."""

VERIFIER = """Independently verify normalized argument records against the FULL observed
chart and public task. Their order, repetition and origin are not evidence.
Check O (direct observation/entity binding), B (conditional interpretation within
scope), and implication (whether the premises suffice for the complete task).
Return JSON {"checks":[{"chain_id":"c1","O":"supported|refuted|undetermined",
"B":"supported|refuted|undetermined","implication":"supported|refuted|undetermined",
"evidence":[{"ref":"chart_1","location":"visible area","content":"direct visible fact"}],
"reason":"brief separate explanation of observation, rule and implication checks"}],
"recommendation":"exact option label or null","unresolved_reason":"string"}.
""" + OBSERVATION_CONTRACT + """
Check the observation boundary BEFORE endorsing a chain. If O embeds decoded
semantics, arithmetic or a conclusion, do not silently repair or approve that O:
mark O undetermined and name the embedded inference in reason. This is a failure
to separate representation layers, not proof that the conclusion is factually false.
Judge B independently; an incorrectly placed inference alone does not refute B.
Evidence.content must also contain raw visible facts or located literal quotations;
put their decoding, calculations and inferential role in reason, not in evidence.
A generator rule, earlier verdict or actor assertion is never evidence for
itself or any other rule. Verify B only from chart, page or public-task evidence;
do not attribute a claim to a page or chart where it is not visibly written.
Distinguish an explicit public routing rule from an inference based on option
wording. Evaluate the latter as an inference; do not call it a printed policy.
Use undetermined when evidence is insufficient. Refuting one candidate is not
proof another is globally best. Opposing rules can both be undetermined.
Do not assume reversing a refuted mapping is valid. All chains must be checked.
Recommend an option only if a chain has direct, supported O, applicable B and
sufficient implication. Do not force agreement, reversal, or a recommendation."""
