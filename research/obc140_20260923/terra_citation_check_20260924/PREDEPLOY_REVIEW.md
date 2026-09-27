# Terra public-task citation compatibility predeployment review

**Gate:** PASS for the first fresh `gpt-5.6-terra` / `b001` four-stage case. The second `pub013` case remains on the planned manual hold until the first case is inspected. This is a same-family, provisional review; `gpt-5.6-sol` with `xhigh` effort was requested, but the actual reviewer backend/model identity was not independently verified.

**Timeline note:** the operational PASS/HOLD gate was communicated before the fresh run's recorded creation time (`2026-09-24T10:57:11.029203+08:00`). This Markdown file was materialized later at `2026-09-24T11:00:36.9026264+08:00`, after the executor had followed the checkpoint and completed both cases. The later fresh results were not backdated or used as predeployment evidence. The four-case offline replay and the fresh eight-call run remain distinct artifacts.

## Blocking issues

None for starting the first `b001` case.

## Correctness and false-acceptance review

- The adapter deep-copies the verifier value before changing it. It retains each model-written task citation, adds the exact located public string and normalized field path, marks the binding `source_bound_content_not_verified`, and returns the untouched raw verifier object separately.
- Only `chart_1`, the current `task_alias`, `task`, and `public_task` are accepted as evidence sources. A task citation must identify a real, nonempty string leaf in the supplied `record["public_task"]`; missing fields, other task aliases, private/offline paths, container values, and empty model text are rejected.
- Task citations are removed from visual `evidence` and placed in `task_evidence`. The unchanged parent verifier therefore still requires at least one `chart_1` item for every check. The task citation never enters generated-chain O and never enters rule-state `E`.
- The original parent validation still checks complete/unique chain coverage, the three O/B/implication labels, public recommendation labels, a fully supported chain for a recommendation, conflicting fully supported options, and disputed shared rules. The adapter does not use task binding to rescue an unsupported recommendation.
- Source binding is intentionally not paraphrase entailment. A false model paraphrase can remain present with the original source text beside it and the unverified marker. Consequently, schema acceptance does not certify that the paraphrase, B judgment, implication, reason, or recommendation is semantically correct.
- `offline_metadata`, gold, and answer fields are not read. `engine.assert_public` is applied to the public record before binding.

## Offline replay evidence

The saved replay contains exactly four archived verifier responses and reports zero model requests. The archived source SHA-256 values match the source files, and every adapted `verification_raw` equals the corresponding archived parsed object.

- Sol / `b001`: old accepted; adapted accepted; zero citation moves.
- Sol / `pub013`: old accepted; adapted accepted; zero citation moves.
- Terra / `b001`: old rejected with `evidence must reference actual chart observation`; adapted accepted with exactly one move from `task_001.user_goal` into `task_evidence`.
- Terra / `pub013`: old accepted; adapted accepted; zero citation moves.

The replay is stored outside the fresh `run/` directory and does not rewrite any archived record or response. It is deterministic reinterpretation, not new model output and not a repair of the old failed run.

## Budget, input, and result invariants

- Fixed live scope: `("b001", "pub013")`, Terra only, two known development cases, no 140-task batch.
- Hard persistent ceiling: eight request attempts total; one attempt per logical call; four ordered stages per case; no automatic retry.
- Inherited endpoint/model/temperature/token caps are unchanged: 700 / 2200 / 2200 / 6500, temperature 0, serial configuration, no browser, business action, GPU, or W&B path.
- Each case stops after the first incomplete/invalid/failed stage, so dependent stages are not sent. Service blocks become a global sticky stop. Parent interrupted-request handling reuses a saved parse or marks the outcome failed without resending.
- Initialization snapshots the two catalog rows, configuration, source files, public records, and chart provenance; resume rejects changed snapshots. At live-run creation, the reviewed `PLAN.md`, `citation_adapter.py`, and `run_validation.py` hashes matched the run's own `runtime.json` source snapshot.
- The live output directory and protocol are separate from the archived APIYI selection runs and the offline replay. The runtime metadata correctly limits model identity to the requested and gateway-reported alias.

The primary test artifact records 90 tests, zero failures, zero errors, and zero skips. Coverage includes exact/invalid field paths, other-task and unknown refs, task-only evidence, raw `task_evidence` forgery, false paraphrases, source-metadata forgery, input immutability, private metadata, unchanged chart-only replay, recommendation/conflict guards, validator restoration, and the Terra/two-task/eight-request/no-retry configuration.

## Non-blocking issues and required operating conditions

1. `run_validation.py` accepts either task at the CLI and does not itself require a successful, inspected `b001` record before `pub013`. This is non-blocking for the current cooperating-operator run, but the plan's sequence must be enforced operationally: inspect `b001` first; do not invoke `pub013` after an invalid, failed, blocked, or otherwise unacceptable first case.
2. Passing structural validation is not semantic certification. Report located source binding separately from judgment quality, and do not claim that the adapter proves the model's task paraphrase or O/B/C conclusion.
3. The two tasks are known development examples. Success can support bounded engineering compatibility only; it cannot estimate correction benefit, validate unseen generalization, or authorize the 140-task run.

## Gate decision

- First Terra / `b001` case: **PASS TO START**.
- Terra / `pub013`: **HOLD UNTIL MANUAL INSPECTION OF `b001`**, then proceed only if the first case and archived request/response/usage are acceptable.
- 140-task batch: **NOT AUTHORIZED / NOT REVIEWED**.

No network/API call, credential access, browser/GPU/remote action, production-code edit, or old-artifact edit was performed by this review.
