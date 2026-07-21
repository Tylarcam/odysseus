# services/transcribe/video_transcriber.py
"""Full-transcript acquisition for agents — URL in, transcript out.

Waterfall:
  1. YouTube caption API (youtube_transcript_api) — instant, works when the
     video has captions and YouTube doesn't demand a browser session. Returns
     the FULL text (unlike the chat-context path, which truncates at 8k chars).
  2. Aether local server (node server.js on the host's residential IP) —
     yt-dlp audio download + chunked Groq Whisper. Handles caption-less and
     long videos. Requires the AetherServer scheduled task / npm run server
     to be running on the host machine.

Output is a normalized dict:
  { success, text, method, source_url, title, channel, duration_sec,
    char_count, warnings, error }
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# From inside the Odysseus container the host's localhost is host.docker.internal
# (extra_hosts: host-gateway in docker-compose.yml). Outside Docker, default to
# localhost.
def _aether_base() -> str:
    explicit = (os.getenv("AETHER_SERVER_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    if os.path.exists("/.dockerenv"):
        return "http://host.docker.internal:3000"
    return "http://localhost:3000"


AETHER_HEALTH_TIMEOUT = 5
# yt-dlp download + chunked Groq STT for a long video can take minutes.
AETHER_TRANSCRIBE_TIMEOUT = 20 * 60


def _normalize(
    *,
    success: bool,
    text: str = "",
    method: str = "",
    source_url: str = "",
    title: Optional[str] = None,
    channel: Optional[str] = None,
    duration_sec: Optional[int] = None,
    warnings: Optional[list] = None,
    error: str = "",
) -> Dict[str, Any]:
    return {
        "success": success,
        "text": text,
        "method": method,
        "source_url": source_url,
        "title": title,
        "channel": channel,
        "duration_sec": duration_sec,
        "char_count": len(text),
        "warnings": warnings or [],
        "error": error,
    }


async def _try_captions(url: str) -> Optional[Dict[str, Any]]:
    """Tier 1: server-side YouTube caption fetch. Returns None on any failure."""
    from services.youtube.youtube_handler import (
        is_youtube_url, extract_youtube_id, extract_transcript_async,
    )

    if not is_youtube_url(url):
        return None
    video_id = extract_youtube_id(url)
    if not video_id:
        return None

    data = await extract_transcript_async(url, video_id, max_retries=2)
    if not data.get("success"):
        logger.info("Caption tier failed for %s: %s", url, data.get("error"))
        return None

    # Rebuild the FULL text from segments — data["transcript"] is truncated
    # at 8k chars for chat-context injection, which is too short for briefs.
    segments = data.get("segments") or []
    full_text = " ".join(s["text"] for s in segments if s.get("text"))
    if not full_text:
        full_text = data.get("transcript") or ""
    if not full_text:
        return None

    warnings = []
    if data.get("is_generated"):
        warnings.append("auto-generated captions — expect some transcription errors")

    return _normalize(
        success=True,
        text=full_text,
        method="captions",
        source_url=url,
        duration_sec=int(segments[-1]["start"]) if segments else None,
        warnings=warnings,
    )


async def _try_aether_server(url: str) -> Optional[Dict[str, Any]]:
    """Tier 2: Aether local server (yt-dlp on residential IP + chunked Groq)."""
    base = _aether_base()
    try:
        async with httpx.AsyncClient(timeout=AETHER_HEALTH_TIMEOUT) as client:
            health = await client.get(f"{base}/health")
        if health.status_code != 200:
            logger.info("Aether server unhealthy (HTTP %s)", health.status_code)
            return None
    except Exception as e:
        logger.info("Aether server unreachable at %s: %s", base, e)
        return None

    try:
        async with httpx.AsyncClient(timeout=AETHER_TRANSCRIBE_TIMEOUT) as client:
            resp = await client.post(f"{base}/api/transcribe-url", json={"url": url})
        data = resp.json()
    except Exception as e:
        logger.warning("Aether transcribe-url call failed: %s", e)
        return None

    if not data.get("success") or not data.get("text"):
        logger.info("Aether transcribe-url unsuccessful: %s", data.get("error"))
        return None

    warnings = ["STT transcript (Groq Whisper) — no speaker labels or timestamps"]
    return _normalize(
        success=True,
        text=data["text"],
        method="local_ytdlp_groq",
        source_url=url,
        title=data.get("title"),
        channel=data.get("channel"),
        duration_sec=data.get("duration_sec"),
        warnings=warnings,
    )


async def transcribe_video_url(url: str) -> Dict[str, Any]:
    """Run the transcript waterfall for a video URL. Never raises."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return _normalize(success=False, source_url=url,
                          error="Provide a full http(s) video URL")

    try:
        result = await _try_captions(url)
        if result:
            return result
    except Exception as e:
        logger.warning("Caption tier raised for %s: %s", url, e)

    try:
        result = await _try_aether_server(url)
        if result:
            return result
    except Exception as e:
        logger.warning("Aether tier raised for %s: %s", url, e)

    return _normalize(
        success=False,
        source_url=url,
        error=(
            "All transcript paths failed. Captions unavailable via API, and the "
            "Aether local server could not transcribe the audio (not running, "
            "video blocked, or STT failed). Fallback: open the video in Chrome "
            "and use the Aether extension (captions or Record tab), then paste "
            "the transcript."
        ),
    )
