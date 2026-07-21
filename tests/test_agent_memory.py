"""Tests for JSON-backed agent memory."""

from tools.agent_memory import search_agent_memory, store_agent_memory


def test_search_agent_memory_finds_pixelrag_entries(tmp_path):
    store_path = tmp_path / "agent_memory.json"

    store_agent_memory(
        "Explored PixelRAG pipelines and decided to use Screenpipe screenshots as tiles.",
        tags=["pixelrag", "pipeline", "decision"],
        related_tiles=["screen_2026-07-07T01-05-00.png"],
        path=store_path,
    )
    store_agent_memory(
        "Interview prep session for MorningAI role.",
        tags=["jobs", "interview"],
        path=store_path,
    )

    hits = search_agent_memory("PixelRAG", path=store_path)
    assert hits
    assert any("pixelrag" in (entry.get("tags") or []) for entry in hits)
    assert any("PixelRAG" in entry.get("summary", "") for entry in hits)
