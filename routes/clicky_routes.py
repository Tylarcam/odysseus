"""Clicky overlay launch routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.clicky_launcher import get_clicky_status, start_clicky
from src.auth_helpers import require_authenticated_request

logger = logging.getLogger(__name__)


class ClickyStartRequest(BaseModel):
    launch_app: bool = Field(default=True, description="Launch the WPF overlay after the worker is healthy")


def setup_clicky_routes() -> APIRouter:
    router = APIRouter()

    @router.get("/api/clicky/status")
    def clicky_status(request: Request) -> Dict[str, Any]:
        require_authenticated_request(request)
        return get_clicky_status()

    @router.post("/api/clicky/start")
    def clicky_start(request: Request, body: Optional[ClickyStartRequest] = None) -> Dict[str, Any]:
        require_authenticated_request(request)
        launch_app = True if body is None else bool(body.launch_app)
        result = start_clicky(launch_app=launch_app)
        if not result.get("ok"):
            raise HTTPException(status_code=503, detail=result.get("error") or "Clicky launch failed")
        return result

    return router
