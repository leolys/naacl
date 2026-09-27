"""Offline, standard-library-only validation. Never calls a model or network."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'web_agent_benchmark/benchmark_v2_open'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    splits = {}
    asset_paths = set()
    expected_groups = {'business47': 47, 'environment35': 35, 'health19': 19, 'public39': 39}
    for split in ('official140', 'clean140'):
        rows = []
        for group, expected in expected_groups.items():
            p = DATA / 'splits' / split / (group + '_tasks.jsonl')
            group_rows = [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
            assert len(group_rows) == expected, (split, group)
            assert all(row['split'] == split for row in group_rows)
            rows.extend(group_rows)
        assert len(rows) == 140
        assert len({row['task_instance_id'] for row in rows}) == 140
        assert len({row['pair_group_id'] for row in rows}) == 140
        splits[split] = {row['pair_group_id']: row for row in rows}
        for row in rows:
            for key, value in row['chart_asset'].items():
                if key.endswith('_path') and value:
                    p = (ROOT / value).resolve()
                    assert ROOT in p.parents and p.is_file(), value
                    asset_paths.add(value)
    assert set(splits['official140']) == set(splits['clean140'])
    assert not (DATA / 'splits/real_world40').exists()
    assert not (DATA / 'assets/real_world40').exists()
    provenance = json.loads((ROOT / 'handoff/SOURCE_PROVENANCE.json').read_text(encoding='utf-8'))
    checked = 0
    for row in provenance['source_files']:
        if row['destination'] == 'git':
            p = ROOT / row['path']
            assert p.is_file() and sha(p) == row['export_sha256'], row['path']
            checked += 1
    latest = ROOT / 'research/ob_full_comparison_20260927'
    manifest = json.loads((latest / 'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['units']) == 140
    for unit in manifest['units']:
        public = json.loads((latest / 'data' / unit / 'input.json').read_text(encoding='utf-8'))
        assert set(public) == {'goal', 'public_task', 'options', 'records'}
    print(json.dumps({'passed': True, 'paired_base_tasks': 140, 'task_instances': 280,
                      'groups_per_split': expected_groups, 'referenced_assets': len(asset_paths),
                      'core_source_hashes_checked': checked, 'latest_public_inputs': 140,
                      'real_world40_present': False, 'model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
