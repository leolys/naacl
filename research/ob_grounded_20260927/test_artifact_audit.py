"""Offline adversarial ledger tests; mutate copies in memory, never real results."""
import copy
import json
from pathlib import Path

import audit_final_artifacts as auditor

ROOT = Path(__file__).resolve().parent
RUNS = ('v1_dev', 'v2_dev', 'v3_dev', 'v3_confirm')


def ledger():
    return json.loads((ROOT / 'ob_grounded_v3_confirm_final.json').read_text(encoding='utf-8'))['ledger']


def test_actual_archive_reconciles():
    result = auditor.audit(ROOT, ledger(), RUNS)
    assert result['artifact_audit_passed'], result['issues']
    assert result['attempts'] == result['archived_responses'] == 102


def test_duplicate_response_reference_rejected():
    events = copy.deepcopy(ledger())
    events['events'][1]['folder'] = events['events'][0]['folder']
    events['events'][1]['attempt'] = events['events'][0]['attempt']
    result = auditor.audit(ROOT, events, RUNS)
    assert not result['artifact_audit_passed']
    assert any(x.startswith('duplicate_ledger_response:') for x in result['issues'])
    assert 'ledger_response_set_mismatch' in result['issues']


def test_same_total_swapped_event_usage_rejected():
    events = copy.deepcopy(ledger())
    one, two = events['events'][:2]
    assert one['usage'] != two['usage']
    one['usage'], two['usage'] = two['usage'], one['usage']
    result = auditor.audit(ROOT, events, RUNS)
    assert not result['artifact_audit_passed']
    assert any(x.startswith('event_usage:') for x in result['issues'])
    assert 'usage_not_reconciled' not in result['issues']
