# routes/stt_stream_routes.py
"""Streaming STT WebSocket — /api/stt/stream (Phase 2 of the voice rebuild).

Protocol (client -> server):
  {"type": "start", "sampleRate": 16000}   — begin a turn
  <binary frame>                            — 16-bit PCM mono @ sampleRate
  {"type": "stop"}                          — flush + final transcript, then close
  {"type": "cancel"}                        — discard buffer, no reply, close

Protocol (server -> client):
  {"type": "partial", "text": "..."}        — interim transcript (~every 1.5s of audio)
  {"type": "final", "text": "..."}          — transcript at stop
  {"type": "error", "message": "..."}       — actionable error, socket closes after

Only wired up when the configured STT provider is "local" (faster-whisper).
Other providers get an immediate error frame + close — batch
/api/stt/transcribe and the browser Web Speech API path are untouched.

Phase 2 note: transcription re-decodes the full accumulated PCM buffer on
every partial/final run (no true incremental/streaming decode yet). That's an
acceptable simplification for this phase — see docs/voice-rebuild-orchestration.md.
"""

from __future__ import annotations

import asyncio
import io
import logging
import struct
import time
import wave
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.voice.realtime_gateway import VoiceSessionRegistry
from src.auth_helpers import authenticate_websocket

logger = logging.getLogger(__name__)

# Cap buffered audio to ~60s at 16kHz/16-bit mono so a runaway client can't
# grow the server-side buffer without bound.
_MAX_BUFFER_SECONDS = 60
_PARTIAL_INTERVAL_SECONDS = 1.5

# Reuse the realtime gateway's per-user session-slot registry (Pipecat/
# LiveKit-style cap) instead of inventing a second one for this transport.
_stream_registry = VoiceSessionRegistry(max_per_user=3, ttl_seconds=300)


def _pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit PCM mono samples in a WAV container faster-whisper can read."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def setup_stt_stream_routes(stt_service) -> APIRouter:
    router = APIRouter(prefix="/api/stt", tags=["stt"])

    def _run_transcription(model, wav_bytes: bytes, language: str = "") -> str:
        """Blocking transcription call — run in a thread executor."""
        import tempfile
        from pathlib import Path

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                tmp_path = tmp.name
            kwargs = {}
            if language:
                kwargs["language"] = language
            segments, _info = model.transcribe(tmp_path, **kwargs)
            return " ".join(seg.text.strip() for seg in segments).strip()
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    @router.websocket("/stream")
    async def stt_stream(websocket: WebSocket):
        user = authenticate_websocket(websocket)
        if user is None:
            await websocket.close(code=4401)
            return

        settings = stt_service._load_settings()
        provider = settings.get("stt_provider", "disabled")
        if provider != "local":
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "message": (
                    f'Streaming STT requires the "local" provider (currently "{provider}"). '
                    "Choose Local (Whisper) in Settings > Audio & Voice."
                ),
            })
            await websocket.close(code=4400)
            return

        model = stt_service._get_whisper()
        if model is None:
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "message": (
                    "Local Whisper model is not available on the server "
                    "(faster-whisper missing or failed to load). Check server logs, "
                    "or switch STT provider in Settings > Audio & Voice."
                ),
            })
            await websocket.close(code=4400)
            return

        session_key = user or "anonymous"
        if not _stream_registry.try_acquire(session_key):
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "message": "Too many concurrent streaming STT connections — try again shortly.",
            })
            await websocket.close(code=4429)
            return

        await websocket.accept()

        sample_rate = 16000
        language = settings.get("stt_language", "")
        pcm_buffer = bytearray()
        cancelled = False
        last_partial_at = time.monotonic()
        loop = asyncio.get_event_loop()

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                text_frame = message.get("text")
                if text_frame is not None:
                    import json

                    try:
                        payload = json.loads(text_frame)
                    except ValueError:
                        continue
                    msg_type = payload.get("type")

                    if msg_type == "start":
                        sample_rate = int(payload.get("sampleRate") or 16000)
                        pcm_buffer.clear()
                        continue

                    if msg_type == "cancel":
                        cancelled = True
                        break

                    if msg_type == "stop":
                        final_text = ""
                        if pcm_buffer:
                            wav_bytes = _pcm16_to_wav_bytes(bytes(pcm_buffer), sample_rate)
                            final_text = await loop.run_in_executor(
                                None, _run_transcription, model, wav_bytes, language
                            )
                        await websocket.send_json({"type": "final", "text": final_text})
                        break

                    continue

                binary_frame = message.get("bytes")
                if binary_frame:
                    max_bytes = _MAX_BUFFER_SECONDS * sample_rate * 2
                    if len(pcm_buffer) + len(binary_frame) > max_bytes:
                        # Cap hit — drop the oldest audio rather than growing
                        # unbounded; keep the most recent ~60s.
                        overflow = len(pcm_buffer) + len(binary_frame) - max_bytes
                        del pcm_buffer[:overflow]
                    pcm_buffer.extend(binary_frame)

                    now = time.monotonic()
                    if now - last_partial_at >= _PARTIAL_INTERVAL_SECONDS and pcm_buffer:
                        last_partial_at = now
                        wav_bytes = _pcm16_to_wav_bytes(bytes(pcm_buffer), sample_rate)
                        partial_text = await loop.run_in_executor(
                            None, _run_transcription, model, wav_bytes, language
                        )
                        await websocket.send_json({"type": "partial", "text": partial_text})

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("stt stream error: %s", e, exc_info=True)
            try:
                await websocket.send_json({"type": "error", "message": "Streaming STT failed"})
            except Exception:
                pass
        finally:
            pcm_buffer.clear()
            try:
                if not cancelled:
                    await websocket.close()
                else:
                    await websocket.close(code=1000)
            except Exception:
                pass

    return router
