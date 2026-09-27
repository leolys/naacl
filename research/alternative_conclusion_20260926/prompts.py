"""Frozen-stage prompt candidates for a conclusion-first development diagnostic.

The old-question arm is an adaptation of v3's questioning objective to this
shared schema, NOT a verbatim reproduction of the historical prompt/protocol.
No task identities, outcome labels, comparison arm, or answers occur here.
"""

COMMON = """
Use only the supplied complete page image, public goal, current public state,
actual public history, public options, and candidate records. Candidate records
and the pending actor proposal are not external evidence or answer keys.
Return concise, checkable argument records, not private reasoning transcripts.
Do not use hidden answers, underlying data, another chart version, or earlier
verifier verdicts. Neither printed labels nor customary geometry has automatic
precedence. Do not invent marks, values, entities, task policies, uniqueness,
or time conditions to complete an argument.

An O-B-C chain is self-contained:
O is a list of localized literal marks, inscriptions, colors, positions,
lengths, and screen-space relationships actually visible in the image.
Public task requirements are not image observations; cite those requirements
explicitly in B where needed. Decoding a color/position/length into meaning,
semantic ranking, and reading hypotheses belong in B, not in O.
B states the conditional bridge from O and the public task to C, with the
adopted reading assumptions and comparison scope in conditions. A hypothesis
may be unverified but must be motivated by public or visible cues. B must not
merely assume the desired C in other words.
C states a concrete, testable task candidate under the adopted reading. It
may later prove wrong. Do not replace C with uncertainty or a missing-evidence
note. Unresolved searches can remain outside the chain. C.option_label is an
exact string from public options if C supports that option, otherwise null;
null is allowed for a concrete comparison or negative conclusion.

Do not modify or silently discard supplied initial chains. Order and repeated
claims confer no authority. Candidate generation and independent verification
are separate stages. No candidate, question, or check authorizes an action or
submission. Return only JSON matching the supplied schema.
"""

INITIAL = """Examine the full image and public task. Generate up to three distinct
O-B-C candidates motivated by plausible readings of the displayed chart.
This is a maximum, not a quota. One candidate may suffice; candidates may
agree or disagree. Use unique IDs such as c1, c2, c3. Do not take the pending
actor choice as the answer. A candidate may adopt an explicitly stated,
unverified decoding assumption without first proving its applicability.
Each candidate must contain literal O, a conditional B, and a concrete C.
If no complete candidate can be formed, return an empty chains list and explain
the specific limitation in notes without inventing observations. notes is a
brief account of coverage/limits, not a verdict or completeness guarantee.
Output {"chains":[{"id":"c1","O":[{"location":"visible location",
"content":"literal observation"}],"B":{"rule":"conditional bridge",
"conditions":["adopted reading and scope"]},"C":{"claim":"concrete candidate",
"option_label":null}}],"notes":"coverage and remaining limits"}.
""" + COMMON

QUESTIONS_OLD = """Inspect the whole initial candidate set and the image for useful
questions about omitted observations, rule conditions, or explanation coverage.
Ask at most two questions; zero is allowed. Preserve all initial candidates.
A publicly motivated but unrepresented reading may deserve a question before
its applicability is verified. A question may lead to more evidence, a clarified
condition, a new candidate, or no addition. Agreement is allowed; do not
manufacture conflict or require more chains merely to increase their count.
Questions are not verdicts. Use unique IDs such as q1, q2. Write each as a
specific checkable question. summary states what was inspected and remaining
limits, not proof of complete explanation coverage.
Output {"questions":[{"id":"q1","question":"checkable question"}],
"summary":"coverage and remaining limits"}.
""" + COMMON

