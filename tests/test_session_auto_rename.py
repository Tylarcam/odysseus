"""Tidy-options Rename recaps placeholder-named chats and retitles them."""
import json
import sys
import tempfile
import types
import uuid
from unittest.mock import MagicMock

import core.database as cdb
from core.database import ChatMessage as DbMsg
from core.database import Session as DbSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

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


def _add_session(db, *, owner, name, messages):
    sid = str(uuid.uuid4())
    db.add(DbSession(
        id=sid, owner=owner, name=name,
        endpoint_url="http://localhost", model="gpt-4", archived=False,
    ))
    for i, (role, content) in enumerate(messages):
        db.add(DbMsg(
            id=str(uuid.uuid4()), session_id=sid, role=role, content=content,
        ))
    return sid


def test_auto_rename_retitles_placeholder_chats_from_recap(monkeypatch):
    import routes.session_routes as sr

    _stub_multipart_if_missing(monkeypatch)
    monkeypatch.setattr(sr, "SessionLocal", _TS)
    monkeypatch.setattr(sr, "effective_user", lambda request: "alice")

    db = _TS()
    try:
        db.query(DbMsg).delete()
        db.query(DbSession).delete()
        leftover = _add_session(db, owner="alice", name="Chat: leftover", messages=[
            ("user", "Fix the STM32 CW decoder"),
            ("assistant", "Here is the patch for the baud rate."),
        ])
        custom = _add_session(db, owner="alice", name="Grant proposal recap", messages=[
            ("user", "Draft the Vanier letter"),
            ("assistant", "Here is a draft."),
        ])
        _add_session(db, owner="alice", name="Incognito", messages=[
            ("user", "secret ask"),
            ("assistant", "secret answer"),
        ])
        _add_session(db, owner="bob", name="Chat: leftover", messages=[
            ("user", "Bob's bug"),
            ("assistant", "Bob's fix"),
        ])
        empty = _add_session(db, owner="alice", name="Chat: empty", messages=[])
        db.commit()
    finally:
        db.close()

    captured = {}

    def _fake_llm(candidates, messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return json.dumps({"names": {leftover[:8]: "STM32 CW decoder"}})

    monkeypatch.setattr(
        "src.endpoint_resolver.resolve_task_candidates",
        lambda owner=None: [("http://example", "model", {})],
    )
    monkeypatch.setattr("src.llm_core.llm_call_with_fallback", _fake_llm)

    class _SM:
        sessions = {}

    router = sr.setup_session_routes(_SM(), {})
    endpoint = next(
        r.endpoint for r in router.routes
        if getattr(r, "path", "") == "/api/sessions/auto-sort/rename"
        and "POST" in getattr(r, "methods", set())
    )
    result = endpoint(request=MagicMock())
    assert result["status"] == "ok"
    assert result["renamed"] == 1
    assert leftover[:8] in captured["prompt"]
    assert "Fix the STM32 CW decoder" in captured["prompt"]
    assert custom[:8] not in captured["prompt"]
    assert empty[:8] not in captured["prompt"]

    db = _TS()
    try:
        names = {row.id: row.name for row in db.query(DbSession).all()}
    finally:
        db.close()
    assert names[leftover] == "STM32 CW decoder"
    assert names[custom] == "Grant proposal recap"
    assert names[empty] == "Chat: empty"


def _single_rename_endpoint(monkeypatch, session_manager=None):
    import routes.session_routes as sr

    _stub_multipart_if_missing(monkeypatch)
    monkeypatch.setattr(sr, "SessionLocal", _TS)
    monkeypatch.setattr(sr, "effective_user", lambda request: "alice")
    sm = session_manager if session_manager is not None else type("SM", (), {"sessions": {}})()
    router = sr.setup_session_routes(sm, {})
    return next(
        r.endpoint for r in router.routes
        if getattr(r, "path", "") == "/api/session/{sid}/auto-rename"
        and "POST" in getattr(r, "methods", set())
    )


def test_single_auto_rename_retitles_named_chat(monkeypatch):
    db = _TS()
    try:
        db.query(DbMsg).delete()
        db.query(DbSession).delete()
        sid = _add_session(db, owner="alice", name="Grant proposal recap", messages=[
            ("user", "Draft the Vanier letter"),
            ("assistant", "Here is a draft."),
        ])
        db.commit()
    finally:
        db.close()

    def _fake_llm(candidates, messages, **kwargs):
        return json.dumps({"names": {sid[:8]: "Vanier nomination letter"}})

    monkeypatch.setattr(
        "src.endpoint_resolver.resolve_task_candidates",
        lambda owner=None: [("http://example", "model", {})],
    )
    monkeypatch.setattr("src.llm_core.llm_call_with_fallback", _fake_llm)

    endpoint = _single_rename_endpoint(monkeypatch)
    result = endpoint(request=MagicMock(), sid=sid)
    assert result["status"] == "ok"
    assert result["name"] == "Vanier nomination letter"

    db = _TS()
    try:
        row = db.query(DbSession).filter(DbSession.id == sid).one()
        assert row.name == "Vanier nomination letter"
    finally:
        db.close()


def test_single_auto_rename_rejects_incognito(monkeypatch):
    from fastapi import HTTPException

    db = _TS()
    try:
        db.query(DbMsg).delete()
        db.query(DbSession).delete()
        sid = _add_session(db, owner="alice", name="Nobody", messages=[
            ("user", "secret ask"),
            ("assistant", "secret answer"),
        ])
        db.commit()
    finally:
        db.close()

    endpoint = _single_rename_endpoint(monkeypatch)
    try:
        endpoint(request=MagicMock(), sid=sid)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_single_auto_rename_skips_empty_recap(monkeypatch):
    db = _TS()
    try:
        db.query(DbMsg).delete()
        db.query(DbSession).delete()
        sid = _add_session(db, owner="alice", name="Untitled research notes", messages=[])
        db.commit()
    finally:
        db.close()

    endpoint = _single_rename_endpoint(monkeypatch)
    result = endpoint(request=MagicMock(), sid=sid)
    assert result["status"] == "skipped"
    assert "recap" in result["reason"].lower()
