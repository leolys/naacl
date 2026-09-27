"""Read-only counts without exposing application choices during development."""
from collections import Counter
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    active = read(HERE / 'ACTIVE.json') if (HERE / 'ACTIVE.json').exists() else {}
    active['process'] = subprocess.run(['ps', '-p', str(active.get('pid', 0)), '-o', 'pid,etimes,args'],
                                     capture_output=True, text=True).stdout
    events = read(HERE / 'ledger.json').get('events', []) if (HERE / 'ledger.json').exists() else []
    usage = Counter()
    for event in events:
        usage.update({k: v for k, v in (event.get('usage') or {}).items() if isinstance(v, int)})
    runs = {}
    for path in (HERE / 'runs').glob('*/summary.json'):
        result = read(path)
        runs[path.parent.name] = {'state': result['status'], 'units': len(result['units']),
                                  'states': dict(Counter(v['status'] for v in result['units'].values()))}
    print(json.dumps({'active': active, 'attempts': len(events), 'usage': dict(usage),
                      'last_event': events[-1] if events else None, 'runs': runs}))


if __name__ == '__main__':
    main()
