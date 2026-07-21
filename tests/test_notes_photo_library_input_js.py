"""Notes photo attach must allow photo-library picks on mobile.

Hidden display:none inputs + deferred .click() break iOS Safari. Notes use an
ephemeral off-screen picker without `capture` so the native sheet offers Photo
Library + Take Photo. A window-focus dismiss hack must not run — iOS fires
focus while the user is still browsing the library. See handoffs 67f40c7d,
c9e35312.
"""
from pathlib import Path

SRC = Path("static/js/notes.js").read_text(encoding="utf-8")


def test_note_photo_uses_ephemeral_picker_without_capture():
    assert "function _pickNoteImageFile()" in SRC
    assert "function _attachNoteImageFile(" in SRC
    assert "note-form-photo-input" not in SRC
    assert 'capture="environment"' not in SRC
    assert "input.accept = 'image/*'" in SRC
    assert "left:-9999px" in SRC
    assert "addEventListener('focus'" not in SRC.split("function _pickNoteImageFile()")[1].split("function _attachNoteImageFile")[0]
