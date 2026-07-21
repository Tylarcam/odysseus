"""Golden voice turn traces — event order contracts for CI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.voice.metrics import latencies_from_turn_events
from services.voice.trace_validate import validate_forbidden_after, validate_ordered_steps

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "voice"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture_file",
    [
        "golden_realtime_turn.json",
        "golden_ptt_turn.json",
        "golden_barge_in_turn.json",
    ],
)
def test_golden_trace_sample_passes(fixture_file: str):
    spec = _load(fixture_file)
    events = spec["sample_events"]
    errors = validate_ordered_steps(events, spec["steps"])
    assert errors == [], f"{spec['name']}: {errors}"
    forbidden = validate_forbidden_after(events, spec.get("forbidden_after", {}))
    assert forbidden == [], f"{spec['name']} forbidden: {forbidden}"


def test_golden_realtime_mic_to_first_audio_slo():
    spec = _load("golden_realtime_turn.json")
    derived = latencies_from_turn_events(spec["sample_events"])
    assert derived["mic_to_first_audio_ms"] == 3980  # 4100 - 120
    assert derived["speech_stop_to_response_ms"] == 400  # 3600 - 3200


def test_broken_trace_detects_missing_commit():
    spec = _load("golden_realtime_turn.json")
    broken = [e for e in spec["sample_events"] if e["event"] != "turn.committed"]
    errors = validate_ordered_steps(broken, spec["steps"])
    assert any("turn.committed" in err or "input_audio_buffer.committed" in err for err in errors)


def test_forbidden_after_detects_stuck_loop():
    spec = _load("golden_realtime_turn.json")
    events = spec["sample_events"] + [{"event": "loop.stuck", "elapsedMs": 9500}]
    errors = validate_forbidden_after(events, spec["forbidden_after"])
    assert errors
