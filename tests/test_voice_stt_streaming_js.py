"""Streaming STT (Phase 2) — static JS contract tests.

Regression guard for the batch-transcription bottleneck: recording used to
upload a full blob and wait for one server round trip before the turn could
submit. sttStream.js opens a WebSocket channel instead so the turn can submit
close to VAD stop. These are static string assertions (no browser/jsdom) —
mirrors the convention in test_voice_esc_cancel.py / test_voice_phase0.py.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


stt_stream = _read("sttStream.js")
voice_recorder = _read("voiceRecorder.js")
voice_chat = _read("voiceChat.js")


def test_stt_stream_exports_four_functions():
    assert "export function isStreamingSttAvailable()" in stt_stream
    assert "export function startStream(" in stt_stream
    assert "export function stopStream()" in stt_stream
    assert "export function cancelStream()" in stt_stream
    assert "  isStreamingSttAvailable," in stt_stream
    assert "  startStream," in stt_stream
    assert "  stopStream," in stt_stream
    assert "  cancelStream," in stt_stream


def test_stt_stream_available_only_when_provider_is_local():
    body = stt_stream.split("export function isStreamingSttAvailable()")[1].split("export function")[0]
    assert "_cachedProvider === 'local'" in body


def test_stt_stream_ws_protocol_frames():
    assert "type: 'start'" in stt_stream
    assert "sampleRate: TARGET_SAMPLE_RATE" in stt_stream
    assert "type: 'stop'" in stt_stream
    assert "type: 'cancel'" in stt_stream


def test_voice_recorder_imports_stt_stream():
    assert "import sttStreamModule from './sttStream.js';" in voice_recorder


def test_voice_recorder_streams_only_behind_availability_check():
    assert "opts.streamStt && sttStreamModule.isStreamingSttAvailable()" in voice_recorder


def test_voice_recorder_cancel_recording_cancels_stream():
    cancel_fn = voice_recorder.split("export function cancelRecording()")[1]
    body = cancel_fn.split("export function")[0]
    assert "sttStreamModule.cancelStream()" in body


def test_voice_recorder_onstop_prefers_stream_final_over_batch():
    onstop = voice_recorder.split("mediaRecorder.onstop")[1]
    assert onstop.index("_usingStreamStt") < onstop.index("transcribeOnServer")
    assert "sttStreamModule.stopStream()" in onstop


def test_voice_chat_prefers_streaming_stt_for_local_turns():
    opts_block = voice_chat.split("const LOCAL_VOICE_RECORDING_OPTS = {")[1].split("};")[0]
    assert "streamStt: true" in opts_block
