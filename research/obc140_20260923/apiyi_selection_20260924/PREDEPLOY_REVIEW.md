# APIYI two-task model-selection predeployment review

**Date:** 2026-09-24  
**Reviewer:** Codex sub-agent; `gpt-5.6-sol` with `xhigh` was requested, backend-reported identity unavailable  
**Assurance:** same-family provisional; executor identity unavailable; independence unverified  
**Scope:** New APIYI wrapper/configuration for the frozen `b001`/`pub013` × Sol/Terra/5.4-mini pilot only. No API call, credential read, browser action, GPU/remote action, 140-task batch, or production-code edit was performed by this review.

## Gate

- **First operation — Sol / b001 proposal: PASS.** Use only `D:\anaconda\python.exe run_selection.py --model gpt-5.6-sol --task b001 --stop-after proposal` from this directory. Inspect the saved proposal before any continuation.
- **Overall 24-request small panel: PASS.** No blocking correctness, isolation, budget, or resume defect was found in the reviewed wrapper and reused implementation.
- **140-task execution: NOT AUTHORIZED / NOT REVIEWED.** Stop after the two-task pilot and cost estimate unless the user separately approves more work.

## Primary evidence

1. `PLAN.md` freezes exactly three requested models and two development tasks, orders Sol/`b001` proposal first, caps the design at `2 × 3 × 4 = 24` requests, and explicitly prohibits automatic retry, hidden/gold data, other-arm data, business actions, GPU use, and automatic expansion to 140 tasks.
2. `run_selection.py` accepts only the frozen model/task tuples. Each model writes to its own new `runs/<model>` directory, while the historical endpoint run is referenced only as metadata. The new endpoint is exact, proxy use is disabled, `max_attempts_per_call=1`, and each model has an eight-attempt persistent ceiling; the reused budget charges before sending each request.
3. Every model/case retains its own record. Generation reads that record's proposal, verification reads that record's normalized candidates, and translation reads that record's source records. No Sol proposal or output is copied into Terra or 5.4-mini context. The common inputs are the fixed public task, original chart, prompts, and option order—not another model's answer.
4. The reused runner creates immutable per-run config/catalog/source snapshots, refuses overwrite, requires exact config/base-source identity on resume, and the wrapper separately checks its snapshotted entry point. Completed, invalid, and failed phases are not re-called; an interrupted running phase is validated from an already saved parsed result or marked failed without resend. Provider quota/auth blocks stop and inhibit the other aliases.
5. The request path stores payload/context/response metadata but not the Authorization header. The public-input assertion runs before a call. The wrapper exposes no browser, submission, GPU, or remote-execution path.
6. `test_selection.py` and its saved JUnit record cover the fixed panel/cap, unchanged inherited inference settings, rejection of unlisted model/task values, and the public-chart proposal context. The fresh offline invocation exited successfully; the saved suite record reports **4 passed, 0 failures, 0 errors**.
7. `PRICE_SOURCES.md` / `provider_rates.json` keep pricing outside inference control and distinguish public APIYI list rates from account charges. Any result estimate must use returned usage by model, disclose missing billing categories, and must not be represented as an actual bill.

## Required checkpoint and interpretation limits

The wrapper constrains allowed combinations but does not encode the chronological first-call rule. That is acceptable for this operator-controlled pilot only if the first invocation is the exact bounded command above. After it returns:

- A structural `completed` status means only that the JSON normalized to one exact public option. It does **not** establish that the option, chart observation, or brief basis is semantically correct.
- Before continuing Sol/`b001`, inspect the raw response and validated proposal for visible chart grounding, invented values, uncertainty, exact option identity, finish reason, gateway-reported model, and usage.
- Continue the remaining three Sol/`b001` stages only after that inspection. Then follow the frozen panel serially; do not run combinations concurrently.
- Interpret comparisons as end-to-end outputs conditioned on each model's own proposal and generated chains. They are not a shared-context translation contest, and model agreement is not ground truth.
- Preserve every failure. Do not delete a failed run, force-resume the historical endpoint run, resample, or select tasks/models based on pilot answers.

## Findings

**Blocking:** none.

**Non-blocking:** the first-call chronology is an execution instruction rather than an internal wrapper guard. Because the allowed state space and hard budgets are already bounded, and the executor has the exact first command, no production patch is warranted for this small audited pilot.

## Files reviewed

- `apiyi_selection_20260924/PLAN.md`
- `apiyi_selection_20260924/run_selection.py`
- `apiyi_selection_20260924/test_selection.py`
- `apiyi_selection_20260924/tests_selection.xml`
- `apiyi_selection_20260924/PRICE_SOURCES.md`
- `apiyi_selection_20260924/provider_rates.json`
- Reused `panel_core.py`, `run_panel.py`, and the prior `PREDEPLOY_REVIEW.md`

No production code, configuration, or result was changed by this review. Only this review artifact and its requested trace were added.
