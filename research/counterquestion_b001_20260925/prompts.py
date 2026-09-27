"""Task-agnostic, explicit question -> candidate dependency; no preferred answers."""
from prompts_observation_v4 import OBSERVATION_CONTRACT, VERIFIER

QUESTIONER = """Inspect the supplied current argument against the same full chart and public task.
Produce three concise, checkable counterquestions, one for each kind below.
These are critical questions about evidential sufficiency and interpretation,
not requests to assume that the chart or the current choice is wrong.
Do not invent an opposite answer or treat any evidence channel as automatically true.
Address these linked questions:
1. evidence_sufficiency: Are the reported observations sufficient for the claim?
2. rule_assumptions: Which interpretation clauses and scope assumptions does the
   claim require, and what visible/public evidence tests those assumptions?
3. alternative_explanation: Can another materially different, evidence-grounded
   interpretation of this same chart defeat the claim or support the same action
   for different reasons? Identify what would distinguish these interpretations.
Return JSON only:
{"questions":[{"id":"q1","kind":"evidence_sufficiency",
"target_chain_ids":["c1"],"target_rule_ids":["r1"],
"question":"task-specific critical question",
"brief_assessment":"short evidence-based assessment, not a long reasoning transcript",
"chart_evidence":[{"ref":"chart_1","location":"visible area","content":"raw visible fact"}],
"candidate_bridge":"conditional alternative worth testing, or null",
"discriminating_check":"what visible facts would discriminate the interpretations",
"uncertainty":"remaining limitations, or empty string"}],
"questioning_summary":"brief summary"}.
Return exactly three records, q1/q2/q3, in the kind order given above.
Use the actual supplied chain/rule IDs. chart_evidence may be empty if none can
be localized; acknowledge that limit. Questions and assessments are not verified
facts. A conditional alternative can be explored before it is accepted.
""" + OBSERVATION_CONTRACT

COMPETITOR = """Use the actual supplied counterquestions to construct new competing arguments
alongside the unchanged supplied base argument, using the same full chart and
public task. Address every question explicitly. Do not restate the base chain
as a new chain. A new chain must differ in observation binding, interpretation
bridge, scope or inferential sufficiency; it need not choose another action.
Generate at most two new chains. Do not force a second chain or an opposite answer.
An alternative bridge may be a visibly motivated conditional hypothesis awaiting
verification, not an established fact. If no substantiated alternative can be
constructed, return empty new_rules/new_chains and record why for each question.
Return JSON only:
{"new_rules":[{"id":"new_r1","text":"conditional interpretation, not an option",
"component":"encoding/task relation","conditions":"scope and assumptions"}],
"new_chains":[{"candidate_id":"n1","question_ids":["q1","q3"],
"observations":[{"ref":"chart_1","location":"visible area","content":"raw visible fact"}],
"rule_id":"new_r1","option_label":"exact public option",
"claim":"conditional derived interpretation and task implication",
"difference_from_base":"which bridge/binding/scope differs, not just different wording"}],
"question_responses":[{"question_id":"q1","resolution":"candidate_generated|no_supported_alternative",
"candidate_ids":["n1"],"reason":"concise evidence-based response"}]}.
Each new chain must link at least one actual question. Each question needs one
response; candidate_ids must agree with those links. Use new rule IDs, not base
rule IDs. Do not edit the inherited argument or claim the questioner is authority.
""" + OBSERVATION_CONTRACT

VERIFICATION = VERIFIER + """
Citation format clarification: chart facts use ref='chart_1', a localized natural
language location, and a literal visible fact as content. Public task quotations
may use ref='public_task' with location equal to ONE exact leaf field path from
public_task_text_paths (for example user_goal or option_labels.0). A descriptive
table name is not a field path. Do not use a rule or candidate as an evidence ref.
Every chain still needs at least one actual chart evidence citation. The path
index contains only public input field names, not new evidence or answer labels.
"""
