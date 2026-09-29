# CUGA Policy-System Rebuttal Experiment

This experiment compares the same CUGA 0.3.0 agent and underlying model under two conditions:

- `default`: CUGA policy storage is enabled but contains no chart-specific policy.
- `playbook`: CUGA loads `chart_verification_playbook.md` through its native policy storage and matching system.

The frozen mini-set contains 16 paired cases (32 task instances), with four cases from each scenario and 11 misleading-mechanism strata. Running both conditions produces 64 trajectories. Selection uses seed `20260710`; no model outcome from this CUGA experiment is used for selection.

The CUGA checkout is isolated under `external_tools/cuga-agent` and its experiment environment under `external_tools/cuga-agent/.venv-policy`. API credentials are read from the process environment and are never written to experiment records.

CUGA 0.3.0's policy hook is implemented in its CugaLite/Supervisor graphs, while its Playwright-capable legacy `web` graph does not call that hook. This adapter therefore invokes CUGA's public `PolicyEnactment.check_and_enact` API before entering the legacy web graph and passes the returned `playbook_guidance` in the task goal. This preserves the stock CUGA browser planner/action loop and the native CUGA policy storage, trigger matching, action creation, and enactment semantics. Every trajectory records the policy ID, confidence, reasoning, exact guidance, and guidance hash. The adapter contains no task labels, misleading-mechanism names, correct answers, or hidden evaluator fields.

The local checkout applies five deployment-only compatibility patches: knowledge/Docling imports in `cuga.__init__` are optional because this browser-policy experiment disables CUGA knowledge retrieval; the browser planner accepts a single `thoughts` string as a one-item list for GPT-5.4 compatibility; a duplicate `tool_provider` argument in CUGA 0.3.0's non-streaming controller call is removed; the action event processor explicitly invokes CUGA's selected browser-tool provider because the installed LangChain version does not inject `RunnableConfig` into the decorated tool call; and the QA agent accepts its documented `thoughts/name/answer` field format when strict JSON parsing fails. No policy, browser action, answer content, or decision content is changed.

The playbook uses a deterministic keyword trigger (`benchmark`). Its SQLite storage uses a fixed placeholder vector because no natural-language/semantic trigger is evaluated; matching and enactment still use CUGA's native policy runtime.

The local CUGA registry is started with `empty_mcp_servers.yaml`. It is required by CUGA's planner bookkeeping, but no API/MCP tools are exposed to the browser agent.

Each task shell is started on a newly allocated localhost port and writes to its condition-specific submission file. This prevents interrupted or stale shell processes from mixing default and playbook submissions.

The full runner executes all four cells of a paired case contiguously. Condition and split order are reversed on odd case indices to reduce time-order confounding. Per-step screenshots are decoded to PNG files and referenced by path and SHA-256 in JSONL rather than embedding large base64 payloads.

Smoke test:

```bash
external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/run_cuga_policy_system_miniset.py \
  --conditions default,playbook \
  --benchmarks official,clean \
  --limit 1 \
  --output-root web_agent_benchmark/pair_evaluation_records/cuga_policy_system_smoke_20260710
```

Full run:

```bash
external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/run_cuga_policy_system_miniset.py
```

The runner checkpoints after every task. Re-running the same command skips completed rows and retries `agent_error` rows.

CUGA's native `55`-step budget counts internal graph nodes (analysis, decomposition, planning, and action), not only browser actions. Reports therefore use `cuga_action_count` for behavioral-efficiency comparisons.

## Full140 Extension

The frozen full-set manifest is `full140.jsonl`. It contains every paired synthetic case in canonical scenario/task order: 39 public, 47 business, 35 environment, and 19 health cases. Running both conditions on both splits produces 560 trajectories. The stopping rule is fixed in advance: run all 140 cases and do not stop based on the observed policy effect.

Regenerate and validate the manifest from the paired benchmark files:

```bash
python web_agent_benchmark/evaluation/cuga_policy_system/build_full140_manifest.py
```

Prepare a full-set directory by importing the verified 64 mini-set trajectories without making model requests:

