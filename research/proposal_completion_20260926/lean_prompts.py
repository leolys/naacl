"""Fresh concise prompts: no concatenation of historical OBC instructions."""

PROPOSE = '''Counterquestion: could another image-grounded reading lead to a task
conclusion? Record up to two exploration proposals, not a final answer.
For each give a tentative conclusion, locatable visual cues to examine, the
reading rule to try, and explicit assumptions. A reading rule must apply to
other objects too; assuming the desired answer is not a rule. Use public options
exactly when applicable. Existing action labels are only previous candidates,
not facts. The same action with a different basis is allowed; you have not been
given the old arguments, so do not declare their evidence coverage complete.
Do not reject a proposal merely because it conflicts with a previous choice or
its reading has not been verified. Do not decide which reading wins here.
Do not invent visible marks, values or business rules, or change the public task.
Return zero proposals if none is apparent; never force opposition or a quota.
Give concise records matching the schema. Put each possibility in proposals,
not only in notes. Notes describe inspection scope, not a truth verdict.'''

EXPAND = '''Express the supplied exploration proposal as one self-contained O-B-C
candidate using the same image and public task. O lists located literal marks,
text, colors or spatial relations, not decoded ranks. B states the reading rule
and explicit conditions connecting O to the proposed C. C is a concrete task
conclusion under those conditions, not "uncertain". Preserve the proposal's
conclusion, reading and assumptions; do not substitute another candidate.
This stage articulates, not verifies: disagreement with an old answer or lack
of verification of B is not a reason to discard the proposal. Do not decide
which chain wins or whether another chain already covers it.
Do not fabricate observations, invent task policies or make B assume C.
If a concrete necessary ingredient cannot be stated from the image and the
proposal, report unexpanded with that specific gap and no chain. The original
proposal will remain recorded. Otherwise return expanded with one complete
chain. Use the supplied proposal_id; explain any remaining limitation briefly.'''

VERIFY = '''Check every supplied O-B-C record independently against the image and
public task. Do not rewrite a chain or choose an action. For each give separate
judgments: O supported/refuted/uncertain for literal visible observations;
B supported/refuted/uncertain for applicability of its stated reading, task
conditions and comparison scope; inference valid/invalid/incomplete for whether
C follows assuming its stated O and B. An unverified B does not alone invalidate
a conditional inference; writing "if" does not make B applicable. A conflicting
reading is not by itself a refutation. Do not invent a different business metric
or extra uniqueness requirement. Cite visible/public evidence, keep enum labels
consistent with your reasons, and flag concrete gaps or contradictions. Give
exactly one check per chain ID. These are fallible checks, not human approval.'''

PROMPTS = {'propose': PROPOSE, 'expand': EXPAND, 'verify': VERIFY}
