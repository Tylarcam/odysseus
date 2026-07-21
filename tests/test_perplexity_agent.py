"""Tests for Perplexity Agent API integration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.perplexity_agent import (
    check_budget,
    get_api_key,
    parse_agent_response,
    record_spend,
    resolve_research_engine,
    run_deep_research,
    verify_sonar_api_key,
)


SAMPLE_RESPONSE = {
    "id": "resp_test",
    "status": "completed",
    "output": [
        {
            "type": "search_results",
            "queries": ["test query"],
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com/a",
                    "snippet": "Snippet text",
                }
            ],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Final report body."}],
        },
    ],
    "usage": {
        "cost": {"total_cost": 0.042, "currency": "USD"},
    },
}


def test_resolve_research_engine_aliases():
    assert resolve_research_engine("perplexity_agent") == "perplexity_agent"
    assert resolve_research_engine("perplexity") == "perplexity_agent"
    assert resolve_research_engine("agent") == "perplexity_agent"
    assert resolve_research_engine("iterative") == "iterative"
    assert resolve_research_engine("") == "iterative"


def test_parse_agent_response_extracts_report_sources_and_cost():
    parsed = parse_agent_response(SAMPLE_RESPONSE, preset="deep-research")
    assert parsed["report"] == "Final report body."
    assert len(parsed["sources"]) == 1
    assert parsed["sources"][0]["url"] == "https://example.com/a"
    assert parsed["findings"][0]["summary"] == "Snippet text"
    assert parsed["stats"]["Engine"] == "Perplexity Agent"
    assert parsed["total_cost_usd"] == pytest.approx(0.042)


def test_get_api_key_prefers_settings(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    with patch("src.settings.get_setting", return_value="settings-key"):
        assert get_api_key() == "settings-key"


def test_get_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "env-key")
    with patch("src.settings.get_setting", return_value=""):
        assert get_api_key() == "env-key"


def test_check_budget_blocks_when_over_cap(tmp_path, monkeypatch):
    usage_file = tmp_path / "perplexity_usage.json"
    monkeypatch.setattr("src.perplexity_agent.USAGE_FILE", usage_file)
    monkeypatch.setattr("src.perplexity_agent._today_key", lambda: "2026-06-14")
    usage_file.write_text(json.dumps({"2026-06-14": {"total_usd": 6.0}}), encoding="utf-8")
    with patch("src.settings.get_setting", return_value=5.0):
        err = check_budget()
    assert err is not None
    assert "budget" in err.lower()


@pytest.mark.asyncio
async def test_run_deep_research_posts_preset(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_RESPONSE

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.perplexity_agent.httpx.AsyncClient", return_value=mock_client), patch(
        "src.perplexity_agent.record_spend"
    ) as record, patch("src.perplexity_agent.check_budget", return_value=None):
        parsed = await run_deep_research("What is Comet?", preset="deep-research")

    mock_client.post.assert_awaited_once()
    _args, kwargs = mock_client.post.call_args
    assert kwargs["json"]["preset"] == "deep-research"
    assert kwargs["json"]["input"] == "What is Comet?"
    assert parsed["report"] == "Final report body."
    record.assert_called_once_with(0.042)


def test_record_spend_accumulates(tmp_path, monkeypatch):
    usage_file = tmp_path / "perplexity_usage.json"
    monkeypatch.setattr("src.perplexity_agent.USAGE_FILE", usage_file)
    monkeypatch.setattr("src.perplexity_agent._today_key", lambda: "2026-06-14")
    record_spend(1.25)
    record_spend(0.75)
    data = json.loads(usage_file.read_text(encoding="utf-8"))
    assert data["2026-06-14"]["total_usd"] == pytest.approx(2.0)
    assert data["2026-06-14"]["calls"] == 2


@pytest.mark.asyncio
async def test_verify_sonar_api_key_posts_chat_completion(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "API key test worked."}}],
        "usage": {"cost": {"total_cost": 0.00628}},
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.perplexity_agent.httpx.AsyncClient", return_value=mock_client):
        result = await verify_sonar_api_key()

    mock_client.post.assert_awaited_once()
    _args, kwargs = mock_client.post.call_args
    assert kwargs["json"]["model"] == "sonar-pro"
    assert result["ok"] is True
    assert result["message"] == "API key test worked."
    assert result["total_cost_usd"] == pytest.approx(0.00628)
