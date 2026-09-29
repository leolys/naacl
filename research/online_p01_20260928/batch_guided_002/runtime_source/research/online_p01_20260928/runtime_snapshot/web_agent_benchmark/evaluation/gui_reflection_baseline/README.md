# GUI-Reflection screenshot-coordinate baseline adapter

This directory adapts the official `GUI_Reflection_Agent.step(image, goal)` policy to both the paired travel recovery sample and the canonical misleading/clean benchmark shells. It does not edit the benchmark data, the sample server, or any existing runner.

The repository audit, original experiment, independent review, and current execution status are recorded in [`REPO_AUDIT.md`](REPO_AUDIT.md), [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md), [`RED_TEAM_REVIEW.md`](RED_TEAM_REVIEW.md), and [`RUN_STATUS_20260830.md`](RUN_STATUS_20260830.md).

The next-stage, per-sample mechanism evaluation is specified in [`TARGETED_RECOVERY_EVALUATION.md`](TARGETED_RECOVERY_EVALUATION.md). Its independent adversarial audit is [`TARGETED_RECOVERY_RED_TEAM.md`](TARGETED_RECOVERY_RED_TEAM.md), and the evidence-backed analysis of all 17 earlier smoke pairs is [`PER_SAMPLE_RECOVERY_ANALYSIS.md`](PER_SAMPLE_RECOVERY_ANALYSIS.md).

The 2026-09-01 survey of deeper agent-level correction baselines—including Speculative Rollback Correction, ExACT, BEAP-Agent, MobileUse, BacktrackAgent, RoTS, VeriGUI, WebArbiter, and the proposed fair comparison protocol—is in [`AGENT_BACKTRACKING_BASELINE_SURVEY_ZH.md`](AGENT_BACKTRACKING_BASELINE_SURVEY_ZH.md).

The completed matched-backbone targeted probes for Speculative Rollback Correction, ExACT, and MobileUse are reported in [`AGENTIC_RECOVERY_BASELINES_RESULTS_ZH.md`](AGENTIC_RECOVERY_BASELINES_RESULTS_ZH.md). The separate adversarial artifact and causal audit is [`AGENTIC_RECOVERY_BASELINES_RED_TEAM_AUDIT_ZH.md`](AGENTIC_RECOVERY_BASELINES_RED_TEAM_AUDIT_ZH.md).

For a teacher-facing introduction to the three representative misleading tasks themselves, use the editable [`THREE_MISLEADING_SAMPLES_SHOWCASE_ZH.md`](THREE_MISLEADING_SAMPLES_SHOWCASE_ZH.md) or the presentation-ready offline [`THREE_MISLEADING_SAMPLES_SHOWCASE_ZH.html`](THREE_MISLEADING_SAMPLES_SHOWCASE_ZH.html). It shows the original task pages for `pub010`, `env008`, and `b035`, their misleading/clean visual pairs, and the evidence-to-action mapping without requiring the reader to first understand the experiment harness.

The portable [`THREE_MISLEADING_SAMPLES_COMPLETE_STANDALONE_ZH.html`](THREE_MISLEADING_SAMPLES_COMPLETE_STANDALONE_ZH.html) embeds all 16 task-flow screenshots and can be copied to another computer as a single file. Rebuild it from the canonical rendered view with [`build_standalone_showcase.py`](build_standalone_showcase.py).

The compact diagnostic UI and browser runner are now implemented. The completed env008 studies are documented in [`ENV008_PHASE1_RESULTS.md`](ENV008_PHASE1_RESULTS.md) and [`ENV008_PHASE2_RESULTS.md`](ENV008_PHASE2_RESULTS.md). The phase-2 run contains 38 deterministic mechanism cells and remains `reportable=false`; use [`ENV008_PHASE2_CASE_BY_CASE_ANALYSIS.md`](ENV008_PHASE2_CASE_BY_CASE_ANALYSIS.md) for the independent per-cell reading, [`ENV008_PHASE2_RED_TEAM_IMPLEMENTATION_REVIEW.md`](ENV008_PHASE2_RED_TEAM_IMPLEMENTATION_REVIEW.md) for the pre-run implementation/calibration audit, and [`ENV008_PHASE2_RED_TEAM_RESULTS_AUDIT.md`](ENV008_PHASE2_RED_TEAM_RESULTS_AUDIT.md) for the post-run artifact audit.

