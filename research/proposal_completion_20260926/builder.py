"""Offline proposal-preserving review; no service connection or inferred records.

Build-time dependency: ../alternative_conclusion_20260926/build_review.py for
HTML escaping, image collection, and OBC rendering. Produced HTML is standalone.
"""

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / "alternative_conclusion_20260926" / "build_review.py"
spec = importlib.util.spec_from_file_location("proposal_offline_review_helpers", HELPER)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

CASES = {
    "pub001_misleading": "州风险任务：误导图",
    "pub001_normal": "州风险任务：正常图",
    "b002": "浏览器优先测试任务",
    "pub013": "州风险地图详情任务",
}


def obj(value):
    return value if isinstance(value, dict) else {}


def accepted(call):
    return obj(obj(call).get("records")).get("accepted.json")


def collect(run):
    collector = ui.Collector(run)
    collector.read_pngs()
    files = {}
    for path in sorted(Path(run).rglob("*.json")):
        if "runtime_source" not in path.relative_to(run).parts:
            files[path.relative_to(run).as_posix()] = collector.load(path)
    cases = {}
    for case in CASES:
        folder = Path(run) / case
        cases[case] = {
            "result": files.get(case + "/result.json"),
            "context": files.get(case + "/context.json"),
            "initial": files.get(case + "/initial.json"),
            "image_sha256": ui.sha((folder / "chart.png").read_bytes()) if (folder / "chart.png").exists() else None,
            "calls": {stage.name: collector.call(stage) for stage in sorted(folder.iterdir())
                      if stage.is_dir() and stage.name in ("propose", "expand_00", "expand_01", "verify")}
                     if folder.is_dir() else {},
            "files": {name: value for name, value in files.items() if name.startswith(case + "/")},
        }
    return {"summary": files.get("summary.json"), "config": files.get("config.json"),
            "ledger": files.get("ledger.json"), "cases": cases, "files": files,
            "read_issues": collector.issues}, collector


def original_proposals(case):
    proposals = obj(case.get("result")).get("proposals")
    if proposals is None:
        proposals = accepted(obj(case.get("calls")).get("propose"))
    return proposals


def counts(case):
    result = obj(case.get("result"))
    proposals = original_proposals(case)
    count = len(proposals["proposals"]) if isinstance(proposals, dict) and isinstance(proposals.get("proposals"), list) else None
    expansions = result.get("expansions", [])
    return {
        "proposals": count,
        "expanded": sum(item.get("status") == "accepted" and obj(item.get("data")).get("outcome") == "expanded" for item in expansions),
        "unexpanded": sum(item.get("status") == "accepted" and obj(item.get("data")).get("outcome") == "unexpanded" for item in expansions),
        "interface_failed": sum(item.get("status") == "interface_failed_no_retry" for item in expansions),
        "not_recorded": max(0, count - len(expansions)) if count is not None else None,
    }


def proposal_note(note):
    note = obj(note)
    if not note:
        return ""
    parts = ['<aside class="translation"><strong>Codex 离线中文翻译／分析：不是模型原文，也不是独立人工确认。</strong>']
    for field, title in (("candidate", "候选结论"), ("visual_cues", "待查看视觉线索"),
                         ("reading_to_try", "待尝试读法"), ("assumptions", "假设"), ("assessment", "分析备注")):
        value = note.get(field)
        if value is None:
            continue
        parts.append('<h5>' + title + '</h5>')
        parts.append('<ul>' + ''.join('<li>' + ui.escaped(item) + '</li>' for item in value) + '</ul>'
                     if isinstance(value, list) else '<p>' + ui.escaped(value) + '</p>')
    return ''.join(parts) + '</aside>'


