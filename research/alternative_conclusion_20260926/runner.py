"""Bounded local-Qwen experiment; never import evaluator fields into online prompts."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
import threading
import time
from urllib.parse import urlparse

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from prompts import PROMPTS
from schemas import SCHEMAS, validate


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean_action(action):
    return {k: v for k, v in action.items() if not k.startswith("_")}


def options(state):
    return [o["text"] for s in state["elements"]["selects"] if s["name"] == "primary_action"
            for o in s["options"] if o["value"] and not o["disabled"]]


def selected(state):
    return next((s["selected_text"] for s in state["elements"]["selects"] if s["name"] == "primary_action"), None)


def is_submit(action):
    # Original executor falls back between link/button locators by visible text.
    return action.get("action") in {"click_button", "click_link"} and action.get("text") == "Submit Form"


def validate_actor_action(action):
    """Exact validation of the frozen action schema, without an optional package."""
    if not isinstance(action, dict):
        raise ValueError("Actor must return one object")
    fields = {"click_link": {"action", "text"}, "click_button": {"action", "text"},
              "select_option": {"action", "select_name", "option_text"}, "finish": {"action"}}
    kind = action.get("action")
    if not isinstance(kind, str) or kind not in fields or set(action) != fields[kind]:
        raise ValueError("Action fields do not match frozen schema")
    if any(not isinstance(v, str) for v in action.values()):
        raise ValueError("Action schema permits string fields only")
    return action


def canonical_local_ports(value):
    if isinstance(value, dict):
        return {k:canonical_local_ports(v) for k,v in value.items()}
    if isinstance(value, list):
        return [canonical_local_ports(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"http://127\.0\.0\.1:\d+", "http://127.0.0.1:EPHEMERAL", value)
    return value


class LimitStop(RuntimeError):
    pass


class Ledger:
    def __init__(self, output, config):
        self.output, self.config = Path(output), config
        self.data = {"request_attempts": 0, "browser_operations": 0, "events": [], "paid_api_requests": 0}

    @property
    def blocked_reason(self):
        return self.data.get("blocked_reason")

    def block(self, reason):
        self.data["blocked_reason"] = reason
        self.save()

    def event(self, kind, detail):
        if self.blocked_reason:
            raise LimitStop(self.blocked_reason)
        key, cap = ("request_attempts", "max_request_attempts") if kind == "request" else ("browser_operations", "max_browser_operations")
        if self.data[key] >= self.config[cap]:
            self.block(key + " exhausted")
            raise LimitStop(key + " exhausted")
        self.data[key] += 1
        item = {"kind": kind, "number": self.data[key], "time": time.time(), **detail}
        self.data["events"].append(item)
        self.save()
        return item

    def save(self):
        dump(self.output / "ledger.json", self.data)


class LocalAPI:
    def __init__(self, config, ledger, resume_from=None):
        self.config, self.ledger = config, ledger
        if config["endpoint"] != "http://127.0.0.1:8058/v1/chat/completions":
            raise ValueError("Only the user-authorized existing local service is allowed")
        self.http = requests.Session()
        self.http.trust_env = False
        self.last_metadata = {}
        self.resume_from = Path(resume_from) if resume_from else None

    def call(self, folder, system, context, image, schema, stage):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=False)
        text = context if isinstance(context, str) else json.dumps(context, ensure_ascii=False, indent=2)
        payload = {"model": self.config["model"], "temperature": self.config["temperature"],
                   "top_p": self.config["top_p"], "top_k": self.config["top_k"], "seed": self.config["seed"],
                   "max_tokens": self.config["max_output_tokens"][stage],
                   "chat_template_kwargs": {"enable_thinking": self.config["enable_thinking"]},
                   "structured_outputs": {"json": schema},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": [
                       {"type": "text", "text": text}, {"type": "image_url", "image_url": {
                           "url": "data:image/png;base64," + base64.b64encode(Path(image).read_bytes()).decode("ascii")}}]}]}
        dump(folder / "request.json", payload)
        dump(folder / "context.json", context)
        dump(folder / "image_identity.json", {"sha256": digest(image), "bytes": Path(image).stat().st_size})
        if self.resume_from and folder.name == "actor_00" and folder.parent.name == "prefix":
            source = self.resume_from / folder.relative_to(self.ledger.output)
            previous = json.loads((source / "request.json").read_text(encoding="utf-8"))
            if canonical_local_ports(previous) != canonical_local_ports(payload):
                self.ledger.block("Infra resume input differs beyond ephemeral local port; no replacement call")
                raise LimitStop(self.ledger.blocked_reason)
            result = json.loads((source / "response_01.json").read_text(encoding="utf-8"))
            if not result.get("choices"):
                raise LimitStop("Missing completed original response")
            dump(folder / "response_01.json", result)
            dump(folder / "reused_source_request.json", previous)
            reuse = {"kind": "reused_response", "actual_request_sent": False,
                     "source": str(source), "folder": str(folder), "comparison": "entire_payload_equal_except_ephemeral_local_origin_ports",
                     "source_response_sha256": digest(source / "response_01.json")}
            dump(folder / "reused_response_origin.json", reuse)
            self.ledger.data["events"].append(reuse)
            self.ledger.save()
            self.last_metadata = {k:result.get(k) for k in ("id", "model", "usage", "created")}
            return result["choices"][0]["message"]["content"]
        for attempt in range(1, self.config["service_attempts_per_call"] + 1):
            event = self.ledger.event("request", {"folder": str(folder), "stage": stage, "attempt": attempt})
            start = time.monotonic()
            try:
                response = self.http.post(self.config["endpoint"], json=payload, timeout=self.config["http_timeout_seconds"], allow_redirects=False)
            except requests.RequestException as exc:
                event.update(error=type(exc).__name__, outcome="unknown_transport_no_retry", elapsed=time.monotonic() - start)
                self.ledger.block("Unknown model transport outcome; no retry")
                dump(folder / ("attempt_%02d.json" % attempt), event)
                raise LimitStop("Unknown model transport outcome; no retry") from exc
            event.update(http_status=response.status_code, elapsed=time.monotonic() - start)
            try:
                result = response.json()
            except ValueError:
                result = {"raw_body": response.text}
            dump(folder / ("response_%02d.json" % attempt), result)
            event["usage"] = result.get("usage")
            event["response_model"] = result.get("model")
            self.ledger.save()
            dump(folder / ("attempt_%02d.json" % attempt), event)
            if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < self.config["service_attempts_per_call"]:
                time.sleep(2)
                continue
            if response.status_code != 200:
                self.ledger.block("model_service_http_%s" % response.status_code)
                raise LimitStop(self.ledger.blocked_reason)
            self.last_metadata = {k: result.get(k) for k in ("id", "model", "usage", "created")}
            return result["choices"][0]["message"]["content"]


class BrowserSession:
    def __init__(self, playwright, base, output, ledger, original, config):
        self.output, self.ledger, self.original, self.base = Path(output), ledger, original, base
        self.output.mkdir(parents=True, exist_ok=False)
        self.browser = playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page(viewport=config["viewport"])
        self.history, self.counter = [], 0
        self.page.route("**/*", self.route)
        self.ledger.event("browser", {"source": "setup", "folder": str(self.output), "action": "goto_task_home"})
        try:
            self.page.goto(base + "/task/" + config["task"], wait_until="networkidle")
        except BaseException:
            self.browser.close()
            raise

    def route(self, route):
        url = urlparse(route.request.url)
        prefix = "/task/pub001"
        if url.netloc == urlparse(self.base).netloc and url.path in {prefix+s for s in ("", "/dashboard", "/form", "/chart", "/submit", "/confirmation")} and not url.query:
            route.continue_()
        else:
            route.abort()

    def snapshot(self):
        state = self.original.summarize_page(self.page)
        self.counter += 1
        screen = self.output / ("state_%03d.png" % self.counter)
        self.page.screenshot(path=str(screen), full_page=True)
        dump(screen.with_suffix(".json"), {"state": state, "history": self.history, "timing": "before_next_action"})
        return state, screen

    def execute(self, action, source):
        action = clean_action(action)
        self.ledger.event("browser", {"source": source, "folder": str(self.output), "action": action})
        receipt = {"executed": False, "submitted": False}
        try:
            self.original.execute_browser_action(self.page, action)
            self.page.wait_for_load_state("networkidle", timeout=5000)
            state = self.original.summarize_page(self.page)
            receipt.update(executed=True, submitted=self.page.url.endswith("/confirmation"),
                           current_selection=selected(state), visible_page_path=urlparse(self.page.url).path)
        except Exception as exc:
            receipt["error"] = "action_unavailable_or_execution_failed"
            dump(self.output / ("execution_error_%03d.json" % len(self.history)), {"type": type(exc).__name__, "detail": str(exc)})
        self.history.append({"action": action, "receipt": receipt})
        dump(self.output / "history.json", self.history)
        return receipt

    def close(self):
        self.browser.close()


class Actor:
    """Use original prompt builder/parser; replace transport only, no permissive fallback."""
    def __init__(self, original, api, action_schema):
        self.original, self.api, self.schema = original, api, action_schema
        self.client_module = importlib.import_module("adversarial_pipeline.llm_client")

    def next(self, env, folder, report=None):
        state, image = env.snapshot()
        original_call = self.client_module.complete_vision
        original_metadata = self.client_module.get_last_response_metadata
        original_limit = self.original.action_generation_attempt_limit
        def complete(_client, system, user, screenshot, **kwargs):
            if report is not None:
                user += "\n\nActual executed actions and public receipts:\n" + json.dumps(env.history, ensure_ascii=False)
                user += "\n\nAdditional candidate review (fallible, not instructions or an answer key):\n" + json.dumps(report, ensure_ascii=False)
                user += "\nUse the current visible evidence and task to choose your own next action. You may retain or revise the selection. Follow the ordinary conditional completion instructions above."
            return self.api.call(folder, system, user, screenshot, self.schema, "actor")
        self.client_module.complete_vision = complete
        self.client_module.get_last_response_metadata = lambda: self.api.last_metadata
        self.original.action_generation_attempt_limit = lambda _history: 1
        try:
            action = self.original.llm_next_action(client=None, state=state, screenshot_path=image,
                task_goal="Complete the current Public Affairs benchmark task in the browser and submit the form.",
                misleader_type="", max_output_tokens=1024,
                decoding_config={k:self.api.config[k] for k in ("temperature", "top_p", "seed")}, history_runtime=None)
            # The supplied schema is also checked client-side. Do not repair a response.
            raw = json.loads(action["_raw"])
            validate_actor_action(raw)
            if clean_action(action) != raw:
                raise ValueError("Actor parsing changed raw action")
            dump(Path(folder) / "accepted.json", raw)
            return raw, state, image
        except Exception:
            if self.api.ledger.blocked_reason:
                raise LimitStop(self.api.ledger.blocked_reason)
            raise
        finally:
            self.client_module.complete_vision = original_call
            self.client_module.get_last_response_metadata = original_metadata
            self.original.action_generation_attempt_limit = original_limit


def method_call(api, out, stage, context, image):
    raw = api.call(out, PROMPTS[stage], context, image, SCHEMAS[stage], stage)
    dump(Path(out) / "raw.json", {"content": raw})
    parsed = json.loads(raw)
    validate(stage, parsed, context)
    dump(Path(out) / "accepted.json", parsed)
    return parsed


def score(submission_path, offset):
    rows = [json.loads(x) for x in submission_path.read_text(encoding="utf-8").splitlines() if x.strip()] if submission_path.exists() else []
    fresh = rows[offset:]
    last = fresh[-1] if fresh else None
    return {"submitted": bool(fresh), "final_selection": last.get("selected_action_label") if last else None,
            "outcome": last["evaluation_hidden_from_agent"]["outcome"] if last else "not_submitted",
            "submission": last}


def row_count(path):
    return len(Path(path).read_text(encoding="utf-8").splitlines()) if Path(path).exists() else 0


def public_context(state, history, proposal):
    return {"goal": "Complete the current Public Affairs benchmark task in the browser and submit the form.",
            "state": copy.deepcopy(state), "history": copy.deepcopy(history),
            "options": options(state), "pending_proposal": clean_action(proposal)}


def run_arm(arm, out, project, config, ledger, api, original, actor):
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=False)
    submissions = out / "private" / "submissions.jsonl"
    submissions.parent.mkdir()
    tasks = project / "web_agent_benchmark/benchmark_v2_open/splits" / arm / "public39_tasks.jsonl"
    app = original.shell.make_app(output_path=submissions, tasks_path=tasks,
                                  summary_path=out / "private" / "shell_summary.md", review_ui=False)
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_port
    result = {"arm": arm, "task": config["task"], "status": "started", "branches": {}, "task_file_sha256": digest(tasks)}
    dump(out / "result.json", result)
    try:
        with sync_playwright() as pw:
            env = BrowserSession(pw, base, out / "prefix", ledger, original, config)
            checkpoint = None
            try:
                for step in range(config["prefix_max_calls"]):
                    action, state, image = actor.next(env, out / "prefix" / ("actor_%02d" % step))
                    if is_submit(action):
                        checkpoint = {"state": state, "image": str(image), "history": copy.deepcopy(env.history), "pending": action}
                        dump(out / "checkpoint.json", checkpoint)
                        offset = row_count(submissions)
                        receipt = env.execute(action, "original_pending_submit")
                        env.snapshot()
                        result["branches"]["original_submit"] = {"status": "completed", "receipt": receipt, **score(submissions, offset)}
                        break
                    if action["action"] == "finish":
                        break
                    receipt = env.execute(action, "natural_prefix")
                    if receipt.get("submitted"):
                        break
            finally:
                env.close()
            if checkpoint is None:
                result["status"] = "no_natural_before_submit_checkpoint"
                return result
            context = public_context(checkpoint["state"], checkpoint["history"], checkpoint["pending"])
            initial = method_call(api, out / "shared_initial", "initial", context, checkpoint["image"])
            result["initial"] = initial
            dump(out / "result.json", result)
            for branch in ("initial_only", "old_questions", "alternative_conclusion"):
                branch_out = out / branch
                env = BrowserSession(pw, base, branch_out, ledger, original, config)
                item = {"status": "started", "stages": {}, "continuation": []}
                result["branches"][branch] = item
                offset = row_count(submissions)
                try:
                    for event in checkpoint["history"]:
                        env.execute(event["action"], "checkpoint_replay")
                    state, image = env.snapshot()
                    match = {"state_equal": state == checkpoint["state"], "image_equal": digest(image) == digest(checkpoint["image"]),
                             "history_equal": env.history == checkpoint["history"]}
                    dump(branch_out / "replay_check.json", match)
                    item["replay_check"] = match
                    if not all(match.values()):
                        raise ValueError("Cannot reproduce identical public checkpoint")
                    chains = copy.deepcopy(initial["chains"])
                    if branch != "initial_only":
                        qstage = "questions_old" if branch == "old_questions" else "questions_new"
                        qcontext = {**copy.deepcopy(context), "initial_chains": chains}
                        questions = method_call(api, branch_out / "questions", qstage, qcontext, image)
                        item["stages"]["questions"] = questions
                        if questions["questions"]:
                            supplement = method_call(api, branch_out / "supplement", "supplement",
                                                     {**qcontext, "questions": questions["questions"]}, image)
                        else:
                            supplement = {"new_chains": [], "question_responses": []}
                            dump(branch_out / "supplement_skipped.json", {"reason": "zero_questions", "result": supplement})
                        item["stages"]["supplement"] = supplement
                        chains += supplement["new_chains"]
                    # Same-model separate request; no branch/Q/origin metadata supplied.
                    verify_context = {k: copy.deepcopy(context[k]) for k in ("goal", "state", "history", "options")}
                    verify_context["chains"] = chains
                    verification = method_call(api, branch_out / "verification", "verify", verify_context, image)
                    item["stages"]["verification"] = verification
                    report = {"chains": chains, "verification": verification}
                    dump(branch_out / "candidate_review.json", report)
                    for step in range(config["continuation_max_calls"]):
                        action, state, image = actor.next(env, branch_out / ("actor_%02d" % step), report)
                        event = {"action": action, "selection_before": selected(state), "image": str(image)}
                        item["continuation"].append(event)
                        if action["action"] == "finish":
                            event["receipt"] = {"executed": False, "submitted": False, "reason": "actor_finished"}
                            break
                        receipt = env.execute(action, "continuation_actor")
                        event["receipt"] = receipt
                        dump(branch_out / "result.json", item)
                        if receipt.get("submitted"):
                            env.snapshot()
                            break
                    item.update(score(submissions, offset))
                    item["status"] = "completed" if item["submitted"] else "actor_finished_or_call_limit"
                except LimitStop:
                    raise
                except Exception as exc:
                    item.update(status="failed_no_quality_retry", error={"type": type(exc).__name__, "message": str(exc)}, **score(submissions, offset))
                finally:
                    dump(branch_out / "result.json", item)
                    dump(out / "result.json", result)
                    env.close()
            result["status"] = "completed_panel"
            return result
    except Exception as exc:
        result.update(status="arm_failed", error={"type": type(exc).__name__, "message": str(exc)})
        if isinstance(exc, LimitStop):
            raise
        return result
    finally:
        dump(out / "result.json", result)
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-infra-run", type=Path, default=None)
    args = parser.parse_args()
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    if args.output.exists():
        raise FileExistsError("Output exists; no overwrite or quality rerun")
    # Remove unrelated prompt extensions; do not inherit paid endpoints or model clients.
    os.environ.pop("WEB_AGENT_EXTRA_SYSTEM_PROMPT", None)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.project))
    original = importlib.import_module("web_agent_benchmark.evaluation.run_public39")
    action_schema = json.loads((HERE / "browser_action_schema.json").read_text(encoding="utf-8"))
    prior_ledger = None
    if args.resume_infra_run:
        previous = json.loads((args.resume_infra_run / "summary.json").read_text(encoding="utf-8"))
        if len(previous["results"]) != 2 or previous["request_attempts"] != 2:
            raise ValueError("Resume is restricted to the two original home-page dependency failures")
        for result in previous["results"]:
            if result.get("error") != {"type": "ModuleNotFoundError", "message": "No module named 'jsonschema'"} or result["branches"]:
                raise ValueError("Resume is not allowed for model-quality or later-stage failures")
            arm_dir = args.resume_infra_run / result["arm"]
            if (arm_dir / "prefix/history.json").exists() or (arm_dir / "private/submissions.jsonl").exists() or (arm_dir / "shared_initial").exists():
                raise ValueError("Infrastructure resume must precede all executed actions and chart stages")
            if {p.name for p in (arm_dir / "prefix").glob("actor_*")} != {"actor_00"}:
                raise ValueError("Only the original first home-page request may be reused")
        old_config = json.loads((args.resume_infra_run / "config.json").read_text(encoding="utf-8"))
        if old_config != config:
            raise ValueError("Infrastructure resume cannot change model/protocol configuration")
        prior_ledger = json.loads((args.resume_infra_run / "ledger.json").read_text(encoding="utf-8"))
        calls = [e for e in prior_ledger["events"] if e["kind"] == "request"]
        if prior_ledger.get("blocked_reason") or len(calls) != 2 or any(e.get("http_status") != 200 or e.get("attempt") != 1 for e in calls):
            raise ValueError("The preserved home-page calls must both have known successful transport")
        old_hashes = json.loads((args.resume_infra_run / "source_hashes.json").read_text(encoding="utf-8"))
        for name in ("prompts.py", "schemas.py", "browser_action_schema.json", "config.json", "PROTOCOL.md"):
            if old_hashes[str(HERE / name)] != digest(HERE / name):
                raise ValueError("Infrastructure resume cannot change frozen prompts, schema, configuration or protocol")
    lock_name = "LIVE_INFRA_RESUME_LOCK.json" if args.resume_infra_run else "LIVE_LAUNCH_LOCK.json"
    with (HERE / lock_name).open("x", encoding="utf-8") as stream:
        json.dump({"output": str(args.output), "time": time.time(), "scope": "one_fixed_pub001_pair"}, stream)
    args.output.mkdir(parents=True)
    ledger = Ledger(args.output, config)
    preflight = HERE / "preflight_001" / "ledger.json"
    if preflight.exists():
        before = json.loads(preflight.read_text(encoding="utf-8"))
        if before["request_attempts"] != 0:
            raise ValueError("Preflight must not call model")
        ledger.data["browser_operations"] = before["browser_operations"]
        ledger.data["events"] = before["events"]
        ledger.data["preflight_included"] = str(preflight)
        ledger.save()
    if prior_ledger is not None:
        ledger.data = prior_ledger
        ledger.data["inherited_infrastructure_run"] = str(args.resume_infra_run)
        ledger.save()
    api = LocalAPI(config, ledger, args.resume_infra_run)
    actor = Actor(original, api, action_schema)
    sources = list(HERE.glob("*.py")) + [HERE / n for n in ("config.json", "PROTOCOL.md", "browser_action_schema.json")]
    sources += [args.project / n for n in ("web_agent_benchmark/evaluation/run_public39.py",
                 "web_agent_benchmark/public_benchmark/public_benchmark_shell_app.py",
                 "web_agent_benchmark/public_shell/public_shell_app.py",
                 "web_agent_benchmark/public_affairs_shell/public_affairs_shell_app.py",
                 "web_agent_benchmark/evaluation/reflection_history.py", "adversarial_pipeline/llm_client.py")]
    hashes = {}
    for source in sources:
        target = args.output / "runtime_source" / source.relative_to(args.project)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(source)] = digest(source)
    dump(args.output / "source_hashes.json", hashes)
    dump(args.output / "config.json", config)
    summary = {"status": "running", "results": [], "service_changes": [], "selection": "user_supplied_known_development_pair"}
    try:
        for arm in config["arms"]:
            print("START " + arm, flush=True)
            result = run_arm(arm, args.output / arm, args.project, config, ledger, api, original, actor)
            summary["results"].append(result)
            dump(args.output / "summary.json", summary)
            print(json.dumps({"arm": arm, "status": result["status"], "branches": {k:{a:v.get(a) for a in ("status","outcome","final_selection")} for k,v in result["branches"].items()}}, ensure_ascii=False), flush=True)
        summary["status"] = "finished"
    except Exception as exc:
        summary.update(status="stopped", error={"type": type(exc).__name__, "message": str(exc)})
    finally:
        summary["request_attempts"] = ledger.data["request_attempts"]
        summary["browser_operations"] = ledger.data["browser_operations"]
        summary["source_preserved"] = {p:digest(p) == sha for p,sha in hashes.items()}
        dump(args.output / "summary.json", summary)
        print(json.dumps({k:v for k,v in summary.items() if k != "results"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