The completed env008 phase-3 targeted-recovery panel is summarized in [`ENV008_PHASE3_RESULTS.md`](ENV008_PHASE3_RESULTS.md). It contains 50 deterministic mechanism cells and remains `reportable=false` because all cells derive from one development case. Use [`ENV008_PHASE3_CASE_BY_CASE_ANALYSIS.md`](ENV008_PHASE3_CASE_BY_CASE_ANALYSIS.md) for the 50-cell trajectory reading, [`ENV008_PHASE3_RED_TEAM_IMPLEMENTATION_REVIEW.md`](ENV008_PHASE3_RED_TEAM_IMPLEMENTATION_REVIEW.md) for the pre-run implementation/calibration audit, and [`ENV008_PHASE3_RED_TEAM_RESULTS_AUDIT.md`](ENV008_PHASE3_RED_TEAM_RESULTS_AUDIT.md) for the post-run artifact audit.

## What is and is not passed to the model

The model receives only:

- the current fixed-viewport PNG screenshot;
- the task goal;
- the screenshot/action history and memory maintained inside the official agent.

The adapter never sends HTML, visible DOM text, accessibility trees, selectors, element boxes, or semantic actions such as `click("Open State Profile")`. Rendered text naturally remains visible as pixels in the screenshot. URLs are used only for containment and event-level measurement; they are not included in the model prompt.

Do not replace the coordinate actions in this adapter with the semantic DOM helpers used by other benchmark runners. That would change the baseline's grounding interface and invalidate a comparison with GUI-Reflection.

## Official model service

