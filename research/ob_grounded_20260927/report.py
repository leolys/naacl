"""Offline audit and portable HTML; structure/cost are not semantic truth."""
import argparse
import base64
import copy
from collections import Counter
import hashlib
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = {'supported': '有依据支持', 'refuted': '存在反证', 'unclear': '证据不足',
          'completed': '核验及决策调用完成', 'interface_failed': '接口/结构失败', 'stopped': '已停止',
          'not_run': '未运行（仍保留在预定面板）', 'prepared': '仅准备输入'}
ZH_CACHE = {}
NEW_ZH = {}
AGREEMENT_CN = {'matches_original_target': '与原目标选项一致', 'original_trap_option': '原任务标记的误导选项',
                'other_original_option': '其他原选项', 'no_option': '未给出选项',
                'interface_failed': '接口/结构未完成', 'not_run': '未运行',
                'historical_proposal_unavailable': '没有历史建议', 'unsupported_mapping': '无法对齐',
                'not_a_public_option': '不是公开选项'}

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def h(x):
    return html.escape(str(x))

def pre(v):
    return '<pre>' + h(json.dumps(v, ensure_ascii=False, indent=2)) + '</pre>'

def evidence_text(value):
    """Exact-source-key Chinese summary with reviewer commentary kept separate."""
    if value in NEW_ZH:
        item = NEW_ZH[value]
        translated = '<p><b>模型理由中文摘要（非逐字译文）：</b><br>' + h(item['zh_summary']) + '</p>'
        if item.get('review_note'):
            translated += '<aside><b>Codex离线审阅旁注：</b><br>' + h(item['review_note']) + '</aside>'
        return translated + '<details><summary>模型英文原文</summary><p>' + h(value) + '</p></details>'
    return h(value)

def stage_state(source, stage):
    folder = source / stage
    if (folder / 'accepted.json').exists():
        return '输出通过接口校验（不代表内容正确）'
    if (folder / 'failure.json').exists():
        return '已尝试，但接口/结构未完成'
    if (folder / 'request.json').exists():
        return '请求已存档；未获得可接受输出'
    return '未运行'

def bilingual(v):
    if isinstance(v, str) and v in ZH_CACHE:
        return {'中文（已有逐字对应译文）': ZH_CACHE[v]['zh'], '原文': v}
    if isinstance(v, dict):
        return {k: bilingual(x) for k, x in v.items()}
    if isinstance(v, list):
        return [bilingual(x) for x in v]
    return v


def readable_original_text(value):
    if isinstance(value, str) and value in ZH_CACHE:
        return '<p>' + h(ZH_CACHE[value]['zh']) + '</p><details><summary>原英文</summary><p>' + h(value) + '</p></details>'
    return '<p>' + h(value) + '</p>' if isinstance(value, str) else pre(bilingual(value))


def observation_view(value):
    if isinstance(value, str):
        return readable_original_text(value)
    if isinstance(value, dict) and 'content' in value and set(value) <= {'ref', 'location', 'content'}:
        content = readable_original_text(value['content'])
        location = value.get('location')
        if location:
            content += '<p class="location">原定位：' + h(ZH_CACHE.get(location, {}).get('zh', location)) + '</p>'
        return content + '<details><summary>完整原O字段</summary>' + pre(value) + '</details>'
    return pre(bilingual(value))


def reading_view(value):
    if isinstance(value, str):
        return readable_original_text(value)
    if isinstance(value, dict) and 'text' in value and set(value) <= {'text', 'conditions'}:
        content = '<b>条件式读法</b>' + readable_original_text(value['text'])
        if value.get('conditions'):
            content += '<b>原必要条件</b>' + readable_original_text(value['conditions'])
        return content + '<details><summary>完整原B字段</summary>' + pre(value) + '</details>'
    return pre(bilingual(value))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def request_audit(folder, image, projected):
    issues, attempts, tokens = [], 0, Counter()
    for req in sorted(folder.glob('*/request.json')):
        stage = req.parent.name
        p = read(req)
        c = json.loads(p['messages'][1]['content'][0]['text'])
        image_data = base64.b64decode(p['messages'][1]['content'][1]['image_url']['url'].split(',', 1)[1])
        if hashlib.sha256(image_data).hexdigest() != sha(image): issues.append('image:' + stage)
        if stage in ('read', 'supply') and set(c) != {'goal', 'public_task', 'options'}: issues.append('blind_scope:' + stage)
        if stage in ('verify', 'decide') and c['records'] != projected['records']: issues.append('record_drift:' + stage)
        for r in c.get('records', []):
            if set(r) != {'id', 'O', 'B'}: issues.append('record_fields:' + stage)
        for response in req.parent.glob('response_*.json'):
            attempts += 1
            body = read(response).get('body')
            if isinstance(body, dict):
                for k, v in (body.get('usage') or {}).items():
                    if isinstance(v, int): tokens[k] += v
    return issues, attempts, dict(tokens)

