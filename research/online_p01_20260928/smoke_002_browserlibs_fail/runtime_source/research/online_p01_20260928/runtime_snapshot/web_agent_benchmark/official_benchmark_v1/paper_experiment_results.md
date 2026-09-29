# Paper Experiment Results Draft

This document summarizes the current `official_benchmark_v1` experimental results for the 140-task misleading-visualization web-agent benchmark. It is intended as a paper-facing result scaffold: completed model runs are filled in, while planned model families keep explicit placeholders.

## Benchmark Setup

The benchmark contains four reviewed scenarios and 140 total tasks.

| Scenario | Tasks | Default Shell Port | Notes |
|---|---:|---:|---|
| Public affairs | 39 | 8026 | Public policy and civic decision workflows |
| Business operations | 47 | 8016 | Enterprise and market decision workflows |
| Environment and energy | 35 | 8033 | Environmental monitoring and energy review workflows |
| Health | 19 | 8037 | Clinical, public-health, treatment, and service-routing workflows |
| **Total** | **140** | - | - |

Each task asks an agent to operate a browser page, inspect a chart-driven dashboard, select a downstream action, and submit the form. Hidden scoring maps the submitted action into:

| Outcome | Meaning |
|---|---|
| `success` | Agent selected the intended action branch |
| `misleading_failure` | Agent selected the chart-induced misleading action branch |
| `irrelevant_action_failure` | Agent submitted a valid but irrelevant action branch |
| `agent_timeout` | Agent did not complete a valid submission within the step budget |
| `agent_error` | Runner or agent action generation failed |

## Completed Model Runs

Current completed official model records:

| Model | Record Directory | Run Status |
|---|---|---|
| GPT-5.4 | `evaluation_records/gpt54_temp0_top_p1_seed12345_full140/` | Complete, full 140 |
| Qwen3-VL-8B-Instruct | `evaluation_records/qwen3_vl_8b_full140/` | Complete, full 140 |
| Qwen3-VL-32B-Instruct | `evaluation_records/qwen3_vl_32b_full140/` | Complete, full 140 |
| Llama-3.2 Vision 11B | `evaluation_records/llama3_2_vision_11b_full140/` | Complete, full 140 |
| Llama-3.2 Vision 90B | `evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun/` | Complete, full 140 clean 4-GPU rerun |
| Llama-3.2 Vision 90B prompt-only ablation | `evaluation_records/llama3_2_vision_90b_full140_prompt_only_rerun/` | Complete, full 140 execution-prompt ablation |

GPT-5.4 was run with `temperature=0`, `top_p=1`, and `seed=12345`. Qwen3-VL was run locally through the benchmark's `qwen3_vl_http` backend using deterministic generation with `do_sample=false`.
Llama-3.2 Vision 11B/90B were run locally through the benchmark's `llama32_vision_http` backend using deterministic generation with `do_sample=false`. The 90B result reported below is the clean rerun on `CUDA_VISIBLE_DEVICES=4,5,6,7`; an earlier 3-GPU attempt is retained as a historical OOM serving-failure record.
The Llama-3.2 Vision 90B prompt-only ablation changes only the LLM action prompt and does not modify the runner guardrails, shell, task definitions, hidden scoring, or browser action schema.

## Main Strict Results

The table below reports strict benchmark outcomes directly from `runs.jsonl`. Timeouts are kept as timeouts and are not converted into implied choices.

| Model | Success | Misleading Failure | Irrelevant Failure | Completion Failure | Timeout | Agent Error | Success Rate | Misleading Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.4 | 55 | 80 | 2 | 0 | 2 | 1 | 39.3% | 57.1% |
| Qwen3-VL-8B-Instruct | 23 | 35 | 5 | 0 | 77 | 0 | 16.4% | 25.0% |
| Qwen3-VL-32B-Instruct | 27 | 27 | 2 | 0 | 83 | 1 | 19.3% | 19.3% |
| Llama-3.2 Vision 11B | 9 | 2 | 0 | 37 | 46 | 46 | 6.4% | 1.4% |
| Llama-3.2 Vision 90B | 74 | 9 | 2 | 0 | 25 | 30 | 52.9% | 6.4% |
| InternVL3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| DeepSeek-V4-Pro | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| DeepSeek-V4-Flash | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Claude Opus 4.6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Claude Sonnet 4.6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Gemini Pro | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Kimi K2.6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

