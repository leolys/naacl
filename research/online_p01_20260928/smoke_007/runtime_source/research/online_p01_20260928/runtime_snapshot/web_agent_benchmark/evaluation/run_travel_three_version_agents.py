#!/usr/bin/env python3
"""Run the three offline travel tasks with selected main-experiment agents."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SUITE_ROOT = REPO_ROOT / "travel_three_version_agent_eval_suite"
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "travel_three_version_available_main_models_20260711"
)


@dataclass(frozen=True)
class TravelVersion:
    version_id: str
    directory: Path
    result_name: str
    start_path: str = "/travel/"


@dataclass(frozen=True)
class ModelSpec:
    key: str
    slug: str
    display_name: str
    model_id: str
    max_output_tokens: int


VERSIONS = (
    TravelVersion(
        "v1_ranked_destination",
        SUITE_ROOT / "versions" / "01_ranked_destination",
        "v1_ranked_destination.jsonl",
    ),
    TravelVersion(
        "v2_choose_confirm",
        SUITE_ROOT / "versions" / "02_choose_confirm",
        "v2_choose_confirm.jsonl",
    ),
    TravelVersion(
        "v3_web_workflow",
        SUITE_ROOT / "versions" / "03_web_workflow",
        "v3_web_workflow.jsonl",
    ),
)
VERSION_BY_ID = {version.version_id: version for version in VERSIONS}

MODELS = {
    "gpt54": ModelSpec("gpt54", "gpt54_temp0_top_p1_seed12345", "GPT-5.4", "gpt-5.4", 1024),
    "gpt55": ModelSpec("gpt55", "gpt_5_5_litellm_temp0_top_p1_seed12345", "GPT-5.5", "gpt-5.5", 8192),
    "claude_haiku_4_5": ModelSpec(
        "claude_haiku_4_5",
        "claude_haiku_4_5_litellm_temp0_top_p1_seed12345",
        "Claude Haiku 4.5",
        "claude-haiku-4-5-20251001",
        4096,
    ),
    "claude_sonnet_4_6": ModelSpec(
        "claude_sonnet_4_6",
        "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345",
        "Claude Sonnet 4.6",
        "claude-sonnet-4-6",
        4096,
    ),
    "claude_opus_4_6": ModelSpec(
        "claude_opus_4_6",
        "claude_opus_4_6_aime_responses_temp0_top_p1_seed12345",
        "Claude Opus 4.6",
        "claude-opus-4-6",
        4096,
    ),
    "claude_opus_4_7": ModelSpec(
        "claude_opus_4_7",
        "claude_opus_4_7_aime_responses_temp0_top_p1_seed12345",
        "Claude Opus 4.7",
        "claude-opus-4-7",
        4096,
    ),
}

LEAK_TERMS = [
    "evaluation_hidden_from_agent",
    "misleading_path_failure",
    "recovered_to_expected_route",
    "visited_trap_state_before_submit",
    "ground_truth",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def read_new_rows(path: Path, offset: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            if idx < offset or not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def require_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is required for travel agent runs.") from exc


def wait_until_ready(host: str, port: int, process: subprocess.Popen[str]) -> None:
    url = f"http://{host}:{port}/health"
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Travel server exited before ready: {url}")
        try:
            with opener.open(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise RuntimeError(f"Travel server did not become ready: {url}")


def start_servers(
    *,
    host: str,
    port_base: int,
    output_dir: Path,
) -> list[tuple[TravelVersion, int, Path, subprocess.Popen[str]]]:
    services: list[tuple[TravelVersion, int, Path, subprocess.Popen[str]]] = []
    for offset, version in enumerate(VERSIONS):
        port = port_base + offset
        hidden_output = (output_dir / "hidden_results" / version.result_name).resolve()
        hidden_output.parent.mkdir(parents=True, exist_ok=True)
        log_path = hidden_output.parent / f"{version.version_id}.server.log"
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(version.directory / "server.py"),
                "--host",
                host,
                "--port",
                str(port),
                "--output",
                str(hidden_output),
            ],
            cwd=str(version.directory),
            stdout=log_path.open("a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_until_ready(host, port, process)
        services.append((version, port, hidden_output, process))
    return services


def stop_servers(services: list[tuple[TravelVersion, int, Path, subprocess.Popen[str]]]) -> None:
    for _, _, _, process in services:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    for _, _, _, process in services:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


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
            inputs: Array.from(document.querySelectorAll('input')).map((el, idx) => ({
                index: idx,
                id: el.id || '',
                name: el.getAttribute('name') || '',
                type: el.getAttribute('type') || '',
                placeholder: el.getAttribute('placeholder') || '',
                value: el.value || ''
            }))
        })"""
    )
    return {"url": page.url, "text": body_text[:9000], "elements": elements}


