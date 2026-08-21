"""Realtime voice function calling — curated tool set + session wiring."""

from pathlib import Path
import json

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
        "manage_memory",
    ):
        assert required in names


def test_manage_memory_schema_allows_pin_and_unpin():
    from services.voice.voice_tools import _MEMORY_ACTIONS

    schema = next(s for s in get_voice_tool_schemas() if s["name"] == "manage_memory")
    enum = schema["parameters"]["properties"]["action"]["enum"]
    for act in ("list", "add", "edit", "delete", "search", "pin", "unpin"):
        assert act in enum
        assert act in _MEMORY_ACTIONS
    assert "pin" in (schema.get("description") or "").lower()
    assert "does not delete" in (schema.get("description") or "").lower()


def test_pin_memory_item_toggles_without_delete(tmp_path):
    from src.memory import MemoryManager, pin_memory_item

    mgr = MemoryManager(str(tmp_path))
    entry = mgr.add_entry("Q3 retainer is $12k", category="fact", owner="tcam")
    mgr.save([entry])
    result = pin_memory_item(mgr, entry["id"], pinned=True, owner="tcam")
    assert result["ok"] is True
    assert result["pinned"] is True
    loaded = mgr.load_all()
    assert len(loaded) == 1
    assert loaded[0]["pinned"] is True
    assert loaded[0]["text"] == "Q3 retainer is $12k"
    un = pin_memory_item(mgr, entry["id"][:8], pinned=False, owner="tcam")
    assert un["ok"] is True
    assert un["pinned"] is False
    remaining = mgr.load_all()
    assert len(remaining) == 1
    assert remaining[0]["pinned"] is False
    assert remaining[0]["text"] == "Q3 retainer is $12k"


@pytest.mark.asyncio
async def test_manage_memory_pin_calls_pin_not_delete(monkeypatch):
    from services.voice import voice_tools

    pin_calls = []

    def fake_pin(memory_id, pinned=True, owner=None):
        pin_calls.append({"memory_id": memory_id, "pinned": pinned, "owner": owner})
        return {"ok": True, "pinned": pinned, "memory_id": memory_id}

    async def boom(*args, **kwargs):
        raise AssertionError("execute_tool_block must not run for pin")

    monkeypatch.setattr(voice_tools, "pin_memory_for_voice", fake_pin)
    monkeypatch.setattr("src.tool_execution.execute_tool_block", boom)

    out = await execute_voice_tool(
        "manage_memory",
        {"action": "pin", "memory_id": "probe-mem-1"},
        owner="tcam",
    )
    assert pin_calls == [{"memory_id": "probe-mem-1", "pinned": True, "owner": "tcam"}]
    assert "pinned" in out.lower()
    assert "deleted" not in out.lower()
    assert "Error" not in out

    pin_calls.clear()
    un = await execute_voice_tool(
        "manage_memory",
        {"action": "unpin", "memory_id": "probe-mem-1"},
        owner="tcam",
    )
    assert pin_calls == [{"memory_id": "probe-mem-1", "pinned": False, "owner": "tcam"}]
    assert "unpinned" in un.lower()
    assert "deleted" not in un.lower()


def test_jarvis_instructions_mention_memory_pin():
    from services.voice.realtime_gateway import _JARVIS_INSTRUCTIONS

    low = _JARVIS_INSTRUCTIONS.lower()
    assert "manage_memory" in low
    assert "action=pin" in low
    assert "does not delete" in low


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
    assert resolve_cmd_action("open_doc", "4f9a694f-7103-4ced-9798-3a701929bcbe")["ok"] is True
    assert resolve_cmd_action("open_note")["ok"] is True
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


# --- Human-gate confirm send (checklist / NPR draft; never SMTP / Upwork submit) ---


class _FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


