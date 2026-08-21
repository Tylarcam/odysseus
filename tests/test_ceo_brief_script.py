"""CEO brief full-picture harvest: Top 3 inside complete sections, swarm excerpt kept."""

from datetime import date
from pathlib import Path

from services.documents.ceo_brief_script import (
    classify_task_run,
    collect_grant_calls,
    compose_ceo_brief_markdown,
    extract_grant_calls_from_text,
    find_grant_packet,
    harvest_fruit_ledger_text,
    is_full_picture_brief,
    rank_money_candidates,
)
from services.home.cmd_center import _build_money_hero
from services.home.mycelia_feed import parse_top3


SWARM_EXCERPT = """# Swarm Plan — 2026-07-31 (Friday)

## SENSED
- Canonical blackboard still stuck on Top 3 from 2026-07-12.

## Top 3 (2026-07-31)
1. **SUBMIT Prelim — SWE Product** — hygiene item 1; materials ready.
2. **SEND NPR Panel 2 thank-you emails** — drafts ready.
3. **Close Q3 residue** — checkbox still open.
"""

RESEARCH_EXCERPT = (
    "# Strategic War-Gaming for LLM Intelligence Distillation\n"
    "## 1. TASK / AIM / OBJECTIVE\n"
    "Maximize return on frontier model access.\n"
)

LEDGER_EXCERPT = (
    "# Fruit Ledger\n"
    "_None since swarm inception._\n"
)


def test_classify_task_run_exceptions():
    assert classify_task_run({"status": "error", "result": "boom"}) == "failed"
    assert classify_task_run({"status": "success", "result": "timed out after 30s"}) == "timeout"
    assert classify_task_run({"status": "skipped", "result": "morning harvest not ready"}) == "missed"
    assert classify_task_run({"status": "success", "result": "tidied 3"}) == "success"
    assert classify_task_run({"status": "skipped", "result": "nothing to do"}) == "silence"


def test_compose_full_picture_keeps_harvest_dump_and_ranked_top3():
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-18",
        generated_at="09:00",
        events=[{"start": "tomorrow 10:00", "title": "Standup"}],
        due_soon=[{"title": "Pay insurance", "due_date": "2026-08-19"}],
        overdue=[{"title": "RSVP Thesis Defence"}],
        jobs={
            "headline": "2 jobs need attention",
            "needs_review": [{"company": "Alkira", "role": "Engineer"}],
            "ready_to_apply": [{"company": "Acme", "role": "PM"}],
        },
        handoffs={"needs_attention": [{"title": "Handoff A", "handoff_target": "cursor"}]},
        runs=[
            {"name": "Email Tags", "status": "error", "result": "boom", "at": "2026-08-18T08:00:00"},
            {
                "name": "Chat Sessions Tidy",
                "status": "success",
                "result": "tidied 3 sessions",
                "at": "2026-08-18T08:05:00",
            },
            {"name": "Memory Tidy", "status": "success", "result": "ok", "at": "2026-08-18T08:06:00"},
        ],
        next_run={"name": "Email AI Auto Reply", "next_run": "2026-08-19T06:00:00"},
        substrate_txt=SWARM_EXCERPT,
        research_txt=RESEARCH_EXCERPT,
        ledger_txt=LEDGER_EXCERPT,
    )
    assert "## Top 3 actions that move the needle" in md
    assert "## Inbound opportunity" in md
    assert "## What's upcoming" in md
    assert "## Job pipeline" in md
    assert "## Handoffs in flight" in md
    assert "## Research findings (Rhizo)" in md
    assert "## Fruit ledger (Herald)" in md
    assert "## Recent chron outputs" in md
    assert "## Headline" not in md
    assert "## Needs you" not in md
    assert "## Can wait" not in md
    assert "_Generated 09:00 from the morning chron wave._" in md
    top3_block = md.split("## Top 3 actions that move the needle", 1)[1].split("## What's upcoming", 1)[0]
    assert "1. **SUBMIT Prelim — SWE Product**" in top3_block
    assert "2. **SEND NPR Panel 2 thank-you emails**" in top3_block
    assert "No tagged grant, proposal, invoice, or paid inbound" in top3_block
    assert "No grant/RFP on file" in top3_block
    assert "SEND NPR Panel 2 thank-you emails" in top3_block.split("## Inbound opportunity", 1)[-1]
    assert "From the Swarm Plan / blackboard (Sporangium):" in top3_block
    assert "Canonical blackboard still stuck" in top3_block
    assert "Standup" in md
    assert "Pay insurance" in md
    assert "RSVP Thesis Defence" in md
    assert "Alkira" in md
    assert "Acme" in md
    assert "Handoff A → cursor" in md
    assert "Strategic War-Gaming" in md
    assert "## Fruit ledger (Herald)" in md
    assert "_No fruit ledger entry yet._" in md
    assert "_None since swarm inception._" not in md
    assert "Chat Sessions Tidy" in md
    assert "tidied 3 sessions" in md
    assert "Memory Tidy" in md
    assert "Email Tags" not in md
    assert "Email AI Auto Reply" in md


def test_compose_empty_harvest_uses_full_picture_placeholders():
    md = compose_ceo_brief_markdown(title="CEO Brief")
    assert "## Top 3 actions that move the needle" in md
    assert "Sporangium may not have run" in md
    assert "## Inbound opportunity" in md
    assert "No tagged grant, proposal, invoice, or paid inbound" in md
    assert "No grant/RFP on file" in md
    assert "Do not invent grants" in md
    assert "_Clear day._" in md
    assert "No job applications need attention" in md
    assert "_None._" in md
    assert "Rhizo hasn't filed" in md
    assert "No fruit ledger" in md
    assert "No successful chron runs" in md
    assert "## Headline" not in md
    assert "```" not in md


def test_compose_fallback_top3_from_jobs_when_swarm_has_no_ranking():
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        jobs={"ready_to_apply": [{"company": "Acme", "role": "PM"}]},
        substrate_txt="# Swarm Plan\n\n## SENSED\n- Quiet board.\n",
    )
    top3_block = md.split("## Top 3 actions that move the needle", 1)[1].split("## What's upcoming", 1)[0]
    assert "1. Submit Acme — PM" in top3_block
    assert "Quiet board" in top3_block


def test_is_full_picture_brief_rejects_spoken_script_and_accepts_harvest():
    slim = (
        "# CEO Brief — 2026-08-20\n\n"
        "## Headline\nShip the needle.\n\n"
        "## What changed\nSlim script.\n\n"
        "## Needs you\nClick CEO Brief.\n\n"
        "## Can wait\nEverything else.\n"
    )
    assert is_full_picture_brief(slim) is False
    harvest = compose_ceo_brief_markdown(title="CEO Brief — 2026-08-20")
    assert is_full_picture_brief(harvest) is True


def test_parse_top3_and_money_hero_read_composed_needle_when_ready():
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        jobs={"ready_to_apply": [{"company": "Loom", "role": "pack"}]},
    )
    items = parse_top3(md)
    assert items
    assert "Loom" in items[0]["title"]
    hero = _build_money_hero(
        ceo_brief={
            "status": "ready",
            "content": md,
            "id": "d9b62b7e-ed38-4bad-ad7e-fcecd54fc3d0",
            "title": "CEO Brief — 2026-08-20",
        },
    )
    assert hero["unit"] == "TOP 3"
    assert "Loom" in (hero.get("title") or "")


