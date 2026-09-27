# Experiment Audit Report

最终补充审查见 [EXPERIMENT_AUDIT_SUPPLEMENT.md](EXPERIMENT_AUDIT_SUPPLEMENT.md)：仍为 WARN，无当前支持范围内的 critical 问题。最终68 mock calls/229 transitions、33单元测试通过、3浏览器测试通过。当前可见选择项均公开；泛化到隐藏/禁用的已选 option 尚未验证。子审查平台日志的 spawn message 实际是加密载荷，已保留 ciphertext 和完整 final 响应，但不冒充可读的原始 prompt；主审查请求/响应全文已记录。

Date: 2026-09-06
Auditor: fresh GPT-5.6-Sol ultra, same-family/provisional.
Overall verdict: WARN. Integrity status: warn.

以下是独立审查者第一份完整响应；行号和54/175预算对应其审查时截面。随后针对DOM和B3反馈的补充修正、最终预算见STAGE_REPORT和本目录session_accounting.json。原文“34/34 discovered with two ... skips”实际为34发现、32通过、2跳过，不是34个全部执行通过。最终源码另有36发现/33通过/3浏览器入口跳过的日志。完整子审查trace已另外请求，不把概述当逐字原文。

review_independence=same-family
acceptance_status=provisional

Overall verdict: **WARN — acceptable only as a stage-one inventory and stage-two engineering-only simulation artifact.**

| Check | Verdict | Finding |
|---|---|---|
| A. GT provenance / isolation | **WARN** | GT comes directly from the release-candidate dataset (`official140/.../environment35_tasks.jsonl:1,25`; `clean140/.../environment35_tasks.jsonl:1,25`). Actual requests, opaque filenames, and screenshots showed no checked leak, and scoring occurs only after terminal receipt (`runner.py:1157-1179`). However, generalized isolation is incomplete: DOM extraction includes hidden controls (`runner.py:225-245`), which are passed as public state and can trigger the hook (`core.py:172-210,221-240`). The supplemental forbidden-key set is not a full allowlist (`core.py:27-61,127-130`), and hidden values are scanned only in request files, not filenames/error logs (`validate_run.py:446-512`). No actual run leak was found. |
| B. Normalization | **PASS** | Scoring is categorical action-ID mapping, without own-maximum or selective-denominator normalization (`safe_shell.py:233-254`). All 16 configured units remain represented. |
| C. Counts / artifacts | **PASS** | Direct reconciliation found 16 units, 4 prefixes/checkpoints, 36 request/response pairs, 16 replays/results/scores/POST receipts, 96 transitions, and 8/8 scripted outcomes, matching `run_manifest.json:21-47` and `validation_post_review.json:8-69`. All replay image/state values also matched on independent read-only recomputation. Current-source divergence is explicitly preserved (`validation_post_review.json:71-95`). |
| D. Code / behavioral coverage | **WARN** | Post-review score/receipt/action consistency checks are now present and exercised (`validate_run.py:149-188,341-347`; `unit_tests_post_review.log:9-24`). Remaining gaps: B3 carries successful crop images but not saved prefix trajectory, crop coordinates, or tool-error feedback (`policies.py:194-323`; `core.py:278-280`), so “generic active tool/history” is supported only as a bounded crop/image-history baseline. The validator still trusts stored replay equality flags (`validate_run.py:317-320`) and does not require paired successful response files (`validate_run.py:408-435`). Hidden-DOM behavior is untested. |
| E. Scope / budgets | **PASS** | Only stages 1/2 were executed. The sole smoke grid is 16 units at 36/96; aggregate retained smoke plus browser controls is 54 mock calls/175 transitions, below 160/800 (`session_accounting.json:2-17`). The initial failed main-control 4/13 portion is honestly marked reconstructed. Current real-model calls are zero, with no service/GPU/API startup (`real_smoke_status.json:2-12`; `run_manifest.json:7-20`). Historical live work is clearly separated. |
| F. Evaluation type | **PASS** | `evaluation_type=simulation_only`: the backend is scripted and explicitly non-research (`run_manifest.json:7-20,127-129`; `validation_post_review.json:339-340`). Dataset GT is used only for terminal plumbing. No B0/B2/B3/B4 efficacy or visual-model result exists. |

