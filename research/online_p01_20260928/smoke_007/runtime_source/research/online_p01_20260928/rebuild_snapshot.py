"""Rebuild the missing original-runtime mirror from canonical repo sources.

The 20260925 export intentionally omitted `.aris/task_flows_20260924/`
(snapshot + RUNTIME_TASKS.json). Both are runtime mirrors of sources that ARE
in this repository: the four domain shell packages, the benchmark_v2_open
splits and assets, and the two pub005 runtime-recovery assets that
prepare_runtime.py had restored FROM these same repo paths. This script
recreates the mirror with byte-verification and never touches experiment
outputs or historical results.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
RESEARCH = HERE.parent
SOURCE = PROJECT / 'web_agent_benchmark'
TARGET_ROOT = PROJECT / '.aris/task_flows_20260924'
RECOVERED = {
    'web_agent_benchmark/public_shell/assets/p005_texas_red.jpeg':
        '7bacf4de09d530f34aab7f5a8363583de0cfd86f571b300a5e6da4b695a849d1',
    'web_agent_benchmark/clean_benchmark_v1/assets/pub005/clean.png':
        '5ad8423233b02d6ca1c42237a3426b4e704d7eb6d4fb4f51c3e96cc5688bc0ad'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if TARGET_ROOT.exists():
        raise ValueError('refuse_to_overwrite_existing_mirror')
    snapshot = TARGET_ROOT / 'snapshot'
    snapshot.mkdir(parents=True)
    shutil.copytree(SOURCE, snapshot / 'web_agent_benchmark')
    rows = []
    domains = ('business47', 'public39', 'environment35', 'health19')
    for arm in ('official140', 'clean140'):
        for domain in domains:
            path = snapshot / 'web_agent_benchmark/benchmark_v2_open/splits' / arm / (domain + '_tasks.jsonl')
            for line in path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                rows.append({'slug': row['task_slug'], 'arm': arm, 'domain': domain, 'spec': row})
    (TARGET_ROOT / 'RUNTIME_TASKS.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    for relative, expected in RECOVERED.items():
        actual = digest(snapshot / relative)
        if actual != expected:
            raise ValueError('recovered_asset_digest_mismatch:' + relative)
    manifest = {'built_from': str(SOURCE), 'rows': len(rows),
                'arms': {'official140': sum(1 for r in rows if r['arm'] == 'official140'),
                         'clean140': sum(1 for r in rows if r['arm'] == 'clean140')},
                'recovered_assets_verified': {k: v for k, v in RECOVERED.items()},
                'note': 'runtime mirror reconstructed from canonical repo sources; '
                        'byte-verified against the 20260925 asset_recovery hashes'}
    (HERE / 'rebuild' / 'snapshot_manifest.json').parent.mkdir(exist_ok=True)
    (HERE / 'rebuild' / 'snapshot_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print('SNAPSHOT rows', len(rows), 'at', snapshot)


if __name__ == '__main__':
    sys.exit(main())
