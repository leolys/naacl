"""Offline viewer for conclusion-search phases; no inference or artifact repair."""

import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / "alternative_conclusion_20260926" / "build_review.py"
spec = importlib.util.spec_from_file_location("historical_offline_review_helpers", HELPER)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

PHASES = {
    "main": "主面板：四种搜索方案／完整页面截图",
    "chart": "附加诊断：方法阶段使用公开完整原图",
    "transfer": "静态迁移：两个其他任务，没有 Actor",
    "contract": "附加诊断：完整候选输出契约模板",
    "isolated": "混合续接：GUI 候选发现去执行上下文／静态契约首次续接",
    "joint": "纯候选诊断：通用反问与新链同次生成（无核验／Actor）",
}
STRATEGIES = {
    "action_conclusion_only": "仅已有行动结论（去除原 O/B 与论据）",
    "option_search": "逐公开选项进行结论搜索",
    "fresh_search": "不提供旧解释集合的独立搜索",
    "symmetric_hypotheses": "逐公开选项对称假设",
    "contract_hypotheses": "逐选项假设＋完整 OBC 输出契约",
    "joint_discovery": "程序通用反问＋模型自选其他结论并直接成链",
}
CASES = {"official140": "已知开发例／误导图", "clean140": "已知开发例／正常图",
         "b002": "浏览器任务／静态图表诊断", "pub013": "州风险任务／静态图表诊断"}


def obj(value):
    return value if isinstance(value, dict) else {}


def phase_collect(path, key):
    if path is None or not Path(path).is_dir():
        return {"key": key, "path": str(path) if path else None, "available": False,
                "status": "未运行或未提供本地工件"}, None
    root = Path(path).resolve()
    collector = ui.Collector(root)
    collector.read_pngs()
    files = {}
    for source in sorted(root.rglob("*.json")):
        if "runtime_source" in source.relative_to(root).parts:
            continue
        files[source.relative_to(root).as_posix()] = collector.load(source)
    cases = {}
    expected = ("b002", "pub013") if key == "transfer" else ("official140", "clean140")
    if key in ("contract", "isolated", "joint"):
        expected = ("official140", "clean140", "b002", "pub013")
    case_names = sorted(set(expected) | {folder.name for folder in root.iterdir()
                                       if folder.is_dir() and folder.name in CASES})
    for case_name in case_names:
        folder = root / case_name
        result = obj(files.get(folder.name + "/result.json"))
        initial = result.get("initial")
        if initial is None:
            initial = files.get(folder.name + "/shared_initial.json")
        if initial is None:
            initial = files.get(folder.name + "/shared_initial/accepted.json")
        branches = {}
        branch_names = list(obj(result.get("branches")))
        branch_names += [name for name in STRATEGIES if (folder / name).is_dir() and name not in branch_names]
        for name in branch_names:
            branch_dir = folder / name
            branch_result = obj(result.get("branches")).get(name)
            if branch_result is None:
                branch_result = files.get(folder.name + "/" + name + "/result.json")
            branches[name] = {"result": branch_result, "session": collector.session(branch_dir),
                              "calls": {call.name: collector.call(call) for call in sorted(branch_dir.iterdir())
                                        if call.is_dir() and any(call.glob("*.json"))} if branch_dir.is_dir() else {}}
        cases[folder.name] = {
            "result": result, "initial": initial, "branches": branches,
            "static_diagnostic": key == "joint" or folder.name in ("b002", "pub013"),
            "result_record_exists": folder.name + "/result.json" in files,
            "request_record_count": sum(1 for name in files if name.startswith(folder.name + "/")
                                        and name.endswith("/request.json")),
            "checkpoint": files.get(folder.name + "/source_checkpoint.json"),
            "reuse_provenance": files.get(folder.name + "/reuse_provenance.json"),
            "public_context": files.get(folder.name + "/public_context.json"),
            "images": {str(p.relative_to(folder).as_posix()): ui.sha(p.read_bytes()) for p in sorted(folder.rglob("*.png"))},
        }
    return {"key": key, "path": str(root), "available": True, "summary": files.get("summary.json"),
            "config": files.get("config.json"), "ledger": files.get("ledger.json"), "cases": cases,
            "files": files, "read_issues": collector.issues}, collector


