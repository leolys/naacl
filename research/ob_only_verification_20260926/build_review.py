"""Portable static viewer: exact model records plus separate Chinese commentary."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path

NAMES = {'pub001_misleading': 'pub001 · 误导图', 'pub001_normal': 'pub001 · 正常图', 'b002': 'b002 · 柱图', 'pub013': 'pub013 · 地图'}
VARIANTS = {'registration': '候选登记版反问来源', 'coverage': '候选登记＋读取覆盖版反问来源'}
STATUSES = {'supported': '支持', 'refuted': '反驳', 'unclear': '无法确认'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def esc(v):
    return html.escape(str(v), quote=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def image_refs(value):
    if isinstance(value, dict):
        return {k: image_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [image_refs(v) for v in value]
    if isinstance(value, str) and value.startswith('data:image/'):
        data = base64.b64decode(value.split(',', 1)[1])
        return '[图像字节省略，SHA256=' + digest(data) + ']'
    return value


def raw(title, value):
    return '<details><summary>' + esc(title) + '</summary><pre>' + esc(json.dumps(image_refs(value), ensure_ascii=False, indent=2)) + '</pre></details>'


def paragraphs(items):
    return ''.join('<p>' + esc(x) + '</p>' for x in (items or []))


def decision_label(r):
    if r.get('decision') is None:
        return '未得到选择返回'
    return r['decision']['option_label'] or '明确未选：证据不足（null）'


def status_label(r):
    return {'prepared': '尚未运行', 'verified_pending_decision': '核验完成，待选择',
            'completed_ob_diagnostic': '核验及选择已返回', 'stopped_transport_or_budget': '传输/预算停止，详见原记录',
            'ob_verify_interface_failed_no_quality_retry': '核验接口失败，未选择',
            'decide_interface_failed_no_quality_retry': '选择接口失败'}.get(r['status'], r['status'])


CSS = '''*{box-sizing:border-box}body{margin:0;background:#f4f7f9;color:#173042;font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1180px;margin:auto;padding:25px 22px 65px}h1{font-size:28px}h2{font-size:24px}h3{font-size:20px}h4{font-size:18px}nav{display:flex;gap:10px;flex-wrap:wrap}a{color:#0b5d7b}nav a{background:white;padding:8px 12px;border:1px solid #cbd7df;border-radius:6px;text-decoration:none}section,.record{background:white;border:1px solid #cbd7df;border-radius:10px;padding:20px;margin:20px 0}.record{background:#fcfdfe}p{margin:9px 0}.note{background:#eaf4f8;padding:12px 16px;border-radius:8px}.notice{background:#fff4d9;padding:14px 16px;border-left:4px solid #b68523}.muted{font-size:14px;color:#566b79}img{max-width:100%;height:auto}.hash{font:12px/1.5 monospace;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;vertical-align:top;border-bottom:1px solid #cbd7df;padding:9px;overflow-wrap:anywhere}th{background:#edf2f5}.scroll{overflow:auto}details{border:1px solid #cbd7df;border-radius:7px;margin:12px 0;overflow:hidden}summary{cursor:pointer;background:#edf2f5;padding:10px 13px;overflow-wrap:anywhere}pre{padding:13px;margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 Consolas,monospace;max-height:620px;overflow:auto}.columns{display:grid;grid-template-columns:1fr 1fr;gap:18px}.columns>div{min-width:0}li{margin:7px 0}@media(max-width:700px){main{padding:16px 12px}section,.record{padding:13px}.columns{grid-template-columns:1fr}h1{font-size:23px}table{min-width:660px}}'''


def build(run, output, notes):
    summary, config, ledger = (read(run / n) for n in ('summary.json', 'config.json', 'ledger.json'))
    rows = summary['results']; indexed = {(r['case'], r['variant']): r for r in rows}
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>O/B 核验与重新选择</title><style>', CSS, '</style><main><h1>只核验 O/B，再重新选择行动</h1>']
    parts.append('<div class="notice">3 个基础任务、4 个图输入 × 2 个原反问来源，共8个固定诊断单元；不是8个独立任务。本轮不生成新反问或展开，不提交表单、不生成持久规则，也不设置普通重看对照。</div>')
    parts.append('<p>核验不再包含 inference 或整链有效性：逐项查 O；B 分别查视觉解码、任务适用性。独立 C 字段没有送入模型，但原 O/B 可能含行动名称，不能声称真正结论盲审。重新选择另看同图，不直接复制旧 C。</p>')
    parts.append('<div class="note">' + paragraphs(notes.get('overview')) + '</div>')
    parts.append('<p class="muted">实际请求尝试：%s；付费 API：%s；业务浏览器操作：%s。模型判断不是人工确认；结构通过不是语义正确。</p>' % (ledger['request_attempts'], ledger['paid_api_requests'], ledger['browser_operations']))
    parts.append('<nav>' + ''.join('<a href="#%s">%s</a>' % (c, NAMES[c]) for c in config['cases']) + '<a href="#archive">提示与档案</a></nav>')
    parts.append('<section><h2>重新选择结果</h2><div class="scroll"><table><tr><th>输入</th><th>候选来源</th><th>新选择（未执行）</th><th>状态</th></tr>')
    for r in rows:
        parts.append('<tr>' + ''.join('<td>' + esc(v) + '</td>' for v in (NAMES[r['case']], VARIANTS[r['variant']], decision_label(r), status_label(r))) + '</tr>')
    parts.append('</table></div></section>')
    archive = {}
    for case in config['cases']:
        parts.append('<section id="%s"><h2>%s</h2>' % (case, NAMES[case]))
        blobs = {}
        for variant in config['variants']:
            blob = (run / variant / case / 'source_chart.png').read_bytes()
            blobs.setdefault(digest(blob), blob)
        if len(blobs) != 1:
            parts.append('<p>注意：两个来源的图像不同，不能假定输入相同。</p>')
        for h, blob in blobs.items():
            parts.append('<img alt="%s原图" src="data:image/png;base64,%s"><p class="hash">SHA256=%s</p>' % (NAMES[case], base64.b64encode(blob).decode(), h))
        parts.append(raw('公开任务原文', read(run / config['variants'][0] / case / 'source_context.json')))
        for variant in config['variants']:
            r = indexed[(case, variant)]; folder = run / variant / case
            public = read(folder / 'projected.json'); old = read(folder / 'source_candidate_set.json')
            unit_notes = notes.get('units', {}).get(variant + '/' + case, {})
            reviews = {x['id']: x for x in (r['verification'] or {}).get('reviews', [])}
            parts.append('<section id="%s-%s"><h3>%s</h3><p>%s</p>' % (case, variant, VARIANTS[variant], esc(status_label(r))))
            parts.append('<div class="note">' + paragraphs(unit_notes.get('summary')) + '</div>')
            parts.append('<h4>新选择：%s</h4>' % esc(decision_label(r)))
            if unit_notes.get('decision_basis_zh'):
                parts.append('<div class="note"><b>新选择依据 · 离线中文翻译</b>' + paragraphs([unit_notes['decision_basis_zh']]) + '</div>')
            parts.append(raw('新选择完整原文（不是提交回执）', r['decision']))
            for record, source in zip(public['records'], old['chains']):
                check = reviews.get(record['id'])
                parts.append('<div class="record"><h4>%s：原 O/B 与新核验</h4>' % esc(record['id']))
                parts.append('<p class="muted">来源 C 仅离线对照、未作为独立字段输入：%s</p>' % esc(source['C'].get('claim')))
                rnotes = unit_notes.get('records', {}).get(record['id'], [])
                if rnotes:
                    parts.append('<div class="note"><b>中文审阅注释（非模型输出）</b>' + paragraphs(rnotes) + '</div>')
                parts.append('<div class="columns"><div><b>观察 O 原文</b><ol>')
                for o in record['O']:
                    parts.append('<li>%s：%s</li>' % (esc(o['location']), esc(o['content'])))
                parts.append('</ol><b>读法 B 原文</b><p>%s</p>' % esc(record['B']['rule']))
                parts.append('<ul>' + ''.join('<li>' + esc(c) + '</li>' for c in record['B']['conditions']) + '</ul></div><div>')
                if check:
                    parts.append('<b>逐项观察核验</b><ul>')
                    for o in check['O']:
                        parts.append('<li>O%d · %s：%s</li>' % (o['index'], STATUSES[o['status']], esc(o['evidence'])))
                    parts.append('</ul>')
                    for k, label in (('visual_decoding', 'B · 视觉解码'), ('task_applicability', 'B · 任务适用性')):
                        assessment = check['B'][k]
                        parts.append('<b>%s：%s</b><p>%s</p>' % (label, STATUSES[assessment['status']], esc(assessment['evidence'])))
                else:
                    parts.append('<p>无已完成核验，不解释为该读法被反驳。</p>')
                parts.append('</div></div></div>')
            parts.append(raw('完整核验原文', r['verification']))
            parts.append(raw('完整单元执行结果', r))
            stages = {}
            for stage in ('ob_verify', 'decide'):
                for path in sorted((folder / stage).glob('*.json')):
                    stages[stage + '/' + path.name] = read(path)
            parts.append(raw('实际请求与响应：全文保留，图片字节替换为hash', stages))
            parts.append('</section>')
            archive[variant + '/' + case] = image_refs({'result': r, 'projection': public, 'source': old, 'stages': stages})
        parts.append('</section>')
    parts.append('<section id="archive"><h2>提示与运行档案</h2>')
    for name in ('prompts_ob.py', 'records_ob.py'):
        text = (run / 'runtime_source/research/ob_only_verification_20260926' / name).read_text(encoding='utf-8')
        parts.append('<details><summary>' + esc(name) + '</summary><pre>' + esc(text) + '</pre></details>')
    for title, data in (('配置', config), ('实际账本', ledger), ('摘要', summary), ('中文注释', notes), ('源哈希', read(run / 'source_hashes.json'))):
        parts.append(raw(title, data))
    parts.append('<p>中文注释由Codex离线撰写，不进入被测模型。原图已内嵌，HTML可脱离项目独立打开。</p></section></main></html>')
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'OB_ONLY_REVIEW.html'
    target.write_text(''.join(parts), encoding='utf-8')
    (output / 'RECORDS_WITH_IMAGE_HASHES.json').write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'PROVENANCE.json').write_text(json.dumps({'run': str(run.resolve()), 'sha256': digest(target.read_bytes()),
        'renderer_sha256': digest(Path(__file__).read_bytes()), 'standalone': True, 'semantic_validation': False}, indent=2), encoding='utf-8')
    return target


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--notes', type=Path, required=True)
    a = p.parse_args()
    print(build(a.run, a.output, read(a.notes)))
