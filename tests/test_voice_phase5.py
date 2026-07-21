"""Phase 5 voice UX polish — static JS contract tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


voice_status = _read("voiceStatus.js")
voice_visualizer = _read("voiceVisualizer.js")
voice_realtime = _read("voiceRealtime.js")
voice_chat = _read("voiceChat.js")
index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
settings_py = (ROOT / "src" / "settings.py").read_text(encoding="utf-8")
gateway_py = (ROOT / "services" / "voice" / "realtime_gateway.py").read_text(encoding="utf-8")


def test_voice_status_states_and_init():
    assert "initVoiceStatus" in voice_status
    assert "setVoiceModeActive" in voice_status
    assert "thinking" in voice_status
    assert "reconnecting" in voice_status
    assert "odysseus:voice-ui-state" in voice_status


def test_voice_visualizer_thinking_state():
    assert "emitVoiceThinking" in voice_visualizer
    assert "is-thinking" in voice_visualizer
    assert "odysseus:voice-thinking" in voice_visualizer


def test_voice_realtime_phase5_hooks():
    assert "emitVoiceThinking" in voice_realtime
    assert "setReconnectEnabled" in voice_realtime
    assert "pauseMic" in voice_realtime
    assert "reconnect" in voice_realtime
    assert "odysseus:audio-output-changed" in voice_realtime
    assert "odysseus:voice-realtime-reconnecting" in voice_realtime
    assert "voice_chat_enabled" in voice_realtime


def test_voice_chat_feature_flag():
    assert "isVoiceChatFeatureEnabled" in voice_chat
    assert "voice_chat_enabled" in voice_chat
    assert "odysseus:voice-ui-state" in voice_chat


def test_index_voice_status_bar():
    assert 'id="voice-status-bar"' in index_html
    assert "realtime AI session" in index_html


def test_settings_voice_chat_enabled_default():
    assert '"voice_chat_enabled": True' in settings_py


def test_gateway_exposes_voice_chat_enabled():
    assert "voice_chat_enabled" in gateway_py
