# Experiment code review — 2026-09-23

**Review type:** fresh same-family Codex predeployment review; provisional, not cross-model-independent.

**Scope reviewed:** `METHOD_SOURCE.md`, `refine-logs/EXPERIMENT_PLAN.md`, `engine.py`, `run_demo.py`, `adapter.py`, `configs/demo.json`, `tests_engine.py`, `tests_adapter.py`, and the already prepared six-case data manifest. No model API was called, no GPU/full-140 run was performed, and no experiment code was modified by this review.

## Verdict

### BLOCKING

None found for the fixed development run of pub013, health004, and b046 × official140/clean140 × ordinary/competing_persistent = 12 trajectories.

The current implementation is suitable to proceed to the bounded development API run, provided it is launched with the project-local `.venv` interpreter noted below. This verdict does not establish the paper's empirical claims and does not authorize the full 140-pair evaluation.

### NONBLOCKING

1. **Defense-applied selections are mislabelled in the low-level browser history.** `run_demo.py` applies a verifier recommendation through `browser.execute(...)`, while `BrowserTask.execute()` records every such call with the default source `"actor"`. The higher-level `verification_events`, `selection_execution`, and `handoff` artifacts preserve the true provenance, so outcome scoring and the actor-only-submit property remain correct. Minimal later cleanup: let `execute` accept a source label and pass `defense_recommendation` for this one call.

2. **Use the project interpreter.** `D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe` has the required Playwright/browser stack. The workspace-default `D:\anaconda\python.exe` does not have Playwright. With the wrong interpreter, `run_demo.py` fails closed while recording package versions, before `API(...)` is constructed, so this is an operational launch requirement rather than a leakage or result-validity bug.

3. **The persistent-state evidence is interface-level only in this three-case run.** The offline report correctly fixes `genuine_later_semantic_judgment_count` to 0 and labels the persistence effect `not_applicable_native_single_decision`. Do not use these trajectories as evidence that persistence improves later judgments.

4. **Finite prototype limitations remain declared and acceptable here.** Semantic rule equivalence is primarily requested from the model; programmatic normalization is exact structured-text deduplication. Scope matching is bounded to chart reference plus public metric, with component/conditions retained in the record rather than fully proved. The plan already states these limitations, so the development report must not describe this as full semantic normalization or general dynamic-scope validation.

## Checks passed

- **Fixed scope and actual paths:** the manifest contains exactly case01–case06 for pub013, health004, and b046 in official140/clean140 pairs. Every prepared chart hash matches both its manifest entry and the existing source file. The test source expression resolves correctly to `D:\ths_Viswork\.aris\dataset_inventory_20260918\raw`. Within each of the three paired tasks, public goals and visible option labels match across arms, and the original gold option label is unchanged. The only expected public-object difference is the neutral case alias.
- **Leakage isolation:** the acting model receives only the allowlisted public task projection, browser state/history, chart, page screenshot, and—only in the method arm—rule-state/handoff records. Hidden action IDs, expected IDs, misleading IDs, hidden companion defaults, raw rows, and scoring data are absent from HTML and model context. Offline raw data is first consulted by `offline_evaluate` after all actors stop.
- **Ground-truth scoring:** primary outcome is joined from the submitted visible label to the original raw action entry and compared with the original `expected_action_id`/`misleading_action_ids`. It is not scored against a model recommendation or verifier label. Reconstructed companion exact matches remain explicitly diagnostic and are not called the official full end-to-end score.
- **Gold-blind first trigger:** the full method triggers on the first actor-proposed `select` before that selection executes. The first proposal is recorded at that point. Triggering does not consult correctness or hidden scoring. The verifier receives normalized candidates rather than the actor proposal/source role, and a recommendation is executable only when a fully supported candidate chain exists. Conflicting fully supported options or conflicting B-status for a shared rule fail closed to unresolved.
- **Candidate/verifier alignment:** candidate chains must use visible options and chart-provenanced observations; duplicate chains do not become votes; unreferenced generated rules are excluded; all chains require exactly one verifier check; and the candidate set must include an argument for the proposed/current selection.
- **Rule-state fidelity and dependency guard:** state stores B rather than chosen actions, plus chart/component/metric/conditions scope, status, evidence, version, and transition reasons. Supported/refuted/undetermined B maps to active/revoked/pending, conflicting B checks map to disputed, and history is retained. Explicit use of any non-active rule blocks execution and returns dependency feedback to the actor; re-verification requires an explicit challenge plus new visible evidence and is bounded by the configured extra-verification budget. As declared in the plan, latent dependencies the actor fails to cite cannot be guaranteed detectable.
- **Actor-only submission:** verifier recommendations can apply a selection but never submit. The same ordinary actor must make a later `submit` proposal; server-required visible fields and confirmation are checked, and a non-submission is not scored as a real submission.
- **Paired-arm isolation:** each trajectory creates a fresh `RuleStore`, Flask app, browser/server session, history, and output directory. The API client is stateless between calls; no conversation history crosses trajectories. Ordinary and full arms use the same public bundle, option ordering, chart dimensions/assets, actor prompt, and browser executor.
- **Retries/routes/cost accounting:** every HTTP attempt is charged before transmission, including retries. Retries are bounded and limited to transport failures plus 408/429/5xx; parse/schema/content failures do not trigger answer-based reruns. Per-attempt response model, response ID, usage, status/error, retryability, and elapsed time are retained, while the global budget retains every request attempt and high-level browser operation, including failed actions. No monetary estimate is claimed.
- **Syntax/runtime:** all five Python files compile. With the project `.venv` and the configured Edge executable, the full test suite passes **17/17**, including real browser selection, required-field rejection, fill, server receipt, confirmation, and operation charging. The Edge executable path exists. The Flask/ItsDangerous deprecation warnings are nonblocking for this frozen development run.

## Claim boundary

This review supports only engineering readiness of the fixed 12-trajectory development prototype. Three previously exposed development tasks cannot establish general superiority, correction rate, or persistence benefit. The review is from the same model family and must not be represented as independent cross-model validation.

## Addendum — 2026-09-23

The nonblocking low-level provenance issue above was fixed before the API launch. In both the live source and the copies archived under `runs/api_demo_20260923_v1/runtime_source`, `BrowserTask.execute` accepts a `source` argument and forwards it to `_record`, while verifier-applied selections call it with `source="verification_application"`. Ordinary actor calls retain the default `source="actor"`. The launched runtime therefore preserves the correct selection provenance.

No browser or API test was rerun for this addendum; it is an exact source-line confirmation. The review's already completed browser case charged 7 high-level operations—three setup navigations, selection, blocked submit, field fill, and successful submit—bringing the recorded engineering-check total to 21 operations.
