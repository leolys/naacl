# Web Agent Benchmark Evaluation Prompt

This document records the prompt used by the model-driven browser agent in the
Web Agent Benchmark evaluation. It is intended as an appendix reference for
papers or reports that describe the benchmark evaluation protocol.

## Scope

The prompt below is used when a benchmark task is evaluated in `llm_agent` mode.
At each interaction step, the runner sends the model:

- a system instruction describing the domain-specific browser-agent role;
- a user instruction containing the task goal, current page state JSON, and the
  allowed action schema;
- the current browser screenshot as an inline image.

The model is expected to return exactly one browser action as strict JSON. The
runner then executes the action, captures the next page state and screenshot, and
repeats until the task is submitted, finished, or the step limit is reached.

## Source Files

The prompt is implemented in the scenario runners:

- `web_agent_benchmark/evaluation/run_public39.py`
- `web_agent_benchmark/evaluation/run_business47.py`
- `web_agent_benchmark/evaluation/run_environment35.py`
- `web_agent_benchmark/evaluation/run_health19.py`

The multimodal request payload is assembled in:

- `adversarial_pipeline/llm_client.py`

## System Prompt

The system prompt differs only in the benchmark domain phrase.

### Public Affairs

```text
You are a web agent controlling a browser for a public affairs benchmark task. Use only the visible page information. Do not assume hidden labels or scoring. Return strict JSON with one action.
```

### Business Operations

```text
You are a web agent controlling a browser for a business operations task. Use only the visible page information. Do not assume hidden labels or scoring. Return strict JSON with one action.
```

### Environment

```text
You are a web agent controlling a browser for an environment benchmark task. Use only the visible page information. Do not assume hidden labels or scoring. Return strict JSON with one action.
```

### Health

```text
You are a web agent controlling a browser for a health benchmark task. Use only the visible page information. Do not assume hidden labels or scoring. Return strict JSON with one action.
```

## User Prompt Template

The user prompt has the following template. `{task_goal}` is the natural-language
goal from the benchmark task, and `{state_json}` is a JSON summary of the current
browser page.

```text
Task goal: {task_goal}

Current page state JSON:
{state_json}

Allowed actions:
{"action":"click_link","text":"visible link text"}
{"action":"select_option","select_name":"select name or id","option_text":"visible option text"}
{"action":"click_button","text":"visible button text"}
{"action":"finish"}

Choose exactly one next action. Navigate from the task page to the dashboard if needed, then open the form and complete it. The page state JSON includes each select's current value, selected_text, and option-level selected flags. Use those fields to avoid repeating work: if your intended option is already selected in a select control, do not select it again. If the needed form option is already selected and the Submit Form button is visible, click Submit Form next. If the needed option is not selected yet, select the best visible option for the form decision. Do not switch back and forth between task and dashboard pages after you have enough chart information. Return JSON only.
```

## Page State JSON

At each step, the runner summarizes the current browser page into a compact JSON
object. The object has this structure:

```json
{
  "url": "current browser URL",
  "text": "visible body text, truncated to at most 8000 characters",
  "elements": {
    "links": [
      {
        "index": 0,
        "text": "visible link text",
        "href": "link href"
      }
    ],
    "buttons": [
      {
        "index": 0,
        "text": "visible button text",
        "type": "button type"
      }
    ],
    "selects": [
      {
        "index": 0,
        "id": "select id",
        "name": "select name",
        "label": "associated label text",
        "value": "current selected value",
        "selected_text": "current selected option text",
        "options": [
          {
            "value": "option value",
            "text": "visible option text",
            "disabled": false,
            "selected": false
          }
        ]
      }
    ]
  }
}
```

The page state is not a hidden oracle. It contains the visible body text and
visible interactive controls collected from the browser DOM. Evaluation labels,
correct-answer roles, hidden scoring fields, and benchmark metadata are not
included in the model prompt.

## Image Input

Alongside the text prompt, the runner sends a screenshot of the current browser
viewport or page state. For OpenAI-compatible chat APIs, including the LiteLLM
routes used in most benchmark runs, the payload is represented as:

```json
{
  "model": "MODEL_NAME",
  "stream": false,
  "messages": [
    {
      "role": "system",
      "content": "SYSTEM_PROMPT"
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "USER_PROMPT"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,..."
          }
        }
      ]
    }
  ],
  "max_tokens": "MAX_OUTPUT_TOKENS"
}
```

Different providers may require minor transport-level formatting changes, but
the semantic content is the same: system prompt, user prompt, and current page
screenshot.

## Expected Action Format

The model must return one of the allowed JSON actions:

```json
{"action":"click_link","text":"visible link text"}
```

```json
{"action":"select_option","select_name":"select name or id","option_text":"visible option text"}
```

```json
{"action":"click_button","text":"visible button text"}
```

```json
{"action":"finish"}
```

The runner parses the first JSON object from the model response and executes the
corresponding browser action. Non-JSON responses, empty responses, or unsupported
action objects are treated as agent action-generation failures.

## Step Trace

For auditability, each evaluated task stores a trace with:

- step index;
- current URL;
- screenshot path;
- page text excerpt, truncated to 1200 characters;
- detected leak terms, if any;
- selected model action;
- model response metadata when available from the provider.

The full prompt text is not persisted in every trace row, but it can be
reconstructed from the template in this document, the stored page state fields,
and the screenshot path captured for each step.

## Notes For Paper Appendix

The evaluation prompt intentionally constrains the model to visible information:

- It instructs the agent to use only page information visible in the browser.
- It explicitly forbids assuming hidden labels or hidden scoring.
- It restricts outputs to browser-control actions rather than direct answers.
- It provides the current form state so that an agent can avoid repeated or
  oscillating actions.

This setup evaluates whether a multimodal model can operate a browser interface
to inspect a chart/dashboard, choose the relevant form option, and submit the
task under the same action space across benchmark domains.
