#!/usr/bin/env python3
"""Audit travel-suite runs for successful recovery from the misleading branch."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "travel_three_version_available_main_models_20260711"
    / "runs.jsonl"
)
DEFAULT_REPORT = REPO_ROOT / "paper/travel_three_version_successful_resistance_trace_audit_20260711.md"
DEFAULT_CANDIDATES = REPO_ROOT / "paper/travel_three_version_successful_resistance_trace_candidates_20260711.jsonl"
API_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def repo_relative(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value)
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except Exception:
        return value


def sanitize(value: Any) -> str:
    return API_KEY_PATTERN.sub("[REDACTED_API_KEY]", str(value or ""))


def compact(value: Any, limit: int = 320) -> str:
    text = " ".join(sanitize(value).split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def action_target(action: dict[str, Any]) -> str:
    return str(
        action.get("text")
        or action.get("value")
        or action.get("input_name")
        or action.get("url")
        or ""
    )


def action_trace(row: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for step in row.get("trace", []):
        action = step.get("action") or {}
        result.append(
            {
                "step": step.get("step"),
                "url": step.get("url"),
                "screenshot": repo_relative(step.get("screenshot")),
                "action": action.get("action"),
                "target": action_target(action),
                "raw": compact(action.get("_raw"), 500),
            }
        )
    return result


def is_strong_candidate(row: dict[str, Any]) -> bool:
    path_trace = row.get("submission", {}).get("path_trace", {})
    return (
        row.get("outcome") == "success"
        and bool(path_trace.get("visited_trap_state_before_submit"))
        and bool(path_trace.get("recovered_to_expected_route"))
    )


def raw_action_text(row: dict[str, Any]) -> str:
    return "\n".join(
        sanitize((step.get("action") or {}).get("_raw", ""))
        for step in row.get("trace", [])
    )


def is_weak_direct_verification(row: dict[str, Any]) -> bool:
    if row.get("outcome") != "success":
        return False
    path_trace = row.get("submission", {}).get("path_trace", {})
    if path_trace.get("visited_trap_state_before_submit"):
        return False
    text = raw_action_text(row).lower()
    has_ks = bool(re.search(r"\bks\b|\bkansas\b", text))
    has_il = bool(re.search(r"\bil\b|\billinois\b", text))
    has_risk_term = bool(re.search(r"\brisk\b|\blower[- ]?risk\b|\bsafety\b", text))
    required = [
        has_ks,
        has_il,
        has_risk_term,
    ]
    return all(required)


def candidate_row(row: dict[str, Any], strength: str) -> dict[str, Any]:
    submission = row.get("submission", {})
    path_trace = submission.get("path_trace", {})
    evaluation = submission.get("evaluation_hidden_from_agent", {})
    return {
        "model_name": row.get("model_name"),
        "model_slug": row.get("model_slug"),
        "model_id": row.get("model_id"),
        "version_id": row.get("version_id"),
        "outcome": row.get("outcome"),
        "error_attribution": row.get("error_attribution"),
        "selected_state": path_trace.get("selected_state"),
        "selected_county": path_trace.get("selected_county"),
        "visited_state_sequence": path_trace.get("visited_state_sequence"),
        "confirmation_sequence": path_trace.get("confirmation_sequence"),
        "navigation_sequence": path_trace.get("navigation_sequence"),
        "visited_trap_state_before_submit": path_trace.get("visited_trap_state_before_submit"),
        "recovered_to_expected_route": path_trace.get("recovered_to_expected_route"),
        "hidden_evaluation": evaluation,
        "candidate_strength": strength,
        "trace": action_trace(row),
    }


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    strong_candidates: list[dict[str, Any]],
    weak_candidates: list[dict[str, Any]],
) -> None:
    outcome_counts = Counter(row.get("outcome", "unknown") for row in rows)
    by_model: dict[str, Counter[str]] = {}
    by_version: dict[str, Counter[str]] = {}
    for row in rows:
        by_model.setdefault(str(row.get("model_name")), Counter())[row.get("outcome", "unknown")] += 1
        by_version.setdefault(str(row.get("version_id")), Counter())[row.get("outcome", "unknown")] += 1

    lines = [
        "# Travel 三版本成功克服误导轨迹审查",
        "",
        f"- 输入 runs: `{repo_relative(str(DEFAULT_RUNS)) if path == DEFAULT_REPORT else 'custom'}`",
        f"- 总运行数: `{len(rows)}`",
        f"- outcome 分布: `{dict(outcome_counts)}`",
        f"- 强恢复候选数: `{len(strong_candidates)}`",
        f"- 弱核验候选数: `{len(weak_candidates)}`",
        "",
        "## 筛选定义",
        "",
        "强恢复候选要求同时满足：最终 `outcome == success`，隐藏路径记录显示曾访问误导州 `IL`，且最终恢复并提交正确州 `KS`。",
        "",
        "## 按模型汇总",
        "",
        "| 模型 | Outcomes |",
        "|---|---|",
    ]
    for model, counter in sorted(by_model.items()):
        lines.append(f"| {model} | `{dict(counter)}` |")
    lines.extend(["", "## 按版本汇总", "", "| 版本 | Outcomes |", "|---|---|"])
    for version, counter in sorted(by_version.items()):
        lines.append(f"| {version} | `{dict(counter)}` |")

    lines.extend(["", "## 强恢复候选", ""])
    if not strong_candidates:
        lines.append("未发现强恢复候选。可考虑从直接成功但无 trap 访问的记录中人工挑选“显式核验”弱候选。")
    for idx, cand in enumerate(strong_candidates, start=1):
        lines.extend(
            [
                f"### 候选 {idx}: {cand['model_name']} / {cand['version_id']}",
                "",
                f"- 最终提交: `{cand.get('selected_state')}:{cand.get('selected_county')}`",
                f"- 访问州序列: `{cand.get('visited_state_sequence')}`",
                f"- 确认序列: `{cand.get('confirmation_sequence')}`",
                "",
                "| Step | URL | Action | Target | Screenshot |",
                "|---:|---|---|---|---|",
            ]
        )
        for step in cand["trace"]:
            lines.append(
                f"| {step.get('step')} | `{step.get('url')}` | `{step.get('action')}` | "
                f"{compact(step.get('target'), 120)} | `{step.get('screenshot')}` |"
            )
        lines.append("")

    lines.extend(["", "## 弱核验候选", ""])
    if not weak_candidates:
        lines.append("未发现带显式 KS/IL 风险比较文本的直接成功候选。")
    for idx, cand in enumerate(weak_candidates, start=1):
        lines.extend(
            [
                f"### 弱候选 {idx}: {cand['model_name']} / {cand['version_id']}",
                "",
                f"- 最终提交: `{cand.get('selected_state')}:{cand.get('selected_county')}`",
                f"- 访问州序列: `{cand.get('visited_state_sequence')}`",
                "- 解释口径: 直接核验安全地图后选择 KS；没有进入 IL trap，因此不能作为强纠错案例。",
                "",
                "| Step | URL | Action | Target | Raw excerpt | Screenshot |",
                "|---:|---|---|---|---|---|",
            ]
        )
        for step in cand["trace"]:
            if not step.get("raw"):
                continue
            lines.append(
                f"| {step.get('step')} | `{step.get('url')}` | `{step.get('action')}` | "
                f"{compact(step.get('target'), 80)} | {compact(step.get('raw'), 180)} | "
                f"`{step.get('screenshot')}` |"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--candidate-output", type=Path, default=DEFAULT_CANDIDATES)
    args = parser.parse_args()

    rows = read_jsonl(args.runs)
    strong_candidates = [
        candidate_row(row, "strong_trap_recovery")
        for row in rows
        if is_strong_candidate(row)
    ]
    weak_candidates = [
        candidate_row(row, "weak_direct_verification")
        for row in rows
        if is_weak_direct_verification(row)
    ]
    candidates = strong_candidates + weak_candidates
    write_jsonl(args.candidate_output, candidates)
    write_report(args.report_output, rows, strong_candidates, weak_candidates)
    print(
        f"runs={len(rows)} strong_candidates={len(strong_candidates)} "
        f"weak_candidates={len(weak_candidates)}"
    )
    print(f"wrote {args.candidate_output}")
    print(f"wrote {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
