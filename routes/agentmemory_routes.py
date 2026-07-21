"""Proxy routes for AgentMemory long-term recall (handshake apply workflow)."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_PLAYBOOK = (
    r"C:\Users\tylar\code\notion\Projects\job-application-ops\config\handshake-apply-workflow.md"
)
DEFAULT_PROJECT_ROOT = r"C:\Users\tylar\code\notion\Projects\job-application-ops"


class AgentMemoryRememberRequest(BaseModel):
    slot: str = "handshake-apply-workflow"
    job_id: str = ""
    goal: str = ""
    refresh: bool = True


def _agentmemory_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    secret = (os.getenv("AGENTMEMORY_SECRET") or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return headers


def _load_playbook() -> str:
    playbook_path = (os.getenv("HANDSHAKE_APPLY_PLAYBOOK") or DEFAULT_PLAYBOOK).strip()
    if os.path.isfile(playbook_path):
        with open(playbook_path, encoding="utf-8") as fh:
            return fh.read()
    project_root = (os.getenv("JOB_APPLICATION_OPS_ROOT") or DEFAULT_PROJECT_ROOT).strip()
    return (
        "Handshake apply playbook not found on disk.\n"
        f"Expected: {playbook_path}\n"
        f"Project root: {project_root}\n"
        "Set HANDSHAKE_APPLY_PLAYBOOK or JOB_APPLICATION_OPS_ROOT in .env."
    )


def setup_agentmemory_routes() -> APIRouter:
    router = APIRouter(prefix="/api/agentmemory", tags=["agentmemory"])

    @router.post("/remember")
    async def remember_handshake_workflow(body: AgentMemoryRememberRequest) -> dict[str, Any]:
        """Save the Handshake apply workflow to AgentMemory long-term recall."""
        base_url = (os.getenv("AGENTMEMORY_URL") or "http://localhost:3111").rstrip("/")
        content = _load_playbook()
        project_root = (os.getenv("JOB_APPLICATION_OPS_ROOT") or DEFAULT_PROJECT_ROOT).strip()

        extra_lines = [
            "",
            "---",
            "Canonical project root:",
            project_root,
            "Playbook:",
            os.getenv("HANDSHAKE_APPLY_PLAYBOOK") or DEFAULT_PLAYBOOK,
            "Scripts:",
            f"{project_root}\\scripts\\convert-resume-pdf.ps1",
            f"{project_root}\\scripts\\handshake-upload-resume.ps1",
            "Browser:",
            "browser-harness + Comet CDP at BU_CDP_URL=http://127.0.0.1:9333 (not Docker MCP Playwright)",
        ]
        if body.job_id.strip():
            extra_lines.extend(["", f"Active Handshake job ID: {body.job_id.strip()}"])
        if body.goal.strip():
            extra_lines.extend([f"Goal: {body.goal.strip()}"])

        payload: dict[str, Any] = {
            "project": "job-application-ops",
            "title": body.slot or "handshake-apply-workflow",
            "content": content + "\n".join(extra_lines),
            "concepts": [
                "handshake",
                "job-application",
                "browser-harness",
                "comet-cdp",
                "single-session",
                "tailor-resume",
            ],
            "type": "workflow",
            "files": [
                os.getenv("HANDSHAKE_APPLY_PLAYBOOK") or DEFAULT_PLAYBOOK,
                f"{project_root}\\scripts\\convert-resume-pdf.ps1",
                f"{project_root}\\scripts\\handshake-upload-resume.ps1",
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                health = await client.get(f"{base_url}/agentmemory/health", headers=_agentmemory_headers())
                if health.status_code >= 500:
                    raise HTTPException(
                        503,
                        f"AgentMemory health check failed ({health.status_code}) at {base_url}",
                    )
                response = await client.post(
                    f"{base_url}/agentmemory/remember",
                    json=payload,
                    headers=_agentmemory_headers(),
                )
        except httpx.RequestError as exc:
            logger.warning("AgentMemory unreachable at %s: %s", base_url, exc)
            raise HTTPException(
                503,
                f"AgentMemory unreachable at {base_url}. Start with: npx -y @agentmemory/agentmemory",
            ) from exc

        if response.status_code >= 400:
            detail = (response.text or "").strip()[:500] or "remember failed"
            raise HTTPException(response.status_code, detail)

        data: Optional[dict[str, Any]] = None
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text[:500]}

        return {"ok": True, "slot": body.slot, "agentmemory": data}

    return router
