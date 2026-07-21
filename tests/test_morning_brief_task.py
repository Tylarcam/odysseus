"""Morning brief scheduled task — empty-response detection and tool allowlist."""

from src.task_scheduler import (
    MORNING_BRIEF_TOOLS,
    _EMPTY_AGENT_RESPONSE,
    _is_morning_brief_task,
    is_empty_agent_response,
)


def test_is_empty_agent_response_detects_fallback():
    assert is_empty_agent_response(_EMPTY_AGENT_RESPONSE)
    assert is_empty_agent_response("(no output)")
    assert is_empty_agent_response("")
    assert is_empty_agent_response("   ")


def test_is_empty_agent_response_accepts_real_brief():
    text = "# Morning Brief — 2026-06-14\n\n## Executive Summary\nShip the sprint."
    assert not is_empty_agent_response(text)


def test_morning_brief_tools_include_mcp_email():
    assert "mcp__email__list_emails" in MORNING_BRIEF_TOOLS
    assert "manage_notes" in MORNING_BRIEF_TOOLS
    assert "app_api" in MORNING_BRIEF_TOOLS


def test_is_morning_brief_task_name():
    class T:
        name = "Ras Morning Brief"
    assert _is_morning_brief_task(T())
    class T2:
        name = "Email Calendar Events"
    assert not _is_morning_brief_task(T2())