CHARTER_Q3 = """# Objectives — Q3 2026

Pinned. Standup EOW/Monthly **must** read this.

## Mission (12–18 mo) / Yearly
Prosperity via grants, proposals, and side hustles. No dollar target on file.

## This quarter — Objective
Fred Hutch over-delivery (onboarding) plus kanban revenue. FT pipeline gated.

## Key results
1. Over-deliver / onboard at Fred Hutch.
2. Send staged proposals and capture inbound.
3. FT apps stay gated — not the needle.

## Daily
- Close money residue: grants, proposals, inbound — not job-queue hygiene.

## Weekly
- Send staged proposals; capture inbound opportunity.

## Monthly
- Portfolio + fruit scorecard.

## Kill criteria
- Stop ranking SUBMIT Prelim as #1 while the job pipeline is deferred to kanban revenue.
"""


def test_empty_charter_preserves_swarm_submit_order():
    stub = "# Objectives — Q3 2026\n\n## Mission (12–18 mo)\n…\n\n## Weekly KPIs\n- …\n"
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=stub,
    )
    top3_block = md.split("## Top 3 actions that move the needle", 1)[1].split("## What's upcoming", 1)[0]
    assert "1. **SUBMIT Prelim — SWE Product**" in top3_block


def test_charter_outranks_swarm_job_hygiene_in_compose_and_money_hero():
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=CHARTER_Q3,
        jobs={"ready_to_apply": [{"company": "Prelim", "role": "SWE Product"}]},
    )
    top3_block = md.split("## Top 3 actions that move the needle", 1)[1].split("## What's upcoming", 1)[0]
    first_line = next(ln for ln in top3_block.splitlines() if ln.startswith("1."))
    assert "SUBMIT Prelim" not in first_line
    assert "NPR" in first_line
    assert "SUBMIT Prelim" not in top3_block.split("2.")[0]
    items = parse_top3(md)
    assert items
    assert "SUBMIT Prelim" not in items[0]["title"]
    assert "NPR" in items[0]["title"]

    hero = _build_money_hero(
        ceo_brief={
            "status": "ready",
            "content": md,
            "id": "d9b62b7e-ed38-4bad-ad7e-fcecd54fc3d0",
            "title": "CEO Brief — 2026-08-20",
        },
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }],
    )
    assert hero["unit"] == "TOP 3"
    assert "SUBMIT Prelim" not in (hero.get("title") or "")
    assert "NPR" in (hero.get("title") or "")
    ranked = hero.get("ranked_top3") or []
    assert ranked
    assert "SUBMIT Prelim" not in ranked[0]["title"]
    assert "NPR" in ranked[0]["title"]

    from services.voice.vault_brief import build_brief_script

    blob = " ".join(
        line["text"]
        for line in build_brief_script(money_hero=hero, ceo_brief={"status": "ready", "content": md})
    )
    assert "SUBMIT Prelim" not in blob
    assert "NPR" in blob
    assert "Top money move" in blob


def test_money_hero_reranks_existing_brief_that_still_lists_submit_prelim():
    harvest = (
        "# CEO Brief — 2026-08-20\n\n"
        "## Top 3 actions that move the needle\n"
        "1. **SUBMIT Prelim — SWE Product** — hygiene item 1; materials ready.\n"
        "2. **SEND NPR Panel 2 thank-you emails** — drafts ready.\n"
        "3. **Close Q3 residue** — checkbox still open.\n"
        "\n## What's upcoming\n_Clear day._\n"
        "\n## Job pipeline\nNo job applications need attention.\n"
        "\n## Handoffs in flight\n_None._\n"
        "\n## Research findings (Rhizo)\n_None._\n"
        "\n## Fruit ledger (Herald)\n_None._\n"
        "\n## Recent chron outputs\n_None._\n"
    )
    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": harvest, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }],
    )
    assert "SUBMIT Prelim" not in (hero.get("title") or "")
    assert "NPR" in (hero.get("title") or "")
    assert hero["ranked_top3"][0]["title"]
    assert "submit prelim" not in hero["ranked_top3"][0]["title"].lower()

    from services.voice.vault_brief import build_brief_script

    spoken = " ".join(
        line["text"]
        for line in build_brief_script(
            money_hero=hero,
            ceo_brief={"status": "ready", "content": harvest},
        )
    )
    assert "SUBMIT Prelim" not in spoken
    assert "NPR" in spoken


def test_tagged_invoice_email_outranks_charter_slogan_and_jobs():
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=CHARTER_Q3,
        comms_preview=[{
            "id": "acct:99",
            "uid": "99",
            "subject": "Invoice 441 past due",
            "from": "ap@client.com",
            "tags": ["finance", "bills"],
            "reason": "Unpaid invoice",
            "score": 3,
        }],
    )
    inbound = md.split("## Inbound opportunity", 1)[1].split("## What's upcoming", 1)[0]
    assert "Invoice 441 past due" in inbound
    assert "No tagged grant" not in inbound
    assert "No grant/RFP on file" in inbound
    first_line = next(ln for ln in md.splitlines() if ln.startswith("1."))
    assert "Invoice 441" in first_line
    assert "SUBMIT Prelim" not in first_line

    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": md, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }],
        comms_preview=[{
            "id": "acct:99",
            "uid": "99",
            "subject": "Invoice 441 past due",
            "from": "ap@client.com",
            "tags": ["finance", "bills"],
            "reason": "Unpaid invoice",
            "score": 3,
        }],
    )
    assert "Invoice 441" in (hero.get("title") or "")
    assert hero.get("action") == "email"
    assert not hero.get("confirm_action")
    assert not hero.get("confirm_one_action")

    from services.voice.vault_brief import build_brief_script

    spoken = " ".join(
        line["text"]
        for line in build_brief_script(
            money_hero=hero,
            ceo_brief={"status": "ready", "content": md},
        )
    )
    assert "Invoice 441" in spoken
    assert "SUBMIT Prelim" not in spoken


def test_upwork_residue_used_when_inbox_has_no_tagged_opportunity():
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=CHARTER_Q3,
        inbound_notes=[{
            "id": "f1cf1f16",
            "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
            "items": [{"text": "Send 01", "done": False} for _ in range(5)],
            "pinned": True,
        }],
        inbound_docs=[{
            "id": "4f9a694f-7103-4ced-9798-3a701929bcbe",
            "title": "Upwork Send Pack — 5 Proposals (HUMAN GATE)",
        }],
    )
    inbound = md.split("## Inbound opportunity", 1)[1].split("## What's upcoming", 1)[0]
    assert "No tagged grant, proposal, invoice, or paid inbound" in inbound
    assert "No grant/RFP on file" in inbound
    assert "f1cf1f16" in inbound
    assert "4f9a694f" in inbound
    first_line = next(ln for ln in md.splitlines() if ln.startswith("1."))
    assert "Upwork" in first_line
    assert "SUBMIT Prelim" not in first_line

    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": md, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }, {
            "id": "f1cf1f16",
            "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
            "items": [{"text": "Send 01", "done": False} for _ in range(5)],
            "pinned": True,
        }],
        documents=[{
            "id": "4f9a694f-7103-4ced-9798-3a701929bcbe",
            "title": "Upwork Send Pack — 5 Proposals (HUMAN GATE)",
        }],
    )
    assert "Upwork" in (hero.get("title") or "")
    assert "SUBMIT Prelim" not in (hero.get("title") or "")
    assert hero.get("action") == "open_doc"
    assert "4f9a694f" in str(hero.get("target_id") or "")
    assert hero.get("target_id") != "d9b62b7e"
    assert hero.get("target_id") != "f1cf1f16"
    assert hero.get("confirm_action") == "confirm_pack_sent"
    assert hero.get("confirm_one_action") == "confirm_proposal_sent"

    from services.voice.vault_brief import build_brief_script

    spoken = " ".join(
        line["text"]
        for line in build_brief_script(
            money_hero=hero,
            ceo_brief={"status": "ready", "content": md},
        )
    )
    assert "Upwork" in spoken
    assert "f1cf1f16" in spoken or "4f9a694f" in spoken or "Upwork Proposals" in spoken


