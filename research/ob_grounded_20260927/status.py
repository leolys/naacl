"""Read-only compact progress; never infer task success from API completion."""
from collections import Counter
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def main():
    active = read(HERE / 'ACTIVE.json') if (HERE / 'ACTIVE.json').exists() else {}
    events = read(HERE / 'ledger.json').get('events', []) if (HERE / 'ledger.json').exists() else []
    usage = Counter()
    elapsed = 0
    for event in events:
        for k, v in (event.get('usage') or {}).items():
            if isinstance(v, int): usage[k] += v
        elapsed += event.get('elapsed', 0)
    active['process'] = subprocess.run(['ps', '-p', str(active.get('pid', 0)), '-o', 'pid,etimes,args'],
                                     capture_output=True, text=True).stdout
    runs = {}
    for summary in (HERE / 'runs').glob('*/summary.json'):
        s = read(summary)
        runs[summary.parent.name] = {'state': s['status'], 'units': len(s['units']),
            'states': dict(Counter(r['status'] for r in s['units'].values())),
            'choices': {k: (v.get('choice') or {}).get('option_label') for k, v in s['units'].items()}}
    print(json.dumps({'active': active, 'attempts': len(events), 'usage': dict(usage),
                     'request_seconds': elapsed, 'last_event': events[-1] if events else None, 'runs': runs}))

if __name__ == '__main__':
    main()
