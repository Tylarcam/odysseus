# routes/stt_routes.py
"""STT API routes — multi-provider (local Whisper, API endpoint, browser)."""

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
import logging

from src.upload_limits import read_upload_limited, STT_MAX_AUDIO_BYTES

logger = logging.getLogger(__name__)


def _stt_unavailable_message(stats: dict) -> str:
    """Actionable 503 detail from get_stats() — mirrors Settings status hints."""
    provider = stats.get("provider", "disabled")
    if provider == "browser":
        return (
            'STT provider is "browser" — audio is transcribed in the browser, '
            "not on the server. Choose Local (Whisper) in Settings > Audio & Voice, "
            "or retry from a browser that supports speech recognition."
        )
    if provider == "local":
        reason = stats.get("reason") or stats.get("local_status") or ""
        if reason == "missing_package":
            return (
                'Local Whisper is not installed on the server (provider: "local"). '
                "Rebuild with INSTALL_STT=true or pip install faster-whisper. "
                "Or switch STT to Browser in Settings > Audio & Voice."
            )
        if reason == "load_failed":
            detail = stats.get("local_detail") or "model load failed"
            return (
                f'Local Whisper failed to load (provider: "local"): {detail}. '
                "Try a smaller model, or switch STT to Browser in Settings > Audio & Voice."
            )
        if reason == "ffmpeg_missing" or stats.get("ffmpeg") is False:
            return (
                "Local Whisper is loaded but ffmpeg is missing — browser mic audio "
                "(webm) cannot be decoded. Rebuild the Odysseus image (ffmpeg is in "
                "the Dockerfile) or run: apt-get install -y ffmpeg inside the container."
            )
    return (
        f'STT service is not available (provider: "{provider}"). '
        "Check Settings > Audio & Voice."
    )


def setup_stt_routes(stt_service):
    """Setup STT routes with the provided STT service"""
    router = APIRouter(prefix="/api/stt", tags=["stt"])

    @router.get("/stats")
    async def get_stt_stats():
        """Get STT service statistics"""
        try:
            # get_stats() can lazily import faster_whisper/torch and load the
            # Whisper model — a multi-minute blocking operation that must not
            # run on the event loop.
            return await run_in_threadpool(stt_service.get_stats)
        except Exception as e:
            logger.error(f"Failed to get STT stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/transcribe")
    async def transcribe_audio(file: UploadFile = File(...)):
        """Transcribe uploaded audio file to text"""
        try:
            # available/get_stats/transcribe may import torch and load the
            # Whisper model synchronously — keep them off the event loop.
            if not await run_in_threadpool(lambda: stt_service.available):
                stats = await run_in_threadpool(stt_service.get_stats)
                message = _stt_unavailable_message(stats)
                raise HTTPException(status_code=503, detail={"message": message})

            audio_bytes = await read_upload_limited(file, STT_MAX_AUDIO_BYTES, "Audio file")
            if not audio_bytes:
                raise HTTPException(status_code=400, detail={"message": "Empty audio file"})

            text = await run_in_threadpool(
                stt_service.transcribe,
                audio_bytes,
                content_type=file.content_type or "",
                filename=file.filename or "",
            )
            if text is None:
                stats = await run_in_threadpool(stt_service.get_stats)
                message = _stt_unavailable_message(stats)
                if stats.get("ffmpeg") is False or stats.get("reason") == "ffmpeg_missing":
                    raise HTTPException(status_code=503, detail={"message": message})
                hint = stats.get("hint") or stats.get("local_detail") or ""
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": (
                            "Transcription failed"
                            + (f" — {hint}" if hint else "")
                        )
                    },
                )

            return {"text": text}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"message": f"Transcription failed: {str(e)}"}
            )

    return router
