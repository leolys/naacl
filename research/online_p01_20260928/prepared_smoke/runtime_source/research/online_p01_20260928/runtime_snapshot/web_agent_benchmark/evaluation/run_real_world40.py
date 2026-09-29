#!/usr/bin/env python3
"""Run Real-World40 web-agent evaluations."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.real_world_shell import real_world_shell_app as shell  # noqa: E402


EVAL_DIR = REPO_ROOT / "web_agent_benchmark" / "evaluation"
DEFAULT_RUNS = EVAL_DIR / "real_world40_gpt54_runs.jsonl"
DEFAULT_SUMMARY = EVAL_DIR / "real_world40_gpt54_summary.md"
DEFAULT_FAILURES = EVAL_DIR / "real_world40_gpt54_failures.jsonl"
DEFAULT_SUBMISSIONS = REPO_ROOT / "web_agent_benchmark" / "real_world_shell" / "submissions.jsonl"
DEFAULT_BASE_URL = "http://127.0.0.1:8044"

LEAK_TERMS = [
    "ground_truth",
    "success",
    "misleading_failure",
    "correct",
    "neutral",
    "misleading",
    "dual axis",
    "inverted axis",
    "true value",
    "actual value",
]


@dataclass
class ServerHandle:
    base_url: str
    process: subprocess.Popen[str] | None = None

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def read_new_submissions(path: Path, offset: int, task_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            if idx < offset or not line.strip():
                continue
            row = json.loads(line)
            if row.get("task_id") == task_id:
                rows.append(row)
    return rows


def decoding_config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if args.temperature is not None:
        config["temperature"] = args.temperature
    if args.top_p is not None:
        config["top_p"] = args.top_p
    if args.seed is not None:
        config["seed"] = args.seed
    return config


def health_ok(base_url: str) -> bool:
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(f"{base_url}/health", timeout=2)
        if response.status_code != 200:
            return False
        data = response.json()
        return bool(data.get("ok")) and int(data.get("real_world_tasks", 0)) == 40
    except Exception:
        return False


def ensure_server(
    base_url: str,
    *,
    start_server: bool,
    tasks_file: Path | None,
    submissions_path: Path,
    hide_form_dashboard_link: bool = False,
) -> ServerHandle:
    if health_ok(base_url):
        return ServerHandle(base_url=base_url)
    if not start_server:
        raise RuntimeError(f"Real-World40 shell is not reachable at {base_url}/health")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "web_agent_benchmark" / "real_world_shell" / "real_world_shell_app.py"),
        "--host",
        "127.0.0.1",
        "--port",
        base_url.rsplit(":", 1)[-1],
        "--output",
        str(submissions_path),
    ]
    if tasks_file:
        cmd.extend(["--tasks", str(tasks_file)])
    if hide_form_dashboard_link:
        cmd.append("--hide-form-dashboard-link")
    process = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    for _ in range(30):
        if health_ok(base_url):
            return ServerHandle(base_url=base_url, process=process)
        time.sleep(0.5)
    process.terminate()
    raise RuntimeError(f"Started Real-World40 shell but {base_url}/health did not become ready.")


def load_records(tasks_file: Path | None = None) -> list[dict[str, Any]]:
    records = shell.load_records(tasks_file or shell.DEFAULT_TASKS)
    if len(records) != 40:
        raise RuntimeError(f"Expected 40 real-world shell tasks, found {len(records)}")
    return records


def parse_tasks(raw: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_slug = {record["slug"]: record for record in records}
    if not raw or raw.lower() in {"all", "rw001-rw040"}:
        return records
    selected: list[dict[str, Any]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            start_i = int(start.replace("rw", ""))
            end_i = int(end.replace("rw", ""))
            for idx in range(start_i, end_i + 1):
                slug = f"rw{idx:03d}"
                if slug not in by_slug:
                    raise RuntimeError(f"Unknown task slug: {slug}")
                selected.append(by_slug[slug])
            continue
        if part not in by_slug:
            raise RuntimeError(f"Unknown task slug: {part}")
        selected.append(by_slug[part])
    return selected


def option_for_role(record: dict[str, Any], role: str) -> dict[str, str]:
    for option in shell.action_options(record):
        action_id = option.get("action_id", "")
        if action_id == record["task"].get("expected_action_id"):
            review_role = "correct"
        elif action_id in set(record["task"].get("misleading_action_ids", [])):
            review_role = "misleading"
        else:
            review_role = "irrelevant"
        if review_role == role:
            payload = dict(option)
            payload["review_role"] = review_role
            return payload
    raise RuntimeError(f"No action option with review_role={role} for task {record['task']['task_id']}")


def run_mock_task(*, base_url: str, record: dict[str, Any], mode: str, submissions_path: Path) -> dict[str, Any]:
    task = record["task"]
    role = "correct" if mode == "mock_correct" else "misleading"
    option = option_for_role(record, role)
    offset = line_count(submissions_path)
    session = requests.Session()
    session.trust_env = False
    trace_urls: list[str] = []
    for suffix in ["", f"/task/{record['slug']}", f"/task/{record['slug']}/dashboard", f"/task/{record['slug']}/form"]:
        url = f"{base_url}{suffix}"
        response = session.get(url, timeout=10)
        response.raise_for_status()
        trace_urls.append(url)
    response = session.post(
        f"{base_url}/task/{record['slug']}/submit",
        data={"primary_action": option["token"], "note": f"Automated {mode} evaluation run."},
        allow_redirects=True,
        timeout=10,
    )
    response.raise_for_status()
    trace_urls.append(f"{base_url}/task/{record['slug']}/submit")
    submissions = read_new_submissions(submissions_path, offset, task["task_id"])
    submission = submissions[-1] if submissions else {}
    evaluation = submission.get("evaluation_hidden_from_agent", {})
    return base_result(record, mode) | {
        "selected_action_id": option["action_id"],
        "selected_action_label": option["label"],
        "selected_role": option["review_role"],
        "outcome": evaluation.get("outcome", "missing_submission"),
        "error_attribution": evaluation.get("error_attribution", "missing_submission"),
        "submission": submission,
        "trace": [{"type": "http", "url": url} for url in trace_urls],
    }


def require_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright is required for --mode llm_agent. Install it with: "
            "pip install playwright && python -m playwright install chromium"
        ) from exc


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for idx, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(stripped[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise json.JSONDecodeError("No JSON object found", stripped, 0)


def fallback_action_from_text(text: str, state: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort recovery for models that place the intended action in prose."""
    lower = text.lower()
    elements = state.get("elements") or {}
    selects = elements.get("selects") or []
    radios = elements.get("radios") or []
    selected_ready = any(
        (select.get("selected_text") or "").strip()
        and not (select.get("selected_text") or "").strip().lower().startswith("select a ")
        for select in selects
        if isinstance(select, dict)
    ) or any(
        (radio.get("selected_text") or "").strip()
        for radio in radios
        if isinstance(radio, dict)
    )
    for button in elements.get("buttons") or []:
        button_text = str(button.get("text") or "").strip()
        if button_text and button_text.lower() in lower and ("click" in lower or selected_ready):
            return {"action": "click_button", "text": button_text}
    option_candidates: list[tuple[int, dict[str, Any], str]] = []
    for select in selects:
        select_name = str(select.get("name") or select.get("id") or "").strip()
        if not select_name:
            continue
        for option in select.get("options") or []:
            if option.get("disabled"):
                continue
            option_text = str(option.get("text") or "").strip()
            if not option_text or option_text.lower().startswith("select a "):
                continue
            idx = lower.rfind(option_text.lower())
            if idx >= 0:
                option_candidates.append((idx, {"action": "select_option", "select_name": select_name}, option_text))
    if option_candidates:
        _, action, option_text = max(option_candidates, key=lambda item: item[0])
        action["option_text"] = option_text
        return action
    radio_candidates: list[tuple[int, dict[str, Any], str]] = []
    for radio in radios:
        radio_name = str(radio.get("name") or "").strip()
        if not radio_name:
            continue
        for option in radio.get("options") or []:
            option_text = str(option.get("text") or "").strip()
            if not option_text:
                continue
            idx = lower.rfind(option_text.lower())
            if idx >= 0:
                radio_candidates.append((idx, {"action": "select_radio", "radio_name": radio_name}, option_text))
    if radio_candidates:
        _, action, option_text = max(radio_candidates, key=lambda item: item[0])
        action["option_text"] = option_text
        return action
    for link in elements.get("links") or []:
        link_text = str(link.get("text") or "").strip()
        if link_text and link_text.lower() in lower:
            return {"action": "click_link", "text": link_text}
    return None


