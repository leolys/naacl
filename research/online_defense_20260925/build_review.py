"""Offline single-file review using the installed ARIS renderer/template.

Canonical sources: REPORT.md + EVIDENCE.json + READER_NOTES_ZH.json.
Trusted local PNG/JPEGs are embedded by code, never passed through as raw model HTML.
"""
import base64
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from deps import HERE, PROJECT, wire, module

ESC=html.escape


def pretty(value):
    return '<pre><code>'+ESC(json.dumps(value,ensure_ascii=False,indent=2))+'</code></pre>'


def fold(label, body):
    return '<details><summary>'+ESC(label)+'</summary>'+body+'</details>'


def bitmap(path,label):
    path=Path(path)
    if not path.is_file() or path.suffix.lower() not in ('.png','.jpeg','.jpg'):
        raise ValueError('only_existing_png_jpeg_images')
    if not path.resolve().is_relative_to(HERE):
        raise ValueError('image_outside_run_artifacts')
    mime='image/png' if path.suffix.lower()=='.png' else 'image/jpeg'
    data=base64.b64encode(path.read_bytes()).decode('ascii')
    return '<figure><img loading="lazy" src="data:'+mime+';base64,'+data+'" alt="'+ESC(label,quote=True)+'"><figcaption>'+ESC(label)+' · '+wire.digest(path)[:12]+'</figcaption></figure>'


