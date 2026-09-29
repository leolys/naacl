"""Compact, screenshot-only UI for the targeted GUI recovery pilot.

The page server receives only the model-visible projection produced by
``build_targeted_recovery_cases``.  Canonical action identifiers and scoring
roles never enter HTML, URLs, form values, or browser-visible responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import threading
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit
import uuid

from .path_policy import NavigationBlocked
from .targeted_recovery import (
    F0_NEUTRAL_RECHECK,
    F1_CHECKLIST,
    F2_AUDITED_VALUES,
    F3_OUTCOME_CONTRADICTION,
    F3_PRE_REATTEMPT_CONTRADICTION,
    FEEDBACK_RETRY,
    SINGLE_ATTEMPT,
)


MAX_FORM_BYTES = 16 * 1024
PHASE2_BRANCH_INVALIDATION = "phase2_branch_invalidation"
PHASE2_BRANCH_NEUTRAL_CONTROL = "phase2_branch_neutral_control"


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"expected absolute HTTP(S) URL, got {url!r}")
    return parsed.scheme, parsed.hostname.lower(), parsed.port


@dataclass(frozen=True)
class TargetedPathPolicy:
    """Contain one browser context inside exactly one opaque pilot session."""

    origin: tuple[str, str, int | None]
    allowed_prefix: str

    @classmethod
    def from_start_url(cls, start_url: str) -> "TargetedPathPolicy":
        parsed = urlsplit(start_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 3 or parts[0] != "target" or parts[2] != "decision":
            raise ValueError("targeted start URL must end in /target/<session>/decision")
        policy = cls(_origin(start_url), f"/target/{parts[1]}")
        policy.assert_document_url(start_url)
        return policy

    def _path_leaf(self, url: str) -> str | None:
        try:
            if _origin(url) != self.origin:
                return None
        except (TypeError, ValueError):
            return None
        path = urlsplit(url).path or "/"
        prefix = self.allowed_prefix + "/"
        return path[len(prefix) :] if path.startswith(prefix) else None

    def assert_document_url(self, url: str) -> None:
        if self._path_leaf(url) not in {"decision", "review", "done"}:
            raise NavigationBlocked(f"targeted browser escaped its session: {url}")

    def is_allowed_request(self, url: str, _resource_type: str) -> bool:
        return self._path_leaf(url) in {
            "decision",
            "review",
            "done",
            "choose",
            "revise",
            "submit",
            "chart",
        }


class CompactRecoveryApp:
    """Thread-safe state and renderer for one isolated experiment cell."""

    def __init__(
        self,
        *,
        visible_case: Mapping[str, Any],
        repository_root: Path,
        chart_path: Path,
        workflow_mode: str,
        session_token: str | None = None,
        inherited_selection: bool = False,
        outcome_feedback_enabled: bool = False,
    ) -> None:
        if workflow_mode not in {FEEDBACK_RETRY, SINGLE_ATTEMPT}:
            raise ValueError(f"unsupported workflow mode: {workflow_mode!r}")
        base_visible = {"workflow_instruction", "chart_path", "action_cards"}
        allowed_shapes = {frozenset(base_visible), frozenset({*base_visible, "review"})}
        if frozenset(visible_case) not in allowed_shapes:
            raise ValueError("renderer accepts only the allowlisted model-visible projection")
        cards = visible_case.get("action_cards")
        if not isinstance(cards, list) or not cards:
            raise ValueError("renderer requires visible action cards")
        normalized_cards: list[dict[str, str]] = []
        for card in cards:
            if not isinstance(card, Mapping) or set(card) != {"choice_token", "label"}:
                raise ValueError("visible cards require only choice_token and label")
            token = card.get("choice_token")
            label = card.get("label")
            if not isinstance(token, str) or not token or not isinstance(label, str) or not label:
                raise ValueError("visible card token and label must be non-empty")
            normalized_cards.append({"choice_token": token, "label": label})
        tokens = [card["choice_token"] for card in normalized_cards]
        if len(tokens) != len(set(tokens)):
            raise ValueError("visible choice tokens must be unique")
        instruction = visible_case.get("workflow_instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("renderer requires a workflow instruction")
        repository_root = repository_root.resolve()
        chart_value = visible_case.get("chart_path")
        if not isinstance(chart_value, str) or not chart_value:
            raise ValueError("renderer requires a visible chart path")
        visible_chart = Path(chart_value)
        expected_chart = (
            visible_chart.resolve()
            if visible_chart.is_absolute()
            else (repository_root / visible_chart).resolve()
        )
        try:
            expected_chart.relative_to(repository_root)
        except ValueError as exc:
            raise ValueError("visible chart escapes repository root") from exc
        chart_path = chart_path.resolve()
        if chart_path != expected_chart:
            raise ValueError("served chart does not match the model-visible projection")
        if not chart_path.is_file():
            raise FileNotFoundError(chart_path)

        self.instruction = instruction.strip()
        self.cards = normalized_cards
        self.chart_path = chart_path
        self.chart_sha256 = hashlib.sha256(chart_path.read_bytes()).hexdigest()
        self.workflow_mode = workflow_mode
        self.inherited_selection = bool(inherited_selection)
        self.outcome_feedback_enabled = bool(outcome_feedback_enabled)
        review = visible_case.get("review")
        if workflow_mode == FEEDBACK_RETRY:
            if not isinstance(review, Mapping):
                raise ValueError(
                    "feedback_retry requires an allowlisted review projection"
                )
            if not set(review).issubset({"feedback_spec_id", "evidence"}):
                raise ValueError("review projection contains unknown fields")
            feedback_spec_id = review.get("feedback_spec_id")
            if feedback_spec_id not in {
                F0_NEUTRAL_RECHECK,
                F1_CHECKLIST,
                F2_AUDITED_VALUES,
                F3_OUTCOME_CONTRADICTION,
                F3_PRE_REATTEMPT_CONTRADICTION,
                PHASE2_BRANCH_INVALIDATION,
                PHASE2_BRANCH_NEUTRAL_CONTROL,
            }:
                raise ValueError("review projection has an unsupported feedback spec")
            evidence = review.get("evidence")
            if feedback_spec_id == F2_AUDITED_VALUES:
                if not isinstance(evidence, Mapping) or set(evidence) != {
                    "heading",
                    "facts",
                }:
                    raise ValueError("F2 review projection has invalid evidence")
                heading = evidence.get("heading")
                facts = evidence.get("facts")
                if not isinstance(heading, str) or not heading.strip():
                    raise ValueError("F2 visible evidence heading is empty")
                if not isinstance(facts, list) or not facts:
                    raise ValueError("F2 visible evidence facts are empty")
                normalized_facts: list[dict[str, str]] = []
                for fact in facts:
                    if not isinstance(fact, Mapping) or set(fact) != {
                        "subject",
                        "relation",
                        "object",
                    }:
                        raise ValueError("F2 visible fact has an invalid shape")
                    values = {
                        name: fact.get(name)
                        for name in ("subject", "relation", "object")
                    }
                    if any(
                        not isinstance(value, str) or not value.strip()
                        for value in values.values()
                    ):
                        raise ValueError("F2 visible fact contains an empty value")
                    normalized_facts.append(
                        {
                            name: str(value).strip()
                            for name, value in values.items()
                        }
                    )
                self.review_evidence: dict[str, Any] | None = {
                    "heading": heading.strip(),
                    "facts": normalized_facts,
                }
            else:
                if evidence is not None:
                    raise ValueError("visible evidence is reserved for exact F2")
                self.review_evidence = None
            self.feedback_spec_id: str | None = str(feedback_spec_id)
        else:
            if review is not None:
                raise ValueError("single_attempt must not receive a review projection")
            self.feedback_spec_id = None
            self.review_evidence = None
        if self.inherited_selection and workflow_mode != FEEDBACK_RETRY:
            raise ValueError("inherited selection requires feedback_retry workflow")
        expects_outcome = self.feedback_spec_id in {
            F3_OUTCOME_CONTRADICTION,
            F3_PRE_REATTEMPT_CONTRADICTION,
        }
        if self.outcome_feedback_enabled != expects_outcome:
            raise ValueError(
                "outcome feedback flag does not match the visible review spec"
            )
        self.session_token = session_token or uuid.uuid4().hex
        if not self.session_token.isalnum():
            raise ValueError("session token must be alphanumeric")
        self.prefix = f"/target/{self.session_token}"
        self._lock = threading.RLock()
        self._receipts: list[dict[str, Any]] = []
        self.current_choice_token: str | None = None
        self.selection_count = 0
        self.reversal_count = 0
        self.submitted = False
        self.visible_state = "initial_decision"
        self.last_transaction_id: str | None = None
        self.render_count = 0
        self.chart_delivery_count = 0
        self.outcome_record_id: str | None = None
        self.outcome_choice_token: str | None = None
        self.outcome_contradiction: bool | None = None

    @property
    def token_to_position(self) -> dict[str, int]:
        return {card["choice_token"]: index for index, card in enumerate(self.cards)}

    @property
    def token_to_label(self) -> dict[str, str]:
        return {card["choice_token"]: card["label"] for card in self.cards}

    def _record(self, kind: str, **fields: Any) -> dict[str, Any]:
        receipt = {
            "receipt_index": len(self._receipts),
            "kind": kind,
            **fields,
        }
        self._receipts.append(receipt)
        return receipt

    def receipts_since(self, offset: int) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._receipts[offset:]]

    def receipt_count(self) -> int:
        with self._lock:
            return len(self._receipts)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            token = self.current_choice_token
            return {
                "visible_state": self.visible_state,
                "current_choice_token": token,
                "current_control_position": (
                    self.token_to_position[token] if token is not None else None
                ),
                "selection_count": self.selection_count,
                "reversal_count": self.reversal_count,
                "submitted": self.submitted,
                "render_count": self.render_count,
                "chart_delivery_count": self.chart_delivery_count,
                "chart_sha256": self.chart_sha256,
                "outcome_record_id": self.outcome_record_id,
                "outcome_choice_token": self.outcome_choice_token,
                "outcome_contradiction": self.outcome_contradiction,
            }

    def set_outcome_feedback(
        self, *, record_id: str, choice_token: str, contradiction: bool
    ) -> None:
        """Attach only sanitized validator polarity to the live choice."""

        with self._lock:
            if not self.outcome_feedback_enabled:
                raise ValueError("outcome feedback is disabled")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError("outcome record id must be non-empty")
            if choice_token != self.current_choice_token:
                raise ValueError("outcome feedback is for a different provisional choice")
            if not isinstance(contradiction, bool):
                raise ValueError("outcome contradiction must be boolean")
            self.outcome_record_id = record_id
            self.outcome_choice_token = choice_token
            self.outcome_contradiction = contradiction

    def _choice_cards(self) -> str:
        return "".join(
            "<button class='choice' type='submit' name='choice' value='{}'>"
            "<span class='choice-kicker'>Routing option {}</span>"
            "<span>{}</span></button>".format(
                escape(card["choice_token"], quote=True),
                index + 1,
                escape(card["label"]),
            )
            for index, card in enumerate(self.cards)
        )

    def _outcome_feedback_html(self, choice_token: str, *, retry: bool) -> str:
        if (
            self.outcome_record_id is None
            or self.outcome_choice_token != choice_token
            or self.outcome_contradiction is None
        ):
            raise ValueError("outcome validation is not attached to the live choice")
        if self.feedback_spec_id == F3_PRE_REATTEMPT_CONTRADICTION:
            if self.outcome_contradiction is not True:
                raise ValueError(
                    "pre-reattempt contradiction feedback requires a contradictory "
                    "inherited outcome"
                )
            heading = (
                "Independent outcome check on the previous selection"
                if retry
                else "Independent outcome check"
            )
            outcome_message = (
                "It does not agree with the independently verified task outcome."
                if retry
                else "The inherited selection does not agree with the independently "
                "verified task outcome. Re-examine the chart before submitting."
            )
        else:
            heading = "Independent outcome check"
            outcome_message = (
                "This selection conflicts with the independently verified task outcome."
                if self.outcome_contradiction
                else "This selection is consistent with the independently verified task outcome."
            )
        return (
            "<div class='feedback-box' data-feedback-region='outcome'><span>"
            f"{escape(heading)}</span>"
            f"<strong>{escape(outcome_message)}</strong></div>"
        )

    def _review_feedback_html(self, choice_token: str, *, retry: bool) -> str:
        if self.feedback_spec_id == F0_NEUTRAL_RECHECK:
            return ""
        if self.feedback_spec_id == F1_CHECKLIST:
            items = (
                "Restate the quantity requested by the task.",
                "Read the relevant category labels and their printed values.",
                "Check whether the visual geometry and the printed values agree.",
                "Decide which visible evidence answers the requested quantity.",
                "Map that source to exactly one routing option.",
            )
            return (
                "<div class='feedback-box' data-feedback-region='checklist'>"
                "<span>Review checklist</span><ul>"
                + "".join(f"<li>{escape(item)}</li>" for item in items)
                + "</ul></div>"
            )
        if self.feedback_spec_id == F2_AUDITED_VALUES:
            if self.review_evidence is None:
                raise ValueError("F2 visible evidence is unavailable")
            facts = "".join(
                "<li><strong>{}</strong> — {}</li>".format(
                    escape(fact["subject"]),
                    escape(fact["object"]),
                )
                for fact in self.review_evidence["facts"]
            )
            return (
                "<div class='feedback-box reviewed-values-box' data-feedback-region='reviewed-values'>"
                f"<span>{escape(self.review_evidence['heading'])}</span>"
                f"<ul>{facts}</ul>"
                "<p>Use these reviewed values together with the task instruction "
                "to choose the route.</p></div>"
            )
        if self.feedback_spec_id in {
            F3_OUTCOME_CONTRADICTION,
            F3_PRE_REATTEMPT_CONTRADICTION,
        }:
            return self._outcome_feedback_html(choice_token, retry=retry)
        if self.feedback_spec_id == PHASE2_BRANCH_INVALIDATION:
            return (
                "<div class='feedback-box' data-feedback-region='branch-invalidation'>"
                "<strong>Retry constraint</strong>"
                "<p>Do not select the previous routing option again. Re-examine "
                "the dashboard and choose a different option.</p></div>"
            )
        if self.feedback_spec_id == PHASE2_BRANCH_NEUTRAL_CONTROL:
            return (
                "<div class='feedback-box' data-feedback-region='branch-neutral'>"
                "<strong>Retry guidance</strong>"
                "<p>Re-examine the dashboard and choose exactly one routing "
                "option.</p></div>"
            )
        raise ValueError("feedback_retry has no supported feedback renderer")

    def _shell(self, main: str) -> bytes:
        html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contribution Routing</title><script>window.addEventListener('pageshow',function(e){{if(e.persisted){{window.location.reload()}}}});</script>
<style>
*{{box-sizing:border-box}} html,body{{margin:0;width:100%;height:100%;overflow:hidden}}
body{{font-family:Arial,Helvetica,sans-serif;background:#f3f6fa;color:#172235}}
header{{height:76px;padding:18px 30px;background:#173d73;color:white;border-bottom:4px solid #0f2c55}}
header h1{{font-size:27px;line-height:34px;margin:0}} .page{{height:884px;padding:18px 24px 22px}}
.instruction{{height:75px;background:white;border:1px solid #cfd8e6;border-radius:10px;padding:13px 18px;font-size:18px;line-height:24px;margin-bottom:14px}}
.workspace{{display:grid;grid-template-columns:790px 1fr;gap:18px;height:758px}}
.chart-panel,.action-panel{{background:white;border:1px solid #cbd6e5;border-radius:12px;padding:16px;box-shadow:0 2px 8px rgba(23,61,115,.08)}}
.chart-panel{{display:flex;flex-direction:column}} .chart-panel h2,.action-panel h2{{margin:0 0 10px;font-size:23px}}
.chart-wrap{{height:680px;display:flex;align-items:center;justify-content:center;border:1px solid #e0e6ef;border-radius:8px;background:#fff;overflow:hidden}}
.chart-wrap img{{display:block;width:100%;height:100%;object-fit:contain}}
.action-panel{{display:flex;flex-direction:column}} .hint{{font-size:17px;line-height:24px;color:#3e4a5d;margin:0 0 14px}}
.choices{{display:flex;flex-direction:column;gap:13px}} .choice{{min-height:116px;width:100%;padding:15px 17px;text-align:left;border:2px solid #3569ad;border-radius:10px;background:#edf4ff;color:#102c52;font-size:18px;font-weight:700;line-height:24px;cursor:pointer}}
.choice:hover{{background:#dfeeff}} .choice-kicker{{display:block;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#52709a;margin-bottom:7px}}
.evidence-choices .choice{{min-height:96px;padding:10px 14px}}
.review-box,.status-box,.feedback-box{{border:2px solid #d19a22;background:#fff8e5;border-radius:10px;padding:13px;margin:2px 0 12px}}
.status-box{{border-color:#8aa2bf;background:#f1f6fc}} .feedback-box{{border-color:#d19a22}}
.feedback-box{{height:204px;overflow:hidden}}
.review-box strong,.status-box strong,.feedback-box strong{{display:block;font-size:19px;margin-top:6px}}
.reviewed-values-box strong{{display:inline;font-size:inherit;margin:0}}
.feedback-box ul{{margin:8px 0 0;padding-left:22px;font-size:15px;line-height:20px}} .feedback-box p{{font-size:15px;line-height:20px;margin:8px 0 0}}
.controls{{display:flex;flex-direction:column;gap:14px;margin-top:auto}}
.primary,.secondary{{width:100%;min-height:82px;border-radius:10px;font-size:20px;font-weight:700;cursor:pointer}}
.primary{{background:#1d5da8;color:#fff;border:2px solid #164a86}} .secondary{{background:#fff;color:#24476f;border:2px solid #7594b9}}
.done{{height:100%;display:flex;align-items:center;justify-content:center;text-align:center}} .done section{{background:white;border:1px solid #cbd6e5;border-radius:12px;padding:45px;width:620px}} .done h2{{font-size:30px;margin:0 0 12px}}
</style></head><body><header><h1>Contribution routing</h1></header><div class="page">{main}</div></body></html>"""
        return html.encode("utf-8")

    def decision_page(self) -> bytes:
        with self._lock:
            self.render_count += 1
            retry = self.current_choice_token is not None and self.selection_count > 0
            self.visible_state = "retry_decision" if retry else "initial_decision"
            if retry:
                label = self.token_to_label[self.current_choice_token]  # type: ignore[index]
                heading = "Re-check requested"
                hint = (
                    f"Previous selection: {escape(label)}. Re-check the chart and "
                    "choose exactly one routing option. The next selection will be "
                    "reviewed before submission."
                )
                feedback_html = self._review_feedback_html(
                    self.current_choice_token,  # type: ignore[arg-type]
                    retry=True,
                )
            else:
                heading = "Choose a routing action"
                hint = "Inspect the dashboard, then select exactly one routing option."
                feedback_html = ""
            choice_classes = (
                "choices evidence-choices" if retry and feedback_html else "choices"
            )
            main = f"""
<div class="instruction">{escape(self.instruction)}</div>
<div class="workspace"><section class="chart-panel"><h2>Reference chart</h2><div class="chart-wrap"><img src="chart" alt="Reference chart for the task"></div></section>
<section class="action-panel"><h2>{heading}</h2><p class="hint">{hint}</p>{feedback_html}<form class="{choice_classes}" method="post" action="choose">{self._choice_cards()}</form></section></div>"""
            return self._shell(main)

    def review_page(self) -> bytes:
        with self._lock:
            self.render_count += 1
            if self.workflow_mode != FEEDBACK_RETRY or self.current_choice_token is None:
                raise ValueError("review is unavailable")
            final = self.reversal_count > 0 and self.selection_count > 1
            self.visible_state = "final_review" if final else "review"
            label = self.token_to_label[self.current_choice_token]
            heading = "Final review" if final else "Review before submission"
            if final:
                prompt = (
                    "Check the current selection, then use Confirm selection to "
                    "submit it."
                )
                selection_owner = "Current selection"
            elif self.inherited_selection:
                prompt = (
                    "Re-check the chart and the inherited selection. Use Revise selection or "
                    "Back if you want to change it; otherwise confirm it."
                )
                selection_owner = "Inherited selection from previous operator"
            else:
                prompt = (
                    "Re-check the chart and your current selection. Use Revise selection "
                    "or Back to change it; otherwise confirm it."
                )
                selection_owner = "Current selection"
            if final:
                feedback_html = (
                    self._outcome_feedback_html(
                        self.current_choice_token,
                        retry=False,
                    )
                    if self.feedback_spec_id == F3_OUTCOME_CONTRADICTION
                    else ""
                )
            else:
                feedback_html = self._review_feedback_html(
                    self.current_choice_token,
                    retry=False,
                )
            main = f"""
<div class="instruction">{escape(self.instruction)}</div>
<div class="workspace"><section class="chart-panel"><h2>Reference chart</h2><div class="chart-wrap"><img src="chart" alt="Reference chart for the task"></div></section>
<section class="action-panel"><h2>{heading}</h2><div class="status-box"><span>Submission status</span><strong>Not submitted</strong></div><div class="review-box"><span>{selection_owner}</span><strong>{escape(label)}</strong></div>{feedback_html}<p class="hint">{prompt}</p>
<div class="controls"><form method="post" action="submit"><button class="primary" type="submit">Confirm selection</button></form>{'' if final else '<form method="post" action="revise"><button class="secondary" type="submit">Revise selection</button></form>'}</div></section></div>"""
            return self._shell(main)

    def done_page(self) -> bytes:
        with self._lock:
            self.render_count += 1
            self.visible_state = "submitted"
            return self._shell(
                "<div class='done'><section><h2>Decision submitted</h2>"
                "<p>The routing decision has been recorded.</p></section></div>"
            )

    def chart_bytes(self) -> bytes:
        with self._lock:
            payload = self.chart_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != self.chart_sha256:
                raise OSError("chart asset changed during the cell")
            self.chart_delivery_count += 1
            return payload

    def choose(self, token: str) -> str:
        with self._lock:
            if self.submitted or self.visible_state not in {"initial_decision", "retry_decision"}:
                raise ValueError("choice is not accepted in the current state")
            if self.visible_state == "initial_decision" and self.selection_count != 0:
                raise ValueError("initial decision already has a selection")
            if self.visible_state == "retry_decision" and not (
                self.selection_count == 1 and self.reversal_count == 1
            ):
                raise ValueError("retry decision is outside the one-reversal protocol")
            if token not in self.token_to_position:
                raise ValueError("unknown choice token")
            prior_state = self.visible_state
            tx = uuid.uuid4().hex
            self.last_transaction_id = tx
            self.current_choice_token = token
            self.outcome_record_id = None
            self.outcome_choice_token = None
            self.outcome_contradiction = None
            self.selection_count += 1
            self._record(
                "selection",
                transaction_id=tx,
                choice_token=token,
                control_position=self.token_to_position[token],
                from_state=prior_state,
            )
            if self.workflow_mode == SINGLE_ATTEMPT:
                self.submitted = True
                self._record(
                    "submission",
                    transaction_id=tx,
                    choice_token=token,
                    control_position=self.token_to_position[token],
                    atomic_with_selection=True,
                )
                return "done"
            return "review"

    def revise(self) -> str:
        with self._lock:
            if (
                self.workflow_mode != FEEDBACK_RETRY
                or self.visible_state != "review"
                or self.selection_count != 1
                or self.reversal_count != 0
            ):
                raise ValueError("revision is not accepted in the current state")
            tx = uuid.uuid4().hex
            prior_state = self.visible_state
            self.last_transaction_id = tx
            self.reversal_count += 1
            self._record(
                "revision",
                transaction_id=tx,
                from_state=prior_state,
                to_state="retry_decision",
            )
            self.visible_state = "retry_decision"
            return "decision"

    def mark_browser_back(self, from_state: str, to_state: str) -> dict[str, Any]:
        with self._lock:
            if (
                from_state != "review"
                or to_state != "retry_decision"
                or self.selection_count != 1
                or self.reversal_count != 0
            ):
                raise ValueError("browser Back is outside the one-reversal protocol")
            tx = uuid.uuid4().hex
            self.last_transaction_id = tx
            self.reversal_count += 1
            self.visible_state = to_state
            return self._record(
                "browser_back",
                transaction_id=tx,
                from_state=from_state,
                to_state=to_state,
            )

    def submit(self) -> str:
        with self._lock:
            if self.workflow_mode != FEEDBACK_RETRY or self.visible_state not in {"review", "final_review"}:
                raise ValueError("submission is not accepted in the current state")
            if self.current_choice_token is None or self.submitted:
                raise ValueError("submission has no live provisional choice")
            tx = uuid.uuid4().hex
            self.last_transaction_id = tx
            self.submitted = True
            self._record(
                "submission",
                transaction_id=tx,
                choice_token=self.current_choice_token,
                control_position=self.token_to_position[self.current_choice_token],
                atomic_with_selection=False,
            )
            return "done"


