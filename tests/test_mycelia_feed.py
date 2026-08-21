"""Tests for Mycelia blackboard feed parsing."""

from datetime import datetime, timezone

from services.home.mycelia_feed import (
    CANONICAL_BLACKBOARD_ID,
    append_conversion_fruit,
    build_mycelia_feed,
    conversion_fruit_events,
    find_fruit_ledger,
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
    assert parsed["last_fruit"] == "Submitted grant draft"
    assert parsed["pending"][0]["item"] == "Job follow-up"


def test_parse_fruit_ledger_empty():
    parsed = parse_fruit_ledger("")
    assert parsed["fruit_count"] == 0
    assert parsed["last_fruit"] == ""
    assert parsed["fruits"] == []


def test_conversion_fruit_empty_when_gate_open():
    notes = [{
        "id": "f1cf1f16",
        "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
        "items": [{"text": "Send 01", "done": False} for _ in range(5)],
    }]
    docs = [{"id": "fruit-1", "title": "🍄 Fruit Ledger — Odysseus Swarm", "content": ""}]
    events = conversion_fruit_events(notes=notes, documents=docs)
    assert events == []
    text, added = append_conversion_fruit("", events, today="2026-08-20")
    assert added == []
    assert parse_fruit_ledger(text)["fruit_count"] == 0


def test_conversion_fruit_one_after_gate_clear():
    notes = [{
        "id": "f1cf1f16-aaaa-bbbb-cccc-dddddddddddd",
        "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
        "items": [{"text": "Send 01", "done": True} for _ in range(5)],
    }]
    events = conversion_fruit_events(notes=notes, documents=[])
    assert len(events) == 1
    assert "5 proposals sent" in events[0]["fruit"]
    assert "$" not in events[0]["fruit"]
    text, added = append_conversion_fruit("", events, today="2026-08-20")
    assert len(added) == 1
    parsed = parse_fruit_ledger(text)
    assert parsed["fruit_count"] == 1
    assert parsed["last_fruit"] == "Upwork Send Pack — 5 proposals sent"
    assert "f1cf1f16" in text
    again, added2 = append_conversion_fruit(text, events, today="2026-08-20")
    assert added2 == []
    assert parse_fruit_ledger(again)["fruit_count"] == 1


def test_find_fruit_ledger_falls_back_to_note_stub():
    notes = [{"id": "506a37f1", "title": "🍄 Fruit Ledger — Odysseus Swarm", "content": "No fruit today."}]
    found = find_fruit_ledger([], notes)
    assert found["kind"] == "note"
    assert found["record"]["id"] == "506a37f1"


def test_find_fruit_ledger_empty_doc_loses_to_live_stub():
    documents = [{
        "id": "empty-fruit-doc",
        "title": "🍄 Fruit Ledger — Odysseus Swarm",
        "content": "",
        "updated_at": "2026-08-20T12:00:00+00:00",
    }]
    notes = [{
        "id": "506a37f1",
        "title": "🍄 Fruit Ledger — Odysseus Swarm",
        "content": "- FRUIT: Upwork Send Pack — 5 proposals sent\n",
        "updated_at": "2026-08-19T12:00:00+00:00",
    }]
    found = find_fruit_ledger(documents, notes)
    assert found["kind"] == "note"
    assert found["record"]["id"] == "506a37f1"


HOWTO_FRUIT_DOC = {
    "id": "howto-fruit-doc",
    "title": "¡¡¡ Fruit Ledger ¡¡¡ Odysseus Swarm",
    "content": (
        "# ¡¡¡ Fruit Ledger ¡¡¡ Odysseus Swarm\n"
        "> Restored 2026-07-09 by Cursor (Culler remediation).\n"
        "## How to log fruit\n"
        "- FRUIT: what left the system\n"
        "## Recorded fruit\n"
        "_None since swarm inception._\n"
        "### 2026-07-15 · Herald\n"
        "- FRUIT: No fruit today.\n"
    ),
    "updated_at": "2026-08-20T18:00:00+00:00",
}


def test_find_fruit_ledger_howto_doc_loses_to_empty_herald_note():
    notes = [{"id": "506a37f1", "title": "🍄 Fruit Ledger — Odysseus Swarm", "content": ""}]
    found = find_fruit_ledger([HOWTO_FRUIT_DOC], notes)
    assert found["kind"] == "note"
    assert found["record"]["id"] == "506a37f1"
    assert parse_fruit_ledger(HOWTO_FRUIT_DOC["content"])["fruit_count"] >= 1


def test_find_fruit_ledger_howto_doc_loses_to_live_fruit_note():
    notes = [{
        "id": "506a37f1",
        "title": "🍄 Fruit Ledger — Odysseus Swarm",
        "content": "- FRUIT: Upwork Send Pack — 5 proposals sent\n",
    }]
    found = find_fruit_ledger([HOWTO_FRUIT_DOC], notes)
    assert found["kind"] == "note"
    assert found["record"]["id"] == "506a37f1"
    assert "- FRUIT:" in (found["record"].get("content") or "")


def test_find_fruit_ledger_empty_doc_loses_to_empty_stub():
    documents = [{
        "id": "empty-fruit-doc",
        "title": "🍄 Fruit Ledger — Odysseus Swarm",
        "content": "placeholder, no fruit lines",
    }]
    notes = [{"id": "506a37f1", "title": "🍄 Fruit Ledger — Odysseus Swarm", "content": ""}]
    found = find_fruit_ledger(documents, notes)
    assert found["kind"] == "note"
    assert found["record"]["id"] == "506a37f1"


def test_find_fruit_ledger_live_doc_beats_live_stub():
    documents = [{
        "id": "live-fruit-doc",
        "title": "🍄 Fruit Ledger — Odysseus Swarm",
        "content": "- FRUIT: Library row\n",
    }]
    notes = [{
        "id": "506a37f1",
        "title": "🍄 Fruit Ledger — Odysseus Swarm",
        "content": "- FRUIT: Note stub row\n",
    }]
    found = find_fruit_ledger(documents, notes)
    assert found["kind"] == "doc"
    assert found["record"]["id"] == "live-fruit-doc"


def test_find_fruit_ledger_empty_doc_loses_to_other_live_note():
    documents = [{
        "id": "empty-fruit-doc",
        "title": "🍄 Fruit Ledger — Odysseus Swarm",
        "content": "",
    }]
    notes = [{
        "id": "other-fruit-note",
        "title": "Fruit Ledger — overflow",
        "content": "- FRUIT: Overflow row\n",
    }]
    found = find_fruit_ledger(documents, notes)
    assert found["kind"] == "note"
    assert found["record"]["id"] == "other-fruit-note"


def test_build_mycelia_feed_prefers_live_note_over_empty_doc():
    feed = build_mycelia_feed(
        documents=[{
            "id": "empty-fruit-doc",
            "title": "🍄 Fruit Ledger — Odysseus Swarm",
            "content": "",
        }],
        notes=[{
            "id": "506a37f1",
            "title": "🍄 Fruit Ledger — Odysseus Swarm",
            "content": "- FRUIT: Gate cleared\n",
        }],
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    assert feed["fruit"]["fruit_count"] == 1
    assert feed["fruit"]["ledger_kind"] == "note"
    assert feed["fruit"]["ledger_id"] == "506a37f1"
    assert feed["fruit"]["last_fruit"] == "Gate cleared"


def test_conversion_fruit_npr_draft_marked_sent():
    notes = [{
        "id": "4be22ee3-1111-2222-3333-444444444444",
        "title": "NPR Panel 2 thank-you (sent)",
        "content": "draft body",
    }]
    events = conversion_fruit_events(notes=notes, documents=[])
    assert len(events) == 1
    assert events[0]["fruit"] == "NPR Panel 2 thank-you sent"
    assert "$" not in events[0]["fruit"]
    text, added = append_conversion_fruit("", events, today="2026-08-20")
    parsed = parse_fruit_ledger(text)
    assert parsed["fruit_count"] == 1
    assert parsed["last_fruit"] == "NPR Panel 2 thank-you sent"


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
