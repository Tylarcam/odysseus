"""Realtime voice function calling — curated tool set + session wiring."""

from pathlib import Path

import pytest

from services.voice.realtime_gateway import RealtimeVoiceGateway
from services.voice.voice_tools import (
    VOICE_TOOL_NAMES,
    _flatten_result,
    execute_voice_tool,
    get_voice_tool_schemas,
)

ROOT = Path(__file__).resolve().parent.parent


def test_voice_tool_schemas_are_realtime_flattened():
    schemas = get_voice_tool_schemas()
    names = {s["name"] for s in schemas}
    assert names == set(VOICE_TOOL_NAMES)
    for s in schemas:
        assert s["type"] == "function"
        assert "function" not in s  # flattened, not chat-completions nested
        assert s["parameters"]["type"] == "object"


def test_voice_tools_exclude_dangerous_tools():
    names = {s["name"] for s in get_voice_tool_schemas()}
    for banned in ("bash", "python", "write_file", "edit_file", "manage_settings", "send_email"):
        assert banned not in names


def test_voice_tools_include_jarvis_surface():
    names = {s["name"] for s in get_voice_tool_schemas()}
    for required in (
        "list_emails",
        "read_email",
        "manage_research",
        "list_handoffs",
        "process_job_application",
        "cmd_navigate",
        "manage_notes",
    ):
        assert required in names


@pytest.mark.asyncio
async def test_list_handoffs_formats_buckets(monkeypatch):
    from services.voice import voice_tools

    monkeypatch.setattr(
        voice_tools,
        "list_handoffs_for_voice",
        lambda owner=None, bucket="needs_attention", limit=5: (
            "Handoffs: 1 waiting · 0 in progress · 0 done\n"
            "Top 1 (needs_attention):\n"
            "- Swarm Health → cursor [queued] id=abcd1234"
        ),
    )
    out = await execute_voice_tool("list_handoffs", {"bucket": "needs_attention"}, owner="tcam")
    assert "Swarm Health" in out
    assert "1 waiting" in out


@pytest.mark.asyncio
async def test_execute_voice_tool_rejects_non_whitelisted():
    with pytest.raises(ValueError):
        await execute_voice_tool("bash", {"command": "rm -rf /"})


@pytest.mark.asyncio
async def test_cmd_navigate_resolves_safe_actions():
    from services.voice.voice_tools import resolve_cmd_action

    assert resolve_cmd_action("agent_bin")["ok"] is True
    assert resolve_cmd_action("jobs")["ok"] is True
    bad = resolve_cmd_action("run_shell")
    assert bad["ok"] is False


@pytest.mark.asyncio
async def test_process_job_blocks_mutating_actions_in_voice():
    out = await execute_voice_tool("process_job_application", {"action": "tailor"})
    assert "Error" in out
    assert "list/status" in out or "agent mode" in out.lower()


def test_flatten_result_prefers_output_keys_and_truncates():
    assert _flatten_result({"output": "hello", "exit_code": 0}) == "hello"
    assert _flatten_result({"results": "found it"}) == "found it"
    assert _flatten_result({"error": "boom"}) == "Error: boom"
    long = _flatten_result({"output": "x" * 20000})
    assert len(long) < 20000
    assert long.endswith("[output truncated]")


def test_session_config_includes_tools_when_enabled(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({"voice_tools_enabled": True})
    assert cfg.get("tool_choice") == "auto"
    names = {t["name"] for t in cfg.get("tools", [])}
    assert "web_search" in names


def test_session_config_omits_tools_when_disabled(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({"voice_tools_enabled": False})
    assert "tools" not in cfg
    assert "agent mode" in cfg["instructions"]


def test_session_config_omits_tools_for_agent_bridge(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({"voice_tools_enabled": True}, agent_bridge=True)
    assert "tools" not in cfg
    assert cfg["turn_detection"]["create_response"] is False


def test_stats_reports_tools_flag_without_leaking_schemas(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    gw = RealtimeVoiceGateway()
    stats = gw.get_stats({})
    assert stats["tools_enabled"] is True
    assert "tools" not in stats


# --- Client + settings UI contracts (static asserts) ---


def test_client_handles_realtime_function_calls():
    js = (ROOT / "static" / "js" / "voiceRealtime.js").read_text(encoding="utf-8")
    assert "response.function_call_arguments.done" in js
    assert "/api/voice/tool-call" in js
    assert "function_call_output" in js
    # Agent mode strips voice tools (agent loop owns tools there)
    assert "session.tools = []" in js


def test_audio_settings_tab_exists():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'data-settings-tab="audio"' in html
    assert 'data-settings-panel="audio"' in html
    # Voice card + relocated TTS/STT cards all live in the audio panel
    for el_id in (
        "set-voiceChatEnabledToggle", "set-voiceRealtimeToggle",
        "set-voiceToolsToggle", "set-voiceInstructionsInput",
        "set-ttsProviderSelect", "set-sttProviderSelect",
    ):
        assert el_id in html


def test_settings_js_wires_voice_chat_settings():
    js = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    assert "initVoiceChatSettings" in js
    assert "voice_realtime_instructions" in js
    assert "voice_tools_enabled" in js