class _FakeDb:
    def __init__(self, notes):
        self.notes = notes
        self.committed = False

    def query(self, model):
        return _FakeQuery(self.notes)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class _FakeNote:
    def __init__(self, nid, title, items=None, archived=False):
        self.id = nid
        self.title = title
        self.items = json.dumps(items) if items is not None else None
        self.archived = archived
        self.owner = "tcam"
        self.note_type = "checklist" if items is not None else "note"


def test_confirm_actions_are_whitelisted_not_submit():
    from services.voice.voice_tools import CONFIRM_SEND_ACTIONS, resolve_cmd_action

    for act in CONFIRM_SEND_ACTIONS:
        ok = resolve_cmd_action(act)
        assert ok["ok"] is True
        assert ok["action"] == act
    assert resolve_cmd_action("send_email")["ok"] is False
    assert resolve_cmd_action("submit")["ok"] is False
    schema = next(s for s in get_voice_tool_schemas() if s["name"] == "cmd_navigate")
    enum = schema["parameters"]["properties"]["action"]["enum"]
    for act in CONFIRM_SEND_ACTIONS:
        assert act in enum
    assert "never" in schema["description"].lower()
    assert "smtp" in schema["description"].lower()


def test_confirm_pack_sent_marks_checklist_items():
    from services.home.mycelia_feed import conversion_fruit_events
    from services.voice.voice_tools import confirm_human_send

    items = [{"text": f"Send {i:02d}", "done": False} for i in range(1, 6)]
    note = _FakeNote(
        "f1cf1f16-aaaa-bbbb-cccc-dddddddddddd",
        "Upwork Proposals — 5 To Send (HUMAN GATE)",
        items,
    )
    db = _FakeDb([note])
    result = confirm_human_send("confirm_pack_sent", owner="tcam", db=db)
    assert result["ok"] is True
    assert result["submit"] is False
    assert db.committed is True
    parsed = json.loads(note.items)
    assert all(it["done"] is True for it in parsed)
    assert "(sent)" in note.title.lower()
    rec = {"id": note.id, "title": note.title, "items": parsed}
    events = conversion_fruit_events(notes=[rec], documents=[])
    assert events
    assert "proposals sent" in events[0]["fruit"].lower()
    assert "smtp" not in (result.get("speech") or "").lower()
    assert "not submitting" in (result.get("speech") or "").lower()


def test_confirm_proposal_sent_ticks_first_unchecked():
    from services.voice.voice_tools import confirm_human_send

    items = [
        {"text": "Send 01", "done": True},
        {"text": "Send 02", "done": False},
        {"text": "Send 03", "done": False},
    ]
    note = _FakeNote(
        "f1cf1f16-aaaa",
        "Upwork Proposals — 5 To Send (HUMAN GATE)",
        items,
    )
    db = _FakeDb([note])
    result = confirm_human_send("confirm_proposal_sent", owner="tcam", db=db)
    assert result["ok"] is True
    assert result["submit"] is False
    parsed = json.loads(note.items)
    assert parsed[0]["done"] is True
    assert parsed[1]["done"] is True
    assert parsed[2]["done"] is False
    assert "(sent)" not in note.title.lower()


def test_confirm_npr_sent_marks_4be22ee3_then_next():
    from services.home.mycelia_feed import conversion_fruit_events
    from services.voice.voice_tools import confirm_human_send

    drafts = [
        _FakeNote("4be22ee3-aaaa-bbbb-cccc-ddddeeeeffff", "DRAFT · NPR Panel 2 — Thank-you · Greta"),
        _FakeNote("8504c427-aaaa-bbbb-cccc-ddddeeeeffff", "DRAFT · NPR Panel 2 — Thank-you · Kriti"),
        _FakeNote("80aa4a73-aaaa-bbbb-cccc-ddddeeeeffff", "DRAFT · NPR Panel 2 — Thank-you · Nicolette"),
    ]
    db = _FakeDb(drafts)
    first = confirm_human_send("confirm_npr_sent", owner="tcam", db=db)
    assert first["ok"] is True
    assert first["submit"] is False
    assert drafts[0].title.endswith("(sent)")
    assert "(sent)" not in drafts[1].title
    recs = [{"id": n.id, "title": n.title, "archived": n.archived} for n in drafts]
    events = conversion_fruit_events(notes=recs, documents=[])
    assert any("npr" in e["fruit"].lower() for e in events)

    second = confirm_human_send("confirm_npr_sent", owner="tcam", db=db)
    assert second["ok"] is True
    assert drafts[1].title.endswith("(sent)")
    assert "(sent)" not in drafts[2].title


