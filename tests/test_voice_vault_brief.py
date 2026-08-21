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


HARVEST_MD = """# CEO Brief — 2026-08-20

_Generated 09:00 from the morning chron wave._

## Top 3 actions that move the needle
1. **SUBMIT Prelim — SWE Product** — hygiene item 1; materials ready.
2. **SEND NPR Panel 2 thank-you emails** — drafts ready.
3. **Close Q3 residue** — checkbox still open.

## What's upcoming
Calendar (next 48h):
- tomorrow 10:00 — Aether standup
Due soon:
- Pay insurance
Overdue:
- RSVP Thesis Defence

## Job pipeline
No job applications need attention.

## Handoffs in flight
_None._

## Research findings (Rhizo)
_Rhizo hasn't filed a research brief today._

## Fruit ledger (Herald)
_No fruit ledger entry yet._

## Recent chron outputs
_No successful chron runs in the recent window._
"""


def test_build_brief_script_harvest_leads_with_top3_not_hud_hero():
    script = build_brief_script(
        hero={"label": "Prod", "title": "Search as Code", "unit": "DIRECTIVES", "branch": "prod"},
        money_hero={
            "title": "SUBMIT Prelim — SWE Product",
            "true_line": "Top money move: SUBMIT Prelim — SWE Product.",
            "unit": "TOP 3",
            "branch": "prod",
        },
        ceo_brief={"status": "ready", "content": HARVEST_MD, "title": "CEO Brief — 2026-08-20"},
        priority_queue=[{"title": "Search as Code", "status": "due", "branch": "prod"}],
        overdue_count=0,
        research=[{"title": "Open Notebook slim script", "status": "done"}],
    )
    blob = " ".join(line["text"] for line in script)
    assert "SUBMIT Prelim" in blob
    assert "Top money move" in blob
    assert "Top 3:" in blob
    assert "Needs you:" in blob
    assert "Can wait:" in blob
    assert "That's the state of the V.A.U.L.T." in blob
    assert "Search as Code" not in blob
    assert "Open Notebook" not in blob
    assert "What changed" not in blob
    assert "2099" not in blob
    assert 3 <= len(script) <= 6


def test_build_brief_script_speaks_fruit_count_when_present():
    harvest = HARVEST_MD.replace(
        "_No fruit ledger entry yet._",
        "```\n### 2026-08-20 · Herald\n"
        "- FRUIT: Upwork Send Pack — 5 proposals sent\n"
        "- EVIDENCE: checklist f1cf1f16 all done\n```",
    )
    script = build_brief_script(
        money_hero={
            "title": "SEND NPR Panel 2 thank-you emails",
            "spoken_needle": "Top money move: SEND NPR Panel 2 thank-you emails.",
            "true_line": (
                "Top money move: SEND NPR Panel 2 thank-you emails. "
                "1 fruit on the ledger. Last: Upwork Send Pack — 5 proposals sent."
            ),
            "fruit_count": 1,
            "last_fruit": "Upwork Send Pack — 5 proposals sent",
            "unit": "TOP 3",
            "branch": "prod",
        },
        ceo_brief={"status": "ready", "content": harvest, "title": "CEO Brief — 2026-08-20"},
    )
    blob = " ".join(line["text"] for line in script)
    assert "1 fruit on the ledger" in blob
    assert "Upwork Send Pack" in blob
    assert "don't invent fruit" not in blob.lower()
    assert "do not invent fruit" not in blob.lower()


def test_format_vault_brief_includes_money_needle_and_top3():
    text = format_vault_brief(
        hero={
            "label": "Directives",
            "title": "Search as Code",
            "explain": "10 open directives",
        },
        money_hero={
            "true_line": "Top money move: SUBMIT Prelim — SWE Product.",
            "title": "SUBMIT Prelim — SWE Product",
        },
        ceo_brief={"status": "ready", "content": HARVEST_MD},
        priority_queue=[{"title": "Handoff A", "kind": "handoff"}],
        counts={"handoffs_attention": 1},
    )
    assert "Search as Code" in text
    assert "Money needle" in text
    assert "SUBMIT Prelim" in text
    assert "Today's Top 3" in text
    assert "SEND NPR" in text
    assert len(text) <= MAX_BRIEF_CHARS


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
    assert 'data-core-lens="full_picture"' in cmd
    assert 'data-core-lens="money_move"' in cmd
    assert "coreLens: 'full_picture'" in cmd
    assert "payload.money_hero" in cmd
    speak = cmd[cmd.index("function _speakHeroTrue"): cmd.index("function _briefHasFullPicture")]
    assert "onMoneyMove" in speak
    assert "payload.money_hero" in speak
    assert "_coreLens === 'money_move'" in speak
    paint = cmd[cmd.index("function _paint()"): cmd.index("function _forceCloseCmdCenter")]
    assert "_speakHeroTrue" not in paint
    assert "_fireBrief" not in paint
    assert "runBrief" not in paint
    ceo = cmd[cmd.index("if (action === 'ceo_brief')"): cmd.index("// DISABLED: Docker Odysseus")]
    assert "_speakHeroTrue()" not in ceo
    assert "runBrief" not in ceo
    assert "_fireBrief" not in ceo
    assert "audio-brief" not in ceo
    fire = cmd[cmd.index("function _fireBrief"): cmd.index("function _wireClicks")]
    assert "brief_script" in fire
    assert "Listen" in fire or "Harvest-ranked" in fire

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