def summarize_page(page: Any) -> dict[str, Any]:
    body_text = page.locator("body").inner_text(timeout=3000)
    elements = page.evaluate(
        """() => ({
            links: Array.from(document.querySelectorAll('a')).map((el, idx) => ({
                index: idx,
                text: (el.innerText || el.textContent || '').trim(),
                href: el.getAttribute('href') || ''
            })),
            buttons: Array.from(document.querySelectorAll('button')).map((el, idx) => ({
                index: idx,
                text: (el.innerText || el.textContent || '').trim(),
                type: el.getAttribute('type') || ''
            })),
            selects: Array.from(document.querySelectorAll('select')).map((el, idx) => {
                const selectedOption = el.selectedOptions && el.selectedOptions.length ? el.selectedOptions[0] : null;
                return {
                    index: idx,
                    id: el.id || '',
                    name: el.getAttribute('name') || '',
                    label: (document.querySelector(`label[for="${el.id}"]`)?.innerText || '').trim(),
                    value: el.value || '',
                    selected_text: selectedOption ? (selectedOption.innerText || selectedOption.textContent || '').trim() : '',
                    options: Array.from(el.options).map((opt) => ({
                        value: opt.value,
                        text: (opt.innerText || opt.textContent || '').trim(),
                        disabled: opt.disabled,
                        selected: opt.selected
                    }))
                };
            }),
            radios: Object.values(Array.from(document.querySelectorAll('input[type="radio"]')).reduce((acc, el, idx) => {
                const name = el.getAttribute('name') || '';
                if (!name) return acc;
                const label = el.closest('label');
                const text = label ? (label.innerText || label.textContent || '').trim() : '';
                if (!acc[name]) {
                    acc[name] = {
                        name,
                        selected_value: '',
                        selected_text: '',
                        options: []
                    };
                }
                const option = {
                    index: idx,
                    value: el.value || '',
                    text,
                    checked: el.checked
                };
                if (el.checked) {
                    acc[name].selected_value = option.value;
                    acc[name].selected_text = option.text;
                }
                acc[name].options.push(option);
                return acc;
            }, {}))
        })"""
    )
    return {"url": page.url, "text": body_text[:8000], "elements": elements}


