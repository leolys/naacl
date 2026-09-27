# 实验独立审查：20260906T1219Z

审查者：fresh gpt-5.6-sol ultra；same-family / provisional；总体 WARN。
以下为审查者完整回复。代码路径相对 research/decision_evidence_audit；运行工件相对 runs/stage2_live_smoke_20260906T1219Z；报告/验证工件在本 revisions 目录。行号为审查时版本。

执行者限定说明：Git executable 存在，但没有可验证 HEAD；审查回复末段的“Git is unavailable”应理解为没有可用提交溯源。硬件 UUID/PID/启动前占用是执行者工具检查记录，不称独立 CUDA 子审查已核验 UUID。服务/客户端/数据/权重未纳入现有14文件 fingerprint 的限制保留；本轮不新增 hash、contract 或 gate。

## Independent audit verdict

**Overall: WARN — same-family/provisional.** The run is a valid, tightly bounded real-model engineering smoke, but not a valid B0/B2/B3/B4 efficacy comparison. The documented stage-two stopping point is appropriate.

| Area | Verdict | Finding |
|---|---|---|
| A. Ground truth and isolation | **PASS** | Ground truth comes from fixed dataset rows, remains offline, and was not derived from model output. |
| B. Denominators/normalization | **PASS** | All 16 configured units remain in the denominator; no output-based normalization or post-hoc exclusion was found. |
| C. Files/numbers/retention | **WARN** | Primary counts match, including failed scores, but end-to-end source/model provenance is incomplete and some hardware particulars are only executor-recorded. |
| D. Called vs dead code | **WARN** | Model, scorer, validator, aggregator, replay, and POST paths ran. B3’s intended active-observation/accepted-decision semantics did not. Natural revision never ran. |
| E. Scope/limits | **PASS** | Exactly 2 tasks × 2 conditions × 4 strategies = 16 units; 55/160 calls and 149/800 transitions including controls. No pilot expansion. |
| F. Classification | **PASS** | `real_gt` at the scoring boundary, using a released synthetic benchmark inside a local simulated browser shell. Injected controls are `simulation_only`; this is not human evaluation, self-supervision, or a real-world deployment. |

### A — PASS: provenance and online isolation

- Exact task sources are `web_agent_benchmark/benchmark_v2_open/splits/{official140,clean140}/environment35_tasks.jsonl:1` for `env001` and `:25` for `env025`. `evaluator/pair_invariant_audit.json` records no non-chart field differences.
- Online task projection is allowlisted and option labels are sorted independently of expected-answer order: `core.py:18-69,135-171`.
- Visible DOM extraction removes hidden/disabled content, including `display:none`, `visibility:hidden`, and `opacity:0`: `runner.py:225-275`; browser adversarial control: `tests/test_browser_integration.py:122-160`.
- The local shell receives only the public projection and has no scorer object; scoring occurs offline from receipt label → dataset action ID → expected/misleading IDs: `safe_shell.py:36-51,136-153,196-214,233-254`.
- Strict validation found no forbidden online keys, hidden values, or image metadata leakage across 127 online JSON files and 70 images, and checked 41 request files/54 image references: `validation.strict.json:61-89`; implementation at `validate_run.py:453-512`.
- I independently checked every referenced request image: files exist, Pillow dimensions match returned server metadata, and `image.info` is empty. Filenames are generic ordinals/roles, not task, condition, source-chart, or answer filenames.

Limitation: this establishes within-run provenance to the packaged benchmark rows, not independent semantic validation of how those labels were originally constructed.

### B — PASS: denominators and scores

- `evaluator/scores.jsonl:1-16` contains all 16 units: 12 `success`, four `misleading_failure`, no exclusions.
- Each strategy is reported as 3/4 because all four task-condition cells remain included. No denominator depends on whether the model submitted, changed, or answered correctly.
- `summarize_run.py:18-88` copies/counts raw finalized outcomes; it does not regenerate favorable labels or normalize by completed successes.
- Execution-failure retention is implemented in `runner.py:1017-1095` and enforced at `validate_run.py:323-385`. The live run had no execution failures, so that branch is supported by controls/tests rather than a live failure. The four evaluation failures are visibly retained.

### C — WARN: claimed versus actual artifacts

Verified exact:

