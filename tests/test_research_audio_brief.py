"""Tests for deep research audio brief generation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.research import audio_brief as ab


@pytest.fixture
def research_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "deep_research"
    data_dir.mkdir()
    monkeypatch.setattr(ab, "DEEP_RESEARCH_DIR", str(data_dir))
    monkeypatch.setattr(ab, "RESEARCH_AUDIO_DIR", data_dir / "audio")
    return data_dir


def test_chunk_script_respects_tts_limit():
    lines = [f"HOST: Sentence number {i} with some extra words." for i in range(200)]
    script = "\n".join(lines)
    chunks = ab.chunk_script_for_tts(script)
    assert chunks
    assert all(len(c) <= ab._MAX_CHUNK_CHARS for c in chunks)


def test_chunk_script_single_line():
    chunks = ab.chunk_script_for_tts("HOST: Hello\nANALYST: World")
    assert len(chunks) == 1
    assert "HOST" in chunks[0]
    assert "ANALYST" in chunks[0]


def test_parse_host_analyst_dialogue_format():
    script = "HOST: Welcome to the brief.\nANALYST: Here are three findings."
    chunks = ab.chunk_script_for_tts(script)
    assert chunks == [script]
    assert script.count("HOST:") == 1
    assert script.count("ANALYST:") == 1


def test_research_json_path_rejects_invalid(research_env):
    assert ab._research_json_path("../escape") is None


@pytest.mark.asyncio
async def test_generate_audio_brief_ready(research_env):
    session_id = "rp-testaudio001"
    report = "## Findings\nAI safety has three major approaches."
    path = research_env / f"{session_id}.json"
    path.write_text(json.dumps({
        "query": "AI safety?",
        "status": "done",
        "result": report,
        "raw_report": report,
        "owner": "alice",
    }), encoding="utf-8")

    entry = {
        "status": "done",
        "owner": "alice",
        "llm_endpoint": "http://fake/v1/chat/completions",
        "llm_model": "test-model",
        "llm_headers": {},
    }

    fake_audio = b"ID3" + b"\x00" * 100

    tts = MagicMock()
    tts._load_settings.return_value = {
        "tts_enabled": True,
        "tts_provider": "local",
        "tts_model": "tts-1",
        "tts_voice": "alloy",
        "tts_speed": "1",
    }
    tts.available = True
    tts.synthesize.return_value = fake_audio

    with patch.object(ab, "generate_brief_script", new=AsyncMock(return_value="HOST: Hi\nANALYST: There")):
        await ab.generate_audio_brief(session_id, tts, entry)

    data = json.loads(path.read_text(encoding="utf-8"))
    brief = data.get("audio_brief") or {}
    assert brief.get("status") == "ready"
    assert brief.get("chunk_count") == 1
    assert (research_env / "audio" / session_id / "chunk_000.mp3").exists()


@pytest.mark.asyncio
async def test_generate_audio_brief_skips_when_tts_empty(research_env):
    session_id = "rp-testaudio-skip"
    report = "## Findings\nToken arbitrage saves money."
    path = research_env / f"{session_id}.json"
    path.write_text(json.dumps({
        "query": "Token arbitrage?",
        "status": "done",
        "result": report,
        "raw_report": report,
        "owner": "alice",
    }), encoding="utf-8")

    entry = {
        "status": "done",
        "owner": "alice",
        "llm_endpoint": "http://fake/v1/chat/completions",
        "llm_model": "test-model",
        "llm_headers": {},
    }

    tts = MagicMock()
    tts._load_settings.return_value = {
        "tts_enabled": True,
        "tts_provider": "voiceai",
        "tts_model": "tts-1",
        "tts_voice": "alloy",
        "tts_speed": "1",
    }
    tts.available = True
    tts.last_error = "Voice.ai billing required (402 Payment Required)"
    tts.synthesize.return_value = None

    with patch.object(ab, "generate_brief_script", new=AsyncMock(return_value="HOST: Hi\nANALYST: There")):
        await ab.generate_audio_brief(session_id, tts, entry)

    data = json.loads(path.read_text(encoding="utf-8"))
    brief = data.get("audio_brief") or {}
    assert brief.get("status") == "skipped"
    assert "browser voice" in (brief.get("error") or "").lower()
    assert (brief.get("script") or "").startswith("HOST:")
    assert int(brief.get("chunk_count") or 0) == 0


def test_read_audio_chunk(research_env):
    session_id = "rp-testaudio002"
    path = research_env / f"{session_id}.json"
    path.write_text(json.dumps({
        "audio_brief": {
            "status": "ready",
            "chunk_count": 1,
            "mime": "audio/mpeg",
            "ext": "mp3",
        }
    }), encoding="utf-8")
    audio_dir = research_env / "audio" / session_id
    audio_dir.mkdir(parents=True)
    (audio_dir / "chunk_000.mp3").write_bytes(b"ID3fake")

    result = ab.read_audio_chunk(session_id, 0)
    assert result is not None
    data, mime = result
    assert data.startswith(b"ID3")
    assert mime == "audio/mpeg"


def test_delete_audio_brief_files(research_env):
    session_id = "rp-testaudio003"
    audio_dir = research_env / "audio" / session_id
    audio_dir.mkdir(parents=True)
    (audio_dir / "chunk_000.mp3").write_bytes(b"ID3fake")
    ab.delete_audio_brief_files(session_id)
    assert not audio_dir.exists()
