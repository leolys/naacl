# -*- coding: utf-8 -*-
"""Offline, standalone Chinese comparison viewer; original model text retained."""
import argparse
import base64
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from evaluate import HERE, digest, read, state
from freeze import inspect_audit


def optional(path):
    return read(path) if path.exists() else None


def build(output, version, panel):
    manifest = read(HERE / 'manifest.json')
    labels = read(HERE / 'offline/labels.json')['tasks']
    old = read(HERE / 'offline/old_v3_summary.json')['units']
    ids = [k for k, v in manifest['units'].items() if panel == 'full' or v['panel'] == panel]
    records = []
    versions = [v for v in ('plain', 'v4', 'v5', 'v6', 'v7') if (HERE / 'runs' / (v + '_dev')).exists()]
    for key in ids:
        unit = manifest['units'][key]
        projected = read(HERE / 'data' / key / 'input.json')
        image = HERE / 'data' / key / unit['image']
        arms = {'historical_v3': {'result': old[key], 'state': state(old[key], labels[key]),
                                  'origin': '上轮历史结果，非同期随机对照'}}
        for method in versions:
            run_path = HERE / 'runs' / (method + '_' + unit['panel']) / key
            result = optional(run_path / 'result.json')
            if result is None:
                continue
            arm = {'result': result, 'state': state(result, labels[key]), 'stages': {}}
            for stage in ('read', 'verify', 'decide'):
                request = optional(run_path / stage / 'request.json')
                if request:
                    arm['stages'][stage] = {
                        'system': request['messages'][0]['content'],
                        'context': optional(run_path / stage / 'context.json'),
                        'accepted': optional(run_path / stage / 'accepted.json'),
                        'response_files': [str(p.relative_to(HERE)) for p in sorted((run_path / stage).glob('response_*.json'))],
                        'request_sha256': digest(run_path / stage / 'request.json'),
                        'decode': {k: request.get(k) for k in ('model', 'temperature', 'top_p', 'top_k', 'seed', 'max_tokens', 'chat_template_kwargs')},
                    }
            arms[method] = arm
        audits = {}
        for method in versions:
            audit = optional(HERE / 'audit' / (method + '_dev.json'))
            if audit and key in audit.get('units', {}):
                audits[method] = audit['units'][key]
        application_notes = optional(HERE / 'audit/application_notes.json') or {}
        note = application_notes.get(key)
        records.append({'id': key, 'slug': unit['slug'], 'panel': unit['panel'], 'family': unit['family'],
                        'image': 'data:image/jpeg;base64,' + base64.b64encode(image.read_bytes()).decode('ascii'),
                        'image_sha256': unit['image_sha256'], 'input': projected,
                        'target': labels[key]['original_correct_label'], 'arms': arms,
                        'audit': audits, 'application_note': note})
    evaluations = {}
    for p in (HERE / 'analysis').glob('*.json'):
        value = read(p)
        if 'comparisons' in value and 'version' in value and 'panel' in value:
            evaluations[value['version'] + '_' + value['panel']] = value
    development = []
    frozen = optional(HERE / 'FREEZE.json')
    for method in ('v4', 'v5', 'v6', 'v7'):
        evaluation = evaluations.get(method + '_dev')
        if evaluation is None:
            continue
        audit_path = HERE / 'audit' / (method + '_dev.json')
        audit_issues = inspect_audit(method, audit_path, evaluation) if audit_path.exists() else None
        cost = optional(HERE / 'audit' / (method + '_dev_costs.json')) or {}
        method_cost = cost.get('by_run', {}).get(method + '_dev', {})
        development.append({'version': method, 'n': evaluation['n'],
                            'counts': evaluation['counts'][method],
                            'net_vs_plain': evaluation['comparisons']['plain']['net_target'],
                            'net_vs_v3': evaluation['comparisons']['historical_v3']['net_target'],
                            'numeric_gate': evaluation['dev_numeric_gate'],
                            'audit_issues': audit_issues,
                            'frozen': bool(frozen and frozen['version'] == method),
                            'cost': method_cost})
    payload = {'created': datetime.now(timezone.utc).isoformat(), 'version': version,
               'panel': panel, 'records': records, 'evaluations': evaluations,
               'development': development,
               'stopped_without_freeze': (not frozen and len(development) == 4
                    and all(not row['numeric_gate'] or bool(row['audit_issues']) for row in development)),
               'versions': (HERE / 'VERSION_HISTORY.md').read_text(encoding='utf-8'),
               'report': (HERE / 'REPORT.md').read_text(encoding='utf-8') if (HERE / 'REPORT.md').exists() else '开发中。不得据部分结果宣称全量提升。'}
    encoded = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    page = TEMPLATE.replace('@@DATA@@', encoded)
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'OB_REFINEMENT_REVIEW.html'
    target.write_text(page, encoding='utf-8')
    print(json.dumps({'path': str(target), 'cases': len(records), 'bytes': target.stat().st_size, 'sha256': digest(target)}, ensure_ascii=False))