def main():
    helper=module('aris_online_renderer',PROJECT/'.agents/skills/render-html/scripts/render_html.py')
    report=(HERE/'REPORT.md').read_text(encoding='utf-8')
    data=wire.read(HERE/'EVIDENCE.json')
    notes=wire.read(HERE/'READER_NOTES_ZH.json')
    body,toc=helper._render_blocks(helper.parse_blocks(helper.strip_frontmatter(report).split('\n')),collect_toc=True)
    body+='<h2 id="actual-traces">逐条实际记录</h2><p>所有“支持/反驳/未确定”均是模型核验判断，不是人工金标准。图片是实际请求中的原字节；本页没有模型调用、外链脚本或提交按钮。</p>'
    toc.append({'level':2,'id':'actual-traces','text':'逐条实际记录'})
    for run in data['runs']:
        for row in run['rows']:
            case=row['score']['case']
            system='普通 Agent' if row['score']['system']=='ordinary' else '新版方法'
            title=case['task_id']+' · '+('原图' if case['arm']=='official140' else '干净图')+' · '+system
            if run['run']!='live_v1':title+=' · 单次接口复测，不替换原面板'
            anchor=run['run']+'_'+row['unit']
            toc.append({'level':2,'id':anchor,'text':title})
            body+='<section class="trace"><h2 id="'+ESC(anchor)+'">'+ESC(title)+'</h2>'
            body+='<p>'+ESC(row['classification'])+'</p>'
            key=case['task_id']+'_'+case['arm']
            body+='<p><strong>原任务：</strong>'+ESC(notes['cases'][key]['task'])+'</p>'
            body+='<p>真实请求 '+str(row['cost']['request_attempts'])+' 次；浏览器动作 '+str(row['cost']['browser_operations'])+' 次；原服务器提交收据 '+str(row['score']['server_receipt_count'])+' 份。</p>'
            charts={}
            for request in row['requests']:
                for item in request['images']:
                    if item['ref']=='chart_1':charts[item['sha256']]=item
            for item in charts.values():body+=bitmap(item['file'],'实际送入模型的图表')
            body+=fold('1. 结果、成本及原评分（仅离线阅览）',pretty({'score':row['score'],'cost':row['cost'],'counts':row['counts']}))
            if row['score']['system']=='online_completion':
                for label,keyname in [('2. 完整初始 O—B—C 解释集合','initial_set'),
                                      ('3. 反问（允许零问题）','questions'),
                                      ('4. 补齐响应（含未通过结构检查的原始内容）','supplement'),
                                      ('5. 结构检查通过后的完整集合','combined'),
                                      ('6. 模型逐项核验：O、B、推导','verification'),
                                      ('7. 实際保存并重新读取的规则状态','rule_states')]:
                    value=row[keyname]
                    body+=fold(label,pretty(value) if value else '<p>本条未产生此工件；查看状态与前序记录，不能当作已执行该阶段。</p>')
            history='<p>每步图片显示动作提议前的 s_t；下面的 action 是 a_t。未执行/被暂存的提议不改变页面；只有实际工具回执证明发生了操作。不要把旧输入截图误当作动作后状态。</p>'
            for action in row['result']['action_records']:
                step=action['step']
                matching=[q for q in row['requests'] if q['stage']=='actor' and ('step_%02d'%step) in q['path']]
                detail=pretty(action)
                if matching:
                    state=matching[0]['public_context']['state']
                    detail='<h4>当前输入状态 s_t</h4>'+pretty(state)+'<h4>提议 a_t 与是否执行、执行回执</h4>'+detail
                    for item in matching[0]['images']:
                        if item['ref']!='chart_1':detail+=bitmap(item['file'],'该步模型输入页面截图，动作尚未执行')
                history+=fold('步骤 '+str(step)+' · '+action['proposal']['action']['kind']+' · '+('已执行' if action['executed'] else '未执行'),detail)
            history+=fold('结束时的公开状态与完整真实动作历史',pretty({'last_state':row['result'].get('last_public_state'),
                                                                      'history':row['result'].get('history'),
                                                                      'error':row['result'].get('error')}))
            body+=fold('8. actor 逐步执行时间线',history)
            requests='<p>下面来自实际 request.json，而非事后生成的提示示意。完整 HTTP 响应、使用量与原字节图片另存于压缩包；本页列出 system、公开 user 文本和图像引用。</p>'
            for index,request in enumerate(row['requests'],1):
                content='<h4>system</h4><pre>'+ESC(request['system_prompt'])+'</pre><h4>user：完整公开文本</h4>'+pretty(request['public_context'])+'<h4>实际图像引用与字节证据</h4>'+pretty(request['images'])
                requests+=fold(str(index)+' · '+request['stage']+' · '+request['path'],content)
            body+=fold('9. 完整输入文字、实际图像清单',requests)
            body+=fold('10. API 请求/响应型号与路由回执',pretty(row['route_records']))
            body+='</section>'
    source_hash=helper.sha256_of(report)
    evidence_hash=wire.digest(HERE/'EVIDENCE.json')
    notes_hash=wire.digest(HERE/'READER_NOTES_ZH.json')
    css='''<style>.trace{margin-top:3rem;border-top:3px solid #ac4a32;padding-top:1rem}details{margin:.8rem 0;padding:.5rem .8rem;border:1px solid #d4c6b5;border-radius:6px}summary{cursor:pointer;font-weight:600}pre{max-height:650px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}figure img{display:block;max-width:100%;height:auto;max-height:650px;object-fit:contain;background:white}figcaption{font-size:.82rem;overflow-wrap:anywhere}.source-proof{overflow-wrap:anywhere}section{scroll-margin-top:1rem}</style>'''
    body='<p class="source-proof">记录来源：EVIDENCE.json · SHA256 '+evidence_hash+'<br>中文导读来源：READER_NOTES_ZH.json · SHA256 '+notes_hash+'</p>'+body
    variables={'LANG':'zh-CN','TITLE':'在线解释补齐：实际轨迹与规则状态',
        'SUBTITLE_BLOCK':'<p class="subtitle">开发联调，不代表方法已经有效；本文件可独立离线打开。</p>',
        'EYEBROW_BLOCK':'<div class="eyebrow">MisVis · bounded developer panel</div>','BYLINE_BLOCK':'',
        'SOURCE_PATH':'research/online_defense_20260925/REPORT.md',
        'SOURCE_SHA256':source_hash,'SOURCE_SHA256_SHORT':source_hash[:12],
        'GENERATED_AT':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'HEAD_CDN':helper.CDN_BLOCK_OFFLINE,'TOC_HTML':helper.render_toc(toc),'TOC_LABEL':'目录',
        'BODY_HTML':body,'EXTRA_META':'<meta name="evidence-sha256" content="'+evidence_hash+'"><meta name="notes-sha256" content="'+notes_hash+'">'+css}
    output=HERE/'ONLINE_DEFENSE_REVIEW.html'
    output.write_text(helper.substitute(helper.load_template('academic'),variables),encoding='utf-8')
    print('Generated standalone review',output.stat().st_size,'bytes')


if __name__=='__main__':main()
