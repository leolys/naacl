"""Set completion, not mandatory opposition; shared prompts for every case."""
from prompts_observation_v4 import OBSERVATION_CONTRACT

COMMON = """
Use only the complete chart and public task in this request. These are concise
checkable argument records, not a private reasoning transcript. The supplied
initial explanations are candidates, not verified facts. Neither printed text
nor customary geometry is automatically authoritative. A conditional reading
may await checking: state its visible/public motivation and open conditions,
rather than pretending its correctness has already been established.

Keep every existing explanation available. The aim is to fill meaningful gaps
in this SET, not to discover a conflict, reverse a choice, or maximize chain
count. An already represented interpretation need not be generated again.
Compatible and same-action explanations can be useful. Missing support can be
recorded without asserting an alternative action. Do not invent a missing
policy threshold or require uniqueness/time metadata absent from the task.

Use chart evidence as {"ref":"chart_1","location":"localized visible area",
"content":"literal visual observation"}. Public task evidence is separate:
{"ref":"public_task","path":"exact JSON Pointer from public_task_leaf_paths",
"content":"exact source text at that path"}. Never put public task text into
image observations, or cite an explanation as external evidence. Do not use
hidden data, another image condition, remembered answers or old verdicts.
Keep supplied rule IDs stable. Link dependencies in ID fields; make rule text
and claims self-contained, without references such as 'r1 says ...'.
""" + OBSERVATION_CONTRACT

QUESTIONS = """Review the ENTIRE supplied initial explanation set for omissions.
Return at most three short questions about unresolved evidence, conditions or
interpretation coverage. Inspect the image; do not merely trust an initial O.
Consider what already supports the task as well as what could weaken support.
A question may concern one chain or several chains. Do not require a third
alternative if two existing explanations already cover the relevant readings.
Do not require a question of each kind or any new conflict. Zero questions is
allowed; describe what you checked and your limits, not that all possible
interpretations have been exhaustively enumerated.

Return JSON only:
{"questions":[{"id":"q1","target_chain_ids":["actual existing chain ID"],
"focus":"observations|rule_conditions|coverage",
"question":"specific checkable omission or completeness question"}],
"summary":"bounded description of inspected coverage and remaining limits"}.
Use unique q1/q2/q3 IDs for the actual questions. Do not give answers as facts.
""" + COMMON

SUPPLEMENT = """Respond to the actual questions using the whole initial explanation
set and full chart. Supplement only where meaningful. Do not overwrite the base
records. Independently check the questions' premises against the chart/task.
No newly generated chain is required. Do not duplicate a chain merely to count
it as new. A candidate's truth is decided by later verification, not by being
new, longer, or in agreement with a preferred answer.

You can add up to two explanations, add up to two refinements to existing
chains, say an issue is already covered by specified existing chains, or leave
an issue unresolved. These are alternatives, not four mandatory output slots.
A refinement supplies observations/task evidence or makes a needed condition
explicit. It is a separate candidate note, not a silent edit of an old rule.
If a materially different rule or conclusion is needed, add an explanation.
An addition can be compatible, competing, or a support gap. A discriminating
test is relevant for competing readings but is NOT a required field for all
additions. No need to invent an opposing mapping for a compatible refinement.

Return JSON only:
{"new_rules":[{"id":"supp_r1","text":"self-contained conditional bridge",
"component":"encoding/task relation","conditions":"actual scope/assumptions"}],
"new_chains":[{"chain_id":"supp_c1","rule_id":"actual existing or new rule ID",
"observations":[{"ref":"chart_1","location":"visible area","content":"raw fact"}],
"task_evidence":[],"claim_kind":"supports_action|challenges_support|underdetermined",
"option_label":"exact public option for supports_action, otherwise null",
"claim":"conditional task implication or support gap","question_ids":["q1"],
"relationship":"compatible|competing|support_gap"}],
"refinements":[{"id":"refine_1","target_chain_id":"actual initial chain ID",
"question_ids":["q1"],"added_observations":[],"added_task_evidence":[],
"condition_note":"specific condition clarification, or empty if just evidence",
"reason":"why this adds something not already represented"}],
"question_responses":[{"question_id":"q1",
"outcome":"new_explanation|refined_existing|already_covered|unresolved",
"record_ids":["actual supp_c1 or refine_1"],
"covered_chain_ids":["existing chain that already addresses this issue"],
"reason":"specific explanation, with limits"}]}.

Return exactly one response for each actual question. All added records link
actual question IDs, and record_ids must match those links in both directions.
If a question has both new and refined records, use new_explanation. Otherwise
use refined_existing when it has refinement records. For already_covered,
record_ids is empty and covered_chain_ids must cite relevant initial chains.
For unresolved, record_ids is empty and explain the evidence gap. An empty
questions list yields empty additions and responses. Every new rule must be
used by a new chain. New IDs are supp_r1/supp_r2, supp_c1/supp_c2, refine_1/refine_2;
never renumber or reuse old IDs. Do not refer to rule IDs inside free text.
""" + COMMON

VERIFY = """Check all supplied explanations and refinement notes against the FULL
chart and public task. Origin, order and repetition confer no authority. The
task is not to pick a winner or prove correction. Multiple compatible readings
can stand; unresolved readings can remain unresolved. No business action is
being executed. For each chain, check O (literal observations/bindings), B
(the referenced rule in scope), and implication (whether they suffice for C).
An incorrect observation need not refute its decoding rule. A supported rule
does not certify all observations or a task conclusion. Do not endorse decoded
rankings/trends in O as if they were raw visual facts.

Check each refinement separately, using its target chain for context: O checks
its added observations/task citations; B checks the proposed condition note or
the applicability of its target rule to this added support; implication checks
whether the claimed refinement is warranted and bears on the target conclusion.
When a component has no assertion to test, mark it undetermined with a reason;
do not invent evidence to populate an empty slot. Supporting a condition note
does not silently rewrite or activate a different version of an existing rule.

Return JSON only:
{"checks":[{"target_id":"actual chain_id or refinement id",
"O":{"status":"supported|refuted|undetermined","evidence":[],"reason":"brief basis"},
"B":{"status":"supported|refuted|undetermined","evidence":[],"reason":"brief basis"},
"implication":{"status":"supported|refuted|undetermined","evidence":[],"reason":"brief basis"}}],
"summary":"bounded verification summary and unresolved issues"}.
Exactly one check is required per chain and per refinement. Cite actual chart
or public-task evidence for supported/refuted judgments. Empty evidence is
allowed for undetermined only. A model judgment is still fallible; acknowledge
unreadability, limited precision or missing support. Do not infer the opposite
rule or a winning action merely because one explanation is refuted.
""" + COMMON

PROMPTS = {"questions": QUESTIONS, "supplement": SUPPLEMENT, "verification": VERIFY}
