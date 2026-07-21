"""Phase 0 voice-chat instrumentation — static JS contract tests.

Verifies VoiceTelemetry, STT onend wait, awaiting watchdog, stream-error
recovery, TTS idle events, and telemetry emissions without a browser.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


voice_telemetry = _read("voiceTelemetry.js")
voice_recorder = _read("voiceRecorder.js")
voice_chat = _read("voiceChat.js")
voice_realtime = _read("voiceRealtime.js")
chat = _read("chat.js")
tts_ai = _read("tts-ai.js")


# --- voiceTelemetry.js ---


def test_voice_telemetry_exports_and_debug_gate():
    assert "export function startTurn()" in voice_telemetry
    assert "export function emit(" in voice_telemetry
    assert "export function getRecentEvents(" in voice_telemetry
    assert "function isDebug()" in voice_telemetry
    assert "get('voice_debug')" in voice_telemetry
    assert "odysseus_voice_debug" in voice_telemetry
    assert "  startTurn," in voice_telemetry
    assert "  emit," in voice_telemetry
    assert "  getRecentEvents," in voice_telemetry
    assert "  isDebug," in voice_telemetry
    assert "_events.slice(-limit)" in voice_telemetry


# --- voiceRecorder.js ---


def test_voice_recorder_stop_browser_stt_waits_for_onend():
    assert "function stopBrowserSTT()" in voice_recorder
    assert "return new Promise" in voice_recorder
    assert "rec.onend" in voice_recorder
    assert "wait for onend" in voice_recorder.lower()


# --- voiceChat.js ---


def test_voice_chat_awaiting_watchdog_and_on_turn_failed():
    assert "AWAITING_TIMEOUT_MS" in voice_chat
    assert "onTurnFailed('awaiting_timeout')" in voice_chat
    assert "export function onTurnFailed(" in voice_chat


def test_voice_chat_listens_for_tts_idle():
    assert "addEventListener('odysseus:tts-idle'" in voice_chat
    assert "voiceTelemetry.emit('tts.idle')" in voice_chat


# --- chat.js ---


def test_chat_calls_on_turn_failed_on_stream_error_when_awaiting():
    assert "isAwaitingReply" in chat
    assert "onTurnFailed" in chat
    idx_awaiting = chat.index("isAwaitingReply")
    idx_failed = chat.index("onTurnFailed", idx_awaiting)
    assert idx_failed > idx_awaiting
    assert "stream_error" in chat or "failReason" in chat


def test_chat_emits_response_created():
    assert "response.created" in chat
    assert "voiceTelemetry.emit('response.created')" in chat


# --- tts-ai.js ---


def test_tts_ai_stop_dispatches_idle_event():
    stop_idx = tts_ai.index("stop() {")
    idle_idx = tts_ai.index("odysseus:tts-idle", stop_idx)
    assert idle_idx > stop_idx


def test_tts_ai_emits_first_audio_out():
    assert "first_audio_out" in tts_ai
    assert "voiceTelemetry.emit('first_audio_out'" in tts_ai


def test_tts_ai_skip_to_next_paragraph():
    assert "skipToNext()" in tts_ai
    assert "_splitParagraphs" in tts_ai
    assert "ai-tts-skip-btn" in tts_ai
    assert "Skip to next paragraph" in tts_ai


def test_tts_ai_strips_horizontal_rules():
    extract_idx = tts_ai.index("extractPlainText(content)")
    section = tts_ai[extract_idx:extract_idx + 1200]
    assert "/^(?:---|\\*\\*\\*|___)\\s*$/gm" in section
    assert "querySelectorAll('pre, code, hr')" in section


# --- voiceDebugPanel.js (optional file) ---


def test_voice_debug_panel_shows_last_20_events_if_present():
    panel_path = JS / "voiceDebugPanel.js"
    if not panel_path.exists():
        return
    panel = panel_path.read_text(encoding="utf-8")
    assert "MAX_DISPLAY_EVENTS = 20" in panel
    assert "slice(-MAX_DISPLAY_EVENTS)" in panel


# --- Phase 4: reconnect + latency ---


def test_voice_realtime_reconnect_backoff():
    assert "scheduleReconnect" in voice_realtime
    assert "RECONNECT_DELAYS_MS" in voice_realtime
    assert "MAX_RECONNECT_ATTEMPTS" in voice_realtime
    assert "realtime.reconnect.start" in voice_realtime
    assert "realtime.reconnect.done" in voice_realtime
    assert "session.expired" in voice_realtime


def test_voice_chat_handles_realtime_reconnect():
    assert "odysseus:voice-realtime-reconnecting" in voice_chat
    assert "odysseus:voice-realtime-reconnect-failed" in voice_chat
    assert "pauseMic" in voice_chat
    assert "voiceRealtimeModule.reconnect" in voice_chat


def test_voice_telemetry_unified_first_audio_and_reconnect_diag():
    assert "FIRST_AUDIO_EVENTS" in voice_telemetry
    assert "speechStopToResponse" in voice_telemetry
    assert "voiceChatModule" in voice_telemetry
    assert "reconnecting" in voice_telemetry


def test_voice_telemetry_server_flush():
    assert "flushTurnToServer" in voice_telemetry
    assert "/api/voice/telemetry" in voice_telemetry
    assert "TURN_FLUSH_EVENTS" in voice_telemetry

