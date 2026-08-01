"""Deterministic job pipeline state machine."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.job_pipeline.deduper import check_duplicate
from src.job_pipeline.materialize import materialize_job_jd
from src.job_pipeline.parser import compute_dedup_key, parse_raw
from src.job_pipeline.store import (
    add_job_event,
    create_job_record,
    get_job_record,
    job_record_to_dict,
    update_job_record,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
TERMINAL_STATUSES = frozenset({
    "archived", "error", "rejected", "tailoring_started",
    "applied", "ready_to_apply", "needs_review", "validated",
})
VALIDATION_STATUSES = frozenset({"tailoring_started", "tailoring_complete"})


def _transition(
    job_id: str,
    *,
    from_status: Optional[str],
    to_status: str,
    stage: str,
    message: str,
    detail: Optional[dict[str, Any]] = None,
    **fields: Any,
) -> None:
    add_job_event(
        job_id=job_id,
        from_status=from_status,
        to_status=to_status,
        stage=stage,
        message=message,
        detail=detail,
    )
    update_job_record(job_id, status=to_status, **fields)


def _fail(job_id: str, from_status: str, stage: str, message: str, retry_count: int) -> dict[str, Any]:
    _transition(
        job_id,
        from_status=from_status,
        to_status="error",
        stage=stage,
        message=message,
        error_message=message,
        retry_count=retry_count,
    )
    record = get_job_record(job_id)
    return job_record_to_dict(record) if record else {"id": job_id, "status": "error"}


def _stage_parse(job_id: str, raw_input: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
    try:
        parsed = parse_raw(raw_input)
        return True, parsed, ""
    except Exception as exc:
        return False, {}, str(exc)


def _stage_normalize(parsed: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(parsed)
    normalized["dedup_key"] = compute_dedup_key(
        normalized.get("company"),
        normalized.get("role"),
        normalized.get("apply_url"),
    )
    return normalized


def process_job_record(job_id: str) -> dict[str, Any]:
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if record.status in TERMINAL_STATUSES:
        return job_record_to_dict(record)

    raw_input = record.raw_input or {}
    retries = record.retry_count or 0
    status = record.status

    if status == "email_received":
        ok, parsed, err = _stage_parse(job_id, raw_input)
        if not ok:
            if retries < MAX_RETRIES:
                update_job_record(job_id, retry_count=retries + 1)
                return process_job_record(job_id)
            return _fail(job_id, status, "parse", err or "parse failed", retries + 1)
        _transition(
            job_id,
            from_status=status,
            to_status="parsed",
            stage="parse",
            message="Parsed raw input",
            detail={"fields": list(parsed.keys())},
            **{k: parsed.get(k) for k in (
                "company", "role", "location", "compensation", "source",
                "apply_url", "handshake_job_id", "jd_text", "confidence",
            )},
        )
        status = "parsed"

    record = get_job_record(job_id)
    if not record or record.status != "parsed":
        return job_record_to_dict(record) if record else {"id": job_id}

    if record.status == "parsed":
        try:
            normalized = _stage_normalize(
                {
                    "company": record.company,
                    "role": record.role,
                    "location": record.location,
                    "compensation": record.compensation,
                    "source": record.source,
                    "apply_url": record.apply_url,
                    "handshake_job_id": record.handshake_job_id,
                    "jd_text": record.jd_text,
                    "confidence": record.confidence,
                }
            )
        except Exception as exc:
            if retries < MAX_RETRIES:
                update_job_record(job_id, retry_count=retries + 1)
                return process_job_record(job_id)
            return _fail(job_id, record.status, "normalize", str(exc), retries + 1)
        _transition(
            job_id,
            from_status="parsed",
            to_status="normalized",
            stage="normalize",
            message="Normalized fields and dedup key",
            detail={"dedup_key": normalized["dedup_key"]},
            dedup_key=normalized["dedup_key"],
        )
        try:
            from src.job_pipeline.research_enrichment import maybe_start_job_research

            maybe_start_job_research(job_id, owner=record.owner)
        except Exception as exc:
            logger.debug("Research enrichment hook skipped: %s", exc)

    record = get_job_record(job_id)
    if not record or record.status != "normalized":
        return job_record_to_dict(record) if record else {"id": job_id}

    dup = check_duplicate(
        job_id=job_id,
        company=record.company,
        role=record.role,
        apply_url=record.apply_url,
        jd_text=record.jd_text,
    )
    if dup["is_duplicate"]:
        _transition(
            job_id,
            from_status="normalized",
            to_status="archived",
            stage="dedup",
            message=f"Duplicate detected ({dup['reason']})",
            detail=dup,
            duplicate_of_id=str(dup["duplicate_of_id"]) if dup["duplicate_of_id"] else None,
        )
        record = get_job_record(job_id)
        return job_record_to_dict(record) if record else {"id": job_id}

    if not (record.jd_text or "").strip():
        return _fail(job_id, "normalized", "materialize", "Missing jd_text", retries)

    try:
        result = materialize_job_jd(
            job_id=job_id,
            company=record.company or "Unknown",
            role=record.role or "Role",
            jd_text=record.jd_text or "",
        )
    except OSError as exc:
        if retries < MAX_RETRIES:
            update_job_record(job_id, retry_count=retries + 1)
            return process_job_record(job_id)
        return _fail(job_id, "normalized", "materialize", str(exc), retries + 1)

    _transition(
        job_id,
        from_status="normalized",
        to_status="deduped",
        stage="dedup",
        message="New job materialized",
        detail=result,
        folder_slug=result.get("folder"),
        jd_path=result.get("jd_path"),
    )
    record = get_job_record(job_id)
    return job_record_to_dict(record) if record else {"id": job_id}


def _stage_evaluate_retries(job_id: str) -> int:
    from src.job_pipeline.store import get_job_events

    return sum(
        1
        for e in get_job_events(job_id)
        if e.stage == "evaluate" and e.to_status == "error"
    )


def _stage_dispatch_retries(job_id: str) -> int:
    from src.job_pipeline.store import get_job_events

    return sum(
        1
        for e in get_job_events(job_id)
        if e.stage == "dispatch" and e.to_status == "error"
    )


def evaluate_job(job_id: str, *, owner: Optional[str] = None) -> dict[str, Any]:
    """Run evaluation gate: deduped → evaluated → rejected (if below gate)."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if record.status in ("rejected", "tailoring_started", "archived", "error"):
        return job_record_to_dict(record)
    if record.status not in ("deduped", "evaluated"):
        raise ValueError(f"job {job_id} not ready for evaluation (status={record.status})")

    from src.job_pipeline.evaluator import run_evaluation

    retries = _stage_evaluate_retries(job_id)
    try:
        result = run_evaluation(job_id, owner=owner or record.owner)
    except Exception as exc:
        if retries < MAX_RETRIES:
            _transition(
                job_id,
                from_status=record.status,
                to_status="error",
                stage="evaluate",
                message=str(exc),
            )
            update_job_record(job_id, status=record.status)
            return evaluate_job(job_id, owner=owner)
        return _fail(job_id, record.status, "evaluate", str(exc), retries + 1)

    if result.get("gate_score") is None and not result.get("proceed"):
        _transition(
            job_id,
            from_status=record.status,
            to_status="rejected",
            stage="evaluate",
            message=result.get("reason") or "score unavailable",
            detail=result,
            terminal_status="below_gate",
            error_message=result.get("reason"),
        )
        record = get_job_record(job_id)
        return job_record_to_dict(record) if record else {"id": job_id, "status": "rejected"}

    _transition(
        job_id,
        from_status=record.status,
        to_status="evaluated",
        stage="evaluate",
        message=f"Gate score {result.get('gate_score')}",
        detail=result,
        match_score=result.get("match_score"),
        gate_score=str(result.get("gate_score")) if result.get("gate_score") is not None else None,
        profile=result.get("profile"),
        evaluation_path=result.get("evaluation_path"),
    )

    if not result.get("proceed"):
        _transition(
            job_id,
            from_status="evaluated",
            to_status="rejected",
            stage="evaluate",
            message=f"Below gate ({result.get('gate_score')})",
            detail=result,
            terminal_status="below_gate",
        )

    record = get_job_record(job_id)
    return job_record_to_dict(record) if record else {"id": job_id}


