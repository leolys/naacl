"""Offline-only, self-contained case viewer; never called by the online agent."""

from __future__ import annotations

import argparse
import base64
import html
import json
from collections import Counter
from pathlib import Path

from .core import write_json
from .runner import find_task, read_jsonl, task_spec_path
from .safe_shell import score_receipt
from .validate_run import missing_executable_sources


STRATEGY_NAMES = {
    "B0": "原样继续（B0）",
    "B2": "重看完整图表＋目标语义核查（B2）",
    "B3": "通用主动视觉核验（B3）",
    "B4": "模型自行提取后再决策（B4）",
}
CONDITION_NAMES = {"official140": "原误导图表", "clean140": "清洁图表"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def transition_class(initial: str, terminal: str, *, submitted: bool) -> str:
    if not submitted:
        return "未完成真实提交"
    if initial == "success":
        return "原本正确并保持" if terminal == "success" else "原本正确却改错"
    return "原本错误后提交正确" if terminal == "success" else "原本错误且未纠正"


def displayed_class(initial: str, terminal: str, *, submitted: bool, real: bool) -> str:
    if not real:
        return "脚本工程提交已完成（不评价纠错）" if submitted else "脚本工程提交未完成（不评价纠错）"
    return transition_class(initial, terminal, submitted=submitted)


def pretty(value) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2))


def embed_image(run_root: Path, artifact: str, caption: str) -> str:
    path = (run_root / artifact).resolve()
    if not path.is_relative_to(run_root.resolve()) or not path.is_file():
        return f"<p>截图未生成：{html.escape(artifact)}</p>"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f'<figure><img loading="lazy" src="data:image/png;base64,{encoded}" '
        f'alt="{html.escape(caption, quote=True)}"><figcaption>{html.escape(caption)}</figcaption></figure>'
    )


