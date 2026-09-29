"""Portable, public-only browser adapter for the fixed three-task development demo.

This is a new, explicitly field-complete shell, NOT the original benchmark UI.
Original figures and task rows are copied without modification. Hidden scoring
metadata never enters HTML, public state, or execution feedback. Native primary
action lookup is preserved; companion checks are separately named diagnostics.
"""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import Flask, redirect, request, send_file, session, url_for
from werkzeug.serving import make_server


TASKS = (("pub013", "public39"), ("health004", "health19"), ("b046", "business47"))
CONDITIONS = ("official140", "clean140")
PROTOCOL_VERSION = "field-complete-public-shell-v1"
PUBLIC_KEYS = {
    "task_alias", "page_title", "user_goal", "chart_reference",
    "primary_field_label", "option_labels", "companion_fields", "completion_label",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_projection(raw: dict, alias: str) -> dict:
    """Strict allowlist; only readonly context values may originate as defaults."""
    companions = []
    for field in raw.get("companion_actions", []):
        kind = field.get("input_type", "text")
        if kind == "hidden":
            continue
        item = {
            "field": str(field["field_id"]),
            "label": str(field.get("field_label") or field["field_id"]),
            "type": str(kind),
            "required": bool(field.get("required", False)),
        }
        if kind == "readonly":
            # These are original non-editable public program context, not a
            # chart-derived expected response or a generated interpretation.
            item["value"] = str(field.get("correct_value") or "")
        if kind not in {"text", "textarea", "checkbox", "readonly"}:
            raise ValueError("Unsupported visible companion field type: " + str(kind))
        companions.append(item)
    chart = raw.get("chart_asset") or {}
    return {
        "task_alias": alias,
        "page_title": raw.get("page_title") or chart.get("html_title") or "Decision review",
        "user_goal": raw["workflow_instruction"],
        "chart_reference": raw.get("chart_reference") or chart.get("html_title") or "Task dashboard chart",
        "primary_field_label": (raw.get("primary_action") or {}).get("field_label", "Decision"),
        "option_labels": sorted(str(item["label"]) for item in raw["action_space"]),
        "companion_fields": companions,
        "completion_label": (raw.get("completion_action") or {}).get("label", "Submit decision"),
    }


def prepare_bundle(source_raw_dir: Any, data_dir: Any) -> dict:
    """Copy exactly the predeclared six cases; never pick using model outcomes."""
    source, destination = Path(source_raw_dir), Path(data_dir)
    manifest = {"protocol_version": PROTOCOL_VERSION, "tasks": []}
    for slug, family in TASKS:
        for condition in CONDITIONS:
            index = len(manifest["tasks"]) + 1
            alias = "case%02d" % index
            split_path = source / "splits" / condition / (family + "_tasks.jsonl")
            matches = [line for line in split_path.read_text(encoding="utf-8").splitlines()
                       if line.strip() and json.loads(line).get("task_slug") == slug]
            if len(matches) != 1:
                raise ValueError("Expected one raw row for %s/%s" % (condition, slug))
            raw_line, raw = matches[0], json.loads(matches[0])
            figure_name = Path(raw["chart_asset"]["figure_path"]).name
            source_chart = source / "assets" / condition / family / slug / figure_name
            case_dir = destination / alias
            chart = case_dir / ("chart" + source_chart.suffix.lower())
            public = public_projection(raw, alias)
            provenance = {
                "task_slug": slug, "family": family, "condition": condition,
                "source_split": str(split_path.resolve()),
                "source_chart": str(source_chart.resolve()),
                "source_row_sha256": hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                "chart_sha256": file_hash(source_chart),
                "protocol_version": PROTOCOL_VERSION,
            }
            if (case_dir / "public.json").exists():
                # Refuse silent mutation of an already prepared bundle.
                if json.loads((case_dir / "public.json").read_text(encoding="utf-8")) != public:
                    raise ValueError("Existing public bundle differs: " + alias)
                if not chart.is_file() or file_hash(chart) != provenance["chart_sha256"]:
                    raise ValueError("Existing chart differs: " + alias)
            else:
                _write_json(case_dir / "public.json", public)
                shutil.copyfile(source_chart, chart)
                _write_json(case_dir / "offline" / "raw.json", raw)
                _write_json(case_dir / "offline" / "provenance.json", provenance)
            manifest["tasks"].append(dict(provenance, task_alias=alias, directory=alias,
                                          chart_file=chart.name))
    _write_json(destination / "offline" / "manifest.json", manifest)
    return manifest


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _page(title: str, body: str) -> str:
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title>
<style>body{font:16px Arial,sans-serif;background:#f5f7fa;color:#172033;margin:0}
header{background:white;border-bottom:1px solid #d7deea;padding:14px 24px}
main{max-width:1240px;padding:20px;margin:auto}.card{background:white;border:1px solid #d7deea;
border-radius:8px;padding:18px}.layout{display:grid;grid-template-columns:58%% 1fr;gap:16px}
.chart{width:100%%;max-height:680px;object-fit:contain}label{display:block;margin:14px 0 6px}
select,textarea,input[type=text]{width:100%%;box-sizing:border-box;padding:9px;font:inherit}
textarea{min-height:80px}button,a{display:inline-block;margin-top:14px;padding:9px 12px;
background:#2356a8;color:white;border:0;border-radius:5px;font:inherit;text-decoration:none}
.error{color:#9e1823}.readonly{background:#f2f4f7;padding:8px}
</style></head><body><header><h1>%s</h1></header><main>%s</main></body></html>""" % (_h(title), _h(title), body)


def make_app(public_task: dict, chart_path: Any, output_path: Any,
             server_defaults: Optional[dict] = None) -> Flask:
    """Build app from an allowlisted task; no scorer nor answer-bearing rows."""
    if set(public_task) != PUBLIC_KEYS:
        raise ValueError("Unexpected public task fields")
    chart, output = Path(chart_path).resolve(), Path(output_path)
    alias = public_task["task_alias"]
    labels = public_task["option_labels"]
    token_labels = {"option_%d" % index: label for index, label in enumerate(labels)}
    fields = {item["field"]: item for item in public_task["companion_fields"]}
    server_defaults = dict(server_defaults or {})
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"
    app.config["RECEIPTS"] = []

    @app.route("/task/<task_alias>", methods=["GET"])
    def task_home(task_alias):
        if task_alias != alias:
            return "Unknown task", 404
        session["visited_task"] = True
        return _page(public_task["page_title"], '<section class="card"><h2>Task</h2><p>%s</p><a href="%s">Open Dashboard</a></section>' %
                     (_h(public_task["user_goal"]), url_for("dashboard", task_alias=alias)))

    @app.route("/task/<task_alias>/dashboard", methods=["GET"])
    def dashboard(task_alias):
        if task_alias != alias:
            return "Unknown task", 404
        session["visited_dashboard"] = True
        return _page(public_task["page_title"], '<section class="card"><h2>Dashboard</h2><p>%s</p><img class="chart" src="%s" alt="Decision dashboard chart"><a href="%s">Open Form</a></section>' %
                     (_h(public_task["chart_reference"]), url_for("chart_image", task_alias=alias), url_for("form", task_alias=alias)))

    def render_form(error="", values=None):
        values = values or {}
        options = '<option value="">Select a route</option>' + "".join(
            '<option value="%s"%s>%s</option>' % (_h(token), " selected" if values.get("primary_action") == token else "", _h(label))
            for token, label in token_labels.items())
        companions = []
        for field, item in fields.items():
            label = '<label for="%s">%s%s</label>' % (_h(field), _h(item["label"]), " (required)" if item["required"] else "")
            required = " required" if item["required"] else ""
            value = values.get(field, "")
            if item["type"] == "readonly":
                control = '<input type="text" id="%s" name="%s" value="%s" readonly>' % (_h(field), _h(field), _h(item.get("value", "")))
            elif item["type"] == "checkbox":
                control = '<input type="checkbox" id="%s" name="%s" value="true"%s%s>' % (_h(field), _h(field), required, " checked" if value else "")
            else:
                control = '<textarea id="%s" name="%s"%s>%s</textarea>' % (_h(field), _h(field), required, _h(value))
            companions.append(label + control)
        body = '<div class="layout"><section class="card"><h2>Dashboard reference</h2><p>%s</p><img class="chart" src="%s" alt="Decision dashboard chart"></section><section class="card"><h2>Submit decision</h2><p>%s</p><p class="error">%s</p><form method="post" action="%s"><label for="primary_action">%s</label><select id="primary_action" name="primary_action" required>%s</select>%s<button type="submit">%s</button></form></section></div>' % (
            _h(public_task["chart_reference"]), url_for("chart_image", task_alias=alias),
            _h(public_task["user_goal"]), _h(error), url_for("submit", task_alias=alias),
            _h(public_task["primary_field_label"]), options, "".join(companions), _h(public_task["completion_label"]))
        return _page(public_task["page_title"], body)

    @app.route("/task/<task_alias>/form", methods=["GET"])
    def form(task_alias):
        if task_alias != alias:
            return "Unknown task", 404
        session["visited_form"] = True
        return render_form()

    @app.route("/task/<task_alias>/chart", methods=["GET"])
    def chart_image(task_alias):
        if task_alias != alias:
            return "Unknown task", 404
        return send_file(chart)

    @app.route("/task/<task_alias>/submit", methods=["POST"])
    def submit(task_alias):
        if task_alias != alias:
            return "Unknown task", 404
        token = request.form.get("primary_action", "")
        visible = {}
        missing = []
        for name, item in fields.items():
            if item["type"] == "readonly":
                value = item.get("value", "")
            elif item["type"] == "checkbox":
                value = request.form.get(name) == "true"
            else:
                value = str(request.form.get(name, ""))
            visible[name] = value
            if item["required"] and not str(value or "").strip():
                missing.append(item["label"])
        if token not in token_labels or missing:
            problem = "Choose an available route." if token not in token_labels else "Complete required fields: " + ", ".join(missing)
            return render_form(problem, request.form), 400
        receipt = {
            "timestamp": utc_now(), "task_alias": alias,
            "selected_option_token": token, "selected_option_label": token_labels[token],
            "fields": visible, "navigation": {key: bool(session.get(key)) for key in ("visited_task", "visited_dashboard", "visited_form")},
            "server_received": True,
        }
        app.config["RECEIPTS"].append(receipt)
        _append_json(output, receipt)
        # Kept on disk only, never returned to the browser or acting model.
        _append_json(output.with_name("server_context.private.jsonl"), {
            "timestamp": receipt["timestamp"], "server_default_fields": server_defaults,
            "automatic_context_not_agent_actions": True,
        })
        return redirect(url_for("confirmation", task_alias=alias))

    @app.route("/task/<task_alias>/confirmation", methods=["GET"])
    def confirmation(task_alias):
        if task_alias != alias:
            return "Unknown task", 404
        return _page("Submission received", '<section class="card"><h2>Submission received</h2><p>The decision form has been submitted.</p></section>')

    return app


class BrowserTask:
    """One isolated real browser/server session, synchronous and serial."""

    def __init__(self, data_dir: Any, output_dir: Any, browser_executable: Any = None,
                 ledger: Any = None):
        self.data_dir, self.output_dir = Path(data_dir), Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.public_task = json.loads((self.data_dir / "public.json").read_text(encoding="utf-8"))
        figures = list(self.data_dir.glob("chart.*"))
        if len(figures) != 1:
            raise ValueError("Exactly one figure is required")
        self.chart_path = figures[0].resolve()
        self.browser_executable = str(browser_executable) if browser_executable else None
        self.ledger = ledger
        self.history = []
        self.receipt = None
        self._snapshot_count = 0
        self._server = self._playwright = self.browser = self.page = None

    def _charge(self, action):
        if self.ledger is not None:
            if callable(self.ledger):
                self.ledger(action)
            else:
                self.ledger.transition(action)

    def _record(self, action, result, source="actor"):
        record = {"sequence": len(self.history), "action": action, "result": result, "source": source}
        self.history.append(record)
        _append_json(self.output_dir / "browser_history.jsonl", record)
        return result

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        raw = json.loads((self.data_dir / "offline" / "raw.json").read_text(encoding="utf-8"))
        defaults = {item["field_id"]: item.get("correct_value") for item in raw.get("companion_actions", []) if item.get("input_type") == "hidden"}
        self.app = make_app(self.public_task, self.chart_path, self.output_dir / "submission_receipts.jsonl", defaults)
        self._server = make_server("127.0.0.1", 0, self.app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        try:
            self._playwright = sync_playwright().start()
            options = {"headless": True}
            if self.browser_executable:
                options["executable_path"] = self.browser_executable
            self.browser = self._playwright.chromium.launch(**options)
            self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            base = "http://127.0.0.1:%d/task/%s" % (self._server.server_port, self.public_task["task_alias"])
            for action in ({"kind": "setup_open_task"}, {"kind": "setup_open_dashboard"}, {"kind": "setup_open_form"}):
                self._charge(action)
                if action["kind"] == "setup_open_task":
                    self.page.goto(base, wait_until="networkidle")
                else:
                    name = "Open Dashboard" if action["kind"] == "setup_open_dashboard" else "Open Form"
                    self.page.get_by_role("link", name=name, exact=True).click()
                    self.page.wait_for_load_state("networkidle")
                self._record(action, {"ok": True, "page": self.page.url.split("/")[-1]}, "deterministic_setup")
            self.snapshot("initial_form")
            return self
        except BaseException:
            self.close()
            raise

    def state(self) -> dict:
        return self.page.evaluate("""() => {
            const select = document.getElementById('primary_action');
            const fields = [...document.querySelectorAll('textarea, input')].map(e => ({
              id:e.id,field:e.id,label:document.querySelector('label[for="'+e.id+'"]')?.textContent || e.id,
              type:e.readOnly?'readonly':e.type,required:e.required,
              value:e.type==='checkbox'?e.checked:e.value,editable:!e.readOnly}));
            const options = select ? [...select.options].filter(o=>o.value).map(o=>({label:o.text,selected:o.selected})) : [];
            return {page: location.pathname.endsWith('/confirmation')?'confirmation':'form',
                current_selection:select?.selectedOptions[0]?.value ? select.selectedOptions[0].text : '',
                options:options.map(o=>o.label),option_states:options,fields,submit_visible:!!document.querySelector('button[type=submit]'),
                confirmation_visible:location.pathname.endsWith('/confirmation') && document.body.innerText.includes('Submission received')};
        }""")

    def snapshot(self, tag="state") -> dict:
        self._snapshot_count += 1
        path = self.output_dir / ("%03d_%s.png" % (self._snapshot_count, "".join(c for c in tag if c.isalnum() or c in "_-")))
        self.page.screenshot(path=str(path), full_page=True)
        state = self.state()
        _write_json(path.with_suffix(".json"), {"timestamp": utc_now(), "state": state, "history_length": len(self.history), "screenshot": path.name})
        return {"state": state, "screenshot": str(path.resolve())}

    def execute(self, action: dict, source: str = "actor") -> dict:
        """Validate actions against current DOM; never infer or repair a choice."""
        kind = action.get("kind")
        before = self.state()
        self._charge(action)
        try:
            if kind == "select":
                label = action.get("option")
                if label not in self.public_task["option_labels"]:
                    raise ValueError("Option must exactly match a visible label")
                self.page.locator("#primary_action").select_option(label=label)
            elif kind in {"fill", "check"}:
                field = str(action.get("field", ""))
                allowed = {item["field"]: item for item in self.public_task["companion_fields"]}
                item = allowed.get(field)
                if not item or item["type"] == "readonly":
                    raise ValueError("Field is not an editable public field")
                if kind == "check":
                    if item["type"] != "checkbox" or not isinstance(action.get("value"), bool):
                        raise ValueError("check requires a checkbox and boolean value")
                    self.page.locator("[id='%s']" % field).set_checked(action["value"])
                else:
                    if item["type"] == "checkbox":
                        raise ValueError("Use check for checkbox fields")
                    self.page.locator("[id='%s']" % field).fill(str(action.get("value", "")))
            elif kind == "submit":
                self.page.get_by_role("button", name=self.public_task["completion_label"], exact=True).click()
                self.page.wait_for_load_state("networkidle")
            elif kind == "observe":
                pass
            else:
                raise ValueError("Unknown action kind")
            after = self.state()
            result = {"ok": True, "before_selection": before["current_selection"],
                      "current_selection": after["current_selection"], "page": after["page"],
                      "submitted": bool(after["confirmation_visible"])}
            if kind == "submit" and not after["confirmation_visible"]:
                result.update(ok=False, error="Browser or server form validation blocked submission; complete required visible fields.")
            if self.app.config["RECEIPTS"]:
                self.receipt = dict(self.app.config["RECEIPTS"][-1])
                self.receipt["confirmation_observed"] = bool(after["confirmation_visible"])
                result["submission_receipt"] = self.receipt
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "submitted": False,
                      "current_selection": self.state()["current_selection"]}
        self._record(action, result, source=source)
        self.snapshot("after_" + str(kind))
        return result

    def close(self):
        if self.browser is not None:
            self.browser.close()
            self.browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __exit__(self, exc_type, exc, tb):
        self.close()


def score_summary(raw: dict, receipt: Optional[dict]) -> dict:
    """Offline, original primary lookup + explicitly reconstructed diagnostics.

    Exact text equality is NOT a semantic companion scorer and cannot be called
    an official end-to-end score. Automatic hidden defaults are not agent work.
    """
    receipt = receipt or {}
    label = str(receipt.get("selected_option_label") or "")
    matches = [item for item in raw.get("action_space", []) if item.get("label") == label]
    if not label or not receipt.get("server_received"):
        primary = "completion_failure"
    elif len(matches) != 1:
        primary = "invalid_action_failure"
    elif matches[0].get("action_id") == raw.get("expected_action_id"):
        primary = "success"
    elif matches[0].get("action_id") in raw.get("misleading_action_ids", []):
        primary = "misleading_failure"
    else:
        primary = "irrelevant_action_failure"
    companion = []
    for item in raw.get("companion_actions", []):
        kind = item.get("input_type", "text")
        actual = receipt.get("fields", {}).get(item["field_id"])
        companion.append({
            "field": item["field_id"], "type": kind, "required": bool(item.get("required", False)),
            "status": "automatic_server_context_not_agent_action" if kind == "hidden" else
                      "readonly_public_context_not_agent_action" if kind == "readonly" else
                      "exact_match" if actual == item.get("correct_value") else "not_exact_match",
            "present": bool(str(actual or "").strip()) if kind not in {"hidden", "readonly"} else None,
        })
    editable_required = [item for item in companion if item["required"] and item["type"] not in {"hidden", "readonly"}]
    return {
        "primary_outcome": primary,
        "real_submission": bool(receipt.get("server_received") and receipt.get("confirmation_observed")),
        "selected_option_label": label,
        "required_editable_fields_present": all(item["present"] for item in editable_required) and bool(receipt),
        "companion_exact_match_diagnostic": companion,
        "official_full_end_to_end_score": "not_computed",
        "score_scope": "Original expected/misleading primary action lookup; separate reconstructed companion exact checks; no semantic text judging.",
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_bundle(args.source, args.output), indent=2, ensure_ascii=False))