def proposal_html(proposal, index, case, note):
    result = obj(case.get("result"))
    expansions = result.get("expansions", [])
    expansion = expansions[index] if index < len(expansions) else None
    call = obj(case.get("calls")).get("expand_%02d" % index)
    candidates = obj(result.get("candidate_set"))
    link = next((item for item in candidates.get("proposal_links", []) if item.get("proposal_id") == proposal.get("id")), None)
    parts = ['<article class="proposal"><h4>原始提案 ' + ui.escaped(proposal.get("id")) + '</h4>',
             '<p>这是一条探索提案，不是完整 OBC，也不是已经核实的视觉事实。</p>',
             '<h5>可能结论 candidate（模型原文）</h5>', ui.pretty(proposal.get("candidate")),
             '<h5>待查看视觉线索 visual_cues（不是已核验 O）</h5>',
             '<ul>' + ''.join('<li>' + ui.escaped(value) + '</li>' for value in proposal.get("visual_cues", [])) + '</ul>',
             '<h5>待尝试读法 reading_to_try</h5><p>' + ui.escaped(proposal.get("reading_to_try", "未记录")) + '</p>',
             '<h5>显式假设 assumptions</h5><ul>' + ''.join('<li>' + ui.escaped(value) + '</li>' for value in proposal.get("assumptions", [])) + '</ul>',
             proposal_note(obj(note.get("proposals")).get(proposal.get("id"))),
             '<h4>对应提案的实际展开</h4>']
    if expansion is None:
        if call:
            parts.append('<p class="missing">存在展开调用工件，但 case 结果未记录完成；不能推测展开成功或未展开。原始调用保留如下。</p>')
        else:
            parts.append('<p class="missing">未运行／没有展开调用记录；原提案仍保留，不算核验失败。</p>')
    elif expansion.get("status") == "interface_failed_no_retry":
        parts.append('<p class="missing">展开接口失败，没有质量重试；原提案和原响应保留，不改写成完整链。</p>' + ui.pretty(expansion.get("error")))
    else:
        data = obj(expansion.get("data"))
        if data.get("outcome") == "unexpanded":
            parts.append('<p>模型明确返回 unexpanded：未展开。它仍是一条保留的提案，不是被丢弃、不是完整链核验失败。</p>')
        elif data.get("outcome") == "expanded":
            parts.append('<p>模型返回 expanded：形成了结构链；是否忠实于提案和是否有依据仍需分别审阅。</p>')
        else:
            parts.append('<p class="missing">展开状态未识别，保留原记录。</p>')
        parts.append('<h5>展开 reason 原文（不从其中补写链）</h5><p>' + ui.escaped(data.get("reason", "未记录")) + '</p>')
        linked = [chain for chain in candidates.get("chains", []) if chain.get("id") in obj(link).get("chain_ids", [])]
        if linked:
            parts.append(ui.chains_html(linked, note.get("expanded_chains")))
        elif data.get("chains"):
            parts.append('<p>下列为展开阶段原始链，尚未找到完整聚合关联记录。</p>' + ui.chains_html(data["chains"], {}))
        else:
            parts.append('<p>实际链数组为空；不把 reason 当作已生成 OBC。</p>')
    if link:
        signals = {key: link.get(key, "不适用／未记录") for key in
                   ("proposal_id", "expansion_status", "outcome", "chain_ids", "same_action_label", "same_claim_text")}
        parts.append('<h5>提案—展开审计关联与字面匹配信号</h5>' + ui.pretty(signals))
        parts.append('<p>same_action_label 只比较公开选项字符串，same_claim_text 只比较结论原文字面相等；不是语义一致／忠实性的裁决。不匹配的结构合法链也保留并核验，不按结果过滤。</p>')
    else:
        parts.append('<p>没有已聚合 proposal_link；不能自行补造提案与链的关系。</p>')
    if call:
        parts.append(ui.call_html(call, "展开阶段完整请求／响应（含未接纳内容）"))
    return ''.join(parts) + '</article>'