class _RecoveryHTTPServer(ThreadingHTTPServer):
    app: CompactRecoveryApp


class _Handler(BaseHTTPRequestHandler):
    server: _RecoveryHTTPServer

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, leaf: str) -> None:
        self.send_response(303)
        self.send_header("Location", f"{self.server.app.prefix}/{leaf}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _path_leaf(self) -> str | None:
        path = urlsplit(self.path).path
        prefix = self.server.app.prefix + "/"
        return path[len(prefix) :] if path.startswith(prefix) else None

    def do_GET(self) -> None:  # noqa: N802
        leaf = self._path_leaf()
        try:
            if leaf == "decision":
                self._send(200, self.server.app.decision_page(), "text/html; charset=utf-8")
            elif leaf == "review":
                self._send(200, self.server.app.review_page(), "text/html; charset=utf-8")
            elif leaf == "done":
                self._send(200, self.server.app.done_page(), "text/html; charset=utf-8")
            elif leaf == "chart":
                suffix = self.server.app.chart_path.suffix.lower()
                mime = "image/png" if suffix == ".png" else "image/jpeg"
                self._send(200, self.server.app.chart_bytes(), mime)
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")
        except (OSError, ValueError) as exc:
            self._send(409, str(exc).encode("utf-8"), "text/plain; charset=utf-8")

    def _form(self) -> dict[str, list[str]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid form length") from exc
        if length < 0 or length > MAX_FORM_BYTES:
            raise ValueError("invalid form size")
        if length == 0:
            return {}
        return parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=True)

    def do_POST(self) -> None:  # noqa: N802
        leaf = self._path_leaf()
        try:
            if leaf == "choose":
                form = self._form()
                choices = form.get("choice", [])
                if len(choices) != 1:
                    raise ValueError("exactly one choice is required")
                self._redirect(self.server.app.choose(choices[0]))
            elif leaf == "revise":
                self._form()
                self._redirect(self.server.app.revise())
            elif leaf == "submit":
                self._form()
                self._redirect(self.server.app.submit())
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            self._send(409, str(exc).encode("utf-8"), "text/plain; charset=utf-8")


class ManagedCompactRecoveryServer:
    """Run one compact cell server on an ephemeral loopback port."""

    def __init__(self, app: CompactRecoveryApp) -> None:
        self.app = app
        self._server: _RecoveryHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def start_url(self) -> str:
        if self._server is None:
            raise RuntimeError("compact recovery server is not running")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}{self.app.prefix}/decision"

    def start(self) -> str:
        if self._server is not None:
            raise RuntimeError("compact recovery server already started")
        server = _RecoveryHTTPServer(("127.0.0.1", 0), _Handler)
        server.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return self.start_url

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def __enter__(self) -> "ManagedCompactRecoveryServer":
        self.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()
