"""Story Canvas Firecrawl research endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.story_canvas_routes import setup_story_canvas_routes


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        "routes.story_canvas_routes.get_current_user",
        lambda _request: None,
    )
    app = FastAPI()
    app.include_router(setup_story_canvas_routes())
    return TestClient(app)


def test_story_canvas_research_requires_firecrawl_key(client, monkeypatch):
    monkeypatch.setattr(
        "services.search.providers._get_provider_key",
        lambda _p: "",
    )
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    res = client.post("/api/story-canvas/research", json={"query": "test"})
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert "FIRECRAWL_API_KEY" in detail
    assert "firecrawl_api_key" in detail


def test_story_canvas_research_returns_results(client, monkeypatch):
    monkeypatch.setattr(
        "services.search.providers._get_provider_key",
        lambda _p: "fc-test-key",
    )
    monkeypatch.setattr(
        "services.search.providers.firecrawl_search",
        lambda query, count=None: [
            {"title": "Example", "url": "https://example.com", "snippet": "Hello"}
        ],
    )

    res = client.post("/api/story-canvas/research", json={"query": "test"})
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "test"
    assert data["provider"] == "firecrawl"
    assert data["result_count"] == 1
    assert data["results"][0]["url"] == "https://example.com"


def test_get_provider_key_reads_firecrawl_env(monkeypatch):
    from services.search import providers

    monkeypatch.setattr(providers, "_get_search_settings", lambda: {})
    monkeypatch.setenv("FIRECRAWL_API_KEY", "from-env-key")
    assert providers._get_provider_key("firecrawl") == "from-env-key"