- 4 checkpoints, 16 units, 16 state-equal and screenshot-equal replays, 16 single POSTs, 16 receipts, 16 confirmations, 41 real model calls, and 96 live browser transitions: `run_manifest.json:86-115`, `validation.strict.json:3-20`, and `real_smoke_status.json:2-15`.
- Raw cardinalities agree: 16 unit maps/results/scores/receipts, 4 prefix records, 41 requests, 41 successful responses, contiguous request ordinals.
- Call decomposition is exactly `1 witness + 16 prefix + 4 B2 + 12 B3 + 8 B4 = 41`.
- Current `summarize_run.py` reproduces `analysis.final.json`; final accounting is 41 real calls, 14 control mocks, 96 live transitions, 53 control transitions, totals 55/149: `analysis.final.json:35-41`. The old `analysis.json` is explicitly retained as the first, superseded aggregation: `STAGE_REPORT.md:121`.
- B3’s misleading legacy count is corrected without rewriting raw artifacts: zero accepted decisions, zero successful crops, eight dispatch errors at `analysis.final.json:2040-2047` and `STAGE_REPORT.md:82-90`.

Remaining limitations:

- `run_manifest.json:132-191` fingerprints only 14 package files. It does **not** bind the actually executed `qwen3_vl_server.py`, local-Qwen path in `adversarial_pipeline/llm_client.py`, exact task JSONLs/chart assets, or model weights. Git HEAD is unavailable. Thus those external dependencies could change in place while `current_tree_matches_recorded_files` remains true (`validate_run.py:518-574`).
- Qwen family/path/8B identity is strongly supported, but exact upstream model revision or weight content is unverified; the report already admits this at `revisions/20260906T1219Z/STAGE_REPORT.md:27`.
- The physical GPU UUID, PID, and pre-run 3 MiB figures at `STAGE_REPORT.md:21,29` are not independently backed by raw pre-run query output in scope. `ENVIRONMENT_WITNESS.md:14` explicitly says its independent command did not verify physical UUID. Post-run GPU release and port release are supported by `gpu_released.csv` and `port_released.txt`.

### D — WARN: actual semantic execution

The local model path genuinely ran:

- Qwen3-VL BF16/eval loading and native ordered multi-image processing: `qwen3_vl_server.py:40-70,85-123,149-169`.
- Single loopback POST path, proxy environment disabled, with returned model/image/protocol metadata: `llm_client.py:1198-1245,1566-1590`; loopback restriction and zero automatic retries: `models.py:223-308`.
- `service.log:1-7,11-51` shows model loading and exactly 41 HTTP 200 `/complete` requests.
- Scorer, strict validator, and final aggregator all produced reproducible outputs, so they are not dead reporting code.

Policy semantics:

| Policy | Actual live execution |
|---|---|
| B0 | **Executed as intended.** Four units, zero policy calls, original saved proposal submitted unchanged. Outcomes 3/4. Code: `policies.py:121-140`. |
| B2 | **Executed as intended at interface level.** Four one-call decisions; request contains goal/options and dashboard but intentionally omits current selection (`policies.py:161-192`). All parsed valid; no revisions; outcomes 3/4. Terminal correctness does not validate rationale quality. |
| B3 | **Semantic failure.** Four units × three calls, but zero accepted decisions and zero crops. Each of eight “active observations” was an empty dispatch ending `unknown screenshot_id`; initial replies tried `click_button Submit Form`, and later env001 replies nested the decision under `decision`, which the top-level parser rejects. See all four `online/units/unit_{0003,0007,0011,0015}/result.json:4-43`; representative detail at `unit_0003/result.json:9-41`. Its 3/4 terminal score is only fallback retention of the prefix choice, not B3 performance. |
| B4 | **Executed as intended at interface level.** Four dashboard extraction calls followed by four decisions using extraction/current/options plus a neutral 32×32 image, not the chart itself: `policies.py:338-395`. All parsed valid; no revisions; outcomes 3/4. |

Actual revision status:

