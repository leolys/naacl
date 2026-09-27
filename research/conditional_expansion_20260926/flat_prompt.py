"""New standalone expansion instruction, not appended to an old prompt."""

EXPAND = '''Express the supplied candidate as an O-B-C hypothesis awaiting verification.
O: located literal marks or spatial relations used by the candidate, not decoded
business rankings. B: its reading rule and necessary assumptions, stated
conditionally in a short paragraph. Keep unverified assumptions as assumptions.
C: the candidate's concrete proposed action; use its exact option_label when
provided. C records the candidate's claim, not your endorsement.
Do not decide whether the reading applies, which evidence source should win,
or whether the inference is sound. Leave existing conflicts for verification;
do not repair them by changing the conclusion or adding a policy or observation.
Return only O, B, C. An empty record (O=[], B="", C="") is permitted only when
the input lacks a concrete conclusion or any locatable cue, not for uncertainty
or disagreement.'''
