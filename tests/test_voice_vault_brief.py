"""Vault brief for Jarvis / Realtime voice context injection."""

from pathlib import Path

from services.voice.realtime_gateway import RealtimeVoiceGateway
from services.voice.vault_brief import MAX_BRIEF_CHARS, build_brief_script, format_vault_brief


ROOT = Path(__file__).resolve().parent.parent


def test_build_brief_script_covers_overdue_priority_agents_calendar():
    script = build_brief_script(
        hero={"label": "Prod", "title": "Clear overdues", "unit": "OVERDUE", "value": 5, "branch": "prod"},
        priority_queue=[
            {
                "title": "RSVP Thesis Defence",
                "status": "overdue",
                "overdue_days": 4,
                "branch": "prod",
                "kind": "note",
            },
            {"title": "Alkira cover letter", "status": "due", "branch": "agency", "kind": "job"},
        ],
        counts={"handoffs_in_progress": 2, "handoffs_attention": 1},
        agenda={
            "overdue": [{"title": "RSVP Thesis Defence"}],
            "next_event": {"title": "Aether standup", "start": "2099-01-15T18:00:00+00:00"},
            "due_soon": [],
        },
        overdue_count=5,
    )
    assert 3 <= len(script) <= 6
    for line in script:
        assert "text" in line and line["text"].strip()
        assert "highlight" in line
        assert line["highlight"]["type"] in ("overdue", "domain", "all")
        if line["highlight"]["type"] == "domain":
            assert line["highlight"].get("domain")

    blob = " ".join(line["text"] for line in script)
    assert "5 items need" in blob or "attention" in blob.lower()
    assert "RSVP Thesis Defence" in blob
    assert "in flight" in blob.lower()
    assert "Aether standup" in blob
    assert "Needs you" in blob
    # Speech-friendly: no ISO timestamps in spoken text.
    assert "2099-01-15" not in blob
    assert "T18:" not in blob
    assert script[0]["highlight"]["type"] == "overdue"
    assert script[-1]["highlight"]["type"] == "all"


def test_build_brief_script_empty_deck_still_speaks():
    script = build_brief_script()
    assert 3 <= len(script) <= 6
    blob = " ".join(line["text"] for line in script).lower()
    assert "overdue" in blob or "clear" in blob or "green" in blob
    assert "vault" in blob
    assert "zero agents" not in blob
    assert script[-1]["highlight"]["type"] == "all"


def test_build_brief_script_mentions_research_not_success_jobs():
    script = build_brief_script(
        research=[{
            "id": "rp-canvas",
            "title": "Visual Storytelling Canvas",
            "status": "done",
            "bullets": ["Story beats beat decks"],
        }],
        failed_runs=[{"name": "Email Tags", "status": "error"}],
        overdue_count=0,
        counts={"handoffs_in_progress": 0, "jobs_review": 0},
    )
    blob = " ".join(line["text"] for line in script)
    assert "Visual Storytelling Canvas" in blob
    assert "Email Tags" in blob
    assert "Chat Sessions Tidy" not in blob
    assert "doctrine" not in blob.lower()


def test_build_brief_script_domain_highlight_from_branch():
    script = build_brief_script(
        priority_queue=[{"title": "Pick up handoff", "status": "due", "branch": "relay", "kind": "handoff"}],
        counts={"handoffs_in_progress": 0},
        overdue_count=0,
    )
    priority_line = next(l for l in script if "Pick up handoff" in l["text"])
    assert priority_line["highlight"]["type"] == "domain"
    assert priority_line["highlight"]["domain"] == "RELAY"


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
