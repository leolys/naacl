# Health004 supplement predeployment review — 2026-09-23

**Review status:** same-family Codex review; provisional, not cross-model-independent.

**Scope:** read-only review of the current `engine.py`, `run_supplement.py`, `configs/health004_supplement.json`, and the two archived V2 health004 generator failures. No API request or browser operation was performed by this review. Only the archived response text was passed through the new pure parsing/candidate-normalization functions offline.

## Verdict

### BLOCKING

None found. The fixed two-condition, full-method-only health004 supplement is ready to launch with `configs/health004_supplement.json`.

### NONBLOCKING / reporting boundary

The supplement is a post-interface-fix engineering result. It must remain separate from the immutable V2 rows, must not be counted as two new independent tasks, and must not be described as natural recovery, a clean rerun of the original protocol, or evidence of general method efficacy.

## Actual request and failure summary

- Immutable V2 completed with **38 request attempts** and **62 browser operations**. Together with V1 and the recorded engineering/replay operations, the pre-supplement aggregate is **73 requests** and **141 browser operations**.
- The health004 official/`case03` full-method generator returned a valid object with **4 rules and 4 chains**, exceeding the fixed total candidate budget `K+1 = 3`. The raw first three chains include the proposed expansion route and two additional emitted explanations; the fourth chain is the omitted general-route explanation.
- The health004 clean/`case04` full-method generator returned `finish_reason: "stop"`. Its response text contains one complete JSON object with exactly the root keys `rules` and `chains`, both list-valued, containing **3 rules and 3 chains**. Python `raw_decode` consumed characters `0..2436` (`object_end = 2437` of 2439); the entire remaining suffix is exactly `]}`. There is no explanatory text, opening delimiter, or second JSON value.

## Findings

1. **Trailing-delimiter repair is syntax-only and fail-closed.** Normal JSON parsing runs first. The fallback is enabled only by the supplement config, only for the generator phase, and only when the API reports `finish_reason: "stop"`. It requires one complete dictionary with exactly `{rules, chains}`, requires both values to be lists, and accepts only trailing whitespace and redundant closing `]`/`}` delimiters. Text, a second object/array, an opening delimiter, a truncated first object, or another root shape is rejected. The raw `response_*.json` remains unchanged; the repaired representation and metadata record finish reason, decoded endpoint, exact ignored suffix, and rule/chain counts.

2. **Candidate cap implements the declared finite K without answer-aware selection.** When enabled, normalization retains raw chain indices `0..K` before deduplication, performs no duplicate backfill, and restricts processing to rules referenced by retained chains. `candidate_bound_audit.json` records raw count, limit, retained indices, omitted indices, and the selection rule. The existing proposed/current-option guard remains after normalization, so an ordering that omits the current argument fails closed rather than being rearranged using the action or score.

3. **Archived payloads exercise the intended paths.** Offline, the clean response repaired to the complete 3-rule/3-chain object with metadata `object_end: 2437` and `ignored_suffix: "]}"`. The official response deterministically reduced from 4 raw chains to 3 normalized chains and 3 referenced rules. No model call, verifier call, browser restoration, or gold lookup was needed for these checks.

4. **Supplement scope is mechanically bounded.** `run_supplement.py` accepts only aliases `case03` and `case04`, task `health004`, and system `competing_persistent`; it rejects request or browser caps above 40. It invokes the existing `one_run` implementation for exactly those two trajectories, writes a separate scope/config/runtime-source snapshot, and produces a separate offline result file without modifying V2.

5. **Budget is safely below the aggregate ceiling.** The supplement config caps new work at **40 request attempts** and **40 browser operations**, tighter than the available 77/159. Thus the worst-case aggregate is **113 requests** and **181 browser operations**, below the declared 150/300 limits. Per-attempt and per-operation charging continues through the existing shared budget implementation.

6. **Model and task controls remain fixed.** The supplement retains `gpt-5.6-sol`, temperature 0, max tokens 2200, three transport attempts per call, seven actor calls, one extra verification, two competitors, the same endpoint/proxy/browser, and the same health004 official/clean prepared cases. The only enabled interface changes are explicit action-container normalization, generator-only redundant-closing recovery, and deterministic first-`K+1` candidate capping.

## Recommendation

Launch only the two fixed health004 full-method supplement trajectories with the reviewed config and a new output directory. Preserve V1 and V2 unchanged, report both original V2 interface failures, and present the supplement solely as separately labelled engineering validation of the corrected interface.
