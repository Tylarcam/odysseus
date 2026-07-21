"""Tests for job search pipeline Phase 2 — evaluate, tailor, auto_process."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from src.job_pipeline.orchestrator import (
    evaluate_job,
    inbound_job_event,
    process_job,
    tailor_job,
)
from src.job_pipeline.store import get_job_events, get_job_record


@pytest.fixture()
def job_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs_phase2.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.tailoring_dispatch.SessionLocal", session_factory)
    root = tmp_path / "job-app-ops"
    (root / "templates").mkdir(parents=True)
    (root / "source-of-truth").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "templates" / "evaluation-rubric.md").write_text("# Rubric\nGate >= 4.0", encoding="utf-8")
    (root / "source-of-truth" / "Master_Resume_Complete.md").write_text("# Resume\nAI Engineer", encoding="utf-8")
    (root / "config" / "AGENT_WORKFLOW_SPEC.md").write_text("# Workflow\nSteps 0-7", encoding="utf-8")
    monkeypatch.setenv("JOB_APPLICATION_OPS_ROOT", str(root))
    return session_factory


def _sample_payload(**overrides):
    base = {
        "company": "Acme Corp",
        "role": "AI Engineer",
        "jd_text": "**Employer:** Acme Corp\n**Title:** AI Engineer\n\nBuild agents.",
        "source": "manual",
        "apply_url": "https://apply.example.com/jobs/123",
    }
    base.update(overrides)
    return base


def _mock_llm(gate_score: float, *, match_score: int = 80, profile: str = "2"):
    def _fn(**_kwargs):
        return {
            "gate_score": gate_score,
            "match_score": match_score,
            "profile": profile,
            "proceed": gate_score >= 4.0,
            "reason": None,
        }

    return _fn


def _ingest_deduped(owner: str = "alice"):
    with patch("src.job_pipeline.evaluator._default_llm_evaluate", side_effect=RuntimeError("no llm")):
        return inbound_job_event(_sample_payload(), owner=owner)


def test_evaluate_writes_evaluation_md_and_match_score(job_db, monkeypatch):
    record = _ingest_deduped()
    assert record["status"] == "deduped"

    monkeypatch.setattr(
        "src.job_pipeline.evaluator.run_evaluation",
        lambda job_id, **kw: __import__(
            "src.job_pipeline.evaluator", fromlist=["run_evaluation"]
        ).run_evaluation(job_id, llm_callable=_mock_llm(4.5), **{k: v for k, v in kw.items() if k != "llm_callable"}),
    )

    with patch("src.job_pipeline.evaluator.run_evaluation") as mock_eval:
        mock_eval.return_value = {
            "gate_score": 4.5,
            "match_score": 88,
            "profile": "2",
            "proceed": True,
            "evaluation_path": os.path.join(
                os.environ["JOB_APPLICATION_OPS_ROOT"],
                "positions",
                "_active",
                record["folder_slug"],
                "evaluation.md",
            ),
            "reason": None,
        }
        job = evaluate_job(record["id"], owner="alice")

    assert job["status"] == "evaluated"
    assert job["gate_score"] == "4.5"
    assert job["match_score"] == "88"


def test_below_gate_rejected(job_db):
    record = _ingest_deduped()

    with patch("src.job_pipeline.evaluator.run_evaluation") as mock_eval:
        mock_eval.return_value = {
            "gate_score": 3.2,
            "match_score": 55,
            "profile": "3",
            "proceed": False,
            "evaluation_path": "/tmp/evaluation.md",
            "reason": "weak fit",
        }
        job = evaluate_job(record["id"], owner="alice")

    assert job["status"] == "rejected"
    assert job["terminal_status"] == "below_gate"
    events = [e.to_status for e in get_job_events(record["id"])]
    assert "evaluated" in events
    assert events[-1] == "rejected"


def test_above_gate_tailor_dispatches_handoff(job_db):
    record = _ingest_deduped()
    fake_doc = SimpleNamespace(id="doc-handoff-1", current_content="handoff body", title="handoff")

    with patch("src.job_pipeline.evaluator.run_evaluation") as mock_eval:
        mock_eval.return_value = {
            "gate_score": 4.6,
            "match_score": 90,
            "profile": "2",
            "proceed": True,
            "evaluation_path": "/tmp/evaluation.md",
            "reason": None,
        }
        evaluated = evaluate_job(record["id"], owner="alice")
    assert evaluated["status"] == "evaluated"

    with patch(
        "src.job_pipeline.tailoring_dispatch._create_handoff_document",
        return_value=fake_doc,
    ), patch("src.job_pipeline.tailoring_dispatch.queue_handoff_relay_for_document", return_value={"ok": True, "inbox_path": "/tmp/inbox.md", "note_id": "n1"}):
        job = tailor_job(record["id"], owner="alice")

    assert job["status"] == "tailoring_started"
    assert job["handoff_doc_id"] == "doc-handoff-1"
    assert job["terminal_status"] == "tailoring_dispatched"


def test_auto_process_ingest_evaluates_and_tailors(job_db):
    fake_doc = SimpleNamespace(id="doc-auto-1", current_content="body", title="handoff")

    with patch("src.job_pipeline.evaluator.run_evaluation") as mock_eval:
        mock_eval.return_value = {
            "gate_score": 4.8,
            "match_score": 92,
            "profile": "2",
            "proceed": True,
            "evaluation_path": "/tmp/evaluation.md",
            "reason": None,
        }
        with patch(
            "src.job_pipeline.tailoring_dispatch._create_handoff_document",
            return_value=fake_doc,
        ), patch("src.job_pipeline.tailoring_dispatch.queue_handoff_relay_for_document", return_value={"ok": True, "inbox_path": "/tmp/inbox.md", "note_id": "n1"}):
            job = inbound_job_event(_sample_payload(), owner="alice", auto_process=True)

    assert job["status"] == "tailoring_started"
    assert job["handoff_doc_id"] == "doc-auto-1"


def test_api_evaluate_and_tailor_routes(job_db):
    record = _ingest_deduped(owner="bob")
    fake_doc = SimpleNamespace(id="doc-api-1", current_content="body", title="handoff")

    with patch("src.job_pipeline.evaluator.run_evaluation") as mock_eval:
        mock_eval.return_value = {
            "gate_score": 4.4,
            "match_score": 85,
            "profile": "2",
            "proceed": True,
            "evaluation_path": "/tmp/evaluation.md",
            "reason": None,
        }
        eval_result = evaluate_job(record["id"], owner="bob")
    assert eval_result["status"] == "evaluated"

    with patch(
        "src.job_pipeline.tailoring_dispatch._create_handoff_document",
        return_value=fake_doc,
    ), patch("src.job_pipeline.tailoring_dispatch.queue_handoff_relay_for_document", return_value={"ok": True, "inbox_path": "/tmp/inbox.md", "note_id": "n1"}):
        tailor_result = tailor_job(record["id"], owner="bob")
    assert tailor_result["status"] == "tailoring_started"


@pytest.mark.asyncio
async def test_process_job_application_tool_actions(job_db):
    from src.tool_implementations import do_process_job_application

    record = _ingest_deduped(owner="carol")
    fake_doc = SimpleNamespace(id="doc-tool-1", current_content="body", title="handoff")

    with patch("src.job_pipeline.evaluator.run_evaluation") as mock_eval:
        mock_eval.return_value = {
            "gate_score": 4.1,
            "match_score": 78,
            "profile": "2",
            "proceed": True,
            "evaluation_path": "/tmp/evaluation.md",
            "reason": None,
        }
        eval_out = await do_process_job_application(
            json.dumps({"action": "evaluate", "job_id": record["id"]}),
            owner="carol",
        )
    assert eval_out["exit_code"] == 0
    assert eval_out["job"]["status"] == "evaluated"

    with patch(
        "src.job_pipeline.tailoring_dispatch._create_handoff_document",
        return_value=fake_doc,
    ), patch("src.job_pipeline.tailoring_dispatch.queue_handoff_relay_for_document", return_value={"ok": True, "inbox_path": "/tmp/inbox.md", "note_id": "n1"}):
        tailor_out = await do_process_job_application(
            json.dumps({"action": "tailor", "job_id": record["id"]}),
            owner="carol",
        )
    assert tailor_out["exit_code"] == 0
    assert tailor_out["job"]["status"] == "tailoring_started"

    status_out = await do_process_job_application(
        json.dumps({"action": "status", "job_id": record["id"]}),
        owner="carol",
    )
    assert status_out["exit_code"] == 0
    assert status_out["job"]["id"] == record["id"]
    assert len(status_out["events"]) >= 3

    list_out = await do_process_job_application(
        json.dumps({"action": "list", "status": "tailoring_started"}),
        owner="carol",
    )
    assert list_out["exit_code"] == 0
    assert any(j["id"] == record["id"] for j in list_out["jobs"])


def test_run_evaluation_writes_file_with_mock_llm(job_db, monkeypatch):
    from src.job_pipeline.evaluator import run_evaluation

    record = _ingest_deduped()
    monkeypatch.setattr(
        "src.job_pipeline.evaluator._default_llm_evaluate",
        MagicMock(side_effect=RuntimeError("skip")),
    )

    result = run_evaluation(record["id"], llm_callable=_mock_llm(4.3, match_score=86, profile="2"))
    assert result["proceed"] is True
    assert os.path.isfile(result["evaluation_path"])
    with open(result["evaluation_path"], encoding="utf-8") as fh:
        text = fh.read()
    assert "4.3" in text
    assert "Acme Corp" in text

    loaded = get_job_record(record["id"])
    assert loaded.match_score == "86"
    assert loaded.evaluation_path == result["evaluation_path"]
