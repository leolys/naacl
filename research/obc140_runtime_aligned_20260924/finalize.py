# -*- coding: utf-8 -*-
"""Report actual new-run results and input provenance; never infer gold accuracy."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

from prepare import HERE, OLD_RUN, read, digest, check_preservation
import native_zh


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def gather():
    records = list(native_zh.records())
    phase_counts = {phase: dict(Counter(row["status"][phase] for row in records))
                    for phase in ("proposal", "generation", "verification")}
    attempts, responses, failures, models, finished = [], [], [], Counter(), Counter()
    for path in sorted((HERE / "run/tasks").glob("*/*/round_*/attempt_*.json")):
        meta = read(path)
        attempts.append({"path": str(path), **meta})
        if meta.get("error_category"):
            failures.append({"path": str(path), "category": meta["error_category"], "phase": meta.get("phase")})
    for path in sorted((HERE / "run/tasks").glob("*/*/round_*/response_*.json")):
        response = read(path)
        models[str(response.get("model"))] += 1
        choices = response.get("choices", [])
        if choices:
            finished[str(choices[0].get("finish_reason"))] += 1
        responses.append(str(path))
    invalid = []
    for record in records:
        for phase in ("proposal", "generation", "verification"):
            if record["status"][phase] in ("invalid", "failed", "blocked"):
                stage = record["stages"].get(phase, {})
                reason = stage.get("error_category")
                # Replay validation OFFLINE solely for a more specific failure label.
                # Canonical records and responses remain unchanged.
                if record["status"][phase] == "invalid" and phase + "_invalid_raw" in record:
                    sys.path.insert(0, str(HERE))
                    import runner
                    try:
                        runner.citation_adapter.validate_stage(phase, record[phase + "_invalid_raw"], record, read(HERE / "config.json"))
                    except Exception as error:
                        reason = str(error)
                invalid.append({"task": record["task_slug"], "phase": phase,
                                "status": record["status"][phase], "reason": reason})
    pending = [r["task_slug"] for r in records
               if not (all(r["status"][p] == "completed" for p in phase_counts) or
                       any(r["status"][p] in {"invalid", "failed"} for p in phase_counts))]
    multi_choice = [r["task_slug"] for r in records
                    if len({c["option_label"] for c in (r.get("normalized") or {}).get("chains", [])}) >= 2]
    chained = Counter(len((r.get("normalized") or {}).get("chains", [])) for r in records)
    budget = read(HERE / "run/budget.json") if (HERE / "run/budget.json").exists() else {}
    recommendation = Counter()
    for r in records:
        if r["status"]["verification"] != "completed":
            continue
        choice = r["verification"].get("recommendation")
        original = r["proposal"]["action"]["option"]
        # The fixed schema recommendation is an option label or null.
        recommendation["none" if choice is None else "same_as_proposal" if choice == original else "different_from_proposal"] += 1
    state = read(HERE / "run/run_state.json")
    test_path = HERE / "offline_tests_final_delivery.xml"
    tests = {}
    if test_path.is_file():
        suites = list(ET.parse(test_path).getroot().iter("testsuite"))
        tests = {key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
                 for key in ("tests", "failures", "errors", "skipped")}
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "run_status": state.get("status"),
        "blocked_reason": state.get("blocked_reason"), "domain_counts": dict(Counter(r["domain"] for r in records)),
        "phase_counts": phase_counts, "record_count": len(records), "pending_tasks": pending,
        "request_attempts": budget.get("request_attempts", 0), "attempt_files": len(attempts),
        "response_files": len(responses), "response_model_aliases": dict(models),
        "finish_reasons": dict(finished), "transport_or_parse_attempt_errors": failures,
        "terminal_stage_failures": invalid, "normalized_chain_counts": dict(chained),
        "different_option_candidate_tasks": multi_choice, "verification_recommendations": dict(recommendation),
        "estimated_ledger_usd": budget.get("estimated_ledger_usd", 0), "actual_bill_usd": None,
        "old_model_results_reused": 0, "api_translation_calls": 0, "browser_business_actions": 0,
        "native_translation": native_zh.status(), "source_preservation": check_preservation(HERE / "prepared"),
        "offline_delivery_tests": tests,
        "artifact_checks": {name: read(HERE / name) if (HERE / name).is_file() else "not_yet_run"
                            for name in ("all_request_checks.json", "browser_check.json", "note_isolation_check.json")}}
    save("RESULTS.json", summary)
    return summary


def report(summary):
    diff = read(HERE / "prepared/input_comparison.json")["summary"]
    p = summary["phase_counts"]
    stage_table = "\n".join("| %s | %s | %s | %s | %s | %s |" % (
        label, p[phase].get("completed", 0), p[phase].get("invalid", 0),
        p[phase].get("failed", 0), p[phase].get("not_run", 0),
        sum(value for key, value in p[phase].items() if key not in {"completed", "invalid", "failed", "not_run"}))
        for phase, label in (("proposal", "初始选择提案"), ("generation", "解释／竞争解释生成"),
                             ("verification", "规则与解释核验")))
    text = f'''# 原网页对齐版 OBC140：修复与本轮记录

## 当前实际完成状态

- 汇总时间：{summary['generated_at']}；队列状态：`{summary['run_status']}`；阻塞原因：`{summary['blocked_reason']}`。运行中汇总仅是临时快照。
- 固定任务：140 条原 official140 图，图表未改；不是 280 条双条件任务。
- 目录组成：`{json.dumps(summary['domain_counts'], ensure_ascii=False)}`。这是样本数，不表示 140 种独立任务语义。
- 新请求尝试：{summary['request_attempts']}；已有响应：{summary['response_files']}；待处理任务：{len(summary['pending_tasks'])}。
- 提案结构通过：{p['proposal'].get('completed', 0)}；OBC 生成结构通过：{p['generation'].get('completed', 0)}；核验结构通过：{p['verification'].get('completed', 0)}。
- 规范化后包含不同选项候选：{len(summary['different_option_candidate_tasks'])} 条。多链未必有不同行动，结构通过不等于解释正确。
- 新估算账本：{summary['estimated_ledger_usd']:.6f} 美元；20 美元授权上限／450 请求尝试。不是供应商实际账单。
- 中文当前完整任务数：{summary['native_translation']['tasks_current_text_complete']}；待译唯一字符串：{summary['native_translation']['missing_unique_strings']}；APIYI 翻译调用 0。
- 旧模型解释复用 0；真实浏览器业务操作／提交 0；GPU 使用 0。

这是静态 OBC 解释与核验材料，不是防御有效率，也不是真实 Agent 任务完成率。没有根据 gold 判断正确或错误，不把核验器结论当作真实答案。

## 结果分层：不能混在一起统计

| 阶段 | 结构通过 | 返回但结构无效 | 调用／解析失败 | 未运行 | 其他状态（含进行中或阻塞） |
|---|---:|---:|---:|---:|---:|
{stage_table}

前阶段无效／失败时不执行后续阶段；“未运行”不是已执行失败。无效草稿保留供人工阅读，不补写为合格解释。规范化后的链数量分布：`{json.dumps(summary['normalized_chain_counts'], ensure_ascii=False)}`；其中 0 包括没有有效生成结果的记录。

仅在结构通过的核验中，建议保持初始选项 {summary['verification_recommendations'].get('same_as_proposal', 0)} 条，建议另一选项 {summary['verification_recommendations'].get('different_from_proposal', 0)} 条，无明确推荐 {summary['verification_recommendations'].get('none', 0)} 条。这些是**建议**，没有执行改选或提交；不把“建议另一选项”称为纠正成功，也不把“保持”称为正确。

结构校验不等于人工语义审核：例如 O 是否只记录可见事实、B 是否过度确定、竞争链是否有充分依据，仍需逐条人工阅览。中文保留模型原有错误和不确定性，不作为第二次答题。

## 修复了什么

原适配直接读取 raw workflow_instruction，绕过原网页已有的任务覆盖。这轮从入口／看板／表单真实 non-review HTML 提取业务公开字段。

| 修复范围 | 条数 |
|---|---:|
| 标题、用户目标、图表说明发生变化 | 各 58 |
| 主选项标签或顺序发生变化 | 127 |
| 其中仅顺序不同 | 102 |
| 其中选项集合也不同 | 25 |
| 主字段标签变化 | 36 |
| 伴随字段／上下文与真实提交按钮变化 | 各 140 |
| 补入实际公开规则表 | 14 条有表格，其他为空 |

所有 140 条完整输入均有变化，因此全部重新生成，不把旧结果换标题后沿用。新输入含公开规则、原选项顺序、真实 Submit Form 和三页说明；新旧差异不能只归因于“去掉误导提示”。

## 信息边界与保留的限定

- API 仅收到英文 public.json、原图、本轮前阶段输出。无 gold、离线审核标签、正确选项标记、原始 CSV 或另一 arm。
- 原网页入口中 54 条 environment/health 机制 chip 属于 benchmark 元数据，被统一业务字段白名单排除。不是把整个原网页截图原样输入模型，也没有修改原网页。
- b003、b006、b008 公开规则仍含 labeled rating share / mislabeled_value，原样保留并标注，不能称这些样本完全无提示。未命中关键词也不等于人工认证完全中性。
- 任务图上的标题、图例、文字保留，包括相互冲突的线索；未重绘、未删除样本。
- 中文是单独阅览层，保留错误与不确定性。只复用完全相同英文字符串的既有中文译文，不复用旧模型解释。

## 模型与运行

请求模型 gpt-5.6-terra，经已有 APIYI 服务；温度 0，三阶段输出上限 700 / 2200 / 2200；单并发。请求名／返回名仅证明网关声明，不能验证权重身份。真实返回模型名称分布：`{json.dumps(summary['response_model_aliases'], ensure_ascii=False)}`。

使用原 proposal / observation_boundary_v4 / public_task_citation_v1，不按样本调提示。固定流程检查 b001、pub003、env008 计入同一预算，其余按原目录顺序。结构失败、截断和无推荐原样保留；没有质量重采样。

保留原回复、解析结果和规范化结果。沿用已有 JSON 外层格式兼容、公开引用适配及按生成顺序的候选数量上限；这些不是新的模型回答，也不是根据正确答案挑选候选。请在展示中对照“原始生成”与“规范化后”，详细差异以逐任务适配记录为准。

## 工件入口

- RUNTIME_INPUTS_140_ZH.html：140 条原网页公开任务与旧版差异，明确不含模型结果。
- OBC140_TERRA_ZH_REVIEW.html：本轮新模型解释、规则状态与中文阅览；尚未生成此最终文件时只看明确标记的 PREVIEW_IN_PROGRESS.html。
- prepared/tasks/<编号>/public.json：实际英文任务输入；provenance.json 是不进入模型的来源旁证。
- run/tasks/<编号>/<阶段>/round_001/request.json：实际请求；同目录响应、attempt、parsed／validated 保留全部可用工件。
- run/tasks/<编号>/record.json：本轮英文规范记录；translation=not_run 是因为中文另存，并非调用遗漏。
- run/summary.json 和 run/budget.json 提供动态真实计数；run_state.json 中的 real_model_requests 是初始化占位值，不作为计数依据。
- translations/：原生中文映射与去重英文；不回流模型。
- RESULTS.json：全部状态、失败、成本与计数；不得把下游未运行当成已执行核验失败。
- reviews/：同家族独立上下文审查，工程性 provisional，不冒充人工或跨模型验收。

## 工程回执

- 运行前回归 170 项通过；交付前完整回归：`{json.dumps(summary['offline_delivery_tests'], ensure_ascii=False)}`。新增两项只检查新旧阅览笔记隔离，不改变模型运行协议。
- 原来源与旧工件检查 {summary['source_preservation']['checked_files']} 个文件，变化列表：`{summary['source_preservation']['changed_files']}`。
- 全量请求逐项一致性见 all_request_checks.json；最终 140 条离线显示见 browser_check.json；笔记隔离见 note_isolation_check.json。尚未产生的回执在 RESULTS.json 标作 not_yet_run，不能当作通过。
- 所有工程通过均不证明研究假设或模型语义正确性。

## 停止条件

固定 140 条处理完或达到授权预算即停止，不追加任务、改变模型或开发新机制。若 pending_tasks 非空，明确报告剩余，不称全量完成。
'''
    (HERE / "REPORT.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    result = gather()
    report(result)
    print(json.dumps({key: result[key] for key in ("request_attempts", "phase_counts", "estimated_ledger_usd", "pending_tasks")}, ensure_ascii=False))
