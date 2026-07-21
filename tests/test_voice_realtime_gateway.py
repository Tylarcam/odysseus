"""Tests for OpenAI Realtime voice gateway."""

from services.voice.realtime_gateway import RealtimeVoiceGateway, VoiceSessionRegistry


def test_build_session_config_uses_settings_and_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({
        "voice_realtime_model": "gpt-4o-realtime-preview-2024-12-17",
        "voice_realtime_voice": "nova",
    })
    assert cfg["type"] == "realtime"
    assert cfg["model"] == "gpt-4o-realtime-preview-2024-12-17"
    assert cfg["audio"]["output"]["voice"] == "nova"
    assert cfg["turn_detection"]["type"] == "server_vad"
    assert cfg["input_audio_transcription"]["model"] == "whisper-1"
    # create_response stays false until the client session.update — avoids
    # auto-answering before the Jarvis/agent bridge patch lands.
    assert cfg["turn_detection"]["create_response"] is False


def test_build_session_config_includes_persona_instructions(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({})
    assert "Odysseus" in cfg.get("instructions", "")


def test_build_session_config_custom_instructions_override(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({"voice_realtime_instructions": "Speak like a pirate."})
    assert cfg["instructions"].startswith("Speak like a pirate.")


def test_get_stats_never_exposes_instructions(monkeypatch):
    """/api/voice/stats is public — memory-backed instructions must not leak."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    gw = RealtimeVoiceGateway()
    stats = gw.get_stats({})
    assert "instructions" not in stats
    flat = str(stats)
    assert "Odysseus, the user's personal AI assistant" not in flat


def test_get_stats_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    stats = gw.get_stats({"voice_realtime_enabled": True})
    assert stats["available"] is False
    assert stats["provider"] == "openai_realtime"


def test_get_stats_respects_voice_chat_feature_flag(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    gw = RealtimeVoiceGateway()
    stats = gw.get_stats({"voice_realtime_enabled": True, "voice_chat_enabled": False})
    assert stats["voice_chat_enabled"] is False
    assert stats["available"] is False


def test_safety_identifier_is_stable():
    gw = RealtimeVoiceGateway()
    assert gw.safety_identifier("alice") == gw.safety_identifier("alice")
    assert gw.safety_identifier("alice") != gw.safety_identifier("bob")


def test_session_registry_enforces_per_user_limit():
    reg = VoiceSessionRegistry(max_per_user=2, ttl_seconds=3600)
    assert reg.try_acquire("alice") is True
    assert reg.try_acquire("alice") is True
    assert reg.try_acquire("alice") is False
    assert reg.active_count("alice") == 2
    assert reg.try_acquire("bob") is True


def test_session_registry_expires_stale_sessions():
    reg = VoiceSessionRegistry(max_per_user=1, ttl_seconds=10)
    reg._sessions["alice"] = [1000.0]
    assert reg.active_count("alice") == 0
    assert reg.try_acquire("alice") is True
