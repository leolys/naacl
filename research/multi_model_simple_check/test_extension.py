"""Focused checks only; scripted browser fixture is not chart/model evidence."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from research.decision_evidence_audit import core, models, runner
from research.prospective_simple_check_pilot import panel
from research.prospective_simple_check_pilot.test_panel import fixture_manifest, fixture_raw, ImageRouteMock
from .run import single_manifest, LocalBackend, startup_retry_source
from research.prospective_simple_check_pilot.api_backend import ApiStop
from .server import image_tiles
from .settings import SOURCE_MANIFEST, BROWSER


class ExtensionTests(unittest.TestCase):
    def test_startup_retry_rejects_consumed_calls_or_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'new_model'
            budget = dict(model_calls=0,browser_transitions=0,events=[])
            core.write_json(source/'budget.json',budget)
            core.write_json(source/'progress.json',dict(prefixes=[],rows=[dict(prefix_started=False)]))
            core.write_json(source/'extension_failure.json',dict(error_type='TimeoutError',error='BrowserType.launch: Timeout 20000ms exceeded.'))
            with patch('research.multi_model_simple_check.run.RUN_ROOT', root):
                self.assertEqual(startup_retry_source('new_model'),source)
                budget['model_calls']=1
                core.write_json(source/'budget.json',budget)
                with self.assertRaises(RuntimeError): startup_retry_source('new_model')
                budget['model_calls']=0
                core.write_json(source/'budget.json',budget)
                core.write_json(source/'progress.json',dict(prefixes=[{}],rows=[dict(prefix_started=True)]))
                with self.assertRaises(RuntimeError): startup_retry_source('new_model')

    def test_local_service_failure_stops_panel_without_implicit_retry(self):
        import requests
        backend = LocalBackend.__new__(LocalBackend)
        backend.url, backend.session = 'http://127.0.0.1:18767', Mock()
        backend.session.post.side_effect = requests.HTTPError('synthetic 500')
        request = models.OnlineRequest('id', 'prefix', 'system', 'user', (Path('visible.png'),), ('visible.png',))
        with self.assertRaises(ApiStop):
            backend.complete(request)
        backend.session.post.assert_called_once()

    def test_original_schedule_requires_both_old_models(self):
        manifest = fixture_manifest()
        manifest['case_interleaved_order'] = manifest['case_interleaved_order'][:1]
        with self.assertRaises(ValueError):
            panel.validate_schedule(manifest)

    def test_single_schedule_is_explicit_complete_and_keeps_source(self):
        original = json.loads(SOURCE_MANIFEST.read_text())
        before = copy.deepcopy(original)
        manifest = single_manifest(original, 'new_model')
        self.assertEqual(original, before)
        self.assertEqual(len(manifest['case_interleaved_order']), 16)
        self.assertEqual(manifest['rows'], before['rows'])
        with self.assertRaises(ValueError):
            panel.validate_schedule(manifest)
        panel.validate_schedule(manifest, backbones=('new_model',))
        manifest['case_interleaved_order'].pop()
        with self.assertRaises(ValueError):
            panel.validate_schedule(manifest, backbones=('new_model',))

    def test_tiling_records_native_bounded_tiles(self):
        for size in ((180,120),(1440,1100),(6000,200)):
            tiles = image_tiles(Image.new('RGB', size))
            self.assertTrue(1 <= len(tiles) <= 13)
            self.assertTrue(all(im.size == (448,448) for im in tiles))

    def test_single_offline_report_no_fake_models_or_recovery(self):
        manifest = fixture_manifest()
        schedule = [u for u in manifest['case_interleaved_order'] if u['model'] == 'M_small']
        for i,u in enumerate(schedule,1):
            u.update(ordinal=i, model='new_model')
        manifest['case_interleaved_order'] = schedule
        with tempfile.TemporaryDirectory() as temp:
            result = panel.offline_report(manifest, dict(rows=panel.initial_rows(schedule)), core.BudgetLedger(),
                Path(temp), raw_loader=fixture_raw, mock=True, backbones=('new_model',))
        self.assertEqual(len(result['groups']), 2)
        for group in result['groups']:
            self.assertEqual(group['model'], 'new_model')
            self.assertEqual(group['error_checkpoint_count'], 0)
            self.assertTrue(all(s['recovery_fraction'] == 'N/A' for s in group['strategies']))


def browser_fixture(output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    manifest = fixture_manifest()
    schedule = [u for u in manifest['case_interleaved_order'] if u['model'] == 'M_small']
    for i,u in enumerate(schedule,1):
        u.update(ordinal=i, model='new_model')
    manifest['case_interleaved_order'] = schedule
    blank = root / 'blank.png'
    Image.new('RGB', (300,180), 'white').save(blank)
    ledger = core.BudgetLedger(max_model_calls=50, max_browser_transitions=150)
    ledger.bind_snapshot(root / 'mock_budget.json')
    view = panel.ModelBudget(ledger, 'new_model', 50)
    model = models.RecordedModel(ImageRouteMock(initial_wrong=True, crop=True), ledger=view)
    with runner.require_playwright()() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(runner.BROWSER_LAUNCH_ARGS))
        try:
            result = panel.execute_schedule(browser, manifest, {'new_model':model}, {'new_model':view}, ledger, root,
                resolve_public=lambda row, arm: (row['public_task'], blank), backbones=('new_model',))
        finally:
            browser.close()
    summary = panel.offline_report(manifest, result, ledger, root,
        raw_loader=fixture_raw, mock=True, backbones=('new_model',))
    assert len(result['prefixes']) == 2 and len(result['rows']) == 6
    assert all(r['submitted'] and r['confirmation_observed'] for r in result['rows'])
    for row in result['rows']:
        if row['strategy'] == 'B0':
            assert row['actor_final_submission']['option'] == 'Route B'
        else:
            assert row['verifier_recommendation'] == row['executor_selection'] == row['actor_final_submission']['option'] == 'Route A'
    assert not (root / 'stop.json').exists()
    core.write_json(root / 'TEST_RESULT.json', dict(passed=True, real_model_calls=0,
        mock_model_calls=ledger.model_calls, actual_browser_transitions=ledger.browser_transitions,
        actual_local_submissions=6, diagnostic='scripted nonchart engineering only'))
    print((root / 'TEST_RESULT.json').read_text())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-output', type=Path, required=True)
    args = parser.parse_args()
    browser_fixture(args.browser_output)
