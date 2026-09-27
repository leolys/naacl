"""Offline actual-attempt accounting. Never impute missing response usage as zero."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
from evaluate import HERE, read, save_new, digest


def summarize(metadata):
    meta = read(metadata)
    ledger = meta['ledger']
    events = ledger['events']
    if [x['number'] for x in events] != list(range(1, len(events) + 1)) or ledger['attempts'] != len(events):
        raise ValueError('Ledger attempt sequence mismatch')
    by_run = defaultdict(lambda: {'attempts': 0, 'known_usage': Counter(), 'unknown_usage_attempts': 0,
                                  'http_status': Counter(), 'stages': Counter(), 'retry_attempts': 0})
    known = Counter()
    archived_responses = 0
    for event in events:
        name = Path(event['folder']).parts[1]
        row = by_run[name]
        row['attempts'] += 1
        row['stages'][event['stage']] += 1
        row['http_status'][str(event.get('http_status', 'not_available'))] += 1
        row['retry_attempts'] += int(event['attempt'] > 1)
        usage = event.get('usage')
        if usage is None:
            row['unknown_usage_attempts'] += 1
        else:
            for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                if not isinstance(usage.get(key), int):
                    raise ValueError('Partial usage; inspect before aggregation')
                row['known_usage'][key] += usage[key]
                known[key] += usage[key]
        response_path = HERE / event['folder'] / ('response_%02d.json' % event['attempt'])
        if response_path.exists():
            response = read(response_path)
            if response['http_status'] != event.get('http_status'):
                raise ValueError('Archive/ledger response status differs')
            actual_usage = response.get('body', {}).get('usage') if isinstance(response.get('body'), dict) else None
            if usage is not None and any(actual_usage.get(k) != usage[k] for k in known):
                raise ValueError('Archive/ledger response usage differs')
            archived_responses += 1
    if 'usage' in ledger and dict(known) != {key: ledger['usage'][key] for key in known}:
        raise ValueError('Ledger cumulative usage differs')
    return {'source_snapshot': str(metadata), 'source_sha256': digest(metadata),
            'attempts': len(events), 'known_usage': dict(known),
            'unknown_usage_attempts': sum(v['unknown_usage_attempts'] for v in by_run.values()),
            'response_files_checked': archived_responses, 'by_run': dict(by_run),
            'usage_source': 'sum of per-attempt ledger entries, cross-checked against each available raw response',
            'all_ledger_responses_available_locally': archived_responses == sum(x['state'] == 'response_saved' for x in events),
            'business_submissions': 0, 'business_browser_transitions': 0, 'paid_api_calls': 0,
            'reused_candidate_generation_cost_included': False,
            'reused_candidate_scope': 'Fixed historical O/B records; their earlier generation is outside this round, not a claim of zero end-to-end cost.',
            'local_display_qa_not_benchmark': True,
            'interpretation': 'Real model attempts including failures/retries; no cost charged by this task to an external API. Single-call baseline and three-stage method are not compute matched.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    got = summarize(args.snapshot)
    save_new(args.output, got)
    print({key: got[key] for key in ('attempts', 'known_usage', 'unknown_usage_attempts', 'response_files_checked')})