Required semantic checks:

- Neutral first-before-submit: **PASS for the safe shell**, subject to the hidden-DOM limitation. Capture precedes execution and is one-shot (`runner.py:616-638`; `core.py:293-330`).
- B0 direct equivalence: **PASS within the adapted neutral protocol**. The injected browser control compares direct continuation with B0 receipts/actions (`tests/test_browser_integration.py:154-186`). It is not original-benchmark equivalence.
- B2 independent observation: **PASS**; dashboard required, current selection excluded (`policies.py:142-191`).
- B3 genuine tools/history: **WARN**; real crop execution and cumulative images exist, but it is not unrestricted browser-tool or complete trajectory/error history.
- B4 self-extraction: **PASS**; the same backend extracts from the observed dashboard and consumes its own extraction (`policies.py:326-369`).
- Same executor/budgets, failure retention, exact replay, real POST, and no scorer feedback: **PASS** for exercised paths. The smoke had no semantic revision; actual changed-selection POST is proven only by the injected positive control (`tests/test_browser_integration.py:187-206`).

Actionable remaining issues, highest severity first:

1. **Medium:** Filter hidden/disabled links, buttons, selects, and options before constructing public DOM state or testing submit visibility; add one hidden-DOM swap/control.
2. **Medium:** Describe B3 as a bounded crop/image-history baseline unless prior trajectory and failed-tool feedback are actually returned to the model.
3. **Low:** If `valid=true` is intended to certify replay integrity, recompute canonical state and screenshot hashes rather than trusting `state_equal`/`screenshot_equal`; also reconcile request/response IDs and success status.
4. **Low:** Preserve a session-wide ledger for future failed controls. Current reconstructed 4/13 accounting is credible and far below the cap, but not equivalent to a persisted ledger.

Resolved during review:

- Current scorer now uses non-causal `selected_dataset_misleading_option` (`safe_shell.py:246-250`); legacy run scores retain `chart_induced_intermediate_decision_error` and must not be interpreted causally (`STAGE_REPORT.md:40-42`).
- B3/B4 no longer substitute a form image for a missing dashboard (`policies.py:65-70,142-153`).
- The manifest is now correctly documented as descriptive rather than executable (`PROTOCOL.md:9-10,134-138`).
- Post-review unit tests pass 34/34 discovered with two opt-in browser skips, and offline revalidation passes without rewriting the original run.

Claim ceiling: evidence supports asset/count facts and the exercised safe-shell checkpoint/replay/POST/scoring engineering chain. It does **not** support visual-model capability, policy efficacy, causal chart-error attribution, original benchmark equivalence, the sufficiency of B2/B3/B4, or the need for a new mechanism. `env001` additionally remains semantically under-specified for research scoring (`LOCAL_AUDIT.md:18,224`).

Delegated-review traces containing the full prompts and final payloads:

- `/root/stage2_integrity_review/gt_isolation` — prompt: direct source/dataset/original-runner isolation review covering trigger, B0/B2/B3/B4, POST and scorer feedback. Final: WARN, identifying hidden-DOM, guard/scanner, validator, and B3-history qualifications.
- `/root/stage2_integrity_review/artifact_counts` — prompt: direct manifest/run/revision review covering B–E, counts, caps, failures, replay and executor identity. Final: counts/scope passed with validator/accounting qualifications.

Trace disclosure: the artifact-count reviewer unintentionally ran `python -m compileall -q research/decision_evidence_audit`, potentially refreshing pre-existing `__pycache__`. No source, dataset, run artifact, browser transition, or model inference was changed; the deviation is retained at `COMMANDS.md:73-77`.