def response_content(call):
    """Return a parsed original output if possible, without accepting or repairing it."""
    records = obj(obj(call).get("records"))
    if isinstance(records.get("accepted.json"), dict):
        return records["accepted.json"], True
    raw = obj(records.get("raw.json")).get("content")
    if raw is None:
        names = sorted(name for name in records if name.startswith("response_"))
        if names:
            response = obj(records[names[-1]])
            choices = response.get("choices", [])
            if choices:
                raw = obj(obj(choices[0]).get("message")).get("content")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        parsed = None
    return parsed, False


def branch_parts(branch):
    result = obj(branch.get("result"))
    stages = obj(result.get("stages"))
    calls = obj(branch.get("calls"))
    questions = stages.get("questions")
    if questions is None:
        questions = ui.accepted(calls.get("questions"))
    supplement = stages.get("supplement")
    if supplement is None:
        supplement = ui.accepted(calls.get("supplement"))
    hypotheses = stages.get("hypotheses")
    verification = stages.get("verification")
    if verification is None:
        verification = ui.accepted(calls.get("verification"))
    return result, calls, questions, supplement, hypotheses, verification


def added_chains(branch):
    _, _, _, supplement, hypotheses, _ = branch_parts(branch)
    if isinstance(hypotheses, dict) and "new_chains" in hypotheses:
        return hypotheses["new_chains"]
    if isinstance(supplement, dict) and "new_chains" in supplement:
        return supplement["new_chains"]
    return None


def is_static(case):
    return case.get("static_diagnostic") or obj(case.get("result")).get("mode") == "static_public_task_transfer"


def design_label(phase, case, strategy=None):
    """The final run mixes different interventions; never relabel static as V7."""
    if phase == "isolated":
        if is_static(case):
            return "静态契约版首次工程续接（第六方案；不是去历史迁移）"
        return "候选发现去执行上下文（第七方案；GUI）"
    return STRATEGIES.get(strategy, strategy) if strategy is not None else PHASES[phase]


def question_count(name, branch, case):
    _, calls, questions, _, hypotheses, _ = branch_parts(branch)
    if name == "joint_discovery":
        return ("程序通用反问；模型同次自选结论并成链（没有先行问题生成调用）"
                if calls.get("discovery") else "程序通用反问；未找到实际发现请求")
    if name in ("symmetric_hypotheses", "contract_hypotheses"):
        actual = sum(1 for folder in calls if folder.startswith("hypothesis_"))
        expected = len(obj(case.get("public_context")).get("options", []))
        if not expected:
            checkpoint = obj(case.get("checkpoint"))
            for select in obj(obj(checkpoint.get("state")).get("elements")).get("selects", []):
                if select.get("name") == "primary_action":
                    expected = sum(1 for item in select.get("options", []) if item.get("value") and not item.get("disabled"))
        if not expected:
            expected = len(obj(hypotheses).get("hypotheses", [])) or "数量未记录"
        return "程序模板{}项；实际请求{}项（没有生成问题的模型调用）".format(expected, actual)
    if isinstance(questions, dict) and isinstance(questions.get("questions"), list):
        return "模型生成{}问".format(len(questions["questions"]))
    return "未运行／未接纳问题输出"


def notes_for(annotations, phase, case=None, branch=None):
    note = obj(obj(annotations.get("phases")).get(phase))
    if case is not None:
        note = obj(obj(note.get("cases")).get(case))
    if branch is not None:
        note = obj(obj(note.get("branches")).get(branch))
    return note