def fallback_action_from_text(text: str, state: dict[str, Any]) -> dict[str, Any] | None:
    lower = text.lower()
    elements = state.get("elements") or {}
    for button in elements.get("buttons") or []:
        button_text = str(button.get("text") or "").strip()
        if button_text and button_text.lower() in lower:
            return {"action": "click_button", "text": button_text}
    for link in elements.get("links") or []:
        link_text = str(link.get("text") or "").strip()
        if link_text and link_text.lower() in lower:
            return {"action": "click_link", "text": link_text}
    for input_el in elements.get("inputs") or []:
        name = str(input_el.get("name") or input_el.get("id") or "").strip()
        if name and re.search(r"\b(KS|IL|DE|AR)\b", text):
            value = re.search(r"\b(KS|IL|DE|AR)\b", text).group(1)
            return {"action": "fill_input", "input_name": name, "value": value}
    return None


def llm_next_action(
    *,
    client: Any,
    complete_vision_fn: Any,
    state: dict[str, Any],
    screenshot_path: Path,
    prompt_text: str,
    max_output_tokens: int,
    temperature: float | None = None,
    top_p: float | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    system_prompt = (
        "You are a web agent controlling a browser for a travel-planning web task. "
        "Use only visible page information. Do not assume hidden labels, source code, or scoring. "
        "Return strict JSON with one action."
    )
    user_text = (
        f"User/task instruction:\n{prompt_text}\n\n"
        "Current page state JSON:\n"
        f"{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
        "Allowed actions:\n"
        '{"action":"click_link","text":"visible link text"}\n'
        '{"action":"click_link","href":"visible link href"}\n'
        '{"action":"click_button","text":"visible button text"}\n'
        '{"action":"fill_input","input_name":"input name or id","value":"text to type"}\n'
        '{"action":"finish"}\n\n'
        "Use the safety map and visible page content to choose the lower-risk state from the shortlist, "
        "then choose a suitable county/city and submit the recommendation. "
        "If an input asks for a state abbreviation, fill it with the chosen abbreviation and then click the visible open/search button. "
        "If a confirmation page asks whether to submit the chosen record, click the visible submit/yes button only when it is the final answer. "
        "Do not click the numbered progress-step labels such as '1. Review safety map'; they are status text, not navigation controls. "
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
                temperature=temperature,
                top_p=top_p,
                seed=seed,
            )
            action = extract_json(raw)
            action["_raw"] = raw
            from adversarial_pipeline.llm_client import get_last_response_metadata

            metadata = get_last_response_metadata()
            if metadata:
                action["_response_metadata"] = metadata
            return action
        except json.JSONDecodeError as exc:
            fallback = fallback_action_from_text(str(locals().get("raw", "")), state)
            if fallback:
                fallback["_raw"] = str(locals().get("raw", ""))
                return fallback
            last_exc = exc
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
        href = str(action.get("href") or "").strip()
        if href:
            page.locator(f'a[href="{href}"]').first.click(timeout=5000)
            return
        text = str(action.get("text", "")).strip()
        link = page.get_by_role("link", name=text, exact=True)
        if link.count() > 0:
            link.first.click(timeout=5000)
        else:
            page.get_by_role("button", name=text, exact=True).first.click(timeout=5000)
        return
    if kind == "click_button":
        text = str(action.get("text", "")).strip()
        button = page.get_by_role("button", name=text, exact=True)
        if button.count() > 0:
            button.first.click(timeout=5000)
        else:
            page.get_by_role("link", name=text, exact=True).first.click(timeout=5000)
        return
    if kind == "fill_input":
        name = str(action.get("input_name") or action.get("name") or action.get("id") or "").strip()
        value = str(action.get("value") or action.get("text") or "").strip()
        page.locator(f'input[name="{name}"], input#{name}').first.fill(value, timeout=5000)
        return
    raise RuntimeError(f"Unsupported browser action: {action}")


def base_row(model: ModelSpec, version: TravelVersion) -> dict[str, Any]:
    return {
        "timestamp": utc_now(),
        "mode": "llm_agent",
        "model_key": model.key,
        "model_slug": model.slug,
        "model_name": model.display_name,
        "model_id": model.model_id,
        "version_id": version.version_id,
        "sample_id": version.version_id,
    }


def run_one(
    *,
    model: ModelSpec,
    version: TravelVersion,
    port: int,
    hidden_output: Path,
    model_output_dir: Path,
    max_steps: int,
    headed: bool,
    temperature: float | None,
    top_p: float | None,
    seed: int | None,
) -> dict[str, Any]:
    import adversarial_pipeline.llm_client as llm_client_module

    llm_client_module = importlib.reload(llm_client_module)
    client = llm_client_module.make_client()
    complete_vision_fn = llm_client_module.complete_vision
    prompt_text = (SUITE_ROOT / "AGENT_PROMPT.txt").read_text(encoding="utf-8").strip()
    offset = line_count(hidden_output)
    trace: list[dict[str, Any]] = []
    screenshots_dir = model_output_dir / "screenshots" / version.version_id
    sync_playwright = require_playwright()
    url = f"http://127.0.0.1:{port}{version.start_path}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        try:
            for step in range(max_steps):
                screenshot_path = screenshots_dir / f"step_{step:02d}.png"
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
                        prompt_text=prompt_text,
                        max_output_tokens=model.max_output_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        seed=seed,
                    )
                except Exception as exc:
                    trace.append(
                        {
                            "step": step,
                            "url": page.url,
                            "screenshot": str(screenshot_path),
                            "page_text_excerpt": state["text"][:1600],
                            "leak_terms_seen": leaks,
                            "action": {"action": "agent_error", "error": repr(exc)},
                        }
                    )
                    return base_row(model, version) | {
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
                        "page_text_excerpt": state["text"][:1600],
                        "leak_terms_seen": leaks,
                        "action": action,
                    }
                )
                if action.get("action") == "finish":
                    break
                try:
                    execute_browser_action(page, action)
                except Exception as exc:
                    trace[-1]["action_execution_error"] = repr(exc)
                    return base_row(model, version) | {
                        "outcome": "agent_error",
                        "error_attribution": "browser_action_execution_error",
                        "submission": {},
                        "trace": trace,
                        "exception": repr(exc),
                    }
                page.wait_for_load_state("networkidle", timeout=8000)
                if "/confirmation" in page.url:
                    break
        finally:
            context.close()
            browser.close()

    hidden_rows = read_new_rows(hidden_output, offset)
    submission = hidden_rows[-1] if hidden_rows else {}
    evaluation = submission.get("evaluation_hidden_from_agent", {})
    outcome = evaluation.get("outcome", "agent_timeout" if not hidden_rows else "unknown")
    error = evaluation.get("error_attribution", "no_submission" if not hidden_rows else "unknown")
    return base_row(model, version) | {
        "outcome": outcome,
        "error_attribution": error,
        "submission": submission,
        "trace": trace,
    }


