"""Offline report of this authorized panel; invoke only after online run ended."""
import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def label(value):
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else "未运行/无输出"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    root = run.parent
    audit_status = read(root / "EXPERIMENT_AUDIT.json")["verdict"] if (root / "EXPERIMENT_AUDIT.json").exists() else "待审"
    summary = read(run / "evaluator/SUMMARY.json")
    table = read(run / "evaluator/CASE_TABLE.json")
    progress = read(run / "progress.json")
    origin = read(run / "resume_origin.json")
    ledger = read(run / "budget.json")
    spend = read(run / "api_wire/api_spend.json")
    old = Path(origin["source"])
    prior_cost = read(old.parent / "CUMULATIVE_COSTS.json")
    baselines = [r for r in table if r["strategy"] == "B0"]
    started = [r for r in baselines if r["prefix_started"]]
    checkpoints = [r for r in baselines if r["checkpoint_reached"]]
    errors = [r for r in checkpoints if not r["checkpoint_correct"]]
    correct = [r for r in checkpoints if r["checkpoint_correct"]]
    current_calls = Counter(e["status"] for e in spend["entries"])
    routes = Counter(e.get("gateway_reported_route") or "未报告" for e in spend["entries"] if e["status"] == "completed")
    unknown = [e for e in spend["entries"] if "usage_cost_upper_usd" not in e]
    live_calls = Counter(e["request_id"].split("/")[0] for e in ledger["events"] if e["kind"] == "model_call")
    token_totals = dict(api_prompt_tokens=prior_cost["api_known_prompt_tokens"],
        api_completion_tokens=prior_cost["api_known_completion_tokens"],
        qwen_prompt_tokens=prior_cost["qwen_prompt_tokens_reported"],
        qwen_completion_tokens=prior_cost["qwen_completion_tokens_reported"])
    for entry in spend["entries"]:
        usage = entry.get("usage") or {}
        for field, key in (("prompt_tokens", "api_prompt_tokens"), ("completion_tokens", "api_completion_tokens")):
            if type(usage.get(field)) is int:
                token_totals[key] += usage[field]
    local_ordinals = {p["ordinal"] for p in progress["prefixes"] if p["model"] == "M_small" and "source_run" not in p}
    for ordinal in local_ordinals:
        for path in (run / "online" / f"unit_{ordinal:02d}").rglob("responses/*.json"):
            usage = (read(path).get("metadata") or {}).get("usage") or {}
            for field, key in (("prompt_tokens", "qwen_prompt_tokens"), ("completion_tokens", "qwen_completion_tokens")):
                if type(usage.get(field)) is int:
                    token_totals[key] += usage[field]
    totals = dict(
        scope="same_preselected_panel_cumulative_including_linked_prior_units",
        planned_base_tasks=8, started_base_tasks=len({r["task_slug"] for r in started}),
        started_prefixes=len(started), natural_checkpoints=len(checkpoints), natural_error_checkpoints=len(errors),
        independent_error_tasks=len({r["task_slug"] for r in errors}),
        confirmed_submissions=sum(r["confirmed_completion"] for r in table),
        new_confirmed_submissions=sum(r["confirmed_completion"] and "source_directory" not in r for r in table),
        api_attempts=live_calls["M_strong"], qwen_calls=live_calls["M_small"],
        api_wire_attempt_records=prior_cost["api_attempts"] + len(spend["entries"]),
        api_accounting_calls_without_new_wire_entry=live_calls["M_strong"] - prior_cost["api_attempts"] - len(spend["entries"]),
        live_model_attempts=ledger["model_calls"],
        live_browser_transitions=ledger["browser_transitions"],
        engineering_browser_transitions=origin["non_live_transition_consumption"],
        all_actual_browser_transitions=ledger["browser_transitions"] + origin["non_live_transition_consumption"],
        current_segment_api_attempts=len(spend["entries"]), current_segment_api_statuses=dict(current_calls),
        current_segment_completed_gateway_routes=dict(routes),
        api_accounted_upper_usd=str(Decimal(origin["old_api_accounted_upper_usd"]) + Decimal(spend["accounted_upper_usd"])),
        current_segment_unsettled_reservations_usd=str(sum((Decimal(e["reserved_usd"]) for e in unknown), Decimal(0))),
        api_actual_billed_usd=None,
        known_reported_tokens=token_totals,
        stop=read(run / "stop.json") if (run / "stop.json").exists() else None,
        prior_cost_source=str(old.parent / "CUMULATIVE_COSTS.json"),
        note="Reservations are not invoices; earlier ledgers are linked once, not summed repeatedly.")
    (root / "CUMULATIVE_COSTS.json").write_text(json.dumps(totals, indent=2, ensure_ascii=False) + "\n")
    lines = ["# 同一面板补跑报告", "",
        "本报告由本目录 report_results.py 在在线调度终止后生成；原数据集评分，safe-shell 主决策/真实本地POST/确认链，不是原网站完整 benchmark 或官方 GUI 系统排名。", "",
        f"原计划8个基础任务、32条自然前缀、96条策略记录；累计实际启动{len(started)}条前缀，覆盖{totals['started_base_tasks']}个基础任务，形成{len(checkpoints)}个自然提交前 checkpoint。",
        f"其中{len(errors)}个错误 checkpoint（{totals['independent_error_tasks']}个独立基础任务）；累计{totals['confirmed_submissions']}条确认提交，本次新增{totals['new_confirmed_submissions']}条，原9条只引用而不重跑。", "",
        "这次已完成状态上的结果：" + "；".join(f"{s}正确完成{sum(r['confirmed_correct_completion'] for r in table if r['strategy']==s)}/{len(checkpoints)}" for s in ("B0", "B2", "B3")) + "。这只是已到hook的状态保持，全部已启动前缀口径另见下表。",
        "具体核查后改坏及理由—图像不一致见[CASE_NOTES.md](CASE_NOTES.md)，未完成原因见[NEXT_ACTION.md](NEXT_ACTION.md)。official140表示原误导条件，clean140表示原clean对照。", "",
        "## 方法与模型", "",
        "B0：执行原提交提议，不核查。B2：独立全图目标核验，不给当前选择或暴露它的历史。B3：通用主动视觉核验，可裁剪但不强制。B2/B3分别最多1/3次逻辑核验，之后最多4次普通actor动作。推荐、实际改选、最终提交分开保存。所有方法共用H_base真实历史与条件式完成说明，未改变提示、原图、gold或选项顺序。", "",
        "M_small（本地）：Qwen3-VL-8B-Instruct，bfloat16、贪心解码、temperature0/top_p1/seed12345、输出上限1024、max_pixels1003520、原生多图；共享GPU0、25% allocator cap。M_strong（API）：请求gpt-5.6-sol，reasoning_effort=medium、输出上限8192、image_detail=high、并发1；身份遵照用户豁免只记录，不能据请求名认定真实权重。",
        f"本次HTTP200完成响应报告的路由：{dict(routes)}。失败尝试的上游权重未知。", "",
        "## 按模型与图表条件分开比较", "",
        "分母为该组全部已启动前缀；未到hook的失败不删去。各模型产生自己的状态池，不能跨模型把恢复分数直接当作方法强弱。误导条件不等于选错，clean条件也不保证选对。", "",
        "| 模型 | 条件 | 已启动 | 到hook | 错误checkpoint | B0正确完成 | B2正确完成（相对B0） | B3正确完成（相对B0） |",
        "|---|---|---:|---:|---:|---:|---|---|"]
    for group in summary["groups"]:
        by_strategy = {s["strategy"]: s for s in group["strategies"]}
        baseline = by_strategy["B0"]["confirmed_correct_completions"]
        def value(name):
            n = by_strategy[name]["confirmed_correct_completions"]
            relative = f"{(n-baseline)/baseline:+.1%}" if baseline else "N/A（B0为0）"
            return f"{n}（差{n-baseline:+d}；相对{relative}）"
        lines.append(f"| {'Qwen8B' if group['model']=='M_small' else '网关请求Sol'} | {'误导' if group['arm']=='official140' else 'clean'} | {group['started_prefixes']} | {group['checkpoint_count']} | {group['error_checkpoint_count']} | {baseline} | {value('B2')} | {value('B3')} |")
    lines += ["", "| 模型/条件/核查 | 错误状态恢复 | 正确保持 | 正确→错 | 正确→未提交 | 已尝试核验 | 未返回核验结果 | 裁剪次数 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for g in summary["groups"]:
        for s in g["strategies"]:
            lines.append(f"| {g['model']}/{g['arm']}/{s['strategy']} | {s['recovery_fraction']} | {s['correct_preserved']} | {s['correct_to_wrong']} | {s['correct_to_no_submit']} | {s['verification_executed']} | {s['verifier_failed_before_policy_return']} | {s['B3_crops']} |")
    lines += ["", "## 逐前缀实际结果", "",
              "正确/错误均按原评分；‘未运行’不能当成策略失败，‘未到hook’不能当成核验已执行失败。", "",
              "| 序号 | 基础任务 | 条件 | 模型 | 原checkpoint选项/评分 | B0 | B2 | B3 |", "|---:|---|---|---|---|---|---|---|"]
    for base in baselines:
        rows = {r["strategy"]: r for r in table if r["ordinal"] == base["ordinal"]}
        cp = (label(base["checkpoint_selection"]) + (" / 正确" if base["checkpoint_correct"] else " / 错误")) if base["checkpoint_reached"] else ("未到hook" if base["prefix_started"] else "未启动")
        def result_text(row):
            if row["confirmed_completion"]:
                return "正确提交" if row["confirmed_correct_completion"] else "错误提交"
            return row["status"]
        lines.append(f"| {base['ordinal']} | {base['task_slug']} | {base['arm']} | {base['model']} | {cp} | {' | '.join(result_text(rows[s]) for s in ('B0','B2','B3'))} |")
    lines += ["", "## 直接观察与结论边界", "",
        "1. 原中断公开页面、历史、截图像素和完整wire图像字节已重建一致；前三个单元只链接旧工件，未再生成或提交。真实重试是否完成见api_wire各物理attempt，而不是由mock通过推断。",
        f"2. 本组共有{len(errors)}个错误提交前状态。" + ("恢复率为N/A，不能由正确保持叫作纠错成功。" if not errors else "只能在这些同模型共享状态内比较B0/B2/B3；不能把多策略当多个独立错误样本。"),
        "3. 字段变化和真实提交是直接观察；内部信念是否修复、视觉观察选择是否必要均不能仅靠这份结果判定。暂时改选不等于稳定恢复。",
        "4. 工程重试不是视觉防御；没有改任务或补强提示，也未启动复杂观察选择、前提账本、回滚或新机制。", "",
        "## 成本与停止", "",
        f"累计真实模型调用尝试{ledger['model_calls']}（API {live_calls['M_strong']}、Qwen {live_calls['M_small']}）；live浏览器{ledger['browser_transitions']}，加工程{origin['non_live_transition_consumption']}，实际共{totals['all_actual_browser_transitions']} / 4000。",
        f"本次API物理尝试{len(spend['entries'])}：{dict(current_calls)}。累计API费用记账上界${totals['api_accounted_upper_usd']} / $50；未知请求不释放预留，不是实际账单。",
        f"API wire累计{totals['api_wire_attempt_records']}条；调用账本中另有{totals['api_accounting_calls_without_new_wire_entry']}次没有新wire条目的前置计数（例如发送前预算拒绝），不能把它当成已派发HTTP请求。",
        f"累计已报告token：{token_totals}。未返回usage的失败请求仍未知；不能把它们当作零token或零费用。",
        f"停止工件：{totals['stop'] if totals['stop'] else '没有调度停止错误；预定遍历结束，个别轨迹结果仍逐条保留。'}", "",
        f"详细原始表在live_panel_03/evaluator/CASE_TABLE.json与.csv；三层记录见CASE_LAYERS.md。SOURCE_CHANGES.patch与运行时源码副本给出工程版本；旧结果未回写。审查结论：{audit_status}，详见EXPERIMENT_AUDIT.md；同系列审查为provisional，不等于完整性PASS或研究假设成立。"]
    (root / "PILOT_REPORT.md").write_text("\n".join(lines) + "\n")
    layers = ["# 推荐—落实—最终提交三层记录", "", "B0=不核查；B2=独立全图目标核验；B3=通用主动视觉核验。空缺明确标记，不由理由补写推荐或替代actor选择。", "",
        "| 单元/任务/条件/模型 | 配置 | checkpoint | 核验推荐 | 执行后选择 | actor提交选项 | 已确认提交 | 原评分/状态 |", "|---|---|---|---|---|---|---|---|"]
    for r in table:
        final = (r.get("actor_final_submission") or {}).get("option")
        layers.append(f"| {r['ordinal']}/{r['task_slug']}/{r['arm']}/{r['model']} | {r['strategy']} | {label(r.get('checkpoint_selection'))} | {label(r.get('verifier_recommendation'))} | {label(r.get('executor_selection'))} | {label(final)} | {r['confirmed_completion']} | {r['score']['outcome']} / {r['status']} |")
    (root / "CASE_LAYERS.md").write_text("\n".join(layers) + "\n")
    print(json.dumps(totals, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
