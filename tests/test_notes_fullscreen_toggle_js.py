"""Notes panel header includes a fullscreen toggle to the right of minimize."""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
SRC = (_REPO / "static" / "js" / "notes.js").read_text(encoding="utf-8")
APP = (_REPO / "static" / "app.js").read_text(encoding="utf-8")
CSS = (_REPO / "static" / "style.css").read_text(encoding="utf-8")


def test_fullscreen_button_follows_minimize_in_header():
    min_idx = SRC.index('id="notes-minimize-btn"')
    fs_idx = SRC.index('id="notes-fullscreen-toggle"')
    assert fs_idx > min_idx
    header_slice = SRC[min_idx:fs_idx + 80]
    assert "notes-fullscreen-toggle" in header_slice
    assert "Full screen" in SRC


def test_fullscreen_toggle_wires_click_and_helpers():
    assert "function _toggleNotesFullscreen(pane)" in SRC
    assert "function _enterNotesFullscreen(pane)" in SRC
    assert "_toggleNotesFullscreen(pane)" in SRC
    assert "fsClass: 'notes-window-fullscreen'" in SRC


def test_notes_route_clicks_existing_fullscreen_toggle():
    assert "getElementById('notes-fullscreen-toggle')" in APP
    assert "notes-window-fullscreen" in APP
    assert "notes-pane-fullscreen" not in APP


def test_fullscreen_toggle_hidden_on_mobile():
    assert "body.notes-mobile-mode #notes-fullscreen-toggle" in CSS
    assert "#notes-fullscreen-toggle { display: none !important; }" in CSS
