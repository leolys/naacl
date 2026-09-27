"""Recount actual latest result files from Release ZIPs without extracting them."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'research/ob_full_comparison_20260927'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--assets-dir', type=Path, default=ROOT / 'artifacts')
    a = p.parse_args()
    rows = json.loads((ROOT / 'handoff/SOURCE_PROVENANCE.json').read_text(encoding='utf-8'))['source_files']
    index = {row['path']: row for row in rows}
    archives = {}
    checked = 0

    def read(name):
        nonlocal checked
        info = index[name]
        if info['destination'] == 'git':
            raw = (ROOT / name).read_bytes()
        else:
            part = info['destination']
            if part not in archives:
                archives[part] = ZipFile(a.assets_dir / part)
            raw = archives[part].read(name)
        assert hashlib.sha256(raw).hexdigest() == info['export_sha256'], name
        checked += 1
        return json.loads(raw)

    spec = importlib.util.spec_from_file_location('original_offline_evaluate', ROOT / PREFIX / 'evaluate.py')
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    labels = read(PREFIX + '/offline/labels.json')['tasks']
    units = read(PREFIX + '/manifest.json')['units']
    expected = {
        'plain': {'target': 81, 'trap': 54, 'other': 4, 'no_option': 0, 'interface_failed': 1},
        'v3': {'target': 74, 'trap': 37, 'other': 10, 'no_option': 13, 'interface_failed': 6},
        'v4': {'target': 87, 'trap': 36, 'other': 8, 'no_option': 9, 'interface_failed': 0},
        'v5': {'target': 96, 'trap': 26, 'other': 12, 'no_option': 6, 'interface_failed': 0},
        'v6': {'target': 84, 'trap': 29, 'other': 12, 'no_option': 13, 'interface_failed': 2},
        'v7': {'target': 91, 'trap': 32, 'other': 12, 'no_option': 5, 'interface_failed': 0},
    }
    actual = {}
    all_results = {}
    for version in evaluator.VERSIONS:
        counts = Counter()
        all_results[version] = {}
        for key in units:
            result = read(PREFIX + '/captures/final_001/runs/' + version + '/' + key + '/result.json')
            assert result['unit'] == key and result['version'] == version
            all_results[version][key] = result
            counts[evaluator.state(result, labels[key])] += 1
        assert sum(counts.values()) == 140
        assert all(counts[state] == n for state, n in expected[version].items()), version
        actual[version] = {state: counts[state] for state in expected[version]}
    paired = evaluator.pair(all_results['plain'], all_results['v5'], list(units), units, labels)
    assert paired['net_target'] == 15
    for archive in archives.values():
        archive.close()
    print(json.dumps({'passed': True, 'results_checked': 840, 'hashes_checked': checked,
                      'full140': actual, 'v5_vs_plain': paired['broad_transitions'],
                      'scope': 'static original-label comparison', 'model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