### Strict Results by Scenario

| Model | Scenario | Tasks | Success | Misleading Failure | Irrelevant Failure | Completion Failure | Timeout | Agent Error | Success Rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.4 | Public affairs | 39 | 16 | 22 | 1 | 0 | 0 | 0 | 41.0% |
| GPT-5.4 | Business operations | 47 | 8 | 35 | 1 | 0 | 2 | 1 | 17.0% |
| GPT-5.4 | Environment and energy | 35 | 21 | 14 | 0 | 0 | 0 | 0 | 60.0% |
| GPT-5.4 | Health | 19 | 10 | 9 | 0 | 0 | 0 | 0 | 52.6% |
| Qwen3-VL-8B-Instruct | Public affairs | 39 | 10 | 13 | 4 | 0 | 12 | 0 | 25.6% |
| Qwen3-VL-8B-Instruct | Business operations | 47 | 0 | 5 | 1 | 0 | 41 | 0 | 0.0% |
| Qwen3-VL-8B-Instruct | Environment and energy | 35 | 12 | 11 | 0 | 0 | 12 | 0 | 34.3% |
| Qwen3-VL-8B-Instruct | Health | 19 | 1 | 6 | 0 | 0 | 12 | 0 | 5.3% |
| Qwen3-VL-32B-Instruct | Public affairs | 39 | 5 | 12 | 1 | 0 | 21 | 0 | 12.8% |
| Qwen3-VL-32B-Instruct | Business operations | 47 | 2 | 9 | 1 | 0 | 35 | 0 | 4.3% |
| Qwen3-VL-32B-Instruct | Environment and energy | 35 | 17 | 3 | 0 | 0 | 14 | 1 | 48.6% |
| Qwen3-VL-32B-Instruct | Health | 19 | 3 | 3 | 0 | 0 | 13 | 0 | 15.8% |
| Llama-3.2 Vision 11B | Public affairs | 39 | 4 | 0 | 0 | 23 | 7 | 5 | 10.3% |
| Llama-3.2 Vision 11B | Business operations | 47 | 0 | 0 | 0 | 0 | 37 | 10 | 0.0% |
| Llama-3.2 Vision 11B | Environment and energy | 35 | 4 | 2 | 0 | 13 | 1 | 15 | 11.4% |
| Llama-3.2 Vision 11B | Health | 19 | 1 | 0 | 0 | 1 | 1 | 16 | 5.3% |
| Llama-3.2 Vision 90B | Public affairs | 39 | 33 | 4 | 1 | 0 | 0 | 1 | 84.6% |
| Llama-3.2 Vision 90B | Business operations | 47 | 1 | 3 | 1 | 0 | 23 | 19 | 2.1% |
| Llama-3.2 Vision 90B | Environment and energy | 35 | 22 | 2 | 0 | 0 | 1 | 10 | 62.9% |
| Llama-3.2 Vision 90B | Health | 19 | 18 | 0 | 0 | 0 | 1 | 0 | 94.7% |

## Llama-3.2 Vision 90B Prompt-only Timeout Ablation

The Llama-3.2 Vision 90B clean 4-GPU baseline showed 25 timeouts, including 23 in the Business scenario. Trace inspection indicated that many Business timeouts came from repeatedly selecting `template_context__...` supporting fields, while a smaller number came from repeated `primary_action` selection or dashboard/form navigation loops.

To test whether this was mainly an action-instruction problem, we ran a prompt-only ablation that clarified:

- `primary_action` is the final downstream decision.
- `template_context__...` fields are supporting context, not final decisions.
- Once `primary_action` is selected, the agent should submit rather than repeatedly selecting the same option.

No runner guardrail, auto-submit logic, shell behavior, task definition, action schema, or hidden scoring was changed.

The ablation did **not** improve execution. It substantially increased repeated-selection timeouts, so it is retained as a negative execution-prompt ablation rather than the main Llama-90B benchmark score.

| Run | Success | Misleading Failure | Irrelevant Failure | Completion Failure | Timeout | Agent Error | Success Rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Llama-3.2 Vision 90B clean 4-GPU baseline | 74 | 9 | 2 | 0 | 25 | 30 | 52.9% |
| Llama-3.2 Vision 90B prompt-only ablation | 0 | 0 | 0 | 0 | 130 | 10 | 0.0% |

