"""Read-only final invariant audit. No inference and no result repairs."""
import base64
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import panel_core as core
import native_zh


def terminal_api_record(record):
    states = [record['status'][phase] for phase in ('proposal', 'generation', 'verification')]
    return (all(status == 'completed' for status in states)
            or (states[0] in {'failed', 'invalid'} and states[1:] == ['not_run', 'not_run'])
            or (states[0] == 'completed' and states[1] in {'failed', 'invalid'}
                and states[2] == 'not_run')
            or (states[:2] == ['completed', 'completed']
                and states[2] in {'failed', 'invalid'}))


def verify():
    run = HERE / 'run'
    run_state = core.read(run / 'run_state.json')
    assert run_state.get('status') in {'completed', 'finished_with_terminal_failures'}, run_state
    prepared_marker = HERE / 'translations/ALL_INPUTS_PREPARED'
    assert prepared_marker.is_file(), 'native translation inputs are not finalized'
    prepared = core.read(prepared_marker)
    assert prepared.get('run_status') == run_state['status'], ('stale translation input marker', prepared)
    runtime = core.read(run / 'runtime.json')
    for name, expected in runtime['source_sha256'].items():
        assert core.digest(HERE.parent.parent / name) == expected, ('runtime source changed', name)
        assert core.digest(run / 'runtime_source' / name) == expected, ('snapshot changed', name)
    snapshot = core.read(run / 'inputs_snapshot.json')
    canonical_slugs = [row['task_slug'] for row in snapshot]
    assert len(canonical_slugs) == len(set(canonical_slugs)) == 140
    manifest = {row['task_slug']: row for row in snapshot}
    budget = core.read(run / 'budget.json')
    assert budget['request_attempts'] == len(budget['events']) <= 450
    event_ids = {(e['task_slug'], e['phase'], e['round'], e['attempt']) for e in budget['events']}
    assert len(event_ids) == len(budget['events'])
    assert not any(e['phase'] == 'translation' for e in budget['events'])
    assert all(e['task_slug'] not in ('b001','pub013') for e in budget['events'])
    model_requests, reused_requests = 0, 0
    missing_meta = []
    pending_tasks = []
    record_sha256 = {}
    for slug, item in manifest.items():
        assert core.digest(item['public_path']) == item['public_sha256']
        assert core.digest(item['chart_path']) == item['chart_sha256']
        public = core.read(item['public_path'])
        record_path = run / 'tasks' / slug / 'record.json'
        record = core.read(record_path)
        relative_record = record_path.relative_to(HERE).as_posix()
        record_sha256[relative_record] = core.digest(record_path)
        if not terminal_api_record(record):
            pending_tasks.append({'task_slug': slug, 'status': record['status']})
        assert record['public_task'] == public
        assert record['status']['translation'] == 'not_run'
        assert record['translations'] == {'items': {}}
        for request in (run / 'tasks' / slug).glob('*/round_*/request.json'):
            phase = request.parent.parent.name
            assert phase in ('proposal','generation','verification')
            body = core.read(request)
            assert body['model'] == 'gpt-5.6-terra' and body['temperature'] == 0
            content = body['messages'][1]['content']
            context = json.loads(content[0]['text'])
            core.engine.assert_public(context)
            assert context['task'] == public
            assert context['history'] == []
            assert len(content) == 3
            image = base64.b64decode(content[2]['image_url']['url'].split(',', 1)[1], validate=True)
            assert hashlib.sha256(image).hexdigest() == item['chart_sha256']
            if slug in ('b001','pub013'):
                reused_requests += 1
            else:
                model_requests += 1
    assert not pending_tasks, ('non-terminal canonical records', pending_tasks)
    for event in budget['events']:
        path = Path(event['folder']) / ('attempt_%02d.json' % event['attempt'])
        if not path.exists():
            missing_meta.append(str(path))
    translations, warnings, _ = native_zh.load_translations()
    missing_translations = []
    for record in native_zh.records():
        for row in native_zh.items(record):
            if native_zh.sid(row['text']) not in translations:
                missing_translations.append(record['task_slug'] + ':' + row['key'])
    review_path = HERE / 'review_data_zh.json'
    review = core.read(review_path)
    review_rows = review['tasks']
    review_slugs = [row['task_slug'] for row in review_rows]
    assert review_slugs == canonical_slugs, ('review task identity/order changed', review_slugs)
    for row in review_rows:
        relative_record = 'run/tasks/%s/record.json' % row['task_slug']
        actual = row['native_translation_provenance']['source_record_sha256']
        assert actual == record_sha256[relative_record], ('stale review task', row['task_slug'])
    assert review['summary']['run_status'] == run_state['status'], ('stale review run status', review['summary'])
    review_data_sha256 = core.digest(review_path)
    view_provenance = core.read(HERE / 'view_provenance.json')
    assert view_provenance['source_sha256'] == review_data_sha256, 'viewer source is stale'
    assert view_provenance['task_count'] == 140
    html_path = HERE / 'OBC140_TERRA_ZH_REVIEW.html'
    html_sha256 = core.digest(html_path)
    browser_check = core.read(HERE / 'browser_check.json')
    assert browser_check.get('status') == 'PASS', browser_check
    assert browser_check.get('tasks_rendered') == canonical_slugs, 'browser check task coverage changed'
    assert browser_check.get('javascript_errors') == [], browser_check
    assert browser_check.get('external_requests') == [], browser_check
    assert browser_check.get('html_sha256') == html_sha256, 'browser check HTML is stale'
    assert browser_check.get('review_data_sha256') == review_data_sha256, 'browser check review data is stale'
    incomplete = bool(missing_meta or missing_translations or warnings)
    summary = {'engineering_status': 'INCOMPLETE' if incomplete else 'PASS',
        'scope': 'Engineering/provenance only, not semantic correctness',
        'run_status': run_state['status'], 'tasks_checked': len(manifest), 'terminal_tasks': 140,
        'pending_tasks': [], 'all_inputs_prepared': True,
        'new_logical_request_files': model_requests,
        'reused_logical_request_files': reused_requests, 'new_attempts': budget['request_attempts'],
        'api_translation_calls': 0, 'original_inputs_unchanged': True, 'runtime_sources_unchanged': True,
        'english_records_untranslated': True, 'all_request_images_match_original': True,
        'public_context_projection_passed': True, 'missing_attempt_metadata': missing_meta,
        'missing_native_translations': missing_translations, 'translation_numeric_warnings': warnings,
        'record_sha256': record_sha256, 'html_sha256': html_sha256,
        'review_data_sha256': review_data_sha256, 'browser_check_status': browser_check['status'],
        'actual_bill_verified': False}
    core.dump(HERE / 'delivery_checks.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    verify()
