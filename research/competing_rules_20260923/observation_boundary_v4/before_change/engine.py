"""Bounded competing-interpretation prototype. No evaluator/data-loader imports."""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import time
from pathlib import Path

import requests


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def append(path, value):
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")


class Budget:
    def __init__(self, root, config):
        self.path = Path(root) / "budget.json"
        self.config = config
        self.attempts = 0
        self.operations = 0
        self.events = []

    def charge(self, kind, detail):
        if kind == "request":
            if self.attempts >= self.config["max_request_attempts"]:
                raise RuntimeError("request budget exhausted")
            self.attempts += 1
        else:
            if self.operations >= self.config["max_browser_operations"]:
                raise RuntimeError("browser budget exhausted")
            self.operations += 1
        self.events.append({"kind": kind, "detail": detail, "time": time.time()})
        dump(self.path, {"attempts": self.attempts, "browser_operations": self.operations,
                         "events": self.events})

    def transition(self, action):
        self.charge("browser", action)


FORBIDDEN = {"ground_truth", "correct_value", "correct_action_id", "expected_action_id",
             "misleader_type", "misleading_context", "rationale", "csv_path", "source_csv",
             "misleading_action_ids", "scoring_outcome", "error_attribution", "gold",
             "evaluation_hidden_from_agent", "role", "action_space", "condition"}


def assert_public(value):
    if isinstance(value, dict):
        bad = set(value) & FORBIDDEN
        if bad:
            raise ValueError("private key in online data: " + str(sorted(bad)))
        for item in value.values():
            assert_public(item)
    elif isinstance(value, list):
        for item in value:
            assert_public(item)


def parse_json(text, allow_trailing_closers=False, repair_log=None):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        if not allow_trailing_closers:
            raise
        value, end = json.JSONDecoder().raw_decode(text)
        suffix = text[end:]
        # A complete object must already exist. Never recover text, a second
        # value, truncated content, or an alternative action from a response.
        if (not isinstance(value, dict) or set(value) != {"rules", "chains"}
                or not all(isinstance(value[k], list) for k in ("rules", "chains"))
                or not re.fullmatch(r"[\s}\]]+", suffix)):
            raise ValueError("JSON suffix is not redundant closing delimiters")
        if repair_log is not None:
            repair_log.append({"rule": "ignore_only_closers_after_complete_object",
                               "object_end": end, "ignored_suffix": suffix,
                               "rule_count": len(value["rules"]), "chain_count": len(value["chains"])})
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


class API:
    def __init__(self, config, budget):
        self.config, self.budget = config, budget
        self.key = os.environ.get("MODEL_API_KEY")
        if not self.key:
            raise RuntimeError("Set MODEL_API_KEY; credentials are not bundled")
        self.session = requests.Session()
        self.session.trust_env = False
        if config.get("proxy"):
            self.session.proxies.update({"https": config["proxy"], "http": config["proxy"]})

    def call(self, folder, phase, system, context, images):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        assert_public(context)
        content = [{"type": "text", "text": json.dumps(context, ensure_ascii=False)}]
        for ref, path in images:
            image_path = Path(path)
            mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
            content += [{"type": "text", "text": "Observation " + ref},
                        {"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," +
                          base64.b64encode(image_path.read_bytes()).decode("ascii")}}]
        payload = {"model": self.config["model"], "temperature": self.config["temperature"],
                   "max_tokens": self.config["max_tokens"], "messages": [
                       {"role": "system", "content": system}, {"role": "user", "content": content}]}
        # Full actual wire body, never Authorization. Image references are also saved for easy reading.
        dump(folder / "request.json", payload)
        dump(folder / "context.json", {"phase": phase, "context": context,
                                      "images": [{"ref": r, "file": str(p)} for r, p in images]})
        for attempt in range(1, self.config["max_attempts_per_call"] + 1):
            self.budget.charge("request", {"phase": phase, "attempt": attempt})
            started = time.time()
            meta = {"attempt": attempt, "requested_model": payload["model"], "phase": phase}
            transient = False
            try:
                response = self.session.post(self.config["endpoint"], json=payload,
                    headers={"Authorization": "Bearer " + self.key},
                    timeout=self.config["timeout_seconds"])
                meta["http_status"] = response.status_code
                try:
                    body = response.json()
                except ValueError:
                    body = {"unparsed_body": response.text[:2000]}
                dump(folder / ("response_%02d.json" % attempt), body)
                meta.update(response_model=body.get("model"), usage=body.get("usage"),
                            response_id=body.get("id"))
                transient = response.status_code in (408, 429, 500, 502, 503, 504)
                if response.status_code != 200:
                    raise RuntimeError("HTTP " + str(response.status_code))
                text = body["choices"][0]["message"]["content"]
                meta["elapsed_seconds"] = time.time() - started
                dump(folder / ("attempt_%02d.json" % attempt), meta)
                repairs = []
                finish = body["choices"][0].get("finish_reason")
                result = parse_json(text, self.config.get("allow_trailing_json_closers", False)
                                    and phase == "generate" and finish == "stop", repairs)
                if repairs:
                    repairs[0]["finish_reason"] = finish
                    dump(folder / "json_representation_normalization.json", repairs)
                dump(folder / "parsed.json", result)
                return result
            except (requests.RequestException, RuntimeError, ValueError, KeyError, IndexError) as exc:
                if isinstance(exc, requests.RequestException):
                    transient = True
                meta.update(error=type(exc).__name__ + ": " + str(exc)[:500],
                            elapsed_seconds=time.time() - started, retryable=transient)
                dump(folder / ("attempt_%02d.json" % attempt), meta)
                if not transient or attempt == self.config["max_attempts_per_call"]:
                    raise RuntimeError("API call failed: " + meta["error"]) from exc
                time.sleep(min(attempt * 2, 6))


