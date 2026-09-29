"""Durable pre-request reservations and conservative ESTIMATED USD accounting.

This controls an estimate, not the provider invoice. Unresolved usage keeps its
reservation. Reconciliation may exceed a reservation; no subsequent call is then
admitted if its reservation would cross the cap. Historical reused calls are
outside this new-request ledger and remain separately attributed.
"""
from decimal import Decimal
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "apiyi_selection_20260924"))
import panel_core as core
from analyze_usage import normalize_usage


def money(value):
    return Decimal(str(value))


class EstimatedBudget:
    def __init__(self, path, config):
        self.path, self.config = Path(path), config
        self.current_folder = None
        self.value = core.read(self.path, {
            "schema_version": 1, "request_attempts": 0, "browser_operations": 0,
            "events": [], "estimated_ledger_usd": 0, "blocked_reason": None,
            "actual_charge_usd": None,
            "accounting_scope": "new_requests_only_reused_historical_calls_excluded",
            "cost_policy": "all_input_times_2.5_plus_output_times_12_per_million_no_cache_discount",
            "cost_warning": "ESTIMATED proxy, not invoice and not guaranteed upper bound",
        })
        if self.value["request_attempts"] != len(self.value["events"]):
            raise ValueError("budget event count mismatch; audit required")
        self.reconcile()

    def save(self):
        self.value["estimated_ledger_usd"] = float(sum(
            (money(event["charged_estimated_usd"]) for event in self.value["events"]), Decimal(0)))
        core.dump(self.path, self.value)

    def stop(self, reason):
        self.value["blocked_reason"] = reason
        self.save()
        raise core.ServiceStop(reason)

    def reconcile(self):
        for event in self.value["events"]:
            if event["accounting_status"] == "usage_reconciled":
                continue
            response_path = Path(event["folder"]) / ("response_%02d.json" % event["attempt"])
            if not response_path.is_file():
                continue
            response = core.read(response_path)
            usage = response.get("usage") if isinstance(response, dict) else None
            normalized = normalize_usage(usage if isinstance(usage, dict) else {})
            event["normalized_usage"] = normalized
            event["response_sha256"] = core.digest(response_path)
            if normalized["errors"] or normalized["values"]["input_tokens"] > 272000:
                event["accounting_status"] = "unknown_usage_reserve_retained"
                continue
            counts = normalized["values"]
            amount = (money(counts["input_tokens"]) * money(self.config["estimated_input_usd_per_m"])
                      + money(counts["output_tokens"]) * money(self.config["estimated_output_usd_per_m"])) / 1000000
            event.update(charged_estimated_usd=float(amount), accounting_status="usage_reconciled",
                         reconciled_at=time.time())
        self.save()

    def charge(self, detail):
        # PanelAPI calls this immediately BEFORE every network attempt, including retries.
        self.reconcile()
        if self.value.get("blocked_reason"):
            raise core.ServiceStop(self.value["blocked_reason"])
        if self.value["request_attempts"] >= self.config["max_request_attempts"]:
            self.stop("local_request_budget_exhausted")
        reserve = money(self.config["attempt_reserve_usd"])
        if money(self.value["estimated_ledger_usd"]) + reserve > money(self.config["max_estimated_usd"]):
            self.stop("local_estimated_usd_budget_exhausted")
        if self.current_folder is None:
            raise ValueError("attempt folder must be bound before charging")
        if detail["phase"] not in ("proposal", "generation", "verification"):
            raise ValueError("API translation and other phases are forbidden")
        self.value["request_attempts"] += 1
        self.value["events"].append({**detail, "time": time.time(),
            "folder": str(Path(self.current_folder).resolve()),
            "reserved_estimated_usd": float(reserve), "charged_estimated_usd": float(reserve),
            "accounting_status": "pending_or_unknown_reserve_retained"})
        self.save()


class BudgetedPanelAPI(core.PanelAPI):
    """Reuse the original payload, retry and unknown-outcome behavior unchanged."""
    def call(self, folder, task_id, phase, prompt, context, images):
        if phase not in ("proposal", "generation", "verification"):
            raise ValueError("API translation and other phases are forbidden")
        self.budget.current_folder = Path(folder)
        try:
            return super().call(folder, task_id, phase, prompt, context, images)
        finally:
            self.budget.reconcile()
            self.budget.current_folder = None
