"""Offline view/export layer, separate from frozen English API records."""
import argparse
import copy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import panel_core as core
import run_panel as runner
import render_viewer
import native_zh

LABELS = {'ref': '来源引用', 'location': '来源内位置',
 'task_evidence': '公开任务文字引用（非图像观察）',
 'source_kind': '来源类型', 'source_field': '公开字段位置',
 'source_text': '请求中实际公开字段原文',
 'binding_status': '来源绑定状态（不代表转述含义已验证）',
 'native_translation_provenance': '本轮原生中文翻译溯源',
 'review_flags': '另列的审阅提示（非模型输出）'}

STATE_ZH = {'supported': '模型判为有支持', 'refuted': '模型判为被反驳',
    'undetermined': '模型未能确定／证据不足', 'active': '规则生效（模型状态，不代表整链成立）',
    'revoked': '已撤销（模型核验后的规则状态）', 'pending': '待确定',
    'disputed': '存在争议'}


def add_state_labels(task):
    """Deterministic Chinese UI labels for machine statuses omitted by text translator."""
    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = path + '.' + key
                if key in ('O','B','implication','status','from_status','to_status') and isinstance(child, str) and child in STATE_ZH:
                    task['translations']['items'][child_path] = STATE_ZH[child]
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, path + '.' + str(index))
    for name in ('verification','verification_raw','verification_invalid_raw','rule_state'):
        visit(task.get(name), name)


def compose(destination=None):
    translations, warnings, origins = native_zh.load_translations()
    catalog = core.read(HERE.parent / 'catalog.json')
    state = core.read(HERE / 'run/run_state.json', {})
    budget = core.read(HERE / 'run/budget.json', {'request_attempts': 0})
    notes = core.read(HERE / 'semantic_review.json', {})
    failures = core.read(HERE / 'failure_audit.json', [])
    tasks = []
    for entry, original in zip(catalog['tasks'], native_zh.records()):
        task = copy.deepcopy(original)
        required = native_zh.items(task)
        task['translation_items'] = required
        task['translations'] = {'items': {row['key']: translations[native_zh.sid(row['text'])]
            for row in required if native_zh.sid(row['text']) in translations}}
        missing = [row['key'] for row in required if native_zh.sid(row['text']) not in translations]
        task['status']['translation'] = 'not_run' if missing else 'completed'
        task['native_translation_provenance'] = {
            'producer': 'codex-native', 'apiyi_translation_calls': 0,
            'complete_keys': len(task['translations']['items']), 'missing_keys': missing,
            'source_files': sorted({origins[native_zh.sid(row['text'])] for row in required
                                   if native_zh.sid(row['text']) in origins}),
            'source_record_sha256': core.digest(HERE / 'run/tasks' / task['task_slug'] / 'record.json')
                if (HERE / 'run/tasks' / task['task_slug'] / 'record.json').exists() else None}
        add_state_labels(task)
        task['native_translation_provenance']['machine_status_labels'] = 'Deterministic Chinese UI glossary in make_view.py; original values retained.'
        offline = core.read(HERE.parent / entry['offline_file'])
        task['offline_metadata'] = {k: offline.get(k) for k in ('original_mechanism',
            'audited_mechanism', 'original_plot', 'audit_note', 'review_records', 'evidence_limit_flags')}
        chains = (task.get('normalized') or {}).get('chains', [])
        options = {chain.get('option_label') for chain in chains}
        flags = ['这是静态图表解释与核验，不是已执行的网页提交；核验完成不代表解释已获人工确认。']
        if len(chains) < 2 and task['status']['generation'] == 'completed':
            flags.append('本条只有一条解释链；未强行补写竞争解释。')
        elif len(chains) >= 2 and len(options) < 2:
            flags.append('本条有多条解释，但指向相同选项，不能视为不同任务行动的竞争。')
        if task.get('provenance', {}).get('reuse'):
            flags.append('英文三阶段复用已完成的两例兼容性检查，不计作本轮新 API 调用。')
        if task['task_slug'] == 'b001':
            flags.append('待人工复核：核验用几何大小“接近”反驳“略大”，这一否定可能过强。原输出保留，译文不修正。')
        for failure in failures:
            if failure['task'] != task['task_slug']:
                continue
            reason = failure.get('reason', failure['status'])
            if reason == 'output_length_limit':
                flags.append('本次回答达到预设输出长度上限，核验未完成；原始截断片段已保留，未补全。')
            elif reason == 'invalid_json_on_normal_stop':
                flags.append('接口解析失败：模型标为正常停止，但返回的 JSON 语法无效；不是长度截断。原文保留，不补写为有效核验。')
            elif reason.startswith('task citation field unavailable:'):
                flags.append('接口失败：公开任务引用的位置不是现有字段路径。此失败本身不代表图表理解错误。')
            elif reason == 'rule contains an action label instead of an interpretation':
                flags.append('校验拒绝：规则文字包含某个完整选项字样，触发既有字面过滤。须结合原文判断是否属于过度拒绝，不能直接据此判定视觉理解错误。')
            elif reason == 'unobserved evidence source':
                flags.append('接口拒绝：核验引用的来源标记未能匹配本次请求允许的公开来源。须查看实际引用，不能仅凭这个错误判断图表结论是否正确。')
            elif reason == 'candidate observations lack chart provenance':
                flags.append('接口拒绝：观察记录缺少协议要求的图像来源标记。原始解释保留，未转为有效规则状态。')
            else:
                flags.append('保留的接口／校验失败（不自动等同于视觉理解错误）：' + reason)
        flags.extend(notes.get(task['task_slug'], []))
        task['review_flags'] = flags
        tasks.append(task)
    summary = {'total_tasks': len(tasks), 'request_attempts': budget['request_attempts'],
        'generated': sum(t['status']['generation'] == 'completed' for t in tasks),
        'verified': sum(t['status']['verification'] == 'completed' for t in tasks),
        'translated': sum(t['status']['translation'] == 'completed' for t in tasks),
        'run_status': state.get('status'), 'blocked_reason': state.get('blocked_reason'),
        'apiyi_translation_calls': 0, 'browser_operations': 0,
        'scope': 'static explanations only; not defense efficacy or GUI completion'}
    result = {'schema_version': 'obc140_review_v1', 'generated_at': runner.now(),
        'title': '140 条原图任务 · Terra 解释链与原生中文阅览', 'summary': summary,
        'field_labels': LABELS, 'tasks': tasks,
        'protocol': core.read(HERE / 'config.json'), 'translation_warnings': warnings}
    core.dump(destination or HERE / 'review_data_zh.json', result)
    return result


