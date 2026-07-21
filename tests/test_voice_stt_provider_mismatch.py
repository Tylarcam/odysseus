"""STT provider mismatch — static contract tests (Phase 1.5).

Regression guard for: pressing record showed "Transcription failed: STT
service not available or set to browser mode" because the client's cached
_sttProvider (populated once from GET /api/stt/stats) had gone stale, or the
provider said "browser" while the browser itself lacked SpeechRecognition.
The fix re-checks the provider before committing to record and gives an
actionable 503 message instead of a generic one.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


voice_recorder = _read("voiceRecorder.js")
stt_routes = (ROOT / "routes" / "stt_routes.py").read_text(encoding="utf-8")
settings_js = _read("settings.js")
index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_recorder_refreshes_stale_provider_before_recording():
    assert "_sttProviderFetchedAt" in voice_recorder
    assert "STT_PROVIDER_STALE_MS" in voice_recorder
    # The staleness check + refresh must happen before mediaRecorder.start.
    then_block = voice_recorder.split(".then(async stream =>")[1]
    start_idx = then_block.index("mediaRecorder.start(")
    assert "await refreshSttProvider()" in then_block[:start_idx]
    assert "_sttProviderFetchedAt" in then_block[:start_idx]


def test_recorder_guards_missing_browser_speech_recognition():
    then_block = voice_recorder.split(".then(async stream =>")[1]
    start_idx = then_block.index("mediaRecorder.start(")
    guard = then_block[:start_idx]
    assert "!window.SpeechRecognition && !window.webkitSpeechRecognition" in guard
    assert "showError" in guard
    assert "Settings > Audio & Voice" in guard
    # Must not silently proceed to record — reset the UI instead.
    assert "_resetRecordingUI();" in guard.split("SpeechRecognition")[-1] or "_resetRecordingUI()" in guard


def test_stt_routes_503_message_names_provider_and_settings():
    assert "stt_service.get_stats()" in stt_routes
    assert "_stt_unavailable_message" in stt_routes
    assert "Settings > Audio & Voice" in stt_routes
    assert "detail={\"message\": message}" in stt_routes
    assert "INSTALL_STT=true" in stt_routes


def test_settings_stt_status_polls_stats():
    assert "set-sttStatusMsg" in index_html
    assert "refreshSttStats" in settings_js
    assert "/api/stt/stats" in settings_js
    assert "missing_package" in settings_js
    assert "load_failed" in settings_js
