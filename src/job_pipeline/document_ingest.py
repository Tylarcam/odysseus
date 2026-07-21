"""Ingest job pipeline events from library documents."""

from __future__ import annotations

import re
from typing import Any, Optional

from core.database import Document, Session as DbSession, SessionLocal
from src.document_processor import strip_pdf_content_marker
from src.job_pipeline.orchestrator import inbound_job_event
from src.job_pipeline.parser import parse_manual_ingest
from src.job_pipeline.title_parse import heuristic_company_role

_PDF_COMMENT_RE = re.compile(
    r"<!--\s*pdf_(?:form_)?source\s+upload_id=\"[^\"]+\"\s*-->\s*",
    re.I,
)
_MIN_JD_CHARS = 20


def _assert_doc_owner(doc: Document, owner: str, db) -> None:
    if doc.owner is not None:
        if doc.owner != owner:
            raise ValueError("Document not found")
        return
    if not doc.session_id:
        raise ValueError("Document not found")
    session = db.query(DbSession).filter(DbSession.id == doc.session_id).first()
    if not session or session.owner != owner:
        raise ValueError("Document not found")


def extract_jd_text_from_document_content(content: str) -> str:
    text = (content or "").strip()
    text = _PDF_COMMENT_RE.sub("", text, count=1).strip()
    text = strip_pdf_content_marker(text)
    return text.strip()


def build_document_job_payload(
    *,
    title: str = "",
    content: str = "",
    doc_id: str,
) -> dict[str, Any]:
    jd_text = extract_jd_text_from_document_content(content)
    if len(jd_text) < _MIN_JD_CHARS:
        raise ValueError(
            "No readable JD text — open the document and run Extract PDF text first"
        )
    company, role = heuristic_company_role(title, jd_text)
    parsed = parse_manual_ingest(
        {
            "company": company or "Unknown",
            "role": role or "Role",
            "jd_text": jd_text,
            "source": "document",
        }
    )
    payload = dict(parsed)
    payload["document_id"] = doc_id
    return payload


def ingest_document_to_job_pipeline(
    doc_id: str,
    *,
    owner: Optional[str] = None,
    auto_process: bool = True,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        doc = (
            db.query(Document)
            .filter(Document.id == doc_id, Document.is_active == True)  # noqa: E712
            .first()
        )
        if not doc:
            raise ValueError("Document not found")
        if owner:
            _assert_doc_owner(doc, owner, db)
        payload = build_document_job_payload(
            title=doc.title or "",
            content=doc.current_content or "",
            doc_id=doc_id,
        )
    finally:
        db.close()

    return inbound_job_event(
        payload,
        owner=owner,
        source="document",
        auto_process=auto_process,
    )
