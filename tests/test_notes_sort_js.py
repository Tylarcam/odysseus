"""Regression: notes.js sort dropdown + compare helper."""

from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent


def test_notes_sort_ui_and_helpers_present():
    src = (_REPO / "static" / "js" / "notes.js").read_text(encoding="utf-8")

    assert "id=\"notes-sort\"" in src
    assert "NOTES_SORT_KEY = 'odysseus-notes-sort'" in src
    assert "function _compareNotes(a, b)" in src
    assert "function _notesDragReorderEnabled()" in src
    assert "function _syncNotesSortSelect()" in src
    assert "value=\"manual\">Custom</option>" in src
    assert "value=\"due\">Due date</option>" in src
    assert "localStorage.setItem(NOTES_SORT_KEY, _notesSort)" in src
    assert "draggable=\"${(_selectMode || _isNotesMobileMode() || !_notesDragReorderEnabled())" in src


def test_notes_sort_select_css_present():
    css = (_REPO / "static" / "style.css").read_text(encoding="utf-8")
    assert ".notes-search-bar .notes-sort-select" in css
