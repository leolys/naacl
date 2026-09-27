# -*- coding: utf-8 -*-
"""Standalone Chinese-interface six-version viewer, retaining real English outputs."""
import argparse
import base64
import json
from pathlib import Path
from evaluate import HERE, VERSIONS, read, sha, state
import hashlib


def optional(path):
    return read(path) if path.exists() else None


def build(capture, analysis, output):
    analysis_summary = read(analysis / 'SUMMARY.json')
    if analysis_summary['source_hashes']['capture/CAPTURE_MANIFEST.json'] != sha(capture / 'CAPTURE_MANIFEST.json'):
        raise ValueError('Analysis is from a different capture')
    units = read(HERE / 'manifest.json')['units']
    labels = read(HERE / 'offline/labels.json')['tasks']
    history = read(HERE / 'offline/old_v3_summary.json')['units']
    evaluations = {v: read(analysis / (v + '.json')) for v in VERSIONS}
    rows = []
    for key, unit in units.items():
        projected = read(HERE / 'data' / key / 'input.json')
        row = {'key': key, 'id': unit['slug'], 'family': unit['family'], 'domain': unit['domain'],
            'previous_dev': unit['panel'] == 'dev', 'input': projected, 'image_sha256': unit['image_sha256'],
            'image': 'data:image/jpeg;base64,' + base64.b64encode((HERE / 'data' / key / unit['image']).read_bytes()).decode(),
            'target': labels[key]['original_correct_label'], 'arms': {},
            'evidence_conflict': unit['slug'] == 'env008'}
        for version in VERSIONS:
            result = evaluations[version]['units'][key]
            run = capture / 'runs' / version / key
            arm = {'result': result, 'state': state(result, labels[key]), 'stages': {}}
            for stage in ('read', 'verify', 'decide'):
                root = run / stage
                request = optional(root / 'request.json')
                if not request:
                    continue
                context = optional(root / 'context.json')
                if json.loads(request['messages'][1]['content'][0]['text']) != context:
                    raise ValueError('Displayed context is not the actual request')
                image_bytes = base64.b64decode(request['messages'][1]['content'][1]['image_url']['url'].split(',', 1)[1], validate=True)
                if hashlib.sha256(image_bytes).hexdigest() != unit['image_sha256']:
                    raise ValueError('Request uses a different image')
                arm['stages'][stage] = {'system': request['messages'][0]['content'],
                    'context': context, 'accepted': optional(root / 'accepted.json'),
                    'failure': optional(root / 'failure.json'), 'schema': request['structured_outputs']['json'],
                    'responses': [read(p) for p in sorted(root.glob('response_*.json'))],
                    'request_sha256': sha(root / 'request.json'),
                    'image_identity': optional(root / 'image_identity.json'),
                    'owner': optional(root / 'owner.json'),
                    'parameters': {k: request[k] for k in ('model', 'temperature', 'top_p', 'top_k', 'seed', 'max_tokens', 'chat_template_kwargs')}}
            row['arms'][version] = arm
        row['historical_v3'] = {'result': history[key], 'state': state(history[key], labels[key])}
        rows.append(row)
    payload = {'rows': rows, 'summary': analysis_summary, 'evaluations': evaluations,
               'protocol': (HERE / 'PROTOCOL.md').read_text(encoding='utf-8'),
               'report': (HERE / 'REPORT.md').read_text(encoding='utf-8') if (HERE / 'REPORT.md').exists() else '完整分析尚未形成。',
               'versions': (HERE / 'VERSION_GUIDE.md').read_text(encoding='utf-8') if (HERE / 'VERSION_GUIDE.md').exists() else ''}
    encoded = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    output.mkdir(parents=True, exist_ok=False)
    page = output / 'OB_FULL_COMPARISON_REVIEW.html'
    page.write_text(TEMPLATE.replace('@@DATA@@', encoded), encoding='utf-8')
    print(json.dumps({'path': str(page), 'cases': len(rows), 'bytes': page.stat().st_size, 'sha256': sha(page)}, ensure_ascii=False))


