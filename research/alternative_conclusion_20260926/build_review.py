"""Offline, self-contained, escaped HTML review of the frozen diagnostic.

No model calls, browser actions, scores, or missing explanations are generated.
Large request images are replaced by SHA-256 references and embedded once.
"""

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path


ARMS = {"official140": "原始发布图表条件", "clean140": "正常图表条件"}
BRANCHES = {
    "original_submit": "原 Agent 自然提交（无附加核查）",
    "initial_only": "只用初始解释链＋同模型独立请求核验",
    "old_questions": "旧思路反问适配：观察／条件／覆盖",
    "alternative_conclusion": "新反问：其他具体结论先行",
}
STATUS = {"supported": "有支持", "refuted": "有反证", "uncertain": "尚不能确定适用性／支持",
          "valid": "给定前提下推导成立", "invalid": "推导不成立", "incomplete": "缺少推导前提",
          "success": "原评分：成功", "irrelevant_action_failure": "原评分：无关行动失败",
          "not_submitted": "未真实提交", "completed": "已完成", "started": "已开始，未记录完成",
          "failed_no_quality_retry": "阶段失败，未作质量重试",
          "actor_finished_or_call_limit": "Actor 结束或达到调用上限，未提交"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def escaped(value):
    return html.escape(str(value), quote=True)


def pretty(value):
    return '<pre>' + escaped(json.dumps(value, ensure_ascii=False, indent=2)) + '</pre>'


def details(title, body):
    return '<details><summary>' + escaped(title) + '</summary>' + body + '</details>'


def label(value):
    return STATUS.get(value, value) if value is not None else "未记录"


class Collector:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.files = {}
        self.images = {}
        self.issues = []

    def rel(self, path):
        return Path(path).relative_to(self.root).as_posix()

    def load(self, path, required=False):
        path = Path(path)
        if not path.exists():
            if required:
                self.issues.append({"path": self.rel(path), "status": "missing"})
            return None
        raw = path.read_bytes()
        self.files[self.rel(path)] = {"sha256": sha(raw), "bytes": len(raw)}
        try:
            return self.sanitize(json.loads(raw.decode("utf-8-sig")), self.rel(path))
        except (ValueError, UnicodeDecodeError) as exc:
            issue = {"path": self.rel(path), "status": "invalid_json", "error": str(exc)}
            self.issues.append(issue)
            return {"_read_error": issue, "_raw_text": raw.decode("utf-8", errors="replace")}

    def add_image(self, raw, mime, source):
        digest = sha(raw)
        if digest not in self.images:
            self.images[digest] = {"sha256": digest, "mime": mime, "bytes": len(raw),
                                   "sources": [], "data": base64.b64encode(raw).decode("ascii")}
        if source not in self.images[digest]["sources"]:
            self.images[digest]["sources"].append(source)
        return digest

    def sanitize(self, obj, source):
        if isinstance(obj, dict):
            return {key: self.sanitize(value, source) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self.sanitize(value, source) for value in obj]
        if isinstance(obj, str) and obj.startswith("data:image/"):
            try:
                header, encoded = obj.split(",", 1)
                mime = header[5:].split(";", 1)[0]
                if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"} or not header.endswith(";base64"):
                    raise ValueError("unsupported raster data URI")
                digest = self.add_image(base64.b64decode(encoded, validate=True), mime, source + "#request-image")
                return "embedded-image-sha256:" + digest
            except (ValueError, TypeError) as exc:
                self.issues.append({"path": source, "status": "invalid_image_uri", "error": str(exc)})
                return "[invalid image data URI; original request retained on disk]"
        return obj

    def read_pngs(self):
        for path in sorted(self.root.rglob("*.png")):
            if "runtime_source" in path.parts:
                continue
            raw = path.read_bytes()
            source = self.rel(path)
            self.files[source] = {"sha256": sha(raw), "bytes": len(raw)}
            self.add_image(raw, "image/png", source)

    def call(self, folder):
        folder = Path(folder)
        if not folder.exists():
            return None
        records = {}
        for path in sorted(folder.glob("*.json")):
            records[path.name] = self.load(path)
        return {"path": self.rel(folder), "records": records}

    def session(self, folder):
        folder = Path(folder)
        if not folder.exists():
            return None
        return {
            "history": self.load(folder / "history.json"),
            "snapshots": [{"path": self.rel(path), "data": self.load(path),
                           "image_sha256": sha(path.with_suffix(".png").read_bytes())
                           if path.with_suffix(".png").exists() else None}
                          for path in sorted(folder.glob("state_*.json"))],
            "actors": [self.call(path) for path in sorted(folder.glob("actor_*")) if path.is_dir()],
        }

    def collect(self):
        self.read_pngs()
        bundle = {"summary": self.load(self.root / "summary.json", required=True),
                  "config": self.load(self.root / "config.json", required=True),
                  "ledger": self.load(self.root / "ledger.json", required=True), "arms": {}}
        for arm in ARMS:
            folder = self.root / arm
            entry = {"result": self.load(folder / "result.json", required=True),
                     "checkpoint": self.load(folder / "checkpoint.json"),
                     "prefix": self.session(folder / "prefix"),
                     "shared_initial": self.call(folder / "shared_initial"), "branches": {}}
            for branch in BRANCHES:
                if branch == "original_submit":
                    continue
                branch_dir = folder / branch
                entry["branches"][branch] = {
                    "result": self.load(branch_dir / "result.json"),
                    "session": self.session(branch_dir),
                    "replay_check": self.load(branch_dir / "replay_check.json"),
                    "candidate_review": self.load(branch_dir / "candidate_review.json"),
                    "supplement_skipped": self.load(branch_dir / "supplement_skipped.json"),
                    "calls": {stage: self.call(branch_dir / stage)
                              for stage in ("questions", "supplement", "verification")},
                }
            bundle["arms"][arm] = entry
        bundle["images"] = {key: {k: v for k, v in item.items() if k != "data"}
                            for key, item in self.images.items()}
        bundle["read_issues"] = self.issues
        return bundle


def as_dict(value):
    return value if isinstance(value, dict) else {}


def accepted(call):
    return as_dict(as_dict(call).get("records")).get("accepted.json")


def selected_from_snapshot(snapshot):
    state = as_dict(as_dict(snapshot).get("data")).get("state")
    for item in as_dict(as_dict(state).get("elements")).get("selects", []):
        if item.get("name") == "primary_action":
            return item.get("selected_text")
    return None


def image_link(digest, title="查看该时刻完整输入截图"):
    if not digest:
        return '<span class="missing">截图缺失</span>'
    return '<a href="#image-' + escaped(digest) + '">' + escaped(title) + '</a>'


def call_html(call, caption):
    if not call:
        return '<p class="missing">' + escaped(caption) + '：未运行或请求工件缺失；不能认定成功。</p>'
    records = as_dict(call.get("records"))
    body = '<p>归档位置：' + escaped(call.get("path")) + '</p>'
    if "reused_response_origin.json" in records:
        body += '<p class="notice">本步骤复用已保存响应，非新模型调用；只修复基础设施后继续执行。原请求匹配与响应来源见 reused_response_origin.json，旧请求成本仍应计入总账本。</p>'
    if "accepted.json" not in records:
        body += '<p class="missing">没有 accepted.json：未记录结构接纳；以下保留原始输出或错误，不替模型补链。</p>'
    if "request.json" not in records:
        body += '<p class="missing">完整请求未归档／缺失。</p>'
    for name, value in records.items():
        body += details(name, pretty(value))
    return details(caption + "：完整请求、响应与结构接纳记录", body)


def translated_chain(note):
    note = as_dict(note)
    if not note:
        return ""
    parts = ['<div class="translation"><h5>Codex 离线中文翻译／备注（非模型原文，非独立人工确认）</h5>']
    for key, title in (("O", "观察 O"), ("B", "解释规则 B"), ("conditions", "采用条件"), ("C", "候选结论 C")):
        if key not in note:
            continue
        value = note[key]
        parts.append('<strong>' + escaped(title) + '</strong>')
        parts.append('<ul>' + ''.join('<li>' + escaped(x) + '</li>' for x in value) + '</ul>'
                     if isinstance(value, list) else '<p>' + escaped(value) + '</p>')
    parts.append('</div>')
    return ''.join(parts)


def chain_html(chain, notes=None):
    chain = as_dict(chain)
    body = '<article class="chain"><h4>解释链 ' + escaped(chain.get("id", "未记录 ID")) + '</h4>'
    body += '<h5>O｜模型声称的观察（可能含误读／解读；以下为模型原文）</h5><ul>'
    for obs in chain.get("O", []):
        body += '<li><strong>' + escaped(obs.get("location", "未记录位置")) + '</strong>：' + escaped(obs.get("content", "未记录")) + '</li>'
    body += '</ul><h5>B｜解释规则与采用条件（模型原文）</h5><p>' + escaped(as_dict(chain.get("B")).get("rule", "未记录")) + '</p><ul>'
    for condition in as_dict(chain.get("B")).get("conditions", []):
        body += '<li>' + escaped(condition) + '</li>'
    body += '</ul><h5>C｜具体候选结论（模型原文）</h5><p class="conclusion">' + escaped(as_dict(chain.get("C")).get("claim", "未记录")) + '</p>'
    body += '<p>关联公开选项：' + escaped(as_dict(chain.get("C")).get("option_label")) + '；不代表已经执行。</p>'
    return body + translated_chain(notes) + '</article>'


def chains_html(chains, notes):
    if chains is None:
        return '<p class="missing">未记录结构接纳的解释链。</p>'
    if not chains:
        return '<p>实际记录为空：没有生成／接纳新的完整解释链，不补造候选。</p>'
    return ''.join(chain_html(chain, as_dict(notes).get(chain.get("id"))) for chain in chains)


def notes_html(note):
    note = as_dict(note)
    parts = []
    if note.get("overview"):
        parts.append('<p>' + escaped(note["overview"]) + '</p>')
    for field, title in (("questions", "反问中文翻译"), ("assessment", "离线分析备注")):
        if note.get(field):
            parts.append('<h5>' + title + '</h5><ul>' + ''.join('<li>' + escaped(text) + '</li>' for text in note[field]) + '</ul>')
    return '<aside class="translation"><strong>Codex 离线翻译／分析；不是模型原文，也不是独立人工确认。</strong>' + ''.join(parts) + '</aside>' if parts else ''


def session_html(session, continuation=None, prefix=False):
    if not session:
        return '<p class="missing">未找到该分支浏览器轨迹。</p>'
    parts = []
    snapshots = session.get("snapshots", [])
    actors = session.get("actors", [])
    history = session.get("history")
    events = history if prefix and isinstance(history, list) else (continuation if isinstance(continuation, list) else [])
    parts.append('<p>截图为动作前输入 sₜ；动作执行回执对应 sₜ₊₁。最后确认页截图是动作后状态，不应当作最后一次模型输入。</p>')
    for index, call in enumerate(actors):
        records = as_dict(call.get("records"))
        identity = as_dict(records.get("image_identity.json"))
        digest = identity.get("sha256")
        snapshot = next((snap for snap in snapshots if snap.get("image_sha256") == digest), None)
        event = events[index] if index < len(events) else None
        action = records.get("accepted.json")
        parts.append('<article class="step"><h4>模型动作 ' + str(index + 1) + '</h4>')
        parts.append('<p>输入时当前选择：<strong>' + escaped(selected_from_snapshot(snapshot) if snapshot else as_dict(event).get("selection_before", "未记录")) + '</strong> · ' + image_link(digest) + '</p>')
        parts.append('<h5>真实输出动作（未记录则不推测）</h5>' + pretty(action))
        if event:
            parts.append('<h5>对应执行记录</h5>' + pretty(event))
        else:
            parts.append('<p class="missing">没有对应执行回执；动作输出不等于动作已执行。</p>')
        parts.append(call_html(call, "本步骤模型调用") + '</article>')
    if not actors:
        parts.append('<p class="missing">未发现 actor 请求；不将浏览器重放误计为模型续跑。</p>')
    rows = []
    for index, snapshot in enumerate(snapshots):
        data = as_dict(snapshot.get("data"))
        rows.append('<tr><td>' + str(index + 1) + '</td><td>' + escaped(selected_from_snapshot(snapshot)) + '</td><td>' + escaped(data.get("timing")) + '</td><td>' + image_link(snapshot.get("image_sha256"), "完整截图") + '</td><td>' + details(snapshot["path"], pretty(data)) + '</td></tr>')
    parts.append(details("全部状态时间线（包括重放与动作后确认页）", '<table><thead><tr><th>序号</th><th>当前选择</th><th>时序标签</th><th>图</th><th>公开状态与当时历史</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'))
    parts.append(details("浏览器完整真实执行历史（重放也在其中）", pretty(history)))
    return ''.join(parts)


def verification_html(data):
    if data is None:
        return '<p class="missing">未运行／没有结构接纳的核验结果。不能写成核验通过或核验失败。</p>'
    if not data.get("checks"):
        return '<p>核验记录中没有候选检查项。</p>' + pretty(data)
    rows = []
    for item in data["checks"]:
        rows.append('<tr><td>' + escaped(item.get("chain_id")) + '</td><td>' + escaped(label(item.get("O_status"))) + '</td><td>' + escaped(label(item.get("B_status"))) + '</td><td>' + escaped(label(item.get("inference"))) + '</td><td>' + escaped(item.get("reason")) + '<ul>' + ''.join('<li>' + escaped(e) + '</li>' for e in item.get("visible_evidence", [])) + '</ul></td></tr>')
    return '<p>同一模型的另一次请求；没有挑选赢家，不改写原 C。不是独立模型／人工裁决。</p><table><thead><tr><th>链</th><th>O 的图面支持</th><th>B 当前适用性</th><th>给定前提下 C 的推导</th><th>模型原文理由／证据</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table><p>' + escaped(data.get("summary", "")) + '</p>'


def branch_result(entry, name):
    result = as_dict(entry.get("result"))
    value = as_dict(result.get("branches")).get(name)
    if value is not None:
        return value
    return as_dict(as_dict(entry.get("branches")).get(name)).get("result")


def render(bundle, images, notes):
    notes = as_dict(notes)
    config = as_dict(bundle.get("config"))
    summary = as_dict(bundle.get("summary"))
    ledger = as_dict(bundle.get("ledger"))
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>其他结论先行：解释链与执行轨迹审阅</title><style>',
        'body{max-width:1320px;margin:0 auto;padding:24px;background:#f3f5f8;color:#1f2b3a;font:16px/1.65 system-ui,sans-serif}h1,h2,h3,h4,h5{line-height:1.35}h2{margin-top:48px;border-top:3px solid #294b70;padding-top:20px}h3{margin-top:28px}h5{margin:14px 0 6px}.notice,.translation{background:#e8eef9;border-left:4px solid #416b9a;padding:12px 18px;margin:14px 0}.missing{color:#a32929;font-weight:600}.chain,.step,figure{background:white;border:1px solid #d8e0e8;border-radius:8px;padding:16px;margin:14px 0}table{border-collapse:collapse;width:100%;background:white;font-size:14px;table-layout:fixed}td,th{border:1px solid #d3dbe4;padding:10px;vertical-align:top;overflow-wrap:anywhere}th{background:#e4ebf3}pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font:13px/1.5 ui-monospace,Consolas,monospace;background:#f5f7fa;padding:14px;border-radius:5px}details{margin:10px 0}summary{cursor:pointer;color:#254f7d}a{color:#23568b;overflow-wrap:anywhere}img{max-width:100%;height:auto}figure{scroll-margin-top:20px}figcaption{font-size:13px;overflow-wrap:anywhere}.conclusion{background:#f2f8ed;padding:10px}nav a{display:inline-block;margin-right:20px}.muted{color:#5c6874}@media(max-width:720px){body{padding:12px}table{font-size:12px}td,th{padding:5px}}</style></head><body>',
        '<h1>其他具体结论先行：解释链、反问与真实执行</h1>',
        '<div class="notice">这是 1 个已知开发例的两个图表条件，不是独立测试集、完整 benchmark 或泛化成功率。候选结论、核验意见、Actor 执行选择和服务器真实提交分层展示。结构接纳只证明接口格式／引用成立，不证明解释正确。</div>',
        '<nav><a href="#overview">核心结果</a>' + ''.join('<a href="#' + arm + '">' + title + '</a>' for arm, title in ARMS.items()) + '<a href="#gallery">完整截图图库</a><a href="#provenance">成本与工件</a></nav>',
        '<p>请求模型：<strong>' + escaped(config.get("model", "未记录")) + '</strong>；运行状态：' + escaped(summary.get("status", "未记录")) + '；模型请求尝试：' + escaped(ledger.get("request_attempts", summary.get("request_attempts", "未记录"))) + '；浏览器操作：' + escaped(ledger.get("browser_operations", summary.get("browser_operations", "未记录"))) + '。</p>',
        '<h2 id="overview">同一自然提交前状态上的四个分支</h2>',
        '<p>旧反问是旧思路在统一新接口上的适配，并非历史 v3 提示的逐字复现。初始解释链只生成一次供三个附加流程共享；旧／新反问之外的补充、核验和后续 Actor 协议保持一致。无附加核查分支直接执行原 Agent 已经自然提出的提交，不是强迫模型提交。</p>',
        notes_html(notes)]
    rows = []
    for arm, entry in bundle.get("arms", {}).items():
        for branch, title in BRANCHES.items():
            result = as_dict(branch_result(entry, branch))
            stages = as_dict(result.get("stages"))
            questions = as_dict(stages.get("questions")).get("questions")
            supplement = as_dict(stages.get("supplement"))
            added = supplement.get("new_chains")
            submitted = result.get("submitted")
            rows.append('<tr><td>' + escaped(ARMS.get(arm, arm)) + '</td><td><a href="#' + escaped(arm + '-' + branch) + '">' + escaped(title) + '</a></td><td>' + escaped(len(questions) if isinstance(questions, list) else "不适用" if branch in ("initial_only", "original_submit") else "未记录") + '</td><td>' + escaped(len(added) if isinstance(added, list) else "不适用" if branch in ("initial_only", "original_submit") else "未记录") + '</td><td>' + escaped("是" if submitted is True else "否" if submitted is False else "未记录") + '</td><td>' + escaped(result.get("final_selection", "未记录")) + '</td><td>' + escaped(label(result.get("outcome"))) + '<br>' + escaped(label(result.get("status"))) + '</td></tr>')
    parts.append('<table><thead><tr><th>条件</th><th>分支</th><th>实际反问数</th><th>实际新增链</th><th>真实提交</th><th>最终选项</th><th>原评分／流程状态</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')
    for arm, entry in bundle.get("arms", {}).items():
        arm_note = as_dict(as_dict(notes.get("arms")).get(arm))
        result = as_dict(entry.get("result"))
        parts += ['<h2 id="' + arm + '">' + escaped(ARMS.get(arm, arm)) + '</h2>',
                  '<p>内部条件目录标签 ' + escaped(arm) + ' 未注入请求文本；原图中的既有文字照常可见。此处的条件说明用于离线阅览。</p>', notes_html(arm_note),
                  '<h3 id="' + arm + '-original_submit">1．原 Agent 自然前缀与原样提交</h3>',
                  session_html(entry.get("prefix"), prefix=True),
                  details("真实 before-submit checkpoint：当时公开状态、历史和待执行提交", pretty(entry.get("checkpoint"))),
                  details("原样提交：执行回执与离线原评分", pretty(branch_result(entry, "original_submit"))),
                  '<h3>2．三个附加流程共享的初始解释链</h3>']
        initial = result.get("initial") or accepted(entry.get("shared_initial"))
        parts.append(chains_html(as_dict(initial).get("chains"), arm_note.get("initial_chains")))
        if initial:
            parts.append('<p>初始生成备注（原文）：' + escaped(as_dict(initial).get("notes", "未记录")) + '</p>')
        parts.append(call_html(entry.get("shared_initial"), "共享初始生成"))
        for branch in ("initial_only", "old_questions", "alternative_conclusion"):
            branch_data = as_dict(as_dict(entry.get("branches")).get(branch))
            branch_note = as_dict(as_dict(arm_note.get("branches")).get(branch))
            item = as_dict(branch_result(entry, branch))
            stages = as_dict(item.get("stages"))
            calls = as_dict(branch_data.get("calls"))
            parts += ['<h3 id="' + arm + '-' + branch + '">' + escaped(BRANCHES[branch]) + '</h3>', notes_html(branch_note)]
            parts.append(details("同状态重放检查（不是新独立自然前缀）", pretty(branch_data.get("replay_check") or item.get("replay_check"))))
            if branch == "initial_only":
                parts.append('<p>此分支按设计不运行反问与补充，直接核验共享初始集合后交还普通 Actor。</p>')
            else:
                questions = stages.get("questions") or accepted(calls.get("questions"))
                parts.append('<h4>反问原文</h4>')
                if questions is None:
                    parts.append('<p class="missing">反问未运行／没有结构接纳记录。</p>')
                elif not as_dict(questions).get("questions"):
                    parts.append('<p>实际返回零个问题；不是记录缺失。</p>')
                else:
                    parts.append('<ol>' + ''.join('<li><strong>' + escaped(q.get("id")) + '</strong>：' + escaped(q.get("question")) + '</li>' for q in questions["questions"]) + '</ol>')
                if questions:
                    parts.append('<p>原文总结：' + escaped(questions.get("summary", "未记录")) + '</p>')
                parts.append(call_html(calls.get("questions"), "反问阶段"))
                supplement = stages.get("supplement") or accepted(calls.get("supplement"))
                if supplement is None:
                    supplement = as_dict(branch_data.get("supplement_skipped")).get("result")
                parts.append('<h4>反问后实际新增的解释链</h4>')
                parts.append(chains_html(as_dict(supplement).get("new_chains"), branch_note.get("new_chains")))
                parts.append(details("每个问题的实际回应：新增／已覆盖／未形成", pretty(as_dict(supplement).get("question_responses"))))
                if branch_data.get("supplement_skipped"):
                    parts.append(details("补充阶段按零问题规则跳过，未调用模型", pretty(branch_data["supplement_skipped"])))
                else:
                    parts.append(call_html(calls.get("supplement"), "补充阶段"))
            verification = stages.get("verification") or accepted(calls.get("verification"))
            parts += ['<h4>独立请求核验：原 C 保留不改</h4>', verification_html(verification), call_html(calls.get("verification"), "核验阶段"),
                      '<h4>Actor 获得候选与核验后的实际续跑</h4>', session_html(branch_data.get("session"), item.get("continuation")),
                      '<h4>真实提交与原评分</h4>', pretty({key: item.get(key, "未记录") for key in ("status", "submitted", "final_selection", "outcome", "error", "submission")})]
        parts.append(details("该图表条件完整结果记录", pretty(result)))
    parts.append('<h2 id="gallery">完整原始截图图库</h2><p>相同图像字节只内嵌一次。所有步骤的链接按 SHA-256 指向实际输入图；完整页面未裁剪、未重绘。</p>')
    for digest, item in images.items():
        parts.append('<figure id="image-' + digest + '"><figcaption>SHA-256 ' + digest + '<br>' + '<br>'.join(escaped(source) for source in item["sources"]) + '</figcaption><img loading="lazy" alt="归档的完整页面截图" src="data:' + item["mime"] + ';base64,' + item["data"] + '"></figure>')
    parts += ['<h2 id="provenance">成本、运行配置与局限</h2>',
              '<p>此展示只整理已有工件，没有调用模型、翻译 API 或浏览器。中文文字由 Codex 离线整理。原评分只读取服务器提交后的评估记录；没有真实提交不能认定完成。测试通过仅说明工程检查通过。</p>',
              details("运行配置", pretty(config)), details("运行汇总", pretty(summary)), details("全部请求／浏览器成本账本", pretty(ledger)),
              details("读取缺失或异常（保留，不隐瞒）", pretty(bundle.get("read_issues", []))),
              '<p class="muted">页面为静态单文件：无 JavaScript、CDN 或远程依赖；模型输出只作为转义文本显示。</p></body></html>']
    return ''.join(parts)


