"""GET /api/sessions/recent — welcome-screen Jump Back In feed."""

import sys
import tempfile
import types
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from unittest.mock import MagicMock

import core.database as cdb
from core.database import ChatMessage, Session as DbSession

_TMPDB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_ENGINE = create_engine(
    f"sqlite:///{_TMPDB.name}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
cdb.Base.metadata.create_all(_ENGINE)
_TS = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


def _stub_multipart_if_missing(monkeypatch):
    try:
        import python_multipart  # noqa: F401
        return
    except ImportError:
        pass
    stub = types.ModuleType("python_multipart")
    stub.__version__ = "0.0.20"
    monkeypatch.setitem(sys.modules, "python_multipart", stub)


def _recent_endpoint(monkeypatch):
    import routes.session_routes as sr

    _stub_multipart_if_missing(monkeypatch)
    monkeypatch.setattr(sr, "SessionLocal", _TS)
    monkeypatch.setattr(sr, "effective_user", lambda request: "alice")
    router = sr.setup_session_routes(MagicMock(), {})
    return next(
        r.endpoint
        for r in router.routes
        if getattr(r, "path", "") == "/api/sessions/recent"
        and "GET" in getattr(r, "methods", set())
    )


def test_recent_sessions_returns_owner_chats_sorted_with_preview(monkeypatch):
    endpoint = _recent_endpoint(monkeypatch)
    now = datetime.utcnow()
    older_id = str(uuid.uuid4())
    newer_id = str(uuid.uuid4())
    hidden_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())

    db = _TS()
    try:
        db.query(ChatMessage).delete()
        db.query(DbSession).delete()
        db.add_all(
            [
                DbSession(
                    id=older_id,
                    owner="alice",
                    name="Older chat",
                    endpoint_url="http://localhost",
                    model="gpt-4",
                    archived=False,
                    message_count=1,
                    last_message_at=now - timedelta(hours=2),
                ),
                DbSession(
                    id=newer_id,
                    owner="alice",
                    name="Newer chat",
                    endpoint_url="http://localhost",
                    model="gpt-4",
                    archived=False,
                    message_count=1,
                    last_message_at=now - timedelta(minutes=5),
                ),
                DbSession(
                    id=hidden_id,
                    owner="alice",
                    name="Incognito",
                    endpoint_url="http://localhost",
                    model="gpt-4",
                    archived=False,
                    message_count=1,
                    last_message_at=now,
                ),
                DbSession(
                    id=other_id,
                    owner="bob",
                    name="Bob chat",
                    endpoint_url="http://localhost",
                    model="gpt-4",
                    archived=False,
                    message_count=1,
                    last_message_at=now,
                ),
            ]
        )
        db.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=newer_id,
                role="assistant",
                content="Latest reply preview text",
                timestamp=now - timedelta(minutes=5),
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=older_id,
                role="user",
                content="Older message",
                timestamp=now - timedelta(hours=2),
            )
        )
        db.commit()
    finally:
        db.close()

    result = endpoint(request=MagicMock(), limit=5)
    ids = [s["id"] for s in result["sessions"]]
    assert ids == [newer_id, older_id]
    assert result["sessions"][0]["title"] == "Newer chat"
    assert "Latest reply preview" in result["sessions"][0]["preview"]
    assert hidden_id not in ids
    assert other_id not in ids


def test_recent_sessions_respects_limit(monkeypatch):
    endpoint = _recent_endpoint(monkeypatch)
    now = datetime.utcnow()
    db = _TS()
    try:
        db.query(ChatMessage).delete()
        db.query(DbSession).delete()
        for i in range(4):
            sid = str(uuid.uuid4())
            db.add(
                DbSession(
                    id=sid,
                    owner="alice",
                    name=f"Chat {i}",
                    endpoint_url="http://localhost",
                    model="gpt-4",
                    archived=False,
                    message_count=1,
                    last_message_at=now - timedelta(minutes=i),
                )
            )
            db.add(
                ChatMessage(
                    id=str(uuid.uuid4()),
                    session_id=sid,
                    role="user",
                    content=f"Message {i}",
                    timestamp=now - timedelta(minutes=i),
                )
            )
        db.commit()
    finally:
        db.close()

    result = endpoint(request=MagicMock(), limit=2)
    assert result["count"] == 2
    assert len(result["sessions"]) == 2
