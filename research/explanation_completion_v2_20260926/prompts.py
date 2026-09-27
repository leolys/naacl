"""Generic v2 prompts: concrete claims, conditional derivation, separate grounding."""

COMMON = """
Use only the supplied complete chart, public task, actual public history, and
candidate records. Return concise, checkable argument records, not private
reasoning transcripts. A candidate, an actor proposal, or an earlier explanation
is not external evidence. Neither printed labels nor customary geometry has
automatic precedence. Do not use hidden answers, raw data, another chart arm,
or previous verifier verdicts. Do not invent policy, time or uniqueness demands.

O contains only localized visible marks, literal inscriptions and screen-space
relationships: colors, positions, lengths, attachments, ticks, words and printed
numbers. Decoded ranks, trends, unprinted calculations and business meanings
are not O. A printed value is an inscription, not an independently proven fact.
B explicitly states the decoding, binding, scale, scope and task-action bridge,
including the reading assumptions adopted by THIS chain. Do not hide a bridge
in O or encode a preferred answer in a supposedly general rule.
C (claim) is the SPECIFIC task-relevant conclusion under this chain's explicit
O and B: the entity, comparison, direction, scope and/or action being asserted
or rejected. Keep it in natural language, not a forced yes/no for one universal
proposition. When those premises suffice, state that conditional C even if a
different reading yields a conflicting C. Conflict between chains does NOT
erase either conditional conclusion. Whether a reading applies to this chart
is a separate verification question.
If the premises really lack a required entity, comparison, mapping or task
condition, identify the precise gap. Do not guess a conclusion. Failure to
derive a proposition is not derivation of its negation. A counterexample to
one candidate being largest does not prove a replacement is globally largest.

The aim is to complete the existing SET, not manufacture conflict, increase
chain count, or ensure correction. Preserve the whole initial set. Zero new
chains, compatible explanations, refinements, already-covered questions and
genuine support gaps are allowed. A support-gap note must not substitute for
a concrete conditional conclusion that the stated premises already entail.
If a materially different, visibly motivated reading is missing, express it
as its own O-B-C candidate, not only a warning attached to the original chain.
Do not invent an opposite reading or require a third chain when both are present.

Chart references: {"ref":"chart_1","location":"visible location",
"content":"literal observation"}. Public task references are separate:
{"ref":"public_task","path":"exact JSON Pointer from public_task_leaf_paths",
"content":"exact public value"}. Never place public text in image observations.
Keep rule/chain IDs and original text unchanged. Supplement records must link
actual questions and targets. Their order or repetition confers no credibility.

When decision_reference is present, it contains the public goal and the actor's
actual proposed option, NOT an answer key. Its only role is to identify the
decision being discussed. Do not derive this reference from gold or choose a
favored existing chain. For a new chain you may record proposal_relation as
{"target_option":"exact referenced option","stance":"supports|refutes|alternative|not_addressed",
"reason":"brief relationship"}. A different option is not automatically a
refutation: exclusivity and scope must justify that relation. If the reference
is absent, omit proposal_relation. Never reduce every C to that reference.
"""

GENERATOR = """Make an initial set of concise O-B-C arguments for the public task
and, if supplied, the actual proposed decision. Include its conditional argument
and at most two materially different, publicly motivated alternatives. Do not
invent certainty or opposition. Give a concrete claim under each reading.
Return JSON only:
{"rules":[{"id":"r1","text":"explicit conditional bridge",
"component":"visual/task relation","conditions":"scope and assumptions"}],
"chains":[{"observations":[],"task_evidence":[],"rule_id":"r1",
"claim_kind":"supports_action|challenges_support|underdetermined",
"option_label":"exact supported public option, otherwise null",
"claim":"specific conditional conclusion or a precise missing-premise record"}]}.
When decision_reference exists, a chain may additionally include the optional
proposal_relation object defined below; otherwise omit that field entirely.
For challenges_support, state whether you actually derive a negative conclusion
or only identify lack of support; those are not equivalent. No numeric chain
quota must be filled. Only used rules may be returned.
""" + COMMON

QUESTIONS = """Inspect the complete initial explanation set and chart for meaningful
omissions. Ask at most three questions about observations, rule conditions or
coverage. An unrepresented conditional reading may need a question even while
its eventual applicability remains unverified; do not demand prior proof of a
winner just to articulate a candidate. Conversely, do not repeat readings that
the set already contains. No question, contradiction or new chain is mandatory.
Return JSON only:
{"questions":[{"id":"q1","target_chain_ids":["existing chain ID"],
"focus":"observations|rule_conditions|coverage","question":"checkable gap"}],
"summary":"what was inspected and remaining limits, not completeness proof"}.
Use unique q1/q2/q3 IDs and real target IDs. Questions are not factual verdicts.
""" + COMMON

