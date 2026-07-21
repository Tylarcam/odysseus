"""Voice route rate limits and session caps."""

from unittest.mock import MagicMock

import pytest

from src.rate_limiter import RateLimiter
from services.voice.realtime_gateway import RealtimeVoiceGateway, VoiceSessionRegistry


def test_connect_rate_limiter_blocks_third_request():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    key = "alice:127.0.0.1"
    assert limiter.check(key) is True
    assert limiter.check(key) is True
    assert limiter.check(key) is False


def test_session_registry_purge_releases_expired_slot():
    reg = VoiceSessionRegistry(max_per_user=1, ttl_seconds=60)
    reg._sessions["alice"] = [1000.0]
    active = reg._purge_stale("alice", 1061.0)
    assert active == []
    assert reg.try_acquire("alice") is True


@pytest.mark.asyncio
async def test_connect_webrtc_session_limit_surfaces_as_runtime_error():
    reg = VoiceSessionRegistry(max_per_user=1, ttl_seconds=3600)
    reg.try_acquire("alice")

    gw = RealtimeVoiceGateway.__new__(RealtimeVoiceGateway)
    gw.api_key = "test-key"
    gw.base_url = "https://api.openai.com/v1"
    gw.default_model = "gpt-4o-realtime-preview"
    gw.timeout = 30
    gw.session_registry = reg

    with pytest.raises(RuntimeError, match="session limit"):
        await gw.connect_webrtc("v=0", username="alice")
