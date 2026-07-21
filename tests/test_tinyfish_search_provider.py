"""TinyFish Search provider — request shape and result normalization."""

from services.search import providers


def test_tinyfish_search_sends_api_key_and_maps_results(monkeypatch):
    seen = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "query": "web automation",
                "results": [
                    {
                        "position": 1,
                        "site_name": "tinyfish.ai",
                        "title": "TinyFish",
                        "snippet": "AI web automation",
                        "url": "https://tinyfish.ai",
                        "date": "2026-07-01",
                    },
                    {
                        "position": 2,
                        "title": "Attention paper",
                        "snippet": "Transformers",
                        "url": "https://arxiv.org/abs/1706.03762",
                        "venue": "NeurIPS",
                        "year": 2017,
                        "cited_by_count": 100000,
                    },
                ],
                "total_results": 2,
                "page": 0,
            }

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["params"] = kwargs["params"]
        seen["headers"] = kwargs["headers"]
        return _Response()

    monkeypatch.setattr(providers, "_get_provider_key", lambda _p: "tf-test-key")
    monkeypatch.setattr(providers, "_get_result_count", lambda: 5)
    monkeypatch.setattr(providers.httpx, "get", fake_get)

    results = providers.tinyfish_search("web automation", count=5)

    assert seen["url"] == "https://api.search.tinyfish.ai"
    assert seen["params"]["query"] == "web automation"
    assert seen["headers"]["X-API-Key"] == "tf-test-key"
    assert len(results) == 2
    assert results[0]["title"] == "TinyFish"
    assert results[0]["url"] == "https://tinyfish.ai"
    assert results[0]["age"] == "2026-07-01"
    assert "NeurIPS" in results[1]["snippet"]
    assert "cited 100000" in results[1]["snippet"]


def test_tinyfish_search_maps_day_filter_to_news_recency(monkeypatch):
    seen = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    def fake_get(url, **kwargs):
        seen["params"] = kwargs["params"]
        return _Response()

    monkeypatch.setattr(providers, "_get_provider_key", lambda _p: "tf-test-key")
    monkeypatch.setattr(providers, "_get_result_count", lambda: 5)
    monkeypatch.setattr(providers.httpx, "get", fake_get)

    providers.tinyfish_search("breaking news", count=3, time_filter="day")

    assert seen["params"]["domain_type"] == "news"
    assert seen["params"]["recency_minutes"] == 1440


def test_tinyfish_search_returns_empty_without_key(monkeypatch):
    monkeypatch.setattr(providers, "_get_provider_key", lambda _p: "")
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    assert providers.tinyfish_search("anything") == []


def test_tinyfish_in_provider_registry_and_core_dispatch(monkeypatch):
    from services.search import core

    assert "tinyfish" in providers.PROVIDER_INFO
    label, needs_key, needs_url = providers.PROVIDER_INFO["tinyfish"]
    assert label == "TinyFish"
    assert needs_key is True
    assert needs_url is False

    called = {}

    def fake_tf(query, count, time_filter=None):
        called["query"] = query
        called["count"] = count
        return [{"title": "ok", "url": "https://example.com", "snippet": "s"}]

    monkeypatch.setattr(core, "tinyfish_search", fake_tf)
    out = core._call_provider("tinyfish", "hello", 3)
    assert called == {"query": "hello", "count": 3}
    assert out[0]["title"] == "ok"


def test_tinyfish_provider_key_from_settings_and_env(monkeypatch):
    from services.search import core

    for env_name in (
        "DATA_BRAVE_API_KEY",
        "GOOGLE_API_KEY",
        "TAVILY_API_KEY",
        "SERPER_API_KEY",
        "FIRECRAWL_API_KEY",
        "TINYFISH_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = {"search_provider": "tinyfish", "tinyfish_api_key": "from-settings"}
    monkeypatch.setattr(core, "_get_search_settings", lambda: settings)
    monkeypatch.setattr(providers, "_get_search_settings", lambda: settings)
    assert core.get_search_config()["has_api_key"] is True
    assert providers._get_provider_key("tinyfish") == "from-settings"

    settings_env = {"search_provider": "tinyfish"}
    monkeypatch.setenv("TINYFISH_API_KEY", "from-env")
    monkeypatch.setattr(core, "_get_search_settings", lambda: settings_env)
    monkeypatch.setattr(providers, "_get_search_settings", lambda: settings_env)
    assert providers._get_provider_key("tinyfish") == "from-env"
