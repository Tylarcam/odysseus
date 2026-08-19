"""CEO brief spoken-script contract: exceptions only, research excerpt, no swarm dump."""

from services.documents.ceo_brief_script import classify_task_run, compose_ceo_brief_markdown


SWARM_DUMP = (
    "SPORANGIUM DOCTRINE\n" * 40
    + "Top 3 from the Swarm Substrate blackboard: never ship without the guild."
)


def test_classify_task_run_exceptions():
    assert classify_task_run({"status": "error", "result": "boom"}) == "failed"
    assert classify_task_run({"status": "success", "result": "timed out after 30s"}) == "timeout"
    assert classify_task_run({"status": "skipped", "result": "morning harvest not ready"}) == "missed"
    assert classify_task_run({"status": "success", "result": "tidied 3"}) == "success"
    assert classify_task_run({"status": "skipped", "result": "nothing to do"}) == "silence"


def test_compose_mentions_failed_job_and_research_not_successes():
    md = compose_ceo_brief_markdown(
        title="CEO Brief — 2026-08-18",
        generated_at="09:00",
        events=[{"start": "tomorrow 10:00", "title": "Standup"}],
        due_soon=[{"title": "Pay insurance", "due_date": "2026-08-19"}],
        overdue=[{"title": "RSVP Thesis Defence"}],
        jobs={
            "needs_review": [{"company": "Alkira", "role": "Engineer"}],
            "ready_to_apply": [{"company": "Acme", "role": "PM"}],
        },
        handoffs={"needs_attention": [{"title": "Handoff A", "handoff_target": "cursor"}]},
        research=[{
            "id": "rp-canvas",
            "title": "Visual Storytelling Canvas",
            "status": "done",
            "url": "/api/research/report/rp-canvas",
            "bullets": ["Story beats beat decks", "Operators want a 10-second headline"],
        }],
        runs=[
            {"name": "Email Tags", "status": "error", "result": "boom"},
            {"name": "Chat Sessions Tidy", "status": "success", "result": "tidied 3 sessions"},
            {"name": "Memory Tidy", "status": "success", "result": "ok"},
        ],
        harvest_flags={"has_swarm_plan": True, "swarm_excerpt": SWARM_DUMP},
    )
    assert "## Headline" in md
    assert "## What changed" in md
    assert "## Needs you" in md
    assert "## Can wait" in md
    assert "Email Tags" in md
    assert "Chat Sessions Tidy" not in md
    assert "Memory Tidy" not in md
    assert "tidied 3 sessions" not in md
    assert "Visual Storytelling Canvas" in md
    assert "Story beats beat decks" in md
    assert "/api/research/report/rp-canvas" in md
    assert SWARM_DUMP not in md
    assert "SPORANGIUM DOCTRINE" not in md
    assert "never ship without the guild" not in md
    assert "RSVP Thesis Defence" in md
    assert "Alkira" in md


def test_compose_all_green_collapses_cron():
    md = compose_ceo_brief_markdown(
        title="CEO Brief",
        runs=[
            {"name": "Chat Sessions Tidy", "status": "success", "result": "tidied 3"},
            {"name": "Memory Tidy", "status": "success", "result": "ok"},
        ],
    )
    assert "Chat Sessions Tidy" not in md
    assert "ran green" in md.lower() or "Needs you" in md
    assert "```" not in md
