"""Explicit continuation of one transport-interrupted prefix, never task resampling.

Completed units stay in their original artifact directories. This deliberately
does not resume interrupted verification/submission branches or arbitrary crashes.
"""
from __future__ import annotations

import argparse
import copy
import json
from decimal import Decimal
from pathlib import Path

from PIL import Image

from research.decision_evidence_audit import core, models, runner
from research.path_compat import resolve_path
from . import panel
from .api_backend import ApiConfig, IntranetApiBackend, RETRYABLE_HTTP, wire_payload
from .h_base import actor_prompt
from .harness import snapshot


def read(path):
    return json.loads(resolve_path(path).read_text())


class PrefixResume:
    def __init__(self, source, manifest):
        self.source = resolve_path(source).resolve()
        if read(self.source / "TASK_MANIFEST.json") != manifest:
            raise ValueError("resume must use the identical original task manifest")
        self.progress = read(self.source / "progress.json")
        prefs = self.progress["prefixes"]
        if not prefs:
            raise ValueError("no interrupted prefix to resume")
        active = prefs[-1]
        self.ordinal, self.model = active["ordinal"], active["model"]
        self.prior_cost = active["cost"]
        self.completed_ordinals = {p["ordinal"] for p in prefs[:-1]}
        if self.completed_ordinals != set(range(1, self.ordinal)) or active["checkpoint_reached"]:
            raise ValueError("only a contiguous completed schedule followed by a pre-hook interruption is supported")
        for row in self.progress["rows"]:
            if row["ordinal"] in self.completed_ordinals:
                if not row.get("submitted") or len(row.get("server_receipts", [])) != 1:
                    raise ValueError("prior completed units must have terminal submission receipts")
            elif row.get("checkpoint_reached") or row.get("submitted") or row.get("verification_executed"):
                raise ValueError("cannot resume a branch or repeat a previously proposed/executed submit")
            elif row["ordinal"] > self.ordinal and row.get("prefix_started"):
                raise ValueError("later tasks already started")
        self.prefix_dir = self.source / "online" / f"unit_{self.ordinal:02d}" / "prefix"
        self.timeline = read(self.prefix_dir / "timeline.json")
        self.history = read(self.prefix_dir / "execution_receipts.json")
        if runner.line_count(self.prefix_dir.parent / "server_receipts.jsonl"):
            raise ValueError("interrupted prefix already has server submissions")
        last = self.timeline[-1]
        if last.get("error_type") not in {"ApiStop", "BudgetExceeded"} or any(k in last for k in ("action", "receipt", "response")):
            raise ValueError("only an unanswered transport failure before any action can be reissued")
        if last.get("error_type") == "BudgetExceeded":
            stop = read(self.source / "api_wire/transport_stop.json")
            if stop.get("stop_reason") != "budget_exhausted_before_another_dispatch":
                raise ValueError("budget interruption was not an undispatched transport retry")
        self.logical_completed = len(self.timeline) - 1
        if not 0 <= self.logical_completed < 12:
            raise ValueError("no remaining original logical prefix allowance")
        self.contexts = [dict(response=t["response"], proposed_action=t["action"])
                         for t in self.timeline[:-1] if "response" in t]
        self.observed = [dict(kind=runner.screenshot_kind(t["state_before"]["url_path"]),
                              path=t["screenshot_before"]) for t in self.timeline[:-1]]
        entries = read(self.source / "api_wire/api_spend.json")["entries"]
        entry = entries[-1]
        if self.model != "M_strong" or entry.get("status") != "http_failure" or entry.get("http_status") not in RETRYABLE_HTTP:
            raise ValueError("last unanswered request is not a supported transient HTTP failure")
        self.failed_id = entry.get("logical_request_id", entry["request_id"])
        self.prior_attempts = sum(e.get("logical_request_id", e["request_id"]) == self.failed_id for e in entries)
        self.prior_attempts += entry.get("prior_transport_attempts", 0)
        self.request = read(self.prefix_dir / "requests" / f"{self.failed_id}.json")
        response = read(self.prefix_dir / "responses" / f"{self.failed_id}.json")
        if response.get("ok") is not False:
            raise ValueError("completed model response cannot be resampled")
        self.wire = read(self.source / "api_wire" / f"call_{len(entries):04d}" / "request.json")
        if self.wire["request_id"] != entry["request_id"]:
            raise ValueError("wire attempt identity mismatch")
        self.ready = False

    def rows(self):
        fresh = panel.initial_rows(read(self.source / "TASK_MANIFEST.json")["case_interleaved_order"])
        old = {(r["ordinal"], r["strategy"]): r for r in self.progress["rows"]}
        return [{**copy.deepcopy(old[(r["ordinal"], r["strategy"])]),
                 "source_directory": old[(r["ordinal"], r["strategy"])].get(
                     "source_directory", str(self.source / "online" / f"unit_{r['ordinal']:02d}"))}
                if r["ordinal"] in self.completed_ordinals else r for r in fresh]

    def completed_prefixes(self):
        return [{**copy.deepcopy(p), "source_run": p.get("source_run", str(self.source))}
                for p in self.progress["prefixes"][:-1]]

    def restore_prefix(self, page, executor, base_url, directory):
        if not self.history or self.history[0]["action"]["action"] != "goto":
            raise ValueError("original initial navigation receipt missing")
        executor.navigate(base_url + self.history[0]["after_url_path"], phase="replay_resume_initial")
        for receipt in self.history[1:]:
            if not receipt.get("executed") or receipt["action"]["action"] == "goto":
                raise ValueError("ambiguous prior browser failure or navigation is unsupported")
            executor.execute(receipt["action"], phase="replay_resume_action", max_attempts=1)
        state, shot = snapshot(page, directory, "resume_restored")
        with Image.open(resolve_path(self.timeline[-1]["screenshot_before"])) as a, Image.open(shot) as b:
            pixels_equal = a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()
        system, user, public = actor_prompt(self.request["public_context"]["user_goal"], state, self.history)
        prompt_equal = (system == self.request["system_prompt"] and user == self.request["user_prompt"]
                        and public == self.request["public_context"])
        proof = dict(source_run=str(self.source), source_request_id=self.failed_id,
                     public_state_equal=state == self.timeline[-1]["state_before"],
                     screenshot_pixels_equal=pixels_equal, original_prompt_equal=prompt_equal,
                     replay_receipts=executor.receipts[:], prior_logical_calls=self.logical_completed,
                     prior_failed_transport_attempts=self.prior_attempts,
                     logical_history="original receipts followed by new actions; physical replay excluded")
        core.write_json(directory / "resume_proof.json", proof)
        if not all(proof[k] for k in ("public_state_equal", "screenshot_pixels_equal", "original_prompt_equal")):
            raise ValueError("same interrupted public input could not be reconstructed; no model dispatch")
        self.ready = True
        return dict(prior_history=self.history, receipt_offset=len(executor.receipts),
                    observed=self.observed, prior_context=self.contexts)


