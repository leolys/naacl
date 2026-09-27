"""Build a portable, no-network HTML record of the fixed registration panel.

This is a renderer, not a semantic scorer. It never promotes notes to candidates,
merges chains, generates translations, or calls a model. Optional Chinese reviewer
annotations are clearly distinguished from the preserved model outputs.
"""
import argparse
import base64
import hashlib
import html
import json
import re
from pathlib import Path


VARIANTS = ("registration", "coverage")
CASES = ("pub001_misleading", "pub001_normal", "b002", "pub013")
VARIANT_NAMES = {"registration": "候选登记版反问", "coverage": "候选登记＋读取覆盖版反问"}
CASE_NAMES = {"pub001_misleading": "pub001 · 误导图", "pub001_normal": "pub001 · 正常图", "b002": "b002 · 原误导图", "pub013": "pub013 · 原误导图"}


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def redact_images(value):
    """Keep every text field; replace embedded image bytes with content hashes."""
    if isinstance(value, dict):
        return {key: redact_images(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_images(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        header, sep, encoded = value.partition(",")
        if sep and ";base64" in header:
            try:
                blob = base64.b64decode(encoded, validate=True)
                return "[内嵌图片：%s；sha256=%s；bytes=%d；请按 hash 对照本页原图]" % (header.split(";")[0][5:], digest(blob), len(blob))
            except ValueError:
                return "[无法解码的内嵌图片字符串；原始字符串 sha256=%s]" % digest(value.encode("utf-8"))
    return value


def esc(value):
    return html.escape(str(value), quote=True)


def raw_block(title, value, opened=False):
    text = json.dumps(redact_images(value), ensure_ascii=False, indent=2)
    return '<details%s><summary>%s</summary><pre>%s</pre></details>' % (" open" if opened else "", esc(title), esc(text))


def paragraphs(items, css=""):
    if isinstance(items, str):
        items = [items]
    return ''.join('<p%s>%s</p>' % (' class="%s"' % css if css else "", esc(item)) for item in (items or []))


def as_chains(value):
    if isinstance(value, dict):
        return value.get("chains", [])
    return value if isinstance(value, list) else []


def chain_block(chain, translation=None):
    translation = translation or {}
    parts = ['<article class="chain"><h4>解释链 %s</h4>' % esc(chain.get("id", "未标识"))]
    if translation:
        parts.append('<div class="annotation"><b>离线中文阅览注释（非模型原文）</b>')
        for label in ("O", "B", "C"):
            if label in translation:
                parts.append('<p><b>%s</b></p>%s' % (label, paragraphs(translation[label])))
        parts.append('</div>')
    else:
        parts.append('<p class="muted">此链暂未提供中文注释；下方保留完整英文原文。</p>')
    parts.append(raw_block("完整 O／B／C 原文", chain, opened=not bool(translation)))
    parts.append('</article>')
    return ''.join(parts)


def candidate_block(candidate, translation=None):
    translation = translation or {}
    parts = ['<article class="candidate"><h4>登记候选 %s</h4>' % esc(candidate.get("id", "未标识"))]
    if translation:
        parts.append('<div class="annotation"><b>离线中文阅览注释（非模型原文）</b>')
        for key, label in (("claim", "候选结论"), ("visual_cues", "图面线索"), ("reading_to_try", "拟采用的读法"), ("assumptions", "必要假设")):
            if key in translation:
                parts.append('<p><b>%s</b></p>%s' % (label, paragraphs(translation[key])))
        parts.append('</div>')
    parts.append(raw_block("登记候选完整原文（不等同新增解释路径）", candidate, opened=not bool(translation)))
    parts.append('</article>')
    return ''.join(parts)


def all_stage_records(folder):
    records = []
    for stage in sorted(folder.iterdir()) if folder.exists() else []:
        if stage.is_dir() and (stage.name in ("register", "verify") or stage.name.startswith("expand_")):
            for path in sorted(stage.glob("*.json")):
                records.append((path.relative_to(folder).as_posix(), read_json(path)))
    return records


def count_expanded(result):
    count = 0
    for expansion in result.get("expansions", []):
        data = expansion.get("data") or {}
        count += len(data.get("chains") or [])
    return count


def collect(run_dir):
    run_dir = Path(run_dir)
    summary = read_json(run_dir / "summary.json", {})
    indexed = {(row.get("variant"), row.get("case")): row for row in summary.get("results", [])}
    records = []
    for case in CASES:
        for variant in VARIANTS:
            folder = run_dir / variant / case
            result = read_json(folder / "result.json", indexed.get((variant, case)))
            if result is None:
                result = {"variant": variant, "case": case, "status": "not_run_or_missing", "registration": None, "expansions": [], "submitted": False}
            initial = read_json(folder / "initial.json", {})
            records.append({"case": case, "variant": variant, "folder": folder, "result": result,
                            "initial": initial, "context": read_json(folder / "context.json"),
                            "stages": all_stage_records(folder)})
    return summary, records


STYLE = """
:root{color-scheme:light;--ink:#183040;--muted:#566775;--line:#cbd7df;--blue:#125978;--soft:#edf6fa;--amber:#fff5dc}
*{box-sizing:border-box}body{margin:0;background:#f4f7f9;color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1160px;margin:auto;padding:30px 24px 70px}h1{font-size:30px;line-height:1.35}h2{font-size:25px;margin:0 0 16px}h3{font-size:21px;margin:0 0 12px}h4{margin:0 0 10px}p{margin:9px 0}a{color:var(--blue)}nav{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}nav a{background:white;border:1px solid var(--line);padding:7px 12px;border-radius:8px;text-decoration:none}.panel,.variant{background:white;border:1px solid var(--line);border-radius:12px;padding:22px;margin:22px 0}.variant{background:#fbfdfe}.notice{background:var(--amber);border-left:4px solid #ba8622;padding:14px 18px}.annotation{background:var(--soft);padding:13px 16px;border-radius:8px}.muted{color:var(--muted);font-size:14px}.chart{display:block;max-width:100%;height:auto;margin:14px auto;border:1px solid var(--line)}.hash{font:12px/1.5 monospace;overflow-wrap:anywhere}.chain,.candidate{padding:15px 0;border-top:1px solid var(--line)}details{margin:13px 0;border:1px solid var(--line);border-radius:8px;overflow:hidden}summary{cursor:pointer;padding:10px 14px;font-weight:600;background:#edf2f5;overflow-wrap:anywhere}pre{font:13px/1.55 ui-monospace,Consolas,monospace;margin:0;padding:14px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:680px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:9px 8px;overflow-wrap:anywhere}.table-scroll{overflow-x:auto}th{background:#edf2f5}.stats{display:flex;flex-wrap:wrap;gap:10px}.stats span{background:var(--soft);padding:7px 12px;border-radius:7px}.label{font-size:13px;color:var(--muted)}.warning{color:#984413}section{scroll-margin-top:16px}@media(max-width:600px){main{padding:18px 12px 45px}h1{font-size:24px}h2{font-size:21px}.panel,.variant{padding:14px}table{min-width:650px}.stats{font-size:14px}pre{font-size:12px}}
"""


def build(run_dir, output_dir, annotations=None):
    run_dir, output_dir = Path(run_dir), Path(output_dir)
    annotations = annotations or {}
    summary, records = collect(run_dir)
    ledger = read_json(run_dir / "ledger.json", {})
    config = read_json(run_dir / "config.json", {})
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>反问候选登记开发验证</title><style>', STYLE, '</style></head><body><main><h1>反问候选登记与读取覆盖 · 开发验证</h1>']
    parts.append('<div class="notice">本轮没有“普通重看”对照，目的是改进已选定的反问实现，不用于判定反问是否有贡献。复用已有开发输入和旧初始链，不是未见任务测试。候选数、展开链数不等于新增有效解释路径数；新增性与事实正确性须单独审阅。本页不把 notes 补写成解释链。</div>')
    parts.append('<p>执行流程：旧行动结论＋原图＋公开任务 → 反问登记候选 → 逐候选展开 OBC → 独立核验。没有运行后续 actor，没有业务提交；核验本身也可能误读图面或混淆字段职责，不保证其判断可靠。</p>')
    parts.append(paragraphs(annotations.get("overview"), "annotation"))
    parts.append('<div class="stats"><span>实际请求尝试：%s</span><span>浏览器操作：%s</span><span>付费 API 请求：%s</span></div>' % tuple(esc(ledger.get(key, "未记录")) for key in ("request_attempts", "browser_operations", "paid_api_requests")))
    parts.append('<nav>' + ''.join('<a href="#%s">%s</a>' % (case, esc(CASE_NAMES[case])) for case in CASES) + '<a href="#archive">配置与账本</a></nav>')
    parts.append('<section class="panel"><h2>执行概览</h2><div class="table-scroll"><table><thead><tr><th>输入</th><th>反问版本</th><th>登记候选数</th><th>展开返回链数</th><th>核验执行</th><th>运行状态</th><th>真实提交</th></tr></thead><tbody>')
    for item in records:
        result = item["result"]
        registration = result.get("registration")
        candidate_count = len(registration.get("candidates", [])) if isinstance(registration, dict) else "未完成"
        values = (CASE_NAMES[item["case"]], VARIANT_NAMES[item["variant"]], candidate_count, count_expanded(result), "有返回" if result.get("verification") is not None else "未完成／未运行", result.get("status", "未知"), "是" if result.get("submitted") is True else "否")
        parts.append('<tr>' + ''.join('<td>%s</td>' % esc(value) for value in values) + '</tr>')
    parts.append('</tbody></table></div><p class="muted">展开返回链数仅计 expansions[].data.chains 的实际记录，重复路径或有缺陷的链也保留；不会据结论标签自动去重。</p></section>')
    source_records = {}
    for case in CASES:
        items = [item for item in records if item["case"] == case]
        case_notes = annotations.get("cases", {}).get(case, {})
        parts.append('<section class="panel" id="%s"><h2>%s</h2>' % (case, esc(CASE_NAMES[case])))
        images = {}
        for item in items:
            path = item["folder"] / "chart.png"
            if path.exists():
                blob = path.read_bytes()
                images.setdefault(digest(blob), {"blob": blob, "variants": []})["variants"].append(item["variant"])
        if not images:
            parts.append('<p class="warning">此输入图像文件缺失，不能据本页确认模型所见图面。</p>')
        for sha, info in images.items():
            if len(images) > 1:
                parts.append('<p class="warning">两个版本的图像 hash 不同，不得假定为同一图像输入。</p>')
            parts.append('<p class="label">图像用于：%s</p><img class="chart" alt="%s 原始输入图" src="data:image/png;base64,%s"><p class="hash">sha256=%s</p>' % (esc('、'.join(VARIANT_NAMES[v] for v in info["variants"])), esc(CASE_NAMES[case]), base64.b64encode(info["blob"]).decode("ascii"), sha))
        parts.append(paragraphs(case_notes.get("summary"), "annotation"))
        first = next((item for item in items if item["initial"] or item["context"]), items[0])
        parts.append(raw_block("公开任务与输入上下文原文", first["context"]))
        parts.append('<h3>旧初始解释链（输入来源，不是本轮新生成）</h3>')
        initial = as_chains(first["initial"])
        for chain in initial:
            parts.append(chain_block(chain, case_notes.get("initial_chains", {}).get(chain.get("id"))))
        if not initial:
            parts.append('<p class="warning">没有找到旧初始链记录。</p>')
        for item in items:
            variant, result = item["variant"], item["result"]
            notes = case_notes.get("variants", {}).get(variant, {})
            parts.append('<section class="variant" id="%s-%s"><h3>%s</h3><p class="muted">运行状态：%s</p>' % (case, variant, esc(VARIANT_NAMES[variant]), esc(result.get("status", "未知"))))
            parts.append(paragraphs(notes.get("summary"), "annotation"))
            if item["context"] != first["context"]:
                parts.append(raw_block("注意：此版本上下文不同，完整原文", item["context"], True))
            if item["initial"] != first["initial"]:
                parts.append(raw_block("注意：此版本旧初始链不同，完整原文", item["initial"], True))
            parts.append('<h4>反问登记的候选</h4>')
            registration = result.get("registration")
            candidates = registration.get("candidates", []) if isinstance(registration, dict) else []
            if registration is None:
                parts.append('<p class="warning">候选登记未完成或没有可接受的结构化返回；这不是模型明确返回零候选。</p>')
            elif not candidates:
                parts.append('<p>模型返回零候选；没有据此手工补链。</p>')
            for candidate in candidates:
                parts.append(candidate_block(candidate, notes.get("candidates", {}).get(candidate.get("id"))))
            parts.append(raw_block("登记阶段完整结构化结果", registration))
            parts.append('<h4>逐候选展开记录与完整新 OBC</h4>')
            expansions = result.get("expansions", [])
            if not expansions:
                parts.append('<p>没有展开调用记录；不能视为展开器已成功或已拒绝某条链。</p>')
            for index, expansion in enumerate(expansions):
                data = expansion.get("data") or {}
                parts.append('<p>展开 %d：%s；结果 %s</p>' % (index + 1, esc(expansion.get("status", "未记录")), esc(data.get("outcome", "未记录"))))
                for chain in data.get("chains", []):
                    translations = notes.get("new_chains", {})
                    scoped_id = 'expand_%02d/%s' % (index, chain.get("id", ""))
                    translation = translations.get(scoped_id, translations.get(chain.get("id")))
                    parts.append(chain_block(chain, translation))
                parts.append(raw_block("该次展开全部原文（含未展开原因／错误）", expansion))
            parts.append('<h4>独立核验</h4>')
            parts.append(paragraphs(notes.get("verification"), "annotation"))
            if result.get("verification") is None:
                parts.append('<p class="warning">无完成的核验结果，不可算作已核验失败。</p>')
            parts.append(raw_block("核验完整原文（模型判断，非人工确认）", result.get("verification")))
            parts.append(raw_block("合并候选集与提案关联原文（原链、新链均保留）", result.get("candidate_set")))
            parts.append(raw_block("完整运行结果与错误", result))
            parts.append('<details><summary>完整实际请求与响应档案（保留 system／user 文本；图片仅替换为 hash）</summary>')
            if not item["stages"]:
                parts.append('<p>没有找到阶段请求档案。</p>')
            for name, value in item["stages"]:
                parts.append(raw_block(name, value))
            parts.append('</details></section>')
            source_records['%s/%s' % (variant, case)] = {"result": result, "context": item["context"], "initial": item["initial"], "stages": {name: redact_images(value) for name, value in item["stages"]}}
        parts.append('</section>')
    parts.append('<section class="panel" id="archive"><h2>配置、版本与成本记录</h2>')
    for title, value in (("运行配置", config), ("请求与成本账本", ledger), ("源文件身份", read_json(run_dir / "source_hashes.json")), ("完整运行摘要", summary), ("离线中文阅览注释原文", annotations)):
        parts.append(raw_block(title, value))
    parts.append('<p class="muted">这是可直接复制到其他电脑离线打开的单文件。中文注释是研究者阅览层，不曾送入被测模型；模型英文原文与实际请求可展开检查。</p></section></main></body></html>')
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "CANDIDATE_REGISTRATION_REVIEW.html"
    if output_path.exists():
        raise FileExistsError("Refusing to overwrite existing review: %s" % output_path)
    output_path.write_text(''.join(parts), encoding="utf-8")
    provenance = {"source_run": str(run_dir.resolve()), "review_sha256": digest(output_path.read_bytes()), "renderer_sha256": digest(Path(__file__).read_bytes()), "annotations_provided": bool(annotations), "redaction": "Only data:image;base64 strings replaced with sha256 references; all system/user text retained.", "semantic_scoring": False}
    (output_dir / "PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "RECORDS_WITH_IMAGE_HASHES.json").write_text(json.dumps(source_records, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    print(build(args.run, args.output, read_json(args.annotations, {}) if args.annotations else {}))


if __name__ == "__main__":
    main()
