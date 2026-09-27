"""Offline descriptive tables and final fixed-source/cost evidence checks."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from evaluate import HERE, VERSIONS, read, state, new, sha
from engine import verify_seal


def main():
    capture = HERE / 'captures/final_001'
    out = HERE / 'analysis/final_001'
    seal = verify_seal()
    for name in ('manifest.json', 'schedule.json', 'config.json', 'PROTOCOL.md'):
        assert sha(capture / name) == sha(HERE / name), name
    manifest = read(HERE / 'manifest.json')['units']
    labels = read(HERE / 'offline/labels.json')['tasks']
    runs = {v: read(out / (v + '.json')) for v in VERSIONS}
    summary = read(out / 'SUMMARY.json')
    history = read(HERE / 'offline/old_v3_summary.json')['units']
    panels, families, domains, failures = {}, {}, {}, []
    for v, data in runs.items():
        panels[v] = {}
        for panel, item in data['panels'].items():
            panels[v][panel] = {'n': item['n'], 'counts': item['counts']}
            for ref in ('vs_plain', 'vs_fresh_v3', 'vs_historical_v3'):
                panels[v][panel][ref] = {k: item[ref][k] for k in (
                    'net_target', 'broad_transitions', 'exact_transitions',
                    'common_parsed_including_null', 'both_nonnull_auxiliary')}
        for key, result in data['units'].items():
            s = state(result, labels[key])
            for target, field in ((families, 'family'), (domains, 'domain')):
                group = target.setdefault(manifest[key][field], {})
                group.setdefault(v, Counter())[s] += 1
            if result['status'] == 'interface_failed':
                root = capture / 'runs' / v / key / result['failed_stage']
                reply = read(root / 'response_01.json')
                choice = reply['body']['choices'][0]
                item = {'version': v, 'unit': key, 'stage': result['failed_stage'],
                        'error': result['error'], 'http_status': reply['http_status'],
                        'finish_reason': choice['finish_reason'], 'usage': reply['body']['usage']}
                if result['error']['message'] == 'record coverage':
                    item['expected_ids'] = [r['id'] for r in read(root / 'context.json')['records']]
                    item['returned_ids'] = [r['id'] for r in json.loads(choice['message']['content'])['reviews']]
                failures.append(item)
    events = [event for w in range(4) for event in read(capture / 'workers' / str(w) / 'ledger.json')['events']]
    cutoff = datetime.fromisoformat(read(HERE / 'config.json')['deadline_utc'])
    assert all(datetime.fromisoformat(e['start']) <= cutoff for e in events)
    assert all(e['state'] == 'response_saved' and e['http_status'] == 200 and e['attempt'] == 1 for e in events)
    starts = [r['started'] for d in runs.values() for r in d['units'].values()]
    ends = [r['ended'] for d in runs.values() for r in d['units'].values()]
    costs = summary['costs']
    total_usage = {k: sum(x['known_usage'][k] for x in costs.values())
                   for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    record = {'seal_sha256': seal, 'sealed_files_verified': len(read(HERE / 'RUNTIME_SEAL.json')['files']),
        'captured_public_files_equal_local': True, 'panels': panels, 'families': families,
        'domains': domains, 'failures': failures, 'total_usage_including_controls': total_usage,
        'main_first_started_utc': min(starts), 'main_last_ended_utc': max(ends),
        'all_attempts_before_deadline': True, 'all_http200_no_retries': True,
        'historical_v3_counts': dict(Counter(state(history[k], labels[k]) for k in manifest)),
        'limits': 'Descriptive original-label agreement; family names are inherited grouping labels, not independent mechanism counts.'}
    new(out / 'SUPPLEMENTAL.json', record)
    print(json.dumps({'panels': panels, 'failures': failures, 'totals': total_usage,
        'start': min(starts), 'end': max(ends), 'domains': domains}, ensure_ascii=False))


if __name__ == '__main__':
    main()
