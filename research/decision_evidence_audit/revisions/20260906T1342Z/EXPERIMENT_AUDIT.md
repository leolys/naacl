# Experiment Audit — B3 repair and real smoke

Date: 2026-09-06. Auditor: fresh GPT-5.6-Sol ultra sub-agent, same-family/provisional. Full response below, unchanged. Relative evidence paths are within the project/research package/run as indicated. Executor follow-up messages and interim response are retained in `.aris/traces/experiment-audit/2026-09-06_b3_fix_1342Z/`; this was not a cross-family or fully blinded review.

## Overall verdict: WARN

Same-family/provisional read-only audit. No fake GT, normalization, phantom-result, denominator, or budget failure found. The artifacts support a completed engineering/diagnostic smoke only. They do not support B3 semantic reliability, method ranking, a pilot conclusion, or a claim that a new mechanism is necessary.

### A — Ground truth and online isolation: PASS

GT is dataset-provided, not model-generated. The runner loads the released official/clean rows and requires chart-only pair invariants (`research/decision_evidence_audit/runner.py:50-75,954-969`). The exact rows contain expected action IDs, categorical roles, and computations: env001 at `web_agent_benchmark/benchmark_v2_open/splits/{official140,clean140}/environment35_tasks.jsonl:1`; env025 at the same paths `:25`. Their CSVs independently contain 23.9 and 10.1 (`.../assets/{official140,clean140}/environment35/env001/source.csv:1-11`) and 442/380/255 (`.../env025/source.csv:1-4`).

Online data is constructed by allowlist, labels are publicly sorted to remove raw answer-position leakage, and evaluator keys are rejected (`core.py:18-69,141-171,180-219`). The actual B3 request contains goal, visible options/current choice, permitted history, and two screenshot references, but no GT/action roles/condition/other arm (`runs/stage2_live_smoke_20260906T1342Z/online/units/unit_0003/requests/request_0007.json:3-55`). The validator found no forbidden-key, hidden-value, or image-metadata hit across 33 requests/38 image references (`revisions/20260906T1342Z/validation.strict.json:67-96`).

Limitation: env001’s public “large enough” rule has no numeric threshold; provenance passes, but its business-label semantics are underdetermined (`revisions/20260906T1342Z/STAGE_REPORT.md:24-29`).

### B — Scoring and denominators: PASS

Scoring is offline categorical matching from submitted visible label to the raw task action, with no numeric normalization or prediction-derived denominator (`safe_shell.py:233-254`; `runner.py:1189-1200,1231-1241`). The fixed schedule creates every task-condition-strategy combination (`runner.py:975-1004`), and failure paths retain unrun/unscored units rather than dropping them (`runner.py:1017-1095,1159-1175`). `evaluator/scores.jsonl:1-16` contains all 16 rows: 12 success and four misleading failures, including all four env001-official failures. No exclusions occurred.

### C — Raw artifacts versus counts and claims: PASS

Raw files reconcile: 16 unit results, 16 replays, 16 server receipts, 33 requests and 33 responses. The strict artifact audit reports 4 checkpoints, 16 equal states/screenshots, 16 submissions/receipts/confirmations, 33 calls, and 96 transitions (`validation.strict.json:6-28`). The manifest independently reports the same 16-unit grid and 12/4 outcomes (`runs/.../run_manifest.json:86-115`). The service log has 39 successful `/complete` POSTs, matching 33 grid plus six real control inferences (`revisions/20260906T1342Z/service.log:11-51`; summarized at `analysis.json:35-64`).

The finalized narrative accurately says no natural revision/crop and explicitly warns that `warnings=[]` is structural, not a semantic-control pass (`revisions/20260906T1342Z/STAGE_REPORT.md:39-61,73-100`). No claim-to-artifact mismatch found.

### D — Executed policy/crop/revision paths: WARN

The repaired parser is generic: it accepts only top-level decision or observation JSON and rejects browser actions, nested answers, mixed objects, malformed coordinates, and unknown labels; it never inserts an answer (`policies.py:67-95,242-255,297-339`). It preserves goal, current selection, visible actions/model history, cumulative images, the three-call ceiling, and two dispatched-observation ceiling (`policies.py:227-347`). Invalid outputs consume calls but not observations; valid dispatched attempts count even if cropping fails, while successful crops are separate (`policies.py:294-339`). Tests cover these distinctions and 2→3→4 image accumulation (`tests/test_core.py:275-329,453-520`); final unit and browser logs are 38 tests with three opt-in skips, then 3/3 actual browser tests (`unit_tests_final.log:1-45`; `browser_tests.log:65-78`).

However, the real grid’s four B3 executions each made one call, accepted the current choice, requested/dispatched zero observations, produced zero crops, and made zero revisions (`validation.strict.json:45-58`; representative raw result `online/units/unit_0003/result.json:4-40`). Thus autonomous crop use and natural correction were not exercised.

Both live control sets failed overall. First attempt failed the injected two-crop semantic decision despite two successful crops/four-image transport (`live_controls/summary.json:87-202`). Retry passed transport but failed visible revision: its reason says Route B is correct while its accepted `option_label` is Route A (`live_controls_retry1/summary.json:5-43,198-202`). The parser’s syntactic acceptance does not check reason/action consistency. Four-image delivery itself is evidenced (`live_controls_retry1/.../responses/request_0003.json:18-40`), and the client/server genuinely preserve all images (`models.py:284-307`; `adversarial_pipeline/llm_client.py:1566-1590`; `qwen3_vl_server.py:85-170`).

B0 regression passes: zero calls, unchanged selection (`policies.py:164-173`; `tests/test_core.py:350-360`), with direct-vs-B0 receipt equivalence and true POST tested (`tests/test_browser_integration.py:196-228`). Revision→POST and failure retention are also exercised in browser controls (`:229-258,356-391`), though the final live grid never took the revision branch.

### E — Scope and budgets: PASS

The sole grid is exactly 2 tasks × 2 conditions × 4 strategies = 16 (`run_manifest.json:88-103`). Including both failed live-control sets and browser mocks, totals are 39 real + 4 injected + 15 mock = 58 counted calls and 155 transitions (`analysis.json:35-44`), below 160/800. The pre-grid reservation also capped worst case at 145/709 (`revisions/20260906T1342Z/COMMANDS.md:44-48`). No hidden second grid is evidenced.

### F — Evaluation classification: PASS

Main terminal scoring is `real_gt` using dataset-provided GT, executed through an adapted synthetic local web shell—not the original benchmark webpage/runtime. Both live synthetic B3 controls and browser/mock controls are `simulation_only`. The manifest correctly labels the run `stage_two_smoke`, disallows research interpretation, and calls it engineering-chain validation (`run_manifest.json:6,198-200`).

Actionable limitations: retain both failed controls; do not promote 3/4 or 12/16 into efficacy claims; next authorized control should separately test reason/action consistency and genuinely autonomous observation requests without injected crop choices; resolve or replace env001’s ambiguous threshold before any pilot. Unverified: exact upstream weight revision, byte-level equivalence to the official benchmark runtime/scorer, exhaustive pixel/OCR leakage, and cross-family reviewer independence.
