"""Generic v3 prompts: generate concrete candidates, then independently verify."""

COMMON = """
Use only the supplied complete chart, public task, actual public history, and
candidate records. Return concise, checkable argument records, not private
reasoning transcripts. A candidate, actor proposal, or earlier explanation is
not external evidence. Neither printed labels nor customary geometry has
automatic precedence. Do not use hidden answers, raw data, another chart arm,
or previous verifier verdicts.
Reading hypotheses must be motivated by visible or public cues. Do not invent
visible entities, values, public task facts, business policies, time requirements
or uniqueness requirements to complete a chain. B must supply a conditional
bridge, not merely assume the desired C in different words. These boundaries
do not require prior confirmation that a proposed interpretation applies.

O contains only localized visible marks, literal inscriptions and screen-space
relationships: colors, positions, lengths, attachments, ticks, words and printed
numbers. Put decoding, semantic mappings and reading assumptions in B and its
conditions. B states the conditional bridge from these observations to the
task-relevant C, with the reading assumptions this candidate adopts explicitly
named. Those assumptions do not need prior confirmation to be proposed.

C (claim) is a concrete, testable task candidate: a named entity, comparison,
direction, scoped conclusion, or supported/rejected action. It may later prove
wrong. Write its content directly in natural language. Do not force every C
into a binary label for one universal proposition. There is no claim_kind field.
Set option_label to an exact public option only when the candidate explicitly
supports it; otherwise use null. A concrete negative or comparative C may have
option_label=null. Null does not mean unknown and is not a claim classifier.

Chart references: {"ref":"chart_1","location":"visible location",
"content":"literal observation"}. Public task references are separate:
{"ref":"public_task","path":"exact JSON Pointer from public_task_leaf_paths",
"content":"exact public value"}. Never place public text in image observations.
Keep existing rule/chain IDs and original text unchanged. Supplement records
must link actual questions and targets. Order and repetition confer no weight.

When decision_reference is present, it contains the public goal and the actor's
actual proposed option, not an answer key. It identifies the decision being
discussed and must not become a universal target proposition for all claims.
A chain may then include proposal_relation as
{"target_option":"exact referenced option","stance":"supports|refutes|alternative|not_addressed",
"reason":"brief relationship"}. If the reference is absent, omit that field.
"""

GENERATOR = """Generate an initial set of explicit O-B-C task candidates. Examine
the chart and public task and express the plausible readings they motivate.
Include at most three distinct candidates, without filling a quota. One or two
candidates may suffice. Different candidates may agree or compete. A candidate
can adopt an unverified B/conditions hypothesis; state that hypothesis and its
concrete C. Candidate generation is separate from later verification.

Each chain must end in a concrete task-relevant conclusion. A missing mapping,
unclear comparison, lack of support, inability to decide, or 'underdetermined'
is not C. Put any such remaining generation question outside the chains in
unresolved_questions with a specific question and reason. When no complete
candidate can be formulated, return rules=[] and chains=[] with at least one
real unresolved question; do not invent a placeholder chain. Unresolved notes
can also accompany a nonempty candidate set. Use gap1, gap2, ... as their IDs.
Do not add a free-standing unused rule.

Return JSON only:
{"rules":[{"id":"r1","text":"explicit conditional bridge",
"component":"visual/task relation","conditions":"scope and adopted assumptions"}],
"chains":[{"observations":[],"task_evidence":[],"rule_id":"r1",
"option_label":null,"claim":"concrete task candidate under the stated reading"}],
"unresolved_questions":[{"id":"gap1","question":"specific unresolved question",
"reason":"what prevents formulating the corresponding complete candidate"}]}.
Use unresolved_questions=[] when no such generation question remains.
""" + COMMON

QUESTIONS = """Inspect the whole initial candidate set and the chart for useful
questions about omitted observations, rule conditions, or coverage. Ask at most
three questions; zero is allowed. Preserve all initial candidates. A publicly
motivated but unrepresented reading may deserve a question even before its B
is verified. A question can lead to more evidence, a clarified condition, a new
candidate, or no addition. Agreement between candidates is allowed; do not
manufacture conflict or require a new chain just to increase the count.
Unresolved generation questions are separate records, not candidate chains.

Return JSON only:
{"questions":[{"id":"q1","target_chain_ids":["existing initial chain ID"],
"focus":"observations|rule_conditions|coverage","question":"checkable question"}],
"summary":"what was inspected and remaining limits, not completeness proof"}.
Use unique q1/q2/q3 IDs and real initial target IDs. Questions are not verdicts.
""" + COMMON

