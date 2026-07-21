"""Apply package composition and human confirmation (Phase 4)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from src.handoff_materialize import default_job_app_root
from src.job_pipeline.store import (
    add_job_event,
    get_job_record,
    job_record_to_dict,
    update_job_record,
)

logger = logging.getLogger(__name__)

HANDSHAKE_APPLY_PROJECT = default_job_app_root()
HANDSHAKE_APPLY_PLAYBOOK = os.path.join(HANDSHAKE_APPLY_PROJECT, "config", "handshake-apply-workflow.md")

_PDF_CANDIDATES = ("resume.pdf", "Resume.pdf", "TylarCampbell_Resume.pdf")
_COVER_LETTER_CANDIDATES = (
    "cover-letter.md",
    "CoverLetter.md",
    "cover_letter.md",
    "CoverLetter.docx",
)


def compose_handshake_apply_message(
    *,
    handshake_job_id: Optional[str] = None,
    goal: Optional[str] = None,
) -> str:
    """Mirror static/js/slashCommands.js _composeHandshakeApplyMessage."""
    lines = [
        "Run the Handshake job-application workflow end-to-end in ONE session (no mid-flow handoffs).",
        "",
        "Rules:",
        "- Use browser-harness + Comet CDP (BU_CDP_URL=http://127.0.0.1:9333), NOT Docker MCP Playwright.",
        "- Stop once if login wall (/access); user finishes OTP in Comet, then continue.",
        "- Same agent builds DOCX, converts PDF, and uploads — do not hand off between those steps.",
        "- Stop before Submit Application; user clicks Submit after preview.",
        "",
        "Ordered steps:",
        "A. JD capture → save positions/_active/<Folder>/JD.md",
        "B. Tailor package → notes, answers, cover letter, build script, DOCX (state Profile + match %)",
        f"C. PDF → {HANDSHAKE_APPLY_PROJECT}\\scripts\\convert-resume-pdf.ps1",
        f"D. Upload → {HANDSHAKE_APPLY_PROJECT}\\scripts\\handshake-upload-resume.ps1 -JobId <ID> -PdfPath <pdf> -StopBeforeSubmit",
        "E. User submits in Comet",
        "F. Post-submit → status.md + SESSION_LOG.md",
        "",
        f"Playbook: {HANDSHAKE_APPLY_PLAYBOOK}",
        f"Project: {HANDSHAKE_APPLY_PROJECT}",
    ]
    if handshake_job_id:
        lines.extend(
            [
                "",
                f"Handshake job ID: {handshake_job_id}",
                f"Job URL: https://stanford.joinhandshake.com/jobs/{handshake_job_id}",
            ]
        )
    if goal:
        lines.extend(["", f"Goal: {goal}"])
    lines.extend(
        [
            "",
            "Follow the playbook Procedure / Pitfalls. Ask only if login or missing prerequisites block progress.",
        ]
    )
    return "\n".join(lines)


def _job_folder_path(record) -> Optional[str]:
    slug = (record.folder_slug or "").strip()
    if not slug:
        jd_path = (record.jd_path or "").strip()
        if jd_path:
            return os.path.dirname(jd_path)
        return None
    root = default_job_app_root()
    return os.path.join(root, "positions", "_active", slug)


def _first_existing(folder: str, names: tuple[str, ...]) -> Optional[str]:
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None


def _find_pdf(folder: str) -> Optional[str]:
    found = _first_existing(folder, _PDF_CANDIDATES)
    if found:
        return found
    try:
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(".pdf"):
                return os.path.join(folder, name)
    except OSError:
        pass
    return None


def resolve_job_artifact_paths(record) -> dict[str, Optional[str]]:
    folder_path = _job_folder_path(record)
    if not folder_path:
        return {
            "folder_path": None,
            "jd_path": record.jd_path,
            "pdf_path": None,
            "cover_letter_path": None,
        }
    return {
        "folder_path": folder_path,
        "jd_path": record.jd_path or _first_existing(folder_path, ("JD.md",)),
        "pdf_path": _find_pdf(folder_path),
        "cover_letter_path": _first_existing(folder_path, _COVER_LETTER_CANDIDATES),
    }


def build_apply_package(record) -> dict[str, Any]:
    paths = resolve_job_artifact_paths(record)
    goal = f"{record.company or 'Company'} {record.role or 'Role'}".strip()
    package = {
        "job_id": record.id,
        "company": record.company,
        "role": record.role,
        "folder": record.folder_slug,
        "folder_path": paths["folder_path"],
        "jd_path": paths["jd_path"],
        "pdf_path": paths["pdf_path"],
        "cover_letter_path": paths["cover_letter_path"],
        "handshake_job_id": record.handshake_job_id,
        "apply_url": record.apply_url,
        "composed_message": compose_handshake_apply_message(
            handshake_job_id=record.handshake_job_id,
            goal=goal,
        ),
        "mark_applied_path": f"/api/jobs/{record.id}/mark-applied",
        "apply_package_path": None,
        "playbook_path": HANDSHAKE_APPLY_PLAYBOOK,
        "project_path": HANDSHAKE_APPLY_PROJECT,
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }
    return package


def persist_apply_package(job_id: str, package: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    package = package or build_apply_package(record)
    folder_path = package.get("folder_path")
    artifact_path = None
    if folder_path and os.path.isdir(folder_path):
        artifact_path = os.path.join(folder_path, "apply-package.json")
        try:
            with open(artifact_path, "w", encoding="utf-8") as fh:
                json.dump(package, fh, indent=2)
                fh.write("\n")
            package["apply_package_path"] = artifact_path
        except OSError as exc:
            logger.warning("Failed to write apply-package.json for %s: %s", job_id, exc)
    update_job_record(job_id, apply_package_json=package)
    return package


def get_apply_package(job_id: str) -> dict[str, Any]:
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if record.apply_package_json:
        return dict(record.apply_package_json)
    package = persist_apply_package(job_id)
    return package


def _write_status_md(record, *, applied_at: datetime) -> Optional[str]:
    """Best-effort status.md write — never block mark_applied on disk/permission errors."""
    paths = resolve_job_artifact_paths(record)
    folder_path = paths.get("folder_path")
    if not folder_path:
        return None
    status_path = os.path.join(folder_path, "status.md")
    lines = [
        "# Application Status",
        "",
        f"- **Status:** applied",
        f"- **Applied at:** {applied_at.isoformat()}",
        f"- **Company:** {record.company or ''}",
        f"- **Role:** {record.role or ''}",
    ]
    if record.handshake_job_id:
        lines.append(f"- **Handshake job ID:** {record.handshake_job_id}")
    if record.apply_url:
        lines.append(f"- **Apply URL:** {record.apply_url}")
    lines.extend(["", "Confirmed via Odysseus job pipeline.", ""])
    try:
        os.makedirs(folder_path, exist_ok=True)
        with open(status_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return status_path
    except OSError as exc:
        # Docker often has no writable JOB_APPLICATION_OPS_ROOT mount (/app/code/...).
        # DB status update must still succeed.
        logger.warning("Failed to write status.md for %s at %s: %s", record.id, status_path, exc)
        return None


def maybe_update_notion_applied(record, *, notion_client: Any = None) -> dict[str, Any]:
    """Optional Notion sync — skipped when notion_page_id absent or client not provided."""
    page_id = (record.notion_page_id or "").strip()
    if not page_id:
        return {"skipped": True, "reason": "no notion_page_id"}
    if notion_client is None:
        return {"skipped": True, "reason": "notion_client_not_configured", "notion_page_id": page_id}
    try:
        notion_client.pages.update(page_id, properties={"Status": {"select": {"name": "Applied"}}})
        return {"ok": True, "notion_page_id": page_id}
    except Exception as exc:
        logger.warning("Notion update failed for job %s: %s", record.id, exc)
        return {"ok": False, "error": str(exc), "notion_page_id": page_id}


def mark_applied(
    job_id: str,
    *,
    owner: Optional[str] = None,
    notion_client: Any = None,
) -> dict[str, Any]:
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if owner and record.owner and record.owner != owner:
        raise ValueError("access denied")
    if record.status == "applied":
        return job_record_to_dict(record)

    applied_at = datetime.now(timezone.utc).replace(tzinfo=None)
    from_status = record.status
    status_path = _write_status_md(record, applied_at=applied_at)
    notion_result = maybe_update_notion_applied(record, notion_client=notion_client)

    update_job_record(
        job_id,
        status="applied",
        terminal_status="applied",
        applied_at=applied_at,
    )
    add_job_event(
        job_id=job_id,
        from_status=from_status,
        to_status="applied",
        stage="apply_confirm",
        message="User confirmed Handshake submission",
        detail={"status_md": status_path, "notion": notion_result},
    )

    from src.job_pipeline.followups import schedule_followup

    try:
        schedule_followup(job_id, days=7, owner=record.owner)
    except Exception as exc:
        logger.warning("Follow-up scheduling failed for %s: %s", job_id, exc)

    record = get_job_record(job_id)
    return job_record_to_dict(record) if record else {"id": job_id, "status": "applied"}


def on_ready_to_apply(job_id: str) -> dict[str, Any]:
    """Build apply package when job enters ready_to_apply."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")

    ready_at = datetime.now(timezone.utc).replace(tzinfo=None)
    package = persist_apply_package(job_id)
    update_job_record(job_id, ready_to_apply_at=ready_at)

    from src.job_pipeline.followups import schedule_ready_to_apply_reminder
    from src.job_pipeline.notifier import notify_ready_to_apply

    try:
        schedule_ready_to_apply_reminder(job_id, owner=record.owner)
    except Exception as exc:
        logger.warning("Ready-to-apply reminder failed for %s: %s", job_id, exc)

    notify_ready_to_apply(record, package)
    return package
