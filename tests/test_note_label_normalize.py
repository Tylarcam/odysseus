"""Note labels are always stored lowercase to prevent tag-chip duplicates."""

from pathlib import Path

from src.note_label import normalize_note_label

_REPO = Path(__file__).resolve().parents[1]


def test_normalize_lowercases_and_dedupes():
    assert normalize_note_label("Jobs #JOBS jobs") == "jobs"
    assert normalize_note_label("Job JOB job") == "job"
    assert normalize_note_label("Hermes, Swarm") == "hermes swarm"
    assert normalize_note_label("  #Lili  Gamma  ") == "lili gamma"
    assert normalize_note_label("") == ""
    assert normalize_note_label(None) is None


def test_notes_js_normalizes_labels_lowercase():
    src = (_REPO / "static" / "js" / "notes.js").read_text(encoding="utf-8")
    assert "function _normalizeNoteLabel(raw)" in src
    helper = src.split("function _normalizeNoteLabel(raw)")[1].split("function ")[0]
    assert ".toLowerCase()" in helper
    assert "const _tags = _normalizeNoteLabel(_rawLabel);" in src
    assert "const tags = _normalizeNoteLabel(n?.label);" in src