def make(browser_check=False, preview=False):
    source = HERE / ('review_data_preview.json' if preview else 'review_data_zh.json')
    result = compose(source)
    template = render_viewer.TEMPLATE_PATH.read_text(encoding='utf-8')
    template = template.replace('const literalKeys = new Set([',
        'const literalKeys = new Set(["task_alias","chart","field","type",')
    anchor = 'container.append(panel); renderChart(task,container);'
    addition = 'for(const flag of (task.review_flags||[])) panel.append(el("div","notice",flag)); '
    if template.count(anchor) != 1:
        raise ValueError('viewer template changed: review flag insertion requires inspection')
    template = template.replace(anchor, addition + anchor)
    summary_anchor = 'const messages=[]; if(catalog.summary?.blocked_reason)'
    if template.count(summary_anchor) != 1:
        raise ValueError('viewer summary changed: inspect before rendering')
    template = template.replace(summary_anchor,
        'const messages=["静态解释材料，不是网页执行成功率；中文为 Codex 原生翻译。生成时运行状态："+({running:"处理中",completed:"固定队列三阶段全部完成",finished_with_terminal_failures:"固定队列已处理完，含保留的失败",blocked:"已停止，存在阻塞"}[catalog.summary?.run_status]||String(catalog.summary?.run_status||"unknown"))]; if(catalog.summary?.blocked_reason)')
    row_anchor = 'state.append(stateBadge(statusOf(task,"generation")));'
    if template.count(row_anchor) != 1:
        raise ValueError('viewer row status changed: inspect before rendering')
    template = template.replace(row_anchor,
        'state.append(el("span","muted","生成 "),stateBadge(statusOf(task,"generation")),el("span","muted"," · 核验 "),stateBadge(statusOf(task,"verification")));')
    chain_anchor = 'const candidate=task[chainSource],base=chainSource;'
    if template.count(chain_anchor) != 1:
        raise ValueError('viewer chain source changed: inspect before rendering')
    template = template.replace(chain_anchor,
        'const rejected=chainSource==="generated"&&!task.generated&&task.generation_invalid_raw&&Array.isArray(task.generation_invalid_raw.chains); '
        'const base=rejected?"generation_invalid_raw":chainSource,candidate=task[base]; '
        'if(rejected)panel.append(el("div","notice danger","以下为模型原始解释草稿，未通过结构校验；仅供阅览，未转成有效规则状态，也未人工修正。"));')
    template = template.replace('["provenance","数据溯源"]',
        '["provenance","数据溯源"],["native_translation_provenance","原生中文翻译溯源"],["display_failure_outputs","失败阶段的原始回答片段（未修复或补全）"],["display_failure_provenance","失败回答来源与截断状态"]')
    template_path = HERE / 'viewer_template_native.html'
    template_path.write_text(template, encoding='utf-8')
    destination = HERE / ('PREVIEW_IN_PROGRESS.html' if preview else 'OBC140_TERRA_ZH_REVIEW.html')
    provenance = render_viewer.render(source, destination,
                                      template_path=template_path, field_labels=LABELS)
    core.dump(HERE / ('preview_provenance.json' if preview else 'view_provenance.json'), provenance)
    if browser_check:
        from playwright.sync_api import sync_playwright
        issues, external, seen = [], [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True,
                executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
            try:
                page = browser.new_page(viewport={'width': 1500, 'height': 1080})
                page.on('pageerror', lambda error: issues.append(str(error)))
                page.on('request', lambda request: external.append(request.url)
                        if request.url.startswith(('http://', 'https://')) else None)
                page.goto(destination.as_uri())
                assert page.locator('.task-row').count() == 140
                for task in result['tasks']:
                    slug = task['task_slug']
                    page.locator('.task-row[data-slug="' + slug + '"]').click()
                    assert page.locator('.task-code').inner_text() == slug
                    assert page.locator('.chart-button img').evaluate('n => n.complete && n.naturalWidth > 0')
                    candidate = task.get('generated') or task.get('generation_invalid_raw') or {}
                    expected = candidate.get('chains', []) if isinstance(candidate, dict) else []
                    expected_count = len(expected) if isinstance(expected, list) else 0
                    assert page.locator('#chains-panel article.chain').count() == expected_count, slug
                    if not task.get('generated') and expected_count:
                        assert '未通过结构校验' in page.locator('#chains-panel').inner_text(), slug
                    seen.append(slug)
                for slug in ('b001', 'b010', 'b011', 'pub013', result['tasks'][-1]['task_slug']):
                    page.locator('.task-row[data-slug="' + slug + '"]').click()
                    page.click('[data-language="zh"]')
                    page.locator('#chains-panel').scroll_into_view_if_needed()
                    page.screenshot(path=str(HERE / (('preview_' if preview else 'view_') + slug + '.png')))
                assert not issues, issues
                assert not external, external
            finally:
                browser.close()
        core.dump(HERE / ('preview_browser_check.json' if preview else 'browser_check.json'), {'status': 'PASS', 'tasks_rendered': seen,
            'scope': 'offline_reading_only', 'javascript_errors': issues, 'external_requests': external,
            'html_sha256': core.digest(destination), 'review_data_sha256': core.digest(source),
            'displayed_chain_counts_match': True, 'invalid_drafts_labeled': True,
            'model_requests': 0, 'business_actions': 0})
    print(json.dumps({'html': str(destination), 'summary': result['summary'],
                      'translation_warnings': len(result['translation_warnings'])}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-check', action='store_true')
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    make(args.browser_check, args.preview)
