"""API for handoff relay status and external agent completion."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.auth_helpers import effective_user
from src.handoff_relay import (
    claim_external_relay,
    complete_external_relay,
    list_pending_external,
    queue_handoff_relay_for_document,
)

router = APIRouter(prefix="/api/handoff-relay", tags=["handoff-relay"])


def _owner(request: Request) -> Optional[str]:
    """Resolve note owner for bearer tokens (api_token_owner), not pseudo-user 'api'."""
    try:
        return effective_user(request)
    except Exception:
        return None


class HandoffRelayCompleteRequest(BaseModel):
    outcome: str = ""
    status: str = "complete"


@router.get("/pending")
def pending_handoffs(request: Request, target: Optional[str] = None):
    """Pending cursor/claude handoffs for external CLIs — full packet, no ID paste."""
    owner = _owner(request)
    return {"handoffs": list_pending_external(owner, target=target)}


@router.post("/{doc_id}/queue")
def queue_handoff_relay(request: Request, doc_id: str):
    """Queue relay for a handoff document (repair or manual trigger)."""
    owner = _owner(request)
    result = queue_handoff_relay_for_document(doc_id, owner=owner, relay=True)
    if not result.get("ok"):
        reason = result.get("reason") or "queue_failed"
        if reason == "forbidden":
            raise HTTPException(403, "Forbidden")
        if reason == "document_not_found":
            raise HTTPException(404, "Document not found")
        raise HTTPException(400, reason)
    return result


@router.post("/{doc_id}/claim")
def claim_handoff_relay(request: Request, doc_id: str, session_id: Optional[str] = None):
    """Mark a queued cursor/claude handoff as running (CLI watcher / pickup)."""
    owner = _owner(request)
    ok = claim_external_relay(doc_id, owner, session_id=session_id)
    if not ok:
        raise HTTPException(404, "Handoff relay not found or not claimable")
    return {"ok": True, "doc_id": doc_id, "status": "running", "session_id": session_id}


@router.post("/{doc_id}/complete")
async def complete_handoff_relay(request: Request, doc_id: str, body: HandoffRelayCompleteRequest):
    """Mark an external relay complete (Cursor/Claude CLI watcher)."""
    owner = _owner(request)
    ok = await complete_external_relay(
        doc_id,
        owner,
        outcome=body.outcome,
        status=body.status if body.status in ("complete", "failed") else "complete",
    )
    if not ok:
        raise HTTPException(404, "Handoff relay not found")
    return {"ok": True, "doc_id": doc_id, "status": body.status}