def image_gallery(images):
    body = ['<h2 id="images">全部原始图像（按字节哈希去重）</h2>',
            '<p>步骤链接指向真实输入图像。完整页面和公开原图分别保留；没有重新绘图或拼造截图。</p>']
    for digest, image in images.items():
        body.append('<figure id="image-' + digest + '"><figcaption>SHA-256 ' + digest + '<br>' +
                    '<br>'.join(ui.escaped(source) for source in image["sources"]) +
                    '</figcaption><img loading="lazy" alt="归档原始图像" src="data:' + image["mime"] +
                    ';base64,' + image["data"] + '"></figure>')
    return ''.join(body)


def hypothesis_html(calls, note):
    folders = [(name, call) for name, call in calls.items() if name.startswith("hypothesis_")]
    if not folders:
        return '<p class="missing">未发现逐选项假设请求；不把它写成零链模型响应。</p>'
    parts = ['<p>以下是假设模板按公开选项逐一调用，不是模型自由生成了这些反问。空 chains 仍是实际响应；notes 不自动转写为结构链。</p>']
    for name, call in folders:
        context = obj(obj(call.get("records")).get("context.json"))
        response, accepted = response_content(call)
        response = obj(response)
        parts.append('<article class="chain"><h4>' + ui.escaped(name) + '：' +
                     ui.escaped(context.get("hypothesis_option", "假设选项未记录")) + '</h4>')
        parts.append('<p>模板问题：' + ui.escaped(context.get("search_question", "见完整请求")) + '</p>')
        parts.append('<p>' + ("已被接口接纳；不等于语义正确。" if accepted else
                     '<span class="missing">未被接口接纳的原始响应／草稿；不能计入新增链。</span>') + '</p>')
        if "chains" in response:
            parts.append('<p>本次模型返回 chains 数量：' + str(len(response["chains"])) + '</p>')
            parts.append(ui.chains_html(response["chains"], {}))
        else:
            parts.append('<p class="missing">没有可解析的 chains 字段；原响应完整保留在下方。</p>')
        parts.append('<h5>模型 notes 原文（空链时也必须审阅）</h5><p>' +
                     ui.escaped(response.get("notes", "未记录")) + '</p>')
        parts.append(ui.notes_html(obj(obj(note.get("hypotheses")).get(name))))
        parts.append(ui.call_html(call, name + " 完整请求与响应") + '</article>')
    return ''.join(parts)


def discovery_html(branch):
    result = obj(branch.get("result"))
    stage = obj(obj(result.get("stages")).get("discovery"))
    call = obj(branch.get("calls")).get("discovery")
    response = stage.get("response")
    if response is None:
        response, accepted = response_content(call)
    else:
        accepted = isinstance(ui.accepted(call), dict)
    parts = ['<div class="notice">这是程序提供的一条通用反问，由模型在同一次请求中自行寻找其他可能结论并输出 OBC。没有模型先生成问题的阶段；stages.supplement 只是新增链的存储字段，不代表又执行了旧补充调用。</div>',
             '<h4>程序通用反问与单次候选发现</h4>']
    if stage.get("program_counterquestion"):
        parts.append('<p>' + ui.escaped(stage["program_counterquestion"]) + '</p>')
    if response is None:
        parts.append('<p class="missing">未记录可解析的发现响应；原始请求响应见下方。</p>')
    else:
        parts.append('<p>' + ("结构已接纳；不是语义核验。" if accepted else "未被接口接纳的原始草稿，不计入正式新增集合。") + '</p>')
        parts.append(ui.chains_html(obj(response).get("chains"), {}))
        parts.append('<h5>发现响应 notes 原文</h5><p>' + ui.escaped(obj(response).get("notes", "未记录")) + '</p>')
    parts.append(ui.call_html(call, "单次 discovery 完整提示、上下文与响应"))
    return ''.join(parts)


def historical_reference(main_path):
    """Load an existing historical baseline for reference only; no recomputation."""
    root = Path(main_path).resolve().parent.parent / "alternative_conclusion_20260926" / "run_live_002"
    rows = {}
    for arm in ("official140", "clean140"):
        path = root / arm / "result.json"
        if path.exists():
            try:
                result = json.loads(path.read_text(encoding="utf-8-sig"))
                original = obj(result.get("branches")).get("original_submit")
                if original:
                    rows[arm] = {"source": str(path), "sha256": ui.sha(path.read_bytes()), "result": original}
            except (ValueError, UnicodeDecodeError):
                rows[arm] = {"source": str(path), "status": "历史文件无法解析"}
    return rows