- Every live unit has `revision_action: null`; natural revisions = 0 (`real_smoke_status.json:14`).
- The revised-selection → actual POST branch is demonstrated only by the injected browser control at `revisions/20260906T1219Z/browser_controls/test_checkpoint_replay_true_revision_submit_b0_and_illegal_control/online/b2/result.json` and its `receipts.jsonl`. That control changes Route A→B, cancels the proposal, executes selection, then submits B.
- B0’s no-check equivalence is independently demonstrated against a direct no-hook submission in the sibling `online/b0/result.json` and `tests/test_browser_integration.py:198-228`. These are simulation controls, not natural learned-model recovery.

### E — PASS: scope, replay, retries, and ceilings

- Runner hard-limits the smoke to one or two named development tasks and refuses requested budgets above 160/800: `runner.py:914-926`.
- Scheduling is exactly two conditions and four policies per task: `runner.py:976-1004`; therefore the ceiling is 16 configured units.
- Neutral first-submit interception occurs before the executor and checks receipt count did not change: `runner.py:578-710`, with four finalized `online/prefixes/prefix_000{1..4}/{checkpoint.json,prefix_result.json}` artifacts. All show zero receipts at capture.
- All 16 branches physically replayed the same public state and screenshot before policy execution and performed one final submission: `runner.py:747-907`; confirmed at `validation.strict.json:7-18`.
- The two-image witness consumed one real model call and returned two ordered 512×384 images with matching identity/size/protocol metadata: `run_manifest.json:27-84` and `online/preflight_witness/result.json`.
- Model calls are charged before backend invocation, including failures: `models.py:68-123`. Local Qwen has no auto-retry loop. Live browser actions were all attempt 1; retry and single-submit behavior are covered by `tests/test_core.py:535-575` and `tests/test_browser_integration.py:393-455`.
- Conservative total is 55 calls and 149 transitions, below 160/800, with exactly 16 experiment units. Unit-test stubs are not additional model experiments.

### F — PASS: evaluation classification

This is a **released synthetic benchmark with fixed dataset ground truth (`real_gt` at the evaluator boundary), real local Qwen inference, and a locally adapted simulated web shell**. The browser controls are `simulation_only`. It must not be described as a pilot, real-world task performance, human evaluation, or support for the proposed research mechanism. `run_manifest.json:194-196`, `analysis.final.json:2047`, and `real_smoke_status.json:15,18-19` classify it consistently.

### Supported and unsupported claims

Supported:

- Real Qwen3-VL-8B-Instruct-family inference ran at the recorded local path.
- Ordered two-image transport, request/response recording, neutral checkpoint capture, exact replay, one POST per unit, server receipt, confirmation, and offline scoring all worked.
- Scores are mechanically 3/4 per strategy and 12/16 overall.
- No learned policy changed a selection.
- B3 had zero accepted decisions/crops and eight failed dispatches.
- Current final reports correctly stop at engineering-smoke conclusions.

Unsupported or requiring qualification:

- Any claim that all four policy interfaces passed.
- Any B3 efficacy, “eight active visual observations,” or generic active-verification failure claim.
- Any natural revised-POST/recovery claim; only an injected control revised.
- Policy ranking, error-recovery rate, false-positive damage rate, generalization, or necessity of a new mechanism.
- Semantic correctness of model rationales merely because the selected label scored correctly.
- Exact upstream model revision/weight identity.
- Independently verified GPU UUID/PID/pre-run state.
- Live execution-failure retention beyond the no-execution-failure run; only evaluation failures were exercised live.

### Actions and stopping point

The current stop is correct: do not proceed to a pilot or candidate mechanism.

1. Fix B3’s phase/schema contract generically, with distinct counters for invalid output, legal observation request, successful crop, and accepted decision. Preserve the old run and do not silently accept nested schemas.
2. Exercise direct decision, valid crop with accumulated 3/4-image history, illegal action, and nested-decision rejection in a small simulation control. A new learned-model smoke requires separate authorization.
3. Before any formal pilot, minimally bind the external server/client, exact task rows/chart assets, and model revision used. This is justified because Git is unavailable and these dependencies sit outside the current 14-file fingerprint, so in-place changes cannot otherwise be detected.
4. Qualify hardware particulars as executor-recorded unless raw UUID/PID/pre-run evidence is preserved.
5. Resolve the `env001` rule ambiguity and separate `env025` action correctness from rationale correctness before treating either as research evidence.

I applied the project-local `experiment-audit` A–F rubric; because this review is from the same model family, it remains explicitly provisional.
