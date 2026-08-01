"""Tests for Mycelia blackboard feed parsing."""

from datetime import datetime, timezone

from services.home.mycelia_feed import (
    CANONICAL_BLACKBOARD_ID,
    build_mycelia_feed,
    is_blackboard_spill_title,
    mycelia_priority_queue_items,
    parse_blackboard_entries,
    parse_fruit_ledger,
    parse_top3,
)
from services.home.swarm_registry import resolve_swarm_docs


BOARD_SAMPLE = """
## Today's Top 3
- Ship CMD Center MYCELIA feed — consolidates blackboard intel
- Review MorningAI follow-ups — revenue clock
- Finish dissertation chapter outline

### 2026-07-12 · Sporangium (morning plan)
- SENSED: Empty harvest from paused agents
- DID: Set Top 3 priorities on blackboard
- SIGNAL -> Human: confirm which agents to re-activate

### 2026-07-12 · Culler (health scan)
- SENSED: 31 spill notes detected
- DID: Logged health report
- SIGNAL -> Sporangium: merge clone docs
"""

FRUIT_SAMPLE = """
### 2026-07-12 · Herald
- FRUIT: Submitted grant draft
- CHANNEL: email
- EVIDENCE: sent confirmation

## Pending at sporulation gate
| Item | Status |
| --- | --- |
| Job follow-up | awaiting approval |
"""


def test_parse_blackboard_entries_extracts_fields():
    entries = parse_blackboard_entries(BOARD_SAMPLE, source_id="board-1", source_kind="doc")
    assert len(entries) == 2
    human = next(e for e in entries if "Human" in e.get("signal_target", ""))
    assert human["sensed"].startswith("Empty harvest")
    assert human["did"].startswith("Set Top 3")
    assert human["signal"].startswith("confirm")


def test_parse_top3_ranked_items():
    items = parse_top3(BOARD_SAMPLE)
    assert len(items) == 3
    assert "CMD Center" in items[0]["title"]
    assert items[0]["rank"] == 1


def test_parse_fruit_ledger_pending_and_fruit():
    parsed = parse_fruit_ledger(FRUIT_SAMPLE)
    assert parsed["fruit_count"] == 1
    assert parsed["pending"][0]["item"] == "Job follow-up"


def test_build_mycelia_feed_merges_board_and_spill_notes():
    now = datetime(2026, 7, 12, 15, 0, tzinfo=timezone.utc)
    documents = [
        {
            "id": CANONICAL_BLACKBOARD_ID,
            "title": "¡¡¡ Swarm Blackboard ¡¡¡ CANONICAL",
            "content": BOARD_SAMPLE,
            "updated_at": "2026-07-12T10:00:00+00:00",
        },
        {
            "id": "fruit-1",
            "title": "🍄 Fruit Ledger — Odysseus Swarm",
            "content": FRUIT_SAMPLE,
            "updated_at": "2026-07-12T21:00:00+00:00",
        },
    ]
    notes = [
        {
            "id": "n-spill",
            "title": "⬛ Blackboard entry 2026-07-11 – Scout",
            "content": "### 2026-07-11 · Scout\n- SENSED: inbox quiet\n- DID: triaged 3 threads\n- SIGNAL -> Rhizo: research Acme role",
            "archived": False,
        }
    ]
    feed = build_mycelia_feed(documents=documents, notes=notes, agent_activity=[], now=now)
    assert len(feed["top3"]) == 3
    assert any(s.get("for_human") for s in feed["signals"])
    assert feed["health"]["spill_note_count"] == 1
    assert feed["fruit"]["pending"]
    assert feed["quick_read"]
    assert len(feed["entries"]) >= 2


def test_mycelia_priority_queue_items_shape():
    feed = build_mycelia_feed(
        documents=[{"id": CANONICAL_BLACKBOARD_ID, "title": "Blackboard", "content": BOARD_SAMPLE}],
        notes=[],
        now=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )
    rows = mycelia_priority_queue_items(feed)
    assert rows[0]["kind"] == "mycelia_priority"
    assert rows[0]["branch"] == "mycelia"
    assert rows[0]["urgency"] >= 82


def test_is_blackboard_spill_title_expanded():
    assert is_blackboard_spill_title("⬛ Blackboard entry 2026-07-20 – Scout")
    assert is_blackboard_spill_title("Blackboard — 2026-07-13 · Keeper")
    assert is_blackboard_spill_title("[Swarm · TODO] Sporangium: Merge blackboard clones")
    assert not is_blackboard_spill_title("Morning brief")


def test_resolve_swarm_docs_prefers_pinned_blackboard():
    docs = [
        {"id": "other", "title": "Swarm Substrate (Blackboard)", "content": "clone"},
        {"id": CANONICAL_BLACKBOARD_ID, "title": "¡¡¡ Swarm Blackboard ¡¡¡ CANONICAL", "content": "canonical"},
    ]
    resolved = resolve_swarm_docs(docs)
    assert resolved["board"]["id"] == CANONICAL_BLACKBOARD_ID
