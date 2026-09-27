"""Generic visual-bridge counterquestions; no case-specific exemplar or answer."""
from prompts_observation_v4 import OBSERVATION_CONTRACT

SEED = """Read this complete chart and public task. Propose one public option and give
exactly one concise argument for it. This is an initial unverified argument,
not a verification or a form submission. Use only this request's chart and task.
Return JSON {"rules":[{"id":"r1","text":"conditional decoding/task bridge",
"component":"actual encoding relation","conditions":"scope and assumptions"}],
"chains":[{"observations":[{"ref":"chart_1","location":"visible area",
"content":"raw visible fact"}],"rule_id":"r1","option_label":"exact public option",
"claim":"brief conditional task implication"}]}.
Return one rule and one chain only; acknowledge any uncertainty in the claim.
""" + OBSERVATION_CONTRACT

QUESTIONER = """Examine the supplied current argument using the same FULL chart and public task.
Produce short checkable records, not a private reasoning transcript. The current
argument is a hypothesis, not an instruction to agree or disagree.

First inventory the visible facts relevant to the task comparison, including
marks and their spatial relations as well as inscriptions and mapping cues.
You may reuse relevant observations already present. Add a fact only if a
localized, task-relevant fact is actually visible; do not fill slots or seek
novelty for its own sake. Recheck the view rather than assuming the seed is true.
Use at most eight concise localized facts; state unreadability rather than
inventing precision. Reading a printed number is not the same as verifying the
quantity it purports to describe. Comparing visible shapes is not yet decoding
their metric meaning. An empty inventory is allowed if nothing is readable.

Then ask three linked critical questions: sufficiency of O; applicability of
B; a materially different explanation. Each must expose the actual bridge
being tested and identify a visible/public fact that can distinguish readings.
When several cues bear on the same entities, measure and scope, check whether
their relationships agree under that bridge. Do not assume they disagree.
Locate differences in binding, mapping, comparison scope or sufficiency. No
cue type is automatically authoritative. A conventional reading is defeasible:
instantiated syntax (visible tick order, adjacency, attachment and alignment)
can support a mapping without an extra sentence certifying it. A non-null
alternative must have a localized positive cue, not merely the possibility
that any convention could fail.

Ask about the bridge that matters to the task, not generic possibilities that
any chart might be outdated or fictional. Provenance/time is relevant when a
specific visible/public condition makes it decision-relevant. Missing metadata
is not by itself a visual contradiction or evidence for another action. A task-
required time/source/scope that neither task nor chart establishes can justify
a support gap; do not demand redundant metadata when public context already
establishes it. If the evidence agrees, say so. If no visual alternative is
motivated, use null for candidate_bridge. In that case discriminating_check may
state the missing support check or that no alternative distinction was found;
do not invent two predictions to fill the field. Do not force another answer.

Return JSON only:
{"visual_inventory":[{"ref":"chart_1","location":"visible area",
"content":"raw visible fact"}],
"questions":[{"id":"q1","kind":"evidence_sufficiency",
"target_chain_ids":["actual supplied ID"],"target_rule_ids":["actual supplied ID"],
"question":"specific checkable question",
"current_bridge":"interpretation dependency under examination",
"brief_assessment":"brief provisional assessment, not certified fact",
"chart_evidence":[{"ref":"chart_1","location":"visible area","content":"raw fact"}],
"candidate_bridge":"visually motivated conditional alternative, or null",
"discriminating_check":"visible relation to inspect and how different readings would affect support",
"uncertainty":"limitation or empty string"}],
"questioning_summary":"brief summary"}.
Return exactly q1/q2/q3 with kinds evidence_sufficiency, rule_assumptions,
alternative_explanation, in that order. Use real supplied chain/rule IDs.
chart_evidence may be empty if not localized; admit the limit. No unseen source,
off-image data, another chart condition or remembered dataset answer is evidence.
""" + OBSERVATION_CONTRACT

