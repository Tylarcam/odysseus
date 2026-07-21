"""Tests for unified personal memory API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.agent_memory import store_agent_memory
from tools.mempalace_search import build_notes_index
from tools.unified_memory_api import create_app, query_personal_memory


@pytest.fixture
def memory_fixtures(tmp_path):
    agent_path = tmp_path / "agent_memory.json"
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    (notes_root / "pixelrag_pipeline_notes.md").write_text(
        "# PixelRAG Pipeline Notes\n\nTiles from Screenpipe.\n",
        encoding="utf-8",
    )
    notes_index = tmp_path / "notes_index.json"
    build_notes_index(notes_root=notes_root, index_path=notes_index)

    store_agent_memory(
        "Explored PixelRAG pipelines.",
        tags=["pixelrag"],
        path=agent_path,
    )

    metadata_path = tmp_path / "tiles_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "0": {
                    "article_id": 0,
                    "source_filename": "tile-a.png",
                    "timestamp": "2026-07-07T01:05:00",
                    "url": "https://example.com/pixelrag",
                    "window_title": "PixelRAG docs",
                    "screenpipe_path": "/fake/screen.png",
                },
                "tile-a.png": {
                    "article_id": 0,
                    "source_filename": "tile-a.png",
                    "timestamp": "2026-07-07T01:05:00",
                    "url": "https://example.com/pixelrag",
                    "window_title": "PixelRAG docs",
                    "screenpipe_path": "/fake/screen.png",
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_pixelrag(query_text: str, k: int):
        return [{"article_id": 0, "id": "0", "score": 0.99, "query": query_text}]

    return {
        "agent_path": agent_path,
        "notes_index": notes_index,
        "metadata_path": metadata_path,
        "fake_pixelrag": fake_pixelrag,
    }


def test_query_personal_memory_combines_sources(memory_fixtures, monkeypatch):
    monkeypatch.setattr(
        "tools.unified_memory_api.search_agent_memory",
        lambda q, limit=5: [{"summary": "Explored PixelRAG pipelines.", "tags": ["pixelrag"]}],
    )
    monkeypatch.setattr(
        "tools.unified_memory_api.search_notes_index",
        lambda q, limit=5: [{"filename": "pixelrag_pipeline_notes.md", "title": "PixelRAG Pipeline Notes"}],
    )

    result = query_personal_memory(
        "PixelRAG pipeline diagram",
        k=3,
        pixelrag_search=memory_fixtures["fake_pixelrag"],
        metadata_path=memory_fixtures["metadata_path"],
    )

    assert result["visual_results"]
    assert result["agent_memory_results"]
    assert result["notes_results"]
    assert result["visual_results"][0]["tile_metadata"]["window_title"] == "PixelRAG docs"


def test_unified_memory_api_route(memory_fixtures, monkeypatch):
    monkeypatch.setattr(
        "tools.unified_memory_api.query_personal_memory",
        lambda query_text, k=5, **kwargs: {
            "query": query_text,
            "visual_results": [{"id": "tile-a.png"}],
            "agent_memory_results": [{"summary": "Explored PixelRAG pipelines."}],
            "notes_results": [{"filename": "pixelrag_pipeline_notes.md"}],
        },
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    response = client.post("/query", json={"query": "PixelRAG", "k": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["visual_results"]
    assert body["agent_memory_results"]
    assert body["notes_results"]
    assert response.headers.get("X-Request-ID")


def test_remember_endpoint_persists_summary(memory_fixtures, monkeypatch):
    # store_agent_memory re-loads memory_stack.env which would clobber an
    # AGENT_MEMORY_PATH env override, so patch the path resolver directly.
    monkeypatch.setattr(
        "tools.agent_memory.agent_memory_path",
        lambda path=None: memory_fixtures["agent_path"],
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/remember",
        json={"summary": "Shipped incremental embed for archivist.", "tags": ["cursor-session"], "source": "cursor"},
    )

    assert response.status_code == 200
    record = response.json()
    assert record["summary"] == "Shipped incremental embed for archivist."
    assert "cursor-session" in record["tags"]
    assert "source:cursor" in record["tags"]
    assert record["id"]

    persisted = json.loads(memory_fixtures["agent_path"].read_text(encoding="utf-8"))
    entries = persisted.get("entries") or []
    assert any(e["summary"] == "Shipped incremental embed for archivist." for e in entries)


def test_remember_endpoint_rejects_empty_summary(memory_fixtures, monkeypatch):
    monkeypatch.setattr(
        "tools.agent_memory.agent_memory_path",
        lambda path=None: memory_fixtures["agent_path"],
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    assert client.post("/remember", json={"summary": ""}).status_code == 400
    assert client.post("/remember", json={}).status_code == 400
    assert client.post("/remember", json={"summary": "   "}).status_code == 400
