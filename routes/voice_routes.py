# routes/voice_routes.py
"""Realtime voice API — WebRTC session bootstrap (server-side API key)."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from services.voice.metrics import get_voice_metrics_store
from src.auth_helpers import effective_user, require_authenticated_request
from src.rate_limiter import RateLimiter
from src.settings import load_settings

logger = logging.getLogger(__name__)


class VoiceClientSecretResponse(BaseModel):
    value: str
    expires_at: Optional[int] = None
    session: Optional[dict] = None


class VoiceToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    call_id: Optional[str] = None


class VoiceTelemetryEvent(BaseModel):
    ts: Optional[int] = None
    event: str
    turnId: Optional[str] = None
    elapsedMs: Optional[int] = None
    model_config = {"extra": "allow"}


class VoiceTelemetryTurn(BaseModel):
    turnId: Optional[str] = None
    events: List[VoiceTelemetryEvent] = Field(default_factory=list, max_length=50)


class VoiceTelemetryRequest(BaseModel):
    turns: List[VoiceTelemetryTurn] = Field(default_factory=list, max_length=10)


class MicLeaseClaimRequest(BaseModel):
    holder: str = "odysseus"
    mode: str = ""
    ttl_sec: int = 90


class MicLeaseReleaseRequest(BaseModel):
    holder: str = "odysseus"
    token: Optional[str] = None


class VoiceCmdActionRequest(BaseModel):
    action: str
    id: Optional[str] = None


def _rate_limit_key(request: Request) -> str:
    user = effective_user(request) or "anonymous"
    ip = request.client.host if request.client else "unknown"
    return f"{user}:{ip}"


def setup_voice_routes(gateway):
    router = APIRouter(prefix="/api/voice", tags=["voice"])
    metrics = get_voice_metrics_store()

    connect_limit = int(os.getenv("VOICE_CONNECT_RATE_LIMIT", "10"))
    connect_window = int(os.getenv("VOICE_CONNECT_RATE_WINDOW", "60"))
    secret_limit = int(os.getenv("VOICE_SECRET_RATE_LIMIT", "5"))
    secret_window = int(os.getenv("VOICE_SECRET_RATE_WINDOW", "60"))
    telemetry_limit = int(os.getenv("VOICE_TELEMETRY_RATE_LIMIT", "30"))
    telemetry_window = int(os.getenv("VOICE_TELEMETRY_RATE_WINDOW", "60"))
    tool_limit = int(os.getenv("VOICE_TOOL_RATE_LIMIT", "20"))
    tool_window = int(os.getenv("VOICE_TOOL_RATE_WINDOW", "60"))

    _connect_limiter = RateLimiter(max_requests=connect_limit, window_seconds=connect_window)
    _secret_limiter = RateLimiter(max_requests=secret_limit, window_seconds=secret_window)
    _telemetry_limiter = RateLimiter(max_requests=telemetry_limit, window_seconds=telemetry_window)
    _tool_limiter = RateLimiter(max_requests=tool_limit, window_seconds=tool_window)

    def _settings():
        return load_settings()

    def _safety_id(request: Request) -> str:
        user = effective_user(request) or ""
        return gateway.safety_identifier(user)

    def _username(request: Request) -> str:
        return effective_user(request) or "anonymous"

    @router.get("/mic/status")
    async def mic_status():
        """Whether the default mic is leased (Clicky vs Odysseus web voice)."""
        from services.voice.mic_lease import get_status

        return get_status()

    @router.post("/mic/claim")
    async def mic_claim(body: MicLeaseClaimRequest, request: Request):
        """Claim the shared mic lease before browser capture starts."""
        require_authenticated_request(request)
        from services.voice.mic_lease import REALTIME_TTL_SEC, claim

        ttl = body.ttl_sec
        if body.mode == "realtime":
            ttl = max(ttl, REALTIME_TTL_SEC)
        result = claim(body.holder, mode=body.mode, ttl_sec=ttl)
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail=result)
        return result

    @router.post("/mic/release")
    async def mic_release(body: MicLeaseReleaseRequest, request: Request):
        """Release the shared mic lease after browser capture stops."""
        require_authenticated_request(request)
        from services.voice.mic_lease import release

        return release(body.holder, body.token)

    @router.get("/stats")
    async def voice_stats():
        """Realtime voice availability (no secrets)."""
        try:
            stats = gateway.get_stats(_settings())
            stats["slo"] = metrics.slo_summary()
            return stats
        except Exception as e:
            logger.error("voice stats error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/vault-brief")
    async def voice_vault_brief(request: Request):
        """Compact live vault briefing for Jarvis / Realtime system context."""
        require_authenticated_request(request)
        from services.voice.vault_brief import build_vault_brief

        owner = effective_user(request)
        try:
            return build_vault_brief(owner)
        except Exception as e:
            logger.error("voice vault-brief error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail={"message": str(e)})

    @router.post("/cmd-action")
    async def voice_cmd_action(body: VoiceCmdActionRequest, request: Request):
        """Validate a CMD Center navigate action; execute human-send confirms."""
        require_authenticated_request(request)
        from services.voice.voice_tools import (
            CONFIRM_SEND_ACTIONS,
            confirm_human_send,
            resolve_cmd_action,
        )

        resolved = resolve_cmd_action(body.action, body.id)
        if not resolved.get("ok"):
            raise HTTPException(status_code=400, detail={"message": resolved.get("error")})
        if resolved.get("action") in CONFIRM_SEND_ACTIONS:
            result = confirm_human_send(resolved["action"], owner=effective_user(request))
            if not result.get("ok"):
                raise HTTPException(
                    status_code=400,
                    detail={"message": result.get("error") or "could not log send"},
                )
            logger.info(
                "voice cmd-action confirm user=%s action=%s id=%s submit=false",
                _username(request),
                result.get("action"),
                result.get("id") or "",
            )
            return {**resolved, **result}
        logger.info(
            "voice cmd-action user=%s action=%s id=%s",
            _username(request),
            resolved.get("action"),
            resolved.get("id") or "",
        )
        return resolved

    @router.get("/slo")
    async def voice_slo():
        """Aggregate voice latency SLO summary (no PII)."""
        return metrics.slo_summary()

    @router.post("/telemetry")
    async def voice_telemetry(body: VoiceTelemetryRequest, request: Request):
        """Ingest batched client voice telemetry for SLO histograms."""
        require_authenticated_request(request)
        if not _telemetry_limiter.check(_rate_limit_key(request)):
            raise HTTPException(
                status_code=429,
                detail={"message": "Too many telemetry posts — try again later"},
            )

        turn_events: List[List[Dict[str, Any]]] = []
        for turn in body.turns:
            if not turn.events:
                continue
            turn_events.append([ev.model_dump() for ev in turn.events])

        if not turn_events:
            return {"recorded": 0, "slo": metrics.slo_summary()}

        recorded = metrics.ingest_batch(turn_events)
        logger.debug("voice telemetry user=%s turns=%s", _username(request), recorded)
        return {"recorded": recorded, "slo": metrics.slo_summary()}

    @router.post("/tool-call")
    async def voice_tool_call(body: VoiceToolCallRequest, request: Request):
        """Execute one whitelisted tool for a realtime voice function call."""
        require_authenticated_request(request)
        if not _tool_limiter.check(_rate_limit_key(request)):
            raise HTTPException(
                status_code=429,
                detail={"message": "Too many voice tool calls — try again later"},
            )

        settings = _settings()
        if not gateway.tools_enabled(settings) or not settings.get("voice_chat_enabled", True):
            raise HTTPException(
                status_code=403,
                detail={"message": "Voice tools are disabled in Settings"},
            )

        from services.voice.voice_tools import execute_voice_tool

        owner = effective_user(request)
        try:
            output = await execute_voice_tool(body.name, body.arguments, owner=owner)
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"message": str(e)})
        except Exception as e:
            logger.error("voice tool-call error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail={"message": str(e)})

        logger.info(
            "voice tool-call user=%s tool=%s chars=%s",
            _username(request), body.name, len(output),
        )
        return {"name": body.name, "call_id": body.call_id, "output": output}

    @router.post("/client-secret", response_model=VoiceClientSecretResponse)
    async def voice_client_secret(request: Request):
        """Mint ephemeral client secret for browser-direct WebRTC (ek_* token only)."""
        require_authenticated_request(request)
        if not _secret_limiter.check(_rate_limit_key(request)):
            raise HTTPException(
                status_code=429,
                detail={"message": "Too many voice token requests — try again later"},
            )
        try:
            if not gateway.available:
                raise HTTPException(
                    status_code=503,
                    detail={"message": "Realtime voice unavailable — set OPENAI_API_KEY"},
                )
            data = await gateway.create_client_secret(
                _settings(),
                _safety_id(request),
                username=_username(request),
            )
            return VoiceClientSecretResponse(
                value=data.get("value", ""),
                expires_at=data.get("expires_at"),
                session=data.get("session"),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("voice client-secret error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail={"message": str(e)})

    @router.post("/connect", response_class=PlainTextResponse)
    async def voice_connect(request: Request):
        """WebRTC unified interface — POST SDP offer, receive SDP answer."""
        require_authenticated_request(request)
        if not _connect_limiter.check(_rate_limit_key(request)):
            raise HTTPException(
                status_code=429,
                detail={"message": "Too many voice connect attempts — try again later"},
            )
        try:
            if not gateway.available:
                raise HTTPException(
                    status_code=503,
                    detail={"message": "Realtime voice unavailable — set OPENAI_API_KEY"},
                )

            content_type = (request.headers.get("content-type") or "").lower()
            if "application/sdp" in content_type or "text/plain" in content_type:
                sdp_body = (await request.body()).decode("utf-8", errors="replace")
            else:
                raise HTTPException(
                    status_code=415,
                    detail={"message": "Send SDP offer as application/sdp or text/plain"},
                )

            # CMD Jarvis / agent mode: client sends X-Voice-Agent-Bridge so the
            # initial Realtime session never auto-answers or seeds voice tools.
            bridge_hdr = (request.headers.get("x-voice-agent-bridge") or "").strip()
            agent_bridge = bridge_hdr in ("1", "true", "yes")
            answer = await gateway.connect_webrtc(
                sdp_body,
                _settings(),
                _safety_id(request),
                username=_username(request),
                agent_bridge=agent_bridge,
            )
            return PlainTextResponse(content=answer, media_type="application/sdp")
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"message": str(e)})
        except RuntimeError as e:
            msg = str(e)
            if "session limit" in msg.lower():
                raise HTTPException(status_code=429, detail={"message": msg})
            raise HTTPException(status_code=502, detail={"message": msg})
        except Exception as e:
            logger.error("voice connect error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail={"message": str(e)})

    return router