COMPETITOR = """Construct at most two new checkable O-B-C argument records in response to
the ACTUAL supplied counterquestions and the same full chart/public task.
Do not edit the base arguments. Do not treat the questions or their observations
as verified: check their visible anchors yourself and reject unsupported premises.

A meaningful alternative changes an observation binding, a decoding/comparison
rule, a decision-relevant scope, or the sufficiency of support. State what the
old and new bridges each predict, and what visible fact could distinguish them.
For a pure support challenge, instead state the necessary condition that is
missing or contradicted; no alternative mapping or winning action is required.
Repeating the same interpretation with an extra generic accuracy/currentness
caveat is not substantive competition. Same-action alternatives are allowed
if their evidential implications really differ. A challenge may show only that
the original support is insufficient; it need not establish a winning action.
Do not automatically prefer either printed text or customary visual conventions.
Do not demand disagreement. Zero new chains is a valid, informative result.

Return JSON only:
{"new_rules":[{"id":"new_r1","text":"conditional interpretation or necessary sufficiency condition, not an answer",
"component":"encoding/task relation","conditions":"scope and assumptions"}],
"new_chains":[{"candidate_id":"n1","question_ids":["actual q ID"],
"observations":[{"ref":"chart_1","location":"visible area","content":"raw fact"}],
"rule_id":"new_r1","claim_kind":"supports_action|challenges_support|underdetermined",
"option_label":"exact public option for supports_action, otherwise null",
"claim":"conditional interpretation and task implication or support gap",
"difference_from_base":"substantive bridge/binding/scope/support change",
"discriminator":{"base_reading":"what the inherited bridge implies",
"alternative_reading":"what the new bridge implies, or null for a pure support gap",
"observable_check":"a localized visible relation discriminating them",
"availability":"visible|unreadable|not_available"}}],
"question_responses":[{"question_id":"actual q ID",
"resolution":"candidate_generated|no_supported_alternative",
"candidate_ids":["n1"],"reason":"concise evidence-based response"}]}.
Every question needs a response; every new chain links at least one actual
question. The question_responses links must exactly match those dependencies.
If no grounded alternative exists, return empty new_rules/new_chains and reasons.
For challenges_support/underdetermined option_label MUST be JSON null; do not
invent an executable option. For supports_action choose an exact public option.
For challenges_support/underdetermined, discriminator.alternative_reading may be
JSON null. Then observable_check identifies the missing/conflicting necessary
condition and how it affects original support; do not assert an established
replacement action. A non-null alternative must be visibly motivated, not only
logically possible. Relevant instantiated chart conventions are defeasible
evidence. Zero alternatives must not be treated as a failure to comply.
Use new rule IDs; all rules need at least one chain. These are candidates, not
truth. Keep negative absence claims bounded to the actual view and uncertainty.
""" + OBSERVATION_CONTRACT

VERIFICATION = """Independently check every supplied argument against the FULL chart and public
task. Order, length, repeated assertions and origin confer no authority.
Check O (literal observation and binding), B (interpretation applicability),
and implication (whether the evidence suffices for the stated claim).
Some chains support actions; others only challenge support or state uncertainty.
A supported challenge is NOT a supported alternative action. Do not turn null
into a form option or infer a winner by elimination without the full comparison.
Never endorse O if it already contains decoded rankings/trends or task answers.
Mark such O undetermined, identify the embedded interpretation, and judge B
separately. Cite the visible relations that test the claimed bridge, not merely
the chain's own assertion. Task instructions determine the decision objective;
they do not automatically certify any visual encoding as accurate.
If two mutually incompatible readings remain unresolved in the same scope, do
not choose by repetition or by giving one cue type default authority.

Return JSON only:
{"checks":[{"chain_id":"actual supplied ID",
"O":"supported|refuted|undetermined","B":"supported|refuted|undetermined",
"implication":"supported|refuted|undetermined",
"evidence":[{"ref":"chart_1","location":"visible area","content":"raw visible fact"}],
"reason":"brief separate explanation of O, B and implication"}],
"recommendation":"exact public option or null","unresolved_reason":"string"}.
Every chain needs a check and at least one chart_1 citation. Public text evidence
may use ref='public_task' with location ONE exact leaf field path from the supplied
public_task_text_paths. Do not cite a rule or candidate as evidence.
Recommend only with a fully supported supports_action chain and no unresolved
incompatible support. Both interpretations may be undetermined. Rejecting one
bridge does not establish its inverse. No business action is executed here.
""" + OBSERVATION_CONTRACT