TEMPLATE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>O/B 核验优化 · 同模型逐项比较</title>
<style>
:root{color-scheme:light;--ink:#172c36;--muted:#556a73;--line:#d6e1e4;--paper:#fff;--base:#edf3f3;--accent:#08686a}
*{box-sizing:border-box}body{margin:0;background:var(--base);color:var(--ink);font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif}
header{padding:30px 4vw;background:#173f4b;color:white}h1{margin:0;font-size:28px}h2{font-size:22px}h3{margin-top:0}p{margin:.6em 0}
main{max-width:1550px;margin:auto;padding:20px}nav{position:sticky;top:0;background:#edf3f3f5;padding:12px 0;z-index:3;display:flex;gap:10px;flex-wrap:wrap}
input,select,button{font:inherit;border:1px solid #93abad;border-radius:6px;padding:7px 10px;background:white;min-width:60px;max-width:100%}nav>*{min-width:0}#case{flex:1 1 360px;max-width:100%}button{cursor:pointer}button:hover{background:#deeeee}
section,.card{background:var(--paper);border:1px solid var(--line);border-radius:9px;padding:20px;margin-bottom:18px}
.muted{color:var(--muted)}.warning{border-left:5px solid #bd7719;background:#fff7e8;padding:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.chart{max-width:100%;max-height:720px;object-fit:contain;display:block;margin:auto}.card{min-width:0}.small{overflow-wrap:anywhere}.badge{border-radius:5px;padding:2px 7px;background:#e7eded;font-size:13px}.target{background:#e1f1e8}.trap,.other{background:#fbe8e6}.no_option,.interface_failed{background:#fff1d2}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.65 system-ui,sans-serif;background:#f4f7f8;padding:12px;border-radius:5px}details{border-top:1px solid var(--line);padding:12px 0}summary{cursor:pointer;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:9px;border-bottom:1px solid var(--line);text-align:left}.scroll{overflow:auto}.toolbar{display:flex;gap:12px;align-items:center}.small{font-size:13px}a{color:var(--accent)}
@media(max-width:650px){main{padding:10px}header{padding:20px}h1{font-size:23px}.grid{grid-template-columns:1fr}}@media print{nav,button{display:none}section{break-inside:avoid}}
</style><header><h1>O/B 核验优化：同模型逐项比较</h1><p>原图与公开任务 → 独立观察 → 核验 O 与 B → 静态选择</p><p>本页可离线单文件打开。没有真实业务提交；标签一致不等于核验语义完全正确。</p></header>
<main><section id="intro"></section><nav><input id="query" placeholder="任务编号 / 家族" aria-label="搜索任务"><select id="filter" aria-label="筛选"><option value="all">全部任务</option><option value="improved">较普通决策新增原目标相合</option><option value="degraded">原目标相合转不相合</option><option value="same">标签相合状态未变</option><option value="failed">接口失败 / 未完成 / 对照缺失</option></select><select id="case" aria-label="选择任务"></select><button id="prev">上一条</button><button id="next">下一条</button></nav><div id="body"></div></main>
<script id="data" type="application/json">@@DATA@@</script><script>
const D=JSON.parse(document.querySelector('#data').textContent),$=s=>document.querySelector(s);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty=x=>esc(typeof x==='string'?x:JSON.stringify(x,null,2));
const names={plain:'本轮普通直接决策',historical_v3:'上轮核验 v3',v4:'核验 v4',v5:'核验 v5',v6:'核验 v6',v7:'核验 v7'};
const states={target:'与原目标标签一致',trap:'原误导选项',other:'其他原选项',no_option:'返回空选项（见原始理由）',interface_failed:'接口 / 结构失败',not_completed:'未完成'};
const stageNames={read:'独立观察（不输入候选）',verify:'核验原 O 与 B（不裁决整链）',decide:'重新选择（不是提交）'};
const panelNames={dev:'开发面板',application:'本轮未调参应用集',full:'完整 140 条'};
function auditDescription(v){if(v.audit_issues===null)return '待完成';if(!v.audit_issues.length)return '未见冻结阻塞';return v.audit_issues.map(x=>x.startsWith('New target agreement not visibly justified: ')?'新增相合依据不足：'+x.split(': ').pop().replace(/^full_/,''):x==='Prompt generality not verified'?'提示通用性尚未确认':x).join('；')}
const summary=D.evaluations[D.version+'_'+D.panel];
let counts=summary?'<div class="scroll"><table><tr><th>配置</th><th>原目标一致</th><th>误导选项</th><th>其他</th><th>未选项</th><th>失败 / 未完成</th></tr>'+Object.entries(summary.counts).map(([k,v])=>`<tr><td>${esc(names[k]||k)}</td><td>${v.target||0}/${summary.n}</td><td>${v.trap||0}</td><td>${v.other||0}</td><td>${v.no_option||0}</td><td>${(v.interface_failed||0)+(v.not_completed||0)}</td></tr>`).join('')+'</table></div>':'';
if(summary){let transitions='<details><summary>配对转移：提升、退化与空选项分开计数</summary>';for(const [method,c] of Object.entries(summary.comparisons)){transitions+=`<h3>相对${esc(names[method]||method)}：净增 ${c.net_target} 条</h3><p>共同完成解析（包括空选项）：${c.common_parsed_including_null.n} 条，净增 ${c.common_parsed_including_null.net_target} 条。</p><div class="scroll"><table><tr><th>原状态 → 新状态</th><th>数量</th></tr>`+Object.entries(c.exact_transitions).map(([label,n])=>{const [a,b]=label.split(' -> ');return `<tr><td>${esc(states[a]||a)} → ${esc(states[b]||b)}</td><td>${n}</td></tr>`}).join('')+'</table></div>'}transitions+='</details><details><summary>按原任务家族比较（变式不当作独立机制）</summary><div class="scroll"><table><tr><th>离线任务家族</th><th>数量</th><th>相对普通决策净增</th><th>相对旧 v3 净增</th></tr>';for(const [family,c] of Object.entries(summary.comparisons.plain.families)){transitions+=`<tr><td>${esc(family)}</td><td>${c.n}</td><td>${c.net_target}</td><td>${summary.comparisons.historical_v3.families[family]?.net_target??'未运行'}</td></tr>`}counts+=transitions+'</table></div></details>'}
const development='<details><summary>全部已完成开发版本：固定 24 条，不逐样本挑最好版本</summary><p>以下“依据审阅”只判断冻结所需的新增相合依据与通用性，不表示该版本全部 O/B 都核验正确。开发版本不是独立测试集。</p><div class="scroll"><table><tr><th>版本</th><th>原目标一致</th><th>较普通决策</th><th>较旧 v3</th><th>数值门槛</th><th>新增相合依据审阅</th><th>实际请求 / token</th><th>冻结</th></tr>'+D.development.map(v=>`<tr><td>${esc(v.version)}</td><td>${v.counts.target||0}/${v.n}</td><td>${v.net_vs_plain}</td><td>${v.net_vs_v3}</td><td>${v.numeric_gate?'通过':'未通过'}</td><td>${esc(auditDescription(v))}</td><td>${v.cost.attempts??'未汇总'} / ${v.cost.known_usage?.total_tokens??'未汇总'}</td><td>${v.frozen?'已冻结':'未冻结'}</td></tr>`).join('')+'</table></div></details>';
$('#intro').innerHTML=`<p><b>${D.records.length} 条 · ${esc(panelNames[D.panel]||D.panel)} · ${esc(D.version)}（不是按效果挑出的获胜版）</b></p>${D.stopped_without_freeze?'<p class="warning"><b>本轮已停止，未确认全量提升。</b> 四个开发版本均未通过完整冻结要求；已完成同24条的比较，116条应用未运行。各版有改善也有退化，见下方全部版本表。</p>':''}<div class="warning">24 条用于本轮开发；其余 116 条只在冻结后使用。整个数据集此前已被运行，不是全新未见集。正常流程普通决策 1 次、核验方案 3 次请求，失败与基础设施重试另计实际成本，不是等算力比较。原目标标签仅用于本页离线计分，未发送给模型。核验沿用已有 O/B 候选，本轮不重新生成反问或新链、不测试持久规则；旧候选生成成本未计入本轮，不能据此声称完整方法只需三次请求。中文旁注是 AI 辅助审阅记录，不是项目所有者的人工认证。</div>${counts}${development}<details><summary>本轮结论与限制</summary><pre>${esc(D.report)}</pre></details><details><summary>每个版本具体方案与全部迭代结果</summary><pre>${esc(D.versions)}</pre></details>`;
function changeType(r){const a=r.arms.plain?.state,b=r.arms[D.version]?.state;if(!a||!b)return 'failed';if(['interface_failed','not_completed'].includes(b))return 'failed';if(a!=='target'&&b==='target')return 'improved';if(a==='target'&&b!=='target')return 'degraded';return 'same'}
let filtered=[];
function list(){const q=$('#query').value.toLowerCase().trim(),f=$('#filter').value,exact=D.records.some(r=>r.slug===q);filtered=D.records.filter(r=>(exact?r.slug===q:(r.slug+' '+r.family).toLowerCase().includes(q))&&(f==='all'||changeType(r)===f));const hash=decodeURIComponent(location.hash.slice(1));$('#case').innerHTML=filtered.map(r=>`<option value="${esc(r.slug)}">${esc(r.slug)} · ${esc(r.family)}</option>`).join('');if(filtered.some(r=>r.slug===hash))$('#case').value=hash;render()}
function render(){const r=filtered.find(r=>r.slug===$('#case').value)||filtered[0];if(!r){$('#body').innerHTML='<section>没有符合筛选的样本。</section>';return}history.replaceState(null,'','#'+r.slug);let arms='';
for(const [name,arm] of Object.entries(r.arms)){let stages='';for(const [key,v] of Object.entries(arm.stages||{})){stages+=`<details><summary>${stageNames[key]}</summary><pre>${pretty(v.accepted||{notice:'无接受输出，原始失败保存在响应文件中'})}</pre><details><summary>实际提示及公共输入（英语原文）</summary><pre>${pretty(v.system)}</pre><pre>${pretty(v.context)}</pre><pre>${pretty(v.decode)}</pre><p class="small">请求 SHA256：${esc(v.request_sha256)}<br>图片 SHA256：${esc(r.image_sha256)}<br>原始响应：${esc(v.response_files.join('；'))}</p></details></details>`}
arms+=`<article class="card"><h3>${esc(names[name]||name)}</h3><span class="badge ${arm.state}">${esc(states[arm.state])}</span><p><b>${esc(arm.result.choice?.option_label??'未产生选项')}</b></p><pre>${pretty(arm.result.choice?.basis||arm.result.error||arm.result)}</pre>${stages}</article>`}
let audits=Object.entries(r.audit).map(([v,a])=>`<p><b>${esc(v)} 中文开发审阅：</b>${esc(a.note)}</p>`).join('');if(r.application_note)audits+=`<p><b>应用后离线分析：</b>${esc(r.application_note.note||r.application_note)}</p>`;
$('#body').innerHTML=`<section><h2>${esc(r.slug)} · 原始任务与图表</h2><p class="muted">${r.panel==='dev'?'固定开发样本':'本轮未参与调参应用样本'} · 原图未修改</p><p class="small muted">离线研究分类（不发送给模型）：${esc(r.family)}</p><p>${esc(r.input.goal)}</p><img class="chart" alt="${esc(r.slug)} 原始任务图表" src="${r.image}"><p class="small muted">图像 SHA256：${esc(r.image_sha256)}</p><details><summary>公开任务、选项与沿用的 O/B 候选</summary><pre>${pretty(r.input)}</pre></details><details><summary>离线原标签与中文 AI 审阅（不是模型输入或人工认证）</summary><p>原目标标签：${esc(r.target)}</p>${audits||'<p>尚无逐项中文审阅记录；请对照原图和原始输出审阅。</p>'}</details></section><div class="grid">${arms}</div>`}
$('#query').addEventListener('input',list);$('#filter').addEventListener('change',list);$('#case').addEventListener('change',render);$('#prev').onclick=()=>{let i=$('#case').selectedIndex;$('#case').selectedIndex=Math.max(0,i-1);render()};$('#next').onclick=()=>{let i=$('#case').selectedIndex;$('#case').selectedIndex=Math.min(filtered.length-1,i+1);render()};list();
</script></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--panel', choices=['dev', 'application', 'full'], required=True)
    args = parser.parse_args()
    build(args.output, args.version, args.panel)
