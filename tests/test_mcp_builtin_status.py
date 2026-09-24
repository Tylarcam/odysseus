"""Builtin MCP servers must be listable and reconnectable without a DB row."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.builtin_mcp import _BUILTIN_SERVERS, builtin_status_entries


def test_builtin_status_entries_includes_email():
    mcp = MagicMock()
    mcp.get_server_status.side_effect = lambda sid: (
        {"status": "connected", "tool_count": 9} if sid == "email"
        else {"status": "disconnected", "tool_count": 0}
    )
    entries = builtin_status_entries(mcp)
    ids = {e["id"] for e in entries}
    assert "email" in ids
    assert set(_BUILTIN_SERVERS) <= ids
    email = next(e for e in entries if e["id"] == "email")
    assert email["name"] == "Built-in: Email"
    assert email["status"] == "connected"
    assert email["tool_count"] == 9
    assert email["builtin"] is True


def test_builtin_status_entries_disconnected_when_manager_missing():
    entries = builtin_status_entries(None)
    email = next(e for e in entries if e["id"] == "email")
    assert email["status"] == "disconnected"
    assert email["tool_count"] == 0


def test_manage_mcp_reconnect_builtin_without_db_row():
    from src.tool_implementations import do_manage_mcp

    fake_mcp = MagicMock()
    fake_mcp.disconnect_server = AsyncMock()
    fake_mcp.is_builtin.return_value = True
    fake_mcp._reconnect_builtin = AsyncMock(return_value=True)
    fake_mcp.get_server_status.return_value = {"tool_count": 9, "status": "connected"}

    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = None

    with patch("src.tool_implementations.get_mcp_manager", return_value=fake_mcp), \
         patch("core.database.SessionLocal", return_value=fake_db):
        result = asyncio.run(do_manage_mcp(
            '{"action":"reconnect","server_id":"email"}'
        ))

    assert result["exit_code"] == 0
    fake_mcp._reconnect_builtin.assert_awaited_once_with("email")
    assert "builtin" in result["response"]
