import json
from pathlib import Path
import tempfile
import unittest

import build_review as viewer
import run_panel
from bindings import SOURCE, read, dump
from test_panel import FakeAPI


class ViewerTests(unittest.TestCase):
    def fixture(self, root):
        run = root / 'run'
        config = read(Path(__file__).with_name('config.json'))
        run_panel.execute(config, SOURCE, run, FakeAPI())
        dump(run / 'config.json', config)
        dump(run / 'ledger.json', {'request_attempts': 0, 'paid_api_requests': 0, 'browser_operations': 0})
        dump(run / 'source_hashes.json', {})
        for name in ('prompts_ob.py', 'records_ob.py'):
            target = run / 'runtime_source/research/ob_only_verification_20260926' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(__file__).with_name(name).read_bytes())
        return run

    def test_portable_viewer_has_all_units_no_inference_column(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); run = self.fixture(root)
            target = viewer.build(run, root / 'review', {'overview': ['<unsafe>&说明']})
            text = target.read_text(encoding='utf-8')
            self.assertEqual(text.count('<img alt='), 4)
            self.assertEqual(text.count('原 O/B 与新核验</h4>'), 28)
            self.assertIn('&lt;unsafe&gt;&amp;说明', text)
            self.assertNotIn('src="http', text)
            self.assertNotIn('<script', text)
            with self.assertRaises(FileExistsError):
                viewer.build(run, root / 'review', {})

    def test_image_redaction_does_not_change_text(self):
        x = {'system': 'unchanged', 'image': 'data:image/png;base64,YWJj'}
        r = viewer.image_refs(x)
        self.assertEqual(r['system'], x['system'])
        self.assertIn(viewer.digest(b'abc'), r['image'])

    def test_null_choice_is_not_missing_response(self):
        self.assertNotEqual(viewer.decision_label({'decision': None}),
                            viewer.decision_label({'decision': {'option_label': None}}))

    def test_stopped_and_not_run_are_distinct(self):
        self.assertNotEqual(viewer.status_label({'status': 'prepared'}),
                            viewer.status_label({'status': 'stopped_transport_or_budget'}))


if __name__ == '__main__':
    unittest.main()
