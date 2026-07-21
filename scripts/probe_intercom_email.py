#!/usr/bin/env python3
"""One-off probe: find intercom-mail threads across configured accounts."""
import email
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routes.email_helpers import _get_email_config, _imap_connect, _decode_header, _q


def search_gog(addr: str, query: str, max_results: int = 5):
    gog_exe = "/usr/local/bin/gog"
    cmd = [gog_exe, "--json", "--no-input", "-a", addr, "gmail", "search", query, "--max", str(max_results)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if not (p.stdout or "").strip():
        return []
    data = json.loads(p.stdout)
    return data.get("threads") or []


def search_imap(acct_id: str, owner: str):
    conn = _imap_connect(acct_id, owner=owner)
    queries = [
        'FROM "intercom-mail.com"',
        'FROM "api-platform.intercom-mail.com"',
        'TEXT "intercom-mail"',
    ]
    folders = ["INBOX", "Archive", "[Gmail]/All Mail", "All Mail", "Sent"]
    try:
        for folder in folders:
            st, _ = conn.select(_q(folder), readonly=True)
            if st != "OK":
                continue
            for crit in queries:
                st, data = conn.uid("SEARCH", None, crit)
                uids = data[0].split() if st == "OK" and data and data[0] else []
                if not uids:
                    continue
                print(f"  IMAP {folder} {crit} -> {len(uids)} matches")
                for uid in list(reversed(uids))[:3]:
                    st2, md = conn.uid("FETCH", uid, "(RFC822.HEADER)")
                    if st2 != "OK" or not md or not md[0]:
                        continue
                    msg = email.message_from_bytes(md[0][1])
                    print(
                        "   ",
                        _decode_header(msg.get("From", "")),
                        "|",
                        _decode_header(msg.get("Subject", ""))[:80],
                    )
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def main():
    owner = "tylarcam@alumni.stanford.edu"
    accounts = [
        "88272b55192f47c385dbb4a3e8fb7cb4",
        "af028fc64c514abf97eef57064849f3e",
    ]
    gog_queries = [
        "from:api-platform.intercom-mail.com",
        "from:nova@api-platform.intercom-mail.com",
        "api-platform.intercom-mail.com",
        "intercom-mail.com",
        "nova intercom",
    ]
    for acct_id in accounts:
        cfg = _get_email_config(acct_id, owner=owner)
        name = cfg.get("account_name")
        provider = cfg.get("provider")
        print(f"\n=== {name} ({provider}) ===")
        if provider == "gmail_gog":
            addr = cfg.get("from_address") or ""
            for query in gog_queries:
                threads = search_gog(addr, query)
                print(f"  GOG {query!r} -> {len(threads)} threads")
                for t in threads[:3]:
                    print(f"    {t.get('from')} | {t.get('subject', '')[:80]}")
        else:
            search_imap(acct_id, owner)


if __name__ == "__main__":
    main()