TEMPLATE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>140条 · 六配置全量比较</title><style>
:root{--ink:#17313a;--muted:#59707a;--line:#d7e2e5;--accent:#006d77;--bg:#edf3f4}*{box-sizing:border-box}
body{margin:0;font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
header{background:#193c48;color:#fff;padding:30px 4vw}h1{font-size:28px;margin:0}h2{font-size:22px}h3{font-size:19px}
main{max-width:1650px;margin:auto;padding:20px}section,.card{background:#fff;border:1px solid var(--line);border-radius:9px;padding:20px;margin-bottom:18px;min-width:0}
nav{position:sticky;top:0;z-index:3;background:#edf3f4f5;padding:12px 0;display:flex;gap:8px;flex-wrap:wrap}
input,select,button{font:inherit;padding:7px 9px;border:1px solid #9aafb5;border-radius:5px;background:white;min-width:0;max-width:100%}
#case{flex:1 1 260px}button{cursor:pointer}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}
.muted{color:var(--muted)}.small{font-size:13px;overflow-wrap:anywhere}.warning{background:#fff4de;border-left:4px solid #b77b20;padding:12px}
.chart{display:block;margin:auto;max-width:100%;max-height:650px;object-fit:contain}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:950px;font-size:14px}td,th{padding:9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.badge{padding:3px 8px;border-radius:5px;font-size:13px;background:#edf0f1}.target{background:#dcf1e6}.trap,.other{background:#ffe6df}.no_option,.interface_failed,.not_completed{background:#fff0c9}
details{border-top:1px solid var(--line);padding:12px 0}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui,sans-serif;background:#f3f6f7;padding:12px;border-radius:5px}
.choice{overflow-wrap:anywhere}a{color:var(--accent)}@media(max-width:700px){main{padding:10px}header{padding:22px}.grid{grid-template-columns:1fr}h1{font-size:23px}}@media print{nav{display:none}}
</style><header><h1>140 条原任务 · 六配置全量比较</h1><p>普通直接选择、原 v3、v4、v5、v6、v7 · 同一 Qwen3.8-27B · 每条六版同副本</p><p>离线单文件；中文界面与统计说明，模型实际输出保留英语原文，未用翻译 API。</p></header>
<main><section id="overview"></section><nav><input id="query" aria-label="搜索编号或家族" placeholder="任务编号 / 家族"><select id="method" aria-label="比较配置"></select><select id="panel" aria-label="任务子集"><option value="all">全部140条</option><option value="dev">原24条开发样本</option><option value="rest">其余116条</option></select><select id="filter" aria-label="结果筛选"><option value="all">全部结果</option><option value="gain">相对普通方案新增相合</option><option value="loss">相对普通方案丢失相合</option><option value="wrong">原普通方案错误→原目标</option><option value="null">当前空选项</option><option value="failed">当前接口失败或未完成</option></select><select id="case" aria-label="选择任务"></select><button id="prev">上一条</button><button id="next">下一条</button></nav><div id="body"></div></main>
<script id="data" type="application/json">@@DATA@@</script><script>
const D=JSON.parse(document.querySelector('#data').textContent),$=s=>document.querySelector(s);
const names={plain:'普通直接选择',v3:'原核验 v3（本轮重新运行）',v4:'可见参照核验 v4',v5:'范围与条件实测 v5',v6:'逐条件核验 v6',v7:'v4核验＋范围决策 v7'};
const states={target:'与原目标标签相合',trap:'选中原误导选项',other:'选中其他原选项',no_option:'返回空选项',interface_failed:'接口或结构失败',not_completed:'未完成'};
const stages={read:'第一步：独立观察（未输入旧候选）',verify:'第二步：核验已有 O 与 B',decide:'第三步：重新选择（不执行网页提交）'};
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty=x=>esc(typeof x==='string'?x:JSON.stringify(x,null,2));
const count=(c,k)=>c[k]||0;
$('#method').innerHTML=Object.keys(names).filter(v=>v!=='plain').map(v=>`<option value="${v}">${esc(names[v])}</option>`).join('');$('#method').value='v5';
function summaryTable(panel){let html='<div class="scroll"><table><tr><th>配置</th><th>原目标相合</th><th>误导</th><th>其他</th><th>空选项</th><th>接口失败</th><th>未完成</th><th>较普通方案净变化</th><th>较本轮原v3净变化</th></tr>';
for(const [v,e] of Object.entries(D.evaluations)){const p=e.panels[panel],c=p.counts;html+=`<tr><td>${esc(names[v])}</td><td>${count(c,'target')} / ${p.n} (${(100*count(c,'target')/p.n).toFixed(1)}%)</td><td>${count(c,'trap')}</td><td>${count(c,'other')}</td><td>${count(c,'no_option')}</td><td>${count(c,'interface_failed')}</td><td>${count(c,'not_completed')}</td><td>${p.vs_plain.net_target}</td><td>${p.vs_fresh_v3.net_target}</td></tr>`}return html+'</table></div>'}
let cost='<details><summary>实际成本（主方法与服务检查分开）</summary><div class="scroll"><table><tr><th>配置</th><th>请求尝试</th><th>重试</th><th>已知 token</th><th>未知用量请求</th></tr>';
for(const [v,c] of Object.entries(D.summary.costs)){cost+=`<tr><td>${esc(names[v]||'服务控制检查')}</td><td>${c.attempts}</td><td>${c.retry_attempts}</td><td>${c.known_usage.total_tokens||0}</td><td>${c.unknown_usage_attempts}</td></tr>`}cost+='</table></div></details>';
$('#overview').innerHTML=`<h2>六版整体结果</h2><p class="warning">${D.summary.all840_terminal&&D.summary.all_workers_finished?'840个配置单元均已结束（包括接口失败）':'这是未完成面板的快照，不是最终效果。'} ${D.summary.runtime_preserved_all?'四路运行均记录封存身份保持。':'尚未确认全部运行的封存身份保持，不可视作有效完整结果。'} 本页统计为原标签相合，不等于 O/B 核验语义全正确。不是140对正常/误导条件，也不是840个独立任务；不包含网页提交。140条历史上已用于研究，不能称为未见测试。</p>${summaryTable('full140')}<details><summary>原24条开发子集</summary>${summaryTable('previous_dev24')}</details><details><summary>其余116条（本轮未调提示；不是历史完全未见）</summary>${summaryTable('remaining116')}</details>${cost}<details><summary>版本方案与解释边界</summary><pre>${esc(D.versions)}</pre></details><details><summary>本轮固定协议</summary><pre>${esc(D.protocol)}</pre></details><details><summary>整体结论与限制</summary><pre>${esc(D.report)}</pre></details><p class="muted">同一任务六版使用同一副本，顺序事先轮转；所有配置重新运行。原v3保留旧数组schema，其余版本使用固定键schema，因此格式变化不是纯提示效应。既有275条O/B固定，旧候选生成成本不计入本轮；本轮未新生成反问链或持久化规则。</p>`;
let filtered=[];
function keep(r){const v=$('#method').value,a=r.arms.plain.state,b=r.arms[v].state,f=$('#filter').value,p=$('#panel').value;if(p==='dev'&&!r.previous_dev||p==='rest'&&r.previous_dev)return false;
if(f==='gain')return a!=='target'&&b==='target';if(f==='loss')return a==='target'&&b!=='target';if(f==='wrong')return ['trap','other'].includes(a)&&b==='target';if(f==='null')return b==='no_option';if(f==='failed')return ['interface_failed','not_completed'].includes(b);return true}
function list(){const q=$('#query').value.toLowerCase().trim(),exact=D.rows.some(r=>r.id===q),old=$('#case').value,hash=decodeURIComponent(location.hash.slice(1));filtered=D.rows.filter(r=>keep(r)&&(exact?r.id===q:(r.id+' '+r.family).toLowerCase().includes(q)));$('#case').innerHTML=filtered.map(r=>`<option value="${esc(r.id)}">${esc(r.id)} · ${esc(r.family)}</option>`).join('');if(filtered.some(r=>r.id===hash))$('#case').value=hash;else if(filtered.some(r=>r.id===old))$('#case').value=old;render()}
function render(){const r=filtered.find(r=>r.id===$('#case').value)||filtered[0];if(!r){$('#body').innerHTML='<section>没有符合条件的样本。</section>';return}history.replaceState(null,'','#'+r.id);let cards='';for(const [v,a] of Object.entries(r.arms)){let steps='';for(const [stage,s] of Object.entries(a.stages)){steps+=`<details><summary>${v==='plain'?'直接选择（单次请求）':stages[stage]}</summary><pre>${pretty(s.accepted||s.failure||'没有被接受的输出')}</pre><details><summary>完整实际文字输入与格式约束</summary><pre>${pretty(s.system)}</pre><pre>${pretty(s.context)}</pre><pre>${pretty(s.schema)}</pre><pre>${pretty(s.parameters)}</pre><p class="small">请求SHA256：${esc(s.request_sha256)}；图片SHA256：${esc(s.image_identity?.sha256)}。请求中的图像就是本页上方的原图；完整base64见证据包。</p></details><details><summary>原始服务响应（含结构失败）</summary><pre>${pretty(s.responses)}</pre><pre>${pretty(s.owner)}</pre></details></details>`}
cards+=`<article class="card"><h3>${esc(names[v])}</h3><p><span class="badge ${a.state}">${esc(states[a.state])}</span></p><p class="choice"><b>${esc(a.result.choice?.option_label??'未产生非空选项')}</b></p><pre>${pretty(a.result.choice?.basis||a.result.error||a.result.status)}</pre>${steps}</article>`}
const e=D.evaluations[$('#method').value].panels.full140.vs_plain.rows[r.key];
$('#body').innerHTML=`<section><h2>${esc(r.id)} · 原始任务</h2><p class="muted">${r.previous_dev?'原24条开发样本':'其余116条'} · worker ${r.arms.plain.result.worker} · 六版同原图</p><p class="small muted">以下是离线研究分类，不发送给模型：${esc(r.family)}</p>${r.evidence_conflict?'<p class="warning">env008保留原gold及evidence_conflict限定：Wind并非完全没有可见支持。分数按原标签记录，不据本次结果修改原图或答案。</p>':''}<p>${esc(r.input.goal)}</p><img class="chart" alt="${esc(r.id)} 原始图表" src="${r.image}"><p class="small muted">原图SHA256：${esc(r.image_sha256)}</p><details><summary>原始公开任务、选项及固定 O/B</summary><pre>${pretty(r.input)}</pre></details><details><summary>离线评分与历史参照（不发送给模型）</summary><p>原目标标签：${esc(r.target)}</p><p>当前筛选比较：普通方案「${esc(states[e.from])}」→${esc(names[$('#method').value])}「${esc(states[e.to])}」，标签相合净变化 ${e.net_target}。</p><p>历史 v3：${esc(states[r.historical_v3.state])}；不是本轮重新运行结果。</p><pre>${pretty(r.historical_v3.result)}</pre></details></section><div class="grid">${cards}</div>`}
for(const s of ['#method','#panel','#filter'])$(s).onchange=list;$('#query').oninput=list;$('#case').onchange=render;$('#prev').onclick=()=>{$('#case').selectedIndex=Math.max(0,$('#case').selectedIndex-1);render()};$('#next').onclick=()=>{$('#case').selectedIndex=Math.min(filtered.length-1,$('#case').selectedIndex+1);render()};list();
</script></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.capture, args.analysis, args.output)