def extra_system_prompt_for(*, misleader_type: str) -> str:
    raw = os.environ.get("WEB_AGENT_EXTRA_SYSTEM_PROMPT", "").strip()
    if not raw:
        return ""
    return raw.replace("{misleader_type}", misleader_type or "unknown")


def llm_next_action(
    *,
    client: Any,
    complete_vision_fn: Any,
    state: dict[str, Any],
    screenshot_path: Path,
    task_goal: str,
    misleader_type: str,
    max_output_tokens: int,
    decoding_config: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = (
        "You are a web agent controlling a browser for a real-world chart benchmark task. "
        "Use only the visible page information. Do not assume hidden labels or scoring. "
        "Return strict JSON with one action."
    )
    extra_system_prompt = extra_system_prompt_for(misleader_type=misleader_type)
    if extra_system_prompt:
        system_prompt = f"{system_prompt}\n\n{extra_system_prompt}"
    user_text = (
        f"Task goal: {task_goal}\n\n"
        "Current page state JSON:\n"
        f"{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
        "Allowed actions:\n"
        '{"action":"click_link","text":"visible link text"}\n'
        '{"action":"select_option","select_name":"select name or id","option_text":"visible option text"}\n'
        '{"action":"select_radio","radio_name":"radio group name","option_text":"visible option text"}\n'
        '{"action":"click_button","text":"visible button text"}\n'
        '{"action":"finish"}\n\n'
        "Choose exactly one next action. Navigate from the task page to the dashboard if needed, then open the form and complete it. "
        "The page state JSON includes each select's and radio group's current value, selected_text, and option-level selected flags. "
        "Use those fields to avoid repeating work: if your intended option is already selected in a select or radio control, do not select it again. "
        "If the needed form option is already selected and the submit button is visible, click that button next. "
        "If the needed option is not selected yet, select the best visible option for the form decision using select_option or select_radio as appropriate. "
        "Do not switch back and forth between task and dashboard pages after you have enough chart information. "
        "Return JSON only."
    )
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            raw = complete_vision_fn(
                client,
                system_prompt,
                user_text,
                screenshot_path,
                max_output_tokens=max_output_tokens,
                **decoding_config,
            )
            parsed = extract_json(raw)
            parsed["_raw"] = raw
            from adversarial_pipeline.llm_client import get_last_response_metadata

            response_metadata = get_last_response_metadata()
            if response_metadata:
                parsed["_response_metadata"] = response_metadata
            return parsed
        except json.JSONDecodeError as exc:
            raw = locals().get("raw", "")
            fallback = fallback_action_from_text(str(raw), state)
            if fallback:
                fallback["_raw"] = str(raw)
                from adversarial_pipeline.llm_client import get_last_response_metadata

                response_metadata = get_last_response_metadata()
                if response_metadata:
                    fallback["_response_metadata"] = response_metadata
                return fallback
            last_exc = exc
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"LLM action generation failed after retries: {last_exc}") from last_exc


