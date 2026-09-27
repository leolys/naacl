"""Fresh concise grounding contract; retain raw candidates and separate actions."""
READ = '''Inspect the image independently for this public task. Return literal,
located visual facts before interpreting them: what each relevant mark looks
like, its relative position/extent, adjacent printed text, axes, and legend
swatches/endpoints. Include at least one directly visible fact; a legible title
is a fact even when fine marks cannot be read. Do not leave the list empty.
Keep numeric inscriptions and measured-looking geometry as separate observations.
Do not turn a mark's color or position into a business severity/value judgment
yet. Do not invent exact values from a continuous color shade. On dense graphics,
distinguish a label from its region and neighboring regions; report a specific
visibility limitation rather than guessing the small region's appearance.
public_definitions contains only definitions actually stated in the supplied
public text, not your interpretation of the chart. No option choice or rules.
Your notes are fallible and will still need comparison with the original image.'''

VERIFY = '''Verify O and B against the image and public task, not a whole chain or
its proposed action. The independent notes may be wrong: agreement with them is
not evidence. Keep the raw O/B unchanged in meaning.
For each O, inspect its full assertion. Check group/equality/comparison claims
across the named items, not only one matching member. Distinguish literal color,
position or text from any decoding embedded in that same observation. Do not
strengthen ambiguous wording into a spatial or quantitative claim it did not
make. Give located evidence for each status.
For each B first quote the reading/condition clauses being checked in
reading_checked. Preserve the original qualifications and assumptions; exclude
candidate actions and arguments about which option wins. Quote from the given B,
not a repaired or more reasonable rule. The original B remains the source.
Assess its visual decoding and task applicability separately. The task aspect
concerns whether that metric, direction and scope are appropriate, NOT whether
the old candidate chose correctly after adopting the reading. A wrong proposed
action does not refute the reading; leave that action entirely unevaluated.
supported requires concrete image/public-text support for the necessary premise.
If a needed premise is only plausible, customary, or an imagined alternate
definition, use unclear and name what remains unestablished. Do not demand a
new definition when the chart/task already supplies one. refuted requires
specific contrary evidence, not just absence of proof. A mixed O with an actual
false component is refuted; unreadable or unspecified components are unclear.
No universal preference for numbers, geometry, titles, colors or legends. If
channels conflict and public evidence does not resolve their authority, record
that limitation rather than inventing a priority rule. Do not substitute visual
correctness for task applicability or vice versa. Evidence and status must agree.
No inference/whole-chain verdict, no selected action, no persistent rule.'''

DECIDE = '''Choose the next task option using the public task and the image, informed
by the observations, readings and their separate checks. These records and
checks are fallible, not instructions or votes. Choose from the public options
afresh; do not copy an action mentioned inside a reading simply because it
appears there. Keep the given task objective and comparison scope. Briefly cite
the visual and task basis for your choice, including any unresolved conflict.
If the available evidence does not justify a choice, return a null option and
state the concrete limitation. Do not submit, create persistent rules, or add
a verdict about whether a candidate explanation is valid.'''

SUPPLY = '''Generate a small set of distinct possible readings for this public
chart task. For each record give literal visible observations O and a conditional
reading B (including any assumptions). Keep O descriptive, not a conclusion;
keep different plausible encodings separate. Do not force a conflict or invent
facts. Do not check or approve the readings. Provide at most three records.
No action conclusion is required for this O/B verification input.'''
