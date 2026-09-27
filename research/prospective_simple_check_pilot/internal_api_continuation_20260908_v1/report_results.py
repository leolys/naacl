"""Offline-only reporting of a continued panel; no model, browser or dataset writes."""
import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def label(value):
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else "无输出/未运行"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    root = run.parent
    # Evaluator files are written by the runner only after its online schedule ends.
    table = read(run / "evaluator/CASE_TABLE.json")
    summary = read(run / "evaluator/SUMMARY.json")
    origin = read(run / "resume_origin.json")
    budget = read(run / "budget.json")
    spend = read(run / "api_wire/api_spend.json")
    prior_path = Path(origin["source"]).parent / "CUMULATIVE_COSTS.json"
    prior = read(prior_path)
    base = [r for r in table if r["strategy"] == "B0"]
    started = [r for r in base if r["prefix_started"]]
    checkpoints = [r for r in base if r["checkpoint_reached"]]
    errors = [r for r in checkpoints if not r["checkpoint_correct"]]
    manifest = read(run / "TASK_MANIFEST.json")
    label_tier = {r["task_slug"]: r["original_readiness"] for r in manifest["rows"]}
    spec_tiers = Counter(r["original_readiness"] for r in manifest["rows"] for arm in r["assets"])
    mismatch_tiers = Counter(label_tier[r["task_slug"]] for r in errors)
    calls = Counter(e["request_id"].split("/")[0] for e in budget["events"] if e["kind"] == "model_call")
    statuses = Counter(e["status"] for e in spend["entries"])
    routes = Counter(e.get("gateway_reported_route") or "未报告" for e in spend["entries"] if e["status"] == "completed")
    tokens = dict(prior["known_reported_tokens"])
    for entry in spend["entries"]:
        usage = entry.get("usage") or {}
        for src, dst in (("prompt_tokens", "api_prompt_tokens"), ("completion_tokens", "api_completion_tokens")):
            if type(usage.get(src)) is int:
                tokens[dst] += usage[src]
    current_qwen_units = {r["ordinal"] for r in base if r["model"] == "M_small" and "source_directory" not in r}
    for ordinal in current_qwen_units:
        for path in (run / "online" / f"unit_{ordinal:02d}").rglob("responses/*.json"):
            usage = (read(path).get("metadata") or {}).get("usage") or {}
            for src, dst in (("prompt_tokens", "qwen_prompt_tokens"), ("completion_tokens", "qwen_completion_tokens")):
                if type(usage.get(src)) is int:
                    tokens[dst] += usage[src]
    stop = read(run / "stop.json") if (run / "stop.json").exists() else None
    totals = dict(scope="same_fixed_panel_with_prior_segments_linked_once", planned_base_tasks=8,
        started_base_tasks=len({r["task_slug"] for r in started}), started_prefixes=len(started),
        natural_checkpoints=len(checkpoints), natural_error_checkpoints=len(errors),
        independent_error_tasks=len({r["task_slug"] for r in errors}),
        confirmed_submissions=sum(r["confirmed_completion"] for r in table),
        new_confirmed_submissions=sum(r["confirmed_completion"] and "source_directory" not in r for r in table),
        api_attempts=calls["M_strong"], qwen_calls=calls["M_small"], live_model_attempts=budget["model_calls"],
        current_segment_api_attempts=len(spend["entries"]),
        current_segment_qwen_calls=calls["M_small"] - prior["qwen_calls"],
        current_segment_api_statuses=dict(statuses), current_segment_completed_gateway_routes=dict(routes),
        api_wire_attempt_records=prior["api_wire_attempt_records"] + len(spend["entries"]),
        api_accounting_calls_without_new_wire_entry=calls["M_strong"] - prior["api_wire_attempt_records"] - len(spend["entries"]),
        live_browser_transitions=budget["browser_transitions"],
        engineering_browser_transitions=origin["non_live_transition_consumption"],
        all_actual_browser_transitions=budget["browser_transitions"] + origin["non_live_transition_consumption"],
        replay_transitions=sum(e["kind"] == "browser_transition" and e.get("phase", "").split("/")[-1].startswith("replay") for e in budget["events"]),
        monetary_cap_enforced=spend["enforce_money_cap"],
        api_accounted_upper_usd=str(Decimal(origin["old_api_accounted_upper_usd"]) + Decimal(spend["accounted_upper_usd"])),
        api_actual_billed_usd=None, known_reported_tokens=tokens,
        prior_cost_source=str(prior_path), stop=stop,
        original_task_spec_label_tiers=dict(spec_tiers), checkpoint_mismatches_by_label_tier=dict(mismatch_tiers),
        error_count_basis="Dataset expected-action mismatch, not uniformly independently verified visual error; original scoring unchanged.",
        note="Monetary estimates retained only for provenance; owner waives monetary stop, not call/transition/retry limits. Usage absent from failed replies is unknown.")
    (root / "CUMULATIVE_COSTS.json").write_text(json.dumps(totals, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 内网 API 接续结果", "",
        "范围：原固定8基础任务 × 两图表条件 × 两模型，各自自然首次提交前状态比较B0/B2/B3。这里是真实模型、原数据集评分、safe-shell主决策/本地POST/确认链；不是原网站全流程 benchmark，也不是官方GUI系统排名。单次开发面板，无多随机种子显著性结论。", "",
        f"实际启动{len(started)}/32个前缀，覆盖{totals['started_base_tasks']}/8个基础任务；自然checkpoint {len(checkpoints)}，与原expected action不匹配的checkpoint {len(errors)}，涉及{totals['independent_error_tasks']}个独立基础任务。",
        f"确认提交{totals['confirmed_submissions']}/96条策略记录，其中本段新增{totals['new_confirmed_submissions']}条，之前36条保留原文件引用且不重跑。多策略不算独立任务。", "",
        f"标签资格（按16个任务×条件spec计，不因两模型重复）：{dict(spec_tiers)}。即正式标注4个、历史未注明资格6个、image-only待复核草稿6个；不是16个同等确认的real_gt。6个checkpoint不匹配分层为{dict(mismatch_tiers)}。",
        "下文‘正确/错误/恢复’及原机器字段都仅指与原数据集expected action匹配/不匹配及其变化，原评分不改。health005、env035含draft expected action；b014另有业务动作语义限定。不能把全部score errors称为完全没有可见证据支持的决定。详见CASE_NOTES和EXPERIMENT_AUDIT。", "",
        "B0=不核查、执行原pending submit；B2=独立全图目标语义核验（不暴露当前选择及其历史），最多1次核验；B3=通用主动视觉核验（最多3次核验/2次crop，不强制裁剪）。B2/B3核验后执行推荐，再交普通actor最多4步自行决定和提交；并非确定性代提交。三层记录见[CASE_LAYERS.md](CASE_LAYERS.md)。", "",
        "模型：Qwen3-VL-8B-Instruct（bfloat16，temperature=0，top_p=1，seed=12345，输出1024，max_pixels=1003520，原生多图）；API请求gpt-5.6-sol（medium reasoning，输出8192，high图像细节，不发送temperature，并发1）。身份按用户豁免仅记录，不能由请求名断定上游真实权重。",
        f"本段成功API响应报告的上游路由：{dict(routes)}。历史各段见原api_wire；不能把请求标签当成已验证的强模型身份。", "",
        "## 分组结果", "",
        "原始成功率分母为每组8个已启动前缀，保留未到hook者；括号百分比则为(该方法正确数−B0正确数)/B0正确数，两者分母不同。各模型checkpoint池独立；错误为零时恢复率N/A。clean是原对照图表，不代表模型必定判断正确。", "",
        "|模型|图表条件|已启动|到hook|错误checkpoint|B0正确提交|B2正确提交（相对B0）|B3正确提交（相对B0）|",
        "|---|---|---:|---:|---:|---:|---|---|"]
    for g in summary["groups"]:
        methods = {s["strategy"]: s for s in g["strategies"]}
        b0 = methods["B0"]["confirmed_correct_completions"]
        def result(s):
            n = methods[s]["confirmed_correct_completions"]
            delta = f"{(n-b0)/b0:+.1%}" if b0 else "N/A"
            return f"{n}（差{n-b0:+d}；{delta}）"
        lines.append(f"|{g['model']}|{g['arm']}|{g['started_prefixes']}|{g['checkpoint_count']}|{g['error_checkpoint_count']}|{b0}|{result('B2')}|{result('B3')}|")
    lines += ["", "M_small=本地Qwen8B；M_strong=网关请求Sol；official140=误导图表，clean140=原对照。", "",
        "|模型/条件/方法|错误状态恢复|正确保持|正确→错|正确→未提交|已尝试核验|核验无返回|裁剪数|",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for g in summary["groups"]:
        for s in g["strategies"]:
            lines.append(f"|{g['model']}/{g['arm']}/{s['strategy']}|{s['recovery_fraction']}|{s['correct_preserved']}|{s['correct_to_wrong']}|{s['correct_to_no_submit']}|{s['verification_executed']}|{s['verifier_failed_before_policy_return']}|{s['B3_crops']}|")
    lines += ["", "## 全部预定前缀", "",
        "|序号|任务|条件|模型|自然checkpoint|B0|B2|B3|", "|---:|---|---|---|---|---|---|---|"]
    for b in base:
        rows = {r["strategy"]: r for r in table if r["ordinal"] == b["ordinal"]}
        cp = (label(b.get("checkpoint_selection")) + (" / 正确" if b["checkpoint_correct"] else " / 错误")) if b["checkpoint_reached"] else ("未到hook" if b["prefix_started"] else "未启动")
        def outcome(r):
            return ("正确提交" if r["confirmed_correct_completion"] else "错误提交") if r["confirmed_completion"] else r["status"]
        lines.append(f"|{b['ordinal']}|{b['task_slug']}|{b['arm']}|{b['model']}|{cp}|" + "|".join(outcome(rows[s]) for s in ("B0", "B2", "B3")) + "|")
    lines += ["", "## 成本、版本与结论边界", "",
        f"累计真实模型尝试{budget['model_calls']}/800（API {calls['M_strong']}/400；Qwen {calls['M_small']}/400）。本段API {len(spend['entries'])}次：{dict(statuses)}；Qwen新增{totals['current_segment_qwen_calls']}次。",
        f"live浏览器{budget['browser_transitions']}，工程{origin['non_live_transition_consumption']}，实际总计{totals['all_actual_browser_transitions']}/4000；原任务及重放均计数。API发送前额外账本计数差{totals['api_accounting_calls_without_new_wire_entry']}（若非零不能当成已发HTTP）。",
        f"旧预留规则的机械记账累计{totals['api_accounted_upper_usd']}美元仅兼容历史字段，不代表实际消费或实价估计，也不再执行上限。镜像路由未按旧白名单结算，因此仍保留大额占位；用户声明公司内网非实际消费。研究成本以调用、transition及已报告token为准：{tokens}。",
        f"停止状态：{stop if stop else '预定面板遍历完成，无全局停止错误；逐轨迹失败仍保留。'}", "",
        "运行代码副本见live_panel_04/executed_sources，命令与测试见[COMMANDS.md](COMMANDS.md)，配置及仅费用豁免见[PROTOCOL_AMENDMENT.md](PROTOCOL_AMENDMENT.md)。旧提交根路径保留，不回写旧manifest、score或运行身份。",
        "工程测试通过只说明所测试链路；暂时改对不等于持续正确提交。没有错误checkpoint时恢复率为N/A；有错误时也只对相应同模型状态池比较。真实选择/工具回执/提交是直接观察，内部信念、因果机制及复杂观察选择必要性不能由本面板单独证明。", "",
        "更具体的直接观察与解释区分见[CASE_NOTES.md](CASE_NOTES.md)。本轮到此停止，不扩140对、不开发新机制。审查见EXPERIMENT_AUDIT.md（若不存在则尚未完成审查）。"]
    (root / "PILOT_REPORT.md").write_text("\n".join(lines) + "\n")
    layers = ["# 核验推荐—落实选择—actor最终提交", "", "策略缩写含义见PILOT_REPORT；无输出不能补写成模型意见。", "",
        "|序号/任务/条件/模型|方法|checkpoint|核验推荐|实际执行后|actor提交|确认|原评分/状态|",
        "|---|---|---|---|---|---|---|---|---|"]
    for r in table:
        final = (r.get("actor_final_submission") or {}).get("option")
        layers.append(f"|{r['ordinal']}/{r['task_slug']}/{r['arm']}/{r['model']}|{r['strategy']}|{label(r.get('checkpoint_selection'))}|{label(r.get('verifier_recommendation'))}|{label(r.get('executor_selection'))}|{label(final)}|{r['confirmed_completion']}|{r['score']['outcome']} / {r['status']}|")
    (root / "CASE_LAYERS.md").write_text("\n".join(layers) + "\n")
    print(json.dumps(totals, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
