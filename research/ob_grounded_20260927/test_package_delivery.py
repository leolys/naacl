"""Small offline regression for archive credential-pattern false positives."""
from package_delivery import SECRET


def test_research_words_are_not_credentials():
    assert not SECRET.search(b'task-condition-to-action relation')
    assert not SECRET.search(b'risk-selection-to-action relation')


def test_key_after_json_boundary_still_detected():
    synthetic = b'{"api_key":"' + b'sk-' + b'x' * 24 + b'"}'
    assert SECRET.search(synthetic)


def test_bearer_header_still_detected():
    synthetic = b'Authorization: ' + b'Bearer ' + b'x' * 24
    assert SECRET.search(synthetic)
