"""Mycelia swarm registry + MemPalace search bridge tests (Phase 8)."""

from unittest.mock import patch

from services.home.cmd_center import build_cmd_center
from services.home.swarm_registry import (
    SWARM_DOCS,
    SWARM_TASKS,
    is_swarm_task_id,
    resolve_swarm_docs,
    swarm_task_ids,
)
from services.mempalace.bridge import (
    _parse_search_output,
    fetch_mempalace_globe_graph,
)


SAMPLE_SEARCH = """
============================================================
  Results for: "memory"
============================================================

  [1] OpenClaw / general
      Source: SKILL.md
      Match:  cosine=0.56  bm25=0.279

      Memory is living substrate that agents grow through.

  ────────────────────────────────────────────────────────
  [2] Odyssey / notes
      Source: brief.md
      Match:  cosine=0.52  bm25=0.257

      Morning brief links into the fruit ledger.
"""


def test_registry_covers_seeded_swarm_task_ids():
    ids = swarm_task_ids()
    assert "swarm-t-forager" in ids
    assert "swarm-t-sporangium-am" in ids
    assert len(SWARM_TASKS) >= 13
    assert len(SWARM_DOCS) == 3


def test_registry_rejects_coincidental_swarm_name():
    assert is_swarm_task_id("swarm-t-forager") is True
    # Prefix + title look swarm-like but not registered.
    assert is_swarm_task_id("swarm-imposter") is False
    assert is_swarm_task_id("my-swarm-helper") is False
    assert is_swarm_task_id("swarm-t-forager-extra") is False


def test_build_cmd_center_registry_swarm_detection():
    tasks = [
        {"id": "swarm-t-forager", "name": "Swarm · Pipeline scan", "status": "active"},
        {"id": "swarm-t-rhizo", "name": "Swarm · Research", "status": "paused"},
    ]
    docs = [
        {"id": "d-ledger", "title": "Fruit Ledger — Odysseus Swarm", "archived": False},
        {"id": "d-board", "title": "Swarm Substrate (Blackboard)", "archived": False},
    ]
    runs = [
        {
            "id": "r1",
            "task_id": "swarm-t-forager",
            "task_name": "Swarm · Pipeline scan",
            "status": "success",
            "result": "staged one package",
            "finished_at": "2026-07-31T12:00:00+00:00",
        }
    ]
    data = build_cmd_center(
        notes=[],
        documents=docs,
        tasks=tasks,
        sessions=[],
        task_runs=runs,
        include_globe=False,
    )
    mycelia = next(b for b in data["branch_health"] if b["id"] == "mycelia")
    assert mycelia["count"] == 2
    assert mycelia["state"] == "alive"

    cmd_ids = {c["id"] for c in data["commands"] if c.get("group") == "Mycelia"}
    assert "myc_forager" in cmd_ids
    assert "myc_rhizo" in cmd_ids
    assert "myc_fruit" in cmd_ids
    assert "myc_board" in cmd_ids

    swarm_rows = [a for a in data["agent_activity"] if a.get("swarm")]
    assert len(swarm_rows) == 1
    assert swarm_rows[0]["target_id"] == "swarm-t-forager"


def test_build_cmd_center_coincidental_name_not_registered():
    """Negative case: swarm-like id/title must NOT classify as swarm activity."""
    tasks = [
        {
            "id": "swarm-imposter",
            "name": "Swarm Doctrine Helper",
            "status": "active",
        },
        {
            "id": "daily-swarm-scan",
            "name": "Nightly swarm health",
            "status": "active",
        },
    ]
    docs = [
        # Title contains "swarm" but is not a registered doctrine/ledger/board doc
        # unless it matches registry title_keys — "random swarm notes" has "swarm"
        # but not "doctrine", so doctrine must not resolve.
        {"id": "d-noise", "title": "Random swarm notes", "archived": False},
    ]
    runs = [
        {
            "id": "r-fake",
            "task_id": "swarm-imposter",
            "task_name": "Swarm Doctrine Helper",
            "status": "success",
            "result": "not a real swarm agent",
            "finished_at": "2026-07-31T12:00:00+00:00",
        }
    ]
    data = build_cmd_center(
        notes=[],
        documents=docs,
        tasks=tasks,
        sessions=[],
        task_runs=runs,
        include_globe=False,
    )
    assert all(b["id"] != "mycelia" for b in data["branch_health"])
    assert all(not a.get("swarm") for a in data["agent_activity"])
    myc_cmds = [c for c in data["commands"] if c.get("group") == "Mycelia"]
    # CEO brief is always present; no swarm dispatch/open_doc buttons.
    assert {c["id"] for c in myc_cmds} == {"myc_ceo"}
    assert resolve_swarm_docs(docs) == {}


def test_parse_search_output_extracts_content_hits():
    hits = _parse_search_output(SAMPLE_SEARCH)
    assert len(hits) == 2
    assert hits[0]["wing"] == "OpenClaw"
    assert hits[0]["room"] == "general"
    assert hits[0]["source"] == "SKILL.md"
    assert "substrate" in hits[0]["snippet"].lower()
    assert hits[1]["wing"] == "Odyssey"


def test_fetch_mempalace_globe_graph_prefers_search(monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLED", "true")
    monkeypatch.setenv("MEMPALACE_PALACE_PATH", r"C:\fake\MemPalace")
    monkeypatch.setattr("services.mempalace.bridge.os.path.isdir", lambda _p: True)

    with patch("services.mempalace.bridge._run_search", return_value=SAMPLE_SEARCH):
        with patch("services.mempalace.bridge._run_status") as status_mock:
            nodes, edges, status = fetch_mempalace_globe_graph(force=True)

    assert status == "ok"
    assert any(str(n.get("id") or "").startswith("memory:hit:") for n in nodes)
    assert any("substrate" in str(n.get("summary") or "").lower() for n in nodes)
    assert any(e.get("kind") == "hosts" for e in edges)
    status_mock.assert_not_called()


def test_fetch_mempalace_globe_graph_falls_back_to_status(monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLED", "true")
    monkeypatch.setenv("MEMPALACE_PALACE_PATH", r"C:\fake\MemPalace")
    monkeypatch.setattr("services.mempalace.bridge.os.path.isdir", lambda _p: True)

    sample_status = """
  WING: Alpha
    ROOM: general                50 drawers
"""
    with patch("services.mempalace.bridge._run_search", side_effect=RuntimeError("search down")):
        with patch("services.mempalace.bridge._run_status", return_value=sample_status):
            nodes, edges, status = fetch_mempalace_globe_graph(force=True)

    assert status == "ok"
    assert any(n["kind"] == "memory" for n in nodes)
    assert any(e.get("kind") == "hosts" for e in edges)