def test_money_hero_opens_pack_from_brief_backticks_without_inbound_source():
    """parse_top3-only harvest still Do-its the Library pack, not ceo_brief/jobs."""
    harvest = (
        "# CEO Brief — 2026-08-20\n\n"
        "## Top 3 actions that move the needle\n"
        "1. **Upwork Send Pack — 5 Proposals (HUMAN GATE)** — paste-ready (`4f9a694f`).\n"
        "2. **SEND NPR Panel 2 thank-you emails** — drafts ready.\n"
        "3. **Close Q3 residue** — checkbox still open.\n"
        "\n## What's upcoming\n_Clear day._\n"
        "\n## Job pipeline\nNo job applications need attention.\n"
        "\n## Handoffs in flight\n_None._\n"
        "\n## Research findings (Rhizo)\n_None._\n"
        "\n## Fruit ledger (Herald)\n_None._\n"
        "\n## Recent chron outputs\n_None._\n"
    )
    pack_id = "4f9a694f-7103-4ced-9798-3a701929bcbe"
    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": harvest, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }, {
            "id": "f1cf1f16",
            "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
            "items": [{"text": "Send 01", "done": False} for _ in range(5)],
            "pinned": True,
        }],
        documents=[{
            "id": pack_id,
            "title": "Upwork Send Pack — 5 Proposals (HUMAN GATE)",
        }],
    )
    assert "Upwork" in (hero.get("title") or "")
    assert hero.get("action") == "open_doc"
    assert hero.get("target_id") == pack_id
    assert hero.get("confirm_action") == "confirm_pack_sent"
    assert hero.get("confirm_one_action") == "confirm_proposal_sent"


def test_money_hero_drops_pack_when_human_gate_cleared():
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=CHARTER_Q3,
        inbound_notes=[{
            "id": "f1cf1f16",
            "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
            "items": [{"text": "Send 01", "done": True} for _ in range(5)],
            "pinned": True,
        }],
        inbound_docs=[{
            "id": "4f9a694f-7103-4ced-9798-3a701929bcbe",
            "title": "Upwork Send Pack — 5 Proposals (HUMAN GATE)",
        }],
    )
    first_line = next(ln for ln in md.splitlines() if ln.startswith("1."))
    assert "Upwork" not in first_line
    assert "NPR" in first_line

    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": md, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }, {
            "id": "f1cf1f16",
            "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
            "items": [{"text": "Send 01", "done": True} for _ in range(5)],
            "pinned": True,
        }],
        documents=[{
            "id": "4f9a694f-7103-4ced-9798-3a701929bcbe",
            "title": "Upwork Send Pack — 5 Proposals (HUMAN GATE)",
        }],
    )
    assert "Upwork" not in (hero.get("title") or "")
    assert "NPR" in (hero.get("title") or "")
    assert "4f9a694f" not in str(hero.get("target_id") or "")
    assert hero.get("action") == "open_note"
    assert str(hero.get("target_id") or "").startswith("4be22ee3")
    assert hero.get("action") not in ("ceo_brief", "jobs")
    assert hero.get("confirm_action") == "confirm_npr_sent"
    assert not hero.get("confirm_one_action")

    from services.voice.vault_brief import build_brief_script

    spoken = " ".join(
        line["text"]
        for line in build_brief_script(
            money_hero=hero,
            ceo_brief={"status": "ready", "content": md},
        )
    )
    assert "NPR" in spoken
    assert "4be22ee3" in spoken
    assert "Next executable" in spoken
    assert "don't invent fruit" in spoken or "do not invent fruit" in spoken.lower()


def test_money_hero_npr_do_it_skips_sent_draft():
    """First unsent of the three NPR thank-you ids — not ceo_brief/jobs."""
    harvest = (
        "# CEO Brief — 2026-08-20\n\n"
        "## Top 3 actions that move the needle\n"
        "1. **SEND NPR Panel 2 thank-you emails** — drafts ready.\n"
        "2. **Close Q3 residue** — checkbox still open.\n"
        "3. **Protect focus** — no invented inventory.\n"
        "\n## What's upcoming\n_Clear day._\n"
        "\n## Job pipeline\nNo job applications need attention.\n"
        "\n## Handoffs in flight\n_None._\n"
        "\n## Research findings (Rhizo)\n_None._\n"
        "\n## Fruit ledger (Herald)\n_No fruit ledger entry yet._\n"
        "\n## Recent chron outputs\n_None._\n"
    )
    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": harvest, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }, {
            "id": "4be22ee3-aaaa-bbbb-cccc-ddddeeeeffff",
            "title": "DRAFT · NPR Panel 2 — Thank-you Email · Greta Pittenger (sent)",
        }, {
            "id": "8504c427-aaaa-bbbb-cccc-ddddeeeeffff",
            "title": "DRAFT · NPR Panel 2 — Thank-you Email · Kriti Singh",
        }, {
            "id": "80aa4a73-aaaa-bbbb-cccc-ddddeeeeffff",
            "title": "DRAFT · NPR Panel 2 — Thank-you Email · Nicolette Khan",
        }],
    )
    assert "NPR" in (hero.get("title") or "")
    assert hero.get("action") == "open_note"
    assert str(hero.get("target_id") or "").startswith("8504c427")
    assert not str(hero.get("target_id") or "").startswith("4be22ee3")
    assert hero.get("action") != "ceo_brief"
    assert hero.get("confirm_action") == "confirm_npr_sent"
    assert not hero.get("confirm_one_action")


def test_jarvis_open_pack_phrases_use_open_doc_not_only_do_it():
    from services.voice.voice_tools import CMD_NAVIGATE_ACTIONS, resolve_cmd_action

    pack_id = "4f9a694f-7103-4ced-9798-3a701929bcbe"
    assert "open_doc" in CMD_NAVIGATE_ACTIONS
    ok = resolve_cmd_action("open_doc", pack_id)
    assert ok["ok"] is True
    assert ok["action"] == "open_doc"
    assert ok["id"] == pack_id
    assert resolve_cmd_action("open_note")["ok"] is True

    root = Path(__file__).resolve().parents[1]
    rt = (root / "static" / "js" / "voiceRealtime.js").read_text(encoding="utf-8")
    start = rt.index("function maybeDispatchCmdShortcut")
    end = rt.index("function isIOS")
    body = rt[start:end]
    assert "open_doc" in body
    assert pack_id in body
    assert "send )?pack" in body or "send pack" in body
    assert "document" in body
    assert "rule.id" in body


