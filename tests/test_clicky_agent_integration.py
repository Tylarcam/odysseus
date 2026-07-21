"""Simulation tests for Clicky + CMD Center agent integration (handoff 2026-07-08)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.agent_loop import TOOL_SECTIONS, _API_AGENT_RULES
from src.ai_interaction import do_ui_control
from src.tool_index import BUILTIN_TOOL_DESCRIPTIONS


REPO = Path(__file__).resolve().parent.parent
AGENT_LOOP_SRC = (REPO / "src" / "agent_loop.py").read_text(encoding="utf-8")
CMD_CENTER_SRC = (REPO / "services" / "home" / "cmd_center.py").read_text(encoding="utf-8")
SLASH_SRC = (REPO / "static" / "js" / "slashCommands.js").read_text(encoding="utf-8")


def test_open_panel_cmd_center_resolves():
    result = asyncio.run(do_ui_control("open_panel cmd-center"))
    assert result["ui_event"] == "open_panel"
    assert result["panel"] == "cmd-center"


def test_open_panel_vault_alias_resolves():
    result = asyncio.run(do_ui_control("open_panel vault"))
    assert result["ui_event"] == "open_panel"
    assert result["panel"] == "cmd-center"


def test_open_panel_unknown_lists_cmd_center():
    result = asyncio.run(do_ui_control("open_panel not-a-real-panel"))
    assert "cmd-center" in result["error"]


def test_agent_loop_documents_docker_clicky_limit():
    assert "DISABLED (Docker)" in AGENT_LOOP_SRC
    assert "start-clicky.ps1" in AGENT_LOOP_SRC
    assert "cmd-center" in AGENT_LOOP_SRC


def test_runtime_api_agent_rules_redirect_clicky_to_host_script():
    assert "DISABLED (Docker)" in _API_AGENT_RULES
    assert "start-clicky.ps1" in _API_AGENT_RULES
    assert "do NOT call `app_api` POST `/api/clicky/start`" in _API_AGENT_RULES


def test_agent_loop_ui_control_section_mentions_cmd_center():
    ui = TOOL_SECTIONS["ui_control"]
    assert "cmd-center" in ui
    assert "vault" in ui


def test_agent_loop_app_api_section_documents_docker_clicky_limit():
    app_api = TOOL_SECTIONS["app_api"]
    assert "DISABLED (Docker)" in app_api
    assert "start-clicky.ps1" in app_api


def test_tool_index_app_api_description_documents_docker_clicky_limit():
    desc = BUILTIN_TOOL_DESCRIPTIONS["app_api"]
    assert "DISABLED (Docker)" in desc
    assert "start-clicky.ps1" in desc


def test_tool_index_ui_control_description_mentions_cmd_center():
    assert "cmd-center" in BUILTIN_TOOL_DESCRIPTIONS["ui_control"]
    assert "vault" in BUILTIN_TOOL_DESCRIPTIONS["ui_control"]


def test_chat_stream_dispatches_cmd_center_panel():
    js = (REPO / "static" / "js" / "chatStream.js").read_text(encoding="utf-8")
    assert "panel === 'cmd-center'" in js
    assert "import('./cmdCenter.js')" in js
    assert "openCmdCenter" in js


def test_cmd_center_start_clicky_button_disabled():
    assert "DISABLED" in CMD_CENTER_SRC
    active = [ln for ln in CMD_CENTER_SRC.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert not any('"action": "start_clicky"' in ln for ln in active)


def test_slash_clicky_command_disabled():
    assert "DISABLED" in SLASH_SRC
    active = [ln for ln in SLASH_SRC.splitlines() if ln.strip() and not ln.lstrip().startswith("//")]
    assert not any("handler: _cmdStartClicky" in ln for ln in active)
    assert not any("import { launchClicky }" in ln for ln in active)