def test_confirm_grant_packet_sent_marks_08e7c105():
    from services.home.mycelia_feed import append_conversion_fruit, conversion_fruit_events
    from services.voice.voice_tools import confirm_human_send

    items = [
        {"text": "Official URL", "done": False},
        {"text": "HUMAN GATE — do not submit without operator", "done": False},
    ]
    note = _FakeNote(
        "08e7c105-aaaa-bbbb-cccc-dddddddddddd",
        "Impact+ Doctoral — nomination gate",
        items,
    )
    db = _FakeDb([note])
    result = confirm_human_send("confirm_grant_packet_sent", owner="tcam", db=db)
    assert result["ok"] is True
    assert result["submit"] is False
    assert db.committed is True
    parsed = json.loads(note.items)
    assert all(it["done"] is True for it in parsed)
    assert "(sent)" in note.title.lower()
    rec = {"id": note.id, "title": note.title, "items": parsed}
    events = conversion_fruit_events(notes=[rec], documents=[])
    grant = next(e for e in events if "impact+" in e["fruit"].lower())
    assert grant["fruit"] == "Impact+ Doctoral nomination submitted"
    assert grant["evidence"] == "checklist 08e7c105"
    assert "$" not in grant["fruit"]
    text, added = append_conversion_fruit("", events, today="2026-08-20")
    assert added
    assert "- FRUIT: Impact+ Doctoral nomination submitted" in text
    assert "checklist 08e7c105" in text
    assert "$" not in text
    assert "cihr" in (result.get("speech") or "").lower()
    assert "not submitting" in (result.get("speech") or "").lower()

    again = confirm_human_send("confirm_grant_packet_sent", owner="tcam", db=db)
    assert again.get("already") is True
    assert again["submit"] is False


def test_confirm_grant_packet_open_does_not_invent_fruit():
    from services.home.mycelia_feed import conversion_fruit_events

    notes = [{
        "id": "08e7c105-aaaa-bbbb-cccc-dddddddddddd",
        "title": "Impact+ Doctoral — nomination gate",
        "items": [{"text": "HUMAN GATE", "done": False}],
    }]
    events = conversion_fruit_events(notes=notes, documents=[])
    assert not any("impact+" in e["fruit"].lower() for e in events)


@pytest.mark.asyncio
async def test_cmd_navigate_confirm_pack_does_not_submit(monkeypatch):
    from services.voice import voice_tools

    called = {}

    def _fake_confirm(action, owner=None, db=None):
        called["action"] = action
        called["owner"] = owner
        return {
            "ok": True,
            "submit": False,
            "speech": "Logged the send pack as sent. Not submitting to Upwork.",
        }

    monkeypatch.setattr(voice_tools, "confirm_human_send", _fake_confirm)
    out = await execute_voice_tool("cmd_navigate", {"action": "confirm_pack_sent"}, owner="tcam")
    assert called["action"] == "confirm_pack_sent"
    assert "Not submitting" in out
    assert "Error" not in out


def test_confirm_send_never_calls_smtp_or_upwork_submit():
    import inspect

    from services.voice import voice_tools

    src = inspect.getsource(voice_tools.confirm_human_send)
    low = src.lower()
    assert "send_email" not in low
    assert "smtp" not in low or "not sending smtp" in low
    assert "upwork" in low  # mentioned only as not-submitting
    assert "cihr" in low  # mentioned only as not-submitting
    assert "submit" in low
    assert "process_job" not in low
    assert "mark_applied" not in low