ACTOR = """You operate this task's web form using only supplied public task, observed chart,
page and real execution history. Work out the required choice from visible evidence.
Output one JSON object with keys action, brief_basis, used_rule_ids, new_evidence,
challenge_previous_verification (boolean, normally false).
action is one of {\"kind\":\"select\",\"option\":\"exact visible label\"},
{\"kind\":\"fill\",\"field\":\"field id\",\"value\":\"text\"},
{\"kind\":\"check\",\"field\":\"field id\",\"value\":true},
{\"kind\":\"submit\"}, {\"kind\":\"observe\"}.
If the option required by your interpretation is already selected, required fields are
complete and a submit control is visible, you may submit. Otherwise revise or observe.
A nonempty selection alone is not completion. Do not invent execution receipts.
brief_basis is a concise evidence citation, not a step-by-step reasoning transcript.
If rule records are supplied, use only applicable active rules as supported facts;
disputed/revoked rules are historical challenges, not current instructions. A new visible
finding may challenge previous verification. Cite used rule IDs, and put a concise actual
new observation in new_evidence if challenging; set challenge_previous_verification=true
only when asking to revise a prior verification, not when merely using its evidence.
Empty lists/strings are valid.
Verification recommendations are fallible past judgments, not commands to submit."""


GENERATOR = """Create concise checkable argument records for this proposed chart decision.
Use only the full observed chart, public task, actual history and supplied rule state.
Return JSON {\"rules\":[{\"id\":\"r1\",\"text\":\"interpretation relation, NOT a chosen answer\",
\"component\":\"axis/legend/etc actually involved\",\"conditions\":\"scope of relation\"}],
\"chains\":[{\"observations\":[{\"ref\":\"chart_1\",\"location\":\"visible area\",\"content\":\"reading\"}],
\"rule_id\":\"r1\",\"option_label\":\"exact public option\",\"claim\":\"short task implication\"}]}.
Include the argument needed for the proposed choice, even if it has an evidence gap,
then at most two substantively different competing explanations. Alternatives may
support the SAME action on different grounds. Never force an opposite answer.
Normalize semantically identical rules to a single shared ID; preserve distinct entity
comparisons. Duplication is not corroboration. Rules describe encoding or inference
conditions, never store the winning entity/action. Observations may be approximate;
do not invent precise numbers when labels are absent. No long reasoning transcript."""