def test_jarvis_do_it_shortcut_runs_money_hero_not_ceo_brief():
    root = Path(__file__).resolve().parents[1]
    rt = (root / "static" / "js" / "voiceRealtime.js").read_text(encoding="utf-8")
    start = rt.index("function maybeDispatchCmdShortcut")
    end = rt.index("function isIOS")
    body = rt[start:end]
    assert "hero_act" in body
    assert "do (it|that)" in body or "do it" in body

    cmd = (root / "static" / "js" / "cmdCenter.js").read_text(encoding="utf-8")
    hero = cmd[cmd.index("if (action === 'hero_act')"): cmd.index("if (action === 'speak_true')")]
    assert "money_hero" in hero
    assert "target_id" in hero
    click = cmd[cmd.index("const heroHit"): cmd.index("if (target.dataset.action === 'open_directive')")]
    assert "open_note" not in click.split("if (act &&")[1]


def test_ceo_brief_compile_does_not_autostart_listen():
    root = Path(__file__).resolve().parents[1]
    action = (root / "src" / "builtin_actions.py").read_text(encoding="utf-8")
    start = action.index("async def action_ceo_brief")
    end = action.index("async def action_test_skills")
    body = action[start:end]
    assert "kickoff_doc_audio_brief" not in body
    assert "Kicking off CEO audio" not in body

    cmd = (root / "static" / "js" / "cmdCenter.js").read_text(encoding="utf-8")
    start = cmd.index("if (action === 'ceo_brief')")
    end = cmd.index("// DISABLED: Docker Odysseus cannot launch")
    block = cmd[start:end]
    assert "_speakHeroTrue()" not in block
    assert "audio-brief" not in block
    assert "_briefHasFullPicture" in block

    routes = (root / "routes" / "home_routes.py").read_text(encoding="utf-8")
    start = routes.index("async def ceo_brief_run")
    end = routes.index("def ceo_brief_latest")
    block = routes[start:end]
    assert "is_full_picture_brief" in block
    assert "force" in block
    assert "kickoff_doc_audio_brief" not in block


HERALD_FRUIT_STUB = {
    "id": "506a37f1",
    "title": "🍄 Fruit Ledger — Odysseus Swarm",
}


def test_compose_dumps_fruit_line_from_herald_note_stub():
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        notes=[{
            **HERALD_FRUIT_STUB,
            "content": (
                "### 2026-08-20 · Herald\n"
                "- FRUIT: Upwork Send Pack — 5 proposals sent\n"
                "- EVIDENCE: money gate cleared\n"
            ),
        }],
        documents=[],
    )
    fruit_block = md.split("## Fruit ledger (Herald)", 1)[1].split("## Recent chron", 1)[0]
    assert "- FRUIT:" in fruit_block
    assert "Upwork Send Pack — 5 proposals sent" in fruit_block
    assert "_No fruit ledger entry yet._" not in fruit_block


def test_compose_empty_herald_note_is_honest():
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        notes=[{**HERALD_FRUIT_STUB, "content": ""}],
        documents=[],
    )
    fruit_block = md.split("## Fruit ledger (Herald)", 1)[1].split("## Recent chron", 1)[0]
    assert "_No fruit ledger entry yet._" in fruit_block
    assert "- FRUIT:" not in fruit_block
    assert "proposals sent" not in fruit_block.lower()
    assert "$" not in fruit_block


def test_harvest_prefers_library_fruit_doc_over_note():
    text = harvest_fruit_ledger_text(
        documents=[{
            "id": "fruit-doc",
            "title": "🍄 Fruit Ledger — Odysseus Swarm",
            "content": "- FRUIT: Library row\n",
        }],
        notes=[{
            **HERALD_FRUIT_STUB,
            "content": "- FRUIT: Note stub row\n",
        }],
    )
    assert "Library row" in text
    assert "Note stub row" not in text


def test_harvest_empty_library_doc_defers_to_live_herald_note():
    text = harvest_fruit_ledger_text(
        documents=[{
            "id": "fruit-doc",
            "title": "🍄 Fruit Ledger — Odysseus Swarm",
            "content": "",
        }],
        notes=[{
            **HERALD_FRUIT_STUB,
            "content": "- FRUIT: Upwork Send Pack — 5 proposals sent\n",
        }],
    )
    assert "Upwork Send Pack — 5 proposals sent" in text


HOWTO_FRUIT_DOC = {
    "id": "howto-fruit-doc",
    "title": "¡¡¡ Fruit Ledger ¡¡¡ Odysseus Swarm",
    "content": (
        "# ¡¡¡ Fruit Ledger ¡¡¡ Odysseus Swarm\n"
        "> Restored 2026-07-09 by Cursor (Culler remediation).\n"
        "## How to log fruit\n"
        "- FRUIT: what left the system\n"
        "## Recorded fruit\n"
        "_None since swarm inception._\n"
        "### 2026-07-15 · Herald\n"
        "- FRUIT: No fruit today.\n"
    ),
    "updated_at": "2026-08-20T18:00:00+00:00",
}


def test_harvest_howto_doc_vs_empty_note_is_empty():
    text = harvest_fruit_ledger_text(
        documents=[HOWTO_FRUIT_DOC],
        notes=[{**HERALD_FRUIT_STUB, "content": ""}],
    )
    assert text == ""
    assert "Culler remediation" not in text
    assert "¡¡¡" not in text


def test_compose_howto_doc_vs_empty_note_is_honest_stub():
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        documents=[HOWTO_FRUIT_DOC],
        notes=[{**HERALD_FRUIT_STUB, "content": ""}],
    )
    fruit_block = md.split("## Fruit ledger (Herald)", 1)[1].split("## Recent chron", 1)[0]
    assert "_No fruit ledger entry yet._" in fruit_block
    assert "- FRUIT:" not in fruit_block
    assert "Culler remediation" not in fruit_block
    assert "¡¡¡ Fruit Ledger ¡¡¡" not in fruit_block
    assert "how to log fruit" not in fruit_block.lower()
    assert "what left the system" not in fruit_block.lower()


def test_compose_howto_doc_vs_one_fruit_line_dumps_live_fruit():
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        documents=[HOWTO_FRUIT_DOC],
        notes=[{
            **HERALD_FRUIT_STUB,
            "content": (
                "### 2026-08-20 · Herald\n"
                "- FRUIT: Upwork Send Pack — 5 proposals sent\n"
                "- EVIDENCE: money gate cleared\n"
            ),
        }],
    )
    fruit_block = md.split("## Fruit ledger (Herald)", 1)[1].split("## Recent chron", 1)[0]
    assert "- FRUIT:" in fruit_block
    assert "Upwork Send Pack — 5 proposals sent" in fruit_block
    assert "_No fruit ledger entry yet._" not in fruit_block
    assert "Culler remediation" not in fruit_block
    assert "¡¡¡ Fruit Ledger ¡¡¡" not in fruit_block


def test_compose_empty_library_doc_dumps_live_herald_note():
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        documents=[{
            "id": "fruit-doc",
            "title": "🍄 Fruit Ledger — Odysseus Swarm",
            "content": "",
        }],
        notes=[{
            **HERALD_FRUIT_STUB,
            "content": (
                "### 2026-08-20 · Herald\n"
                "- FRUIT: Upwork Send Pack — 5 proposals sent\n"
                "- EVIDENCE: money gate cleared\n"
            ),
        }],
    )
    fruit_block = md.split("## Fruit ledger (Herald)", 1)[1].split("## Recent chron", 1)[0]
    assert "- FRUIT:" in fruit_block
    assert "Upwork Send Pack — 5 proposals sent" in fruit_block
    assert "_No fruit ledger entry yet._" not in fruit_block