def render(phases, images, annotations, history):
    annotations = obj(annotations)
    body = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>结论搜索：多方案解释链与真实执行审阅</title><style>',
        'body{max-width:1360px;margin:auto;padding:24px;background:#f2f5f8;color:#203044;font:16px/1.65 system-ui,sans-serif}h1,h2,h3,h4,h5{line-height:1.35}h2{border-top:3px solid #3b6184;padding-top:20px;margin-top:44px}.notice,.translation{background:#e5edf8;border-left:4px solid #3c6392;padding:14px;margin:16px 0}.missing{color:#a12626;font-weight:600}.chain,.step,figure{background:white;padding:16px;border:1px solid #d4dde7;border-radius:7px;margin:16px 0}table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:14px;background:white}td,th{padding:9px;border:1px solid #d0d9e4;vertical-align:top;overflow-wrap:anywhere}th{background:#e3ebf4}pre{white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;background:#f5f7fa;padding:12px;font:13px/1.5 Consolas,monospace}details{margin:10px 0}summary{cursor:pointer;color:#2e567e}img{max-width:100%;height:auto}a{color:#2b618f;overflow-wrap:anywhere}figure{scroll-margin-top:16px}figcaption{font-size:13px;overflow-wrap:anywhere}.conclusion{background:#edf4e7;padding:10px}nav a{display:inline-block;margin:4px 16px 4px 0}@media(max-width:720px){body{padding:10px}table{font-size:11px}td,th{padding:4px}}</style></head><body>',
        '<h1>结论搜索：多方案 OBC、反问与执行审阅</h1>',
        '<div class="notice">这是已知开发例上的自适应开发诊断，不是独立留出评测。主面板复用历史真实提交前 checkpoint 和初始解释，并非新采样自然前缀。附加阶段是在看到先前结果后确定的，不能混作一次预注册的公平排名。静态迁移只有候选／核验，没有 Actor 或提交。</div>',
        '<p>结构接纳只表示格式及关联符合接口，不表示观察正确或结论成立。notes 中出现正确说法也不等于形成完整结构链，更不自动证明“竞争链促成纠错”。所有英语模型内容原样保留；中文备注仅来自可选离线注释。</p>',
        '<nav><a href="#table">总表</a>' + ''.join('<a href="#' + key + '">' + value + '</a>' for key, value in PHASES.items()) + '<a href="#history">上一轮参考</a><a href="#images">原图图库</a></nav>',
        ui.notes_html(annotations), '<h2 id="table">分阶段结果：新增链、真实动作和提交分开</h2>']
    rows = []
    for phase_key, phase in phases.items():
        for case_key, case in obj(phase.get("cases")).items():
            if not case.get("result_record_exists") and not case.get("branches"):
                state = "未记录模型请求；未运行／工件缺失，不是模型能力失败" if not case.get("request_record_count") else "有请求记录，但缺少完整结果；不推测成功或失败"
                rows.append('<tr><td>' + ui.escaped(PHASES[phase_key]) + '</td><td>' + ui.escaped(CASES.get(case_key, case_key)) +
                            '</td><td>' + ui.escaped(design_label(phase_key, case)) + '</td><td colspan="5">' + ui.escaped(state) + '</td></tr>')
            for name, branch in case["branches"].items():
                result = obj(branch.get("result"))
                added = added_chains(branch)
                submitted = "不适用：静态无 Actor" if is_static(case) else ("是" if result.get("submitted") is True else "否" if result.get("submitted") is False else "未记录")
                outcome = "静态候选诊断，无业务评分" if is_static(case) else ui.label(result.get("outcome"))
                anchor = phase_key + "-" + case_key + "-" + name
                rows.append('<tr><td>' + ui.escaped(PHASES[phase_key]) + '</td><td>' + ui.escaped(CASES.get(case_key, case_key)) + '</td><td><a href="#' + ui.escaped(anchor) + '">' +
                            ui.escaped(design_label(phase_key, case, name)) + '</a></td><td>' + ui.escaped(question_count(name, branch, case)) +
                            '</td><td>' + ui.escaped(len(added) if isinstance(added, list) else "未完成聚合／未记录") +
                            '</td><td>' + ui.escaped(submitted) + '</td><td>' + ui.escaped(result.get("final_selection", "不适用" if is_static(case) else "未记录")) +
                            '</td><td>' + ui.escaped(outcome) + '<br>' + ui.escaped(ui.label(result.get("status"))) + '</td></tr>')
    body.append('<table><thead><tr><th>阶段</th><th>任务／条件</th><th>方案</th><th>问题／假设来源</th><th>接纳且聚合的新增链</th><th>真实提交</th><th>最终选项</th><th>原评分／状态</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')
    body.append('<p>后续账本继承前序成本，不能把各阶段累计请求数相加。主表不计上一轮原样提交，不把静态诊断当作未提交失败。</p>')
    for phase_key, phase in phases.items():
        body.append('<h2 id="' + phase_key + '">' + PHASES[phase_key] + '</h2>')
        if not phase.get("available"):
            body.append('<p class="missing">未运行或未提供本地工件；此页不推测结果。</p>')
            continue
        summary = obj(phase.get("summary"))
        body.append(ui.notes_html(notes_for(annotations, phase_key)))
        if summary.get("error"):
            body.append('<div class="missing">本阶段实际中止原因（包括模型请求前的工程守卫，不统一算成模型失败）</div>' + ui.pretty(summary["error"]))
        if phase_key == "isolated":
            body.append('<div class="notice">本目录混合两种运行：两个 GUI 图表条件测试候选发现去执行上下文；两个静态任务只是前一契约版本的首次工程续接，不是该去上下文方案的迁移评测。静态任务不含 Actor，不能与 GUI 提交效果合并。</div>')
        if phase_key == "joint":
            body.append('<div class="notice">本阶段四个输入均为纯候选诊断，包括原 GUI 任务的两个图表条件。只有候选生成，没有独立核验、Actor 续跑、业务提交或新增浏览器操作；不能报告纠错成功／失败。</div>')
        body.append('<p>本阶段状态：' + ui.escaped(summary.get("status", "未记录")) +
                    '；累计请求尝试：' + ui.escaped(summary.get("request_attempts", obj(phase.get("ledger")).get("request_attempts", "未记录"))) +
                    '；阶段新增请求：' + ui.escaped(summary.get("phase_request_attempts", "未单独记录")) +
                    '；累计浏览器操作：' + ui.escaped(summary.get("browser_operations", obj(phase.get("ledger")).get("browser_operations", "未记录"))) + '。</p>')
        body.append(ui.details("冻结配置／运行汇总", ui.pretty({"config": phase.get("config"), "summary": phase.get("summary")})))
        for case_key, case in phase.get("cases", {}).items():
            note = notes_for(annotations, phase_key, case_key)
            body += ['<h3>' + ui.escaped(CASES.get(case_key, case_key)) + '</h3>', ui.notes_html(note)]
            if not case.get("result_record_exists") and not case.get("branches"):
                message = ("本任务没有请求归档且没有结果：未记录运行，不是已执行方法的模型失败。请结合上方阶段中止原因及来源记录。"
                           if not case.get("request_record_count") else
                           "本任务有请求归档但缺少完整结果：保留原始记录，不推测后续阶段。")
                body.append('<p class="missing">' + message + '</p>')
                incomplete_files = {path: value for path, value in phase["files"].items()
                                    if path.startswith(case_key + "/")}
                if incomplete_files:
                    body.append(ui.details("未完成任务的全部现存 JSON（包括失败的初始请求／响应）",
                                           ''.join(ui.details(path, ui.pretty(value))
                                                   for path, value in incomplete_files.items())))
                continue
            if phase_key == "isolated":
                body.append('<p><strong>本项实际设计：' + ui.escaped(design_label(phase_key, case)) + '</strong></p>')
            body.append('<p>' + ("静态公开任务诊断：没有 Actor、浏览器续跑或真实业务提交。" if is_static(case) else
                        "从历史同一公开 checkpoint 重放；不是一次新的自然前缀。内部条件目录名未注入提示文本，但原图既有文字照常可见。") + '</p>')
            for image_name in ("source_checkpoint.png", "public_chart_observation/chart.png", "chart.png"):
                digest = case.get("images", {}).get(image_name)
                if digest:
                    body.append('<p>' + ui.escaped(image_name) + '：' + ui.image_link(digest) + '</p>')
            body.append(ui.details("来源与公开初始状态", ui.pretty({"reuse_provenance": case.get("reuse_provenance"), "checkpoint": case.get("checkpoint"), "public_context": case.get("public_context")})))
            body.append('<h4>共享／复用的初始解释链</h4>')
            body.append(ui.chains_html(obj(case.get("initial")).get("chains"), note.get("initial_chains")))
            body.append('<h5>初始模型 notes 原文</h5><p>' + ui.escaped(obj(case.get("initial")).get("notes", "未记录")) + '</p>')
            for name, branch in case["branches"].items():
                bnote = notes_for(annotations, phase_key, case_key, name)
                result, calls, questions, supplement, hypotheses, verification = branch_parts(branch)
                body += ['<h3 id="' + ui.escaped(phase_key + "-" + case_key + "-" + name) + '">' +
                         ui.escaped(design_label(phase_key, case, name)) + '</h3>', ui.notes_html(bnote)]
                body.append('<p>' + ui.escaped(question_count(name, branch, case)) + '</p>')
                if result.get("error"):
                    body.append('<div class="missing">实际失败记录（不隐瞒、不以其他响应修复）</div>' + ui.pretty(result["error"]))
                if name == "joint_discovery":
                    body.append(discovery_html(branch))
                elif name in ("symmetric_hypotheses", "contract_hypotheses"):
                    body.append(hypothesis_html(calls, bnote))
                else:
                    body.append('<h4>模型实际反问与总结</h4>')
                    if questions is None:
                        body.append('<p class="missing">未运行／未接纳反问输出。</p>')
                    else:
                        body.append(ui.pretty(questions))
                        if not questions.get("questions"):
                            body.append('<p>实际返回零问，不是未调用。后续补充若被跳过，应区别于返回空链。</p>')
                    body.append(ui.call_html(calls.get("questions"), "反问请求与响应"))
                    body.append('<h4>补充回应及未成链原因</h4>' + ui.pretty(supplement))
                    if calls.get("supplement"):
                        body.append(ui.call_html(calls["supplement"], "补充请求与响应"))
                body.append('<h4>实际接纳并加入集合的新链</h4>')
                body.append(ui.chains_html(added_chains(branch), bnote.get("new_chains")))
                if name == "joint_discovery":
                    body.append('<h4>核验与执行：本阶段不运行</h4><p>按设计没有独立核验，不能算核验失败；没有真正续跑或提交，只能审阅生成了什么候选及其局限。</p>')
                else:
                    body.append('<h4>独立请求核验</h4>' + ui.verification_html(verification))
                    body.append(ui.call_html(calls.get("verification"), "核验完整请求与响应"))
                if is_static(case):
                    body.append('<p class="notice">本分支没有 Actor。submitted=false 是诊断设计，不代表业务执行失败；仅报告候选生成／接口／核验结果。</p>')
                else:
                    body.append('<h4>Actor 的实际执行轨迹</h4>' + ui.session_html(branch.get("session"), result.get("continuation")))
                    body.append('<h4>服务器真实提交及原评分</h4>' + ui.pretty({field: result.get(field, "未记录") for field in ("status", "submitted", "final_selection", "outcome", "submission")}))
                body.append(ui.details("分支完整结构记录", ui.pretty(result)))
            relevant = {path: value for path, value in phase["files"].items() if path.startswith(case_key + "/")}
            body.append(ui.details("本任务全部 JSON 工件（包括未接纳草稿与尚未完成的阶段）", ''.join(ui.details(path, ui.pretty(value)) for path, value in relevant.items())))
        controls = {path: value for path, value in phase["files"].items() if path.startswith("nonchart_control/")}
        if controls:
            body.append('<h3>非图表流程／候选输出控制（不是图表结果）</h3>' +
                        ui.details("非图表控制完整请求响应与回执", ''.join(ui.details(path, ui.pretty(value)) for path, value in controls.items())))
        body.append(ui.details("该阶段完整成本账本与读取异常", ui.pretty({"ledger": phase.get("ledger"), "read_issues": phase.get("read_issues")})))
    body.append('<h2 id="history">上一轮原样提交：仅作历史参考</h2><p>下列记录不是本轮新提交，不能加入本轮请求／分支成功数量。</p>')
    body.append(ui.pretty(history) if history else '<p>未加载旧结果。当前页面的来源 checkpoint 不等于本轮重新采样或重新执行旧 baseline。</p>')
    body.append(image_gallery(images))
    body.append('<footer><p>离线生成，无 API 调用、JavaScript、CDN 或远程图片依赖。所有模型文字均经 HTML 转义；原始 JSON 中图像数据只替换为哈希引用，原运行目录未修改。</p></footer></body></html>')
    return ''.join(body)


