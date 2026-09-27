"""Read-only compact progress; no model requests or filesystem writes."""
from collections import Counter
from pathlib import Path
import json
import requests
from engine import HERE, read, stamp


def main():
    result = {'at': stamp(), 'workers': {}, 'services': {}, 'total_attempts': 0, 'total_units': 0}
    http = requests.Session()
    http.trust_env = False
    for worker in read(HERE / 'config.json')['workers']:
        wid = str(worker['id'])
        work = HERE / 'workers' / wid
        summary = read(work / 'summary.json') if (work / 'summary.json').exists() else {'status': 'not_started', 'units': {}}
        ledger = read(work / 'ledger.json') if (work / 'ledger.json').exists() else {'attempts': 0, 'events': []}
        result['workers'][wid] = {'status': summary['status'], 'units': len(summary['units']),
            'attempts': ledger['attempts'], 'by_version': dict(Counter(x['version'] for x in summary['units'].values())),
            'outcomes': dict(Counter(x['status'] for x in summary['units'].values())),
            'last': ledger['events'][-1] if ledger['events'] else None, 'error': summary.get('error')}
        result['total_attempts'] += ledger['attempts']
        result['total_units'] += len(summary['units'])
        try:
            health = http.get('http://127.0.0.1:%d/health' % worker['port'], timeout=3, allow_redirects=False)
            result['services'][wid] = health.status_code
        except requests.RequestException as exc:
            result['services'][wid] = type(exc).__name__
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