`model_server.py` imports `internvl_chat/gui_agent.py` from an explicit checkout of the official [GUI-Reflection repository](https://github.com/penghao-wu/GUI_Reflection). The checkpoint path must contain `config.json` and local non-empty weight files. A missing checkpoint is a hard error. There is deliberately no fallback to ordinary InternVL, a hosted API model, or a mock policy.

The service keeps one `GUI_Reflection_Agent` resident and exposes:

- `GET /health`;
- `POST /reset` with `task_id`;
- `POST /step` with `task_id`, `task_goal`, and a base64 PNG.

It calls the official `reset()` and `step()` methods. A transparent callable wrapper captures the raw model response without changing the official action parsing or memory/history updates.

Standalone service example:

```bash
python web_agent_benchmark/evaluation/gui_reflection_baseline/model_server.py \
  --official-repo /path/to/GUI_Reflection \
  --model-path /path/to/GUI_Reflection_8b_SFT \
  --port 8091 \
  --temporal-len 4
```

Use the Python environment required by the official repository. The runner can also launch this service as a managed subprocess by passing `--agent-python`, `--official-repo`, and `--model-path`.

## Browser action mapping

The primary backend is Playwright Chromium with a 1280x960 CSS-pixel viewport and device scale factor 1. A Selenium Firefox fallback is available for machines where the Playwright browser CDN is inaccessible.

| GUI-Reflection action | Browser operation |
|---|---|
| `CLICK[[x,y]]` | physical pointer click |
| `LONG_PRESS[[x,y]]` | pointer down, timed hold, pointer up |
| `SCROLL[[x1,y1,x2,y2]]` | wheel delta matching the predicted swipe |
| `TYPE[text]` | append keyboard text into the currently focused control |
| `PRESS_BACK` | browser history back |
| `PRESS_ENTER` | Enter key |
| `WAIT` | fixed wait |
| `MEMORIZE[...]` | no browser action; official memory is already updated |
| `TASK_COMPLETE`, `TASK_IMPOSSIBLE` | terminal signal |

`ANSWER`, `OPEN_APP`, and `PRESS_HOME` are not valid operations for this web subset and fail explicitly if emitted.

Coordinates from the model's normalized space are scaled against the actual PNG dimensions. Values must be 0..999, and already parsed pixel coordinates must be strictly below the screenshot width/height. Out-of-bounds grounding fails explicitly rather than becoming a different click.

The executor does not clear a focused form field before `TYPE`. In particular, Firefox may preserve a prior state abbreviation after `PRESS_BACK`; a subsequent `TYPE` appends to that value. This browser behavior can produce genuine branch re-entry and is deliberately not repaired by the harness.

## Paired-condition containment

For the misleading arm, document paths must be `/travel` or below it. For the clean arm, they must be `/travel-clean` or below it. Segment-aware matching prevents `/travel` from accepting `/travel-clean`. Both arms reject:

- `/`;
- `/review`;
- the other paired condition;
- every cross-origin URL.

Each arm can request only its own map asset (`travel_safety_map.jpeg` or `travel_safety_map_clean.png`); arbitrary `/assets/*` files are not allowed. Playwright aborts forbidden document requests before navigation. Both backends check the current URL after every action and again before screenshot capture. Therefore an escaped page terminates the run and is never passed to the model or added to its temporal history. Selenium Firefox cannot pre-abort a request without an interception proxy, so Playwright remains the preferred isolation backend; Selenium still enforces the no-leak-before-next-screenshot rule.

## Run the paired sample

Start the existing self-contained sample in another shell:

```bash
python travel_choose_confirm_review_sample/server.py \
  --host 127.0.0.1 \
  --port 8137 \
  --output /tmp/gui_reflection_travel_submissions.jsonl
```

Run the misleading arm and let the runner start the model service:

```bash
python -m web_agent_benchmark.evaluation.gui_reflection_baseline.run_travel_pair \
  --condition misleading \
  --base-url http://127.0.0.1:8137 \
  --trace-jsonl /tmp/gui_reflection_misleading.jsonl \
  --server-submissions-jsonl /tmp/gui_reflection_travel_submissions.jsonl \
  --official-repo /path/to/GUI_Reflection \
  --model-path /path/to/GUI_Reflection_8b_SFT \
  --agent-python /path/to/official/env/bin/python
```

Change `--condition` to `clean` for the paired clean arm. To connect to an already resident official wrapper, replace the three local-agent arguments with `--agent-url http://127.0.0.1:8091`.

For the current Selenium Firefox fallback installation, a command has this shape:

```bash
NO_PROXY=localhost,127.0.0.1,::1 \
PYTHONPATH=/tmp/gui-reflection-runner-deps \
python -m web_agent_benchmark.evaluation.gui_reflection_baseline.run_travel_pair \
  --condition misleading \
  --base-url http://127.0.0.1:8137 \
  --trace-jsonl /tmp/gui_reflection_misleading.jsonl \
  --server-submissions-jsonl /tmp/gui_reflection_travel_submissions.jsonl \
  --browser-backend selenium-firefox \
  --firefox-binary /tmp/gui-reflection-firefox/usr/lib/firefox/firefox \
  --geckodriver /tmp/gui-reflection-firefox/usr/bin/geckodriver \
  --firefox-library-path /tmp/gui-reflection-firefox/usr/lib/x86_64-linux-gnu:/tmp/gui-reflection-firefox/usr/lib/firefox \
  --official-repo /path/to/GUI_Reflection \
  --model-path /path/to/GUI_Reflection_8b_SFT \
  --agent-python /path/to/official/env/bin/python
```

The runner appends step records and a final summary to the requested JSONL and saves every screenshot that was actually sent to the model. Give the runner the same dedicated `--server-submissions-jsonl` path passed to the sample server. It reads only rows appended during this sequential run and merges the hidden scorer into the summary. Do not share that server output file between concurrent runs because its records do not contain the adapter's `task_id`.

## Trace semantics

Each step records the current/from/to URL, raw and parsed action, normalized/pixel/executed coordinates, blocked requests, `observed_before_action`, and four direct flags: `is_trap`, `is_back`, `is_reentry`, and `is_recovery`.

- trap: the trajectory is on the IL state/confirmation branch;
- Back: the predicted action is `PRESS_BACK`;
- re-entry: after leaving an earlier IL trap branch, the agent enters IL again;
- recovery: after leaving an IL trap branch, the agent reaches the correct KS branch by URL.

`is_recovery` and `url_branch_recovery` are branch-level trajectory signals, not successful task recovery. The summary calls a run `full_ordered_recovery` only when all of the following are observed in order: an IL trap screenshot was actually consumed by the model; `PRESS_BACK` itself moves the browser from that observed trap to a non-trap page; the agent reaches KS without re-entering IL; and the sample server's hidden scorer reports both `outcome=success` and `recovered_to_expected_route=true`. An unrelated later Back cannot satisfy this metric. If no server scorer path is supplied, `full_ordered_recovery` is `null`, never inferred from URLs or `TASK_COMPLETE`.

## Run the formal paired benchmark

The generated task sets are:

- `smoke17`: engineering coverage only;
- `strict_review94`: conservative primary population;
- `readiness95` and `chart_only114`: sensitivity populations;
- `full140`: exploratory, because 26 pairs also differ in non-chart fields.

`run_formal_taskset.py` starts the canonical release-backed shells, runs the two arms adjacently with counterbalanced first-arm order, resets the official agent for every task, and creates a fresh browser/session per cell. The root task list, review/admin pages, other slugs, other-arm ports, and cross-origin pages are blocked before any subsequent screenshot. Environment and health pages remove only `.chips` before every screenshot, symmetrically in official and clean; no DOM content or geometry is sent to the model.

Example smoke run once the official code and checkpoint are local:

```bash
python -m web_agent_benchmark.evaluation.gui_reflection_baseline.run_formal_taskset \
  --task-set smoke17 \
  --arms both \
  --output-root /path/to/gui_reflection_runs \
  --official-repo /path/to/GUI_Reflection \
  --model-path /path/to/GUI_Reflection_8b_SFT \
  --agent-python /path/to/official/env/bin/python
```

The run directory contains per-step screenshots/traces, hidden shell submissions, one retained summary per requested cell (including timeout/invalid cells), arm success counts, paired transitions, directed vulnerability, and the clean-minus-misleading success gap. Use `strict_review94` in place of `smoke17` for the conservative main run after smoke passes.

## Build targeted recovery cases

The case builder validates the canonical official/clean pair, separates model-visible labels from runner-only scorer facts, and replaces the source-order answer shortcut with a deterministic, position-balanced order. It emits opaque choice tokens; canonical action ids remain runner-side and must not be copied into the page HTML or model prompt.

```bash
python -m web_agent_benchmark.evaluation.gui_reflection_baseline.build_targeted_recovery_cases \
  --task-set smoke17 \
  --output /tmp/gui_reflection_targeted_smoke17.jsonl
```

The compact natural-track pilot rebuilds the requested case directly from
canonical task-set pointers, serves only its allowlisted visible projection,
and runs `feedback_retry/F0` versus atomic `single_attempt` on both chart arms:

```bash
CUDA_VISIBLE_DEVICES=7 \
NO_PROXY=localhost,127.0.0.1,::1 \
PYTHONPATH=/tmp/gui-reflection-runner-deps:. \
python -m web_agent_benchmark.evaluation.gui_reflection_baseline.run_targeted_recovery_pilot \
  --task-set smoke17 \
  --slug env008 \
  --output-root web_agent_benchmark/evaluation/gui_reflection_baseline/runs/targeted_env008 \
  --official-repo /mnt/data/lys/gui_reflection_assets/GUI_Reflection \
  --model-path /mnt/data/lys/gui_reflection_assets/GUI_Reflection_8b_SFT \
  --agent-python /tmp/gui-reflection-model-env/bin/python \
  --browser-backend selenium-firefox
```

Each cell retains all model calls in `steps.jsonl` and only normalized,
server-backed structural events in `events.jsonl`. Service receipts bind the
current PNG, ordered native-4 image history, exact action history, goal,
viewport, memory state, and deterministic generation settings. A separate
canonical scorer consumes the raw submitted token/position. Parser mismatch,
containment failure, receipt incompatibility, or asymmetric workflow start
screens make the pilot exit nonzero instead of becoming a behavioral result.

`targeted_recovery.py` provides the canonical registry binding, event reducer, quartet validator, ladder validator, and qualitative analysis helpers. `analyze_run(..., registry=...)` replays one raw trace and `compare_runs(...)` replays one arm pair; both remain `reportable=false`. `analyze_recovery_quartet(...)` requires exactly candidate/reference × official/clean raw traces plus a direction-sensitive preregistered `contrast_id`, but currently returns only `protocol_complete=true`, never an experiment-reportable result. It rejects missing/duplicate cells, swapped condition roles, reused run/submission/scorer/F3-validator ids, replayed capture/model-step/model-response/execution receipts, and asymmetric task/chart/token-layout/render/model provenance. Its `publication_blockers` are conservative schema-level defaults rather than a per-run implementation inventory. The env008 pilot actually uses the canonical loader, compact browser collector, action receipts, and native-4 model-input binding; the independent run review records that distinction. Immutable external capture storage remains absent, and F3/reflection-training contrasts still require their validator-store/matched-training artifacts.

`validate_case_ladder(...)` replays each level's raw quartet, rejects cross-level identity reuse, and exposes a structural `protocol_complete_autonomous_prefix` for `F0→F1→F2`; its `reportable_autonomous_prefix` stays empty and F3 remains a non-reportable outcome probe. A workflow-on/off quartet is valid as its own contrast, but it is explicitly excluded from the evidence ladder because the single-attempt reference has no review evidence.

Formal role, display order, checkpoint lineage, and approval provenance are not accepted as caller assertions. A `TargetedRecoveryRegistry` resolves roles from canonical case manifests, checkpoint/history/workflow from preregistered conditions, F2 source/reviewer/date from a case-scoped approved evidence record, and any reflection-training contrast from an approved recipe record. The natural F0 pilot now reloads canonical task pointers itself; approved F2 records and a general multi-case formal registry remain pending. In-memory records in tests are not experimental evidence.

A hand-filled `event_trace_reduced` flag is not trusted. Registry binding fixes each arm's task instance/chart and the visible-token→canonical-action map. Every initial/retry selection records the actual token/position, the acknowledged decision PNG, task/chart/UI/render profile, model step, response, and execution receipt; retry inputs also bind the prior provisional choice and the exact current-visible F2/F3 record. Review screenshots bind the provisional control and evidence record. F3 requires a unique validator record for each provisional choice. PNG chunks, CRC, inflated scanlines, filters, and viewport dimensions are checked. Reversal/submission receipts must join the latest model input; single-attempt selection→submission is atomic. Hidden success still comes only from a separate same-submission `source=scorer` event.

The schema alone does not authenticate a runner/validator or prove that a declared payload appears in the PNG/HTML. For the implemented natural F0 pilot, `source=runner/scorer` is written from real rendering, exact model receipts, POST/URL/server-state readback, and an independent canonical hidden scorer. Natural F2 and a formal external F3 validator store remain pending; the inherited-error pilot below instead uses a run-local validator that independently reloads canonical truth. The first real env008 quartet is stored under `runs/targeted_env008/20260830T121341Z_7e5db661`; it is a qualitative, non-reportable pilot rather than a population estimate.

The follow-up inherited-error probes are stored under
`runs/targeted_env008_inherited_f0/20260830T172120Z_9fcc9516` and
`runs/targeted_env008_inherited_f3/20260830T172355Z_8dc091a5`. In every cell,
the evaluator first created a Wind provisional selection through a real
Firefox click and then reset the model before handoff. All eight cells made an
effective Back transition. The four native-4 cells then selected Wind again
and stopped at final review without Confirm; the four true current-only cells
made no new choice and timed out on the retry page. F3 exposed a sanitized
independent contradiction on review, retry, and final review, but produced no
Solar switch. Across both probes there were 44 model steps, 36 resets, zero
submissions, and no model-service HTTP error. These are controlled recovery-
capacity probes, not natural-error rates or a matched reflection-training
contrast. The per-trajectory interpretation is in
`ENV008_INHERITED_RECOVERY_ANALYSIS.md`; its independent adversarial audit is
in `ENV008_INHERITED_RED_TEAM_REVIEW.md`; the staged 9-case expansion is in
`TARGETED_RECOVERY_PANEL_PLAN.md`.

Every comparison declares one contrast axis. Workflow contrasts hold checkpoint/training/history fixed; history contrasts hold checkpoint/training/workflow fixed; replication holds all four fixed. A `reflection_training` contrast additionally requires the same checkpoint stage/history/workflow and one shared reviewed recipe record, but the present schema does not yet prove matched initialization, architecture, ordinary GUI data mixture, steps/tokens/compute, or versioned recipe artifact; that axis therefore carries its own publication blocker. No public SFT `R−` is currently available. Cross-stage or multi-factor comparisons are only `descriptive_system`. A reset or `temporal_len=0` condition must not be labeled as a no-reflection model.

The generated JSONL is a runner/server manifest, not a model input. The implemented natural-F0 decision renderer calls `model_visible_projection(case, arm)` and refuses chart/projection swaps; it never receives the combined case object. Its real HTTP test checks that hidden scorer/action-role fields do not appear in served HTML, and the browser collector enforces an exact path policy. A future F2 review renderer must call `model_visible_review_projection(...)`, which resolves only the structured visible payload from an approved registry record and omits record/source/reviewer metadata. `runner_only` and `source_references` must remain server-side and outside page source, URLs, screenshots, debug output, and prompts. The inherited F3 renderer has tests for review/retry/final-review visibility and canonical layout binding plus screenshot-level red-team inspection; formal F2 leakage tests remain pending.

## Tests

Tests require only the standard library and do not load a model or browser:

```bash
python -m unittest discover \
  -s web_agent_benchmark/evaluation/gui_reflection_baseline/tests \
  -t . \
  -v
```
