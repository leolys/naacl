"""Explicit one-time version freeze after development review; no model calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import run

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--version', choices=['v1','v2','v3'], required=True)
    p.add_argument('--review', type=Path, required=True)
    args = p.parse_args()
    report = args.review.resolve()
    if HERE not in report.parents or not report.is_file():
        raise ValueError('A saved review in this new directory is required')
    dev = run.read(HERE / 'runs' / (args.version + '_dev') / 'summary.json')
    if dev['status'] != 'finished' or len(dev['units']) != 8:
        raise ValueError('Fixed development run must have all eight terminal units')
    if run.read(HERE / 'runs' / (args.version + '_dev') / 'source_hashes.json') != run.source_hashes(args.version):
        raise ValueError('Current candidate differs from the tested development source')
    if not dev.get('runtime_preserved'):
        raise ValueError('Development runtime identity was not preserved')
    if (HERE / 'FREEZE.json').exists():
        raise FileExistsError('Do not replace frozen version after looking at confirmation')
    result = {'version': args.version, 'frozen_at': datetime.now(timezone.utc).isoformat(),
              'prompt_sha256': run.sha(HERE / ('prompts_' + args.version + '.py')),
              'runtime_hashes': run.source_hashes(args.version),
              'development_summary_sha256': run.sha(HERE / 'runs' / (args.version + '_dev') / 'summary.json'),
              'review': str(report.relative_to(HERE)), 'review_sha256': run.sha(report),
              'confirmation_not_used_to_tune': True,
              'meaning': 'A fixed tested candidate for prospective diagnostic application, not a semantic correctness certificate.'}
    with (HERE / 'FREEZE.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result))

if __name__ == '__main__':
    main()
