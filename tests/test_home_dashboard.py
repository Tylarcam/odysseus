"""Home dashboard aggregation and API."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import Document, Note
import routes.home_routes as home_routes
from services.home.cmd_center import build_cmd_center
from services.home.dashboard import (
    build_recent_projects,
    note_project_tags,
    project_from_document_content,
    project_name_from_value,
)
from services.home.kg_graph import build_globe_graph


def test_note_project_tags_splits_and_dedupes():
    assert note_project_tags("alpha beta alpha") == ["alpha", "beta"]
    assert note_project_tags("#odysseus handoff") == ["odysseus", "handoff"]
    assert note_project_tags("") == []


def test_project_name_from_path_uses_basename():
    assert project_name_from_value(r"C:\Users\tylar\code\odysseus") == "odysseus"
    assert project_name_from_value("my-project") == "my-project"


def test_project_from_document_frontmatter():
    content = "---\nproject: grant-grafter\nstatus: pending\n---\n\nBody"
    assert project_from_document_content(content) == "grant-grafter"


def test_build_recent_projects_orders_by_activity():
    now = datetime(2026, 6, 18, 12, 0, 0)
    notes = [
        {
            "id": "n1",
            "title": "Old alpha note",
            "label": "alpha",
            "archived": False,
            "updated_at": (now - timedelta(days=3)).isoformat(),
        },
        {
            "id": "n2",
            "title": "Fresh beta note",
            "label": "beta",
            "archived": False,
            "updated_at": now.isoformat(),
        },
        {
            "id": "n3",
            "title": "Also beta",
            "label": "beta",
            "archived": False,
            "updated_at": (now - timedelta(hours=1)).isoformat(),
        },
    ]
    documents = [
        {
            "id": "d1",
            "title": "Alpha spec",
            "content": "",
            "session_folder": "alpha",
            "archived": False,
            "updated_at": (now - timedelta(hours=2)).isoformat(),
        }
    ]
    result = build_recent_projects(notes, documents, project_limit=5, items_per_project=3)
    names = [p["name"] for p in result["projects"]]
    assert names[0] == "beta"
    assert names[1] == "alpha"
    beta_items = result["projects"][0]["items"]
    assert beta_items[0]["id"] == "n2"
    assert len(beta_items) == 2


def test_recent_projects_route_queries_owner_scoped_rows(monkeypatch, tmp_path):
    """Route logic: notes + documents for the current user feed the aggregator."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'home2.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(home_routes, "SessionLocal", session_factory)

    db = session_factory()
    now = datetime.now()
    db.add(
        Note(
            id=str(uuid.uuid4()),
            owner="alice",
            title="Dashboard note",
            label="odysseus",
            archived=False,
            updated_at=now,
        )
    )
    db.add(
        Document(
            id=str(uuid.uuid4()),
            owner="alice",
            title="Dashboard doc",
            current_content="---\nproject: odysseus\n---\n",
            is_active=True,
            archived=False,
            updated_at=now,
        )
    )
    db.commit()
    db.close()

    db = session_factory()
    try:
        notes = [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "label": n.label,
                "note_type": n.note_type,
                "archived": n.archived,
                "updated_at": n.updated_at.isoformat() if n.updated_at else None,
            }
            for n in db.query(Note).filter(Note.owner == "alice").all()
        ]
        documents = [
            {
                "id": doc.id,
                "title": doc.title,
                "content": doc.current_content,
                "language": doc.language,
                "archived": bool(doc.archived),
                "session_folder": None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            for doc in db.query(Document).filter(Document.owner == "alice").all()
        ]
    finally:
        db.close()

    data = build_recent_projects(notes, documents)
    assert data["project_count"] == 1
    assert data["projects"][0]["name"] == "odysseus"
    assert len(data["projects"][0]["items"]) == 2


def test_build_cmd_center_maps_live_odysseus_surfaces():
    notes = [
        {
            "id": "n1",
            "title": "Morning brief",
            "label": "digest",
            "pinned": True,
            "note_type": "note",
            "archived": False,
            "updated_at": "2026-07-03T12:00:00",
        },
        {
            "id": "n2",
            "title": "Plan today",
            "label": "plan",
            "items": [{"text": "Ship CMD Center", "done": False}],
            "note_type": "checklist",
            "archived": False,
            "updated_at": "2026-07-03T11:00:00",
        },
    ]
    documents = [
        {
            "id": "d1",
            "title": "Spec.md",
            "content": "x" * 2048,
            "language": "markdown",
            "archived": False,
            "updated_at": "2026-07-03T10:00:00",
        }
    ]
    tasks = [{"id": "t1", "name": "Daily digest", "status": "active", "schedule": "daily"}]
    sessions = [{"id": "s1", "title": "Agent session", "last_message_at": "2026-07-03T09:00:00"}]
    handoffs = {
        "needs_attention": [
            {
                "id": "h1",
                "title": "Relay to Cursor",
                "handoff_target": "cursor",
                "handoff_doc_id": "doc-1",
                "updated_at": "2026-07-03T08:00:00",
            }
        ],
        "counts": {"needs_attention": 1, "in_progress": 0},
    }
    jobs = {
        "ready_to_apply_count": 2,
        "needs_review_count": 1,
        "ready_to_apply": [{"id": "j1", "company": "Acme", "role": "Engineer"}],
        "needs_review": [{"id": "j2", "company": "Beta", "role": "PM"}],
        "headline": "2 job(s) ready to apply",
        "summary_lines": ["2 job(s) ready to apply"],
    }

    data = build_cmd_center(
        notes=notes,
        documents=documents,
        tasks=tasks,
        sessions=sessions,
        handoffs=handoffs,
        jobs=jobs,
    )

    assert data["title"] == "V.A.U.L.T."
    assert data["counts"]["notes"] == 2
    assert data["counts"]["documents"] == 1
    assert data["counts"]["handoffs_attention"] == 1
    assert data["counts"]["jobs_ready"] == 2
    assert any(v["id"] == "notes" for v in data["vitals"])
    assert any(d["id"] == "n1" for d in data["directives"])
    assert data["documents"][0]["id"] == "d1"
    assert data["documents"][0]["tag"] == "MD"
    assert any(c["id"] == "morning_report" for c in data["stage_cards"])
    assert len(data["stage_cards"]) == 6
    assert all("branch" in c for c in data["stage_cards"])
    assert any(c["id"] == "up_next" for c in data["stage_cards"])
    assert data["hero"]["value"] == 1
    assert data["hero"]["unit"] == "HANDOFFS"
    assert data["hero"].get("explain")
    assert data["hero"].get("cta_label")
    assert data.get("priority_queue")
    assert data.get("branch_health")
    assert len(data["branch_health"]) >= 8
    assert data["priority_queue"][0]["kind"] == "handoff"
    assert any(c["action"] == "plan_today" for c in data["commands"])
    assert any(c["action"] == "relay_watcher" for c in data["commands"])
    assert not any(c["action"] == "start_clicky" for c in data["commands"])
    assert any("NOTE ·" in w["text"] for w in data["wire"])
    assert data["wire"][0].get("branch")
    assert "Esc dismisses vault" in (data["audio"].get("hint") or "")
    assert data["jobs_detail"]["ready_to_apply"][0]["id"] == "j1"
    assert data["jobs_detail"]["needs_review"][0]["id"] == "j2"

    graph = data.get("globe_graph") or {}
    assert graph.get("nodes")
    assert graph.get("edges") is not None
    assert graph["meta"]["mempalace"] in ("skipped", "disabled", "ok", "unavailable", "empty")
    kinds = {n["kind"] for n in graph["nodes"]}
    assert "urgent" in kinds
    urgent_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "urgent"}
    assert "handoff:h1" in urgent_ids