def tailor_job(job_id: str, *, owner: Optional[str] = None) -> dict[str, Any]:
    """Dispatch Cursor handoff: evaluated (4.0+) → tailoring_started."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if record.status == "tailoring_started":
        return job_record_to_dict(record)
    if record.status != "evaluated":
        raise ValueError(f"job {job_id} must be evaluated with proceed=true (status={record.status})")
    try:
        gate = float(record.gate_score or 0)
    except (TypeError, ValueError):
        gate = 0.0
    if gate < 4.0:
        raise ValueError(f"job {job_id} below evaluation gate")

    from src.job_pipeline.tailoring_dispatch import dispatch_tailoring

    retries = _stage_dispatch_retries(job_id)
    try:
        dispatch = dispatch_tailoring(job_id, owner=owner or record.owner)
    except Exception as exc:
        if retries < MAX_RETRIES:
            _transition(
                job_id,
                from_status="evaluated",
                to_status="error",
                stage="dispatch",
                message=str(exc),
            )
            update_job_record(job_id, status="evaluated")
            return tailor_job(job_id, owner=owner)
        return _fail(job_id, "evaluated", "dispatch", str(exc), retries + 1)

    _transition(
        job_id,
        from_status="evaluated",
        to_status="tailoring_started",
        stage="dispatch",
        message="Tailoring handoff dispatched to Cursor",
        detail=dispatch,
        handoff_doc_id=dispatch.get("handoff_doc_id"),
        terminal_status="tailoring_dispatched",
    )
    record = get_job_record(job_id)
    return job_record_to_dict(record) if record else {"id": job_id}


def process_job(job_id: str, *, auto_tailor: bool = True, owner: Optional[str] = None) -> dict[str, Any]:
    """Run Phase 1 ingest then optional evaluate + tailor."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")

    if record.status in ("email_received", "parsed", "normalized"):
        process_job_record(job_id)
        record = get_job_record(job_id)
        if not record or record.status != "deduped":
            return job_record_to_dict(record) if record else {"id": job_id}

    record = get_job_record(job_id)
    if not record:
        return {"id": job_id}
    if record.status == "deduped":
        evaluate_job(job_id, owner=owner)
        record = get_job_record(job_id)
    if not record:
        return {"id": job_id}
    if record.status == "evaluated" and auto_tailor:
        try:
            gate = float(record.gate_score or 0)
        except (TypeError, ValueError):
            gate = 0.0
        if gate >= 4.0:
            tailor_job(job_id, owner=owner)
            record = get_job_record(job_id)

    return job_record_to_dict(record) if record else {"id": job_id}