def test_cmd_center_snapshot_pins_stale_herald_fruit_note(tmp_path):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    import core.database as cdb
    from core.database import Document, Note
    from routes.home_routes import _ensure_fruit_ledger_snapshot

    engine = create_engine(
        f"sqlite:///{tmp_path / 'fruit_pin.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    old = datetime.now(timezone.utc) - timedelta(days=400)
    db.add(Note(
        id="506a37f1",
        owner="alice",
        title="🍄 Fruit Ledger — Odysseus Swarm",
        content="- FRUIT: Gate cleared\n",
        archived=False,
        updated_at=old.replace(tzinfo=None),
    ))
    db.add(Document(
        id="fruit-doc-1",
        owner="alice",
        title="Fruit Ledger — archive",
        current_content="- FRUIT: Old library\n",
        is_active=True,
        archived=False,
        language="markdown",
        updated_at=old.replace(tzinfo=None),
    ))
    db.commit()
    notes: list = []
    documents: list = []
    _ensure_fruit_ledger_snapshot(db, "alice", notes, documents)
    db.close()
    assert notes and notes[0]["id"] == "506a37f1"
    assert "- FRUIT: Gate cleared" in (notes[0].get("content") or "")
    assert documents and "fruit" in (documents[0].get("title") or "").lower()
    assert "ledger" in (documents[0].get("title") or "").lower()


def test_cmd_center_snapshot_pins_stale_grant_packet_outside_recency(tmp_path):
    """Recency-80 without 08e7c105 still feeds find_grant_packet after pin."""
    import json
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    import core.database as cdb
    from core.database import Document, Note
    from routes.home_routes import (
        HUD_PINNED_DOC_PREFIXES,
        HUD_PINNED_NOTE_PREFIXES,
        _ensure_fruit_ledger_snapshot,
        _id8,
        _note_row_to_cmd,
    )
    from src.auth_helpers import owner_filter

    engine = create_engine(
        f"sqlite:///{tmp_path / 'hud_pin.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(days=400)
    packet_id = "08e7c105-aaaa-bbbb-cccc-dddddddddddd"
    db.add(Note(
        id=packet_id,
        owner="alice",
        title="Impact+ Doctoral — nomination gate",
        content="",
        items=json.dumps([
            {"text": "Official URL (catalog 7785722b)", "done": False},
            {"text": "HUMAN GATE — do not submit without operator", "done": False},
        ]),
        note_type="checklist",
        pinned=True,
        archived=False,
        updated_at=old,
    ))
    db.add(Note(
        id="506a37f1",
        owner="alice",
        title="🍄 Fruit Ledger — Odysseus Swarm",
        content="- FRUIT: Gate cleared\n",
        archived=False,
        updated_at=old,
    ))
    db.add(Note(
        id="ccd47cbf",
        owner="alice",
        title="Objectives — Q3 2026",
        content="# Objectives — Q3 2026\n- Doctoral training awards over faculty Insight.\n",
        pinned=True,
        archived=False,
        updated_at=old,
    ))
    db.add(Note(
        id="f1cf1f16",
        owner="alice",
        title="Upwork Proposals — 5 To Send (HUMAN GATE)",
        items=json.dumps([{"text": "Send 01", "done": False} for _ in range(5)]),
        note_type="checklist",
        pinned=True,
        archived=False,
        updated_at=old,
    ))
    db.add(Note(
        id="4be22ee3-aaaa-bbbb-cccc-ddddeeeeffff",
        owner="alice",
        title="DRAFT · NPR Panel 2 — Thank-you · Greta",
        content="paste-ready thank-you",
        archived=False,
        updated_at=old,
    ))
    db.add(Note(
        id="8504c427-aaaa-bbbb-cccc-ddddeeeeffff",
        owner="alice",
        title="DRAFT · NPR Panel 2 — Thank-you · Kriti",
        content="paste-ready thank-you",
        archived=False,
        updated_at=old,
    ))
    db.add(Note(
        id="80aa4a73-aaaa-bbbb-cccc-ddddeeeeffff",
        owner="alice",
        title="DRAFT · NPR Panel 2 — Thank-you · Nicolette",
        content="paste-ready thank-you",
        archived=False,
        updated_at=old,
    ))
    db.add(Document(
        id="7785722b-e023-4901-9a93-a847f4cc2889",
        owner="alice",
        title="Grant Scout catalog : Research Agent Response",
        current_content="programs\n| name | funder |\n| Impact+ Doctoral | CIHR |\n",
        is_active=True,
        archived=False,
        language="markdown",
        updated_at=old,
    ))
    send_pack_id = "4f9a694f-7103-4ced-9798-3a701929bcbe"
    db.add(Document(
        id=send_pack_id,
        owner="alice",
        title="Upwork Send Pack — 5 Proposals (HUMAN GATE)",
        current_content="# Upwork Send Pack\nPaste-ready proposals.\n",
        is_active=True,
        archived=False,
        language="markdown",
        updated_at=old,
    ))
    for i in range(80):
        db.add(Note(
            id=f"recent-{i:02d}",
            owner="alice",
            title=f"Recent noise {i:02d}",
            content="filler",
            archived=False,
            updated_at=now - timedelta(minutes=i),
        ))
    for i in range(40):
        db.add(Document(
            id=f"recent-doc-{i:02d}",
            owner="alice",
            title=f"Recent doc {i:02d}",
            current_content="filler",
            is_active=True,
            archived=False,
            language="markdown",
            updated_at=now - timedelta(minutes=i),
        ))
    db.commit()

    note_q = db.query(Note).filter(Note.archived == False)  # noqa: E712
    note_q = owner_filter(note_q, Note, "alice")
    notes = [_note_row_to_cmd(n) for n in note_q.order_by(Note.updated_at.desc()).limit(80).all()]
    doc_q = db.query(Document).filter(Document.is_active == True)  # noqa: E712
    documents = [
        {"id": d.id, "title": d.title, "content": d.current_content}
        for d in doc_q.order_by(Document.updated_at.desc()).limit(40).all()
    ]
    recency_ids = {_id8(n.get("id")) for n in notes}
    recency_docs = {_id8(d.get("id")) for d in documents}
    assert "08e7c105" not in recency_ids
    assert "506a37f1" not in recency_ids
    assert "ccd47cbf" not in recency_ids
    assert "f1cf1f16" not in recency_ids
    assert "4be22ee3" not in recency_ids
    assert "8504c427" not in recency_ids
    assert "80aa4a73" not in recency_ids
    assert "7785722b" not in recency_docs
    assert "4f9a694f" not in recency_docs
    assert find_grant_packet(
        "Canada Impact+ Research Training Awards – Doctoral",
        notes,
    ) is None

    _ensure_fruit_ledger_snapshot(db, "alice", notes, documents)
    db.close()

    pinned_notes = {_id8(n.get("id")) for n in notes}
    pinned_docs = {_id8(d.get("id")) for d in documents}
    for prefix in HUD_PINNED_NOTE_PREFIXES:
        assert prefix in pinned_notes, prefix
    for prefix in HUD_PINNED_DOC_PREFIXES:
        assert prefix in pinned_docs, prefix
    assert "4f9a694f" in pinned_docs
    packet = find_grant_packet(
        "Canada Impact+ Research Training Awards – Doctoral",
        notes,
    )
    assert packet and _id8(packet.get("id")) == "08e7c105"
    assert packet["id"] == packet_id


def test_cmd_center_snapshot_pins_send_pack_outside_recency(tmp_path):
    """Recency-40 without 4f9a694f still has the Send Pack in the snapshot."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    import core.database as cdb
    from core.database import Document
    from routes.home_routes import _ensure_fruit_ledger_snapshot, _id8

    engine = create_engine(
        f"sqlite:///{tmp_path / 'send_pack_pin.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(days=400)
    send_pack_id = "4f9a694f-7103-4ced-9798-3a701929bcbe"
    db.add(Document(
        id=send_pack_id,
        owner="alice",
        title="Upwork Send Pack — 5 Proposals (HUMAN GATE)",
        current_content="# Upwork Send Pack\nPaste-ready proposals.\n",
        is_active=True,
        archived=False,
        language="markdown",
        updated_at=old,
    ))
    for i in range(40):
        db.add(Document(
            id=f"recent-doc-{i:02d}",
            owner="alice",
            title=f"Recent doc {i:02d}",
            current_content="filler",
            is_active=True,
            archived=False,
            language="markdown",
            updated_at=now - timedelta(minutes=i),
        ))
    db.commit()

    documents = [
        {"id": d.id, "title": d.title, "content": d.current_content}
        for d in db.query(Document)
        .filter(Document.is_active == True)  # noqa: E712
        .order_by(Document.updated_at.desc())
        .limit(40)
        .all()
    ]
    assert "4f9a694f" not in {_id8(d.get("id")) for d in documents}

    notes: list = []
    _ensure_fruit_ledger_snapshot(db, "alice", notes, documents)
    db.close()

    pinned = [d for d in documents if _id8(d.get("id")) == "4f9a694f"]
    assert pinned and pinned[0]["id"] == send_pack_id
    assert "Send Pack" in (pinned[0].get("title") or "")


def test_cmd_center_snapshot_pins_today_ceo_brief_outside_recency(tmp_path):
    """Recency-40 without today's brief still ranks from the Library snapshot."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    import core.database as cdb
    from core.database import Document
    from routes.home_routes import _ensure_fruit_ledger_snapshot, _id8
    from services.documents.ceo_brief_store import canonical_title, date_label

    engine = create_engine(
        f"sqlite:///{tmp_path / 'ceo_brief_pin.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(days=400)
    brief_id = "d9b62b7e-ed38-4bad-ad7e-fcecd54fc3d0"
    db.add(Document(
        id=brief_id,
        owner="alice",
        title=canonical_title(now),
        current_content=(
            f"# {canonical_title(now)}\n\n"
            "## Top 3 actions that move the needle\n"
            "1. Canada Impact+ Research Training Awards – Doctoral (`08e7c105`)\n"
        ),
        is_active=True,
        archived=False,
        language="markdown",
        updated_at=old,
    ))
    for i in range(40):
        db.add(Document(
            id=f"recent-brief-{i:02d}",
            owner="alice",
            title=f"Recent doc {i:02d}",
            current_content="filler",
            is_active=True,
            archived=False,
            language="markdown",
            updated_at=now - timedelta(minutes=i),
        ))
    db.commit()

    documents = [
        {"id": d.id, "title": d.title, "content": d.current_content}
        for d in db.query(Document)
        .filter(Document.is_active == True)  # noqa: E712
        .order_by(Document.updated_at.desc())
        .limit(40)
        .all()
    ]
    assert "d9b62b7e" not in {_id8(d.get("id")) for d in documents}

    _ensure_fruit_ledger_snapshot(db, "alice", [], documents)
    db.close()

    pinned = [d for d in documents if _id8(d.get("id")) == "d9b62b7e"]
    assert pinned and pinned[0]["id"] == brief_id
    assert date_label(now) in (pinned[0].get("title") or "")
    assert "Impact+" in (pinned[0].get("content") or "")


def test_cmd_center_snapshot_pins_archived_human_gate_checklist(tmp_path):
    """Archived HUMAN GATE checklist still splices into the HUD pin snapshot."""
    import json
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    import core.database as cdb
    from core.database import Note
    from routes.home_routes import _ensure_fruit_ledger_snapshot, _id8

    engine = create_engine(
        f"sqlite:///{tmp_path / 'arch_pin.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(days=400)
    db.add(Note(
        id="f1cf1f16-0fa8-4ecb-aea2-8eacffd35191",
        owner="alice",
        title="Upwork Proposals — 5 To Send (HUMAN GATE)",
        items=json.dumps([{"text": "Send 01", "done": False} for _ in range(5)]),
        note_type="checklist",
        pinned=True,
        archived=True,
        updated_at=old,
    ))
    for i in range(80):
        db.add(Note(
            id=f"recent-note-{i:02d}",
            owner="alice",
            title=f"Recent note {i:02d}",
            content="filler",
            archived=False,
            updated_at=now - timedelta(minutes=i),
        ))
    db.commit()

    notes = [
        {"id": n.id, "title": n.title, "archived": bool(n.archived)}
        for n in db.query(Note)
        .filter(Note.archived == False)  # noqa: E712
        .order_by(Note.updated_at.desc())
        .limit(80)
        .all()
    ]
    assert "f1cf1f16" not in {_id8(n.get("id")) for n in notes}

    _ensure_fruit_ledger_snapshot(db, "alice", notes, [])
    db.close()

    pinned = [n for n in notes if _id8(n.get("id")) == "f1cf1f16"]
    assert pinned and pinned[0]["id"].startswith("f1cf1f16")
    assert pinned[0].get("archived") is True


GRANT_SCOUT_MD = """Grant Scout catalog : Research Agent Response

programs
| id | name | funder | deadline | max_cad | stage | citizenship | fit | official_url | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Canada Research Training Awards Suite – Research Travel Supplements (CRTAS-RTS) | Tri-Agency | 2026-06-10 external | 9000 | PhD research travel | Vanier | 5 | https://research-tools.mun.ca/funding/opportunities/canada-research-training-awards-suite-research-travel-supplements/ | Expired window |
| 4 | Insight Grants (2026 October Competition) | SSHRC | 2026-10 competition deadline | 400000 | Faculty-led | faculty | 4 | https://sshrc-crsh.canada.ca/en/funding/opportunities/insight-grants/2026/competition.aspx | October competition |

rejected (show your work)
| name | reason_rejected | source_checked |
| --- | --- | --- |
| Mitacs Accelerate Global Excellence Award | Postdoctoral; not for current PhD candidates | https://www.mitacs.ca/news/mitacs-announces-new-postdoctoral-fellowship-to-bring-top-global-talent-to-canada/ |
"""

GRANT_CATALOG_DOC = {
    "id": "7785722b-e023-4901-9a93-a847f4cc2889",
    "title": "Grant Scout catalog : Research Agent Response",
    "content": GRANT_SCOUT_MD,
}

UPWORK_NOTE = {
    "id": "f1cf1f16",
    "title": "Upwork Proposals — 5 To Send (HUMAN GATE)",
    "items": [{"text": "Send 01", "done": False} for _ in range(5)],
    "pinned": True,
}

UPWORK_DOC = {
    "id": "4f9a694f-7103-4ced-9798-3a701929bcbe",
    "title": "Upwork Send Pack — 5 Proposals (HUMAN GATE)",
}


def test_grant_present_ranks_catalog_call_over_upwork_residue():
    """Real Grant Scout row → Money Move #1; Do it opens the catalog, no send-gate."""
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=CHARTER_Q3,
        inbound_notes=[UPWORK_NOTE],
        inbound_docs=[GRANT_CATALOG_DOC, UPWORK_DOC],
    )
    inbound = md.split("## Inbound opportunity", 1)[1].split("## What's upcoming", 1)[0]
    assert "Insight Grants" in inbound
    assert "7785722b" in inbound
    assert "No grant/RFP on file" not in inbound
    assert "Mitacs Accelerate" not in inbound
    first_line = next(ln for ln in md.splitlines() if ln.startswith("1."))
    assert "Insight Grants" in first_line
    assert "SSHRC" in first_line
    assert "2026-10" in first_line
    assert "7785722b" in first_line
    assert "SUBMIT Prelim" not in first_line
    assert "9000" not in first_line
    assert "400000" not in first_line
    assert "$" not in first_line

    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": md, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }, UPWORK_NOTE],
        documents=[GRANT_CATALOG_DOC, UPWORK_DOC],
    )
    assert "Insight Grants" in (hero.get("title") or "")
    assert hero.get("action") == "open_doc"
    assert hero.get("target_id") == GRANT_CATALOG_DOC["id"]
    assert not hero.get("confirm_action")
    assert not hero.get("confirm_one_action")
    ranked = hero.get("ranked_top3") or []
    assert ranked and "Insight Grants" in ranked[0]["title"]
    assert "Upwork" in " ".join(item.get("title") or "" for item in ranked)


def test_grant_absent_keeps_residue_and_honest_harvest_line():
    """No grant/RFP on file → Upwork residue stays #1; harvest says so (not a fake KR)."""
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=CHARTER_Q3,
        inbound_notes=[UPWORK_NOTE],
        inbound_docs=[UPWORK_DOC],
    )
    inbound = md.split("## Inbound opportunity", 1)[1].split("## What's upcoming", 1)[0]
    assert "No grant/RFP on file" in inbound
    assert "Insight Grants" not in inbound
    first_line = next(ln for ln in md.splitlines() if ln.startswith("1."))
    assert "Upwork" in first_line
    assert "SUBMIT Prelim" not in first_line
    top3 = md.split("## Top 3 actions that move the needle", 1)[1].split("## Inbound opportunity", 1)[0]
    assert "No grant/RFP on file" not in top3

    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": md, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }, UPWORK_NOTE],
        documents=[UPWORK_DOC],
    )
    assert "Upwork" in (hero.get("title") or "")
    assert "Insight Grants" not in (hero.get("title") or "")
    assert hero.get("action") == "open_doc"
    assert "4f9a694f" in str(hero.get("target_id") or "")
    assert hero.get("confirm_action") == "confirm_pack_sent"