def test_jarvis_confirm_send_shortcut_phrases():
    rt = (ROOT / "static" / "js" / "voiceRealtime.js").read_text(encoding="utf-8")
    start = rt.index("function maybeDispatchCmdShortcut")
    end = rt.index("function isIOS")
    body = rt[start:end]
    assert "confirm_pack_sent" in body
    assert "confirm_proposal_sent" in body
    assert "confirm_npr_sent" in body
    assert "confirm_grant_packet_sent" in body
    assert r"i sent (the )?(upwork )?(send )?pack" in body
    assert r"mark (the )?(upwork )?(send )?pack (as )?(done|sent)" in body
    assert r"check off (the )?(upwork )?(send )?pack" in body
    assert r"i sent proposal (1|one)" in body
    assert r"i sent (the )?(npr )?(thank[- ]you)" in body
    assert r"i submitted (the )?nomination" in body
    assert r"i submitted (the )?(canada )?(impact\+|impact plus)" in body
    assert "confirmSend: true" in body
    assert "never bridge" in body.lower() or "must not SMTP" in body
    assert "send_email" not in body
    assert "smtp" in body.lower()

    cmd = (ROOT / "static" / "js" / "cmdCenter.js").read_text(encoding="utf-8")
    hit = cmd[cmd.index("if (action === 'confirm_pack_sent'"): cmd.index("if (action === 'speak_true')")]
    assert "/api/voice/cmd-action" in hit
    assert "_fetchData" in hit
    assert "_paint" in hit
    assert "send_email" not in hit
    assert "Not submitting" in hit
    assert "_activateVoiceDelegate" not in hit


def test_money_move_confirm_sent_hud_buttons():
    """CORE Money Move HUD Confirm sent uses the same cmd-actions as Jarvis shortcuts."""
    cmd = (ROOT / "static" / "js" / "cmdCenter.js").read_text(encoding="utf-8")
    assert "function _heroNeedleKind" in cmd
    assert 'id="cmd-hero-confirm-sent"' in cmd
    assert 'id="cmd-hero-confirm-one"' in cmd
    assert "Confirm sent" in cmd
    assert "Confirm one proposal" in cmd

    kind_fn = cmd[cmd.index("const SEND_PACK_DOC_PREFIX"): cmd.index("function _renderHeroCtaRow")]
    assert "hero.confirm_action" in kind_fn
    assert "confirm_npr_sent" in kind_fn
    assert "confirm_pack_sent" in kind_fn
    assert "confirm_grant_packet_sent" in kind_fn
    assert kind_fn.index("hero.confirm_action") < kind_fn.index("hero.action")
    assert "return 'npr'" in kind_fn
    assert "return 'pack'" in kind_fn
    assert "return 'grant'" in kind_fn
    assert "4f9a694f" in kind_fn
    assert "f1cf1f16" in kind_fn
    assert "08e7c105" in kind_fn
    assert "4be22ee3" in kind_fn

    row_fn = cmd[cmd.index("function _renderHeroCtaRow"): cmd.index("function _applyHeroToDom")]
    assert "confirm_one_action" in row_fn
    assert 'data-action="confirm_pack_sent"' in row_fn
    assert 'data-action="confirm_npr_sent"' in row_fn
    assert 'data-action="confirm_proposal_sent"' in row_fn
    assert 'data-action="confirm_grant_packet_sent"' in row_fn
    assert "Confirm sent" in row_fn
    assert "send_email" not in row_fn
    assert "CIHR" in row_fn

    build = cmd[cmd.index("function _buildHTML"): cmd.index("function _tickClock")]
    assert "_renderHeroCtaRow(hero)" in build

    start = cmd.index("const target = e.target.closest('[data-action]')")
    end = cmd.index("const heroHit = target.id === 'cmd-hero'")
    click = cmd[start:end]
    assert "CONFIRM_SEND_ACTIONS" in click
    assert "_runAction(confirmAct" in click
    assert "_activateVoiceDelegate" not in click
    assert "send_email" not in click