VERIFIER = """Independently verify normalized argument records against the FULL observed
chart and public task. Their order and repetition do not establish credibility.
Check O (observation/entity binding), B (interpretation rule within scope), implication
(whether supported premises suffice to satisfy the whole task). Distinguish these errors.
Return JSON {\"checks\":[{\"chain_id\":\"c1\",\"O\":\"supported|refuted|undetermined\",
\"B\":\"supported|refuted|undetermined\",\"implication\":\"supported|refuted|undetermined\",
\"evidence\":[{\"ref\":\"chart_1\",\"location\":\"actual visible area\",\"content\":\"reading and what it supports/refutes\"}],
\"reason\":\"concise distinction, not a reasoning transcript\"}],
\"recommendation\":\"exact option label or null\",\"unresolved_reason\":\"string\"}.
Use undetermined for insufficient visible evidence. Refuting one candidate is not proof
another is globally best. Rejecting taller-means-more does not establish shorter-means-more.
Opposing rules can both be undetermined. Reference annotations are evidence, not axioms.
Use only numbers you yourself can read or estimate in these images; state uncertainty.
Do not force agreement, reversal, or a recommendation. All chains must be checked."""


def normalized_candidates(generated, options, max_competitors=2, cap_by_order=False):
    rules = generated.get("rules", [])
    chains = generated.get("chains", [])
    if not rules or not chains or (len(chains) > max_competitors + 1 and not cap_by_order):
        raise ValueError("invalid candidate count")
    if cap_by_order:
        # Fixed generation order BEFORE deduplication; no answer-aware ranking
        # and no backfill. The proposed-option guard remains in verify().
        chains = chains[:max_competitors + 1]
        referenced_ids = {c["rule_id"] for c in chains}
        rules = [r for r in rules if r["id"] in referenced_ids]
    aliases, by_key = {}, {}
    for rule in rules:
        text = str(rule["text"]).strip()
        if not text or any(label.casefold() in text.casefold() for label in options):
            raise ValueError("rule contains an action label instead of an interpretation")
        normalized = {k: str(rule.get(k, "")).strip() for k in ("text", "component", "conditions")}
        key = json.dumps(normalized, sort_keys=True).casefold()
        by_key[key] = normalized
        aliases[str(rule["id"])] = key
    sorted_rules = [{"id": "r" + str(i + 1), **by_key[k]} for i, k in enumerate(sorted(by_key))]
    key_ids = {k: r["id"] for k, r in zip(sorted(by_key), sorted_rules)}
    unique = {}
    for chain in chains:
        if chain.get("option_label") not in options:
            raise ValueError("candidate action is not public")
        observations = chain.get("observations", [])
        if not observations or any(o.get("ref") != "chart_1" for o in observations):
            raise ValueError("candidate observations lack chart provenance")
        item = {"observations": observations, "rule_id": key_ids[aliases[chain["rule_id"]]],
                "option_label": chain["option_label"], "claim": str(chain.get("claim", ""))}
        unique[json.dumps(item, sort_keys=True)] = item
    # Verifier never receives generator role/original-chain index, or vote counts.
    ordered = [{"chain_id": "c" + str(i + 1), **unique[k]} for i, k in enumerate(sorted(unique))]
    referenced = {c["rule_id"] for c in ordered}
    return {"rules": [r for r in sorted_rules if r["id"] in referenced], "chains": ordered}


class RuleStore:
    def __init__(self):
        self.records = []
        self.version = 0

    def update(self, candidates, verification, chart="chart_1", metric="task_metric"):
        checks = {c["chain_id"]: c for c in verification["checks"]}
        self.version += 1
        for rule in candidates["rules"]:
            linked = [c for c in candidates["chains"] if c["rule_id"] == rule["id"]]
            linked_checks = [checks[c["chain_id"]] for c in linked]
            statuses = {c["B"] for c in linked_checks}
            status = ("disputed" if len(statuses) > 1 else
                      {"supported": "active", "refuted": "revoked", "undetermined": "pending"}[next(iter(statuses))])
            scope = {"chart": chart, "component": rule["component"], "metric": metric,
                     "conditions": rule["conditions"]}
            previous = next((r for r in self.records if r["B"] == rule["text"] and r["scope"] == scope), None)
            evidence = [e for c in linked_checks for e in c["evidence"]]
            reasons = [c["reason"] for c in linked_checks]
            record = {"id": previous["id"] if previous else "m" + str(len(self.records) + 1),
                      "B": rule["text"], "scope": scope, "status": status, "E": evidence,
                      "version": self.version,
                      "changes": copy.deepcopy(previous["changes"]) if previous else []}
            record["changes"].append({"from_status": previous["status"] if previous else None,
                                       "to_status": status, "reasons": reasons, "version": self.version})
            if previous:
                self.records[self.records.index(previous)] = record
            else:
                self.records.append(record)

    def read(self, chart, metric):
        result = []
        for r in self.records:
            scope = r["scope"]
            match = "undetermined" if not chart or not metric else (
                "applicable" if scope["chart"] == chart and scope["metric"] == metric else "not_applicable")
            result.append({**copy.deepcopy(r), "match": match})
        return result

    def invalid_dependencies(self, proposal):
        return [r for r in self.records if r["id"] in proposal.get("used_rule_ids", [])
                and r["status"] != "active"]


