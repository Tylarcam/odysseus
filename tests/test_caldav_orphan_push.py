"""Orphan local events should push onto the primary CalDAV calendar during sync."""

import asyncio
import tempfile
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import CalendarCal, CalendarEvent
from src.caldav_writeback import push_orphan_local_events

_TMPDB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_ENGINE = create_engine(
    f"sqlite:///{_TMPDB.name}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
cdb.Base.metadata.create_all(_ENGINE)
_TS = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _patch_session(monkeypatch):
    monkeypatch.setattr("core.database.SessionLocal", _TS)


def _seed_local_event(owner="tester", summary="Call Stanford IT"):
    local_id = "loc-" + uuid.uuid4().hex[:8]
    caldav_id = "caldav-" + uuid.uuid4().hex[:8]
    db = _TS()
    try:
        db.add(CalendarCal(id=local_id, owner=owner, name="Personal", source="local"))
        db.add(CalendarCal(id=caldav_id, owner=owner, name="Stanford", source="caldav"))
        start = datetime.utcnow() + timedelta(hours=2)
        ev = CalendarEvent(
            uid=str(uuid.uuid4()),
            calendar_id=local_id,
            summary=summary,
            dtstart=start,
            dtend=start + timedelta(hours=1),
            all_day=False,
            is_utc=True,
        )
        db.add(ev)
        db.commit()
        return caldav_id, ev.uid
    finally:
        db.close()


async def test_push_orphan_local_events_moves_and_pushes(monkeypatch):
    caldav_id, ev_uid = _seed_local_event()
    calls = []

    async def _fake_writeback(owner, source, cal_id, ev, *, delete=False):
        calls.append({"cal_id": cal_id, "uid": ev.get("uid"), "delete": delete})
        return {"ok": True, "created": True}

    monkeypatch.setattr("src.caldav_writeback.writeback_event", _fake_writeback)
    result = await push_orphan_local_events("tester")
    assert result["pushed"] == 1
    assert calls == [{"cal_id": caldav_id, "uid": ev_uid, "delete": False}]

    db = _TS()
    try:
        ev = db.query(CalendarEvent).filter(CalendarEvent.uid == ev_uid).first()
        assert ev.calendar_id == caldav_id
    finally:
        db.close()


async def test_push_orphan_local_events_no_caldav_calendar():
    db = _TS()
    try:
        local_id = "loc-" + uuid.uuid4().hex[:8]
        db.add(CalendarCal(id=local_id, owner="solo", name="Personal", source="local"))
        start = datetime.utcnow() + timedelta(hours=1)
        db.add(CalendarEvent(
            uid=str(uuid.uuid4()), calendar_id=local_id, summary="Local only",
            dtstart=start, dtend=start + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()
    result = await push_orphan_local_events("solo")
    assert result["pushed"] == 0
    assert result.get("skipped") == "no caldav calendar"
