# -*- coding: utf-8 -*-
"""Offline, source-driven view of input changes. No model outputs are imported."""
import argparse
import base64
from datetime import datetime, timezone
import html
import importlib.util
import json
from pathlib import Path

from prepare import HERE, FLOW, read, digest


def guide():
    spec = importlib.util.spec_from_file_location("runtime_zh_guides", FLOW / "translations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # ONLY display-layer summaries; do not carry gold, clean-arm or other fields.
    return {slug: {key: row[key] for key in ("title", "goal", "choices")}
            for slug, row in module.ZH.items()}


TEMPLATE = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="source-sha256" content="@@HASH@@">
<title>140 条原网页任务 · 输入修复对照</title>
<style>
:root{color-scheme:light;--ink:#233c38;--green:#236859;--paper:#f5f4ed;--line:#d7ded8}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 'Microsoft YaHei','Segoe UI',sans-serif}header{padding:22px 28px;background:#fff;border-bottom:1px solid var(--line)}h1{margin:0;font-size:26px}h2{margin:0 0 12px;font-size:22px}h3{margin:12px 0 8px;font-size:17px}p{margin:6px 0 12px}.muted{font-size:12px;color:#65736d}.notice{padding:12px 15px;background:#fff3db;border-left:4px solid #ac7c29;margin:12px 0}.good{background:#e4f1ea;border-color:#2e7860}.layout{display:grid;grid-template-columns:275px minmax(0,1fr);min-height:85vh}aside{padding:18px;border-right:1px solid var(--line);height:calc(100vh - 10px);position:sticky;top:0;overflow:auto}input{width:100%;padding:9px;border:1px solid var(--line);border-radius:6px;font:inherit}button{font:inherit;cursor:pointer;color:inherit;background:white;border:1px solid var(--line);border-radius:6px;padding:8px 12px}.task{display:block;width:100%;text-align:left;margin:7px 0}.task.active{background:#e2efe8;border-color:var(--green)}.task small{display:block;font-size:11px;color:#65736d}main{padding:22px;min-width:0}.panel{padding:20px;background:white;border:1px solid var(--line);border-radius:9px;margin-bottom:16px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}.en{font-size:14px;color:#3e4c49;white-space:pre-wrap;overflow-wrap:anywhere}.chart{display:block;margin:auto;max-width:100%;max-height:650px;object-fit:contain}details{margin:12px 0}summary{cursor:pointer;color:var(--green);font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:600px;overflow:auto;background:#f5f6f2;padding:12px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:9px;overflow-wrap:anywhere}th{background:#eef3ec}ol{padding-left:25px}.pill{display:inline-block;font-size:12px;padding:2px 7px;border:1px solid var(--line);border-radius:5px;margin-right:5px}.old{border-left:3px solid #aa6b40;padding-left:12px}dialog{width:95vw;max-width:1700px;border:1px solid var(--line);border-radius:8px}dialog img{display:block;max-width:100%;margin:auto}.toolbar{display:flex;justify-content:space-between;gap:10px}@media(max-width:850px){.layout{grid-template-columns:1fr}aside{position:static;height:250px;border-right:0}.columns{grid-template-columns:1fr}main{padding:12px}}
</style></head><body>
<header><h1>140 条原网页任务 · 输入修复对照</h1><p>先对齐 Agent 实际应收到的任务，再重新生成解释。原图、原任务与旧实验均保留。</p><div class="notice">本文件是输入审阅版，不包含新模型解释或新防御结果。中文是辅助导读，不会发送给模型；英文公开任务是本轮输入依据。</div><div id="stats"></div><p class="muted">来源：prepared/input_comparison.json · @@HASH@@ · @@TIME@@</p></header>
<div class="layout"><aside><input id="search" placeholder="搜索编号、标题、目标"><p id="count" class="muted"></p><div id="list"></div></aside><main id="content"></main></div>
<dialog id="zoom"><div class="toolbar"><strong>原图，未经修改</strong><button id="close">关闭</button></div><img id="zoomimg"></dialog>
<script id="payload" type="application/json">@@DATA@@</script>
<script>
const data=JSON.parse(document.getElementById('payload').textContent),rows=data.tasks;
let current=decodeURIComponent(location.hash.slice(1))||rows[0].task_slug;
const $=id=>document.getElementById(id),el=(tag,txt,cls)=>{const n=document.createElement(tag);if(txt!==undefined)n.textContent=txt;if(cls)n.className=cls;return n};
function section(title){const n=el('section',undefined,'panel');n.append(el('h3',title));return n}
function jsonBlock(title,value){const d=el('details');d.append(el('summary',title),el('pre',JSON.stringify(value,null,2)));return d}
function textBlock(n,label,value){n.append(el('h3',label),el('div',value,'en'))}
function choose(slug){current=slug;history.replaceState(null,'','#'+slug);renderList();render()}
function renderList(){const q=$('search').value.trim().toLowerCase(),filtered=rows.filter(r=>(r.task_slug+' '+r.guide.title+' '+r.public_after.page_title+' '+r.public_after.user_goal).toLowerCase().includes(q));$('count').textContent='显示 '+filtered.length+' / 140';$('list').replaceChildren();for(const r of filtered){const b=el('button',r.task_slug+' · '+r.guide.title,'task'+(r.task_slug===current?' active':''));b.dataset.slug=r.task_slug;b.append(el('small',r.advisory_flags.length?'保留原网页证据指导，需分层说明':'原网页公开输入对齐'));b.onclick=()=>choose(r.task_slug);$('list').append(b)}}
function render(){const r=rows.find(r=>r.task_slug===current)||rows[0],p=r.public_after,c=$('content');c.replaceChildren();
 const head=section(r.task_slug+' · '+r.guide.title);head.append(el('div',p.page_title,'en'),el('p','解释生成状态：本输入审阅版不展示模型结果','muted'));head.append(el('div','与旧版不同的字段：'+r.changed_fields.join('、'),'muted'));c.append(head);
 const goal=section('修复后的任务目标');goal.append(el('p',r.guide.goal),el('p','上行为中文导读；以下英文逐字取自原网页入口，是模型实际任务目标。','muted'),el('div',p.user_goal,'en'));if(r.advisory_flags.length)goal.append(el('div','原网页仍有指定标注数值等证据指导。这里忠实保留，并不声称该样本完全无提示；详见下方独立审阅标记。','notice'));c.append(goal);
 const chart=section('原始图表');const img=el('img');img.className='chart';img.src=r.image;img.alt='原图 '+r.task_slug;img.onclick=()=>{$('zoomimg').src=r.image;$('zoom').showModal()};chart.append(img,el('p','点击放大。图片未翻译、未重绘、未替换。','muted'));c.append(chart);
 const action=section('原网页选项顺序与真实提交按钮');action.append(el('p',p.primary_field_label,'en'));const choices=el('ol');p.option_labels.forEach((s,i)=>{const li=el('li');if(r.guide.choices.length===p.option_labels.length)li.append(el('div',r.guide.choices[i]));li.append(el('div',s,'en'));choices.append(li)});action.append(choices,el('p','提交按钮：'+p.completion_label),el('p','这里只展示界面定义，不会执行提交；没有模拟执行回执。','muted'));c.append(action);
 const policy=section('原网页公开规则与表单上下文');textBlock(policy,'看板说明',p.chart_reference);for(const t of p.policy_tables){policy.append(el('h3',t.title));const table=el('table'),thead=el('thead'),tr=el('tr');for(const s of t.headers)tr.append(el('th',s));thead.append(tr);table.append(thead);const tb=el('tbody');for(const rr of t.rows){const tr=el('tr');for(const s of rr)tr.append(el('td',s));tb.append(tr)}table.append(tb);policy.append(table)}policy.append(jsonBlock('查看真实公开字段（含选项、必填与初始值）',p.companion_fields),jsonBlock('查看三个页面的实际说明文字',p.page_instructions));c.append(policy);
 const diff=section('旧输入与新输入对照（仅审阅，不发送给模型）');diff.append(el('div','旧结果留在旧工件中；本页没有把旧解释移植到新任务文字下。','notice good'));for(const key of ['page_title','user_goal','completion_label']){const box=el('div',undefined,'columns');const a=el('div',undefined,'old'),b=el('div');textBlock(a,'旧 '+key,r.public_before[key]);textBlock(b,'新 '+key,p[key]);box.append(a,b);diff.append(box)}diff.append(jsonBlock('全部字段变更',r.changes));c.append(diff);
 const trace=section('输入来源与限制');trace.append(el('p','三个页面文字作为一次性静态任务上下文汇总，不冒充 Agent 已自主浏览三个页面。隐藏表单值、评分字段、另一条件均未投影。'),jsonBlock('修复后的完整公开 JSON',p),jsonBlock('逐字段 DOM 来源',r.bindings),jsonBlock('独立审阅标记（不会发送给模型）',r.advisory_flags));c.append(trace)
}
$('search').oninput=renderList;$('close').onclick=()=>$('zoom').close();$('stats').textContent='140 条输入已对齐 · 58 条标题/目标不同 · 140 条需重新生成 · 不含新模型结果';renderList();render();
</script></body></html>'''


def render():
    source = HERE / "prepared/input_comparison.json"
    data, catalog, translations = read(source), read(HERE / "prepared/catalog.json"), guide()
    entries = {r["task_slug"]: r for r in catalog["tasks"]}
    for row in data["tasks"]:
        entry = entries[row["task_slug"]]
        chart = HERE / "prepared" / entry["chart_file"]
        mime = "image/png" if chart.suffix.lower() == ".png" else "image/jpeg"
        row["image"] = "data:" + mime + ";base64," + base64.b64encode(chart.read_bytes()).decode("ascii")
        row["guide"] = translations[row["task_slug"]]
        row["bindings"] = read(HERE / "prepared" / entry["source_file"])["field_bindings"]
    body = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = TEMPLATE.replace("@@DATA@@", body).replace("@@HASH@@", digest(source)).replace("@@TIME@@", datetime.now(timezone.utc).isoformat())
    dest = HERE / "RUNTIME_INPUTS_140_ZH.html"
    dest.write_text(page, encoding="utf-8")
    return dest


def browser_check(path):
    from playwright.sync_api import sync_playwright
    failures, requests, checked = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
        try:
            page = browser.new_page(viewport={"width": 1480, "height": 1040})
            page.on("pageerror", lambda e: failures.append(str(e)))
            page.on("request", lambda r: requests.append(r.url) if r.url.startswith(("http://", "https://")) else None)
            page.goto(path.as_uri())
            assert page.locator(".task").count() == 140
            for entry in read(HERE / "prepared/catalog.json")["tasks"]:
                page.locator('.task[data-slug="' + entry["task_slug"] + '"]').click()
                assert page.locator("img.chart").evaluate("n=>n.complete && n.naturalWidth>0")
                checked.append(entry["task_slug"])
            for slug in ("b001", "pub003", "b014", "env008"):
                page.locator('.task[data-slug="' + slug + '"]').click()
                page.screenshot(path=str(HERE / ("input_view_" + slug + ".png")), full_page=False)
            assert not failures and not requests
        finally:
            browser.close()
    (HERE / "input_browser_check.json").write_text(json.dumps({"status": "PASS", "html_sha256": digest(path),
        "tasks_rendered": checked, "javascript_errors": failures, "external_requests": requests,
        "model_calls": 0, "business_actions": 0}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-check", action="store_true")
    args = parser.parse_args()
    dest = render()
    if args.browser_check:
        browser_check(dest)
    print(str(dest))
