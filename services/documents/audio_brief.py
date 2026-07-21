"""CEO-level audio briefs for library documents.

Pipeline: document text → CEO brief (Odysseus LLM) → single-narrator audio
report via Open Notebook's podcast engine. When Open Notebook is not
configured or fails, status lands on "skipped" and the frontend reads the
brief aloud with browser speechSynthesis instead (same contract as the deep
research audio brief in services/research/audio_brief.py).

State per document lives at data/doc_audio_briefs/{doc_id}.json; the MP3 is
cached next to it at {doc_id}/chunk_000.mp3 so replays never re-hit Open
Notebook. The brief is invalidated when the document content changes
(content hash comparison on kickoff).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.constants import DOC_AUDIO_BRIEF_DIR

logger = logging.getLogger(__name__)

_DOC_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_MAX_DOC_CHARS = 24000
_MAX_BRIEF_CHARS = 6000

_BRIEF_SYSTEM = (
    "You write CEO-level audio briefs. You are given a document; produce a "
    "spoken executive report that a busy leader can absorb in 2-4 minutes "
    "(~400-700 words).\n"
    "Structure, in this order:\n"
    "1. Executive summary — what this document is and why it matters, in "
    "2-3 sentences.\n"
    "2. Key concepts and points — the core ideas, findings, or decisions, "
    "stated plainly.\n"
    "3. Next steps — concrete actions or recommendations implied by the "
    "document. If none exist, say what should happen next.\n"
    "Rules: plain spoken prose only. No markdown, no headings, no bullet "
    "symbols, no stage directions, no speaker labels — this is a single "
    "narrator reading aloud. Use transitions like 'First', 'Next', "
    "'Finally' instead of formatting. Stay grounded in the document; do "
    "not invent facts."
)


def _valid_doc_id(doc_id: str) -> bool:
    return isinstance(doc_id, str) and bool(_DOC_ID_RE.fullmatch(doc_id))


def _state_path(doc_id: str) -> Optional[Path]:
    if not _valid_doc_id(doc_id):
        return None
    root = Path(DOC_AUDIO_BRIEF_DIR)
    root.mkdir(parents=True, exist_ok=True)
    path = (root / f"{doc_id}.json").resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path


def _audio_dir(doc_id: str) -> Optional[Path]:
    if not _valid_doc_id(doc_id):
        return None
    root = Path(DOC_AUDIO_BRIEF_DIR)
    root.mkdir(parents=True, exist_ok=True)
    path = (root / doc_id).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def get_brief_state(doc_id: str) -> Dict[str, Any]:
    path = _state_path(doc_id)
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_brief_state(doc_id: str, patch: Dict[str, Any]) -> None:
    path = _state_path(doc_id)
    if path is None:
        return
    state = get_brief_state(doc_id)
    state.update(patch)
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write audio brief state for %s: %s", doc_id, e)


def read_brief_audio(doc_id: str, index: int) -> Optional[Tuple[bytes, str]]:
    state = get_brief_state(doc_id)
    if state.get("status") != "ready":
        return None
    chunk_count = int(state.get("chunk_count") or 0)
    if index < 0 or index >= chunk_count:
        return None
    audio_dir = _audio_dir(doc_id)
    if audio_dir is None:
        return None
    ext = state.get("ext") or "mp3"
    chunk_path = audio_dir / f"chunk_{index:03d}.{ext}"
    if not chunk_path.exists():
        return None
    return chunk_path.read_bytes(), state.get("mime") or "audio/mpeg"


def delete_brief(doc_id: str) -> None:
    path = _state_path(doc_id)
    if path is not None and path.exists():
        path.unlink(missing_ok=True)
    audio_dir = _audio_dir(doc_id)
    if audio_dir is not None and audio_dir.exists():
        shutil.rmtree(audio_dir, ignore_errors=True)


def _resolve_llm(owner: str = "") -> Tuple[str, str, dict]:
    from src.endpoint_resolver import resolve_endpoint

    for role in ("utility", "research", "default", "chat"):
        try:
            url, mdl, hdrs = resolve_endpoint(role, owner=owner or None)
        except Exception:
            continue
        if url and mdl:
            return url, mdl, hdrs or {}
    return "", "", {}


async def generate_ceo_brief(
    title: str,
    content: str,
    llm_endpoint: str,
    llm_model: str,
    llm_headers: Optional[dict] = None,
    owner: str = "",
) -> str:
    from src.endpoint_resolver import resolve_utility_fallback_candidates
    from src.llm_core import llm_call_async_with_fallback

    excerpt = (content or "")[:_MAX_DOC_CHARS]
    user_content = (
        f"Document title: {title or 'Untitled'}\n\n"
        f"Document:\n{excerpt}\n\n"
        "Write the CEO-level audio brief now."
    )
    messages = [
        {"role": "system", "content": _BRIEF_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    candidates = [(llm_endpoint, llm_model, llm_headers or {})]
    candidates += resolve_utility_fallback_candidates(owner=owner or None)
    raw = await llm_call_async_with_fallback(
        candidates,
        messages,
        temperature=0.4,
        max_tokens=2048,
        timeout=120,
    )
    brief = (raw or "").strip()
    if len(brief) > _MAX_BRIEF_CHARS:
        brief = brief[:_MAX_BRIEF_CHARS].rsplit(".", 1)[0].strip() + "."
    return brief


async def generate_doc_audio_brief(
    doc_id: str,
    title: str,
    content: str,
    owner: str = "",
) -> None:
    """Full pipeline for one document. Writes progress into the state file."""
    if _state_path(doc_id) is None:
        return
    doc_hash = content_hash(content)

    if not (content or "").strip():
        _write_brief_state(doc_id, {
            "status": "failed",
            "error": "Document has no text content",
            "generated_at": time.time(),
        })
        return

    _write_brief_state(doc_id, {
        "status": "generating",
        "error": None,
        "content_hash": doc_hash,
        "title": title or "Untitled",
    })

    llm_endpoint, llm_model, llm_headers = _resolve_llm(owner)
    if not llm_endpoint or not llm_model:
        _write_brief_state(doc_id, {
            "status": "failed",
            "error": "No LLM endpoint configured for brief generation",
            "generated_at": time.time(),
        })
        return

    try:
        brief = await generate_ceo_brief(
            title=title,
            content=content,
            llm_endpoint=llm_endpoint,
            llm_model=llm_model,
            llm_headers=llm_headers,
            owner=owner,
        )
    except Exception as e:
        logger.error("CEO brief generation failed for doc %s: %s", doc_id, e)
        _write_brief_state(doc_id, {
            "status": "failed",
            "error": f"Brief generation failed: {e}",
            "generated_at": time.time(),
        })
        return

    if not brief.strip():
        _write_brief_state(doc_id, {
            "status": "failed",
            "error": "Empty brief from LLM",
            "generated_at": time.time(),
        })
        return

    _write_brief_state(doc_id, {"script": brief})

    from services.open_notebook import (
        OpenNotebookClient,
        OpenNotebookError,
        open_notebook_configured,
    )

    if not open_notebook_configured():
        _write_brief_state(doc_id, {
            "status": "skipped",
            "error": "Open Notebook not configured — using browser voice",
            "generated_at": time.time(),
        })
        return

    try:
        client = OpenNotebookClient()
        episode_name = f"Brief: {(title or 'Untitled')[:60]}"
        audio, episode_id = await client.generate_brief_audio(episode_name, brief)
    except OpenNotebookError as e:
        logger.warning("Open Notebook audio failed for doc %s: %s", doc_id, e)
        # Brief exists — degrade to browser TTS instead of failing outright.
        _write_brief_state(doc_id, {
            "status": "skipped",
            "error": f"Open Notebook audio unavailable: {e}",
            "generated_at": time.time(),
        })
        return

    audio_dir = _audio_dir(doc_id)
    if audio_dir is None:
        _write_brief_state(doc_id, {
            "status": "failed",
            "error": "Invalid document id for audio storage",
            "generated_at": time.time(),
        })
        return
    if audio_dir.exists():
        shutil.rmtree(audio_dir, ignore_errors=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "chunk_000.mp3").write_bytes(audio)

    _write_brief_state(doc_id, {
        "status": "ready",
        "chunk_count": 1,
        "mime": "audio/mpeg",
        "ext": "mp3",
        "episode_id": episode_id,
        "error": None,
        "generated_at": time.time(),
    })
    logger.info("Audio brief ready for doc %s (episode %s)", doc_id, episode_id)


def kickoff_doc_audio_brief(
    doc_id: str,
    title: str,
    content: str,
    owner: str = "",
) -> Dict[str, Any]:
    """Idempotent fire-and-forget kickoff.

    Returns the current state. Reuses an existing brief when the document
    content is unchanged and the run is in-flight or finished usable
    (ready/skipped both give the client something to play).
    """
    state = get_brief_state(doc_id)
    doc_hash = content_hash(content)
    status = state.get("status")
    if state.get("content_hash") == doc_hash and status in (
        "generating",
        "ready",
        "skipped",
    ):
        return state

    _write_brief_state(doc_id, {
        "status": "generating",
        "error": None,
        "content_hash": doc_hash,
        "chunk_count": 0,
    })

    async def _run():
        try:
            await generate_doc_audio_brief(doc_id, title, content, owner)
        except Exception as e:
            logger.error(
                "Audio brief task crashed for doc %s: %s", doc_id, e, exc_info=True
            )
            _write_brief_state(doc_id, {
                "status": "failed",
                "error": str(e),
                "generated_at": time.time(),
            })

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())
    return get_brief_state(doc_id)
