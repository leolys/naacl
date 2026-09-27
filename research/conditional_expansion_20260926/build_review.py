"""Portable Chinese review of conditional O/B/C expansion, without inference.

Rendering preserves all candidate, old/new expansion and verification records.
It does not score chains, deduplicate them, or convert commentary into chains.
"""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path


CASES = ("pub001_misleading", "pub001_normal", "b002", "pub013")
VARIANTS = ("registration", "coverage")
CASE_NAMES = {"pub001_misleading": "pub001 · 误导图", "pub001_normal": "pub001 · 正常图", "b002": "b002 · 原误导图", "pub013": "pub013 · 原误导图"}
VARIANT_NAMES = {"registration": "来源：候选登记版反问", "coverage": "来源：候选登记＋读取覆盖版反问"}


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def esc(value):
    return html.escape(str(value), quote=True)


def image_hashes(value):
    """Only image bytes are replaced. The surrounding request text is intact."""
    if isinstance(value, dict):
        return {key: image_hashes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [image_hashes(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        header, separator, encoded = value.partition(",")
        if separator and ";base64" in header:
            try:
                blob = base64.b64decode(encoded, validate=True)
                return "[内嵌图像 %s；sha256=%s；bytes=%d；与本页图像 hash 对照]" % (header[5:].split(";")[0], sha(blob), len(blob))
            except ValueError:
                return "[无法解码的内嵌图像；原字符串 sha256=%s]" % sha(value.encode("utf-8"))
    return value


def raw(title, value, opened=False):
    return '<details%s><summary>%s</summary><pre>%s</pre></details>' % (" open" if opened else "", esc(title), esc(json.dumps(image_hashes(value), ensure_ascii=False, indent=2)))


def paragraphs(items, css=""):
    if isinstance(items, str):
        items = [items]
    return ''.join('<p%s>%s</p>' % (' class="%s"' % css if css else "", esc(item)) for item in (items or []))


def blocks(title, fields, labels, note=False):
    parts = ['<div class="%s"><h5>%s</h5>' % ("annotation" if note else "fields", esc(title))]
    for key, label in labels:
        if key in fields:
            parts.append('<b>%s</b>%s' % (esc(label), paragraphs(fields[key])))
    return ''.join(parts) + '</div>'


def record_counts(result):
    expansions = result.get("expansions") or []
    return {"expansion_records": len(expansions),
            "empty_records": sum(row.get("empty_record") is True for row in expansions),
            "adapted_records": sum(row.get("adapted_chain") is not None for row in expansions)}


def status_zh(status):
    return {
        "completed_candidate_diagnostic": "本单元已完成",
        "expanded_pending_verify": "展开完成，核验待执行",
        "stopped_global_budget_or_transport": "因传输或全局限制停止",
        "verification_interface_failed_no_retry": "核验接口未接受返回，未重试",
        "interface_failed_no_retry": "接口未接受返回，未重试",
        "accepted": "已接受结构化返回",
        "started": "已开始",
        "expanding": "正在展开",
        "partial": "部分完成",
        "not_run_or_missing": "未运行或档案缺失",
        "expanded": "已展开",
        "unexpanded": "未展开",
    }.get(status, "未记录或待核对（详见原始档案）")


def verification_state(result, stages):
    """Distinguish recorded completion, sent-but-unknown, and unstarted calls."""
    status = result.get("status")
    if result.get("verification") is not None:
        if status == "completed_candidate_diagnostic":
            return "已完成核验", "已保存核验返回；内容仍是模型判断，不等于人工确认。"
        return "已有返回，状态待核对", "存在核验内容，但单元状态未记为完成；请核对完整原始档案。"
    if "verify/request.json" in stages:
        if status == "verification_interface_failed_no_retry":
            return "已请求，接口未接受返回", "已执行核验请求，但返回未通过接口处理；这不等于核验判断该解释链失败。"
        return "已发送，结果未知", "核验请求已发送，但没有保存可接受的核验结果。超时或传输停止不代表核验判为失败，也不能认定服务端已完成或未完成。"
    if status == "not_run_or_missing":
        return "档案缺失，状态未知", "缺少单元和核验请求档案，不能由缺失直接推断模型核验失败。"
    return "尚未发送核验", "此单元没有核验请求记录，尚未发送核验；不能记为已执行核验失败。"


def collect(run_dir):
    summary = read_json(run_dir / "summary.json", {})
    indexed = {(row.get("variant"), row.get("case")): row for row in summary.get("results", [])}
    rows = []
    for case in CASES:
        for variant in VARIANTS:
            folder = run_dir / variant / case
            result = read_json(folder / "result.json", indexed.get((variant, case)))
            if result is None:
                result = {"case": case, "variant": variant, "status": "not_run_or_missing", "registration": None, "expansions": [], "verification": None, "submitted": False}
            stages = {}
            for child in sorted(folder.iterdir()) if folder.exists() else []:
                if child.is_dir() and (child.name.startswith("expand_") or child.name == "verify"):
                    for path in sorted(child.glob("*.json")):
                        stages[path.relative_to(folder).as_posix()] = read_json(path)
            rows.append({"case": case, "variant": variant, "folder": folder, "result": result,
                         "context": read_json(folder / "context.json"), "initial": read_json(folder / "initial.json"),
                         "registration": read_json(folder / "registration.json", result.get("registration")),
                         "previous": read_json(folder / "previous_result.json"), "stages": stages})
    return summary, rows


CSS = """
:root{color-scheme:light;--ink:#173042;--line:#cbd7df;--muted:#566b79;--soft:#eaf4f8}*{box-sizing:border-box}body{margin:0;background:#f4f7f9;color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1220px;margin:auto;padding:28px 24px 70px}h1{font-size:30px;line-height:1.4}h2{font-size:25px;margin:0 0 16px}h3{font-size:21px;margin:0 0 12px}h4{font-size:19px;margin:12px 0}h5{font-size:16px;margin:0 0 10px}p{margin:8px 0}a{color:#0b5d7b}nav{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}nav a{padding:7px 12px;background:white;border:1px solid var(--line);border-radius:7px;text-decoration:none}.panel,.variant,.candidate{border:1px solid var(--line);border-radius:12px;padding:22px;margin:20px 0;background:white}.variant{background:#fcfdfe}.candidate{padding:16px}.notice{background:#fff4d9;border-left:4px solid #b68523;padding:14px 18px}.annotation{background:var(--soft);padding:13px 16px;border-radius:8px;margin:12px 0}.fields{padding:12px 0}.muted,.label{color:var(--muted);font-size:14px}.warning{color:#9b4420}.chart{display:block;max-width:100%;height:auto;margin:16px auto;border:1px solid var(--line)}.hash{font:12px/1.5 monospace;overflow-wrap:anywhere}.stats{display:flex;gap:10px;flex-wrap:wrap}.stats span{background:var(--soft);padding:7px 12px;border-radius:7px}details{border:1px solid var(--line);border-radius:8px;overflow:hidden;margin:12px 0}summary{cursor:pointer;background:#edf2f5;padding:10px 14px;font-weight:600;overflow-wrap:anywhere}pre{margin:0;padding:14px;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.55 Consolas,ui-monospace,monospace;max-height:680px;overflow:auto}.columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}.column{min-width:0;background:#f6f9fb;border-radius:8px;padding:13px}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:9px 7px;text-align:left;border-bottom:1px solid var(--line);overflow-wrap:anywhere;vertical-align:top}th{background:#edf2f5}section{scroll-margin-top:16px}@media(max-width:700px){main{padding:18px 12px 40px}.panel,.variant{padding:14px}.candidate{padding:12px}h1{font-size:24px}h2{font-size:21px}.columns{grid-template-columns:1fr}table{min-width:760px}pre{font-size:12px}}
"""


def build(run_dir, output_dir, annotations=None):
    run_dir, output_dir = Path(run_dir), Path(output_dir)
    annotations = annotations or {}
    summary, rows = collect(run_dir)
    ledger = read_json(run_dir / "ledger.json", {})
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>条件式三字段 OBC 展开验证</title><style>', CSS, '</style></head><body><main><h1>条件式三字段 OBC 展开 · 候选逐条阅览</h1>']
    parts.append('<div class="notice">本轮复用上轮两种反问方式已经真实生成的 14 个候选，不重跑反问，不重新生成前缀，不添加普通重看对照。只检验新的展开提示与三字段接口。结构化输出不等于有效解释链，更不等于已完成纠错；所有非空展开均保留给后续核验。</div>')
    parts.append('<p>新展开只让模型返回 O（观察列表）、B（条件式解释）、C（结论）三个字段；索引和候选 ID 由程序管理。不让展开器输出拒绝理由或裁定获胜路径；错误、冲突与适用性留给后续独立核验。独立核验也可能出错，不能当成人工确认。</p>')
    parts.append('<p class="muted">计划正常请求 22 次，上限 28 次请求尝试（含失败／重试）；付费 API 与 actor 均不运行。下方账本展示实际成本，而非以预算代替实际调用数。</p>')
    parts.append(paragraphs(annotations.get("overview"), "annotation"))
    parts.append('<div class="stats">' + ''.join('<span>%s：%s</span>' % (label, esc(ledger.get(key, "未记录"))) for key, label in (("request_attempts", "实际请求尝试"), ("browser_operations", "浏览器操作"), ("paid_api_requests", "付费 API 请求"))) + '</div>')
    parts.append('<nav>' + ''.join('<a href="#%s">%s</a>' % (case, esc(CASE_NAMES[case])) for case in CASES) + '<a href="#archive">档案与成本</a></nav>')
    parts.append('<section class="panel"><h2>执行概览</h2><div class="table-scroll"><table><thead><tr><th>输入</th><th>原反问来源</th><th>复用候选数</th><th>展开记录数</th><th>空记录数</th><th>适配为 OBC 的记录数</th><th>核验</th><th>运行状态</th><th>提交</th></tr></thead><tbody>')
    for row in rows:
        result, counts = row["result"], record_counts(row["result"])
        registration = row["registration"]
        values = (CASE_NAMES[row["case"]], VARIANT_NAMES[row["variant"]], len(registration.get("candidates", [])) if isinstance(registration, dict) else "来源缺失", counts["expansion_records"], counts["empty_records"], counts["adapted_records"], verification_state(result, row["stages"])[0], status_zh(result.get("status")), "是" if result.get("submitted") is True else "否")
        parts.append('<tr>' + ''.join('<td>%s</td>' % esc(value) for value in values) + '</tr>')
    parts.append('</tbody></table></div><p class="muted">适配记录数仅表示程序记录了 adapted_chain，不判定其图面事实、推理有效性、任务适用性或新增性；不得把 14 个强结构输出算作 14 条有效新链。</p></section>')
    archive = {}
    for case in CASES:
        case_rows = [row for row in rows if row["case"] == case]
        notes = annotations.get("cases", {}).get(case, {})
        parts.append('<section class="panel" id="%s"><h2>%s</h2>' % (case, esc(CASE_NAMES[case])))
        images = {}
        for row in case_rows:
            image = row["folder"] / "chart.png"
            if image.exists():
                blob = image.read_bytes()
                images.setdefault(sha(blob), {"blob": blob, "variants": []})["variants"].append(row["variant"])
        if not images:
            parts.append('<p class="warning">原图档案缺失，不能据本页确认模型所见图面。</p>')
        if len(images) > 1:
            parts.append('<p class="warning">两个来源的图像 hash 不同，不得假定为相同图像输入。</p>')
        for image_sha, info in images.items():
            parts.append('<p class="label">%s</p><img class="chart" alt="%s 原图" src="data:image/png;base64,%s"><p class="hash">sha256=%s</p>' % (esc('；'.join(VARIANT_NAMES[v] for v in info["variants"])), esc(CASE_NAMES[case]), base64.b64encode(info["blob"]).decode("ascii"), image_sha))
        parts.append(paragraphs(notes.get("summary"), "annotation"))
        first = next((row for row in case_rows if row["context"] or row["initial"]), case_rows[0])
        parts.append(raw("公开任务及上下文原文", first["context"]))
        parts.append(raw("旧初始解释链原文（非本轮新生成）", first["initial"]))
        for row in case_rows:
            variant, result = row["variant"], row["result"]
            variant_notes = notes.get("variants", {}).get(variant, {})
            parts.append('<section class="variant" id="%s-%s"><h3>%s</h3><p class="muted">本轮不重跑这一步反问；以下候选原样继承。运行状态：%s（原始 status 保留在下方完整档案）</p>' % (case, variant, esc(VARIANT_NAMES[variant]), esc(status_zh(result.get("status")))))
            parts.append(paragraphs(variant_notes.get("summary"), "annotation"))
            if row["context"] != first["context"]:
                parts.append(raw("注意：此来源上下文不同，完整原文", row["context"], True))
            if row["initial"] != first["initial"]:
                parts.append(raw("注意：此来源初始链不同，完整原文", row["initial"], True))
            registration = row["registration"]
            candidates = registration.get("candidates", []) if isinstance(registration, dict) else []
            if registration is None:
                parts.append('<p class="warning">候选来源文件缺失，不等于真实返回零候选。</p>')
            elif not candidates:
                parts.append('<p>原反问返回零候选；本轮没有候选可展开。若核验执行，则只核验已有旧链。</p>')
            previous = row["previous"] or {}
            old_expansions = previous.get("expansions") or []
            expansions = {expansion.get("index", index): expansion for index, expansion in enumerate(result.get("expansions") or [])}
            for index, candidate in enumerate(candidates):
                candidate_id = candidate.get("id", "未标识")
                candidate_notes = variant_notes.get("candidates", {}).get(candidate_id)
                expansion = expansions.get(index)
                expansion_notes = variant_notes.get("expansions", {}).get(str(index), {})
                parts.append('<article class="candidate"><h4>候选 %d · %s</h4>' % (index + 1, esc(candidate_id)))
                if candidate_notes:
                    parts.append(blocks("继承候选的离线中文翻译（非本轮模型输出）", candidate_notes, (("claim", "候选结论"), ("visual_cues", "图面线索"), ("reading_to_try", "拟采用的读法"), ("assumptions", "必要假设")), True))
                parts.append(raw("继承的原候选完整英文", candidate, not bool(candidate_notes)))
                parts.append('<div class="columns"><div class="column"><h5>上一轮展开</h5>')
                if index < len(old_expansions):
                    old = old_expansions[index]
                    old_data = old.get("data") or {}
                    parts.append('<p class="muted">状态：%s；展开结果：%s</p>' % (esc(status_zh(old.get("status"))), esc(status_zh(old_data.get("outcome")))))
                    parts.append(raw("上一轮此候选完整展开（含原因）", old, True))
                else:
                    parts.append('<p class="warning">没有此索引的上一轮展开记录。</p>')
                parts.append('</div><div class="column"><h5>本轮三字段展开</h5>')
                if expansion is None:
                    parts.append('<p class="warning">此候选尚无本轮展开记录，不可视为拒绝或空链。</p>')
                else:
                    empty_label = {True: "是", False: "否"}.get(expansion.get("empty_record"), "未记录")
                    parts.append('<p class="muted">状态：%s；空记录标志：%s</p>' % (esc(status_zh(expansion.get("status"))), empty_label))
                    if expansion_notes:
                        parts.append(blocks("新 OBC 的离线中文翻译", expansion_notes, (("O", "O · 观察"), ("B", "B · 条件式解释"), ("C", "C · 结论")), True))
                    parts.append(raw("本轮模型三字段原文", expansion.get("data"), not bool(expansion_notes)))
                    if expansion_notes.get("comment"):
                        parts.append('<div class="annotation"><b>阅览注释（不是模型输出）</b>' + paragraphs(expansion_notes["comment"]) + '</div>')
                    parts.append(raw("本轮执行、行动对应与适配记录", expansion))
                parts.append('</div></div></article>')
            # Preserve any unexpected or unmatched expansion without silently losing it.
            extras = [value for index, value in expansions.items() if index not in range(len(candidates))]
            if extras:
                parts.append(raw("无法按原候选索引对应的展开记录", extras, True))
            parts.append('<h4>后续独立核验</h4>')
            parts.append(paragraphs(variant_notes.get("verification"), "annotation"))
            verification_label, verification_detail = verification_state(result, row["stages"])
            parts.append('<p class="%s"><b>%s：</b>%s</p>' % ("warning" if result.get("verification") is None else "muted", esc(verification_label), esc(verification_detail)))
            parts.append(raw("核验完整原文（模型判断，非人工结论）", result.get("verification")))
            parts.append(raw("合并后的旧链与全部非空新链", result.get("candidate_set")))
            parts.append(raw("本轮完整结果及错误", result))
            parts.append(raw("上一轮完整运行结果（来源档案）", row["previous"]))
            parts.append('<details><summary>完整实际请求与响应（system／user 原文保留，图像替换为 hash）</summary>')
            if not row["stages"]:
                parts.append('<p>没有阶段请求档案。</p>')
            for name, value in row["stages"].items():
                parts.append(raw(name, value))
            parts.append('</details></section>')
            archive['%s/%s' % (variant, case)] = {key: image_hashes(row[key]) for key in ("context", "initial", "registration", "previous", "result", "stages")}
        parts.append('</section>')
    parts.append('<section class="panel" id="archive"><h2>运行档案与实际成本</h2>')
    for label, value in (("配置", read_json(run_dir / "config.json")), ("实际请求账本", ledger), ("源文件身份", read_json(run_dir / "source_hashes.json")), ("运行摘要", summary), ("中文阅览注释完整原文", annotations)):
        parts.append(raw(label, value))
    parts.append('<p class="muted">单文件内嵌原图，可下载后在另一台电脑直接打开，不依赖项目或网络。中文为离线阅览层，不曾送入被测模型。原始英文与请求均可展开。</p></section></main></body></html>')
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "CONDITIONAL_EXPANSION_REVIEW.html"
    if output.exists():
        raise FileExistsError("Refusing overwrite: " + str(output))
    output.write_text(''.join(parts), encoding="utf-8")
    (output_dir / "RECORDS_WITH_IMAGE_HASHES.json").write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    provenance = {"source_run": str(run_dir.resolve()), "review_sha256": sha(output.read_bytes()), "renderer_sha256": sha(Path(__file__).read_bytes()), "semantic_scoring": False, "annotations_provided": bool(annotations), "request_redaction": "Only embedded image data is replaced by hash; system/user text intact."}
    (output_dir / "PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    print(build(args.run, args.output, read_json(args.annotations, {}) if args.annotations else {}))


if __name__ == "__main__":
    main()
