"""manage_calendar must write back to CalDAV the same way HTTP routes do."""

import asyncio
import json
import tempfile
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import CalendarCal
from src import tool_implementations as ti

_TMPDB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_ENGINE = create_engine(
    f"sqlite:///{_TMPDB.name}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
cdb.Base.metadata.create_all(_ENGINE)
_TS = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    monkeypatch.setattr("core.database.SessionLocal", _TS)
    monkeypatch.setattr("src.tool_implementations.SessionLocal", _TS, raising=False)


def _make_cal(source, owner="tester"):
    cid = ("caldav-" if source == "caldav" else "loc-") + uuid.uuid4().hex[:8]
    db = _TS()
    try:
        db.add(CalendarCal(id=cid, owner=owner, name=source.title(), source=source))
        db.commit()
        return cid
    finally:
        db.close()


@pytest.fixture
def writeback_calls(monkeypatch):
    calls = []

    async def _fake(owner, cal, ev_dict, *, delete=False):
        calls.append({
            "owner": owner,
            "source": getattr(cal, "source", None),
            "cal_id": getattr(cal, "id", None),
            "uid": ev_dict.get("uid"),
            "delete": delete,
        })
        return {"ok": True}

    monkeypatch.setattr("routes.calendar_routes.writeback_calendar_event", _fake)
    return calls


async def test_manage_calendar_create_on_caldav_writes_back(writeback_calls):
    cal_id = _make_cal("caldav")
    payload = json.dumps({
        "action": "create_event",
        "summary": "SAR Renew",
        "dtstart": "2026-07-14T12:00:00Z",
        "calendar_href": cal_id,
    })
    res = await ti.do_manage_calendar(payload, owner="tester")
    assert res["exit_code"] == 0
    assert res.get("writeback", {}).get("ok") is True
    assert len(writeback_calls) == 1
    assert writeback_calls[0]["cal_id"] == cal_id
    assert writeback_calls[0]["delete"] is False


async def test_manage_calendar_create_on_local_skips_writeback():
    cal_id = _make_cal("local")
    payload = json.dumps({
        "action": "create_event",
        "summary": "Local only",
        "dtstart": "2026-07-14T12:00:00Z",
        "calendar_href": cal_id,
    })
    res = await ti.do_manage_calendar(payload, owner="tester")
    assert res["exit_code"] == 0
    assert res.get("writeback", {}).get("skipped") == "not a caldav calendar"
