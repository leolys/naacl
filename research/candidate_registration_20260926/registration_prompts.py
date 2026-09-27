"""Two counterquestion implementations; no ordinary-reread comparison arm."""

REGISTER = '''Counterquestion: looking again at the chart, could another reading lead
to a task conclusion? Register the readings you actually form now, before
judging whether they are new or best. Existing action labels are previous
candidates, not facts. Keep a conclusion you just reached even if it seems
preferable; do not silently make it the reference and then seek a third answer.
Repeated conclusions and different bases for the same conclusion are allowed.
For each candidate give its task conclusion, locatable visual cues, the reading
rule to try, and explicit assumptions. A rule must apply to other objects too,
not assume the desired answer. Use public option labels exactly when applicable.
This stage registers possibilities, not verified winners. Do not reject a
reading solely because it conflicts with an earlier choice or is unverified.
Do not invent visible marks, values or task policies. Return up to two records;
zero is allowed if no candidate can be articulated. Do not force opposition or
fill a quota. Put every conclusion you report in candidates.'''

COVERAGE = REGISTER + '''
Consider distinct task-relevant readings from encodings actually present:
text and numbers, position and size, color and its mapping. Having an answer
from one reading is not a reason to skip another available reading. These are
optional routes, not a checklist requiring one candidate each. Preserve readings
separately before resolving their compatibility.'''

REGISTER_PROMPTS = {'registration': REGISTER, 'coverage': COVERAGE}