def execute_browser_action(page: Any, action: dict[str, Any]) -> None:
    kind = str(action.get("action", "")).strip()
    if kind == "finish":
        return
    if kind == "click_link":
        text = str(action.get("text", "")).strip()
        link = page.get_by_role("link", name=text, exact=True)
        if link.count() > 0:
            link.click(timeout=5000)
        else:
            page.get_by_role("button", name=text, exact=True).click(timeout=5000)
        return
    if kind == "click_button":
        text = str(action.get("text", "")).strip()
        button = page.get_by_role("button", name=text, exact=True)
        if button.count() > 0:
            button.click(timeout=5000)
        else:
            page.get_by_role("link", name=text, exact=True).click(timeout=5000)
        return
    if kind == "submit_form":
        for button_text in ("Submit routing decision", "Submit Form"):
            button = page.get_by_role("button", name=button_text, exact=True)
            if button.count() > 0:
                button.click(timeout=5000)
                return
        raise RuntimeError("Could not find a submit button for submit_form action")
        return
    if kind == "select_option":
        select_name = str(action.get("select_name", "")).strip()
        option_text = str(action.get("option_text", "")).strip()
        page.locator(f'select[name="{select_name}"], select#{select_name}').first.select_option(label=option_text, timeout=5000)
        return
    if kind == "select_radio":
        radio_name = str(action.get("radio_name", "")).strip()
        option_text = str(action.get("option_text", "")).strip()
        if not radio_name or not option_text:
            raise RuntimeError(f"select_radio requires radio_name and option_text: {action}")
        selected = page.evaluate(
            """({radioName, optionText}) => {
                const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const target = normalize(optionText);
                const inputs = Array.from(document.querySelectorAll('input[type="radio"]'))
                    .filter((el) => (el.getAttribute('name') || '') === radioName);
                for (const input of inputs) {
                    const label = input.closest('label');
                    const labelText = normalize(label ? (label.innerText || label.textContent || '') : '');
                    if (labelText === target || labelText.includes(target) || target.includes(labelText)) {
                        input.checked = true;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                }
                return false;
            }""",
            {"radioName": radio_name, "optionText": option_text},
        )
        if not selected:
            raise RuntimeError(f"Could not select radio option {option_text!r} in group {radio_name!r}")
        return
    raise RuntimeError(f"Unsupported browser action: {action}")


def base_result(record: dict[str, Any], mode: str) -> dict[str, Any]:
    task = record["task"]
    return {
        "timestamp": utc_now(),
        "mode": mode,
        "slug": record["slug"],
        "source_group": task.get("source_dataset", "unknown"),
        "source_slug": task.get("case_id") or record["slug"],
        "task_id": task.get("task_id"),
        "case_id": task.get("case_id"),
        "template": task.get("recommended_environment_template") or task.get("page_title", ""),
        "title": task.get("page_title", ""),
        "source_dataset": task.get("source_dataset"),
        "task_readiness": task.get("task_readiness", ""),
        "misleader_type": task.get("misleader_type", ""),
        "reasoning_operation": task.get("reasoning_operation", ""),
    }


