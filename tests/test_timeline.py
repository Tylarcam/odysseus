"""Tests for the /timeline endpoint (Task C)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from tools.unified_memory_api import build_timeline, create_app


def _metadata_payload():
    """3 distinct records keyed by both int id and source filename (duplicate)."""
    base = [
        {
            "article_id": 0,
            "source_filename": "screen_2026-07-07T01-05-00.png",
            "timestamp": "2026-07-07T01:05:00",
            "url": "https://example.com/a",
            "window_title": "Window A",
            "screenpipe_path": "/fake/a.png",
            "transcript_path": "/fake/a.json",
        },
        {
            "article_id": 1,
            "source_filename": "screen_2026-07-07T03-05-00.png",
            "timestamp": "2026-07-07T03:05:00",
            "url": "https://example.com/b",
            "window_title": "Window B",
            "screenpipe_path": "/fake/b.png",
            "transcript_path": "/fake/b.json",
        },
        {
            "article_id": 2,
            "source_filename": "screen_2026-07-07T09-05-00.png",
            "timestamp": "2026-07-07T09:05:00",
            "url": "https://example.com/c",
            "window_title": "Window C",
            "screenpipe_path": "/fake/c.png",
            "transcript_path": "/fake/c.json",
        },
    ]
    payload: dict = {}
    for rec in base:
        payload[str(rec["article_id"])] = rec
        payload[rec["source_filename"]] = rec
    return payload


def test_build_timeline_filters_and_sorts_ascending(tmp_path):
    metadata_path = tmp_path / "tiles_metadata.json"
    metadata_path.write_text(json.dumps(_metadata_payload()), encoding="utf-8")

    from_dt = datetime(2026, 7, 7, 2, 0, 0)
    to_dt = datetime(2026, 7, 7, 8, 0, 0)

    result = build_timeline(from_dt=from_dt, to_dt=to_dt, limit=100, metadata_path=metadata_path)

    assert result["count"] == 1
    assert result["events"][0]["window_title"] == "Window B"
    # Ascending order check (single item, but verify structure).
    assert result["events"][0]["article_id"] == 1
    assert result["events"][0]["type"] == "screen"
    assert result["from"] == from_dt.isoformat()
    assert result["to"] == to_dt.isoformat()


def test_build_timeline_no_double_counting(tmp_path):
    """Filename-keyed duplicate entries must NOT inflate the event count."""
    metadata_path = tmp_path / "tiles_metadata.json"
    metadata_path.write_text(json.dumps(_metadata_payload()), encoding="utf-8")

    from_dt = datetime(2026, 7, 7, 0, 0, 0)
    to_dt = datetime(2026, 7, 7, 23, 59, 59)

    result = build_timeline(from_dt=from_dt, to_dt=to_dt, limit=100, metadata_path=metadata_path)

    assert result["count"] == 3  # not 6
    titles = [e["window_title"] for e in result["events"]]
    assert sorted(titles) == ["Window A", "Window B", "Window C"]


def test_build_timeline_limit_caps_results(tmp_path):
    metadata_path = tmp_path / "tiles_metadata.json"
    metadata_path.write_text(json.dumps(_metadata_payload()), encoding="utf-8")

    from_dt = datetime(2026, 7, 7, 0, 0, 0)
    to_dt = datetime(2026, 7, 7, 23, 59, 59)

    result = build_timeline(from_dt=from_dt, to_dt=to_dt, limit=2, metadata_path=metadata_path)

    assert result["count"] == 2
    # Ascending: earliest two first.
    assert result["events"][0]["window_title"] == "Window A"
    assert result["events"][1]["window_title"] == "Window B"


def test_build_timeline_defaults_to_last_24h(tmp_path):
    metadata_path = tmp_path / "tiles_metadata.json"
    metadata_path.write_text(json.dumps(_metadata_payload()), encoding="utf-8")

    now = datetime.now()
    result = build_timeline(metadata_path=metadata_path)

    expected_from = now - timedelta(hours=24)
    # Defaults applied (parsed back).
    assert datetime.fromisoformat(result["to"]) - datetime.fromisoformat(result["from"]) == timedelta(hours=24)
    assert datetime.fromisoformat(result["from"]) >= expected_from - timedelta(seconds=5)


def test_timeline_route(monkeypatch, tmp_path):
    metadata_path = tmp_path / "tiles_metadata.json"
    metadata_path.write_text(json.dumps(_metadata_payload()), encoding="utf-8")

    monkeypatch.setattr(
        "tools.unified_memory_api.resolve_path",
        lambda key, default="", env=None: metadata_path,
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    resp = client.get(
        "/timeline",
        params={"from": "2026-07-07T00:00:00", "to": "2026-07-07T23:59:59", "limit": "2"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["events"][0]["window_title"] == "Window A"
    assert body["events"][1]["window_title"] == "Window B"
    # No double counting via the route either.
    resp_all = client.get(
        "/timeline",
        params={"from": "2026-07-07T00:00:00", "to": "2026-07-07T23:59:59"},
    )
    assert resp_all.json()["count"] == 3


def test_timeline_route_rejects_unparseable_datetimes(monkeypatch, tmp_path):
    metadata_path = tmp_path / "tiles_metadata.json"
    metadata_path.write_text(json.dumps(_metadata_payload()), encoding="utf-8")

    monkeypatch.setattr(
        "tools.unified_memory_api.resolve_path",
        lambda key, default="", env=None: metadata_path,
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    assert client.get("/timeline", params={"from": "not-a-date"}).status_code == 400
    assert client.get("/timeline", params={"to": "2026-13-99"}).status_code == 400
