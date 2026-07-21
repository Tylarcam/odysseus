"""One-off: find apply URLs + archive triage notes."""
import json
import re
import sqlite3
import urllib.request
import os

DB = "data/app.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Apply URL hunt
print("=== APPLY URLS ===")
for row in conn.execute(
    "SELECT company, role, apply_url, handshake_job_id, raw_input, jd_text FROM job_records "
    "WHERE company IN ('MeritFirst','Prelim','Smoosh AI','mond inc.','Artera','Monid')"
):
    d = dict(row)
    text = json.dumps(d.get("raw_input") or "") + (d.get("jd_text") or "")
    urls = re.findall(r"https?://[^\s\"'<>]+", text)
    print(json.dumps({"company": d["company"], "apply_url": d["apply_url"], "handshake_job_id": d["handshake_job_id"], "urls_in_raw": urls[:5]}))

n = conn.execute("SELECT content, items FROM notes WHERE id='619e4419'").fetchone()
if n:
    blob = (n["content"] or "") + json.dumps(n["items"] or "")
    for m in re.finditer(r"https?://[^\s\"'<>]+", blob):
        print("tracker_url:", m.group(0))

# Email search via env
for path in [r"C:\Users\tylar\code\odysseus\.env"]:
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith("ODYSSEUS_") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))

base = os.environ.get("ODYSSEUS_URL", "http://127.0.0.1:7000").rstrip("/")
token = os.environ.get("ODYSSEUS_API_TOKEN", "")
if token:
    req = urllib.request.Request(
        f"{base}/api/codex/emails?folder=INBOX&limit=50&filter=all",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        for e in data.get("emails", []):
            subj = (e.get("subject") or "").lower()
            if any(k in subj for k in ["meritfirst", "prelim", "merit first"]):
                print("email:", e.get("uid"), e.get("subject"))
    except Exception as ex:
        print("email_err:", ex)

TRIAGE_IDS = [
    "e4ec019a", "04ff0704", "8f852325", "2a97536d", "742e5822", "b7cc34f2",
    "7ecb589b", "9ce3fe47", "d92e251b", "1f1c5990", "8d4f4d66", "45a8f2df",
    "7c6fe73e", "0d7c09ef", "6c721925", "9894a4f4", "4d76cb78",
    "7c6fe73e", "0d7c09ef", "6c721925", "b3c3a820", "2add7a36", "3e68b0b9",
    "5d79e517", "34cd2f99", "d89db3b0", "ee67a5f7",
]
# dedupe
TRIAGE_IDS = list(dict.fromkeys(TRIAGE_IDS))
print("=== TRIAGE NOTES TO ARCHIVE ===", len(TRIAGE_IDS))
for nid in TRIAGE_IDS:
    row = conn.execute("SELECT id, title, archived, pinned FROM notes WHERE id LIKE ?", (nid + "%",)).fetchone()
    if row:
        print(row["id"], "| pinned:", row["pinned"], "| archived:", row["archived"], "|", (row["title"] or "")[:60])
