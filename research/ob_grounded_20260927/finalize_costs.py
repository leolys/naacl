"""Reconcile a terminal collector ledger; no network and no inference calls."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.snapshot.read_bytes()
    snapshot = json.loads(raw)
    if snapshot['run'] != 'v3_full' or not snapshot['terminal'] or snapshot['status'] != 'finished':
        raise ValueError('Need terminal full-panel snapshot')
    if snapshot['files_changed_during_snapshot']:
        raise ValueError('Snapshot changed while collecting')
    ledger = snapshot['ledger']
    config = json.loads((HERE / 'config.json').read_text(encoding='utf-8'))
    usage, states, http, runs, retries = Counter(), Counter(), Counter(), {}, 0
    totals = defaultdict(Counter)
    elapsed = 0.0
    for event in ledger['events']:
        run = event['folder'].replace('\\', '/').split('/')[1]
        totals[run]['attempts'] += 1
        if event['attempt'] > 1:
            retries += 1
        if datetime.fromisoformat(event['start']) >= datetime.fromisoformat(config['deadline_utc']):
            raise ValueError('Request started after cutoff')
        states[event['state']] += 1
        http[str(event.get('http_status'))] += 1
        elapsed += event.get('elapsed', 0)
        for name, value in (event.get('usage') or {}).items():
            if isinstance(value, int):
                usage[name] += value
                totals[run][name] += value
    if ledger['attempts'] != len(ledger['events']) or ledger['attempts'] > config['max_attempts']:
        raise ValueError('Budget ledger inconsistent')
    for run, counts in totals.items():
        summary = json.loads((HERE / 'runs' / run / 'summary.json').read_text(encoding='utf-8'))
        runs[run] = {**counts, 'started': summary['started'], 'ended': summary['ended'],
                     'states': dict(Counter(v['status'] for v in summary['units'].values())),
                     'reused_units_not_new_requests': sum(bool(v.get('reused_from')) for v in summary['units'].values())}
    output = {'snapshot_sha256': hashlib.sha256(raw).hexdigest(), 'snapshot_archive_sha256': snapshot['archive_sha256'],
              'ledger': ledger, 'attempts': ledger['attempts'], 'max_attempts': config['max_attempts'],
              'usage': dict(usage), 'event_states': dict(states), 'http_statuses': dict(http),
              'infrastructure_retry_attempts': retries, 'quality_retries': 0,
              'request_elapsed_seconds_sum': elapsed, 'by_run': runs,
              'business_browser_operations': 0, 'business_submissions': 0, 'paid_api_calls': 0,
              'new_model_or_gpu_jobs': 0, 'scope': 'All diagnostic inference attempts including failures and repeats across three planned development versions; confirmation reused without double charging. Token usage is service-reported, not an invoice or exact GPU cost. Local viewer QA is not benchmark execution.'}
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(output, out, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in output.items() if k != 'ledger'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
