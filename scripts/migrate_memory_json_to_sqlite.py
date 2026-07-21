#!/usr/bin/env python3
"""One-shot migration: data/memory.json -> SQLite memories table.

Preserves entry ids so ChromaDB vectors stay aligned. Does not delete memory.json.

Usage:
    python scripts/migrate_memory_json_to_sqlite.py           # dry-run (default)
    python scripts/migrate_memory_json_to_sqlite.py --apply # write to SQLite
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.constants import APP_DB, MEMORY_FILE


def _load_json_entries() -> list[dict]:
    if not os.path.isfile(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise SystemExit(f"Expected JSON array in {MEMORY_FILE}")
    return [e for e in data if isinstance(e, dict) and (e.get("text") or "").strip()]


def _ensure_memories_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            category TEXT DEFAULT 'fact',
            source TEXT DEFAULT 'user',
            owner TEXT,
            session_id TEXT,
            timestamp INTEGER
        )
        """
    )


def migrate(*, apply: bool) -> dict[str, int]:
    entries = _load_json_entries()
    stats = {
        "json_total": len(entries),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "pinned": sum(1 for e in entries if e.get("pinned")),
        "sqlite_before": 0,
        "sqlite_after": 0,
    }

    if not os.path.isfile(APP_DB):
        if apply:
            raise SystemExit(f"Database not found: {APP_DB}")
        stats["sqlite_before"] = 0
        stats["sqlite_after"] = stats["inserted"]
        for entry in entries:
            mem_id = str(entry.get("id") or "").strip()
            text = str(entry.get("text") or "").strip()
            if mem_id and text:
                stats["inserted"] += 1
            else:
                stats["skipped"] += 1
        return stats

    conn = sqlite3.connect(APP_DB)
    try:
        _ensure_memories_table(conn)
        stats["sqlite_before"] = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

        for entry in entries:
            mem_id = str(entry.get("id") or "").strip()
            text = str(entry.get("text") or "").strip()
            if not mem_id or not text:
                stats["skipped"] += 1
                continue

            category = entry.get("category") or "fact"
            source = entry.get("source") or "user"
            owner = entry.get("owner")
            session_id = entry.get("session_id")
            timestamp = int(entry.get("timestamp") or 0) or None

            row = conn.execute(
                "SELECT text, category, source, owner, session_id, timestamp FROM memories WHERE id = ?",
                (mem_id,),
            ).fetchone()

            if row:
                new_vals = (text, category, source, owner, session_id, timestamp)
                if row != new_vals:
                    if apply:
                        conn.execute(
                            """
                            UPDATE memories
                               SET text = ?, category = ?, source = ?, owner = ?,
                                   session_id = ?, timestamp = ?
                             WHERE id = ?
                            """,
                            (*new_vals, mem_id),
                        )
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                if apply:
                    conn.execute(
                        """
                        INSERT INTO memories (id, text, category, source, owner, session_id, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (mem_id, text, category, source, owner, session_id, timestamp),
                    )
                stats["inserted"] += 1

        if apply:
            conn.commit()
            stats["sqlite_after"] = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        else:
            stats["sqlite_after"] = stats["sqlite_before"] + stats["inserted"]
    finally:
        conn.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to SQLite (default is dry-run)",
    )
    args = parser.parse_args()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Memory migration ({mode})")
    print(f"  source: {MEMORY_FILE}")
    print(f"  target: {APP_DB}")

    stats = migrate(apply=args.apply)

    print(f"  json entries:     {stats['json_total']}")
    print(f"  pinned (in JSON): {stats['pinned']}")
    print(f"  sqlite before:    {stats['sqlite_before']}")
    print(f"  would insert:     {stats['inserted']}")
    print(f"  would update:     {stats['updated']}")
    print(f"  skipped:          {stats['skipped']}")
    print(f"  sqlite after:     {stats['sqlite_after']}")
    if not args.apply:
        print("\nNo changes written. Re-run with --apply to migrate.")
    else:
        print("\nDone. memory.json was not modified.")


if __name__ == "__main__":
    main()