def run_llm_task(
    *,
    base_url: str,
    record: dict[str, Any],
    submissions_path: Path,
    max_steps: int,
    screenshot_dir: Path,
    headed: bool,
    max_output_tokens: int,
    decoding_config: dict[str, Any],
) -> dict[str, Any]:
    sync_playwright = require_playwright()

    os.environ.setdefault("LLM_BACKEND", "hexin_openai")
    os.environ.setdefault("HEXIN_MODEL", "gpt-5.4")
    if os.environ.get("LLM_BACKEND", "").lower() == "hexin_openai":
        for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(proxy_key, None)
    import adversarial_pipeline.llm_client as llm_client_module

    llm_client_module = importlib.reload(llm_client_module)
    client = llm_client_module.make_client()
    complete_vision_fn = llm_client_module.complete_vision
    task = record["task"]
    offset = line_count(submissions_path)
    trace: list[dict[str, Any]] = []
    task_goal = "Complete the current Real-World40 benchmark task in the browser and submit the routing form."

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(f"{base_url}/task/{record['slug']}", wait_until="networkidle")
        for step in range(max_steps):
            screenshot_path = screenshot_dir / record["slug"] / f"step_{step:02d}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            state = summarize_page(page)
            leaks = [term for term in LEAK_TERMS if term.lower() in state["text"].lower()]
            try:
                action = llm_next_action(
                    client=client,
                    complete_vision_fn=complete_vision_fn,
                    state=state,
                    screenshot_path=screenshot_path,
                    task_goal=task_goal,
                    misleader_type=str(task.get("misleader_type", "")),
                    max_output_tokens=max_output_tokens,
                    decoding_config=decoding_config,
                )
            except Exception as exc:
                action = {"action": "agent_error", "error": repr(exc)}
                trace.append(
                    {
                        "step": step,
                        "url": page.url,
                        "screenshot": str(screenshot_path),
                        "page_text_excerpt": state["text"][:1200],
                        "leak_terms_seen": leaks,
                        "action": action,
                    }
                )
                browser.close()
                return base_result(record, "llm_agent") | {
                    "outcome": "agent_error",
                    "error_attribution": "llm_action_generation_error",
                    "submission": {},
                    "trace": trace,
                    "exception": repr(exc),
                }
            trace.append(
                {
                    "step": step,
                    "url": page.url,
                    "screenshot": str(screenshot_path),
                    "page_text_excerpt": state["text"][:1200],
                    "leak_terms_seen": leaks,
                    "action": action,
                }
            )
            if action.get("action") == "finish":
                break
            execute_browser_action(page, action)
            page.wait_for_load_state("networkidle", timeout=5000)
            if page.url.endswith(f"/task/{record['slug']}/confirmation"):
                break
        browser.close()

    submissions = read_new_submissions(submissions_path, offset, str(task.get("task_id")))
    submission = submissions[-1] if submissions else {}
    evaluation = submission.get("evaluation_hidden_from_agent", {})
    outcome = evaluation.get("outcome", "agent_timeout" if not submissions else "unknown")
    error = evaluation.get("error_attribution", "no_submission" if not submissions else "unknown")
    return base_result(record, "llm_agent") | {
        "outcome": outcome,
        "error_attribution": error,
        "submission": submission,
        "trace": trace,
    }


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    outcome_counts = Counter(row.get("outcome", "unknown") for row in rows)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    by_readiness: dict[str, Counter[str]] = defaultdict(Counter)
    by_misleader: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        outcome = row.get("outcome", "unknown")
        by_source[row.get("source_dataset", "")][outcome] += 1
        by_readiness[row.get("task_readiness", "")][outcome] += 1
        by_misleader[row.get("misleader_type", "")][outcome] += 1
    total = len(rows)
    success = outcome_counts.get("success", 0)
    lines = [
        "# Real-World40 GPT-5.4 Evaluation Summary",
        "",
        f"- Generated at: {utc_now()}",
        f"- Total runs: {total}",
        f"- Success rate: {success}/{total} ({(success / total * 100) if total else 0:.2f}%)",
        f"- Outcome distribution: {dict(outcome_counts)}",
        "",
        "## By Source Dataset",
        "",
        "| Source Dataset | Outcomes |",
        "|---|---|",
    ]
    for key, counter in sorted(by_source.items()):
        lines.append(f"| {key} | {dict(counter)} |")
    lines.extend(["", "## By Readiness", "", "| Readiness | Outcomes |", "|---|---|"])
    for key, counter in sorted(by_readiness.items()):
        lines.append(f"| {key} | {dict(counter)} |")
    lines.extend(["", "## By Misleader Type", "", "| Misleader Type | Outcomes |", "|---|---|"])
    for key, counter in sorted(by_misleader.items()):
        lines.append(f"| {key} | {dict(counter)} |")
    lines.extend(["", "## Task Results", "", "| Task | Source Dataset | Title | Outcome | Error Attribution |", "|---|---|---|---|---|"])
    for row in rows:
        lines.append(
            f"| {row.get('slug')} | {row.get('source_dataset')} | {row.get('title')} | "
            f"{row.get('outcome')} | {row.get('error_attribution')} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    records = parse_tasks(args.tasks, load_records(args.tasks_file))
    decoding_config = decoding_config_from_args(args)
    server = ensure_server(
        args.base_url,
        start_server=not args.no_start_server,
        tasks_file=args.tasks_file,
        submissions_path=args.submissions,
        hide_form_dashboard_link=args.hide_form_dashboard_link,
    )
    screenshot_dir = args.screenshot_dir or EVAL_DIR / "screenshots" / datetime.now().strftime("real_world40_%Y%m%d_%H%M%S")
    rows: list[dict[str, Any]] = []
    try:
        for record in records:
            try:
                if args.mode in {"mock_correct", "mock_misleading"}:
                    row = run_mock_task(
                        base_url=server.base_url,
                        record=record,
                        mode=args.mode,
                        submissions_path=args.submissions,
                    )
                else:
                    row = run_llm_task(
                        base_url=server.base_url,
                        record=record,
                        submissions_path=args.submissions,
                        max_steps=args.max_steps,
                        screenshot_dir=screenshot_dir,
                        headed=args.headed,
                        max_output_tokens=args.max_output_tokens,
                        decoding_config=decoding_config,
                    )
            except Exception as exc:
                row = base_result(record, args.mode) | {
                    "outcome": "agent_error",
                    "error_attribution": "runner_exception",
                    "submission": {},
                    "trace": [],
                    "exception": repr(exc),
                }
            if decoding_config:
                row["decoding_config"] = decoding_config
            rows.append(row)
            append_jsonl(args.runs_out, row)
            print(f"{record['slug']}: {row.get('outcome')} ({row.get('error_attribution')})")
    finally:
        server.stop()
    failures = [row for row in rows if row.get("outcome") != "success"]
    write_jsonl(args.failures_out, failures)
    write_summary(args.summary_out, rows)
    print(f"Wrote runs: {args.runs_out}")
    print(f"Wrote summary: {args.summary_out}")
    print(f"Wrote failures: {args.failures_out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock_correct", "mock_misleading", "llm_agent"], required=True)
    parser.add_argument("--tasks", default="all", help="Task slugs, e.g. rw001,rw020 or rw001-rw040.")
    parser.add_argument("--tasks-file", type=Path, help="Task JSONL to load in the shell and runner.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--submissions", type=Path, default=DEFAULT_SUBMISSIONS)
    parser.add_argument("--runs-out", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--failures-out", type=Path, default=DEFAULT_FAILURES)
    parser.add_argument("--screenshot-dir", type=Path, help="Directory where Playwright screenshots should be stored.")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--top-p", dest="top_p", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--extra-system-prompt", help="Optional prompt text appended to the system prompt.")
    parser.add_argument("--headed", action="store_true", help="Show browser for llm_agent mode.")
    parser.add_argument("--no-start-server", action="store_true", help="Require an existing Real-World40 shell server.")
    parser.add_argument(
        "--hide-form-dashboard-link",
        action="store_true",
        help="When auto-starting the shell, hide the form-page link back to the full dashboard.",
    )
    args = parser.parse_args()
    if args.extra_system_prompt is not None:
        os.environ["WEB_AGENT_EXTRA_SYSTEM_PROMPT"] = args.extra_system_prompt
    try:
        return run(args)
    except Exception as exc:
        if args.mode == "llm_agent" and "Playwright is required" in str(exc):
            print(str(exc), file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