SUPPLEMENT = """Respond to the actual questions using the entire initial set,
public task and chart. Preserve every initial record verbatim. Add at most two
new chains/rules and two refinements; these are limits, not quotas. A refinement
adds evidence or clarifies an existing condition. A new candidate supplies a
materially different O-B-C basis, and its C may agree with an existing C. B can
be a clearly stated, untested reading hypothesis motivated by public evidence;
prior proof of applicability is not required to articulate its concrete C.
Every new chain must have a concrete task candidate as C. Remaining inability
to formulate a candidate is recorded through an unresolved question response,
never a gap chain. Keep the generation unresolved_questions unchanged.

Return JSON only:
{"new_rules":[{"id":"supp_r1","text":"conditional bridge",
"component":"visual/task relation","conditions":"scope and adopted assumptions"}],
"new_chains":[{"chain_id":"supp_c1","rule_id":"real rule ID",
"observations":[],"task_evidence":[],"option_label":null,
"claim":"concrete task candidate under this reading","question_ids":["q1"],
"relationship":"compatible|competing"}],
"refinements":[{"id":"refine_1","target_chain_id":"initial chain ID",
"question_ids":["q1"],"added_observations":[],"added_task_evidence":[],
"condition_note":"clarified condition or empty for evidence-only addition",
"reason":"specific addition"}],
"question_responses":[{"question_id":"q1",
"outcome":"new_explanation|refined_existing|already_covered|unresolved",
"record_ids":[],"covered_chain_ids":[],"reason":"specific account"}]}.
Use supp_r1/supp_r2, supp_c1/supp_c2, refine_1/refine_2 without ID collisions.
New chains may use a real initial rule. Every new rule must be used. Each added
chain/refinement must link actual questions, with complete bidirectional links
in the responses. Every question has exactly one response. Use new_explanation
if it has a new chain, even with refinements; otherwise refined_existing if it
has refinements. already_covered adds nothing and cites relevant initial chains;
unresolved adds nothing and explains what remains open. With zero questions,
all four arrays are empty. There is no support_gap relationship or claim_kind.
""" + COMMON

VERIFY = """Verify every supplied candidate independently without changing C or
choosing a winner. Candidate generation may have produced an incorrect claim.
Assess that claim as recorded, preserving disagreements and uncertainty.

For each chain return three INDEPENDENT checks:
- O: are its literal observations and public bindings supported by the image
  and task? Decoded ranks, trends and unprinted calculations are not literal O.
  Printed numbers are inscriptions, not independently established data facts.
- B_applicability: does this chart/public task support the rule's decoding and
  required conditions? If an explicit reading assumption is unestablished, use
  undetermined; if contradicted, use refuted. A sensible conditional alone does
  not justify supported. Do not invent policy, time or uniqueness conditions.
- conditional_inference: assuming this chain's stated O and explicit B/conditions,
  does its specific C follow? valid means yes; invalid identifies a logical,
  comparison or scope error; incomplete identifies a necessary premise never
  stated precisely enough to test the inference. List such missing premises.
  Lack of proof that an explicitly stated assumption is true belongs to
  B_applicability, not missing_premises. A rival reading or refuted observation
  does not itself invalidate a conditional derivation. Contradictory premises
  must not be used to prove arbitrary C. Invalid/incomplete does not imply not-C.

Check scope carefully: failing to derive a claim is not deriving its negation;
one counterexample to an item being largest does not identify a replacement
global maximum. Do not import comparisons from other chains or silently add
unstated policy. Different option labels do not automatically imply refutation;
that requires the relevant exclusivity and scope. If C merely records a gap
instead of a concrete task candidate, report the defect in the inference check;
never repair, discard or replace the original claim text.

premise_ids cite only the actual chain and its linked rule, e.g.
chain:base_c1 and rule:r1. They identify assumed premises, not external evidence.
Chart/public evidence belongs to O and B_applicability. Refinements have no
standalone C: check the support for their actual added evidence/conditions
separately. A supported condition note does not silently rewrite a target rule.
Generation unresolved_questions stay outside chain_checks; they are not claims.

Return JSON only:
{"schema_version":"explanation_verification_v3",
"chain_checks":[{"target_id":"actual chain ID",
"O":{"status":"supported|refuted|undetermined","evidence":[],"reason":"basis"},
"B_applicability":{"status":"supported|refuted|undetermined","evidence":[],"reason":"basis"},
"conditional_inference":{"status":"valid|invalid|incomplete",
"premise_ids":["chain:actual_id","rule:actual_id"],"missing_premises":[],
"reason":"inference check, not final action choice"}}],
"refinement_checks":[{"target_id":"actual refinement ID",
"support":{"status":"supported|refuted|undetermined","evidence":[],"reason":"basis"}}],
"summary":"conditional inference and current applicability assessed separately"}.
Cover every chain/refinement exactly once. Definite supported/refuted O,
B_applicability and refinement judgments need actual chart/public citations.
For valid/invalid inference cite both linked premise IDs and leave missing_premises
empty. For incomplete give nonempty precise missing_premises. Never rewrite C
as unknown to express uncertainty. Verification is fallible and authorizes no
action or submission.
""" + COMMON

PROMPTS = {"generation": GENERATOR, "questions": QUESTIONS,
           "supplement": SUPPLEMENT, "verification": VERIFY}
