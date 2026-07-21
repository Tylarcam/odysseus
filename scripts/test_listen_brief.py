#!/usr/bin/env python3
"""Smoke-test document Listen audio brief against the running Odysseus API."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:7000"


def get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def post(path: str) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        method="POST",
        headers={"Accept": "application/json", "Content-Length": "0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    doc_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if not doc_id:
        lib = get("/api/documents/library?limit=5&sort=recent")
        docs = lib.get("documents") or lib.get("items") or []
        if not docs:
            print("No documents in library")
            return 1
        doc_id = docs[0]["id"]
        print(f"Using doc: {doc_id!r} title={docs[0].get('title')!r}")

    print("POST audio-brief kickoff...")
    kick = post(f"/api/document/{doc_id}/audio-brief")
    print("kickoff:", kick)

    deadline = time.time() + 300
    while time.time() < deadline:
        st = get(f"/api/document/{doc_id}/audio-brief/status")
        status = st.get("status")
        print("status:", status, st.get("error") or "")
        if status in ("ready", "skipped", "failed"):
            if status == "failed":
                return 1
            if status == "skipped":
                tr = get(f"/api/document/{doc_id}/audio-brief/transcript")
                script = (tr.get("script") or "").strip()
                print(f"skipped — transcript len={len(script)}")
                print(script[:500] + ("..." if len(script) > 500 else ""))
                return 0 if script else 1
            chunk_url = f"{BASE}/api/document/{doc_id}/audio-brief/chunk/0"
            req = urllib.request.Request(chunk_url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            print(f"ready — chunk0 bytes={len(data)} mime={resp.headers.get('Content-Type')}")
            return 0
        time.sleep(3)

    print("timed out")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"HTTP {e.code}: {body[:500]}")
        raise SystemExit(1)