```bash
external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/run_cuga_policy_system_miniset.py \
  --manifest web_agent_benchmark/evaluation/cuga_policy_system/full140.jsonl \
  --seed-runs-from web_agent_benchmark/pair_evaluation_records/cuga_policy_system_miniset_16paired_20260710/runs.jsonl \
  --output-root web_agent_benchmark/pair_evaluation_records/cuga_policy_system_full140_gpt54_20260711 \
  --prepare-only
```

Remove `--prepare-only` to run only the 496 missing condition/split cells. The same command is interruption-safe: destination rows take precedence over seed rows, completed results are skipped, and `agent_error` rows are retried.

For unattended execution, use the supervisor. It performs at most five fixed passes, resuming missing rows and retrying only `agent_error` rows. Once all 560 unique rows are present with no agent errors, it automatically generates the case-transition and rebuttal reports:

```bash
external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/run_cuga_policy_system_full140_supervisor.py
```

## Completed Run

The verified 16-pair run is stored at:

`web_agent_benchmark/pair_evaluation_records/cuga_policy_system_miniset_16paired_20260710`

It contains 64 unique trajectories, 64 evaluator submissions, 0 `agent_error` rows, 32/32 intended Playbook matches, and 0/32 policy matches in the default condition. Key generated reports are:

- `summary.md`: aggregate split and paired metrics.
- `case_transitions.md` / `case_transitions.jsonl`: case-level recovery and regression transitions.
- `rebuttal_summary.md`: Reviewer 4H6i-facing protocol, results, case study, interpretation, and suggested response text.

Regenerate the analysis with:

```bash
external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/analyze_cuga_policy_system_miniset.py
```

## Playbook v2 + PreSubmitGuard

The v2 experiment is implemented separately and does not modify the v1 runner or
the vendored CUGA source. Its frozen policy is
`chart_verification_playbook_v2.md`; the runner refuses to start unless its
SHA-256 is
`06012867be220f82e344b09fd38a4cf2c044ce15103ac4cf5e6e4a6fbfe3d0ec`.

`run_cuga_policy_system_v2_guarded.py` uses CUGA's native
`match_policies_by_type` path so that the parsed `AlwaysTrigger` is enacted. The
generic CUGA `match_policy` implementation in this checkout only aggregates
keyword and natural-language matches and therefore does not select an
always-triggered Playbook.

The evaluation adapter injects `GuardedPlaywrightToolImplProvider`, which wraps
only the primary decision select and the submit button. The Guard sees the
current full-page screenshot, visible body text, visible primary options, and
CUGA's proposed option. It never receives task JSON or evaluator fields. It may
block once, never substitutes an answer, and fails open while marking the row as
a technical `guard_error` for supervisor retry.

The registry uses `48001`. Shell ports are intentionally below Linux's ephemeral
port range (`32768-60999`) so unrelated outbound connections cannot claim them:

- Official: business `30116`, public `30126`, environment `30133`, health `30137`.
- Clean: business `30216`, public `30226`, environment `30233`, health `30237`.

Run the fixed four-case smoke only after starting an empty CUGA registry on
`127.0.0.1:48001`:

```bash
external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/run_cuga_policy_system_v2_guarded.py \
  --manifest web_agent_benchmark/evaluation/cuga_policy_system/v2_smoke_4.jsonl \
  --output-root web_agent_benchmark/pair_evaluation_records/cuga_policy_system_v2_guarded_smoke_gpt54_20260711

external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/analyze_cuga_policy_system_v2_guarded.py \
  --root web_agent_benchmark/pair_evaluation_records/cuga_policy_system_v2_guarded_smoke_gpt54_20260711 \
  --expected-cases 4 \
  --strict-smoke
```

Start Full140 only when strict smoke validation passes. The supervisor resumes
missing rows and retries only `agent_error` or `guard_error` rows:

```bash
external_tools/cuga-agent/.venv-policy/bin/python \
  web_agent_benchmark/evaluation/run_cuga_policy_system_v2_guarded_supervisor.py
```

The v2 mechanism was designed after inspecting v1 aggregate and transition
results. Reports must describe it as a refined, post-hoc follow-up rather than an
independent confirmatory experiment.