def build(run, output, notes_path=None):
    run, output = Path(run).resolve(), Path(output).resolve()
    if not run.is_dir():
        raise NotADirectoryError(str(run))
    if output.exists():
        raise FileExistsError("Review output already exists; preserving it: " + str(output))
    if output == run or run in output.parents:
        raise ValueError("Keep generated review outside the immutable run directory")
    collector = Collector(run)
    bundle = collector.collect()
    notes = {}
    notes_identity = None
    if notes_path:
        raw = Path(notes_path).read_bytes()
        notes = json.loads(raw.decode("utf-8-sig"))
        notes_identity = {"path": str(Path(notes_path).resolve()), "sha256": sha(raw)}
    document = render(bundle, collector.images, notes)
    output.mkdir(parents=True, exist_ok=False)
    html_path = output / "EXPLANATION_ALTERNATIVE_REVIEW.html"
    html_path.write_text(document, encoding="utf-8")
    (output / "RESULTS_FULL.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    provenance = {"source_run": str(run), "read_inputs": collector.files,
                  "notes": notes_identity, "builder_sha256": sha(Path(__file__).read_bytes()),
                  "html_sha256": sha(html_path.read_bytes()), "image_count": len(collector.images),
                  "read_issues": collector.issues, "model_calls_by_viewer": 0,
                  "translation": "optional Codex offline notes, not model output or independent human review"}
    (output / "PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return html_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notes", type=Path)
    args = parser.parse_args()
    print(build(args.run, args.output, args.notes))


if __name__ == "__main__":
    main()
