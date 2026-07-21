"""Voice SLO metrics store and latency derivation."""

from services.voice.metrics import VoiceMetricsStore, get_voice_metrics_store, latencies_from_turn_events


def _turn(mic_start=100, speech_stop=500, response_created=700, first_audio=900, barge=None):
    events = [
        {"event": "turn.start", "elapsedMs": 0},
        {"event": "mic.start", "elapsedMs": mic_start},
        {"event": "speech.stop", "elapsedMs": speech_stop},
        {"event": "response.created", "elapsedMs": response_created},
        {"event": "first_audio_out", "elapsedMs": first_audio},
    ]
    if barge is not None:
        events.append({"event": "barge_in", "latencyMs": barge})
    return events


def test_latencies_from_turn_events():
    derived = latencies_from_turn_events(_turn())
    assert derived["mic_to_first_audio_ms"] == 800
    assert derived["speech_stop_to_response_ms"] == 200
    assert derived["barge_in_ms"] is None


def test_latencies_barge_in_from_detail():
    derived = latencies_from_turn_events(_turn(barge=180))
    assert derived["barge_in_ms"] == 180


def test_metrics_store_ingest_and_percentiles():
    store = VoiceMetricsStore(max_samples=100, mic_p50_target_ms=1200, mic_p95_target_ms=2500)
    for first in (800, 900, 1000, 1100, 3000):
        store.ingest_turn(_turn(first_audio=first))

    slo = store.slo_summary()
    mic = slo["mic_to_first_audio"]
    assert mic["count"] == 5
    assert mic["p50_ms"] is not None
    assert mic["p95_ms"] is not None
    assert slo["healthy"] is False  # 3000ms sample pushes p95 over target


def test_metrics_store_healthy_when_within_targets():
    store = VoiceMetricsStore(max_samples=100, mic_p50_target_ms=1200, mic_p95_target_ms=2500)
    for first in (800, 900, 1000, 1100, 1150):
        store.ingest_turn(_turn(first_audio=first))
    assert store.slo_summary()["healthy"] is True


def test_metrics_tracks_cmd_jarvis_slice():
    store = VoiceMetricsStore(max_samples=100, mic_p50_target_ms=1200, mic_p95_target_ms=2500)
    events = _turn(first_audio=900)
    events[0]["source"] = "cmd_jarvis"
    store.ingest_turn(events)
    slo = store.slo_summary()
    assert slo["cmd_jarvis"]["ingest_count"] == 1
    assert slo["cmd_jarvis"]["mic_to_first_audio"]["count"] == 1


def test_get_voice_metrics_store_singleton():
    assert get_voice_metrics_store() is get_voice_metrics_store()