TODAY = date(2026, 8, 20)

LIVE_GRANT_SCOUT_MD = """Grant Scout catalog : Research Agent Response

programs
| id | name | funder | deadline | max_cad | stage | citizenship | fit | official_url | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Canada Research Training Awards Suite – Research Travel Supplements (CRTAS-RTS) | Tri-Agency | 2026-06-10 external | 9000 | PhD research travel | Vanier | 5 | https://example.test/crtas | Expired window |
| 2 | NFRF – Exploration Grants 2026 | New Frontiers in Research Fund | NOI due 2026-08-11; full application later in 2026 (date set by program) | 125000 | Faculty-led | faculty | 2 | https://example.test/nfrf | NOI is the executable gate |
| 3 | Canada Impact+ Research Training Awards – Doctoral | CIHR | 2026-03-04 application; 2026-12-31 replacement nomination | 40000 | PhD doctoral scholarship | Canadian | 3 | https://example.test/impact | Replacement nomination still open |
| 4 | Insight Grants (2026 October Competition) | SSHRC | 2026-10 competition deadline | 400000 | Faculty-led | faculty | 1 | https://example.test/insight | October competition |
| 5 | Canada Research Training Awards – Research Travel Supplements (Vanier stream highlighted) | Tri-Agency | Same external deadline 2026-06-10 for all eligible Vanier and CGS-D holders | 9000 | Supplement | Vanier | 5 | https://example.test/crtas-vanier | Same past travel window |
"""

