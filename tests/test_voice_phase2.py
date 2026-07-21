"""Phase 2 voice turn-taking — static JS + gateway contract tests.

Hands-free VAD, chat timeline sync from realtime transcripts, agent-mode
tool bridge, and region-aware session config.
"""
from pathlib import Path

from services.voice.realtime_gateway import RealtimeVoiceGateway

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


voice_realtime = _read("voiceRealtime.js")
voice_realtime_sync = _read("voiceRealtimeSync.js")
voice_chat = _read("voiceChat.js")
app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")


# --- Gateway: VAD + transcription ---


def test_gateway_session_has_transcription_and_vad(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({
        "voice_realtime_turn_detection": "semantic_vad",
        "voice_realtime_silence_ms": 600,
    })
    assert cfg["input_audio_transcription"]["model"] == "whisper-1"
    assert cfg["turn_detection"]["type"] == "semantic_vad"
    assert cfg["turn_detection"]["silence_duration_ms"] == 600
    assert cfg["turn_detection"]["create_response"] is False
    assert "text" in cfg["modalities"]


def test_gateway_region_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("VOICE_REALTIME_BASE_URL", "https://eu.api.openai.com/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    assert gw.realtime_base_url == "https://eu.api.openai.com/v1"
    stats = gw.get_stats({})
    assert stats["region_base_url"] == "https://eu.api.openai.com/v1"


# --- Client: session.update + transcript sync ---


def test_realtime_applies_session_update_on_datachannel_open():
    assert "applyClientSessionPatch" in voice_realtime
    assert "session.update" in voice_realtime
    assert "input_audio_transcription" in voice_realtime


def test_realtime_syncs_user_transcription():
    assert "conversation.item.input_audio_transcription.completed" in voice_realtime
    assert "voiceRealtimeSync.onUserTranscript" in voice_realtime
    assert "voiceRealtimeSync.onUserCommitted" in voice_realtime


def test_realtime_syncs_assistant_audio_transcript_deltas():
    assert "response.audio_transcript.delta" in voice_realtime
    assert "response.output_audio_transcript.delta" in voice_realtime
    assert "voiceRealtimeSync.onAssistantDelta" in voice_realtime


def test_voice_realtime_sync_module_exports():
    assert "export function onUserTranscript" in voice_realtime_sync
    assert "export function onAssistantDelta" in voice_realtime_sync
    assert "source: 'voice-realtime'" in voice_realtime_sync


# --- Realtime turn persistence (session history survives reload) ---


def test_realtime_sync_persists_turns_to_session():
    assert "inject_messages" in voice_realtime_sync
    assert "persistMessage" in voice_realtime_sync
    # Agent bridge persists via the chat pipeline — no double-write
    assert "isAgentBridge" in voice_realtime_sync


# --- Bridge streaming speech (sentence-by-sentence during agent run) ---


def test_bridge_speaks_sentences_during_stream():
    assert "export function onAssistantStreamText" in voice_chat
    assert "pumpBridgeSpeech" in voice_chat
    assert "resetBridgeSpeech" in voice_chat
    chat_js = _read("chat.js")
    assert "onAssistantStreamText" in chat_js
    assert "onAssistantStreamRoundEnd" in chat_js


# --- Agent-mode tool bridge ---


def test_cmd_center_voice_delegate_activation():
    cmd_center = _read("cmdCenter.js")
    assert "_activateVoiceDelegate" in cmd_center
    assert "_ensureAgentModeForDelegate" in cmd_center
    assert "mode-agent-btn" in cmd_center
    assert "reapplySessionPatch" in cmd_center or "agent voice" in cmd_center


def test_cmd_center_display_settings_and_atlas():
    cmd_center = _read("cmdCenter.js")
    assert "CMD_COMPONENT_ATLAS" in cmd_center
    assert "odysseus-cmd-center-visibility" in cmd_center
    assert "cmd-center-settings" in cmd_center
    assert "data-cmd-vis" in cmd_center
    assert "_applyVisibilityPrefs" in cmd_center
    assert "_updateRailLayout" in cmd_center
    assert 'data-cmd-rail="left"' in cmd_center
    assert 'data-cmd-rail="right"' in cmd_center
    for comp_id in (
        "status_pills", "vitals", "priority_queue", "globe_scene",
        "hero", "command_deck", "ai_wire",
    ):
        assert comp_id in cmd_center


def test_realtime_reapply_session_patch():
    assert "export function reapplySessionPatch" in voice_realtime


def test_realtime_bridges_agent_mode_to_chat():
    assert "shouldBridgeTranscript" in voice_realtime
    assert "onBridgeTranscript" in voice_realtime
    assert "export function onBridgeTranscript" in voice_chat
    assert "speakText" in voice_chat


def test_realtime_speak_text_via_response_create():
    assert "export function speakText" in voice_realtime
    assert "response.create" in voice_realtime
    assert "create_response: !_voiceLocked && !agent" in voice_realtime
    assert "X-Voice-Agent-Bridge" in voice_realtime
    assert "softRearmListening" in voice_realtime
    assert "isVoiceBargeSubmit" in voice_chat
    assert "[cmd_jarvis]" in voice_chat


# --- Hands-free UI (no PTT in realtime mode) ---


def test_app_shows_listening_mode_for_realtime():
    # Mic button reflects hands-free realtime listening state
    assert "realtimeListening" in app_js
    assert "isRealtimeActive" in app_js
    assert "Listening — speak naturally" in app_js


def test_local_voice_mode_auto_starts_and_auto_stops():
    voice_recorder = _read("voiceRecorder.js")
    assert "LOCAL_VOICE_RECORDING_OPTS" in voice_chat
    assert "scheduleAutoResume({ force: true })" in voice_chat
    assert "_startRecordingFn(LOCAL_VOICE_RECORDING_OPTS)" in voice_chat
    assert "autoStart: false" in voice_chat
    assert "startAutoStopMonitor" in voice_recorder
    assert "vad.local.start" in voice_recorder
    assert "vad.local.stop" in voice_recorder
    assert "opts = {}" in app_js
    assert "voiceRecorderModule.startRecording(" in app_js and "opts" in app_js