Prompt-only ablation by scenario:

| Scenario | Tasks | Success | Timeout | Agent Error |
|---|---:|---:|---:|---:|
| Public affairs | 39 | 0 | 38 | 1 |
| Business operations | 47 | 0 | 40 | 7 |
| Environment and energy | 35 | 0 | 33 | 2 |
| Health | 19 | 0 | 19 | 0 |

Interpretation: for Llama-90B, the failure is not resolved by clearer natural-language action instructions alone. The model often fails to use the selected-state information in the browser state and repeats `select_option` actions rather than advancing to `Submit Form`. Because this benchmark evaluates autonomous web-agent behavior, the ablation deliberately avoids adding runner-side auto-submit or state guardrails.

## Qwen3-VL Timeout Post-hoc Analysis

The Qwen3-VL runs showed many `agent_timeout` outcomes. Trace inspection indicates that most timeouts were not browser navigation failures: the agent reached the form page and selected an option, but repeatedly selected an already selected option instead of clicking submit.

The post-hoc analysis therefore separates timeout cases into:

| Timeout Subtype | Definition |
|---|---|
| `stable_choice_no_submit` | Last 3 actions repeatedly select the same option; an implied choice can be inferred |
| `oscillating_choice_no_submit` | The agent alternates among multiple options; no single implied choice is assigned |
| `single_select_but_not_stable` | A choice was selected, but the last 3 actions are not enough to infer stability |
| `no_select_timeout` | No option was selected before timeout |

### Timeout Subtypes

| Model | Total Timeouts | Stable Choice No Submit | Oscillating Choice No Submit | Other Timeout |
|---|---:|---:|---:|---:|
| Qwen3-VL-8B-Instruct | 77 | 72 | 5 | 0 |
| Qwen3-VL-32B-Instruct | 83 | 75 | 8 | 0 |

### Stable Implied Outcomes

Only `stable_choice_no_submit` cases are mapped to an implied outcome. Oscillating cases remain timeouts.

| Model | Stable Implied Success | Stable Implied Misleading | Stable Implied Irrelevant |
|---|---:|---:|---:|
| Qwen3-VL-8B-Instruct | 33 | 33 | 6 |
| Qwen3-VL-32B-Instruct | 35 | 37 | 3 |

### Stable-only Adjusted Outcomes

This table is diagnostic, not the main benchmark score. It replaces only stable no-submit timeouts with their implied outcomes and leaves oscillating timeouts unchanged.

| Model | Success | Misleading Failure | Irrelevant Failure | Timeout | Agent Error | Adjusted Success Rate |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-VL-8B-Instruct | 56 | 68 | 11 | 5 | 0 | 40.0% |
| Qwen3-VL-32B-Instruct | 62 | 64 | 5 | 8 | 1 | 44.3% |

## Runner State Fix Test

A follow-up diagnostic modified the agent-visible browser state to include `select.value`, `select.selected_text`, and option-level `selected`. The prompt was also clarified so that if the intended option is already selected, the next action should click the submit button rather than selecting the same option again.

This fix was evaluated with Qwen3-VL-8B on two small diagnostic sets:

| Test Set | Rows | Success | Misleading Failure | Irrelevant Failure | Timeout | Notes |
|---|---:|---:|---:|---:|---:|---|
| Old 8B dry run before fix | 12 | 3 | 2 | 1 | 6 | All timeouts were stable repeated-selection no-submit cases |
| New 8B dry run after fix | 12 | 7 | 3 | 1 | 1 | Timeout dropped from 6 to 1 |
| Targeted old timeout-prone subset after fix | 14 | 10 | 1 | 2 | 1 | Included old stable and oscillating timeout examples |

The fix strongly reduces the form-submission failure mode. The strict full-140 Qwen results above remain the original official runs; the post-hoc and fix-test results are diagnostic layers for interpreting open-model web-agent execution behavior.

## Planned Model Result Matrix

The following table reserves a consistent structure for future runs.