LIVE_GRANT_DOC = {
    "id": "7785722b-e023-4901-9a93-a847f4cc2889",
    "title": "Grant Scout catalog : Research Agent Response",
    "content": LIVE_GRANT_SCOUT_MD,
}

IMPACT_PACKET = {
    "id": "c1a7a10d-1111-2222-3333-444444444444",
    "title": "Impact+ Doctoral — nomination gate",
    "note_type": "checklist",
    "pinned": True,
    "items": [
        {"text": "Official URL (catalog 7785722b): https://example.test/impact", "done": False},
        {"text": "Replacement nomination due 2026-12-31", "done": False},
        {"text": "HUMAN GATE — do not submit without operator", "done": False},
    ],
}


def test_past_noi_not_ranked_above_future_deadline():
    """On 2026-08-20, a past NOI must not outrank a still-open future deadline."""
    rows = extract_grant_calls_from_text(
        LIVE_GRANT_SCOUT_MD,
        source_id=LIVE_GRANT_DOC["id"],
        source_kind="doc",
        today=TODAY,
    )
    names = [r["name"] for r in rows]
    assert names, "catalog rows must parse"
    assert "NFRF" not in names[0]
    assert "2026-06-10" not in (rows[0].get("deadline") or "")
    nfrf = next(r for r in rows if "NFRF" in r["name"])
    impact = next(r for r in rows if "Impact+" in r["name"])
    insight = next(r for r in rows if "Insight Grants" in r["name"])
    assert names.index(impact["name"]) < names.index(insight["name"])
    assert names.index(insight["name"]) < names.index(nfrf["name"])
    assert names.index(impact["name"]) < names.index(nfrf["name"])
    open_names = [c["title"] for c in collect_grant_calls(
        documents=[LIVE_GRANT_DOC], today=TODAY, limit=2,
    )]
    assert all("NFRF" not in n for n in open_names)
    assert "Impact+" in open_names[0]
    assert any("Insight Grants" in n for n in open_names)
    catalog_calls = collect_grant_calls(documents=[LIVE_GRANT_DOC], today=TODAY, limit=1)
    assert catalog_calls[0]["action"] == "open_doc"
    assert catalog_calls[0]["target_id"] == LIVE_GRANT_DOC["id"]

    ranked = rank_money_candidates(
        [
            {
                "title": "NFRF – Exploration Grants 2026",
                "raw": "NFRF – Exploration Grants 2026 — due 2026-08-11 (`7785722b`)",
                "kind": "grant",
                "grant_open": False,
                "source": "doc",
            },
            {
                "title": "Canada Impact+ Research Training Awards – Doctoral",
                "raw": "Canada Impact+ Research Training Awards – Doctoral — due 2026-12-31 (`7785722b`)",
                "kind": "grant",
                "grant_open": True,
                "grant_due": "2026-12-31",
                "source": "doc",
            },
        ],
        CHARTER_Q3,
    )
    assert "Impact+" in ranked[0]["title"]
    assert "NFRF" not in ranked[0]["title"]