def test_build_cmd_center_up_next_card_prefers_calendar_event():
    now = datetime.now(timezone.utc)
    calendar_events = [
        {"uid": "evt-1", "title": "Standup", "start": (now + timedelta(minutes=45)).isoformat()},
    ]
    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        calendar_events=calendar_events,
    )
    up_next = next(c for c in data["stage_cards"] if c["id"] == "up_next")
    assert "Standup" in up_next["subtitle"]
    assert up_next["action"] == "calendar"
    assert up_next["target_id"] == "evt-1"
    assert data["agenda"]["next_event"]["uid"] == "evt-1"
    assert data["agenda"]["today_events"] >= 1

    graph = data["globe_graph"]
    event_nodes = [n for n in graph["nodes"] if n["id"] == "event:evt-1"]
    assert event_nodes
    assert event_nodes[0]["tone"] == "scheduled"
    assert event_nodes[0]["action"] == "calendar"


def test_build_cmd_center_up_next_card_falls_back_to_due_note_then_task():
    now = datetime.now(timezone.utc)
    notes = [
        {
            "id": "n-due-soon",
            "title": "Send invoice",
            "due_date": (now + timedelta(hours=2)).isoformat(),
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[])
    up_next = next(c for c in data["stage_cards"] if c["id"] == "up_next")
    assert "Send invoice" in up_next["subtitle"]
    assert up_next["action"] == "open_note"
    assert up_next["target_id"] == "n-due-soon"

    tasks = [
        {
            "id": "t-next",
            "name": "Nightly sync",
            "status": "active",
            "schedule": "daily",
            "next_run": (now + timedelta(hours=6)).isoformat(),
        }
    ]
    data2 = build_cmd_center(notes=[], documents=[], tasks=tasks, sessions=[])
    up_next2 = next(c for c in data2["stage_cards"] if c["id"] == "up_next")
    assert "Nightly sync" in up_next2["subtitle"]
    assert up_next2["action"] == "open_task"
    assert up_next2["target_id"] == "t-next"

    data3 = build_cmd_center(notes=[], documents=[], tasks=[], sessions=[])
    up_next3 = next(c for c in data3["stage_cards"] if c["id"] == "up_next")
    assert up_next3["subtitle"] == "Nothing scheduled"


def test_build_cmd_center_bumps_overdue_note_urgency():
    now = datetime.now(timezone.utc)
    notes = [
        {
            "id": "n-overdue",
            "title": "Overdue reminder",
            "due_date": (now - timedelta(hours=3)).isoformat(),
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[])
    entry = next(i for i in data["priority_queue"] if i["id"] == "n-overdue")
    assert entry["urgency"] == 85
    assert data["agenda"]["overdue"][0]["id"] == "n-overdue"


def test_build_globe_graph_projects_agent_and_scheduled():
    now = datetime(2026, 7, 3, 12, 0, 0)
    notes = [
        {
            "id": "n-due",
            "title": "Deadline note",
            "due_date": "2026-07-10",
            "archived": False,
            "updated_at": now.isoformat(),
        },
        {
            "id": "n1",
            "title": "Alpha work",
            "label": "alpha",
            "archived": False,
            "updated_at": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "id": "n2",
            "title": "Beta work",
            "label": "beta",
            "archived": False,
            "updated_at": now.isoformat(),
        },
    ]
    documents = [
        {
            "id": "d1",
            "title": "Beta spec",
            "session_folder": "beta",
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    projects = build_recent_projects(notes, documents)
    tasks = [
        {"id": "t1", "name": "Nightly digest", "status": "active", "schedule": "0 6 * * *"},
    ]
    agent_activity = [
        {
            "id": "run-1",
            "agent": "Swarm-01",
            "status": "running",
            "text": "⋯ indexing",
            "swarm": True,
            "ts": now.isoformat(),
            "action": "open_task",
            "target_id": "swarm-1",
        }
    ]
    priority_queue = [
        {
            "id": "j2",
            "kind": "job",
            "title": "Beta — PM",
            "subtitle": "Agency · needs review",
            "branch": "agency",
            "urgency": 95,
            "action": "jobs",
            "target_id": "j2",
            "ts": now.isoformat(),
        }
    ]

    graph = build_globe_graph(
        notes=notes,
        documents=documents,
        tasks=tasks,
        handoffs={"needs_attention": [], "counts": {}},
        priority_queue=priority_queue,
        agent_activity=agent_activity,
        projects=projects,
    )

    nodes = {n["id"]: n for n in graph["nodes"]}
    project_nodes = [n for n in graph["nodes"] if n["kind"] == "project"]
    assert project_nodes
    assert project_nodes[0]["kind"] == "project"
    assert project_nodes[0]["tone"] == "bright"
    assert project_nodes[0]["size"] >= project_nodes[-1]["size"] or len(project_nodes) == 1

    assert "agent:run-1" in nodes
    assert nodes["agent:run-1"]["tone"] == "agent"
    assert nodes["agent:run-1"]["branch"] == "mycelia"

    assert "task:t1" in nodes
    assert nodes["task:t1"]["tone"] == "scheduled"

    assert "note:n-due" in nodes
    assert nodes["note:n-due"]["tone"] == "urgent"

    assert any(e["kind"] == "run" for e in graph["edges"])
