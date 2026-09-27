from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_view


def test_new_run_has_separate_note_storage(tmp_path, monkeypatch):
    source = make_view.OLD / "viewer_template.html"
    original = source.read_bytes()
    monkeypatch.setattr(make_view, "HERE", tmp_path)
    previous = make_view.view.render_viewer.TEMPLATE_PATH
    try:
        make_view.isolate_note_storage()
        emitted = make_view.view.render_viewer.TEMPLATE_PATH.read_text(encoding="utf-8")
        assert 'const storageKey = "obc140-runtime-dom-v1-20260924-notes:" +' in emitted
        assert 'const storageKey = "obc140-notes-v1:" +' not in emitted
        assert source.read_bytes() == original
    finally:
        make_view.view.render_viewer.TEMPLATE_PATH = previous


def test_note_contract_drift_is_not_silently_accepted(tmp_path, monkeypatch):
    (tmp_path / "viewer_template.html").write_text("different template", encoding="utf-8")
    monkeypatch.setattr(make_view, "OLD", tmp_path)
    with pytest.raises(ValueError, match="Inspect note namespace"):
        make_view.isolate_note_storage()
