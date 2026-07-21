"""Tests for handoff packet builders."""

from src.handoff_packet import (
    build_handoff_content,
    build_note_handoff_fields,
    handoff_doc_title,
    normalize_target,
    pickup_hint,
)


def test_normalize_target_aliases():
    assert normalize_target("cursor-ide") == "cursor"
    assert normalize_target("claude-code") == "claude"
    assert normalize_target("brudda") == "hermes"


def test_build_note_handoff_fields_from_checklist():
    fields = build_note_handoff_fields({
        "id": "abc123",
        "title": "Ship handoff button",
        "note_type": "todo",
        "items": [
            {"text": "Wire toast", "done": True},
            {"text": "Add API", "done": False},
        ],
    })
    assert fields["goal"] == "Ship handoff button"
    assert "Wire toast" in fields["done"]
    assert any("checklist" in step.lower() for step in fields["next_steps"])
    assert "Ship handoff button" in fields["note_body"]


def test_build_handoff_content_sections():
    content = build_handoff_content(
        source="odysseus",
        target="cursor",
        goal="Test goal",
        context=["Note ID: n1"],
        done=["Already done"],
        next_steps=["Do the thing"],
        note_body="# Test goal\n\nBody",
    )
    assert content.startswith("---")
    assert "## Goal" in content
    assert "## Next steps" in content
    assert "## Notes" in content


def test_build_handoff_content_hermes_bootstrap():
    content = build_handoff_content(
        source="odysseus",
        target="hermes",
        goal="Probe Hermes relay",
    )
    assert "target: hermes" in content
    assert "handoff_api.py list --pending" in content


def test_pickup_hint():
    assert pickup_hint("cursor", "doc-1") == "Pick up handoff doc-1"