SUPPLEMENT = """Answer the actual questions using the full initial set, public task
and chart. Check each question's premises. Keep initial records unchanged.
Add at most two new chains/rules and two refinements; do not fill these quotas.
A refinement adds evidence or clarifies an existing condition. A materially
different interpretation that derives a distinct conclusion is a new chain,
not merely an unresolved condition note. Its O and the motivation to consider
the reading must come from visible/public information. B can be an explicit
untested interpretation hypothesis; do not demand proven applicability before
expressing its conditional conclusion. Final applicability is checked later.
Return JSON only:
{"new_rules":[{"id":"supp_r1","text":"conditional bridge",
"component":"visual/task relation","conditions":"scope and assumptions"}],
"new_chains":[{"chain_id":"supp_c1","rule_id":"real rule ID",
"observations":[],"task_evidence":[],
"claim_kind":"supports_action|challenges_support|underdetermined",
"option_label":"exact supported option, otherwise null",
"claim":"specific conclusion under this reading, or a precise genuine gap",
"question_ids":["q1"],"relationship":"compatible|competing|support_gap"}],
"refinements":[{"id":"refine_1","target_chain_id":"initial chain ID",
"question_ids":["q1"],"added_observations":[],"added_task_evidence":[],
"condition_note":"condition clarification or empty for evidence-only addition",
"reason":"specific addition"}],
"question_responses":[{"question_id":"q1",
"outcome":"new_explanation|refined_existing|already_covered|unresolved",
"record_ids":[],"covered_chain_ids":[],"reason":"specific account"}]}.
When decision_reference exists, a new chain may additionally include the
optional proposal_relation object defined below; otherwise omit that field.
Use supp_r1/supp_r2, supp_c1/supp_c2, refine_1/refine_2 without ID collisions.
Each new rule must be used; each added record must link actual questions.
Each question has exactly one response with complete bidirectional record links.
Use new_explanation if it has a new chain (even with refinements); otherwise
refined_existing if it has refinements. already_covered has no new records and
must cite relevant initial chains; unresolved has no new records. With zero
questions all four arrays are empty. Non-action chains have option_label=null;
a negative claim must name the rejected action/entity explicitly in claim.
""" + COMMON

VERIFY = """Verify all supplied candidate chains WITHOUT changing their claims.
Do not choose a winner. Separate two questions that the old protocol conflated:
(1) what follows IF this chain's stated interpretation assumptions are adopted;
(2) whether those assumptions are supported by the actual chart/public task.

For each chain return three INDEPENDENT checks:
- O: are its literal observations and public bindings supported by the image
  and task? Do not endorse decoded rankings as if they were literal marks.
- B_applicability: does the current chart/public task actually support the
  rule's decoding and required scope/conditions? A sensible conditional rule
  is NOT enough for supported. If its antecedent remains unestablished, say
  undetermined here; if current evidence contradicts it, say refuted here.
- conditional_inference: taking the stated O and the stated reading assumptions
  in B/conditions as premises, does the SPECIFIC C follow? valid means it does;
  invalid means the proposed inference has an identifiable logical/comparison/
  scope error; incomplete means a necessary premise was never stated precisely
  enough to test the inference. List such missing premises. Lack of proof that
  an explicitly stated assumption is true belongs to B_applicability, NOT to
  missing_premises. A rival interpretation or a refuted observation does not
  itself invalidate the conditional derivation. Do not use contradictory
  premises to 'prove' an arbitrary C. Invalid/incomplete does not mean not-C.

Reference the actual chain and rule in premise_ids, e.g. chain:base_c1, rule:r1.
These identify assumed premises for logic checking; they are NOT independent
visual evidence. External evidence belongs to O and B_applicability. No rival
chain ID belongs in the current chain's premise_ids. Do not import a missing
comparison from another chain or assume a convenient unstated policy.

Refinements have no standalone C: return a separate support judgment for each
note and its actual added observations/conditions. Supporting a warning or
condition note does not activate, negate or silently rewrite its target rule.

Return JSON only:
{"schema_version":"explanation_verification_v2",
"chain_checks":[{"target_id":"actual chain ID",
"O":{"status":"supported|refuted|undetermined","evidence":[],"reason":"basis"},
"B_applicability":{"status":"supported|refuted|undetermined","evidence":[],"reason":"basis"},
"conditional_inference":{"status":"valid|invalid|incomplete",
"premise_ids":["chain:actual_id","rule:actual_id"],
"missing_premises":[],"reason":"short inference check, not final action choice"}}],
"refinement_checks":[{"target_id":"actual refinement ID",
"support":{"status":"supported|refuted|undetermined","evidence":[],"reason":"basis"}}],
"summary":"separate conditional conclusions from current evidence applicability"}.
Cover every chain/refinement exactly once. For supported/refuted O,
B_applicability and refinement support, give actual chart/public citations.
For valid/invalid inference, cite both linked premise IDs and leave
missing_premises empty. For incomplete, name nonempty precise missing premises.
Never revise C to 'unknown' merely to express an applicability concern.
This verification is fallible; it grants no action or submission permission.
""" + COMMON

PROMPTS = {"questions": QUESTIONS, "supplement": SUPPLEMENT, "verification": VERIFY}
