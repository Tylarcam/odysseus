"""Tests for Clicky unified memory client."""

import json
from pathlib import Path
from unittest.mock import patch

from clicky_integration.clicky_client import (
    format_overlay_summary,
    load_clicky_config,
    query_unified_memory,
    quick_last_reading_query,
    quick_page_connections_query,
)


def test_load_clicky_config_reads_url(tmp_path):
    cfg_path = tmp_path / "clicky_config.json"
    cfg_path.write_text(
        json.dumps({"unified_memory_api_url": "http://localhost:49999/query"}),
        encoding="utf-8",
    )
    cfg = load_clicky_config(cfg_path)
    assert cfg["unified_memory_api_url"] == "http://localhost:49999/query"


def test_query_unified_memory_parses_response(tmp_path):
    cfg_path = tmp_path / "clicky_config.json"
    cfg_path.write_text(
        json.dumps({"unified_memory_api_url": "http://memory.local/query"}),
        encoding="utf-8",
    )

    fake_body = json.dumps(
        {
            "query": "PixelRAG",
            "visual_results": [{"id": "tile-a.png", "tile_metadata": {"window_title": "Docs"}}],
            "agent_memory_results": [{"summary": "Explored PixelRAG pipelines."}],
            "notes_results": [{"title": "PixelRAG Pipeline Notes", "filename": "notes.md"}],
        }
    ).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return fake_body

    with patch("clicky_integration.clicky_client.request.urlopen", return_value=FakeResponse()):
        result = query_unified_memory("PixelRAG", config_path=cfg_path)

    assert result["visual_results"]
    summary = format_overlay_summary(result)
    assert "PixelRAG" in summary or "Docs" in summary


def test_quick_query_helpers():
    assert "last 120 seconds" in quick_last_reading_query()
    assert "Example" in quick_page_connections_query("https://example.com", "Example")
    assert "example.com" in quick_page_connections_query("https://example.com")