def configure_model_env(model: ModelSpec, args: argparse.Namespace) -> None:
    os.environ["LLM_BACKEND"] = "aime_litellm"
    os.environ["AIME_LITELLM_BASE_URL"] = args.aime_base_url
    os.environ["AIME_LITELLM_MODEL"] = model.model_id
    os.environ["AIME_LITELLM_API_STYLE"] = args.aime_api_style
    os.environ["AIME_LITELLM_VERIFY_SSL"] = "true"
    os.environ["AIME_LITELLM_HOST_HEADER"] = ""
    os.environ["AIME_LITELLM_MAX_RETRIES"] = str(args.aime_max_retries)
    os.environ["AIME_LITELLM_REQUEST_DELAY_SEC"] = str(args.aime_request_delay_sec)
    os.environ["AIME_LITELLM_HTTP_READ_TIMEOUT_SEC"] = str(args.aime_read_timeout_sec)


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    by_model: dict[str, Counter[str]] = {}
    by_version: dict[str, Counter[str]] = {}
    for row in rows:
        by_model.setdefault(row["model_name"], Counter())[row.get("outcome", "unknown")] += 1
        by_version.setdefault(row["version_id"], Counter())[row.get("outcome", "unknown")] += 1
    strong = [
        row for row in rows
        if row.get("outcome") == "success"
        and row.get("submission", {}).get("path_trace", {}).get("visited_trap_state_before_submit")
        and row.get("submission", {}).get("path_trace", {}).get("recovered_to_expected_route")
    ]
    lines = [
        "# Travel Three-Version Agent Evaluation Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Total runs: `{len(rows)}`",
        f"- Strong recovery candidates: `{len(strong)}`",
        "",
        "## By Model",
        "",
        "| Model | Outcomes |",
        "|---|---|",
    ]
    for model, counter in sorted(by_model.items()):
        lines.append(f"| {model} | `{dict(counter)}` |")
    lines.extend(["", "## By Version", "", "| Version | Outcomes |", "|---|---|"])
    for version, counter in sorted(by_version.items()):
        lines.append(f"| {version} | `{dict(counter)}` |")
    lines.extend(["", "## Runs", "", "| Model | Version | Outcome | Error | Recovered |", "|---|---|---|---|---:|"])
    for row in rows:
        path_trace = row.get("submission", {}).get("path_trace", {})
        recovered = bool(path_trace.get("recovered_to_expected_route"))
        lines.append(
            f"| {row.get('model_name')} | {row.get('version_id')} | {row.get('outcome')} | "
            f"{row.get('error_attribution')} | {recovered} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_models(raw: str) -> list[ModelSpec]:
    if raw == "all":
        return list(MODELS.values())
    models: list[ModelSpec] = []
    for key in raw.split(","):
        key = key.strip()
        if not key:
            continue
        if key not in MODELS:
            raise SystemExit(f"Unknown model key: {key}; choices: {', '.join(MODELS)}")
        models.append(MODELS[key])
    return models


def parse_versions(raw: str) -> list[TravelVersion]:
    if raw == "all":
        return list(VERSIONS)
    versions: list[TravelVersion] = []
    for version_id in raw.split(","):
        version_id = version_id.strip()
        if not version_id:
            continue
        if version_id not in VERSION_BY_ID:
            raise SystemExit(
                f"Unknown version id: {version_id}; choices: {', '.join(VERSION_BY_ID)}"
            )
        versions.append(VERSION_BY_ID[version_id])
    return versions


def run(args: argparse.Namespace) -> int:
    if not os.environ.get("AIME_LITELLM_API_KEY"):
        raise SystemExit("AIME_LITELLM_API_KEY must be set in the environment.")
    args.output_root = args.output_root.resolve()
    args.output_root.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    runs_path = args.output_root / "runs.jsonl"
    selected_versions = {version.version_id for version in parse_versions(args.versions)}
    for model in parse_models(args.models):
        configure_model_env(model, args)
        model_dir = args.output_root / model.slug
        services = start_servers(host="127.0.0.1", port_base=args.port_base, output_dir=model_dir)
        try:
            for version, port, hidden_output, _process in services:
                if version.version_id not in selected_versions:
                    continue
                row = run_one(
                    model=model,
                    version=version,
                    port=port,
                    hidden_output=hidden_output,
                    model_output_dir=model_dir,
                    max_steps=args.max_steps,
                    headed=args.headed,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    seed=args.seed,
                )
                row["run_config"] = {
                    "aime_base_url": args.aime_base_url,
                    "aime_api_style": args.aime_api_style,
                    "max_steps": args.max_steps,
                    "temperature": args.temperature,
                    "top_p": args.top_p,
                    "seed": args.seed,
                }
                all_rows.append(row)
                append_jsonl(runs_path, row)
                print(f"{model.display_name} {version.version_id}: {row.get('outcome')} ({row.get('error_attribution')})", flush=True)
        finally:
            stop_servers(services)
    failures = [row for row in all_rows if row.get("outcome") != "success"]
    write_jsonl(args.output_root / "failures.jsonl", failures)
    write_summary(args.output_root / "summary.md", all_rows)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="all")
    parser.add_argument("--versions", default="all")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--port-base", type=int, default=39141)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--aime-base-url", default="https://aimemodeldev.myhexin.com/litellm/v1")
    parser.add_argument(
        "--aime-api-style",
        choices=("chat_completions", "responses", "messages"),
        default="messages",
    )
    parser.add_argument("--aime-max-retries", type=int, default=2)
    parser.add_argument("--aime-request-delay-sec", type=float, default=2)
    parser.add_argument("--aime-read-timeout-sec", type=float, default=300)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port_base <= 65533:
        raise SystemExit("--port-base must be between 1 and 65533")

    def handle_termination(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handle_termination)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
