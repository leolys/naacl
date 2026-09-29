"""Interface-only correction: public evidence preserves the exact JSON scalar type.

No task-specific cues, answer changes, content repairs, or changed decision gates.
Frozen v1 prompts and validator remain untouched.
"""
import prompts as v1

completion = v1.completion
OLD = '''{"ref":"public_task","path":"exact JSON Pointer from public_task_leaf_paths",
"content":"exact source text at that path"}. Never put public task text into'''
NEW = '''{"ref":"public_task","path":"exact JSON Pointer from public_task_leaf_paths",
"content":<exact JSON scalar value at that path>}. Preserve the JSON type and
value exactly: strings remain quoted strings, booleans are unquoted true/false,
numbers remain numbers, and null is unquoted null. For example, "Europe", true,
3, and null are four different scalar types. Do not stringify or paraphrase
the supplied value, and do not invent an absent citation. Never put public task text into'''


def typed_contract(text):
    if text.count(OLD) != 1:
        raise ValueError('expected_one_original_public_evidence_contract')
    return text.replace(OLD, NEW)


ACTOR = v1.ACTOR
GENERATE = typed_contract(v1.GENERATE)
QUESTIONS = typed_contract(v1.QUESTIONS)
SUPPLEMENT = typed_contract(v1.SUPPLEMENT)
VERIFY = typed_contract(v1.VERIFY)
PROMPTS = {'actor': ACTOR, 'generation': GENERATE, 'questions': QUESTIONS,
           'supplement': SUPPLEMENT, 'verification': VERIFY}
