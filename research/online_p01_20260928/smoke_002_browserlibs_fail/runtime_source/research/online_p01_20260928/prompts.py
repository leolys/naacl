from deps import completion

ACTOR = '''Operate the currently visible original web task. Follow its ordinary
navigation to review the dashboard and open the workflow form. Use only actual
public pages/images and real execution history. Return ONE action, never an
invented execution receipt. If the desired choice is already selected and the
required public fields are complete, submit; do not select a different option
merely because one is already selected. Optional fields need not be filled.
An initial choice is a proposal, not proof that it is correct.

Actions: {"kind":"open_link","label":"exact visible link text"},
{"kind":"select","option":"exact primary option"},
{"kind":"fill","field":"visible field ID","value":"text"},
{"kind":"check","field":"visible checkbox ID","value":true},
{"kind":"select_field","field":"visible field ID","option":"visible option"},
{"kind":"submit"}, or {"kind":"unresolved"}.

If interpretation_rules and verified_arguments are supplied, read their actual
status, evidence and scope. They are fallible checked records, not hidden answers.
For a chart-based selection or submission, cite a chain whose O, B and implication
are supported, with an active rule whose conditions you judge applicable to this
unchanged chart/task. State that scope check explicitly. B alone does not prove a
choice. Do not cite a revoked, disputed, stale-version or unknown-scope rule as
active. You may challenge a prior check with actual new chart/task evidence:
return kind unresolved and a challenge; no replacement is automatically executed.
If support remains insufficient, return unresolved, not an invented opposite.

JSON only:
{"action":{"kind":"..."},"chart_dependent":false,
"brief_basis":"concise checkable evidence and task basis",
"used_rules":[{"rule_id":"actual ID","version":1,"conditions_match":true,
"basis":"why the current public context satisfies this rule's conditions"}],
"supporting_chain_ids":[],"challenge":null}.
Use empty lists when no verified state is supplied. For a challenge use
{"evidence":[{"ref":"chart_1","location":"area","content":"literal fact"}],
"reason":"how it challenges a specific previous finding"}.
These are concise argument records, not a long private reasoning transcript.
'''

GENERATE = '''Generate the initial explanation SET for the supplied unexecuted
chart-related proposal, complete original chart, public task, and real history.
No business choice has been executed by this request. Do not assume the proposed
choice is correct. Include its support or support gap and other substantively
different visibly motivated readings that you already notice. At most 3 chains;
there is no minimum number of alternatives. Distinct grounds may support the
same option. Preserve raw O versus conditional B versus derived C.

JSON only:
{"rules":[{"id":"r1","text":"self-contained conditional bridge",
"component":"encoding/task relation","conditions":"scope/assumptions"}],
"chains":[{"chain_id":"base_c1","rule_id":"r1",
"observations":[{"ref":"chart_1","location":"visible area","content":"raw fact"}],
"task_evidence":[],"claim_kind":"supports_action|challenges_support|underdetermined",
"option_label":"exact public option for supports_action, otherwise null",
"claim":"conditional conclusion or support gap"}]}.
Use unique stable r1/r2/r3 and base_c1/base_c2/base_c3 IDs; every rule must be used.
''' + completion.COMMON

QUESTIONS = completion.QUESTIONS.replace('public task in this request', 'public task in this request')
SUPPLEMENT = completion.SUPPLEMENT
VERIFY = completion.VERIFY
PROMPTS = {'actor': ACTOR, 'generation': GENERATE, 'questions': QUESTIONS,
           'supplement': SUPPLEMENT, 'verification': VERIFY}
