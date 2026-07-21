"""Voice.ai TTS provider — request shape + missing-key behavior."""

from services.tts import tts_service as tts_mod
from services.tts.tts_service import TTSService, VOICEAI_DEFAULT_MODEL, VOICEAI_TTS_URL


def test_voiceai_unavailable_without_key(monkeypatch, tmp_path):
    service = TTSService(cache_dir=str(tmp_path))
    monkeypatch.delenv("VOICEAI_API_KEY", raising=False)
    monkeypatch.setattr(service, "_load_settings", lambda: {
        "tts_enabled": True,
        "tts_provider": "voiceai",
        "tts_model": VOICEAI_DEFAULT_MODEL,
        "tts_voice": "",
        "tts_speed": "1",
    })

    assert service.available is False
    assert service.synthesize("hello") is None
    stats = service.get_stats()
    assert stats["available"] is False
    assert stats["reason"] == "missing_api_key"


def test_voiceai_synthesize_request_shape(monkeypatch, tmp_path):
    service = TTSService(cache_dir=str(tmp_path))
    monkeypatch.setenv("VOICEAI_API_KEY", "vk_test_key")
    monkeypatch.setenv("VOICEAI_VOICE_ID", "voice-default-uuid")
    monkeypatch.setattr(service, "_load_settings", lambda: {
        "tts_enabled": True,
        "tts_provider": "voiceai",
        "tts_model": "tts-1",  # leftover OpenAI model → remapped
        "tts_voice": "alloy",  # leftover OpenAI voice → env default
        "tts_speed": "1",
    })

    captured = {}

    class FakeResponse:
        content = b"ID3fake-mp3"

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(tts_mod.httpx, "post", fake_post)

    assert service.available is True
    audio = service.synthesize("Hello from Voice.ai", use_cache=False)
    assert audio == b"ID3fake-mp3"
    assert captured["url"] == VOICEAI_TTS_URL
    assert captured["headers"]["Authorization"] == "Bearer vk_test_key"
    assert captured["json"]["text"] == "Hello from Voice.ai"
    assert captured["json"]["model"] == VOICEAI_DEFAULT_MODEL
    assert captured["json"]["language"] == "en"
    assert captured["json"]["audio_format"] == "mp3"
    assert captured["json"]["voice_id"] == "voice-default-uuid"


def test_voiceai_respects_explicit_voice_and_model(monkeypatch, tmp_path):
    service = TTSService(cache_dir=str(tmp_path))
    monkeypatch.setenv("VOICEAI_API_KEY", "vk_test_key")
    monkeypatch.setattr(service, "_load_settings", lambda: {
        "tts_enabled": True,
        "tts_provider": "voiceai",
        "tts_model": "voiceai-tts-lite-v1-latest",
        "tts_voice": "custom-voice-uuid",
        "tts_speed": "1",
    })

    captured = {}

    class FakeResponse:
        content = b"\xff\xfbaudio"

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(tts_mod.httpx, "post", fake_post)
    assert service.synthesize("hi", use_cache=False)
    assert captured["json"]["model"] == "voiceai-tts-lite-v1-latest"
    assert captured["json"]["voice_id"] == "custom-voice-uuid"
