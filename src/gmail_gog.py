"""gmail_gog.py — Gmail adapter backed by gogcli (gog.exe).

Provides list / read / send / label operations that mirror the IMAP-based
interface in email_routes.py, so Gmail accounts that can't use IMAP basic-auth
(e.g. Google Workspace without App Passwords) can integrate via the already-
authenticated gogcli OAuth session.

Configuration:
  GOG_PATH  — path to gog.exe (env var). Defaults to the standard Windows
               Store location at %LOCALAPPDATA%\\Microsoft\\WindowsApps\\gog.exe.
"""

import base64
import calendar as _cal
import email.utils
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_gog_exec() -> str:
    # 1. Explicit override
    if explicit := os.environ.get("GOG_PATH"):
        return explicit
    # 2. gog on PATH (Windows Store apps are typically on PATH via WindowsApps)
    if on_path := shutil.which("gog"):
        return on_path
    # 3. Standard Windows Store location — use Path.home() so it works in
    #    background server processes where LOCALAPPDATA may not be set.
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return str(Path(localappdata) / "Microsoft" / "WindowsApps" / "gog.exe")
    linux_default = Path("/usr/local/bin/gog")
    if linux_default.is_file():
        return str(linux_default)
    return "gog"

# Odysseus folder name → Gmail query string
_FOLDER_TO_QUERY: dict[str, str] = {
    "INBOX":               "in:inbox",
    "Sent":                "in:sent",
    "[Gmail]/Sent Mail":   "in:sent",
    "[Gmail]/All Mail":    "in:anywhere",
    "All Mail":            "in:anywhere",
    "[Gmail]/Trash":       "in:trash",
    "Trash":               "in:trash",
    "[Gmail]/Spam":        "in:spam",
    "Spam":                "in:spam",
    "Starred":             "is:starred",
    "[Gmail]/Starred":     "is:starred",
    "[Gmail]/Drafts":      "in:drafts",
    "Drafts":              "in:drafts",
    "Archive":             "in:archive",
}

# Pseudo-folder list returned to the UI for Gmail accounts
GMAIL_FOLDERS = [
    "INBOX",
    "[Gmail]/Sent Mail",
    "[Gmail]/Drafts",
    "[Gmail]/Starred",
    "[Gmail]/All Mail",
    "[Gmail]/Trash",
    "[Gmail]/Spam",
]


def _folder_query(folder: str) -> str:
    return _FOLDER_TO_QUERY.get(folder, f"label:{folder.lower().replace(' ', '-')}")


def _run(args: list[str], account: str) -> dict:
    """Run a gog command with --json --no-input and return parsed output."""
    gog = _resolve_gog_exec()
    cmd = [gog, "--json", "--no-input", "-a", account] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise RuntimeError(
            f"gog.exe not found at {gog!r}. "
            "Install gogcli or set the GOG_PATH environment variable."
        )
    # exit code 3 = empty result set (no matching threads/messages)
    if r.returncode not in (0, 3):
        raise RuntimeError(
            f"gog exited {r.returncode}: {(r.stderr or r.stdout)[:300]}"
        )
    if not (r.stdout or "").strip():
        return {}
    return json.loads(r.stdout)


def _header_val(headers: list[dict], name: str) -> str:
    nl = name.lower()
    for h in headers:
        if (h.get("name") or "").lower() == nl:
            return h.get("value", "")
    return ""


def _b64decode(data: str) -> bytes:
    """Decode Gmail's URL-safe base64 (padding optional)."""
    data = data.replace("-", "+").replace("_", "/")
    pad = (-len(data)) % 4
    return base64.b64decode(data + "=" * pad)


def _extract_body(payload: dict) -> tuple[str, str]:
    """Recursively extract (plain_text, html) from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    body_data = (payload.get("body") or {}).get("data", "")
    parts = payload.get("parts") or []

    if mime == "text/plain" and body_data:
        return _b64decode(body_data).decode("utf-8", errors="replace"), ""
    if mime == "text/html" and body_data:
        return "", _b64decode(body_data).decode("utf-8", errors="replace")

    text, html = "", ""
    for part in parts:
        t, h = _extract_body(part)
        text = text or t
        html = html or h
    return text, html


def _parse_rfc2822(raw: str) -> tuple[str, float]:
    """Parse RFC 2822 date → (iso_str, epoch). Returns ("", 0.0) on failure."""
    if not raw:
        return "", 0.0
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        return dt.isoformat(), dt.timestamp()
    except Exception:
        return raw, 0.0


def _parse_gog_date(s: str) -> float:
    """Parse gog's 'YYYY-MM-DD HH:MM' display string → UTC epoch."""
    if not s:
        return 0.0
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return float(_cal.timegm(dt.timetuple()))
    except Exception:
        return 0.0


# ── Public API ────────────────────────────────────────────────────────────────

