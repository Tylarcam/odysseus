#!/usr/bin/env python3
"""Merge blackboard spill notes into the canonical board and archive clutter.

Usage:
  python scripts/cleanup_blackboard_spill.py           # dry-run
  python scripts/cleanup_blackboard_spill.py --apply # commit changes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import Document, Note, SessionLocal
from services.home.mycelia_feed import (
    CANONICAL_BLACKBOARD_ID,
    is_blackboard_clone_doc,
    is_blackboard_spill_title,
    is_swarm_health_note_title,
    merge_entries_into_board,
    parse_blackboard_entries,
)


def _collect_spill_notes(notes: list[Note]) -> list[Note]:
    out: list[Note] = []
    for note in notes:
        if note.archived:
            continue
        title = note.title or ""
        if is_blackboard_spill_title(title):
            out.append(note)
            continue
        if is_swarm_health_note_title(title):
            out.append(note)
    return out


def _content_already_on_board(board_text: str, content: str) -> bool:
    snippet = content.strip()[:200]
    if len(snippet) < 40:
        return snippet in board_text
    return snippet in board_text


def run(*, apply: bool) -> int:
    db = SessionLocal()
    try:
        board = db.query(Document).filter(Document.id == CANONICAL_BLACKBOARD_ID).first()
        if board is None:
            print(f"ERROR: canonical blackboard not found ({CANONICAL_BLACKBOARD_ID})")
            return 1

        notes = db.query(Note).all()
        spill_notes = _collect_spill_notes(notes)
        board_text = board.current_content or ""
        total_appended = 0
        total_fallback = 0

        print(f"Canonical board: {board.title!r} ({len(board_text)} chars)")
        print(f"Spill / health notes to archive: {len(spill_notes)}")

        for note in spill_notes:
            content = (note.content or "").strip()
            if content.lower() == "placeholder":
                print(f"  note {note.id[:8]}… {note.title[:60]!r} → skip placeholder")
                continue
            entries = parse_blackboard_entries(content, source_id=note.id, source_kind="note")
            new_text, n = merge_entries_into_board(board_text, entries)
            board_text = new_text
            total_appended += n
            fallback = 0
            if n == 0 and content and not _content_already_on_board(board_text, content):
                block = f"\n\n### Migrated from note · {note.title}\n\n{content}\n"
                board_text = board_text.rstrip() + block
                fallback = 1
                total_fallback += 1
            print(
                f"  note {note.id[:8]}… {note.title[:60]!r} → "
                f"merge {n} entries" + (f" + fallback body" if fallback else "")
            )

        clone_docs = [
            d
            for d in db.query(Document).filter(Document.is_active == True).all()  # noqa: E712
            if is_blackboard_clone_doc({"id": d.id, "title": d.title})
        ]
        print(f"Clone blackboard docs to deactivate: {len(clone_docs)}")
        for doc in clone_docs:
            print(f"  doc {doc.id[:8]}… {doc.title[:60]!r}")

        print(f"Total structured entries merged: {total_appended}")
        print(f"Total fallback bodies migrated: {total_fallback}")
        print(f"Board size after merge: {len(board_text)} chars")

        if not apply:
            print("\nDry run — pass --apply to commit.")
            return 0

        board.current_content = board_text
        board.version_count = (board.version_count or 1) + 1
        for note in spill_notes:
            note.archived = True
        for doc in clone_docs:
            doc.is_active = False
            doc.archived = True
        db.commit()
        print("\nApplied: archived spill notes, merged board, deactivated clone docs.")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes to the database")
    args = parser.parse_args()
    raise SystemExit(run(apply=args.apply))


if __name__ == "__main__":
    main()