def validate_verification(candidates, verification, options, observed_refs=("chart_1",)):
    checks = verification.get("checks", [])
    wanted = {c["chain_id"] for c in candidates["chains"]}
    if len(checks) != len(wanted) or {c.get("chain_id") for c in checks} != wanted:
        raise ValueError("incomplete/duplicate verifier checks")
    for c in checks:
        if any(c.get(k) not in ("supported", "refuted", "undetermined") for k in ("O", "B", "implication")):
            raise ValueError("invalid evidence status")
        if not isinstance(c.get("reason"), str) or not c.get("evidence"):
            raise ValueError("verification lacks evidence")
        if (any(e.get("ref") not in observed_refs or not e.get("content") or not e.get("location") for e in c["evidence"])
                or not any(e.get("ref") == "chart_1" for e in c["evidence"])):
            raise ValueError("evidence must reference actual chart observation")
    rec = verification.get("recommendation")
    if rec is not None and rec not in options:
        raise ValueError("invalid recommendation")
    if rec is not None:
        by_id = {c["chain_id"]: c for c in checks}
        supported = [c for c in candidates["chains"] if c["option_label"] == rec and
                     all(by_id[c["chain_id"]][k] == "supported" for k in ("O", "B", "implication"))]
        if not supported:
            # Unsupported action never silently executes; retain original verification artifact.
            verification = {**verification, "recommendation": None,
                            "unresolved_reason": "No fully supported chain for recommendation"}
        fully_supported_options = {c["option_label"] for c in candidates["chains"] if
             all(by_id[c["chain_id"]][k] == "supported" for k in ("O", "B", "implication"))}
        supported_rule_ids = {c["rule_id"] for c in supported}
        disputed_rules = {rid for rid in supported_rule_ids if len({by_id[c["chain_id"]]["B"]
            for c in candidates["chains"] if c["rule_id"] == rid}) > 1}
        if len(fully_supported_options) > 1 or disputed_rules:
            verification = {**verification, "recommendation": None,
                            "unresolved_reason": "Conflicting supported conclusions or shared-rule checks"}
    return verification


def verify(api, folder, task, state, history, images, proposal, store, config):
    metric = task["primary_field_label"]
    common = {"task": task, "state": state, "history": history,
              "interpretation_rules": store.read("chart_1", metric)}
    generated = api.call(Path(folder) / "generate", "generate", GENERATOR,
                         {**common, "proposal": proposal}, images)
    cap = config.get("cap_candidates_by_generation_order", False)
    if cap:
        count = len(generated.get("chains", []))
        limit = config["competitors"] + 1
        dump(Path(folder) / "candidate_bound_audit.json", {
            "raw_count": count, "limit": limit,
            "retained_raw_indices": list(range(min(count, limit))),
            "omitted_raw_indices": list(range(limit, count)),
            "rule": "first K+1 before deduplication; no backfill or answer-aware selection"})
    candidates = normalized_candidates(generated, state["options"], config["competitors"], cap_by_order=cap)
    proposed_option = proposal.get("action", {}).get("option", state["current_selection"])
    if proposed_option and not any(c["option_label"] == proposed_option for c in candidates["chains"]):
        raise ValueError("candidate set omitted argument for proposed/current choice")
    dump(Path(folder) / "normalized_candidates.json", candidates)
    # Proposed actor choice/origin role intentionally absent from verifier input.
    verdict = api.call(Path(folder) / "verify", "verify", VERIFIER,
                       {**common, "arguments": candidates}, images)
    verdict = validate_verification(candidates, verdict, state["options"], observed_refs=[ref for ref, _ in images])
    store.update(candidates, verdict, metric=metric)
    dump(Path(folder) / "validated_verification.json", verdict)
    dump(Path(folder) / "rule_state.json", store.records)
    return verdict
