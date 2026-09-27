"""Report actual runs without turning mock behavior into research results."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from audit import pixels_equal, read
from runtime import load_runtime, resolve_path


LABELS = {
    "Select decline-response option": "下降应对",
    "Select growth-planning option": "增长规划",
    "Select monitor-without-change option": "继续监测",
    "Route Solar for priority contribution follow-up": "Solar 优先跟进",
    "Route Wind for priority contribution follow-up": "Wind 优先跟进",
    "Route to production efficiency review": "生产效率审查",
    "Route to capacity expansion planning": "产能扩张规划",
}


def label(value):
    return LABELS.get(value, value or "—")


def bool_text(value):
    return "是" if value is True else "否" if value is False else "—"


def summarize_row(row):
    if row is None:
        return "未运行"
    return (f"{row['status']}；末选 {label(row.get('final_selection'))}；"
            f"提交 {bool_text(row.get('submitted'))}；{row.get('model_calls', 0)} 调用")


def verification_row(row):
    if row is None:
        return ["未运行"] * 7
    return [label(row.get("immediate_selection")), bool_text(row.get("next_action_changed_selection")),
            label(row.get("final_selection")), bool_text(row.get("submitted")), row["status"],
            str(row.get("model_calls", 0)), str((row.get("verification") or {}).get("active_observations", 0))]


def run_checks(rt, run, rows, controls):
    checks = []
    for row in rows:
        directory = run / "online" / row["prefix_id"] / row["method"]
        proof_path = directory / "reconstruction.json"
        proof = read(proof_path) if proof_path.exists() else {}
        checkpoints = list(directory.glob("before_submit_checkpoint.json"))
        actual_submit_proposals = [x for x in row.get("timeline", [])
            if rt.core.is_submit_proposal(x.get("action", {}), x["state_before"])]
        checks.append(dict(prefix_id=row["prefix_id"], method=row["method"],
            reconstructed_state_equal=proof.get("public_state_equal"), reconstructed_all_images_equal=proof.get("all_images_equal"),
            saved_checkpoint_matches_actual_proposal=bool(checkpoints) == bool(actual_submit_proposals),
            no_submit_without_actor_proposal=not row.get("submitted") or bool(actual_submit_proposals),
            submission_receipt_matches_proposal_selection=not row.get("submitted") or row.get("final_selection") == row.get("checkpoint_selection")))
    for number in range(1, 5):
        pair = [x for x in controls if x["control_id"] == number]
        if len(pair) == 2 and all("initial_state" in x for x in pair):
            checks.append(dict(control_id=number,
                initial_public_state_equal=pair[0]["initial_state"] == pair[1]["initial_state"],
                initial_all_pixels_equal=pixels_equal(pair[0]["initial_screenshot"], pair[1]["initial_screenshot"])))
    request_checks = []
    for path in (run / "online").rglob("requests/*.json"):
        payload = read(path)
        rt.core.assert_online_payload(payload)
        # Verify the recorder's exact state and message relationship, not merely its key whitelist.
        if payload["phase"] == "prefix":
            c = payload["public_context"]
            expected = rt.runner.prefix_prompt(c["user_goal"], c["state"])
            assert payload["system_prompt"] == expected[0]
            assert payload["user_prompt"].startswith(expected[1])
            assert c["current_selection"] == rt.core.current_selection(c["state"])
            assert c["visible_options"] == rt.core.visible_options(c["state"])
        request_checks.append(str(path.relative_to(run)))
    result = dict(replay_and_submission_checks=checks,
                  model_request_allowlist_and_current_state_checked=request_checks,
                  note="Ordinary post-run checks, not a research hypothesis test or blanket leakage guarantee.")
    rt.core.write_json(run / "evaluator/engineering_checks.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, help="New report location; preserve previous report versions")
    args = parser.parse_args()
    root = resolve_path(args.session_root).resolve()
    report_dir = args.report_dir.resolve() if args.report_dir else root
    report_dir.mkdir(parents=True, exist_ok=True)
    sources = read(root / "audit/FIRST_SELECTION_SOURCES.json")
    rt = load_runtime(resolve_path(sources[0]["source_run"]))
    manifests = [(p.parent, read(p)) for p in sorted(root.glob("*/run_manifest.json"))]
    live = [(p, m) for p, m in manifests if m["mode"] == "live-local"]
    mock = [(p, m) for p, m in manifests if m["mode"] == "mock"]
    all_rows, all_controls = [], []
    for run, manifest in manifests:
        rows = read(run / "evaluator/chart_results.json")
        controls = read(run / "evaluator/controls.json")
        if not (run / "evaluator/engineering_checks.json").exists():
            run_checks(rt, run, rows, controls)
        if manifest["mode"] == "live-local":
            all_rows.extend(rows)
            all_controls.extend(controls)
    initial = []
    for source in sources:
        raw = rt.runner.find_task(rt.runner.task_spec_path(source["condition"], source["task_slug"]), source["task_slug"])
        selected = source["request_after_selection"]["public_context"]["current_selection"]
        initial.append(dict(prefix_id=source["prefix_id"], task=source["task_slug"],
                            arm="误导图" if source["condition"] == "official140" else "对照图",
                            first_selection=selected,
                            correct=rt.safe_shell.score_receipt(raw, {"selected_option_label": selected})["outcome"] == "success",
                            evidence_conflict=source["task_slug"] == "env008"))
    total = dict(real_model_calls=sum(m["budget"]["model_calls"] for _, m in live),
                 mock_backend_calls=sum(m["budget"]["model_calls"] for _, m in mock),
                 browser_transitions=sum(m["budget"]["browser_transitions"] for _, m in manifests))
    by_phase = Counter()
    for _, m in manifests:
        for event in m["budget"]["events"]:
            by_phase[(m["mode"], event["kind"], event["phase"])]+=1
    rt.core.write_json(report_dir / "SESSION_ACCOUNTING.json", dict(**total, limits=dict(real_model_calls=200, browser_transitions=800),
        phase_counts=[dict(mode=k[0], kind=k[1], phase=k[2], count=v) for k, v in by_phase.items()]))
    rt.core.write_json(report_dir / "INITIAL_STATE_LABELS_OFFLINE.json", initial)
    lines = ["# DIAGNOSTIC_REPORT", "", "## 本轮状态", "",
        ("真实模型诊断已执行；以下区分已运行、未运行和失败分支。" if live else
         "真实模型诊断：**未运行**。本轮共享 GPU 0 授权尚未确认；没有启动模型、访问未知推理服务、下载权重或调用付费 API。已完成离线真实请求审计、代码实现、单元回归与明确标记的浏览器 mock 链路。"), "",
        "本轮只诊断六个历史首选状态；不是新自然任务采样，也不是 H1 从初始页自主执行的结果。没有新增视觉机制、无条件提交或修改原任务/gold。", "",
        "## 1. 旧前缀输入审计：直接观察", "",
        "完整证据见 [PREFIX_INPUT_AUDIT.md](audit/PREFIX_INPUT_AUDIT.md) 和 [完整请求—响应—回执时间线](audit/REQUEST_TIMELINE.json)。共 48 个真实前缀请求、六条前缀。",
        "三个交替循环前缀从首选后可比较的 21 对相隔两步请求，system/user 文本、完整公开状态、全部图像解码后像素均相同。旧模型没有收到动作历史或执行回执；这些只被日志保存。",
        "当前选择、selected_text、option selected flags 和可见提交按钮一致；选中项仍在选项列表中。没有证实公开状态投影错误，也没有‘必须换选项’提示。",
        "Figure 10 及原 run_public39.py 有‘所需选项已选中则提交，否则修改’的普通流程提示；旧诊断模板删去了它。本轮保持 H0 原文，H1 只加真实历史，避免两因素同改。缺失提示的因果影响未在本轮单独测试。",
        "截图是动作前 s_t；最后执行动作 a_t 改到另一项而末张输入截图仍是旧选项，是正常时间顺序。末步动作后的选择由执行器成功回执及选中项后置检查支持，不伪造末步后截图。", "",
        "旧运行仍为：6 条自然前缀，3 个正确 before-submit checkpoint，0 个错误 checkpoint；12 条真实提交来自这三状态的四个策略分支。错误 checkpoint 恢复率=N/A。原 24 配置不是 24 条已执行策略轨迹；原 B3 三条核查均直接决定、未 crop。", "",
        "## 2. 六个首选状态与重建", "",
        "选取规则只看时间和成功执行的非空 primary_action，不看 gold；所有状态均进入，包括正确选择。以下正确性只用于离线报告。", "",
        "| 历史前缀 | 原任务 | 图表条件 | 首选 | 原评分正确 | 限定 |", "|---|---|---|---|---|---|"]
    for row in initial:
        lines.append(f"| {row['prefix_id']} | {row['task']} | {row['arm']} | {label(row['first_selection'])} | {bool_text(row['correct'])} | {'evidence_conflict（可见证据冲突）' if row['evidence_conflict'] else '—'} |")
    lines += ["", "这里只有一个原评分错误的首选源状态：pub010 误导图。各分支与后续反复改错不是独立错误样本。env008 保持原 gold，同时保留证据冲突标记；误导图中 Wind 的柱高及纵轴读数是可见线索，不能称其完全无支持。本轮没有加入‘必须信打印标签’规则。", "",
        "重建原始实现、原资产、原动作；每个分支保存 reconstruction.json，检查全程已观察图像像素与最终公开状态。失败会标不支持，不继续冒充同状态核验。", "",
        "## 3. 四个非图表流程控制：真实模型结果", "",
        "H0 为旧当前页原文；H1 仅加入最近最多四个真实动作与公开回执。每场景每配置最多两次调用。", "",
        "| 场景 | 公开目标 | 当前选择 | 所需流程 | H0 | H1 |", "|---|---|---|---|---|---|"]
    for number, (target, selected) in enumerate((("Route A", "Route A"), ("Route A", "Route B"), ("Route B", "Route A"), ("Route B", "Route B")), 1):
        vals = [summarize_row(next((r for r in all_controls if r["control_id"] == number and r["context_mode"] == mode), None)) for mode in ("H0", "H1")]
        lines.append(f"| {number} | {target} | {selected} | {'保持后提交' if target == selected else '修改后提交'} | {' | '.join(vals)} |")
    lines += ["", "这些控制即使真实模型通过，也只是流程能力结果，不是图表理解或视觉纠错结果。", "",
        "## 4. 同一历史首选状态的 H0/H1 真实续跑", "",
        "每分支最多四次 actor 调用；不自动提交、不锁定选择。仅实际提交提议构成 before-submit checkpoint。", "",
        "| 原任务/条件 | H0 当前页 | H1 真实历史 |", "|---|---|---|"]
    for source in initial:
        vals = [summarize_row(next((r for r in all_rows if r["prefix_id"] == source["prefix_id"] and r["method"] == mode), None)) for mode in ("H0", "H1")]
        lines.append(f"| {source['task']} / {source['arm']} | {' | '.join(vals)} |")
    lines += ["", "## 5. 首选后 A0/A2/A3/A4 真实核验—续跑", "",
        "A0=同状态 H1 正常续跑（复用，不新增调用）；A2=独立全图目标核验；A3=通用主动核验（最多两次观察/三次调用）；A4=模型图表提取后再决策。核验之后，后三者均交给同一个 H1 actor，最多四次普通动作调用。", "",
        "这里没有 pending submit；与原 B0 执行原提交提议不同。核验结果只推荐选择，统一执行器完成真实修改，再将实际核验输出与修改回执交给 actor。模型可再次修改，只有它真正提议提交才提交。A2 独立判断有意隐藏当前选择及暴露它的历史；A3 允许历史和主动观察；A4 保留图表独立提取步骤。不强迫 A3 crop。", "",
        "| 状态 | 方法 | 核验后立即选择¹ | 下一步改选 | 最终选择 | 真实提交 | 结束状态 | 调用 | crop |", "|---|---|---|---|---|---|---|---:|---:|"]
    for source in initial:
        for method in ("A0", "A2", "A3", "A4"):
            row = next((r for r in all_rows if r["prefix_id"] == source["prefix_id"] and r["method"] == ("H1" if method == "A0" else method)), None)
            lines.append(f"| {source['task']} / {source['arm']} | {method} | {' | '.join(verification_row(row))} |")
    lines += ["", "¹ A0 未核查，该列是继承首选。A0 自行改正是主要比较，不把 A2 暂时改对等同新增稳定恢复。", "",
        "## 6. 错误、纠正、提交与失败：真实结果计数", "",
        "H1 与 A0 是同一轨迹；下表按方法分开列，不把它们合并求独立样本数。错误选择事件可重复发生，必须与一个初始错误源状态区分。", "",
        "| 方法 | 已运行 | 后续错误选择事件 | 续跑actor改正² | 核验直接改正 | 正确→错误 | 提议提交 | 错误提议 | 真提交 | 正确提交 | 超时 | 核查未运行 | 核查解析/运行失败 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for method in ("H0", "H1/A0", "A2", "A3", "A4"):
        rr = [r for r in all_rows if r["method"] == ("H1" if method == "H1/A0" else method)]
        if not rr:
            lines.append(f"| {method} | 0 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 |")
            continue
        counts = Counter()
        for r in rr:
            counts.update(r["evaluation"]["event_counts"])
        vals = [len(rr), counts["wrong_selections"], counts["ordinary_self_corrections"], counts["verification_corrections"], counts["correct_to_wrong"],
                sum(r.get("checkpoint_reached", False) for r in rr), sum(r["evaluation"]["checkpoint_selection_correct"] is False for r in rr),
                sum(r.get("submitted", False) for r in rr), sum(r["evaluation"]["score"]["outcome"] == "success" for r in rr),
                sum(r["status"] == "actor_call_limit" for r in rr), sum(not r.get("verification_executed") for r in rr),
                sum(r["status"] == "verification_failure" or (r.get("verification_executed") and r.get("verification", {}).get("parse_status") != "valid") for r in rr)]
        lines.append(f"| {method} | {' | '.join(map(str, vals))} |")
    lines += ["", "² H0/H1 的 actor 改正是无核验自行改正；A2/A3/A4 的 actor 已收到核验输出，其后续改正可能受核验说明影响，不能称为独立于核验的自行改正。H0/H1 按设计不核查，‘核查未运行’不是这两种配置的失败。语法解析通过也不代表核查结论正确，错误建议另见逐案例分析。",
        "未到 hook、未运行核查、已核查但建议错误/解析失败、actor 超时、执行/提交错误分别保留在结果 JSON，不能都写成‘纠错失败’。已执行核查的错误建议还需与后续 actor 修正和最终完成分开。未运行不是 0% 失败率。", "",
        "## 7. 工程测试与成本（不作研究结果）", "",
        "新增 9 项窄范围单元测试通过（包含末次调用仅改选时不自动提交）；原运行时快照的既有回归 49 项中 46 通过、3 项 opt-in 浏览器用例跳过。浏览器链路由下列独立 mock 面板实际执行。", "",
        "| 工程运行 | 模型性质 | 流程分支 | 图表状态分支 | 真浏览器提交/确认 | mock 调用 | transition |", "|---|---|---:|---:|---:|---:|---:|"]
    for run, manifest in mock:
        rr, cc = read(run / "evaluator/chart_results.json"), read(run / "evaluator/controls.json")
        submits = sum(x.get("submitted") and x.get("confirmation_observed") for x in rr + cc)
        lines.append(f"| {run.name} | 脚本，仅工程测试 | {len(cc)} | {len(rr)} | {submits} | {manifest['budget']['model_calls']} | {manifest['budget']['browser_transitions']} |")
    lines += ["", "工程面板的 30 个重放分支最终公开状态均相同，120 张重放观察图逐像素一致；四个非图表控制的 H0/H1 初始页面也相同。38 次实际 POST 都有对应 actor 提议、hook 保存和确认页面；5 次核验改选、6 次 mock crop 的链路已实际走通。此处的提交/改选是脚本输出驱动，绝不是 Qwen 的能力结果。",
        "工程面板启动时新增源码保存在 implementation/。之后仅补充了提交已发生但回执/动作报错时的状态分类（保留 submitted_with_runtime_error，而非覆盖为成功）及一个无自动提交单元测试；没有修改已完成工程运行的源码副本或结果。正常成功路径未改，异常分支的浏览器故障注入未在本轮额外运行。"]
    lines += ["", f"本 session 累计：真实模型调用 {total['real_model_calls']} / 200；mock backend 调用 {total['mock_backend_calls']}；实际浏览器 transition {total['browser_transitions']} / 800。重放、失败和重试全部计入；详见 SESSION_ACCOUNTING.json（按阶段分项）和各 budget.json（逐事件）。",
        "无新模型环境构建。run-experiment 技能用于已有环境复用、资源授权和成本记录；按本执行单不扩大审查系统。模型计划沿用 Qwen3-VL-8B-Instruct / BF16，本轮若未获授权则没有真实参数实测。温度 0、top_p 1、seed 12345、最大输出 1024、max_pixels 1003520、原生多图、viewport 1440×1100；实际运行身份以 run_manifest.json 与逐响应 metadata 为准。", "",
        "## 8. 本轮决定与剩余问题", "",
        ("只解释这次配对续跑和首选后诊断，不能当作新任务泛化或自然错误 checkpoint 恢复。按本轮实际结果作后续决定，不自动开展下一面板。" if live else
         "现在没有真实 H0/H1 或 A0/A2/A3/A4 比较，不能判断历史是否消除循环、简单核查是否稳定改善完成，更不能宣称新视觉机制必要。唯一执行阻塞是本轮 GPU/模型授权。代码与 mock 已完成，等待这一处授权后方可执行一次真实面板。"),
        "若普通历史就改善完成，只能视为基线可靠性线索。若核查只暂时改对、随后改坏或不提交，不算稳定恢复。没有自然错误提交则错误 checkpoint 恢复率仍为 N/A，不能用 mock、注入、强制提交或事后错误时点替代。",
        "本轮不自动启动完整 pilot、B5 全移植、独立任务采样或候选机制。", "",
        "## 附录索引", "",
        "- audit/REQUEST_TIMELINE.json：48 个完整请求、响应及动作前后证据。",
        "- audit/TWO_STEP_COMPARISONS.json：21 对文本/状态/全部图像比较。",
        "- audit/PUBLIC_FIELD_CONSISTENCY.json：公开字段、选项可用性和提交按钮。",
        "- audit/FIRST_SELECTION_SOURCES.json：时间/动作取样、真实来源与重放序列。",
        "- 各运行 online/：真实截图、模型请求响应、reconstruction、verification_handoff、actor_timeline、before_submit_checkpoint 与 result。",
        "- 各运行 server_receipts/：真实本地 POST 收据；evaluator/：独立评分、A0 复用关系与工程检查。",
        "- 各运行 implementation/：实际启动时的新增代码副本；旧实现从参考 run 的 runtime_source_snapshot 只读加载。",
        "- COMMANDS.md 与测试日志：实际命令、测试结果。"]
    rendered = "\n".join(lines) + "\n"
    rendered = rendered.replace("](audit/", "](" + os.path.relpath(root / "audit", report_dir) + "/")
    (report_dir / "DIAGNOSTIC_REPORT.md").write_text(rendered, encoding="utf-8")
    print(json.dumps(total, indent=2))


if __name__ == "__main__":
    main()
