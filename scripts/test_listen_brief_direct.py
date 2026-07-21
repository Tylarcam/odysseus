#!/usr/bin/env python3
"""Direct in-process test of document audio brief (no HTTP)."""
import asyncio
import sqlite3
import sys

from services.documents import audio_brief as dab


def pick_doc_id() -> str:
    conn = sqlite3.connect("/app/data/app.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title FROM documents WHERE archived=0 ORDER BY updated_at DESC LIMIT 1"
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise SystemExit("no documents")
    print(f"doc={row[0]!r} title={row[1]!r}")
    return row[0]


async def main() -> None:
    doc_id = sys.argv[1] if len(sys.argv) > 1 else pick_doc_id()
    conn = sqlite3.connect("/app/data/app.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT title, current_content, owner FROM documents WHERE id=?",
        (doc_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise SystemExit(f"document {doc_id} not found")
    title, content, owner = row
    dab.delete_brief(doc_id)
    print("generating brief (utility primary + default_model_fallbacks)...")
    await dab.generate_doc_audio_brief(doc_id, title or "", content or "", owner or "")
    state = dab.get_brief_state(doc_id)
    print("final status:", state.get("status"))
    print("error:", state.get("error"))
    script = (state.get("script") or "").strip()
    print(f"script len={len(script)}")
    if script:
        print(script[:400] + ("..." if len(script) > 400 else ""))


if __name__ == "__main__":
    asyncio.run(main())
