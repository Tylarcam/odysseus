"""MCP email_server must route gmail_gog accounts through gmail_gog, not IMAP."""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mcp_servers.email_server as es


@pytest.fixture
def gog_db(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(es, "_db_path", lambda: db_path)
    es._ACCOUNT_CACHE.clear()

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE email_accounts (
            id TEXT PRIMARY KEY,
            name TEXT,
            is_default INTEGER,
            enabled INTEGER,
            provider TEXT,
            imap_host TEXT,
            imap_port INTEGER,
            imap_user TEXT,
            imap_password TEXT,
            imap_starttls INTEGER,
            smtp_host TEXT,
            smtp_port INTEGER,
            smtp_security TEXT,
            smtp_user TEXT,
            smtp_password TEXT,
            from_address TEXT,
            created_at TEXT
        )
    """)
    conn.execute(
        """
        INSERT INTO email_accounts VALUES (
            'acct-gog', 'Stanford', 1, 1, 'gmail_gog',
            '', 993, 'user@alumni.stanford.edu', '', 0,
            '', 465, '', '', '', 'user@alumni.stanford.edu', '2026-01-01'
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_list_emails_uses_gog_not_imap(gog_db, monkeypatch):
    calls = {"imap": 0, "gog": 0}

    def fake_imap(*args, **kwargs):
        calls["imap"] += 1
        raise AssertionError("IMAP should not run for gmail_gog accounts")

    class FakeGog:
        @staticmethod
        def list_inbox(account, folder="INBOX", limit=50, offset=0, filter_="all", from_addr=None):
            calls["gog"] += 1
            assert account == "user@alumni.stanford.edu"
            assert filter_ == "unread"
            return {
                "emails": [{
                    "uid": "thread-abc123",
                    "message_id": "thread-abc123",
                    "subject": "Cardinal Careers",
                    "from_name": "BEAM",
                    "from_address": "beam@stanford.edu",
                    "date": "2026-06-13 15:15",
                }],
                "total": 1,
                "folder": folder,
            }

    monkeypatch.setattr(es, "_imap_connect", fake_imap)
    monkeypatch.setattr(es, "_get_cached_summaries", lambda: {})
    monkeypatch.setitem(sys.modules, "src.gmail_gog", FakeGog)

    rows = es._list_emails(
        folder="INBOX",
        max_results=5,
        unread_only=True,
        account="Stanford",
    )
    assert calls == {"imap": 0, "gog": 1}
    assert len(rows) == 1
    assert rows[0]["uid"] == "thread-abc123"
    assert rows[0]["subject"] == "Cardinal Careers"


def test_read_email_uses_gog(gog_db, monkeypatch):
    calls = {"imap": 0, "gog": 0}

    def fake_imap(*args, **kwargs):
        calls["imap"] += 1
        raise AssertionError("IMAP should not run for gmail_gog accounts")

    class FakeGog:
        @staticmethod
        def read_message(account, message_id, folder="INBOX", mark_seen=True):
            calls["gog"] += 1
            assert account == "user@alumni.stanford.edu"
            assert message_id == "thread-abc123"
            return {
                "uid": "thread-abc123",
                "subject": "Cardinal Careers",
                "from_name": "BEAM",
                "from_address": "beam@stanford.edu",
                "date": "2026-06-13T15:15:00",
                "message_id": "<beam@stanford.edu>",
                "body": "Fall opportunities open soon.",
                "attachments": [],
            }

    monkeypatch.setattr(es, "_imap_connect", fake_imap)
    monkeypatch.setitem(sys.modules, "src.gmail_gog", FakeGog)

    result = es._read_email(uid="thread-abc123", account="Stanford")
    assert calls == {"imap": 0, "gog": 1}
    assert "error" not in result
    assert "Fall opportunities" in result["body"]
    assert result["uid"] == "thread-abc123"