def render(bundle, images, annotations):
    summary, config, ledger = obj(bundle.get("summary")), obj(bundle.get("config")), obj(bundle.get("ledger"))
    annotations = obj(annotations)
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>反问提案保留与解释链展开审阅</title><style>',
             'body{max-width:1320px;margin:auto;padding:24px;font:16px/1.65 system-ui,sans-serif;background:#f2f5f8;color:#213247}h1,h2,h3,h4,h5{line-height:1.4}h2{margin-top:40px;border-top:3px solid #3a607f;padding-top:18px}.notice,.translation{padding:14px;background:#e5edf8;border-left:4px solid #315c88;margin:16px 0}.missing{color:#a12828;font-weight:600}.proposal,.chain,figure{background:white;border:1px solid #d4dde5;padding:16px;margin:14px 0;border-radius:7px}.conclusion{background:#edf5e8;padding:12px}table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:14px;background:white}td,th{border:1px solid #ccd7e2;padding:9px;vertical-align:top;overflow-wrap:anywhere}th{background:#e2ebf4}pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font:13px/1.5 Consolas,monospace;background:#f5f7fa;padding:12px}summary{cursor:pointer;color:#2d557c}details{margin:10px 0}img{max-width:100%;height:auto}a{color:#285d8c;overflow-wrap:anywhere}nav a{display:inline-block;margin:4px 18px 4px 0}figcaption{font-size:13px;overflow-wrap:anywhere}@media(max-width:700px){body{padding:12px}table{font-size:11px}td,th{padding:5px}}</style></head><body>',
             '<h1>反问先保留提案，再展开 OBC</h1>',
             '<div class="notice"><strong>纯候选验证，没有执行纠错。</strong>本页没有 Actor、业务提交或新的自然前缀；四个固定输入都是开发样本，不是独立留出测试。展示原提案、展开结果和后续核验，不以最终选项成功率包装生成效果。</div>',
             '<p>本轮为精简提示＋提案保留接口的组合开发验证，不能归因某一句提示。原图不变；正常图原有 Clean／true value 页脚仍可见。结构通过不等于读图正确，不同 C 不等于有据竞争链，模型 notes／reason 不会由展示器补写成链。</p>',
             '<nav><a href="#summary">结果总览</a>' + ''.join('<a href="#' + case + '">' + title + '</a>' for case, title in CASES.items()) + '<a href="#images">完整原图</a></nav>',
             ui.notes_html(annotations), '<h2 id="summary">真实提案—展开—核验记录</h2>',
             '<p>请求模型：' + ui.escaped(config.get("model", "未记录")) + '；运行状态：' + ui.escaped(summary.get("status", "未记录")) +
             '；请求尝试：' + ui.escaped(ledger.get("request_attempts", summary.get("request_attempts", "未记录"))) +
             '；浏览器操作：' + ui.escaped(ledger.get("browser_operations", summary.get("browser_operations", "未记录"))) + '。</p>']
    if summary.get("error"):
        parts.append('<p class="missing">实际运行中止：</p>' + ui.pretty(summary["error"]))
    rows = []
    for name, case in bundle["cases"].items():
        result, measured = obj(case.get("result")), counts(case)
        verification = result.get("verification")
        vstatus = "已执行且结构接纳（不是人工确认）" if verification is not None else (
            "未执行：没有完整链" if result.get("verification_status") == "not_run_no_complete_chains" else
            "有核验工件但未记录接纳结果" if obj(case.get("calls")).get("verify") else "未运行／未记录")
        rows.append('<tr><td><a href="#' + name + '">' + CASES[name] + '</a></td><td>' +
                    ui.escaped(measured["proposals"] if measured["proposals"] is not None else "未接纳／未运行") +
                    '</td><td>' + str(measured["expanded"]) + '</td><td>' + str(measured["unexpanded"]) +
                    '</td><td>' + str(measured["interface_failed"]) + '</td><td>' +
                    ui.escaped(measured["not_recorded"] if measured["not_recorded"] is not None else "不适用") +
                    '</td><td>' + ui.escaped(vstatus) + '<br>' + ui.escaped(result.get("status", "没有 case 结果")) + '</td></tr>')
    parts.append('<table><thead><tr><th>输入</th><th>保留提案</th><th>明确展开</th><th>明确未展开</th><th>展开接口失败</th><th>未记录展开</th><th>核验／运行状态</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')
    for name, case in bundle["cases"].items():
        note = obj(obj(annotations.get("cases")).get(name))
        result = obj(case.get("result"))
        parts += ['<h2 id="' + name + '">' + CASES[name] + '</h2>', ui.notes_html(note),
                  '<p>' + ui.image_link(case.get("image_sha256"), "查看本例实际完整原图") + '</p>',
                  ui.details("公开任务输入（不含执行续跑）", ui.pretty(case.get("context"))),
                  '<h3>复用的原始解释链</h3>', ui.chains_html(obj(case.get("initial")).get("chains"), note.get("initial_chains")),
                  '<h5>原始 notes</h5><p>' + ui.escaped(obj(case.get("initial")).get("notes", "未记录")) + '</p>']
        proposals = original_proposals(case)
        parts.append('<h3>反问后的原始探索提案</h3>')
        if proposals is None:
            parts.append('<p class="missing">没有结构接纳的提案输出；可能未调用或接口失败，以完整请求响应为准。不能写成模型提出零条。</p>')
        else:
            parts.append('<h5>提案阶段 notes 原文</h5><p>' + ui.escaped(proposals.get("notes", "未记录")) + '</p>')
            if not proposals.get("proposals"):
                parts.append('<p>模型实际返回零提案，不是未调用；没有展开阶段是正常分支。</p>')
            for index, proposal in enumerate(proposals.get("proposals", [])):
                parts.append(proposal_html(proposal, index, case, note))
        parts.append(ui.call_html(obj(case.get("calls")).get("propose"), "提案阶段完整提示／输入／响应"))
        if result.get("error"):
            parts.append('<p class="missing">本例实际接口／流程错误</p>' + ui.pretty(result["error"]))
        parts.append('<h3>全部完整链的独立请求核验</h3>')
        if result.get("verification_status") == "not_run_no_complete_chains":
            parts.append('<p>没有完整链，按协议不执行核验；这不是已执行核验失败。</p>')
        else:
            parts.append(ui.verification_html(result.get("verification")))
        if obj(case.get("calls")).get("verify"):
            parts.append(ui.call_html(case["calls"]["verify"], "核验完整请求／响应"))
        parts.append(ui.details("完整候选集合与所有提案关联（含未展开／失败）", ui.pretty(result.get("candidate_set"))))
        parts.append('<p class="notice">本例没有 Actor、实际改选或业务提交。核验只检查候选，不代表任务纠错或持久化规则已经生效。</p>')
        parts.append(ui.details("本例全部真实 JSON 工件（失败草稿同样保留）",
                                ''.join(ui.details(path, ui.pretty(value)) for path, value in case["files"].items())))
    parts.append('<h2 id="images">完整输入图像</h2><p>每个相同字节图像仅内嵌一次；请求中的大段图像数据用 SHA-256 引用展示，原工件不修改。</p>')
    for digest, item in images.items():
        parts.append('<figure id="image-' + digest + '"><figcaption>SHA-256 ' + digest + '<br>' +
                     '<br>'.join(ui.escaped(source) for source in item["sources"]) + '</figcaption><img loading="lazy" alt="完整输入图表" src="data:' + item["mime"] + ';base64,' + item["data"] + '"></figure>')
    parts += ['<h2>配置、成本与来源</h2>', ui.details("冻结配置与运行汇总", ui.pretty({"config": bundle.get("config"), "summary": bundle.get("summary")})),
              ui.details("所有请求成本账本", ui.pretty(bundle.get("ledger"))), ui.details("读取异常", ui.pretty(bundle.get("read_issues"))),
              '<p>静态单文件，无 JavaScript、CDN 或外部图片依赖；展示器未调用模型。中文注释为离线翻译／分析，不伪装成模型输出或独立人工确认。</p></body></html>']
    return ''.join(parts)


