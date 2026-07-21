"""Transcription routes — POST /api/transcribe/url (video URL -> full transcript).

External surface for the transcribe_video waterfall (YouTube captions ->
Aether local server). Used by agents outside the chat loop (Claude Code /
Cursor skills, scripts) that hold an admin session or API token.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.middleware import require_admin

logger = logging.getLogger(__name__)


class TranscribeUrlRequest(BaseModel):
    url: str = Field(min_length=10, max_length=1000)


def setup_transcribe_routes() -> APIRouter:
    router = APIRouter(tags=["transcribe"])

    @router.post("/api/transcribe/url")
    async def transcribe_url(request: Request, body: TranscribeUrlRequest) -> Dict[str, Any]:
        """Run the transcript waterfall. Long videos can take minutes —
        callers should use a generous read timeout."""
        require_admin(request)
        from services.transcribe import transcribe_video_url
        return await transcribe_video_url(body.url)

    return router
