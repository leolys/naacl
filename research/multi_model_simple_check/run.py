"""Freeze the old task selection; run one new backbone using the existing harness."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import traceback

import requests
from research.decision_evidence_audit import core, models, runner
from research.prospective_simple_check_pilot import panel
from research.prospective_simple_check_pilot.api_backend import ApiStop
from research.prospective_simple_check_pilot.panel_controls import qualify
from .settings import CONFIGS, NAMES, TASKS, REPO, PACKAGE, RUN_ROOT, SOURCE_MANIFEST, BROWSER, PORT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def single_manifest(original, name):
    manifest = copy.deepcopy(original)
    assert tuple(r['task_slug'] for r in manifest['rows']) == TASKS, 'No task resampling allowed'
    schedule = [u for u in manifest['case_interleaved_order'] if u['model'] == 'M_small']
    for i, unit in enumerate(schedule, 1):
        unit.update(ordinal=i, model=name, status='not_run')
    manifest['case_interleaved_order'] = schedule
    manifest['status'] = 'fixed_previous_eight_tasks_new_backbone_extension'
    manifest['scope'] = 'reused eight-task development panel; not held-out confirmation or GUI system ranking'
    panel.validate_schedule(manifest, backbones=(name,))
    return manifest


def prepare():
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    target = RUN_ROOT / 'SOURCE_TASK_MANIFEST.json'
    if target.exists():
        if target.read_bytes() != SOURCE_MANIFEST.read_bytes():
            raise RuntimeError('Frozen task source changed')
    else:
        shutil.copy2(SOURCE_MANIFEST, target)
    original = json.loads(target.read_text())
    assets = []
    for row in original['rows']:
        for arm in ('official140', 'clean140'):
            public, path = panel.public_unit(row, arm)
            assets.append(dict(task_slug=row['task_slug'], arm=arm, path=str(path), sha256=digest(path)))
    record = dict(source_manifest_sha256=digest(target), task_order=list(TASKS), model_order=list(NAMES),
        assets=assets, max_calls_per_model=400, max_browser_transitions_per_model=2000,
        total_model_call_cap=1200, total_browser_transition_cap=6000, concurrency=1,
        natural_prefix_calls=12, prefix_transitions=20, continuation_calls=4,
        B2_calls=1, B3_calls=3, B3_crops=2, controls_max_calls=16,
        gpu='7', no_paid_api=True, no_new_weight_download=True)
    path = RUN_ROOT / 'FROZEN_PLAN.json'
    if path.exists() and json.loads(path.read_text()) != record:
        raise RuntimeError('Frozen plan or chart assets changed')
    core.write_json(path, record)
    for name in NAMES:
        manifest = single_manifest(original, name)
        path = RUN_ROOT / f'TASK_MANIFEST_{name}.json'
        if path.exists() and json.loads(path.read_text()) != manifest:
            raise RuntimeError('Frozen manifest changed')
        core.write_json(path, manifest)
    return record


class LocalBackend:
    """No generic gateway/fallback. Only our validated loopback service."""
    def __init__(self, name):
        self.url = f'http://127.0.0.1:{PORT}'
        self.session = requests.Session()
        self.session.trust_env = False
        response = self.session.get(self.url + '/health', timeout=5)
        response.raise_for_status()
        health = response.json()
        if (health.get('model_name') != name or health.get('model_path') != CONFIGS[name]['weights']
            or health.get('native_multi_image') is not True or health.get('physical_gpu') != '7'
            or health.get('decoding') != dict(do_sample=False, max_new_tokens=1024, seed=12345)):
            raise RuntimeError('Service identity/configuration mismatch')
        self.metadata = dict(kind='local_native_vlm', model_name=name, health=health,
                             retries=0, automatic_fallback=False)

    def complete(self, request):
        try:
            response = self.session.post(self.url + '/complete', timeout=(5, 300), json=dict(
                system_prompt=request.system_prompt, user_prompt=request.user_prompt,
                image_paths=[str(p) for p in request.image_paths]))
            response.raise_for_status()
            data = response.json()
            return models.ModelReply(data['text'], data['metadata'])
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            # Reuse the harness's fatal transport signal, not per-task behaviour failure.
            # In particular, an OOM/HTTP500 must not be retried on every remaining task.
            raise ApiStop(f'Local service transport/protocol failure: {type(exc).__name__}: {exc}') from exc


def startup_retry_source(name):
    """Only an infrastructure failure before ANY model/control/task dispatch."""
    source = RUN_ROOT / name
    budget = json.loads((source / 'budget.json').read_text())
    progress = json.loads((source / 'progress.json').read_text())
    failure = json.loads((source / 'extension_failure.json').read_text())
    if (budget['model_calls'] != 0 or budget['browser_transitions'] != 0 or budget['events']
        or progress['prefixes'] or any(r['prefix_started'] for r in progress['rows'])
        or list((source / 'online').glob('**/requests/*.json'))
        or failure.get('error_type') != 'TimeoutError'
        or 'BrowserType.launch: Timeout' not in failure.get('error', '')):
        raise RuntimeError('Not a zero-dispatch browser startup failure; retry forbidden')
    return source


def run(name, *, startup_retry=False):
    frozen = prepare()
    source = startup_retry_source(name) if startup_retry else None
    root = RUN_ROOT / (name + '_startup_retry01' if startup_retry else name)
    browser_timeout = 120000 if startup_retry else 20000
    root.mkdir(exist_ok=False)
    manifest_path = RUN_ROOT / f'TASK_MANIFEST_{name}.json'
    manifest = json.loads(manifest_path.read_text())
    ledger = core.BudgetLedger(max_model_calls=400, max_browser_transitions=2000)
    ledger.bind_snapshot(root / 'budget.json')
    panel.snapshot_sources(root)
    shutil.copytree(PACKAGE, root / 'executed_sources/research/multi_model_simple_check',
        ignore=shutil.ignore_patterns('runs','runtime','backups','__pycache__'))
    shutil.copy2(manifest_path, root / 'TASK_MANIFEST.json')
    core.write_json(root / 'MODEL_CONFIG.json', dict(**CONFIGS[name], name=name,
        frozen_plan_sha256=digest(RUN_ROOT / 'FROZEN_PLAN.json'), browser=str(BROWSER),
        browser_sha256=digest(BROWSER), browser_launch_timeout_ms=browser_timeout,
        gpu='7', max_calls=400, max_transitions=2000,
        startup_failure_source=str(source) if source else None,
        startup_failure_sha256=digest(source / 'extension_failure.json') if source else None,
        prior_attempt_model_calls=0, prior_attempt_browser_transitions=0))
    identities = {str(p.relative_to(root / 'executed_sources')): digest(p)
                  for p in (root / 'executed_sources').rglob('*') if p.is_file()}
    core.write_json(root / 'SOURCE_SHA256.json', identities)
    result = dict(prefixes=[], rows=panel.initial_rows(manifest['case_interleaved_order']))
    core.write_json(root / 'progress.json', result)
    try:
        backend = LocalBackend(name)
        core.write_json(root / 'backend_metadata.json', backend.metadata)
        view = panel.ModelBudget(ledger, name, 400)
        model = models.RecordedModel(backend, ledger=view)
        with runner.require_playwright()() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER),
                args=list(runner.BROWSER_LAUNCH_ARGS), timeout=browser_timeout)
            core.write_json(root / 'browser_runtime.json', dict(version=browser.version, viewport=[1440,1100]))
            try:
                qualify(browser, model, view, root / 'online/controls' / name)
                core.write_json(root / 'qualification.json', dict(passed=True))
                result = panel.execute_schedule(browser, manifest, {name:model}, {name:view}, ledger, root,
                    backbones=(name,))
            finally:
                browser.close()
    except Exception as exc:
        traceback.print_exc()
        core.write_json(root / 'extension_failure.json', dict(error_type=type(exc).__name__, error=str(exc)))
    finally:
        # Offline scorer runs only after model dispatch has ended. Never used to pick or retry tasks.
        panel.offline_report(manifest, result, ledger, root, backbones=(name,))
        core.write_json(root / 'final_status.json', dict(model=name, model_calls=ledger.model_calls,
            browser_transitions=ledger.browser_transitions, panel_completed=len(result['prefixes']) == 16
            and not (root / 'stop.json').exists(), qualification=(root / 'qualification.json').exists()))
        print('MODEL_PANEL_STOPPED ' + name + ' ' + json.dumps(panel.cost(ledger.events)), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--model', choices=NAMES)
    p.add_argument('--startup-retry', action='store_true')
    args = p.parse_args()
    if args.prepare:
        print(json.dumps(prepare(), ensure_ascii=False, indent=2))
    elif args.model:
        run(args.model, startup_retry=args.startup_retry)
    else:
        p.error('Choose --prepare or --model')
