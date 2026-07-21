"""Pin email library search wiring — local Fuse index, not IMAP /search."""
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_EMAIL_LIBRARY = _REPO / "static" / "js" / "emailLibrary.js"


def test_email_library_search_uses_local_fuzzy_index():
    src = _EMAIL_LIBRARY.read_text(encoding="utf-8")
    assert "searchEmailCorpus" in src
    assert "_ensureEmailSearchCorpus" in src
    assert "/api/email/search" not in src
    assert "./emailLibrary/localSearch.js" in src
