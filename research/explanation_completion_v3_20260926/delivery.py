"""Offline, loss-aware Chinese review of the three-case candidate-C run.

No model, browser, network, ARIS, or translation dependencies. Source JSON is
canonical. The portable JSON keeps every case record, replacing only embedded
image data with auditable SHA-256 references; the HTML embeds each image once.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
HISTORY_RUN = HERE.parent / "explanation_completion_20260925" / "run"
HISTORY_NOTES = HISTORY_RUN.parent / "notes_zh.json"
CASE_IDS = ("b001", "b002", "pub013")
STAGES = ("generation", "questions", "supplement", "verification")
STAGE_LABELS = {
    "generation": "初始候选生成", "questions": "反问检查遗漏",
    "supplement": "新增解释与细化", "verification": "独立三维核验",
}
LABELS = {
    "supported": "有证据支持", "refuted": "有证据否定", "undetermined": "尚不能确定",
    "valid": "条件推导有效", "invalid": "条件推导无效", "active": "规则适用性获支持",
    "pending": "待定", "revoked": "已撤销", "disputed": "存在分歧",
    "completed": "流程完成", "running": "运行中", "prepared_not_sent": "仅准备，未发送",
    "failed_stage_no_quality_retry": "阶段失败，未按质量重跑",
    "completed_with_case_failures": "运行结束，含案例失败", "stopped_global": "全局停止",
    "not_attempted_global_stop": "全局停止后未尝试", "not_attempted": "未尝试",
    "failed": "失败", "missing": "记录缺失", "real_model": "真实模型输出",
    "offline_fixture": "离线测试夹具", "new_explanation": "新增具体候选解释",
    "refined_existing": "细化已有解释", "already_covered": "已有解释覆盖",
    "unresolved": "链外尚未解决", "no_new_explanation": "未发现新的解释",
    "no_new": "未发现新的解释", "compatible": "相容解释", "competing": "竞争解释",
    "support_gap": "支持缺口（旧版类型）", "observations": "观察依据",
    "rule_conditions": "规则适用条件", "coverage": "解释覆盖范围",
    "conditional_candidate": "条件性候选", "grounded_candidate": "已具依据的候选",
    "not_supported": "未获支持", "supported_candidate": "获支持的候选",
    "incomplete": "推导缺少必要前提", "no_complete_candidate": "未生成完整具体候选",
    "not_run_no_complete_candidate": "无完整候选，后续阶段未运行", "mock_completed": "离线夹具流程完成",
    "unverified": "尚未核验", "contradicted_premises": "前提与证据冲突",
    "invalid_inference": "条件推导无效", "incomplete_inference": "条件推导不完整",
    "supports_action": "条件性支持行动（旧版类型）",
    "challenges_support": "质疑支持充分性（旧版类型）",
}
IMAGE_URI = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\r\n]+)$")


def esc(value):
    if value is None:
        value = "未记录（null）"
    elif isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return html.escape(str(value), quote=True)


def paragraph(value, css=""):
    return '<p class="' + css + '">' + esc(value) + '</p>'


def label(value):
    value = str(value if value is not None else "missing")
    return LABELS.get(value, value) + " · " + value if value in LABELS else value


def badge(value):
    css = "good" if value in {"completed", "supported", "valid", "active"} else (
        "bad" if value in {"failed", "refuted", "invalid", "revoked", "missing"}
        or "failed" in str(value) else "neutral")
    return '<span class="badge ' + css + '">' + esc(label(value)) + '</span>'


def raw_block(title, value, opened=False):
    return ('<details class="raw"' + (' open' if opened else '') + '><summary>' + esc(title)
            + '</summary><pre>' + esc(value) + '</pre></details>')


def text_list(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return '<ul>' + ''.join('<li>' + esc(x) + '</li>' for x in value) + '</ul>'
    return paragraph(value)


def note_block(value):
    if not value:
        return ""
    return ('<aside class="note"><strong>中文阅读注释</strong>' + text_list(value)
            + '<small>Codex 离线中文翻译与审阅备注；非 API 输出，也不是独立人工确认。英文原文未改写。</small></aside>')


def dict_value(value):
    return value if isinstance(value, dict) else {}


def list_value(value):
    return value if isinstance(value, list) else []


def evidence(items):
    if not items:
        return paragraph("此处未记录证据。", "muted")
    parts = []
    for item in list_value(items):
        if isinstance(item, dict):
            parts.append('<li><small>' + esc(item.get("ref")) + ' · '
                         + esc(item.get("location", item.get("path"))) + '</small>'
                         + paragraph(item.get("content")) + '</li>')
        else:
            parts.append('<li>' + esc(item) + '</li>')
    return '<ul class="evidence">' + ''.join(parts) + '</ul>'


def raster_mime(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def register_image(data, source, images):
    sha = hashlib.sha256(data).hexdigest()
    mime = raster_mime(data)
    if sha not in images:
        images[sha] = {"sha256": sha, "mime": mime, "bytes": len(data),
                       "sources": [], "data_base64": base64.b64encode(data).decode("ascii")}
    if source not in images[sha]["sources"]:
        images[sha]["sources"].append(source)
    return sha


def compact_images(value, source, images):
    """Only embedded image strings are substituted. Other model text is intact."""
    if isinstance(value, dict):
        return {k: compact_images(v, source, images) for k, v in value.items()}
    if isinstance(value, list):
        return [compact_images(v, source, images) for v in value]
    match = IMAGE_URI.fullmatch(value) if isinstance(value, str) else None
    if match:
        try:
            data = base64.b64decode(re.sub(r"\s", "", match.group(2)), validate=True)
        except ValueError:
            return value
        sha = register_image(data, source, images)
        return {"_embedded_image_reference": sha, "declared_mime": match.group(1),
                "decoded_bytes": len(data), "original_data_uri_sha256":
                hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "note_zh": "原始请求保留完整图片；展示包以 SHA-256 引用共用嵌图，未改源文件。"}
    return value


def read_record(path, images, provenance):
    data = path.read_bytes()
    provenance[str(path)] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return {"_delivery_read_error": str(error), "_raw_file_text": data.decode("utf-8", errors="replace")}
    return compact_images(value, str(path), images)


def load_case(run, cid, images, provenance):
    folder = run / "cases" / cid
    records = {}
    if folder.is_dir():
        for path in sorted(folder.rglob("*.json")):
            records[path.relative_to(folder).as_posix()] = read_record(path, images, provenance)
    missing = [name for name in ("inputs.json", "result.json", "initial_set.json",
                                 "combined_arguments.json", "rule_state.json") if name not in records]
    chart = folder / "chart.jpeg"
    chart_sha = None
    if chart.is_file():
        data = chart.read_bytes()
        chart_sha = register_image(data, str(chart), images)
        provenance[str(chart)] = {"sha256": chart_sha, "bytes": len(data)}
    else:
        missing.append("chart.jpeg")
    result = dict_value(records.get("result.json"))
    warnings = []
    if result.get("task_id") not in (None, cid):
        warnings.append("result.json 的 task_id 与目录不一致；以下保留真实记录。")
    state = records.get("rule_state.json")
    if state is not None and result.get("rule_state") is not None and state != result["rule_state"]:
        warnings.append("rule_state.json 与 result.json 内规则状态不同；两份记录均保留，不能当作一致。")
    inputs = dict_value(records.get("inputs.json"))
    chart_ref = inputs.get("chart_ref", "")
    if chart_sha and isinstance(chart_ref, str) and re.search(r":[a-f0-9]{64}$", chart_ref):
        if chart_ref.rsplit(":", 1)[1] != chart_sha:
            warnings.append("chart_ref 的图像哈希与 chart.jpeg 不一致。")
    for name, value in records.items():
        if isinstance(value, dict) and "_delivery_read_error" in value:
            warnings.append(name + " 无法解析；完整原文保留在审查记录。")
    return {"task_id": cid, "source_directory": str(folder), "chart_sha256": chart_sha,
            "missing_files": missing, "warnings": warnings, "records": records}


def load_bundle(run, notes_path=None, history_run=None, history_notes=None):
    run = Path(run).resolve()
    if not run.is_dir():
        raise ValueError("Run directory does not exist: " + str(run))
    images, provenance = {}, {}
    metadata = {}
    for name in ("summary.json", "budget.json", "prompt_templates.json", "runtime.json"):
        path = run / name
        metadata[name] = read_record(path, images, provenance) if path.is_file() else None
    notes_path = Path(notes_path).resolve() if notes_path else run.parent / "notes_zh.json"
    notes = read_record(notes_path, images, provenance) if notes_path.is_file() else {}
    if not isinstance(notes, dict):
        raise ValueError("notes_zh.json must be a JSON object")
    cases = [load_case(run, cid, images, provenance) for cid in CASE_IDS]
    history_run = Path(history_run or HISTORY_RUN).resolve()
    history_notes = Path(history_notes or HISTORY_NOTES).resolve()
    history = {"source_directory": str(history_run), "available": history_run.is_dir(), "cases": []}
    if history_run.is_dir():
        history["cases"] = [load_case(history_run, cid, images, provenance) for cid in CASE_IDS]
    history["notes_zh"] = read_record(history_notes, images, provenance) if history_notes.is_file() else {}
    return {"schema_version": "candidate_c_delivery_v3", "created_at": datetime.now(timezone.utc).isoformat(),
            "source_directory": str(run), "metadata": metadata, "cases": cases, "notes_zh": notes,
            "notes_source": str(notes_path) if notes_path.is_file() else None, "history": history,
            "images": images, "source_files": provenance,
            "limits_zh": "旧版仅为描述性历史参照，不是受控 A/B 实验；不能据此归因改进或证明反问增益、解释完备性。",
            "image_policy_zh": "源请求含完整图片，展示 JSON 仅将图片 data URI 换成哈希引用；所有其他已读 JSON 字段保留。"}


def chain_card(chain, rules, notes=None, historical=False):
    chain = dict_value(chain)
    cid = chain.get("chain_id", chain.get("id", "未记录链标识"))
    rule = next((r for r in list_value(rules) if isinstance(r, dict) and r.get("id") == chain.get("rule_id")), {})
    notes = dict_value(notes)
    parts = ['<article class="chain"><h4>解释链 ' + esc(cid) + '</h4>']
    if chain.get("relationship"):
        parts.append(paragraph(label(chain["relationship"]), "muted"))
    for key, title in (("O", "观察 O：原图中的可见事实"), ("B", "解释规则 B：如何由观察得到候选"),
                       ("conditions", "适用条件：仍需成立的前提"), ("C", "结论 C：具体候选")):
        parts.append('<section class="obc-part"><h5>' + title + '</h5>')
        if key in notes:
            parts.append('<div class="translation">' + text_list(notes[key]) + '</div>')
        if key == "O":
            parts.append(evidence(chain.get("observations")))
            if chain.get("task_evidence"):
                parts.append('<strong>公开任务证据（单独记录）</strong>' + evidence(chain["task_evidence"]))
        elif key == "B":
            parts.append(paragraph(rule.get("text", "没有找到对应规则，未补写。")))
            parts.append(paragraph("规则标识：" + str(chain.get("rule_id")), "muted"))
        elif key == "conditions":
            parts.append(text_list(rule.get("conditions", "未记录适用条件。")))
        else:
            parts.append(paragraph(chain.get("claim")))
            parts.append('<strong>对应候选选项</strong>' + paragraph(chain.get("option_label")))
            if historical and "claim_kind" in chain:
                parts.append(paragraph("旧版结论分类：" + label(chain["claim_kind"]), "muted"))
        parts.append('</section>')
    parts.append(note_block(notes.get("comment")))
    parts.append(raw_block("这条链与对应规则的原始字段", {"chain": chain, "rule": rule}))
    return ''.join(parts) + '</article>'


def refinement_card(value):
    value = dict_value(value)
    return ('<article class="chain"><h4>已有解释细化 ' + esc(value.get("id")) + '</h4>'
            + paragraph("目标链：" + str(value.get("target_chain_id")))
            + '<h5>补充的图像观察</h5>' + evidence(value.get("added_observations"))
            + '<h5>补充的任务证据</h5>' + evidence(value.get("added_task_evidence"))
            + '<h5>适用条件说明</h5>' + paragraph(value.get("condition_note"))
            + '<h5>补充理由</h5>' + paragraph(value.get("reason"))
            + raw_block("完整细化记录", value) + '</article>')


def verification_card(check, historical=False, refinement=False):
    check = dict_value(check)
    parts = ['<article class="check"><h4>' + ('细化核验 ' if refinement else '候选链核验 ')
             + esc(check.get("target_id")) + '</h4><div class="dimensions">']
    dimensions = (("O", "观察及证据绑定"), ("B_applicability", "规则在当前任务中的适用性"),
                  ("conditional_inference", "给定前提下的条件推导"))
    if refinement and "support" in check:
        dimensions = (("support", "细化内容的独立证据支持"),)
    if historical and "B_applicability" not in check:
        dimensions = (("O", "旧版：观察及绑定"), ("B", "旧版：规则核验（未拆分适用性）"),
                      ("implication", "旧版：结论或细化支持"))
    for key, title in dimensions:
        record = dict_value(check.get(key))
        parts.append('<section class="dimension"><h5>' + esc(title) + '</h5><code>' + esc(key)
                     + '</code><div>' + badge(record.get("status")) + '</div>'
                     + paragraph(record.get("reason")))
        if "evidence" in record:
            parts.append(evidence(record["evidence"]))
        if "premise_ids" in record:
            parts.append('<strong>引用前提</strong>' + text_list(record["premise_ids"]))
        if "missing_premises" in record:
            parts.append('<strong>缺少前提</strong>' + (text_list(record["missing_premises"])
                         if record["missing_premises"] else paragraph("未列出缺少前提；不等于前提已被事实核实。")))
        parts.append('</section>')
    parts.append('</div>' + raw_block("完整核验对象", check) + '</article>')
    return ''.join(parts)


def state_section(state):
    if not isinstance(state, dict) or "_delivery_read_error" in state:
        return paragraph("没有可读取的持久规则状态；不能推断规则已保存或核验通过。", "warning")
    parts = [paragraph("规则状态、候选链判断及细化记录分别保存。规则为启用状态或条件推导有效，均不等于候选已确定，也不授权执行任务。", "notice")]
    for record in list_value(state.get("rules")):
        record = dict_value(record)
        parts.append('<article class="rule"><h4>规则 ' + esc(record.get("rule_id")) + ' · 版本 '
                     + esc(record.get("version")) + '</h4>' + badge(record.get("status"))
                     + paragraph(dict_value(record.get("rule")).get("text"))
                     + raw_block("适用范围、核验依据与版本历史", record) + '</article>')
    if state.get("chain_assessments"):
        parts.append('<h4>每条候选链的最终记录</h4>')
        for record in list_value(state["chain_assessments"]):
            record = dict_value(record)
            parts.append('<article class="rule"><strong>' + esc(record.get("chain_id")) + '</strong>'
                         + paragraph(record.get("claim")) + badge(record.get("grounding"))
                         + raw_block("完整候选判断记录", record) + '</article>')
    if state.get("refinements"):
        parts.append(raw_block("完整细化状态记录（含目标、版本与是否应用）", state["refinements"]))
    if state.get("unresolved_questions"):
        parts.append(raw_block("初始生成时记录的未解问题（原样保留；不是最终未解决计数）", state["unresolved_questions"]))
    parts.append(raw_block("完整持久规则状态 rule_state.json", state))
    return ''.join(parts)


def get_initial(records, result):
    for value in (result.get("initial_arguments"), records.get("initial_set.json"),
                  dict_value(records.get("inputs.json")).get("base_arguments")):
        if isinstance(value, dict) and "_delivery_read_error" not in value:
            return value
    return None


def case_notes(notes, cid):
    notes = dict_value(notes)
    return dict_value(dict_value(notes.get("cases", notes)).get(cid))


def section_heading(anchor, title):
    return '<h3 id="' + anchor + '">' + esc(title) + '</h3>'


def unaccepted_stage_output(records, stage):
    name = stage + "/raw.json"
    if name in records:
        return (paragraph("以下是真实未通过校验的阶段输出，仅供审查，不计入有效解释、补充或核验。", "warning")
                + raw_block("未通过校验的真实原文 · " + name, records[name], opened=True))
    responses = [(name, value) for name, value in records.items()
                 if name.startswith(stage + "/") and re.search(r"/response_\d+\.json$", name)]
    return ''.join(raw_block("未获得有效结果的真实响应 · " + name, value, opened=True)
                   for name, value in responses)


def stage_audit(case, historical=False):
    records = case["records"]
    result = dict_value(records.get("result.json"))
    stages = dict_value(result.get("stages"))
    parts = [paragraph("请求与响应按原始目录逐项保留。图片 data URI 用哈希引用显示；源 request.json 含完整图片。所有模型原文按文本转义，未经修正或筛选。", "muted")]
    for stage in (STAGES[1:] if historical else STAGES):
        stage_records = {name: value for name, value in records.items() if name.startswith(stage + "/")}
        stage_state = dict_value(stages.get(stage))
        parts.append('<details class="stage"><summary>' + esc(STAGE_LABELS[stage]) + ' · '
                     + esc(label(stage_state.get("status", "missing"))) + ' · '
                     + str(len(stage_records)) + ' 份记录</summary>')
        parts.append(raw_block("阶段状态与失败信息", stage_state))
        if not stage_records:
            parts.append(paragraph("没有此阶段的请求／响应文件；不能称为该阶段已完成。", "warning"))
        for name, value in stage_records.items():
            parts.append(raw_block(name, value))
        parts.append('</details>')
    other = {name: value for name, value in records.items() if "/" not in name}
    parts.append(raw_block("案例根目录全部 JSON（含原始 generation / result / rule_state）", other))
    unknown = {name: value for name, value in records.items()
               if "/" in name and name.split("/", 1)[0] not in STAGES}
    if unknown:
        parts.append(raw_block("其他持久化记录", unknown))
    return ''.join(parts)


def render_case(case, notes, historical=False, images=None, embedded=None):
    cid = case["task_id"]
    prefix = ("history-" if historical else "case-") + cid
    records = case["records"]
    result = dict_value(records.get("result.json"))
    inputs = dict_value(records.get("inputs.json"))
    task = dict_value(inputs.get("task"))
    notes = dict_value(notes)
    initial = get_initial(records, result)
    combined = dict_value(result.get("combined") or records.get("combined_arguments.json"))
    supplement = result.get("supplement")
    questions = result.get("questions")
    verification = result.get("verification")
    rules = combined.get("rules", dict_value(initial).get("rules", []))
    parts = ['<section class="case" id="' + prefix + '"><header class="case-header"><p class="eyebrow">'
             + ('2026-09-25 历史结果 · 仅描述性参照' if historical else '本轮 v3 · C 保持具体候选')
             + '</p><h2>' + esc(cid) + '</h2>' + badge(result.get("status")) + '</header>']
    parts.append(note_block(notes.get("overview", notes.get("summary"))))
    if case["missing_files"]:
        parts.append(paragraph("缺失文件：" + "、".join(case["missing_files"])
                               + "。缺失不等于零新增、无问题或核验成功。", "warning"))
    parts.extend(paragraph(w, "warning") for w in case["warnings"])
    if result.get("failure"):
        parts.append(raw_block("本例真实失败信息（未隐藏）", result["failure"], opened=True))
    parts.append('<nav class="case-nav" aria-label="' + esc(cid) + ' 阶段导航">')
    for step, title in (("task", "任务与原图"), ("initial", "初始候选"), ("questions", "反问"),
                        ("supplement", "补充与链外状态"), ("verification", "三维核验"),
                        ("state", "持久规则"), ("audit", "原始审查")):
        parts.append('<a href="#' + prefix + '-' + step + '">' + title + '</a>')
    parts.append('</nav>' + section_heading(prefix + "-task", "任务公开目标、选项与原图"))
    parts.append('<div class="task"><h4>页面标题</h4>' + paragraph(task.get("page_title"))
                 + '<h4>公开用户目标</h4>' + paragraph(task.get("user_goal"))
                 + '<h4>原图说明</h4>' + paragraph(task.get("chart_reference"))
                 + '<h4>公开候选选项</h4>' + text_list(task.get("option_labels"))
                 + raw_block("完整公开任务与 decision_reference", {"task": task,
                             "decision_reference": inputs.get("decision_reference")}) + '</div>')
    if case["chart_sha256"]:
        sha = case["chart_sha256"]
        if images is not None and embedded is not None and sha not in embedded:
            parts.append(image_figure(sha, images[sha], cid))
            embedded.add(sha)
        else:
            parts.append('<a class="chart-link" href="#image-' + sha
                         + '">查看本例完整原图（共用原始嵌图） ↗</a>')
    else:
        parts.append(paragraph("原图缺失；没有以占位图冒充真实图表。", "warning"))
    parts.append(section_heading(prefix + "-initial", "1 · 初始解释：观察、规则、条件与具体候选"))
    parts.append(note_block(notes.get("initial")))
    if initial is None:
        parts.append(paragraph("没有通过接口校验的初始解释集合；原始生成与失败回执仍在下方保留。", "warning"))
        parts.append(unaccepted_stage_output(records, "generation"))
    else:
        chains = list_value(initial.get("chains"))
        parts.append(paragraph("保存的初始解释链：" + str(len(chains)) + " 条。所有初始链均展示。", "muted"))
        for chain in chains:
            chain_note = dict_value(notes.get("chains")).get(dict_value(chain).get("chain_id"))
            parts.append(chain_card(chain, initial.get("rules", []), chain_note, historical))
        if initial.get("unresolved_questions"):
            parts.append(raw_block("初始生成时记录的未解问题（原样保留；后续可能已补充）", initial["unresolved_questions"], opened=True))
        parts.append(raw_block("完整初始集合 initial_set / initial_arguments", initial))
    if "generation" in result:
        parts.append(raw_block("初始生成原始输出 generation（未改写）", result["generation"]))
    parts.append(section_heading(prefix + "-questions", "2 · 反问：检查已有解释遗漏了什么"))
    parts.append(note_block(notes.get("questions")))
    if not isinstance(questions, dict):
        parts.append(paragraph("没有通过接口校验的反问结果；不能当作没有遗漏。", "warning"))
        parts.append(unaccepted_stage_output(records, "questions"))
    else:
        parts.append(paragraph(questions.get("summary")))
        for question in list_value(questions.get("questions")):
            question = dict_value(question)
            parts.append('<article class="question"><h4>' + esc(question.get("id")) + ' · '
                         + esc(label(question.get("focus"))) + '</h4>' + paragraph(question.get("question"))
                         + '<strong>指向已有链</strong>' + text_list(question.get("target_chain_ids")) + '</article>')
        if not questions.get("questions"):
            parts.append(paragraph("本轮记录 0 个反问；该数量不证明解释完备。", "notice"))
        parts.append(raw_block("反问完整输出", questions))
    parts.append(section_heading(prefix + "-supplement", "3 · 新增链、已有链细化与链外未解决问题"))
    parts.append(note_block(notes.get("supplement")))
    if not isinstance(supplement, dict):
        parts.append(paragraph("没有通过接口校验的补充结果；不能计为零新增成功。请审查真实 raw 与响应。", "warning"))
        parts.append(unaccepted_stage_output(records, "supplement"))
    else:
        parts.append('<h4>新增具体候选解释链 · ' + str(len(list_value(supplement.get("new_chains")))) + ' 条</h4>')
        for chain in list_value(supplement.get("new_chains")):
            chain_note = dict_value(notes.get("chains")).get(dict_value(chain).get("chain_id"))
            parts.append(chain_card(chain, rules, chain_note, historical))
        parts.append('<h4>已有解释的独立细化 · ' + str(len(list_value(supplement.get("refinements")))) + ' 条</h4>')
        parts.extend(refinement_card(x) for x in list_value(supplement.get("refinements")))
        parts.append('<h4>链外反问处理与未解决状态</h4>'
                     + paragraph("没有新解释、已有覆盖或尚未解决，均可以是真实结果；这些状态不冒充具体候选 C。", "notice"))
        for response in list_value(supplement.get("question_responses")):
            response = dict_value(response)
            parts.append('<article class="disposition"><h5>' + esc(response.get("question_id")) + ' · '
                         + esc(label(response.get("outcome"))) + '</h5>' + paragraph(response.get("reason"))
                         + raw_block("完整链外处理记录", response) + '</article>')
        if supplement.get("unresolved"):
            parts.append(raw_block("补充阶段链外未解决记录", supplement["unresolved"], opened=True))
        parts.append(raw_block("完整补充原始输出（含新规则、所有记录）", supplement))
    parts.append(section_heading(prefix + "-verification", "4 · 独立核验：观察、适用性与条件推导"))
    parts.append(note_block(notes.get("verification")))
    parts.append(paragraph("此处“独立”指同一模型的独立请求核验；不是独立模型、严格盲审或人工确认。", "muted"))
    parts.append(paragraph("条件推导有效只表示：若所列前提成立，结论能否推出。它不确认前提真实，也不代替规则对当前图的适用性核验。", "notice"))
    if not isinstance(verification, dict):
        parts.append(paragraph("没有通过接口校验的核验结果；不得宣称核验已通过。", "warning"))
        parts.append(unaccepted_stage_output(records, "verification"))
    else:
        parts.append(paragraph(verification.get("summary")))
        parts.extend(verification_card(x, historical) for x in list_value(
            verification.get("chain_checks", verification.get("checks", []))))
        parts.extend(verification_card(x, historical, refinement=True)
                     for x in list_value(verification.get("refinement_checks")))
        parts.append(raw_block("核验完整原始输出", verification))
    parts.append(note_block(notes.get("assessment")))
    parts.append(section_heading(prefix + "-state", "5 · 完整持久规则状态"))
    parts.append(note_block(notes.get("rule_state")))
    state = records.get("rule_state.json")
    parts.append(state_section(state))
    if state is None and result.get("rule_state") is not None:
        parts.append(raw_block("仅 result.json 中存在的规则状态（没有独立状态文件）", result["rule_state"]))
    parts.append(section_heading(prefix + "-audit", "6 · 阶段、请求、真实响应与失败审查"))
    parts.append(raw_block("本例状态、调用与成本", {k: result.get(k) for k in
        ("status", "stages", "failure", "request_attempts", "estimated_ledger_usd", "evidence_mode")}))
    parts.append(stage_audit(case, historical))
    parts.append('</section>')
    return ''.join(parts)


STYLE = """
:root{color-scheme:light;--ink:#192f3d;--muted:#536975;--blue:#176989;--line:#d8e3e7;--paper:#fff;--bg:#f4f6f5}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:30px}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 system-ui,-apple-system,'Segoe UI','Microsoft YaHei',sans-serif}
a{color:var(--blue);text-underline-offset:3px}a:focus,summary:focus{outline:3px solid #d69420;outline-offset:4px}.layout{display:grid;grid-template-columns:230px minmax(0,1120px);gap:36px;max-width:1480px;margin:auto;padding:36px 28px}.sidebar{position:sticky;top:28px;align-self:start}.brand{font-size:13px;letter-spacing:.14em;color:var(--muted);font-weight:700}.sidebar nav{display:grid;gap:10px;margin:26px 0}.sidebar a{background:#fff;padding:11px 14px;border:1px solid var(--line);border-radius:8px;text-decoration:none}.sidebar small{color:var(--muted)}main{min-width:0}h1{font-size:clamp(27px,3.3vw,44px);line-height:1.25;margin:12px 0 18px}h2{font-size:32px;margin:4px 0 12px}h3{font-size:23px;margin:38px 0 18px;padding-top:9px;border-top:1px solid var(--line)}h4{font-size:18px;margin:10px 0}h5{font-size:15px;margin:8px 0}p{margin:9px 0}small,.muted{color:var(--muted)}.hero,.case,.metadata,.gallery{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:30px;margin-bottom:28px}.eyebrow{font-size:12px;letter-spacing:.09em;color:var(--blue);font-weight:750}.lead{font-size:18px;max-width:820px}.flow{border-left:4px solid var(--blue);padding:12px 18px;background:#eef5f7;margin:20px 0}.notice,.warning,.note{padding:14px 18px;border-radius:8px;margin:18px 0}.notice{background:#eef5f7}.warning{background:#fff0e9;border-left:4px solid #b64b20;color:#783916}.note{background:#f1f5e9;border-left:4px solid #719147}.note small{display:block;font-size:12px;margin-top:8px}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:22px 0}.metric{border:1px solid var(--line);border-radius:10px;padding:16px}.metric strong{font-size:25px;display:block}.metric small{font-size:12px}.badge{font-size:12px;display:inline-block;border-radius:20px;padding:4px 11px;max-width:100%;overflow-wrap:anywhere}.good{background:#e6f1e8;color:#285c35}.bad{background:#fbe8e2;color:#9c3524}.neutral{background:#f7efd9;color:#775916}.case-nav{display:flex;flex-wrap:wrap;gap:8px 18px;margin:24px 0}.case-nav a{font-size:13px}.chain,.check,.rule,.question,.disposition,.task{border:1px solid var(--line);padding:20px;border-radius:10px;margin:16px 0;min-width:0}.chain{border-top:3px solid #5c8795}.obc-part{padding:12px 0;border-top:1px solid #e8edef}.translation{background:#f1f5e9;padding:8px 13px;margin:8px 0}.translation:before{content:'中文释义';font-size:11px;font-weight:700;color:#607741}.evidence{padding-left:24px}.evidence li{margin:10px 0}.evidence small{font-family:Consolas,monospace;font-size:12px;overflow-wrap:anywhere}.dimensions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.dimension{border-radius:8px;background:#f5f7f7;padding:15px;overflow-wrap:anywhere}.dimension code{font-size:12px;color:var(--muted)}details{border:1px solid var(--line);border-radius:7px;margin:12px 0;background:#fcfdfd}summary{cursor:pointer;padding:11px 14px;font-size:13px;font-weight:600;overflow-wrap:anywhere}details[open]>summary{border-bottom:1px solid var(--line)}pre{margin:0;padding:16px;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font:12px/1.65 Consolas,'Microsoft YaHei',monospace;max-height:650px;overflow:auto}.stage[open]{padding:0 14px 10px}.stage[open]>summary{margin:0 -14px 12px}.chart-link{display:inline-block;padding:10px 15px;background:#eef5f7;border-radius:8px}.gallery figure{margin:28px 0 45px;scroll-margin-top:20px}.gallery img{display:block;max-width:100%;height:auto;background:#fff;border:1px solid var(--line)}figcaption{font-size:12px;overflow-wrap:anywhere;color:var(--muted);margin-top:12px}.source{font-size:12px;overflow-wrap:anywhere}.history-banner{padding:20px;background:#fff0d7;border-radius:10px;margin:24px 0}.history-wrapper>summary{font-size:20px;padding:22px}.history-wrapper[open]{background:transparent;border:0}.history-wrapper[open]>summary{margin-bottom:20px}.history-wrapper .case{border-top:4px solid #c89a40}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;border-bottom:1px solid var(--line);padding:12px 8px;overflow-wrap:anywhere}footer{font-size:12px;color:var(--muted);padding:20px 0 45px}.table-wrap{overflow:auto}
.original-chart{margin:26px 0;scroll-margin-top:20px}.original-chart img{display:block;max-width:100%;height:auto;border:1px solid var(--line)}
@media(max-width:1000px){.layout{grid-template-columns:180px minmax(0,1fr);gap:18px;padding:20px}.dimensions{grid-template-columns:1fr}.hero,.case,.metadata,.gallery{padding:22px}}
@media(max-width:700px){.layout{display:block;padding:14px}.sidebar{position:static}.sidebar nav{display:flex;flex-wrap:wrap;margin:12px 0 20px;gap:6px}.sidebar a{padding:6px 10px;font-size:13px}.sidebar small{display:none}.metrics{grid-template-columns:1fr}.hero,.case,.metadata,.gallery{padding:18px;border-radius:10px}h3{font-size:21px}.chain,.check,.task{padding:15px}}
@media print{.sidebar{display:none}.layout{display:block;padding:0}.case,.hero{break-before:page;border:0}details:not([open]){display:none}.dimensions{grid-template-columns:1fr}a{color:inherit}.gallery img{max-height:85vh;width:auto}}
"""


def image_figure(sha, image, title):
    parts = ['<figure class="original-chart" id="image-' + sha + '"><h4>' + esc(title) + ' · 完整原图</h4>']
    if image["mime"]:
        parts.append('<img src="data:' + image["mime"] + ';base64,' + image["data_base64"]
                     + '" alt="' + esc(title) + ' 原始任务图表" loading="lazy">')
    else:
        parts.append(paragraph("该图片不是可识别的安全栅格格式，未尝试展示；原始摘要与来源保留。", "warning"))
    parts.append('<figcaption>原始字节嵌入 · SHA-256：' + sha + ' · ' + str(image["bytes"]) + ' 字节</figcaption>'
                 + raw_block("图像源文件及请求引用位置", image["sources"]) + '</figure>')
    return ''.join(parts)


def render_html(bundle):
    metadata = bundle["metadata"]
    summary = dict_value(metadata.get("summary.json"))
    budget = dict_value(metadata.get("budget.json"))
    notes = bundle["notes_zh"]
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width, initial-scale=1">'
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             'img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
             '<title>具体候选 C 修正 · 三例完整阅览</title><style>' + STYLE
             + '</style></head><body><div class="layout"><aside class="sidebar">'
             '<div class="brand">EXPLANATION REVIEW · V3</div><nav aria-label="主导航">'
             '<a href="#overview">运行概览</a>']
    parts.extend('<a href="#case-' + cid + '">' + cid + ' · 本轮结果</a>' for cid in CASE_IDS)
    parts.append('<a href="#images">三例完整原图</a><a href="#history">旧版历史参照</a>'
                 '<a href="#sources">成本、来源与审查</a></nav><small>自包含离线页面<br>无外部资源或 API 请求<br>每张原图只嵌入一次</small></aside><main>')
    parts.append('<section class="hero" id="overview"><p class="eyebrow">三例开发面板 · b001 / b002 / pub013</p>'
                 '<h1>让结论保持为<br>可检验的具体候选</h1>'
                 '<p class="lead">按原始任务和整张图表，阅览初始解释、反问、补充、独立核验与持久规则。每个候选保留完整的观察 O、解释规则 B、适用条件及结论 C。</p>'
                 '<div class="flow">初始具体候选 → 反问检查遗漏 → 新候选／已有链细化／链外未解决 → 独立三维核验 → 保存规则状态</div>'
                 '<p class="notice">“无法确定”可以记录在链外处理结果或核验状态；本轮候选 C 应是可检验的具体主张。条件推导有效不等于候选被证实，新增链数量不代表改进幅度。</p>')
    parts.append('<div class="metrics"><div class="metric"><small>实际请求尝试</small><strong>'
                 + esc(summary.get("request_attempts", budget.get("request_attempts"))) + '</strong></div>'
                 '<div class="metric"><small>估算账本 · 美元</small><strong>'
                 + esc(summary.get("estimated_ledger_usd", budget.get("estimated_ledger_usd")))
                 + '</strong><small>估算口径，非提供商实际账单</small></div><div class="metric"><small>运行状态</small><p>'
                 + badge(summary.get("status")) + '</p>' + badge(summary.get("evidence_mode")) + '</div></div>')
    parts.append(note_block(dict_value(notes).get("overview")))
    parts.append('<div class="table-wrap"><table><thead><tr><th>案例</th><th>初始链</th><th>新增链</th><th>细化</th><th>状态</th></tr></thead><tbody>')
    for case in bundle["cases"]:
        result = dict_value(case["records"].get("result.json"))
        initial = get_initial(case["records"], result)
        supplement = result.get("supplement")
        values = [len(list_value(initial.get("chains"))) if initial is not None else "未获得有效结果",
                  len(list_value(supplement.get("new_chains"))) if isinstance(supplement, dict) else "未获得有效结果",
                  len(list_value(supplement.get("refinements"))) if isinstance(supplement, dict) else "未获得有效结果"]
        parts.append('<tr><td><a href="#case-' + case["task_id"] + '">' + case["task_id"] + '</a></td>'
                     + ''.join('<td>' + esc(v) + '</td>' for v in values) + '<td>'
                     + badge(result.get("status")) + '</td></tr>')
    parts.append('</tbody></table></div><p class="muted">计数只描述保存的有效结构；原始失败输出仍完整保留。旧版仅作描述性历史参照，不是受控 A/B 实验，不能用于归因改进。</p></section>')
    embedded = set()
    parts.extend(render_case(case, case_notes(notes, case["task_id"]), images=bundle["images"], embedded=embedded)
                 for case in bundle["cases"])
    parts.append('<section class="gallery" id="images"><p class="eyebrow">原始图像 · 按字节保留</p><h2>完整原图</h2>'
                 '<p>以下是本轮或历史记录实际包含的图像；相同 SHA-256 只嵌入一次。没有裁剪、重绘或替换标签。</p>')
    for sha, image in bundle["images"].items():
        sources = image["sources"]
        cids = [cid for cid in CASE_IDS if any(re.search(r"[/\\]" + cid + r"[/\\]", p) for p in sources)]
        title = ' / '.join(cids) or "请求内图片"
        if sha in embedded:
            parts.append('<p><a href="#image-' + sha + '">' + esc(title) + ' · 跳转到已嵌入的完整原图</a></p>')
        else:
            parts.append(image_figure(sha, image, title))
            embedded.add(sha)
    parts.append('</section><section id="history"><div class="history-banner"><h2>旧版历史参照</h2>'
                 '<p>以下仅离线读取 2026-09-25 已保存结果与中文注释。新旧使用不同的生成链路、提示与核验定义，只是描述性历史参照，不是受控 A/B 实验；不能据此声称性能提升、因果收益或解释完备。旧版记录没有发送给本轮模型。</p>'
                 '<p>旧版允许支持缺口／无法确定类型的链；这里保留其原始类型与旧版核验字段，不转换成新版结果。</p></div>')
    if bundle["history"]["available"]:
        parts.append('<details class="history-wrapper"><summary>展开 b001、b002、pub013 的旧版完整流程与审查记录</summary>')
        for case in bundle["history"]["cases"]:
            old_notes = case_notes(bundle["history"]["notes_zh"], case["task_id"])
            new_notes = case_notes(notes, case["task_id"])
            if new_notes.get("history_chains"):
                old_notes = dict(old_notes, chains=new_notes["history_chains"])
            parts.append(render_case(case, old_notes, historical=True))
        parts.append('</details>')
    else:
        parts.append(paragraph("历史运行目录缺失，未构造历史结果。", "warning"))
    parts.append('</section><section class="metadata" id="sources"><h2>成本、来源与完整记录</h2>'
                 '<p>本页面生成过程只读取本地工件并整理中文，不调用模型、浏览器或翻译接口。计费估算以原始预算记录为准；没有实际账单字段时，不将估算当成已支付金额。</p>'
                 '<p>打包文件 RESULTS_FULL.json 保留全部案例 JSON 字段及模型原文；只将图片数据替换成可核对的哈希引用。PROVENANCE.json 保存已读取源文件的哈希与字节数。英文输出未因展示需要而修正。</p>'
                 + paragraph("本轮目录：" + bundle["source_directory"], "source")
                 + paragraph("历史目录：" + bundle["history"]["source_directory"], "source")
                 + paragraph("中文注释：" + str(bundle["notes_source"]), "source"))
    for name, value in metadata.items():
        parts.append(raw_block(name + (" · 缺失" if value is None else " · 完整记录"), value))
    parts.append(raw_block("来源文件 SHA-256 与字节数", bundle["source_files"]))
    parts.append(raw_block("本轮完整中文离线注释", notes))
    parts.append('</section><footer>页面生成时间：' + esc(bundle["created_at"])
                 + '。结构校验、模型核验与独立正确性结论是不同层次；页面不自动授权任何业务操作。</footer></main></div></body></html>')
    return ''.join(parts)


def portable_bundle(bundle):
    """Drop base64 only in the portable JSON; it is embedded once in the HTML."""
    result = dict(bundle)
    result["images"] = {sha: {k: v for k, v in record.items() if k != "data_base64"}
                        for sha, record in bundle["images"].items()}
    return result


def write_delivery(run, output, notes=None, history_run=None, history_notes=None):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing output directory: " + str(output))
    bundle = load_bundle(run, notes, history_run, history_notes)
    page = render_html(bundle)
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "EXPLANATION_COMPLETION_V3_REVIEW.html": page,
        "RESULTS_FULL.json": json.dumps(portable_bundle(bundle), ensure_ascii=False, indent=2) + "\n",
        "PROVENANCE.json": json.dumps({"created_at": bundle["created_at"], "source_files": bundle["source_files"],
            "limits_zh": bundle["limits_zh"], "image_policy_zh": bundle["image_policy_zh"]}, ensure_ascii=False, indent=2) + "\n",
    }
    for name, content in artifacts.items():
        with (output / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return {"output": str(output), "files": [str(output / name) for name in artifacts],
            "unique_images": len(bundle["images"]), "source_files": len(bundle["source_files"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="A new directory; existing output is never overwritten")
    parser.add_argument("--notes", type=Path, default=None)
    args = parser.parse_args(argv)
    print(json.dumps(write_delivery(args.run, args.output, args.notes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
