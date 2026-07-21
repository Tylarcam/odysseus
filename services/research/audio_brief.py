"""Podcast-style audio brief generation for completed deep research reports."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.constants import DEEP_RESEARCH_DIR

logger = logging.getLogger(__name__)

RESEARCH_AUDIO_DIR = Path(DEEP_RESEARCH_DIR) / "audio"
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,128}$")
_MAX_CHUNK_CHARS = 4500
_MAX_SCRIPT_CHARS = 4000

_BRIEF_SYSTEM = (
    "You write podcast-style audio briefs for deep research reports.\n"
    "Output ONLY dialogue lines in this exact format (no markdown, no stage directions):\n"
    "HOST: ...\n"
    "ANALYST: ...\n"
    "Keep it 3-4 minutes when read aloud (~600-900 words max).\n"
    "Host introduces the topic and asks clarifying questions.\n"
    "Analyst explains key findings, implications, and one actionable takeaway.\n"
    "Stay grounded in the provided report — do not invent facts."
)


def _research_json_path(session_id: str) -> Optional[Path]:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        return None
    root = Path(DEEP_RESEARCH_DIR).resolve()
    path = (Path(DEEP_RESEARCH_DIR) / f"{session_id}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def _audio_dir(session_id: str) -> Optional[Path]:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        return None
    root = RESEARCH_AUDIO_DIR.resolve()
    RESEARCH_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    path = (RESEARCH_AUDIO_DIR / session_id).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def _detect_audio_ext(data: bytes) -> Tuple[str, str]:
    is_mp3 = data[:3] == b"ID3" or (
        len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    )
    if is_mp3:
        return "audio/mpeg", "mp3"
    return "audio/wav", "wav"


def _tts_can_synthesize_server(tts_service) -> bool:
    settings = tts_service._load_settings()
    if settings.get("tts_enabled") is False:
        return False
    provider = settings.get("tts_provider", "disabled")
    if provider in ("disabled", "browser"):
        return False
    return bool(tts_service.available)


def _degrade_to_browser_voice(session_id: str, reason: str) -> None:
    """Keep the generated script and let the report UI fall back to browser TTS."""
    _write_audio_brief_meta(session_id, {
        "status": "skipped",
        "error": reason,
        "generated_at": time.time(),
    })


def resolve_llm_for_brief(entry: dict, owner: str = "") -> Tuple[str, str, dict]:
    ep = (entry.get("llm_endpoint") or "").strip()
    model = (entry.get("llm_model") or "").strip()
    headers = entry.get("llm_headers") or {}
    if ep and model:
        return ep, model, headers

    from src.endpoint_resolver import resolve_endpoint

    for role in ("utility", "research", "default", "chat"):
        try:
            url, mdl, hdrs = resolve_endpoint(role, owner=owner or None)
        except Exception:
            continue
        if url and mdl:
            return url, mdl, hdrs or {}
    return "", "", {}


def chunk_script_for_tts(script: str) -> List[str]:
    """Split dialogue script into TTS-safe chunks."""
    text = (script or "").strip()
    if not text:
        return []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    chunks: List[str] = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= _MAX_CHUNK_CHARS:
            current = candidate
        else:
            flush()
            if len(line) <= _MAX_CHUNK_CHARS:
                current = line
            else:
                start = 0
                while start < len(line):
                    chunks.append(line[start : start + _MAX_CHUNK_CHARS])
                    start += _MAX_CHUNK_CHARS
                current = ""

    flush()

    if not chunks and text:
        start = 0
        while start < len(text):
            chunks.append(text[start : start + _MAX_CHUNK_CHARS])
            start += _MAX_CHUNK_CHARS
    return chunks


async def generate_brief_script(
    query: str,
    report_md: str,
    llm_endpoint: str,
    llm_model: str,
    llm_headers: Optional[dict] = None,
) -> str:
    from src.llm_core import llm_call_async

    report_excerpt = (report_md or "")[:12000]
    user_content = (
        f"Research question: {query}\n\n"
        f"Report:\n{report_excerpt}\n\n"
        "Write the HOST/ANALYST podcast brief now."
    )
    messages = [
        {"role": "system", "content": _BRIEF_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    raw = await llm_call_async(
        url=llm_endpoint,
        model=llm_model,
        messages=messages,
        temperature=0.7,
        max_tokens=2048,
        headers=llm_headers or {},
        timeout=120,
    )
    script = (raw or "").strip()
    if len(script) > _MAX_SCRIPT_CHARS:
        script = script[:_MAX_SCRIPT_CHARS].rsplit("\n", 1)[0].strip()
    return script


def _write_audio_brief_meta(session_id: str, patch: Dict[str, Any]) -> None:
    path = _research_json_path(session_id)
    if path is None or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        brief = data.get("audio_brief") or {}
        brief.update(patch)
        data["audio_brief"] = brief
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to update audio_brief meta for %s: %s", session_id, e)


def get_audio_brief_meta(session_id: str) -> Optional[Dict[str, Any]]:
    path = _research_json_path(session_id)
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("audio_brief")
    except Exception:
        return None


def read_audio_chunk(session_id: str, index: int) -> Optional[Tuple[bytes, str]]:
    brief = get_audio_brief_meta(session_id)
    if not brief or brief.get("status") != "ready":
        return None
    chunk_count = int(brief.get("chunk_count") or 0)
    if index < 0 or index >= chunk_count:
        return None
    audio_dir = _audio_dir(session_id)
    if audio_dir is None:
        return None
    ext = brief.get("ext") or "mp3"
    chunk_path = audio_dir / f"chunk_{index:03d}.{ext}"
    if not chunk_path.exists():
        return None
    mime = brief.get("mime") or "audio/mpeg"
    return chunk_path.read_bytes(), mime


def delete_audio_brief_files(session_id: str) -> None:
    audio_dir = _audio_dir(session_id)
    if audio_dir is None:
        return
    if audio_dir.exists():
        shutil.rmtree(audio_dir, ignore_errors=True)


async def generate_audio_brief(
    session_id: str,
    tts_service,
    entry: dict,
) -> None:
    path = _research_json_path(session_id)
    if path is None or not path.exists():
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    if data.get("status") != "done":
        return

    report_md = data.get("raw_report") or data.get("result") or ""
    if not str(report_md).strip():
        _write_audio_brief_meta(session_id, {
            "status": "skipped",
            "error": "No report text available",
            "generated_at": time.time(),
        })
        return

    _write_audio_brief_meta(session_id, {"status": "generating", "error": None})

    owner = data.get("owner") or entry.get("owner") or ""
    llm_endpoint, llm_model, llm_headers = resolve_llm_for_brief(entry, owner)

    if not llm_endpoint or not llm_model:
        _write_audio_brief_meta(session_id, {
            "status": "failed",
            "error": "No LLM endpoint configured for audio brief script",
            "generated_at": time.time(),
        })
        return

    try:
        script = await generate_brief_script(
            query=data.get("query") or "",
            report_md=str(report_md),
            llm_endpoint=llm_endpoint,
            llm_model=llm_model,
            llm_headers=llm_headers,
        )
    except Exception as e:
        logger.error("Audio brief script generation failed for %s: %s", session_id, e)
        _write_audio_brief_meta(session_id, {
            "status": "failed",
            "error": f"Script generation failed: {e}",
            "generated_at": time.time(),
        })
        return

    if not script.strip():
        _write_audio_brief_meta(session_id, {
            "status": "failed",
            "error": "Empty audio brief script",
            "generated_at": time.time(),
        })
        return

    _write_audio_brief_meta(session_id, {"script": script})

    if not _tts_can_synthesize_server(tts_service):
        _write_audio_brief_meta(session_id, {
            "status": "skipped",
            "error": "Server TTS unavailable — use Listen for browser playback",
            "generated_at": time.time(),
        })
        return

    chunks = chunk_script_for_tts(script)
    if not chunks:
        _write_audio_brief_meta(session_id, {
            "status": "failed",
            "error": "Could not chunk script for TTS",
            "generated_at": time.time(),
        })
        return

    audio_dir = _audio_dir(session_id)
    if audio_dir is None:
        _write_audio_brief_meta(session_id, {
            "status": "failed",
            "error": "Invalid session id for audio storage",
            "generated_at": time.time(),
        })
        return

    if audio_dir.exists():
        shutil.rmtree(audio_dir, ignore_errors=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    mime = "audio/mpeg"
    ext = "mp3"
    saved = 0

    for i, chunk_text in enumerate(chunks):
        try:
            audio_bytes = await asyncio.to_thread(tts_service.synthesize, chunk_text)
        except Exception as e:
            logger.error("TTS chunk %s failed for %s: %s", i, session_id, e)
            _degrade_to_browser_voice(
                session_id,
                f"Server TTS failed on chunk {i + 1}: {e} — using browser voice",
            )
            return

        if not audio_bytes:
            detail = getattr(tts_service, "last_error", None) or "provider returned no audio"
            logger.error(
                "TTS chunk %s empty for %s (%s)",
                i,
                session_id,
                detail,
            )
            _degrade_to_browser_voice(
                session_id,
                f"Server TTS unavailable ({detail}) — using browser voice",
            )
            return

        if i == 0:
            mime, ext = _detect_audio_ext(audio_bytes)

        out_path = audio_dir / f"chunk_{i:03d}.{ext}"
        out_path.write_bytes(audio_bytes)
        saved += 1

    _write_audio_brief_meta(session_id, {
        "status": "ready",
        "chunk_count": saved,
        "mime": mime,
        "ext": ext,
        "error": None,
        "generated_at": time.time(),
    })
    logger.info("Audio brief ready for %s (%s chunks)", session_id, saved)


def kickoff_audio_brief(session_id: str, entry: dict, tts_service) -> None:
    """Fire-and-forget background audio brief generation."""
    if entry.get("status") != "done":
        return
    try:
        from services.tts import get_tts_service
        svc = tts_service or get_tts_service()
    except Exception:
        svc = tts_service
    if svc is None:
        return

    async def _run():
        try:
            await generate_audio_brief(session_id, svc, entry)
        except Exception as e:
            logger.error("Audio brief task crashed for %s: %s", session_id, e, exc_info=True)
            _write_audio_brief_meta(session_id, {
                "status": "failed",
                "error": str(e),
                "generated_at": time.time(),
            })

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())
