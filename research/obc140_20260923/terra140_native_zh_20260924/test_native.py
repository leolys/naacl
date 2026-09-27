"""Offline text/display checks, not visual reasoning validation."""
import copy
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_zh as zh


def test_identical_strings_deduplicate():
    assert zh.sid('High 100') == zh.sid('High 100')
    assert zh.sid('High 100') != zh.sid('High 0')


def test_invalid_output_is_not_silently_omitted():
    record = {'generation_invalid_raw': {'rules': [{'text': 'If X then Y.'}]}}
    assert zh.items(record) == [{'key': 'generation_invalid_raw.rules.0.text', 'text': 'If X then Y.'}]


def test_original_record_not_modified():
    record = {'public_task': {'user_goal': 'Choose A, not B.'},
              'proposal': {'brief_basis': 'Maybe 15, not 10.'}}
    before = copy.deepcopy(record)
    zh.items(record)
    assert record == before


def test_missing_key_rejected_by_shared_validator():
    import pytest
    with pytest.raises(ValueError):
        zh.core.validate_translation([{'key': 'a', 'text': 'Choose A.'}], {'items': {}})


def test_numeric_drop_warned():
    warnings = zh.core.validate_translation([{'key': 'a', 'text': 'Maybe 15, not 10.'}],
                                           {'items': {'a': '可能为 15，并非更小值。'}})
    assert warnings == [{'key': 'a', 'type': 'numeric_literal_missing', 'numbers': ['10']}]


def test_truncated_failure_view_not_repaired():
    text = '{"reason":"The required Campaign Type and'
    record = {'display_failure_outputs': {'verification': text}}
    assert zh.items(record) == [{'key': 'display_failure_outputs.verification', 'text': text}]
    assert record['display_failure_outputs']['verification'] == text


def test_state_glossary_preserves_original_statuses():
    import make_view
    task = {'translations': {'items': {}},
            'verification': {'chains': [{'O': 'supported', 'B': 'undetermined'}]},
            'rule_state': [{'status': 'revoked'}]}
    source = copy.deepcopy(task)
    make_view.add_state_labels(task)
    assert task['verification'] == source['verification']
    assert task['rule_state'] == source['rule_state']
    assert task['translations']['items']['verification.chains.0.O'] == '模型判为有支持'
    assert task['translations']['items']['verification.chains.0.B'] == '模型未能确定／证据不足'
    assert task['translations']['items']['rule_state.0.status'].startswith('已撤销')


def test_packaging_rejects_running_queue(tmp_path):
    import json
    import pytest
    import package_delivery
    (tmp_path / 'run').mkdir()
    (tmp_path / 'run/run_state.json').write_text(json.dumps({'status': 'running'}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='unfinished'):
        package_delivery.require_current_checks(tmp_path)


def test_packaging_rejects_stale_html_hash(tmp_path):
    import json
    import pytest
    import package_delivery
    (tmp_path / 'run').mkdir()
    (tmp_path / 'run/run_state.json').write_text(json.dumps({'status': 'completed'}), encoding='utf-8')
    (tmp_path / 'delivery_checks.json').write_text(json.dumps({'engineering_status': 'PASS', 'html_sha256': 'old'}), encoding='utf-8')
    (tmp_path / 'browser_check.json').write_text(json.dumps({'status': 'PASS', 'html_sha256': 'old'}), encoding='utf-8')
    (tmp_path / 'OBC140_TERRA_ZH_REVIEW.html').write_text('new offline page', encoding='utf-8')
    with pytest.raises(RuntimeError, match='Artifact changed'):
        package_delivery.require_current_checks(tmp_path)


def test_credential_scan_covers_bytes_and_utf16():
    import package_delivery
    token = 'sk-' + 'x' * 20  # Synthetic fixture, never a credential.
    assert package_delivery.credential_pattern_found(('<xml>' + token + '</xml>').encode('utf-8'))
    assert package_delivery.credential_pattern_found(token.encode('utf-16'))
    assert not package_delivery.credential_pattern_found(b'No credential provided; use an environment variable.')


def test_terminal_record_uses_three_api_stages_not_api_translation():
    import verify_delivery
    record = {'status': {'proposal': 'completed', 'generation': 'completed',
                         'verification': 'completed', 'translation': 'not_run'}}
    assert verify_delivery.terminal_api_record(record)
    record['status'].update(generation='invalid', verification='not_run')
    assert verify_delivery.terminal_api_record(record)
    record['status']['generation'] = 'not_run'
    assert not verify_delivery.terminal_api_record(record)
