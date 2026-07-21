"""Job search pipeline API — Phase 1 ingest and listing."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.auth_helpers import effective_user
from src.job_pipeline.apply_queue import get_apply_package
from src.job_pipeline.orchestrator import (
    evaluate_job,
    inbound_job_event,
    mark_applied,
    process_job,
    tailor_job,
    validate_and_route,
)
from src.job_pipeline.store import (
    get_job_events,
    get_job_record,
    job_event_to_dict,
    job_record_to_dict,
    list_job_records,
)
from src.job_pipeline.validator import load_validation_report

logger = logging.getLogger(__name__)


class JobIngestRequest(BaseModel):
    jd_text: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    source: Optional[str] = "manual"
    apply_url: Optional[str] = None
    handshake_job_id: Optional[str] = None
    location: Optional[str] = None
    compensation: Optional[str] = None
    confidence: Optional[float] = None


class JobEmailIngestRequest(BaseModel):
    uid: Optional[str] = None
    folder: str = "INBOX"
    subject: Optional[str] = None
    body: Optional[str] = None
    message_id: Optional[str] = None
    auto_process: bool = True


class JobDocumentIngestRequest(BaseModel):
    doc_id: str = Field(..., min_length=1)
    auto_process: bool = True


def setup_job_routes() -> APIRouter:
    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    def _owner(request: Request) -> Optional[str]:
        try:
            return effective_user(request)
        except Exception:
            return None

    @router.post("/ingest")
    def ingest_job(
        request: Request,
        body: JobIngestRequest,
        auto_process: bool = Query(False),
    ) -> dict[str, Any]:
        owner = _owner(request)
        payload = body.model_dump(exclude_none=True)
        payload.setdefault("source", "manual")
        record = inbound_job_event(
            payload,
            owner=owner,
            source=payload.get("source"),
            auto_process=auto_process,
        )
        return {"job": record}

    @router.post("/ingest-from-email")
    def ingest_from_email(
        request: Request,
        body: JobEmailIngestRequest,
    ) -> dict[str, Any]:
        from src.job_pipeline.email_ingest import ingest_email_to_job_pipeline

        owner = _owner(request)
        subject = (body.subject or "").strip()
        email_body = (body.body or "").strip()
        if not email_body and not subject:
            raise HTTPException(400, "Email subject or body required")
        try:
            job = ingest_email_to_job_pipeline(
                subject=subject,
                body=email_body,
                message_id=body.message_id,
                uid=body.uid,
                owner=owner,
                auto_process=body.auto_process,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            logger.exception("ingest-from-email failed uid=%s", body.uid)
            raise HTTPException(500, "Job pipeline ingest failed") from exc
        return {"job": job}

    @router.post("/ingest-from-document")
    def ingest_from_document(
        request: Request,
        body: JobDocumentIngestRequest,
    ) -> dict[str, Any]:
        from src.job_pipeline.document_ingest import ingest_document_to_job_pipeline

        owner = _owner(request)
        try:
            job = ingest_document_to_job_pipeline(
                body.doc_id,
                owner=owner,
                auto_process=body.auto_process,
            )
        except ValueError as exc:
            msg = str(exc)
            if "not found" in msg.lower():
                raise HTTPException(404, msg) from exc
            raise HTTPException(400, msg) from exc
        except Exception as exc:
            logger.exception("ingest-from-document failed doc_id=%s", body.doc_id)
            raise HTTPException(500, "Job pipeline ingest failed") from exc
        return {"job": job}

    @router.post("/{job_id}/evaluate")
    def evaluate_job_route(request: Request, job_id: str) -> dict[str, Any]:
        record = get_job_record(job_id)
        if not record:
            raise HTTPException(404, "Job record not found")
        owner = _owner(request)
        if owner and record.owner and record.owner != owner:
            raise HTTPException(404, "Job record not found")
        try:
            job = evaluate_job(job_id, owner=owner)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"job": job}

    @router.post("/{job_id}/tailor")
    def tailor_job_route(request: Request, job_id: str) -> dict[str, Any]:
        record = get_job_record(job_id)
        if not record:
            raise HTTPException(404, "Job record not found")
        owner = _owner(request)
        if owner and record.owner and record.owner != owner:
            raise HTTPException(404, "Job record not found")
        try:
            job = tailor_job(job_id, owner=owner)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"job": job}

    @router.get("/{job_id}")
    def get_job(request: Request, job_id: str) -> dict[str, Any]:
        record = get_job_record(job_id)
        if not record:
            raise HTTPException(404, "Job record not found")
        owner = _owner(request)
        if owner and record.owner and record.owner != owner:
            raise HTTPException(404, "Job record not found")
        events = get_job_events(job_id)
        return {
            "job": job_record_to_dict(record),
            "events": [job_event_to_dict(e) for e in events],
        }

    @router.get("")
    def list_jobs(
        request: Request,
        limit: int = Query(50, ge=1, le=200),
        status: Optional[str] = Query(None),
    ) -> dict[str, Any]:
        owner = _owner(request)
        records = list_job_records(limit=limit, status=status, owner=owner)
        return {"jobs": [job_record_to_dict(r) for r in records]}

    @router.post("/{job_id}/validate")
    def validate_job(request: Request, job_id: str) -> dict[str, Any]:
        record = get_job_record(job_id)
        if not record:
            raise HTTPException(404, "Job record not found")
        owner = _owner(request)
        if owner and record.owner and record.owner != owner:
            raise HTTPException(404, "Job record not found")
        try:
            result = validate_and_route(job_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return result

    @router.get("/{job_id}/validation")
    def get_validation(request: Request, job_id: str) -> dict[str, Any]:
        record = get_job_record(job_id)
        if not record:
            raise HTTPException(404, "Job record not found")
        owner = _owner(request)
        if owner and record.owner and record.owner != owner:
            raise HTTPException(404, "Job record not found")
        report = load_validation_report(record.validation_report_path or "")
        return {
            "job_id": job_id,
            "validation_report_path": record.validation_report_path,
            "terminal_status": record.terminal_status,
            "validation_report": report,
        }

    @router.get("/{job_id}/apply-package")
    def get_apply_package_route(request: Request, job_id: str) -> dict[str, Any]:
        record = get_job_record(job_id)
        if not record:
            raise HTTPException(404, "Job record not found")
        owner = _owner(request)
        if owner and record.owner and record.owner != owner:
            raise HTTPException(404, "Job record not found")
        try:
            package = get_apply_package(job_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"job_id": job_id, "apply_package": package}

    @router.post("/{job_id}/mark-applied")
    def mark_applied_route(request: Request, job_id: str) -> dict[str, Any]:
        record = get_job_record(job_id)
        if not record:
            raise HTTPException(404, "Job record not found")
        owner = _owner(request)
        if owner and record.owner and record.owner != owner:
            raise HTTPException(404, "Job record not found")
        try:
            job = mark_applied(job_id, owner=owner)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        return {"job": job}

    return router
