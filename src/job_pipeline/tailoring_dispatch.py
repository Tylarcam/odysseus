"""Dispatch tailoring handoff to Cursor (Phase 2)."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from core.database import Document, DocumentVersion, SessionLocal
from src.handoff_materialize import default_job_app_root
from src.handoff_packet import build_handoff_content, handoff_doc_title
from src.handoff_relay import is_external_relay_target, queue_handoff_relay_for_document
from src.job_pipeline.store import get_job_record, update_job_record

logger = logging.getLogger(__name__)

TARGET = "cursor"
WORKFLOW_SPEC = os.path.join(
    default_job_app_root(),
    "config",
    "AGENT_WORKFLOW_SPEC.md",
)


def _read_jd(record) -> str:
    path = (record.jd_path or "").strip()
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return (record.jd_text or "").strip()


def _create_handoff_document(*, owner: Optional[str], title: str, content: str) -> Document:
    db = SessionLocal()
    try:
        doc_id = str(uuid.uuid4())
        ver_id = str(uuid.uuid4())
        doc = Document(
            id=doc_id,
            session_id=None,
            title=title,
            language="markdown",
            current_content=content,
            version_count=1,
            is_active=True,
            owner=owner,
        )
        ver = DocumentVersion(
            id=ver_id,
            document_id=doc_id,
            version_number=1,
            content=content,
            summary="Job tailoring handoff",
            source="job_pipeline",
        )
        db.add(doc)
        db.add(ver)
        db.commit()
        db.refresh(doc)
        return doc
    finally:
        db.close()


def dispatch_tailoring(job_id: str, *, owner: Optional[str] = None, relay: bool = True) -> dict[str, Any]:
    """Create handoff doc and optionally queue relay."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")

    company = record.company or "Company"
    role = record.role or "Role"
    folder_slug = record.folder_slug or ""
    folder_path = os.path.join(default_job_app_root(), "positions", "_active", folder_slug)
    jd_text = _read_jd(record)
    project = default_job_app_root()

    goal = f"Tailor resume and cover letter for {company} — {role}"
    next_steps = [
        f"Read `{folder_path}/JD.md` and `{WORKFLOW_SPEC}` Steps 0-7.",
        f"Write notes.md, cover-letter.md, tailored-resume.json, and build DOCX/PDF in `{folder_path}`.",
        "Include Match: NN% in notes.md after keyword analysis.",
        "Do not hand off mid-flow for PDF conversion.",
    ]
    content = build_handoff_content(
        source="odysseus",
        target=TARGET,
        project=project,
        goal=goal,
        context=[
            f"Job folder: `{folder_path}`",
            f"Odysseus job id: `{job_id}`",
        ],
        next_steps=next_steps,
    )
    if jd_text:
        content = content.rstrip() + f"\n\n## Full job description\n\n{jd_text.strip()}\n"

    doc_title = handoff_doc_title(TARGET, f"{company} — {role}")
    doc = _create_handoff_document(owner=owner or record.owner, title=doc_title, content=content)

    update_job_record(job_id, handoff_doc_id=doc.id)

    inbox_path = None
    relay_note_id = None
    if relay:
        relay_result = queue_handoff_relay_for_document(
            doc.id,
            owner=owner or record.owner,
            target=TARGET,
            relay=True,
        )
        inbox_path = relay_result.get("inbox_path")
        relay_note_id = relay_result.get("note_id")
        if relay_result.get("ok") and is_external_relay_target(TARGET):
            logger.info(
                "Tailoring handoff queued for external relay doc_id=%s note_id=%s",
                doc.id,
                relay_note_id,
            )

    # Lineage: job → handoff note (fail-soft; never blocks dispatch).
    handoff_target_id = relay_note_id or doc.id
    if handoff_target_id:
        try:
            from core.lineage import record_lineage_edge

            record_lineage_edge(
                source_kind="job",
                source_id=job_id,
                target_kind="handoff",
                target_id=str(handoff_target_id),
                relation="materialized",
            )
        except Exception as exc:
            logger.warning("lineage: job→handoff write failed for job %s: %s", job_id, exc)

    return {
        "handoff_doc_id": doc.id,
        "title": doc_title,
        "folder_path": folder_path,
        "inbox_path": inbox_path,
        "relay_note_id": relay_note_id,
        "target": TARGET,
    }
