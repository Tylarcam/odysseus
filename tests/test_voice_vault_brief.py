"""Vault brief for Jarvis / Realtime voice context injection."""

from pathlib import Path

from services.voice.realtime_gateway import RealtimeVoiceGateway
from services.voice.vault_brief import MAX_BRIEF_CHARS, format_vault_brief


ROOT = Path(__file__).resolve().parent.parent


def test_format_vault_brief_includes_hero_and_branches():
    text = format_vault_brief(
        hero={
            "label": "Relay",
            "title": "3 handoffs waiting",
            "explain": "Agent bin needs attention",
            "cta_label": "Open agent bin",
        },
        priority_queue=[
            {"title": "Handoff A", "kind": "handoff"},
            {"title": "Job B", "kind": "job"},
        ],
        counts={"handoffs_attention": 3, "jobs_ready": 2, "notes": 10},
        branch_health=[
            {"id": "relay", "label": "Relay", "state": "attention", "summary": "3 waiting"},
            {"id": "agency", "label": "Agency", "state": "ok", "summary": "2 ready"},
            {"id": "voice", "label": "Voice", "state": "ok", "summary": "realtime"},
        ],
        pinned_facts=["Prefers concise answers", "Works in Vancouver"],
    )
    assert "Vault brief" in text
    assert "3 handoffs waiting" in text
    assert "Relay" in text
    assert "Agency" in text
    assert "Prefers concise answers" in text
    assert len(text) <= MAX_BRIEF_CHARS


def test_format_vault_brief_clips_to_max_chars():
    huge = "x" * 5000
    text = format_vault_brief(hero={"title": huge, "label": "Hero"})
    assert len(text) <= MAX_BRIEF_CHARS


def test_build_voice_instructions_includes_jarvis_and_brief(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_brief(owner=None):
        return {"markdown": "# Vault brief (live CMD Center)\n\n- test brief fire\n"}

    monkeypatch.setattr(
        "services.voice.vault_brief.build_vault_brief",
        fake_brief,
    )
    monkeypatch.setattr(
        "services.voice.realtime_gateway._load_pinned_memory_facts",
        lambda owner=None: [],
    )

    gw = RealtimeVoiceGateway()
    instructions = gw.build_voice_instructions({}, owner="tcam", jarvis=True)
    assert "Jarvis" in instructions
    assert "test brief fire" in instructions


def test_session_config_injects_vault_brief(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "services.voice.vault_brief.build_vault_brief",
        lambda owner=None: {"markdown": "# Vault brief\n\nwhat's on fire\n"},
    )
    monkeypatch.setattr(
        "services.voice.realtime_gateway._load_pinned_memory_facts",
        lambda owner=None: [],
    )
    gw = RealtimeVoiceGateway()
    cfg = gw.build_session_config({"voice_tools_enabled": False}, owner="tcam")
    assert "what's on fire" in cfg["instructions"]
    assert "Jarvis" in cfg["instructions"]


def test_client_wires_vault_brief_and_jarvis():
    rt = (ROOT / "static" / "js" / "voiceRealtime.js").read_text(encoding="utf-8")
    assert "/api/voice/vault-brief" in rt
    assert "setJarvisMode" in rt
    assert "reapplyVaultBrief" in rt
    assert "setVoiceLock" in rt
    assert "maybeDispatchCmdShortcut" in rt or "cmd.shortcut" in rt
    assert "create_response: !_voiceLocked && !agent" in rt

    cmd = (ROOT / "static" / "js" / "cmdCenter.js").read_text(encoding="utf-8")
    assert "setJarvisMode" in cmd
    assert "reapplyVaultBrief" in cmd
    assert "cmd-audio-lock" in cmd
    assert "Jarvis stays armed" in cmd

    ptt = (ROOT / "static" / "js" / "voiceKeyboardPtt.js").read_text(encoding="utf-8")
    assert "Alt+Shift+V" in ptt or "altKey && e.shiftKey" in ptt
    assert "toggleVoiceLock" in ptt

    chat = (ROOT / "static" / "js" / "voiceChat.js").read_text(encoding="utf-8")
    assert "cmd_jarvis" in chat

    tel = (ROOT / "static" / "js" / "voiceTelemetry.js").read_text(encoding="utf-8")
    assert "setSource" in tel

    routes = (ROOT / "routes" / "voice_routes.py").read_text(encoding="utf-8")
    assert "/vault-brief" in routes
    assert "cmd-action" in routes
