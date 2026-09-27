"""Offline, source-traceable view of the fixed explanation-completion panel.

No model/network imports, translation calls, image transformations, or result
inference. Original JSON remains canonical; Chinese notes are separately
authored reading aids. All model/source text is escaped before HTML rendering.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
CASE_IDS = ("b001", "b002", "pub013")
STATUS = {
    "supported": "有支持（模型核验）", "refuted": "被否定（模型核验）",
    "undetermined": "尚不能确定", "active": "启用记录（仅解释规则维度有支持）",
    "pending": "待定", "revoked": "撤销", "disputed": "存在分歧",
    "completed": "流程完成", "failed_stage_no_quality_retry": "阶段失败，未按质量重跑",
    "prepared_not_sent": "仅准备，未发送", "running": "运行中",
    "stopped_global": "全局停止", "not_attempted_global_stop": "全局停止后未尝试",
    "completed_with_case_failures": "运行结束，含样本阶段失败",
}
OUTCOME = {
    "new_explanation": "补充新解释", "refined_existing": "细化已有解释",
    "already_covered": "模型认为已有链覆盖", "unresolved": "未解决／证据不足",
}
FOCUS = {"observations": "观察依据", "rule_conditions": "规则适用条件", "coverage": "解释覆盖"}
RELATION = {"compatible": "相容解释", "competing": "竞争解释", "support_gap": "支持缺口"}
KIND = {"supports_action": "条件性支持行动", "challenges_support": "质疑支持是否充分",
        "underdetermined": "无法确定"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def esc(value):
    """Escape data, including values that resemble Markdown/HTML."""
    if value is None:
        return "未给出（null）"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return html.escape(str(value), quote=True)


def paragraph(value, css=""):
    return '<p' + (' class="' + css + '"' if css else '') + '>' + esc(value) + '</p>'


def badge(value):
    # Classes come from this allowlist, never model strings.
    css = "ok" if value in {"supported", "active", "completed"} else (
        "bad" if value in {"refuted", "revoked"} else "pending")
    return '<span class="badge ' + css + '">' + esc(STATUS.get(value, value)) + '</span>'


def json_block(label, value):
    return ('\n<div class="raw-record">\n<details><summary>' + esc(label)
            + '</summary><pre><code>' + esc(json.dumps(value, ensure_ascii=False, indent=2))
            + '</code></pre></details>\n</div>\n')


def note_block(value):
    if value is None:
        return ('<div class="zh-note missing"><strong>中文阅读说明</strong>'
                '<p>中文解释尚未补充；以下保留真实英文记录，未自动补写模型判断。</p></div>')
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError("Chinese notes must be a string or list of strings")
    return ('<div class="zh-note"><strong>中文阅读说明（Codex 离线中文整理，非人工确认；不是额外 API 模型输出）</strong>'
            + ''.join(paragraph(x) for x in value) + '</div>')


def evidence(items):
    if not items:
        return '<p class="muted">没有记录此类证据。</p>'
    lines = []
    for item in items:
        source = item.get("ref")
        location = item.get("location", item.get("path", "未记录位置"))
        lines.append('<li><span class="evidence-source">' + esc(source) + ' · ' + esc(location)
                     + '</span><div>' + esc(item.get("content")) + '</div></li>')
    return '<ul class="evidence">' + ''.join(lines) + '</ul>'


def chain_card(chain, rules):
    rule = next((r for r in rules if r.get("id") == chain.get("rule_id")), None)
    pieces = ['<article class="chain-card"><h4>解释链 ' + esc(chain.get("chain_id")) + '</h4>']
    if "relationship" in chain:
        pieces.append(paragraph(RELATION.get(chain["relationship"], chain["relationship"])))
    pieces.append('<dl class="obc"><dt>观察 O：原始可见事实</dt><dd>'
                  + evidence(chain.get("observations", [])) + '</dd>')
    if chain.get("task_evidence"):
        pieces.append('<dt>公开任务证据（不是图像观察）</dt><dd>'
                      + evidence(chain["task_evidence"]) + '</dd>')
    pieces.append('<dt>解释规则 B · ' + esc(chain.get("rule_id")) + '</dt><dd>')
    if rule is None:
        pieces.append(paragraph("未在工件中找到引用规则；不能补写规则。", "warning"))
    else:
        pieces.extend([paragraph(rule.get("text")), '<strong>规则范围／条件</strong>',
                       paragraph(rule.get("conditions")), '<strong>图表或任务关系</strong>',
                       paragraph(rule.get("component"))])
    pieces.append('</dd><dt>结论 C</dt><dd>' + paragraph(chain.get("claim"))
                  + paragraph(KIND.get(chain.get("claim_kind"), chain.get("claim_kind", "未标注结论类型")))
                  + '<strong>条件性对应选项</strong>' + paragraph(chain.get("option_label")) + '</dd></dl>')
    if chain.get("question_ids"):
        pieces.append(paragraph("关联反问：" + ', '.join(chain["question_ids"])))
    pieces.append(json_block("这条链的完整原始记录", chain))
    pieces.append('</article>')
    return ''.join(pieces)


def refinement_card(refinement):
    return ('<article class="chain-card"><h4>细化记录 ' + esc(refinement.get("id")) + '</h4>'
            + paragraph("目标已有链：" + str(refinement.get("target_chain_id")))
            + paragraph("关联反问：" + ', '.join(refinement.get("question_ids", [])))
            + '<strong>增加的图像观察</strong>' + evidence(refinement.get("added_observations", []))
            + '<strong>增加的公开任务证据</strong>' + evidence(refinement.get("added_task_evidence", []))
            + '<strong>条件说明</strong>' + paragraph(refinement.get("condition_note"))
            + '<strong>为何需要补充（生成模型的判断）</strong>' + paragraph(refinement.get("reason"))
            + json_block("细化的完整原始记录", refinement) + '</article>')


def verification_card(check):
    parts = ['<article class="check-card"><h4>核验对象 ' + esc(check.get("target_id")) + '</h4>']
    for dimension, label in (("O", "观察及绑定"), ("B", "规则在当前条件下的适用性"),
                             ("implication", "是否足以支持结论／细化")):
        record = check.get(dimension, {})
        parts.append('<section class="dimension"><h5>' + label + ' · ' + dimension + '</h5>'
                     + badge(record.get("status", "未记录")) + paragraph(record.get("reason"))
                     + evidence(record.get("evidence", [])) + '</section>')
    parts.append(json_block("该对象的完整核验记录", check))
    return ''.join(parts) + '</article>'


def rule_state_section(state):
    if state is None:
        return paragraph("没有生成持久化规则文件；不能推断为规则被否定或核验通过。", "warning")
    parts = [paragraph("以下状态来自模型对解释规则 B 的核验汇总；active 不表示观察和结论均成立，也不授权执行行动。", "warning")]
    for record in state.get("rules", []):
        rule = record.get("rule", {})
        parts.append('<article class="rule-card"><h4>规则 ' + esc(record.get("rule_id"))
                     + ' · 版本 ' + esc(record.get("version")) + '</h4>'
                     + badge(record.get("status", "未记录")) + paragraph(rule.get("text"))
                     + '<strong>适用范围与条件</strong>' + json_block("完整规则范围", record.get("scope"))
                     + paragraph("关联链：" + ', '.join(record.get("chain_ids", [])))
                     + json_block("该规则、核验依据及版本历史", record) + '</article>')
    for record in state.get("refinements", []):
        refinement = record.get("record", {})
        parts.append('<article class="rule-card"><h4>保存的细化 ' + esc(refinement.get("id"))
                     + '</h4>' + badge(record.get("status", "未记录"))
                     + paragraph("是否修改原始规则：" + str(record.get("applied_to_original")))
                     + json_block("细化状态与核验依据", record) + '</article>')
    parts.append(json_block("完整规则状态文件 rule_state.json", state))
    return ''.join(parts)


def case_markdown(case, notes):
    cid = case["task_id"]
    inputs, result = case["inputs"], case["result"]
    base = inputs["base_arguments"]
    task = inputs["task"]
    supplement = result.get("supplement")
    combined = result.get("combined")
    questions = result.get("questions")
    verification = result.get("verification")
    parts = ['## ' + cid + ' · 解释集合补齐\n',
             '<div class="case-overview">' + badge(result.get("status", "未记录"))
             + paragraph("初始解释链：" + str(len(base.get("chains", []))))
             + paragraph("本轮请求尝试：" + str(result.get("request_attempts", "未记录"))) + '</div>',
             note_block(notes.get("summary")),
             '### ' + cid + ' · 任务与原图\n',
             '<div class="task-card"><strong>原公开页面标题</strong>' + paragraph(task.get("page_title"))
             + '<strong>原公开用户目标</strong>' + paragraph(task.get("user_goal"))
             + '<strong>原公开图表说明</strong>' + paragraph(task.get("chart_reference"))
             + '<strong>原公开行动选项（不代表本轮已执行）</strong>'
             + '<ul>' + ''.join('<li>' + esc(x) + '</li>' for x in task.get("option_labels", [])) + '</ul>'
             + json_block("完整公开任务输入", task) + '</div>',
             '<figure><img src="EMBED_CHART_' + cid + '" alt="' + cid + ' 原始任务图表" />'
             + '<figcaption>本轮模型看到的完整原图；仅原封嵌入，没有裁剪、重绘或翻译替换。</figcaption></figure>',
             '### ' + cid + ' · 1 初始全部解释\n', note_block(notes.get("initial")),
             '<div class="chains">\n' + '\n'.join(chain_card(c, base.get("rules", [])) for c in base.get("chains", [])) + '\n</div>',
             json_block("完整初始集合（所有链和规则，未按选项过滤）", base),
             '### ' + cid + ' · 2 反问检查遗漏\n', note_block(notes.get("questions"))]
    if questions is None:
        parts.append(paragraph("没有通过接口校验的反问记录；请查看阶段回执。"))
    else:
        parts.append('<div>' + paragraph(questions.get("summary")) + '</div>')
        for q in questions.get("questions", []):
            parts.append('<article class="question"><h4>' + esc(q.get("id")) + ' · '
                         + esc(FOCUS.get(q.get("focus"), q.get("focus"))) + '</h4>'
                         + paragraph(q.get("question"))
                         + paragraph("针对已有链：" + ', '.join(q.get("target_chain_ids", []))) + '</article>')
        if not questions.get("questions"):
            parts.append(paragraph("本轮生成了 0 个反问；这不自动证明解释已经完备。"))
        parts.append(json_block("反问的完整原始输出", questions))
    parts.extend(['### ' + cid + ' · 3 补齐／已有覆盖／未解决\n', note_block(notes.get("supplement"))])
    if supplement is None:
        parts.append(paragraph("没有通过接口校验的补齐结果；不能将其视为零新增成功。"))
    else:
        parts.append('<div class="callout callout-info"><p>新增 0 条并不是失败；“已有覆盖”也是模型判断，不是完备性证明。</p></div>')
        rules = (combined or {}).get("rules", base.get("rules", []) + supplement.get("new_rules", []))
        parts.append('<div>\n<h4>实际新增解释：' + str(len(supplement.get("new_chains", []))) + ' 条</h4>\n'
                     + '\n'.join(chain_card(c, rules) for c in supplement.get("new_chains", [])) + '\n</div>')
        parts.append('<div>\n<h4>已有解释的独立细化：' + str(len(supplement.get("refinements", []))) + ' 条</h4>\n'
                     + '\n'.join(refinement_card(r) for r in supplement.get("refinements", [])) + '\n</div>')
        for response in supplement.get("question_responses", []):
            parts.append('<article class="disposition"><h4>' + esc(response.get("question_id")) + ' → '
                         + esc(OUTCOME.get(response.get("outcome"), response.get("outcome"))) + '</h4>'
                         + paragraph(response.get("reason"))
                         + paragraph("补充记录：" + ', '.join(response.get("record_ids", [])))
                         + paragraph("已覆盖链：" + ', '.join(response.get("covered_chain_ids", []))) + '</article>')
        parts.append(json_block("补齐的完整原始输出", supplement))
    parts.extend(['### ' + cid + ' · 4 逐维核验\n', note_block(notes.get("verification"))])
    if verification is None:
        parts.append(paragraph("没有通过接口校验的核验输出；不得称为已执行核验通过。"))
    else:
        parts.append('<div>' + paragraph(verification.get("summary")) + '</div>')
        parts.extend(verification_card(check) for check in verification.get("checks", []))
        parts.append(json_block("核验的完整原始输出", verification))
    parts.extend(['### ' + cid + ' · 5 持久化规则状态\n', note_block(notes.get("rule_state")),
                  '<div>' + rule_state_section(case.get("rule_state")) + '</div>',
                  json_block("状态重新读取的回执（不是 actor 使用证明）", case.get("state_reload_check")),
                  '### ' + cid + ' · 6 阶段回执与原始记录\n',
                  json_block("阶段、失败与成本记录", {k: result.get(k) for k in
                      ("status", "stages", "failure", "request_attempts", "estimated_ledger_usd", "browser_operations")}),
                  json_block("此样本的完整输入和结果", case)])
    return '\n\n'.join(parts)


def load_bundle(run, notes_path):
    run = Path(run).resolve()
    summary_path = run / "summary.json"
    summary = read(summary_path)
    if [x["task_id"] for x in summary.get("cases", [])] != list(CASE_IDS):
        raise ValueError("Expected the fixed three-case panel in manifest order")
    source_paths = [summary_path]
    cases = []
    for cid in CASE_IDS:
        folder = run / "cases" / cid
        inputs_path, result_path = folder / "inputs.json", folder / "result.json"
        inputs, result = read(inputs_path), read(result_path)
        if result.get("task_id") != cid:
            raise ValueError("Result case identity mismatch")
        chart = folder / "chart.jpeg"
        chart_bytes = chart.read_bytes()
        if not chart_bytes.startswith(b"\xff\xd8\xff"):
            raise ValueError("Expected original JPEG bytes, not a converted or external image")
        sources = inputs.get("source_sha256", {})
        source_chart = inputs.get("chart_source")
        if sources.get(source_chart) != digest(chart):
            raise ValueError("Run image differs from the frozen original source hash")
        state_path = folder / "rule_state.json"
        state = read(state_path) if state_path.exists() else None
        if result.get("rule_state") != state:
            raise ValueError("Rule-state file differs from the saved result; do not hide drift")
        reload_path = folder / "state_reload_check.json"
        reload_check = read(reload_path) if reload_path.exists() else None
        cases.append({"task_id": cid, "inputs": inputs, "result": result,
                      "rule_state": state, "state_reload_check": reload_check,
                      "chart_sha256": digest(chart), "chart_source": str(chart)})
        source_paths.extend([inputs_path, result_path, chart])
        source_paths.extend(p for p in (state_path, reload_path) if p.exists())
    notes_path = Path(notes_path).resolve()
    notes = read(notes_path) if notes_path.exists() else {}
    if not isinstance(notes, dict) or not isinstance(notes.get("cases", {}), dict):
        raise ValueError("notes_zh.json must contain an object with an optional cases mapping")
    if notes_path.exists():
        source_paths.append(notes_path)
    extra = {}
    for filename in ("runtime.json", "budget.json", "prompt_templates.json", "initial_set_audit.json"):
        path = run / filename
        if path.exists():
            extra[filename] = read(path)
            source_paths.append(path)
    return {"schema_version": "explanation_completion_delivery_v1", "summary": summary, "cases": cases,
            "notes_zh": notes, "notes_status": "provided" if notes_path.exists() else "not_provided",
            "metadata": extra, "source_sha256": {str(p): digest(p) for p in source_paths},
            "limits": "Offline presentation only; source/model judgments remain fallible. No browser submission or actor rule-use test."}


def source_markdown(bundle):
    summary, notes = bundle["summary"], bundle["notes_zh"]
    parts = ['# 解释集合补齐 · 三例真实验证\n',
             '> ⚠️ **范围说明：** 本展示检验“保留初始全部解释 → 反问补齐 → 核验 → 保存规则”的工程流程。新增链数量不是成功指标；结构通过不等于语义正确或解释完备。没有执行网页提交，也没有运行后续 actor 检查持久规则的实际使用。\n',
             '<div class="flow">初始全部解释 → 反问检查遗漏 → 新解释／细化／已有覆盖／未解决 → 逐维核验 → 规则文件</div>',
             '## 运行概览\n', note_block(notes.get("overview")),
             '<div class="summary-grid"><div><strong>请求尝试</strong>'
             + paragraph(summary.get("request_attempts")) + '</div><div><strong>估算账本（美元）</strong>'
             + paragraph(summary.get("estimated_ledger_usd")) + '</div><div><strong>整体状态</strong>'
             + badge(summary.get("status", "未记录")) + '</div></div>',
             '<div class="callout callout-warn"><p>估算账本不是实际账单。中文解释为 Codex 离线中文整理，非人工确认；真实模型输出以英文原始 JSON 为准。初始链来自已存在的生成记录，本轮不是从零独立生成的全部成本。</p></div>',
             json_block("完整运行汇总", summary)]
    for case in bundle["cases"]:
        parts.append(case_markdown(case, notes.get("cases", {}).get(case["task_id"], {})))
    parts.extend(['## 文件来源与完整数据\n',
                  '<div class="callout callout-info"><p>本页是 JSON 工件的派生视图。源文件路径、SHA256 与生成时间记录在页眉及页面元信息中；下方记录各输入的指纹。独立 HTML 自带原图和全部数据，不依赖本地项目目录或网络。</p></div>',
                  json_block("所有输入来源与 SHA256", bundle["source_sha256"]),
                  json_block("全部工件汇总（RESULTS_FULL.json 的完整内容）", bundle)])
    return '\n\n'.join(parts) + '\n'


EXTRA_CSS = """<style>
.layout{grid-template-columns:250px minmax(0,1fr)}
main{min-width:0;overflow-wrap:anywhere}main h1{font-size:30px}
main img{display:block;max-width:100%;height:auto;margin:1em auto}
main pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:36em;overflow:auto}
main code,main td,main th{overflow-wrap:anywhere;word-break:break-word}
main table{width:100%;table-layout:fixed}main h4{font-size:18px;margin:.4em 0 .7em}
main h5{font-size:16px;margin:.3em 0}.chain-card,.rule-card,.check-card,.question,.disposition,.task-card{padding:18px 22px;border:1px solid #d8d4c9;border-radius:6px;margin:18px 0;background:#fffefa}
.obc{margin:0}.obc dt{font-weight:700;border-top:1px solid #e9e5dc;padding-top:12px;margin-top:12px}.obc dd{margin:6px 0 0}
.evidence li{margin:10px 0}.evidence-source{font-size:13px;color:#625d54;display:block}
.zh-note{background:#edf4f1;border-left:4px solid #567d70;padding:14px 20px;margin:18px 0}.zh-note p{margin:8px 0}.zh-note.missing{background:#f6f3ec;border-color:#b69c69}
.badge{display:inline-block;font-size:13px;padding:4px 9px;border-radius:4px;background:#eee}.badge.ok{background:#e6efe9;color:#305b40}.badge.bad{background:#f4e5df;color:#823923}.badge.pending{background:#f5ecd5;color:#715717}
.dimension{margin:14px 0;padding:12px;border-left:3px solid #ccc}.summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.summary-grid>div{border-top:2px solid #666;padding:14px;background:#f8f6ef}.summary-grid p{font-size:21px}
.flow{font-size:17px;line-height:1.9;padding:14px;background:#f2efe7}.muted,figcaption{font-size:13px;color:#6b655b}.warning{background:#fff3d7;padding:12px}.raw-record details{margin:14px 0}.case-overview{padding:12px 0}
@media(max-width:900px){.layout{grid-template-columns:minmax(0,1fr)}.summary-grid{grid-template-columns:1fr}.chain-card,.rule-card,.check-card{padding:13px}}
@media print{main pre{max-height:none}.chain-card,.rule-card,.question{break-inside:avoid}.layout{display:block}}
</style>"""


def render(run, output_dir=None, notes_path=None):
    output_dir = Path(output_dir or HERE).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = load_bundle(run, notes_path or HERE / "notes_zh.json")
    result_path = output_dir / "RESULTS_FULL.json"
    source_path = output_dir / "REVIEW_SOURCE.md"
    target = output_dir / "EXPLANATION_COMPLETION_REVIEW.html"
    provenance_path = output_dir / "VIEW_PROVENANCE.json"
    for path in (result_path, source_path, target, provenance_path):
        if path.exists():
            raise FileExistsError("Do not overwrite a delivered view; choose a new --output-dir: " + str(path))
    dump_new(result_path, bundle)
    # Match the helper's UTF-8/LF source hash on Windows as well as POSIX.
    with source_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(source_markdown(bundle))
    helper = PROJECT / ".agents/skills/render-html/scripts/render_html.py"
    spec = importlib.util.spec_from_file_location("completion_render_helper", helper)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if module.main([str(source_path), "--out", str(target), "--offline", "--title", "解释集合补齐 · 三例完整记录",
                    "--eyebrow", "保留全部解释 · 补齐而非强造冲突"]):
        raise RuntimeError("HTML helper failed")
    page = target.read_text(encoding="utf-8")
    embedded = []
    for case in bundle["cases"]:
        marker = 'src="EMBED_CHART_' + case["task_id"] + '"'
        if page.count(marker) != 1:
            raise ValueError("Expected exactly one original chart for " + case["task_id"])
        chart = Path(case["chart_source"])
        page = page.replace(marker, 'src="data:image/jpeg;base64,' + base64.b64encode(chart.read_bytes()).decode("ascii") + '"')
        embedded.append({"task_id": case["task_id"], "source": str(chart), "sha256": digest(chart)})
    extra_meta = ('<meta name="canonical-results-path" content="' + esc(str(result_path)) + '" />\n'
                  + '<meta name="canonical-results-sha256" content="' + digest(result_path) + '" />\n')
    page = page.replace('</head>', extra_meta + EXTRA_CSS + '\n</head>')
    target.write_text(page, encoding="utf-8")
    provenance = {"created_at": datetime.now(timezone.utc).isoformat(), "source": str(source_path),
                  "source_sha256": digest(source_path), "result_source": str(result_path),
                  "result_sha256": digest(result_path), "html": str(target), "html_sha256": digest(target),
                  "renderer": str(helper), "renderer_sha256": digest(helper),
                  "delivery_code_sha256": digest(__file__), "embedded_original_images": embedded,
                  "notes_status": bundle["notes_status"], "offline": True, "model_calls": 0,
                  "review_status": "not_performed_by_renderer",
                  "limits": "Rendering does not certify semantic correctness or completeness."}
    dump_new(provenance_path, provenance)
    print(json.dumps({"html": str(target), "embedded_images": len(embedded), "model_calls": 0}, ensure_ascii=False))
    return provenance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["render"])
    parser.add_argument("--run", type=Path, default=HERE / "run")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--notes", type=Path, default=HERE / "notes_zh.json")
    args = parser.parse_args()
    render(args.run, args.output_dir, args.notes)
