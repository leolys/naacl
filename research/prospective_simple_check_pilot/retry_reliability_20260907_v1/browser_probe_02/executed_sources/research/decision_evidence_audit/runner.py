"""Stage-two before-submit smoke runner.

This is a thin adapter around the released environment task rows.  It does not
call the original paired supervisor because that entrypoint deletes same-slug
outputs and may auto-start GPU models.  The controller sees only agent-safe HTTP
pages and allowlisted request objects; scoring happens after submission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageDraw
from werkzeug.serving import make_server

from .core import (
    BeforeSubmitHook,
    BudgetLedger,
    Checkpoint,
    append_jsonl,
    canonical_state,
    current_selection,
    public_action,
    public_browser_state,
    state_digest,
    visible_options,
    write_json,
)
from .models import LocalQwenServiceBackend, RecordedModel, ScriptedMockBackend
from .policies import STRATEGIES, PolicyResult, run_policy
from .safe_shell import build_shell_bundle, make_app, score_receipt


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = REPOSITORY_ROOT / "web_agent_benchmark" / "benchmark_v2_open"
CONDITION_FILES = {
    "official140": RELEASE_ROOT / "splits" / "official140" / "environment35_tasks.jsonl",
    "clean140": RELEASE_ROOT / "splits" / "clean140" / "environment35_tasks.jsonl",
}
DEFAULT_DEV_TASKS = ("env001", "env025")
TASK_PROFILES = {
    "stage-two": DEFAULT_DEV_TASKS,
    "clear-rule-probe": ("pub010", "env008", "b035"),
}
TASK_FAMILY_FILES = {
    "pub": "public39_tasks.jsonl",
    "env": "environment35_tasks.jsonl",
    "b": "business47_tasks.jsonl",
}
DEFAULT_ALIASES = {"env001": "dev01", "env025": "dev02"}
BROWSER_LAUNCH_ARGS = ("--no-sandbox", "--disable-gpu")
PAIR_INVARIANT_FIELDS = (
    "task_id",
    "case_id",
    "page_title",
    "workflow_instruction",
    "chart_reference",
    "ground_truth",
    "intermediate_decision",
    "primary_action",
    "companion_actions",
    "action_space",
    "expected_action_id",
    "misleading_action_ids",
    "fallback_scoring",
    "completion_action",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def read_rows_after(path: Path, offset: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = read_jsonl(path)
    return rows[offset:]


def find_task(path: Path, slug: str) -> dict[str, Any]:
    for row in read_jsonl(path):
        if str(row.get("task_slug") or row.get("official_slug") or "") == slug:
            return row
    raise KeyError(f"task slug {slug!r} is absent from {path}")


def task_spec_path(condition: str, slug: str) -> Path:
    """Resolve the released source family; never infer it from scoring fields."""
    if condition not in CONDITION_FILES:
        raise ValueError(f"unsupported chart condition: {condition!r}")
    for prefix, filename in TASK_FAMILY_FILES.items():
        if re.fullmatch(re.escape(prefix) + r"\d{3}", slug):
            return RELEASE_ROOT / "splits" / condition / filename
    raise ValueError(f"unsupported task slug: {slug!r}")


def selected_task_slugs(args: argparse.Namespace) -> tuple[str, ...]:
    profile = getattr(args, "profile", "stage-two")
    if profile not in TASK_PROFILES:
        raise ValueError(f"unknown experiment profile: {profile!r}")
    task_slugs = tuple(value.strip() for value in args.tasks.split(",") if value.strip())
    allowed = TASK_PROFILES[profile]
    if not 1 <= len(task_slugs) <= len(allowed):
        raise ValueError(f"{profile} allows one to {len(allowed)} development base tasks")
    if len(set(task_slugs)) != len(task_slugs):
        raise ValueError(f"{profile} task slugs must be unique")
    unsupported = sorted(set(task_slugs) - set(allowed))
    if unsupported:
        raise ValueError(f"task(s) are outside the {profile} development split: {unsupported}")
    return task_slugs


def pair_invariant_differences(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return [field for field in PAIR_INVARIANT_FIELDS if left.get(field) != right.get(field)]


def completed_chain_unit(result: dict[str, Any], score_row: dict[str, Any]) -> bool:
    """A clean chain requires commit, acknowledgement, confirmation, and a score."""

    return (
        result.get("status") == "submitted"
        and result.get("confirmation_observed") is True
        and score_row.get("terminal_score") is not None
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_fingerprint(extra_paths: tuple[Path, ...] = ()) -> dict[str, Any]:
    package_paths = {
        path
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file()
        and not {"runs", "revisions", "__pycache__"}.intersection(
            path.relative_to(PACKAGE_ROOT).parts
        )
        and path.suffix in {".py", ".json", ".jsonl"}
    }
    paths = sorted(package_paths | {path.resolve() for path in extra_paths if path.is_file()})
    rows = [
        {"path": path.relative_to(REPOSITORY_ROOT).as_posix(), "sha256": file_sha256(path)}
        for path in paths
    ]
    joined = "\n".join(f"{row['sha256']}  {row['path']}" for row in rows)
    return {
        "method": (
            "sha256 over executable adapter source, tests, manifests, selected task specs/assets, "
            "and live client/server dependencies; excludes run and revision artifacts"
        ),
        "tree_sha256": hashlib.sha256(joined.encode("utf-8")).hexdigest(),
        "files": rows,
    }


def snapshot_runtime_sources(
    fingerprint: dict[str, Any], *, destination: Path
) -> list[dict[str, str]]:
    """Copy every fingerprinted runtime input into the run directory."""

    copied: list[dict[str, str]] = []
    for row in fingerprint.get("files") or []:
        relative = Path(str(row["path"]))
        source = (REPOSITORY_ROOT / relative).resolve()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append({"path": relative.as_posix(), "sha256": file_sha256(target)})
    return copied


class RuntimeSourceChanged(RuntimeError):
    """The configured source identity changed after the run began."""


def git_revision_status() -> str:
    """Record current Git availability without changing repository configuration."""

    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={REPOSITORY_ROOT}", "rev-parse", "--verify", "HEAD"],
            cwd=REPOSITORY_ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {type(exc).__name__}"
    return result.stdout.strip() if result.returncode == 0 else "Git available; no verifiable HEAD commit"


class QuietHandler:
    def log(self, request_type: str, message: str, *args: Any) -> None:
        return None


@dataclass
class ServerHandle:
    base_url: str
    server: Any
    thread: threading.Thread

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)


@contextmanager
def managed_shell(public_task: dict[str, Any], chart_path: Path, output_path: Path) -> Iterator[ServerHandle]:
    app = make_app(public_task, chart_path=chart_path, output_path=output_path)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name="decision-evidence-shell", daemon=True)
    thread.start()
    handle = ServerHandle(base_url=f"http://127.0.0.1:{server.server_port}", server=server, thread=thread)
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(f"{handle.base_url}/health", timeout=3)
        response.raise_for_status()
        yield handle
    finally:
        try:
            session.close()
        finally:
            handle.stop()


def require_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except ModuleNotFoundError:
        audited_fallback = Path("/tmp/wa_playwright")
        if audited_fallback.is_dir():
            sys.path.insert(0, str(audited_fallback))
            from playwright.sync_api import sync_playwright

            return sync_playwright
        raise RuntimeError("Playwright is unavailable; no dependency was downloaded")


def browser_executable(candidate: str | None) -> Path | None:
    if candidate:
        path = Path(candidate)
        if not path.is_file():
            raise FileNotFoundError(f"browser executable does not exist: {path}")
        return path
    audited = Path("/tmp/wa_pw_browsers/chromium-1117/chrome-linux/chrome")
    return audited if audited.is_file() else None


def raw_browser_state(page: Any) -> dict[str, Any]:
    elements = page.evaluate(
        """() => {
          const visible = el => {
            if (!el || !el.getClientRects().length) return false;
            for (let node = el; node; node = node.parentElement) {
              const style = getComputedStyle(node);
              if (node.hidden || style.display === 'none' || style.visibility === 'hidden'
                  || style.visibility === 'collapse' || Number(style.opacity) === 0) return false;
            }
            return true;
          };
          const enabled = el => visible(el) && !el.matches(':disabled')
            && el.getAttribute('aria-disabled') !== 'true';
          const text = [];
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          while (walker.nextNode()) {
            const node = walker.currentNode;
            if (visible(node.parentElement) && node.textContent.trim()) text.push(node.textContent.trim());
          }
          return {
          visible_text: text.join('\\n'),
          links: Array.from(document.querySelectorAll('a')).filter(enabled).map(el => ({
            text: (el.innerText || el.textContent || '').trim(), href: el.href || ''
          })),
          buttons: Array.from(document.querySelectorAll('button')).filter(enabled).map(el => ({
            text: (el.innerText || el.textContent || '').trim(), type: el.type || ''
          })),
          selects: Array.from(document.querySelectorAll('select')).filter(enabled).map(el => ({
            name: el.name || el.id || '',
            id: el.id || '',
            label: Array.from(el.labels || []).filter(visible).map(x => x.innerText.trim()).join(' '),
            selected_text: el.selectedOptions.length ?
              (el.selectedOptions[0].innerText || el.selectedOptions[0].textContent || '').trim() : '',
            options: Array.from(el.options).filter(opt => !opt.hidden && !opt.disabled
              && !opt.parentElement.disabled && getComputedStyle(opt).display !== 'none').map(opt => ({
              text: (opt.innerText || opt.textContent || '').trim(),
              disabled: Boolean(opt.disabled), selected: Boolean(opt.selected)
            }))
          }))
        }; }"""
    )
    return {
        "url": page.url,
        "text": elements.pop("visible_text"),
        "elements": elements,
    }


def capture_state(page: Any) -> dict[str, Any]:
    return public_browser_state(raw_browser_state(page))


def screenshot_kind(url_path: str) -> str:
    if url_path.endswith("/dashboard"):
        return "dashboard"
    if url_path.endswith("/form"):
        return "form"
    return "task"


def _extract_action(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    candidates = [stripped]
    candidates.extend(stripped[index:] for index, char in enumerate(stripped) if char == "{")
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            action = public_action(parsed)
            if action.get("action"):
                return action
    return {"action": "invalid"}


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    decoder = json.JSONDecoder()
    for candidate in [stripped, *(stripped[index:] for index, char in enumerate(stripped) if char == "{")]:
        try:
            parsed, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def run_multi_image_witness(
    *, model: RecordedModel, run_root: Path, seed: int
) -> dict[str, Any]:
    """Make one budgeted two-image call before a live smoke begins."""

    witness_dir = run_root / "online" / "preflight_witness"
    images_dir = witness_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    panel_1 = images_dir / "panel_01.png"
    panel_2 = images_dir / "panel_02.png"

    first = Image.new("RGB", (512, 384), "white")
    first_draw = ImageDraw.Draw(first)
    first_draw.polygon([(256, 48), (64, 336), (448, 336)], fill=(235, 32, 32))
    first.save(panel_1)
    first.close()

    second = Image.new("RGB", (512, 384), "white")
    second_draw = ImageDraw.Draw(second)
    second_draw.ellipse((96, 32, 416, 352), fill=(30, 90, 235))
    second.save(panel_2)
    second.close()

    calls_before = model.ledger.model_calls
    try:
        reply = model.call(
            phase="preflight_multi_image_witness",
            system_prompt=(
                "Use only the two supplied images, in their supplied order. "
                "Identify the dominant colored shape in each panel and return JSON only."
            ),
            user_prompt=(
                "Return exactly "
                '{"panel_1":{"color":"...","shape":"..."},'
                '"panel_2":{"color":"...","shape":"..."}}. '
                "Do not use filenames as evidence."
            ),
            image_path=[panel_1, panel_2],
            image_artifact=["images/panel_01.png", "images/panel_02.png"],
            public_context={
                "witness": "ordered_two_image_transport",
                "supplied_panel_count": 2,
                "seed": seed,
            },
            request_dir=witness_dir / "requests",
            response_dir=witness_dir / "responses",
        )
        parsed = _extract_json_object(reply.text)
        panel_1_text = json.dumps(parsed.get("panel_1"), ensure_ascii=False).casefold()
        panel_2_text = json.dumps(parsed.get("panel_2"), ensure_ascii=False).casefold()
        content_checks = {
            "panel_1_red_triangle": "red" in panel_1_text and "triangle" in panel_1_text,
            "panel_2_blue_circle": "blue" in panel_2_text and "circle" in panel_2_text,
        }
        vision_input = reply.metadata.get("vision_input") or {}
        returned_image_count = vision_input.get("image_count")
        count_ok = returned_image_count == 2
        passed = count_ok and all(content_checks.values())
        result = {
            "status": "passed" if passed else "failed",
            "seed": seed,
            "model_calls": model.ledger.model_calls - calls_before,
            "http_attempts": model.ledger.model_calls - calls_before,
            "supplied_image_count": 2,
            "returned_input_image_count": returned_image_count,
            "returned_original_image_sizes": vision_input.get("original_image_sizes"),
            "server_protocol_version": vision_input.get("server_protocol_version"),
            "content_checks": content_checks,
            "response_text": reply.text,
            "response_metadata": reply.metadata,
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "seed": seed,
            "model_calls": model.ledger.model_calls - calls_before,
            "http_attempts": model.ledger.model_calls - calls_before,
            "supplied_image_count": 2,
            "returned_input_image_count": None,
            "content_checks": {},
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    write_json(witness_dir / "result.json", result)
    return result


class BrowserExecutor:
    """One shared action implementation and retry bound for every strategy."""

    def __init__(
        self,
        page: Any,
        *,
        ledger: BudgetLedger,
        task_alias: str,
        max_attempts: int = 2,
    ) -> None:
        self.page = page
        self.ledger = ledger
        self.task_alias = task_alias
        self.max_attempts = max_attempts
        self.receipts: list[dict[str, Any]] = []

    def _contained(self) -> bool:
        path = urlsplit(self.page.url).path
        prefix = f"/task/{self.task_alias}"
        return path == prefix or path.startswith(f"{prefix}/")

    def _select_target(self, identifier: str, option_text: str) -> Any:
        """Resolve a public control, never a task-specific alias or a guessed option.

        Enumerating controls avoids CSS interpolation and silently selecting the
        first of multiple matches. Name/id take precedence over visible labels.
        The same resolver is used by prefix, replay, and every revision policy.
        """

        controls = self.page.locator("select")
        rows = controls.evaluate_all("""els => els.map((el, index) => ({
          index, name: el.name, id: el.id,
          visible: !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden',
          disabled: el.disabled,
          labels: Array.from(el.labels || []).map(x => (x.innerText || '').trim()),
          options: Array.from(el.options).map(x => ({
            text: (x.innerText || x.textContent || '').trim(),
            disabled: x.disabled || (x.parentElement.tagName === 'OPTGROUP' && x.parentElement.disabled)
          }))
        }))""")
        visible = [row for row in rows if row["visible"]]
        exact = [row for row in visible if identifier and identifier in (row["name"], row["id"])]
        matches = exact or [row for row in visible if identifier and identifier in row["labels"]]
        if len(matches) != 1:
            raise RuntimeError(f"select_target_not_unique: {identifier!r}; matches={len(matches)}")
        selected = matches[0]
        options = [item for item in selected["options"] if item["text"] == option_text]
        if selected["disabled"] or len(options) != 1 or options[0]["disabled"]:
            raise RuntimeError(f"select_option_not_unique_or_enabled: {option_text!r}")
        return controls.nth(selected["index"])

    def navigate(self, url: str, *, phase: str) -> dict[str, Any]:
        action = {"action": "goto", "text": f"/task/{self.task_alias}"}
        self.ledger.charge_transition(phase=phase, action=action)
        before = self.page.url
        try:
            self.page.goto(url, wait_until="networkidle", timeout=10000)
            ok = self._contained()
            error = "" if ok else "path_containment_failure"
        except Exception as exc:
            ok = False
            error = f"{type(exc).__name__}: {exc}"
        receipt = {
            "phase": phase,
            "attempt": 1,
            "action": action,
            "before_url_path": public_browser_state({"url": before})["url_path"],
            "after_url_path": public_browser_state({"url": self.page.url})["url_path"],
            "executed": ok,
            "error": error,
        }
        self.receipts.append(receipt)
        if not ok:
            raise RuntimeError(error)
        return receipt

    def execute(
        self, action: dict[str, Any], *, phase: str, max_attempts: int | None = None
    ) -> dict[str, Any]:
        clean_action = public_action(action)
        last_error = ""
        attempt_limit = self.max_attempts if max_attempts is None else max_attempts
        if not 1 <= attempt_limit <= self.max_attempts:
            raise ValueError("per-action max_attempts must be within the executor limit")
        for attempt in range(1, attempt_limit + 1):
            self.ledger.charge_transition(phase=phase, action=clean_action)
            before = self.page.url
            try:
                kind = clean_action.get("action")
                if kind == "click_link":
                    text = clean_action.get("text", "")
                    target = self.page.get_by_role("link", name=text, exact=True)
                    if target.count() == 0:
                        target = self.page.get_by_role("button", name=text, exact=True)
                    target.click(timeout=5000)
                elif kind in {"click_button", "submit_form"}:
                    text = clean_action.get("text") or "Submit Form"
                    target = self.page.get_by_role("button", name=text, exact=True)
                    if target.count() == 0:
                        target = self.page.get_by_role("link", name=text, exact=True)
                    target.click(timeout=5000)
                elif kind == "select_option":
                    select_name = clean_action.get("select_name", "")
                    option_text = clean_action.get("option_text", "")
                    target = self._select_target(select_name, option_text)
                    target.select_option(label=option_text, timeout=5000)
                    selected_text = str(
                        target.evaluate(
                            "el => el.selectedOptions.length ? "
                            "(el.selectedOptions[0].innerText || el.selectedOptions[0].textContent || '').trim() : ''"
                        )
                        or ""
                    ).strip()
                    if selected_text != option_text:
                        raise RuntimeError(
                            "selection_postcondition_failure: "
                            f"requested {option_text!r}, observed {selected_text!r}"
                        )
                else:
                    raise RuntimeError(f"unsupported browser action: {clean_action}")
                self.page.wait_for_load_state("networkidle", timeout=5000)
                if not self._contained():
                    raise RuntimeError("path_containment_failure")
                receipt = {
                    "phase": phase,
                    "attempt": attempt,
                    "action": clean_action,
                    "before_url_path": public_browser_state({"url": before})["url_path"],
                    "after_url_path": public_browser_state({"url": self.page.url})["url_path"],
                    "executed": True,
                    "error": "",
                }
                self.receipts.append(receipt)
                return receipt
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self.receipts.append(
                    {
                        "phase": phase,
                        "attempt": attempt,
                        "action": clean_action,
                        "before_url_path": public_browser_state({"url": before})["url_path"],
                        "after_url_path": public_browser_state({"url": self.page.url})["url_path"],
                        "executed": False,
                        "error": last_error,
                    }
                )
        raise RuntimeError(last_error)


def prefix_prompt(user_goal: str, state: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a browser agent. Use only the supplied visible page and screenshot. "
        "Do not assume hidden labels, scores, or unavailable source data. Return one JSON action."
    )
    user = (
        f"User goal: {user_goal}\n\n"
        f"Visible page state: {json.dumps(state, ensure_ascii=False)}\n\n"
        "Allowed actions:\n"
        '{"action":"click_link","text":"exact visible link"}\n'
        '{"action":"click_button","text":"exact visible button"}\n'
        '{"action":"select_option","select_name":"visible select name","option_text":"exact visible option"}\n'
        '{"action":"finish"}\n'
        "Choose exactly one next action. Complete and submit the visible decision form."
    )
    return system, user


def generate_checkpoint(
    *,
    browser: Any,
    base_url: str,
    task_alias: str,
    user_goal: str,
    model: RecordedModel,
    ledger: BudgetLedger,
    run_root: Path,
    prefix_dir: Path,
    submission_path: Path,
    max_model_calls: int,
) -> tuple[Checkpoint | None, dict[str, Any]]:
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    executor = BrowserExecutor(page, ledger=ledger, task_alias=task_alias)
    hook = BeforeSubmitHook()
    action_prefix: list[dict[str, Any]] = []
    observed: list[dict[str, str]] = []
    model_context: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    checkpoint: Checkpoint | None = None
    receipt_count_before = line_count(submission_path)
    step = -1
    try:
        try:
            executor.navigate(f"{base_url}/task/{task_alias}", phase="prefix_start")
            for step in range(max_model_calls):
                state = capture_state(page)
                shot = prefix_dir / "screenshots" / f"observed_{step:02d}.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
                relative_shot = shot.relative_to(run_root).as_posix()
                observed.append({"kind": screenshot_kind(state["url_path"]), "path": relative_shot})
                system, user = prefix_prompt(user_goal, state)
                reply = model.call(
                    phase="prefix",
                    system_prompt=system,
                    user_prompt=user,
                    image_path=shot,
                    image_artifact=relative_shot,
                    public_context={
                        "state": state,
                        "visible_options": visible_options(state),
                        "current_selection": current_selection(state),
                        "user_goal": user_goal,
                    },
                    request_dir=prefix_dir / "requests",
                    response_dir=prefix_dir / "responses",
                )
                action = _extract_action(reply.text)
                context_record = {
                    "step": step,
                    "request_id": reply.metadata.get("request_id"),
                    "response": reply.text,
                    "proposed_action": action,
                    "state_digest": state_digest(state),
                }
                model_context.append(context_record)
                candidate = hook.inspect(
                    task_alias=task_alias,
                    user_goal=user_goal,
                    state=state,
                    current_screenshot=relative_shot,
                    observed_screenshots=observed,
                    visible_action_prefix=action_prefix,
                    model_context=model_context,
                    proposal=action,
                )
                if candidate is not None:
                    checkpoint = candidate
                    break
                if action.get("action") == "finish":
                    errors.append({"step": step, "kind": "finish_before_submit"})
                    break
                if action.get("action") == "invalid":
                    errors.append(
                        {"step": step, "kind": "invalid_model_action", "response": reply.text}
                    )
                    continue
                try:
                    executor.execute(action, phase="prefix_action")
                    action_prefix.append(action)
                except Exception as exc:
                    errors.append(
                        {"step": step, "kind": "action_failure", "error": str(exc), "action": action}
                    )
            else:
                errors.append({"step": max_model_calls, "kind": "prefix_model_call_limit"})
        except Exception as exc:
            errors.append(
                {
                    "step": step,
                    "kind": "prefix_runtime_failure",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        after = line_count(submission_path)
        if after != receipt_count_before:
            errors.append(
                {
                    "step": step,
                    "kind": "unexpected_submission_before_checkpoint",
                    "submission_count_before": receipt_count_before,
                    "submission_count_after": after,
                }
            )
            checkpoint = None
        if checkpoint is not None:
            write_json(prefix_dir / "checkpoint.json", checkpoint.to_dict())
    finally:
        try:
            page.close()
        except Exception as exc:
            errors.append(
                {
                    "step": step,
                    "kind": "prefix_page_close_failure",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    result = {
        "checkpoint_reached": checkpoint is not None,
        "submission_count_before": receipt_count_before,
        "submission_count_after_capture": line_count(submission_path),
        "executed_prefix": action_prefix,
        "pending_proposal": checkpoint.pending_proposal if checkpoint else None,
        "errors": errors,
        "executor_receipts": executor.receipts,
    }
    write_json(prefix_dir / "prefix_result.json", result)
    return checkpoint, result


def _write_unit_online_result(unit_dir: Path, value: dict[str, Any]) -> None:
    write_json(unit_dir / "result.json", value)


def _close_unit_page(page: Any, online_result: dict[str, Any], unit_dir: Path) -> None:
    """Close cleanup without overriding an already determined terminal result."""

    try:
        page.close()
    except Exception as exc:
        close_error = f"{type(exc).__name__}: {exc}"
        if online_result:
            online_result["page_close_error"] = close_error
            try:
                _write_unit_online_result(unit_dir, online_result)
            except Exception:
                pass


def _submission_status(
    *,
    receipt: dict[str, Any] | None,
    duplicate_receipts: list[dict[str, Any]],
    submit_error: str,
    confirmation_error: str,
    screenshot_error: str,
) -> str:
    if duplicate_receipts:
        return "duplicate_submission_error"
    if receipt and (submit_error or confirmation_error or screenshot_error):
        return "submitted_acknowledgement_error"
    return "submitted" if receipt else "submit_not_observed"


def replay_and_run_unit(
    *,
    browser: Any,
    base_url: str,
    task_alias: str,
    checkpoint: Checkpoint,
    strategy: str,
    model: RecordedModel,
    ledger: BudgetLedger,
    run_root: Path,
    unit_dir: Path,
    submission_path: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    executor = BrowserExecutor(page, ledger=ledger, task_alias=task_alias)
    policy_result: PolicyResult | None = None
    receipt: dict[str, Any] | None = None
    duplicate_receipts: list[dict[str, Any]] = []
    online_result: dict[str, Any] = {}
    try:
        executor.navigate(f"{base_url}/task/{task_alias}", phase="replay_start")
        for action in checkpoint.visible_action_prefix:
            executor.execute(action, phase="replay_prefix")
        restored_state = capture_state(page)
        restored_shot = unit_dir / "screenshots" / "restored.png"
        restored_shot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(restored_shot), full_page=True)
        original_shot = run_root / checkpoint.current_screenshot
        replay = {
            "state_equal": canonical_state(restored_state) == canonical_state(checkpoint.current_state),
            "original_state_digest": state_digest(checkpoint.current_state),
            "restored_state_digest": state_digest(restored_state),
            "restored_state": restored_state,
            "screenshot_equal": file_sha256(original_shot) == file_sha256(restored_shot),
            "original_screenshot_sha256": file_sha256(original_shot),
            "restored_screenshot_sha256": file_sha256(restored_shot),
            "executor_receipts": executor.receipts,
        }
        write_json(unit_dir / "replay.json", replay)
        if not replay["state_equal"] or not replay["screenshot_equal"]:
            online_result = {
                "status": "unsupported_replay_mismatch",
                "strategy": strategy,
                "submission_observed": False,
                "replay": replay,
            }
            _write_unit_online_result(unit_dir, online_result)
            return online_result, None
        calls_before = ledger.model_calls
        policy_result = run_policy(
            strategy,
            checkpoint,
            model=model,
            artifact_root=run_root,
            unit_dir=unit_dir,
        )
        if ledger.model_calls - calls_before > 3:
            raise RuntimeError("verification policy exceeded three model calls")
        original_proposal_status = "pending"
        revision_receipt: dict[str, Any] | None = None
        if policy_result.changed:
            original_proposal_status = "cancelled_for_visible_revision"
            revision_receipt = executor.execute(
                {
                    "action": "select_option",
                    "select_name": "primary_action",
                    "option_text": policy_result.recommended_option,
                },
                phase="revision_action",
            )
        state_before_submit = capture_state(page)
        selected_before_submit = current_selection(state_before_submit)
        offset = line_count(submission_path)
        submit_error = ""
        try:
            # A submit is irreversible.  Do not blindly repeat it if POST committed
            # but the browser failed while waiting for the redirect/acknowledgement.
            submit_receipt = executor.execute(
                checkpoint.pending_proposal, phase="final_submit", max_attempts=1
            )
        except Exception as exc:
            submit_error = f"{type(exc).__name__}: {exc}"
            submit_receipt = executor.receipts[-1] if executor.receipts else None
        new_receipts = read_rows_after(submission_path, offset)
        if len(new_receipts) == 1:
            receipt = new_receipts[0]
        elif len(new_receipts) > 1:
            duplicate_receipts = new_receipts
        elif submit_error:
            raise RuntimeError(submit_error)
        confirmation_error = ""
        try:
            confirmation_path = capture_state(page)["url_path"]
            confirmation_observed = confirmation_path.endswith("/confirmation")
            if not confirmation_observed:
                confirmation_error = (
                    f"confirmation_path_not_observed: {confirmation_path}"
                )
        except Exception as exc:
            confirmation_observed = False
            confirmation_error = f"{type(exc).__name__}: {exc}"
        final_shot = unit_dir / "screenshots" / "after_submit.png"
        screenshot_error = ""
        try:
            page.screenshot(path=str(final_shot), full_page=True)
        except Exception as exc:
            screenshot_error = f"{type(exc).__name__}: {exc}"
        status = _submission_status(
            receipt=receipt,
            duplicate_receipts=duplicate_receipts,
            submit_error=submit_error,
            confirmation_error=confirmation_error,
            screenshot_error=screenshot_error,
        )
        if not policy_result.changed:
            original_proposal_status = "executed" if receipt else "execution_not_confirmed"
        online_result = {
            "status": status,
            "strategy": strategy,
            "policy": policy_result.to_dict(),
            "original_proposal": {
                "action": checkpoint.pending_proposal,
                "status": original_proposal_status,
            },
            "revision_action": revision_receipt,
            "executed_submission": submit_receipt,
            "post_commit_acknowledgement_error": (
                submit_error if receipt or duplicate_receipts else ""
            ),
            "confirmation_observation_error": confirmation_error,
            "after_submit_screenshot_error": screenshot_error,
            "selected_before_submit": selected_before_submit,
            "submission_observed": receipt is not None or bool(duplicate_receipts),
            "submission_receipt_count": (
                len(duplicate_receipts) if duplicate_receipts else int(receipt is not None)
            ),
            "submission_receipt_public": receipt,
            "duplicate_submission_receipts_public": duplicate_receipts,
            "confirmation_observed": confirmation_observed,
            "executor_receipts": executor.receipts,
        }
        _write_unit_online_result(unit_dir, online_result)
        return online_result, receipt
    except Exception as exc:
        online_result = {
            "status": "unit_error",
            "strategy": strategy,
            "submission_observed": receipt is not None or bool(duplicate_receipts),
            "submission_receipt_count": (
                len(duplicate_receipts) if duplicate_receipts else int(receipt is not None)
            ),
            "submission_receipt_public": receipt,
            "duplicate_submission_receipts_public": duplicate_receipts,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "policy": policy_result.to_dict() if policy_result else None,
            "executor_receipts": executor.receipts,
        }
        _write_unit_online_result(unit_dir, online_result)
        return online_result, receipt
    finally:
        _close_unit_page(page, online_result, unit_dir)


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")


def run_smoke(args: argparse.Namespace) -> Path:
    profile = getattr(args, "profile", "stage-two")
    task_slugs = selected_task_slugs(args)
    if args.max_model_calls > 160 or args.max_browser_transitions > 800:
        raise ValueError("requested budgets exceed the authorized 160-call/800-transition ceiling")
    if args.prefix_max_model_calls > 12:
        raise ValueError("prefix model-call limit cannot exceed 12")
    run_root = args.output_root / (args.run_id or _run_id())
    if run_root.exists():
        raise FileExistsError(f"run directory already exists: {run_root}")

    # Everything below can reject the run before an episode begins.  Complete
    # these checks before creating run_root so an invalid task or unavailable
    # endpoint cannot leave an unfinalized, non-reusable run directory behind.
    ledger = BudgetLedger(
        max_model_calls=args.max_model_calls,
        max_browser_transitions=args.max_browser_transitions,
    )
    if args.mode == "mock":
        backend = ScriptedMockBackend()
        real_smoke_status = "not_run_no_authorized_active_local_model_service"
    else:
        if not args.local_model_url:
            raise ValueError("--local-model-url is required for live-local mode")
        backend = LocalQwenServiceBackend(
            server_url=args.local_model_url,
            model_name=args.local_model_name,
            max_output_tokens=args.max_output_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            seed=args.seed,
        )
        real_smoke_status = "running_live_local_model"
    model = RecordedModel(backend, ledger=ledger)
    selected: dict[str, dict[str, dict[str, Any]]] = {}
    invariant_audit: list[dict[str, Any]] = []
    for slug in task_slugs:
        selected[slug] = {
            condition: find_task(task_spec_path(condition, slug), slug)
            for condition in CONDITION_FILES
        }
        differences = pair_invariant_differences(
            selected[slug]["official140"], selected[slug]["clean140"]
        )
        invariant_audit.append({"task_slug": slug, "different_non_chart_fields": differences})
        if differences:
            raise RuntimeError(
                f"development pair {slug} is not a chart-only pair; differing fields: {differences}"
            )
    run_root.mkdir(parents=True, exist_ok=False)
    runtime_extra_paths: list[Path] = [
        task_spec_path(condition, slug)
        for slug in task_slugs for condition in CONDITION_FILES
    ]
    for slug in task_slugs:
        for condition in ("official140", "clean140"):
            chart_relative = str(
                (selected[slug][condition].get("chart_asset") or {}).get("figure_path") or ""
            )
            chart_path = (REPOSITORY_ROOT / chart_relative).resolve()
            if chart_path.is_file():
                runtime_extra_paths.append(chart_path)
    if args.mode == "live-local":
        runtime_extra_paths.extend(
            [
                REPOSITORY_ROOT / "adversarial_pipeline" / "llm_client.py",
                REPOSITORY_ROOT / "web_agent_benchmark" / "evaluation" / "qwen3_vl_server.py",
            ]
        )
    runtime_extra = tuple(sorted(set(path.resolve() for path in runtime_extra_paths)))
    start_fingerprint = source_fingerprint(runtime_extra)
    run_config = {
        "profile": profile,
        "mode": args.mode,
        "task_slugs": list(task_slugs),
        "conditions": ["official140", "clean140"],
        "strategies": list(STRATEGIES),
        "model": model.metadata,
        "max_model_calls": args.max_model_calls,
        "max_browser_transitions": args.max_browser_transitions,
        "prefix_max_model_calls": args.prefix_max_model_calls,
        "browser_executable": args.browser_executable,
        "local_model_url": args.local_model_url,
        "local_model_name": args.local_model_name,
        "max_output_tokens": args.max_output_tokens,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "seed": args.seed,
        "viewport": [1440, 1100],
        "browser_launch_args": list(BROWSER_LAUNCH_ARGS),
    }
    config_canonical = json.dumps(
        run_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    config_sha256 = hashlib.sha256(config_canonical.encode("utf-8")).hexdigest()
    snapshot_rows = snapshot_runtime_sources(
        start_fingerprint,
        destination=run_root / "evaluator" / "runtime_source_snapshot",
    )
    write_json(
        run_root / "evaluator" / "run_start.json",
        {
            "integrity_schema_version": 2,
            "started_at": utc_now(),
            "run_config": run_config,
            "run_config_sha256": config_sha256,
            "source_fingerprint": start_fingerprint,
            "runtime_source_snapshot": snapshot_rows,
            "budget_ledger_path": "budget.json",
        },
    )
    ledger.bind_snapshot(run_root / "budget.json")
    write_json(run_root / "evaluator" / "pair_invariant_audit.json", invariant_audit)
    unit_map: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    prefix_rows: list[dict[str, Any]] = []
    unit_ordinal = 0
    prefix_ordinal = 0
    schedule: list[dict[str, Any]] = []
    for slug in task_slugs:
        task_alias = DEFAULT_ALIASES.get(slug, f"dev{task_slugs.index(slug) + 1:02d}")
        for condition in ("official140", "clean140"):
            prefix_ordinal += 1
            prefix_id = f"prefix_{prefix_ordinal:04d}"
            mappings: list[dict[str, Any]] = []
            for strategy in STRATEGIES:
                unit_ordinal += 1
                mapping = {
                    "unit_id": f"unit_{unit_ordinal:04d}",
                    "prefix_id": prefix_id,
                    "task_slug": slug,
                    "task_alias": task_alias,
                    "condition": condition,
                    "strategy": strategy,
                    "model_mode": args.mode,
                }
                mappings.append(mapping)
                unit_map.append(mapping)
            schedule.append(
                {
                    "prefix_ordinal": prefix_ordinal,
                    "prefix_id": prefix_id,
                    "task_slug": slug,
                    "task_alias": task_alias,
                    "condition": condition,
                    "mappings": mappings,
                }
            )

    run_errors: list[dict[str, str]] = []
    executable: Path | None = None
    preflight_witness: dict[str, Any] = {
        "required": args.mode == "live-local",
        "status": "not_run_mock_mode" if args.mode == "mock" else "not_started",
        "model_calls": 0,
        "http_attempts": 0,
    }
    started_at = utc_now()
    started = time.monotonic()

    def assert_runtime_unchanged(phase: str) -> None:
        current = source_fingerprint(runtime_extra)
        if current.get("tree_sha256") != start_fingerprint.get("tree_sha256"):
            raise RuntimeSourceChanged(
                f"runtime source changed during {phase}; stop and begin a fresh authorized run"
            )

    def retain_unfinished(plan: dict[str, Any], *, kind: str, exc: Exception) -> None:
        error = {"kind": kind, "error_type": type(exc).__name__, "error": str(exc)}
        run_errors.append({"prefix_id": str(plan["prefix_id"]), **error})
        existing_prefix = next(
            (row for row in prefix_rows if row.get("prefix_id") == plan["prefix_id"]), None
        )
        if existing_prefix is None:
            prefix_result = {
                "checkpoint_reached": False,
                "submission_count_before": 0,
                "submission_count_after_capture": 0,
                "executed_prefix": [],
                "pending_proposal": None,
                "errors": [error],
                "executor_receipts": [],
            }
            prefix_rows.append(
                {
                    "prefix_id": plan["prefix_id"],
                    "task_slug": plan["task_slug"],
                    "condition": plan["condition"],
                    "checkpoint_reached": False,
                    "prefix_result": prefix_result,
                }
            )
            write_json(
                run_root / "online" / "prefixes" / plan["prefix_id"] / "prefix_result.json",
                prefix_result,
            )
        else:
            existing_prefix.setdefault("outer_errors", []).append(error)
        scored = {str(row.get("unit_id")) for row in score_rows}
        for mapping in plan["mappings"]:
            if mapping["unit_id"] in scored:
                continue
            unit_dir = run_root / "online" / "units" / mapping["unit_id"]
            result_path = unit_dir / "result.json"
            if result_path.is_file():
                online_result = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                online_result = {
                    "status": "not_run_prefix_or_shell_failure",
                    "strategy": mapping["strategy"],
                    "submission_observed": False,
                    "prefix_failure_in_denominator": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                _write_unit_online_result(unit_dir, online_result)
            public_receipt = online_result.get("submission_receipt_public")
            retained_receipt = (
                public_receipt
                if online_result.get("submission_observed") is True
                and isinstance(public_receipt, dict)
                else None
            )
            terminal_score = (
                score_receipt(
                    selected[str(plan["task_slug"])][str(plan["condition"])],
                    retained_receipt,
                )
                if retained_receipt
                else None
            )
            score_rows.append(
                mapping
                | {
                    "terminal_score": terminal_score,
                    "online_status": online_result.get("status"),
                    "selected_option_label": (
                        str(retained_receipt.get("selected_option_label") or "")
                        if retained_receipt
                        else ""
                    ),
                    "exclusion_reason": (
                        "" if terminal_score else f"{kind}:{type(exc).__name__}"
                    ),
                }
            )

    browser: Any | None = None
    try:
        assert_runtime_unchanged("preflight")
        if args.mode == "live-local":
            preflight_witness = {
                "required": True,
                **run_multi_image_witness(model=model, run_root=run_root, seed=args.seed),
            }
            if preflight_witness["status"] != "passed":
                raise RuntimeError("ordered two-image preflight witness failed")
        sync_playwright = require_playwright()
        executable = browser_executable(args.browser_executable)
        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": list(BROWSER_LAUNCH_ARGS),
            }
            if executable:
                launch_kwargs["executable_path"] = str(executable)
            browser = playwright.chromium.launch(**launch_kwargs)
            for plan in schedule:
                assert_runtime_unchanged(f"before_{plan['prefix_id']}")
                slug = str(plan["task_slug"])
                task_alias = str(plan["task_alias"])
                condition = str(plan["condition"])
                raw_task = selected[slug][condition]
                prefix_id = str(plan["prefix_id"])
                prefix_dir = run_root / "online" / "prefixes" / prefix_id
                submission_path = (
                    run_root
                    / "server_receipts"
                    / f"receipts_{int(plan['prefix_ordinal']):04d}.jsonl"
                )
                try:
                    bundle = build_shell_bundle(
                        raw_task, task_alias=task_alias, repository_root=REPOSITORY_ROOT
                    )
                    with managed_shell(
                        bundle.public_task, bundle.chart_path, submission_path
                    ) as shell:
                        checkpoint, prefix_result = generate_checkpoint(
                            browser=browser,
                            base_url=shell.base_url,
                            task_alias=task_alias,
                            user_goal=bundle.public_task["user_goal"],
                            model=model,
                            ledger=ledger,
                            run_root=run_root,
                            prefix_dir=prefix_dir,
                            submission_path=submission_path,
                            max_model_calls=args.prefix_max_model_calls,
                        )
                        prefix_rows.append(
                            {
                                "prefix_id": prefix_id,
                                "task_slug": slug,
                                "condition": condition,
                                "checkpoint_reached": bool(checkpoint),
                                "prefix_result": prefix_result,
                            }
                        )
                        for mapping in plan["mappings"]:
                            assert_runtime_unchanged(f"before_{mapping['unit_id']}")
                            strategy = str(mapping["strategy"])
                            unit_dir = run_root / "online" / "units" / mapping["unit_id"]
                            if checkpoint is None:
                                online_result = {
                                    "status": "not_run_no_checkpoint",
                                    "strategy": strategy,
                                    "submission_observed": False,
                                    "prefix_failure_in_denominator": True,
                                }
                                _write_unit_online_result(unit_dir, online_result)
                                score_rows.append(
                                    mapping
                                    | {
                                        "terminal_score": None,
                                        "online_status": online_result["status"],
                                        "selected_option_label": "",
                                        "exclusion_reason": "no_before_submit_checkpoint",
                                    }
                                )
                                continue
                            online_result, receipt = replay_and_run_unit(
                                browser=browser,
                                base_url=shell.base_url,
                                task_alias=task_alias,
                                checkpoint=checkpoint,
                                strategy=strategy,
                                model=model,
                                ledger=ledger,
                                run_root=run_root,
                                unit_dir=unit_dir,
                                submission_path=submission_path,
                            )
                            terminal_score = score_receipt(raw_task, receipt) if receipt else None
                            score_rows.append(
                                mapping
                                | {
                                    "terminal_score": terminal_score,
                                    "online_status": online_result["status"],
                                    "selected_option_label": (
                                        receipt.get("selected_option_label") if receipt else ""
                                    ),
                                    "exclusion_reason": "" if terminal_score else online_result["status"],
                                }
                            )
                            assert_runtime_unchanged(f"after_{mapping['unit_id']}")
                except Exception as exc:
                    kind = (
                        "runtime_source_changed"
                        if isinstance(exc, RuntimeSourceChanged)
                        else "prefix_or_shell_runtime_failure"
                    )
                    retain_unfinished(plan, kind=kind, exc=exc)
                    if isinstance(exc, RuntimeSourceChanged):
                        raise
            browser.close()
            browser = None
        assert_runtime_unchanged("finalization")
    except Exception as exc:
        run_errors.append(
            {"prefix_id": "", "kind": "runner_startup_or_browser_failure", "error_type": type(exc).__name__, "error": str(exc)}
        )
        completed_prefix_ids = {str(row.get("prefix_id")) for row in prefix_rows}
        for plan in schedule:
            if plan["prefix_id"] not in completed_prefix_ids:
                retain_unfinished(plan, kind="runner_startup_or_browser_failure", exc=exc)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:
                run_errors.append(
                    {"prefix_id": "", "kind": "browser_close_failure", "error_type": type(exc).__name__, "error": str(exc)}
                )
    elapsed = time.monotonic() - started
    prefix_rows.sort(key=lambda row: str(row.get("prefix_id")))
    score_rows.sort(key=lambda row: str(row.get("unit_id")))
    for row in unit_map:
        append_jsonl(run_root / "evaluator" / "unit_map.jsonl", row)
    for row in score_rows:
        append_jsonl(run_root / "evaluator" / "scores.jsonl", row)
    for row in prefix_rows:
        append_jsonl(run_root / "evaluator" / "prefixes.jsonl", row)
    write_json(run_root / "budget.json", ledger.to_dict())
    outcomes: dict[str, int] = {}
    for row in score_rows:
        score = row.get("terminal_score") or {}
        name = str(score.get("outcome") or row.get("exclusion_reason") or "unknown")
        outcomes[name] = outcomes.get(name, 0) + 1
    submitted_units = sum(
        str(row.get("online_status") or "")
        in {"submitted", "submitted_acknowledgement_error"}
        and row.get("terminal_score") is not None
        for row in score_rows
    )
    score_by_unit = {str(row.get("unit_id")): row for row in score_rows}
    completed_chain_units = 0
    for mapping in unit_map:
        unit_id = str(mapping["unit_id"])
        result_path = run_root / "online" / "units" / unit_id / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
        score_row = score_by_unit.get(unit_id) or {}
        completed_chain_units += int(completed_chain_unit(result, score_row))
    if args.mode == "live-local":
        real_smoke_status = (
            "completed_chain_smoke"
            if completed_chain_units == len(unit_map) and len(unit_map) > 0
            else "attempted_incomplete_chain_smoke"
        )
    end_fingerprint = source_fingerprint(runtime_extra)
    run_manifest = {
        "run_id": run_root.name,
        "started_at": started_at,
        "completed_at": utc_now(),
        "elapsed_seconds": round(elapsed, 3),
        "stage": "clear_rule_development_probe" if profile == "clear-rule-probe" else "stage_two_smoke",
        "profile": profile,
        "model": model.metadata,
        "model_mode": args.mode,
        "preflight_multi_image_witness": preflight_witness,
        "real_model_smoke_status": real_smoke_status,
        "real_model_chain_exercised": args.mode == "live-local",
        "task_count": len(task_slugs),
        "conditions": ["official140", "clean140"],
        "strategies": list(STRATEGIES),
        "configured_units": len(unit_map),
        "completed_units": len(score_rows),
        "submitted_units": submitted_units,
        "completed_chain_units": completed_chain_units,
        "checkpoint_count": sum(1 for row in prefix_rows if row["checkpoint_reached"]),
        "outcome_counts": outcomes,
        "run_errors": run_errors,
        "run_status": "completed" if not run_errors else "completed_with_retained_errors",
        "budget": {
            "model_calls": ledger.model_calls,
            "model_call_limit": ledger.max_model_calls,
            "browser_transitions": ledger.browser_transitions,
            "browser_transition_limit": ledger.max_browser_transitions,
        },
        "browser": {
            "engine": "chromium/playwright",
            "executable": str(executable) if executable else "playwright-managed",
            "viewport": [1440, 1100],
            "launch_args": list(BROWSER_LAUNCH_ARGS),
        },
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "integrity_schema_version": 2,
        "run_config_sha256": config_sha256,
        "runtime_source_unchanged": (
            end_fingerprint.get("tree_sha256") == start_fingerprint.get("tree_sha256")
        ),
        "code_fingerprint": start_fingerprint,
        "end_code_fingerprint": end_fingerprint,
        "runtime_source_snapshot": "evaluator/runtime_source_snapshot",
        "git_status": git_revision_status(),
        "research_interpretation_allowed": False,
        "smoke_purpose": (
            "exploratory case-level natural error/recovery inspection on previously used development tasks; "
            "not a confirmatory or population-level research hypothesis test"
            if profile == "clear-rule-probe" and args.mode == "live-local"
            else "engineering chain validation only; not a research hypothesis test"
        ),
        "case_level_inspection_allowed": profile == "clear-rule-probe" and args.mode == "live-local",
    }
    write_json(run_root / "run_manifest.json", run_manifest)
    return run_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "live-local"], default="mock")
    parser.add_argument("--profile", choices=list(TASK_PROFILES), default="stage-two")
    parser.add_argument("--tasks", default=",".join(DEFAULT_DEV_TASKS))
    parser.add_argument("--output-root", type=Path, default=PACKAGE_ROOT / "runs")
    parser.add_argument("--run-id")
    parser.add_argument("--max-model-calls", type=int, default=160)
    parser.add_argument("--max-browser-transitions", type=int, default=800)
    parser.add_argument("--prefix-max-model-calls", type=int, default=12)
    parser.add_argument("--browser-executable")
    parser.add_argument("--local-model-url")
    parser.add_argument("--local-model-name", default="qwen3_vl")
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=12345)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_root = run_smoke(args)
    print(run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
