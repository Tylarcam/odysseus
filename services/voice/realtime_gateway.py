# services/voice/realtime_gateway.py
"""OpenAI Realtime API gateway — ephemeral tokens and WebRTC SDP proxy.

API keys stay server-side. Browsers connect via WebRTC using either:
  - POST /api/voice/connect (unified interface — recommended)
  - POST /api/voice/client-secret + client-side SDP to OpenAI
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-realtime-preview-2024-12-17"
DEFAULT_VOICE = "alloy"

DEFAULT_VOICE_INSTRUCTIONS = (
    "You are Odysseus, the user's personal AI assistant, speaking with them by voice. "
    "Be warm, natural, and conversational. Keep answers short — one to three sentences "
    "unless the user asks for depth. Never read out markdown, URLs, code, or lists "
    "verbatim; summarize them in plain speech."
)

_TOOLS_INSTRUCTIONS = (
    "You have tools: web search, fetching a URL, and the user's notes/todos, "
    "calendar, and memory. Use them whenever they'd give a better answer — "
    "current events, the user's schedule, their todo list, saving a fact. "
    "While a tool runs, say a brief natural filler like 'let me check'. "
    "For shell commands, past chat search, email, documents, or deep research, "
    "tell the user to enable agent voice (CMD Center Audio I/O or agent mode)."
)

_NO_TOOLS_INSTRUCTIONS = (
    "If a task needs tools (email, calendar, documents, web research), "
    "tell the user to switch to agent mode for that."
)

_JARVIS_INSTRUCTIONS = (
    "When armed from CMD Center you are Jarvis for the Odysseus vault. "
    "Answer status questions from the vault brief. Prefer tools for lookups: "
    "list_handoffs for Agent Bin / Relay, manage_notes for todos/checklists, "
    "list_emails/read_email for mail, cmd_navigate to open vault surfaces. "
    "Draft email replies via agent bridge (confirm before send). "
    "For multi-step vault actions (claim handoffs, jobs tailor, research start, email send), "
    "the session may bridge into full agent mode — speak results briefly."
)

# Keep injected memory context well under realtime session limits.
_MAX_MEMORY_FACTS = 20
_MAX_INSTRUCTIONS_CHARS = 4000


def _load_pinned_memory_facts(owner: Optional[str]) -> List[str]:
    """Pinned user facts from memory.json, best-effort (never blocks connect)."""
    try:
        from src.constants import DATA_DIR
        from src.memory import MemoryManager

        # Single-user installs (auth off) have no meaningful owner — load all.
        effective_owner = None if not owner or owner == "anonymous" else owner
        entries = MemoryManager(DATA_DIR).load(owner=effective_owner)
        return [
            (e.get("text") or "").strip()
            for e in entries
            if e.get("pinned") and (e.get("text") or "").strip()
        ][:_MAX_MEMORY_FACTS]
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("voice: failed to load pinned memories: %s", e)
        return []


class VoiceSessionRegistry:
    """In-memory per-user voice session slots with TTL auto-expiry."""

    def __init__(self, max_per_user: int = 2, ttl_seconds: int = 3600) -> None:
        self.max_per_user = max(1, max_per_user)
        self.ttl_seconds = max(60, ttl_seconds)
        self._sessions: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _purge_stale(self, user: str, now: float) -> List[float]:
        cutoff = now - self.ttl_seconds
        active = [t for t in self._sessions.get(user, []) if t > cutoff]
        if active:
            self._sessions[user] = active
        elif user in self._sessions:
            del self._sessions[user]
        return active

    def try_acquire(self, user: str) -> bool:
        """Register a new session if under per-user limit."""
        key = (user or "anonymous").strip() or "anonymous"
        now = time.monotonic()
        with self._lock:
            active = self._purge_stale(key, now)
            if len(active) >= self.max_per_user:
                return False
            active.append(now)
            self._sessions[key] = active
            return True

    def active_count(self, user: str) -> int:
        key = (user or "anonymous").strip() or "anonymous"
        now = time.monotonic()
        with self._lock:
            return len(self._purge_stale(key, now))

    def total_active(self) -> int:
        now = time.monotonic()
        with self._lock:
            total = 0
            for user in list(self._sessions.keys()):
                total += len(self._purge_stale(user, now))
            return total


class RealtimeVoiceGateway:
    """Thin gateway to OpenAI Realtime (WebRTC)."""

    def __init__(self) -> None:
        self.api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        base = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.base_url = base
        # Optional region-specific base (e.g. Azure/OpenAI regional endpoint).
        self.realtime_base_url = (
            os.getenv("VOICE_REALTIME_BASE_URL") or self.base_url
        ).rstrip("/")
        self.default_model = (os.getenv("VOICE_REALTIME_MODEL") or DEFAULT_MODEL).strip()
        self.timeout = float(os.getenv("VOICE_REALTIME_TIMEOUT", "30"))
        max_sessions = int(os.getenv("VOICE_MAX_SESSIONS_PER_USER", "2"))
        session_ttl = int(os.getenv("VOICE_SESSION_TTL_SECONDS", "3600"))
        self.session_registry = VoiceSessionRegistry(
            max_per_user=max_sessions,
            ttl_seconds=session_ttl,
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self, safety_id: Optional[str] = None) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if safety_id:
            headers["OpenAI-Safety-Identifier"] = safety_id
        return headers

    @staticmethod
    def safety_identifier(username: str) -> str:
        """Stable privacy-preserving user id for OpenAI safety header."""
        raw = (username or "anonymous").encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def build_voice_instructions(
        self,
        settings: Optional[dict] = None,
        owner: Optional[str] = None,
        *,
        include_vault_brief: bool = True,
        vault_brief_markdown: Optional[str] = None,
        jarvis: bool = False,
    ) -> str:
        """Persona + tool guidance + pinned memory (+ optional vault brief)."""
        settings = settings or {}
        base = (
            (settings.get("voice_realtime_instructions") or "").strip()
            or DEFAULT_VOICE_INSTRUCTIONS
        )
        parts = [base]
        if jarvis:
            parts.append(_JARVIS_INSTRUCTIONS)
        if self.tools_enabled(settings):
            parts.append(_TOOLS_INSTRUCTIONS)
        else:
            parts.append(_NO_TOOLS_INSTRUCTIONS)
        facts = _load_pinned_memory_facts(owner)
        if facts:
            facts_text = "\n".join(f"- {f}" for f in facts)
            parts.append(
                "Known facts about the user (from their saved memory — use them "
                f"naturally, don't recite them):\n{facts_text}"
            )
        if include_vault_brief:
            brief = (vault_brief_markdown or "").strip()
            if not brief:
                try:
                    from services.voice.vault_brief import build_vault_brief

                    brief = (build_vault_brief(owner).get("markdown") or "").strip()
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning("voice: vault brief failed: %s", e)
                    brief = ""
            if brief:
                parts.append(brief)
        instructions = "\n\n".join(parts)
        return instructions[:_MAX_INSTRUCTIONS_CHARS]

    @staticmethod
    def tools_enabled(settings: Optional[dict] = None) -> bool:
        return bool((settings or {}).get("voice_tools_enabled", True))

    def build_session_config(
        self,
        settings: Optional[dict] = None,
        owner: Optional[str] = None,
        include_instructions: bool = True,
        *,
        agent_bridge: bool = False,
    ) -> Dict[str, Any]:
        settings = settings or {}
        model = (settings.get("voice_realtime_model") or "").strip() or self.default_model
        voice = (
            (settings.get("voice_realtime_voice") or "").strip()
            or (settings.get("tts_voice") or "").strip()
            or DEFAULT_VOICE
        )
        vad_type = (
            (settings.get("voice_realtime_turn_detection") or "").strip()
            or os.getenv("VOICE_REALTIME_TURN_DETECTION", "server_vad").strip()
            or "server_vad"
        )
        if vad_type not in ("server_vad", "semantic_vad"):
            vad_type = "server_vad"
        silence_ms = int(settings.get("voice_realtime_silence_ms") or 500)
        silence_ms = max(200, min(silence_ms, 2000))
        threshold = float(settings.get("voice_realtime_vad_threshold") or 0.5)
        threshold = max(0.1, min(threshold, 1.0))
        transcription_model = (
            (settings.get("voice_realtime_transcription_model") or "").strip()
            or "whisper-1"
        )
        # Default create_response=False so the session does not auto-answer
        # before the client session.update lands. Agent/Jarvis bridge keeps it
        # false (tools run in the Odysseus agent loop). Native voice re-enables
        # create_response from the client after the data channel opens.
        turn_detection: Dict[str, Any] = {
            "type": vad_type,
            "threshold": threshold,
            "prefix_padding_ms": 300,
            "silence_duration_ms": silence_ms,
            "create_response": False,
            "interrupt_response": True,
        }
        config: Dict[str, Any] = {
            "type": "realtime",
            "model": model,
            "modalities": ["text", "audio"],
            "audio": {
                "output": {"voice": voice},
            },
            "input_audio_transcription": {
                "model": transcription_model,
            },
            "turn_detection": turn_detection,
        }
        if include_instructions:
            # Always ground Realtime in the live vault brief + Jarvis persona
            # when an owner is known (CMD arm and normal voice share the path).
            config["instructions"] = self.build_voice_instructions(
                settings,
                owner=owner,
                jarvis=True,
                include_vault_brief=True,
            )
            # Agent bridge owns tools via the chat agent loop — never seed
            # Realtime function tools for that path (avoids dual-brain race).
            if not agent_bridge and self.tools_enabled(settings):
                try:
                    from services.voice.voice_tools import get_voice_tool_schemas

                    tools = get_voice_tool_schemas()
                    if tools:
                        config["tools"] = tools
                        config["tool_choice"] = "auto"
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning("voice: failed to load tool schemas: %s", e)
        return config

    def get_stats(self, settings: Optional[dict] = None) -> Dict[str, Any]:
        settings = settings or {}
        chat_enabled = settings.get("voice_chat_enabled", True)
        enabled = settings.get("voice_realtime_enabled", True)
        # /api/voice/stats is public — never build (or leak) memory-backed instructions.
        session = self.build_session_config(settings, include_instructions=False)
        return {
            "available": self.available and enabled and chat_enabled,
            "enabled": enabled,
            "voice_chat_enabled": chat_enabled,
            "provider": "openai_realtime",
            "model": session["model"],
            "voice": session["audio"]["output"]["voice"],
            "turn_detection": session.get("turn_detection"),
            "input_audio_transcription": session.get("input_audio_transcription"),
            "transport": "webrtc",
            "tools_enabled": self.tools_enabled(settings),
            "region_base_url": self.realtime_base_url,
            "max_sessions_per_user": self.session_registry.max_per_user,
            "active_sessions": self.session_registry.total_active(),
        }

    async def create_client_secret(
        self,
        settings: Optional[dict] = None,
        safety_id: Optional[str] = None,
        *,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.available:
            raise RuntimeError("Realtime voice not configured (missing OPENAI_API_KEY)")

        session = self.build_session_config(settings, owner=username)
        payload = {"session": session}
        url = f"{self.realtime_base_url}/realtime/client_secrets"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url,
                headers={**self._headers(safety_id), "Content-Type": "application/json"},
                json=payload,
            )

        if resp.status_code >= 400:
            logger.error("client_secrets failed: %s %s", resp.status_code, resp.text[:500])
            raise RuntimeError(f"Failed to create realtime client secret ({resp.status_code})")

        data = resp.json()
        if not data.get("value"):
            raise RuntimeError("Realtime client secret response missing value")
        return data

    async def connect_webrtc(
        self,
        sdp_offer: str,
        settings: Optional[dict] = None,
        safety_id: Optional[str] = None,
        *,
        username: Optional[str] = None,
        agent_bridge: bool = False,
    ) -> str:
        """Unified WebRTC interface — proxy SDP offer, return SDP answer."""
        if not self.available:
            raise RuntimeError("Realtime voice not configured (missing OPENAI_API_KEY)")

        if username is not None and not self.session_registry.try_acquire(username):
            raise RuntimeError(
                f"Voice session limit reached ({self.session_registry.max_per_user} per user)"
            )

        offer = (sdp_offer or "").strip()
        if not offer:
            raise ValueError("SDP offer is required")

        session = self.build_session_config(
            settings, owner=username, agent_bridge=agent_bridge
        )
        url = f"{self.realtime_base_url}/realtime/calls"

        files = {
            "sdp": (None, offer, "application/sdp"),
            "session": (None, json.dumps(session), "application/json"),
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(safety_id), files=files)

        if resp.status_code >= 400:
            logger.error("realtime/calls failed: %s %s", resp.status_code, resp.text[:500])
            raise RuntimeError(f"Realtime WebRTC negotiation failed ({resp.status_code})")

        answer = (resp.text or "").strip()
        if not answer:
            raise RuntimeError("Realtime WebRTC negotiation returned empty SDP answer")

        logger.info(
            "voice connect ok user=%s active=%s",
            username or "unknown",
            self.session_registry.active_count(username or ""),
        )
        return answer


_gateway: Optional[RealtimeVoiceGateway] = None


def get_realtime_voice_gateway() -> RealtimeVoiceGateway:
    global _gateway
    if _gateway is None:
        _gateway = RealtimeVoiceGateway()
    return _gateway
