"""Archive triage notes + find apply URLs."""
import json
import os
import re
import sqlite3
import urllib.request

DB = "data/app.db"
TRIAGE_PREFIXES = [
    "e4ec019a", "04ff0704", "8f852325", "2a97536d", "742e5822", "b7cc34f2",
    "7ecb589b", "9ce3fe47", "d92e251b", "1f1c5990", "8d4f4d66", "45a8f2df",
    "7c6fe73e", "0d7c09ef", "6c721925", "9894a4f4", "4d76cb78", "b3c3a820",
    "2add7a36", "3e68b0b9", "5d79e517", "34cd2f99", "d89db3b0", "ee67a5f7",
]
KEEP = {"619e4419", "45a8f2df"}  # canonical tracker; keep today's scout if still active

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print("=== HANDSHAKE URLS IN DB ===")
for row in conn.execute(
    "SELECT id, title, content FROM notes WHERE content LIKE '%joinhandshake%' OR title LIKE '%Merit%' OR title LIKE '%Prelim%'"
):
    urls = re.findall(r"https?://[^\s\"'<>]*joinhandshake[^\s\"'<>]*", row["content"] or "")
    if urls:
        print(row["id"][:8], row["title"][:40], urls[:3])

for row in conn.execute("SELECT id, title, current_content FROM documents WHERE title LIKE '%Merit%' OR title LIKE '%Prelim%'"):
    blob = row["current_content"] or ""
    urls = re.findall(r"https?://[^\s\"'<>]*(?:joinhandshake|prelim)[^\s\"'<>]*", blob, re.I)
    if urls:
        print("doc", row["id"][:8], urls)

# job-application-ops metadata
meta_paths = [
    r"C:\Users\tylar\code\notion\Projects\job-application-ops\positions\_active",
]
for base in meta_paths:
    if os.path.isdir(base):
        for name in os.listdir(base):
            print("folder", name)

# Archive via API
for path in [r"C:\Users\tylar\code\odysseus\.env"]:
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith("ODYSSEUS_") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))

base = os.environ.get("ODYSSEUS_URL", "http://127.0.0.1:7000").rstrip("/")
token = os.environ.get("ODYSSEUS_API_TOKEN", "")

archived = []
errors = []
if token:
    for prefix in TRIAGE_PREFIXES:
        row = conn.execute("SELECT id, title, pinned, archived FROM notes WHERE id LIKE ?", (prefix + "%",)).fetchone()
        if not row:
            continue
        nid = row["id"]
        if any(k in nid for k in KEEP):
            print("SKIP keep", nid[:8], row["title"][:50])
            continue
        if row["archived"]:
            print("already archived", nid[:8])
            continue
        body = json.dumps({"action": "update", "id": nid, "archived": True, "pinned": False}).encode()
        req = urllib.request.Request(
            f"{base}/api/codex/todos",
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=20)
            archived.append((nid[:8], row["title"][:50]))
        except Exception as ex:
            errors.append((nid[:8], str(ex)))

print("=== ARCHIVED ===", len(archived))
for a in archived:
    print(" ", a[0], a[1])
if errors:
    print("=== ERRORS ===", errors)