QUESTIONS_NEW = """Search for other concrete task conclusions that this image
might support. The purpose is to expand the possible conclusion set, NOT to
criticize, disprove, or interrogate the existing O, B, or C. Treat existing
conclusions only as a set to avoid duplicating, not as correct answers.

Re-observe the full image. Starting from a plausible DIFFERENT concrete task
conclusion, look back for locatable visual cues that could motivate it. A
different conclusion can concern the selected entity, comparison direction,
trend class, scope, or task action. It need not be the logical negation of an
existing conclusion. This is a search hypothesis, not a required answer.
Do not guess an arbitrary alternative and then invent evidence for it.

Ask at most two search questions. In each question, explicitly name the
possible concrete conclusion being explored and the visible location/cue to
re-examine for its candidate basis. Ask whether that reading can yield a
complete O-B-C candidate. Do not merely ask whether an old chain is wrong,
which old condition is missing, or which encoding must have authority.
Reading priority need not already be established to explore a clearly stated
conditional candidate. Later verification assesses applicability.

If the initial set already represents the plausible alternative conclusions
and bases you found, or no additional image-grounded possibility is apparent,
return questions=[] and state what was inspected. Do not force an opposing
answer, an extra chain, or a fixed number of questions. Avoid cosmetic
paraphrases of existing candidates. Use unique IDs such as q1, q2. Questions
are exploration targets, not observations, final conclusions, or verdicts.
Output {"questions":[{"id":"q1","question":"Could [specific candidate C]
follow under a reading motivated by [locatable visible cue]? Can that reading
form an O-B-C candidate?"}],"summary":"coverage and remaining limits"}.
""" + COMMON

SUPPLEMENT = """Respond to every supplied question using the same full image,
public task, and entire initial set. Preserve all initial chains unchanged.
Add at most two self-contained new O-B-C candidates, never to fill a quota.
A new candidate must offer a materially different conclusion or inferential
basis; cosmetic paraphrases do not count. Its C may agree with an existing C.
Use new chain IDs such as n1 and n2 that do not collide with initial IDs.

For an image-grounded reading, state actual visible O, explicit conditional B
and scope, then concrete C. An unverified reading assumption is permitted;
unclear precedence alone does not prevent articulating its conditional C.
Do not fabricate O, smuggle in task policies, or make B a restatement of C.
Do not decide which candidate wins and do not rewrite the initial chains.

Return exactly one response for every actual question ID. Use outcome new_chain
when the response produced at least one new chain and list its exact IDs;
already_covered when the existing set covers it (explain which existing chain
in reason); no_grounded_candidate when no distinct complete candidate could
be formed (explain the search and limitation). The latter two outcomes have
new_chain_ids=[]. Every added chain must be linked by at least one response.
Different questions may point to the same added chain. For zero questions,
return both arrays empty. Do not claim a new candidate was added if it was not.
Output {"new_chains":[],"question_responses":[{"question_id":"q1",
"outcome":"no_grounded_candidate","new_chain_ids":[],
"reason":"specific account of coverage or search result"}]}.
""" + COMMON

VERIFY = """Independently check every supplied chain without choosing a winner,
changing any C, or executing an action. Do not infer truth from chain order.
The inputs do not include the questions or a preferred candidate origin.
Assess the original candidate as written; do not silently repair its premises.

For each chain give three SEPARATE judgments:
O_status supported/refuted/uncertain: are its literal image observations
actually visible? A printed value is an inscription, not proof of underlying
data accuracy. A decoded semantic rank or trend is not a literal observation.
B_status supported/refuted/uncertain: do the current image and public task
support the adopted decoding rule, mapping, scope, and conditions? A logically
sensible conditional alone is not evidence it applies. An explicit but
unestablished reading assumption belongs here as uncertain, not automatically
as an inference gap. Identify supporting or contradicting visible/public cues.
inference valid/invalid/incomplete: assuming the chain's stated O and explicit
B/conditions, does its specific C follow? A rival reading or uncertainty about
B applicability does not itself invalidate a conditional derivation. Mark
incomplete for a necessary premise not stated sufficiently; identify that
premise. Do not borrow comparisons from another chain. Contradictory premises
cannot justify arbitrary conclusions. Failure to derive C does not derive
not-C; one item exceeding another does not prove a global maximum.

In reason explain the separate grounds for all three judgments. In
visible_evidence cite actual visible locations/literal content or exact public
task requirements, not hidden data or candidate repetition. Include one check
for every actual chain ID, no extra IDs. Preserve disagreement and uncertainty
in the judgments, never by replacing the candidate C with 'unknown'.
Output {"checks":[{"chain_id":"actual ID","O_status":"supported",
"B_status":"uncertain","inference":"valid","reason":"separate grounds",
"visible_evidence":["specific visible or public evidence"]}],
"summary":"scope and limitations of these fallible checks"}.
""" + COMMON

PROMPTS = {
    "initial": INITIAL,
    "questions_old": QUESTIONS_OLD,
    "questions_new": QUESTIONS_NEW,
    "supplement": SUPPLEMENT,
    "verify": VERIFY,
}