def make_report(run_root: Path, output_root: Path) -> dict:
    manifest = load(run_root / "run_manifest.json")
    mappings = read_jsonl(run_root / "evaluator" / "unit_map.jsonl")
    prefixes = read_jsonl(run_root / "evaluator" / "prefixes.jsonl")
    scores = {r["unit_id"]: r for r in read_jsonl(run_root / "evaluator" / "scores.jsonl")}
    real = manifest.get("model_mode") == "live-local"
    validation = load(run_root / "evaluator" / "validation.json")
    source_coverage = not missing_executable_sources((manifest.get("code_fingerprint") or {}).get("files") or [])
    qualified = (
        real and validation.get("valid") is True and source_coverage
        and manifest.get("runtime_source_unchanged") is True and not manifest.get("run_errors")
        and (manifest.get("preflight_multi_image_witness") or {}).get("status") == "passed"
    )
    mode_label = "真实本地模型尝试：有效性须另看工程与来源审查" if real else "脚本 mock：不是自然错误，不是模型效果"
    body = [f"<h1>明确规则任务：逐条轨迹</h1><p class='notice'>{mode_label}</p>"]
    body.append(f"<p>验证器通过：{validation.get('valid', '未验证')}；可执行代码来源完整：{source_coverage}；可汇总真实自然轨迹：{qualified}。</p>")
    body.append(
        "<p>每种图表只生成一次前缀，在首次提出提交、尚未执行时暂停。四种策略从相同暂停状态开始。"
        "这里的正确性来自离线数据集评分；理由是否被可见证据支持须逐条核查，不能由选项正确自动推断。"
        "本报告及其中答案从未提供给在线模型。安全 shell 的真实本地提交不等于原始网站全部业务完成。</p>"
    )
    body.append(f"<details><summary>实际运行与模型设置</summary><pre>{pretty(manifest)}</pre></details>")
    cases = []
    transitions = Counter()
    engineering_submissions = Counter()
    for prefix in prefixes:
        prefix_id = prefix["prefix_id"]
        slug, condition = prefix["task_slug"], prefix["condition"]
        raw = find_task(task_spec_path(condition, slug), slug)
        checkpoint = load(run_root / "online" / "prefixes" / prefix_id / "checkpoint.json")
        initial_label = checkpoint.get("current_selection", "")
        initial = score_receipt(raw, {"selected_option_label": initial_label})["outcome"] if checkpoint else "no_checkpoint"
        expected = next((a["label"] for a in raw["action_space"] if a["action_id"] == raw["expected_action_id"]), "")
        case = {
            "task_slug": slug, "condition": condition, "prefix_id": prefix_id,
            "checkpoint_reached": bool(checkpoint), "initial_selection": initial_label,
            "initial_outcome": initial, "expected_label_offline_only": expected,
            "model_mode": manifest.get("model_mode"), "units": [],
        }
        body.append(f"<section><h2>{slug} · {CONDITION_NAMES[condition]}</h2>")
        body.append(f"<p><b>完整公开任务：</b>{html.escape(raw.get('workflow_instruction', ''))}</p>")
        body.append(f"<p><b>离线正确动作：</b>{html.escape(expected)}</p>")
        body.append(f"<p><b>暂停时已选：</b>{html.escape(initial_label or '没有 checkpoint')}；离线类别：{html.escape(initial)}</p>")
        for shot in checkpoint.get("observed_screenshots", []):
            if shot.get("kind") == "dashboard":
                body.append(embed_image(run_root, shot["path"], "自然前缀实际看到的仪表盘"))
                break
        if checkpoint:
            body.append(f"<details><summary>前缀动作与模型原始输出（含待提交动作）</summary><pre>{pretty(checkpoint.get('model_context'))}</pre></details>")
            body.append(embed_image(run_root, checkpoint["current_screenshot"], "首次提出提交前的实际状态"))
        else:
            request_dir = run_root / "online" / "prefixes" / prefix_id / "requests"
            requests = [load(path) for path in sorted(request_dir.glob("*.json"))]
            dashboard_request = next((r for r in requests if str((r.get("public_context") or {}).get("state", {}).get("url_path", "")).endswith("/dashboard")), None)
            if dashboard_request and dashboard_request.get("image_artifacts"):
                body.append(embed_image(run_root, dashboard_request["image_artifacts"][0], "未形成 checkpoint 的前缀实际看到的仪表盘"))
            if requests and requests[-1].get("image_artifacts"):
                body.append(embed_image(run_root, requests[-1]["image_artifacts"][0], "该前缀最后一次模型调用看到的状态"))
            responses = [load(path) for path in sorted((request_dir.parent / "responses").glob("*.json"))]
            body.append(f"<details><summary>未到达提交前暂停点：模型逐步原始输出</summary><pre>{pretty(responses)}</pre></details>")
            body.append(f"<pre>{pretty(prefix)}</pre>")
        for mapping in [m for m in mappings if m["prefix_id"] == prefix_id]:
            unit_id = mapping["unit_id"]
            unit_dir = run_root / "online" / "units" / unit_id
            result = load(unit_dir / "result.json")
            replay = load(unit_dir / "replay.json")
            score = scores.get(unit_id, {})
            terminal = (score.get("terminal_score") or {}).get("outcome", "unscored")
            submitted = (
                result.get("status") == "submitted"
                and result.get("submission_receipt_count") == 1
                and result.get("confirmation_observed") is True
            )
            classification = displayed_class(initial, terminal, submitted=submitted, real=real)
            if qualified:
                transitions[classification] += 1
            engineering_submissions["clean_submission" if submitted else "incomplete_submission"] += 1
            policy = result.get("policy") or {}
            row = {
                "unit_id": unit_id, "strategy": mapping["strategy"],
                "strategy_name": STRATEGY_NAMES[mapping["strategy"]],
                "final_selection": result.get("selected_before_submit", ""),
                "terminal_outcome": terminal, "trajectory_class": classification,
                "clean_submission_chain": submitted,
                "policy_changed": policy.get("changed"),
                "revision_action": result.get("revision_action"),
                "replay_state_equal": replay.get("state_equal"),
                "replay_screenshot_equal": replay.get("screenshot_equal"),
                "model_calls": policy.get("model_calls", 0),
                "active_observations": policy.get("active_observations", 0),
                "parse_status": policy.get("parse_status"),
                "evidence_support": "not_automatically_judged_requires_visible_evidence_review",
            }
            case["units"].append(row)
            body.append(f"<h3>{row['strategy_name']} · {classification}</h3>")
            body.append(f"<p>提交选择：{html.escape(row['final_selection'])}；核查调用 {row['model_calls']} 次；主动观察 {row['active_observations']} 次。</p>")
            body.append(f"<details><summary>核查原文、修改动作、POST 回执、确认结果</summary><pre>{pretty(result)}</pre></details>")
            for crop in sorted((unit_dir / "observations").glob("active_crop_*.png")):
                body.append(embed_image(run_root, str(crop.relative_to(run_root)), "模型实际选取的重观察区域"))
        body.append("</section>")
        cases.append(case)
    summary = {
        "run_id": run_root.name, "model_mode": manifest.get("model_mode"),
        "run_path": str(run_root.resolve()), "mode_label": mode_label,
        "offline_reporter_path": str(Path(__file__).resolve()),
        "case_count": len(cases), "configured_units": len(mappings),
        "observed_checkpoint_artifacts": sum(c["checkpoint_reached"] for c in cases),
        "natural_checkpoints": sum(c["checkpoint_reached"] for c in cases) if qualified else None,
        "natural_wrong_checkpoints": sum(c["checkpoint_reached"] and bool(c["initial_selection"]) and c["initial_outcome"] != "success" for c in cases) if qualified else None,
        "trajectory_counts": dict(transitions),
        "trajectory_counts_are_real_model_results": qualified,
        "engineering_submission_counts": dict(engineering_submissions),
        "source_coverage_complete": source_coverage,
        "validation_passed": validation.get("valid"),
        "budget": manifest.get("budget"), "cases": cases,
    }
    document = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>明确规则任务轨迹</title>
<style>body{font:17px/1.7 system-ui,sans-serif;max-width:1200px;margin:auto;padding:28px;background:#f6f8fa;color:#17212c}section{background:white;padding:24px;margin:28px 0;border:1px solid #ccd4dd;border-radius:8px}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 monospace;padding:14px;background:#eef2f6}.notice{background:#ffe6b4;padding:16px}summary{cursor:pointer;color:#145b8f}figure{margin:18px 0}figcaption{color:#586675}</style><body>""" + "\n".join(body) + "</body></html>"
    output_root.mkdir(parents=True, exist_ok=True)
    for name in ("CASE_SUMMARY.json", "CASE_VIEWER.html"):
        if (output_root / name).exists():
            raise FileExistsError(output_root / name)
    write_json(output_root / "CASE_SUMMARY.json", summary)
    (output_root / "CASE_VIEWER.html").write_text(document, encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = make_report(args.run_dir.resolve(), args.output_dir.resolve())
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