def inbound_job_event(
    raw_input: dict[str, Any],
    *,
    owner: Optional[str] = None,
    source: Optional[str] = None,
    auto_process: bool = False,
) -> dict[str, Any]:
    """Entry point for email or manual job ingest."""
    payload = dict(raw_input)
    if source:
        payload.setdefault("source", source)
    record = create_job_record(
        owner=owner,
        status="email_received",
        source=payload.get("source") or source or "manual",
        raw_input=payload,
    )
    add_job_event(
        job_id=record.id,
        from_status=None,
        to_status="email_received",
        stage="ingest",
        message="Job ingest received",
        detail={"source": record.source},
    )
    if auto_process:
        return process_job(record.id, owner=owner)
    return process_job_record(record.id)


def validate_and_route(job_id: str) -> dict[str, Any]:
    """Validate tailored artifacts and route to terminal_status."""
    from src.job_pipeline.apply_queue import on_ready_to_apply
    from src.job_pipeline.notifier import notify_validation_terminal
    from src.job_pipeline.routing import route_job, routing_reasons
    from src.job_pipeline.validator import (
        resolve_job_folder,
        validate_job_folder,
        write_validation_report,
    )

    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")

    if record.status == "tailoring_started":
        _transition(
            job_id,
            from_status="tailoring_started",
            to_status="tailoring_complete",
            stage="handoff_complete",
            message="Tailoring handoff completed",
        )
        record = get_job_record(job_id)
    elif record.status not in VALIDATION_STATUSES.union({"validated"}):
        if record.status in ("ready_to_apply", "needs_review") or record.terminal_status:
            return {
                "job": job_record_to_dict(record),
                "validation_report": None,
                "terminal_status": record.terminal_status,
            }
        raise ValueError(f"job not ready for validation (status={record.status})")

    folder = resolve_job_folder(record)
    if folder is None:
        retries = record.retry_count or 0
        if retries < MAX_RETRIES:
            update_job_record(job_id, retry_count=retries + 1)
            record = get_job_record(job_id)
        else:
            return _fail(job_id, record.status if record else "tailoring_complete", "validate", "job folder missing", retries + 1)
        folder = resolve_job_folder(record)

    if folder is None or not folder.exists():
        return _fail(
            job_id,
            record.status if record else "tailoring_complete",
            "validate",
            f"job folder not found: {folder}",
            (record.retry_count or 0) + 1,
        )

    report = validate_job_folder(folder)
    report_path = write_validation_report(folder, report)
    terminal_status = route_job(record, report)
    reasons = routing_reasons(record, report, terminal_status)

    if terminal_status == "error":
        _transition(
            job_id,
            from_status=record.status,
            to_status="error",
            stage="validate",
            message="Validation failed — retries exhausted",
            detail={"validation_report": report, "reasons": reasons},
            terminal_status="error",
            validation_report_path=report_path,
            error_message="; ".join(reasons[:3]) or "validation error",
        )
    else:
        route_status = (
            terminal_status
            if terminal_status in ("ready_to_apply", "needs_review")
            else "validated"
        )
        _transition(
            job_id,
            from_status=record.status,
            to_status=route_status,
            stage="validate",
            message=f"Validation routed to {terminal_status}",
            detail={"validation_report": report, "reasons": reasons},
            terminal_status=terminal_status,
            validation_report_path=report_path,
        )
        if terminal_status == "ready_to_apply":
            try:
                on_ready_to_apply(job_id)
            except Exception as exc:
                logger.warning("Apply package hook failed for %s: %s", job_id, exc)

    record = get_job_record(job_id)
    if record:
        notify_validation_terminal(record, terminal_status, report, reasons)

    return {
        "job": job_record_to_dict(record) if record else {"id": job_id},
        "validation_report": report,
        "terminal_status": terminal_status,
        "reasons": reasons,
    }


