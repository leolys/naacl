"""Render completed, actually recorded demo runs; never call a model or browser.

All correctness labels come from the runner's *offline* evaluation, after actors
have stopped. Missing files/failed trajectories remain explicitly missing.
No hypothetical numerical chart readings or successful trajectories are added.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path


SYSTEMS = {"ordinary": "普通 Agent", "competing_persistent": "竞争解释＋持续规则状态"}
CONDITIONS = {"official140": "原误导条件", "clean140": "对应清洁条件"}
STATUSES = {
    "submitted": "已真实提交", "actor_call_limit": "达到动作调用上限，未提交",
    "unresolved_visual_evidence": "证据仍不足，未提交",
    "unresolved_reverification_budget": "再次核验预算已用完，未提交",
    "error": "运行错误", "not_started": "未启动",
}


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def read_jsonl(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def cell(value):
    if value is None:
        return "未记录"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value).replace("|", "\\|").replace("\n", " ")


def json_block(value):
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n"


def rel_link(label, path, base):
    relative = os.path.relpath(Path(path).resolve(), Path(base).resolve()).replace("\\", "/")
    return "[%s](<%s>)" % (label, relative)


def image_link(label, path, base):
    return "!" + rel_link(label, path, base)


def action_text(action):
    action = action or {}
    if isinstance(action, str):
        return "模型原始扁平动作名：" + action + "（是否执行见实际回执）"
    kind = action.get("kind", "未记录")
    if kind == "select":
        return "选择：" + str(action.get("option", "未记录"))
    if kind == "fill":
        return "填写 %s：%s" % (action.get("field", ""), action.get("value", ""))
    if kind == "check":
        return "勾选 %s = %s" % (action.get("field", ""), action.get("value", ""))
    return {"submit": "点击提交", "observe": "观察当前页面", "setup_open_task": "准备：打开任务页",
            "setup_open_dashboard": "准备：打开图表页", "setup_open_form": "准备：打开表单页"}.get(kind, str(kind))


def result_text(execution):
    if not execution:
        return "没有执行记录"
    if execution.get("submitted"):
        return "服务器接收并观察到确认页"
    if not execution.get("ok"):
        return "未成功：" + str(execution.get("error", "未知"))
    selection = execution.get("current_selection")
    return "执行成功；当前选择=" + str(selection) if selection else "执行成功"


def route_statistics(run_dir):
    routes = Counter()
    requested = Counter()
    usage_models = Counter()
    attempts = []
    known = Counter()
    missing_token_fields = Counter()
    unknown_usage = failed = 0
    for path in sorted(Path(run_dir).glob("case*/step_*/**/attempt_*.json")):
        item = read_json(path, {})
        requested[str(item.get("requested_model") or "未报告")] += 1
        routes[str(item.get("response_model") or "未报告")] += 1
        usage = item.get("usage")
        if isinstance(usage, dict):
            usage_models[str(usage.get("model_name") or "未报告")] += 1
        else:
            unknown_usage += 1
            usage_models["未报告"] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key) if isinstance(usage, dict) else None
            if isinstance(value, (int, float)):
                known[key] += value
            else:
                missing_token_fields[key] += 1
        is_failed = bool(item.get("error")) or item.get("http_status") != 200
        failed += is_failed
        attempts.append({"file": str(path.relative_to(run_dir)).replace("\\", "/"),
                         "phase": item.get("phase"), "http_status": item.get("http_status"),
                         "requested_model": item.get("requested_model"), "response_model": item.get("response_model"),
                         "usage_model_name": usage.get("model_name") if isinstance(usage, dict) else None,
                         "failed": is_failed, "elapsed_seconds": item.get("elapsed_seconds"), "usage": usage})
    return {"attempts_with_metadata": len(attempts), "failed_attempts": failed,
            "attempts_without_usage": unknown_usage, "requested_models": dict(requested),
            "response_models": dict(routes), "usage_model_names": dict(usage_models),
            "known_token_totals": dict(known), "attempts_missing_each_token_field": dict(missing_token_fields),
            "attempt_records": attempts}


def trajectory_path(run_dir, row):
    return Path(run_dir) / (row["case_alias"] + "_" + row["system"])


def summary_counts(rows):
    systems = {}
    for system in SYSTEMS:
        group = [row for row in rows if row["system"] == system]
        systems[system] = {
            "trajectories": len(group),
            "first_wrong_proposals": sum(row.get("first_correct") is False for row in group),
            "real_submissions": sum(bool(row.get("final_score", {}).get("real_submission")) for row in group),
            "primary_success_with_real_submission": sum(row.get("final_score", {}).get("primary_outcome") == "success" and bool(row.get("final_score", {}).get("real_submission")) for row in group),
            "wrong_first_to_primary_success": sum(row.get("first_correct") is False and row.get("final_score", {}).get("primary_outcome") == "success" for row in group),
            "correct_first_to_non_success": sum(row.get("first_correct") is True and row.get("final_score", {}).get("primary_outcome") != "success" for row in group),
            "no_real_submission": sum(not bool(row.get("final_score", {}).get("real_submission")) for row in group),
            "runtime_errors": sum(row.get("status") == "error" for row in group),
            "recommendation_correct_but_final_not_success": sum(any(event.get("recommendation_correct") is True for event in row.get("verification_events", [])) and row.get("final_score", {}).get("primary_outcome") != "success" for row in group),
            "verification_decisions": dict(Counter(event.get("decision", "未记录") for row in group for event in row.get("verification_events", []))),
        }
    return systems


def executed_selection_audit(rows, run_dir, data_dir):
    """Offline only: expose wrong intermediate selections even when endpoints agree."""
    records, totals = [], {system: Counter() for system in SYSTEMS}
    for row in rows:
        raw = read_json(Path(data_dir) / row["case_alias"] / "offline" / "raw.json")
        correct = next(a["label"] for a in raw["action_space"] if a["action_id"] == raw["expected_action_id"])
        changes = []
        for receipt in read_jsonl(trajectory_path(run_dir, row) / "browser" / "browser_history.jsonl"):
            result = receipt.get("result", {})
            if receipt.get("action", {}).get("kind") != "select" or not result.get("ok"):
                continue
            before, after = result.get("before_selection", ""), result.get("current_selection", "")
            if not before:
                transition = "first_executed_correct" if after == correct else "first_executed_wrong"
            elif before == after:
                transition = "repeat_correct" if after == correct else "repeat_wrong"
            elif before == correct:
                transition = "correct_to_wrong"
            elif after == correct:
                transition = "wrong_to_correct"
            else:
                transition = "wrong_to_other_wrong"
            item = {"sequence": receipt["sequence"], "source": receipt["source"], "before": before,
                    "after": after, "after_correct": after == correct, "transition": transition}
            changes.append(item)
            totals[row["system"]][transition] += 1
        totals[row["system"]]["trajectories_with_any_executed_wrong"] += any(not c["after_correct"] for c in changes)
        records.append({"task": row["task"], "condition": row["condition"], "system": row["system"], "changes": changes})
    return {"totals": {k: dict(v) for k, v in totals.items()}, "trajectories": records,
            "warning": "Events are not independent samples; wrong-to-correct may be ordinary self-correction. No-submission is not wrong-choice regression."}


def top_table(rows):
    lines = ["| 任务 | 图表条件 | 系统 | 首次选择提案 | 首提按原标签正确 | 最终提交选项 | 真实提交 | 主动作评分 | 状态 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        score = row.get("final_score", {})
        fields = [row["task"], CONDITIONS.get(row["condition"], row["condition"]), SYSTEMS.get(row["system"], row["system"]),
                  row.get("first_option"), row.get("first_correct"), score.get("selected_option_label") or "未提交",
                  bool(score.get("real_submission")), score.get("primary_outcome"), STATUSES.get(row.get("status"), row.get("status"))]
        lines.append("| " + " | ".join(cell(item) for item in fields) + " |")
    return "\n".join(lines) + "\n"


def steps_section(folder, trajectory, base):
    lines = ["### 真实请求、提案与执行时间线", "",
             "模型输入截图对应动作前状态；浏览器 `after_*` 截图对应该次实际执行后的状态。未执行提案不当作已发生错误。", "",
             "| 时间位置 | 来源 | 动作／判断 | 真实执行结果或输入证据 |", "|---|---|---|---|"]
    for history in trajectory.get("history", []):
        if history.get("source") == "deterministic_setup":
            lines.append("| 准备 | 确定性环境准备，非模型推理 | %s | %s |" % (cell(action_text(history.get("action"))), cell(result_text(history.get("result")))))
    executed = {item.get("step"): item for item in read_jsonl(folder / "actor_execution.jsonl")}
    events = {item.get("step"): item for item in trajectory.get("verification_events", [])}
    for step_dir in sorted(folder.glob("step_*")):
        step = int(step_dir.name.split("_")[-1])
        proposal = read_json(step_dir / "actor" / "parsed.json")
        if proposal is None:
            lines.append("| %s | 模型调用失败／未解析 | 没有可用动作提案 | %s |" % (step, rel_link("请求目录", step_dir / "actor", base)))
            continue
        request_link = rel_link("完整实际请求", step_dir / "actor" / "request.json", base)
        public_link = rel_link("可读输入与图像引用", step_dir / "actor" / "context.json", base)
        lines.append("| %s | Actor 提案，尚未执行 | %s | %s；%s |" % (step, cell(action_text(proposal.get("action"))), request_link, public_link))
        representation = read_json(step_dir / "action_representation_normalization.json")
        if representation:
            lines.append("| %s | 仅动作容器规范化 | %s | %s |" % (step, cell(action_text(representation.get("normalized", {}).get("action"))), rel_link("原文与规范化字段", step_dir / "action_representation_normalization.json", base)))
        if step in events:
            event = events[step]
            recommendation = (event.get("verification") or {}).get("recommendation")
            lines.append("| %s | 核验器建议 | %s：%s | 建议不是提交命令 |" % (step, cell(event.get("decision")), cell(recommendation)))
            lines.append("| %s | 共同选择执行器 | 实际选择：%s | %s |" % (step, cell(event.get("applied_selection")), cell(result_text(event.get("selection_execution")))))
        if step in executed:
            item = executed[step]
            lines.append("| %s | Actor 实际执行 | %s | %s |" % (step, cell(action_text(item.get("proposal", {}).get("action"))), cell(result_text(item.get("execution")))))
        blocked = read_json(step_dir / "blocked_dependency.json")
        if blocked:
            lines.append("| %s | 规则依赖检查 | 提案未执行 | %s |" % (step, cell(blocked.get("dependency_problem"))))
    lines += ["", "浏览器原始执行日志：" + rel_link("browser_history.jsonl", folder / "browser" / "browser_history.jsonl", base) + "。"]
    if trajectory.get("error"):
        lines += ["", "实际错误：`" + str(trajectory["error"]).replace("`", "'") + "`。"]
    screenshots = sorted((folder / "browser").glob("*.png"))
    if screenshots:
        lines += ["", "最后观察到的实际页面：", "", image_link("真实最后页面", screenshots[-1], base)]
    return "\n".join(lines) + "\n"


def method_section(folder, trajectory, base):
    lines = ["### 本方法的真实防御记录", "",
             "下面记录模型实际生成的简短可检验论证，不补写正确答案或未生成的数值。O 是可见观察，B 是解释规则，结论是该动作是否符合公开任务。", ""]
    if not trajectory.get("verification_events"):
        lines += ["此轨迹没有已完成的核验事件。不能将未进入核验／核验执行失败记成核验成功或已执行核验后的失败。", ""]
    lines += ["首次选择提案（尚未执行）：", "", json_block(trajectory.get("first_proposal"))]
    for step_dir in sorted(folder.glob("step_*")):
        defense = step_dir / "defense"
        if not defense.is_dir():
            continue
        candidates = read_json(defense / "normalized_candidates.json")
        lines += ["#### 第 %s 步：候选解释与核验" % step_dir.name.split("_")[-1], ""]
        if candidates is not None:
            lines += ["规范化的规则与竞争解释：", "", json_block(candidates)]
        else:
            generated = read_json(defense / "generate" / "parsed.json")
            if generated is not None:
                lines += ["候选生成器已有实际输出，但未通过当前接口规范化；以下不是已完成的核验：", "", json_block(generated)]
            else:
                response_files = sorted((defense / "generate").glob("response_*.json"))
                if response_files:
                    response = read_json(response_files[-1], {})
                    choices = response.get("choices") or []
                    raw_text = choices[0].get("message", {}).get("content") if choices else None
                    lines += ["候选生成调用未得到可接受的解析结果；以下是原始响应文本，不作已执行论证或核验建议：", "", json_block({"raw_model_content": raw_text}),
                              rel_link("未解析的完整实际响应", response_files[-1], base), ""]
        bound = read_json(defense / "candidate_bound_audit.json")
        if bound is not None:
            lines += ["本补充协议的候选上限处理记录（按生成顺序，不按正确答案）：", "", json_block(bound)]
        repaired_json = read_json(defense / "generate" / "json_representation_normalization.json")
        if repaired_json is not None:
            lines += ["实际发生的 JSON 表示规范化记录：", "", json_block(repaired_json)]
        calls = sorted(path for path in defense.glob("**/parsed.json"))
        for path in calls:
            if "verif" in str(path.parent.name).lower():
                lines += ["独立核验器实际输出：", "", json_block(read_json(path))]
        for path in sorted(defense.glob("**/request.json")):
            lines += ["输入证据：" + rel_link(str(path.parent.name) + " 完整请求", path, base) + "。", ""]
        extra = step_dir / "additional_check"
        if (extra / "parsed.json").exists():
            lines += ["预算内额外全图复核实际输出：", "", json_block(read_json(extra / "parsed.json")),
                      rel_link("额外复核完整请求", extra / "request.json", base), ""]
        handoff = read_json(step_dir / "handoff.json")
        if handoff:
            lines += ["核验推荐 → 实际落实选择（两者分别保留）：", "", json_block(handoff)]
        rules = read_json(step_dir / "rule_state.json")
        if rules is not None:
            lines += ["交给后续 Actor 的规则状态快照：", "", json_block(rules)]
    lines += ["Actor 后续是否实际继续调用：**%s**。最终业务提交由 Actor 自己提出，见上方真实执行时间线。" % cell(trajectory.get("continued_after_verification")), "",
              "这里保留状态并传入后续调用，只证明接口与短流程链路。三个原生任务各只有一次主要读图决策，后续选择／填理由／提交不构成新的独立语义决策，因此不能据此宣称长期防复发有效；该因果效果为 **N/A**。", ""]
    return "\n".join(lines)


def example_document(task, rows, run_dir, data_dir, output_dir, document_dir=None):
    base = Path(document_dir) if document_dir else output_dir / "examples"
    lines = ["# %s：原任务与实际防御示例" % task, "",
             "这是预先固定的开发示例，不是未见测试样本。正确性标签仅在全部在线运行结束后从原任务离线评分产生，没有进入被测模型输入。", ""]
    task_rows = [row for row in rows if row["task"] == task]
    lines += [top_table(task_rows)]
    aliases = list(dict.fromkeys(row["case_alias"] for row in task_rows))
    for alias in aliases:
        row = next(item for item in task_rows if item["case_alias"] == alias)
        case = data_dir / alias
        public = read_json(case / "public.json", {})
        images = sorted(case.glob("chart.*"))
        lines += ["## " + CONDITIONS.get(row["condition"], row["condition"]), "",
                  "公开任务原文：", "", str(public.get("user_goal", "未记录")), "",
                  "可选业务动作：", ""]
        lines.extend("- " + label for label in public.get("option_labels", []))
        lines += ["", "原提交控件：" + str(public.get("completion_label", "未记录")) + "。", "",
                  "公开附属字段（不会展示隐藏字段或 text 期望答案）：", "", json_block(public.get("companion_fields", []))]
        if images:
            lines += ["原图字节未修改：", "", image_link("原始任务图表", images[0], base), ""]
        for row in [item for item in task_rows if item["case_alias"] == alias]:
            folder = trajectory_path(run_dir, row)
            trajectory = read_json(folder / "trajectory.json", {})
            lines += ["## " + CONDITIONS.get(row["condition"], row["condition"]) + " / " + SYSTEMS.get(row["system"], row["system"]), "",
                      "状态：%s。主动作评分：`%s`。真实提交：%s。" % (STATUSES.get(row.get("status"), row.get("status")), row.get("final_score", {}).get("primary_outcome"), cell(row.get("final_score", {}).get("real_submission"))), "",
                      steps_section(folder, trajectory, base)]
            if row["system"] == "competing_persistent":
                lines += [method_section(folder, trajectory, base)]
            lines += ["### 三层记录与离线评分", "", json_block({
                "first_actor_proposal": row.get("first_option"),
                "verification_recommendation_and_applied_selection": row.get("verification_events", []),
                "actor_actual_final_submission": (trajectory.get("receipt") or {}).get("selected_option_label"),
                "actual_submission_receipt": trajectory.get("receipt"),
                "offline_final_score": row.get("final_score"),
            }), rel_link("完整轨迹", folder / "trajectory.json", base), ""]
    return "\n".join(lines)


def build_health_supplement(run_dir, output_dir, data_dir=None):
    """Separate engineering supplement; never replace the v2 panel/examples."""
    run_dir, output_dir = Path(run_dir).resolve(), Path(output_dir).resolve()
    data_dir = Path(data_dir).resolve() if data_dir else Path(__file__).resolve().parent / "data"
    if not (run_dir / "offline_results.json").is_file():
        raise RuntimeError("Supplement is not complete; do not invent outcome rows")
    rows = read_json(run_dir / "offline_results.json")
    if len(rows) != 2 or {row["case_alias"] for row in rows} != {"case03", "case04"} or any(
            row["task"] != "health004" or row["system"] != "competing_persistent" for row in rows):
        raise ValueError("Expected exactly the two complete health004 full-method supplement records")
    config, budget = read_json(run_dir / "config_snapshot.json"), read_json(run_dir / "budget.json")
    scope = read_json(run_dir / "scope.json", {})
    routes = route_statistics(run_dir)
    cap_audits = [{"source": str(path.relative_to(run_dir)).replace("\\", "/"), "audit": read_json(path)}
                  for path in sorted(run_dir.glob("case*/step_*/defense/candidate_bound_audit.json"))]
    json_repairs = [str(path.relative_to(run_dir)).replace("\\", "/")
                    for path in sorted(run_dir.glob("case*/step_*/**/json_representation_normalization.json"))]
    summary = {"source_run": str(run_dir), "scope": scope, "counts": summary_counts(rows), "results": rows,
               "budget": {k: v for k, v in budget.items() if k != "events"}, "routing_and_cost": routes,
               "candidate_bound_audits": cap_audits, "actual_json_representation_repairs": json_repairs,
               "v2_rows_replaced": False, "independent_tasks_added": 0,
               "persistence_causal_effect": "not_applicable_native_single_decision"}
    lines = ["# health004：独立归档的通用格式修复工程补充", "",
             "**这是 v2 主面板完成后的两条件工程补充，不是覆盖旧失败后的新主成绩，也不是从旧 checkpoint 恢复。** 两个图表条件都重新从初始公开页运行，只运行完整方法；没有新普通 Agent 对照。v2 中两条失败记录原样保留在 [health004 主面板示例](examples/health004.md)。", "",
             "任务、原图、gold、模型与视觉提示不变。本补充启用两项预先固定的通用接纳规则：生成超过 K+1 条候选时，按原生成顺序只保留前 K+1 条，去重后不回填、不按答案筛选；仅在模型明确结束并已有完整 rules/chains JSON 对象时，允许去除对象之后的多余闭合符。原始响应与变换日志都保留。", "",
             "这些是接口补充，不是新视觉防御。补充任务由上一版接口失败定位而来，结果不得当作预先固定主面板的无偏性能提升证据。", "",
             "实际触发检查：%s 条生成发生候选截断，%s 次发生 JSON 闭合符修复。若两者均为零，本次成功不能归因于这些修复被触发；它是新生成的一次工程运行，不能由不同次响应的结果差异推出修复的因果收益。" % (sum(bool(item["audit"].get("omitted_raw_indices")) for item in cap_audits), len(json_repairs)), "",
             "## 补充结果与开销", "", top_table(rows), "",
             "本补充真实请求尝试 %s 次，浏览器操作 %s 次，失败请求尝试 %s 次。" % (budget.get("attempts"), budget.get("browser_operations"), routes["failed_attempts"]), "",
             "请求模型名：%s；响应顶层模型名：%s；usage 模型名：%s。它们是网关自报路由，不是权重身份认证。" % (json.dumps(routes["requested_models"], ensure_ascii=False), json.dumps(routes["response_models"], ensure_ascii=False), json.dumps(routes["usage_model_names"], ensure_ascii=False)), "",
             "已报告 token 合计：%s；缺失字段计数：%s。" % (json.dumps(routes["known_token_totals"], ensure_ascii=False), json.dumps(routes["attempts_missing_each_token_field"], ensure_ascii=False)), "",
             "配置：", "", json_block(config), "补充范围与此前成本引用：", "", json_block(scope),
             "## 全过程证据", "",
             example_document("health004", rows, run_dir, data_dir, output_dir, document_dir=output_dir), "",
             "## 结论边界", "",
             "仅按上面实际轨迹判断本补充是否完成。核验推荐与落实选择、Actor 最终提交分别计数；KEEP 不是纠错，暂时选对但未提交不是完成。未执行的核验、模型输出格式错误、已执行核验后的失败不可混为一谈。", "",
             "这些原生任务仍没有新的独立后续语义判断，持续规则状态防复发的因果效果为 N/A；没有去状态或等预算普通核验对照，不据此归因。", "",
             "机器记录：" + rel_link("补充离线结果", run_dir / "offline_results.json", output_dir) + "；" + rel_link("补充汇总", output_dir / "HEALTH004_SUPPLEMENT_SUMMARY.json", output_dir) + "。", ""]
    caveat = output_dir / "HEALTH004_QUALITATIVE_CAVEAT_20260923.md"
    if caveat.is_file() and run_dir.name in caveat.read_text(encoding="utf-8"):
        lines += ["## 已发现的核验依据问题", "",
                  "事后只读审查发现：误导条件的数值增长读取有图内依据，但核验器用模型自己生成的 r2 去证明存在明确业务映射，又在 page_00 证据中混入该生成规则。页面本身并未明文提供 r2。因此正确提交不等于这次规则核验具有独立充分依据；接口通过也不证明语义证据合格。持久状态还继承了这一薄弱依据。", "",
                  "这不改变原 gold，也不表示最终扩容选择错误。它把“数值趋势读取”“合理业务解释”“独立核验证成”三个层次分开：当前记录完成了执行链路，但不能作为可靠独立规则核验已经成功的证明。", "",
                  "完整证据及状态覆盖限定见 " + rel_link("health004 核验依据审查", caveat, output_dir) + "。", ""]
    report_path = output_dir / "HEALTH004_SUPPLEMENT_20260923.md"
    if report_path.exists():
        raise FileExistsError("Existing supplement report preserved; use a new versioned output directory")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "HEALTH004_SUPPLEMENT_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": str(report_path), "actual_rows": len(rows), "main_panel_replaced": False}


def build(run_dir, output_dir, data_dir=None):
    run_dir, output_dir = Path(run_dir).resolve(), Path(output_dir).resolve()
    data_dir = Path(data_dir).resolve() if data_dir else Path(__file__).resolve().parent / "data"
    if not (run_dir / "offline_results.json").is_file():
        raise RuntimeError("Run is not complete: offline_results.json is missing. Do not synthesize results.")
    rows = read_json(run_dir / "offline_results.json")
    if not isinstance(rows, list):
        raise ValueError("Expected the actual list of offline result rows")
    budget = read_json(run_dir / "budget.json", {})
    runtime = read_json(run_dir / "runtime.json", {})
    config = read_json(run_dir / "config_snapshot.json", {})
    route = route_statistics(run_dir)
    selection_audit = executed_selection_audit(rows, run_dir, data_dir)
    summary = {
        "source_run": str(run_dir), "created_at": datetime.now().isoformat(),
        "scope": "Three predetermined development tasks, two chart conditions, ordinary versus competing+persistent prototype.",
        "expected_trajectories": 12, "recorded_trajectories": len(rows),
        "counts": summary_counts(rows), "budget": {k: v for k, v in budget.items() if k != "events"},
        "routing_and_cost": route, "results": rows,
        "executed_selection_audit": selection_audit,
        "official_full_end_to_end_score": "not_computed",
        "persistence_causal_effect": "not_applicable_native_single_decision",
        "engineering_browser_regression_operations_separate_from_run": 21,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "examples").mkdir(exist_ok=True)
    prior_summary = read_json(output_dir / "report_summary.json", {})
    if str(prior_summary.get("source_run", "")).endswith("api_demo_20260923_v1") and run_dir.name != "api_demo_20260923_v1":
        archive = output_dir / "DEMO_REPORT_V1_20260923.md"
        if not archive.exists() and (output_dir / "DEMO_REPORT.md").exists():
            # A new archival presentation copy, not a mutation of prior dated report/results.
            old_report = (output_dir / "DEMO_REPORT.md").read_text(encoding="utf-8")
            archived_links = old_report.replace("(<examples/", "(<examples_v1/")
            archived_links = archived_links.replace("(<report_summary.json>)", "(<report_summary_v1.json>)")
            archive.write_text(archived_links, encoding="utf-8")
    for task in ("pub013", "health004", "b046"):
        document = example_document(task, rows, run_dir, data_dir, output_dir)
        (output_dir / "examples" / (task + ".md")).write_text(document, encoding="utf-8")
    lines = ["# 三任务 API 开发示例：实际结果与可复现证据", "",
             "此报告直接读取本轮实际请求、响应、浏览器执行回执和离线评分；未补写模型结论，也未根据效果换样本。", "",
             "## 运行范围", "",
             "本报告仅汇报运行 `%s`（协议 `%s`）。其他接口版本和补充诊断分别归档，不与本表合并成独立样本。" % (run_dir.name, config.get("protocol", "未记录")), "",
             "预先固定 pub013、health004、b046，各使用原误导图和对应清洁图；普通 Agent 与竞争解释＋持续规则状态使用相同 API 配置、图像和公开任务权限。计划 12 条轨迹，实际归档 %s 条。" % len(rows), "",
             "这是 API 工程验证和开发观察，不是完整 140 对实验、独立泛化证明、官方 GUI 系统排名，或方法优越性的定论。此前丢失数据上的结果不计入本报告证据。", "",
             "## 12 条结果逐项展示", "", top_table(rows), "",
             "“首次选择”是 Actor 首次提出的选择。方法组会在执行该提案之前核验，因此改掉错误提案属于阻止错误选择，不能伪称在已执行错误状态上恢复。普通组则按正常执行继续。", "",
             "## 数量汇总", "", json_block(summary["counts"]),
             "`wrong_first_to_primary_success` 只是首提与最终提交间的实际转移：普通组可称正常自行改正；方法组须结合其核验推荐与执行层判断，不能仅凭转移归因。KEEP 是保留判断，不是新增纠错。无提交、API 错误、证据未决分别保留。", "",
             "## 中间实际选择的变化（不只看首尾）", "", json_block(selection_audit["totals"]),
             "`correct_to_wrong` 表示已正确选择后实际改坏；`wrong_to_correct` 表示实际改回。重复选择和首次执行另列。事件不能当作独立样本，普通Agent的自行改正不能归功于核验。未提交不等于选错。逐条变化见 report_summary.json 的 executed_selection_audit。", "",
             "## 请求路由、重试与开销", "",
             "- 运行预算记录的真实请求尝试：%s；归档尝试元数据：%s；失败尝试：%s。" % (budget.get("attempts", "未记录"), route["attempts_with_metadata"], route["failed_attempts"]),
             "- 本轮浏览器操作：%s。另有三次无模型浏览器回归共 21 次操作（实现、保存工件复核、审查各7次），单列，不伪装成研究轨迹。" % budget.get("browser_operations", "未记录"),
             "- 缺少 usage 的尝试：%s。已报告 token 合计：%s；未知部分不是零。" % (route["attempts_without_usage"], json.dumps(route["known_token_totals"], ensure_ascii=False)),
             "- 各 token 字段未报告的尝试数：%s。" % json.dumps(route["attempts_missing_each_token_field"], ensure_ascii=False),
             "- 请求模型名：%s。" % json.dumps(route["requested_models"], ensure_ascii=False),
             "- 响应顶层模型名：%s。" % json.dumps(route["response_models"], ensure_ascii=False),
             "- usage 内模型名：%s。" % json.dumps(route["usage_model_names"], ensure_ascii=False), "",
             "以上名称是网关自报字段，不是对实际底层权重身份的独立认证。完整每次尝试见机器汇总与各请求目录。内网费用按用户豁免口径，不推算真实消费。", "",
             "固定配置：", "", json_block(config),
             "运行时版本与代码哈希：", "", json_block(runtime),
             "## 三份完整任务与防御示例", ""]
    for task in ("pub013", "health004", "b046"):
        lines += ["- " + rel_link(task + "：原图、原任务、竞争解释、核验、执行与真实提交", output_dir / "examples" / (task + ".md"), output_dir)]
    lines += ["", "## 评分与证据边界", "",
              "- 正确性只在在线运行结束后依据原数据集标签离线计算；标签、另一条件、CSV、误导类型和原始 action_id 不向被测模型提供。",
              "- 使用 `field-complete-public-shell-v1`：保留原公开任务、原图、原选项、真实可见附属字段与提交标签，并真正执行浏览器表单 POST；它不是原门户网站逐像素复现。",
              "- 主动作按原 expected/misleading action 对应关系评分；附属文字的 exact-match 只是独立诊断，不当作语义正确性。原官方完整端到端分数未计算。",
              "- 隐藏上下文字段由服务器带入，只是原流程静态上下文，不计作 Agent 完成的操作。只读公开字段同样不计作 Agent 推理。",
              "- 核验推荐、选择执行器落实的选择、Actor 最终提交三层不合并。暂时推荐正确但没有正确提交，不算稳定完成。",
              "- 原生三任务只有一次主要读图判断。后续选择／理由／提交可见规则状态传入接口，但没有新的独立语义判断，持续规则状态的防复发因果效果为 N/A。",
              "- 本次没有普通全图核查、竞争解释不持久化的实际对照，不能把与普通 Agent 的差异独立归因到竞争解释或持续规则状态；对应公平对照留在后续预注册实验配置。",
              "- 工程测试通过只证明接口与执行链路，不等于研究假设成立。本轮结束即停止，不自动运行完整 140 对。", "",
              "## 原始证据入口", "",
              "- " + rel_link("离线结果", run_dir / "offline_results.json", output_dir),
              "- " + rel_link("请求／操作总账", run_dir / "budget.json", output_dir),
              "- " + rel_link("运行时代码快照", run_dir / "runtime_source", output_dir),
              "- " + rel_link("机器可读报告与逐次路由记录", output_dir / "report_summary.json", output_dir), ""]
    report = "\n".join(lines)
    dated = output_dir / "DEMO_REPORT_20260923.md"
    if dated.exists() and dated.read_text(encoding="utf-8") != report:
        dated = output_dir / ("DEMO_REPORT_20260923_" + datetime.now().strftime("%H%M%S") + ".md")
    dated.write_text(report, encoding="utf-8")
    (output_dir / "DEMO_REPORT.md").write_text(report, encoding="utf-8")
    (output_dir / "report_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": str(dated), "example_count": 3, "trajectory_count": len(rows)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="Completed run directory containing offline_results.json")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--data", default=None)
    parser.add_argument("--health-supplement", action="store_true")
    args = parser.parse_args()
    renderer = build_health_supplement if args.health_supplement else build
    print(json.dumps(renderer(args.run, args.output, args.data), ensure_ascii=False, indent=2))
