# services/voice/metrics.py
"""In-memory voice SLO metrics — latency histograms from client telemetry batches."""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

FIRST_AUDIO_EVENTS = frozenset({"first_audio_out", "response.first_audio_out"})
MIC_START_EVENTS = frozenset({"mic.start", "turn.start"})
MIC_START_ORDER = ("mic.start", "turn.start")
STT_DONE_EVENTS = frozenset({"stt.final", "stt.server.done", "stt.browser.end"})
JARVIS_SOURCE = "cmd_jarvis"


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    rank = (len(ordered) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    weight = rank - lo
    return round(ordered[lo] * (1 - weight) + ordered[hi] * weight, 1)


def _segment_ms(events: List[dict], from_event: str, to_event: str) -> Optional[float]:
    start = next((e for e in events if e.get("event") == from_event), None)
    end = next((e for e in events if e.get("event") == to_event), None)
    if not start or not end:
        return None
    a, b = start.get("elapsedMs"), end.get("elapsedMs")
    if a is None or b is None:
        return None
    return float(b - a)


def _first_elapsed(events: List[dict], names: frozenset) -> Optional[float]:
    for entry in events:
        if entry.get("event") in names:
            val = entry.get("elapsedMs")
            if val is not None:
                return float(val)
    return None


def turn_is_jarvis(events: List[dict]) -> bool:
    """True when any event in the turn is tagged source=cmd_jarvis."""
    return any((e.get("source") or "") == JARVIS_SOURCE for e in events)


def latencies_from_turn_events(events: List[dict]) -> Dict[str, Optional[float]]:
    """Derive SLO latency segments from a single turn's ordered telemetry events."""
    mic_start = None
    for name in MIC_START_ORDER:
        if name not in MIC_START_EVENTS:
            continue
        hit = next((e for e in events if e.get("event") == name), None)
        if hit and hit.get("elapsedMs") is not None:
            mic_start = float(hit["elapsedMs"])
            break
    first_audio = _first_elapsed(events, FIRST_AUDIO_EVENTS)
    mic_to_first = None
    if mic_start is not None and first_audio is not None:
        mic_to_first = first_audio - mic_start

    barge = next((e for e in events if e.get("event") == "barge_in"), None)
    barge_ms = None
    if barge and barge.get("latencyMs") is not None:
        barge_ms = float(barge["latencyMs"])

    return {
        "mic_to_first_audio_ms": mic_to_first,
        "speech_stop_to_response_ms": _segment_ms(events, "speech.stop", "response.created"),
        "barge_in_ms": barge_ms,
    }


class VoiceMetricsStore:
    """Thread-safe rolling latency samples for voice SLO dashboards."""

    def __init__(
        self,
        max_samples: int = 5000,
        mic_p50_target_ms: float = 1200,
        mic_p95_target_ms: float = 2500,
    ) -> None:
        self.max_samples = max(100, max_samples)
        self.mic_p50_target_ms = mic_p50_target_ms
        self.mic_p95_target_ms = mic_p95_target_ms
        self._lock = threading.Lock()
        self._mic_to_first_audio: List[float] = []
        self._speech_stop_to_response: List[float] = []
        self._barge_in: List[float] = []
        self._jarvis_mic_to_first_audio: List[float] = []
        self._jarvis_ingest_count = 0
        self._ingest_count = 0

    def ingest_turn(self, events: List[dict]) -> Dict[str, Optional[float]]:
        """Record derived latencies from one turn's event list."""
        derived = latencies_from_turn_events(events)
        jarvis = turn_is_jarvis(events)
        with self._lock:
            self._ingest_count += 1
            if jarvis:
                self._jarvis_ingest_count += 1
            if derived["mic_to_first_audio_ms"] is not None:
                self._append(self._mic_to_first_audio, derived["mic_to_first_audio_ms"])
                if jarvis:
                    self._append(self._jarvis_mic_to_first_audio, derived["mic_to_first_audio_ms"])
            if derived["speech_stop_to_response_ms"] is not None:
                self._append(self._speech_stop_to_response, derived["speech_stop_to_response_ms"])
            if derived["barge_in_ms"] is not None:
                self._append(self._barge_in, derived["barge_in_ms"])
        return derived

    def ingest_batch(self, turns: List[List[dict]]) -> int:
        recorded = 0
        for events in turns:
            if events:
                self.ingest_turn(events)
                recorded += 1
        return recorded

    def _append(self, bucket: List[float], value: float) -> None:
        bucket.append(value)
        overflow = len(bucket) - self.max_samples
        if overflow > 0:
            del bucket[:overflow]

    def _series_summary(self, values: List[float]) -> Dict[str, Any]:
        if not values:
            return {"count": 0, "p50_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None}
        return {
            "count": len(values),
            "p50_ms": _percentile(values, 50),
            "p95_ms": _percentile(values, 95),
            "min_ms": round(min(values), 1),
            "max_ms": round(max(values), 1),
        }

    def slo_summary(self) -> Dict[str, Any]:
        with self._lock:
            mic = self._series_summary(self._mic_to_first_audio)
            speech = self._series_summary(self._speech_stop_to_response)
            barge = self._series_summary(self._barge_in)
            jarvis_mic = self._series_summary(self._jarvis_mic_to_first_audio)
            ingest_count = self._ingest_count
            jarvis_ingest = self._jarvis_ingest_count

        mic_p50 = mic["p50_ms"]
        mic_p95 = mic["p95_ms"]
        mic_ok = (
            mic["count"] > 0
            and mic_p50 is not None
            and mic_p95 is not None
            and mic_p50 <= self.mic_p50_target_ms
            and mic_p95 <= self.mic_p95_target_ms
        )

        jarvis_p95 = jarvis_mic["p95_ms"]
        jarvis_ok = (
            jarvis_mic["count"] > 0
            and jarvis_p95 is not None
            and jarvis_p95 <= self.mic_p95_target_ms
        )

        return {
            "ingest_count": ingest_count,
            "healthy": mic_ok,
            "targets": {
                "mic_to_first_audio_p50_ms": self.mic_p50_target_ms,
                "mic_to_first_audio_p95_ms": self.mic_p95_target_ms,
            },
            "mic_to_first_audio": mic,
            "speech_stop_to_response": speech,
            "barge_in": barge,
            "cmd_jarvis": {
                "ingest_count": jarvis_ingest,
                "healthy": jarvis_ok if jarvis_mic["count"] > 0 else None,
                "mic_to_first_audio": jarvis_mic,
                "target_p95_ms": self.mic_p95_target_ms,
            },
        }


_store: Optional[VoiceMetricsStore] = None


def get_voice_metrics_store() -> VoiceMetricsStore:
    global _store
    if _store is None:
        max_samples = int(os.getenv("VOICE_METRICS_MAX_SAMPLES", "5000"))
        p50 = float(os.getenv("VOICE_SLO_MIC_FIRST_AUDIO_P50_MS", "1200"))
        p95 = float(os.getenv("VOICE_SLO_MIC_FIRST_AUDIO_P95_MS", "2500"))
        _store = VoiceMetricsStore(max_samples=max_samples, mic_p50_target_ms=p50, mic_p95_target_ms=p95)
    return _store