def transition_to_ready_to_apply(job_id: str, **fields: Any) -> dict[str, Any]:
    """Phase 3→4 handoff: package apply materials and notify user."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if record.status == "ready_to_apply":
        from src.job_pipeline.apply_queue import get_apply_package

        return {"job": job_record_to_dict(record), "apply_package": get_apply_package(job_id)}

    from_status = record.status
    _transition(
        job_id,
        from_status=from_status,
        to_status="ready_to_apply",
        stage="ready",
        message="Application package ready for human submit",
        **fields,
    )
    from src.job_pipeline.apply_queue import on_ready_to_apply

    package = on_ready_to_apply(job_id)
    record = get_job_record(job_id)
    return {"job": job_record_to_dict(record) if record else {"id": job_id}, "apply_package": package}


def mark_applied(job_id: str, *, owner: Optional[str] = None, notion_client: Any = None) -> dict[str, Any]:
    """User confirmed Handshake submission — terminal applied state."""
    from src.job_pipeline.apply_queue import mark_applied as _mark_applied
    from src.job_pipeline.notifier import notify_applied

    result = _mark_applied(job_id, owner=owner, notion_client=notion_client)
    record = get_job_record(job_id)
    if record:
        notify_applied(record)
    return result


def archive_job(
    job_id: str,
    *,
    owner: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """User-initiated archive — terminal archived without implying an application.

    Idempotent when already archived. Allowed from any status (including
    applied) so mistaken mark_applied rows can be cleaned up. Does not
    schedule follow-up tasks.
    """
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if owner and record.owner and record.owner != owner:
        raise ValueError("access denied")
    if record.status == "archived":
        return job_record_to_dict(record)

    from_status = record.status
    msg = (reason or "").strip() or "User archived job"
    _transition(
        job_id,
        from_status=from_status,
        to_status="archived",
        stage="user_archive",
        message=msg,
        detail={"reason": reason or "user_declined", "prior_status": from_status},
        terminal_status="archived",
    )
    record = get_job_record(job_id)
    return job_record_to_dict(record) if record else {"id": job_id, "status": "archived"}
