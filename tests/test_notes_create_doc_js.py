"""Regression: notes.js create-doc-from-note wiring."""

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def test_notes_create_doc_button_and_helpers_present():
    src = (_REPO / "static" / "js" / "notes.js").read_text(encoding="utf-8")
    assert "note-form-create-doc-btn" in src
    assert "function _serializeNoteForDoc(payload)" in src
    assert "function _createDocFromNote(form, note)" in src
    assert "data-act=\"create-doc\"" in src
    assert "injectFreshDoc" in src
    assert "language: 'markdown'" in src