class ReissueFirstRequest:
    """Only the first resumed call; validates full wire input before spending."""
    def __init__(self, backend, resume, output):
        self.backend, self.resume, self.output = backend, resume, output
        self.used = False

    @property
    def metadata(self):
        return {**self.backend.metadata, "explicit_resumed_request": self.resume.failed_id,
                "prior_transport_attempts": self.resume.prior_attempts}

    def complete(self, request):
        if self.used:
            return self.backend.complete(request)
        if not self.resume.ready:
            raise ValueError("public replay must succeed before the interrupted request is reissued")
        payload, _ = wire_payload(self.backend.config, request)
        equal = payload == self.resume.wire["payload"]
        equal = equal and request.public_context == self.resume.request["public_context"]
        core.write_json(self.output / "reissued_request.json", dict(
            prior_run=str(self.resume.source), old_request_id=self.resume.failed_id,
            new_request_id=request.request_id, serialized_payload_and_image_bytes_equal=equal,
            prior_transport_attempts=self.resume.prior_attempts))
        if not equal:
            raise ValueError("reissued prompt, parameters or image bytes differ from original request")
        self.used = True
        reply = self.backend.complete(request, prior_transport_attempts=self.resume.prior_attempts)
        reply.metadata["resumed_from"] = dict(source=str(self.resume.source), request_id=self.resume.failed_id,
                                              prior_transport_attempts=self.resume.prior_attempts)
        return reply


def carry_budget(ledger, source):
    prior = read(Path(source) / "budget.json")
    counted = panel.cost(prior["events"])
    if counted["model_call_attempts"] != prior["model_calls"] or counted["browser_transitions"] != prior["browser_transitions"]:
        raise ValueError("prior budget totals disagree with recorded events")
    if prior["model_calls"] > ledger.max_model_calls or prior["browser_transitions"] > ledger.max_browser_transitions:
        raise core.BudgetExceeded("old consumption exceeds remaining approved total")
    ledger.events = copy.deepcopy(prior["events"])
    ledger.model_calls, ledger.browser_transitions = prior["model_calls"], prior["browser_transitions"]


