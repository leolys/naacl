"""Final planned development alternative: appearance-first notes, one B judgment."""
READ = '''Inspect the original chart for the public task. First write appearance_facts:
literal page-space positions, extents, shapes and color relationships of relevant
marks. Entity names may locate a mark, but do not use its printed numeric label
as its apparent size. Describe higher/lower on the page, not higher/lower data
value; an axis may reverse direction or use a different scale. For any rank or
same-color claim, compare the actual marks/regions, not their nearby labels.
Do not substitute a neighboring region for a small named region. If you cannot
separate them, say so rather than guess.
Only then write printed_facts: exact inscriptions, axes, units, legend endpoints
and titles with locations. Keep these separate from the first appearance facts;
do not change one channel to agree with another. Both are fallible readings of
the same whole image, not independently isolated visual inputs.
public_definitions quotes only task definitions actually supplied. State concrete
visibility or definition gaps in uncertain. Keep at most eight brief facts per
channel: group comparisons relevant to the public choice, not an inventory of
every mark or region. Incomplete comparison remains a gap, not a guessed rank.
Do not choose an option, assign
business severity to a color, decide source precedence, or approve a rule.'''

VERIFY = '''Check observations O and readings B, not whether a candidate action is
correct or follows from a chain. The image and public task are the sources;
appearance/printed notes are fallible aids, not facts to copy.
For every complete O assertion briefly cite its visual/public support or counterevidence.
Check named members of comparisons and color groups individually. If a sentence
mixes literal appearance and decoding, check both; do not support the whole
sentence because only its appearance part matches. Do not invent a more specific
meaning for ambiguous wording. A specific contrary fact means refuted; missing
visibility or an unresolved necessary part means unclear; all factual parts
supported by the sources means supported.
For each B quote the reading and its necessary conditions in reading_checked,
excluding the candidate's proposed action and arguments about which option wins.
Retain the original conditions; do not repair or replace the rule. Give one
evidence-based judgment of that reading's applicability: supported only if its
necessary decoding and task conditions have concrete public/visible support;
unclear if a necessary condition remains only an assumption, naming that gap;
refuted only if specific visible/public evidence contradicts a necessary part,
naming that part. State what is supported and what remains unestablished briefly.
Conventional plausibility alone is not confirmation or counterevidence. Do not
assume one encoding always overrides another or invent an unstated metric.
Do not reject a reading because the candidate selected the wrong entity under
it. Do not evaluate O+B=>C, approve a whole chain, select an action, or create
persistent rules. The one B judgment is not a certificate of truth.'''

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
