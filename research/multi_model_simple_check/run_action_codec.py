"""Explicitly authorized one-time pre-chart interface continuation for Qwen32."""
import argparse
import json
import shutil
import traceback

from research.decision_evidence_audit import core, runner
from research.prospective_simple_check_pilot import panel
from research.prospective_simple_check_pilot.panel_controls import qualify
from .action_codec import ActionCodecModel, VERSION
from .run import prepare, digest, LocalBackend
from .retry_startup import check_identity
from .settings import RUN_ROOT, PACKAGE, CONFIGS, BROWSER

NAME = 'qwen3_32b'
ATTEMPT = NAME + '_action_codec_v2'


def continuation_source():
    source = RUN_ROOT / (NAME + '_startup_retry01')
    progress = json.loads((source / 'progress.json').read_text())
    failure = json.loads((source / 'extension_failure.json').read_text())
    budget = json.loads((source / 'budget.json').read_text())
    if (progress['prefixes'] or any(r['prefix_started'] for r in progress['rows'])
        or list((source / 'online').glob('unit_*'))
        or (source / 'qualification.json').exists()
        or failure.get('error') != 'public-route interface control failed; panel not started'
        or any('/controls/' not in e['phase'] for e in budget['events'])
        or budget['model_calls'] <= 0):
        raise RuntimeError('Only the recorded pre-chart control failure can be continued')
    return source


def run():
    source = continuation_source()
    identity = check_identity(NAME, source)
    prepare()
    root = RUN_ROOT / ATTEMPT
    root.mkdir(exist_ok=False)
    ledger = core.BudgetLedger(max_model_calls=400, max_browser_transitions=2000)
    panel.carry_in_budget(ledger, source)
    prior_calls, prior_transitions = ledger.model_calls, ledger.browser_transitions
    ledger.bind_snapshot(root / 'budget.json')
    manifest_path = RUN_ROOT / f'TASK_MANIFEST_{NAME}.json'
    manifest = json.loads(manifest_path.read_text())
    panel.snapshot_sources(root)
    shutil.copytree(PACKAGE, root / 'executed_sources/research/multi_model_simple_check',
        ignore=shutil.ignore_patterns('runs', 'runtime', 'backups', '__pycache__'))
    shutil.copy2(manifest_path, root / 'TASK_MANIFEST.json')
    core.write_json(root / 'MODEL_CONFIG.json', dict(**CONFIGS[NAME], name=NAME,
        gpu='7', browser=str(BROWSER), browser_sha256=digest(BROWSER), browser_launch_timeout_ms=120000,
        action_codec_version=VERSION, explicit_user_authorization=True,
        frozen_plan_sha256=digest(RUN_ROOT / 'FROZEN_PLAN.json'),
        continuation_source=str(source), prior_budget_sha256=digest(source / 'budget.json'),
        prior_attempt_model_calls=prior_calls, prior_attempt_browser_transitions=prior_transitions,
        budget_includes_carried_prior_attempt=True, max_calls=400, max_transitions=2000,
        identity_check=identity))
    core.write_json(root / 'SOURCE_SHA256.json', {str(p.relative_to(root / 'executed_sources')): digest(p)
        for p in (root / 'executed_sources').rglob('*') if p.is_file()})
    result = dict(prefixes=[], rows=panel.initial_rows(manifest['case_interleaved_order']))
    core.write_json(root / 'progress.json', result)
    try:
        backend = LocalBackend(NAME)
        core.write_json(root / 'backend_metadata.json', dict(backend.metadata, action_codec=VERSION))
        view = panel.ModelBudget(ledger, NAME, 400)
        model = ActionCodecModel(backend, ledger=view)
        model._ordinal = prior_calls  # Distinct IDs from carried-in control attempts.
        with runner.require_playwright()() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER),
                args=list(runner.BROWSER_LAUNCH_ARGS), timeout=120000)
            core.write_json(root / 'browser_runtime.json', dict(version=browser.version, viewport=[1440,1100]))
            try:
                qualify(browser, model, view, root / 'online/controls' / NAME)
                core.write_json(root / 'qualification.json', dict(passed=True))
                result = panel.execute_schedule(browser, manifest, {NAME:model}, {NAME:view}, ledger, root,
                    backbones=(NAME,))
            finally:
                browser.close()
    except Exception as exc:
        traceback.print_exc()
        core.write_json(root / 'extension_failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
    finally:
        panel.offline_report(manifest, result, ledger, root, backbones=(NAME,))
        core.write_json(root / 'final_status.json', dict(model=NAME, model_calls=ledger.model_calls,
            browser_transitions=ledger.browser_transitions,
            new_model_calls=ledger.model_calls-prior_calls,
            new_browser_transitions=ledger.browser_transitions-prior_transitions,
            budget_includes_carried_prior_attempt=True,
            panel_completed=len(result['prefixes']) == 16 and not (root / 'stop.json').exists(),
            qualification=(root / 'qualification.json').exists()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorized-action-codec', action='store_true', required=True)
    parser.parse_args()
    run()