def main():
    global ZH_CACHE, NEW_ZH
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--agreement', type=Path, help='Optional offline label-agreement output; never part of model input')
    args = p.parse_args()
    if (HERE / 'ZH_EXACT_CACHE.json').exists():
        ZH_CACHE = read(HERE / 'ZH_EXACT_CACHE.json')['items']
    if (HERE / 'SUPPLIED_CANDIDATES_ZH.json').exists():
        for english, translated in read(HERE / 'SUPPLIED_CANDIDATES_ZH.json')['items'].items():
            if english in ZH_CACHE and ZH_CACHE[english]['zh'] != translated['zh']:
                raise ValueError('Conflicting exact-source candidate translation')
            ZH_CACHE[english] = translated
    if (HERE / 'NEW_EVIDENCE_ZH_v2.json').exists():
        NEW_ZH = read(HERE / 'NEW_EVIDENCE_ZH_v2.json')['translations']
    root = HERE / 'runs' / args.run
    manifest = read(HERE / 'manifest.json')
    summary = read(root / 'summary.json')
    agreement_report = read(args.agreement) if args.agreement else {}
    agreement = agreement_report.get('units', {})
    notes_file = HERE / ('NOTES_' + args.run + '.json')
    notes = read(notes_file) if notes_file.exists() else {}
    confirmation_notes = read(HERE / 'NOTES_v3_confirm.json') if (HERE / 'NOTES_v3_confirm.json').exists() else {}
    args.output.mkdir(parents=True, exist_ok=False)
    cards, audits, option_counts, statuses = [], {}, Counter(), Counter()
    responses, token_total = 0, Counter()
    decision_basis_total = decision_basis_zh = 0
    b_evidence_total = b_evidence_zh = 0
    o_evidence_total = o_evidence_zh = 0
    panel = summary['panel']
    eligible = {k: u for k, u in manifest['units'].items() if
                (panel == 'dev' and u['panel'] == 'dev') or
                (panel == 'confirm' and u['panel'] == 'full' and u['confirm']) or
                (panel == 'full' and u['panel'] == 'full')}
    for key in eligible:
        result = summary['units'].get(key, {'unit': key, 'status': 'not_run'})
        unit = manifest['units'][key]
        source = HERE / result['reused_from'] if result.get('reused_from') else root / key
        data = HERE / 'data' / key
        image = data / unit['image']
        projected = read(source / 'projected.json') if (source / 'projected.json').exists() else read(data / 'input.json')
        issues, calls, usage = request_audit(source, image, projected)
        audits[key] = {'issues': issues, 'response_count': calls, 'usage': usage, 'reused': bool(result.get('reused_from'))}
        if not result.get('reused_from'):
            responses += calls
            token_total.update(usage)
        statuses[result['status']] += 1
        option = (result.get('choice') or {}).get('option_label')
        basis = (result.get('choice') or {}).get('basis')
        if basis is not None:
            decision_basis_total += 1
            decision_basis_zh += basis in NEW_ZH
        option_counts['完成且给出选项' if result['status'] == 'completed' and option is not None
                      else '完成但未给出选项' if result['status'] == 'completed' else '未完成'] += 1
        checks = read(source / 'verify/accepted.json') if (source / 'verify/accepted.json').exists() else {'reviews': []}
        for reviewed in checks['reviews']:
            for observed in reviewed['O']:
                o_evidence_total += 1
                o_evidence_zh += observed['evidence'] in NEW_ZH
            evidence = reviewed.get('B', {}).get('evidence')
            if evidence is not None:
                b_evidence_total += 1
                b_evidence_zh += evidence in NEW_ZH
        byid = {r['id']: r for r in checks['reviews']}
        oc = Counter(o['status'] for r in checks['reviews'] for o in r['O'])
        bc = Counter(r['B']['status'] for r in checks['reviews'] if 'status' in r['B'])
        def counts_text(counts):
            return '、'.join(LABELS[s] + str(counts[s]) + '项' for s in ('supported', 'refuted', 'unclear'))
        model_counts = '原候选读法%d条。模型对O的判定：%s。' % (len(projected['records']), counts_text(oc))
        if bc:
            model_counts += '对B的判定：%s。' % counts_text(bc)
        if not checks['reviews']:
            model_counts += '本样本没有通过接口校验的完整核验输出；具体是已尝试失败还是未运行，见下面分阶段状态。'
        model_counts += '这些是模型给出的标签，不是人工确认或核验准确率。'
        content = '<aside>' + h(model_counts) + '</aside>'
        for rec in projected['records']:
            check = byid.get(rec['id'])
            rows = ''
            for i, o in enumerate(rec['O'], 1):
                judged = next((x for x in check['O'] if x['index'] == i), None) if check else None
                rows += '<tr><td>O%d</td><td>%s</td><td>%s</td></tr>' % (i, observation_view(o),
                    h(LABELS.get(judged['status'], judged['status'])) + '<br>' + evidence_text(judged['evidence']) if judged else '无可接受的完整核验输出')
            b = ''
            if check and 'status' in check['B']:
                b = '<p><b>读法及必要条件：%s</b></p>%s' % (h(LABELS[check['B']['status']]), evidence_text(check['B']['evidence']))
            elif check:
                b = ''.join('<p><b>%s：%s</b><br>%s</p>' % (
                    title, h(LABELS[check['B'][axis]['status']]), h(check['B'][axis]['evidence']))
                    for axis, title in [('visual_decoding', '视觉读法'), ('task_applicability', '任务适用')])
            if check and check['B'].get('reading_checked'):
                b = '<p><b>模型声称实际核对的读法/条件片段：</b><br>' + h(check['B']['reading_checked']) + '</p>' + b
            content += '<details><summary>%s — 原O/B与逐项核验</summary><table><thead><tr><th>编号</th><th>原观察 O（未改写）</th><th>被测模型的核验</th></tr></thead><tbody>%s</tbody></table><h4>原B（未经程序修正）</h4>%s%s</details>' % (h(rec['id']), rows, reading_view(rec['B']), b)
        image_bytes = image.read_bytes()
        image_src = 'data:image/' + ('jpeg' if image_bytes[:2] == b'\xff\xd8' else 'png') + ';base64,' + base64.b64encode(image_bytes).decode()
        note = read(source / 'read/accepted.json') if (source / 'read/accepted.json').exists() else None
        annotated = notes.get(key, confirmation_notes.get(key, '') if result.get('reused_from') else '')
        if unit['slug'] in ('b003', 'b006', 'b008'):
            annotated += ' 公开任务已要求使用标注份额，策略表原样含mislabeled_value；这是原页面提示性条件，不是本轮新增。按标注值选择有任务依据，不能把本例当成毫无来源提示时的自主优先级发现。'
        if unit['candidate_source'] == 'missing_old_input_supply_once':
            source_label = '旧链缺失；本轮Qwen单次补生成%d条候选' % len(projected['records']) if (source / 'supply/accepted.json').exists() else '旧链缺失；补生成尚无可接受输出'
        elif unit['candidate_source'] == 'Terra_runtime_aligned':
            source_label = '既有Terra候选（runtime-aligned）'
        else:
            source_label = '既有Qwen条件式候选（%s）' % unit.get('variant', '开发')
        if option is not None:
            choice_title = ZH_CACHE.get(option, {}).get('zh', option)
        elif result['status'] == 'completed':
            choice_title = '模型明确返回空选项（null）'
        elif (source / 'decide/request.json').exists():
            choice_title = '重新选择已尝试，但未取得可接受输出'
        else:
            choice_title = '重新选择未运行'
        raw = {stage: read(source / stage / 'accepted.json') for stage in ('read','verify','decide','supply') if (source / stage / 'accepted.json').exists()}
        if result['status'] != 'completed':
            raw['failure_record'] = result
            for rejected in sorted(source.glob('*/failure.json')):
                raw[rejected.parent.name + '_failure'] = read(rejected)
                raw[rejected.parent.name + '_raw_responses'] = [read(r) for r in sorted(rejected.parent.glob('response_*.json'))]
        request_view = {}
        for req_path in sorted(source.glob('*/request.json')):
            req = copy.deepcopy(read(req_path))
            req['messages'][1]['content'][1]['image_url']['url'] = '[图像原字节省略，SHA256=' + sha(image) + ']'
            request_view[req_path.parent.name] = req
        content += '<details><summary>完整实际请求（图片以哈希代替，上方展示原图）</summary>' + pre(request_view) + '</details>'
        old_file = HERE / 'offline_source' / (unit['slug'] + '.json')
        if unit['panel'] == 'full' and old_file.exists():
            content += '<details><summary>历史候选C与Terra旧建议（仅离线参考，不是本轮同模型基线）</summary>' + pre(bilingual(read(old_file))) + '</details>'
        if unit['panel'] == 'dev':
            old_dev = HERE.parent / 'ob_only_verification_20260926/run_live_001' / unit['variant'] / unit['slug'] / 'provenance_map.json'
            if old_dev.exists():
                content += '<details><summary>原候选C（仅离线展示，本轮未发送独立C字段）</summary>' + pre(read(old_dev)) + '</details>'
        if key in agreement:
            row = agreement[key]
            content += '<details><summary>与原标签的离线对齐（未发送模型，不是任务成功率）</summary>'
            content += '<p>本轮：%s；历史Terra建议：%s。跨模型对比不是同模型核验收益。</p>' % (h(AGREEMENT_CN.get(row['new_class'], row['new_class'])), h(AGREEMENT_CN.get(row['historical_class'], row['historical_class'])))
            content += pre(bilingual(row)) + '</details>'
        stages = '<details><summary>分阶段运行状态</summary><ul>' + ''.join('<li>%s：%s</li>' % (title, h(stage_state(source, stage))) for stage, title in [('supply', '补链（仅旧链缺失时）'), ('read', '独立读取'), ('verify', 'O/B核验'), ('decide', '重新选择')]) + '</ul></details>'
        domain_label = {'business47': '商业任务（47条）', 'environment35': '环境任务（35条）',
                        'health19': '健康任务（19条）', 'public39': '公共领域任务（39条）'}.get(unit.get('domain'), '开发输入')
        family_info = ('<details><summary>离线任务分类（未输入模型）</summary><p>%s · %s</p></details>' % (h(domain_label), h(unit.get('family', '开发输入'))))
        card = '<section id="%s"><h2>%s</h2><p>%s | 来源：%s%s</p><img loading="lazy" alt="原始输入图" src="%s"><h3>公开任务</h3><p>%s</p><details><summary>完整公开任务</summary>%s</details><h3>新选择：%s</h3><p>%s</p>%s<details><summary>候选不可见时的独立读取</summary>%s</details>%s<details><summary>原始模型结构化记录（英文原文）</summary>%s</details></section>' % (
            h(key), h(key), h(LABELS.get(result['status'], result['status'])), h(source_label), '；复用冻结确认结果' if result.get('reused_from') else '',
            image_src, h(ZH_CACHE.get(projected['goal'], {}).get('zh', projected['goal'])), pre(bilingual(projected['public_task'])), h(choice_title),
            evidence_text((result.get('choice') or {}).get('basis', '')), ('<aside><b>Codex离线审阅摘要（不是人工确认）</b><br>'+h(annotated)+'</aside>' if annotated else '') + stages + family_info, pre(note), content, pre(raw))
        card = card.replace('<section ', '<section data-state="%s" data-agreement="%s" ' % (h(result['status']), h(agreement.get(key, {}).get('new_class', 'unscored'))), 1)
        cards.append(card)
    audit = {'run': args.run, 'status': summary['status'], 'reported_units': len(cards), 'states': dict(statuses),
             'choice_presence_not_accuracy': dict(option_counts), 'new_archived_response_count': responses,
             'new_usage': dict(token_total), 'units': audits, 'request_input_isolation_audit_passed': not any(x['issues'] for x in audits.values()),
             'all_planned_units_completed': all(x.get('status') == 'completed' for x in [summary['units'].get(k, {}) for k in eligible]),
             'accepted_decision_reasons': decision_basis_total, 'decision_reasons_with_exact_source_chinese_summary': decision_basis_zh,
             'accepted_B_reasons': b_evidence_total, 'B_reasons_with_exact_source_chinese_summary': b_evidence_zh,
             'accepted_O_reasons': o_evidence_total, 'O_reasons_with_exact_source_chinese_summary': o_evidence_zh,
             'audit_scope': 'Only archived request projection, candidate fields and image identity; not response schema acceptance or semantic truth.',
             'semantic_verified': False, 'submitted': 0,
             'note': 'Counts do not prove correctness. Reused confirmation calls are not charged twice. All output text is fallible model output.'}
    (args.output / 'AUDIT.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    nav = ''.join('<a href="#%s">%s</a> ' % (h(k), h(k)) for k in eligible)
    overview = '<div class="overview"><h2>本页结果口径</h2><p>' + h('；'.join(LABELS.get(s, s) + str(n) + '条' for s, n in statuses.items())) + '。</p>'
    overview += '<p>' + h('；'.join(s + str(n) + '条' for s, n in option_counts.items())) + '。实际业务提交：0。</p>'
    if agreement_report:
        overview += '<p>本轮静态选项与原标签对齐：' + h('；'.join(AGREEMENT_CN.get(s, s) + str(n) + '条' for s, n in agreement_report['new_label_agreement_counts'].items())) + '。</p>'
    if panel == 'full':
        overview += '<p>140个official140原指定单图任务，来自21个核心任务家族；不是280个双条件运行，也不是140个独立任务类型。136个沿用Terra旧候选，4个缺失旧链仅补生成一次。原公开输入并非完全无提示：b003/b006/b008指定标注份额；pub019原图还印有Clean choropleth及深色为高值说明。全部原样保留，不按结果剔除。</p>'
    overview += '<p>O/B的“有依据支持”是模型判断；本页不提供140条人工核验准确率。新选择不是提交结果。原图、原任务及原标签均未修改。</p></div>'
    overview += '<p>已获得%d条重新选择理由，其中%d条提供按英文原文匹配的中文摘要；逐项核验依据仅部分有中文摘要，完整英文始终保留。中文摘要不是新增模型输出。</p>' % (decision_basis_total, decision_basis_zh)
    overview += '<p>已接受的B核验理由共%d条，其中%d条提供中文摘要；O核验依据及独立读取仍主要保留英文。中文只用于离线阅览，没有发给被测模型。</p>' % (b_evidence_total, b_evidence_zh)
    overview += '<p>已接受的O核验理由共%d条，其中%d条提供中文摘要；主要覆盖固定家族代表及少量明示的事后例证。独立读取仍保留英文。中文覆盖范围不等于人工语义审查范围。</p>' % (o_evidence_total, o_evidence_zh)
    if panel == 'full':
        examples = [('full_pub030', '公开规则与证据能对上'), ('full_b003', '原任务明确按标注值'),
                    ('full_health005', '原有正确读法被误反驳'), ('full_env033', 'O关系误反驳与漏数值锚点'),
                    ('full_health006', '发现范围缺口后仍越界选择'), ('full_env008', '保留真实通道冲突并未选'),
                    ('full_pub032', '读到数值锚点却仍跨轴比高度'), ('full_pub035', '反驳错误尺度后未利用可比较区间'),
                    ('full_pub038', '没有目标年标签不等于没有证据')]
        overview += '<aside><b>建议先阅览的具体例证</b>（事后说明现象，不是随机抽样或准确率估计）：<br>'
        overview += ' · '.join('<a href="#%s">%s：%s</a>' % (h(k), h(k[5:]), h(label)) for k, label in examples if k in eligible)
        overview += '</aside>'
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>O/B核验：独立读图与全量诊断</title><style>
body{max-width:1160px;margin:auto;padding:24px;background:#f5f6f8;color:#172638;font:16px/1.65 system-ui,sans-serif}h1,h2,h3{line-height:1.4}section{background:white;margin:24px 0;padding:24px;border-radius:12px;border:1px solid #d8e1e8}img{width:100%;height:auto;max-height:730px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f7;padding:12px;font-size:13px}details{border-top:1px solid #d8e1e8;padding:12px 0}summary{cursor:pointer;font-weight:600}table{width:100%;border-collapse:collapse;table-layout:fixed}td{border:1px solid #d8e1e8;padding:8px;vertical-align:top;overflow-wrap:anywhere}td:first-child{width:42px}aside{background:#fff1cb;padding:16px;border-left:4px solid #d99118}nav a{display:inline-block;margin:4px;color:#075a99}header{background:#e4eef8;padding:22px;border-radius:12px}@media(max-width:650px){body{padding:12px}section{padding:12px}td{font-size:13px}}
</style><header><h1>先独立读图，再核验 O/B</h1><p>本页为固定输入上的核验与重新选择诊断。没有业务提交；返回选项不等于任务成功。支持标签不是事实认证。</p><p>原候选、核验和选择全部保留。部分模型依据另有中文摘要，与Codex审阅旁注分开显示；英文原文始终保留，没有调用翻译API。</p>''' + '<p>'+h(args.run)+' | 预定面板 '+str(len(cards))+' 单元 | '+h(summary['status'])+'</p></header>'+overview+'<nav>'+nav+'</nav>'+''.join(cards)+'</html>'
    page = page.replace('</style>', 'h1,h2,h3,summary,nav a{overflow-wrap:anywhere}*{box-sizing:border-box}input{width:100%;padding:12px;font:inherit;margin:12px 0}</style>')
    page = page.replace('</style>', 'th{text-align:left;padding:8px;background:#e4eef8;border:1px solid #d8e1e8}th:first-child{width:42px}.location{font-size:13px;color:#46596a}@media(max-width:650px){table,tbody,tr,td{display:block;width:100%}thead{display:none}td:first-child{width:100%;background:#e4eef8;font-weight:600}td:last-child:before{content:"模型核验：";font-weight:600;display:block}}</style>')
    filters = '<input id="search" aria-label="搜索任务或记录" placeholder="搜索任务编号、原文或核验状态"><label>运行状态 <select id="state-filter"><option value="">全部</option>' + ''.join('<option value="%s">%s</option>' % (h(s), h(LABELS.get(s, s))) for s in statuses) + '</select></label> '
    filters += '<label>原标签对齐 <select id="agreement-filter"><option value="">全部</option>' + ''.join('<option value="%s">%s</option>' % (h(s), h(AGREEMENT_CN.get(s, s))) for s in agreement_report.get('new_label_agreement_counts', {})) + '</select></label><nav>'
    page = page.replace('<nav>', filters, 1)
    page = page.replace('<nav>', '<details' + (' open' if len(cards) <= 12 else '') + '><summary>任务索引（' + str(len(cards)) + '条）</summary><nav>', 1)
    page = page.replace('</nav>', '</nav></details>', 1)
    page = page.replace('</html>', '''<script>const boxes=[...document.querySelectorAll('section')];const search=document.getElementById('search'),sf=document.getElementById('state-filter'),af=document.getElementById('agreement-filter');let timer;function apply(){const q=search.value.toLowerCase().trim();boxes.forEach(s=>{s.style.display=s.textContent.toLowerCase().includes(q)&&(!sf.value||s.dataset.state===sf.value)&&(!af.value||s.dataset.agreement===af.value)?'':'none';});}search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,120);});sf.addEventListener('change',apply);af.addEventListener('change',apply);document.addEventListener('click',e=>{if(e.target.closest('a[href^="#"]')){clearTimeout(timer);search.value=sf.value=af.value='';apply();}});</script></html>''')
    (args.output / 'OB_GROUNDED_REVIEW.html').write_text(page, encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='units'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
