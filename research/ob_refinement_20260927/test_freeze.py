import json
from pathlib import Path
import pytest
import freeze as f


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def fixture(tmp_path, monkeypatch, version='v4'):
    monkeypatch.setattr(f, 'HERE', tmp_path)
    source = tmp_path / 'prompts.py'
    source.write_text('generic prompt', encoding='utf-8')
    put(tmp_path / ('runs/' + version + '_dev/source_hashes.json'), {'prompts.py': f.digest(source)})
    (tmp_path / 'freeze.py').write_text('test', encoding='utf-8')
    (tmp_path / 'evaluate.py').write_text('test', encoding='utf-8')
    row = {'rows': {'full_example': {'net_target': 1}}, 'net_target': 2,
           'positive_net_families': 2, 'common_parsed_including_null': {'n': 24, 'net_target': 2}}
    result = {'dev_numeric_gate': True, 'comparisons': {'plain': row, 'historical_v3': row},
              'source_hashes': {'summary': 'bound'}, 'dev_conditions': {'plain': {'pass': True}}}
    monkeypatch.setattr(f, 'evaluate', lambda *args: result)
    audit = {'version': version, 'complete': True, 'task_specific_prompt_rules': False,
             'bound_result_files': result['source_hashes'],
             'units': {'full_example': {'note': 'Checked image and public task; evidence supports this change.',
                'improved_choice_visible_support': True, 'evidence_files': {'prompts.py': f.digest(source)}}}}
    audit_path = tmp_path / 'audit' / (version + '_dev.json')
    put(audit_path, audit)
    return result, audit, audit_path


def test_freeze_binds_source_results_and_audit(tmp_path, monkeypatch):
    result, audit, path = fixture(tmp_path, monkeypatch)
    got = f.make_freeze('v4', path)
    assert got['qualitative_audit_sha256'] == f.digest(path)
    assert got['bound_result_files'] == result['source_hashes']
    assert got['earlier_version_dispositions'] == {}


def test_freeze_rejects_numeric_failure(tmp_path, monkeypatch):
    result, audit, path = fixture(tmp_path, monkeypatch)
    result['dev_numeric_gate'] = False
    with pytest.raises(ValueError, match='numeric'):
        f.make_freeze('v4', path)


def test_freeze_rejects_unsupported_new_choice(tmp_path, monkeypatch):
    result, audit, path = fixture(tmp_path, monkeypatch)
    audit['units']['full_example']['improved_choice_visible_support'] = False
    put(path, audit)
    with pytest.raises(ValueError, match='visibly justified'):
        f.make_freeze('v4', path)


def test_freeze_rejects_changed_evidence(tmp_path, monkeypatch):
    result, audit, path = fixture(tmp_path, monkeypatch)
    (tmp_path / 'prompts.py').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence missing or changed'):
        f.make_freeze('v4', path)


def test_freeze_earlier_full_pass_cannot_be_skipped(tmp_path, monkeypatch):
    result, audit, path = fixture(tmp_path, monkeypatch, 'v5')
    put(tmp_path / 'runs/v4_dev/summary.json', {'status': 'finished'})
    earlier = dict(audit, version='v4')
    put(tmp_path / 'audit/v4_dev.json', earlier)
    with pytest.raises(ValueError, match='Earlier full pass'):
        f.make_freeze('v5', path)


def test_freeze_earlier_numeric_pass_semantic_failure_retained(tmp_path, monkeypatch):
    result, audit, path = fixture(tmp_path, monkeypatch, 'v5')
    put(tmp_path / 'runs/v4_dev/summary.json', {'status': 'finished'})
    earlier = json.loads(json.dumps(audit))
    earlier['version'] = 'v4'
    earlier['units']['full_example']['improved_choice_visible_support'] = False
    put(tmp_path / 'audit/v4_dev.json', earlier)
    got = f.make_freeze('v5', path)
    assert got['earlier_version_dispositions']['v4']['semantic_failure']
    assert got['earlier_version_dispositions']['v4']['audit_sha256']
