"""Operator brief routing — never collapse Morning Brief to ALWAYS_AVAILABLE."""

from src.action_intents import classify_tool_intent, message_needs_tools
from src.agent_loop import _DOMAIN_TOOL_MAP, _classify_agent_request
from src.tool_index import ALWAYS_AVAILABLE, MORNING_BRIEF_TOOLS, OPERATOR_BRIEF_TOOLS


def test_morning_brief_is_operator_brief_not_low_signal():
    result = _classify_agent_request([], "Morning Brief")
    assert "operator_brief" in result["domains"]
    assert result["low_signal"] is False


def test_focus_phrases_are_operator_brief():
    for msg in (
        "what have we been working on",
        "what's next today",
        "today's focus",
        "catch me up",
        "generate a morning brief",
        "Daily Brief",
    ):
        result = _classify_agent_request([], msg)
        assert "operator_brief" in result["domains"], msg
        assert result["low_signal"] is False, msg


def test_bare_brief_is_not_operator_brief():
    """Avoid false positives like 'brief me on this PDF'."""
    result = _classify_agent_request([], "brief me on this PDF")
    assert "operator_brief" not in result["domains"]


def test_operator_brief_tools_superset_of_always_available():
    pack = _DOMAIN_TOOL_MAP["operator_brief"]
    assert ALWAYS_AVAILABLE < (ALWAYS_AVAILABLE | pack)
    assert pack != set(ALWAYS_AVAILABLE)
    assert MORNING_BRIEF_TOOLS <= pack
    assert "manage_skills" in pack
    assert "web_search" in pack
    assert "manage_notes" in pack
    assert "manage_calendar" in pack
    assert "list_emails" in pack


def test_operator_brief_tools_includes_scheduled_allowlist():
    assert MORNING_BRIEF_TOOLS <= OPERATOR_BRIEF_TOOLS


def test_morning_brief_chat_escalates_to_agent():
    assert message_needs_tools("Morning Brief")
    intent = classify_tool_intent("Morning Brief")
    assert intent.needs_tools
    assert intent.category == "operator_brief"


def test_focus_phrases_chat_escalate():
    assert message_needs_tools("what have we been working on")
    assert message_needs_tools("catch me up")
    assert classify_tool_intent("what's next today").category == "operator_brief"
