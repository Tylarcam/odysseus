"""Phase 3 voice barge-in — static JS contract tests.

Verifies interruption policy: response.cancel, output buffer clear,
debounce during agent start, half-duplex fallback, and visualizer priority.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


voice_realtime = _read("voiceRealtime.js")
voice_chat = _read("voiceChat.js")
voice_visualizer = _read("voiceVisualizer.js")
voice_telemetry = _read("voiceTelemetry.js")
app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
voice_status = _read("voiceStatus.js")


def test_realtime_barge_in_sends_cancel_and_clear():
    assert "performBargeIn" in voice_realtime
    assert "response.cancel" in voice_realtime
    assert "output_audio_buffer.clear" in voice_realtime
    assert "voiceTelemetry.emit('barge_in'" in voice_realtime


def test_realtime_debounces_barge_in_at_agent_start():
    assert "BARGE_IN_DEBOUNCE_MS" in voice_realtime
    assert "isBargeInDebounced" in voice_realtime
    assert "barge_in.debounced" in voice_realtime


def test_realtime_half_duplex_pauses_mic_during_agent_speech():
    assert "isHalfDuplex" in voice_realtime
    assert "setHalfDuplex" in voice_realtime
    assert "HALF_DUPLEX_STORAGE_KEY" in voice_realtime
    idx_half = voice_realtime.index("isHalfDuplex()")
    idx_pause = voice_realtime.index("pauseMic()", idx_half)
    assert idx_pause > idx_half


def test_realtime_stops_remote_playback_on_barge_in():
    assert "stopRemotePlayback" in voice_realtime
    idx_barge = voice_realtime.index("performBargeIn")
    idx_stop = voice_realtime.index("stopRemotePlayback", idx_barge)
    assert idx_stop > idx_barge


def test_realtime_handles_cancelled_response():
    assert "response.cancelled" in voice_realtime
    assert "output_audio_buffer.cleared" in voice_realtime


def test_visualizer_listening_overrides_speaking():
    assert "listening && !thinking" in voice_visualizer or "speaking && !listening" in voice_visualizer
    idx_listen = voice_visualizer.index("is-listening")
    assert "speaking && !listening" in voice_visualizer


def test_visualizer_reconcile_prioritizes_listening():
    idx_reconcile = voice_visualizer.index("function reconcileAudioGraph")
    chunk = voice_visualizer[idx_reconcile:idx_reconcile + 400]
    listen_idx = chunk.index("if (listening)")
    speak_idx = chunk.index("if (speaking)")
    assert listen_idx < speak_idx


def test_telemetry_tracks_barge_in():
    assert "'barge_in'" in voice_telemetry
    assert "barge-in OK" in voice_telemetry


def test_local_voice_barge_in_stops_tts_and_listens():
    assert "export async function startLocalListening" in voice_chat
    assert "localTtsIsSpeaking" in voice_chat
    assert "window.aiTTSManager.stop()" in voice_chat
    assert "voiceTelemetry.emit('local_barge_in'" in voice_chat
    assert "startLocalListening({ interrupt: true" in app_js


def test_local_voice_status_shows_transcribing_as_thinking():
    assert "stt.server.start" in voice_status
    assert "stt.browser.end" in voice_status
    assert "applyState('thinking')" in voice_status
