"""Email background poller must use gogcli for gmail_gog accounts, not IMAP."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

_TMP_DATA = Path(tempfile.mkdtemp(prefix="odysseus-email-gog-poller-"))
os.environ.setdefault("DATA_DIR", str(_TMP_DATA))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DATA / 'app.db'}")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def test_auto_summarize_uses_gog_not_imap_for_gmail_gog_provider(monkeypatch):
    import routes.email_pollers as email_pollers
    from routes.email_helpers import _init_scheduled_db

    db_path = str(_TMP_DATA / "scheduled.db")
    monkeypatch.setattr(email_pollers, "SCHEDULED_DB", db_path)
    monkeypatch.setattr("routes.email_helpers.SCHEDULED_DB", db_path)
    _init_scheduled_db()

    calls = {"imap": 0, "gog_list": 0, "gog_read": 0}

    def fake_imap_connect(*args, **kwargs):
        calls["imap"] += 1
        raise AssertionError("IMAP connect should not run for gmail_gog accounts")

    def fake_get_email_config(account_id=None, owner=""):
        return {
            "account_id": account_id or "acct-gog",
            "account_name": "Stanford",
            "provider": "gmail_gog",
            "from_address": "user@alumni.stanford.edu",
            "imap_user": "user@alumni.stanford.edu",
        }

    class _FakeGog:
        @staticmethod
        def list_inbox(account, folder="INBOX", limit=50, offset=0, filter_="all", from_addr=None):
            calls["gog_list"] += 1
            assert account == "user@alumni.stanford.edu"
            return {
                "emails": [
                    {
                        "uid": "thread-1",
                        "message_id": "thread-1",
                        "subject": "Hello",
                        "from_name": "Sam",
                        "from_address": "sam@example.com",
                        "date": "2026-06-13 10:00",
                    }
                ],
                "total": 1,
                "folder": folder,
            }

        @staticmethod
        def read_message(account, message_id, folder="INBOX", mark_seen=True):
            calls["gog_read"] += 1
            return {
                "message_id": "<msg-1@example.com>",
                "subject": "Hello",
                "from_name": "Sam",
                "from_address": "sam@example.com",
                "date": "2026-06-13T10:00:00",
                "body": (
                    "Please review the attached document by Monday. "
                    "The team needs your feedback on the revised scope and timeline "
                    "before we send the final version to the client."
                ),
            }

    monkeypatch.setattr(email_pollers, "_imap_connect", fake_imap_connect)
    monkeypatch.setattr(email_pollers, "_get_email_config", fake_get_email_config)
    monkeypatch.setattr(email_pollers, "_owner_for_email_account", lambda _id: "user")
    monkeypatch.setattr(email_pollers, "_load_settings", lambda: {"email_auto_summarize": True})
    monkeypatch.setattr(
        "src.endpoint_resolver.resolve_endpoint",
        lambda *a, **k: ("http://llm.test/v1/chat/completions", "test-model", {}),
    )

    import src.gmail_gog as gmail_gog

    monkeypatch.setattr(gmail_gog, "list_inbox", _FakeGog.list_inbox)
    monkeypatch.setattr(gmail_gog, "read_message", _FakeGog.read_message)

    import requests

    class _Resp:
        ok = True

        @staticmethod
        def json():
            return {
                "choices": [
                    {
                        "message": {
                            "content": "<<<SUMMARY>>>\n- Review doc by Monday\n<<<END>>>"
                        }
                    }
                ]
            }

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())

    result = await email_pollers._auto_summarize_pass_single(
        days_back=1, account_id="acct-gog", progress_cb=None
    )

    assert calls["imap"] == 0
    assert calls["gog_list"] == 1
    assert calls["gog_read"] == 1
    assert "summarized 1" in result