def assert_same_backbones(old_cfg, cfg):
    """Compare both directions: deleting an old decoding field is still drift."""
    ignored = panel.RETRY_CONFIG_FIELDS | {"max_calls", "money_cap_usd", "authorization_reference",
        "cost_ceiling_basis", "enforce_money_cap", "money_limit_waiver_reference"}
    strong = lambda c: {k: v for k, v in c["M_strong"].items() if k not in ignored}
    def small(c):
        result = dict(c["M_small"])
        if "weights" in result:
            result["weights"] = str(resolve_path(result["weights"]))
        return result
    if small(cfg) != small(old_cfg) or strong(cfg) != strong(old_cfg):
        raise ValueError("resuming must preserve original model/decoding/image/identity settings")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    args = parser.parse_args()
    source, root = resolve_path(args.source).resolve(), args.output.resolve()
    manifest, cfg = read(source / "TASK_MANIFEST.json"), read(args.config)
    missing = panel.readiness(cfg)
    if missing:
        raise PermissionError("no inference: " + ", ".join(missing))
    resume = PrefixResume(source, manifest)
    old_cfg = read(source / "MODEL_CONFIG.json")
    assert_same_backbones(old_cfg, cfg)
    old_spend = read(source / "api_wire/api_spend.json")
    used_money = Decimal(old_cfg["prior_cost_reconciliation"]["reconciled_usage_upper_usd"]) + Decimal(old_spend["accounted_upper_usd"])
    used_api = sum(e["kind"] == "model_call" and e["request_id"].startswith("M_strong/")
                   for e in read(source / "budget.json")["events"])
    money_reset = (cfg["M_strong"].get("enforce_money_cap", True) and
                   Decimal(cfg["M_strong"]["money_cap_usd"]) + used_money > Decimal("50"))
    if money_reset or cfg["M_strong"]["max_calls"] + used_api > 400:
        raise ValueError("resume cannot reset original money/API allowance")
    root.mkdir(parents=True, exist_ok=False)
    panel.snapshot_runtime(root, source / "TASK_MANIFEST.json", args.config)
    ledger = core.BudgetLedger(max_model_calls=800, max_browser_transitions=cfg["budgets"]["browser_transitions"])
    carry_budget(ledger, source)
    ledger.bind_snapshot(root / "budget.json")
    core.write_json(root / "resume_origin.json", dict(source=str(source), completed_ordinals=sorted(resume.completed_ordinals),
        interrupted_ordinal=resume.ordinal, old_request_id=resume.failed_id,
        old_api_accounted_upper_usd=str(used_money), carried_live_cost=panel.cost(ledger.events),
        non_live_transition_consumption=4000 - ledger.max_browser_transitions,
        authorization=cfg["M_strong"]["authorization_reference"],
        enforce_money_cap=cfg["M_strong"].get("enforce_money_cap", True),
        money_limit_waiver_reference=cfg["M_strong"].get("money_limit_waiver_reference")))
    views = {name: panel.ModelBudget(ledger, name, 400) for name in panel.BACKBONES}
    result = dict(prefixes=resume.completed_prefixes(), rows=resume.rows())
    api = None
    try:
        small = cfg["M_small"]
        local = models.LocalQwenServiceBackend(server_url=small["server_url"], max_output_tokens=small["max_output_tokens"],
            temperature=small["temperature"], top_p=small["top_p"], seed=small["seed"])
        health = local.metadata["health"]
        if (resolve_path(health.get("model_path") or "") != resolve_path(small["weights"]) or health.get("max_pixels") != small["max_pixels"]
                or health.get("native_multi_image") is not True):
            raise ValueError("Qwen service does not match original image/model settings")
        api = IntranetApiBackend(ApiConfig(**cfg["M_strong"]), artifact_dir=root / "api_wire", retry_charge=views["M_strong"].charge_model)
        backends = dict(M_small=local, M_strong=ReissueFirstRequest(api, resume, root))
        recorded = {name: models.RecordedModel(b, ledger=views[name]) for name, b in backends.items()}
        for name, model in recorded.items():
            model._ordinal = max([int(e["request_id"].split("request_")[-1].split("__")[0]) for e in ledger.events
                if e["kind"] == "model_call" and e["request_id"].startswith(name + "/request_")] or [0])
        core.write_json(root / "backend_metadata.json", {name: b.metadata for name, b in backends.items()})
        controls_source = resolve_path(old_cfg["qualified_controls_source"])
        for name in panel.BACKBONES:
            controls = read(controls_source / "online/controls" / name / "results.json")
            if len(controls) != 6 or not all(r["passed"] for r in controls):
                raise ValueError("previously completed fixed controls are not qualified")
        core.write_json(root / "controls_reused.json", dict(source=str(controls_source), counted_in_carried_budget=True,
            repeated_control_generations=0, note="Same backend configuration; existing controls are not resampled"))
        with runner.require_playwright()() as pw:
            br = pw.chromium.launch(headless=True, executable_path=str(args.browser), args=list(runner.BROWSER_LAUNCH_ARGS), timeout=20000)
            try:
                result = panel.execute_schedule(br, manifest, recorded, views, ledger, root, resume=resume,
                    prefix_calls=cfg["budgets"]["prefix_calls"], prefix_transitions=cfg["budgets"]["prefix_transitions"],
                    continuation_calls=cfg["budgets"]["continuation_calls"])
            finally:
                br.close()
    except Exception as exc:
        core.write_json(root / "stop.json", dict(error_type=type(exc).__name__, stage="resume_startup",
                                                note="No task/model replacement or budget reset"))
        core.write_json(root / "progress.json", result)
    finally:
        if api:
            api.close()
    panel.offline_report(manifest, result, ledger, root)
    core.write_json(root / "cost_scope.json", dict(
        cumulative_live_cost=panel.cost(ledger.events), prior_run=str(source),
        prior_usage_directory=str(source / "online"),
        note="SUMMARY response metadata covers this new segment only; old artifacts and costs are linked, not overwritten"))
    print(json.dumps(dict(output=str(root), stopped=(root / "stop.json").exists(), cumulative_live_cost=panel.cost(ledger.events)), indent=2))


if __name__ == "__main__":
    main()
