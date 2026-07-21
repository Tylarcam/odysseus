"""Tests for the document library "Listen" audio brief pipeline."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.documents import audio_brief as dab


@pytest.fixture
def brief_env(tmp_path, monkeypatch):
    root = tmp_path / "doc_audio_briefs"
    monkeypatch.setattr(dab, "DOC_AUDIO_BRIEF_DIR", str(root))
    return root


def test_state_path_rejects_invalid(brief_env):
    assert dab._state_path("../escape") is None
    assert dab._state_path("a/b") is None
    assert dab._state_path("") is None


def test_state_roundtrip(brief_env):
    dab._write_brief_state("doc-1", {"status": "generating", "script": "hi"})
    state = dab.get_brief_state("doc-1")
    assert state["status"] == "generating"
    assert state["script"] == "hi"


def test_content_hash_stability():
    assert dab.content_hash("abc") == dab.content_hash("abc")
    assert dab.content_hash("abc") != dab.content_hash("abd")


@pytest.mark.asyncio
async def test_generate_ready_via_open_notebook(brief_env, monkeypatch):
    fake_client = AsyncMock()
    fake_client.generate_brief_audio = AsyncMock(
        return_value=(b"ID3" + b"\x00" * 50, "episode:abc")
    )

    import services.open_notebook as on
    monkeypatch.setattr(on, "open_notebook_configured", lambda: True)
    monkeypatch.setattr(on, "OpenNotebookClient", lambda *a, **k: fake_client)

    with patch.object(dab, "_resolve_llm", return_value=("http://fake", "m", {})), \
         patch.object(dab, "generate_ceo_brief", new=AsyncMock(return_value="The brief.")):
        await dab.generate_doc_audio_brief("doc-ready", "Title", "Some content")

    state = dab.get_brief_state("doc-ready")
    assert state["status"] == "ready"
    assert state["chunk_count"] == 1
    assert state["script"] == "The brief."
    assert state["episode_id"] == "episode:abc"

    result = dab.read_brief_audio("doc-ready", 0)
    assert result is not None
    data, mime = result
    assert data.startswith(b"ID3")
    assert mime == "audio/mpeg"


@pytest.mark.asyncio
async def test_generate_skipped_when_open_notebook_unconfigured(brief_env, monkeypatch):
    import services.open_notebook as on
    monkeypatch.setattr(on, "open_notebook_configured", lambda: False)

    with patch.object(dab, "_resolve_llm", return_value=("http://fake", "m", {})), \
         patch.object(dab, "generate_ceo_brief", new=AsyncMock(return_value="The brief.")):
        await dab.generate_doc_audio_brief("doc-skip", "Title", "Some content")

    state = dab.get_brief_state("doc-skip")
    assert state["status"] == "skipped"
    assert state["script"] == "The brief."
    assert dab.read_brief_audio("doc-skip", 0) is None


@pytest.mark.asyncio
async def test_generate_skipped_when_open_notebook_fails(brief_env, monkeypatch):
    from services.open_notebook import OpenNotebookError

    fake_client = AsyncMock()
    fake_client.generate_brief_audio = AsyncMock(
        side_effect=OpenNotebookError("boom")
    )

    import services.open_notebook as on
    monkeypatch.setattr(on, "open_notebook_configured", lambda: True)
    monkeypatch.setattr(on, "OpenNotebookClient", lambda *a, **k: fake_client)

    with patch.object(dab, "_resolve_llm", return_value=("http://fake", "m", {})), \
         patch.object(dab, "generate_ceo_brief", new=AsyncMock(return_value="The brief.")):
        await dab.generate_doc_audio_brief("doc-onfail", "Title", "Some content")

    state = dab.get_brief_state("doc-onfail")
    assert state["status"] == "skipped"
    assert "boom" in (state.get("error") or "")
    # Brief text survives so the browser voice can still read it.
    assert state["script"] == "The brief."


@pytest.mark.asyncio
async def test_generate_failed_without_llm(brief_env):
    with patch.object(dab, "_resolve_llm", return_value=("", "", {})):
        await dab.generate_doc_audio_brief("doc-nollm", "Title", "Some content")
    state = dab.get_brief_state("doc-nollm")
    assert state["status"] == "failed"


@pytest.mark.asyncio
async def test_generate_failed_on_empty_content(brief_env):
    await dab.generate_doc_audio_brief("doc-empty", "Title", "   ")
    assert dab.get_brief_state("doc-empty")["status"] == "failed"


def test_kickoff_reuses_fresh_state(brief_env, monkeypatch):
    content = "unchanged content"
    dab._write_brief_state("doc-reuse", {
        "status": "ready",
        "chunk_count": 1,
        "content_hash": dab.content_hash(content),
    })
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(dab, "generate_doc_audio_brief", _boom)
    state = dab.kickoff_doc_audio_brief("doc-reuse", "T", content)
    assert state["status"] == "ready"
    assert called["n"] == 0


def test_kickoff_regenerates_on_content_change(brief_env, monkeypatch):
    dab._write_brief_state("doc-stale", {
        "status": "ready",
        "chunk_count": 1,
        "content_hash": dab.content_hash("old content"),
    })
    ran = {"n": 0}

    async def _fake(doc_id, title, content, owner=""):
        ran["n"] += 1
        dab._write_brief_state(doc_id, {"status": "ready"})

    monkeypatch.setattr(dab, "generate_doc_audio_brief", _fake)
    state = dab.kickoff_doc_audio_brief("doc-stale", "T", "new content")
    assert ran["n"] == 1


def test_delete_brief(brief_env):
    dab._write_brief_state("doc-del", {"status": "ready", "chunk_count": 1,
                                       "mime": "audio/mpeg", "ext": "mp3"})
    audio_dir = dab._audio_dir("doc-del")
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "chunk_000.mp3").write_bytes(b"ID3x")
    dab.delete_brief("doc-del")
    assert dab.get_brief_state("doc-del") == {}
    assert not audio_dir.exists()


def test_read_brief_audio_bounds(brief_env):
    dab._write_brief_state("doc-bounds", {"status": "ready", "chunk_count": 1,
                                          "mime": "audio/mpeg", "ext": "mp3"})
    audio_dir = dab._audio_dir("doc-bounds")
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "chunk_000.mp3").write_bytes(b"ID3x")
    assert dab.read_brief_audio("doc-bounds", 0) is not None
    assert dab.read_brief_audio("doc-bounds", 1) is None
    assert dab.read_brief_audio("doc-bounds", -1) is None