def test_grant_present_skips_past_noi_for_open_calls():
    """Live catalog: NFRF NOI-passed is not Money Move #1; open calls + Upwork residue."""
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-20",
        substrate_txt=SWARM_EXCERPT,
        charter_txt=CHARTER_Q3,
        inbound_notes=[IMPACT_PACKET, UPWORK_NOTE],
        inbound_docs=[LIVE_GRANT_DOC, UPWORK_DOC],
        today=TODAY,
    )
    first_line = next(ln for ln in md.splitlines() if ln.startswith("1."))
    top3 = md.split("## Top 3 actions that move the needle", 1)[1].split("## Inbound opportunity", 1)[0]
    numbered = [ln for ln in top3.splitlines() if ln[:2] in ("1.", "2.", "3.")]
    top3_blob = top3.lower()
    inbound = md.split("## Inbound opportunity", 1)[1].split("## What's upcoming", 1)[0]
    assert "nfrf" not in first_line.lower()
    assert "crtas" not in first_line.lower()
    assert "impact+" in first_line.lower()
    assert IMPACT_PACKET["id"][:8] in first_line
    assert IMPACT_PACKET["id"][:8] in inbound
    assert "submit prelim" not in first_line.lower()
    assert len(numbered) >= 3
    assert "impact+" in numbered[0].lower()
    assert "insight grants" in numbered[1].lower()
    assert "upwork" in numbered[2].lower()
    if "nfrf" in top3_blob:
        nfrf_at = top3_blob.index("nfrf")
        open_at = min(
            i for i in (
                top3_blob.find("impact+"),
                top3_blob.find("insight grants"),
            ) if i >= 0
        )
        assert open_at < nfrf_at

    hero = _build_money_hero(
        ceo_brief={"status": "ready", "content": md, "id": "d9b62b7e", "title": "CEO Brief"},
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": CHARTER_Q3,
            "pinned": True,
        }, IMPACT_PACKET, UPWORK_NOTE],
        documents=[LIVE_GRANT_DOC, UPWORK_DOC],
        today=TODAY,
    )
    ranked = hero.get("ranked_top3") or []
    titles = " ".join(item.get("title") or "" for item in ranked)
    assert ranked and "NFRF" not in (ranked[0].get("title") or "")
    assert "Impact+" in (ranked[0].get("title") or "")
    assert len(ranked) >= 3
    assert "Insight Grants" in (ranked[1].get("title") or "")
    assert "Upwork" in (ranked[2].get("title") or "")
    assert "Insight Grants" in titles
    assert "Upwork" in titles
    assert hero.get("action") == "open_note"
    assert hero.get("target_id") == IMPACT_PACKET["id"]
    assert hero.get("target_id") != LIVE_GRANT_DOC["id"]
    assert "7785722b" not in str(hero.get("target_id") or "")
    assert hero.get("confirm_action") == "confirm_grant_packet_sent"
    assert not hero.get("confirm_one_action")
    packet = find_grant_packet(
        "Canada Impact+ Research Training Awards – Doctoral",
        [IMPACT_PACKET, UPWORK_NOTE],
    )
    assert packet and packet["id"] == IMPACT_PACKET["id"]
    calls = collect_grant_calls(
        notes=[IMPACT_PACKET, UPWORK_NOTE],
        documents=[LIVE_GRANT_DOC],
        today=TODAY,
        limit=1,
    )
    assert calls[0]["action"] == "open_note"
    assert calls[0]["target_id"] == IMPACT_PACKET["id"]


def test_doctoral_training_outranks_faculty_insight():
    """Doctoral training award outranks faculty Insight when both are future-dated."""
    rows = extract_grant_calls_from_text(
        LIVE_GRANT_SCOUT_MD,
        source_id=LIVE_GRANT_DOC["id"],
        source_kind="doc",
        today=TODAY,
    )
    names = [r["name"] for r in rows]
    assert "Impact+" in names[0]
    assert names.index(next(n for n in names if "Impact+" in n)) < names.index(
        next(n for n in names if "Insight Grants" in n)
    )

    insight = {
        "title": "Insight Grants (2026 October Competition)",
        "raw": "Insight Grants (2026 October Competition) — SSHRC · due 2026-10 (`7785722b`)",
        "kind": "grant",
        "grant_open": True,
        "grant_due": "2026-10-01",
        "source": "doc",
    }
    doctoral = {
        "title": "Canada Impact+ Research Training Awards – Doctoral",
        "raw": "Canada Impact+ Research Training Awards – Doctoral — CIHR · due 2026-12-31 (`7785722b`)",
        "kind": "grant",
        "grant_open": True,
        "grant_due": "2026-12-31",
        "source": "doc",
    }
    ranked = rank_money_candidates([insight, doctoral], CHARTER_Q3)
    assert "Impact+" in ranked[0]["title"]
    assert "Insight Grants" in ranked[1]["title"]

    faculty_charter = CHARTER_Q3 + "\n\n## Daily\n- Faculty PI Insight Grants this quarter.\n"
    flipped = rank_money_candidates([insight, doctoral], faculty_charter)
    assert "Insight Grants" in flipped[0]["title"]


def test_nomination_packet_outranks_faculty_insight_when_charter_names_pi():
    """Live HUD: Impact+ packet note stays Money Move #1 even if charter names faculty PI."""
    insight = {
        "title": "Insight Grants (2026 October Competition)",
        "raw": "Insight Grants (2026 October Competition) — SSHRC · due 2026-10 (`7785722b`)",
        "kind": "grant",
        "grant_open": True,
        "grant_due": "2026-10-01",
        "grant_evidence": "Insight Grants (2026 October Competition) Faculty-led research project",
        "source": "doc",
        "action": "open_doc",
        "target_id": LIVE_GRANT_DOC["id"],
        "id": LIVE_GRANT_DOC["id"],
    }
    packet = {
        "title": "Canada Impact+ Research Training Awards – Doctoral",
        "raw": "Canada Impact+ Research Training Awards – Doctoral — CIHR · due 2026-12-31 (`08e7c105`)",
        "kind": "grant",
        "grant_open": True,
        "grant_due": "2026-12-31",
        "grant_evidence": "Canada Impact+ Research Training Awards – Doctoral PhD doctoral scholarship",
        "source": "note",
        "action": "open_note",
        "target_id": "08e7c105-166c-4ca4-a8b3-a57f9575e692",
        "id": "08e7c105-166c-4ca4-a8b3-a57f9575e692",
    }
    faculty_charter = CHARTER_Q3 + "\n\n## Daily\n- Faculty PI Insight Grants this quarter.\n"
    ranked = rank_money_candidates([insight, packet], faculty_charter)
    assert "Impact+" in ranked[0]["title"]
    assert str(ranked[0].get("target_id") or ranked[0].get("id") or "").startswith("08e7c105")

    hero = _build_money_hero(
        ceo_brief={
            "status": "ready",
            "content": (
                "## Top 3 actions that move the needle\n"
                "1. Insight Grants (2026 October Competition)\n"
                "2. Canada Impact+ Research Training Awards – Doctoral (`08e7c105`)\n"
            ),
            "id": "d9b62b7e",
            "title": "CEO Brief",
        },
        notes_list=[{
            "id": "ccd47cbf",
            "title": "Objectives — Q3 2026",
            "content": faculty_charter,
            "pinned": True,
        }, IMPACT_PACKET],
        documents=[LIVE_GRANT_DOC],
        today=TODAY,
    )
    assert "Impact+" in (hero.get("title") or "")
    assert str(hero.get("target_id") or "").startswith("08e7c105") or str(
        hero.get("target_id") or ""
    ) == IMPACT_PACKET["id"]
    assert hero.get("action") == "open_note"
    assert hero.get("confirm_action") == "confirm_grant_packet_sent"


