"""Serial dual-backbone panel. Default is a local readiness check, not inference.

Run records are new directories; there is no implicit resume, model fallback,
task replacement, automatic model launch, or scorer-driven online branching.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import shutil
import subprocess
from collections import Counter
from decimal import Decimal
from pathlib import Path

from PIL import Image

from research.decision_evidence_audit import core, models, runner, safe_shell
from research.path_compat import resolve_path
from .api_backend import ApiConfig, ApiStop, IntranetApiBackend, RETRY_CONFIG_FIELDS
from .h_base import PROTOCOL_VERSION
from .harness import TransitionScope, capture_pending, restore, run_branch

BACKBONES = ("M_small", "M_strong")
STRATEGIES = ("B0", "B2", "B3")
REPO = Path(__file__).resolve().parents[2]
PREPARED = Path(__file__).parent / "preparation_20260907_v1"


class PrefixTransitionLimit(core.BudgetExceeded):
    """Local prefix allowance, distinct from exhaustion of the whole panel."""


class PrefixTransitions(TransitionScope):
    def charge_transition(self, **kwargs):
        if self.used >= self.cap:
            raise PrefixTransitionLimit("this prefix reached its transition allowance")
        super().charge_transition(**kwargs)


class ModelBudget:
    """A view of ONE physical ledger, with per-backbone/control call limits."""
    def __init__(self, ledger, name, cap):
        self.ledger, self.name, self.cap = ledger, name, cap
        self.section = "controls"

    def charge_model(self, *, phase, request_id):
        if self.ledger.browser_transitions >= self.ledger.max_browser_transitions:
            raise core.BudgetExceeded("panel browser budget exhausted before another model dispatch")
        calls = [e for e in self.ledger.events if e["kind"] == "model_call"
                 and e["request_id"].startswith(self.name + "/")]
        section_calls = sum(e["phase"].startswith(f"{self.name}/{self.section}/") for e in calls)
        section_cap = 16 if self.section == "controls" else 384
        if len(calls) >= self.cap or section_calls >= section_cap:
            raise core.BudgetExceeded(f"{self.name} {self.section} call allowance exhausted")
        self.ledger.charge_model(phase=f"{self.name}/{self.section}/{phase}",
                                request_id=f"{self.name}/{request_id}")

    def charge_transition(self, *, phase, action):
        self.ledger.charge_transition(phase=f"{self.name}/{self.section}/{phase}", action=action)


def cost(events):
    return dict(model_call_attempts=sum(e["kind"] == "model_call" for e in events),
                browser_transitions=sum(e["kind"] == "browser_transition" for e in events),
                replay_transitions=sum(e["kind"] == "browser_transition" and
                    "/replay_" in e["phase"] for e in events))


def plus(a, b):
    return {key: a.get(key, 0) + b.get(key, 0) for key in set(a) | set(b)}


def verification_attempts(events):
    return sum(e["kind"] == "model_call" and e["phase"].rsplit("/", 1)[-1].startswith(("b2_", "b3_")) for e in events)


def initial_rows(schedule):
    return [dict(ordinal=u["ordinal"], task_slug=u["task_slug"], arm=u["arm"], model=u["model"],
                 strategy=s, status="not_run", prefix_started=False, checkpoint_reached=False,
                 verification_executed=False, submitted=False)
            for u in schedule for s in u["strategies"]]


def carry_in_budget(ledger, source):
    """Explicit continuation of an interrupted control run; never replay its tasks."""
    if not source:
        return
    source = resolve_path(source).resolve()
    prior = json.loads((source / "budget.json").read_text())
    progress = json.loads((source / "progress.json").read_text())
    if any(row.get("prefix_started") for row in progress["rows"]):
        raise ValueError("control-only continuation cannot restart previously used panel tasks")
    events = prior["events"]
    if cost(events)["model_call_attempts"] != prior["model_calls"] or cost(events)["browser_transitions"] != prior["browser_transitions"]:
        raise ValueError("prior budget event counts disagree with totals")
    if prior["model_calls"] > ledger.max_model_calls or prior["browser_transitions"] > ledger.max_browser_transitions:
        raise core.BudgetExceeded("prior consumption exceeds the approved panel allowance")
    ledger.events = [dict(event, carried_from=str(source)) for event in events]
    ledger.model_calls, ledger.browser_transitions = prior["model_calls"], prior["browser_transitions"]


def validate_schedule(manifest, *, backbones=BACKBONES):
    """Ordinary input shape check; no new frozen contract or task selection."""
    rows, schedule = manifest["rows"], manifest["case_interleaved_order"]
    slugs = {r["task_slug"] for r in rows}
    if not backbones or len(set(backbones)) != len(backbones):
        raise ValueError("declare non-empty, unique backbone identifiers")
    expected = {(slug, arm, model) for slug in slugs for arm in ("official140", "clean140") for model in backbones}
    actual = [(u["task_slug"], u["arm"], u["model"]) for u in schedule]
    if len(slugs) != len(rows) or set(actual) != expected or len(actual) != len(expected):
        raise ValueError("each declared task needs exactly two arms and every declared backbone")
    if [u["ordinal"] for u in schedule] != list(range(1, len(schedule) + 1)):
        raise ValueError("schedule ordinals must preserve the declared order")
    if any(sorted(u["strategies"]) != sorted(STRATEGIES) for u in schedule):
        raise ValueError("each prefix needs B0/B2/B3 exactly once")


def prior_control_usage(config, root):
    """Reuse completed controls explicitly, not failed attempts or panel trajectories."""
    source = resolve_path(config["qualified_controls_source"]).resolve()
    if source != resolve_path(config.get("carry_in_budget_source", "")).resolve():
        raise ValueError("reused controls must be included in the carried budget")
    old_config = json.loads((source / "MODEL_CONFIG.json").read_text())
    for name in BACKBONES:
        ignored = {"money_cap_usd", "max_calls", "authorization_reference", "cost_ceiling_basis"} | RETRY_CONFIG_FIELDS
        old_backend = {k: v for k, v in old_config[name].items() if k not in ignored}
        new_backend = {k: v for k, v in config[name].items() if k not in ignored}
        if name == "M_small":
            for backend in (old_backend, new_backend):
                if "weights" in backend:
                    backend["weights"] = str(resolve_path(backend["weights"]))
        if old_backend != new_backend:
            raise ValueError("completed controls belong to a different backend configuration")
    references = {}
    for name in BACKBONES:
        path = source / "online" / "controls" / name / "results.json"
        results = json.loads(path.read_text())
        expected = {("nonchart_public_route", target, initial, None)
                    for target in ("Route A", "Route B") for initial in ("Route A", "Route B")}
        expected |= {("ordered_two_images", None, None, i) for i in (0, 1)}
        actual = {(r["kind"], r.get("target"), r.get("initial"), r.get("order_index")) for r in results}
        if len(results) != 6 or actual != expected or not all(r["passed"] is True for r in results):
            raise ValueError("only the complete passing fixed controls may be reused")
        references[name] = str(path)
    entries = json.loads((source / "api_wire/api_spend.json").read_text())["entries"]
    if not entries or any(e.get("status") != "completed" or "usage_cost_upper_usd" not in e for e in entries):
        raise ValueError("completed control usage required for retained pre-panel estimate")
    core.write_json(root / "reused_controls.json", dict(source=str(source), results=references,
        note="Previously executed controls, counted via carry-in; no new model replies or task histories synthesized."))
    return [Decimal(e["usage_cost_upper_usd"]) for e in entries]


def readiness(config, *, check_credential=True):
    missing = ApiConfig(**config["M_strong"]).missing(check_credential=check_credential)
    small, budget = config["M_small"], config["budgets"]
    if not small.get("authorized"):
        missing.append("this_panel_local_service_or_GPU_permission")
    if not small.get("server_url"):
        missing.append("authorized_running_loopback_Qwen_service")
    if not budget.get("approved"):
        missing.append("this_panel_call_and_transition_budget_approval")
    bounds = dict(local_model_calls=400, api_model_calls=400, browser_transitions=4000,
                  concurrency=1, prefix_calls=12, prefix_transitions=20,
                  B2_check_calls=1, B3_check_calls=3, B3_crops=2, continuation_calls=4)
    for field, cap in bounds.items():
        value = budget.get(field)
        if type(value) is not int or value < 1 or value > cap:
            missing.append(f"valid_bounded_budget:{field}")
    # Policy call limits are those of the reused B2/B3 implementation.
    for field in ("B2_check_calls", "B3_check_calls", "B3_crops"):
        if budget.get(field) != bounds[field]:
            missing.append(f"implemented_policy_limit:{field}={bounds[field]}")
    return sorted(set(missing))


def public_unit(manifest_row, arm):
    path = resolve_path(manifest_row["assets"][arm]["path"], base=REPO)
    if not path.is_file():
        raise FileNotFoundError("preselected chart asset missing; do not replace this task")
    task = manifest_row["public_task"]
    if set(task) != core.PUBLIC_TASK_KEYS:
        raise core.IsolationError("only the existing public task projection may enter the shell")
    core.assert_online_payload(task)
    return task, path


def execute_schedule(browser, manifest, recorded, views, ledger, root, *, resolve_public=public_unit,
                     prefix_calls=12, prefix_transitions=20, continuation_calls=4, resume=None,
                     backbones=BACKBONES):
    """All online work, with no raw dataset row or gold argument."""
    validate_schedule(manifest, backbones=backbones)
    table = resume.rows() if resume else initial_rows(manifest["case_interleaved_order"])
    by_slug = {r["task_slug"]: r for r in manifest["rows"]}
    prefixes = resume.completed_prefixes() if resume else []
    def persist():
        core.write_json(root / "progress.json", dict(prefixes=prefixes, rows=table))
    persist()
    try:
        for unit in manifest["case_interleaved_order"]:
            if resume and unit["ordinal"] in resume.completed_ordinals:
                continue
            name = unit["model"]
            views[name].section = "panel"
            model = recorded[name]
            directory = root / "online" / f"unit_{unit['ordinal']:02d}"
            rows = [r for r in table if r["ordinal"] == unit["ordinal"]]
            pref = {**unit, "status": "starting", "checkpoint_reached": False}
            prefixes.append(pref)
            start = len(ledger.events)
            checkpoint = None
            history = []
            base_cost = resume.prior_cost if resume and unit["ordinal"] == resume.ordinal else {}
            public, chart = resolve_public(by_slug[unit["task_slug"]], unit["arm"])
            submissions = directory / "server_receipts.jsonl"
            with runner.managed_shell(public, chart, submissions) as server:
                page = browser.new_page(viewport=dict(width=1440, height=1100))
                executor = runner.BrowserExecutor(page, ledger=PrefixTransitions(views[name], prefix_transitions),
                                                   task_alias=public["task_alias"])
                try:
                    for row in rows:
                        row.update(status="prefix_started", prefix_started=True)
                    persist()
                    kwargs = {}
                    if base_cost:
                        executor.ledger.used = base_cost["browser_transitions"]
                        kwargs = resume.restore_prefix(page, executor, server.base_url, directory / "prefix")
                        for row in rows:
                            row["prior_prefix_directory"] = str(resume.prefix_dir)
                        pref["resumed_from"] = str(resume.source)
                    else:
                        executor.navigate(server.base_url + "/task/" + public["task_alias"], phase="initial_navigation")
                    checkpoint, result = capture_pending(page, executor, model, goal=public["user_goal"],
                        alias=public["task_alias"], directory=directory / "prefix",
                        max_calls=prefix_calls - (resume.logical_completed if base_cost else 0), **kwargs)
                    pref.update(status=result["status"], checkpoint_reached=checkpoint is not None)
                    history = list(kwargs.get("prior_history", ())) + executor.receipts[kwargs.get("receipt_offset", 0):]
                except PrefixTransitionLimit:
                    pref["status"] = "prefix_transition_limit"
                    # This branch has no hook; continue the predeclared schedule, not this prefix.
                finally:
                    pref["cost"] = plus(base_cost, cost(ledger.events[start:]))
                    core.write_json(directory / "prefix" / "execution_receipts.json", executor.receipts)
                    page.close()
                    persist()
                if checkpoint is None:
                    for row in rows:
                        row.update(status="not_executed_no_checkpoint", prefix_status=pref["status"],
                                   prefix_cost=pref["cost"], independent_deployment_cost=pref["cost"])
                    persist()
                    continue
                pref["checkpoint_selection"] = checkpoint.current_selection
                for row in rows:
                    row.update(checkpoint_reached=True, checkpoint_selection=checkpoint.current_selection,
                               prefix_cost=pref["cost"], status="pending_branch")
                persist()
                for row in rows:
                    branch_dir = directory / row["strategy"]
                    page = browser.new_page(viewport=dict(width=1440, height=1100))
                    executor = runner.BrowserExecutor(page, ledger=views[name], task_alias=public["task_alias"])
                    start_branch = len(ledger.events)
                    row["status"] = "branch_started"
                    persist()
                    try:
                        if not restore(page, executor, checkpoint, base_url=server.base_url, directory=branch_dir):
                            row["status"] = "unsupported_restore"
                        else:
                            row.update(run_branch(page, executor, model, checkpoint, strategy=row["strategy"],
                                directory=branch_dir, prefix_receipts=history, submission_path=submissions,
                                max_continuation_calls=continuation_calls))
                    except (ApiStop, core.BudgetExceeded):
                        failure = branch_dir / "branch_result.json"
                        if failure.exists():
                            row.update(json.loads(failure.read_text()))
                        row["status"] = "panel_stopped_during_branch"
                        raise
                    except Exception as exc:
                        row.update(status="branch_runtime_failure", error_type=type(exc).__name__)
                    finally:
                        row["incremental_cost"] = cost(ledger.events[start_branch:])
                        row["verification_call_attempts"] = verification_attempts(ledger.events[start_branch:])
                        # The recorder charges failed calls too. This is attempted execution,
                        # not a successful verifier response or proof of remote HTTP dispatch.
                        row["verification_executed"] = row["verification_call_attempts"] > 0
                        row["verification_policy_returned"] = "policy" in row
                        # A separate deploy includes the shared prefix, but not experimental reset/replay.
                        deploy = plus(pref["cost"], row["incremental_cost"])
                        deploy["browser_transitions"] -= deploy["replay_transitions"]
                        deploy["replay_transitions"] = 0
                        row["independent_deployment_cost"] = deploy
                        core.write_json(branch_dir / "execution_receipts.json", executor.receipts)
                        page.close()
                        persist()
    except Exception as exc:
        # No restart/replacement/backbone fallback, including an infrastructure failure.
        for row in table:
            if row["status"] in {"not_run", "pending_branch", "prefix_started"}:
                row.update(status="not_completed_panel_stop" if row["prefix_started"] else "not_run_panel_stop",
                           stop_error_type=type(exc).__name__)
        core.write_json(root / "stop.json", dict(error_type=type(exc).__name__,
            note="Stopped after the configured bounded transport policy; no task restart, replacement or backbone fallback."))
        persist()
    return dict(prefixes=prefixes, rows=table)


def load_raw(row, arm):
    path = REPO / "web_agent_benchmark/benchmark_v2_open/splits" / arm / (row["family"] + "_tasks.jsonl")
    matches = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    # Dataset identifiers are used only by the offline evaluator, after the panel stops.
    matches = [r for r in matches if r.get("task_slug") == row["task_slug"]]
    if len(matches) != 1:
        raise ValueError("offline dataset task lookup must be unique")
    return matches[0]


def reported_usage(*directories):
    """Sum observed token/latency fields, without treating missing data as zero usage."""
    totals = dict(prompt_tokens_reported=0, completion_tokens_reported=0,
                  seconds_reported=0.0, response_records=0, missing_token_records=0,
                  unknown_retry_usage_records=0)
    for directory in directories:
        for path in directory.rglob("responses/*.json"):
            data = json.loads(path.read_text())
            meta = data.get("metadata", {})
            usage = meta.get("usage") or {}
            totals["response_records"] += 1
            # A successful logical reply must not turn earlier failed HTTP attempts into zero-cost usage.
            for attempt in (meta.get("transport_attempts") or [])[:-1]:
                retry_usage = attempt.get("usage") or {}
                if not all(type(retry_usage.get(k)) is int for k in ("prompt_tokens", "completion_tokens")):
                    totals["unknown_retry_usage_records"] += 1
            if all(isinstance(usage.get(k), int) for k in ("prompt_tokens", "completion_tokens")):
                totals["prompt_tokens_reported"] += usage["prompt_tokens"]
                totals["completion_tokens_reported"] += usage["completion_tokens"]
            else:
                totals["missing_token_records"] += 1
            totals["seconds_reported"] += meta.get("elapsed_seconds", 0.0)
    totals["usage_complete"] = totals["missing_token_records"] == 0 and totals["unknown_retry_usage_records"] == 0
    return totals


def offline_report(manifest, result, ledger, root, *, raw_loader=load_raw, mock=False, backbones=BACKBONES):
    """Called only after all online dispatch has ended; never consulted by actors."""
    by_slug = {r["task_slug"]: r for r in manifest["rows"]}
    evaluator = root / "evaluator"
    table = []
    for original in result["rows"]:
        row = dict(original)
        raw = raw_loader(by_slug[row["task_slug"]], row["arm"])
        if row["checkpoint_reached"]:
            actions = {a["label"]: a["action_id"] for a in raw["action_space"]}
            row["checkpoint_correct"] = actions.get(row["checkpoint_selection"]) == raw["expected_action_id"]
        receipts = row.get("server_receipts", [])
        if row.get("submitted") and len(receipts) == 1:
            row["score"] = safe_shell.score_receipt(raw, receipts[0])
        else:
            row["score"] = dict(outcome="not_submitted" if row["prefix_started"] else "not_run")
        row["confirmed_completion"] = bool(row.get("submitted") and row.get("confirmation_observed")
                                            and (row.get("submit_execution") or {}).get("executed"))
        row["confirmed_correct_completion"] = row["confirmed_completion"] and row["score"]["outcome"] == "success"
        directory = resolve_path(row.get("source_directory", root / "online" / f"unit_{row['ordinal']:02d}"))
        usage_dirs = [directory / "prefix", directory / row["strategy"]]
        if row.get("prior_prefix_directory"):
            usage_dirs.append(resolve_path(row["prior_prefix_directory"]))
        row["independent_deployment_reported_usage"] = reported_usage(*usage_dirs)
        table.append(row)
    groups = []
    for name in backbones:
        for arm in ("official140", "clean140"):
            group = [r for r in table if r["model"] == name and r["arm"] == arm]
            baseline = [r for r in group if r["strategy"] == "B0"]
            errors = {r["ordinal"] for r in baseline if r.get("checkpoint_correct") is False}
            correct = {r["ordinal"] for r in baseline if r.get("checkpoint_correct") is True}
            paired = []
            for strategy in STRATEGIES:
                subset = [r for r in group if r["strategy"] == strategy]
                recovered = sum(r["ordinal"] in errors and r["confirmed_correct_completion"] for r in subset)
                paired.append(dict(strategy=strategy, outcomes=dict(Counter(r["score"]["outcome"] for r in subset)),
                    statuses=dict(Counter(r["status"] for r in subset)),
                    verification_executed=sum(r["verification_executed"] for r in subset),
                    verifier_failed_before_policy_return=sum(r["verification_executed"] and not r.get("verification_policy_returned", "policy" in r) for r in subset),
                    confirmed_correct_completions=sum(r["confirmed_correct_completion"] for r in subset),
                    submitted_without_confirmed_completion=sum(r.get("submitted", False) and not r["confirmed_completion"] for r in subset),
                    recovered_from_shared_error=recovered, recovery_fraction=f"{recovered}/{len(errors)}" if errors else "N/A",
                    correct_to_wrong=sum(r["ordinal"] in correct and r.get("submitted") and r["score"]["outcome"] != "success" for r in subset),
                    correct_to_no_submit=sum(r["ordinal"] in correct and not r.get("submitted") for r in subset),
                    correct_preserved=sum(r["ordinal"] in correct and r["confirmed_correct_completion"] for r in subset),
                    B3_crops=sum((r.get("policy") or {}).get("active_observations", 0) for r in subset)))
            groups.append(dict(model=name, arm=arm, started_prefixes=sum(r["prefix_started"] for r in baseline),
                checkpoint_count=sum(r["checkpoint_reached"] for r in baseline),
                error_checkpoint_count=len(errors),
                independent_error_tasks=len({r["task_slug"] for r in baseline if r["ordinal"] in errors}), strategies=paired))
    # Token counts are reported metadata, not an invoice; failed HTTP costs may be unknown.
    response_meta = []
    for path in sorted((root / "online").rglob("responses/*.json")):
        data = json.loads(path.read_text())
        response_meta.append(dict(artifact=str(path.relative_to(root)), ok=data.get("ok"),
                                  metadata=data.get("metadata", {})))
    spend_path = root / "api_wire" / "api_spend.json"
    costs = dict(experiment_actual=cost(ledger.events), response_metadata=response_meta,
                 experiment_reported_usage=reported_usage(root / "online"),
                 api_reservation_ledger=json.loads(spend_path.read_text()) if spend_path.exists() else None,
                 api_observed_billed_usd=None, note="Call attempts conservatively include failures. API reservations are not invoices.",
                 independent_strategy_cost=[{k: r.get(k) for k in ("ordinal", "model", "arm", "strategy", "independent_deployment_cost", "independent_deployment_reported_usage")} for r in table])
    summary = dict(scope="nonchart_scripted_mock" if mock else "prospective_primary_decision_panel",
                   protocol=PROTOCOL_VERSION, base_tasks=len(manifest["rows"]), groups=groups, costs=costs)
    core.write_json(evaluator / "CASE_TABLE.json", table)
    core.write_json(evaluator / "SUMMARY.json", summary)
    columns = ("ordinal", "task_slug", "arm", "model", "strategy", "prefix_started", "checkpoint_reached",
               "checkpoint_selection", "checkpoint_correct", "verification_executed", "verifier_recommendation",
               "executor_selection", "actor_final_submission", "submitted", "confirmed_completion", "status", "score", "incremental_cost", "independent_deployment_cost")
    with (evaluator / "CASE_TABLE.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in table:
            writer.writerow({key: json.dumps(row[key], ensure_ascii=False) if isinstance(row.get(key), dict) else row.get(key) for key in columns})
    return summary


def snapshot_sources(root):
    for folder in ("research/prospective_simple_check_pilot", "research/decision_evidence_audit"):
        for path in (REPO / folder).glob("*.py"):
            target = root / "executed_sources" / path.relative_to(REPO)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for file in ("adversarial_pipeline/llm_client.py", "web_agent_benchmark/evaluation/qwen3_vl_server.py", "research/path_compat.py"):
        path = REPO / file
        if path.exists():
            target = root / "executed_sources" / file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    git = subprocess.run(["git", "-c", f"safe.directory={REPO}", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    core.write_json(root / "runtime.json", dict(python=platform.python_version(), git_head=git.stdout.strip() if git.returncode == 0 else None,
        source_identity="runtime source copies include uncommitted code; not inferred from Git HEAD alone",
        protocol=PROTOCOL_VERSION, automatic_launch=False, concurrency=1))


def snapshot_runtime(root, manifest_path, config_path):
    snapshot_sources(root)
    shutil.copy2(manifest_path, root / "TASK_MANIFEST.json")
    shutil.copy2(config_path, root / "MODEL_CONFIG.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PREPARED / "TASK_MANIFEST.json")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--retry-policy", type=Path, help="explicit transport-only overrides; no model/budget changes")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--execute", action="store_true", help="requires explicit panel authorization in config")
    args = parser.parse_args()
    manifest, config = json.loads(args.manifest.read_text()), json.loads(args.config.read_text())
    if args.retry_policy:
        overrides = json.loads(args.retry_policy.read_text())
        if not isinstance(overrides, dict) or not overrides or set(overrides) - RETRY_CONFIG_FIELDS:
            parser.error("retry-policy may contain only the four transport retry configuration fields")
        config["M_strong"].update(overrides)
        config["transport_retry_policy_source"] = str(args.retry_policy.resolve())
    validate_schedule(manifest)
    missing = readiness(config)
    if not args.execute:
        print(json.dumps(dict(status="local_readiness_only", missing=missing,
            prefixes=len(manifest["case_interleaved_order"]), strategy_records=len(initial_rows(manifest["case_interleaved_order"])),
            real_model_calls=0, network_requests=0), ensure_ascii=False, indent=2))
        return
    if missing:
        parser.error("No inference started: " + ", ".join(missing))
    if args.output is None or args.browser is None or not args.browser.is_file():
        parser.error("a new output directory and existing browser binary are required")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    snapshot_runtime(root, args.manifest, args.config)
    if args.retry_policy:
        shutil.copy2(args.retry_policy, root / "RETRY_POLICY.json")
        core.write_json(root / "MODEL_CONFIG.json", config)  # Effective config, not stale pre-CLI values.
    budgets = config["budgets"]
    ledger = core.BudgetLedger(max_model_calls=budgets["local_model_calls"] + budgets["api_model_calls"],
                               max_browser_transitions=budgets["browser_transitions"])
    carry_in_budget(ledger, config.get("carry_in_budget_source"))
    ledger.bind_snapshot(root / "budget.json")
    result = dict(prefixes=[], rows=initial_rows(manifest["case_interleaved_order"]))
    core.write_json(root / "progress.json", result)
    api = None
    try:
        # Both backends initialize BEFORE either one can generate a task prefix.
        small = config["M_small"]
        local = models.LocalQwenServiceBackend(server_url=small["server_url"], max_output_tokens=small["max_output_tokens"],
            temperature=small["temperature"], top_p=small["top_p"], seed=small["seed"])
        health = local.metadata["health"]
        if (resolve_path(health.get("model_path") or "") != resolve_path(small["weights"]) or health.get("max_pixels") != small["max_pixels"]
                or health.get("native_multi_image") is not True):
            raise RuntimeError("running Qwen service differs from the approved image/model configuration")
        views = {name: ModelBudget(ledger, name, budgets["local_model_calls" if name == "M_small" else "api_model_calls"]) for name in BACKBONES}
        api = IntranetApiBackend(ApiConfig(**config["M_strong"]), artifact_dir=root / "api_wire",
                                 retry_charge=views["M_strong"].charge_model)
        backends = dict(M_small=local, M_strong=api)
        recorded = {name: models.RecordedModel(backends[name], ledger=views[name]) for name in BACKBONES}
        for name, recorder in recorded.items():
            recorder._ordinal = sum(e["kind"] == "model_call" and e["request_id"].startswith(name + "/") for e in ledger.events)
        core.write_json(root / "backend_metadata.json", {name: b.metadata for name, b in backends.items()})
        from .panel_controls import qualify
        with runner.require_playwright()() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=str(args.browser), args=list(runner.BROWSER_LAUNCH_ARGS), timeout=20000)
            try:
                # A fixed non-chart qualification, not repeated until PASS.
                if config.get("qualified_controls_source"):
                    observed = prior_control_usage(config, root)
                else:
                    for name in reversed(BACKBONES):
                        qualify(browser, recorded[name], views[name], root / "online" / "controls" / name)
                    observed = [Decimal(e["usage_cost_upper_usd"]) for e in api.spend.entries if "usage_cost_upper_usd" in e]
                # Cost planning occurs before any prospective task, never after selecting wins.
                planning = config.get("cost_planning")
                if planning:
                    if (not config.get("qualified_controls_source") and len(observed) != len(api.spend.entries)) or not observed:
                        raise ApiStop("complete API control usage needed for pre-panel cost planning")
                    forecast = (max(observed) * planning["control_to_panel_cost_multiplier"] * planning["main_api_call_upper_limit"]
                                + api.spend.accounted_upper() + api.spend.ceiling)
                    core.write_json(root / "pre_panel_cost_estimate.json", dict(planning=planning,
                        max_control_usage_upper_usd=str(max(observed)), projected_upper_scenario_usd=str(forecast),
                        authorized_cap_usd=str(api.spend.cap), fits=forecast <= api.spend.cap,
                        note="Planning scenario, not a guarantee; live per-request conservative reservations still apply."))
                    if forecast > api.spend.cap:
                        raise core.BudgetExceeded("pre-panel control-based cost scenario exceeds approved cap; no tasks started")
                result = execute_schedule(browser, manifest, recorded, views, ledger, root,
                    prefix_calls=budgets["prefix_calls"], prefix_transitions=budgets["prefix_transitions"],
                    continuation_calls=budgets["continuation_calls"])
            finally:
                try:
                    browser.close()
                except Exception as exc:
                    core.write_json(root / "browser_cleanup_error.json", dict(error_type=type(exc).__name__))
    except Exception as exc:
        core.write_json(root / "stop.json", dict(error_type=type(exc).__name__, stage="startup_or_controls",
            note="Entire panel stopped after bounded transport handling; no single-model substitute or task restart."))
        for row in result["rows"]:
            row.update(status="not_run_startup_or_controls_failed")
        core.write_json(root / "progress.json", result)
    finally:
        if api is not None:
            try:
                api.close()
            except Exception as exc:
                core.write_json(root / "api_cleanup_error.json", dict(error_type=type(exc).__name__))
    summary = offline_report(manifest, result, ledger, root)
    print(json.dumps(dict(output=str(root), costs=summary["costs"]["experiment_actual"], stopped=(root / "stop.json").exists()), indent=2))


if __name__ == "__main__":
    main()
