# OBC140 predeployment review

**Date:** 2026-09-23  
**Reviewer:** Codex sub-agent, same-family provisional review  
**Scope:** Static, bilingual O/B/C artifact generation for the fixed 140 `official140` tasks. No browser task execution, submission, GPU work, clean-arm expansion, or six-method benchmark.

## Verdict

- **Code and protocol gate: PASS.** No unresolved implementation blocker remains for the bounded first-task proposal probe or for later serial resume of the four-stage 140-task artifact run.
- **Current execution gate: BLOCKED (external).** The real `b001` proposal probe made exactly one authorized request and the service returned `budget_exceeded`. The run stopped globally with 0 completed proposal/generation/verification/translation stages and 139 tasks untouched. Do not start the full batch until the user confirms service restoration.

## Blocking finding resolved before the real probe

The initial implementation retried every `requests.RequestException`, including a post-send read timeout whose service outcome could be unknown. That could silently double-call or resample a task. The final implementation retries only `ConnectTimeout`; `ReadTimeout` and other ambiguous request exceptions become `UnknownRequestOutcome`, are recorded as terminal `failed`, and are not resent even when `service_restored=True`. The runner-level regression test checks one session call and no later resend.

## Evidence reviewed

- The catalog contains exactly 140 unique, fixed-order `official140` task slugs across business47/public39/environment35/health19; no task resampling or clean-arm expansion is present.
- Prepared chart bytes and task rows are tied to the existing audits. The real `b001` request embedded chart bytes whose SHA-256 matched both its prepared manifest and the original-chart provenance.
- Online task data use the strict public projection only. The real request contained only `task`, empty `history`, and static state with an empty current selection. It contained no gold, expected/misleading action IDs, mechanism labels, original CSV, other arm, analyst review, or Authorization material.
- Reviewed readonly public context is preserved. Non-readonly companion `correct_value` fields, including all select companions, are suppressed; select options are not invented.
- The v4 generator and verifier prompts are imported unchanged. Proposal, generation, and verification receive the original chart; translation is a separate text-only call with exact structural keys and no chart or offline metadata.
- No business action or submission path is invoked by this runner. Configuration enforces serial execution, business actions disabled, GPU disabled, and W&B disabled.
- Run creation refuses overwrite; resume binds the config, catalog, and source hashes. Completed/invalid/failed stages are not recalled. A running stage with saved parsed output is validated locally; a running stage without it is marked unknown and not resent. A blocked service stage requires explicit restoration confirmation.
- Quota and authorization responses stop the run globally. The real service response was classified non-retryably as `server_quota_exceeded` on attempt 1.
- The saved real-run source hashes still match the reviewed current sources after the timeout fix.
- The executor reports 28 offline tests passed, plus browser acceptance and a fresh offline HTML review. This review independently inspected the relevant catalog, request, run ledger, isolation, retry, and resume artifacts; it did not make another API call.

## Real probe state

- Run: `runs/obc140_v4_20260923`
- Request attempts: 1
- Browser operations: 0
- `b001`: proposal `blocked`; later stages `not_run`
- Other 139 tasks: all stages `not_run`
- Global state: `blocked / server_quota_exceeded`

## Checks deferred until service restoration

These are validation checkpoints, not reasons to call the service again now:

1. Confirm the first successful proposal is structurally valid, uses one exact public option, and records the gateway-reported model/usage.
2. Complete only `b001` generation, verification, and translation before resuming the remaining tasks; inspect raw English, normalized chains, verifier output, and translation warnings together.
3. Treat translation completion as structural completion. Numeric-literal or duplicate-source consistency warnings remain visible and require review; English source records remain authoritative.
4. Resume only with the explicit service-restoration flag. Do not replace the run, delete the blocked round, or launch the full batch automatically.

No production code was changed by this review. Only this review artifact and the requested trace were added.