def build(run, output, chart_run=None, transfer_run=None, contract_run=None, annotations=None, isolated_run=None, joint_run=None):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Do not overwrite an existing review: " + str(output))
    if not Path(run).is_dir():
        raise NotADirectoryError(str(run))
    paths = {"main": run, "chart": chart_run, "transfer": transfer_run, "contract": contract_run, "isolated": isolated_run, "joint": joint_run}
    for path in paths.values():
        if path and (Path(path).resolve() == output or Path(path).resolve() in output.parents):
            raise ValueError("Review must stay outside immutable run directories")
    phases, images, source_files = {}, {}, {}
    for key, path in paths.items():
        phase, collector = phase_collect(path, key)
        phases[key] = phase
        if collector:
            source_files[key] = collector.files
            for digest, item in collector.images.items():
                if digest not in images:
                    images[digest] = {**item, "sources": []}
                images[digest]["sources"] += [key + "/" + source for source in item["sources"]]
    note = json.loads(Path(annotations).read_text(encoding="utf-8-sig")) if annotations else {}
    history = historical_reference(run)
    document = render(phases, images, note, history)
    output.mkdir(parents=True, exist_ok=False)
    page = output / "CONCLUSION_SEARCH_REVIEW.html"
    page.write_text(document, encoding="utf-8")
    bundle = {"phases": phases, "historical_reference_only": history,
              "images": {digest: {key: value for key, value in item.items() if key != "data"} for digest, item in images.items()}}
    (output / "RESULTS_FULL.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    provenance = {"inputs": source_files, "builder_sha256": ui.sha(Path(__file__).read_bytes()),
                  "helper_sha256": ui.sha(HELPER.read_bytes()), "html_sha256": ui.sha(page.read_bytes()),
                  "model_calls_by_viewer": 0, "annotation_path": str(annotations) if annotations else None,
                  "annotation_sha256": ui.sha(Path(annotations).read_bytes()) if annotations else None}
    (output / "PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--chart-run", type=Path)
    parser.add_argument("--transfer-run", type=Path)
    parser.add_argument("--contract-run", type=Path)
    parser.add_argument("--isolated-run", type=Path)
    parser.add_argument("--joint-run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    print(build(args.run, args.output, args.chart_run, args.transfer_run, args.contract_run, args.annotations,
                isolated_run=args.isolated_run, joint_run=args.joint_run))


if __name__ == "__main__":
    main()
