"""Tests for MemPalace markdown notes search."""

from tools.mempalace_search import build_notes_index, search_notes_index


def test_mempalace_search_finds_keyword(tmp_path):
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    (notes_root / "pixelrag_pipeline_notes.md").write_text(
        "# PixelRAG Pipeline Notes\n\nScreenpipe screenshots become tiles.\n",
        encoding="utf-8",
    )
    (notes_root / "morningai_prep.md").write_text(
        "# MorningAI Prep\n\nBehavioral interview stories.\n",
        encoding="utf-8",
    )

    index_path = tmp_path / "notes_index.json"
    build_notes_index(notes_root=notes_root, index_path=index_path)

    hits = search_notes_index("pixelrag", index_path=index_path)
    assert hits
    assert any("pixelrag_pipeline_notes.md" in hit.get("filename", "") for hit in hits)