def list_inbox(
    account: str,
    folder: str = "INBOX",
    limit: int = 50,
    offset: int = 0,
    filter_: str = "all",
    from_addr: str | None = None,
) -> dict:
    """Return email list in the same dict shape as _list_emails_sync."""
    query = _folder_query(folder)
    if filter_ == "unread":
        query += " is:unread"
    elif filter_ == "favorites":
        query += " is:starred"
    if from_addr:
        query += f" from:{from_addr}"

    # Gmail uses page tokens; fetch offset+limit in one shot and slice.
    fetch_max = min(offset + limit, 500)
    args = ["gmail", "search", query, "--max", str(fetch_max)]

    try:
        data = _run(args, account)
    except Exception as e:
        logger.error(f"gog list_inbox failed: {e}")
        return {"emails": [], "total": 0, "folder": folder, "error": str(e)}

    threads = data.get("threads") or []
    next_token = data.get("nextPageToken", "")
    page = threads[offset: offset + limit]

    emails = []
    for t in page:
        labels = t.get("labels") or []
        is_read = "UNREAD" not in labels
        is_flagged = "STARRED" in labels
        raw_sender = t.get("from", "")
        sender_name, sender_addr = email.utils.parseaddr(raw_sender)
        date_str = t.get("date", "")
        date_epoch = _parse_gog_date(date_str)

        emails.append({
            "uid":             t["id"],   # thread ID used as uid throughout
            "message_id":      t["id"],
            "subject":         t.get("subject", "(no subject)"),
            "from_name":       sender_name or sender_addr,
            "from_address":    sender_addr,
            "to":              "",
            "cc":              "",
            "date":            date_str,
            "date_display":    date_str,
            "date_epoch":      date_epoch,
            "size":            0,
            "is_read":         is_read,
            "is_answered":     False,
            "is_flagged":      is_flagged,
            "flags":           "",
            "has_attachments": False,
            "tags":            [],
            "is_spam_verdict": "SPAM" in labels,
            "thread_id":       t["id"],
            "message_count":   t.get("messageCount", 1),
        })

    return {
        "emails":          emails,
        "total":           len(threads),
        "folder":          folder,
        "next_page_token": next_token,
    }


def read_message(
    account: str,
    message_id: str,
    folder: str = "INBOX",
    mark_seen: bool = True,
) -> dict:
    """Read a Gmail thread and return the latest message in Odysseus format."""
    try:
        data = _run(["gmail", "thread", "get", message_id], account)
    except Exception as e:
        logger.error(f"gog read_message failed: {e}")
        return {"error": str(e)}

    thread = data.get("thread") or {}
    messages = thread.get("messages") or []
    if not messages:
        return {"error": "Message not found"}

    msg = messages[-1]
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []

    subject    = _header_val(headers, "Subject") or "(no subject)"
    sender     = _header_val(headers, "From") or "unknown"
    to         = _header_val(headers, "To")
    cc         = _header_val(headers, "Cc")
    date_raw   = _header_val(headers, "Date")
    in_reply_to = _header_val(headers, "In-Reply-To")
    references  = _header_val(headers, "References")
    msg_id_hdr  = _header_val(headers, "Message-ID")

    sender_name, sender_addr = email.utils.parseaddr(sender)
    iso_date, _ = _parse_rfc2822(date_raw)
    body, body_html = _extract_body(payload)
    label_ids = msg.get("labelIds") or []

    if mark_seen and "UNREAD" in label_ids:
        try:
            _run(["gmail", "batch", "modify", msg["id"], "--remove", "UNREAD"], account)
        except Exception:
            pass

    return {
        "uid":             message_id,
        "folder":          folder,
        "message_id":      msg_id_hdr.strip(),
        "subject":         subject,
        "from_name":       sender_name or sender_addr,
        "from_address":    sender_addr,
        "to":              to,
        "cc":              cc,
        "date":            iso_date,
        "in_reply_to":     in_reply_to.strip(),
        "references":      references.strip(),
        "body":            body,
        "body_html":       body_html,
        "attachments":     [],
        "cached_summary":  None,
        "cached_ai_reply": None,
        "boundaries":      None,
        "thread_turns":    None,
        "sender_signature": None,
    }


def send_message(
    account: str,
    to: str,
    subject: str,
    body: str,
    body_html: str = "",
    cc: str = "",
    bcc: str = "",
    in_reply_to_msg_id: str = "",
    thread_id: str = "",
    from_addr: str = "",
) -> dict:
    """Send an email via gog gmail send."""
    args = ["gmail", "send", "--to", to, "--subject", subject, "--body", body]
    if body_html:
        args += ["--body-html", body_html]
    if cc:
        args += ["--cc", cc]
    if bcc:
        args += ["--bcc", bcc]
    if in_reply_to_msg_id:
        args += ["--reply-to-message-id", in_reply_to_msg_id]
    elif thread_id:
        args += ["--thread-id", thread_id]
    if from_addr and from_addr != account:
        args += ["--from", from_addr]

    try:
        data = _run(args, account)
        return {"ok": True, "id": data.get("id", "")}
    except Exception as e:
        logger.error(f"gog send_message failed: {e}")
        return {"ok": False, "error": str(e)}


def modify_labels(
    account: str,
    message_ids: list[str],
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict:
    """Add/remove Gmail system labels on one or more message IDs."""
    if not message_ids:
        return {"ok": True}
    args = ["gmail", "batch", "modify"] + message_ids
    for label in (add_labels or []):
        args += ["--add", label]
    for label in (remove_labels or []):
        args += ["--remove", label]
    try:
        _run(args, account)
        return {"ok": True}
    except Exception as e:
        logger.error(f"gog modify_labels failed: {e}")
        return {"ok": False, "error": str(e)}


def mark_read(account: str, message_id: str) -> dict:
    return modify_labels(account, [message_id], remove_labels=["UNREAD"])


def mark_unread(account: str, message_id: str) -> dict:
    return modify_labels(account, [message_id], add_labels=["UNREAD"])


def trash_message(account: str, message_id: str) -> dict:
    return modify_labels(account, [message_id], add_labels=["TRASH"], remove_labels=["INBOX"])


def archive_message(account: str, message_id: str) -> dict:
    return modify_labels(account, [message_id], remove_labels=["INBOX"])
