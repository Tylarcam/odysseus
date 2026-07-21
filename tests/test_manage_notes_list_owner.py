"""manage_notes list must not filter to owner=='' in single-user mode."""

import asyncio
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

from src import tool_implementations


class _OwnerEq:
    """Minimal stand-in for SQLAlchemy `Model.owner == user` binary expressions."""

    def __init__(self, owner: str):
        self.left = SimpleNamespace(key="owner")
        self.right = SimpleNamespace(value=owner)


class _ListQuery:
    def __init__(self, notes):
        self.notes = notes
        self.owner_filter = None

    def filter(self, *args, **kwargs):
        # SQLAlchemy emits binary expressions; capture owner equality.
        for arg in args:
            left = getattr(arg, "left", None)
            right = getattr(arg, "right", None)
            key = getattr(left, "key", None) or getattr(left, "name", None)
            if key == "owner" and right is not None:
                val = getattr(right, "value", None)
                if val is not None:
                    self.owner_filter = val
        if self.owner_filter is not None:
            self.notes = [n for n in self.notes if n.owner == self.owner_filter]
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.notes


class _Db:
    def __init__(self, notes):
        self.notes = notes

    def query(self, *args, **kwargs):
        return _ListQuery(list(self.notes))

    def close(self):
        pass


def _install(monkeypatch, notes):
    fake_core_db = types.ModuleType("core.database")
    fake_core_db.SessionLocal = lambda: _Db(notes)
    fake_core_db.Note = MagicMock()
    fake_core_db.Note.owner = MagicMock()
    fake_core_db.Note.archived = MagicMock()
    fake_core_db.Note.label = MagicMock()
    fake_core_db.Note.pinned = MagicMock()
    fake_core_db.Note.updated_at = MagicMock()
    monkeypatch.setitem(sys.modules, "core.database", fake_core_db)
    monkeypatch.setitem(
        sys.modules,
        "src.auth_helpers",
        types.SimpleNamespace(
            owner_filter=lambda q, model, user, include_shared=True: q.filter(_OwnerEq(user))
        ),
    )


def _note(**kwargs):
    data = {
        "id": "abc12345-test",
        "owner": "alice",
        "title": "Buy milk",
        "content": "",
        "note_type": "note",
        "label": None,
        "items": None,
        "pinned": False,
        "archived": False,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_list_empty_owner_does_not_filter_to_blank(monkeypatch):
    _install(monkeypatch, [_note()])
    result = asyncio.run(
        tool_implementations.do_manage_notes(json.dumps({"action": "list"}), owner="")
    )
    assert "results" in result
    assert "Buy milk" in result["results"]


def test_list_scoped_owner_returns_only_matching(monkeypatch):
    _install(
        monkeypatch,
        [_note(owner="alice", title="Alice task"), _note(owner="bob", title="Bob task")],
    )
    result = asyncio.run(
        tool_implementations.do_manage_notes(json.dumps({"action": "list"}), owner="alice")
    )
    assert "Alice task" in result["results"]
    assert "Bob task" not in result["results"]


def test_list_empty_response_discourages_fabrication(monkeypatch):
    _install(monkeypatch, [])
    result = asyncio.run(
        tool_implementations.do_manage_notes(json.dumps({"action": "list"}), owner="alice")
    )
    assert result.get("empty") is True
    assert "Do NOT invent" in result["response"]
