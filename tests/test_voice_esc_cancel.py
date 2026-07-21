"""Esc cancels a voice turn (discard, never submit) — static JS contract tests.

Regression guard for the Esc-to-stop-recording bug: stopping the recorder
used to transcribe + submit the take, and the PTT loop auto-resumed the mic
right after. Esc must map to a real cancel: discard the audio, abort the
voice-submitted agent turn, silence speech, and stay quiet until the user
explicitly re-arms.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


voice_recorder = _read("voiceRecorder.js")
voice_chat = _read("voiceChat.js")
voice_ptt = _read("voiceKeyboardPtt.js")


def test_recorder_has_discarding_cancel():
    assert "export function cancelRecording()" in voice_recorder
    assert "_discardOnStop = true;" in voice_recorder
    # The discard branch must run before any transcription/delivery.
    onstop = voice_recorder.split("mediaRecorder.onstop")[1]
    assert onstop.index("_discardOnStop") < onstop.index("deliverTranscription")
    # cancelRecording is reachable through the module object.
    assert "cancelRecording,\n" in voice_recorder


def test_recorder_cancel_covers_getusermedia_window():
    assert "_acquiringMic = true;" in voice_recorder
    assert "_cancelWhileAcquiring = true;" in voice_recorder
    # Cancelled during acquire: release the mic tracks and reset the UI.
    assert "stream.getTracks().forEach(track => track.stop());" in voice_recorder
    assert "mic.cancelled" in voice_recorder


def test_recorder_cancel_aborts_browser_stt():
    cancel_fn = voice_chat and voice_recorder.split("export function cancelRecording()")[1]
    body = cancel_fn.split("export function")[0]
    assert "rec.abort()" in body
    assert "_browserTranscript = ''" in body


def test_voice_chat_cancel_turn_contract():
    assert "export function cancelTurn(" in voice_chat
    assert "voiceRecorderModule.cancelRecording?.()" in voice_chat
    assert "abortCurrentRequest?.(true)" in voice_chat
    assert "turn.cancelled" in voice_chat
    assert "cancelTurn,\n" in voice_chat


def test_voice_chat_suppresses_auto_resume_after_cancel():
    assert "_resumeSuppressed = true;" in voice_chat
    # Both resume entry points must consult the suppression flag.
    schedule = voice_chat.split("function scheduleAutoResume")[1].split("function ")[0]
    assert "_resumeSuppressed" in schedule
    listening = voice_chat.split("export async function startLocalListening")[1].split("export ")[0]
    assert "_resumeSuppressed" in listening
    # Explicit user starts clear the suppression.
    assert "if (reason === 'manual' || reason === 'space_hold') _resumeSuppressed = false;" in voice_chat


def test_ptt_esc_cancels_instead_of_stop_submit():
    assert "cancelTurn?.({ reason: 'esc' })" in voice_ptt
    # The old stop-and-submit path must be gone from the Esc handler.
    stop_fn = voice_ptt.split("function _stopVoice()")[1].split("function ")[0]
    assert "stopRecording" not in stop_fn
    # Realtime hot mic: Esc with nothing in flight disconnects the link.
    assert "isRealtimeActive?.()" in stop_fn
    assert "setActive(false" in stop_fn
