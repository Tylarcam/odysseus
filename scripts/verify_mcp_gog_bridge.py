"""Smoke test MCP email_server gog bridge against live gogcli (optional)."""
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mcp_servers.email_server as es


def _find_gog_account() -> tuple[str, str] | None:
    db = os.environ.get("DATABASE_URL", "sqlite:///./data/app.db")
    if db.startswith("sqlite:///"):
        path = db.replace("sqlite:///", "", 1)
        if not Path(path).is_absolute():
            path = str(PROJECT_ROOT / path)
    else:
        return None
    if not Path(path).exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(email_accounts)").fetchall()}
        if "provider" not in cols:
            return None
        row = conn.execute(
            "SELECT id, name, from_address, imap_user FROM email_accounts "
            "WHERE enabled=1 AND provider='gmail_gog' ORDER BY is_default DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        addr = (row["from_address"] or row["imap_user"] or "").strip()
        selector = row["name"] or row["id"] or addr
        return selector, addr
    finally:
        conn.close()


def main() -> int:
    es._ACCOUNT_CACHE.clear()
    monkeypatch_db = os.environ.get("DATA_DIR")
    if monkeypatch_db:
        es._db_path = lambda: Path(monkeypatch_db) / "app.db"  # type: ignore[method-assign]

    acct = _find_gog_account()
    if not acct:
        print("SKIP: no gmail_gog account in database")
        return 0

    selector, addr = acct
    print(f"Testing gog account: {selector} ({addr})")

    rows = es._list_emails(max_results=3, account=selector)
    print(f"list_emails: {len(rows)} row(s)")
    if not rows:
        print("WARN: empty inbox (or gog auth issue)")
        return 0

    uid = rows[0].get("uid")
    print(f"  first UID: {uid}")
    print(f"  subject: {rows[0].get('subject')}")

    body = es._read_email(uid=uid, account=selector)
    if body.get("error"):
        print(f"read_email FAIL: {body['error']}")
        return 1
    print(f"read_email OK: {len(body.get('body') or '')} chars body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
