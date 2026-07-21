"""Tests for Deep Research visual report hero image layout and generation."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from src.visual_report import generate_visual_report


def test_hero_rq_caption_uses_raw_query():
    raw = "Find this paper and compare with similar ideas https://x.com/example"
    synthesized_report = "# Synthesized Report Title\n\nBody text."

    html = generate_visual_report(
        raw,
        synthesized_report,
        sources=[],
        stats={},
        session_id="rp-rq-test",
    )
    soup = BeautifulSoup(html, "html.parser")

    rq = soup.select_one(".hero-rq")
    assert rq is not None
    assert raw in rq.get_text()
    assert "Synthesized Report Title" not in rq.get_text()
    assert soup.select_one(".hero h1") is None


def test_hero_ai_image_preferred_over_og():
    og_url = "https://example.com/og.png"
    ai_url = "/api/generated-image/abc123def456.png"

    html = generate_visual_report(
        "quantum computing trends",
        "## Report\n\nContent.",
        sources=[{"url": "https://example.com", "title": "Ex", "image": og_url}],
        stats={},
        session_id="rp-ai-hero",
        hero_image_url=ai_url,
        hero_image_status="done",
    )
    soup = BeautifulSoup(html, "html.parser")

    hero_img = soup.select_one(".hero-image-ai img")
    assert hero_img is not None
    assert hero_img["src"] == ai_url

    # OG image stays in the spare pool (not used as hero when AI URL is set).
    assert og_url in html
    assert soup.select_one(".hero-image-ai")["data-hero-ai"] == "1"


def test_hero_gradient_until_image_gen():
    og_url = "https://example.com/hero.png"

    html = generate_visual_report(
        "fallback query",
        "## Report\n\nContent.",
        sources=[{"url": "https://example.com", "title": "Ex", "image": og_url}],
        stats={},
        session_id="rp-gradient-fallback",
    )
    soup = BeautifulSoup(html, "html.parser")

    assert soup.select_one(".hero-placeholder") is not None
    assert soup.select_one(".hero-image img") is None
    assert "#1d3557" in html
    assert "#f4a261" in html
    assert "#e76f51" in html
    assert og_url in html


def test_hero_placeholder_when_no_images():
    html = generate_visual_report(
        "empty visuals query",
        "## Report\n\nContent.",
        sources=[],
        stats={},
        session_id="rp-placeholder",
        hero_image_status="pending",
    )
    soup = BeautifulSoup(html, "html.parser")

    assert soup.select_one(".hero-placeholder") is not None
    rq = soup.select_one(".hero-rq")
    assert rq is not None
    assert "empty visuals query" in rq.get_text()


@pytest.fixture
def _redirect_research_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "routes.research_routes.DEEP_RESEARCH_DIR",
        str(tmp_path / "data" / "deep_research"),
    )
    monkeypatch.setattr(
        "services.research.hero_image.DEEP_RESEARCH_DIR",
        str(tmp_path / "data" / "deep_research"),
    )


def _write_research(data_dir, session_id: str, **data):
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{session_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_kickoff_hero_image_patches_json(tmp_path, monkeypatch, _redirect_research_dir):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    session_id = "rp-hero-gen"
    _write_research(
        data_dir,
        session_id,
        owner="alice",
        status="done",
        query="test query",
        raw_report="# Title\n\nBody",
        hero_image_status="pending",
    )

    entry = {"status": "done", "owner": "alice", "query": "test query"}

    async def _fake_generate(content, session_id=None, owner=None):
        return {
            "image_url": "/api/generated-image/deadbeef.png",
            "image_model": "Z-Image-Turbo",
        }

    with patch("src.ai_interaction.do_generate_image", new=AsyncMock(side_effect=_fake_generate)):
        with patch("services.research.hero_image.image_gen_enabled", return_value=True):
            from services.research.hero_image import generate_and_persist_hero_image

            asyncio.run(generate_and_persist_hero_image(session_id, entry))

    data = json.loads((data_dir / f"{session_id}.json").read_text(encoding="utf-8"))
    assert data["hero_image_status"] == "done"
    assert data["hero_image_url"] == "/api/generated-image/deadbeef.png"
    assert data.get("hero_image_prompt")


def test_kickoff_skipped_when_disabled(tmp_path, monkeypatch, _redirect_research_dir):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    session_id = "rp-hero-skip"
    _write_research(
        data_dir,
        session_id,
        owner="alice",
        status="done",
        query="test",
        hero_image_status="pending",
    )

    entry = {"status": "done", "owner": "alice", "query": "test"}

    with patch("src.ai_interaction.do_generate_image", new=AsyncMock()) as mock_gen:
        with patch("services.research.hero_image.image_gen_enabled", return_value=False):
            from services.research.hero_image import generate_and_persist_hero_image

            asyncio.run(generate_and_persist_hero_image(session_id, entry))

    mock_gen.assert_not_called()
    data = json.loads((data_dir / f"{session_id}.json").read_text(encoding="utf-8"))
    assert data["hero_image_status"] == "skipped"


def test_build_hero_prompt_uses_synthesized_title():
    from services.research.hero_image import build_hero_prompt

    prompt = build_hero_prompt(
        "raw user query about quantum",
        category="science",
        synthesized_title="Quantum Computing Landscape 2026",
    )
    assert "Quantum Computing Landscape 2026" in prompt
    assert "science" in prompt.lower()
    assert "no text" in prompt.lower()


def test_get_hero_image_meta_reads_json(tmp_path, monkeypatch, _redirect_research_dir):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    session_id = "rp-status"
    _write_research(
        data_dir,
        session_id,
        owner="alice",
        hero_image_status="done",
        hero_image_url="/api/generated-image/xyz.png",
        hero_image_prompt="test prompt",
    )

    from services.research.hero_image import get_hero_image_meta

    meta = get_hero_image_meta(session_id)
    assert meta["status"] == "done"
    assert meta["url"] == "/api/generated-image/xyz.png"
    assert meta["prompt"] == "test prompt"


def test_kickoff_hero_image_force_bypasses_done(tmp_path, monkeypatch, _redirect_research_dir):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    session_id = "rp-regen"
    _write_research(
        data_dir,
        session_id,
        owner="alice",
        status="done",
        query="regen test",
        hero_image_status="done",
        hero_image_url="/api/generated-image/old.png",
    )

    entry = {"status": "done", "owner": "alice", "query": "regen test"}

    async def _fake_generate(content, session_id=None, owner=None):
        return {"image_url": "/api/generated-image/new.png", "image_model": "test"}

    with patch("src.ai_interaction.do_generate_image", new=AsyncMock(side_effect=_fake_generate)):
        with patch("services.research.hero_image.image_gen_enabled", return_value=True):
            from services.research.hero_image import generate_and_persist_hero_image

            asyncio.run(generate_and_persist_hero_image(session_id, entry, force=True))

    data = json.loads((data_dir / f"{session_id}.json").read_text(encoding="utf-8"))
    assert data["hero_image_status"] == "done"
    assert data["hero_image_url"] == "/api/generated-image/new.png"


def test_research_routes_declare_hero_endpoints():
    from pathlib import Path

    body = Path("routes/research_routes.py").read_text(encoding="utf-8")
    assert '"/api/research/{session_id}/regenerate-hero"' in body
    assert '"/api/research/{session_id}/hero-image/status"' in body


def test_generation_skipped_when_already_in_flight(tmp_path, monkeypatch, _redirect_research_dir):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    session_id = "rp-inflight"
    import time

    _write_research(
        data_dir,
        session_id,
        owner="alice",
        status="done",
        query="test",
        hero_image_status="pending",
        hero_image_started_at=time.time(),
    )

    entry = {"status": "done", "owner": "alice", "query": "test"}

    with patch("src.ai_interaction.do_generate_image", new=AsyncMock()) as mock_gen:
        with patch("services.research.hero_image.image_gen_enabled", return_value=True):
            from services.research.hero_image import generate_and_persist_hero_image

            asyncio.run(generate_and_persist_hero_image(session_id, entry))

    mock_gen.assert_not_called()
