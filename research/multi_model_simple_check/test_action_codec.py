"""Small syntax/receipt boundary checks; no chart understanding claims."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from research.decision_evidence_audit import core, models, runner
from research.prospective_simple_check_pilot import panel
from research.prospective_simple_check_pilot.panel_controls import route_task
from research.prospective_simple_check_pilot.harness import TransitionScope, capture_pending, run_branch
from .action_codec import ActionCodecModel, normalize
from .run_action_codec import NAME, continuation_source
from .settings import BROWSER


def wrapped(action):
    return json.dumps(dict(action=action, executed=True, error='', attempt=1,
        after_url_path='/task/control/complete'))


class ActionCodecTests(unittest.TestCase):
    def test_flat_actor_output_is_byte_identical(self):
        for text in (' {"action": "click_button", "text":"Submit Form"}\n',
                     '```json\n{"action":"select_option","select_name":"primary_action","option_text":"Route B"}\n```',
                     'some prose {"action":"click_link","text":"Open Form"}'):
            self.assertEqual(normalize(text)[0], text)

    def test_wrapper_keeps_only_legal_action(self):
        action = dict(action='select_option', select_name='primary_action', option_text='Route B')
        text, audit = normalize(wrapped(dict(action, executed=True, url='https://irrelevant.invalid')))
        self.assertEqual(json.loads(text), action)
        self.assertEqual(audit['status'], 'unwrapped')
        self.assertIn('executed', audit['discarded_outer_fields'])
        self.assertIn('url', audit['discarded_inner_fields'])

    def test_wrapped_finish_preserves_no_submit_stopping(self):
        output, audit = normalize(wrapped(dict(action='finish')))
        self.assertEqual(runner._extract_action(output), dict(action='finish'))
        self.assertEqual(audit['status'], 'unwrapped')

    def test_malformed_envelopes_do_not_invent_or_execute_actions(self):
        for inner in ({'action':'goto', 'text':'https://irrelevant.invalid'},
                      {'action':{'action':'click_button','text':'Submit Form'}},
                      {'action':'select_option','select_name':'primary_action'},
                      {'action':'select_option','select_name':True,'option_text':'Route B'},
                      {'action':'click_button','text':['Submit Form']}):
            output, audit = normalize(wrapped(inner))
            self.assertEqual(json.loads(output), {'action':'invalid'})
            self.assertEqual(audit['status'], 'rejected_invalid_envelope')

    def test_verifier_output_is_not_unwrapped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backend = Mock()
            original = wrapped(dict(action='click_button', text='Submit Form'))
            backend.complete.return_value = models.ModelReply(original)
            model = ActionCodecModel(backend, ledger=core.BudgetLedger())
            reply = model.call(phase='b3_plan', system_prompt='s', user_prompt='u', image_path=root/'image.png',
                image_artifact='image.png', public_context={}, request_dir=root/'requests', response_dir=root/'responses')
            self.assertEqual(reply.text, original)
            self.assertFalse((root/'action_codec').exists())

    def test_raw_output_preserved_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = wrapped(dict(action='select_option', select_name='primary_action', option_text='Route B'))
            backend = Mock()
            backend.complete.return_value = models.ModelReply(original, {'usage':{'completion_tokens':23}})
            ledger = core.BudgetLedger()
            model = ActionCodecModel(backend, ledger=ledger)
            reply = model.call(phase='actor_continuation', system_prompt='s', user_prompt='u', image_path=root/'image.png',
                image_artifact='image.png', public_context={}, request_dir=root/'requests', response_dir=root/'responses')
            self.assertEqual(json.loads((root/'responses/request_0001.json').read_text())['text'], original)
            self.assertEqual(json.loads(reply.text)['option_text'], 'Route B')
            self.assertNotIn('executed', json.loads(reply.text))
            self.assertEqual(ledger.model_calls, 1)
            self.assertTrue((root/'action_codec/request_0001.json').exists())

    def test_control_continuation_carries_budget_and_blocks_chart_resampling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/(NAME+'_startup_retry01')
            ledger = core.BudgetLedger(max_model_calls=5, max_browser_transitions=20)
            view = panel.ModelBudget(ledger, NAME, 5)
            view.charge_model(phase='prefix', request_id='request_0001')
            view.charge_transition(phase='control_setup', action={'action':'click_link','text':'Open Form'})
            core.write_json(source/'budget.json', ledger.to_dict())
            core.write_json(source/'extension_failure.json', dict(error='public-route interface control failed; panel not started'))
            core.write_json(source/'progress.json', dict(prefixes=[], rows=[dict(prefix_started=False)]))
            with patch('research.multi_model_simple_check.run_action_codec.RUN_ROOT', root):
                self.assertEqual(continuation_source(), source)
                fresh = core.BudgetLedger(max_model_calls=1, max_browser_transitions=20)
                panel.carry_in_budget(fresh, source)
                self.assertEqual((fresh.model_calls, fresh.browser_transitions), (1, 1))
                with self.assertRaises(core.BudgetExceeded):
                    panel.ModelBudget(fresh, NAME, 1).charge_model(phase='prefix', request_id='request_0002')
                core.write_json(source/'progress.json', dict(prefixes=[{}], rows=[dict(prefix_started=True)]))
                with self.assertRaises(RuntimeError): continuation_source()


def browser_fixture(output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    image = root/'blank.png'
    Image.new('RGB', (300,180), 'white').save(image)
    task = route_task()
    task['user_goal'] = 'Choose Route B and submit.'
    backend = Mock()
    backend.complete.side_effect = [
        models.ModelReply(wrapped(dict(action='select_option',select_name='primary_action',option_text='Route B'))),
        models.ModelReply(wrapped(dict(action='click_button',text='Submit Form')))]
    ledger = core.BudgetLedger(max_model_calls=2, max_browser_transitions=20)
    ledger.bind_snapshot(root/'mock_budget.json')
    view = panel.ModelBudget(ledger, 'mock_codec', 2)
    model = ActionCodecModel(backend, ledger=view)
    submissions = root/'server_receipts.jsonl'
    with runner.require_playwright()() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER),
            args=list(runner.BROWSER_LAUNCH_ARGS), timeout=120000)
        try:
            with runner.managed_shell(task, image, submissions) as server:
                page = browser.new_page(viewport=dict(width=1440,height=1100))
                executor = runner.BrowserExecutor(page, ledger=TransitionScope(view), task_alias='control')
                executor.navigate(server.base_url+'/task/control', phase='control_setup')
                for action in (dict(action='click_link',text='Open Dashboard'),dict(action='click_link',text='Open Form'),
                    dict(action='select_option',select_name='primary_action',option_text='Route A')):
                    executor.execute(action, phase='control_setup')
                cp, result = capture_pending(page,executor,model,goal=task['user_goal'],alias='control',
                    directory=root/'prefix', max_calls=2)
                assert cp is not None and cp.current_selection == 'Route B'
                assert not submissions.exists() or not submissions.read_text().strip()
                assert executor.receipts[-1]['executed'] and executor.receipts[-1]['action']['option_text']=='Route B'
                # The model claimed completion before it really occurred. Only B0 now submits.
                branch = run_branch(page,executor,model,cp,strategy='B0',directory=root/'B0',
                    prefix_receipts=executor.receipts[:],submission_path=submissions)
                assert branch['submitted'] and branch['confirmation_observed']
                assert branch['server_receipts'][0]['selected_option_label']=='Route B'
                core.write_json(root/'execution_receipts.json',executor.receipts)
                page.close()
        finally:
            browser.close()
    core.write_json(root/'TEST_RESULT.json',dict(passed=True,real_model_calls=0,mock_model_calls=ledger.model_calls,
        actual_browser_transitions=ledger.browser_transitions,actual_local_submissions=1,
        diagnostic='scripted public-route syntax/receipt boundary only'))
    print((root/'TEST_RESULT.json').read_text())


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--browser-output', type=Path, required=True)
    browser_fixture(p.parse_args().browser_output)
