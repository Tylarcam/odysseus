"""MemPalace bridge tests."""

from unittest.mock import patch

from services.mempalace.bridge import (
    _parse_status_output,
    fetch_mempalace_globe_graph,
    mempalace_enabled,
)


SAMPLE_STATUS = """
=======================================================
  MemPalace Status — 100 drawers
=======================================================

  WING: Alpha
    ROOM: general                50 drawers
    ROOM: technical              20 drawers

  WING: Beta
    ROOM: docs                   30 drawers
"""


def test_parse_status_output_extracts_wings_and_rooms():
    wings = _parse_status_output(SAMPLE_STATUS)
    assert len(wings) == 2
    assert wings[0]["name"] == "Alpha"
    assert wings[0]["rooms"][0]["name"] == "general"
    assert wings[0]["rooms"][0]["drawers"] == 50


def test_fetch_mempalace_globe_graph_unavailable_when_disabled(monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLED", "false")
    nodes, edges, status = fetch_mempalace_globe_graph(force=True)
    assert nodes == []
    assert edges == []
    assert status == "disabled"


def test_fetch_mempalace_globe_graph_parses_status(monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLED", "true")
    monkeypatch.setenv("MEMPALACE_PALACE_PATH", r"C:\fake\MemPalace")
    monkeypatch.setattr("services.mempalace.bridge.os.path.isdir", lambda _p: True)

    with patch("services.mempalace.bridge._run_status", return_value=SAMPLE_STATUS):
        nodes, edges, status = fetch_mempalace_globe_graph(force=True)

    assert status == "ok"
    assert any(n["kind"] == "memory" for n in nodes)
    assert any(n["tone"] == "memory" for n in nodes)
    assert any(e["kind"] == "tunnel" for e in edges)


def test_fetch_mempalace_globe_graph_graceful_on_subprocess_error(monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLED", "true")
    monkeypatch.setenv("MEMPALACE_PALACE_PATH", r"C:\fake\MemPalace")
    monkeypatch.setattr("services.mempalace.bridge.os.path.isdir", lambda _p: True)

    with patch("services.mempalace.bridge._run_status", side_effect=RuntimeError("boom")):
        nodes, edges, status = fetch_mempalace_globe_graph(force=True)

    assert nodes == []
    assert edges == []
    assert status == "unavailable"


def test_mempalace_enabled_respects_env(monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLED", "false")
    assert mempalace_enabled() is False
