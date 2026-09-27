# Predeployment review: observation boundary v4

Status: **PASS for the fixed, bounded 22-call module diagnostic; no code-level blocker remains.** The reviewed code may proceed with the frozen 20 generator/verifier module calls plus two one-time ordinary proposal calls, subject to the configured 60 request-attempt and 30 browser-operation caps. This is a same-family, static code review. It makes no efficacy claim and did not call an API, launch a browser, use a GPU, or inspect model outcomes.

## Initial blocking findings and resolution

1. **Verifier self-corroboration prohibition — resolved.**

   Initial finding: the earlier wording said that a generated rule could not prove “another rule.” Read literally, it did not forbid treating candidate B as evidence for itself, leaving the requested self-corroboration failure mode ambiguous.

   Resolution: `prompts_observation_v4.py:71-73` now says that a generated rule, earlier verdict, or actor assertion is never evidence for itself or any other rule; B must be checked from chart, page, or public-task evidence, and generated claims cannot be attributed to the page.

2. **Single-rule schema/instruction mismatch — resolved.**

   Initial finding: the earlier generator instruction said “Reference every necessary rule in a chain,” while the declared wire schema and `engine.normalized_candidates` accept exactly one `rule_id`. This could either induce invalid output or omit a necessary bridge on samples such as the fixed dual-axis chart.

   Resolution: `prompts_observation_v4.py:49-51` now requires every necessary bridge clause to be included in the chain's single referenced rule record, matching the declared schema and `engine.normalized_candidates` without a schema change.

## Checks that passed

- O is restricted to localized visible geometry or located literal inscriptions; decoded ranks, trends, interpolations, calculations, business meaning, and actions are excluded from O and retained in B/C.
- Transcribing printed text or numerals is explicitly separated from accepting them as true.
- The prompts contain no fixed task IDs, entities, encoding directions, or preferred answers.
- Legacy configs default to the exact pre-change prompt constants; the new profile is explicit and both initial and additional verification use the selected verifier.
- `run_check.py` derives a per-arm `defense_prompt_profile`, reuses the same public generator context and image bytes within each pair, fixes and alternates the five cases, and allows generated verifier candidates to differ as outputs.
- The runner plans 20 module calls plus two one-time ordinary proposal calls, enforces 60 request attempts and 30 browser operations, never executes a proposal or recommendation, and consults hidden labels only in the offline scoring stage after all module slots.
- Output metadata labels this as a module diagnostic and explicitly marks submission, natural recovery, and end-to-end success as not applicable.

## Final re-review conclusion

Both initial blockers are fixed at the prompt level. The final offline suite records 42 passed tests and one browser-dependent skip in `unit_tests_final.xml`. I see no further code-level blocker to running the frozen 22-call diagnostic exactly as reviewed. Real outputs will still need the protocol's per-item semantic review; structural tests cannot establish O purity or method efficacy.