def build(run, output, annotations=None):
    run, output = Path(run).resolve(), Path(output).resolve()
    if not run.is_dir():
        raise NotADirectoryError(str(run))
    if output.exists():
        raise FileExistsError("Do not overwrite review: " + str(output))
    if run == output or run in output.parents:
        raise ValueError("Review must be outside the immutable run directory")
    bundle, collector = collect(run)
    notes = json.loads(Path(annotations).read_text(encoding="utf-8-sig")) if annotations else {}
    document = render(bundle, collector.images, notes)
    output.mkdir(parents=True, exist_ok=False)
    page = output / "PROPOSAL_COMPLETION_REVIEW.html"
    page.write_text(document, encoding="utf-8")
    bundle["images"] = {digest: {key: value for key, value in item.items() if key != "data"} for digest, item in collector.images.items()}
    (output / "RESULTS_FULL.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    provenance = {"source_run": str(run), "inputs": collector.files, "builder_sha256": ui.sha(Path(__file__).read_bytes()),
                  "helper": str(HELPER), "helper_sha256": ui.sha(HELPER.read_bytes()), "html_sha256": ui.sha(page.read_bytes()),
                  "annotation_sha256": ui.sha(Path(annotations).read_bytes()) if annotations else None, "model_calls_by_viewer": 0}
    (output / "PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    print(build(args.run, args.output, args.annotations))


if __name__ == "__main__":
    main()