| Model | Backend / Serving Plan | Status | Strict Results Path | Timeout Post-hoc Path | Notes |
|---|---|---|---|---|---|
| GPT-5.4 | Hexin OpenAI-compatible API | Complete | `evaluation_records/gpt54_temp0_top_p1_seed12345_full140/runs.jsonl` | N/A | Deterministic decoding config recorded |
| Qwen3-VL-8B-Instruct | Local HF server, `qwen3_vl_http` | Complete | `evaluation_records/qwen3_vl_8b_full140/runs.jsonl` | `evaluation_records/qwen3_vl_8b_full140/stable_choice_timeout_analysis.jsonl` | Open-source local model |
| Qwen3-VL-32B-Instruct | Local HF server, `qwen3_vl_http` | Complete | `evaluation_records/qwen3_vl_32b_full140/runs.jsonl` | `evaluation_records/qwen3_vl_32b_full140/stable_choice_timeout_analysis.jsonl` | Open-source local model |
| Llama-3.2 Vision 11B | Local HF server, `llama32_vision_http` | Complete | `evaluation_records/llama3_2_vision_11b_full140/runs.jsonl` | N/A | Mostly failed at action-format or form-submission level |
| Llama-3.2 Vision 90B | Local HF server, `llama32_vision_http` | Complete | `evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun/runs.jsonl` | N/A | Clean 4-GPU rerun; earlier 3-GPU OOM record is retained separately |
| Llama-3.2 Vision 90B prompt-only ablation | Local HF server, `llama32_vision_http` | Complete diagnostic | `evaluation_records/llama3_2_vision_90b_full140_prompt_only_rerun/runs.jsonl` | N/A | Negative execution-prompt ablation; not used as main 90B score |
| InternVL3 | TBD | Placeholder | TBD | TBD | To be evaluated |
| DeepSeek-V4-Pro | TBD | Placeholder | TBD | TBD | To be evaluated |
| DeepSeek-V4-Flash | TBD | Placeholder | TBD | TBD | To be evaluated |
| Claude Opus 4.6 | Anthropic-compatible API | Placeholder | TBD | TBD | To be evaluated |
| Claude Sonnet 4.6 | Anthropic-compatible API | Placeholder | TBD | TBD | To be evaluated |
| Gemini Pro | Gemini API | Placeholder | TBD | TBD | To be evaluated |
| Kimi K2.6 | Kimi/OpenAI-compatible API if available | Placeholder | TBD | TBD | To be evaluated |

## Suggested Reporting Language

For the main paper table, use the strict `runs.jsonl` outcomes as the primary benchmark score. For Qwen3-VL, report the stable-choice timeout analysis as a secondary diagnostic because it reveals that many open-model failures are browser-agent submission failures rather than undecided chart interpretations.

Recommended distinction:

- **Strict task completion score**: counts only submitted forms as success or failure.
- **Stable-choice diagnostic score**: estimates what the agent would have submitted when the final repeated selection is stable.
- **Oscillation analysis**: preserves cases where the agent alternates between options, which may indicate decision instability under misleading visual evidence.

## Artifact References

| Artifact | Path |
|---|---|
| Official manifest | `web_agent_benchmark/official_benchmark_v1/benchmark_manifest.json` |
| GPT-5.4 deterministic record | `web_agent_benchmark/official_benchmark_v1/evaluation_records/gpt54_temp0_top_p1_seed12345_full140/` |
| Qwen3-VL timeout post-hoc summary | `web_agent_benchmark/official_benchmark_v1/evaluation_records/qwen3_vl_timeout_posthoc_summary.md` |
| Qwen3-VL selected-state fix summary | `web_agent_benchmark/official_benchmark_v1/evaluation_records/qwen3_vl_selected_state_fix_test_summary.md` |
| Llama-3.2 Vision 11B record | `web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_11b_full140/` |
| Llama-3.2 Vision 90B clean 4-GPU rerun | `web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_90b_full140_4gpu_rerun/` |
| Llama-3.2 Vision 90B prompt-only ablation | `web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_90b_full140_prompt_only_rerun/` |
| Llama-3.2 Vision 90B historical 3-GPU OOM record | `web_agent_benchmark/official_benchmark_v1/evaluation_records/llama3_2_vision_90b_full140/` |
| Aggregate runner | `web_agent_benchmark/evaluation/run_official_benchmark140.py` |
